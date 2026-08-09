"""Export paragraphs to texts.json for the Colab Binoculars scorer.

The pipeline scores against `DETECTOR_RESULTS_PATH` (scores.json). That file is
produced by scripts/colab/binoculars_score.py on a free GPU (Google Colab T4).
This tool collects the paragraphs you want scored — from a completed post, a raw
text file, or inline text — into texts.json.

Usage:
    python -m tools.colab_export --post <post_id>
    python -m tools.colab_export --post <post_id> --include-revisions
    python -m tools.colab_export --file post.txt
    python -m tools.colab_export --text "paragraph one.\n\nparagraph two."

Then: upload texts.json + scripts/colab/binoculars_score.py to Colab, run it,
download scores.json into the project root, and (re)start with DETECTOR_MODE=colab.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.detector.client import split_paragraphs  # noqa: E402

DEFAULT_OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "texts.json"
)


def load_post_text(post_id, include_revisions):
    from db.database import SessionLocal
    from db import models

    db = SessionLocal()
    try:
        post = db.get(models.Post, post_id)
        if not post:
            raise SystemExit(f"post {post_id} not found")
        texts = [post.content]
        if include_revisions:
            for r in sorted(post.revisions, key=lambda x: x.iteration):
                texts.append(r.content)
        return texts
    finally:
        db.close()


def load_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return [f.read()]


def main():
    ap = argparse.ArgumentParser(description="Export paragraphs to texts.json for Colab Binoculars")
    ap.add_argument("--post", default=None, help="post id (defaults to latest completed post)")
    ap.add_argument("--include-revisions", action="store_true",
                    help="also export every humanize revision (cover all hashes in one Colab run)")
    ap.add_argument("--file", default=None, help="raw text file to split into paragraphs")
    ap.add_argument("--text", default=None, help="inline text to split into paragraphs")
    ap.add_argument("--out", default=DEFAULT_OUT, help="output path (default: texts.json)")
    args = ap.parse_args()

    if args.post:
        sources = load_post_text(args.post, args.include_revisions)
    elif args.file:
        sources = load_file(args.file)
    elif args.text:
        sources = [args.text]
    else:
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
        sources = [post.content]

    seen, paragraphs = set(), []
    for s in sources:
        for p in split_paragraphs(s):
            if p not in seen:
                seen.add(p)
                paragraphs.append(p)

    if not paragraphs:
        raise SystemExit("no paragraphs found")

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(paragraphs, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(paragraphs)} unique paragraphs to {args.out}")
    print("Next steps:")
    print("  1. Upload texts.json + scripts/colab/binoculars_score.py to")
    print("     https://colab.research.google.com and run it (free T4).")
    print("  2. Download scores.json into the project root.")
    print("  3. Set DETECTOR_MODE=colab in .env and restart the backend.")


if __name__ == "__main__":
    main()
