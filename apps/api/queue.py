from config import settings


def enqueue(post_id, topic, options):
    """Dispatch to Celery if redis is configured, else return False
    (caller should run the pipeline synchronously)."""
    try:
        from apps.worker.tasks import generate_post_task, celery_app
    except ImportError:
        return False

    if celery_app is not None and settings.redis_url:
        generate_post_task.delay(post_id, topic, options)
        return True
    return False
