"""
Webhook server with FastAPI to receive notifications from n8n.
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
    Data model for n8n webhook payload.
    """
    discord_entry_id: str = Field(..., description="ID of the page in Discord Message Database")
    youtube_url: str = Field(..., description="URL of the YouTube video")
    channel: str = Field(..., description="Discord channel")
    parent_drive_folder_id: Optional[str] = Field(None, description="ID of parent folder in Drive (optional)")

    @validator('youtube_url')
    def validate_youtube_url(cls, v):
        if not is_valid_youtube_url(v):
            raise ValueError(f"Invalid YouTube URL: {v}")
        return v

    @validator('channel')
    def validate_channel(cls, v):
        if not is_valid_channel(v):
            raise ValueError(f"Invalid channel: {v}")
        return v

    class Config:
        schema_extra = {
            "example": {
                "discord_entry_id": "28bdaf66daf7816383e6ce8390b0a866",
                "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "channel": "market-outlook",
                "parent_drive_folder_id": "1ABC123xyz"
            }
        }


class TaskResponse(BaseModel):
    """Response model for queued tasks."""
    status: str
    message: str
    task_id: str
    timestamp: str
    data: dict


# ========== AUTHENTICATION MIDDLEWARE ==========

def verify_webhook_secret(x_webhook_secret: Optional[str] = Header(None)):
    """
    Verify webhook secret for basic authentication.

    Args:
        x_webhook_secret: Custom header with secret

    Raises:
        HTTPException: If secret is invalid or missing
    """
    if WEBHOOK_SECRET and WEBHOOK_SECRET != "change-this-secret-in-production":
        if not x_webhook_secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authentication header: X-Webhook-Secret"
            )
        if x_webhook_secret != WEBHOOK_SECRET:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid webhook secret"
            )


# ========== ENDPOINTS ==========

@app.get("/")
async def root():
    """Root endpoint to verify server is running."""
    return {
        "service": "YouTube to Notion Webhook Server",
        "status": "running",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
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
    Main endpoint to receive n8n webhooks and queue video processing.

    Args:
        payload: Webhook data
        x_webhook_secret: Authentication header

    Returns:
        TaskResponse: Information about the queued task
    """
    # Verify authentication
    verify_webhook_secret(x_webhook_secret)

    try:
        logger.info("=" * 80)
        logger.info("📨 Webhook received")
        logger.info(f"   Discord Entry ID: {payload.discord_entry_id}")
        logger.info(f"   YouTube URL: {payload.youtube_url}")
        logger.info(f"   Channel: {payload.channel}")
        logger.info("=" * 80)

        # Queue task in Celery
        task = process_youtube_video.apply_async(
            kwargs={
                "discord_entry_id": payload.discord_entry_id,
                "youtube_url": payload.youtube_url,
                "channel": payload.channel,
                "parent_drive_folder_id": payload.parent_drive_folder_id
            }
        )

        logger.info(f"✅ Task queued successfully [Task ID: {task.id}]")

        return TaskResponse(
            status="queued",
            message="Video queued for processing",
            task_id=task.id,
            timestamp=datetime.utcnow().isoformat(),
            data={
                "youtube_url": payload.youtube_url,
                "channel": payload.channel,
                "discord_entry_id": payload.discord_entry_id
            }
        )

    except Exception as e:
        logger.error(f"❌ Error processing webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error queuing task: {str(e)}"
        )


@app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """
    Get the status of a task by its ID.

    Args:
        task_id: Celery task ID

    Returns:
        dict: Task status and result
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
        response["message"] = "Task pending or does not exist"
    elif task.state == "STARTED":
        response["message"] = "Task in progress"
    elif task.state == "SUCCESS":
        response["message"] = "Task completed successfully"
        response["result"] = task.result
    elif task.state == "FAILURE":
        response["message"] = "Task failed"
        response["error"] = str(task.info)
    elif task.state == "RETRY":
        response["message"] = "Task retrying"
        response["retry_info"] = str(task.info)

    return response


@app.post("/test/task")
async def test_celery_task(message: str = "Test message"):
    """
    Test endpoint to verify Celery works.

    Args:
        message: Test message

    Returns:
        dict: Test task information
    """
    try:
        task = test_task.apply_async(kwargs={"message": message})

        logger.info(f"🧪 Test task queued [Task ID: {task.id}]")

        return {
            "status": "queued",
            "message": "Test task queued",
            "task_id": task.id,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Error queuing test task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {str(e)}"
        )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"❌ Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "detail": str(exc),
            "timestamp": datetime.utcnow().isoformat()
        }
    )


# ========== MAIN FUNCTION ==========

def start_server():
    """Start the webhook server."""
    logger.info("=" * 80)
    logger.info("🚀 Starting webhook server")
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
