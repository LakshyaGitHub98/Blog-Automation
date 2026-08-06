import logging
import os
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.queue import enqueue
from apps.worker.pipeline import create_post, run_pipeline
from config import settings, BASE_DIR
from db import models
from db.database import get_db

logger = logging.getLogger("blog_gen.api")

router = APIRouter()


class GenerateRequest(BaseModel):
    topic: str = Field(min_length=3)
    max_iterations: int | None = Field(default=None, ge=0, le=10)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=50, le=8192)


class PostOut(BaseModel):
    id: str
    topic: str
    title: str
    status: str
    stage: str
    iterations_used: int
    final_score: float | None
    detector: str
    error: str
    created_at: str
    content: str


def _post_out(p: models.Post) -> PostOut:
    return PostOut(
        id=p.id,
        topic=p.topic,
        title=p.title,
        status=p.status,
        stage=p.stage or "",
        iterations_used=p.iterations_used or 0,
        final_score=p.final_score,
        detector=p.detector,
        error=p.error or "",
        created_at=p.created_at.isoformat() if p.created_at else "",
        content=p.content or "",
    )


@router.post("/api/generate")
def generate(req: GenerateRequest, db: Session = Depends(get_db)):
    post = create_post(req.topic)
    options = {
        "max_iterations": req.max_iterations if req.max_iterations is not None else settings.max_iterations,
        "threshold": req.threshold if req.threshold is not None else settings.threshold,
        "temperature": req.temperature if req.temperature is not None else settings.temperature,
        "max_tokens": req.max_tokens if req.max_tokens is not None else settings.max_tokens,
    }
    logger.info(
        "POST /api/generate post=%s options=%s", post.id, options
    )
    if enqueue(post.id, req.topic, options):
        return {"request_id": post.id, "status": "queued", "async": True}
    # no redis -> run pipeline on a background thread so the HTTP request
    # returns instantly; the dashboard polls /api/status for progress.
    thread = threading.Thread(
        target=_run_sync_job,
        args=(post.id, req.topic, options),
        name=f"pipeline-{post.id[:8]}",
        daemon=True,
    )
    thread.start()
    return {"request_id": post.id, "status": "queued", "async": True}


def _run_sync_job(post_id, topic, options):
    try:
        run_pipeline(post_id, topic, options)
    except Exception as e:  # noqa: BLE001
        logger.error("background job %s failed: %s", post_id, e)


@router.get("/api/status/{post_id}")
def status(post_id: str, db: Session = Depends(get_db)):
    post = db.get(models.Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="not found")
    elapsed = None
    if post.created_at:
        created = post.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        elapsed = max(0, round((datetime.now(timezone.utc) - created).total_seconds()))
    return {
        "request_id": post.id,
        "status": post.status,
        "stage": post.stage or "",
        "error": post.error or "",
        "title": post.title,
        "final_score": post.final_score,
        "iterations_used": post.iterations_used or 0,
        "detector": post.detector,
        "elapsed_seconds": elapsed,
    }


@router.get("/api/posts")
def list_posts(db: Session = Depends(get_db)):
    posts = (
        db.query(models.Post)
        .order_by(models.Post.created_at.desc())
        .limit(100)
        .all()
    )
    return {"posts": [_post_out(p).model_dump() for p in posts]}


@router.get("/api/posts/{post_id}")
def post_detail(post_id: str, db: Session = Depends(get_db)):
    post = db.get(models.Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="not found")
    revisions = []
    for r in sorted(post.revisions, key=lambda x: x.iteration):
        revisions.append(
            {
                "id": r.id,
                "iteration": r.iteration,
                "ai_score": r.ai_score,
                "detector": r.detector,
                "content": r.content,
            }
        )
    return {"post": _post_out(post).model_dump(), "revisions": revisions}


@router.get("/")
def dashboard():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))
