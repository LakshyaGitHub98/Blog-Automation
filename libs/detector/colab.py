import json
import os
import statistics

from libs.detector.mock import _text_hash, _wobble
from libs.detector.client import DetectorResult, split_paragraphs, _sentences


class ColabDetector:
    """Reads scores produced by scripts/colab/binoculars_score.py (run on a
    free GPU — Google Colab/Kaggle). The file maps paragraph sha256 -> score.
    Falls back to the mock heuristic for paragraphs that haven't been scored
    yet (score 0.5 = unknown)."""

    name = "colab"

    def __init__(self, results_path):
        self.results_path = results_path
        self._cache = None
        self._unscored = []

    def unscored_texts(self):
        """Paragraphs from the last score_text() call that had no Binoculars
        score in the results file (they fell back to the mock heuristic)."""
        return self._unscored

    def _load(self):
        if self._cache is not None:
            return self._cache
        self._cache = {}
        if not os.path.exists(self.results_path):
            return self._cache
        with open(self.results_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        rows = data if isinstance(data, list) else data.get("results", [])
        for row in rows:
            self._cache[row["text_hash"]] = float(row["score"])
        return self._cache

    def score_text(self, text):
        cache = self._load()
        paras = split_paragraphs(text)
        results = []
        self._unscored = []
        for p in paras:
            score = cache.get(_text_hash(p))
            if score is None:
                self._unscored.append(p)
                sents = _sentences(p)
                lengths = [len(s.split()) for s in sents]
                if len(lengths) < 2:
                    score = 0.5
                else:
                    mean = statistics.mean(lengths)
                    std = statistics.pstdev(lengths)
                    burstiness = std / mean if mean else 0.5
                    score = max(0.03, min(0.97, 0.95 - burstiness)) + _wobble(p)
                score = round(score, 3)
            results.append({"text": p, "score": round(score, 3)})
        overall = round(statistics.mean(r["score"] for r in results), 3) if results else 0.5
        return DetectorResult(overall, results, self.name)
