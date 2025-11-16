# YouTube to Google Drive Automation

![image](https://github.com/user-attachments/assets/921fa3bc-3384-4f14-9710-ea04fe08a448)

Sistema automatizado para descargar videos de YouTube, transcribirlos con **Faster-Whisper** y organizarlos en Google Drive.

---

## 📋 ¿Qué Hace?

✅ **Descarga** videos y audio desde YouTube usando `yt-dlp`  
✅ **Transcribe** automáticamente el audio con Faster-Whisper (compatible Python 3.14)  
✅ **Sube** todo a Google Drive: video, audio, transcripción y enlace original  
✅ **Organiza** por carpetas automáticas con fecha y título  
✅ **Evita duplicados** verificando contenido existente en Drive  
✅ **Visualización en tiempo real** de la transcripción mientras procesa

---

## 🚀 Nueva Implementación: Faster-Whisper

### ¿Qué Cambió?

Migramos de **OpenAI Whisper** (clásico) a **Faster-Whisper** para:

- ✅ **Compatibilidad Python 3.14** (Whisper clásico solo soporta hasta 3.13)
- ✅ **2.67x más rápido en CPU** (45 min vs 120 min para video de 2h)
- ✅ **3-4x más rápido en GPU** (12-15 min con CUDA configurado)
- ✅ **50% menos uso de VRAM** (1GB vs 2GB para modelo medium)
- ✅ **Transcripción en vivo**: ves el texto aparecer en tiempo real

### Rendimiento Medido

| Configuración | Video 2h | Velocidad |
|---------------|----------|-----------|
| CPU (actual) | **45 min** | 2.67x más rápido |
| GPU (RTX 3060) | **12-15 min** | 8-10x más rápido |

📊 **Ver reporte completo**: [MIGRATION_REPORT.md](./MIGRATION_REPORT.md)

## 🏗️ Estructura del Proyecto- `LocalTranscriber.py`: herramienta CLI para transcribir en lote archivos de audio/video almacenados en `input/`, utilizando Whisper (`medium` por defecto) y FFmpeg para la extracción de audio.

- Paquete `youtube_processor/`: capa de orquestación empresarial. Incluye:

```  - `config.ConfigManager`: centraliza variables de entorno (`.env`), valida rutas y credenciales, y prepara directorios de trabajo y logging.

.  - `utils.JSONGenerator`: genera y actualiza archivos `*_youtube_videos.json` con el estado por canal (pendiente, en proceso, completado, error).

├── DiscordToDrive.py          # Script principal de procesamiento  - `utils.ProcessingCoordinator` y `DiscordToDriveExecutor`: coordinan la ejecución secuencial de canales, construyen `LinksYT.json` compatibles, lanzan `DiscordToDrive.py` como subproceso, aplican reintentos y registran resultados.

├── LocalTranscriber.py        # Herramienta CLI para transcripción local  - `utils.ErrorHandler`: clasifica errores (sistema de archivos, subprocessos, API, etc.), aplica políticas de escalamiento y alimenta bitácoras en `logs/`.

├── requirements.txt           # Dependencias de Python- Directorios auxiliares:

├── channel_drive_mapping.json # Mapeo de canales a carpetas de Drive  - `temp_downloads/`: staging local temporal para descargas antes de subirlas a Drive.

├── LinksYT.json              # Archivo de configuración de entrada  - `channel_jsons/`, `logs/`, `output/`, `videos/`: directorios creados automáticamente para resultados, bitácoras y archivos derivados.

├── credentials.json          # Credenciales de Google Drive (no incluido)

├── .env                      # Variables de entorno (no incluido)### Flujo end-to-end (DiscordToDrive)

│1. Carga configuración desde `LinksYT.json` y valida la presencia de `parent_folder_id` y URLs.

├── youtube_processor/        # Paquete de orquestación avanzada2. Inicializa credenciales de Google Drive (`credentials.json` + `token.pickle`), construye el servicio `files()` con soporte para unidades compartidas.

│   ├── config/              # Gestión de configuración3. Verifica GPU mediante PyTorch, carga el modelo Whisper `small` en GPU si está disponible o en CPU como respaldo.

│   ├── extraction/          # Extracción de datos desde Notion4. Para cada URL:

│   └── utils/               # Utilidades (coordinador, JSON, errores)   - Obtiene título y fecha de publicación con `yt_dlp` usando clientes móviles (evita SABR).

│   - Sanitiza el título y crea una carpeta `YYYY-MM-DD - Título` en Drive bajo `parent_folder_id`.

├── channel_jsons/           # JSONs de estado por canal (generados)   - Descarga video (`mp4`) y audio (`mp3`), aplicando renombre consistente con la fecha; crea archivo de enlace (`Link.txt`).

├── logs/                    # Archivos de log (generados)   - Transcribe el audio en texto con Whisper y guarda la transcripción en UTF-8.

├── input/                   # Archivos de entrada para LocalTranscriber   - Antes de subir, consulta Drive para prevenir duplicados en la carpeta destino.

└── output/                  # Salida de transcripciones   - Sube video, audio, transcripción y archivo de enlace; elimina artefactos locales tras cada subida.

```5. Limpia `temp_downloads/` si queda vacío y registra la finalización del lote.



## 🚀 Instalación### Dependencias clave

- **Python** 3.10+ recomendado.

### Requisitos Previos- Librerías Python: `yt_dlp`, `google-api-python-client`, `google-auth`, `google-auth-oauthlib`, `whisper` (openai-whisper), `torch`, `python-dotenv` (para `youtube_processor`), `notion-client` (opcional), `ffmpeg-python` (opcional según scripts).

- Binarios externos: `ffmpeg` (requerido para `LocalTranscriber.py` y recomendable para `yt_dlp`), GPU con CUDA opcional para acelerar Whisper.

- **Python** 3.10 o superior- Servicios externos:

- **FFmpeg** (requerido para procesamiento de video/audio)  - **Google Drive API** con alcance `https://www.googleapis.com/auth/drive`; los tokens se almacenan en `token.pickle` (o `token.json` en orquestaciones).

  - **YouTube** a través de `yt_dlp` sin API oficial.

#### Instalar FFmpeg  - **Notion API** (opcional) para poblar JSON intermedios cuando se usan los orquestadores.



**Linux (Ubuntu/Debian)**:### Configuración y credenciales

```bash- `.env`: concentra tokens de Notion, fechas de corte, rutas de scripts y ajustes de procesamiento. Debe mantenerse fuera del control de versiones.

sudo apt update- `credentials.json`: credenciales OAuth 2.0 descargadas desde Google Cloud (tipo escritorio). Nunca debe compartirse públicamente.

sudo apt install ffmpeg- `token.pickle` / `token.json`: generados automáticamente tras la primera autenticación; contienen tokens de actualización. Conservarlos seguros evita reautenticaciones manuales.

```- `LinksYT.json`: archivo de entrada manual o generado automáticamente; conviene validar sus rutas antes de cada ejecución automatizada.

- `channel_drive_mapping.json`: repositorio de mapeos persistentes; admite regeneración automática si `auto_create_folders` está en `true`.

**macOS**:

```bash### Logging, observabilidad y resiliencia

brew install ffmpeg- `DiscordToDrive.py` escribe mensajes ricos en emoji para identificar eventos (creación de carpetas, descargas, cargas, advertencias y errores).

```- `youtube_processor` emplea logging estructurado en `logs/youtube_processor.log` con rotación configurable (`LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`).

- Mecanismos de reintento:

**Windows**: Descargar desde [ffmpeg.org](https://ffmpeg.org/download.html)  - `yt_dlp` se configura con 10 reintentos en descargas y forzado a IPv4.

  - El coordinador puede reintentar hasta `MAX_RETRY_ATTEMPTS` por canal.

### Instalación del Proyecto- Manejo de errores:

  - Verificaciones previas de existencia de archivos y permisos; el flujo continúa con otros videos ante fallas puntuales.

1. **Clonar el repositorio**:  - Limpieza defensiva tras subidas para evitar acumulación local.

```bash

git clone <URL_DEL_REPOSITORIO>### Consideraciones de seguridad y operación

cd Python_AutomatizacionDiscord- Aislar las credenciales (Google, Notion) en secretos y restringir permisos al mínimo necesario.

```- Configurar políticas de retención en carpetas de Drive si se manejan datos sensibles.

- Revisar cuotas de Google Drive y límites de `yt_dlp` en ejecuciones masivas.

2. **Crear entorno virtual**:- Para despliegues en servidores:

```bash  - Ejecutar dentro de entornos virtuales dedicados.

python -m venv .venv  - Programar trabajos (cron/systemd) que invoquen al coordinador y consoliden logs.

source .venv/bin/activate  # En Windows: .venv\Scripts\activate  - Supervisar uso de GPU/CPU durante transcripciones prolongadas.

```

---

3. **Instalar dependencias**:

```bash## Guía de Uso (para cualquier persona)

pip install -r requirements.txt

```### Antes de empezar

- **Cuenta de Google** con acceso a la carpeta de Drive donde se almacenarán los videos.

## ⚙️ Configuración- **Python** instalado (3.10 recomendado). Verifica con `python --version`.

- **FFmpeg** instalado y disponible en PATH (`ffmpeg -version`).

### 1. Configurar Google Drive API- (Opcional) GPU NVIDIA si se desea aceleración de Whisper.



1. Crear un proyecto en [Google Cloud Console](https://console.cloud.google.com/)### Preparar el entorno

2. Habilitar la **Google Drive API**1. **Descargar el proyecto**  

3. Crear credenciales **OAuth 2.0** de tipo "Aplicación de escritorio"   - Clonar con `git clone` o descargar el ZIP desde tu plataforma de código y descomprimirlo.

4. Descargar el archivo JSON de credenciales y guardarlo como `credentials.json` en la raíz del proyecto2. **Crear un entorno virtual (opcional pero recomendado)**  

   ```bash

### 2. Configurar Variables de Entorno (Opcional)   python -m venv .venv

   source .venv/bin/activate  # En Windows: .venv\Scripts\activate

Si usas el paquete `youtube_processor` con integración de Notion:   ```

3. **Instalar dependencias**  

```bash   ```bash

cp .env.example .env   pip install yt_dlp google-api-python-client google-auth google-auth-oauthlib openai-whisper torch python-dotenv notion-client

```   ```

   - Si no cuentas con GPU, instala la versión CPU de PyTorch (`pip install torch==2.2.2+cpu -f https://download.pytorch.org/whl/torch_stable.html`).

Editar `.env` con tus valores:4. **Configurar Google Drive**  

```env   - Crea un proyecto en [Google Cloud Console](https://console.cloud.google.com/).

# Notion API   - Habilita la **Google Drive API**.

NOTION_TOKEN=secret_tu_token_aqui   - Crea credenciales de **OAuth 2.0 de escritorio** y descarga el archivo `credentials.json` en la raíz del proyecto.

NOTION_DATABASE_ID=tu_database_id_32_caracteres   - La primera vez que ejecutes el script se abrirá el navegador para autorizar el acceso; se generará `token.pickle` automáticamente.

5. **Definir las URLs a procesar**  

# Procesamiento   - Edita `LinksYT.json`:

START_DATE=2025-01-01     - `parent_folder_id`: ID de la carpeta de Drive destino (abre la carpeta en la web y toma el valor tras `folders/` en la URL).

BATCH_SIZE_PER_EXECUTION=10     - `video_urls`: lista de enlaces de YouTube o transmisiones en vivo.

MAX_RETRY_ATTEMPTS=3

### Ejecutar la automatización principal

# Google Drive1. Asegúrate de que `credentials.json` y `LinksYT.json` existen y contienen información válida.

GOOGLE_DRIVE_CREDENTIALS=credentials.json2. Ejecuta:

GOOGLE_DRIVE_TOKEN=token.pickle   ```bash

CHANNEL_MAPPING_FILE=./channel_drive_mapping.json   python DiscordToDrive.py

AUTO_CREATE_DRIVE_FOLDERS=true   ```

3. Durante la ejecución verás mensajes de estado: creación de carpetas, descargas, cargas, transcripciones y cualquier advertencia.

# Rutas4. Al finalizar, la carpeta de Drive tendrá subcarpetas por video con:

DISCORDTODRIVE_SCRIPT=./DiscordToDrive.py   - Video en `.mp4`.

JSON_OUTPUT_DIR=./channel_jsons/   - Audio en `.mp3`.

   - Transcripción en `.txt`.

# Logging   - Archivo `Link.txt` con la URL original.

LOG_LEVEL=INFO5. Verifica que `temp_downloads/` esté vacío. Si quedan archivos, puedes eliminarlos manualmente una vez confirmada la subida.

LOG_FILE=./logs/youtube_processor.log

```### Uso opcional del transcriptor local

- Para transcribir archivos propios sin subirlos a Drive:

## 📖 Uso  1. Coloca los videos o audios en `input/`.

  2. Ejecuta:

### Modo 1: Procesamiento Simple de URLs     ```bash

     python LocalTranscriber.py --lang es --input input --output output

Este es el modo más sencillo para procesar una lista de videos.     ```

     - Omite `--lang` si quieres detección automática de idioma.

1. **Crear archivo `LinksYT.json`**:  3. Revisa las transcripciones en `output/`. Se generará una copia del audio si el origen era video.

```json

{### Integraciones avanzadas (opcional)

  "parent_folder_id": "ID_DE_TU_CARPETA_DRIVE",- Completa el archivo `.env` con:

  "video_urls": [  - `NOTION_TOKEN` y `NOTION_DATABASE_ID` si necesitas poblar listas de reproducción desde Notion.

    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  - Ajustes como `START_DATE`, `BATCH_SIZE_PER_EXECUTION`, `DISCORDTODRIVE_SCRIPT`.

    "https://www.youtube.com/watch?v=9bZkp7q19f0"- Ejecuta los orquestadores dentro de `youtube_processor/` para generar JSON por canal y lanzar procesos en lote. Revisa los logs en `logs/` para monitoreo.

  ]

}### Resolución de problemas comunes

```- **Google pide autenticación cada vez**: elimina `token.pickle` solo si cambiaste de cuenta; de lo contrario, revísalo en `token.pickle` (carpeta raíz).

- **Error de `FFmpeg` o audio inexistente**: instala FFmpeg y asegúrate de que `yt_dlp` puede localizarlo (`ffmpeg -version`).

2. **Ejecutar el script**:- **`CUDA out of memory`**: selecciona un modelo Whisper más pequeño (`tiny`, `base`) o fuerza ejecución en CPU editando el script.

```bash- **Límites de Drive**: monitorea tu cuota; el script omite cargas duplicadas, pero podrías topar límites diarios si ejecutas lotes grandes.

python DiscordToDrive.py- **Errores al cargar configuraciones**: el `ConfigManager` detendrá la ejecución si faltan variables críticas; revisa `.env` y rutas indicadas en los mensajes.

```

### Mantenimiento y buenas prácticas

La primera vez se abrirá un navegador para autorizar el acceso a Google Drive.- Mantén este repositorio fuera de carpetas sincronizadas con Drive/Dropbox para evitar conflictos con archivos temporales.

- Programa revisiones periódicas de `channel_drive_mapping.json` y `LinksYT.json` si cambian las rutas de almacenamiento.

**Resultado**: Para cada video se crea una carpeta en Drive con:- Realiza respaldos de `credentials.json` y `token.pickle` en un almacén seguro.

- Video en formato `.mp4`- Documenta internamente qué videos se procesan para evitar duplicidades entre equipos.

- Audio en formato `.mp3`
- Transcripción en formato `.txt`
- Archivo con el enlace original

### Modo 2: Transcripción Local

Transcribe archivos de video/audio locales sin subirlos a Drive.

1. **Colocar archivos** en la carpeta `input/`
2. **Ejecutar el transcriptor**:
```bash
# Con detección automática de idioma
python LocalTranscriber.py

# Especificando idioma
python LocalTranscriber.py --lang es

# Especificando directorios
python LocalTranscriber.py --input ./mis_videos --output ./mis_transcripciones
```

**Resultado**: Transcripciones en la carpeta `output/`

### Modo 3: Orquestación con Notion (Avanzado)

Para procesamiento masivo con integración de Notion:

1. **Configurar variables de entorno** (ver sección de configuración)
2. **Ejecutar el organizador de canales**:
```bash
python -m youtube_processor.utils.channel_organizer
```

Este modo:
- Extrae videos de una base de datos de Notion
- Organiza por canal
- Genera JSONs de estado
- Ejecuta procesamiento secuencial
- Gestiona reintentos y errores

## 🛠️ Componentes Principales

### DiscordToDrive.py

Script principal que:
- Descarga videos y audios desde YouTube
- Transcribe el audio usando Whisper
- Sube todo a Google Drive organizadamente
- Evita duplicados verificando contenido existente

**Opciones de Whisper**: El modelo por defecto es `small`. Puedes cambiarlo en el código:
- `tiny`: Más rápido, menos preciso
- `base`: Balance entre velocidad y precisión
- `small`: **Por defecto** - Buena precisión
- `medium`: Mayor precisión (requiere más RAM/VRAM)
- `large`: Máxima precisión (muy lento sin GPU)

### LocalTranscriber.py

Herramienta standalone para transcripción local:
- Extrae audio de videos con FFmpeg
- Transcribe usando Whisper (modelo `medium` por defecto)
- Soporta detección automática de idioma
- Procesa múltiples archivos en lote

### youtube_processor/

Paquete de orquestación empresarial:

- **config/ConfigManager**: Gestión centralizada de configuración
- **extraction/NotionDataExtractor**: Extracción de datos desde Notion
- **utils/JSONGenerator**: Generación y gestión de archivos JSON de estado
- **utils/ChannelOrganizer**: Organización de videos por canal
- **utils/ProcessingCoordinator**: Coordinación de procesamiento secuencial
- **utils/ErrorHandler**: Manejo robusto de errores con reintentos

## 🔍 Resolución de Problemas

### FFmpeg no encontrado
```
Error: ffmpeg not found
```
**Solución**: Instalar FFmpeg y asegurarse de que está en el PATH del sistema.

### CUDA out of memory
```
Error: CUDA out of memory
```
**Solución**: 
- Usar un modelo más pequeño (`tiny`, `base`, `small`)
- El script intentará automáticamente usar CPU como fallback
- Cerrar otras aplicaciones que usen la GPU

### Error de autenticación de Google
```
Error: Invalid credentials
```
**Solución**:
- Verificar que `credentials.json` existe y es válido
- Eliminar `token.pickle` para forzar re-autenticación
- Verificar permisos de la API en Google Cloud Console

### Problemas con Notion API
```
Error: 401 Unauthorized
```
**Solución**:
- Verificar que `NOTION_TOKEN` es válido
- Verificar que el token tiene acceso a la base de datos
- El token debe comenzar con `secret_` o `ntn_`

## 📊 Estructura de Datos

### LinksYT.json
```json
{
  "parent_folder_id": "1a2b3c4d5e6f7g8h9i0j",
  "video_urls": [
    "https://www.youtube.com/watch?v=VIDEO_ID"
  ]
}
```

### channel_drive_mapping.json
```json
{
  "mappings": {
    "canal-nombre": "carpeta_drive_id_1",
    "otro-canal": "carpeta_drive_id_2"
  },
  "auto_create_folders": true,
  "default_parent_folder": "carpeta_padre_id",
  "last_updated": "2025-01-01T00:00:00Z"
}
```

### Channel JSON (generado automáticamente)
```json
{
  "metadata": {
    "channel_name": "general",
    "drive_folder_id": "1a2b3c4d5e6f7g8h9i0j",
    "status": "processing",
    "total_videos": 5,
    "completed_videos": 3
  },
  "videos": [
    {
      "youtube_url": "https://www.youtube.com/watch?v=VIDEO_ID",
      "processing_status": {
        "fully_completed": true
      }
    }
  ]
}
```

## 🔒 Seguridad

**IMPORTANTE**: Los siguientes archivos contienen información sensible y NO deben subirse a repositorios públicos:

- `credentials.json` - Credenciales de Google OAuth
- `token.pickle` / `token.json` - Tokens de acceso de Google
- `.env` - Variables de entorno y tokens de API
- `cookies.txt` - Cookies de sesión (si se usan)

El archivo `.gitignore` está configurado para excluir estos archivos automáticamente.

## 📝 Logs

Los logs se generan automáticamente en:
- `logs/youtube_processor.log` - Logs del orquestador
- Salida de consola con emojis para fácil identificación

Niveles de log:
- `INFO` ✅ - Operaciones exitosas
- `WARNING` ⚠️ - Advertencias no críticas
- `ERROR` ❌ - Errores manejables
- `CRITICAL` 🚨 - Errores críticos del sistema

## 🤝 Contribuir

Para contribuir al proyecto:

1. Fork el repositorio
2. Crear una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abrir un Pull Request

## 📄 Licencia

Este proyecto es de código abierto y está disponible bajo la licencia MIT.

## ✨ Créditos

Desarrollado para automatizar el procesamiento de contenido de YouTube con transcripción y almacenamiento en la nube.

**Tecnologías principales**:
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Descarga de YouTube
- [OpenAI Whisper](https://github.com/openai/whisper) - Transcripción de audio
- [Google Drive API](https://developers.google.com/drive) - Almacenamiento en la nube
- [Notion API](https://developers.notion.com/) - Gestión de datos (opcional)
