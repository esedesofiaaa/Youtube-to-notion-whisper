"""
JSONGenerator - Manejo de archivos JSON
Responsabilidades:
- Crear estructura JSON por canal
- Escribir/leer archivos JSON
- Validar estructura JSON
- Manejo de archivos temporales
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import uuid


class JSONGenerator:
    """Maneja la generación y manipulación de archivos JSON del sistema"""
    
    def __init__(self, output_dir: str = "./channel_jsons/"):
        """
        Inicializa el generador JSON
        
        Args:
            output_dir: Directorio base para archivos JSON
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Esquema base para JSONs por canal
        self.channel_schema = {
            "metadata": {
                "channel_name": "",
                "drive_folder_id": "",
                "created_at": "",
                "last_updated": "",
                "total_videos": 0,
                "completed_videos": 0,
                "failed_videos": 0,
                "status": "pending"  # pending, processing, completed, error
            },
            "videos": []
        }
        
        # Esquema para cada video
        self.video_schema = {
            "youtube_url": "",
            "message_id": "",
            "date": "",
            "video_title": "",
            "video_duration": "",
            "processing_status": {
                "audio_extracted": False,
                "transcription_completed": False,
                "uploaded_to_drive": False,
                "fully_completed": False,
                "error_message": None,
                "retry_count": 0,
                "last_attempt": ""
            }
        }
    
    def create_channel_json(self, channel_name: str, drive_folder_id: str, 
                           videos_data: List[Dict[str, Any]]) -> str:
        """
        Crea un archivo JSON para un canal específico
        
        Args:
            channel_name: Nombre del canal de Discord
            drive_folder_id: ID de la carpeta de Google Drive
            videos_data: Lista de datos de videos
            
        Returns:
            Ruta del archivo JSON creado
        """
        # Sanitizar nombre del canal para nombre de archivo
        safe_channel_name = self._sanitize_filename(channel_name)
        filename = f"{safe_channel_name}_youtube_videos.json"
        filepath = self.output_dir / filename
        
        # Crear estructura del JSON
        channel_json = self.channel_schema.copy()
        
        # Llenar metadata
        channel_json["metadata"]["channel_name"] = channel_name
        channel_json["metadata"]["drive_folder_id"] = drive_folder_id
        channel_json["metadata"]["created_at"] = datetime.now(timezone.utc).isoformat()
        channel_json["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        channel_json["metadata"]["total_videos"] = len(videos_data)
        channel_json["metadata"]["status"] = "pending"
        
        # Procesar videos
        processed_videos = []
        for video_data in videos_data:
            video_entry = self._create_video_entry(video_data)
            processed_videos.append(video_entry)
        
        channel_json["videos"] = processed_videos
        
        # Guardar archivo
        self._write_json_file(filepath, channel_json)
        
        print(f"📄 JSON creado para canal '{channel_name}': {filename}")
        print(f"   └── {len(videos_data)} videos pendientes")
        
        return str(filepath)
    
    def _create_video_entry(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crea una entrada de video con el esquema correcto
        
        Args:
            video_data: Datos del video desde Notion
            
        Returns:
            Entrada de video estructurada
        """
        video_entry = self.video_schema.copy()
        
        # Llenar datos básicos
        video_entry["youtube_url"] = video_data.get("youtube_url", "")
        video_entry["message_id"] = video_data.get("message_id", "")
        video_entry["date"] = video_data.get("date", "")
        video_entry["video_title"] = video_data.get("video_title", "")
        video_entry["video_duration"] = video_data.get("video_duration", "")
        
        # Inicializar estado de procesamiento
        video_entry["processing_status"]["last_attempt"] = ""
        
        return video_entry
    
    def load_channel_json(self, filepath: str) -> Dict[str, Any]:
        """
        Carga un archivo JSON de canal
        
        Args:
            filepath: Ruta del archivo JSON
            
        Returns:
            Datos del canal
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validar estructura básica
            if not self._validate_channel_json_structure(data):
                raise ValueError(f"Estructura JSON inválida en {filepath}")
            
            return data
            
        except FileNotFoundError:
            raise FileNotFoundError(f"Archivo JSON no encontrado: {filepath}")
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON inválido en {filepath}: {e}")
    
    def update_channel_json(self, filepath: str, updates: Dict[str, Any]) -> None:
        """
        Actualiza un archivo JSON de canal
        
        Args:
            filepath: Ruta del archivo JSON
            updates: Actualizaciones a aplicar
        """
        # Cargar datos actuales
        data = self.load_channel_json(filepath)
        
        # Aplicar actualizaciones
        if "metadata" in updates:
            data["metadata"].update(updates["metadata"])
        
        if "videos" in updates:
            # Actualizar videos específicos o todos
            for update_video in updates["videos"]:
                video_url = update_video.get("youtube_url")
                if video_url:
                    # Encontrar y actualizar video específico
                    for i, video in enumerate(data["videos"]):
                        if video["youtube_url"] == video_url:
                            data["videos"][i].update(update_video)
                            break
        
        # Actualizar timestamp
        data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        
        # Recalcular estadísticas
        self._update_channel_statistics(data)
        
        # Guardar archivo actualizado
        self._write_json_file(filepath, data)
    
    def update_video_status(self, filepath: str, youtube_url: str, 
                           status_updates: Dict[str, Any]) -> None:
        """
        Actualiza el estado de un video específico
        
        Args:
            filepath: Ruta del archivo JSON del canal
            youtube_url: URL del video a actualizar
            status_updates: Actualizaciones de estado
        """
        data = self.load_channel_json(filepath)
        
        # Encontrar el video
        video_found = False
        for video in data["videos"]:
            if video["youtube_url"] == youtube_url:
                # Actualizar estado de procesamiento
                video["processing_status"].update(status_updates)
                video["processing_status"]["last_attempt"] = datetime.now(timezone.utc).isoformat()
                video_found = True
                break
        
        if not video_found:
            raise ValueError(f"Video no encontrado: {youtube_url}")
        
        # Actualizar metadata del canal
        data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._update_channel_statistics(data)
        
        # Guardar cambios
        self._write_json_file(filepath, data)
    
    def mark_video_completed(self, filepath: str, youtube_url: str) -> None:
        """
        Marca un video como completamente procesado
        
        Args:
            filepath: Ruta del archivo JSON del canal
            youtube_url: URL del video completado
        """
        status_updates = {
            "audio_extracted": True,
            "transcription_completed": True,
            "uploaded_to_drive": True,
            "fully_completed": True,
            "error_message": None
        }
        
        self.update_video_status(filepath, youtube_url, status_updates)
        print(f"✅ Video marcado como completado: {youtube_url}")
    
    def mark_video_failed(self, filepath: str, youtube_url: str, 
                         error_message: str) -> None:
        """
        Marca un video como fallido
        
        Args:
            filepath: Ruta del archivo JSON del canal
            youtube_url: URL del video fallido
            error_message: Mensaje de error
        """
        data = self.load_channel_json(filepath)
        
        for video in data["videos"]:
            if video["youtube_url"] == youtube_url:
                video["processing_status"]["error_message"] = error_message
                video["processing_status"]["retry_count"] += 1
                video["processing_status"]["last_attempt"] = datetime.now(timezone.utc).isoformat()
                break
        
        # Actualizar metadata
        data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._update_channel_statistics(data)
        
        self._write_json_file(filepath, data)
        print(f"❌ Video marcado como fallido: {youtube_url}")
        print(f"   └── Error: {error_message}")
    
    def get_pending_videos(self, filepath: str) -> List[Dict[str, Any]]:
        """
        Obtiene videos pendientes de procesamiento
        
        Args:
            filepath: Ruta del archivo JSON del canal
            
        Returns:
            Lista de videos pendientes
        """
        data = self.load_channel_json(filepath)
        
        pending_videos = []
        for video in data["videos"]:
            if not video["processing_status"]["fully_completed"]:
                pending_videos.append(video)
        
        return pending_videos
    
    def is_channel_completed(self, filepath: str) -> bool:
        """
        Verifica si un canal está completamente procesado
        
        Args:
            filepath: Ruta del archivo JSON del canal
            
        Returns:
            True si todos los videos están completados
        """
        data = self.load_channel_json(filepath)
        
        for video in data["videos"]:
            if not video["processing_status"]["fully_completed"]:
                return False
        
        return True
    
    def create_discordtodrive_json(self, channel_filepath: str, 
                                  temp_dir: Optional[str] = None) -> str:
        """
        Crea un JSON temporal compatible con DiscordToDrive.py
        
        Args:
            channel_filepath: Ruta del JSON del canal
            temp_dir: Directorio temporal (opcional)
            
        Returns:
            Ruta del archivo temporal creado
        """
        data = self.load_channel_json(channel_filepath)
        
        # Obtener videos pendientes
        pending_videos = self.get_pending_videos(channel_filepath)
        
        if not pending_videos:
            raise ValueError("No hay videos pendientes para procesar")
        
        # Crear estructura compatible con DiscordToDrive.py
        compatible_json = {
            "parent_folder_id": data["metadata"]["drive_folder_id"],
            "video_urls": [video["youtube_url"] for video in pending_videos]
        }
        
        # Crear archivo temporal
        if temp_dir:
            temp_file = Path(temp_dir) / f"temp_{uuid.uuid4().hex[:8]}_LinksYT.json"
        else:
            temp_file = self.output_dir / f"temp_{uuid.uuid4().hex[:8]}_LinksYT.json"
        
        self._write_json_file(temp_file, compatible_json)
        
        print(f"🔄 JSON temporal creado: {temp_file.name}")
        print(f"   └── {len(pending_videos)} videos para procesar")
        
        return str(temp_file)
    
    def get_all_channel_files(self) -> List[str]:
        """
        Obtiene todas las rutas de archivos JSON de canales
        
        Returns:
            Lista de rutas de archivos JSON
        """
        json_files = []
        
        for file_path in self.output_dir.glob("*_youtube_videos.json"):
            if not file_path.name.startswith("temp_"):  # Excluir archivos temporales
                json_files.append(str(file_path))
        
        return sorted(json_files)
    
    def cleanup_completed_channels(self) -> List[str]:
        """
        Limpia archivos JSON de canales completados
        
        Returns:
            Lista de archivos eliminados
        """
        cleaned_files = []
        
        for filepath in self.get_all_channel_files():
            if self.is_channel_completed(filepath):
                try:
                    # Crear backup antes de eliminar
                    backup_path = self._create_backup(filepath)
                    os.remove(filepath)
                    cleaned_files.append(filepath)
                    print(f"🧹 Canal completado limpiado: {Path(filepath).name}")
                    print(f"   └── Backup creado: {backup_path}")
                except Exception as e:
                    print(f"⚠️ Error limpiando {filepath}: {e}")
        
        return cleaned_files
    
    def cleanup_temp_files(self) -> int:
        """
        Limpia archivos temporales
        
        Returns:
            Número de archivos eliminados
        """
        deleted_count = 0
        
        for file_path in self.output_dir.glob("temp_*.json"):
            try:
                os.remove(file_path)
                deleted_count += 1
                print(f"🗑️ Archivo temporal eliminado: {file_path.name}")
            except Exception as e:
                print(f"⚠️ Error eliminando {file_path}: {e}")
        
        return deleted_count
    
    def _update_channel_statistics(self, data: Dict[str, Any]) -> None:
        """Actualiza estadísticas del canal"""
        total_videos = len(data["videos"])
        completed_videos = sum(1 for video in data["videos"] 
                             if video["processing_status"]["fully_completed"])
        failed_videos = sum(1 for video in data["videos"] 
                          if video["processing_status"]["error_message"] and 
                          video["processing_status"]["retry_count"] >= 3)
        
        data["metadata"]["total_videos"] = total_videos
        data["metadata"]["completed_videos"] = completed_videos
        data["metadata"]["failed_videos"] = failed_videos
        
        # Actualizar estado del canal
        if completed_videos == total_videos:
            data["metadata"]["status"] = "completed"
        elif failed_videos > 0 or completed_videos > 0:
            data["metadata"]["status"] = "processing"
        else:
            data["metadata"]["status"] = "pending"
    
    def _validate_channel_json_structure(self, data: Dict[str, Any]) -> bool:
        """Valida la estructura de un JSON de canal"""
        required_keys = ["metadata", "videos"]
        required_metadata_keys = ["channel_name", "drive_folder_id", "status"]
        
        # Verificar claves principales
        for key in required_keys:
            if key not in data:
                return False
        
        # Verificar metadata
        for key in required_metadata_keys:
            if key not in data["metadata"]:
                return False
        
        # Verificar que videos sea una lista
        if not isinstance(data["videos"], list):
            return False
        
        return True
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitiza nombre de archivo"""
        # Reemplazar caracteres problemáticos
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Remover espacios extra y convertir a lowercase
        filename = '_'.join(filename.split()).lower()
        
        return filename
    
    def _write_json_file(self, filepath: Path, data: Dict[str, Any]) -> None:
        """Escribe datos JSON a archivo"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            raise IOError(f"Error escribiendo archivo JSON {filepath}: {e}")
    
    def _create_backup(self, filepath: str) -> str:
        """Crea backup de un archivo JSON"""
        backup_dir = self.output_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_name = Path(filepath).stem
        backup_name = f"{original_name}_{timestamp}.json"
        backup_path = backup_dir / backup_name
        
        # Copiar archivo
        import shutil
        shutil.copy2(filepath, backup_path)
        
        return str(backup_path)
    
    def get_channel_summary(self, filepath: str) -> Dict[str, Any]:
        """
        Obtiene resumen de un canal
        
        Args:
            filepath: Ruta del archivo JSON del canal
            
        Returns:
            Resumen del canal
        """
        data = self.load_channel_json(filepath)
        
        return {
            "channel_name": data["metadata"]["channel_name"],
            "total_videos": data["metadata"]["total_videos"],
            "completed_videos": data["metadata"]["completed_videos"],
            "failed_videos": data["metadata"]["failed_videos"],
            "pending_videos": data["metadata"]["total_videos"] - data["metadata"]["completed_videos"],
            "status": data["metadata"]["status"],
            "last_updated": data["metadata"]["last_updated"]
        }
    
    def print_channel_status(self, filepath: str) -> None:
        """Imprime estado de un canal"""
        summary = self.get_channel_summary(filepath)
        
        print(f"\n📺 Canal: {summary['channel_name']}")
        print(f"   📊 Total videos: {summary['total_videos']}")
        print(f"   ✅ Completados: {summary['completed_videos']}")
        print(f"   ⏳ Pendientes: {summary['pending_videos']}")
        print(f"   ❌ Fallidos: {summary['failed_videos']}")
        print(f"   🔄 Estado: {summary['status']}")
        print(f"   📅 Actualizado: {summary['last_updated'][:19]}")


if __name__ == "__main__":
    # Pruebas de la clase JSONGenerator
    print("🧪 PRUEBAS DE JSONGenerator")
    print("="*40)
    
    # Crear instancia
    json_gen = JSONGenerator()
    
    # Datos de prueba
    test_videos = [
        {
            "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "message_id": "notion_msg_001",
            "date": "2025-07-23T10:00:00Z",
            "video_title": "Never Gonna Give You Up",
            "video_duration": "00:03:32"
        },
        {
            "youtube_url": "https://www.youtube.com/watch?v=9bZkp7q19f0",
            "message_id": "notion_msg_002", 
            "date": "2025-07-23T11:00:00Z",
            "video_title": "PSY - GANGNAM STYLE",
            "video_duration": "00:04:12"
        }
    ]
    
    try:
        # Prueba 1: Crear JSON de canal
        print("\n1️⃣ Creando JSON de canal de prueba...")
        channel_file = json_gen.create_channel_json(
            channel_name="general",
            drive_folder_id="1A2B3C4D5E6F7G8H9I0J",
            videos_data=test_videos
        )
        
        # Prueba 2: Cargar y verificar JSON
        print("\n2️⃣ Cargando y verificando JSON...")
        data = json_gen.load_channel_json(channel_file)
        print(f"✅ JSON cargado correctamente")
        print(f"   └── Canal: {data['metadata']['channel_name']}")
        print(f"   └── Videos: {data['metadata']['total_videos']}")
        
        # Prueba 3: Actualizar estado de video
        print("\n3️⃣ Actualizando estado de video...")
        json_gen.update_video_status(
            channel_file,
            test_videos[0]["youtube_url"],
            {"audio_extracted": True, "transcription_completed": True}
        )
        print("✅ Estado actualizado")
        
        # Prueba 4: Marcar video como completado
        print("\n4️⃣ Marcando video como completado...")
        json_gen.mark_video_completed(channel_file, test_videos[0]["youtube_url"])
        
        # Prueba 5: Obtener videos pendientes
        print("\n5️⃣ Obteniendo videos pendientes...")
        pending = json_gen.get_pending_videos(channel_file)
        print(f"✅ Videos pendientes: {len(pending)}")
        
        # Prueba 6: Crear JSON temporal compatible
        print("\n6️⃣ Creando JSON temporal compatible...")
        temp_file = json_gen.create_discordtodrive_json(channel_file)
        print(f"✅ JSON temporal creado: {Path(temp_file).name}")
        
        # Prueba 7: Estado del canal
        print("\n7️⃣ Estado del canal:")
        json_gen.print_channel_status(channel_file)
        
        # Prueba 8: Limpiar archivos temporales
        print("\n8️⃣ Limpiando archivos temporales...")
        cleaned = json_gen.cleanup_temp_files()
        print(f"✅ {cleaned} archivos temporales eliminados")
        
        print("\n✅ ¡Todas las pruebas de JSONGenerator pasaron!")
        
    except Exception as e:
        print(f"\n❌ Error en pruebas: {e}")
        import traceback
        traceback.print_exc()