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
    get_destination_database,
    DESTINATION_DB_FIELDS
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

        database_id = destination_db["database_id"]
        database_name = destination_db["database_name"]
        drive_folder_id_from_config = destination_db.get("drive_folder_id")
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
        # 8. CREATE NOTION PAGE (atomic, after everything is ready)
        # ============================================================
        logger.info(f"📝 Creating page in Notion ({database_name})...")
        page_title = f"{video_info.upload_date} - {video_info.title}"

        notion_page = notion_client.create_video_page(
            database_id=database_id,
            title=page_title,
            video_date=video_info.upload_date,
            video_url=youtube_url,
            drive_folder_url=drive_folder_url,
            drive_video_url=drive_video_url or "",
            discord_channel=channel,
            audio_file_url=drive_audio_url,
            transcript_file_url=drive_transcript_txt_url,
            transcript_srt_file_url=drive_transcript_srt_url
        )

        if not notion_page:
            raise Exception("Could not create page in Notion")

        notion_page_url = notion_page.get("url")
        notion_page_id = notion_page.get("id")
        logger.info(f"✅ Notion page created: {notion_page_url}")

        # Add transcript as dropdown block in Notion page
        if transcription_text:
            logger.info("📝 Adding transcript dropdown to Notion page...")
            notion_client.add_transcript_dropdown(notion_page_id, transcription_text)

        # ============================================================
        # 9. UPDATE DISCORD MESSAGE DATABASE
        # ============================================================
        logger.info("🔄 Updating Transcript field in Discord Message DB...")
        update_success = notion_client.update_transcript_field(
            discord_entry_id,
            notion_page_url
        )

        if not update_success:
            logger.warning("⚠️ Could not update Transcript field in Discord Message DB")

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
