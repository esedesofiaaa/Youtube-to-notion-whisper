"""
Asynchronous Celery tasks for video processing.

This module uses a unified streaming pipeline for all video processing:
- Downloads video while simultaneously transcribing audio in real-time
- Falls back to traditional sequential processing if streaming fails
- Atomic upload to Drive and Notion creation after processing completes
"""
import os
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from src.celery_app import celery_app
from src.youtube_downloader import YouTubeDownloader
from src.transcriber import AudioTranscriber
from src.drive_manager import DriveManager
from src.notion_client import NotionClient
from src.models import MediaFile, StreamingTranscriptionResult
from config.logger import get_logger
from config.settings import (
    TEMP_DOWNLOAD_DIR,
    WHISPER_MODEL_DEFAULT,
    TRANSCRIPTION_FILE_FORMAT,
    CELERY_TASK_MAX_RETRIES,
    CELERY_TASK_RETRY_DELAY
)
from config.notion_config import (
    get_destination_database
)
from utils.helpers import (
    ensure_directory_exists,
    safe_remove_file,
    clean_temp_directory
)

logger = get_logger(__name__)


class CallbackTask(Task):
    """
    Base class for tasks with automatic callbacks.
    """

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Executed when a task fails."""
        logger.error(f"❌ Task {task_id} failed: {exc}")
        logger.error(f"   Args: {args}")
        logger.error(f"   Traceback: {einfo}")

    def on_success(self, retval, task_id, args, kwargs):
        """Executed when a task succeeds."""
        logger.info(f"✅ Task {task_id} completed successfully")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Executed when a task is retried."""
        logger.warning(f"🔄 Task {task_id} retrying due to: {exc}")


@celery_app.task(
    bind=True,
    base=CallbackTask,
    max_retries=CELERY_TASK_MAX_RETRIES,
    default_retry_delay=CELERY_TASK_RETRY_DELAY,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,  # Max 10 minutes backoff
    retry_jitter=True
)
def process_youtube_video(
    self,
    discord_entry_id: str,
    youtube_url: str,
    channel: str,
    parent_drive_folder_id: str = None
) -> dict:
    """
    Main task: Process a YouTube video/stream using unified streaming pipeline.

    This task uses a hybrid Single-Pass Processing architecture:
    1. Starts streaming download via yt-dlp -> FFmpeg pipeline
    2. FFmpeg simultaneously saves video to disk AND pipes audio for transcription
    3. Transcription happens in real-time as audio data arrives
    4. Once stream/video ends: atomic upload to Drive + create Notion page

    If the streaming pipeline fails (broken pipe, network issues, etc.),
    automatically falls back to traditional sequential processing.

    Works for both:
    - Live streams (infinite until ended)
    - VOD/regular videos (finite, more efficient than traditional)

    Args:
        discord_entry_id: ID of the entry in Discord Message Database
        youtube_url: YouTube video/stream URL
        channel: Discord channel (to determine destination DB)
        parent_drive_folder_id: ID of parent folder in Drive (optional)

    Returns:
        dict: Information about the completed task including:
            - status: 'success'
            - processing_mode: 'streaming' or 'fallback'
            - notion_page_url: URL of created Notion page
            - drive_folder_url: URL of Drive folder
            - transcription_length: Character count of transcription
            - chunks_processed: Number of audio chunks (streaming mode only)

    Raises:
        Exception: If processing fails after all retries
    """
    task_id = self.request.id
    logger.info("=" * 80)
    logger.info(f"🚀 Starting video processing [Task ID: {task_id}]")
    logger.info(f"   YouTube URL: {youtube_url}")
    logger.info(f"   Channel: {channel}")
    logger.info(f"   Discord Entry ID: {discord_entry_id}")
    logger.info(f"   Mode: Unified Streaming Pipeline")
    logger.info("=" * 80)

    # Track processing mode for result
    streaming_failed = False
    stream_error = None
    chunks_count = 0

    try:
        # ============================================================
        # 1. VALIDATE AND GET CONFIGURATION
        # ============================================================
        destination_db = get_destination_database(channel)
        if not destination_db:
            raise ValueError(f"No destination database found for channel: {channel}")

        action_type = destination_db.get("action_type", "create_new_page")
        database_id = destination_db.get("database_id")  # May be None for update_origin
        database_name = destination_db["database_name"]
        drive_folder_id_from_config = destination_db.get("drive_folder_id")
        
        # Validate database_id is present for create_new_page
        if action_type == "create_new_page" and not database_id:
            raise ValueError(f"database_id required for create_new_page action, channel: {channel}")
        
        logger.info(f"📊 Destination database: {database_name}")
        logger.info(f"📁 Drive folder ID: {drive_folder_id_from_config}")

        # ============================================================
        # 2. INITIALIZE COMPONENTS
        # ============================================================
        ensure_directory_exists(TEMP_DOWNLOAD_DIR)
        downloader = YouTubeDownloader(TEMP_DOWNLOAD_DIR)
        transcriber = AudioTranscriber(WHISPER_MODEL_DEFAULT)
        drive_manager = DriveManager()
        notion_client = NotionClient()

        if not drive_manager.service:
            raise Exception("Could not authenticate with Google Drive API")

        # ============================================================
        # 3. GET VIDEO INFORMATION
        # ============================================================
        logger.info("📹 Getting video information...")
        video_info = downloader.get_video_info(youtube_url)
        if not video_info:
            raise Exception(f"Could not get video information: {youtube_url}")

        # ============================================================
        # 4. RESOLVE DRIVE FOLDER
        # ============================================================
        if not parent_drive_folder_id:
            parent_drive_folder_id = drive_folder_id_from_config
            logger.info(f"📂 Using Drive folder from channel config: {parent_drive_folder_id}")
        
        if not parent_drive_folder_id:
            raise ValueError(f"No Drive folder ID configured for channel: {channel}")

        # ============================================================
        # 5. CREATE FOLDER IN DRIVE
        # ============================================================
        folder_name = f"{video_info.upload_date} - {video_info.safe_title}"
        logger.info(f"📁 Creating folder in Drive: {folder_name}")
        drive_folder_id = drive_manager.create_folder(folder_name, parent_drive_folder_id)
        if not drive_folder_id:
            raise Exception("Could not create folder in Google Drive")

        drive_folder_url = f"https://drive.google.com/drive/folders/{drive_folder_id}"

        # ============================================================
        # 6. STREAMING PIPELINE: DOWNLOAD + TRANSCRIBE SIMULTANEOUSLY
        # ============================================================
        logger.info("🔴 Starting streaming pipeline (yt-dlp → FFmpeg → Whisper)...")
        
        video_path = None
        transcription_text = ""
        all_segments = []
        ffmpeg_process = None

        try:
            # Start the stream (saves video to disk + pipes audio for transcription)
            ffmpeg_process, audio_pipe, video_path = downloader.stream_and_capture(
                video_info, save_video=True
            )

            if not ffmpeg_process or not audio_pipe:
                raise Exception("Failed to start streaming pipeline")

            # Transcribe from the audio pipe in real-time
            logger.info("🎤 Starting real-time transcription...")
            
            # Consume the streaming transcription generator
            for chunk_text, chunk_segments in transcriber.transcribe_stream(
                audio_pipe, language="en"
            ):
                transcription_text += chunk_text
                all_segments.extend(chunk_segments)
                chunks_count += 1
                logger.info(f"   📝 Chunk {chunks_count}: {len(chunk_text)} chars transcribed")

            # Wait for FFmpeg to finish (stream/video ended)
            ffmpeg_process.wait()

            # Check for FFmpeg errors
            ffmpeg_errors = downloader.get_stream_errors(ffmpeg_process)
            if ffmpeg_errors:
                logger.warning(f"⚠️ FFmpeg warnings: {ffmpeg_errors}")

            logger.info(f"✅ Streaming complete: {chunks_count} chunks, {len(transcription_text)} chars")

        except (BrokenPipeError, IOError) as e:
            streaming_failed = True
            stream_error = str(e)
            logger.error(f"❌ Stream pipeline error (BrokenPipe/IO): {e}")
            
            # Try to stop any running processes
            if ffmpeg_process:
                downloader.stop_stream(ffmpeg_process)

        except Exception as e:
            streaming_failed = True
            stream_error = str(e)
            logger.error(f"❌ Streaming error: {e}", exc_info=True)
            
            if ffmpeg_process:
                downloader.stop_stream(ffmpeg_process)

        # ============================================================
        # 6b. FALLBACK: TRADITIONAL PROCESSING IF STREAMING FAILED
        # ============================================================
        if streaming_failed:
            logger.warning("=" * 60)
            logger.warning("⚠️ STREAMING FAILED - Falling back to traditional processing")
            logger.warning(f"   Error: {stream_error}")
            logger.warning("=" * 60)
            
            # Reset variables
            video_path = None
            transcription_text = ""
            all_segments = []
            chunks_count = 0

            # Traditional download: video
            logger.info("⬇️ Downloading video (fallback mode)...")
            video_file = downloader.download_video(video_info)
            if video_file and video_file.exists():
                video_path = video_file.path
                logger.info(f"✅ Video downloaded: {video_file.filename}")

            # Traditional download: audio
            logger.info("🎵 Downloading audio (fallback mode)...")
            audio_file = downloader.download_audio(video_info)
            
            if audio_file and audio_file.exists():
                # Traditional transcription
                logger.info("🎤 Transcribing audio (fallback mode)...")
                transcription_result = transcriber.transcribe(audio_file, language="en")
                if transcription_result:
                    transcription_text = transcription_result.text
                    all_segments = transcription_result.segments or []
                    logger.info(f"✅ Transcription complete: {len(transcription_text)} chars")
                safe_remove_file(audio_file.path)
            else:
                logger.warning("⚠️ Could not download audio for transcription")

        # ============================================================
        # 7. ATOMIC UPLOAD TO DRIVE (after processing completes)
        # ============================================================
        logger.info("📤 Starting atomic upload to Drive...")
        
        drive_video_url = None
        drive_audio_url = None
        drive_transcript_txt_url = None
        drive_transcript_srt_url = None

        # Upload video if exists
        if video_path and os.path.exists(video_path):
            logger.info(f"📤 Uploading video: {os.path.basename(video_path)}")
            video_file = MediaFile(
                path=video_path,
                filename=os.path.basename(video_path),
                file_type='video'
            )
            try:
                uploaded, drive_file = drive_manager.upload_if_not_exists(video_file, drive_folder_id)
                if drive_file:
                    drive_video_url = f"https://drive.google.com/file/d/{drive_file.id}/view"
                    logger.info(f"✅ Video uploaded: {drive_video_url}")
            except Exception as e:
                logger.error(f"❌ Error uploading video: {e}")
            finally:
                safe_remove_file(video_path)

        # Save and upload transcription files
        if transcription_text:
            txt_filename = TRANSCRIPTION_FILE_FORMAT.format(
                date=video_info.upload_date,
                title=video_info.safe_title
            )
            local_txt_path = os.path.join(TEMP_DOWNLOAD_DIR, txt_filename)
            local_srt_path = local_txt_path.replace('.txt', '.srt')

            # Save TXT file
            with open(local_txt_path, 'w', encoding='utf-8') as f:
                f.write(transcription_text.strip())
            logger.info(f"✅ Transcription saved: {txt_filename}")

            # Save SRT file if we have segments with timestamps
            if all_segments:
                try:
                    temp_result = StreamingTranscriptionResult(
                        text=transcription_text,
                        language="en",
                        language_probability=1.0,
                        segments=all_segments,
                        chunks_processed=chunks_count,
                        stream_completed=True
                    )
                    temp_result.save_srt(local_srt_path)
                    logger.info(f"✅ SRT file generated: {os.path.basename(local_srt_path)}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not generate SRT file: {e}")

            # Upload TXT to Drive
            if os.path.exists(local_txt_path):
                txt_file = MediaFile(
                    path=local_txt_path,
                    filename=os.path.basename(local_txt_path),
                    file_type='transcription'
                )
                try:
                    uploaded, drive_file = drive_manager.upload_if_not_exists(txt_file, drive_folder_id)
                    if drive_file:
                        drive_transcript_txt_url = f"https://drive.google.com/file/d/{drive_file.id}/view"
                        logger.info(f"✅ Transcript TXT uploaded: {drive_transcript_txt_url}")
                except Exception as e:
                    logger.error(f"❌ Error uploading TXT: {e}")
                finally:
                    safe_remove_file(local_txt_path)

            # Upload SRT to Drive
            if os.path.exists(local_srt_path):
                srt_file = MediaFile(
                    path=local_srt_path,
                    filename=os.path.basename(local_srt_path),
                    file_type='transcription'
                )
                try:
                    uploaded, drive_file = drive_manager.upload_if_not_exists(srt_file, drive_folder_id)
                    if drive_file:
                        drive_transcript_srt_url = f"https://drive.google.com/file/d/{drive_file.id}/view"
                        logger.info(f"✅ Transcript SRT uploaded: {drive_transcript_srt_url}")
                except Exception as e:
                    logger.error(f"❌ Error uploading SRT: {e}")
                finally:
                    safe_remove_file(local_srt_path)

        # ============================================================
        # 8. CREATE/UPDATE NOTION PAGE (atomic, after everything is ready)
        # ============================================================
        field_map = destination_db.get("field_map", {})
        status_value = destination_db.get("status_value")
        name_format = destination_db.get("name_format", "default")
        logger.info(f"📝 Notion action: {action_type} ({database_name})...")

        notion_page_url = None
        notion_page_id = None

        # Build page name based on format
        if name_format == "youtube":
            page_name = f"YouTube Video: {video_info.title}"
        else:
            page_name = f"{video_info.upload_date} - {video_info.title}"

        # Build data dictionary with all available values (logical keys)
        # Map availability to listing status (Public/Unlisted)
        listing_status = "Public" if video_info.availability == "public" else "Unlisted"
        
        page_data = {
            "name": page_name,
            "date": video_info.upload_date,
            "video_date_time": video_info.upload_date,
            "video_link": youtube_url,
            "video_url": youtube_url,  # alias for video_link
            "live_video_url": youtube_url,
            "video_id": video_info.video_id,
            "youtube_channel": video_info.channel,
            "youtube_listing_status": listing_status,
            "drive_folder": drive_folder_url,
            "drive_folder_link": drive_folder_url,
            "video_file": drive_video_url,
            "audio_file": drive_audio_url,
            "transcript_file": drive_transcript_txt_url,
            "transcript_srt_file": drive_transcript_srt_url,
            "transcript_text": transcription_text[:2000] if transcription_text else None,
            "discord_channel": channel,
            "status": status_value,
            "length_min": video_info.duration / 60 if video_info.duration else None,
            "process_errors": None
        }

        if action_type == "create_new_page":
            # ---- Create new page in destination database ----
            notion_page = notion_client.create_video_page(
                database_id=database_id,
                field_map=field_map,
                data=page_data
            )

            if not notion_page:
                raise Exception("Could not create page in Notion")

            notion_page_url = notion_page.get("url")
            notion_page_id = notion_page.get("id")
            logger.info(f"✅ Notion page created: {notion_page_url}")

            # Add transcript as dropdown block in new Notion page
            if transcription_text:
                logger.info("📝 Adding transcript dropdown to Notion page...")
                notion_client.add_transcript_dropdown(notion_page_id, transcription_text)

            # Update Discord Message Database with link to new page
            logger.info("🔄 Updating Transcript field in Discord Message DB...")
            update_success = notion_client.update_transcript_field(
                discord_entry_id,
                notion_page_url
            )
            if not update_success:
                logger.warning("⚠️ Could not update Transcript field in Discord Message DB")

        elif action_type == "update_origin":
            # ---- Update the origin Discord Message DB entry ----
            # Build properties dynamically based on field_map
            update_props = {}

            for logical_key, column_name in field_map.items():
                value = page_data.get(logical_key)
                if value is None:
                    continue

                # Map by property type based on logical key
                if logical_key in ("drive_folder", "drive_folder_link", "video_file", 
                                   "audio_file", "video_link", "video_url", "live_video_url"):
                    update_props[column_name] = notion_client.build_url_property(value)
                elif logical_key in ("transcript_file", "transcript_srt_file"):
                    filename = "Transcript.srt" if "srt" in logical_key else "Transcript.txt"
                    update_props[column_name] = notion_client.build_files_property(value, filename)
                elif logical_key in ("status", "discord_channel", "youtube_channel", "youtube_listing_status"):
                    update_props[column_name] = notion_client.build_select_property(value)
                elif logical_key in ("date", "video_date_time"):
                    update_props[column_name] = notion_client.build_date_property(value)
                elif logical_key == "length_min":
                    update_props[column_name] = notion_client.build_number_property(value)
                elif logical_key in ("video_id", "transcript_text", "process_errors", "name"):
                    update_props[column_name] = notion_client.build_text_property(str(value))

                logger.info(f"   📌 {column_name}: {str(value)[:50]}...")

            # Update the origin page
            if update_props:
                update_success = notion_client.update_page_properties(
                    discord_entry_id,
                    update_props
                )
                if not update_success:
                    raise Exception("Could not update origin page in Notion")
                logger.info(f"✅ Origin page updated: {discord_entry_id}")
            else:
                logger.warning("⚠️ No properties to update (field_map may be empty)")

            # Add transcript dropdown to origin page
            if transcription_text:
                logger.info("📝 Adding transcript dropdown to origin page...")
                notion_client.add_transcript_dropdown(discord_entry_id, transcription_text)

            # For update_origin, the "result" page URL is the original Discord entry
            notion_page_url = f"https://www.notion.so/{discord_entry_id.replace('-', '')}"
            notion_page_id = discord_entry_id

        else:
            raise ValueError(f"Unknown action_type: {action_type}")

        # ============================================================
        # 10. CLEANUP
        # ============================================================
        clean_temp_directory(TEMP_DOWNLOAD_DIR)

        # ============================================================
        # RESULT
        # ============================================================
        processing_mode = "fallback" if streaming_failed else "streaming"
        
        result = {
            "status": "success",
            "task_id": task_id,
            "youtube_url": youtube_url,
            "video_title": video_info.title,
            "notion_page_url": notion_page_url,
            "drive_folder_url": drive_folder_url,
            "drive_video_url": drive_video_url,
            "transcription_length": len(transcription_text),
            "database_name": database_name,
            "processing_mode": processing_mode,
            "chunks_processed": chunks_count
        }

        logger.info("=" * 80)
        logger.info("✅ Video processing completed successfully")
        logger.info(f"   Mode: {processing_mode.upper()}")
        logger.info(f"   Notion Page: {notion_page_url}")
        logger.info(f"   Drive Folder: {drive_folder_url}")
        if processing_mode == "streaming":
            logger.info(f"   Chunks Processed: {chunks_count}")
        logger.info(f"   Transcription: {len(transcription_text)} characters")
        logger.info("=" * 80)

        return result

    except SoftTimeLimitExceeded:
        logger.error(f"⏱️ Task {task_id} exceeded time limit")
        clean_temp_directory(TEMP_DOWNLOAD_DIR)
        raise

    except Exception as e:
        logger.error(f"❌ Error in video processing: {e}", exc_info=True)
        clean_temp_directory(TEMP_DOWNLOAD_DIR)
        raise


@celery_app.task(bind=True, base=CallbackTask)
def test_task(self, message: str = "Hello from Celery!"):
    """
    Test task to verify that Celery works correctly.

    Args:
        message: Message to log

    Returns:
        dict: Task information
    """
    task_id = self.request.id
    logger.info(f"🧪 Test task running [Task ID: {task_id}]")
    logger.info(f"   Message: {message}")

    return {
        "status": "success",
        "task_id": task_id,
        "message": message
    }
