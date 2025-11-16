"""
Utilidades comunes para el proyecto YouTube to Google Drive.
"""
import os
import subprocess
import time
from functools import wraps
from logger_config import get_logger

logger = get_logger(__name__)


def retry_on_failure(max_retries=3, delay=2, exceptions=(Exception,)):
    """
    Decorador para reintentar una función en caso de fallo.

    Args:
        max_retries (int): Número máximo de reintentos
        delay (int): Segundos de espera entre reintentos
        exceptions (tuple): Tupla de excepciones a capturar

    Returns:
        function: Función decorada con lógica de reintentos
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

            # Si llegamos aquí, todos los reintentos fallaron
            raise last_exception

        return wrapper
    return decorator


def validate_ffmpeg():
    """
    Valida que FFmpeg esté instalado y accesible en el sistema.

    Returns:
        bool: True si FFmpeg está disponible, False en caso contrario

    Raises:
        RuntimeError: Si FFmpeg no está disponible
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
            logger.info(f"✅ FFmpeg detectado: {version_info}")
            return True
        else:
            logger.error("⚠️ FFmpeg no parece estar disponible.")
            return False

    except FileNotFoundError:
        logger.error("❌ FFmpeg no está instalado o no está en el PATH del sistema.")
        logger.error("   Instala FFmpeg: https://ffmpeg.org/download.html")
        return False
    except subprocess.TimeoutExpired:
        logger.error("❌ FFmpeg no respondió en tiempo esperado.")
        return False
    except Exception as e:
        logger.error(f"❌ Error al verificar FFmpeg: {e}")
        return False


def validate_credentials(credentials_file):
    """
    Valida que el archivo de credenciales de Google Drive exista.

    Args:
        credentials_file (str): Ruta al archivo de credenciales

    Returns:
        bool: True si el archivo existe, False en caso contrario
    """
    if not os.path.exists(credentials_file):
        logger.error(f"❌ Archivo de credenciales no encontrado: {credentials_file}")
        logger.error("   Descarga las credenciales desde Google Cloud Console")
        logger.error("   https://console.cloud.google.com/")
        return False

    logger.info(f"✅ Archivo de credenciales encontrado: {credentials_file}")
    return True


def validate_config_file(config_file):
    """
    Valida que el archivo de configuración exista.

    Args:
        config_file (str): Ruta al archivo de configuración

    Returns:
        bool: True si el archivo existe, False en caso contrario
    """
    if not os.path.exists(config_file):
        logger.error(f"❌ Archivo de configuración no encontrado: {config_file}")
        return False

    logger.info(f"✅ Archivo de configuración encontrado: {config_file}")
    return True


def sanitize_filename(filename):
    """
    Sanitiza un nombre de archivo reemplazando caracteres inválidos.

    Args:
        filename (str): Nombre de archivo a sanitizar

    Returns:
        str: Nombre de archivo sanitizado
    """
    return "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in filename)


def ensure_directory_exists(directory):
    """
    Asegura que un directorio exista, creándolo si es necesario.

    Args:
        directory (str): Ruta del directorio

    Returns:
        bool: True si el directorio existe o fue creado exitosamente
    """
    try:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"📁 Directorio creado: {directory}")
        return True
    except Exception as e:
        logger.error(f"❌ Error al crear directorio {directory}: {e}")
        return False


def is_audio_file(file_path, audio_extensions=None):
    """
    Determina si un archivo es de audio basado en su extensión.

    Args:
        file_path (str): Ruta al archivo
        audio_extensions (tuple): Tupla de extensiones de audio válidas

    Returns:
        bool: True si es un archivo de audio, False en caso contrario
    """
    if audio_extensions is None:
        from config import AUDIO_EXTENSIONS
        audio_extensions = AUDIO_EXTENSIONS

    return file_path.lower().endswith(audio_extensions)


def is_video_file(file_path, video_extensions=None):
    """
    Determina si un archivo es de video basado en su extensión.

    Args:
        file_path (str): Ruta al archivo
        video_extensions (tuple): Tupla de extensiones de video válidas

    Returns:
        bool: True si es un archivo de video, False en caso contrario
    """
    if video_extensions is None:
        from config import VIDEO_EXTENSIONS
        video_extensions = VIDEO_EXTENSIONS

    return file_path.lower().endswith(video_extensions)


def format_file_size(size_bytes):
    """
    Formatea un tamaño en bytes a una representación legible.

    Args:
        size_bytes (int): Tamaño en bytes

    Returns:
        str: Tamaño formateado (ej: "15.3 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def safe_remove_file(file_path):
    """
    Elimina un archivo de forma segura, manejando errores.

    Args:
        file_path (str): Ruta al archivo a eliminar

    Returns:
        bool: True si se eliminó exitosamente, False en caso contrario
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"🗑️ Eliminado: {os.path.basename(file_path)}")
            return True
        return False
    except OSError as e:
        logger.warning(f"⚠️ Error al eliminar {file_path}: {e}")
        return False


def clean_temp_directory(directory):
    """
    Limpia un directorio temporal si está vacío.

    Args:
        directory (str): Ruta al directorio temporal

    Returns:
        bool: True si se limpió exitosamente o no existía, False si quedaron archivos
    """
    try:
        if not os.path.exists(directory):
            return True

        if not os.listdir(directory):
            os.rmdir(directory)
            logger.info(f"🗑️ Directorio temporal eliminado: {directory}")
            return True
        else:
            logger.warning(
                f"⚠️ Directorio temporal '{directory}' no está vacío, "
                f"puede requerir limpieza manual."
            )
            return False
    except OSError as e:
        logger.warning(f"⚠️ Error al eliminar directorio temporal '{directory}': {e}")
        return False
