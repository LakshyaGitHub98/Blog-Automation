from fastapi import FastAPI

from apps.api.routes import router
from config import settings
from db import models
from db.database import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="blog-gen", version="0.1.0")
app.include_router(router)


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "async" if settings.redis_url else "sync"}
