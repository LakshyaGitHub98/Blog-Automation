import hashlib
import re


def split_paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def _sentences(paragraph):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", paragraph) if s.strip()]


def _text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class DetectorResult:
    def __init__(self, score, paragraphs, detector):
        self.score = score  # 0..1 probability of being AI-written
        self.paragraphs = paragraphs  # [{"text", "score"}]
        self.detector = detector
