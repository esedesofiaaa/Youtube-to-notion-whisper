"""
NotionDataExtractor - Extracción de datos desde Notion
Responsabilidades:
- Conectar con Notion API
- Filtrar mensajes por fecha
- Extraer URLs de YouTube
- Validar URLs extraídas
"""

import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs

# Importar dependencias del sistema
sys.path.append(str(Path(__file__).parent.parent.parent))  # ← Añadir .parent extra
from youtube_processor.config.config_manager import ConfigManager
from youtube_processor.utils.error_handler import ErrorHandler, ErrorCategory, ErrorSeverity

# Importar notion-client
try:
    from notion_client import Client
    from notion_client.errors import APIResponseError, HTTPResponseError
    print("✅ notion-client importado exitosamente")  # ← Añadir esta línea para debug
except ImportError as e:
    print(f"❌ Error: notion-client no está instalado: {e}")
    print("💡 Instalar con: pip install notion-client")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error inesperado importando notion-client: {e}")
    sys.exit(1)


class NotionDataExtractor:
    """Extrae datos de YouTube desde una base de datos de Notion"""
    
    def __init__(self, config_manager: ConfigManager, error_handler: ErrorHandler):
        """
        Inicializa el extractor de datos de Notion
        
        Args:
            config_manager: Gestor de configuración
            error_handler: Manejador de errores
        """
        self.config = config_manager
        self.error_handler = error_handler
        self.logger = error_handler.logger
        
        # Configuración de Notion
        notion_config = self.config.get_notion_config()
        self.notion_token = notion_config['token']
        self.database_id = notion_config['database_id']
        
        # Cliente de Notion
        self.notion_client = None
        
        # Configuración de procesamiento
        processing_config = self.config.get_processing_config()
        self.start_date = datetime.strptime(processing_config['start_date'], '%Y-%m-%d')
        self.start_date = self.start_date.replace(tzinfo=timezone.utc)
        
        # Patrones de URL de YouTube
        self.youtube_patterns = [
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+',
            r'(?:https?://)?(?:www\.)?youtu\.be/[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+',
            r'(?:https?://)?(?:m\.)?youtube\.com/watch\?v=[\w-]+'
        ]
        
        # Cache para propiedades de la base de datos
        self._database_properties = None
        
        # Inicializar cliente
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Inicializa el cliente de Notion con manejo de errores"""
        self.error_handler.log_operation_start("Inicialización cliente Notion")
        
        try:
            self.notion_client = Client(auth=self.notion_token)
            
            # Verificar conexión con la base de datos
            database_info = self.notion_client.databases.retrieve(self.database_id)
            
            self.logger.info(f"✅ Conectado a base de datos: {database_info.get('title', [{}])[0].get('plain_text', 'Sin título')}")
            self.error_handler.log_operation_success("Cliente Notion inicializado")
            
        except APIResponseError as e:
            error_info = self.error_handler.handle_error(
                e, ErrorCategory.NOTION_API,
                context={"operation": "initialize_client", "database_id": self.database_id}
            )
            raise Exception(f"Error de API de Notion: {error_info.message}")
            
        except Exception as e:
            error_info = self.error_handler.handle_error(
                e, ErrorCategory.CONFIGURATION,
                context={"operation": "initialize_client"}
            )
            raise Exception(f"Error inicializando cliente Notion: {error_info.message}")
    
    async def extract_youtube_urls(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extrae URLs de YouTube de la base de datos, organizadas por canal
        
        Returns:
            Diccionario con canal como clave y lista de datos de videos como valor
        """
        self.error_handler.log_operation_start(
            f"Extracción URLs YouTube desde {self.start_date.strftime('%Y-%m-%d')}"
        )
        
        try:
            # Obtener propiedades de la base de datos
            await self._load_database_properties()
            
            # Extraer todos los mensajes relevantes
            messages = await self._extract_messages_with_youtube()
            
            # Organizar por canal
            channels_data = self._organize_by_channel(messages)
            
            # Estadísticas
            total_videos = sum(len(videos) for videos in channels_data.values())
            self.logger.info(f"📊 Extracción completada:")
            self.logger.info(f"   └── {len(channels_data)} canales encontrados")
            self.logger.info(f"   └── {total_videos} videos con URLs de YouTube")
            
            for channel, videos in channels_data.items():
                self.logger.info(f"   └── {channel}: {len(videos)} videos")
            
            self.error_handler.log_operation_success(
                "Extracción URLs YouTube",
                context={"channels": len(channels_data), "total_videos": total_videos}
            )
            
            return channels_data
            
        except Exception as e:
            self.error_handler.handle_error(
                e, ErrorCategory.NOTION_API,
                context={"operation": "extract_youtube_urls"}
            )
            raise
    
    async def _load_database_properties(self) -> None:
        """Carga y valida las propiedades de la base de datos"""
        if self._database_properties is not None:
            return
        
        try:
            database_info = self.notion_client.databases.retrieve(self.database_id)
            self._database_properties = database_info['properties']
            
            # Validar propiedades requeridas
            required_props = ['Attached URL', 'Channel', 'Date', 'Message ID']
            missing_props = []
            
            for prop in required_props:
                if prop not in self._database_properties:
                    missing_props.append(prop)
            
            if missing_props:
                raise ValueError(f"Propiedades faltantes en la base de datos: {missing_props}")
            
            self.logger.info(f"✅ Propiedades de base de datos validadas: {len(self._database_properties)} propiedades")
            
        except Exception as e:
            self.error_handler.handle_error(
                e, ErrorCategory.NOTION_API,
                context={"operation": "load_database_properties", "database_id": self.database_id}
            )
            raise
    
    async def _extract_messages_with_youtube(self) -> List[Dict[str, Any]]:
        """Extrae mensajes que contienen URLs de YouTube"""
        messages_with_youtube = []
        has_more = True
        next_cursor = None
        page_count = 0
        
        while has_more:
            try:
                page_count += 1
                self.logger.info(f"📄 Procesando página {page_count}...")
                
                # Construir filtro de consulta
                query_filter = self._build_query_filter()
                
                # Hacer consulta a Notion
                response = self.notion_client.databases.query(
                    database_id=self.database_id,
                    filter=query_filter,
                    page_size=100,
                    start_cursor=next_cursor
                )
                
                # Procesar resultados de esta página
                page_results = await self._process_page_results(response['results'])
                messages_with_youtube.extend(page_results)
                
                # Preparar para siguiente página
                has_more = response['has_more']
                next_cursor = response.get('next_cursor')
                
                if page_results:
                    self.logger.info(f"   └── {len(page_results)} mensajes con YouTube encontrados")
                
                # Progreso cada 5 páginas
                if page_count % 5 == 0:
                    self.error_handler.log_progress(
                        len(messages_with_youtube), 
                        len(messages_with_youtube) + (50 if has_more else 0),
                        "Extrayendo mensajes"
                    )
                
            except APIResponseError as e:
                if "429" in str(e):  # Rate limit
                    self.logger.warning("⚠️ Rate limit detectado, esperando...")
                    import asyncio
                    await asyncio.sleep(2)
                    continue
                else:
                    self.error_handler.handle_error(
                        e, ErrorCategory.NOTION_API,
                        context={"operation": "query_database", "page": page_count}
                    )
                    raise
                    
            except Exception as e:
                self.error_handler.handle_error(
                    e, ErrorCategory.NOTION_API,
                    context={"operation": "extract_messages", "page": page_count}
                )
                raise
        
        self.logger.info(f"📊 Extracción completada: {len(messages_with_youtube)} mensajes con YouTube")
        return messages_with_youtube
    
    def _build_query_filter(self) -> Dict[str, Any]:
        """Construye filtro para la consulta de Notion"""
        return {
            "and": [
                {
                    "property": "Date",
                    "date": {
                        "on_or_after": self.start_date.isoformat()
                    }
                },
                {
                    "property": "Attached URL",
                    "url": {
                        "is_not_empty": True
                    }
                }
            ]
        }
    
    async def _process_page_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Procesa los resultados de una página"""
        processed_messages = []
        
        for result in results:
            try:
                message_data = self._extract_message_data(result)
                
                if message_data and self._has_youtube_url(message_data['attached_url']):
                    # Enriquecer con información del video
                    video_info = await self._enrich_video_data(message_data)
                    if video_info:
                        processed_messages.append(video_info)
                        
            except Exception as e:
                self.error_handler.handle_error(
                    e, ErrorCategory.PROCESSING,
                    context={"operation": "process_message", "message_id": result.get('id', 'unknown')}
                )
                # Continuar con el siguiente mensaje
                continue
        
        return processed_messages
    
    def _extract_message_data(self, notion_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extrae datos relevantes de un resultado de Notion"""
        try:
            properties = notion_result['properties']
            
            # Extraer URL adjunta
            attached_url_prop = properties.get('Attached URL', {})
            attached_url = attached_url_prop.get('url') if attached_url_prop else None
            
            if not attached_url:
                return None
            
            # Extraer canal
            channel_prop = properties.get('Channel', {})
            channel = None
            if channel_prop.get('select'):
                channel = channel_prop['select']['name']
            elif channel_prop.get('rich_text'):
                channel = channel_prop['rich_text'][0]['plain_text'] if channel_prop['rich_text'] else None
            
            if not channel:
                return None
            
            # Extraer fecha
            date_prop = properties.get('Date', {})
            date = date_prop.get('date', {}).get('start') if date_prop else None
            
            # Extraer Message ID
            message_id_prop = properties.get('Message ID', {})
            message_id = None
            if message_id_prop.get('rich_text'):
                message_id = message_id_prop['rich_text'][0]['plain_text'] if message_id_prop['rich_text'] else None
            elif message_id_prop.get('title'):
                message_id = message_id_prop['title'][0]['plain_text'] if message_id_prop['title'] else None
            
            return {
                'notion_id': notion_result['id'],
                'attached_url': attached_url,
                'channel': channel,
                'date': date,
                'message_id': message_id or notion_result['id']
            }
            
        except Exception as e:
            self.logger.debug(f"⚠️ Error extrayendo datos del mensaje: {e}")
            return None
    
    def _has_youtube_url(self, url: str) -> bool:
        """Verifica si una URL es de YouTube"""
        if not url:
            return False
            
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in self.youtube_patterns)
    
    async def _enrich_video_data(self, message_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Enriquece datos del mensaje con información del video"""
        try:
            youtube_url = message_data['attached_url']
            
            # Normalizar URL de YouTube
            normalized_url = self._normalize_youtube_url(youtube_url)
            
            if not normalized_url:
                return None
            
            # Crear estructura de datos del video
            video_data = {
                'youtube_url': normalized_url,
                'message_id': message_data['message_id'],
                'date': message_data['date'],
                'channel': message_data['channel'],
                'notion_id': message_data['notion_id'],
                'video_title': '',  # Se llenará por DiscordToDrive.py
                'video_duration': ''  # Se llenará por DiscordToDrive.py
            }
            
            return video_data
            
        except Exception as e:
            self.logger.debug(f"⚠️ Error enriqueciendo datos del video: {e}")
            return None
    
    def _normalize_youtube_url(self, url: str) -> Optional[str]:
        """Normaliza URL de YouTube a formato estándar"""
        try:
            # Limpiar URL
            url = url.strip()
            
            # Añadir https si no tiene protocolo
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            parsed = urlparse(url)
            
            # YouTube normal (watch)
            if 'youtube.com' in parsed.netloc and 'watch' in parsed.path:
                query_params = parse_qs(parsed.query)
                video_id = query_params.get('v', [None])[0]
                if video_id:
                    return f"https://www.youtube.com/watch?v={video_id}"
            
            # YouTube short URLs (youtu.be)
            elif 'youtu.be' in parsed.netloc:
                video_id = parsed.path.lstrip('/')
                if video_id:
                    return f"https://www.youtube.com/watch?v={video_id}"
            
            # YouTube Shorts
            elif 'youtube.com' in parsed.netloc and 'shorts' in parsed.path:
                video_id = parsed.path.split('/')[-1]
                if video_id:
                    return f"https://www.youtube.com/shorts/{video_id}"
            
            # Mobile YouTube
            elif 'm.youtube.com' in parsed.netloc:
                query_params = parse_qs(parsed.query)
                video_id = query_params.get('v', [None])[0]
                if video_id:
                    return f"https://www.youtube.com/watch?v={video_id}"
            
            return None
            
        except Exception as e:
            self.logger.debug(f"⚠️ Error normalizando URL {url}: {e}")
            return None
    
    def _organize_by_channel(self, messages: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Organiza mensajes por canal"""
        channels_data = {}
        
        for message in messages:
            channel = message['channel']
            
            if channel not in channels_data:
                channels_data[channel] = []
            
            channels_data[channel].append(message)
        
        # Ordenar videos por fecha dentro de cada canal
        for channel in channels_data:
            channels_data[channel].sort(
                key=lambda x: x['date'] or '1970-01-01',
                reverse=False  # Más antiguos primero
            )
        
        return channels_data
    
    def get_database_info(self) -> Dict[str, Any]:
        """Obtiene información de la base de datos"""
        try:
            database_info = self.notion_client.databases.retrieve(self.database_id)
            
            return {
                'id': database_info['id'],
                'title': database_info.get('title', [{}])[0].get('plain_text', 'Sin título'),
                'properties': list(database_info['properties'].keys()),
                'created_time': database_info.get('created_time'),
                'last_edited_time': database_info.get('last_edited_time')
            }
            
        except Exception as e:
            self.error_handler.handle_error(
                e, ErrorCategory.NOTION_API,
                context={"operation": "get_database_info"}
            )
            raise
    
    def validate_database_structure(self) -> List[str]:
        """
        Valida que la base de datos tenga la estructura requerida
        
        Returns:
            Lista de advertencias o problemas encontrados
        """
        warnings = []
        
        try:
            database_info = self.notion_client.databases.retrieve(self.database_id)
            properties = database_info['properties']
            
            # Propiedades requeridas con sus tipos esperados
            required_properties = {
                'Attached URL': 'url',
                'Channel': ['select', 'rich_text'],
                'Date': 'date',
                'Message ID': ['rich_text', 'title']
            }
            
            for prop_name, expected_types in required_properties.items():
                if prop_name not in properties:
                    warnings.append(f"Propiedad faltante: '{prop_name}'")
                    continue
                
                actual_type = properties[prop_name]['type']
                
                if isinstance(expected_types, list):
                    if actual_type not in expected_types:
                        warnings.append(f"Propiedad '{prop_name}' tipo '{actual_type}', esperado: {expected_types}")
                else:
                    if actual_type != expected_types:
                        warnings.append(f"Propiedad '{prop_name}' tipo '{actual_type}', esperado: '{expected_types}'")
            
            return warnings
            
        except Exception as e:
            self.error_handler.handle_error(
                e, ErrorCategory.NOTION_API,
                context={"operation": "validate_database_structure"}
            )
            return [f"Error validando estructura: {str(e)}"]


if __name__ == "__main__":
    # Pruebas de la clase NotionDataExtractor
    import asyncio
    import logging
    
    print("🧪 PRUEBAS DE NotionDataExtractor")
    print("="*50)
    
    try:
        # Configurar logging para pruebas
        logger = logging.getLogger('test_notion_extractor')
        logger.setLevel(logging.INFO)
        
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # Crear dependencias
        print("\n1️⃣ Inicializando dependencias...")
        config = ConfigManager()
        error_handler = ErrorHandler(logger)
        
        # Crear extractor
        print("\n2️⃣ Inicializando NotionDataExtractor...")
        extractor = NotionDataExtractor(config, error_handler)
        
        # Probar información de base de datos
        print("\n3️⃣ Obteniendo información de base de datos...")
        db_info = extractor.get_database_info()
        print(f"✅ Base de datos: {db_info['title']}")
        print(f"   └── Propiedades: {len(db_info['properties'])}")
        print(f"   └── Creada: {db_info['created_time'][:10]}")
        
        # Validar estructura
        print("\n4️⃣ Validando estructura de base de datos...")
        warnings = extractor.validate_database_structure()
        if warnings:
            print("⚠️ Advertencias encontradas:")
            for warning in warnings:
                print(f"   - {warning}")
        else:
            print("✅ Estructura de base de datos válida")
        
        # Extraer URLs de YouTube (versión limitada para pruebas)
        print("\n5️⃣ Extrayendo URLs de YouTube...")
        
        async def test_extraction():
            try:
                channels_data = await extractor.extract_youtube_urls()
                
                print(f"✅ Extracción completada:")
                print(f"   └── {len(channels_data)} canales encontrados")
                
                for channel, videos in list(channels_data.items())[:3]:  # Mostrar solo primeros 3
                    print(f"   └── {channel}: {len(videos)} videos")
                    for video in videos[:2]:  # Mostrar solo primeros 2 videos
                        print(f"       • {video['youtube_url']}")
                
                return channels_data
                
            except Exception as e:
                print(f"❌ Error en extracción: {e}")
                return {}
        
        # Ejecutar extracción
        channels_data = asyncio.run(test_extraction())
        
        # Mostrar estadísticas de errores
        print("\n6️⃣ Estadísticas de errores:")
        error_handler.print_error_summary()
        
        if channels_data:
            print("\n✅ ¡Todas las pruebas de NotionDataExtractor pasaron!")
        else:
            print("\n⚠️ Pruebas completadas con advertencias")
        
    except Exception as e:
        print(f"\n❌ Error en pruebas: {e}")
        import traceback
        traceback.print_exc()