"""
Servidor de webhooks con FastAPI para recibir notificaciones de n8n.
"""
from fastapi import FastAPI, HTTPException, Header, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from typing import Optional
import uvicorn
from datetime import datetime

from src.tasks import process_youtube_video, test_task
from src.notion_client import NotionClient
from config.logger import get_logger
from config.settings import WEBHOOK_HOST, WEBHOOK_PORT, WEBHOOK_SECRET
from config.notion_config import is_valid_youtube_url, is_valid_channel

logger = get_logger(__name__)

# Crear aplicación FastAPI
app = FastAPI(
    title="YouTube to Notion Webhook Server",
    description="Servidor de webhooks para procesamiento automático de videos de YouTube a Notion",
    version="1.0.0"
)


# ========== MODELOS DE DATOS ==========

class WebhookPayload(BaseModel):
    """
    Modelo de datos para el payload del webhook de n8n.
    """
    discord_entry_id: str = Field(..., description="ID de la página en Discord Message Database")
    youtube_url: str = Field(..., description="URL del video de YouTube")
    channel: str = Field(..., description="Canal de Discord")
    parent_drive_folder_id: Optional[str] = Field(None, description="ID de carpeta padre en Drive (opcional)")

    @validator('youtube_url')
    def validate_youtube_url(cls, v):
        if not is_valid_youtube_url(v):
            raise ValueError(f"URL de YouTube inválida: {v}")
        return v

    @validator('channel')
    def validate_channel(cls, v):
        if not is_valid_channel(v):
            raise ValueError(f"Canal inválido: {v}")
        return v

    class Config:
        schema_extra = {
            "example": {
                "discord_entry_id": "28bdaf66daf7816383e6ce8390b0a866",
                "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "channel": "🎙・market-outlook",
                "parent_drive_folder_id": "1ABC123xyz"
            }
        }


class TaskResponse(BaseModel):
    """Modelo de respuesta para tareas encoladas."""
    status: str
    message: str
    task_id: str
    timestamp: str
    data: dict


# ========== MIDDLEWARE DE AUTENTICACIÓN ==========

def verify_webhook_secret(x_webhook_secret: Optional[str] = Header(None)):
    """
    Verifica el secreto del webhook para autenticación básica.

    Args:
        x_webhook_secret: Header personalizado con el secreto

    Raises:
        HTTPException: Si el secreto es inválido o falta
    """
    if WEBHOOK_SECRET and WEBHOOK_SECRET != "change-this-secret-in-production":
        if not x_webhook_secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Falta header de autenticación: X-Webhook-Secret"
            )
        if x_webhook_secret != WEBHOOK_SECRET:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Secreto de webhook inválido"
            )


# ========== ENDPOINTS ==========

@app.get("/")
async def root():
    """Endpoint raíz para verificar que el servidor está funcionando."""
    return {
        "service": "YouTube to Notion Webhook Server",
        "status": "running",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health_check():
    """Endpoint de health check."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/webhook/process-video", response_model=TaskResponse)
async def process_video_webhook(
    payload: WebhookPayload,
    x_webhook_secret: Optional[str] = Header(None)
):
    """
    Endpoint principal para recibir webhooks de n8n y encolar procesamiento de videos.

    Args:
        payload: Datos del webhook
        x_webhook_secret: Header de autenticación

    Returns:
        TaskResponse: Información de la tarea encolada
    """
    # Verificar autenticación
    verify_webhook_secret(x_webhook_secret)

    try:
        logger.info("=" * 80)
        logger.info("📨 Webhook recibido")
        logger.info(f"   Discord Entry ID: {payload.discord_entry_id}")
        logger.info(f"   YouTube URL: {payload.youtube_url}")
        logger.info(f"   Canal: {payload.channel}")
        logger.info("=" * 80)

        # Encolar tarea en Celery
        task = process_youtube_video.apply_async(
            kwargs={
                "discord_entry_id": payload.discord_entry_id,
                "youtube_url": payload.youtube_url,
                "channel": payload.channel,
                "parent_drive_folder_id": payload.parent_drive_folder_id
            }
        )

        logger.info(f"✅ Tarea encolada exitosamente [Task ID: {task.id}]")

        return TaskResponse(
            status="queued",
            message="Video encolado para procesamiento",
            task_id=task.id,
            timestamp=datetime.utcnow().isoformat(),
            data={
                "youtube_url": payload.youtube_url,
                "channel": payload.channel,
                "discord_entry_id": payload.discord_entry_id
            }
        )

    except Exception as e:
        logger.error(f"❌ Error al procesar webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al encolar tarea: {str(e)}"
        )


@app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """
    Obtiene el estado de una tarea por su ID.

    Args:
        task_id: ID de la tarea de Celery

    Returns:
        dict: Estado y resultado de la tarea
    """
    from celery.result import AsyncResult
    from src.celery_app import celery_app

    task = AsyncResult(task_id, app=celery_app)

    response = {
        "task_id": task_id,
        "status": task.state,
        "timestamp": datetime.utcnow().isoformat()
    }

    if task.state == "PENDING":
        response["message"] = "Tarea pendiente o no existe"
    elif task.state == "STARTED":
        response["message"] = "Tarea en progreso"
    elif task.state == "SUCCESS":
        response["message"] = "Tarea completada exitosamente"
        response["result"] = task.result
    elif task.state == "FAILURE":
        response["message"] = "Tarea falló"
        response["error"] = str(task.info)
    elif task.state == "RETRY":
        response["message"] = "Tarea reintentando"
        response["retry_info"] = str(task.info)

    return response


@app.post("/test/task")
async def test_celery_task(message: str = "Test message"):
    """
    Endpoint de prueba para verificar que Celery funciona.

    Args:
        message: Mensaje de prueba

    Returns:
        dict: Información de la tarea de prueba
    """
    try:
        task = test_task.apply_async(kwargs={"message": message})

        logger.info(f"🧪 Tarea de prueba encolada [Task ID: {task.id}]")

        return {
            "status": "queued",
            "message": "Tarea de prueba encolada",
            "task_id": task.id,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Error al encolar tarea de prueba: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {str(e)}"
        )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Manejador global de excepciones."""
    logger.error(f"❌ Excepción no manejada: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "detail": str(exc),
            "timestamp": datetime.utcnow().isoformat()
        }
    )


# ========== FUNCIÓN PRINCIPAL ==========

def start_server():
    """Inicia el servidor de webhooks."""
    logger.info("=" * 80)
    logger.info("🚀 Iniciando servidor de webhooks")
    logger.info(f"   Host: {WEBHOOK_HOST}")
    logger.info(f"   Port: {WEBHOOK_PORT}")
    logger.info("=" * 80)

    uvicorn.run(
        app,
        host=WEBHOOK_HOST,
        port=WEBHOOK_PORT,
        log_level="info"
    )


if __name__ == "__main__":
    start_server()
