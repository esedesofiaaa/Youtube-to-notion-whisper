"""
Cliente para interactuar con Notion API.
"""
from typing import Optional, Dict, Any
from notion_client import Client
from datetime import datetime
from config.logger import get_logger
from config.notion_config import (
    NOTION_TOKEN,
    NOTION_VERSION,
    DISCORD_MESSAGE_DB_ID,
    DISCORD_DB_FIELDS,
    DESTINATION_DB_FIELDS,
    get_destination_database,
    is_valid_channel
)

logger = get_logger(__name__)


class NotionClient:
    """Cliente para operaciones con Notion API."""

    def __init__(self, token: str = None):
        """
        Inicializa el cliente de Notion.

        Args:
            token: Token de autenticación de Notion (opcional, usa variable de entorno por defecto)
        """
        self.token = token or NOTION_TOKEN
        self.client = Client(auth=self.token)
        logger.info("✅ Cliente de Notion inicializado correctamente")

    def get_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene una página de Notion por su ID.

        Args:
            page_id: ID de la página de Notion

        Returns:
            Dict con los datos de la página o None si falla
        """
        try:
            page = self.client.pages.retrieve(page_id=page_id)
            logger.info(f"📄 Página obtenida: {page_id}")
            return page
        except Exception as e:
            logger.error(f"❌ Error al obtener página {page_id}: {e}", exc_info=True)
            return None

    def get_discord_message_entry(self, page_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene una entrada de Discord Message Database y extrae campos relevantes.

        Args:
            page_id: ID de la página en Discord Message Database

        Returns:
            Dict con campos extraídos o None si falla
        """
        try:
            page = self.get_page(page_id)
            if not page:
                return None

            properties = page.get("properties", {})

            # Extraer campos relevantes
            data = {
                "page_id": page_id,
                "page_url": page.get("url"),
                "channel": self._extract_select(properties.get(DISCORD_DB_FIELDS["channel"])),
                "attached_url": self._extract_url(properties.get(DISCORD_DB_FIELDS["attached_url"])),
                "date": self._extract_date(properties.get(DISCORD_DB_FIELDS["date"])),
                "author": self._extract_title(properties.get(DISCORD_DB_FIELDS["author"])),
                "content": self._extract_rich_text(properties.get(DISCORD_DB_FIELDS["content"])),
                "message_url": self._extract_url(properties.get(DISCORD_DB_FIELDS["message_url"]))
            }

            logger.info(f"✅ Datos extraídos de Discord Message DB: Canal={data['channel']}, URL={data['attached_url']}")
            return data

        except Exception as e:
            logger.error(f"❌ Error al obtener entrada de Discord Message DB {page_id}: {e}", exc_info=True)
            return None

    def create_video_page(
        self,
        database_id: str,
        title: str,
        video_date: str,
        video_url: str,
        drive_folder_url: str,
        drive_video_url: str,
        discord_channel: str
    ) -> Optional[Dict[str, Any]]:
        """
        Crea una página en una base de datos de destino (Paradise Island o Docs Videos).

        Args:
            database_id: ID de la base de datos de destino
            title: Título de la página (formato: "YYYY-MM-DD - Título del video")
            video_date: Fecha del video (YYYY-MM-DD)
            video_url: URL del video de YouTube
            drive_folder_url: URL de la carpeta en Google Drive
            drive_video_url: URL del video MP4 en Google Drive
            discord_channel: Nombre del canal de Discord

        Returns:
            Dict con la página creada o None si falla
        """
        try:
            # Construir propiedades
            properties = {
                DESTINATION_DB_FIELDS["name"]: {
                    "title": [{"text": {"content": title}}]
                },
                DESTINATION_DB_FIELDS["date"]: {
                    "date": {"start": video_date}
                },
                DESTINATION_DB_FIELDS["video_link"]: {
                    "url": video_url
                },
                DESTINATION_DB_FIELDS["google_drive_folder"]: {
                    "url": drive_folder_url
                },
                DESTINATION_DB_FIELDS["drive_link"]: {
                    "url": drive_video_url
                },
                DESTINATION_DB_FIELDS["discord_channel"]: {
                    "select": {"name": discord_channel}
                }
            }

            # Crear página
            page = self.client.pages.create(
                parent={"database_id": database_id},
                properties=properties
            )

            page_url = page.get("url")
            logger.info(f"✅ Página creada en Notion: {page_url}")
            return page

        except Exception as e:
            logger.error(f"❌ Error al crear página en Notion: {e}", exc_info=True)
            return None

    def update_transcript_field(self, page_id: str, transcript_url: str) -> bool:
        """
        Actualiza el campo Transcript en Discord Message Database con la URL de la página creada.

        Args:
            page_id: ID de la página en Discord Message Database
            transcript_url: URL de la página de transcripción en Notion

        Returns:
            bool: True si se actualizó correctamente
        """
        try:
            self.client.pages.update(
                page_id=page_id,
                properties={
                    DISCORD_DB_FIELDS["transcript"]: {
                        "url": transcript_url
                    }
                }
            )
            logger.info(f"✅ Campo Transcript actualizado en Discord Message DB: {page_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error al actualizar campo Transcript: {e}", exc_info=True)
            return False

    # ========== MÉTODOS AUXILIARES PARA EXTRAER DATOS ==========

    def _extract_title(self, prop: Optional[Dict]) -> str:
        """Extrae texto de una propiedad tipo title."""
        if not prop or prop.get("type") != "title":
            return ""
        title_array = prop.get("title", [])
        return title_array[0].get("text", {}).get("content", "") if title_array else ""

    def _extract_rich_text(self, prop: Optional[Dict]) -> str:
        """Extrae texto de una propiedad tipo rich_text."""
        if not prop or prop.get("type") != "rich_text":
            return ""
        text_array = prop.get("rich_text", [])
        return text_array[0].get("text", {}).get("content", "") if text_array else ""

    def _extract_select(self, prop: Optional[Dict]) -> str:
        """Extrae valor de una propiedad tipo select."""
        if not prop or prop.get("type") != "select":
            return ""
        select_obj = prop.get("select")
        return select_obj.get("name", "") if select_obj else ""

    def _extract_url(self, prop: Optional[Dict]) -> str:
        """Extrae URL de una propiedad tipo url."""
        if not prop or prop.get("type") != "url":
            return ""
        return prop.get("url", "") or ""

    def _extract_date(self, prop: Optional[Dict]) -> str:
        """Extrae fecha de una propiedad tipo date."""
        if not prop or prop.get("type") != "date":
            return ""
        date_obj = prop.get("date")
        return date_obj.get("start", "") if date_obj else ""

    def validate_webhook_data(self, data: Dict[str, Any]) -> tuple[bool, str]:
        """
        Valida que los datos del webhook sean correctos.

        Args:
            data: Datos recibidos del webhook

        Returns:
            tuple: (es_válido: bool, mensaje_error: str)
        """
        # Validar campos requeridos
        required_fields = ["discord_entry_id", "youtube_url", "channel"]
        for field in required_fields:
            if field not in data or not data[field]:
                return False, f"Campo requerido faltante: {field}"

        # Validar canal
        channel = data["channel"]
        if not is_valid_channel(channel):
            return False, f"Canal inválido: {channel}. Canales válidos: {list(get_destination_database.keys())}"

        # Validar URL de YouTube
        from config.notion_config import is_valid_youtube_url
        if not is_valid_youtube_url(data["youtube_url"]):
            return False, f"URL de YouTube inválida: {data['youtube_url']}"

        return True, ""
