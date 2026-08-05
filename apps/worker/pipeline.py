import re

from config import settings
from db import models
from db.database import SessionLocal
from libs.detector import get_detector
from libs.llm import get_llm
from libs.llm.provider import LLMError

DRAFT_SYSTEM = (
    "You are an expert blog writer. Write a well-structured, engaging blog post. "
    "Vary your sentence lengths a lot. Use specific, concrete details and natural "
    "first-person perspective. Use '## ' markdown headings for sections. "
    "Never write 'In conclusion', never use emojis, avoid dense bullet-point lists. "
    "Do not mention that you are an AI or a language model."
)

HUMANIZE_SYSTEM = (
    "You are an expert editor who rewrites machine-written text so it reads like it "
    "was written naturally by a person. Rewrite the full post.\n"
    "- Vary sentence lengths dramatically: mix short, punchy sentences with long, "
    "flowing ones. Do not keep sentences roughly the same length.\n"
    "- Use natural, specific, occasionally uncommon word choices (concrete nouns, "
    "vivid verbs). Avoid formulaic AI phrasing like 'in today's fast-paced world', "
    "'it's important to note', 'delve into'.\n"
    "- Keep a genuine first-person voice and natural transitions ('honestly', 'in "
    "practice', 'what surprised me').\n"
    "- Keep every fact and the overall structure, headings, and topic identical. "
    "Do NOT invent new facts, stats, or numbers.\n"
    "- Do not use emojis, do not use heavy bullet lists, never write 'In conclusion' "
    "or 'To summarize'.\n"
    "The flagged paragraphs below were detected as too formulaic; make those "
    "sections the most natural-sounding. Return the complete rewritten post only."
)

_HEADING_RE = re.compile(r"^#+\s+(.+)$", re.MULTILINE)


def create_post(topic):
    db = SessionLocal()
    try:
        post = models.Post(topic=topic, status="queued")
        db.add(post)
        db.commit()
        db.refresh(post)
        return post
    finally:
        db.close()


def extract_title(content):
    m = _HEADING_RE.search(content or "")
    if m:
        return m.group(1).strip()
    plain = re.sub(r"#+", "", (content or "").split("\n")[0]).strip()
    return plain[:80] or "Untitled"


def run_pipeline(post_id, topic, options=None):
    """draft -> humanize -> eval loop. Updates the Post row in place."""
    options = options or {}
    max_iterations = int(options.get("max_iterations", settings.max_iterations))
    threshold = float(options.get("threshold", settings.threshold))
    temperature = float(options.get("temperature", settings.temperature))

    llm = get_llm()
    detector = get_detector()

    _set_status(post_id, "generating", error="")
    try:
        draft = llm.complete(
            DRAFT_SYSTEM, f"Topic: {topic}", temperature=temperature, max_tokens=4096
        )
    except LLMError as e:
        _set_status(post_id, "failed", error=str(e))
        raise

    revisions = []  # (rewrite_count, content, DetectorResult)
    current = draft
    for rewrite_count in range(max_iterations + 1):
        res = detector.score_text(current)
        revisions.append((rewrite_count, current, res))
        if res.score <= threshold:
            break
        if rewrite_count >= max_iterations:
            break
        flagged = [p["text"] for p in res.paragraphs if p["score"] > threshold][:5]
        flag_text = "\n\n---\n\n".join(flagged) if flagged else "none specifically flagged"
        current = llm.complete(
            HUMANIZE_SYSTEM,
            f"Flagged paragraphs:\n{flag_text}\n\nFull post:\n{current}",
            temperature=temperature,
            max_tokens=4096,
        )

    # pick the revision with the lowest (most human) score
    best = min(revisions, key=lambda r: r[2].score)

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

    post = models.Post(id=post_id)
    db = SessionLocal()
    try:
        post = db.get(models.Post, post_id)
        post.title = extract_title(best[1])
        post.content = best[1]
        post.iterations_used = best[0]
        post.final_score = best[2].score
        post.detector = best[2].detector
        post.status = "completed"
        db.commit()
    finally:
        db.close()

    return {
        "status": "completed",
        "post_id": post_id,
        "title": post.title,
        "iterations_used": best[0],
        "final_score": best[2].score,
        "detector": best[2].detector,
        "content": best[1],
    }


def _set_status(post_id, status, error=""):
    db = SessionLocal()
    try:
        post = db.get(models.Post, post_id)
        if post:
            post.status = status
            post.error = error
            db.commit()
    finally:
        db.close()
