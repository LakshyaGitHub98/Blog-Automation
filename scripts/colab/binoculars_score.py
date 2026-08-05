"""Batch scorer for the self-hosted Binoculars detector.

Run this on a free GPU (Google Colab T4 / Kaggle P100). No local GPU needed.

Workflow:
  1. On your machine: put paragraphs you want scored into `texts.json`
     (list of strings), or generate it via the API tool.
  2. In Colab: upload texts.json, then run this file:
         !python binoculars_score.py
  3. Download scores.json and point the app at it:
         DETECTOR_MODE=colab
         DETECTOR_RESULTS_PATH=<path to scores.json>

Binoculars is zero-shot (no training data), which is why it is the best
open-source detector to test a humanizer against.
"""
import hashlib
import json
import os
import sys


def install():
    try:
        import binoculars  # noqa: F401
    except ImportError:
        os.system("pip install -q binoculars")


def hash_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_texts():
    if not os.path.exists("texts.json"):
        print("texts.json not found. Create a JSON array of paragraph strings first.")
        sys.exit(1)
    with open("texts.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("texts", [])


def main():
    install()
    from binoculars import Binoculars

    texts = load_texts()
    print(f"Scoring {len(texts)} paragraphs...")

    # 4-bit quantized variant fits on a T4 (~8GB). Drop mode="accuracy" if you
    # get OOM. max_length limits context for speed.
    bino = Binoculars(mode="accuracy", max_length=512)
    scores = bino.compute_score(texts)

    results = [
        {"text_hash": hash_text(t), "score": float(s)} for t, s in zip(texts, scores)
    ]
    with open("scores.json", "w", encoding="utf-8") as f:
        json.dump({"results": results}, f, indent=2)
    print(f"Wrote scores.json ({len(results)} entries). Download it and set "
          "DETECTOR_MODE=colab + DETECTOR_RESULTS_PATH=scores.json")


if __name__ == "__main__":
    main()
