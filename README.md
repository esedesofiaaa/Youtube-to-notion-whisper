# YouTube to Google Drive Automation

![YouTube to Google Drive Automation](https://github.com/user-attachments/assets/921fa3bc-3384-4f14-9710-ea04fe08a448)

Sistema automatizado de nivel empresarial para descargar videos de YouTube, transcribirlos con **Faster-Whisper** y organizarlos en Google Drive con arquitectura modular y resiliente.

## Tabla de Contenidos

- [Descripcion General](#descripcion-general)
- [Caracteristicas Principales](#caracteristicas-principales)
- [Arquitectura Tecnica](#arquitectura-tecnica)
- [Requisitos del Sistema](#requisitos-del-sistema)
- [Instalacion](#instalacion)
- [Configuracion](#configuracion)
- [Guia de Uso](#guia-de-uso)
- [Componentes del Sistema](#componentes-del-sistema)
- [Resolucion de Problemas](#resolucion-de-problemas)
- [Mejoras Futuras](#mejoras-futuras)
- [Seguridad](#seguridad)
- [Licencia](#licencia)

## Descripcion General

Este sistema proporciona una solucion completa para automatizar el procesamiento de contenido de YouTube:

- Descarga automatizada de videos y audio desde YouTube
- Transcripcion mediante IA con Faster-Whisper
- Almacenamiento organizado en Google Drive
- Integracion opcional con Notion para gestion de contenido
- Sistema robusto de manejo de errores y reintentos
- Arquitectura modular y escalable

El proyecto esta disenado para manejar desde procesamiento individual de archivos hasta flujos de trabajo complejos con multiples canales y cientos de videos.

## Caracteristicas Principales

### Procesamiento de Video

- **Descarga optimizada** con `yt-dlp` y soporte para clientes moviles (evita errores SABR)
- **Formatos flexibles**: MP4 para video, MP3 para audio
- **Extraccion de metadatos**: titulo, fecha de publicacion, URL original
- **Gestion de nombres**: sanitizacion automatica y formato `YYYY-MM-DD - Titulo`

### Transcripcion con Faster-Whisper

#### Ventajas sobre OpenAI Whisper Clasico

| Caracteristica | Faster-Whisper | OpenAI Whisper |
|---------------|----------------|----------------|
| Compatibilidad Python | 3.10 - 3.14+ | 3.10 - 3.13 |
| Velocidad CPU | **2.67x mas rapido** | Baseline |
| Velocidad GPU | **3-4x mas rapido** | Baseline |
| Uso de VRAM | **50% menos (1GB)** | 2GB (medium) |
| Transcripcion en vivo | Si | No |

#### Rendimiento Real

| Hardware | Video 2h | Modelo | Optimizacion |
|----------|----------|--------|--------------|
| CPU (8 cores) | 45 min | medium | int8 |
| GPU RTX 3060 | 12-15 min | medium | float16 |
| GPU RTX 4090 | 8-10 min | medium | float16 |

### Organizacion en Google Drive

- **Estructura jerarquica**: carpetas por fecha y titulo
- **Prevencion de duplicados**: verificacion antes de subir
- **Archivos completos**: video, audio, transcripcion y enlace original
- **Soporte para unidades compartidas**: compatible con Google Workspace

### Sistema de Orquestacion Empresarial

- **Procesamiento por lotes**: multiples canales y videos
- **Gestion de estado**: seguimiento de progreso por video
- **Reintentos automaticos**: hasta 3 intentos configurables
- **Logging estructurado**: registros rotatorios con niveles configurables
- **Integracion Notion**: sincronizacion con bases de datos

## Arquitectura Tecnica

### Diagrama de Componentes

```
youtube_processor/
├── config/
│   └── ConfigManager          # Gestion centralizada de configuracion
├── extraction/
│   └── NotionExtractor        # Extraccion de datos desde Notion
└── utils/
    ├── JSONGenerator          # Generacion y actualizacion de estado
    ├── ChannelOrganizer       # Organizacion de videos por canal
    ├── ProcessingCoordinator  # Coordinacion de ejecucion secuencial
    └── ErrorHandler           # Manejo robusto de errores

Scripts principales:
├── DiscordToDrive.py          # Procesamiento principal de videos
└── LocalTranscriber.py        # Herramienta CLI para transcripcion local
```

### Flujo de Datos

1. **Entrada**: URLs de YouTube (manual o desde Notion)
2. **Organizacion**: Agrupacion por canal y generacion de JSONs de estado
3. **Procesamiento**: Descarga, transcripcion y subida secuencial
4. **Actualizacion**: Marcado de completado/fallido en JSONs
5. **Salida**: Archivos organizados en Google Drive + logs detallados

### Tecnologias Clave

- **Python 3.10+**: Lenguaje principal
- **Faster-Whisper**: Motor de transcripcion con CTranslate2
- **yt-dlp**: Descarga robusta de YouTube
- **Google Drive API**: Almacenamiento en la nube
- **Notion API**: Gestion de contenido (opcional)
- **FFmpeg**: Procesamiento de multimedia

## Requisitos del Sistema

### Software Obligatorio

- **Python**: 3.10 o superior (3.14 totalmente soportado)
- **FFmpeg**: Para procesamiento de audio/video
- **Git**: Para clonar el repositorio

### Hardware Recomendado

#### Minimo (CPU)
- Procesador: 4+ cores
- RAM: 8 GB
- Almacenamiento: 20 GB libres

#### Optimo (GPU)
- GPU: NVIDIA con 4+ GB VRAM
- CUDA: 11.8 o superior
- RAM: 16 GB
- Almacenamiento: 50 GB libres (SSD recomendado)

## Instalacion

### 1. Instalar FFmpeg

**Linux (Ubuntu/Debian)**:
```bash
sudo apt update && sudo apt install ffmpeg
ffmpeg -version
```

**macOS**:
```bash
brew install ffmpeg
```

**Windows**: Descargar desde [ffmpeg.org](https://ffmpeg.org/download.html)

### 2. Clonar el Repositorio

```bash
git clone https://github.com/esedesofiaaa/Youtube-to-notion-whisper.git
cd Youtube-to-notion-whisper
```

### 3. Crear Entorno Virtual

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

### 4. Instalar Dependencias

```bash
pip install -r requirements.txt
```

**Para GPU (NVIDIA con CUDA)**:
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

## Configuracion

### 1. Google Drive API

1. Ir a [Google Cloud Console](https://console.cloud.google.com/)
2. Crear proyecto y habilitar **Google Drive API**
3. Crear credenciales **OAuth 2.0** (Desktop Application)
4. Descargar JSON y guardarlo como `credentials.json` en raiz
5. Primera ejecucion: se abrira navegador para autorizar (genera `token.pickle`)

### 2. Archivo `.env` (Opcional)

```env
# Notion API (Opcional)
NOTION_TOKEN=secret_tu_token_aqui
NOTION_DATABASE_ID=32_caracteres

# Procesamiento
START_DATE=2025-01-01
BATCH_SIZE_PER_EXECUTION=10
MAX_RETRY_ATTEMPTS=3

# Whisper
WHISPER_DEVICE=cpu  # o 'cuda' para GPU
```

### 3. Archivo `LinksYT.json`

```json
{
  "parent_folder_id": "ID_CARPETA_DRIVE",
  "video_urls": [
    "https://www.youtube.com/watch?v=VIDEO_ID"
  ]
}
```

**Obtener ID de carpeta**: URL de Drive `https://drive.google.com/drive/folders/ID_AQUI`

## Guia de Uso

### Modo 1: Procesamiento Simple

```bash
# Verificar archivos
ls credentials.json LinksYT.json

# Ejecutar
python DiscordToDrive.py
```

**Salida esperada**:
```
Processing: https://www.youtube.com/watch?v=ejemplo
Folder '2025-11-15 - Titulo' created
Video downloaded: 2025-11-15 - Titulo.mp4
Audio downloaded: 2025-11-15 - Titulo.mp3
Starting transcription...
================================================================================
TRANSCRIPCION EN VIVO:
================================================================================
[Texto transcrito aparece aqui en tiempo real...]
================================================================================
File uploaded to Drive
Processing complete.
```

### Modo 2: Transcripcion Local

```bash
# Copiar archivos a input/
cp mis_videos/*.mp4 input/

# Transcribir
python LocalTranscriber.py --lang es

# Ver resultados
ls output/
```

**Opciones**:
- `--lang es`: Especificar idioma (es, en, fr, de, it, pt, etc.)
- `--input ./videos`: Directorio de entrada custom
- `--output ./textos`: Directorio de salida custom

### Modo 3: Orquestacion con Notion

```bash
# Generar JSONs de canales
python -m youtube_processor.utils.channel_organizer

# Procesar secuencialmente
python -m youtube_processor.utils.processing_coordinator

# Monitorear logs
tail -f logs/youtube_processor.log
```

### Modo 4: Uso con GPU

```bash
export WHISPER_DEVICE=cuda
python DiscordToDrive.py
```

**Comparativa**:
- CPU (8 cores): 45 min para video de 2h
- GPU RTX 3060: 12-15 min (3x mas rapido)
- GPU RTX 4090: 8-10 min (5x mas rapido)

## Componentes del Sistema

### DiscordToDrive.py

Script principal para descarga, transcripcion y subida.

**Modelos Whisper disponibles**:

| Modelo | Velocidad | Precision | VRAM | RAM |
|--------|-----------|-----------|------|-----|
| tiny | Muy rapida | Baja | 1GB | 1GB |
| base | Rapida | Media | 1GB | 1GB |
| small | Media | Media | 2GB | 2GB |
| medium | Lenta | Alta | 5GB | 5GB |
| large | Muy lenta | Muy alta | 10GB | 10GB |

Cambiar modelo en `DiscordToDrive.py` linea ~170:
```python
whisper_model = WhisperModel("medium", device=device)
```

### LocalTranscriber.py

Herramienta CLI standalone para transcripcion local:
- Extrae audio de videos con FFmpeg
- Usa modelo `medium` por defecto
- Soporta deteccion automatica de idioma
- Procesa multiples archivos en lote

### youtube_processor/

Paquete de orquestacion empresarial:

- **ConfigManager**: Gestion centralizada de configuracion desde `.env`
- **NotionExtractor**: Extraccion de videos desde bases de datos Notion
- **JSONGenerator**: Generacion y actualizacion de estado por canal
- **ChannelOrganizer**: Organizacion de videos por canal
- **ProcessingCoordinator**: Ejecucion secuencial con reintentos
- **ErrorHandler**: Clasificacion y registro de errores

## Resolucion de Problemas

### FFmpeg no encontrado

```bash
# Verificar
ffmpeg -version

# Instalar
sudo apt install ffmpeg  # Linux
brew install ffmpeg      # macOS
```

### Error de autenticacion Google

```bash
# Regenerar token
rm token.pickle
python DiscordToDrive.py  # Se abrira navegador
```

### CUDA out of memory

```python
# Opcion 1: Modelo mas pequeno
whisper_model = WhisperModel("small", device=device)

# Opcion 2: Forzar CPU
export WHISPER_DEVICE=cpu
```

### Error SABR de yt-dlp

```bash
# Actualizar yt-dlp
pip install --upgrade yt-dlp
```

### Notion API 401

```bash
# Verificar token
grep NOTION_TOKEN .env

# Token debe empezar con 'secret_' o 'ntn_'
# Verificar permisos en https://www.notion.so/my-integrations
```

### Transcripcion con repeticiones

Ya implementado en codigo con parametros optimizados. Si persiste:

```python
# En transcribe_audio(), ajustar:
temperature=0.0,  # Mas determinista
no_speech_threshold=0.4  # Mas agresivo
```

### Tecnologias
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Descarga de YouTube
- [Faster-Whisper](https://github.com/guillaumekln/faster-whisper) - Transcripcion IA
- [Google Drive API](https://developers.google.com/drive) - Almacenamiento
- [Notion API](https://developers.notion.com/) - Gestion de contenido
- [FFmpeg](https://ffmpeg.org/) - Procesamiento multimedia