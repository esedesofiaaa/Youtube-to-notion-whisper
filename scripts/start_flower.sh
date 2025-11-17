#!/bin/bash
# Script para iniciar Flower (dashboard de Celery)

echo "========================================="
echo "🌸 Iniciando Flower Dashboard"
echo "========================================="

# Activar entorno virtual si existe
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Establecer PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Iniciar Flower sin autenticación (para desarrollo)
# Para agregar autenticación en producción, agrega: --basic_auth=usuario:password
PYTHONPATH=$(pwd) celery -A src.celery_app flower \
    --port=5555 \
    --address=0.0.0.0 \
    --auth_provider=flower.views.auth.NoAuth

echo "========================================="
echo "✅ Flower Dashboard detenido"
echo "========================================="
