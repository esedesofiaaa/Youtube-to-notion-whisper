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
    CELERY_TASK_RETRY_DELAY,
    COMPRESSION_ENABLED
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
    
    # Variables for error handling (will be set in try block)
    action_type = None
    field_map = {}
    notion_client = None

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
        field_map = destination_db.get("field_map", {})
        
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

        # ============================================================
        # 2.1. UPDATE STATUS: Processing (audit-process only)
        # ============================================================
        if action_type == "update_origin":
            logger.info("📊 Updating status to 'Processing'...")
            notion_client.update_status_field(discord_entry_id, "Processing", field_map)

        if not drive_manager.service:
            raise Exception("Could not authenticate with Google Drive API")

        # ============================================================
        # 3. CHECK FOR EXISTING VIDEO (DEDUPLICATION)
        # ============================================================
        logger.info("🔍 Checking if video already exists in Notion...")
        existing_video = notion_client.find_video_by_url(youtube_url)
        
        if existing_video and existing_video.get("has_transcript"):
            logger.info("✅ Video already processed with transcript!")
            logger.info(f"   Found in: {existing_video['database_name']}")
            logger.info(f"   Page: {existing_video['page_url']}")
            logger.info(f"   Skipping processing")
            
            return {
                "status": "skipped",
                "reason": "already_processed",
                "existing_page_id": existing_video["page_id"],
                "existing_page_url": existing_video["page_url"],
                "database_name": existing_video["database_name"],
                "message": f"Video already processed in {existing_video['database_name']}"
            }
        elif existing_video:
            logger.info(f"⚠️ Video exists in {existing_video['database_name']} but has no transcript")
            logger.info(f"   Will process and update existing page")
        else:
            logger.info("✅ Video not found in any database, proceeding with processing")

        # ============================================================
        # 4. GET VIDEO INFORMATION
        # ============================================================
        logger.info("📹 Getting video information...")
        video_info = downloader.get_video_info(youtube_url)
        if not video_info:
            raise Exception(f"Could not get video information: {youtube_url}")

        # ============================================================
        # 5. RESOLVE DRIVE FOLDER
        # ============================================================
        if not parent_drive_folder_id:
            parent_drive_folder_id = drive_folder_id_from_config
            logger.info(f"📂 Using Drive folder from channel config: {parent_drive_folder_id}")
        
        if not parent_drive_folder_id:
            raise ValueError(f"No Drive folder ID configured for channel: {channel}")

        # ============================================================
        # 6. CREATE FOLDER IN DRIVE
        # ============================================================
        folder_name = f"{video_info.upload_date} - {video_info.safe_title}"
        logger.info(f"📁 Creating folder in Drive: {folder_name}")
        drive_folder_id = drive_manager.create_folder(folder_name, parent_drive_folder_id)
        if not drive_folder_id:
            raise Exception("Could not create folder in Google Drive")

        drive_folder_url = f"https://drive.google.com/drive/folders/{drive_folder_id}"

        # ============================================================
        # 7. STREAMING PIPELINE: DOWNLOAD + TRANSCRIBE SIMULTANEOUSLY
        # ============================================================
        # Update status to "Downloading" (audit-process only)
        if action_type == "update_origin":
            logger.info("📊 Updating status to 'Downloading'...")
            notion_client.update_status_field(discord_entry_id, "Downloading", field_map)
        
        logger.info("🔴 Starting streaming pipeline (yt-dlp → FFmpeg → Whisper)...")
        
        video_path = None
        audio_path = None
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

            # Update status to "Transcribing" (audit-process only)
            if action_type == "update_origin":
                logger.info("📊 Updating status to 'Transcribing'...")
                notion_client.update_status_field(discord_entry_id, "Transcribing", field_map)

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
        # 7b. FALLBACK: TRADITIONAL PROCESSING IF STREAMING FAILED
        # ============================================================
        if streaming_failed:
            logger.warning("=" * 60)
            logger.warning("⚠️ STREAMING FAILED - Falling back to traditional processing")
            logger.warning(f"   Error: {stream_error}")
            logger.warning("=" * 60)
            
            # Reset variables
            video_path = None
            audio_path = None
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
            audio_path = None
            
            if audio_file and audio_file.exists():
                audio_path = audio_file.path
                # Update status to "Transcribing" (audit-process only)
                if action_type == "update_origin":
                    logger.info("📊 Updating status to 'Transcribing'...")
                    notion_client.update_status_field(discord_entry_id, "Transcribing", field_map)
                
                # Traditional transcription
                logger.info("🎤 Transcribing audio (fallback mode)...")
                transcription_result = transcriber.transcribe(audio_file, language="en")
                if transcription_result:
                    transcription_text = transcription_result.text
                    all_segments = transcription_result.segments or []
                    logger.info(f"✅ Transcription complete: {len(transcription_text)} chars")
            else:
                logger.warning("⚠️ Could not download audio for transcription")

        # ============================================================
        # 8. ATOMIC UPLOAD TO DRIVE (after processing completes)
        # ============================================================
        # Update status to "Uploading to Drive" (audit-process only)
        if action_type == "update_origin":
            logger.info("📊 Updating status to 'Uploading to Drive'...")
            notion_client.update_status_field(discord_entry_id, "Uploading to Drive", field_map)
        
        logger.info("📤 Starting atomic upload to Drive...")
        
        drive_video_url = None
        drive_audio_url = None
        drive_transcript_txt_url = None
        drive_transcript_srt_url = None

        # Process video file (convert MKV to MP4 if needed, extract audio)
        final_video_path = video_path
        extracted_audio_path = None
        
        if video_path and os.path.exists(video_path):
            # If video is MKV (from streaming), convert to MP4
            if video_path.endswith('.mkv'):
                logger.info("🔄 Converting MKV to MP4 for better compatibility...")
                mp4_path = downloader.convert_mkv_to_mp4(video_path)
                if mp4_path and os.path.exists(mp4_path):
                    final_video_path = mp4_path
                    safe_remove_file(video_path)  # Remove MKV after successful conversion
                    logger.info(f"✅ Using MP4: {os.path.basename(mp4_path)}")
                else:
                    logger.warning("⚠️ MP4 conversion failed, using MKV")
                    final_video_path = video_path
            
            # ============================================================
            # 7.5. COMPRESS VIDEO (if enabled)
            # ============================================================
            if COMPRESSION_ENABLED:
                logger.info("🗜️ Compressing video before upload...")
                compressed_path = downloader.compress_video(final_video_path)
                
                if compressed_path and os.path.exists(compressed_path):
                    # Compression successful - remove original and use compressed
                    logger.info("✅ Compression successful, using compressed video")
                    safe_remove_file(final_video_path)
                    final_video_path = compressed_path
                else:
                    # Compression failed - continue with original
                    logger.warning("⚠️ Compression failed, using original video")
            else:
                logger.info("ℹ️ Video compression disabled (COMPRESSION_ENABLED=False)")
            
            # Extract audio from video if we don't have audio yet (streaming mode)
            if not audio_path or not os.path.exists(audio_path):
                logger.info("🎵 Extracting audio from video for Drive upload...")
                audio_file_extracted = downloader.extract_audio_from_video(final_video_path)
                if audio_file_extracted and audio_file_extracted.exists():
                    extracted_audio_path = audio_file_extracted.path
                    logger.info(f"✅ Audio extracted: {audio_file_extracted.filename}")
                else:
                    logger.warning("⚠️ Audio extraction failed")

        # Upload video if exists
        if final_video_path and os.path.exists(final_video_path):
            logger.info(f"📤 Uploading video: {os.path.basename(final_video_path)}")
            video_file = MediaFile(
                path=final_video_path,
                filename=os.path.basename(final_video_path),
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
                safe_remove_file(final_video_path)

        # Upload audio - either from fallback mode or extracted from video
        audio_to_upload = audio_path if (audio_path and os.path.exists(audio_path)) else extracted_audio_path
        
        if audio_to_upload and os.path.exists(audio_to_upload):
            logger.info(f"📤 Uploading audio: {os.path.basename(audio_to_upload)}")
            audio_file_obj = MediaFile(
                path=audio_to_upload,
                filename=os.path.basename(audio_to_upload),
                file_type='audio'
            )
            try:
                uploaded, drive_file = drive_manager.upload_if_not_exists(audio_file_obj, drive_folder_id)
                if drive_file:
                    drive_audio_url = f"https://drive.google.com/file/d/{drive_file.id}/view"
                    logger.info(f"✅ Audio uploaded: {drive_audio_url}")
            except Exception as e:
                logger.error(f"❌ Error uploading audio: {e}")
            finally:
                safe_remove_file(audio_to_upload)

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
        # 9. CREATE/UPDATE NOTION PAGE (atomic, after everything is ready)
        # ============================================================
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
                elif logical_key == "name":
                    update_props[column_name] = notion_client.build_title_property(str(value))
                elif logical_key in ("video_id", "transcript_text", "process_errors"):
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
        error_msg = f"Task {task_id} exceeded time limit"
        logger.error(f"⏱️ {error_msg}")
        
        # Update error status in Notion (audit-process only)
        if action_type == "update_origin" and notion_client and field_map:
            notion_client.update_error_field(discord_entry_id, error_msg, field_map)
        
        clean_temp_directory(TEMP_DOWNLOAD_DIR)
        raise

    except Exception as e:
        error_msg = f"Error in video processing: {str(e)}"
        logger.error(f"❌ {error_msg}", exc_info=True)
        
        # Update error status in Notion (audit-process only)
        if action_type == "update_origin" and notion_client and field_map:
            notion_client.update_error_field(discord_entry_id, error_msg, field_map)
        
        clean_temp_directory(TEMP_DOWNLOAD_DIR)
        raise


@celery_app.task(
    bind=True,
    base=CallbackTask,
    max_retries=CELERY_TASK_MAX_RETRIES,
    default_retry_delay=CELERY_TASK_RETRY_DELAY,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True
)
def process_discord_video(
    self,
    notion_page_id: str,
    discord_message_url: str,
    channel: str,
    parent_drive_folder_id: str = None
) -> dict:
    """
    Process a Discord video from message URL.
    
    Workflow:
    1. Fetch message data from Discord API
    2. Download video from Discord CDN
    3. Transcribe using same pipeline as YouTube
    4. Upload to Drive
    5. Create/update Notion page
    
    Args:
        notion_page_id: ID of the entry in Discord Message Database
        discord_message_url: Discord message URL
        channel: Discord channel (to determine destination DB)
        parent_drive_folder_id: ID of parent folder in Drive (optional)
    
    Returns:
        dict: Information about the completed task
    
    Raises:
        Exception: If processing fails after all retries
    """
    from src.discord_downloader import DiscordDownloader
    
    task_id = self.request.id
    logger.info("=" * 80)
    logger.info(f"🚀 Starting Discord video processing [Task ID: {task_id}]")
    logger.info(f"   Discord Message URL: {discord_message_url}")
    logger.info(f"   Channel: {channel}")
    logger.info(f"   Notion Page ID: {notion_page_id}")
    logger.info("=" * 80)
    
    # Variables for error handling (will be set in try block)
    action_type = None
    field_map = {}
    notion_client = None
    
    try:
        # ============================================================
        # 1. VALIDATE AND GET CONFIGURATION
        # ============================================================
        destination_db = get_destination_database(channel)
        if not destination_db:
            raise ValueError(f"No destination database found for channel: {channel}")

        action_type = destination_db.get("action_type", "create_new_page")
        database_id = destination_db.get("database_id")
        database_name = destination_db["database_name"]
        drive_folder_id_from_config = destination_db.get("drive_folder_id")
        field_map = destination_db.get("field_map", {})
        
        if action_type == "create_new_page" and not database_id:
            raise ValueError(f"database_id required for create_new_page action, channel: {channel}")
        
        logger.info(f"📊 Destination database: {database_name}")
        logger.info(f"📁 Drive folder ID: {drive_folder_id_from_config}")

        # ============================================================
        # 2. INITIALIZE COMPONENTS
        # ============================================================
        ensure_directory_exists(TEMP_DOWNLOAD_DIR)
        discord_downloader = DiscordDownloader(TEMP_DOWNLOAD_DIR)
        transcriber = AudioTranscriber(WHISPER_MODEL_DEFAULT)
        drive_manager = DriveManager()
        notion_client = NotionClient()

        # ============================================================
        # 2.1. UPDATE STATUS: Processing (audit-process only)
        # ============================================================
        if action_type == "update_origin":
            logger.info("📊 Updating status to 'Processing'...")
            notion_client.update_status_field(notion_page_id, "Processing", field_map)

        if not drive_manager.service:
            raise Exception("Could not authenticate with Google Drive API")

        # ============================================================
        # 3. DOWNLOAD VIDEO FROM DISCORD
        # ============================================================
        # Update status to "Downloading" (audit-process only)
        if action_type == "update_origin":
            logger.info("📊 Updating status to 'Downloading'...")
            notion_client.update_status_field(notion_page_id, "Downloading", field_map)
        
        logger.info("📥 Downloading video from Discord...")
        video_file, message_data = discord_downloader.download_from_message_url(discord_message_url)
        
        if not video_file:
            raise ValueError("No video found in Discord message")
        
        # Extract metadata from Discord message
        video_title = message_data.get('attached_files', [{}])[0].get('filename', 'Discord Video')
        video_title = os.path.splitext(video_title)[0]  # Remove extension
        upload_date = message_data.get('timestamp', '')[:10]  # YYYY-MM-DD
        safe_title = video_title  # Already safe from Discord
        
        logger.info(f"✅ Video downloaded: {video_file.filename}")
        logger.info(f"   Title: {video_title}")
        logger.info(f"   Date: {upload_date}")

        # ============================================================
        # 4. CREATE DRIVE FOLDER
        # ============================================================
        folder_name = f"{upload_date} - {safe_title}"
        logger.info(f"📁 Creating Drive folder: {folder_name}")
        
        drive_folder_id = drive_manager.create_folder(
            folder_name,
            parent_folder_id=parent_drive_folder_id or drive_folder_id_from_config
        )
        drive_folder_url = f"https://drive.google.com/drive/folders/{drive_folder_id}"
        logger.info(f"✅ Drive folder created: {drive_folder_url}")

        # ============================================================
        # 5. EXTRACT AUDIO FROM VIDEO
        # ============================================================
        logger.info("🎵 Extracting audio from video...")
        logger.info(f"   Video path: {video_file.path}")
        logger.info(f"   Video exists: {os.path.exists(video_file.path)}")
        
        from src.youtube_downloader import YouTubeDownloader
        temp_downloader = YouTubeDownloader(TEMP_DOWNLOAD_DIR)
        
        try:
            audio_file = temp_downloader.extract_audio_from_video(video_file.path)
            
            if not audio_file:
                logger.error("❌ Audio extraction returned None")
                logger.error(f"   Check if FFmpeg is installed on the server")
                logger.error(f"   Video file: {video_file.path}")
                raise Exception("Audio extraction failed - check server logs for FFmpeg errors")
            
            logger.info(f"✅ Audio extracted: {audio_file.filename}")
            
        except Exception as e:
            logger.error(f"❌ Exception during audio extraction: {e}", exc_info=True)
            raise

        # ============================================================
        # 6. TRANSCRIBE AUDIO
        # ============================================================
        # Update status to "Transcribing" (audit-process only)
        if action_type == "update_origin":
            logger.info("📊 Updating status to 'Transcribing'...")
            notion_client.update_status_field(notion_page_id, "Transcribing", field_map)
        
        logger.info("🎤 Starting transcription...")
        transcription_result = transcriber.transcribe(audio_file, language="en")
        
        if not transcription_result or not transcription_result.text:
            raise Exception("Transcription failed or returned empty text")
        
        transcription_text = transcription_result.text
        all_segments = transcription_result.segments or []
        logger.info(f"✅ Transcription completed: {len(transcription_text)} characters")

        # Save transcription files (TXT and SRT)
        txt_filename = TRANSCRIPTION_FILE_FORMAT.format(
            date=upload_date,
            title=safe_title
        )
        txt_path = os.path.join(TEMP_DOWNLOAD_DIR, txt_filename)
        srt_path = txt_path.replace('.txt', '.srt')
        
        # Save TXT file
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(transcription_text.strip())
        logger.info(f"✅ TXT file saved: {txt_filename}")
        
        # Save SRT file if we have segments with timestamps
        if all_segments:
            try:
                from src.models import StreamingTranscriptionResult
                temp_result = StreamingTranscriptionResult(
                    text=transcription_text,
                    language="en",
                    language_probability=1.0,
                    segments=all_segments,
                    chunks_processed=1,
                    stream_completed=True
                )
                temp_result.save_srt(srt_path)
                logger.info(f"✅ SRT file generated: {os.path.basename(srt_path)}")
            except Exception as e:
                logger.warning(f"⚠️ Could not generate SRT file: {e}")

        # ============================================================
        # 6.5. COMPRESS VIDEO (if enabled)
        # ============================================================
        if COMPRESSION_ENABLED:
            logger.info("🗜️ Compressing video before upload...")
            compressed_path = temp_downloader.compress_video(video_file.path)
            
            if compressed_path and os.path.exists(compressed_path):
                # Compression successful - remove original and update video_file
                logger.info("✅ Compression successful, using compressed video")
                safe_remove_file(video_file.path)
                
                # Update video_file object with compressed file info
                video_file.path = compressed_path
                video_file.filename = os.path.basename(compressed_path)
            else:
                # Compression failed - continue with original
                logger.warning("⚠️ Compression failed, using original video")
        else:
            logger.info("ℹ️ Video compression disabled (COMPRESSION_ENABLED=False)")

        # ============================================================
        # 7. UPLOAD TO DRIVE
        # ============================================================
        # Update status to "Uploading to Drive" (audit-process only)
        if action_type == "update_origin":
            logger.info("📊 Updating status to 'Uploading to Drive'...")
            notion_client.update_status_field(notion_page_id, "Uploading to Drive", field_map)
        
        logger.info("☁️ Uploading files to Google Drive...")
        
        # Upload video
        uploaded, video_drive_file = drive_manager.upload_if_not_exists(video_file, drive_folder_id)
        video_drive_url = f"https://drive.google.com/file/d/{video_drive_file.id}/view" if video_drive_file else None
        logger.info(f"   ✅ Video uploaded: {video_file.filename}")
        
        # Upload audio
        audio_drive_url = None
        if audio_file:
            uploaded, audio_drive_file = drive_manager.upload_if_not_exists(audio_file, drive_folder_id)
            audio_drive_url = f"https://drive.google.com/file/d/{audio_drive_file.id}/view" if audio_drive_file else None
            logger.info(f"   ✅ Audio uploaded: {audio_file.filename}")
        
        # Upload TXT transcript
        drive_transcript_txt_url = None
        if os.path.exists(txt_path):
            txt_file = MediaFile(
                path=txt_path,
                filename=os.path.basename(txt_path),
                file_type='transcription'
            )
            try:
                uploaded, drive_file = drive_manager.upload_if_not_exists(txt_file, drive_folder_id)
                if drive_file:
                    drive_transcript_txt_url = f"https://drive.google.com/file/d/{drive_file.id}/view"
                    logger.info(f"   ✅ Transcript TXT uploaded")
            except Exception as e:
                logger.error(f"❌ Error uploading TXT: {e}")
            finally:
                safe_remove_file(txt_path)
        
        # Upload SRT transcript
        drive_transcript_srt_url = None
        if os.path.exists(srt_path):
            srt_file = MediaFile(
                path=srt_path,
                filename=os.path.basename(srt_path),
                file_type='transcription'
            )
            try:
                uploaded, drive_file = drive_manager.upload_if_not_exists(srt_file, drive_folder_id)
                if drive_file:
                    drive_transcript_srt_url = f"https://drive.google.com/file/d/{drive_file.id}/view"
                    logger.info(f"   ✅ Transcript SRT uploaded")
            except Exception as e:
                logger.error(f"❌ Error uploading SRT: {e}")
            finally:
                safe_remove_file(srt_path)

        # ============================================================
        # 8. CREATE/UPDATE NOTION PAGE
        # ============================================================
        logger.info("📝 Creating/updating Notion page...")
        
        # Prepare data for Notion (only fields that apply to Discord videos)
        notion_data = {
            "name": video_title,
            "video_date_time": upload_date,
            "drive_folder_link": drive_folder_url,
            "video_file": video_drive_url,
            "audio_file": audio_drive_url,
            "transcript_file": drive_transcript_txt_url,
            "transcript_srt_file": drive_transcript_srt_url,
            "transcript_text": transcription_text[:2000] if transcription_text else None,
            "status": destination_db.get("status_value", "complete"),
            "length_min": transcription_result.duration_minutes if hasattr(transcription_result, 'duration_minutes') else None
        }
        
        # Note: Discord videos don't have YouTube-specific fields:
        # - video_url (no YouTube URL)
        # - video_id (no YouTube ID)  
        # - youtube_channel (not applicable)
        # - youtube_listing_status (not applicable)
        
        # Create or update based on action_type
        if action_type == "create_new_page":
            notion_page_url = notion_client.create_video_page(
                database_id=database_id,
                data=notion_data,
                field_map=destination_db.get("field_map", {})
            )
            logger.info(f"✅ Notion page created: {notion_page_url}")
            
        else:  # update_origin
            # Build properties dynamically based on field_map
            update_props = {}

            for logical_key, column_name in field_map.items():
                value = notion_data.get(logical_key)
                if value is None:
                    continue

                # Map by property type based on logical key
                if logical_key in ("drive_folder_link", "video_file", "audio_file"):
                    update_props[column_name] = notion_client.build_url_property(value)
                elif logical_key in ("transcript_file", "transcript_srt_file"):
                    filename = "Transcript.srt" if "srt" in logical_key else "Transcript.txt"
                    update_props[column_name] = notion_client.build_files_property(value, filename)
                elif logical_key == "status":
                    update_props[column_name] = notion_client.build_select_property(value)
                elif logical_key in ("video_date_time",):
                    update_props[column_name] = notion_client.build_date_property(value)
                elif logical_key == "length_min":
                    update_props[column_name] = notion_client.build_number_property(value)
                elif logical_key == "name":
                    update_props[column_name] = notion_client.build_title_property(str(value))
                elif logical_key == "transcript_text":
                    update_props[column_name] = notion_client.build_text_property(str(value))

                logger.info(f"   📌 {column_name}: {str(value)[:50]}...")

            # Update the origin page
            if update_props:
                update_success = notion_client.update_page_properties(
                    notion_page_id,
                    update_props
                )
                if not update_success:
                    raise Exception("Could not update origin page in Notion")
                logger.info(f"✅ Origin page updated: {notion_page_id}")
            else:
                logger.warning("⚠️ No properties to update (field_map may be empty)")

            # Add transcript dropdown to origin page
            if transcription_text:
                logger.info("📝 Adding transcript dropdown to origin page...")
                notion_client.add_transcript_dropdown(notion_page_id, transcription_text)
            
            notion_page_url = f"https://notion.so/{notion_page_id}"
            logger.info(f"✅ Notion page updated: {notion_page_url}")

        # ============================================================
        # 9. CLEANUP
        # ============================================================
        logger.info("🧹 Cleaning up temporary files...")
        safe_remove_file(video_file.path)
        if audio_file:
            safe_remove_file(audio_file.path)
        # Transcript files already cleaned up after upload
        
        logger.info("=" * 80)
        logger.info("✅ Discord video processing completed successfully!")
        logger.info(f"   Notion page: {notion_page_url}")
        logger.info(f"   Drive folder: {drive_folder_url}")
        logger.info("=" * 80)

        return {
            "status": "success",
            "source": "Discord",
            "notion_page_url": notion_page_url,
            "drive_folder_url": drive_folder_url,
            "drive_video_url": video_drive_url,
            "transcription_length": len(transcription_text),
            "database_name": database_name,
            "video_title": video_title
        }

    except Exception as e:
        error_msg = f"Error in Discord video processing: {str(e)}"
        logger.error(f"❌ {error_msg}", exc_info=True)
        
        # Update error status in Notion (audit-process only)
        if action_type == "update_origin" and notion_client and field_map:
            notion_client.update_error_field(notion_page_id, error_msg, field_map)
        
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
