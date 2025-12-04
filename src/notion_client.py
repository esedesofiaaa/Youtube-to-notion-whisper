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
    DESTINATION_DB_FIELDS,
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
        title: str,
        video_date: str,
        video_url: str,
        drive_folder_url: str,
        drive_video_url: str,
        discord_channel: str,
        audio_file_url: str = None,
        transcript_file_url: str = None,
        transcript_srt_file_url: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a page in a destination database (Paradise Island or Docs Videos).

        Args:
            database_id: Destination database ID
            title: Page title (format: "YYYY-MM-DD - Video Title")
            video_date: Video date (YYYY-MM-DD)
            video_url: YouTube video URL
            drive_folder_url: URL of Google Drive folder
            drive_video_url: URL of MP4 video on Google Drive (not used, kept for compatibility)
            discord_channel: Discord channel name
            audio_file_url: URL of audio file on Google Drive (optional)
            transcript_file_url: URL of transcript TXT file on Google Drive (optional)
            transcript_srt_file_url: URL of transcript SRT file on Google Drive (optional)

        Returns:
            Dict with created page or None if fails
        """
        try:
            # Build properties (Drive Link is OMITTED to avoid relation type conflict)
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
                DESTINATION_DB_FIELDS["discord_channel"]: {
                    "select": {"name": discord_channel}
                }
            }

            # Add audio file link if provided
            if audio_file_url:
                properties[DESTINATION_DB_FIELDS["audio_file_link"]] = {
                    "url": audio_file_url
                }

            # Add transcript file if provided (Files & Media type)
            if transcript_file_url:
                properties[DESTINATION_DB_FIELDS["transcript_file"]] = {
                    "files": [{"name": "Transcript.txt", "external": {"url": transcript_file_url}}]
                }

            # Add transcript SRT file if provided (Files & Media type)
            if transcript_srt_file_url:
                properties[DESTINATION_DB_FIELDS["transcript_srt_file"]] = {
                    "files": [{"name": "Transcript.srt", "external": {"url": transcript_srt_file_url}}]
                }

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
