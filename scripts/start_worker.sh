#!/bin/bash
# Script para iniciar el worker de Celery

echo "========================================="
echo "🚀 Iniciando Celery Worker"
echo "   Modo: Procesamiento secuencial (1 video a la vez)"
echo "========================================="

# Activar entorno virtual si existe
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Establecer PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Iniciar worker con procesamiento secuencial
# --concurrency=1: Procesa solo un video a la vez (importante para CPU)
# --prefetch-multiplier=1: No prefetch tareas adicionales
PYTHONPATH=$(pwd) celery -A src.celery_app worker \
    --loglevel=info \
    --concurrency=1 \
    --prefetch-multiplier=1 \
    --max-tasks-per-child=5 \
    --time-limit=3600 \
    --soft-time-limit=3300

echo "========================================="
echo "✅ Celery Worker detenido"
echo "========================================="
