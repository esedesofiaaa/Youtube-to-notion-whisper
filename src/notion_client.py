"""
Client to interact with Notion API.
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
    get_destination_database,
    is_valid_channel
)

logger = get_logger(__name__)


class NotionClient:
    """Client for operations with Notion API."""

    def __init__(self, token: str = None):
        """
        Initialize the Notion client.

        Args:
            token: Notion authentication token (optional, uses environment variable by default)
        """
        self.token = token or NOTION_TOKEN
        self.client = Client(auth=self.token)
        logger.info("✅ Notion client initialized successfully")

    def get_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a Notion page by its ID.

        Args:
            page_id: Notion page ID

        Returns:
            Dict with page data or None if fails
        """
        try:
            page = self.client.pages.retrieve(page_id=page_id)
            logger.info(f"📄 Page retrieved: {page_id}")
            return page
        except Exception as e:
            logger.error(f"❌ Error retrieving page {page_id}: {e}", exc_info=True)
            return None

    def get_discord_message_entry(self, page_id: str) -> Optional[Dict[str, Any]]:
        """
        Get an entry from Discord Message Database and extract relevant fields.

        Args:
            page_id: Page ID in Discord Message Database

        Returns:
            Dict with extracted fields or None if fails
        """
        try:
            page = self.get_page(page_id)
            if not page:
                return None

            properties = page.get("properties", {})

            # Extract relevant fields
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

            logger.info(f"✅ Data extracted from Discord Message DB: Channel={data['channel']}, URL={data['attached_url']}")
            return data

        except Exception as e:
            logger.error(f"❌ Error retrieving Discord Message DB entry {page_id}: {e}", exc_info=True)
            return None

    def create_video_page(
        self,
        database_id: str,
        field_map: dict,
        data: dict
    ) -> Optional[Dict[str, Any]]:
        """
        Create a page in a destination database using data-driven field mapping.

        Args:
            database_id: Destination database ID
            field_map: Dictionary mapping logical keys to Notion column names
            data: Dictionary with data values keyed by logical names:
                - name: Page title (required)
                - date: Video date YYYY-MM-DD
                - video_date_time: Video date with time
                - video_link: YouTube URL
                - live_video_url: Live stream URL (usually same as video_link)
                - video_id: YouTube video ID
                - youtube_channel: YouTube channel name
                - drive_folder: Drive folder URL
                - drive_folder_link: Drive folder URL (duplicate)
                - video_file: Video file URL on Drive
                - audio_file: Audio file URL on Drive
                - transcript_file: Transcript TXT file URL
                - transcript_srt_file: Transcript SRT file URL
                - transcript_text: First 2000 chars of transcript
                - discord_channel: Discord channel name
                - status: Processing status
                - length_min: Video duration in minutes
                - process_errors: Error message if any

        Returns:
            Dict with created page or None if fails
        """
        try:
            properties = {}

            # Build properties dynamically based on field_map
            for logical_key, column_name in field_map.items():
                value = data.get(logical_key)
                if value is None:
                    continue

                # Map by property type based on logical key
                if logical_key == "name":
                    properties[column_name] = self.build_title_property(value)
                
                elif logical_key in ("date", "video_date_time"):
                    properties[column_name] = self.build_date_property(value)
                
                elif logical_key in ("video_link", "video_url", "live_video_url", "drive_folder", 
                                     "drive_folder_link", "video_file", "audio_file"):
                    properties[column_name] = self.build_url_property(value)
                
                elif logical_key in ("transcript_file", "transcript_srt_file"):
                    filename = "Transcript.txt" if "srt" not in logical_key else "Transcript.srt"
                    properties[column_name] = self.build_files_property(value, filename)
                
                elif logical_key in ("discord_channel", "youtube_channel", "status", "youtube_listing_status"):
                    properties[column_name] = self.build_select_property(value)
                
                elif logical_key in ("length_min", "processing_time"):
                    properties[column_name] = self.build_number_property(value)
                
                elif logical_key in ("video_id", "transcript_text", "process_errors"):
                    properties[column_name] = self.build_text_property(value)

            # Create page
            page = self.client.pages.create(
                parent={"database_id": database_id},
                properties=properties
            )

            page_url = page.get("url")
            logger.info(f"✅ Page created in Notion: {page_url}")
            return page

        except Exception as e:
            logger.error(f"❌ ERROR creating page in Notion: {e}", exc_info=True)
            return None

    def update_transcript_field(self, page_id: str, transcript_url: str) -> bool:
        """
        Update the Transcript field in Discord Message Database with the created page URL.

        Args:
            page_id: Page ID in Discord Message Database
            transcript_url: URL of transcription page in Notion

        Returns:
            bool: True if updated successfully
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
            logger.info(f"✅ Transcript field updated in Discord Message DB: {page_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error updating Transcript field: {e}", exc_info=True)
            return False

    def update_page_properties(self, page_id: str, properties: dict) -> bool:
        """
        Update properties of a Notion page with pre-formatted properties dict.

        This is a generic method that accepts already-formatted Notion properties.
        Use the build_* helper methods to construct the properties dict.

        Args:
            page_id: Notion page ID to update
            properties: Dict of properties formatted for Notion API

        Returns:
            bool: True if updated successfully
        """
        try:
            self.client.pages.update(
                page_id=page_id,
                properties=properties
            )
            logger.info(f"✅ Page properties updated: {page_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error updating page properties: {e}", exc_info=True)
            return False

    def update_status_field(self, page_id: str, status_value: str, field_map: dict) -> bool:
        """
        Update only the Transcript Process Status field (optimized for progress tracking).
        
        This method is used during audit-process pipeline to track processing progress
        in real-time without updating all other fields.

        Args:
            page_id: Notion page ID to update
            status_value: Status value to set (e.g., "Processing", "Downloading", etc.)
            field_map: Field mapping dict to find the status column name

        Returns:
            bool: True if updated successfully
        """
        try:
            # Get the status field name from field_map
            status_field_name = field_map.get("status")
            if not status_field_name:
                logger.warning("⚠️ No 'status' field found in field_map, skipping status update")
                return False

            # Update only the status field
            properties = {
                status_field_name: self.build_select_property(status_value)
            }
            
            self.client.pages.update(
                page_id=page_id,
                properties=properties
            )
            logger.info(f"📊 Status updated to '{status_value}' for page: {page_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error updating status field: {e}", exc_info=True)
            return False

    def update_error_field(self, page_id: str, error_message: str, field_map: dict) -> bool:
        """
        Update the Process Errors field when an error occurs.
        
        This method is used during audit-process pipeline to record error details
        when processing fails.

        Args:
            page_id: Notion page ID to update
            error_message: Error message to record
            field_map: Field mapping dict to find the process_errors column name

        Returns:
            bool: True if updated successfully
        """
        try:
            # Get the error field name from field_map
            error_field_name = field_map.get("process_errors")
            if not error_field_name:
                logger.warning("⚠️ No 'process_errors' field found in field_map, skipping error update")
                return False

            # Update the error field and status
            properties = {
                error_field_name: self.build_text_property(error_message)
            }
            
            # Also update status to "Error" if status field exists
            status_field_name = field_map.get("status")
            if status_field_name:
                properties[status_field_name] = self.build_select_property("Error")
            
            self.client.pages.update(
                page_id=page_id,
                properties=properties
            )
            logger.info(f"❌ Error recorded for page: {page_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error updating error field: {e}", exc_info=True)
            return False

    # ========== PROPERTY BUILDER METHODS (Data-Driven) ==========

    @staticmethod
    def build_url_property(url: str) -> dict:
        """Build a URL type property value."""
        return {"url": url}

    @staticmethod
    def build_files_property(url: str, filename: str = "File") -> dict:
        """Build a Files & Media type property value with external URL."""
        return {
            "files": [{"name": filename, "external": {"url": url}}]
        }

    @staticmethod
    def build_select_property(value: str) -> dict:
        """Build a Select type property value."""
        return {"select": {"name": value}}

    @staticmethod
    def build_title_property(text: str) -> dict:
        """Build a Title type property value."""
        return {"title": [{"text": {"content": text}}]}

    @staticmethod
    def build_text_property(text: str) -> dict:
        """Build a Rich Text type property value."""
        # Notion has a 2000 char limit per text block
        truncated = text[:2000] if len(text) > 2000 else text
        return {"rich_text": [{"text": {"content": truncated}}]}

    @staticmethod
    def build_date_property(date_str: str) -> dict:
        """Build a Date type property value."""
        return {"date": {"start": date_str}}

    @staticmethod
    def build_number_property(value: float) -> dict:
        """Build a Number type property value."""
        return {"number": value}

    def add_transcript_dropdown(self, page_id: str, transcript_text: str) -> bool:
        """
        Add a dropdown (toggle) block with the transcript text to a Notion page.

        Args:
            page_id: Page ID where to add the dropdown
            transcript_text: Full transcript text to include in the dropdown

        Returns:
            bool: True if added successfully
        """
        try:
            # Split transcript into chunks if too long (Notion has limits)
            # Maximum 2000 characters per text block
            max_chars = 2000
            chunks = []
            
            if len(transcript_text) <= max_chars:
                chunks = [transcript_text]
            else:
                # Split by paragraphs or sentences to avoid cutting words
                words = transcript_text.split()
                current_chunk = ""
                for word in words:
                    if len(current_chunk) + len(word) + 1 <= max_chars:
                        current_chunk += word + " "
                    else:
                        chunks.append(current_chunk.strip())
                        current_chunk = word + " "
                if current_chunk:
                    chunks.append(current_chunk.strip())

            # Create toggle (dropdown) block with transcript
            children = []
            for chunk in chunks:
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": chunk}}]
                    }
                })

            toggle_block = {
                "object": "block",
                "type": "toggle",
                "toggle": {
                    "rich_text": [{"type": "text", "text": {"content": "📝 Transcript"}}],
                    "children": children
                }
            }

            # Append block to page
            self.client.blocks.children.append(
                block_id=page_id,
                children=[toggle_block]
            )

            logger.info(f"✅ Transcript dropdown added to Notion page: {page_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error adding transcript dropdown: {e}", exc_info=True)
            return False

    # ========== HELPER METHODS TO EXTRACT DATA ==========

    def _extract_title(self, prop: Optional[Dict]) -> str:
        """Extract text from a title type property."""
        if not prop or prop.get("type") != "title":
            return ""
        title_array = prop.get("title", [])
        return title_array[0].get("text", {}).get("content", "") if title_array else ""

    def _extract_rich_text(self, prop: Optional[Dict]) -> str:
        """Extract text from a rich_text type property."""
        if not prop or prop.get("type") != "rich_text":
            return ""
        text_array = prop.get("rich_text", [])
        return text_array[0].get("text", {}).get("content", "") if text_array else ""

    def _extract_select(self, prop: Optional[Dict]) -> str:
        """Extract value from a select type property."""
        if not prop or prop.get("type") != "select":
            return ""
        select_obj = prop.get("select")
        return select_obj.get("name", "") if select_obj else ""

    def _extract_url(self, prop: Optional[Dict]) -> str:
        """Extract URL from a url type property."""
        if not prop or prop.get("type") != "url":
            return ""
        return prop.get("url", "") or ""

    def _extract_date(self, prop: Optional[Dict]) -> str:
        """Extract date from a date type property."""
        if not prop or prop.get("type") != "date":
            return ""
        date_obj = prop.get("date")
        return date_obj.get("start", "") if date_obj else ""
    
    def _extract_files(self, prop: Optional[Dict]) -> Optional[str]:
        """Extract first file URL from a files type property."""
        if not prop or prop.get("type") != "files":
            return None
        files = prop.get("files", [])
        if files and len(files) > 0:
            first_file = files[0]
            if first_file.get("type") == "external":
                return first_file.get("external", {}).get("url")
            elif first_file.get("type") == "file":
                return first_file.get("file", {}).get("url")
        return None

    def validate_webhook_data(self, data: Dict[str, Any]) -> tuple[bool, str]:
        """
        Validate that webhook data is correct.

        Args:
            data: Webhook data received

        Returns:
            tuple: (is_valid: bool, error_message: str)
        """
        # Validate required fields
        required_fields = ["discord_entry_id", "youtube_url", "channel"]
        for field in required_fields:
            if field not in data or not data[field]:
                return False, f"Required field missing: {field}"


        # Validate channel
        channel = data["channel"]
        if not is_valid_channel(channel):
            return False, f"Invalid channel: {channel}. Valid channels: {list(get_destination_database.keys())}"

        # Validate YouTube URL
        from config.notion_config import is_valid_youtube_url
        if not is_valid_youtube_url(data["youtube_url"]):
            return False, f"Invalid YouTube URL: {data['youtube_url']}"

        return True, ""

    def find_video_by_url(self, youtube_url: str) -> Optional[Dict[str, Any]]:
        """
        Search for a video across all Notion databases by YouTube URL.
        
        Args:
            youtube_url: YouTube video URL to search for
            
        Returns:
            Dict with video info if found:
                {
                    "page_id": str,
                    "database_id": str,
                    "database_name": str,
                    "page_url": str,
                    "has_transcript": bool,
                    "transcript_file": str | None,
                    "transcript_srt_file": str | None
                }
            None if not found
        """
        from config.notion_config import VIDEOS_DB_ID, DISCORD_MESSAGE_DB_ID, CHANNEL_TO_DATABASE_MAPPING
        
        logger.info(f"🔍 Searching for video: {youtube_url}")
        
        # List of databases to search with their specific URL field names
        databases_to_search = [
            {"id": VIDEOS_DB_ID, "name": "Videos Database", "url_field": "Video Link"},
            {"id": DISCORD_MESSAGE_DB_ID, "name": "Discord Message Database", "url_field": "URL"}
        ]
        
        for db in databases_to_search:
            try:
                logger.debug(f"   Searching in: {db['name']}")
                
                # Query database filtering by URL
                response = self.client.databases.query(
                    database_id=db["id"],
                    filter={
                        "property": db["url_field"],
                        "url": {
                            "equals": youtube_url
                        }
                    }
                )
                
                results = response.get("results", [])
                
                if results:
                    page = results[0]  # Get first match
                    page_id = page["id"]
                    properties = page.get("properties", {})
                    
                    # Check if has transcript
                    transcript_file_prop = properties.get("Transcript File", {})
                    transcript_srt_prop = properties.get("Transcript SRT File", {})
                    
                    has_transcript = bool(
                        self._extract_files(transcript_file_prop) or 
                        self._extract_files(transcript_srt_prop)
                    )
                    
                    logger.info(f"✅ Video found in {db['name']}: {page_id}")
                    logger.info(f"   Has transcript: {has_transcript}")
                    
                    return {
                        "page_id": page_id,
                        "database_id": db["id"],
                        "database_name": db["name"],
                        "page_url": page.get("url"),
                        "has_transcript": has_transcript,
                        "transcript_file": self._extract_files(transcript_file_prop),
                        "transcript_srt_file": self._extract_files(transcript_srt_prop)
                    }
                    
            except Exception as e:
                logger.warning(f"⚠️ Error searching in {db['name']}: {e}")
                continue
        
        logger.info("❌ Video not found in any database")
        return None

