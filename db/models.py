import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, inspect
from sqlalchemy.orm import relationship

from db.database import Base


def _uuid():
    return uuid.uuid4().hex


def _now():
    return datetime.now(timezone.utc)


class Post(Base):
    __tablename__ = "posts"

    id = Column(String(32), primary_key=True, default=_uuid)
    topic = Column(Text, nullable=False)
    title = Column(Text, default="")
    content = Column(Text, default="")
    status = Column(String(20), default="queued")  # queued|generating|completed|failed
    stage = Column(String(40), default="queued")  # draft|evaluating|humanizing|saving|done
    iterations_used = Column(Integer, default=0)
    final_score = Column(Float, nullable=True)
    detector = Column(String(20), default="")
    error = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=_now)

    revisions = relationship(
        "Revision", back_populates="post", cascade="all, delete-orphan"
    )


class Revision(Base):
    __tablename__ = "revisions"

    id = Column(String(32), primary_key=True, default=_uuid)
    post_id = Column(String(32), ForeignKey("posts.id"), nullable=False)
    iteration = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    detector = Column(String(20), default="")
    ai_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    post = relationship("Post", back_populates="revisions")
    eval_scores = relationship(
        "EvalScore", back_populates="revision", cascade="all, delete-orphan"
    )


class EvalScore(Base):
    __tablename__ = "eval_scores"

    id = Column(String(32), primary_key=True, default=_uuid)
    revision_id = Column(String(32), ForeignKey("revisions.id"), nullable=False)
    kind = Column(String(20), default="overall")  # overall | paragraph
    snippet = Column(Text, default="")
    score = Column(Float, nullable=False)

    revision = relationship("Revision", back_populates="eval_scores")


def ensure_post_stage_column(engine):
    """Add posts.stage to pre-existing databases (create_all won't alter tables)."""
    try:
        insp = inspect(engine)
        if "posts" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("posts")}
            if "stage" not in cols:
                with engine.begin() as conn:
                    conn.exec_driver_sql("ALTER TABLE posts ADD COLUMN stage VARCHAR(40) DEFAULT 'queued'")
    except Exception:  # pragma: no cover - best-effort migration
        return False
    return True
