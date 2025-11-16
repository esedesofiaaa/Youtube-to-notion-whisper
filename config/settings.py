"""
Configuración centralizada para el proyecto YouTube to Google Drive.
Usa variables de entorno desde archivo .env
"""
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# ========== GOOGLE DRIVE API ==========
SCOPES = ['https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = os.getenv('CREDENTIALS_FILE', 'credentials.json')
TOKEN_PICKLE = os.getenv('TOKEN_PICKLE', 'token.pickle')

# Configuración de reintentos para uploads a Drive
DRIVE_UPLOAD_MAX_RETRIES = int(os.getenv('DRIVE_UPLOAD_MAX_RETRIES', '3'))
DRIVE_UPLOAD_RETRY_DELAY = int(os.getenv('DRIVE_UPLOAD_RETRY_DELAY', '2'))

# ========== WHISPER TRANSCRIPTION ==========
# Dispositivo: 'cpu' o 'cuda'
WHISPER_DEVICE = os.getenv('WHISPER_DEVICE', 'cpu')

# Tipo de cómputo según dispositivo
WHISPER_COMPUTE_TYPE = "float16" if WHISPER_DEVICE == "cuda" else "int8"

# Modelos disponibles: tiny, base, small, medium, large
WHISPER_MODEL_DEFAULT = os.getenv('WHISPER_MODEL_DEFAULT', 'small')
WHISPER_MODEL_LOCAL = os.getenv('WHISPER_MODEL_LOCAL', 'medium')

# Parámetros de transcripción optimizados
WHISPER_PARAMS = {
    'vad_filter': False,                    # VAD deshabilitado (requiere onnxruntime)
    'beam_size': 5,                         # Balance velocidad/calidad
    'condition_on_previous_text': False,    # Evita repeticiones
    'temperature': 0.1,                     # Más determinista
    'compression_ratio_threshold': 2.0,     # Control de silencios
    'log_prob_threshold': -0.6,             # Umbral de probabilidad
    'no_speech_threshold': 0.2              # Detección de segmentos sin habla
}

# ========== YT-DLP CONFIGURATION ==========
# Headers para evitar bloqueos de YouTube
YT_DLP_USER_AGENT = os.getenv(
    'YT_DLP_USER_AGENT',
    "com.google.android.youtube/19.18.35 (Linux; U; Android 13)"
)
YT_DLP_ACCEPT_LANGUAGE = os.getenv('YT_DLP_ACCEPT_LANGUAGE', "en-US,en;q=0.9")

# Configuración de reintentos
YT_DLP_RETRIES = int(os.getenv('YT_DLP_RETRIES', '10'))
YT_DLP_FRAGMENT_RETRIES = int(os.getenv('YT_DLP_FRAGMENT_RETRIES', '10'))
YT_DLP_SOCKET_TIMEOUT = int(os.getenv('YT_DLP_SOCKET_TIMEOUT', '20'))

# Configuración de clientes (evita SABR)
YT_DLP_PLAYER_SKIP = ["web_safari", "web"]
YT_DLP_PLAYER_CLIENT = ["android", "ios", "tv"]

# Configuración de audio
YT_DLP_AUDIO_CODEC = os.getenv('YT_DLP_AUDIO_CODEC', 'mp3')
YT_DLP_AUDIO_QUALITY = os.getenv('YT_DLP_AUDIO_QUALITY', '192')

# ========== DIRECTORIOS ==========
TEMP_DOWNLOAD_DIR = os.getenv('TEMP_DOWNLOAD_DIR', 'temp_downloads')
INPUT_DIR = os.getenv('INPUT_DIR', 'input')
OUTPUT_DIR = os.getenv('OUTPUT_DIR', 'output')
TEMP_DIR = os.getenv('TEMP_DIR', 'temp')
LOG_DIR = os.getenv('LOG_DIR', 'logs')

# ========== ARCHIVOS DE CONFIGURACIÓN ==========
LINKS_CONFIG_FILE = os.getenv('LINKS_CONFIG_FILE', 'LinksYT.json')
CHANNEL_MAPPING_FILE = os.getenv('CHANNEL_MAPPING_FILE', 'channel_drive_mapping.json')

# ========== LOGGING ==========
# Nivel de logging: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# ========== FFMPEG ==========
FFMPEG_AUDIO_QUALITY = os.getenv('FFMPEG_AUDIO_QUALITY', '0')  # 0 = máxima calidad
FFMPEG_ID3_VERSION = os.getenv('FFMPEG_ID3_VERSION', '3')      # Compatibilidad de tags

# ========== FORMATO DE NOMBRES ==========
DATE_FORMAT = "%Y-%m-%d"
FOLDER_NAME_FORMAT = "{date} - {title}"
VIDEO_FILE_FORMAT = "{date} - {title}.mp4"
AUDIO_FILE_FORMAT = "{date} - {title}.mp3"
TRANSCRIPTION_FILE_FORMAT = "{date} - {title}.txt"
LINK_FILE_FORMAT = "{date} - {title} - Link.txt"

# ========== VALIDACIONES ==========
# Extensiones de archivo soportadas
AUDIO_EXTENSIONS = ('.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg')
VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv')

# ========== CELERY & REDIS CONFIGURATION ==========
# Redis URL para broker y backend de Celery
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', REDIS_URL)

# Configuración de tareas de Celery
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True

# Configuración de reintentos para tareas
CELERY_TASK_MAX_RETRIES = int(os.getenv('CELERY_TASK_MAX_RETRIES', '3'))
CELERY_TASK_RETRY_DELAY = int(os.getenv('CELERY_TASK_RETRY_DELAY', '60'))  # 60 segundos

# Timeout para tareas (en segundos) - videos pueden tardar mucho
CELERY_TASK_TIME_LIMIT = int(os.getenv('CELERY_TASK_TIME_LIMIT', '3600'))  # 1 hora
CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv('CELERY_TASK_SOFT_TIME_LIMIT', '3300'))  # 55 minutos

# Configuración de workers
# IMPORTANTE: Para CPU, usar concurrency=1 (procesamiento secuencial)
# Para GPU, se puede aumentar a 2-4 dependiendo de VRAM disponible
CELERY_WORKER_CONCURRENCY = int(os.getenv('CELERY_WORKER_CONCURRENCY', '1'))

# ========== WEBHOOK SERVER CONFIGURATION ==========
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST', '0.0.0.0')
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '8000'))
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'change-this-secret-in-production')  # Para validar webhooks

# ========== FLOWER DASHBOARD ==========
FLOWER_PORT = int(os.getenv('FLOWER_PORT', '5555'))
FLOWER_BASIC_AUTH = os.getenv('FLOWER_BASIC_AUTH', '')  # Format: "user:password"
