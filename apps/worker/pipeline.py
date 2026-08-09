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
    "You are an experienced essayist writing a polished, professional blog post. "
    "The writing must read as human-authored and low-scoring against AI detectors: "
    "genuine voice, irregular rhythm, and zero machine tells.\n"
    "- Adopt a confident first-person voice with concrete, verifiable detail. Be "
    "honest and precise; never embellish.\n"
    "- Vary sentence lengths dramatically: mix 2-3 word fragments with 25-word "
    "sentences. Do not keep a steady rhythm.\n"
    "- Vary paragraph lengths: some paragraphs 1-2 sentences, others 5-7. Use "
    "'## ' markdown headings for a few sections.\n"
    "- FACT CHECKING IS MANDATORY: Only state facts, figures, names, and quotes "
    "that were supplied in the topic or are common knowledge you are certain "
    "about. If you lack a real number, citation, date, or quote, do NOT invent "
    "one. No fabricated percentages, prices, statistics, 'studies show', "
    "'experts say', or unattributed quotes.\n"
    "- Banned: no emojis; at most one em-dash (—) per paragraph; never write "
    "'In conclusion', 'Furthermore', 'Moreover', 'Additionally', 'delve', "
    "'navigate', 'landscape', 'leverage', 'in today's world', 'it's important "
    "to note', 'at the end of the day', 'as an AI', 'it's no secret', "
    "'in summary', 'everything you need to know', 'at its core', 'studies show'. "
    "Avoid dense bullet-point lists. Never mention that you are an AI or a "
    "language model."
)

HUMANIZE_SYSTEM = (
    "You are a ruthless editor whose explicit goal is to rewrite machine-written "
    "text so it reads as human-written and defeats AI detectors. Rewrite the full "
    "post while keeping every fact intact.\n"
    "- Vary sentence lengths dramatically and DELIBERATELY: alternate very short "
    "sentences (3-6 words) with long ones (20-30 words). Never keep a steady "
    "rhythm. Short fragments are your friend.\n"
    "- Vary paragraph lengths: make some paragraphs just 1-2 sentences, others "
    "5-6. Keep the paragraph breaks (blank lines) — do not merge paragraphs.\n"
    "- Cut formulaic AI phrases and replace them with plain, specific language. "
    "Especially: 'furthermore', 'moreover', 'additionally', 'delve', "
    "'navigate', 'landscape', 'leverage', 'in conclusion', 'at the end of the "
    "day', 'it's important to note', 'in today's world', 'as an AI', 'it's no "
    "secret', 'in summary', 'everything you need to know', 'at its core', "
    "'studies show', 'research indicates'.\n"
    "- Reduce em-dashes (—) to at most one per paragraph; replace the rest with "
    "commas, periods, or a rephrase.\n"
    "- Keep a personal, honest first-person voice with natural transitions, "
    "contractions, and mild imperfection.\n"
    "- FACTUALITY IS MANDATORY: preserve every fact, heading, structure, and the "
    "topic exactly. Never add new facts, statistics, percentages, dollar figures, "
    "attributions, citations, dates, or quotes that are not already in the given "
    "text. If the original lacks a real number, leave it out rather than invent one.\n"
    "- No emojis, no heavy bullet lists.\n"
    "The flagged paragraphs below are the most formulaic; make those sections the "
    "most natural-sounding. Return the complete rewritten post only."
)

_HEADING_RE = re.compile(r"^#+\s+(.+)$", re.MULTILINE)

# The pipeline keeps rewriting until the detector score reaches this literal
# value. NOTE: the mock detector floors scores at ~0.03, so a target of 0.0 is
# in practice unreachable and the loop runs for all `max_iterations`, then serves
# back the best (lowest) revision.
ZERO_TARGET = 0.0


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
    "as an ai",
    "as a language model",
    "it's no secret",
    "it is no secret",
    "in summary",
    "in a nutshell",
    "at its core",
    "in the realm of",
    "in a world where",
    "with the rise of",
    "everything you need to know",
    "essential guide",
    "ultimate guide",
    "comprehensive guide",
    "beginner's guide",
    "beginners guide",
    "step-by-step",
    "step by step",
    "outside the box",
    "at the forefront",
    "the bottom line",
    "all in all",
    "last but not least",
    "boast",
    "supercharge",
    "revolutioniz",
    "drive results",
    "tailored to",
    "getting started with",
    "take a closer look",
    "whether you're a beginner",
    "if you're looking to",
    "it's not just",
    "more than just",
    "rapidly evolving",
    "fast-evolving",
    "ever-evolving",
    "pro tip",
    "ins and outs",
    "wide range of",
    "key takeaways",
    "stand as a testament",
    "stands as a testament",
    "testament to",
    "streamlined",
    "sustainable growth",
    "harness",
    "unleash",
    "transformation journey",
    "navigating the",
    "in the modern era",
    "modern world",
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


# Patterns that, when introduced into content, are unsupported fabrications the
# writer had no basis for: percentages, currency/count figures, dates, and
# unattributed claims ("studies show", "experts say", "a recent report").
_FABRICATED_PATTERNS = [
    re.compile(r"\b\d{1,3}(?:[.,]\d{3})*\s?%|\b\d{1,3}(?:[.,]\d{3})*\s+percent\b", re.IGNORECASE),
    re.compile(r"[$£€₹]\s?\d+(?:[.,]\d+)?\s?(k|m|b|million|billion|thousand)?\b", re.IGNORECASE),
    re.compile(r"\b\d[\d,]*\+(?:\s?users|\s?customers|\s?downloads|\s?people|\s?readers)?\b", re.IGNORECASE),
    re.compile(r"\b(?:\d{1,2}\s)?(?:january|february|march|april|may|june|july|august|september|october|november|december)\s\d{4}\b", re.IGNORECASE),
    re.compile(r"((?:across|according to)\s+)?(\d[\d,]*)\s(?:studies?|reports?|surveys?|respondents?)", re.IGNORECASE),
    re.compile(r"\b(?:studies? show|research shows|research indicates|experts say|a recent (?:study|report|survey)|the data shows)\b", re.IGNORECASE),
]


_FABRICATED_PATTERN = re.compile(
    "|".join(p.pattern for p in _FABRICATED_PATTERNS),
    re.IGNORECASE,
)


def _whitelisted(fragment, base):
    """Return True if the fabrication-like fragment already exists verbatim in the
    ground truth (previous draft / topic), i.e. it is real given information."""
    frag = fragment.strip().lower()
    if len(frag) <= 2:
        return True  # too short/vague to be a fabricated claim
    return frag in (base or "").lower()


_PERSONAL_VOICE = re.compile(r"\b(?:my|i|we|our)\b", re.IGNORECASE)


def strip_invented_facts(text, base):
    """Remove sentences that introduce an unsupported statistic, figure, date, or
    attribution and show no sign of a real given fact. Ground truth is `base` (the
    previous draft plus original topic), so real numbers already present are never
    touched. Returns (cleaned_text, removed_count, removed_fragments)."""
    sentences = re.split(r"(?<=[.!?])\s+", text or "")
    removed = 0
    frags = []
    kept = []
    for sent in sentences:
        low = sent.lower()
        m = _FABRICATED_PATTERN.search(low)
        if not m:
            kept.append(sent)
            continue
        frag = m.group(0)
        if _whitelisted(frag, base):
            kept.append(sent)
            continue
        # The sentence introduces a figure with no basis in the draft/topic.
        removed += 1
        frags.append(frag)
        # For first-person, opinion-led sentences, strip only the fabricated
        # fragment (and surrounding filler) so we don't lose the author's point.
        # Otherwise drop the whole sentence to avoid a dangling unsourced claim.
        cleaned = _FABRICATED_PATTERN.sub(" ", sent).strip()
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        if _PERSONAL_VOICE.search(low) and _has_content(cleaned):
            kept.append(_trim_around_stat(cleaned))
    return " ".join(kept).strip(), removed, frags


def _has_content(s):
    words = re.findall(r"[a-z0-9]+", s.lower())
    return any(w not in _FILLER for w in words)


_FILLER = set("the a an of on in to this is it was were by with for and or but at from been has have had".split())


def _trim_around_stat(s):
    # Collapse "In we pivoted."-style artifacts left after removing a figure.
    return re.sub(r"\s+(?:in|on|by|at|of|for)\s*$", "", s).strip()


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
    temperature = float(options.get("temperature", settings.temperature))
    max_tokens = int(options.get("max_tokens", settings.max_tokens))

    detector = get_detector()

    revisions = []  # (rewrite_count, content, DetectorResult)
    error = None
    try:
        _set_status(post_id, "generating", stage="draft")
        logger.info("post %s | stage=draft start", post_id)
        draft = complete_with_failover(
            DRAFT_SYSTEM, f"Topic: {topic}", temperature=temperature, max_tokens=max_tokens
        )
        draft, removed_draft, draft_frags = strip_invented_facts(draft, topic)
        if removed_draft:
            logger.warning(
                "post %s | stripped %d invented figure(s) from draft: %s",
                post_id,
                removed_draft,
                ", ".join(draft_frags[:5]),
            )
        logger.info("post %s | stage=draft done (%d chars)", post_id, len(draft))

        current = draft
        humanized = 0
        for rewrite_count in range(max_iterations + 1):
            _set_status(post_id, "generating", stage="evaluating")
            res = detector.score_text(current)
            if hasattr(detector, "unscored_texts"):
                unscored = detector.unscored_texts()
                if unscored:
                    logger.warning(
                        "post %s | %d paragraphs have no %s score (mock fallback used). "
                        "Score them: python -m tools.colab_export --post %s",
                        post_id,
                        len(unscored),
                        res.detector,
                        post_id,
                    )
            revisions.append((rewrite_count, current, res))
            logger.info(
                "post %s | eval round=%d overall=%.3f zero_target=%.3f",
                post_id,
                rewrite_count,
                res.score,
                ZERO_TARGET,
            )
            if res.score <= ZERO_TARGET:
                logger.info("post %s | accepted (score reached zero)", post_id)
                break
            if rewrite_count >= max_iterations:
                logger.info("post %s | max iterations reached", post_id)
                break

            # Target the most AI-sounding paragraphs each pass so the overall
            # score keeps dropping toward zero.
            flagged = [
                p["text"]
                for p in sorted(res.paragraphs, key=lambda x: x["score"], reverse=True)
            ][:5]
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
                f"(target: 0.00). Main issues detected: {detector_hints(current)}."
            )
            new = complete_with_failover(
                HUMANIZE_SYSTEM,
                f"{feedback}\n\nFlagged paragraphs:\n{flag_text}\n\nFull post:\n{current}",
                temperature=temperature,
                max_tokens=max_tokens,
            )
            # Anti-fabrication guard: strip any invented stat/figure/attribution
            # the rewrite introduced that we have no basis for.
            new, removed_fabs, fab_frags = strip_invented_facts(new, f"{topic}\n\n{current}")
            if removed_fabs:
                logger.warning(
                    "post %s | stripped %d invented figure(s): %s",
                    post_id,
                    removed_fabs,
                    ", ".join(fab_frags[:5]),
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
