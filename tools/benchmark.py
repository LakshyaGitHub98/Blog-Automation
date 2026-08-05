"""Threshold tuning tool.

Scores a set of AI-generated + human-written texts with the current detector
and prints a false-positive curve to help pick HUMANIZE_THRESHOLD.

Usage:
    python -m tools.benchmark --count 10 --topics-file topics.txt
    python -m tools.benchmark --human-file human_samples.txt --count 5

Output: per-threshold false-positive (human flagged as AI) + true-positive
(AI caught) rates, plus a recommended threshold.
"""
import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.detector import get_detector  # noqa: E402

DEFAULT_TOPICS = [
    "How to build a morning routine that actually sticks",
    "Why side projects fail and how to avoid it",
    "The real cost of remote work on friendships",
    "How I stopped checking my phone every 5 minutes",
    "A beginner's guide to personal finance in 2026",
    "Why your team's standups are wasting everyone's time",
    "How to learn a new programming language fast",
    "The psychology behind impulsive buying",
    "What 3 months of cold showers taught me",
    "How to negotiate your salary like a pro",
]

HUMAN_SAMPLES = [
    "I didn't plan to start this company. It started as a weekend script that "
    "one friend asked about, then another, and suddenly I was taking calls during "
    "lunch. The whole thing felt accidental, but looking back, every step was me "
    "saying yes when I could have said no.",
    "We moved three times before I turned ten. Each time I learned a new "
    "language, lost a set of friends, and figured out which games kids played "
    "in the schoolyard. My mother always said it made us tougher. I think it "
    "mostly made us tired.",
    "The first time I spoke at a conference my hands were shaking so badly I "
    "dropped the clicker twice. Someone in the back laughed. I remember thinking, "
    "well, at least the slides are boring enough to look at. Thirty seconds later "
    "my mouth caught up with my nerves and somehow it went fine.",
    "What nobody tells you about freelancing is that the hardest part isn't "
    "finding clients. It's the empty Tuesday afternoons when no one replies and "
    "you start questioning every decision you ever made. Then a payment lands at "
    "6pm and you're suddenly the smartest person alive again.",
    "My grandfather kept a notebook of every meal he ever cooked, going back to "
    "1962. The handwriting gets better after he retired. Sometimes the notes say "
    "just 'rice and eggs'. Those pages smell like the kitchen and I never throw "
    "them away.",
]


def load_texts(path):
    with open(path, "r", encoding="utf-8") as f:
        data = f.read()
    try:
        parsed = json.loads(data)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except json.JSONDecodeError:
        pass
    return [p.strip() for p in data.split("\n\n") if p.strip()]


def score(parts):
    detector = get_detector()
    scores = []
    for p in parts:
        scores.append(detector.score_text(p).score)
    return scores


def curve(ai_scores, human_scores):
    print("\nThreshold | False-positive (human flagged) | True-positive (AI caught)")
    print("-" * 70)
    best = None
    best_loss = None
    for t in [x / 100 for x in range(5, 85, 5)]:
        fp = sum(1 for s in human_scores if s > t) / max(len(human_scores), 1)
        tp = sum(1 for s in ai_scores if s > t) / max(len(ai_scores), 1)
        loss = fp * 2 + (1 - tp)  # weight false positives higher
        if best_loss is None or loss < best_loss:
            best_loss = loss
            best = t
        print(f"{t:9.2f} | {fp*100:25.1f}% | {tp*100:.1f}%")
    print(f"\nRecommended HUMANIZE_THRESHOLD: {best:.2f}")
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=5, help="number of AI posts to generate")
    ap.add_argument("--topics-file", default=None, help="newline-separated topics")
    ap.add_argument("--human-file", default=None, help="file with human samples (txt or JSON list)")
    ap.add_argument("--draft-only", action="store_true", help="skip humanize/eval loop (cheaper)")
    args = ap.parse_args()

    topics = DEFAULT_TOPICS[: args.count]
    if args.topics_file:
        with open(args.topics_file, "r", encoding="utf-8") as f:
            topics = [l.strip() for l in f if l.strip()][: args.count]

    human_parts = HUMAN_SAMPLES
    if args.human_file:
        human_parts = load_texts(args.human_file)

    from apps.worker.pipeline import DRAFT_SYSTEM, HUMANIZE_SYSTEM, extract_title
    from libs.llm import get_llm

    llm = get_llm()
    ai_parts = []
    print(f"Generating {len(topics)} posts...")
    for i, topic in enumerate(topics, 1):
        print(f"  [{i}/{len(topics)}] {topic[:50]}")
        text = llm.complete(DRAFT_SYSTEM, f"Topic: {topic}", max_tokens=2000)
        if not args.draft_only:
            text = llm.complete(
                HUMANIZE_SYSTEM,
                f"Flagged paragraphs:\n(not flagged yet)\n\nFull post:\n{text}",
                max_tokens=2000,
            )
        ai_parts.extend([p for p in text.split("\n\n") if p.strip()][:8])

    print(f"\nScoring {len(ai_parts)} AI paragraphs and {len(human_parts)} human paragraphs...")
    ai_scores = score(ai_parts)
    human_scores = score(human_parts)

    print(f"\nAI paragraphs:  mean={statistics.mean(ai_scores):.3f} "
          f"min={min(ai_scores):.3f} max={max(ai_scores):.3f}")
    print(f"Human paragraphs: mean={statistics.mean(human_scores):.3f} "
          f"min={min(human_scores):.3f} max={max(human_scores):.3f}")
    curve(ai_scores, human_scores)


if __name__ == "__main__":
    main()
