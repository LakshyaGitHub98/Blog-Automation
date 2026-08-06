import logging
import re
import statistics
from datetime import datetime, timedelta, timezone

from config import settings
from db import models
from db.database import SessionLocal
from libs.detector import get_detector
from libs.llm.provider import LLMError, complete_with_failover

logger = logging.getLogger("blog_gen.pipeline")

DRAFT_SYSTEM = (
    "You are an experienced essayist, not a copywriter. Write a blog post about "
    "the topic that reads like a real person typed it at a kitchen table.\n"
    "- Vary sentence lengths dramatically: mix 2-3 word fragments with 25-word "
    "sentences. Do not keep a steady rhythm.\n"
    "- Vary paragraph lengths: some paragraphs 1-2 sentences, others 5-7.\n"
    "- Use concrete, specific detail and a genuine first-person voice, including "
    "small unpolished observations.\n"
    "- Use '## ' markdown headings for a few sections.\n"
    "- Banned: no emojis; at most one em-dash (—) per paragraph; never write "
    "'In conclusion', 'Furthermore', 'Moreover', 'Additionally', 'delve', "
    "'navigate', 'landscape', 'leverage', 'in today's world', 'it's important "
    "to note', 'at the end of the day'. Avoid dense bullet-point lists. Never "
    "mention that you are an AI or a language model."
)

HUMANIZE_SYSTEM = (
    "You are a ruthless editor making machine-written text read like it was typed "
    "by a person, aiming to beat AI detectors. Rewrite the full post.\n"
    "- Vary sentence lengths dramatically and DELIBERATELY: alternate very short "
    "sentences (3-6 words) with long ones (20-30 words). Never keep a steady "
    "rhythm. Short fragments are your friend.\n"
    "- Vary paragraph lengths: make some paragraphs just 1-2 sentences, others "
    "5-6. Keep the paragraph breaks (blank lines) — do not merge paragraphs.\n"
    "- Cut formulaic AI phrases and replace them with plain, specific language. "
    "Especially remove: 'furthermore', 'moreover', 'additionally', 'delve', "
    "'navigate', 'landscape', 'leverage', 'in conclusion', 'at the end of the "
    "day', 'it's important to note', 'in today's world'.\n"
    "- Reduce em-dashes (—) to at most one per paragraph; replace the rest with "
    "commas, periods, or a rephrase.\n"
    "- Keep a personal, honest first-person voice with natural transitions, "
    "concrete details, contractions, and mild imperfection.\n"
    "- Keep every fact, the headings, structure, and topic identical. Do NOT "
    "invent new facts, stats, or numbers.\n"
    "- No emojis, no heavy bullet lists.\n"
    "The flagged paragraphs below are the most formulaic; make those sections the "
    "most natural-sounding. Return the complete rewritten post only."
)

_HEADING_RE = re.compile(r"^#+\s+(.+)$", re.MULTILINE)


def create_post(topic):
    db = SessionLocal()
    try:
        post = models.Post(topic=topic, status="queued", stage="queued")
        db.add(post)
        db.commit()
        db.refresh(post)
        logger.info("post %s created (topic=%r)", post.id, topic[:80])
        return post
    finally:
        db.close()


def extract_title(content):
    m = _HEADING_RE.search(content or "")
    if m:
        return m.group(1).strip()
    plain = re.sub(r"#+", "", (content or "").split("\n")[0]).strip()
    return plain[:80] or "Untitled"


_FORMULAIC_SUBSTRINGS = [
    "in today's",
    "it's important to note",
    "it is important to note",
    "it's worth noting",
    "furthermore",
    "moreover",
    "additionally",
    "in addition",
    "delve",
    "navigate",
    "leverage",
    "landscape",
    "in conclusion",
    "at the end of the day",
    "seamless",
    "empower",
    "unlock",
    "game-changer",
]


def detector_hints(text):
    """Human-readable summary of why the detector thinks text is AI-ish."""
    hints = []
    if text.count("\u2014") + text.count("\u2013") >= 2:
        hints.append("too many em-dashes")
    low = text.lower()
    found = [c for c in _FORMULAIC_SUBSTRINGS if c in low]
    if found:
        hints.append("formulaic phrases like: " + ", ".join(found[:4]))
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]
    lens = [len(s.split()) for s in sents]
    if len(lens) >= 4 and statistics.mean(lens) > 0:
        cv = statistics.pstdev(lens) / statistics.mean(lens)
        if cv < 0.5:
            hints.append("sentence rhythm too uniform")
    return "; ".join(hints) or "none detected"


def cleanup_stale_posts():
    """Mark generating/queued posts older than JOB_STALE_SECONDS as failed."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.job_stale_seconds)
    db = SessionLocal()
    try:
        rows = (
            db.query(models.Post)
            .filter(models.Post.status.in_(["queued", "generating"]))
            .filter(models.Post.created_at < cutoff)
            .all()
        )
        for post in rows:
            post.status = "failed"
            post.stage = "timed_out"
            post.error = (
                f"job timed out after {settings.job_stale_seconds}s "
                "(process restarted or request interrupted)"
            )
            logger.warning("post %s marked failed: stale %s", post.id, post.status)
        db.commit()
        return len(rows)
    finally:
        db.close()


def run_pipeline(post_id, topic, options=None):
    """draft -> humanize -> eval loop. Updates the Post row in place.

    Always persists partial revisions and always ends in a terminal status
    (completed/failed) so no post is left orphaned as 'generating'.
    """
    options = options or {}
    max_iterations = int(options.get("max_iterations", settings.max_iterations))
    threshold = float(options.get("threshold", settings.threshold))
    temperature = float(options.get("temperature", settings.temperature))
    max_tokens = int(options.get("max_tokens", settings.max_tokens))
    min_humanize_passes = int(
        options.get("min_humanize_passes", settings.min_humanize_passes)
    )

    detector = get_detector()

    revisions = []  # (rewrite_count, content, DetectorResult)
    error = None
    try:
        _set_status(post_id, "generating", stage="draft")
        logger.info("post %s | stage=draft start", post_id)
        draft = complete_with_failover(
            DRAFT_SYSTEM, f"Topic: {topic}", temperature=temperature, max_tokens=max_tokens
        )
        logger.info("post %s | stage=draft done (%d chars)", post_id, len(draft))

        current = draft
        humanized = 0
        for rewrite_count in range(max_iterations + 1):
            _set_status(post_id, "generating", stage="evaluating")
            res = detector.score_text(current)
            revisions.append((rewrite_count, current, res))
            logger.info(
                "post %s | eval round=%d overall=%.3f threshold=%.3f",
                post_id,
                rewrite_count,
                res.score,
                threshold,
            )
            if rewrite_count >= max_iterations:
                logger.info("post %s | max iterations reached", post_id)
                break
            if res.score <= threshold and humanized >= min_humanize_passes:
                logger.info("post %s | accepted (score <= threshold)", post_id)
                break
            if res.score <= threshold:
                logger.info(
                    "post %s | passing but forcing humanize pass %d",
                    post_id,
                    humanized + 1,
                )

            flagged = [p["text"] for p in res.paragraphs if p["score"] > threshold][:5]
            flag_text = "\n\n---\n\n".join(flagged) if flagged else "none specifically flagged"
            _set_status(post_id, "generating", stage="humanizing")
            logger.info(
                "post %s | humanize round=%d (%d flagged paragraphs)",
                post_id,
                rewrite_count,
                len(flagged),
            )
            feedback = (
                f"Current overall AI-score: {res.score:.2f} "
                f"(target: <= {threshold}). Main issues detected: {detector_hints(current)}."
            )
            new = complete_with_failover(
                HUMANIZE_SYSTEM,
                f"{feedback}\n\nFlagged paragraphs:\n{flag_text}\n\nFull post:\n{current}",
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if not new or new == current:
                logger.info("post %s | humanize produced no change, stopping", post_id)
                break
            current = new
            humanized += 1
            logger.info("post %s | humanize round=%d done (%d chars)", post_id, rewrite_count, len(current))

        best = min(revisions, key=lambda r: r[2].score)
        logger.info(
            "post %s | best revision=%d final_score=%.3f",
            post_id,
            best[0],
            best[2].score,
        )
        _save_revisions(post_id, revisions)
        _set_status(post_id, "generating", stage="saving")

        db = SessionLocal()
        try:
            post = db.get(models.Post, post_id)
            post.title = extract_title(best[1])
            post.content = best[1]
            post.iterations_used = best[0]
            post.final_score = best[2].score
            post.detector = best[2].detector
            post.status = "completed"
            post.stage = "done"
            post.error = ""
            db.commit()
        finally:
            db.close()

        result = {
            "status": "completed",
            "post_id": post_id,
            "title": extract_title(best[1]),
            "iterations_used": best[0],
            "final_score": best[2].score,
            "detector": best[2].detector,
            "content": best[1],
        }
        logger.info("post %s | completed", post_id)
        return result
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
        logger.exception("post %s | pipeline FAILED: %s", post_id, error)
        if revisions:
            _save_revisions(post_id, revisions)
        _set_status(post_id, "failed", stage="failed", error=error)
        raise


def _save_revisions(post_id, revisions):
    db = SessionLocal()
    try:
        for rewrite_count, content, res in revisions:
            rev = models.Revision(
                post_id=post_id,
                iteration=rewrite_count,
                content=content,
                detector=res.detector,
                ai_score=res.score,
            )
            db.add(rev)
            db.flush()
            db.add(
                models.EvalScore(
                    revision_id=rev.id, kind="overall", snippet="", score=res.score
                )
            )
            for p in res.paragraphs:
                db.add(
                    models.EvalScore(
                        revision_id=rev.id,
                        kind="paragraph",
                        snippet=p["text"][:500],
                        score=p["score"],
                    )
                )
        db.commit()
    finally:
        db.close()


def _set_status(post_id, status, stage=None, error=""):
    db = SessionLocal()
    try:
        post = db.get(models.Post, post_id)
        if post:
            post.status = status
            if stage is not None:
                post.stage = stage
            post.error = error
            db.commit()
    finally:
        db.close()
