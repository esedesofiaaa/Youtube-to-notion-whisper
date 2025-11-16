"""
ProcessingCoordinator - Coordinación del procesamiento de videos
Responsabilidades:
- Ejecutar canales secuencialmente
- Coordinar con DiscordToDrive.py
- Manejar estado de procesamiento
- Reportar progreso
"""

import sys
import subprocess
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone

# Importar dependencias del sistema
sys.path.append(str(Path(__file__).parent.parent))
from utils.json_generator import JSONGenerator
from utils.error_handler import ErrorHandler, ErrorCategory, ErrorSeverity


class DiscordToDriveExecutor:
    """Ejecuta DiscordToDrive.py y maneja la comunicación"""
    
    def __init__(self, script_path: str, error_handler: ErrorHandler):
        """
        Inicializa el ejecutor
        
        Args:
            script_path: Ruta al script DiscordToDrive.py
            error_handler: Manejador de errores
        """
        self.script_path = Path(script_path)
        self.error_handler = error_handler
        self.logger = error_handler.logger
        
        # Verificar que el script existe
        if not self.script_path.exists():
            raise FileNotFoundError(f"DiscordToDrive.py no encontrado: {script_path}")
    
    def create_compatible_json(self, channel_json_path: str, 
                             temp_dir: str = "./temp") -> str:
        """
        Crea un LinksYT.json compatible con DiscordToDrive.py
        
        Args:
            channel_json_path: Ruta del JSON del canal
            temp_dir: Directorio para archivos temporales
            
        Returns:
            Ruta del archivo LinksYT.json temporal
        """
        try:
            # Crear directorio temporal
            temp_path = Path(temp_dir)
            temp_path.mkdir(exist_ok=True)
            
            # Leer JSON del canal
            with open(channel_json_path, 'r', encoding='utf-8') as f:
                channel_data = json.load(f)
            
            # Extraer videos pendientes
            pending_videos = []
            for video in channel_data.get("videos", []):
                if not video.get("processing_status", {}).get("fully_completed", False):
                    pending_videos.append(video["youtube_url"])
            
            if not pending_videos:
                self.logger.info(f"ℹ️ No hay videos pendientes en {Path(channel_json_path).name}")
                return None
            
            # Crear estructura compatible
            compatible_data = {
                "parent_folder_id": channel_data["metadata"]["drive_folder_id"],
                "video_urls": pending_videos
            }
            
            # Crear archivo temporal
            temp_file = temp_path / "LinksYT.json"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(compatible_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"📄 JSON temporal creado: {len(pending_videos)} videos para procesar")
            return str(temp_file)
            
        except Exception as e:
            self.error_handler.handle_error(
                e, ErrorCategory.FILE_SYSTEM,
                context={"operation": "create_compatible_json", "file": channel_json_path}
            )
            return None
    
    def execute_discord_to_drive(self, working_dir: str = ".") -> Tuple[int, str, str]:
        """
        Ejecuta DiscordToDrive.py como subprocess
        
        Args:
            working_dir: Directorio de trabajo para la ejecución
            
        Returns:
            Tupla (código_retorno, stdout, stderr)
        """
        try:
            self.logger.info(f"🚀 Ejecutando DiscordToDrive.py...")
            start_time = time.time()
            
            # Ejecutar como subprocess
            result = subprocess.run(
                ["python", str(self.script_path)],
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=3600  # Timeout de 1 hora
            )
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Log del resultado
            if result.returncode == 0:
                self.logger.info(f"✅ DiscordToDrive.py completado exitosamente ({duration:.1f}s)")
            else:
                self.logger.error(f"❌ DiscordToDrive.py falló con código {result.returncode} ({duration:.1f}s)")
            
            # Log de output (solo últimas líneas para no saturar)
            if result.stdout:
                stdout_lines = result.stdout.strip().split('\n')
                for line in stdout_lines[-10:]:  # Últimas 10 líneas
                    if line.strip():
                        self.logger.info(f"📝 DiscordToDrive: {line.strip()}")
            
            if result.stderr and result.returncode != 0:
                stderr_lines = result.stderr.strip().split('\n')
                for line in stderr_lines[-5:]:  # Últimas 5 líneas de error
                    if line.strip():
                        self.logger.error(f"🔴 DiscordToDrive Error: {line.strip()}")
            
            return result.returncode, result.stdout, result.stderr
            
        except subprocess.TimeoutExpired:
            self.error_handler.handle_error(
                Exception("DiscordToDrive.py timeout después de 1 hora"),
                ErrorCategory.SUBPROCESS,
                context={"operation": "execute_discord_to_drive", "timeout": 3600}
            )
            return -1, "", "Timeout después de 1 hora"
            
        except Exception as e:
            self.error_handler.handle_error(
                e, ErrorCategory.SUBPROCESS,
                context={"operation": "execute_discord_to_drive"}
            )
            return -1, "", str(e)
    
    def cleanup_temp_files(self, temp_dir: str = "./temp") -> None:
        """Limpia archivos temporales"""
        try:
            temp_path = Path(temp_dir)
            if temp_path.exists():
                for file in temp_path.glob("LinksYT.json"):
                    file.unlink()
                    self.logger.info(f"🗑️ Archivo temporal eliminado: {file.name}")
                
                # Eliminar directorio si está vacío
                if not any(temp_path.iterdir()):
                    temp_path.rmdir()
                    self.logger.info(f"🗑️ Directorio temporal eliminado: {temp_dir}")
        except Exception as e:
            self.logger.warning(f"⚠️ Error limpiando archivos temporales: {e}")


class ProcessingCoordinator:
    """Coordina el procesamiento secuencial de canales"""
    
    def __init__(self, json_generator: JSONGenerator, 
                 executor: DiscordToDriveExecutor,
                 error_handler: ErrorHandler):
        """
        Inicializa el coordinador de procesamiento
        
        Args:
            json_generator: Generador de archivos JSON
            executor: Ejecutor de DiscordToDrive.py
            error_handler: Manejador de errores
        """
        self.json_generator = json_generator
        self.executor = executor
        self.error_handler = error_handler
        self.logger = error_handler.logger
        
        # Estadísticas de procesamiento
        self.stats = {
            "channels_processed": 0,
            "channels_completed": 0,
            "channels_failed": 0,
            "total_videos_processed": 0,
            "total_videos_completed": 0,
            "total_videos_failed": 0,
            "processing_errors": [],
            "start_time": None,
            "end_time": None
        }
    
    def process_all_channels(self, channel_json_files: List[str]) -> Dict[str, Any]:
        """
        Procesa todos los canales secuencialmente
        
        Args:
            channel_json_files: Lista de rutas de archivos JSON por canal
            
        Returns:
            Estadísticas del procesamiento
        """
        self.stats["start_time"] = datetime.now(timezone.utc)
        
        self.error_handler.log_operation_start(
            f"Procesamiento secuencial de {len(channel_json_files)} canales"
        )
        
        try:
            for i, channel_file in enumerate(channel_json_files, 1):
                try:
                    channel_name = Path(channel_file).stem.replace('_youtube_videos', '')
                    
                    self.logger.info(f"\n{'='*60}")
                    self.logger.info(f"📺 PROCESANDO CANAL {i}/{len(channel_json_files)}: {channel_name}")
                    self.logger.info(f"{'='*60}")
                    
                    # Procesar canal individual
                    success = self._process_single_channel(channel_file)
                    
                    if success:
                        self.stats["channels_completed"] += 1
                        self.logger.info(f"✅ Canal '{channel_name}' completado exitosamente")
                    else:
                        self.stats["channels_failed"] += 1
                        self.logger.error(f"❌ Canal '{channel_name}' falló en el procesamiento")
                    
                    self.stats["channels_processed"] += 1
                    
                    # Progreso general
                    self.error_handler.log_progress(
                        i, len(channel_json_files), 
                        f"Procesando canales ({self.stats['channels_completed']} completados)"
                    )
                    
                except Exception as e:
                    self.error_handler.handle_error(
                        e, ErrorCategory.PROCESSING,
                        context={"channel_file": channel_file, "channel_index": i}
                    )
                    self.stats["channels_failed"] += 1
                    self.stats["processing_errors"].append({
                        "channel": channel_file,
                        "error": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    continue
            
            self.stats["end_time"] = datetime.now(timezone.utc)
            
            # Resumen final
            self._print_final_summary()
            
            self.error_handler.log_operation_success(
                "Procesamiento de todos los canales",
                context={
                    "total_channels": len(channel_json_files),
                    "completed": self.stats["channels_completed"],
                    "failed": self.stats["channels_failed"]
                }
            )
            
            return self.stats
            
        except Exception as e:
            self.error_handler.handle_error(
                e, ErrorCategory.PROCESSING,
                context={"operation": "process_all_channels"}
            )
            raise
    
    def _process_single_channel(self, channel_json_path: str) -> bool:
        """
        Procesa un canal individual
        
        Args:
            channel_json_path: Ruta del archivo JSON del canal
            
        Returns:
            True si el procesamiento fue exitoso
        """
        try:
            # Verificar si hay videos pendientes
            pending_videos = self.json_generator.get_pending_videos(channel_json_path)
            
            if not pending_videos:
                self.logger.info("ℹ️ No hay videos pendientes en este canal")
                return True
            
            self.logger.info(f"📋 {len(pending_videos)} videos pendientes de procesamiento")
            
            # Crear JSON temporal compatible
            temp_json = self.executor.create_compatible_json(channel_json_path)
            
            if not temp_json:
                self.logger.warning("⚠️ No se pudo crear JSON temporal")
                return False
            
            try:
                # Ejecutar DiscordToDrive.py
                return_code, stdout, stderr = self.executor.execute_discord_to_drive()
                
                # Actualizar estado basado en resultado
                if return_code == 0:
                    # Marcar todos los videos pendientes como completados
                    self._mark_videos_completed(channel_json_path, pending_videos)
                    self.stats["total_videos_completed"] += len(pending_videos)
                    return True
                else:
                    # Marcar videos como fallidos
                    self._mark_videos_failed(channel_json_path, pending_videos, 
                                           f"DiscordToDrive.py failed with code {return_code}")
                    self.stats["total_videos_failed"] += len(pending_videos)
                    return False
                    
            finally:
                # Limpiar archivos temporales
                self.executor.cleanup_temp_files()
                
        except Exception as e:
            self.logger.error(f"❌ Error procesando canal: {e}")
            return False
    
    def _mark_videos_completed(self, channel_json_path: str, 
                             videos: List[Dict[str, Any]]) -> None:
        """Marca videos como completados"""
        for video in videos:
            try:
                self.json_generator.mark_video_completed(
                    channel_json_path, 
                    video["youtube_url"]
                )
                self.stats["total_videos_processed"] += 1
            except Exception as e:
                self.logger.warning(f"⚠️ Error marcando video como completado: {e}")
    
    def _mark_videos_failed(self, channel_json_path: str, 
                          videos: List[Dict[str, Any]], 
                          error_message: str) -> None:
        """Marca videos como fallidos"""
        for video in videos:
            try:
                self.json_generator.mark_video_failed(
                    channel_json_path, 
                    video["youtube_url"],
                    error_message
                )
                self.stats["total_videos_processed"] += 1
            except Exception as e:
                self.logger.warning(f"⚠️ Error marcando video como fallido: {e}")
    
    def _print_final_summary(self):
        """Imprime resumen final del procesamiento"""
        if self.stats["start_time"] and self.stats["end_time"]:
            duration = self.stats["end_time"] - self.stats["start_time"]
            duration_str = str(duration).split('.')[0]  # Remover microsegundos
        else:
            duration_str = "N/A"
        
        print("\n" + "="*70)
        print("🏁 RESUMEN FINAL DE PROCESAMIENTO")
        print("="*70)
        
        print(f"⏱️ Duración total: {duration_str}")
        print(f"📺 Canales procesados: {self.stats['channels_processed']}")
        print(f"✅ Canales completados: {self.stats['channels_completed']}")
        print(f"❌ Canales fallidos: {self.stats['channels_failed']}")
        print(f"📹 Videos procesados: {self.stats['total_videos_processed']}")
        print(f"✅ Videos completados: {self.stats['total_videos_completed']}")
        print(f"❌ Videos fallidos: {self.stats['total_videos_failed']}")
        
        if self.stats["processing_errors"]:
            print(f"\n⚠️ Errores de procesamiento: {len(self.stats['processing_errors'])}")
            for error in self.stats["processing_errors"][-3:]:  # Últimos 3 errores
                channel_name = Path(error["channel"]).stem
                print(f"   └── {channel_name}: {error['error'][:50]}...")
        
        # Calcular tasa de éxito
        if self.stats["channels_processed"] > 0:
            success_rate = (self.stats["channels_completed"] / self.stats["channels_processed"]) * 100
            print(f"\n📊 Tasa de éxito: {success_rate:.1f}%")
        
        print("="*70)
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del procesamiento"""
        return self.stats.copy()


if __name__ == "__main__":
    # Pruebas del ProcessingCoordinator
    import logging
    
    print("🧪 PRUEBAS DE ProcessingCoordinator")
    print("="*50)
    
    try:
        # Configurar logging
        logger = logging.getLogger('test_processing_coordinator')
        logger.setLevel(logging.INFO)
        
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # Crear dependencias
        print("\n1️⃣ Inicializando dependencias...")
        from config.config_manager import ConfigManager
        
        config = ConfigManager()
        error_handler = ErrorHandler(logger)
        json_generator = JSONGenerator(config.get('processing', 'json_output_dir'))
        
        # Crear ejecutor
        discordtodrive_script = config.get('processing', 'discordtodrive_script')
        executor = DiscordToDriveExecutor(discordtodrive_script, error_handler)
        
        # Crear coordinador
        coordinator = ProcessingCoordinator(json_generator, executor, error_handler)
        
        print("✅ Dependencias inicializadas")
        
        # Obtener archivos JSON de canales
        print("\n2️⃣ Obteniendo archivos JSON de canales...")
        channel_files = json_generator.get_all_channel_files()
        
        if not channel_files:
            print("⚠️ No se encontraron archivos JSON de canales")
            print("💡 Ejecuta primero channel_organizer.py para crear los JSONs")
        else:
            print(f"✅ {len(channel_files)} archivos JSON encontrados:")
            for file in channel_files:
                file_name = Path(file).name
                print(f"   └── {file_name}")
            
            print(f"\n3️⃣ ¿Procesar {len(channel_files)} canales? (y/n): ", end="")
            user_input = input().strip().lower()
            
            if user_input == 'y':
                print("\n🚀 Iniciando procesamiento de canales...")
                
                # Procesar todos los canales
                stats = coordinator.process_all_channels(channel_files)
                
                print(f"\n✅ ¡Procesamiento completado!")
                print(f"📊 Estadísticas finales disponibles")
                
            else:
                print("ℹ️ Procesamiento cancelado por el usuario")
        
        # Mostrar estadísticas de errores del sistema
        print("\n4️⃣ Estadísticas de errores del sistema:")
        error_handler.print_error_summary()
        
    except Exception as e:
        print(f"\n❌ Error en pruebas: {e}")
        import traceback
        traceback.print_exc()