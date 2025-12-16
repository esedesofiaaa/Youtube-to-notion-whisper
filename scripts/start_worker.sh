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

# Cargar variables de entorno
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Usar timeouts desde variables de entorno (con fallbacks que coinciden con config/settings.py)
# Nota: hard/soft < visibility_timeout para que el worker tenga control antes de que Redis re-encole.
VISIBILITY_TIMEOUT=${CELERY_BROKER_VISIBILITY_TIMEOUT:-28800}  # Default: 8 horas
TIME_LIMIT=${CELERY_TASK_TIME_LIMIT:-27000}    # Default: 7.5 horas
SOFT_TIME_LIMIT=${CELERY_TASK_SOFT_TIME_LIMIT:-26000}  # Default: ~7.2 horas

echo "⏱️  Time limits configurados:"
echo "   Visibility timeout: ${VISIBILITY_TIMEOUT}s ($(($VISIBILITY_TIMEOUT / 60)) minutos)"
echo "   Hard limit: ${TIME_LIMIT}s ($(($TIME_LIMIT / 60)) minutos)"
echo "   Soft limit: ${SOFT_TIME_LIMIT}s ($(($SOFT_TIME_LIMIT / 60)) minutos)"
echo ""

# Iniciar worker con procesamiento secuencial
# --concurrency=1: Procesa solo un video a la vez (importante para CPU)
# --prefetch-multiplier=1: No prefetch tareas adicionales
PYTHONPATH=$(pwd) celery -A src.celery_app worker \
    --loglevel=info \
    --concurrency=1 \
    --prefetch-multiplier=1 \
    --max-tasks-per-child=5 \
    --time-limit=${TIME_LIMIT} \
    --soft-time-limit=${SOFT_TIME_LIMIT}

echo "========================================="
echo "✅ Celery Worker detenido"
echo "========================================="
