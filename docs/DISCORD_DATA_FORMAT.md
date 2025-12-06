# Discord Message Data Format

## Overview
This document describes the data format returned by `discord.py-self` in our `DiscordMessageFetcher` class.

## Message Data Structure

```python
message_data = {
    "timestamp": str,          # ISO 8601 timestamp (e.g., "2025-12-06T10:30:00+00:00")
    "message_id": str,         # Discord message ID
    "channel_id": str,         # Discord channel ID
    "channel_name": str,       # Channel name (or "DM" for direct messages)
    "guild_id": str | None,    # Server/guild ID (None for DMs)
    "guild_name": str | None,  # Server/guild name (None for DMs)
    "author": {
        "id": str,             # User ID
        "username": str,       # Username (without discriminator)
        "display_name": str    # Display name in server
    },
    "content": str,            # Message text content
    "attached_files": [
        {
            "filename": str,       # File name with extension
            "url": str,            # Direct CDN URL (public, no auth needed)
            "size": int,           # File size in bytes
            "content_type": str    # MIME type (e.g., "video/mp4")
        }
    ]
}
```

## Field Changes from Old Format

| Old Field | New Field | Notes |
|-----------|-----------|-------|
| `date` | `timestamp` | Now ISO 8601 format instead of custom string |
| `attached_files[].name` | `attached_files[].filename` | Consistent with discord.py naming |
| `attached_files[].extension` | *removed* | Use `os.path.splitext(filename)` instead |
| `attached_files[].is_image` | *removed* | Check MIME type or extension instead |
| `server` | `guild_name` | Discord's official terminology |
| `category` | *removed* | Not needed for current use case |

## Usage Examples

### Extract video title
```python
video_filename = message_data['attached_files'][0]['filename']
video_title = os.path.splitext(video_filename)[0]  # Remove extension
```

### Extract upload date
```python
upload_date = message_data['timestamp'][:10]  # YYYY-MM-DD
```

### Find video attachment
```python
for file in message_data['attached_files']:
    ext = os.path.splitext(file['filename'])[1].lower()
    if ext in {'.mp4', '.mov', '.avi', '.mkv', '.webm'}:
        video_url = file['url']
        break
```

## Migration Checklist

When updating code that uses Discord message data:

- ✅ Replace `['name']` with `['filename']` for attachments
- ✅ Replace `['date']` with `['timestamp']`
- ✅ Replace `['extension']` with `os.path.splitext(filename)[1]`
- ✅ Replace `['is_image']` with MIME type or extension check
- ✅ Replace `['server']` with `['guild_name']`
- ✅ Remove references to `['category']` field
