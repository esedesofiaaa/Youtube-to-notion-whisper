#!/usr/bin/env python3
"""
Main script to download YouTube videos, transcribe them, and upload to Google Drive.
"""
import os
import sys
import json
import datetime

# Add root directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.logger import setup_logger
from config.settings import *
from utils.helpers import (
    validate_ffmpeg,
    validate_credentials,
    validate_config_file,
    ensure_directory_exists,
    safe_remove_file,
    clean_temp_directory
)
from src.youtube_downloader import YouTubeDownloader
from src.transcriber import AudioTranscriber
from src.drive_manager import DriveManager
from src.models import MediaFile

logger = setup_logger(__name__)


def create_link_file(video_url: str, output_dir: str, upload_date: str, safe_title: str) -> MediaFile:
    """
    Create a text file with the video URL.

    Args:
        video_url: YouTube video URL
        output_dir: Directory to save the file
        upload_date: Publication date
        safe_title: Sanitized title

    Returns:
        MediaFile object or None if fails
    """
    filename = LINK_FILE_FORMAT.format(date=upload_date, title=safe_title)
    output_path = os.path.join(output_dir, filename)

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"YouTube URL: {video_url}\n")
            f.write(f"This file was automatically generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"🔗 Link file created: {os.path.basename(output_path)}")
        return MediaFile(
            path=output_path,
            filename=filename,
            file_type='link'
        )
    except Exception as e:
        logger.error(f"❌ Error creating link file: {e}", exc_info=True)
        return None


def main():
    """Main function that coordinates the entire process."""
    logger.info("=" * 80)
    logger.info("🚀 Starting YouTube to Google Drive Automation")
    logger.info("=" * 80)

    # Validate dependencies
    logger.info("🔍 Validating system dependencies...")
    if not validate_ffmpeg():
        logger.error("❌ FFmpeg is required. Install it from: https://ffmpeg.org/download.html")
        return

    if not validate_credentials(CREDENTIALS_FILE):
        return

    if not validate_config_file(LINKS_CONFIG_FILE):
        return

    # Load configuration
    try:
        with open(LINKS_CONFIG_FILE, 'r') as f:
            config = json.load(f)
        parent_folder_id = config.get("parent_folder_id")
        video_urls = config.get("video_urls", [])

        if not parent_folder_id:
            logger.error(f"❌ 'parent_folder_id' not found in {LINKS_CONFIG_FILE}")
            return
        if not video_urls:
            logger.info(f"ℹ️ No URLs found in {LINKS_CONFIG_FILE}")
            return

        logger.info(f"✅ Configuration loaded: {len(video_urls)} video(s) to process")
    except FileNotFoundError:
        logger.error(f"❌ File not found: {LINKS_CONFIG_FILE}")
        return
    except json.JSONDecodeError:
        logger.error(f"❌ {LINKS_CONFIG_FILE} is not valid JSON")
        return

    # Initialize components
    downloader = YouTubeDownloader(TEMP_DOWNLOAD_DIR)
    transcriber = AudioTranscriber(WHISPER_MODEL_DEFAULT)
    drive_manager = DriveManager()

    if not drive_manager.service:
        return

    ensure_directory_exists(TEMP_DOWNLOAD_DIR)

    # Process each video
    for idx, video_url in enumerate(video_urls, 1):
        logger.info("=" * 80)
        logger.info(f"📹 Processing video {idx}/{len(video_urls)}: {video_url}")
        logger.info("=" * 80)

        # Get video information
        video_info = downloader.get_video_info(video_url)
        if not video_info:
            logger.warning(f"⚠️ Skipping video due to missing information: {video_url}")
            continue

        # Create folder in Drive
        folder_name = FOLDER_NAME_FORMAT.format(
            date=video_info.upload_date,
            title=video_info.safe_title
        )
        drive_folder_id = drive_manager.create_folder(folder_name, parent_folder_id)
        if not drive_folder_id:
            logger.warning(f"⚠️ Skipping video due to error creating folder in Drive")
            continue

        # Download video
        video_file = downloader.download_video(video_info)
        if video_file and video_file.exists():
            # Compress video if enabled
            if COMPRESSION_ENABLED:
                logger.info("🗜️ Compressing video before upload...")
                compressed_path = downloader.compress_video(video_file.path)
                
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
            
            try:
                drive_manager.upload_if_not_exists(video_file, drive_folder_id)
            except Exception as e:
                logger.error(f"❌ Error uploading video: {e}", exc_info=True)
            finally:
                safe_remove_file(video_file.path)

        # Download audio
        audio_file = downloader.download_audio(video_info)
        if audio_file and audio_file.exists():
            # Transcribe
            txt_filename = TRANSCRIPTION_FILE_FORMAT.format(
                date=video_info.upload_date,
                title=video_info.safe_title
            )
            local_txt_path = os.path.join(TEMP_DOWNLOAD_DIR, txt_filename)

            transcription_result = transcriber.transcribe(
                audio_file,
                language="en",  # Keep in English
                output_path=local_txt_path
            )

            # Upload audio
            try:
                drive_manager.upload_if_not_exists(audio_file, drive_folder_id)
            except Exception as e:
                logger.error(f"❌ Error uploading audio: {e}", exc_info=True)
            finally:
                safe_remove_file(audio_file.path)

            # Upload transcription
            if transcription_result and transcription_result.output_path:
                transcription_file = MediaFile(
                    path=transcription_result.output_path,
                    filename=os.path.basename(transcription_result.output_path),
                    file_type='transcription'
                )
                try:
                    drive_manager.upload_if_not_exists(transcription_file, drive_folder_id)
                except Exception as e:
                    logger.error(f"❌ Error uploading transcription: {e}", exc_info=True)
                finally:
                    safe_remove_file(transcription_file.path)

        # Create and upload link file
        link_file = create_link_file(
            video_url,
            TEMP_DOWNLOAD_DIR,
            video_info.upload_date,
            video_info.safe_title
        )
        if link_file and link_file.exists():
            try:
                drive_manager.upload_if_not_exists(link_file, drive_folder_id)
            except Exception as e:
                logger.error(f"❌ Error uploading link: {e}", exc_info=True)
            finally:
                safe_remove_file(link_file.path)

        logger.info(f"✅ Video fully processed: {folder_name}")

    # Cleanup
    clean_temp_directory(TEMP_DOWNLOAD_DIR)

    logger.info("=" * 80)
    logger.info("✅ Processing completed successfully")
    logger.info("=" * 80)


if __name__ == '__main__':
    main()
