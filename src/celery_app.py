"""
Celery configuration for asynchronous video processing.
"""
from celery import Celery
from config.settings import (
    CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND,
    CELERY_TASK_SERIALIZER,
    CELERY_RESULT_SERIALIZER,
    CELERY_ACCEPT_CONTENT,
    CELERY_TIMEZONE,
    CELERY_ENABLE_UTC,
    CELERY_TASK_TIME_LIMIT,
    CELERY_TASK_SOFT_TIME_LIMIT,
    CELERY_BROKER_VISIBILITY_TIMEOUT
)

# Create Celery instance
celery_app = Celery(
    'youtube_to_notion',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

# Celery configuration
celery_app.conf.update(
    task_serializer=CELERY_TASK_SERIALIZER,
    result_serializer=CELERY_RESULT_SERIALIZER,
    accept_content=CELERY_ACCEPT_CONTENT,
    timezone=CELERY_TIMEZONE,
    enable_utc=CELERY_ENABLE_UTC,
    broker_transport_options={
        'visibility_timeout': CELERY_BROKER_VISIBILITY_TIMEOUT,
        'fanout_prefix': True,
        'fanout_patterns': True,
    },
    task_time_limit=CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=CELERY_TASK_SOFT_TIME_LIMIT,
    task_track_started=True,  # Track when a task starts
    task_acks_late=True,  # Late acknowledgment (for retries on failure)
    worker_prefetch_multiplier=1,  # Process one task at a time per worker
    worker_max_tasks_per_child=10,  # Restart worker every 10 tasks (free memory)
)

# Auto-discovery of tasks
celery_app.autodiscover_tasks(['src'])

# Additional configuration for logging
celery_app.conf.update(
    worker_hijack_root_logger=False,  # Do not override root logger
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',
)
