#!/bin/bash
# Script para iniciar el worker de Celery

echo "========================================="
echo "🚀 Iniciando Celery Worker"
echo "========================================="

# Activar entorno virtual si existe
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Iniciar worker con configuración optimizada
celery -A src.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --max-tasks-per-child=10 \
    --time-limit=3600 \
    --soft-time-limit=3300

echo "========================================="
echo "✅ Celery Worker detenido"
echo "========================================="
