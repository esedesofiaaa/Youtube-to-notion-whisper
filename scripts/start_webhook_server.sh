#!/bin/bash
# Script para iniciar el servidor de webhooks FastAPI

echo "========================================="
echo "🌐 Iniciando Webhook Server"
echo "========================================="

# Activar entorno virtual si existe
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Iniciar servidor con uvicorn
python -m uvicorn src.webhook_server:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload

echo "========================================="
echo "✅ Webhook Server detenido"
echo "========================================="
