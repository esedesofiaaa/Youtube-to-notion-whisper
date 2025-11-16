#!/bin/bash
# Script maestro para iniciar todos los servicios del sistema

echo "========================================="
echo "🚀 Iniciando Sistema Completo"
echo "   YouTube to Notion Automation"
echo "========================================="

# Verificar si Docker está corriendo
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker no está corriendo"
    echo "   Por favor inicia Docker y vuelve a intentar"
    exit 1
fi

# Iniciar Redis con Docker Compose
echo ""
echo "📦 Iniciando Redis..."
docker-compose up -d redis

# Esperar a que Redis esté listo
echo "⏳ Esperando a que Redis esté listo..."
sleep 3

# Activar entorno virtual si existe
if [ -d ".venv" ]; then
    echo "🐍 Activando entorno virtual..."
    source .venv/bin/activate
fi

# Iniciar Celery Worker en segundo plano
echo ""
echo "🔧 Iniciando Celery Worker (modo secuencial: 1 video a la vez)..."
celery -A src.celery_app worker \
    --loglevel=info \
    --concurrency=1 \
    --prefetch-multiplier=1 \
    --max-tasks-per-child=5 \
    --time-limit=3600 \
    --soft-time-limit=3300 \
    --logfile=logs/celery_worker.log \
    --detach

# Iniciar Flower dashboard en segundo plano
echo ""
echo "🌸 Iniciando Flower Dashboard..."
celery -A src.celery_app flower \
    --port=5555 \
    --address=0.0.0.0 \
    --logfile=logs/flower.log \
    --detach

# Esperar un momento
sleep 2

# Iniciar Webhook Server
echo ""
echo "🌐 Iniciando Webhook Server..."
echo ""
echo "========================================="
echo "✅ Sistema iniciado correctamente"
echo "========================================="
echo ""
echo "📊 Servicios disponibles:"
echo "   • Webhook Server: http://localhost:8000"
echo "   • Flower Dashboard: http://localhost:5555"
echo "   • API Docs: http://localhost:8000/docs"
echo ""
echo "📝 Logs disponibles en:"
echo "   • Celery Worker: logs/celery_worker.log"
echo "   • Flower: logs/flower.log"
echo ""
echo "⚠️  Presiona Ctrl+C para detener el Webhook Server"
echo "    (Worker y Flower seguirán corriendo en segundo plano)"
echo ""
echo "========================================="

# Iniciar servidor de webhooks en primer plano
python -m uvicorn src.webhook_server:app \
    --host 0.0.0.0 \
    --port 8000

# Este código se ejecuta cuando se detiene el servidor con Ctrl+C
echo ""
echo "🛑 Webhook Server detenido"
echo ""
echo "Para detener completamente el sistema, ejecuta:"
echo "   ./scripts/stop_all.sh"
