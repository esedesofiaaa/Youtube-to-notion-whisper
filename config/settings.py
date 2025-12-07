"""
Centralized configuration for YouTube to Google Drive project.
Uses environment variables from .env file
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# ========== GOOGLE DRIVE API ==========
SCOPES = ['https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = os.getenv('CREDENTIALS_FILE', 'credentials.json')
TOKEN_PICKLE = os.getenv('TOKEN_PICKLE', 'token.pickle')

# Retry configuration for Drive uploads
DRIVE_UPLOAD_MAX_RETRIES = int(os.getenv('DRIVE_UPLOAD_MAX_RETRIES', '3'))
DRIVE_UPLOAD_RETRY_DELAY = int(os.getenv('DRIVE_UPLOAD_RETRY_DELAY', '2'))

# ========== WHISPER TRANSCRIPTION ==========
# Device: 'cpu' or 'cuda'
WHISPER_DEVICE = os.getenv('WHISPER_DEVICE', 'cpu')

# Compute type based on device
WHISPER_COMPUTE_TYPE = "float16" if WHISPER_DEVICE == "cuda" else "int8"

# Available models: tiny, base, small, medium, large
WHISPER_MODEL_DEFAULT = os.getenv('WHISPER_MODEL_DEFAULT', 'small')
WHISPER_MODEL_LOCAL = os.getenv('WHISPER_MODEL_LOCAL', 'medium')

# Optimized transcription parameters
WHISPER_PARAMS = {
    'vad_filter': False,                    # VAD disabled (requires onnxruntime)
    'beam_size': 5,                         # Balance speed/quality
    'condition_on_previous_text': False,    # Avoid repetitions
    'temperature': 0.1,                     # More deterministic
    'compression_ratio_threshold': 2.0,     # Silence control
    'log_prob_threshold': -0.6,             # Probability threshold
    'no_speech_threshold': 0.2              # Silent segment detection
}

# ========== YT-DLP CONFIGURATION ==========
# Headers to avoid YouTube blocking
YT_DLP_USER_AGENT = os.getenv(
    'YT_DLP_USER_AGENT',
    "com.google.android.youtube/19.18.35 (Linux; U; Android 13)"
)
YT_DLP_ACCEPT_LANGUAGE = os.getenv('YT_DLP_ACCEPT_LANGUAGE', "en-US,en;q=0.9")

# Retry configuration
YT_DLP_RETRIES = int(os.getenv('YT_DLP_RETRIES', '10'))
YT_DLP_FRAGMENT_RETRIES = int(os.getenv('YT_DLP_FRAGMENT_RETRIES', '10'))
YT_DLP_SOCKET_TIMEOUT = int(os.getenv('YT_DLP_SOCKET_TIMEOUT', '20'))

# Client configuration (avoid SABR)
YT_DLP_PLAYER_SKIP = ["web_safari", "web"]
YT_DLP_PLAYER_CLIENT = ["android", "ios", "tv"]

# Audio configuration
YT_DLP_AUDIO_CODEC = os.getenv('YT_DLP_AUDIO_CODEC', 'mp3')
YT_DLP_AUDIO_QUALITY = os.getenv('YT_DLP_AUDIO_QUALITY', '192')

# ========== DIRECTORIES ==========
TEMP_DOWNLOAD_DIR = os.getenv('TEMP_DOWNLOAD_DIR', 'temp_downloads')
INPUT_DIR = os.getenv('INPUT_DIR', 'input')
OUTPUT_DIR = os.getenv('OUTPUT_DIR', 'output')
TEMP_DIR = os.getenv('TEMP_DIR', 'temp')
LOG_DIR = os.getenv('LOG_DIR', 'logs')

# ========== CONFIGURATION FILES ==========
LINKS_CONFIG_FILE = os.getenv('LINKS_CONFIG_FILE', 'LinksYT.json')
CHANNEL_MAPPING_FILE = os.getenv('CHANNEL_MAPPING_FILE', 'channel_drive_mapping.json')

# ========== LOGGING ==========
# Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# ========== FFMPEG ==========
FFMPEG_AUDIO_QUALITY = os.getenv('FFMPEG_AUDIO_QUALITY', '0')  # 0 = maximum quality
FFMPEG_ID3_VERSION = os.getenv('FFMPEG_ID3_VERSION', '3')      # Tag compatibility

# ========== NAMING FORMAT ==========
DATE_FORMAT = "%Y-%m-%d"
FOLDER_NAME_FORMAT = "{date} - {title}"
VIDEO_FILE_FORMAT = "{date} - {title}.mp4"
AUDIO_FILE_FORMAT = "{date} - {title}.mp3"
TRANSCRIPTION_FILE_FORMAT = "{date} - {title}.txt"
LINK_FILE_FORMAT = "{date} - {title} - Link.txt"

# ========== VALIDATIONS ==========
# Supported file extensions
AUDIO_EXTENSIONS = ('.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg')
VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv')

# ========== CELERY & REDIS CONFIGURATION ==========
# Redis URL for Celery broker and backend
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', REDIS_URL)

# Celery task configuration
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True

# Retry configuration for tasks
CELERY_TASK_MAX_RETRIES = int(os.getenv('CELERY_TASK_MAX_RETRIES', '3'))
CELERY_TASK_RETRY_DELAY = int(os.getenv('CELERY_TASK_RETRY_DELAY', '60'))  # 60 seconds

# Task timeout (in seconds) - videos can take a long time
# Default: 4 hours for long videos with transcription
CELERY_TASK_TIME_LIMIT = int(os.getenv('CELERY_TASK_TIME_LIMIT', '14400'))  # 4 hours
CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv('CELERY_TASK_SOFT_TIME_LIMIT', '14100'))  # 3h 55min

# Worker configuration
# IMPORTANT: For CPU, use concurrency=1 (sequential processing)
# For GPU, can increase to 2-4 depending on available VRAM
CELERY_WORKER_CONCURRENCY = int(os.getenv('CELERY_WORKER_CONCURRENCY', '1'))

# ========== WEBHOOK SERVER CONFIGURATION ==========
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST', '0.0.0.0')
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '8000'))
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'change-this-secret-in-production')  # For webhook validation

# ========== FLOWER DASHBOARD ==========
FLOWER_PORT = int(os.getenv('FLOWER_PORT', '5555'))
FLOWER_BASIC_AUTH = os.getenv('FLOWER_BASIC_AUTH', '')  # Format: "user:password"

# ========== STREAMING TRANSCRIPTION CONFIGURATION ==========
# Audio sample rate for Whisper (16kHz is optimal)
STREAMING_SAMPLE_RATE = int(os.getenv('STREAMING_SAMPLE_RATE', '16000'))

# Buffer size for streaming (in bytes) - larger = more latency but more stable
STREAMING_BUFFER_SIZE = int(os.getenv('STREAMING_BUFFER_SIZE', '65536'))  # 64KB

# Chunk duration in seconds for transcription batching
# Whisper works best with 30-second chunks
STREAMING_CHUNK_DURATION = float(os.getenv('STREAMING_CHUNK_DURATION', '30.0'))

# Minimum audio duration (seconds) before starting transcription
# Helps avoid partial word transcriptions
STREAMING_MIN_AUDIO_DURATION = float(os.getenv('STREAMING_MIN_AUDIO_DURATION', '5.0'))

# Maximum retries for streaming before falling back to traditional method
STREAMING_MAX_RETRIES = int(os.getenv('STREAMING_MAX_RETRIES', '3'))

# Timeout (seconds) for waiting on stream data before considering it stalled
STREAMING_READ_TIMEOUT = float(os.getenv('STREAMING_READ_TIMEOUT', '60.0'))
