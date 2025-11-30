"""
Notion API configuration and database mapping.
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ========== NOTION API ==========
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
NOTION_VERSION = "2022-06-28"  # Notion API version

# ========== DATABASE IDS ==========
# Query database (source)
DISCORD_MESSAGE_DB_ID = os.getenv('DISCORD_MESSAGE_DB_ID')

# Destination databases
PARADISE_ISLAND_DB_ID = os.getenv('PARADISE_ISLAND_DB_ID')
DOCS_VIDEOS_DB_ID = os.getenv('DOCS_VIDEOS_DB_ID')

# ========== CHANNEL TO DATABASE MAPPING ==========
# Each Discord channel is mapped to a specific Notion database
# Note: Channel names without emojis for n8n compatibility
CHANNEL_TO_DATABASE_MAPPING = {
    "market-outlook": {
        "database_id": PARADISE_ISLAND_DB_ID,
        "database_name": "Paradise Island Videos Database"
    },
    "market-analysis-streams": {
        "database_id": DOCS_VIDEOS_DB_ID,
        "database_name": "Docs Videos Database"
    }
}

# List of valid channels for processing
VALID_CHANNELS = list(CHANNEL_TO_DATABASE_MAPPING.keys())

# ========== NOTION FIELD STRUCTURE ==========
# Property names in Discord Message Database (source)
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
    "transcript": "Transcript"  # Here we will store the URL of the created Notion page
}

# Property names in destination databases
# These properties are common to both destination DBs
DESTINATION_DB_FIELDS = {
    "name": "Name",                          # Title
    "date": "Date",                          # Date
    "video_link": "Video Link",              # URL
    "drive_link": "Drive Link",              # URL (link to video on Drive)
    "google_drive_folder": "Google drive Folder",  # URL (link to folder)
    "discord_channel": "Discord Channel"     # Select
}

# Specific fields for Docs Videos Database
DOCS_VIDEOS_SPECIFIC_FIELDS = {
    # Drive Link and DiscordTradersRelation are relations, but we will omit them for now
}

# Specific fields for Paradise Island Videos Database
PARADISE_ISLAND_SPECIFIC_FIELDS = {
    # Drive Link is relation, but we will handle it as URL per instructions
}

# ========== VALIDATIONS ==========
# Valid YouTube URL patterns
YOUTUBE_URL_PATTERNS = [
    "youtube.com/watch?v=",
    "youtu.be/",
    "youtube.com/shorts/",
    "youtube.com/embed/"
]

def is_valid_youtube_url(url: str) -> bool:
    """
    Check if a URL is a valid YouTube URL.

    Args:
        url: URL to validate

    Returns:
        bool: True if it's a valid YouTube URL
    """
    if not url:
        return False
    return any(pattern in url.lower() for pattern in YOUTUBE_URL_PATTERNS)


def get_destination_database(channel: str) -> dict:
    """
    Get destination database information for a given channel.

    Args:
        channel: Discord channel name

    Returns:
        dict: Dictionary with database_id and database_name, or None if not found
    """
    return CHANNEL_TO_DATABASE_MAPPING.get(channel)


def is_valid_channel(channel: str) -> bool:
    """
    Check if a channel is in the list of valid channels for processing.

    Args:
        channel: Discord channel name

    Returns:
        bool: True if the channel is valid
    """
    return channel in VALID_CHANNELS
