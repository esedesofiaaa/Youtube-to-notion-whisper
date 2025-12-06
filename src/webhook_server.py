"""
Webhook server with FastAPI to receive notifications from n8n.
"""
from fastapi import FastAPI, HTTPException, Header, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from typing import Optional
import uvicorn
from datetime import datetime

from src.tasks import process_youtube_video, process_discord_video, test_task
from src.notion_client import NotionClient
from config.logger import get_logger
from config.settings import WEBHOOK_HOST, WEBHOOK_PORT, WEBHOOK_SECRET
from config.notion_config import is_valid_youtube_url, is_valid_channel
from src.discord_client import is_valid_discord_message_url

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
    Supports both YouTube and Discord video URLs.
    Maintains backward compatibility with old field names.
    """
    # New field names (preferred)
    notion_page_id: Optional[str] = Field(None, description="ID of the page in Discord Message Database")
    video_url: Optional[str] = Field(None, description="URL of the video (YouTube or Discord message)")
    channel_name: Optional[str] = Field(None, description="Discord channel name")
    
    # Old field names (backward compatibility)
    discord_entry_id: Optional[str] = Field(None, description="[DEPRECATED] Use notion_page_id instead")
    youtube_url: Optional[str] = Field(None, description="[DEPRECATED] Use video_url instead")
    channel: Optional[str] = Field(None, description="[DEPRECATED] Use channel_name instead")
    
    parent_drive_folder_id: Optional[str] = Field(None, description="ID of parent folder in Drive (optional)")

    @validator('video_url', 'youtube_url', pre=True, always=True)
    def validate_video_url(cls, v, values):
        """Validate that URL is either YouTube or Discord message URL."""
        # Use video_url if provided, otherwise fall back to youtube_url
        url = v or values.get('youtube_url') or values.get('video_url')
        if not url:
            return None
        if not is_valid_youtube_url(url) and not is_valid_discord_message_url(url):
            raise ValueError(f"Invalid video URL. Must be YouTube or Discord message URL: {url}")
        return url

    @validator('channel_name', 'channel', pre=True, always=True)
    def validate_channel(cls, v, values):
        """Validate channel name."""
        # Use channel_name if provided, otherwise fall back to channel
        channel = v or values.get('channel') or values.get('channel_name')
        if not channel:
            return None
        if not is_valid_channel(channel):
            raise ValueError(f"Invalid channel: {channel}")
        return channel
    
    def get_notion_page_id(self) -> str:
        """Get notion_page_id with fallback to discord_entry_id."""
        return self.notion_page_id or self.discord_entry_id
    
    def get_video_url(self) -> str:
        """Get video_url with fallback to youtube_url."""
        return self.video_url or self.youtube_url
    
    def get_channel_name(self) -> str:
        """Get channel_name with fallback to channel."""
        return self.channel_name or self.channel

    class Config:
        schema_extra = {
            "example": {
                "notion_page_id": "28bdaf66daf7816383e6ce8390b0a866",
                "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "channel_name": "audit-process",
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
        # Get values with backward compatibility
        notion_page_id = payload.get_notion_page_id()
        video_url = payload.get_video_url()
        channel_name = payload.get_channel_name()
        
        # Validate required fields
        if not notion_page_id:
            raise ValueError("notion_page_id (or discord_entry_id) is required")
        if not video_url:
            raise ValueError("video_url (or youtube_url) is required")
        if not channel_name:
            raise ValueError("channel_name (or channel) is required")
        
        # Detect video source
        is_youtube = is_valid_youtube_url(video_url)
        is_discord = is_valid_discord_message_url(video_url)
        
        video_source = "YouTube" if is_youtube else "Discord" if is_discord else "Unknown"
        
        logger.info("=" * 80)
        logger.info("📨 Webhook received")
        logger.info(f"   Source: {video_source}")
        logger.info(f"   Notion Page ID: {notion_page_id}")
        logger.info(f"   Video URL: {video_url}")
        logger.info(f"   Channel: {channel_name}")
        logger.info("=" * 80)

        # Route to appropriate task based on URL type
        if is_youtube:
            task = process_youtube_video.apply_async(
                kwargs={
                    "discord_entry_id": notion_page_id,
                    "youtube_url": video_url,
                    "channel": channel_name,
                    "parent_drive_folder_id": payload.parent_drive_folder_id
                }
            )
        elif is_discord:
            task = process_discord_video.apply_async(
                kwargs={
                    "notion_page_id": notion_page_id,
                    "discord_message_url": video_url,
                    "channel": channel_name,
                    "parent_drive_folder_id": payload.parent_drive_folder_id
                }
            )
        else:
            raise ValueError(f"Unsupported video URL type: {video_url}")

        logger.info(f"✅ Task queued successfully [Task ID: {task.id}] [Source: {video_source}]")

        return TaskResponse(
            status="queued",
            message=f"{video_source} video queued for processing",
            task_id=task.id,
            timestamp=datetime.utcnow().isoformat(),
            data={
                "video_url": video_url,
                "source": video_source,
                "channel": channel_name,
                "notion_page_id": notion_page_id
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
