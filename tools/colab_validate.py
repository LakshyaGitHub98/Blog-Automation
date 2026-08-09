"""Validate final text against Colab Binoculars scores.

Run this after you've scored your paragraphs on Colab and have scores.json:

    python -m tools.colab_validate --post <post_id>            # last completed post
    python -m tools.colab_validate --file post.txt             # raw text file
    python -m tools.colab_validate --text "paragraph one.\n\nparagraph two."

Prints a per-paragraph report (Binoculars score vs threshold), flags paragraphs
over the threshold, and lists any that still have NO Binoculars score yet (the
mock heuristic is used for those until you score them on Colab).

This is the real-detector check: mock mode can pass while GPTZero/ZeroGPT flag
the output, so verify the final version here before trusting it.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings  # noqa: E402
from libs.detector.colab import ColabDetector  # noqa: E402


def load_text(args):
    if args.post:
        from db.database import SessionLocal
        from db import models

        db = SessionLocal()
        try:
            post = db.get(models.Post, args.post)
            if not post:
                raise SystemExit(f"post {args.post} not found")
            return post.content
        finally:
            db.close()
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            return f.read()
    if args.text:
        return args.text
    from db.database import SessionLocal
    from db import models

    db = SessionLocal()
    try:
        post = (
            db.query(models.Post)
            .filter(models.Post.status == "completed")
            .order_by(models.Post.created_at.desc())
            .first()
        )
    finally:
        db.close()
    if not post:
        raise SystemExit("no completed post found; pass --post, --file, or --text")
    return post.content


def main():
    ap = argparse.ArgumentParser(description="Validate text against Colab Binoculars scores")
    ap.add_argument("--post", default=None, help="post id (defaults to latest completed post)")
    ap.add_argument("--file", default=None, help="raw text file")
    ap.add_argument("--text", default=None, help="inline text")
    ap.add_argument("--scores", default=settings.detector_results_path, help="scores.json path")
    ap.add_argument("--threshold", type=float, default=settings.threshold, help="pass threshold")
    args = ap.parse_args()

    detector = ColabDetector(args.scores)
    text = load_text(args)
    res = detector.score_text(text)
    unscored = detector.unscored_texts()

    print(f"Detector: {res.detector} | scores file: {args.scores}")
    print(f"Overall Binoculars AI-score: {res.score:.3f} "
          f"(target <= {args.threshold}) -> {'PASS' if res.score <= args.threshold else 'FAIL'}")
    print("-" * 70)
    for i, p in enumerate(res.paragraphs, 1):
        mark = "FLAG" if p["score"] > args.threshold else "ok  "
        print(f"{i:>2}. [{mark}] {p['score']:.3f}  {p['text'][:70].strip()}")
    print("-" * 70)

    flagged = [p for p in res.paragraphs if p["score"] > args.threshold]
    print(f"Flagged paragraphs: {len(flagged)}")
    if flagged:
        print("\nFlagged text (paste these into a targeted humanize pass):")
        for p in flagged:
            print("\n---\n" + p["text"])
    if unscored:
        print(f"\nNOTE: {len(unscored)} paragraphs have no Binoculars score yet "
              "(scored with the mock heuristic). Run:")
        print(f"  python -m tools.colab_export {'--post ' + args.post if args.post else '--file ' + (args.file or '')}")
        print("then score texts.json on Colab and re-run this tool.")


if __name__ == "__main__":
    main()
