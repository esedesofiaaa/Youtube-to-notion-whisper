"""
Discord message fetcher using discord.py-self (user account).
Retrieves message data including attachments from Discord CDN.
"""
import os
import re
import asyncio
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
import discord
from config.logger import get_logger

logger = get_logger(__name__)


class DiscordMessageFetcher:
    """Fetch Discord message data using discord.py-self with user token."""
    
    def __init__(self, user_token: str = None):
        """
        Initialize Discord message fetcher.
        
        Args:
            user_token: Discord user account token (from .env if not provided)
        """
        self.token = user_token or os.getenv('DISCORD_USER_TOKEN')
        if not self.token:
            raise ValueError("DISCORD_USER_TOKEN not found in environment variables")
        
        # Create discord.py-self client
        self.client = discord.Client()
        self._ready = False
    
    async def _ensure_ready(self):
        """Ensure the Discord client is logged in and ready."""
        if not self._ready:
            @self.client.event
            async def on_ready():
                self._ready = True
                logger.info(f"✅ Discord client logged in as {self.client.user}")
            
            # Start client in background if not already running
            if not self.client.is_ready():
                asyncio.create_task(self.client.start(self.token))
                # Wait for ready event
                while not self._ready:
                    await asyncio.sleep(0.1)
    
    def fetch_message_data(self, message_url: str) -> Dict[str, Any]:
        """
        Fetch complete message data from Discord URL (synchronous wrapper).
        
        Args:
            message_url: Discord message URL
                Format: https://discord.com/channels/{guild_id}/{channel_id}/{message_id}
        
        Returns:
            dict: Message data
        
        Raises:
            ValueError: If URL format is invalid
            discord.HTTPException: If Discord API request fails
        """
        # Run async function in event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running, create a new task
            return asyncio.create_task(self._fetch_message_data_async(message_url))
        else:
            # If no loop is running, run until complete
            return loop.run_until_complete(self._fetch_message_data_async(message_url))
    
    async def _fetch_message_data_async(self, message_url: str) -> Dict[str, Any]:
        """
        Fetch complete message data from Discord URL (async implementation).
        
        Args:
            message_url: Discord message URL
        
        Returns:
            dict: Message data
        """
        logger.info(f"🔍 Fetching Discord message: {message_url}")
        
        # Parse URL
        guild_id, channel_id, message_id = self._parse_message_url(message_url)
        
        # Ensure client is ready
        await self._ensure_ready()
        
        # Fetch message
        try:
            channel = self.client.get_channel(int(channel_id))
            if not channel:
                channel = await self.client.fetch_channel(int(channel_id))
            
            message = await channel.fetch_message(int(message_id))
            
            # Extract message data
            message_data = {
                "timestamp": message.created_at.isoformat(),
                "message_id": str(message.id),
                "channel_id": str(message.channel.id),
                "channel_name": message.channel.name if hasattr(message.channel, 'name') else "DM",
                "guild_id": str(message.guild.id) if message.guild else None,
                "guild_name": message.guild.name if message.guild else None,
                "author": {
                    "id": str(message.author.id),
                    "username": message.author.name,
                    "display_name": message.author.display_name
                },
                "content": message.content,
                "attached_files": []
            }
            
            # Extract attachments
            for attachment in message.attachments:
                message_data["attached_files"].append({
                    "filename": attachment.filename,
                    "url": attachment.url,
                    "size": attachment.size,
                    "content_type": attachment.content_type or "unknown"
                })
            
            logger.info(f"✅ Message fetched: {len(message_data['attached_files'])} attachments")
            return message_data
            
        except discord.NotFound:
            logger.error(f"❌ Message not found: {message_url}")
            raise ValueError(f"Message not found: {message_url}")
        except discord.Forbidden:
            logger.error(f"❌ No permission to access message: {message_url}")
            raise ValueError(f"No permission to access message: {message_url}")
        except discord.HTTPException as e:
            logger.error(f"❌ Discord API error: {e}")
            raise
    
    async def close(self):
        """Close the Discord client connection."""
        if self.client and not self.client.is_closed():
            await self.client.close()
            logger.info("🔌 Discord client closed")
    
    def _parse_message_url(self, url: str) -> Tuple[str, str, str]:
        """
        Parse Discord message URL into components.
        
        Args:
            url: Discord message URL
        
        Returns:
            tuple: (guild_id, channel_id, message_id)
        
        Raises:
            ValueError: If URL format is invalid
        """
        pattern = r'https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)'
        match = re.match(pattern, url)
        
        if not match:
            raise ValueError(f"Invalid Discord message URL format: {url}")
        
        guild_id, channel_id, message_id = match.groups()
        return guild_id, channel_id, message_id


def is_valid_discord_message_url(url: str) -> bool:
    """
    Validate if a URL is a Discord message URL.
    
    Args:
        url: URL to validate
    
    Returns:
        bool: True if valid Discord message URL
    
    Examples:
        >>> is_valid_discord_message_url("https://discord.com/channels/123/456/789")
        True
        >>> is_valid_discord_message_url("https://www.youtube.com/watch?v=xxx")
        False
    """
    pattern = r'https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/\d+/\d+/\d+'
    return bool(re.match(pattern, url))
