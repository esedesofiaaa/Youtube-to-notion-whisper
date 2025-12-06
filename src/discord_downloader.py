"""
Discord video downloader.
Downloads videos from Discord CDN after fetching message data.
"""
import os
import requests
from pathlib import Path
from typing import Optional, Dict, Any
from config.logger import get_logger
from src.models import MediaFile
from src.discord_client import DiscordMessageFetcher, is_valid_discord_message_url

logger = get_logger(__name__)


class DiscordDownloader:
    """Download videos from Discord messages."""
    
    def __init__(self, output_dir: str, user_token: str = None):
        """
        Initialize Discord downloader.
        
        Args:
            output_dir: Directory to save downloaded files
            user_token: Discord user token (optional, uses env var if not provided)
        """
        self.output_dir = output_dir
        self.fetcher = DiscordMessageFetcher(user_token)
        
        # Ensure output directory exists
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    def download_from_message_url(self, message_url: str) -> tuple[Optional[MediaFile], Dict[str, Any]]:
        """
        Download video from Discord message URL.
        
        Workflow:
        1. Fetch message data using Discord API
        2. Extract video attachment from attached_files
        3. Download video from Discord CDN
        4. Return MediaFile object + message metadata
        
        Args:
            message_url: Discord message URL
                Format: https://discord.com/channels/{guild_id}/{channel_id}/{message_id}
        
        Returns:
            tuple: (MediaFile object, message_data dict)
                - MediaFile: Downloaded video file info (or None if no video found)
                - message_data: Complete message metadata from Discord
        
        Raises:
            ValueError: If URL is invalid or no video attachment found
            requests.HTTPError: If download fails
        """
        logger.info("=" * 80)
        logger.info("📥 Starting Discord video download")
        logger.info(f"   Message URL: {message_url}")
        logger.info("=" * 80)
        
        # Validate URL format
        if not is_valid_discord_message_url(message_url):
            raise ValueError(f"Invalid Discord message URL: {message_url}")
        
        # Fetch message data
        logger.info("🔍 Fetching message data from Discord API...")
        message_data = self.fetcher.fetch_message_data(message_url)
        
        # Find video attachment
        video_attachment = self._find_video_attachment(message_data)
        if not video_attachment:
            logger.warning("⚠️ No video attachment found in message")
            return None, message_data
        
        # Download video
        logger.info(f"📥 Downloading video: {video_attachment['name']}")
        logger.info(f"   Size: {video_attachment['size'] / 1024 / 1024:.2f} MB")
        logger.info(f"   URL: {video_attachment['url'][:80]}...")
        
        video_file = self._download_file(
            video_attachment['url'],
            video_attachment['name']
        )
        
        logger.info(f"✅ Video downloaded successfully")
        logger.info(f"   Path: {video_file.path}")
        logger.info("=" * 80)
        
        return video_file, message_data
    
    def _find_video_attachment(self, message_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find first video attachment in message data.
        
        Args:
            message_data: Message data from Discord API
        
        Returns:
            dict: Video attachment data or None if not found
        """
        attached_files = message_data.get('attached_files', [])
        
        # Video extensions to look for
        video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.m4v'}
        
        for file in attached_files:
            # Skip images
            if file.get('is_image'):
                continue
            
            # Check extension
            extension = file.get('extension', '').lower()
            if extension in video_extensions:
                logger.debug(f"   Found video: {file['name']} ({extension})")
                return file
        
        # No video found
        logger.warning(f"   No video found. Attachments: {[f['name'] for f in attached_files]}")
        return None
    
    def _download_file(self, cdn_url: str, filename: str) -> MediaFile:
        """
        Download file from Discord CDN.
        
        Args:
            cdn_url: Discord CDN URL
            filename: Original filename
        
        Returns:
            MediaFile: Downloaded file info
        
        Raises:
            requests.HTTPError: If download fails
        """
        output_path = Path(self.output_dir) / filename
        
        # Download with streaming to handle large files
        try:
            response = requests.get(cdn_url, stream=True, timeout=30)
            response.raise_for_status()
            
            # Write to disk in chunks
            with open(output_path, 'wb') as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            
            logger.debug(f"   Downloaded {downloaded / 1024 / 1024:.2f} MB")
            
            return MediaFile(
                path=str(output_path),
                filename=filename,
                file_type='video'
            )
        
        except requests.HTTPError as e:
            logger.error(f"❌ Failed to download from Discord CDN: {e}")
            logger.error(f"   Status code: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error during download: {e}")
            raise
    
    def get_message_metadata(self, message_url: str) -> Dict[str, Any]:
        """
        Get message metadata without downloading video.
        
        Useful for previewing message info before downloading.
        
        Args:
            message_url: Discord message URL
        
        Returns:
            dict: Message metadata
        """
        return self.fetcher.fetch_message_data(message_url)
