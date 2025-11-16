import os
import datetime
import re
import subprocess
from faster_whisper import WhisperModel
import argparse

def get_media_info(media_path):
    """Gets media title and date from filename."""
    try:
        # Expecting filename format: "YYYY-MM-DD - Title.ext"
        filename = os.path.basename(media_path)
        # Extract date and title using regex - compatible with multiple media extensions
        match = re.match(r'(\d{4}-\d{2}-\d{2})\s*-\s*(.+)\.(\w+)', filename)
        
        if match:
            date = match.group(1)
            title = match.group(2)
            print(f"📄 Extracted info from {filename}: Date={date}, Title={title}")
            return title, date
        else:
            # If filename doesn't match expected format, use file modification date
            mod_time = os.path.getmtime(media_path)
            date = datetime.datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d')
            title = os.path.splitext(filename)[0]  # Remove extension
            print(f"⚠️ Couldn't parse filename format. Using: Date={date}, Title={title}")
            return title, date
    except Exception as e:
        print(f"❌ Error getting media info from {media_path}: {e}")
        return None, None

def extract_audio_from_video(video_path, output_dir):
    """Extracts MP3 audio from a video file."""
    # Get the basename without extension
    filename = os.path.basename(video_path)
    base_name = os.path.splitext(filename)[0]
    output_path = os.path.join(output_dir, f"{base_name}.mp3")
    
    # Método 1: Usar FFmpeg directamente (opción preferida)
    if check_ffmpeg():
        try:
            print(f"ℹ️ Extrayendo audio con FFmpeg desde: {filename}")
            ffmpeg_cmd = [
                'ffmpeg', 
                '-i', video_path, 
                '-q:a', '0',         # Alta calidad
                '-map', 'a',         # Solo extraer audio
                '-id3v2_version', '3',  # Compatibilidad ID3 tag
                output_path,
                '-y'                # Sobrescribir si existe
            ]
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if os.path.exists(output_path):
                print(f"✅ Audio extraído con FFmpeg: {os.path.basename(output_path)}")
                return output_path
            else:
                print(f"⚠️ FFmpeg no generó el archivo de salida esperado: {output_path}")
        except Exception as e:
            print(f"❌ Error al extraer audio con FFmpeg: {e}")
    else:
        print(f"⚠️ FFmpeg no disponible. Por favor instale FFmpeg para continuar.")
        return None
    
    print(f"❌ No se pudo extraer el audio de: {filename}")
    return None

def transcribe_audio(model, audio_path, output_txt_path, language=None):
    """Transcribes the audio file using faster-whisper and saves it to a text file.
    
    Args:
        model: The faster-whisper WhisperModel to use
        audio_path: Path to the audio file
        output_txt_path: Path where to save the transcription
        language: ISO language code (e.g. 'es', 'en', 'fr', None for auto-detection)
    """
    try:
        print(f"🎤 Starting transcription for: {os.path.basename(audio_path)}")

        # Si no se especifica el idioma, intentamos detectarlo automáticamente
        target_language = language
        if target_language:
            print(f"ℹ️ Idioma seleccionado manualmente: {target_language}")
        else:
            print("ℹ️ Detección automática de idioma activada")

        print(f"ℹ️ Procesando audio. Optimizando para evitar repeticiones con nuevos umbrales...")

        # faster-whisper usa segments iterator en lugar de un dict result
        segments, info = model.transcribe(
            audio_path,
            language=target_language,  # Puede ser None para detección automática
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

# Variable global para almacenar el estado de FFmpeg
ffmpeg_available = None

def check_ffmpeg():
    """Verifica si FFmpeg está instalado en el sistema."""
    global ffmpeg_available
    
    # Si ya hicimos la verificación antes, retornamos el resultado guardado
    if ffmpeg_available is not None:
        return ffmpeg_available
        
    try:
        result = subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            version_info = result.stdout.decode('utf-8').split('\n')[0]
            print(f"✅ FFmpeg detectado: {version_info}")
            ffmpeg_available = True
            return True
        else:
            print("⚠️ FFmpeg no parece estar disponible.")
            ffmpeg_available = False
            return False
    except FileNotFoundError:
        print("⚠️ FFmpeg no está instalado o no está en el PATH del sistema.")
        ffmpeg_available = False
        return False

def is_audio_file(file_path):
    """Determina si un archivo es de audio basado en su extensión"""
    audio_extensions = ('.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg')
    return file_path.lower().endswith(audio_extensions)

def is_video_file(file_path):
    """Determina si un archivo es de video basado en su extensión"""
    video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv')
    return file_path.lower().endswith(video_extensions)

def main():
    # Configurar parser de argumentos de línea de comandos
    parser = argparse.ArgumentParser(description='Transcribe audio and video files to text')
    parser.add_argument('--lang', type=str, help='Language code (e.g. es, en, fr). Leave empty for auto-detection.')
    parser.add_argument('--input', type=str, default='input', help='Input directory containing audio/video files')
    parser.add_argument('--output', type=str, default='output', help='Output directory for transcriptions')
    
    args = parser.parse_args()
    
    # Directorios de trabajo
    input_dir = args.input  # Directorio para archivos de entrada (videos o audio)
    output_dir = args.output  # Directorio para transcripciones y audio extraído
    temp_dir = "temp"    # Directorio temporal para procesamiento
    
    # Configuración de idioma (códigos ISO: es, en, fr, etc., None para detección automática)
    target_language = args.lang
    
    if target_language:
        print(f"ℹ️ Idioma seleccionado: {target_language}")
    else:
        print("ℹ️ Se utilizará detección automática de idioma")
    
    # Crear directorios si no existen
    for directory in [input_dir, output_dir, temp_dir]:
        if not os.path.exists(directory):
            print(f"ℹ️ Creando directorio: {directory}")
            os.makedirs(directory)

    # Verificar dependencias
    print("ℹ️ Verificando dependencias...")
    has_ffmpeg = check_ffmpeg()
    if not has_ffmpeg:
        print("❌ FFmpeg no está disponible. Necesario para procesar videos.")
        return

    # --- Carga del modelo Whisper ---
    # Usar CPU por defecto. Para GPU: export WHISPER_DEVICE=cuda
    device = os.environ.get('WHISPER_DEVICE', 'cpu')
    compute_type = "float16" if device == "cuda" else "int8"
    
    print(f"ℹ️ Cargando modelo Whisper en {device.upper()}...")
    if device == "cpu":
        print("ℹ️ Para usar GPU: export WHISPER_DEVICE=cuda")
    
    whisper_model = WhisperModel("medium", device=device, compute_type=compute_type)
    print(f"✅ Modelo Whisper 'medium' cargado en {device.upper()}.")
    
    # Obtener archivos de entrada (audio y video)
    input_files = [f for f in os.listdir(input_dir) 
                  if is_audio_file(f) or is_video_file(f)]
    
    if not input_files:
        print(f"❌ No se encontraron archivos de audio o video en '{input_dir}'.")
        return
        
    print(f"ℹ️ Se encontraron {len(input_files)} archivos para procesar.")

    # Procesar cada archivo
    for filename in input_files:
        file_path = os.path.join(input_dir, filename)
        print(f"\nProcesando: {filename}")

        # Obtener información del archivo
        title, date = get_media_info(file_path)
        if not title or not date:
            print(f"⚠️ Omitiendo archivo por falta de información: {filename}")
            continue

        # Sanitizar título para usar en nombres de archivo
        safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in title)
        
        # Manejar la transcripción
        audio_path = file_path
        audio_for_transcription = None
        
        # Si es un video, extraer el audio primero
        if is_video_file(file_path):
            print("ℹ️ Detectado archivo de video, extrayendo audio...")
            audio_path = extract_audio_from_video(file_path, temp_dir)
            audio_for_transcription = audio_path
            
            if not audio_path or not os.path.exists(audio_path):
                print(f"❌ No se pudo extraer el audio del video: {filename}")
                continue
        elif is_audio_file(file_path):
            print("ℹ️ Detectado archivo de audio, usando directamente...")
            audio_for_transcription = file_path
        else:
            print(f"❌ Tipo de archivo no soportado: {filename}")
            continue

        # Preparar ruta para la transcripción
        txt_filename = f"{date} - {safe_title}.txt"
        output_txt_path = os.path.join(output_dir, txt_filename)
        
        # Transcribir el audio
        print(f"ℹ️ Iniciando transcripción de: {os.path.basename(audio_for_transcription)}")
        transcription_path = transcribe_audio(whisper_model, audio_for_transcription, output_txt_path, language=target_language)
        
        # Si se generó audio temporal de un video, guardarlo o eliminarlo según preferencia
        if is_video_file(file_path) and audio_for_transcription and os.path.exists(audio_for_transcription):
            # Opción 1: Guardar el audio extraído en el directorio de salida
            audio_filename = os.path.basename(audio_for_transcription)
            final_audio_path = os.path.join(output_dir, audio_filename)
            
            try:
                # Copiar el archivo de audio al directorio de salida
                import shutil
                shutil.copy2(audio_for_transcription, final_audio_path)
                print(f"✅ Audio guardado en: {os.path.basename(final_audio_path)}")
                
                # Eliminar archivo temporal
                os.remove(audio_for_transcription)
                print(f"🗑️ Eliminado archivo temporal: {os.path.basename(audio_for_transcription)}")
            except Exception as e:
                print(f"⚠️ Error al gestionar el archivo de audio: {e}")

        print(f"✅ Procesamiento completo para: {filename}")

    # Limpiar directorio temporal si está vacío
    try:
        if os.path.exists(temp_dir) and not os.listdir(temp_dir):
            os.rmdir(temp_dir)
        elif os.path.exists(temp_dir) and os.listdir(temp_dir):
            print(f"⚠️ Directorio temporal '{temp_dir}' no está vacío, puede requerir limpieza manual.")
    except OSError as e:
         print(f"⚠️ Error al eliminar directorio temporal '{temp_dir}': {e}")

    print("\n✅ Procesamiento completo de todos los archivos.")

if __name__ == '__main__':
    main()
