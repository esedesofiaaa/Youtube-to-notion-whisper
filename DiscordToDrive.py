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

def build_yt_opts(
    outtmpl=None,
    want_video=False,
    want_audio=False,
    prefer_mp4=True,
    quiet=True
):
    """
    Construye opciones robustas para yt-dlp evitando SABR y saltando players web problemáticos.
    - Fuerza clients: android/ios/tv
    - Ajusta headers tipo Android
    - Retrys agresivos
    - Cookies: usa cookies.txt si existe; si no, intenta leer del navegador (Chrome)
    """
    extractor_args = {
        "youtube": {
            # evita clientes web con SABR
            "player_skip": ["web_safari", "web"],
            # orden de preferencia de clientes
            "player_client": ["android", "ios", "tv"],
            # (opcional) si el DASH molesta en tu red, puedes descomentar:
            # "include_dash_manifest": ["True"],
            # "include_hls_manifest": ["True"],
        }
    }

    http_headers = {
        # UA Android para reforzar client
        "User-Agent": "com.google.android.youtube/19.18.35 (Linux; U; Android 13)",
        "Accept-Language": "en-US,en;q=0.9",
    }

    ydl_opts = {
        "quiet": quiet,
        "nocheckcertificate": False,  # Mejora seguridad; cámbialo a True solo si tu red rompe SSL
        "extractor_args": extractor_args,
        "http_headers": http_headers,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 1,
        "noprogress": quiet,
    }

    ydl_opts.update({
        "socket_timeout": 20,
        "force_ipv4": True,  # a veces IPv6 se cuelga
    })

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
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    return ydl_opts

# Google Drive API setup
SCOPES = ['https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_PICKLE = 'token.pickle'

def get_drive_service():
    """Authenticates and returns a Google Drive service object."""
    creds = None
    if os.path.exists(TOKEN_PICKLE):
        with open(TOKEN_PICKLE, 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_PICKLE, 'wb') as token:
            pickle.dump(creds, token)
    try:
        service = build('drive', 'v3', credentials=creds)
        print("Google Drive API service created successfully.")
        return service
    except Exception as e:
        print(f"❌ Error creating Google Drive service: {e}")
        return None

def get_video_info(video_url):
    """Fetches video title and upload date using yt-dlp con clientes sin SABR."""
    ydl_opts = build_yt_opts(quiet=True)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            title = info.get("title", "Unknown Title")

            # fecha: upload_date (YYYYMMDD) o release_timestamp/timestamp → YYYY-MM-DD
            upload_date_str = info.get("upload_date")
            if upload_date_str:
                upload_date = datetime.datetime.strptime(upload_date_str, "%Y%m%d").strftime("%Y-%m-%d")
            else:
                ts = info.get("release_timestamp") or info.get("timestamp")
                if ts:
                    upload_date = datetime.datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d")
                else:
                    # Último recurso: hoy (evitas saltarte el video)
                    upload_date = datetime.datetime.now().strftime("%Y-%m-%d")

            return title, upload_date
    except Exception as e:
        print(f"❌ Error fetching video info for {video_url}: {e}")
        return None, None

def create_drive_folder(service, folder_name, parent_folder_id):
    """Creates a folder in Google Drive and returns its ID."""
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_folder_id]
    }
    try:
        # Add supportsAllDrives=True to support shared drives
        folder = service.files().create(body=file_metadata, fields='id', supportsAllDrives=True).execute()
        print(f"📁 Folder '{folder_name}' created with ID: {folder.get('id')}")
        return folder.get('id')
    except Exception as e:
        print(f"❌ Error creating folder '{folder_name}': {e}")
        return None

def upload_file_to_drive(service, file_path, folder_id):
    """Uploads a file to a specific Google Drive folder."""
    file_metadata = {
        'name': os.path.basename(file_path),
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, resumable=True)
    try:
        # Add supportsAllDrives=True to support shared drives
        file = service.files().create(body=file_metadata,
                                      media_body=media,
                                      fields='id',
                                      supportsAllDrives=True).execute()
        print(f"⬆️ File '{os.path.basename(file_path)}' uploaded with ID: {file.get('id')}")
        return file.get('id')
    except Exception as e:
        print(f"❌ Error uploading file '{os.path.basename(file_path)}': {e}")
        return None

def check_file_exists_in_drive(service, file_name, folder_id):
    """Checks if a file with the given name already exists in the specified folder."""
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
            print(f"ℹ️ File '{file_name}' already exists in Drive with ID: {files[0].get('id')}")
            return True, files[0].get('id')
        return False, None
    except Exception as e:
        print(f"⚠️ Error checking if file '{file_name}' exists: {e}")
        # If there's an error checking, we'll assume the file doesn't exist
        # and try to upload it anyway
        return False, None

def download_video(video_url, save_path_base, upload_date):
    """Downloads video como MP4 evitando SABR y priorizando AVC1+MP4A."""
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
                        print(f"ℹ️ Renamed video to {os.path.basename(downloaded_path)}")
                    break

            if not downloaded_path:
                original_base_path = ydl.prepare_filename(info).rsplit(".", 1)[0]
                for ext in ["mp4", "mkv", "webm", "avi", "mov"]:
                    potential_path = f"{original_base_path}.{ext}"
                    if os.path.exists(potential_path):
                        new_path = f"{base_path_with_date}.mp4"
                        os.rename(potential_path, new_path)
                        downloaded_path = new_path
                        print(f"ℹ️ Renamed video to {os.path.basename(downloaded_path)}")
                        break

            if downloaded_path:
                print(f"✅ Video downloaded: {os.path.basename(downloaded_path)}")
            else:
                print(f"⚠️ Could not find downloaded video file for {video_url}")

    except Exception as e:
        print(f"❌ Error downloading video for {video_url}: {e}")

    return downloaded_path

def download_audio(video_url, save_path_base, upload_date):
    """Downloads audio como MP3."""
    filename_base = f"{upload_date} - {os.path.basename(save_path_base)}"
    output_template = os.path.join(os.path.dirname(save_path_base), f"{filename_base}.%(ext)s")

    ydl_opts = build_yt_opts(
        outtmpl=output_template,
        want_audio=True,
        quiet=True
    )

    downloaded_path = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)

            base_path_with_date = os.path.join(os.path.dirname(save_path_base), filename_base)
            potential_path = f"{base_path_with_date}.mp3"

            if os.path.exists(potential_path):
                downloaded_path = potential_path
                print(f"✅ Audio downloaded: {os.path.basename(downloaded_path)}")
            else:
                original_base_path = ydl.prepare_filename(info).rsplit(".", 1)[0]
                potential_path_original_ext = f"{original_base_path}.mp3"
                if os.path.exists(potential_path_original_ext):
                    new_path = f"{base_path_with_date}.mp3"
                    os.rename(potential_path_original_ext, new_path)
                    downloaded_path = new_path
                    print(f"ℹ️ Renamed audio to {os.path.basename(downloaded_path)}")
                else:
                    print(f"⚠️ Could not find downloaded audio file for {video_url}")

    except Exception as e:
        print(f"❌ Error downloading audio for {video_url}: {e}")

    return downloaded_path

def transcribe_audio(model, audio_path, output_txt_path):
    """Transcribes the audio file using faster-whisper and saves it to a text file."""
    try:
        print(f"🎤 Starting transcription for: {os.path.basename(audio_path)}")

        target_language = "en"  # Mantener en inglés

        print(f"ℹ️ Procesando audio largo. Optimizando para evitar repeticiones con nuevos umbrales...")

        # faster-whisper usa segments iterator en lugar de un dict result
        segments, info = model.transcribe(
            audio_path,
            language=target_language,
            vad_filter=False,  # VAD deshabilitado (requiere onnxruntime no disponible en Python 3.14)
            beam_size=5,  # Balance entre velocidad y calidad
            condition_on_previous_text=False,  # Sin contexto previo para evitar repeticiones
            temperature=0.1,  # Baja temperatura para más determinismo
            compression_ratio_threshold=2.0,  # Control de periodos silenciosos
            log_prob_threshold=-0.6,  # Umbral de probabilidad logarítmica
            no_speech_threshold=0.2  # Umbral para detectar segmentos sin habla
        )
        
        print(f"ℹ️ Idioma detectado: {info.language} (probabilidad: {info.language_probability:.2f})")
        print("=" * 80)
        print("📝 TRANSCRIPCIÓN EN VIVO:")
        print("=" * 80)
        
        # Recolectar todos los segmentos mostrando en tiempo real
        transcription_text = ""
        for segment in segments:
            # Mostrar cada segmento en vivo
            print(segment.text, end='', flush=True)
            transcription_text += segment.text
        
        print("\n" + "=" * 80)

        with open(output_txt_path, 'w', encoding='utf-8') as f:
            f.write(transcription_text.strip())
        print(f"✅ Transcripción guardada en: {os.path.basename(output_txt_path)}")
        return output_txt_path
    except Exception as e:
        print(f"❌ Error during transcription for {os.path.basename(audio_path)}: {e}")
        return None

def create_link_file(video_url, output_path):
    """Creates a text file containing the YouTube URL."""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"YouTube URL: {video_url}\n")
            f.write(f"Este archivo fue generado automáticamente el {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🔗 Link file created: {os.path.basename(output_path)}")
        return output_path
    except Exception as e:
        print(f"❌ Error creating link file: {e}")
        return None

def main():
    # Load configuration
    try:
        with open("LinksYT.json", 'r') as f:
            config = json.load(f)
        parent_folder_id = config.get("parent_folder_id")
        video_urls = config.get("video_urls", [])
        if not parent_folder_id:
            print("❌ Error: 'parent_folder_id' not found in LinksYT.json")
            return
        if not video_urls:
            print("ℹ️ No video URLs found in LinksYT.json")
            return
    except FileNotFoundError:
        print("❌ Error: LinksYT.json not found.")
        return
    except json.JSONDecodeError:
        print("❌ Error: LinksYT.json is not valid JSON.")
        return

    # Get Google Drive service
    drive_service = get_drive_service()
    if not drive_service:
        return

    # --- Whisper Model Loading ---
    # --- Whisper Model Loading ---
    # Usar CPU por defecto. Para GPU: export WHISPER_DEVICE=cuda
    device = os.environ.get('WHISPER_DEVICE', 'cpu')
    compute_type = "float16" if device == "cuda" else "int8"
    
    print(f"ℹ️ Cargando modelo Whisper en {device.upper()}...")
    if device == "cpu":
        print("ℹ️ Para usar GPU: export WHISPER_DEVICE=cuda")
    
    whisper_model = WhisperModel("small", device=device, compute_type=compute_type)
    print(f"✅ Whisper 'small' cargado en {device.upper()}.")
    # --- End Whisper Model Loading ---

    # Create a temporary directory for downloads
    temp_download_dir = "temp_downloads"
    if not os.path.exists(temp_download_dir):
        os.makedirs(temp_download_dir)

    # Process each video URL
    for video_url in video_urls:
        print(f"\nProcessing: {video_url}")
        title, upload_date = get_video_info(video_url)

        if not title:
            print(f"⚠️ Skipping video due to missing title: {video_url}")
            continue
        # Si no hay fecha, ya la calculamos en get_video_info; no saltamos.

        # Sanitize title for file/folder names (replace invalid characters)
        safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in title)
        # Folder name format: Date - Title
        folder_name = f"{upload_date} - {safe_title}"

        # Create folder in Google Drive
        drive_folder_id = create_drive_folder(drive_service, folder_name, parent_folder_id)
        if not drive_folder_id:
            print(f"⚠️ Skipping video due to error creating Drive folder: {video_url}")
            continue

        # Define local file base path (used by download functions to construct full name)
        local_base_path_without_date = os.path.join(temp_download_dir, safe_title)

        # Download video (pass upload_date)
        video_path = download_video(video_url, local_base_path_without_date, upload_date)
        if video_path and os.path.exists(video_path):
            # Check if video already exists in Drive
            video_filename = os.path.basename(video_path)
            video_exists, _ = check_file_exists_in_drive(drive_service, video_filename, drive_folder_id)
            
            if not video_exists:
                upload_file_to_drive(drive_service, video_path, drive_folder_id)
            else:
                print(f"⏭️ Skipping upload of video file that already exists in Drive: {video_filename}")
            
            # Delete local copy regardless
            try:
                os.remove(video_path)
                print(f"🗑️ Deleted local video: {video_filename}")
            except OSError as e:
                print(f"⚠️ Error deleting local video file {video_path}: {e}")
        else:
            print(f"⚠️ Video download failed or file not found for {video_url}, skipping upload.")

        # Download audio (pass upload_date)
        audio_path = download_audio(video_url, local_base_path_without_date, upload_date)
        transcription_path = None # Initialize transcription path
        if audio_path and os.path.exists(audio_path):
            # --- Transcription Step ---
            # Construct the output path for the transcription .txt file
            txt_filename = f"{upload_date} - {safe_title}.txt"
            local_txt_path = os.path.join(temp_download_dir, txt_filename)

            # Transcribe the downloaded audio
            transcription_path = transcribe_audio(whisper_model, audio_path, local_txt_path)
            # --- End Transcription Step ---

            # Upload audio file
            audio_filename = os.path.basename(audio_path)
            audio_exists, _ = check_file_exists_in_drive(drive_service, audio_filename, drive_folder_id)
            
            if not audio_exists:
                upload_file_to_drive(drive_service, audio_path, drive_folder_id)
            else:
                print(f"⏭️ Skipping upload of audio file that already exists in Drive: {audio_filename}")
                
            try:
                os.remove(audio_path)
                print(f"🗑️ Deleted local audio: {os.path.basename(audio_path)}")
            except OSError as e:
                print(f"⚠️ Error deleting local audio file {audio_path}: {e}")
        else:
             print(f"⚠️ Audio download failed or file not found for {video_url}, skipping upload and transcription.")

        # Upload transcription file if it exists
        if transcription_path and os.path.exists(transcription_path):
            # Check if transcription already exists in Drive
            transcription_filename = os.path.basename(transcription_path)
            transcription_exists, _ = check_file_exists_in_drive(drive_service, transcription_filename, drive_folder_id)
            
            if not transcription_exists:
                upload_file_to_drive(drive_service, transcription_path, drive_folder_id)
            else:
                print(f"⏭️ Skipping upload of transcription file that already exists in Drive: {transcription_filename}")
            
            # Delete local copy regardless
            try:
                os.remove(transcription_path)
                print(f"🗑️ Deleted local transcription: {os.path.basename(transcription_path)}")
            except OSError as e:
                print(f"⚠️ Error deleting local transcription file {transcription_path}: {e}")
        elif audio_path and os.path.exists(audio_path): # Only print if audio existed but transcription failed
             print(f"⚠️ Transcription failed for {video_url}, skipping upload.")

        # Create and upload link file
        link_filename = f"{upload_date} - {safe_title} - Link.txt"
        local_link_path = os.path.join(temp_download_dir, link_filename)
        link_file_path = create_link_file(video_url, local_link_path)
        if link_file_path and os.path.exists(link_file_path):
            # Check if link file already exists in Drive
            link_file_exists, _ = check_file_exists_in_drive(drive_service, os.path.basename(link_file_path), drive_folder_id)
            
            if not link_file_exists:
                upload_file_to_drive(drive_service, link_file_path, drive_folder_id)
            else:
                print(f"⏭️ Skipping upload of link file that already exists in Drive: {os.path.basename(link_file_path)}")
            
            # Delete local copy regardless
            try:
                os.remove(link_file_path)
                print(f"🗑️ Deleted local link file: {os.path.basename(link_file_path)}")
            except OSError as e:
                print(f"⚠️ Error deleting local link file {link_file_path}: {e}")

    # Clean up temporary directory if empty
    try:
        if not os.listdir(temp_download_dir):
            os.rmdir(temp_download_dir)
        else:
            print(f"⚠️ Temporary download directory '{temp_download_dir}' not empty, manual cleanup might be needed.")
    except OSError as e:
         print(f"⚠️ Error removing temporary directory '{temp_download_dir}': {e}")

    print("\n✅ Processing complete.")

if __name__ == '__main__':
    main()
