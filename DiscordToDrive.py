import yt_dlp
import os
import json
import datetime
import pickle
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from faster_whisper import WhisperModel  # Transcripción con faster-whisper

# Módulos propios
from logger_config import setup_logger
from config import *
from utils import (
    retry_on_failure,
    validate_ffmpeg,
    validate_credentials,
    validate_config_file,
    sanitize_filename,
    ensure_directory_exists,
    safe_remove_file,
    clean_temp_directory
)

# Configurar logger
logger = setup_logger(__name__)

def build_yt_opts(
    outtmpl=None,
    want_video=False,
    want_audio=False,
    prefer_mp4=True,
    quiet=True
):
    """
    Construye opciones robustas para yt-dlp evitando SABR y saltando players web problemáticos.

    Args:
        outtmpl (str, optional): Template de nombre de salida
        want_video (bool): True para descargar video
        want_audio (bool): True para descargar solo audio
        prefer_mp4 (bool): Preferir formato MP4 para video
        quiet (bool): Modo silencioso

    Returns:
        dict: Diccionario de opciones para yt-dlp

    Features:
        - Fuerza clients: android/ios/tv
        - Ajusta headers tipo Android
        - Reintentos agresivos
        - Evita errores SABR
    """
    extractor_args = {
        "youtube": {
            "player_skip": YT_DLP_PLAYER_SKIP,
            "player_client": YT_DLP_PLAYER_CLIENT,
        }
    }

    http_headers = {
        "User-Agent": YT_DLP_USER_AGENT,
        "Accept-Language": YT_DLP_ACCEPT_LANGUAGE,
    }

    ydl_opts = {
        "quiet": quiet,
        "nocheckcertificate": False,
        "extractor_args": extractor_args,
        "http_headers": http_headers,
        "retries": YT_DLP_RETRIES,
        "fragment_retries": YT_DLP_FRAGMENT_RETRIES,
        "concurrent_fragment_downloads": 1,
        "noprogress": quiet,
        "socket_timeout": YT_DLP_SOCKET_TIMEOUT,
        "force_ipv4": True,
    }

    if outtmpl:
        ydl_opts["outtmpl"] = outtmpl

    if want_video:
        if prefer_mp4:
            ydl_opts["format"] = "bv*[vcodec*=avc1]+ba[acodec*=mp4a]/b[ext=mp4]/b"
            ydl_opts["merge_output_format"] = "mp4"
        else:
            ydl_opts["format"] = "bv*+ba/b"
    elif want_audio:
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": YT_DLP_AUDIO_CODEC,
            "preferredquality": YT_DLP_AUDIO_QUALITY,
        }]

    return ydl_opts


def get_drive_service():
    """
    Autentica y retorna un objeto de servicio de Google Drive API.

    Returns:
        Resource: Objeto de servicio de Google Drive API o None si falla

    Raises:
        Exception: Si hay un error al crear el servicio
    """
    creds = None
    if os.path.exists(TOKEN_PICKLE):
        with open(TOKEN_PICKLE, 'rb') as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refrescando credenciales de Google Drive...")
            creds.refresh(Request())
        else:
            logger.info("Iniciando flujo de autenticación de Google Drive...")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open(TOKEN_PICKLE, 'wb') as token:
            pickle.dump(creds, token)
            logger.info("Credenciales guardadas en token.pickle")

    try:
        service = build('drive', 'v3', credentials=creds)
        logger.info("✅ Servicio de Google Drive API creado exitosamente.")
        return service
    except Exception as e:
        logger.error(f"❌ Error al crear servicio de Google Drive: {e}", exc_info=True)
        return None

def get_video_info(video_url):
    """
    Obtiene título y fecha de publicación de un video de YouTube usando yt-dlp.

    Args:
        video_url (str): URL del video de YouTube

    Returns:
        tuple: (título, fecha_publicación) o (None, None) si falla
    """
    ydl_opts = build_yt_opts(quiet=True)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            title = info.get("title", "Unknown Title")

            # fecha: upload_date (YYYYMMDD) o release_timestamp/timestamp → YYYY-MM-DD
            upload_date_str = info.get("upload_date")
            if upload_date_str:
                upload_date = datetime.datetime.strptime(upload_date_str, "%Y%m%d").strftime(DATE_FORMAT)
            else:
                ts = info.get("release_timestamp") or info.get("timestamp")
                if ts:
                    upload_date = datetime.datetime.utcfromtimestamp(int(ts)).strftime(DATE_FORMAT)
                else:
                    # Último recurso: hoy
                    upload_date = datetime.datetime.now().strftime(DATE_FORMAT)
                    logger.warning(f"No se encontró fecha de publicación para {video_url}, usando fecha actual")

            logger.info(f"📹 Video info: '{title}' ({upload_date})")
            return title, upload_date
    except Exception as e:
        logger.error(f"❌ Error al obtener información del video {video_url}: {e}", exc_info=True)
        return None, None

def create_drive_folder(service, folder_name, parent_folder_id):
    """
    Crea una carpeta en Google Drive y retorna su ID.

    Args:
        service: Servicio de Google Drive API
        folder_name (str): Nombre de la carpeta a crear
        parent_folder_id (str): ID de la carpeta padre

    Returns:
        str: ID de la carpeta creada o None si falla
    """
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_folder_id]
    }
    try:
        # Add supportsAllDrives=True to support shared drives
        folder = service.files().create(body=file_metadata, fields='id', supportsAllDrives=True).execute()
        folder_id = folder.get('id')
        logger.info(f"📁 Carpeta '{folder_name}' creada con ID: {folder_id}")
        return folder_id
    except Exception as e:
        logger.error(f"❌ Error al crear carpeta '{folder_name}': {e}", exc_info=True)
        return None

@retry_on_failure(max_retries=DRIVE_UPLOAD_MAX_RETRIES, delay=DRIVE_UPLOAD_RETRY_DELAY)
def upload_file_to_drive(service, file_path, folder_id):
    """
    Sube un archivo a una carpeta específica de Google Drive con reintentos automáticos.

    Args:
        service: Servicio de Google Drive API
        file_path (str): Ruta del archivo a subir
        folder_id (str): ID de la carpeta destino en Drive

    Returns:
        str: ID del archivo subido o None si falla

    Note:
        Esta función tiene reintentos automáticos configurados vía decorador.
    """
    file_metadata = {
        'name': os.path.basename(file_path),
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, resumable=True)

    # Add supportsAllDrives=True to support shared drives
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id',
        supportsAllDrives=True
    ).execute()

    file_id = file.get('id')
    logger.info(f"⬆️ Archivo '{os.path.basename(file_path)}' subido con ID: {file_id}")
    return file_id

def check_file_exists_in_drive(service, file_name, folder_id):
    """
    Verifica si un archivo con el nombre dado ya existe en la carpeta especificada.

    Args:
        service: Servicio de Google Drive API
        file_name (str): Nombre del archivo a buscar
        folder_id (str): ID de la carpeta donde buscar

    Returns:
        tuple: (exists: bool, file_id: str or None)
    """
    try:
        # Search for files with the same name in the specified folder
        query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
        response = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)',
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()

        files = response.get('files', [])
        if files:
            file_id = files[0].get('id')
            logger.info(f"ℹ️ Archivo '{file_name}' ya existe en Drive con ID: {file_id}")
            return True, file_id
        return False, None
    except Exception as e:
        logger.warning(f"⚠️ Error al verificar si existe '{file_name}': {e}")
        # If there's an error checking, we'll assume the file doesn't exist
        # and try to upload it anyway
        return False, None

def download_video(video_url, save_path_base, upload_date):
    """
    Descarga video como MP4 evitando SABR y priorizando codecs AVC1+MP4A.

    Args:
        video_url (str): URL del video de YouTube
        save_path_base (str): Ruta base para guardar el archivo
        upload_date (str): Fecha de publicación en formato YYYY-MM-DD

    Returns:
        str: Ruta del archivo descargado o None si falla
    """
    filename_base = f"{upload_date} - {os.path.basename(save_path_base)}"
    output_template = os.path.join(os.path.dirname(save_path_base), f"{filename_base}.%(ext)s")

    ydl_opts = build_yt_opts(
        outtmpl=output_template,
        want_video=True,
        prefer_mp4=True,
        quiet=True
    )

    downloaded_path = None
    try:
        logger.info(f"⬇️ Descargando video: {video_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)

            base_path_with_date = os.path.join(os.path.dirname(save_path_base), filename_base)

            for ext in ["mp4", "mkv", "webm", "avi", "mov"]:
                potential_path = f"{base_path_with_date}.{ext}"
                if os.path.exists(potential_path):
                    downloaded_path = potential_path
                    if ext != "mp4":
                        new_path = f"{base_path_with_date}.mp4"
                        os.rename(potential_path, new_path)
                        downloaded_path = new_path
                        logger.info(f"ℹ️ Video renombrado a {os.path.basename(downloaded_path)}")
                    break

            if not downloaded_path:
                original_base_path = ydl.prepare_filename(info).rsplit(".", 1)[0]
                for ext in ["mp4", "mkv", "webm", "avi", "mov"]:
                    potential_path = f"{original_base_path}.{ext}"
                    if os.path.exists(potential_path):
                        new_path = f"{base_path_with_date}.mp4"
                        os.rename(potential_path, new_path)
                        downloaded_path = new_path
                        logger.info(f"ℹ️ Video renombrado a {os.path.basename(downloaded_path)}")
                        break

            if downloaded_path:
                logger.info(f"✅ Video descargado: {os.path.basename(downloaded_path)}")
            else:
                logger.warning(f"⚠️ No se pudo encontrar archivo de video descargado para {video_url}")

    except Exception as e:
        logger.error(f"❌ Error al descargar video {video_url}: {e}", exc_info=True)

    return downloaded_path

def download_audio(video_url, save_path_base, upload_date):
    """
    Descarga audio como MP3.

    Args:
        video_url (str): URL del video de YouTube
        save_path_base (str): Ruta base para guardar el archivo
        upload_date (str): Fecha de publicación en formato YYYY-MM-DD

    Returns:
        str: Ruta del archivo descargado o None si falla
    """
    filename_base = f"{upload_date} - {os.path.basename(save_path_base)}"
    output_template = os.path.join(os.path.dirname(save_path_base), f"{filename_base}.%(ext)s")

    ydl_opts = build_yt_opts(
        outtmpl=output_template,
        want_audio=True,
        quiet=True
    )

    downloaded_path = None
    try:
        logger.info(f"🎵 Descargando audio: {video_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)

            base_path_with_date = os.path.join(os.path.dirname(save_path_base), filename_base)
            potential_path = f"{base_path_with_date}.mp3"

            if os.path.exists(potential_path):
                downloaded_path = potential_path
                logger.info(f"✅ Audio descargado: {os.path.basename(downloaded_path)}")
            else:
                original_base_path = ydl.prepare_filename(info).rsplit(".", 1)[0]
                potential_path_original_ext = f"{original_base_path}.mp3"
                if os.path.exists(potential_path_original_ext):
                    new_path = f"{base_path_with_date}.mp3"
                    os.rename(potential_path_original_ext, new_path)
                    downloaded_path = new_path
                    logger.info(f"ℹ️ Audio renombrado a {os.path.basename(downloaded_path)}")
                else:
                    logger.warning(f"⚠️ No se pudo encontrar archivo de audio descargado para {video_url}")

    except Exception as e:
        logger.error(f"❌ Error al descargar audio {video_url}: {e}", exc_info=True)

    return downloaded_path

def transcribe_audio(model, audio_path, output_txt_path):
    """
    Transcribe un archivo de audio usando faster-whisper y guarda el resultado.

    Args:
        model: Modelo de WhisperModel
        audio_path (str): Ruta del archivo de audio a transcribir
        output_txt_path (str): Ruta donde guardar la transcripción

    Returns:
        str: Ruta del archivo de transcripción o None si falla
    """
    try:
        logger.info(f"🎤 Iniciando transcripción: {os.path.basename(audio_path)}")

        target_language = "en"  # Mantener en inglés
        logger.info(f"ℹ️ Procesando audio. Optimizando para evitar repeticiones...")

        # faster-whisper usa segments iterator en lugar de un dict result
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
            # Mostrar cada segmento en vivo
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

def create_link_file(video_url, output_path):
    """
    Crea un archivo de texto conteniendo la URL de YouTube.

    Args:
        video_url (str): URL del video de YouTube
        output_path (str): Ruta donde guardar el archivo

    Returns:
        str: Ruta del archivo creado o None si falla
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"YouTube URL: {video_url}\n")
            f.write(f"Este archivo fue generado automáticamente el {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"🔗 Archivo de link creado: {os.path.basename(output_path)}")
        return output_path
    except Exception as e:
        logger.error(f"❌ Error al crear archivo de link: {e}", exc_info=True)
        return None

def main():
    """
    Función principal que coordina el proceso de descarga, transcripción y subida a Drive.
    """
    logger.info("=" * 80)
    logger.info("🚀 Iniciando YouTube to Google Drive Automation")
    logger.info("=" * 80)

    # Validar dependencias
    logger.info("🔍 Validando dependencias del sistema...")
    if not validate_ffmpeg():
        logger.error("❌ FFmpeg es requerido. Instalalo desde: https://ffmpeg.org/download.html")
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

    # Get Google Drive service
    drive_service = get_drive_service()
    if not drive_service:
        return

    # --- Whisper Model Loading ---
    logger.info(f"ℹ️ Cargando modelo Whisper '{WHISPER_MODEL_DEFAULT}' en {WHISPER_DEVICE.upper()}...")
    if WHISPER_DEVICE == "cpu":
        logger.info("ℹ️ Para usar GPU: export WHISPER_DEVICE=cuda")

    whisper_model = WhisperModel(
        WHISPER_MODEL_DEFAULT,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE
    )
    logger.info(f"✅ Modelo Whisper '{WHISPER_MODEL_DEFAULT}' cargado en {WHISPER_DEVICE.upper()}.")

    # Create a temporary directory for downloads
    ensure_directory_exists(TEMP_DOWNLOAD_DIR)

    # Process each video URL
    for idx, video_url in enumerate(video_urls, 1):
        logger.info("=" * 80)
        logger.info(f"📹 Procesando video {idx}/{len(video_urls)}: {video_url}")
        logger.info("=" * 80)

        title, upload_date = get_video_info(video_url)

        if not title:
            logger.warning(f"⚠️ Saltando video por falta de título: {video_url}")
            continue

        # Sanitize title for file/folder names
        safe_title = sanitize_filename(title)
        # Folder name format: Date - Title
        folder_name = FOLDER_NAME_FORMAT.format(date=upload_date, title=safe_title)

        # Create folder in Google Drive
        drive_folder_id = create_drive_folder(drive_service, folder_name, parent_folder_id)
        if not drive_folder_id:
            logger.warning(f"⚠️ Saltando video por error al crear carpeta en Drive: {video_url}")
            continue

        # Define local file base path (used by download functions to construct full name)
        local_base_path_without_date = os.path.join(TEMP_DOWNLOAD_DIR, safe_title)

        # Download video (pass upload_date)
        video_path = download_video(video_url, local_base_path_without_date, upload_date)
        if video_path and os.path.exists(video_path):
            # Check if video already exists in Drive
            video_filename = os.path.basename(video_path)
            video_exists, _ = check_file_exists_in_drive(drive_service, video_filename, drive_folder_id)

            if not video_exists:
                try:
                    upload_file_to_drive(drive_service, video_path, drive_folder_id)
                except Exception as e:
                    logger.error(f"❌ Error al subir video: {e}", exc_info=True)
            else:
                logger.info(f"⏭️ Archivo de video ya existe en Drive, saltando: {video_filename}")

            # Delete local copy regardless
            safe_remove_file(video_path)
        else:
            logger.warning(f"⚠️ Descarga de video falló o archivo no encontrado para {video_url}, saltando subida.")

        # Download audio (pass upload_date)
        audio_path = download_audio(video_url, local_base_path_without_date, upload_date)
        transcription_path = None  # Initialize transcription path

        if audio_path and os.path.exists(audio_path):
            # --- Transcription Step ---
            txt_filename = TRANSCRIPTION_FILE_FORMAT.format(date=upload_date, title=safe_title)
            local_txt_path = os.path.join(TEMP_DOWNLOAD_DIR, txt_filename)

            # Transcribe the downloaded audio
            transcription_path = transcribe_audio(whisper_model, audio_path, local_txt_path)
            # --- End Transcription Step ---

            # Upload audio file
            audio_filename = os.path.basename(audio_path)
            audio_exists, _ = check_file_exists_in_drive(drive_service, audio_filename, drive_folder_id)

            if not audio_exists:
                try:
                    upload_file_to_drive(drive_service, audio_path, drive_folder_id)
                except Exception as e:
                    logger.error(f"❌ Error al subir audio: {e}", exc_info=True)
            else:
                logger.info(f"⏭️ Archivo de audio ya existe en Drive, saltando: {audio_filename}")

            # Delete local copy
            safe_remove_file(audio_path)
        else:
            logger.warning(f"⚠️ Descarga de audio falló o archivo no encontrado para {video_url}, saltando subida y transcripción.")

        # Upload transcription file if it exists
        if transcription_path and os.path.exists(transcription_path):
            # Check if transcription already exists in Drive
            transcription_filename = os.path.basename(transcription_path)
            transcription_exists, _ = check_file_exists_in_drive(drive_service, transcription_filename, drive_folder_id)

            if not transcription_exists:
                try:
                    upload_file_to_drive(drive_service, transcription_path, drive_folder_id)
                except Exception as e:
                    logger.error(f"❌ Error al subir transcripción: {e}", exc_info=True)
            else:
                logger.info(f"⏭️ Archivo de transcripción ya existe en Drive, saltando: {transcription_filename}")

            # Delete local copy
            safe_remove_file(transcription_path)
        elif audio_path:  # Only warn if audio existed but transcription failed
            logger.warning(f"⚠️ Transcripción falló para {video_url}, saltando subida.")

        # Create and upload link file
        link_filename = LINK_FILE_FORMAT.format(date=upload_date, title=safe_title)
        local_link_path = os.path.join(TEMP_DOWNLOAD_DIR, link_filename)
        link_file_path = create_link_file(video_url, local_link_path)

        if link_file_path and os.path.exists(link_file_path):
            # Check if link file already exists in Drive
            link_file_exists, _ = check_file_exists_in_drive(drive_service, os.path.basename(link_file_path), drive_folder_id)

            if not link_file_exists:
                try:
                    upload_file_to_drive(drive_service, link_file_path, drive_folder_id)
                except Exception as e:
                    logger.error(f"❌ Error al subir archivo de link: {e}", exc_info=True)
            else:
                logger.info(f"⏭️ Archivo de link ya existe en Drive, saltando: {os.path.basename(link_file_path)}")

            # Delete local copy
            safe_remove_file(link_file_path)

        logger.info(f"✅ Video procesado completamente: {folder_name}")

    # Clean up temporary directory if empty
    clean_temp_directory(TEMP_DOWNLOAD_DIR)

    logger.info("=" * 80)
    logger.info("✅ Procesamiento completado exitosamente")
    logger.info("=" * 80)

if __name__ == '__main__':
    main()
