"""
Tareas asíncronas de Celery para procesamiento de videos.
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
    Clase base para tareas con callbacks automáticos.
    """

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Ejecutado cuando una tarea falla."""
        logger.error(f"❌ Tarea {task_id} falló: {exc}")
        logger.error(f"   Args: {args}")
        logger.error(f"   Traceback: {einfo}")

    def on_success(self, retval, task_id, args, kwargs):
        """Ejecutado cuando una tarea tiene éxito."""
        logger.info(f"✅ Tarea {task_id} completada exitosamente")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Ejecutado cuando una tarea se reintenta."""
        logger.warning(f"🔄 Tarea {task_id} reintentando debido a: {exc}")


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
    Tarea principal: procesa un video de YouTube y crea entrada en Notion.

    Args:
        discord_entry_id: ID de la entrada en Discord Message Database
        youtube_url: URL del video de YouTube
        channel: Canal de Discord (para determinar DB de destino)
        parent_drive_folder_id: ID de la carpeta padre en Drive (opcional)

    Returns:
        dict: Información de la tarea completada

    Raises:
        Exception: Si ocurre algún error durante el procesamiento
    """
    task_id = self.request.id
    logger.info("=" * 80)
    logger.info(f"🚀 Iniciando procesamiento de video [Task ID: {task_id}]")
    logger.info(f"   YouTube URL: {youtube_url}")
    logger.info(f"   Canal: {channel}")
    logger.info(f"   Discord Entry ID: {discord_entry_id}")
    logger.info("=" * 80)

    try:
        # 1. Validar y obtener configuración
        destination_db = get_destination_database(channel)
        if not destination_db:
            raise ValueError(f"No se encontró base de datos de destino para el canal: {channel}")

        database_id = destination_db["database_id"]
        database_name = destination_db["database_name"]
        logger.info(f"📊 Base de datos de destino: {database_name}")

        # 2. Inicializar componentes
        ensure_directory_exists(TEMP_DOWNLOAD_DIR)
        downloader = YouTubeDownloader(TEMP_DOWNLOAD_DIR)
        transcriber = AudioTranscriber(WHISPER_MODEL_DEFAULT)
        drive_manager = DriveManager()
        notion_client = NotionClient()

        if not drive_manager.service:
            raise Exception("No se pudo autenticar con Google Drive API")

        # 3. Obtener información del video
        logger.info("📹 Obteniendo información del video...")
        video_info = downloader.get_video_info(youtube_url)
        if not video_info:
            raise Exception(f"No se pudo obtener información del video: {youtube_url}")

        # 4. Obtener parent_folder_id de Discord Message Database si no se proporcionó
        if not parent_drive_folder_id:
            logger.info("📄 Obteniendo información de Discord Message Database...")
            discord_data = notion_client.get_discord_message_entry(discord_entry_id)
            if discord_data:
                # Aquí podrías extraer parent_folder_id si estuviera en la DB
                # Por ahora, usaremos un valor por defecto o lo pasaremos desde el webhook
                logger.info("✅ Datos de Discord Message DB obtenidos")

        # Si aún no tenemos parent_folder_id, usar uno por defecto (debería venir del webhook)
        if not parent_drive_folder_id:
            logger.warning("⚠️ No se proporcionó parent_drive_folder_id, usando carpeta raíz")
            parent_drive_folder_id = "root"  # Esto debería configurarse mejor

        # 5. Crear carpeta en Drive
        folder_name = f"{video_info.upload_date} - {video_info.safe_title}"
        logger.info(f"📁 Creando carpeta en Drive: {folder_name}")
        drive_folder_id = drive_manager.create_folder(folder_name, parent_drive_folder_id)
        if not drive_folder_id:
            raise Exception("No se pudo crear carpeta en Google Drive")

        # Construir URL de la carpeta de Drive
        drive_folder_url = f"https://drive.google.com/drive/folders/{drive_folder_id}"

        # 6. Descargar video
        logger.info("⬇️ Descargando video...")
        video_file = downloader.download_video(video_info)
        drive_video_url = None

        if video_file and video_file.exists():
            try:
                uploaded, drive_file = drive_manager.upload_if_not_exists(video_file, drive_folder_id)
                if drive_file:
                    drive_video_url = f"https://drive.google.com/file/d/{drive_file.id}/view"
                    logger.info(f"✅ Video subido a Drive: {drive_video_url}")
            except Exception as e:
                logger.error(f"❌ Error al subir video: {e}", exc_info=True)
            finally:
                safe_remove_file(video_file.path)

        # 7. Descargar audio y transcribir
        logger.info("🎵 Descargando audio...")
        audio_file = downloader.download_audio(video_info)
        transcription_text = ""

        if audio_file and audio_file.exists():
            try:
                # Transcribir
                txt_filename = TRANSCRIPTION_FILE_FORMAT.format(
                    date=video_info.upload_date,
                    title=video_info.safe_title
                )
                local_txt_path = os.path.join(TEMP_DOWNLOAD_DIR, txt_filename)

                logger.info("🎤 Iniciando transcripción...")
                transcription_result = transcriber.transcribe(
                    audio_file,
                    language="en",
                    output_path=local_txt_path
                )

                if transcription_result:
                    transcription_text = transcription_result.text

                # Subir audio
                drive_manager.upload_if_not_exists(audio_file, drive_folder_id)

                # Subir transcripción
                if transcription_result and transcription_result.output_path:
                    transcription_file = MediaFile(
                        path=transcription_result.output_path,
                        filename=os.path.basename(transcription_result.output_path),
                        file_type='transcription'
                    )
                    drive_manager.upload_if_not_exists(transcription_file, drive_folder_id)
                    safe_remove_file(transcription_file.path)

            except Exception as e:
                logger.error(f"❌ Error en transcripción: {e}", exc_info=True)
            finally:
                safe_remove_file(audio_file.path)

        # 8. Crear página en Notion (base de datos de destino)
        logger.info(f"📝 Creando página en Notion ({database_name})...")
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
            raise Exception("No se pudo crear página en Notion")

        notion_page_url = notion_page.get("url")
        logger.info(f"✅ Página de Notion creada: {notion_page_url}")

        # 9. Actualizar campo Transcript en Discord Message Database
        logger.info("🔄 Actualizando campo Transcript en Discord Message DB...")
        update_success = notion_client.update_transcript_field(
            discord_entry_id,
            notion_page_url
        )

        if not update_success:
            logger.warning("⚠️ No se pudo actualizar el campo Transcript")

        # 10. Limpiar archivos temporales
        clean_temp_directory(TEMP_DOWNLOAD_DIR)

        # Resultado de la tarea
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
        logger.info("✅ Procesamiento completado exitosamente")
        logger.info(f"   Notion Page: {notion_page_url}")
        logger.info("=" * 80)

        return result

    except SoftTimeLimitExceeded:
        logger.error(f"⏱️ Tarea {task_id} excedió el tiempo límite")
        raise

    except Exception as e:
        logger.error(f"❌ Error en procesamiento de video: {e}", exc_info=True)
        # Limpiar en caso de error
        clean_temp_directory(TEMP_DOWNLOAD_DIR)
        raise


@celery_app.task(bind=True, base=CallbackTask)
def test_task(self, message: str = "Hello from Celery!"):
    """
    Tarea de prueba para verificar que Celery funciona correctamente.

    Args:
        message: Mensaje a loggear

    Returns:
        dict: Información de la tarea
    """
    task_id = self.request.id
    logger.info(f"🧪 Test task ejecutándose [Task ID: {task_id}]")
    logger.info(f"   Mensaje: {message}")

    return {
        "status": "success",
        "task_id": task_id,
        "message": message
    }
