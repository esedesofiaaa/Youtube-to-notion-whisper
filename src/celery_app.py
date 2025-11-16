"""
Configuración de Celery para el procesamiento asíncrono de videos.
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
    CELERY_TASK_SOFT_TIME_LIMIT
)

# Crear instancia de Celery
celery_app = Celery(
    'youtube_to_notion',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

# Configuración de Celery
celery_app.conf.update(
    task_serializer=CELERY_TASK_SERIALIZER,
    result_serializer=CELERY_RESULT_SERIALIZER,
    accept_content=CELERY_ACCEPT_CONTENT,
    timezone=CELERY_TIMEZONE,
    enable_utc=CELERY_ENABLE_UTC,
    task_time_limit=CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=CELERY_TASK_SOFT_TIME_LIMIT,
    task_track_started=True,  # Rastrear cuando una tarea comienza
    task_acks_late=True,  # Confirmación tardía (para reintentos en caso de fallo)
    worker_prefetch_multiplier=1,  # Procesar una tarea a la vez por worker
    worker_max_tasks_per_child=10,  # Reiniciar worker cada 10 tareas (liberar memoria)
)

# Auto-descubrimiento de tareas
celery_app.autodiscover_tasks(['src'])

# Configuración adicional para logging
celery_app.conf.update(
    worker_hijack_root_logger=False,  # No sobrescribir el logger raíz
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',
)
