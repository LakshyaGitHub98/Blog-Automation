import logging

from fastapi import FastAPI

from apps.api.routes import router
from config import settings
from db import models
from db.database import Base, engine
from libs.logging_setup import setup_logging

logger = logging.getLogger("blog_gen")

setup_logging()

Base.metadata.create_all(bind=engine)
models.ensure_post_stage_column(engine)

app = FastAPI(title="blog-gen", version="0.1.0")
app.include_router(router)

from apps.worker.pipeline import cleanup_stale_posts  # noqa: E402


@app.on_event("startup")
def startup():
    marked = cleanup_stale_posts()
    if marked:
        logger.info("startup: marked %d stale post(s) as failed", marked)


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "async" if settings.redis_url else "sync"}
