#!/usr/bin/env python3
"""
Script to transcribe local audio/video files using Faster-Whisper.
"""
import os
import sys
import argparse
import subprocess
import shutil

# Add root directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.logger import setup_logger
from config.settings import *
from utils.helpers import (
    validate_ffmpeg,
    ensure_directory_exists,
    is_audio_file,
    is_video_file,
    clean_temp_directory,
    sanitize_filename
)
from src.transcriber import AudioTranscriber
from src.models import MediaFile

logger = setup_logger(__name__)


def extract_audio_from_video(video_path, output_dir):
    """Extract MP3 audio from a video file using FFmpeg."""
    filename = os.path.basename(video_path)
    base_name = os.path.splitext(filename)[0]
    output_path = os.path.join(output_dir, f"{base_name}.mp3")

    try:
        logger.info(f"ℹ️ Extracting audio with FFmpeg from: {filename}")
        ffmpeg_cmd = [
            'ffmpeg', '-i', video_path, '-q:a', FFMPEG_AUDIO_QUALITY,
            '-map', 'a', '-id3v2_version', FFMPEG_ID3_VERSION,
            output_path, '-y'
        ]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if os.path.exists(output_path):
            logger.info(f"✅ Audio extracted: {os.path.basename(output_path)}")
            return output_path
    except Exception as e:
        logger.error(f"❌ Error extracting audio: {e}", exc_info=True)
    return None


def main():
    parser = argparse.ArgumentParser(description='Transcribe audio and video files to text')
    parser.add_argument('--lang', type=str, help='Language code (e.g. es, en, fr)')
    parser.add_argument('--input', type=str, default=INPUT_DIR, help='Input directory')
    parser.add_argument('--output', type=str, default=OUTPUT_DIR, help='Output directory')
    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("🎙️ Starting Local Transcriber")
    logger.info("=" * 80)

    for directory in [args.input, args.output, TEMP_DIR]:
        ensure_directory_exists(directory)

    if not validate_ffmpeg():
        logger.error("❌ FFmpeg not available")
        return

    transcriber = AudioTranscriber(WHISPER_MODEL_LOCAL)
    input_files = [f for f in os.listdir(args.input)
                  if is_audio_file(os.path.join(args.input, f)) or is_video_file(os.path.join(args.input, f))]

    if not input_files:
        logger.error(f"❌ No files found in '{args.input}'")
        return

    logger.info(f"✅ {len(input_files)} file(s) to process")

    for idx, filename in enumerate(input_files, 1):
        file_path = os.path.join(args.input, filename)
        logger.info("=" * 80)
        logger.info(f"📄 Processing {idx}/{len(input_files)}: {filename}")

        audio_path = file_path
        if is_video_file(file_path):
            audio_path = extract_audio_from_video(file_path, TEMP_DIR)
            if not audio_path:
                continue

        audio_file = MediaFile(path=audio_path, filename=os.path.basename(audio_path), file_type='audio')
        safe_title = sanitize_filename(os.path.splitext(filename)[0])
        output_path = os.path.join(args.output, f"{safe_title}.txt")

        transcriber.transcribe(audio_file, language=args.lang, output_path=output_path)

        if is_video_file(file_path) and audio_path != file_path:
            final_audio = os.path.join(args.output, os.path.basename(audio_path))
            shutil.copy2(audio_path, final_audio)
            os.remove(audio_path)

    clean_temp_directory(TEMP_DIR)
    logger.info("=" * 80)
    logger.info("✅ Processing complete")
    logger.info("=" * 80)


if __name__ == '__main__':
    main()
