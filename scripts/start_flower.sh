#!/bin/bash
# Script para iniciar Flower (dashboard de Celery)

echo "========================================="
echo "🌸 Iniciando Flower Dashboard"
echo "========================================="

# Activar entorno virtual si existe
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Iniciar Flower
celery -A src.celery_app flower \
    --port=5555 \
    --address=0.0.0.0

echo "========================================="
echo "✅ Flower Dashboard detenido"
echo "========================================="
