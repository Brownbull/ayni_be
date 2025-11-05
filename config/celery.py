"""
Celery configuration for AYNI Backend.

This module configures Celery for async task processing with:
- Redis as broker and result backend
- Automatic task discovery from Django apps
- Task retry policies and error handling
- Task result tracking
- Integration with Flower for monitoring
"""

import os
from celery import Celery
from celery.signals import task_failure, task_success

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Initialize Celery app
app = Celery('ayni')

# Load configuration from Django settings with CELERY namespace
app.config_from_object('django.conf:settings', namespace='CELERY')

# Configure Celery task settings
app.conf.update(
    # Task execution settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='America/Santiago',
    enable_utc=True,

    # Task result settings
    result_expires=3600,  # Results expire after 1 hour
    result_persistent=True,  # Persist results to backend

    # Task retry settings (global defaults)
    task_acks_late=True,  # Acknowledge tasks after execution, not before
    task_reject_on_worker_lost=True,  # Reject tasks if worker crashes

    # Worker settings
    worker_prefetch_multiplier=1,  # Fetch one task at a time for fairness
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks to prevent memory leaks

    # Task routing (can be extended later)
    task_routes={
        'apps.processing.tasks.*': {'queue': 'processing'},
    },

    # Task time limits
    task_soft_time_limit=600,  # 10 minutes soft limit (warning)
    task_time_limit=900,  # 15 minutes hard limit (kill task)

    # Task tracking
    task_track_started=True,  # Track when tasks start
    task_send_sent_event=True,  # Send events when tasks are sent
)

# Auto-discover tasks in all installed apps
# Looks for tasks.py in each app
app.autodiscover_tasks()


# Signal handlers for task monitoring
@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, **kw):
    """
    Handle task failures.

    This is called when a task fails after all retries.
    Useful for logging, alerting, or cleanup.
    """
    print(f"Task {sender.name} ({task_id}) failed: {exception}")
    # TODO: Add Sentry integration or custom error logging


@task_success.connect
def task_success_handler(sender=None, result=None, **kwargs):
    """
    Handle task success.

    This is called when a task completes successfully.
    Useful for logging or triggering follow-up actions.
    """
    print(f"Task {sender.name} completed successfully")


@app.task(bind=True)
def debug_task(self):
    """
    Debug task to test Celery is working.

    Usage:
        from config.celery import debug_task
        result = debug_task.delay()
    """
    print(f'Request: {self.request!r}')
    return {'status': 'ok', 'request': str(self.request)}
