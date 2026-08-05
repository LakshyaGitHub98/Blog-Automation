import statistics

from libs.detector.client import (
    DetectorResult,
    _text_hash,
    _sentences,
    split_paragraphs,
)


class MockDetector:
    """Heuristic, GPU-free detector for dev. Uses burstiness (sentence-length
    variance): uniform, formulaic text scores high; varied text scores low.
    Deterministic per input so results are stable across runs."""

    name = "mock"

    def score_text(self, text):
        paras = split_paragraphs(text)
        results = []
        for p in paras:
            sents = _sentences(p)
            lengths = [len(s.split()) for s in sents]
            if len(lengths) < 2:
                score = 0.5
            else:
                mean = statistics.mean(lengths)
                std = statistics.pstdev(lengths)
                burstiness = std / mean if mean else 0.5
                # human-ish text: burstiness ~0.6-1.2 -> score near 0.2-0.4
                # AI-ish text: burstiness ~0.2-0.4 -> score near 0.6-0.8
                score = max(0.03, min(0.97, 0.95 - burstiness))
                score = round(score + _wobble(p), 3)
            results.append({"text": p, "score": score})
        overall = round(statistics.mean(r["score"] for r in results), 3) if results else 0.5
        return DetectorResult(overall, results, self.name)


def _wobble(text):
    # tiny deterministic offset so different texts with same variance differ
    h = int(_text_hash(text)[:6], 16)
    return ((h % 100) - 50) / 2000  # +/-0.025
