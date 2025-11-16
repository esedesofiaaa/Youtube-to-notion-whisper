import os
import datetime
import re
import subprocess
from faster_whisper import WhisperModel
import argparse

# Módulos propios
from logger_config import setup_logger
from config import *
from utils import (
    validate_ffmpeg,
    sanitize_filename,
    ensure_directory_exists,
    is_audio_file,
    is_video_file
)

# Configurar logger
logger = setup_logger(__name__)

def get_media_info(media_path):
    """
    Obtiene título y fecha del nombre de archivo de un medio.

    Args:
        media_path (str): Ruta al archivo de medio

    Returns:
        tuple: (título, fecha) o (None, None) si falla

    Note:
        Formato esperado de archivo: "YYYY-MM-DD - Título.ext"
    """
    try:
        filename = os.path.basename(media_path)
        # Extract date and title using regex
        match = re.match(r'(\d{4}-\d{2}-\d{2})\s*-\s*(.+)\.(\w+)', filename)

        if match:
            date = match.group(1)
            title = match.group(2)
            logger.info(f"📄 Info extraída de {filename}: Fecha={date}, Título={title}")
            return title, date
        else:
            # If filename doesn't match expected format, use file modification date
            mod_time = os.path.getmtime(media_path)
            date = datetime.datetime.fromtimestamp(mod_time).strftime(DATE_FORMAT)
            title = os.path.splitext(filename)[0]
            logger.warning(f"⚠️ No se pudo parsear formato del nombre. Usando: Fecha={date}, Título={title}")
            return title, date
    except Exception as e:
        logger.error(f"❌ Error al obtener info de medio desde {media_path}: {e}", exc_info=True)
        return None, None

def extract_audio_from_video(video_path, output_dir):
    """
    Extrae audio MP3 de un archivo de video usando FFmpeg.

    Args:
        video_path (str): Ruta al archivo de video
        output_dir (str): Directorio donde guardar el audio extraído

    Returns:
        str: Ruta al archivo de audio extraído o None si falla
    """
    filename = os.path.basename(video_path)
    base_name = os.path.splitext(filename)[0]
    output_path = os.path.join(output_dir, f"{base_name}.mp3")

    try:
        logger.info(f"ℹ️ Extrayendo audio con FFmpeg desde: {filename}")
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', video_path,
            '-q:a', FFMPEG_AUDIO_QUALITY,
            '-map', 'a',
            '-id3v2_version', FFMPEG_ID3_VERSION,
            output_path,
            '-y'
        ]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if os.path.exists(output_path):
            logger.info(f"✅ Audio extraído con FFmpeg: {os.path.basename(output_path)}")
            return output_path
        else:
            logger.warning(f"⚠️ FFmpeg no generó el archivo de salida esperado: {output_path}")
            return None
    except Exception as e:
        logger.error(f"❌ Error al extraer audio con FFmpeg: {e}", exc_info=True)
        return None

def transcribe_audio(model, audio_path, output_txt_path, language=None):
    """
    Transcribe un archivo de audio usando faster-whisper y guarda el resultado.

    Args:
        model: Modelo de WhisperModel a usar
        audio_path (str): Ruta al archivo de audio
        output_txt_path (str): Ruta donde guardar la transcripción
        language (str, optional): Código ISO de idioma (ej. 'es', 'en', 'fr', None para auto-detección)

    Returns:
        str: Ruta al archivo de transcripción o None si falla
    """
    try:
        logger.info(f"🎤 Iniciando transcripción: {os.path.basename(audio_path)}")

        target_language = language
        if target_language:
            logger.info(f"ℹ️ Idioma seleccionado manualmente: {target_language}")
        else:
            logger.info("ℹ️ Detección automática de idioma activada")

        logger.info(f"ℹ️ Procesando audio. Optimizando para evitar repeticiones...")

        # faster-whisper usa segments iterator
        segments, info = model.transcribe(
            audio_path,
            language=target_language,
            **WHISPER_PARAMS
        )

        logger.info(f"ℹ️ Idioma detectado: {info.language} (probabilidad: {info.language_probability:.2f})")
        logger.info("=" * 80)
        logger.info("📝 TRANSCRIPCIÓN EN VIVO:")
        logger.info("=" * 80)

        # Recolectar todos los segmentos mostrando en tiempo real
        transcription_text = ""
        for segment in segments:
            logger.info(segment.text)
            transcription_text += segment.text

        logger.info("=" * 80)

        with open(output_txt_path, 'w', encoding='utf-8') as f:
            f.write(transcription_text.strip())
        logger.info(f"✅ Transcripción guardada: {os.path.basename(output_txt_path)}")
        return output_txt_path
    except Exception as e:
        logger.error(f"❌ Error durante transcripción de {os.path.basename(audio_path)}: {e}", exc_info=True)
        return None

def main():
    """
    Función principal para transcribir archivos de audio/video locales.
    """
    # Configurar parser de argumentos de línea de comandos
    parser = argparse.ArgumentParser(description='Transcribe audio and video files to text')
    parser.add_argument('--lang', type=str, help='Language code (e.g. es, en, fr). Leave empty for auto-detection.')
    parser.add_argument('--input', type=str, default=INPUT_DIR, help='Input directory containing audio/video files')
    parser.add_argument('--output', type=str, default=OUTPUT_DIR, help='Output directory for transcriptions')

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("🎙️ Iniciando Local Transcriber")
    logger.info("=" * 80)

    # Directorios de trabajo
    input_dir = args.input
    output_dir = args.output
    temp_dir = TEMP_DIR

    # Configuración de idioma
    target_language = args.lang

    if target_language:
        logger.info(f"ℹ️ Idioma seleccionado: {target_language}")
    else:
        logger.info("ℹ️ Se utilizará detección automática de idioma")

    # Crear directorios si no existen
    for directory in [input_dir, output_dir, temp_dir]:
        ensure_directory_exists(directory)

    # Verificar dependencias
    logger.info("🔍 Verificando dependencias...")
    if not validate_ffmpeg():
        logger.error("❌ FFmpeg no está disponible. Necesario para procesar videos.")
        logger.error("   Instalalo desde: https://ffmpeg.org/download.html")
        return

    # --- Carga del modelo Whisper ---
    logger.info(f"ℹ️ Cargando modelo Whisper '{WHISPER_MODEL_LOCAL}' en {WHISPER_DEVICE.upper()}...")
    if WHISPER_DEVICE == "cpu":
        logger.info("ℹ️ Para usar GPU: export WHISPER_DEVICE=cuda")

    whisper_model = WhisperModel(
        WHISPER_MODEL_LOCAL,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE
    )
    logger.info(f"✅ Modelo Whisper '{WHISPER_MODEL_LOCAL}' cargado en {WHISPER_DEVICE.upper()}.")

    # Obtener archivos de entrada (audio y video)
    input_files = [f for f in os.listdir(input_dir)
                  if is_audio_file(os.path.join(input_dir, f)) or is_video_file(os.path.join(input_dir, f))]

    if not input_files:
        logger.error(f"❌ No se encontraron archivos de audio o video en '{input_dir}'.")
        return

    logger.info(f"✅ Se encontraron {len(input_files)} archivo(s) para procesar.")

    # Procesar cada archivo
    for idx, filename in enumerate(input_files, 1):
        file_path = os.path.join(input_dir, filename)
        logger.info("=" * 80)
        logger.info(f"📄 Procesando archivo {idx}/{len(input_files)}: {filename}")
        logger.info("=" * 80)

        # Obtener información del archivo
        title, date = get_media_info(file_path)
        if not title or not date:
            logger.warning(f"⚠️ Omitiendo archivo por falta de información: {filename}")
            continue

        # Sanitizar título para usar en nombres de archivo
        safe_title = sanitize_filename(title)

        # Manejar la transcripción
        audio_for_transcription = None

        # Si es un video, extraer el audio primero
        if is_video_file(file_path):
            logger.info("ℹ️ Detectado archivo de video, extrayendo audio...")
            audio_path = extract_audio_from_video(file_path, temp_dir)
            audio_for_transcription = audio_path

            if not audio_path or not os.path.exists(audio_path):
                logger.error(f"❌ No se pudo extraer el audio del video: {filename}")
                continue
        elif is_audio_file(file_path):
            logger.info("ℹ️ Detectado archivo de audio, usando directamente...")
            audio_for_transcription = file_path
        else:
            logger.error(f"❌ Tipo de archivo no soportado: {filename}")
            continue

        # Preparar ruta para la transcripción
        txt_filename = TRANSCRIPTION_FILE_FORMAT.format(date=date, title=safe_title)
        output_txt_path = os.path.join(output_dir, txt_filename)

        # Transcribir el audio
        transcription_path = transcribe_audio(whisper_model, audio_for_transcription, output_txt_path, language=target_language)

        # Si se generó audio temporal de un video, guardarlo
        if is_video_file(file_path) and audio_for_transcription and os.path.exists(audio_for_transcription):
            audio_filename = os.path.basename(audio_for_transcription)
            final_audio_path = os.path.join(output_dir, audio_filename)

            try:
                import shutil
                shutil.copy2(audio_for_transcription, final_audio_path)
                logger.info(f"✅ Audio guardado en: {os.path.basename(final_audio_path)}")

                # Eliminar archivo temporal
                os.remove(audio_for_transcription)
                logger.info(f"🗑️ Eliminado archivo temporal: {os.path.basename(audio_for_transcription)}")
            except Exception as e:
                logger.warning(f"⚠️ Error al gestionar el archivo de audio: {e}")

        logger.info(f"✅ Procesamiento completo para: {filename}")

    # Limpiar directorio temporal si está vacío
    from utils import clean_temp_directory
    clean_temp_directory(temp_dir)

    logger.info("=" * 80)
    logger.info("✅ Procesamiento completo de todos los archivos")
    logger.info("=" * 80)

if __name__ == '__main__':
    main()
