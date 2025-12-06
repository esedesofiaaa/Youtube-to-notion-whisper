"""
Discord message fetcher using HTTP API (user account).
Retrieves message data including attachments from Discord CDN.
"""
import os
import re
import requests
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from config.logger import get_logger

logger = get_logger(__name__)


class DiscordMessageFetcher:
    """Fetch Discord message data using HTTP API with user token."""
    
    # Discord API base URL
    API_BASE = "https://discord.com/api/v10"
    
    def __init__(self, user_token: str = None):
        """
        Initialize Discord message fetcher.
        
        Args:
            user_token: Discord user account token (from .env if not provided)
        """
        self.token = user_token or os.getenv('DISCORD_USER_TOKEN')
        if not self.token:
            raise ValueError("DISCORD_USER_TOKEN not found in environment variables")
        
        self.headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        }
    
    def fetch_message_data(self, message_url: str) -> Dict[str, Any]:
        """
        Fetch complete message data from Discord URL.
        
        Args:
            message_url: Discord message URL
                Format: https://discord.com/channels/{guild_id}/{channel_id}/{message_id}
        
        Returns:
            dict: Message data with structure:
                {
                    "timestamp": ISO timestamp,
                    "message_id": str,
                    "author": str,
                    "date": ISO timestamp,
                    "server": str,
                    "channel": str,
                    "category": str,
                    "content": str,
                    "attached_url": str or None,
                    "message_url": str,
                    "attached_files": [
                        {
                            "name": str,
                            "url": str,
                            "size": int,
                            "width": int or None,
                            "height": int or None,
                            "is_image": bool,
                            "extension": str
                        }
                    ],
                    "preview_images": None,
                    "original_message_id": None,
                    "has_embeds": bool,
                    "embed_count": int,
                    "image_count": int
                }
        
        Raises:
            ValueError: If URL format is invalid
            requests.HTTPError: If Discord API request fails
        """
        logger.info(f"📨 Fetching Discord message from URL: {message_url}")
        
        # Parse URL
        guild_id, channel_id, message_id = self._parse_message_url(message_url)
        logger.debug(f"   Guild ID: {guild_id}, Channel ID: {channel_id}, Message ID: {message_id}")
        
        # Fetch message from Discord API
        message_data = self._fetch_message(channel_id, message_id)
        
        # Fetch channel info (includes guild/server info)
        channel_data = self._fetch_channel(channel_id)
        
        # Fetch guild info
        guild_data = self._fetch_guild(guild_id)
        
        # Format response
        formatted_data = self._format_message_data(
            message_data, 
            channel_data, 
            guild_data, 
            message_url
        )
        
        logger.info(f"✅ Message data fetched successfully")
        logger.info(f"   Author: {formatted_data['author']}")
        logger.info(f"   Attachments: {len(formatted_data['attached_files'])}")
        
        return formatted_data
    
    def _parse_message_url(self, url: str) -> Tuple[str, str, str]:
        """
        Parse Discord message URL to extract IDs.
        
        Args:
            url: Discord message URL
        
        Returns:
            tuple: (guild_id, channel_id, message_id)
        
        Raises:
            ValueError: If URL format is invalid
        """
        # Pattern: https://discord.com/channels/{guild_id}/{channel_id}/{message_id}
        pattern = r'https?://discord\.com/channels/(\d+)/(\d+)/(\d+)'
        match = re.match(pattern, url)
        
        if not match:
            raise ValueError(f"Invalid Discord message URL format: {url}")
        
        return match.groups()
    
    def _fetch_message(self, channel_id: str, message_id: str) -> Dict[str, Any]:
        """
        Fetch message data from Discord API.
        
        Args:
            channel_id: Discord channel ID
            message_id: Discord message ID
        
        Returns:
            dict: Raw message data from Discord API
        
        Raises:
            requests.HTTPError: If request fails
        """
        url = f"{self.API_BASE}/channels/{channel_id}/messages/{message_id}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            logger.error(f"❌ Failed to fetch message: {e}")
            logger.error(f"   Status code: {e.response.status_code}")
            if e.response.status_code == 401:
                logger.error("   Invalid Discord user token")
            elif e.response.status_code == 403:
                logger.error("   No permission to access this message")
            elif e.response.status_code == 404:
                logger.error("   Message not found")
            raise
    
    def _fetch_channel(self, channel_id: str) -> Dict[str, Any]:
        """
        Fetch channel data from Discord API.
        
        Args:
            channel_id: Discord channel ID
        
        Returns:
            dict: Channel data
        """
        url = f"{self.API_BASE}/channels/{channel_id}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            logger.warning(f"⚠️ Failed to fetch channel info: {e}")
            return {}
    
    def _fetch_guild(self, guild_id: str) -> Dict[str, Any]:
        """
        Fetch guild/server data from Discord API.
        
        Args:
            guild_id: Discord guild ID
        
        Returns:
            dict: Guild data
        """
        url = f"{self.API_BASE}/guilds/{guild_id}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            logger.warning(f"⚠️ Failed to fetch guild info: {e}")
            return {}
    
    def _format_message_data(
        self, 
        message: Dict[str, Any], 
        channel: Dict[str, Any], 
        guild: Dict[str, Any],
        message_url: str
    ) -> Dict[str, Any]:
        """
        Format Discord API response to match expected structure.
        
        Args:
            message: Raw message data from API
            channel: Channel data
            guild: Guild data
            message_url: Original message URL
        
        Returns:
            dict: Formatted message data
        """
        # Extract author info
        author = message.get('author', {})
        author_name = f"@{author.get('username', 'unknown')}"
        if discriminator := author.get('discriminator'):
            if discriminator != '0':  # New Discord usernames don't have discriminator
                author_name += f"#{discriminator}"
        
        # Extract attachments
        attachments = []
        for att in message.get('attachments', []):
            # Determine if it's an image
            content_type = att.get('content_type', '')
            is_image = content_type.startswith('image/')
            
            # Get extension
            filename = att.get('filename', '')
            extension = os.path.splitext(filename)[1] if filename else ''
            
            attachments.append({
                "name": filename,
                "url": att.get('url', ''),
                "size": att.get('size', 0),
                "width": att.get('width'),
                "height": att.get('height'),
                "is_image": is_image,
                "extension": extension
            })
        
        # Count images (from attachments and embeds)
        image_count = sum(1 for att in attachments if att['is_image'])
        
        # Format response
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "message_id": message.get('id', ''),
            "author": author_name,
            "date": message.get('timestamp', ''),
            "server": guild.get('name', 'Unknown Server'),
            "channel": channel.get('name', 'Unknown Channel'),
            "category": "Text channels",  # Could be enhanced to get actual category
            "content": message.get('content') or "[No text content]",
            "attached_url": None,  # For YouTube URLs, not applicable here
            "message_url": message_url,
            "attached_files": attachments,
            "preview_images": None,
            "original_message_id": message.get('referenced_message', {}).get('id') if message.get('referenced_message') else None,
            "has_embeds": len(message.get('embeds', [])) > 0,
            "embed_count": len(message.get('embeds', [])),
            "image_count": image_count
        }


def is_valid_discord_message_url(url: str) -> bool:
    """
    Check if a URL is a valid Discord message URL.
    
    Args:
        url: URL to validate
    
    Returns:
        bool: True if it's a valid Discord message URL
    """
    if not url:
        return False
    
    pattern = r'https?://discord\.com/channels/\d+/\d+/\d+'
    return bool(re.match(pattern, url))
