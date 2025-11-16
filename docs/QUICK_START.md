# Quick Start - Sistema de Webhooks con Notion

Guía rápida para poner en marcha el sistema de procesamiento automático de videos.

## Requisitos Previos

- Python 3.10+
- Docker y Docker Compose
- FFmpeg instalado
- Credenciales de Google Drive (`credentials.json`)
- Token de integración de Notion

## Instalación en 5 Pasos

### 1. Instalar Dependencias

```bash
# Clonar repositorio (si no lo has hecho)
git clone https://github.com/esedesofiaaa/Youtube-to-notion-whisper.git
cd Youtube-to-notion-whisper

# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Configurar Variables de Entorno

```bash
# Copiar archivo de ejemplo
cp .env.example .env

# Editar .env
nano .env
```

**Configuración mínima**:
```bash
# Token de Notion (OBLIGATORIO)
NOTION_TOKEN=ntn_tu_token_aqui

# Secreto de webhook (cambiar en producción)
WEBHOOK_SECRET=mi_secreto_seguro_123

# Opcional: Configuración de Whisper
WHISPER_DEVICE=cpu  # o 'cuda' si tienes GPU
WHISPER_MODEL_DEFAULT=small
```

### 3. Configurar Google Drive

1. Coloca `credentials.json` en la raíz del proyecto
2. La primera vez que ejecutes el sistema, se abrirá un navegador para autorizar
3. Esto generará `token.pickle` automáticamente

### 4. Verificar Configuración de Notion

Asegúrate de que tu integración de Notion tenga acceso a las 3 bases de datos:

- **Discord Message Database** (lectura/escritura)
- **Paradise Island Videos Database** (escritura)
- **Docs Videos Database** (escritura)

Para dar acceso:
1. Abre cada base de datos en Notion
2. Click en "..." → "Add connections"
3. Selecciona tu integración

### 5. Iniciar el Sistema

```bash
# Opción A: Iniciar todo con un comando
./scripts/start_all.sh

# Opción B: Iniciar componentes individualmente
# Terminal 1: Redis
docker-compose up redis

# Terminal 2: Worker
./scripts/start_worker.sh

# Terminal 3: Flower (opcional, para monitoreo)
./scripts/start_flower.sh

# Terminal 4: Webhook Server
./scripts/start_webhook_server.sh
```

## Verificar que Funciona

### 1. Health Check

```bash
curl http://localhost:8000/health
```

Deberías ver:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-16T10:00:00Z"
}
```

### 2. Prueba de Celery

```bash
curl -X POST "http://localhost:8000/test/task?message=Hola Celery"
```

Deberías ver:
```json
{
  "status": "queued",
  "message": "Tarea de prueba encolada",
  "task_id": "abc123...",
  "timestamp": "..."
}
```

### 3. Verificar Estado en Flower

Abre en tu navegador: http://localhost:5555

Deberías ver el dashboard con:
- Workers activos
- Tareas en cola
- Tareas completadas

## Probar Procesamiento de Video

### Opción 1: Con curl

```bash
curl -X POST "http://localhost:8000/webhook/process-video" \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: mi_secreto_seguro_123" \
  -d '{
    "discord_entry_id": "tu_page_id_de_notion",
    "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "channel": "🎙・market-outlook",
    "parent_drive_folder_id": "tu_folder_id_de_drive"
  }'
```

### Opción 2: Con la documentación interactiva

1. Abre http://localhost:8000/docs
2. Busca el endpoint `POST /webhook/process-video`
3. Click en "Try it out"
4. Llena los campos y ejecuta

## Monitorear el Progreso

### Ver Estado de la Tarea

```bash
# Reemplaza TASK_ID con el ID recibido en la respuesta
curl http://localhost:8000/task/TASK_ID
```

### En Flower Dashboard

1. Abre http://localhost:5555
2. Click en "Tasks"
3. Busca tu tarea por ID
4. Verás:
   - Estado actual
   - Progreso
   - Logs
   - Tiempo de ejecución
   - Errores (si hay)

## Configurar n8n

### Crear Workflow en n8n

1. **Trigger**: Cron/Schedule (cada X minutos)
2. **Notion Node**: Query Database
   - Database ID: Discord Message Database
   - Filter: Channel = "🎙・market-outlook" OR "🎙・market-analysis-streams"
   - Filter: Attached URL contains "youtube.com"
   - Filter: Transcript is empty
3. **HTTP Request Node**:
   - Method: POST
   - URL: `http://tu-servidor:8000/webhook/process-video`
   - Headers:
     - `Content-Type`: `application/json`
     - `X-Webhook-Secret`: tu_secreto
   - Body:
     ```json
     {
       "discord_entry_id": "{{ $json.id }}",
       "youtube_url": "{{ $json.properties['Attached URL'].url }}",
       "channel": "{{ $json.properties['Channel'].select.name }}",
       "parent_drive_folder_id": "TU_FOLDER_ID"
     }
     ```

## Detener el Sistema

```bash
# Opción A: Detener todo
./scripts/stop_all.sh

# Opción B: Detener componentes individuales
# Ctrl+C en cada terminal

# Detener Redis
docker-compose down
```

## Logs y Debugging

### Ver Logs

```bash
# Logs del worker
tail -f logs/celery_worker.log

# Logs de Flower
tail -f logs/flower.log

# Logs de la aplicación
tail -f logs/*.log
```

### Problemas Comunes

#### Redis no conecta

```bash
# Verificar que Redis esté corriendo
docker ps | grep redis

# Reiniciar Redis
docker-compose restart redis
```

#### Worker no procesa tareas

```bash
# Verificar workers activos
celery -A src.celery_app inspect active

# Ver workers registrados
celery -A src.celery_app inspect registered

# Reiniciar worker
pkill -f "celery.*worker"
./scripts/start_worker.sh
```

#### Error de autenticación en Notion

```bash
# Verificar token
echo $NOTION_TOKEN

# Verificar que la integración tenga acceso a las bases de datos
# Ve a Notion → Settings & Members → Integrations
```

## Próximos Pasos

1. ✅ Sistema funcionando
2. 📝 Configurar n8n para automación
3. 🔐 Cambiar WEBHOOK_SECRET en producción
4. 🌐 Configurar HTTPS con nginx/reverse proxy
5. 📊 Monitorear con Flower regularmente
6. 🔄 Ajustar concurrencia de workers según necesidad

## Documentación Adicional

- **Guía completa**: `docs/NOTION_INTEGRATION.md`
- **API Docs**: http://localhost:8000/docs
- **Changelog**: `docs/CHANGELOG.md`
- **README principal**: `README.md`

## Soporte

Si encuentras problemas:

1. Revisa logs en `logs/`
2. Verifica Flower dashboard
3. Consulta `docs/NOTION_INTEGRATION.md` sección "Troubleshooting"
4. Abre un issue en GitHub

---

¡Felicitaciones! 🎉 El sistema está listo para procesar videos automáticamente.
