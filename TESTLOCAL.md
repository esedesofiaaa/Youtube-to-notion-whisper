# 🚀 Comandos para Iniciar el Proyecto Localmente

## 📋 Prerequisitos (solo una vez)

```bash
# 1. Ir al directorio del proyecto
cd /home/raul/Documents/Work/Youtube-to-notion-whisper

# 2. Configurar Python 3.12.8 para el proyecto
pyenv local 3.12.8

# 3. Crear entorno virtual (si no existe)
~/.pyenv/versions/3.12.8/bin/python -m venv venv

# 4. Instalar dependencias (si no están instaladas)
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 🔧 Iniciar Servicios (cada vez que quieras usar el sistema)

### Terminal 1 - Redis (si no está corriendo con Docker)

```bash
sudo docker-compose up -d redis
# O verificar que esté corriendo:
docker ps | grep redis
```

### Terminal 2 - Celery Worker

```bash
cd /home/raul/Documents/Work/Youtube-to-notion-whisper
source venv/bin/activate
export PYTHONPATH=$PYTHONPATH:/home/raul/Documents/Work/Youtube-to-notion-whisper
celery -A src.celery_app worker --loglevel=info --concurrency=1
```

### Terminal 3 - Webhook Server

```bash
cd /home/raul/Documents/Work/Youtube-to-notion-whisper
source venv/bin/activate
python -m uvicorn src.webhook_server:app --host 0.0.0.0 --port 8000
```

### Terminal 4 - Flower Dashboard (Opcional - Monitoreo)

```bash
cd /home/raul/Documents/Work/Youtube-to-notion-whisper
source venv/bin/activate
celery -A src.celery_app flower --port=5555
```

Luego abre en tu navegador: **http://localhost:5555**

Desde aquí puedes:
- Ver tareas en ejecución, completadas y fallidas
- Monitorear el estado de los workers
- Ver estadísticas de tiempo de ejecución
- Reintentar tareas fallidas
- Ver los logs de cada tarea

---

## 📤 Enviar Video para Procesar

### Terminal 5 - Enviar petición

```bash
curl -X POST http://localhost:8000/webhook/process-video \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: zOwjTcoVnamTKqoOJDAYBubMKACJz4a41JQIr7rfxSg" \
  -d '{
    "discord_entry_id": "ID_DE_PAGINA_NOTION",
    "youtube_url": "URL_DEL_VIDEO",
    "channel": "market-analysis-streams"
  }'
```

### Ejemplo con datos reales

```bash
curl -X POST http://localhost:8000/webhook/process-video \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: zOwjTcoVnamTKqoOJDAYBubMKACJz4a41JQIr7rfxSg" \
  -d '{
    "discord_entry_id": "2badaf66daf780d1a0f5edfa8352e9bb",
    "youtube_url": "https://www.youtube.com/watch?v=euo8Ao0KWQo",
    "channel": "market-analysis-streams"
  }'
```

---

## 🛑 Detener Servicios

```bash
# Detener Celery Worker: Ctrl+C en Terminal 2
# Detener Webhook Server: Ctrl+C en Terminal 3
# Detener Flower Dashboard: Ctrl+C en Terminal 4 (si lo iniciaste)

# Detener Redis:
sudo docker-compose down
```

---

## 📝 Notas Importantes

### Canales válidos y sus carpetas de Google Drive

- **`market-analysis-streams`** → Drive Folder ID: `138kcwrnHsDhp6eW1npM0LZkSijjsWq--`
- **`market-outlook`** → Drive Folder ID: `1m2IkPllwhz3e2Tf4BBEoa4OSV37AafQ6`

### Otras notas

- El campo **Drive Link** queda en blanco en Notion (evita conflicto de tipos)
- Procesamiento **secuencial** (1 video a la vez) para optimizar CPU
- Los logs ahora muestran **ERROR** en lugar de WARNING cuando algo falla
- El worker procesa los videos de forma asíncrona en segundo plano
