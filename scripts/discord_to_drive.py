#!/usr/bin/env python3
"""
Script principal para descargar videos de YouTube, transcribirlos y subirlos a Google Drive.
"""
import os
import sys
import json
import datetime

# Añadir el directorio raíz al path para imports
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
    Crea un archivo de texto con la URL del video.

    Args:
        video_url: URL del video de YouTube
        output_dir: Directorio donde guardar el archivo
        upload_date: Fecha de publicación
        safe_title: Título sanitizado

    Returns:
        MediaFile object o None si falla
    """
    filename = LINK_FILE_FORMAT.format(date=upload_date, title=safe_title)
    output_path = os.path.join(output_dir, filename)

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"YouTube URL: {video_url}\n")
            f.write(f"Este archivo fue generado automáticamente el {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"🔗 Archivo de link creado: {os.path.basename(output_path)}")
        return MediaFile(
            path=output_path,
            filename=filename,
            file_type='link'
        )
    except Exception as e:
        logger.error(f"❌ Error al crear archivo de link: {e}", exc_info=True)
        return None


def main():
    """Función principal que coordina todo el proceso."""
    logger.info("=" * 80)
    logger.info("🚀 Iniciando YouTube to Google Drive Automation")
    logger.info("=" * 80)

    # Validar dependencias
    logger.info("🔍 Validando dependencias del sistema...")
    if not validate_ffmpeg():
        logger.error("❌ FFmpeg es requerido. Instálalo desde: https://ffmpeg.org/download.html")
        return

    if not validate_credentials(CREDENTIALS_FILE):
        return

    if not validate_config_file(LINKS_CONFIG_FILE):
        return

    # Cargar configuración
    try:
        with open(LINKS_CONFIG_FILE, 'r') as f:
            config = json.load(f)
        parent_folder_id = config.get("parent_folder_id")
        video_urls = config.get("video_urls", [])

        if not parent_folder_id:
            logger.error(f"❌ 'parent_folder_id' no encontrado en {LINKS_CONFIG_FILE}")
            return
        if not video_urls:
            logger.info(f"ℹ️ No se encontraron URLs en {LINKS_CONFIG_FILE}")
            return

        logger.info(f"✅ Configuración cargada: {len(video_urls)} video(s) a procesar")
    except FileNotFoundError:
        logger.error(f"❌ Archivo no encontrado: {LINKS_CONFIG_FILE}")
        return
    except json.JSONDecodeError:
        logger.error(f"❌ {LINKS_CONFIG_FILE} no es un JSON válido")
        return

    # Inicializar componentes
    downloader = YouTubeDownloader(TEMP_DOWNLOAD_DIR)
    transcriber = AudioTranscriber(WHISPER_MODEL_DEFAULT)
    drive_manager = DriveManager()

    if not drive_manager.service:
        return

    ensure_directory_exists(TEMP_DOWNLOAD_DIR)

    # Procesar cada video
    for idx, video_url in enumerate(video_urls, 1):
        logger.info("=" * 80)
        logger.info(f"📹 Procesando video {idx}/{len(video_urls)}: {video_url}")
        logger.info("=" * 80)

        # Obtener información del video
        video_info = downloader.get_video_info(video_url)
        if not video_info:
            logger.warning(f"⚠️ Saltando video por falta de información: {video_url}")
            continue

        # Crear carpeta en Drive
        folder_name = FOLDER_NAME_FORMAT.format(
            date=video_info.upload_date,
            title=video_info.safe_title
        )
        drive_folder_id = drive_manager.create_folder(folder_name, parent_folder_id)
        if not drive_folder_id:
            logger.warning(f"⚠️ Saltando video por error al crear carpeta en Drive")
            continue

        # Descargar video
        video_file = downloader.download_video(video_info)
        if video_file and video_file.exists():
            try:
                drive_manager.upload_if_not_exists(video_file, drive_folder_id)
            except Exception as e:
                logger.error(f"❌ Error al subir video: {e}", exc_info=True)
            finally:
                safe_remove_file(video_file.path)

        # Descargar audio
        audio_file = downloader.download_audio(video_info)
        if audio_file and audio_file.exists():
            # Transcribir
            txt_filename = TRANSCRIPTION_FILE_FORMAT.format(
                date=video_info.upload_date,
                title=video_info.safe_title
            )
            local_txt_path = os.path.join(TEMP_DOWNLOAD_DIR, txt_filename)

            transcription_result = transcriber.transcribe(
                audio_file,
                language="en",  # Mantener en inglés
                output_path=local_txt_path
            )

            # Subir audio
            try:
                drive_manager.upload_if_not_exists(audio_file, drive_folder_id)
            except Exception as e:
                logger.error(f"❌ Error al subir audio: {e}", exc_info=True)
            finally:
                safe_remove_file(audio_file.path)

            # Subir transcripción
            if transcription_result and transcription_result.output_path:
                transcription_file = MediaFile(
                    path=transcription_result.output_path,
                    filename=os.path.basename(transcription_result.output_path),
                    file_type='transcription'
                )
                try:
                    drive_manager.upload_if_not_exists(transcription_file, drive_folder_id)
                except Exception as e:
                    logger.error(f"❌ Error al subir transcripción: {e}", exc_info=True)
                finally:
                    safe_remove_file(transcription_file.path)

        # Crear y subir archivo de link
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
                logger.error(f"❌ Error al subir link: {e}", exc_info=True)
            finally:
                safe_remove_file(link_file.path)

        logger.info(f"✅ Video procesado completamente: {folder_name}")

    # Limpiar
    clean_temp_directory(TEMP_DOWNLOAD_DIR)

    logger.info("=" * 80)
    logger.info("✅ Procesamiento completado exitosamente")
    logger.info("=" * 80)


if __name__ == '__main__':
    main()
