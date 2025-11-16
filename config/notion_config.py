"""
Configuración de Notion API y mapeo de bases de datos.
"""
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# ========== NOTION API ==========
NOTION_TOKEN = os.getenv('NOTION_TOKEN', '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')
NOTION_VERSION = "2022-06-28"  # Versión de la API de Notion

# ========== BASE DE DATOS IDS ==========
# Base de datos de consulta (origen)
DISCORD_MESSAGE_DB_ID = "28bdaf66daf7816383e6ce8390b0a866"

# Bases de datos de destino
PARADISE_ISLAND_DB_ID = "287daf66daf7807290d0fb514fdf4d86"
DOCS_VIDEOS_DB_ID = "287daf66daf780fb89f7dd15bac7aa2a"

# ========== MAPEO DE CANALES A BASES DE DATOS ==========
# Cada canal de Discord se mapea a una base de datos de Notion específica
CHANNEL_TO_DATABASE_MAPPING = {
    "🎙・market-outlook": {
        "database_id": PARADISE_ISLAND_DB_ID,
        "database_name": "Paradise Island Videos Database"
    },
    "🎙・market-analysis-streams": {
        "database_id": DOCS_VIDEOS_DB_ID,
        "database_name": "Docs Videos Database"
    }
}

# Lista de canales válidos para procesamiento
VALID_CHANNELS = list(CHANNEL_TO_DATABASE_MAPPING.keys())

# ========== ESTRUCTURA DE CAMPOS DE NOTION ==========
# Nombres de propiedades en Discord Message Database (origen)
DISCORD_DB_FIELDS = {
    "author": "Author",
    "message_id": "Message ID",
    "date": "Date",
    "server": "Server",
    "channel": "Channel",
    "content": "Content",
    "attached_url": "Attached URL",
    "preview_images": "Preview Images",
    "attached_file": "Attached File",
    "message_url": "Message URL",
    "original_message": "Original Message",
    "analyst_type": "Analyst Type",
    "confidence": "Confidence (0-100)",
    "sentiment": "Sentiment",
    "summary": "Summary",
    "token": "Token",
    "transcript": "Transcript"  # Aquí guardaremos la URL de la página de Notion creada
}

# Nombres de propiedades en bases de datos de destino
# Estas propiedades son comunes a ambas DBs de destino
DESTINATION_DB_FIELDS = {
    "name": "Name",                          # Title
    "date": "Date",                          # Date
    "video_link": "Video Link",              # URL
    "drive_link": "Drive Link",              # URL (link al video en Drive)
    "google_drive_folder": "Google drive Folder",  # URL (link a la carpeta)
    "discord_channel": "Discord Channel"     # Select
}

# Campos específicos de Docs Videos Database
DOCS_VIDEOS_SPECIFIC_FIELDS = {
    # Drive Link y DiscordTradersRelation son relations, pero los omitiremos por ahora
}

# Campos específicos de Paradise Island Videos Database
PARADISE_ISLAND_SPECIFIC_FIELDS = {
    # Drive Link es relation, pero lo manejaremos como URL según instrucciones
}

# ========== VALIDACIONES ==========
# Patrones de URL de YouTube válidos
YOUTUBE_URL_PATTERNS = [
    "youtube.com/watch?v=",
    "youtu.be/",
    "youtube.com/shorts/",
    "youtube.com/embed/"
]

def is_valid_youtube_url(url: str) -> bool:
    """
    Verifica si una URL es de YouTube válida.

    Args:
        url: URL a validar

    Returns:
        bool: True si es URL de YouTube válida
    """
    if not url:
        return False
    return any(pattern in url.lower() for pattern in YOUTUBE_URL_PATTERNS)


def get_destination_database(channel: str) -> dict:
    """
    Obtiene información de la base de datos de destino para un canal dado.

    Args:
        channel: Nombre del canal de Discord

    Returns:
        dict: Diccionario con database_id y database_name, o None si no existe
    """
    return CHANNEL_TO_DATABASE_MAPPING.get(channel)


def is_valid_channel(channel: str) -> bool:
    """
    Verifica si un canal está en la lista de canales válidos para procesamiento.

    Args:
        channel: Nombre del canal de Discord

    Returns:
        bool: True si el canal es válido
    """
    return channel in VALID_CHANNELS
