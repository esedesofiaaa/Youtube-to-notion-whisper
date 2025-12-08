# Status Tracking for Audit Process Pipeline

## Overview

This document describes the **real-time status tracking** functionality implemented for the `audit-process` pipeline. This feature allows monitoring the progress of video processing by automatically updating the "Transcript Process Status" field in Notion as the video moves through different stages.

## Key Features

### ✨ What's New

- **Real-time status updates** during video processing
- **Error tracking** with detailed error messages
- **Non-intrusive**: Only affects `audit-process` channel
- **Automatic**: No manual intervention required
- **Informative**: Know exactly where a video is in the pipeline

### 🎯 Status Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    VIDEO PROCESSING FLOW                     │
└─────────────────────────────────────────────────────────────┘

    Start
      │
      ▼
┌──────────────┐
│ Processing   │ ← Task starts, components initialized
└──────────────┘
      │
      ▼
┌──────────────┐
│ Downloading  │ ← Video/audio download begins
└──────────────┘
      │
      ▼
┌──────────────┐
│ Transcribing │ ← Whisper transcription in progress
└──────────────┘
      │
      ▼
┌──────────────┐
│ Uploading    │ ← Files being uploaded to Google Drive
│ to Drive     │
└──────────────┘
      │
      ▼
┌──────────────┐
│  Complete    │ ← Processing finished successfully
└──────────────┘

    ❌ Error can occur at any stage ──┐
                                       │
                                       ▼
                                 ┌──────────┐
                                 │  Error   │
                                 └──────────┘
```

## Configuration

### Notion Database Requirements

The following fields must exist in your Discord Message Database for `audit-process`:

1. **Transcript Process Status** (Select)
   - Type: Select
   - Options (exact names required):
     - `Processing`
     - `Downloading`
     - `Transcribing`
     - `Uploading to Drive`
     - `Complete`
     - `Error`

2. **ProcessErrors** (Text)
   - Type: Rich Text
   - Purpose: Stores error messages when processing fails

### Field Mapping

In `config/notion_config.py`, the `audit-process` configuration includes:

```python
"field_map": {
    # ... other fields ...
    "status": "Transcript Process Status",    # select
    "process_errors": "ProcessErrors"         # text - error messages
}
```

## Implementation Details

### New Methods in NotionClient

#### `update_status_field(page_id, status_value, field_map)`

Updates only the status field for efficient progress tracking.

**Parameters:**
- `page_id` (str): Notion page ID to update
- `status_value` (str): Status value (e.g., "Processing", "Downloading")
- `field_map` (dict): Field mapping configuration

**Returns:**
- `bool`: True if successful

**Example:**
```python
notion_client.update_status_field(
    page_id="123abc...",
    status_value="Transcribing",
    field_map=field_map
)
```

#### `update_error_field(page_id, error_message, field_map)`

Updates error field and sets status to "Error" when processing fails.

**Parameters:**
- `page_id` (str): Notion page ID to update
- `error_message` (str): Error message to record
- `field_map` (dict): Field mapping configuration

**Returns:**
- `bool`: True if successful

**Example:**
```python
notion_client.update_error_field(
    page_id="123abc...",
    error_message="Transcription failed: timeout",
    field_map=field_map
)
```

### Status Update Points

#### In `process_youtube_video` task:

1. **Processing** - After initialization, before download
2. **Downloading** - Before streaming/download begins
3. **Transcribing** - When transcription starts (both streaming and fallback modes)
4. **Uploading to Drive** - Before uploading files to Drive
5. **Complete** - Set via `status_value` in page properties (end of processing)
6. **Error** - On exception, with error message in ProcessErrors field

#### In `process_discord_video` task:

Same status update points, adapted to Discord video workflow:

1. **Processing** - After initialization
2. **Downloading** - Before Discord video download
3. **Transcribing** - Before audio transcription
4. **Uploading to Drive** - Before Drive upload
5. **Complete** - On successful completion
6. **Error** - On exception with error details

### Conditional Execution

Status updates **only execute when**:
```python
if action_type == "update_origin":
    notion_client.update_status_field(...)
```

This ensures:
- ✅ Only `audit-process` channel gets status updates
- ✅ Other channels (market-outlook, market-analysis-streams, etc.) are unaffected
- ✅ No performance impact on other pipelines

## Usage

### Testing

Run the test script to validate the configuration:

```bash
python scripts/test_status_updates.py
```

The test will:
1. Verify NotionClient initialization
2. Check audit-process configuration
3. Validate required fields in field_map
4. Test property builders
5. List all status values

### Monitoring

Once deployed, you can monitor video processing progress by:

1. **Opening Notion** → Discord Message Database
2. **Filter by channel** → `audit-process`
3. **Check Status column** → See current processing stage
4. **If status = "Error"** → Check ProcessErrors field for details

### Example Workflow

```bash
# 1. Video URL posted to Discord audit-process channel
# 2. n8n webhook triggers process_youtube_video task
# 3. In Notion, you see the status update in real-time:

Status: Processing          ← Task initialized
  ↓ (5 seconds later)
Status: Downloading         ← Download started
  ↓ (2 minutes later)
Status: Transcribing        ← Whisper processing audio
  ↓ (3 minutes later)
Status: Uploading to Drive  ← Files uploading
  ↓ (1 minute later)
Status: Complete            ← ✅ Done!

# Or if error occurs:
Status: Error
ProcessErrors: "Transcription failed: timeout after 600s"
```

## Error Handling

### When Errors Occur

If any exception is raised during processing:

1. **Status** is set to `"Error"`
2. **ProcessErrors** field receives the error message
3. **Exception is re-raised** for Celery retry logic
4. **Temporary files are cleaned up**

### Error Message Format

```python
error_msg = f"Error in video processing: {str(e)}"
```

Example error messages:
- `"Error in video processing: YouTube video not available"`
- `"Error in video processing: Drive authentication failed"`
- `"Task 123abc exceeded time limit"`

## Benefits

### 🎯 Visibility
Know exactly what stage each video is in without checking logs

### 🐛 Debugging
Quickly identify where processing failed and why

### 📊 Monitoring
Track processing performance and identify bottlenecks

### ⚡ Proactive Response
Detect stuck videos and take action before users complain

### 📝 Audit Trail
Complete history of processing status in Notion

## Compatibility

| Feature | Compatible |
|---------|------------|
| Streaming Pipeline | ✅ Yes |
| Fallback Mode | ✅ Yes |
| YouTube Videos | ✅ Yes |
| Discord Videos | ✅ Yes |
| Other Channels | ✅ Yes (unaffected) |
| Existing Webhooks | ✅ Yes (no changes needed) |

## Troubleshooting

### Status not updating

**Check:**
1. Field "Transcript Process Status" exists in Notion
2. Field is of type "Select"
3. All status values exist as options
4. Channel is `audit-process`
5. Check logs for Notion API errors

### Error field not showing

**Check:**
1. Field "ProcessErrors" exists in Notion
2. Field is of type "Text" or "Rich Text"
3. Field is mapped in config: `"process_errors": "ProcessErrors"`

### Status stuck at one stage

**Possible causes:**
- Task is still processing (check Flower dashboard)
- Task crashed without updating status (check error logs)
- Celery worker is down (restart workers)

**Solution:**
```bash
# Check Celery workers
celery -A src.celery_app inspect active

# Check Flower dashboard
http://localhost:5555

# Restart workers if needed
./scripts/stop_all.sh
./scripts/start_all.sh
```

## Future Enhancements

Potential improvements for future versions:

- [ ] Add progress percentage (e.g., "Transcribing: 45%")
- [ ] Timestamp tracking for each stage
- [ ] Performance metrics (time spent in each stage)
- [ ] Retry count tracking
- [ ] Queue position indicator
- [ ] Estimated time remaining

## Related Documentation

- [CHANGELOG.md](./CHANGELOG.md) - Version history
- [TECHNICAL_DOCUMENTATION.md](../TECHNICAL_DOCUMENTATION.md) - System architecture
- [NOTION_INTEGRATION.md](./NOTION_INTEGRATION.md) - Notion API details

## Support

If you encounter issues:

1. Run the test script: `python scripts/test_status_updates.py`
2. Check Notion field configuration
3. Review logs in `logs/` directory
4. Check Celery worker status
5. Verify environment variables in `.env`

For questions or bug reports, please open an issue on GitHub.
