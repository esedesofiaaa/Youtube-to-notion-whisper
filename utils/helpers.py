"""
Common utilities for the YouTube to Google Drive project.
"""
import os
import subprocess
import time
from functools import wraps
from config.logger import get_logger

logger = get_logger(__name__)


def retry_on_failure(max_retries=3, delay=2, exceptions=(Exception,)):
    """
    Decorator to retry a function on failure.

    Args:
        max_retries (int): Maximum number of retries
        delay (int): Seconds to wait between retries
        exceptions (tuple): Tuple of exceptions to catch

    Returns:
        function: Decorated function with retry logic
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait_time = delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(
                            f"⚠️ {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}). "
                            f"Retrying in {wait_time}s... Error: {str(e)}"
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            f"❌ {func.__name__} failed after {max_retries + 1} attempts. "
                            f"Last error: {str(e)}"
                        )

            # If we reach here, all retries failed
            raise last_exception

        return wrapper
    return decorator


def validate_ffmpeg():
    """
    Validate that FFmpeg is installed and accessible in the system.

    Returns:
        bool: True if FFmpeg is available, False otherwise

    Raises:
        RuntimeError: If FFmpeg is not available
    """
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )

        if result.returncode == 0:
            version_info = result.stdout.decode('utf-8').split('\n')[0]
            logger.info(f"✅ FFmpeg detected: {version_info}")
            return True
        else:
            logger.error("⚠️ FFmpeg does not appear to be available.")
            return False

    except FileNotFoundError:
        logger.error("❌ FFmpeg is not installed or not in the system PATH.")
        logger.error("   Install FFmpeg: https://ffmpeg.org/download.html")
        return False
    except subprocess.TimeoutExpired:
        logger.error("❌ FFmpeg did not respond in expected time.")
        return False
    except Exception as e:
        logger.error(f"❌ Error verifying FFmpeg: {e}")
        return False


def validate_credentials(credentials_file):
    """
    Validate that the Google Drive credentials file exists.

    Args:
        credentials_file (str): Path to credentials file

    Returns:
        bool: True if file exists, False otherwise
    """
    if not os.path.exists(credentials_file):
        logger.error(f"❌ Credentials file not found: {credentials_file}")
        logger.error("   Download credentials from Google Cloud Console")
        logger.error("   https://console.cloud.google.com/")
        return False

    logger.info(f"✅ Credentials file found: {credentials_file}")
    return True


def validate_config_file(config_file):
    """
    Validate that the configuration file exists.

    Args:
        config_file (str): Path to configuration file

    Returns:
        bool: True if file exists, False otherwise
    """
    if not os.path.exists(config_file):
        logger.error(f"❌ Configuration file not found: {config_file}")
        return False

    logger.info(f"✅ Configuration file found: {config_file}")
    return True


def sanitize_filename(filename):
    """
    Sanitize a filename by replacing invalid characters.

    Args:
        filename (str): Filename to sanitize

    Returns:
        str: Sanitized filename
    """
    return "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in filename)


def ensure_directory_exists(directory):
    """
    Ensure a directory exists, creating it if necessary.

    Args:
        directory (str): Directory path

    Returns:
        bool: True if directory exists or was created successfully
    """
    try:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"📁 Directory created: {directory}")
        return True
    except Exception as e:
        logger.error(f"❌ Error creating directory {directory}: {e}")
        return False


def is_audio_file(file_path, audio_extensions=None):
    """
    Determine if a file is an audio file based on its extension.

    Args:
        file_path (str): File path
        audio_extensions (tuple): Tuple of valid audio extensions

    Returns:
        bool: True if it is an audio file, False otherwise
    """
    if audio_extensions is None:
        from config import AUDIO_EXTENSIONS
        audio_extensions = AUDIO_EXTENSIONS

    return file_path.lower().endswith(audio_extensions)


def is_video_file(file_path, video_extensions=None):
    """
    Determine if a file is a video file based on its extension.

    Args:
        file_path (str): File path
        video_extensions (tuple): Tuple of valid video extensions

    Returns:
        bool: True if it is a video file, False otherwise
    """
    if video_extensions is None:
        from config import VIDEO_EXTENSIONS
        video_extensions = VIDEO_EXTENSIONS

    return file_path.lower().endswith(video_extensions)


def format_file_size(size_bytes):
    """
    Format a size in bytes to a human-readable representation.

    Args:
        size_bytes (int): Size in bytes

    Returns:
        str: Formatted size (e.g. "15.3 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def safe_remove_file(file_path):
    """
    Safely remove a file, handling errors.

    Args:
        file_path (str): Path to file to remove

    Returns:
        bool: True if removed successfully, False otherwise
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"🗑️ Deleted: {os.path.basename(file_path)}")
            return True
        return False
    except OSError as e:
        logger.warning(f"⚠️ Error deleting {file_path}: {e}")
        return False


def clean_temp_directory(directory):
    """
    Clean a temporary directory if it is empty.

    Args:
        directory (str): Path to temporary directory

    Returns:
        bool: True if cleaned successfully or did not exist, False if files remain
    """
    try:
        if not os.path.exists(directory):
            return True

        if not os.listdir(directory):
            os.rmdir(directory)
            logger.info(f"🗑️ Temporary directory deleted: {directory}")
            return True
        else:
            logger.warning(
                f"⚠️ Temporary directory '{directory}' is not empty, "
                f"may require manual cleanup."
            )
            return False
    except OSError as e:
        logger.warning(f"⚠️ Error deleting temporary directory '{directory}': {e}")
        return False


def format_timestamp(seconds: float) -> str:
    """
    Format seconds to SRT timestamp format (HH:MM:SS,mmm).
    
    Args:
        seconds: Time in seconds
        
    Returns:
        str: Formatted timestamp
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(segments: list, output_path: str):
    """
    Generate an SRT file from transcription segments.
    
    Args:
        segments: List of segment dictionaries with 'start', 'end', 'text'
        output_path: Path to save the SRT file
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(segments, start=1):
                # Handle both dictionary and object access for segments
                if isinstance(segment, dict):
                    start_time = segment.get('start', 0)
                    end_time = segment.get('end', 0)
                    text = segment.get('text', '')
                else:
                    start_time = getattr(segment, 'start', 0)
                    end_time = getattr(segment, 'end', 0)
                    text = getattr(segment, 'text', '')

                start = format_timestamp(start_time)
                end = format_timestamp(end_time)
                text = text.strip()
                
                f.write(f"{i}\n")
                f.write(f"{start} --> {end}\n")
                f.write(f"{text}\n\n")
        
        logger.info(f"📝 SRT file generated: {output_path}")
        return True
    except Exception as e:
        logger.error(f"❌ Error generating SRT file: {e}")
        return False
