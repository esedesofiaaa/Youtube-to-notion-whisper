"""
Notion API configuration and database mapping.
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ========== NOTION API ==========
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
if not NOTION_TOKEN:
    raise ValueError("NOTION_TOKEN not found in environment variables. Please set it in .env file")
NOTION_VERSION = "2022-06-28"  # Notion API version

# ========== DATABASE IDS ==========
# Query database (source)
DISCORD_MESSAGE_DB_ID = os.getenv('DISCORD_MESSAGE_DB_ID')

# Destination databases
VIDEOS_DB_ID = os.getenv('VIDEOS_DB_ID')  # Unified videos database
DRIVE_UPLOADS_DB_ID = os.getenv('DRIVE_UPLOADS_DB_ID') or VIDEOS_DB_ID # Drive uploads database (defaults to VIDEOS_DB_ID)

# ========== CHANNEL TO DATABASE MAPPING ==========
# Each Discord channel is mapped to a specific Notion database
# Note: Channel names without emojis for n8n compatibility
#
# Configuration Schema:
# - action_type: "create_new_page" (creates new page in destination DB) or
#                "update_origin" (updates the source Discord Message DB entry)
# - database_id: Notion database ID for destination (required for create_new_page)
# - database_name: Human-readable name for logging
# - drive_folder_id: Google Drive folder ID for uploads
# - field_map: Maps logical keys to real Notion column names
#   Logical keys available:
#     - name (title), name_yt_format (title - "YouTube Video: {title}")
#     - date (date), video_date_time (date)
#     - video_link (url), video_url (url), live_video_url (url), video_id (text)
#     - drive_folder (url), drive_folder_link (url)
#     - video_file (url), audio_file (url)
#     - transcript_file (file), transcript_srt_file (file), transcript_text (text)
#     - discord_channel (select), youtube_channel (select), youtube_listing_status (select)
#     - status (select), length_min (number), process_errors (text)
# - status_value: Value to set in status column when complete
# - name_format: Optional format for page title ("default" or "youtube")
#

# ========== BASE CONFIGURATION FOR VIDEOS DATABASE ==========
# Shared configuration for all channels that use the Videos Database
_VIDEOS_DB_BASE_CONFIG = {
    "action_type": "create_new_page",
    "database_id": VIDEOS_DB_ID,
    "database_name": "Videos Database",
    "field_map": {
        # Title and dates
        "name": "Name",                           # title
        "date": "Date",                           # date
        "video_date_time": "Video Date and time", # date
        
        # YouTube info
        "video_link": "Video Link",               # url - YouTube URL
        "live_video_url": "Live Video URL",       # url - same as video_link
        "video_id": "Video ID",                   # text - YouTube video ID
        "youtube_channel": "YouTube Channel",     # select
        
        # Drive folder
        "drive_folder": "Google drive Folder",    # url
        "drive_folder_link": "GoogleDriveFolderLink",  # url - duplicate
        
        # Media files (URLs)
        "video_file": "Video FIle Link",          # url - video on Drive
        "audio_file": "Audio File Link",          # url - audio on Drive
        
        # Transcription
        "transcript_file": "Transcript File",     # file
        "transcript_srt_file": "Transcript SRT File",  # file
        "transcript_text": "Transcript",          # text - first 2000 chars
        
        # Metadata
        "discord_channel": "Discord Channel",     # select
        "status": "Transcript Process Status",    # select
        # "youtube_listing_status": "YoutubeListingStatus",  # DISABLED: property doesn't exist in Videos DB
        "length_min": "Lenght min",               # number (typo in Notion)
    },
    "status_value": "complete"
}

# ========== DRIVE FOLDER IDS (from .env) ==========
DRIVE_FOLDER_MARKET_OUTLOOK = os.getenv('DRIVE_FOLDER_MARKET_OUTLOOK')
DRIVE_FOLDER_MARKET_ANALYSIS = os.getenv('DRIVE_FOLDER_MARKET_ANALYSIS')
DRIVE_FOLDER_EDUCATION = os.getenv('DRIVE_FOLDER_EDUCATION')
DRIVE_FOLDER_MHC_RECORDINGS = os.getenv('DRIVE_FOLDER_MHC_RECORDINGS')
DRIVE_FOLDER_AUDIT_PROCESS = os.getenv('DRIVE_FOLDER_AUDIT_PROCESS')
DRIVE_FOLDER_UPLOADS = os.getenv('DRIVE_FOLDER_UPLOADS')

# ========== CHANNEL MAPPINGS ==========
CHANNEL_TO_DATABASE_MAPPING = {
    # Drive Uploads
    "drive-uploads": {
        "action_type": "create_new_page",
        "database_id": DRIVE_UPLOADS_DB_ID,
        "database_name": "Drive Uploads DB",
        "drive_folder_id": DRIVE_FOLDER_UPLOADS,
        "field_map": {
            "name": "Name",
            "status": "Transcript Process Status",
            "video_file": "Video FIle Link",
            "drive_folder_link": "GoogleDriveFolderLink",
            "audio_file": "Audio File Link",
            "transcript_text": "Transcript",
            "transcript_file": "Transcript File",
            "transcript_srt_file": "Transcript SRT File",
            "video_date_time": "Video Date and time",
            "length_min": "Lenght min",
            "processing_time": "Processing time",
            "process_errors": "ProcessErrors"
        },
        "status_value": "Success"
    },

    # Drive Uploads (Skip Compression)
    "drive-uploads-skip": {
        "action_type": "create_new_page",
        "database_id": DRIVE_UPLOADS_DB_ID,
        "database_name": "Drive Uploads (No Compress)",
        "drive_folder_id": DRIVE_FOLDER_UPLOADS,
        "skip_compression": True,
        "field_map": {
            "name": "Name",
            "status": "Transcript Process Status",
            "video_file": "Video FIle Link",
            "drive_folder_link": "GoogleDriveFolderLink",
            "audio_file": "Audio File Link",
            "transcript_text": "Transcript",
            "transcript_file": "Transcript File",
            "transcript_srt_file": "Transcript SRT File",
            "video_date_time": "Video Date and time",
            "length_min": "Lenght min",
            "processing_time": "Processing time",
            "process_errors": "ProcessErrors"
        },
        "status_value": "Success"
    },

    # Both channels use the same Videos Database with same configuration
    "market-outlook": {
        **_VIDEOS_DB_BASE_CONFIG,
        "drive_folder_id": DRIVE_FOLDER_MARKET_OUTLOOK
    },
    "market-analysis-streams": {
        **_VIDEOS_DB_BASE_CONFIG,
        "drive_folder_id": DRIVE_FOLDER_MARKET_ANALYSIS
    },
    "education": {
        **_VIDEOS_DB_BASE_CONFIG,
        "drive_folder_id": DRIVE_FOLDER_EDUCATION
    },
    "mhc-recordings": {
        **_VIDEOS_DB_BASE_CONFIG,
        "drive_folder_id": DRIVE_FOLDER_MHC_RECORDINGS
    },
    
    # Audit process: updates the origin Discord Message DB entry directly
    "audit-process": {
        "action_type": "update_origin",
        "database_name": "Discord Message Database (audit mode)",
        "drive_folder_id": DRIVE_FOLDER_AUDIT_PROCESS,
        "name_format": "youtube",  # "YouTube Video: {title}"
        "field_map": {
            # Title (YouTube format)
            "name": "Name",                           # title - "YouTube Video: {title}"
            
            # Date
            "video_date_time": "Video Date and time", # date
            
            # YouTube info
            "video_url": "URL",                       # url - YouTube URL
            # "live_video_url": "Live Video URL",     # DISABLED: property doesn't exist in DB
            "video_id": "Video ID",                   # text - YouTube video ID
            "youtube_channel": "YouTube Channel",     # select
            
            # Drive folder
            "drive_folder_link": "GoogleDriveFolderLink",  # url
            
            # Media files (URLs)
            "video_file": "Video FIle Link",          # url - video on Drive
            "audio_file": "Audio File Link",          # url - audio on Drive
            
            # Transcription
            "transcript_file": "Transcript File",     # file
            "transcript_srt_file": "Transcript SRT File",  # file
            "transcript_text": "Transcript",          # text - first 2000 chars
            
            # Metadata
            "status": "Transcript Process Status",    # select
            "youtube_listing_status": "YoutubeListingStatus",  # select - Public/Unlisted
            "length_min": "Lenght min",               # number (typo in Notion)
            "processing_time": "Processing time",     # number - seconds
            "process_errors": "ProcessErrors"         # text - error messages
        },
        "status_value": "Complete"
    }
}

# List of valid channels for processing
VALID_CHANNELS = list(CHANNEL_TO_DATABASE_MAPPING.keys())

# ========== NOTION FIELD STRUCTURE ==========
# Property names in Discord Message Database (source)
# Used when reading data from Discord Message DB
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
    "transcript": "Transcript"  # URL field - link to created Notion page
}

# ========== VALIDATIONS ==========
# Valid YouTube URL patterns
YOUTUBE_URL_PATTERNS = [
    "youtube.com/watch?v=",
    "youtube.com/live/",
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
