"""
Asynchronous Celery tasks for video processing.
"""
import os
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from src.celery_app import celery_app
from src.youtube_downloader import YouTubeDownloader
from src.transcriber import AudioTranscriber
from src.drive_manager import DriveManager
from src.notion_client import NotionClient
from src.models import MediaFile
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
    retry_backoff_max=600,  # Máximo 10 minutos de backoff
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
    Main task: process a YouTube video and create entry in Notion.

    Args:
        discord_entry_id: ID of the entry in Discord Message Database
        youtube_url: YouTube video URL
        channel: Discord channel (to determine destination DB)
        parent_drive_folder_id: ID of parent folder in Drive (optional)

    Returns:
        dict: Information about the completed task

    Raises:
        Exception: If any error occurs during processing
    """
    task_id = self.request.id
    logger.info("=" * 80)
    logger.info(f"🚀 Starting video processing [Task ID: {task_id}]")
    logger.info(f"   YouTube URL: {youtube_url}")
    logger.info(f"   Channel: {channel}")
    logger.info(f"   Discord Entry ID: {discord_entry_id}")
    logger.info("=" * 80)

    try:
        # 1. Validate and get configuration
        destination_db = get_destination_database(channel)
        if not destination_db:
            raise ValueError(f"No destination database found for channel: {channel}")

        database_id = destination_db["database_id"]
        database_name = destination_db["database_name"]
        drive_folder_id_from_config = destination_db.get("drive_folder_id")
        logger.info(f"📊 Destination database: {database_name}")
        logger.info(f"📁 Drive folder ID: {drive_folder_id_from_config}")

        # 2. Initialize components
        ensure_directory_exists(TEMP_DOWNLOAD_DIR)
        downloader = YouTubeDownloader(TEMP_DOWNLOAD_DIR)
        transcriber = AudioTranscriber(WHISPER_MODEL_DEFAULT)
        drive_manager = DriveManager()
        notion_client = NotionClient()

        if not drive_manager.service:
            raise Exception("Could not authenticate with Google Drive API")

        # 3. Get video information
        logger.info("📹 Getting video information...")
        video_info = downloader.get_video_info(youtube_url)
        if not video_info:
            raise Exception(f"Could not get video information: {youtube_url}")

        # 4. Get parent_folder_id: use config value or webhook parameter
        if not parent_drive_folder_id:
            # Use the folder ID from channel configuration
            parent_drive_folder_id = drive_folder_id_from_config
            logger.info(f"📂 Using Drive folder from channel config: {parent_drive_folder_id}")
        
        if not parent_drive_folder_id:
            raise ValueError(f"No Drive folder ID configured for channel: {channel}")

        # 5. Create folder in Drive
        folder_name = f"{video_info.upload_date} - {video_info.safe_title}"
        logger.info(f"📁 Creating folder in Drive: {folder_name}")
        drive_folder_id = drive_manager.create_folder(folder_name, parent_drive_folder_id)
        if not drive_folder_id:
            raise Exception("Could not create folder in Google Drive")

        # Build Drive folder URL
        drive_folder_url = f"https://drive.google.com/drive/folders/{drive_folder_id}"

        # 6. Download video
        logger.info("⬇️ Downloading video...")
        video_file = downloader.download_video(video_info)
        drive_video_url = None

        if video_file and video_file.exists():
            try:
                uploaded, drive_file = drive_manager.upload_if_not_exists(video_file, drive_folder_id)
                if drive_file:
                    drive_video_url = f"https://drive.google.com/file/d/{drive_file.id}/view"
                    logger.info(f"✅ Video uploaded to Drive: {drive_video_url}")
            except Exception as e:
                logger.error(f"❌ Error uploading video: {e}", exc_info=True)
            finally:
                safe_remove_file(video_file.path)

        # 7. Download audio and transcribe
        logger.info("🎵 Downloading audio...")
        audio_file = downloader.download_audio(video_info)
        transcription_text = ""

        if audio_file and audio_file.exists():
            try:
                # Transcribe
                txt_filename = TRANSCRIPTION_FILE_FORMAT.format(
                    date=video_info.upload_date,
                    title=video_info.safe_title
                )
                local_txt_path = os.path.join(TEMP_DOWNLOAD_DIR, txt_filename)

                logger.info("🎤 Starting transcription...")
                transcription_result = transcriber.transcribe(
                    audio_file,
                    language="en",
                    output_path=local_txt_path
                )

                if transcription_result:
                    transcription_text = transcription_result.text

                # Upload audio
                drive_manager.upload_if_not_exists(audio_file, drive_folder_id)

                # Upload transcription
                if transcription_result and transcription_result.output_path:
                    transcription_file = MediaFile(
                        path=transcription_result.output_path,
                        filename=os.path.basename(transcription_result.output_path),
                        file_type='transcription'
                    )
                    drive_manager.upload_if_not_exists(transcription_file, drive_folder_id)
                    safe_remove_file(transcription_file.path)

            except Exception as e:
                logger.error(f"❌ Error in transcription: {e}", exc_info=True)
            finally:
                safe_remove_file(audio_file.path)

        # 8. Create page in Notion (destination database)
        logger.info(f"📝 Creating page in Notion ({database_name})...")
        page_title = f"{video_info.upload_date} - {video_info.title}"

        notion_page = notion_client.create_video_page(
            database_id=database_id,
            title=page_title,
            video_date=video_info.upload_date,
            video_url=youtube_url,
            drive_folder_url=drive_folder_url,
            drive_video_url=drive_video_url or "",
            discord_channel=channel
        )

        if not notion_page:
            raise Exception("Could not create page in Notion")

        notion_page_url = notion_page.get("url")
        logger.info(f"✅ Notion page created: {notion_page_url}")

        # 9. Update Transcript field in Discord Message Database
        logger.info("🔄 Updating Transcript field in Discord Message DB...")
        update_success = notion_client.update_transcript_field(
            discord_entry_id,
            notion_page_url
        )

        if not update_success:
            logger.error("❌ ERROR: Could not update Transcript field")

        # 10. Clean up temporary files
        clean_temp_directory(TEMP_DOWNLOAD_DIR)

        # Task result
        result = {
            "status": "success",
            "task_id": task_id,
            "youtube_url": youtube_url,
            "video_title": video_info.title,
            "notion_page_url": notion_page_url,
            "drive_folder_url": drive_folder_url,
            "drive_video_url": drive_video_url,
            "transcription_length": len(transcription_text),
            "database_name": database_name
        }

        logger.info("=" * 80)
        logger.info("✅ Processing completed successfully")
        logger.info(f"   Notion Page: {notion_page_url}")
        logger.info("=" * 80)

        return result

    except SoftTimeLimitExceeded:
        logger.error(f"⏱️ Task {task_id} exceeded time limit")
        raise

    except Exception as e:
        logger.error(f"❌ Error in video processing: {e}", exc_info=True)
        # Clean up on error
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
