# Integración con Notion y Sistema de Webhooks

## Descripción General

Este sistema automatiza el procesamiento de videos de YouTube provenientes de mensajes de Discord, transcribiéndolos y organizándolos en bases de datos de Notion.

## Arquitectura del Sistema

```
n8n (Monitoreo de Discord Message DB)
    ↓
    Webhook → FastAPI Server (puerto 8000)
    ↓
    Cola de Tareas → Celery + Redis
    ↓
    Worker Asíncrono:
        1. Descarga video/audio de YouTube
        2. Transcribe con Whisper
        3. Sube a Google Drive
        4. Crea página en Notion DB de destino
        5. Actualiza campo Transcript en Discord Message DB
    ↓
    Monitoreo → Flower Dashboard (puerto 5555)
```

## Componentes del Sistema

### 1. **Webhook Server** (FastAPI)
- **Puerto**: 8000
- **Endpoint principal**: `POST /webhook/process-video`
- **Autenticación**: Header `X-Webhook-Secret`
- **Función**: Recibe notificaciones de n8n y encola tareas

### 2. **Cola de Tareas** (Celery + Redis)
- **Broker**: Redis (puerto 6379)
- **Función**: Gestiona procesamiento asíncrono de videos en cola
- **Características**:
  - Reintentos automáticos (3 intentos)
  - Timeout de 1 hora por tarea
  - Exponential backoff
  - Procesamiento secuencial (FIFO)

### 3. **Worker** (Celery Worker)
- **Modo**: Procesamiento secuencial (1 video a la vez)
- **Concurrencia**: 1 (optimizado para CPU)
- **Función**: Ejecuta el procesamiento completo de videos
- **Nota**: Para GPU con suficiente VRAM, se puede aumentar la concurrencia a 2-4

### 4. **Dashboard** (Flower)
- **Puerto**: 5555
- **URL**: http://localhost:5555
- **Función**: Monitoreo en tiempo real de tareas

## Configuración de Bases de Datos

### Discord Message Database (Origen)
- **ID**: `28bdaf66daf7816383e6ce8390b0a866`
- **Función**: Base de datos monitoreada por n8n
- **Campos relevantes**:
  - `Channel`: Canal de Discord
  - `Attached URL`: URL del video de YouTube
  - `Transcript`: Se actualiza con URL de página de Notion creada

### Bases de Datos de Destino

#### Paradise Island Videos Database
- **ID**: `287daf66daf7807290d0fb514fdf4d86`
- **Canal**: `🎙・market-outlook`
- **Campos**:
  - Name (Title): "YYYY-MM-DD - Título del video"
  - Date: Fecha de publicación del video
  - Video Link: URL de YouTube
  - Google drive Folder: URL de carpeta en Drive
  - Drive Link: URL del video MP4 en Drive
  - Discord Channel: Nombre del canal

#### Docs Videos Database
- **ID**: `287daf66daf780fb89f7dd15bac7aa2a`
- **Canal**: `🎙・market-analysis-streams`
- **Campos**: Mismos que Paradise Island

## Mapeo de Canales

El mapeo se configura en `config/notion_config.py`:

```python
CHANNEL_TO_DATABASE_MAPPING = {
    "🎙・market-outlook": {
        "database_id": "287daf66daf7807290d0fb514fdf4d86",
        "database_name": "Paradise Island Videos Database"
    },
    "🎙・market-analysis-streams": {
        "database_id": "287daf66daf780fb89f7dd15bac7aa2a",
        "database_name": "Docs Videos Database"
    }
}
```

## Instalación

### 1. Instalar Dependencias

```bash
# Instalar dependencias de Python
pip install -r requirements.txt

# Verificar que Docker esté instalado
docker --version
```

### 2. Configurar Variables de Entorno

```bash
# Copiar archivo de ejemplo
cp .env.example .env

# Editar .env y configurar:
nano .env
```

**Variables críticas**:
```bash
# Token de Notion (REQUERIDO)
NOTION_TOKEN=ntn_tu_token_aqui

# Secreto para webhooks (cambiar en producción)
WEBHOOK_SECRET=tu_secreto_seguro_aqui

# Configuración de Redis (por defecto está bien)
REDIS_URL=redis://localhost:6379/0
```

### 3. Configurar Google Drive API

Sigue las instrucciones del README principal para:
1. Obtener `credentials.json`
2. Autorizar la aplicación (genera `token.pickle`)

## Uso

### Opción 1: Iniciar Todo el Sistema (Recomendado)

```bash
./scripts/start_all.sh
```

Esto inicia:
- Redis (Docker)
- Celery Worker
- Flower Dashboard
- Webhook Server

### Opción 2: Iniciar Componentes Individualmente

```bash
# Terminal 1: Redis
docker-compose up redis

# Terminal 2: Celery Worker
./scripts/start_worker.sh

# Terminal 3: Flower Dashboard (opcional)
./scripts/start_flower.sh

# Terminal 4: Webhook Server
./scripts/start_webhook_server.sh
```

### Detener el Sistema

```bash
./scripts/stop_all.sh
```

## Configuración de n8n

### Workflow de n8n

1. **Trigger**: Polling de Discord Message Database
2. **Filtro**: Verificar que `Channel` esté en lista válida y `Attached URL` contenga YouTube
3. **Webhook**: POST a `http://tu-servidor:8000/webhook/process-video`

### Payload del Webhook

```json
{
  "discord_entry_id": "page_id_de_notion",
  "youtube_url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "channel": "🎙・market-outlook",
  "parent_drive_folder_id": "ID_carpeta_drive_opcional"
}
```

### Headers Requeridos

```
Content-Type: application/json
X-Webhook-Secret: tu_secreto_del_env
```

## Endpoints de la API

### Procesar Video

```bash
POST /webhook/process-video
```

**Payload**:
```json
{
  "discord_entry_id": "28bdaf66daf7816383e6ce8390b0a866",
  "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "channel": "🎙・market-outlook"
}
```

**Respuesta**:
```json
{
  "status": "queued",
  "message": "Video encolado para procesamiento",
  "task_id": "abc123-task-id",
  "timestamp": "2025-11-16T10:30:00Z",
  "data": {
    "youtube_url": "...",
    "channel": "...",
    "discord_entry_id": "..."
  }
}
```

### Verificar Estado de Tarea

```bash
GET /task/{task_id}
```

**Respuesta**:
```json
{
  "task_id": "abc123-task-id",
  "status": "SUCCESS",
  "timestamp": "2025-11-16T10:35:00Z",
  "result": {
    "status": "success",
    "youtube_url": "...",
    "video_title": "...",
    "notion_page_url": "https://notion.so/...",
    "drive_folder_url": "https://drive.google.com/...",
    "drive_video_url": "https://drive.google.com/..."
  }
}
```

### Health Check

```bash
GET /health
```

### Documentación Interactiva

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Monitoreo con Flower

Accede al dashboard en: **http://localhost:5555**

### Características:
- **Tasks**: Ver tareas en cola, en progreso, completadas y fallidas
- **Workers**: Monitorear workers activos
- **Broker**: Estado de Redis
- **Monitor**: Gráficos en tiempo real
- **Logs**: Ver logs de tareas

### Autenticación (Opcional)

Para habilitar autenticación en Flower:

```bash
# En .env
FLOWER_BASIC_AUTH=admin:contraseña_segura
```

## Flujo Completo de Procesamiento

```
1. n8n detecta nueva entrada con video de YouTube
   ↓
2. n8n envía webhook a FastAPI server
   ↓
3. FastAPI valida datos y encola tarea en Celery
   ↓
4. Worker toma tarea de la cola
   ↓
5. Worker descarga video y audio de YouTube
   ↓
6. Worker transcribe audio con Whisper
   ↓
7. Worker crea carpeta en Google Drive
   ↓
8. Worker sube video, audio y transcripción a Drive
   ↓
9. Worker crea página en Notion DB de destino
   ↓
10. Worker actualiza campo Transcript en Discord Message DB
    ↓
11. Tarea marcada como completada en Flower
```

## Manejo de Errores

### Reintentos Automáticos

Las tareas se reintentan automáticamente:
- **Máximo de reintentos**: 3
- **Delay inicial**: 60 segundos
- **Exponential backoff**: Sí
- **Jitter**: Sí (evita sobrecarga)

### Logs

Los logs se guardan en:
- **Worker**: `logs/celery_worker.log`
- **Flower**: `logs/flower.log`
- **Application logs**: `logs/src_*_YYYYMMDD.log`

### Monitoreo de Errores

En Flower, puedes ver:
- Tareas fallidas con stack trace
- Número de reintentos
- Tiempo de ejecución
- Errores específicos

## Personalización

### Añadir Nuevos Canales

Edita `config/notion_config.py`:

```python
CHANNEL_TO_DATABASE_MAPPING = {
    "🎙・market-outlook": { ... },
    "🎙・market-analysis-streams": { ... },
    # Nuevo canal
    "📊・nuevo-canal": {
        "database_id": "ID_DE_TU_DATABASE",
        "database_name": "Nombre de la Database"
    }
}
```

### Ajustar Timeouts

En `.env`:

```bash
# Tiempo máximo de procesamiento (1 hora)
CELERY_TASK_TIME_LIMIT=3600

# Tiempo suave (55 minutos)
CELERY_TASK_SOFT_TIME_LIMIT=3300
```

### Ajustar Concurrencia

**Por defecto**: El sistema procesa 1 video a la vez (optimizado para CPU).

#### Opción 1: Usando Variable de Entorno (Recomendado)

```bash
# En .env
CELERY_WORKER_CONCURRENCY=1  # Para CPU (por defecto)
CELERY_WORKER_CONCURRENCY=2  # Para GPU con VRAM suficiente
CELERY_WORKER_CONCURRENCY=4  # Para GPU potente (RTX 4090, etc.)
```

#### Opción 2: Editando Script Manualmente

```bash
# Editar scripts/start_worker.sh
celery -A src.celery_app worker \
    --concurrency=1  # CPU: Solo 1 video a la vez (recomendado)
    # --concurrency=2  # GPU: 2 videos simultáneos
    # --concurrency=4  # GPU potente: 4 videos simultáneos
```

**⚠️ Importante**:
- **CPU**: SIEMPRE usar `--concurrency=1` para evitar saturar el procesador
- **GPU**: Verificar VRAM disponible antes de aumentar concurrencia
  - Modelo `small`: ~2GB VRAM por video
  - Modelo `medium`: ~5GB VRAM por video
  - RTX 3060 (12GB): max 2 videos simultáneos con `medium`
  - RTX 4090 (24GB): max 4 videos simultáneos con `medium`

## Troubleshooting

### Redis no está disponible

```bash
# Verificar que Redis esté corriendo
docker ps | grep redis

# Reiniciar Redis
docker-compose restart redis
```

### Worker no procesa tareas

```bash
# Verificar estado del worker
celery -A src.celery_app inspect active

# Ver workers registrados
celery -A src.celery_app inspect registered
```

### Errores de autenticación en Notion

```bash
# Verificar token en .env
echo $NOTION_TOKEN

# Verificar permisos de integración en Notion:
# - La integración debe tener acceso a las 3 bases de datos
# - Discord Message DB (lectura/escritura)
# - Paradise Island DB (escritura)
# - Docs Videos DB (escritura)
```

### Webhook no recibe peticiones

```bash
# Verificar que el servidor esté corriendo
curl http://localhost:8000/health

# Verificar logs
tail -f logs/*.log

# Verificar firewall/puertos
sudo ufw status
```

## Consideraciones de Producción

### Seguridad

1. **Cambiar WEBHOOK_SECRET** en `.env`
2. **Habilitar HTTPS** con nginx/reverse proxy
3. **Configurar autenticación en Flower**
4. **Restringir acceso a Redis** (no exponer puerto 6379 públicamente)

### Escalabilidad

1. **Múltiples workers**:
   ```bash
   # Iniciar múltiples workers
   celery -A src.celery_app worker --concurrency=4 -n worker1@%h &
   celery -A src.celery_app worker --concurrency=4 -n worker2@%h &
   ```

2. **Redis en servidor dedicado**:
   ```bash
   REDIS_URL=redis://servidor-redis:6379/0
   ```

3. **Persistent Redis**:
   - Docker Compose ya tiene volumen persistente
   - Para producción, considera Redis managed (AWS ElastiCache, etc.)

### Monitoreo

1. **Logs centralizados**: Integrar con ELK Stack o similar
2. **Alertas**: Configurar alertas en Flower para tareas fallidas
3. **Métricas**: Exponer métricas de Celery a Prometheus

## Recursos Adicionales

- **Celery Documentation**: https://docs.celeryq.dev/
- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **Notion API**: https://developers.notion.com/
- **Flower Documentation**: https://flower.readthedocs.io/
