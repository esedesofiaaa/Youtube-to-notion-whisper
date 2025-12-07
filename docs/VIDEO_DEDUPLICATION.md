# Video Deduplication System

## Overview
The system now includes automatic video deduplication to prevent reprocessing videos that already exist in Notion with transcripts.

## Implementation Details

### Affected Pipelines
- ✅ **YouTube Video Processing** (`process_youtube_video`)
  - Checks for duplicates before processing
  - Searches across all Notion databases
  - Skips processing if video exists with transcript

- ❌ **Discord Video Processing** (`process_discord_video`)
  - Does NOT check for duplicates
  - Always processes videos from Discord messages
  - Designed for unique Discord attachments

### How It Works

1. **Early Check (Section 3 of YouTube Pipeline)**
   ```python
   existing_video = notion_client.find_video_by_url(youtube_url)
   ```

2. **Search Scope**
   - Videos Database (`VIDEOS_DB_ID`)
   - Discord Message Database (`DISCORD_MESSAGE_DB_ID`)
   - Uses URL field to match videos

3. **Decision Logic**
   - **Video exists WITH transcript** → Skip processing, return existing page info
   - **Video exists WITHOUT transcript** → Continue processing, update existing page
   - **Video not found** → Continue processing, create new page

### Return Format (When Skipped)

When a duplicate video is detected with transcript:
```json
{
  "status": "skipped",
  "reason": "already_processed",
  "existing_page_id": "notion-page-id",
  "existing_page_url": "https://notion.so/...",
  "database_name": "Videos Database",
  "message": "Video already processed in Videos Database"
}
```

### Transcript Detection

A video is considered "fully processed" if it has BOTH:
1. `Transcript File` property (TXT file in Drive)
2. `Transcript SRT File` property (SRT file in Drive)

If either is missing, processing continues to fill in the gaps.

### Logs Example

**When duplicate found:**
```
🔍 Checking if video already exists in Notion...
✅ Video already processed with transcript!
   Found in: Videos Database
   Page: https://www.notion.so/...
   Skipping processing
```

**When video exists but incomplete:**
```
🔍 Checking if video already exists in Notion...
⚠️ Video exists in Videos Database but has no transcript
   Will process and update existing page
```

**When video is new:**
```
🔍 Checking if video already exists in Notion...
✅ Video not found in any database, proceeding with processing
```

## Benefits

1. **Resource Savings**
   - Avoids re-downloading videos
   - Skips redundant transcription (expensive)
   - Reduces Drive API calls

2. **Time Efficiency**
   - Instant response for duplicates
   - No waiting for processing

3. **Consistency**
   - Single source of truth across databases
   - Prevents conflicting transcripts

## Implementation Files

- `src/notion_client.py`: 
  - `find_video_by_url()` - Main deduplication logic
  - `_extract_files()` - Helper to check transcript files

- `src/tasks.py`:
  - Section 3 of `process_youtube_video()` - Deduplication check

## Testing

To test deduplication:

1. Process a YouTube video normally (first time)
2. Try processing the same URL again
3. Should see "Video already processed" message
4. Check return value has `status: "skipped"`

## Configuration

No configuration needed! The system automatically:
- Uses database IDs from `config/notion_config.py`
- Searches "URL" field (standard across databases)
- Checks "Transcript File" and "Transcript SRT File" properties

## Future Enhancements

Potential improvements:
- Add deduplication to other pipelines if needed
- Cache recent lookups to reduce API calls
- Add manual "force reprocess" flag
- Deduplication dashboard/stats
