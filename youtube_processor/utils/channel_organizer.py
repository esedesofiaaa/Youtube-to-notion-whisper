"""
ChannelOrganizer - Organización de datos por canal
Responsabilidades:
- Agrupar URLs por canal
- Asignar carpetas de Drive
- Generar JSONs por canal
- Manejar canales sin mapeo
"""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone

# Importar dependencias del sistema
sys.path.append(str(Path(__file__).parent.parent))
from utils.json_generator import JSONGenerator
from utils.error_handler import ErrorHandler, ErrorCategory, ErrorSeverity


class ChannelDriveMapper:
    """Maneja el mapeo de canales de Discord a carpetas de Google Drive"""
    
    def __init__(self, error_handler: ErrorHandler, 
                 default_parent_folder: Optional[str] = None,
                 auto_create_folders: bool = True):
        """
        Inicializa el mapeador de canales a Drive
        
        Args:
            error_handler: Manejador de errores
            default_parent_folder: ID de carpeta padre por defecto
            auto_create_folders: Si crear carpetas automáticamente
        """
        self.error_handler = error_handler
        self.logger = error_handler.logger
        self.default_parent_folder = default_parent_folder
        self.auto_create_folders = auto_create_folders
        
        # Mapeo de canales a carpetas (se cargará desde archivo)
        self.channel_mappings = {}
        
        # Google Drive service (se inicializará cuando sea necesario)
        self.drive_service = None
        self._drive_initialized = False
    
    def load_mappings(self, mapping_file: str) -> Dict[str, str]:
        """
        Carga mapeos existentes desde archivo
        
        Args:
            mapping_file: Ruta al archivo de mapeo
            
        Returns:
            Diccionario con mapeo canal -> drive_folder_id
        """
        try:
            import json
            
            with open(mapping_file, 'r', encoding='utf-8') as f:
                mapping_data = json.load(f)
            
            if 'mappings' in mapping_data:
                self.channel_mappings = mapping_data['mappings']
                self.logger.info(f"✅ Mapeo cargado: {len(self.channel_mappings)} canales")
                return self.channel_mappings
            else:
                self.logger.warning(f"⚠️ Archivo de mapeo sin clave 'mappings': {mapping_file}")
                return {}
                
        except FileNotFoundError:
            self.logger.info(f"ℹ️ Archivo de mapeo no encontrado: {mapping_file}")
            self.logger.info("ℹ️ Se crearán mapeos automáticamente")
            return {}
        except Exception as e:
            self.error_handler.handle_error(
                e, ErrorCategory.FILE_SYSTEM,
                context={"operation": "load_mappings", "file": mapping_file}
            )
            return {}
    
    def get_or_create_folder_id(self, channel_name: str) -> str:
        """
        Obtiene o crea un ID de carpeta para un canal
        
        Args:
            channel_name: Nombre del canal de Discord
            
        Returns:
            ID de la carpeta de Google Drive
        """
        # Verificar si ya existe mapeo
        if channel_name in self.channel_mappings:
            folder_id = self.channel_mappings[channel_name]
            self.logger.info(f"📁 Canal '{channel_name}' → Carpeta existente: {folder_id[:8]}...")
            return folder_id
        
        # Si auto-crear está habilitado, generar ID
        if self.auto_create_folders:
            # Por ahora generamos un ID temporal - en la siguiente clase crearemos la carpeta real
            temp_folder_id = self._generate_temp_folder_id(channel_name)
            self.channel_mappings[channel_name] = temp_folder_id
            
            self.logger.info(f"🆕 Canal '{channel_name}' → Nueva carpeta: {temp_folder_id[:8]}...")
            return temp_folder_id
        else:
            # Usar carpeta padre por defecto
            if self.default_parent_folder:
                self.logger.warning(f"⚠️ Canal '{channel_name}' sin mapeo, usando carpeta padre")
                return self.default_parent_folder
            else:
                raise ValueError(f"Canal '{channel_name}' sin mapeo y sin carpeta padre configurada")
    
    def _generate_temp_folder_id(self, channel_name: str) -> str:
        """
        Genera un ID temporal para una carpeta (será reemplazado por ID real más tarde)
        
        Args:
            channel_name: Nombre del canal
            
        Returns:
            ID temporal de carpeta
        """
        import hashlib
        import time
        
        # Crear ID único basado en nombre del canal y timestamp
        unique_string = f"{channel_name}_{int(time.time())}"
        hash_object = hashlib.md5(unique_string.encode())
        temp_id = f"TEMP_{hash_object.hexdigest()[:24]}"
        
        return temp_id
    
    def save_mappings(self, mapping_file: str) -> None:
        """
        Guarda mapeos actualizados al archivo
        
        Args:
            mapping_file: Ruta al archivo de mapeo
        """
        try:
            import json
            
            mapping_data = {
                "mappings": self.channel_mappings,
                "auto_create_folders": self.auto_create_folders,
                "default_parent_folder": self.default_parent_folder,
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "total_channels": len(self.channel_mappings)
            }
            
            # Crear directorio si no existe
            Path(mapping_file).parent.mkdir(parents=True, exist_ok=True)
            
            with open(mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mapping_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"💾 Mapeo guardado: {mapping_file}")
            self.logger.info(f"   └── {len(self.channel_mappings)} canales mapeados")
            
        except Exception as e:
            self.error_handler.handle_error(
                e, ErrorCategory.FILE_SYSTEM,
                context={"operation": "save_mappings", "file": mapping_file}
            )
    
    def get_mapping_summary(self) -> Dict[str, Any]:
        """
        Obtiene resumen del mapeo actual
        
        Returns:
            Diccionario con estadísticas del mapeo
        """
        temp_folders = sum(1 for folder_id in self.channel_mappings.values() 
                          if folder_id.startswith('TEMP_'))
        real_folders = len(self.channel_mappings) - temp_folders
        
        return {
            "total_channels": len(self.channel_mappings),
            "real_folders": real_folders,
            "temp_folders": temp_folders,
            "channels": list(self.channel_mappings.keys()),
            "auto_create_enabled": self.auto_create_folders
        }


class ChannelOrganizer:
    """Organiza datos extraídos de Notion por canal y genera JSONs"""
    
    def __init__(self, json_generator: JSONGenerator, 
                 channel_mapper: ChannelDriveMapper,
                 error_handler: ErrorHandler):
        """
        Inicializa el organizador de canales
        
        Args:
            json_generator: Generador de archivos JSON
            channel_mapper: Mapeador de canales a Drive
            error_handler: Manejador de errores
        """
        self.json_generator = json_generator
        self.channel_mapper = channel_mapper
        self.error_handler = error_handler
        self.logger = error_handler.logger
        
        # Estadísticas del procesamiento
        self.stats = {
            "channels_processed": 0,
            "total_videos": 0,
            "json_files_created": [],
            "processing_errors": []
        }
    
    def organize_channels_data(self, channels_data: Dict[str, List[Dict[str, Any]]],
                              mapping_file: str) -> List[str]:
        """
        Organiza datos por canal y genera JSONs individuales
        
        Args:
            channels_data: Datos organizados por canal desde NotionDataExtractor
            mapping_file: Archivo para guardar mapeo de canales
            
        Returns:
            Lista de rutas de archivos JSON creados
        """
        self.error_handler.log_operation_start(
            f"Organización de {len(channels_data)} canales en JSONs"
        )
        
        try:
            # Cargar mapeos existentes
            self.channel_mapper.load_mappings(mapping_file)
            
            created_files = []
            
            # Procesar cada canal
            for channel_name, videos_data in channels_data.items():
                try:
                    self.logger.info(f"📺 Procesando canal: {channel_name}")
                    
                    # Obtener o crear carpeta de Drive para este canal
                    drive_folder_id = self.channel_mapper.get_or_create_folder_id(channel_name)
                    
                    # Crear JSON para este canal
                    json_file_path = self._create_channel_json(
                        channel_name, 
                        drive_folder_id, 
                        videos_data
                    )
                    
                    if json_file_path:
                        created_files.append(json_file_path)
                        self.stats["channels_processed"] += 1
                        self.stats["total_videos"] += len(videos_data)
                        self.stats["json_files_created"].append({
                            "channel": channel_name,
                            "file": json_file_path,
                            "videos": len(videos_data)
                        })
                        
                        self.logger.info(f"   ✅ JSON creado: {Path(json_file_path).name}")
                        self.logger.info(f"   └── {len(videos_data)} videos incluidos")
                    
                except Exception as e:
                    self.error_handler.handle_error(
                        e, ErrorCategory.PROCESSING,
                        context={"channel": channel_name, "videos_count": len(videos_data)}
                    )
                    self.stats["processing_errors"].append({
                        "channel": channel_name,
                        "error": str(e)
                    })
                    continue
            
            # Guardar mapeo actualizado
            self.channel_mapper.save_mappings(mapping_file)
            
            # Mostrar resumen
            self._print_organization_summary()
            
            self.error_handler.log_operation_success(
                "Organización de canales",
                context={
                    "channels_processed": self.stats["channels_processed"],
                    "total_videos": self.stats["total_videos"],
                    "files_created": len(created_files)
                }
            )
            
            return created_files
            
        except Exception as e:
            self.error_handler.handle_error(
                e, ErrorCategory.PROCESSING,
                context={"operation": "organize_channels_data"}
            )
            raise
    
    def _create_channel_json(self, channel_name: str, drive_folder_id: str, 
                           videos_data: List[Dict[str, Any]]) -> Optional[str]:
        """
        Crea archivo JSON para un canal específico
        
        Args:
            channel_name: Nombre del canal
            drive_folder_id: ID de carpeta de Google Drive
            videos_data: Lista de datos de videos
            
        Returns:
            Ruta del archivo JSON creado o None si falla
        """
        try:
            # Preparar datos de videos en formato correcto para JSONGenerator
            processed_videos = []
            
            for video_data in videos_data:
                # Asegurar que tenemos todos los campos necesarios
                processed_video = {
                    "youtube_url": video_data.get("youtube_url", ""),
                    "message_id": video_data.get("message_id", ""),
                    "date": video_data.get("date", ""),
                    "video_title": video_data.get("video_title", ""),
                    "video_duration": video_data.get("video_duration", "")
                }
                
                # Validar que la URL de YouTube sea válida
                if processed_video["youtube_url"] and self._is_valid_youtube_url(processed_video["youtube_url"]):
                    processed_videos.append(processed_video)
                else:
                    self.logger.warning(f"⚠️ URL de YouTube inválida omitida: {processed_video['youtube_url']}")
            
            if not processed_videos:
                self.logger.warning(f"⚠️ Canal '{channel_name}' no tiene videos válidos")
                return None
            
            # Crear JSON usando JSONGenerator
            json_file_path = self.json_generator.create_channel_json(
                channel_name=channel_name,
                drive_folder_id=drive_folder_id,
                videos_data=processed_videos
            )
            
            return json_file_path
            
        except Exception as e:
            self.logger.error(f"❌ Error creando JSON para canal '{channel_name}': {e}")
            return None
    
    def _is_valid_youtube_url(self, url: str) -> bool:
        """Valida que una URL sea de YouTube"""
        if not url:
            return False
            
        youtube_patterns = [
            r'youtube\.com/watch\?v=',
            r'youtu\.be/',
            r'youtube\.com/shorts/',
            r'm\.youtube\.com/watch\?v='
        ]
        
        import re
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in youtube_patterns)
    
    def _print_organization_summary(self):
        """Imprime resumen de la organización"""
        print("\n" + "="*60)
        print("📊 RESUMEN DE ORGANIZACIÓN POR CANALES")
        print("="*60)
        
        print(f"✅ Canales procesados: {self.stats['channels_processed']}")
        print(f"📹 Total videos: {self.stats['total_videos']}")
        print(f"📄 Archivos JSON creados: {len(self.stats['json_files_created'])}")
        
        if self.stats["json_files_created"]:
            print("\n📁 Archivos creados:")
            for file_info in self.stats["json_files_created"]:
                filename = Path(file_info["file"]).name
                print(f"   └── {filename}")
                print(f"       • Canal: {file_info['channel']}")
                print(f"       • Videos: {file_info['videos']}")
        
        if self.stats["processing_errors"]:
            print(f"\n⚠️ Errores en procesamiento: {len(self.stats['processing_errors'])}")
            for error_info in self.stats["processing_errors"]:
                print(f"   └── {error_info['channel']}: {error_info['error']}")
        
        # Mostrar resumen del mapeo
        mapping_summary = self.channel_mapper.get_mapping_summary()
        print(f"\n🗂️ Mapeo de carpetas:")
        print(f"   └── Total canales: {mapping_summary['total_channels']}")
        print(f"   └── Carpetas reales: {mapping_summary['real_folders']}")
        print(f"   └── Carpetas temporales: {mapping_summary['temp_folders']}")
        
        print("="*60)
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del procesamiento"""
        return self.stats.copy()
    
    def get_created_files(self) -> List[str]:
        """Obtiene lista de archivos JSON creados"""
        return [info["file"] for info in self.stats["json_files_created"]]


if __name__ == "__main__":
    # Pruebas de ChannelOrganizer integrado con NotionDataExtractor
    import asyncio
    import logging
    
    print("🧪 PRUEBAS DE ChannelOrganizer")
    print("="*50)
    
    try:
        # Configurar logging
        logger = logging.getLogger('test_channel_organizer')
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
        
        # Crear mapper con configuración automática
        auto_create = config.get('google_drive', 'auto_create_folders')
        default_parent = config.get('google_drive', 'default_parent_folder')
        
        channel_mapper = ChannelDriveMapper(
            error_handler=error_handler,
            default_parent_folder=default_parent,
            auto_create_folders=auto_create
        )
        
        # Crear organizador
        organizer = ChannelOrganizer(json_generator, channel_mapper, error_handler)
        
        print("✅ Dependencias inicializadas")
        
        # Extraer datos reales desde Notion
        print("\n2️⃣ Extrayendo datos desde Notion...")
        from extraction.notion_extractor import NotionDataExtractor
        
        extractor = NotionDataExtractor(config, error_handler)
        
        async def extract_and_organize():
            # Extraer datos
            channels_data = await extractor.extract_youtube_urls()
            
            if not channels_data:
                print("⚠️ No se encontraron datos para organizar")
                return
            
            print(f"\n3️⃣ Organizando {len(channels_data)} canales...")
            
            # Organizar en JSONs
            mapping_file = config.get('google_drive', 'channel_mapping_file')
            created_files = organizer.organize_channels_data(channels_data, mapping_file)
            
            print(f"\n4️⃣ Verificando archivos creados...")
            for file_path in created_files:
                if Path(file_path).exists():
                    file_size = Path(file_path).stat().st_size
                    print(f"✅ {Path(file_path).name} ({file_size} bytes)")
                else:
                    print(f"❌ {Path(file_path).name} no existe")
            
            return created_files
        
        # Ejecutar extracción y organización
        created_files = asyncio.run(extract_and_organize())
        
        if created_files:
            print(f"\n✅ ¡Organización completada exitosamente!")
            print(f"📁 {len(created_files)} archivos JSON creados en:")
            print(f"   {Path(created_files[0]).parent}")
        else:
            print(f"\n⚠️ No se crearon archivos JSON")
        
        # Mostrar estadísticas de errores
        print("\n5️⃣ Estadísticas finales:")
        error_handler.print_error_summary()
        
    except Exception as e:
        print(f"\n❌ Error en pruebas: {e}")
        import traceback
        traceback.print_exc()