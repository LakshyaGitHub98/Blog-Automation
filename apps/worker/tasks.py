from config import settings
from apps.worker.pipeline import run_pipeline

try:
    from celery import Celery

    _HAS_CELERY = True
except ImportError:
    _HAS_CELERY = False

if _HAS_CELERY and settings.redis_url:
    celery_app = Celery("blog_gen", broker=settings.redis_url, backend=settings.redis_url)
    celery_app.conf.update(
        task_track_started=True,
        worker_hijack_root_logger=False,
        task_acks_late=True,
    )

    @celery_app.task(name="generate_post")
    def generate_post_task(post_id, topic, options=None):
        return run_pipeline(post_id, topic, options)

else:
    celery_app = None

    def generate_post_task(post_id, topic, options=None):
        raise RuntimeError("Celery not configured: REDIS_URL is empty")
