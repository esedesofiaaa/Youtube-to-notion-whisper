# Changelog

## [Pipeline Unificado de Streaming - 2025-12-03]

### 🎯 UNIFICACIÓN: Pipeline de Streaming como Estándar

#### Cambio Principal
Se unificó toda la lógica de procesamiento de videos en un **único pipeline de streaming**.
La tarea `process_youtube_video` ahora utiliza la arquitectura de streaming para **TODOS** los videos,
tanto lives como VOD (videos normales), con fallback automático al método tradicional si falla.

**Beneficios:**
- ✅ **Más eficiente**: Transcribe mientras descarga (no espera a que termine)
- ✅ **Un solo código**: Mantiene la compatibilidad con el webhook existente
- ✅ **Resiliente**: Fallback automático si el streaming falla
- ✅ **Funciona igual**: Para VOD y para Live Streams

### 🔧 Arquitectura Unificada

```
┌─────────────────────────────────────────────────────────────────┐
│                    process_youtube_video                        │
│  (Tarea única para TODO el procesamiento de videos)            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  INTENTO 1: Pipeline de Streaming                               │
│  ┌─────────┐      ┌─────────────────────────────┐              │
│  │ yt-dlp  │─────>│ FFmpeg                      │              │
│  │         │ pipe │  ├─> video.mkv (disco)      │              │
│  └─────────┘      │  └─> WAV 16kHz ──> Whisper  │              │
│                   └─────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ¿Falló streaming?
                              │
              ┌───────────────┴───────────────┐
              │ SÍ                            │ NO
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────────────┐
│  FALLBACK: Tradicional  │     │  Continúa con subida atómica    │
│  • download_video()     │     │  • Upload Drive                 │
│  • download_audio()     │     │  • Create Notion page           │
│  • transcribe()         │     │  • Update Discord DB            │
└─────────────────────────┘     └─────────────────────────────────┘
```

### 📝 Cambios en `src/tasks.py`

- **ELIMINADO**: Tarea `process_live_stream` (ya no existe)
- **MODIFICADO**: `process_youtube_video` ahora usa streaming pipeline + fallback
- **NUEVO CAMPO EN RESULTADO**: `processing_mode` = "streaming" | "fallback"
- **NUEVO CAMPO EN RESULTADO**: `chunks_processed` = número de chunks transcritos

### ✅ Compatibilidad

- ✅ **Sin cambios en el webhook**: `/webhook/process-video` funciona igual
- ✅ **Sin cambios en n8n**: La integración sigue funcionando
- ✅ **Sin cambios en la API**: Mismos parámetros de entrada y salida

### 📦 Resultado de la Tarea

```python
{
    "status": "success",
    "task_id": "...",
    "youtube_url": "...",
    "video_title": "...",
    "notion_page_url": "...",
    "drive_folder_url": "...",
    "drive_video_url": "...",
    "transcription_length": 12345,
    "database_name": "Paradise Island Videos",
    "processing_mode": "streaming",  # o "fallback"
    "chunks_processed": 42           # solo relevante en modo streaming
}
```

---

## [Streaming Transcription - 2025-12-03]

### 🎯 Nueva Funcionalidad: Transcripción en Vivo (Streaming)

#### Pipeline Híbrido de Procesamiento
Se implementó una arquitectura de **"Single-Pass Processing con Subida Diferida"** que permite:
- **Transcripción en tiempo real** mientras se descarga el video
- **Guardado simultáneo** del video en disco (MKV) para backup
- **Subida atómica** a Drive y Notion solo al finalizar el stream

### ✨ Nuevos Componentes

#### 1. Streaming en YouTubeDownloader (`src/youtube_downloader.py`)
- **`stream_and_capture(video_info, save_video=True)`**: Nuevo método que:
  - Ejecuta `yt-dlp` enviando datos a `stdout`
  - `FFmpeg` recibe y bifurca el stream:
    - **Output 1**: Guarda video MKV en disco (codecs copiados, sin re-encoding)
    - **Output 2**: Envía audio WAV 16kHz mono por pipe para Whisper
- **`stop_stream(process)`**: Detiene gracefully los procesos de streaming
- **`is_stream_active(process)`**: Verifica si el stream sigue activo
- **`get_stream_errors(process)`**: Obtiene errores de FFmpeg

#### 2. Transcripción por Streaming (`src/transcriber.py`)
- **`transcribe_stream(audio_pipe, language, chunk_duration)`**: 
  - Lee audio desde pipe en chunks configurables (default 30s)
  - Transcribe cada chunk con Whisper en tiempo real
  - Genera resultados parciales via `yield`
  - Maneja buffer de audio para evitar cortar palabras
- **`_transcribe_audio_buffer(audio_bytes, sample_rate)`**:
  - Convierte bytes PCM a numpy array float32
  - Transcribe usando faster-whisper directamente en memoria

#### 3. Nueva Tarea Celery (`src/tasks.py`)
- **`process_live_stream`**: Tarea dedicada para streaming que:
  1. Inicia pipeline yt-dlp → FFmpeg
  2. Transcribe en vivo acumulando texto
  3. Al finalizar: subida atómica a Drive + creación en Notion
  4. **Fallback automático**: Si streaming falla, usa método tradicional

#### 4. Nuevo Modelo (`src/models.py`)
- **`StreamingTranscriptionResult`**: Extiende TranscriptionResult con:
  - `chunks_processed`: Número de chunks procesados
  - `stream_completed`: Indica si el stream finalizó correctamente
  - `to_transcription_result()`: Conversión para compatibilidad

#### 5. Nuevas Configuraciones (`config/settings.py`)
```python
STREAMING_SAMPLE_RATE = 16000      # Hz para Whisper
STREAMING_BUFFER_SIZE = 65536      # 64KB buffer
STREAMING_CHUNK_DURATION = 30.0    # segundos por chunk
STREAMING_MIN_AUDIO_DURATION = 5.0 # mínimo para transcribir
STREAMING_MAX_RETRIES = 3          # reintentos antes de fallback
STREAMING_READ_TIMEOUT = 60.0      # timeout para datos del stream
```

### 🔧 Arquitectura del Pipeline

```
┌─────────┐      ┌─────────────────────────────────────────┐
│ yt-dlp  │─────>│ FFmpeg                                  │
│ (video) │ pipe │  ├─> Output 1: video.mkv (disco)       │
└─────────┘      │  └─> Output 2: WAV 16kHz ──> Python    │
                 └─────────────────────────────────────────┘
                                                    │
                                                    ▼
                 ┌─────────────────────────────────────────┐
                 │ AudioTranscriber.transcribe_stream()    │
                 │  ├─> Buffer audio (chunks de 30s)       │
                 │  ├─> Transcribir con Whisper            │
                 │  └─> yield (text, segments)             │
                 └─────────────────────────────────────────┘
                                                    │
                                                    ▼ (Al finalizar stream)
                 ┌─────────────────────────────────────────┐
                 │ Subida Atómica                          │
                 │  ├─> Upload video a Drive               │
                 │  ├─> Upload transcripts (TXT/SRT)       │
                 │  └─> Crear página en Notion             │
                 └─────────────────────────────────────────┘
```

### 📝 Uso

```python
from src.tasks import process_live_stream

# Llamar la tarea de streaming
result = process_live_stream.delay(
    discord_entry_id="...",
    youtube_url="https://youtube.com/watch?v=...",
    channel="🎙・market-outlook",
    use_fallback_on_error=True  # Fallback automático si falla streaming
)
```

### ⚠️ Requisitos del Sistema
- **FFmpeg** debe estar instalado y en PATH
- **yt-dlp** debe estar instalado y en PATH
- **NumPy** para conversión de audio a arrays

---

## [Integración con Notion y Sistema Asíncrono - 2025-11-16]

### 🎯 Nueva Funcionalidad Principal

#### Sistema de Webhooks y Cola de Tareas
- **Integración completa con Notion API** para automatización de procesamiento de videos
- **Servidor de webhooks FastAPI** para recibir notificaciones de n8n
- **Cola de tareas asíncrona** con Celery + Redis para procesamiento en segundo plano
- **Dashboard de monitoreo** con Flower para visualizar estado de tareas en tiempo real

### ✨ Nuevos Componentes

#### 1. Cliente de Notion (`src/notion_client.py`)
- Lectura de páginas de Discord Message Database
- Creación de páginas en bases de datos de destino (Paradise Island, Docs Videos)
- Actualización automática del campo "Transcript" con URL de página creada
- Validación de datos de webhook
- Extracción inteligente de propiedades de Notion (title, select, url, date, rich_text)

#### 2. Servidor de Webhooks (`src/webhook_server.py`)
- **Framework**: FastAPI con documentación automática (Swagger/ReDoc)
- **Endpoints**:
  - `POST /webhook/process-video`: Encola procesamiento de videos
  - `GET /task/{task_id}`: Consulta estado de tarea
  - `GET /health`: Health check
  - `POST /test/task`: Prueba de funcionamiento de Celery
- **Autenticación**: Header `X-Webhook-Secret` configurable
- **Validación**: Pydantic models con validación automática
- **Manejo de errores**: Global exception handler con logging detallado

#### 3. Sistema de Colas (`src/celery_app.py` + `src/tasks.py`)
- **Tarea principal**: `process_youtube_video` con flujo completo de procesamiento
- **Reintentos automáticos**: 3 intentos con exponential backoff y jitter
- **Timeouts configurables**: 1 hora por tarea (configurable)
- **Callbacks**: on_success, on_failure, on_retry para logging detallado
- **Tracking**: Estado de tareas (PENDING, STARTED, SUCCESS, FAILURE, RETRY)

#### 4. Configuración de Notion (`config/notion_config.py`)
- **Mapeo flexible** de canales de Discord a bases de datos de Notion
- **IDs de bases de datos** centralizados:
  - Discord Message DB: `28bdaf66daf7816383e6ce8390b0a866`
  - Paradise Island DB: `287daf66daf7807290d0fb514fdf4d86`
  - Docs Videos DB: `287daf66daf780fb89f7dd15bac7aa2a`
- **Mapeo de canales**:
  - `🎙・market-outlook` → Paradise Island Videos Database
  - `🎙・market-analysis-streams` → Docs Videos Database
- **Validadores**: YouTube URLs, canales válidos
- **Estructura de campos** de Notion documentada

### 🔧 Mejoras de Configuración

#### Variables de Entorno Ampliadas (`.env.example`)
```bash
# Notion API
NOTION_TOKEN=tu_token_aqui

# Celery & Redis
REDIS_URL=redis://localhost:6379/0
CELERY_TASK_MAX_RETRIES=3
CELERY_TASK_RETRY_DELAY=60
CELERY_TASK_TIME_LIMIT=3600
CELERY_WORKER_CONCURRENCY=1  # Procesamiento secuencial (CPU)

# Webhook Server
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8000
WEBHOOK_SECRET=tu_secreto_aqui

# Flower Dashboard
FLOWER_PORT=5555
FLOWER_BASIC_AUTH=usuario:contraseña
```

#### Configuración Centralizada en `config/settings.py`
- Parámetros de Celery (reintentos, timeouts, serialización)
- **Worker concurrency**: Configuración de procesamiento secuencial (1 video a la vez) optimizado para CPU
- Configuración de Redis (broker, backend)
- Configuración de webhook server (host, puerto, secreto)
- Configuración de Flower (puerto, autenticación)

### 🐳 Docker & Orquestación

#### Docker Compose (`docker-compose.yml`)
- **Redis**: Imagen Alpine, volumen persistente, healthcheck
- **Flower**: Perfil opcional para monitoreo
- **Networking**: Red dedicada `youtube-to-notion-network`

#### Scripts de Gestión
- `scripts/start_worker.sh`: Inicia Celery worker
- `scripts/start_flower.sh`: Inicia dashboard de Flower
- `scripts/start_webhook_server.sh`: Inicia servidor de webhooks
- `scripts/start_all.sh`: Inicia sistema completo (Redis + Worker + Flower + Webhook)
- `scripts/stop_all.sh`: Detiene todos los servicios
- Todos los scripts son ejecutables y con logging mejorado

### 📋 Flujo de Trabajo Completo

```
1. n8n monitorea Discord Message Database
   ↓
2. Detecta nueva entrada con YouTube URL en canal válido
   ↓
3. n8n envía webhook a FastAPI server
   ↓
4. FastAPI valida datos y encola tarea en Celery
   ↓
5. Worker de Celery procesa tarea:
   a. Descarga video/audio de YouTube
   b. Transcribe con Whisper
   c. Crea carpeta en Google Drive
   d. Sube archivos a Drive
   e. Crea página en Notion DB de destino
   f. Actualiza campo Transcript en Discord Message DB
   ↓
6. Tarea completada, visible en Flower dashboard
```

### 🎛️ Dashboard de Monitoreo (Flower)

- **URL**: http://localhost:5555
- **Características**:
  - Visualización de tareas en tiempo real
  - Gráficos de progreso y rendimiento
  - Logs detallados de cada tarea
  - Estado de workers
  - Reintentos y errores
  - Tiempo de ejecución
- **Autenticación opcional** con basic auth

### 📦 Nuevas Dependencias

```python
# Notion API
notion-client>=2.2.0

# Task Queue & Workers
celery>=5.3.0
redis>=5.0.0
flower>=2.0.0

# Webhook Server
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.5.0
```

### 🏗️ Arquitectura Actualizada

```
Youtube-to-notion-whisper/
├── config/
│   ├── settings.py         # Configuración general + Celery + Webhooks
│   ├── notion_config.py    # Configuración de Notion (NUEVO)
│   └── logger.py           # Sistema de logging
├── src/
│   ├── notion_client.py    # Cliente de Notion API (NUEVO)
│   ├── celery_app.py       # Configuración de Celery (NUEVO)
│   ├── tasks.py            # Tareas asíncronas (NUEVO)
│   ├── webhook_server.py   # Servidor FastAPI (NUEVO)
│   ├── youtube_downloader.py
│   ├── transcriber.py
│   ├── drive_manager.py
│   └── models.py
├── scripts/
│   ├── start_worker.sh     # Iniciar Celery worker (NUEVO)
│   ├── start_flower.sh     # Iniciar Flower (NUEVO)
│   ├── start_webhook_server.sh  # Iniciar webhook server (NUEVO)
│   ├── start_all.sh        # Iniciar todo (NUEVO)
│   ├── stop_all.sh         # Detener todo (NUEVO)
│   ├── discord_to_drive.py # Script original (mantiene compatibilidad)
│   └── local_transcriber.py
├── docs/
│   ├── NOTION_INTEGRATION.md  # Documentación completa (NUEVO)
│   └── CHANGELOG.md
├── docker-compose.yml      # Redis + Flower (NUEVO)
├── .env.example            # Variables de entorno actualizadas
└── requirements.txt        # Dependencias actualizadas
```

### 🔐 Seguridad

- **Autenticación de webhooks** con secreto configurable
- **Validación de datos** con Pydantic
- **HTTPS recomendado** para producción
- **Autenticación opcional** en Flower
- **Token de Notion** protegido en variables de entorno

### 📊 Beneficios de la Nueva Arquitectura

1. **Automatización Completa**: Procesamiento automático desde Discord hasta Notion
2. **Procesamiento Secuencial**: Cola FIFO que procesa videos uno a la vez (optimizado para CPU)
3. **Escalabilidad Opcional**: Configuración flexible para GPU con múltiples videos simultáneos
4. **Resiliencia**: Reintentos automáticos con exponential backoff
5. **Monitoreo**: Dashboard en tiempo real con Flower
6. **Trazabilidad**: Logs detallados de cada paso del proceso
7. **Flexibilidad**: Fácil añadir nuevos canales o bases de datos
8. **Performance**: Procesamiento asíncrono no bloquea el sistema
9. **API RESTful**: Endpoints documentados con Swagger/ReDoc

### 📝 Compatibilidad

- ✅ **Mantiene funcionalidad anterior**: Scripts originales siguen funcionando
- ✅ **Sin breaking changes**: Configuración anterior sigue siendo válida
- ✅ **Opcional**: Puedes usar solo la funcionalidad de webhooks o solo los scripts
- ✅ **Modular**: Cada componente puede usarse independientemente

### 🚀 Próximos Pasos Recomendados

- [ ] Implementar webhook de n8n
- [ ] Configurar parent_drive_folder_id dinámico desde Discord Message DB
- [ ] Añadir tests unitarios para nuevos componentes
- [ ] Implementar rate limiting para API de Notion
- [ ] Añadir métricas con Prometheus
- [ ] Configurar logs centralizados (ELK Stack)
- [ ] Implementar notificaciones de errores (Slack, email)
- [ ] Añadir soporte para más tipos de contenido (no solo YouTube)

### 📖 Documentación

- **Guía completa**: Ver `docs/NOTION_INTEGRATION.md`
- **API Docs**: http://localhost:8000/docs (cuando el servidor está corriendo)
- **Ejemplos de uso**: Incluidos en documentación de integración

---

## [Mejoras - 2025-11-16]

### ✨ Nuevas Características

#### Logging Estructurado
- Implementado sistema de logging profesional con módulo `logger_config.py`
- Logs se guardan automáticamente en directorio `logs/` con rotación automática (max 10MB, 5 backups)
- Formato detallado en archivos: timestamp, nombre del módulo, nivel, función, línea y mensaje
- Formato simple en consola para mantener UX amigable
- Niveles de logging: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Logs persistentes para debugging y auditorías

#### Configuración Centralizada
- Nuevo módulo `config.py` con todas las constantes y parámetros configurables
- Eliminación de valores hardcodeados en el código
- Fácil personalización de:
  - Modelos de Whisper (small para DiscordToDrive, medium para LocalTranscriber)
  - Parámetros de transcripción (temperatura, beam_size, thresholds)
  - Configuración de yt-dlp (reintentos, timeouts, user agents)
  - Formatos de nombres de archivos
  - Rutas de directorios

#### Sistema de Reintentos
- Decorador `@retry_on_failure` en `utils.py` para operaciones propensas a fallos
- Implementado en `upload_file_to_drive()` con exponential backoff
- Configurable: 3 reintentos por defecto con delay de 2 segundos
- Logs detallados de cada intento de reintento

#### Módulo de Utilidades
- Nuevo archivo `utils.py` con funciones comunes reutilizables:
  - `validate_ffmpeg()`: Verifica FFmpeg al inicio
  - `validate_credentials()`: Valida credenciales de Google Drive
  - `sanitize_filename()`: Sanitiza nombres de archivos
  - `ensure_directory_exists()`: Crea directorios si no existen
  - `safe_remove_file()`: Eliminación segura de archivos
  - `clean_temp_directory()`: Limpieza de directorios temporales
  - `is_audio_file()` / `is_video_file()`: Detección de tipos de archivo
  - `format_file_size()`: Formateo legible de tamaños

### 🔧 Mejoras de Código

#### DiscordToDrive.py
- Reemplazados todos los `print()` por `logger.info/error/warning()`
- Añadida validación de dependencias al inicio (FFmpeg, credentials, config)
- Uso de configuración centralizada desde `config.py`
- Docstrings mejorados en todas las funciones con tipos de parámetros y retornos
- Manejo de errores mejorado con `exc_info=True` para tracebacks completos
- Try-catch en uploads con logs detallados de errores
- Uso de funciones de utilidad para operaciones comunes
- Contador de progreso en procesamiento de videos (1/5, 2/5, etc.)
- Mensajes de inicio y fin más informativos

#### LocalTranscriber.py
- Mismas mejoras de logging que DiscordToDrive.py
- Eliminadas funciones duplicadas (ahora usan `utils.py`)
- Validación de FFmpeg al inicio
- Uso de configuración centralizada
- Docstrings mejorados
- Contador de progreso en procesamiento de archivos

### 🛠️ Arquitectura

```
Antes:
- DiscordToDrive.py (monolítico)
- LocalTranscriber.py (monolítico)

Después:
- DiscordToDrive.py (lógica principal)
- LocalTranscriber.py (lógica principal)
- config.py (configuración centralizada)
- logger_config.py (logging estructurado)
- utils.py (funciones comunes)
```

### 📊 Beneficios

1. **Debugging Mejorado**: Logs persistentes con timestamps y contexto completo
2. **Mantenibilidad**: Configuración centralizada y código más modular
3. **Confiabilidad**: Sistema de reintentos para operaciones de red
4. **Documentación**: Docstrings completos con tipos y descripciones
5. **Validación Temprana**: Verifica dependencias antes de iniciar procesamiento
6. **Reutilización**: Funciones comunes en módulo de utilidades
7. **Escalabilidad**: Arquitectura preparada para nuevas features

### ⚙️ Variables de Entorno Soportadas

- `WHISPER_DEVICE`: 'cpu' o 'cuda' (default: 'cpu')
- `LOG_LEVEL`: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL' (default: 'INFO')

### 📝 Notas de Compatibilidad

- ✅ Totalmente compatible con versión anterior
- ✅ Sin cambios en la interfaz de usuario
- ✅ Sin cambios en formato de archivos de entrada (LinksYT.json)
- ✅ Mantiene toda la funcionalidad existente
- ✅ Logs se crean automáticamente en directorio `logs/` (ya en .gitignore)

### 🚀 Próximas Mejoras Sugeridas

- [ ] Tests unitarios con pytest
- [ ] Progress bars con tqdm
- [ ] Rate limiting para Google Drive API
- [ ] Configuración vía archivo .env
- [ ] Módulos separados para yt-dlp, whisper y drive operations
- [ ] CLI mejorado con click o typer
- [ ] Integración con `channel_drive_mapping.json`
