#!/bin/bash
# Script para detener todos los servicios del sistema

echo "========================================="
echo "🛑 Deteniendo Sistema Completo"
echo "========================================="

# Detener Celery workers
echo ""
echo "🔧 Deteniendo Celery Workers..."
pkill -f "celery.*worker" || echo "   No hay workers corriendo"

# Detener Flower
echo ""
echo "🌸 Deteniendo Flower Dashboard..."
pkill -f "celery.*flower" || echo "   Flower no está corriendo"

# Detener servidor de webhooks
echo ""
echo "🌐 Deteniendo Webhook Server..."
pkill -f "uvicorn.*webhook_server" || echo "   Webhook Server no está corriendo"

# Detener Redis con Docker Compose
echo ""
echo "📦 Deteniendo Redis..."
docker compose down

echo ""
echo "========================================="
echo "✅ Sistema detenido completamente"
echo "========================================="
