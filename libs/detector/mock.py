import re
import statistics

from libs.detector.client import (
    DetectorResult,
    _text_hash,
    _sentences,
    split_paragraphs,
)

# Formulaic / AI-tell phrases. Multi-word and construction-level, not generic
# single words, so normal human writing isn't punished for common English.
_CLICHES = [
    "in today's fast-paced world",
    "in today's digital world",
    "in today's world",
    "in today's fast paced world",
    "it's important to note",
    "it is important to note",
    "it's worth noting",
    "it is worth noting",
    "worth noting that",
    "delve into",
    "delve deeper",
    "let's dive in",
    "lets dive in",
    "navigate the complexities",
    "navigate the world of",
    "in conclusion",
    "to summarize",
    "to sum up",
    "at the end of the day",
    "in the world of",
    "when it comes to",
    "it goes without saying",
    "needless to say",
    "unlock the",
    "unlock your",
    "game-changer",
    "game changer",
    "elevate your",
    "elevate the",
    "furthermore,",
    "moreover,",
    "additionally,",
    "in addition,",
    "firstly,",
    "secondly,",
    "lastly,",
    "myriad of",
    "a testament to",
    "testament to the",
    "underscore",
    "in essence",
    "ever-evolving",
    "ever evolving",
    "cutting-edge",
    "state-of-the-art",
    "in this article",
    "in this blog post",
    "this blog post will",
    "this article will",
    "harness the power",
    "harnessing the power",
    "embark on",
    "shed light on",
    "sheds light on",
    "seamless experience",
    "a seamless",
    "holistic approach",
    "empower you",
    "empowers you",
    "transformative journey",
    "key takeaways",
    "here are some",
    "whether you are a seasoned",
    "whether you're a seasoned",
    "in the fast-paced",
    "play a crucial role",
    "plays a crucial role",
    "play a vital role",
    "it is essential to",
    "it's essential to",
    "remember that",
    "keep in mind that",
    "as we all know",
    "in the ever-evolving",
]


class MockDetector:
    """GPU-free heuristic detector.

    Scores 0..1 (probability of being AI-written) from a weighted set of
    deterministic text signals: sentence-length burstiness, em-dash density,
    formulaic AI phrase usage, paragraph-length uniformity, bullet density and
    type-token ratio. Formulaic/smooth LLM output scores high; varied, natural
    writing scores low. Deterministic per input so the eval loop is stable.
    """

    name = "mock"

    def score_text(self, text):
        paras = split_paragraphs(text)
        whole = _score(_features(text))
        results = []
        for p in paras:
            sents = _sentences(p)
            if len(sents) < 2:
                # Headings / one-liners: no signal, keep neutral so they are
                # never flagged as AI and don't drag the overall score.
                score = 0.35
            else:
                local = _score(_features(p)) + _wobble(p)
                # Blend the paragraph's own signal with the whole-text signal,
                # so paragraphs inside an AI-ish doc are easier to flag.
                score = round(0.6 * local + 0.4 * whole, 3)
            results.append({"text": p, "score": score})
        # Overall comes from whole-text statistics (like real detectors), not
        # the paragraph average, so em-dash / cliché / rhythm tells count.
        overall = round(whole + _wobble(text), 3)
        return DetectorResult(overall, results, self.name)


def _features(text):
    paras = split_paragraphs(text)
    sentences = _sentences(text)
    words = re.findall(r"[a-z0-9']+", text.lower())
    chars = max(len(text), 1)

    # Sentence-length coefficient of variation per paragraph (burstiness).
    cvs = []
    for p in paras:
        lens = [len(s.split()) for s in _sentences(p)]
        if len(lens) >= 2:
            m = statistics.mean(lens)
            if m:
                cvs.append(statistics.pstdev(lens) / m)
    burstiness = statistics.mean(cvs) if cvs else 0.5

    # Overall sentence-length CV (uniform rhythm -> AI-ish).
    s_lens = [len(s.split()) for s in sentences]
    if len(s_lens) >= 2 and statistics.mean(s_lens) > 0:
        overall_cv = statistics.pstdev(s_lens) / statistics.mean(s_lens)
    else:
        overall_cv = 0.5

    # Em-dash / en-dash density per 1000 chars.
    em_density = (text.count("\u2014") + text.count("\u2013")) / (chars / 1000)

    low = text.lower()
    phrase_hits = sum(low.count(c) for c in _CLICHES)

    # Paragraph-length uniformity.
    p_lens = [len(p.split()) for p in paras]
    if len(p_lens) >= 2 and statistics.mean(p_lens) > 0:
        p_cv = statistics.pstdev(p_lens) / statistics.mean(p_lens)
    else:
        p_cv = 0.5

    # Bullet/list line density.
    lines = [l for l in text.splitlines() if l.strip()]
    bullet_lines = sum(
        1
        for l in lines
        if re.match(r"^\s*(?:[-*•]|\d{1,2}[.)])\s", l)
    )
    bullet_frac = bullet_lines / max(len(lines), 1)

    ttr = (len(set(words)) / len(words)) if words else 1.0

    return {
        "burstiness": burstiness,
        "overall_cv": overall_cv,
        "em_density": em_density,
        "phrase_hits": phrase_hits,
        "p_cv": p_cv,
        "bullet_frac": bullet_frac,
        "ttr": ttr,
    }


def _score(f):
    s = 0.42

    b = f["burstiness"]
    if b >= 0.9:
        s -= 0.10
    elif b >= 0.6:
        s -= 0.05
    else:
        s += 0.12  # smooth, samey rhythm is the signal (noisy on tiny samples)

    oc = f["overall_cv"]
    if oc >= 0.75:
        s -= 0.05
    elif oc <= 0.30:
        s += 0.10

    # Em-dashes are the single biggest free-LLM tell: up to +0.40.
    s += min(0.40, f["em_density"] * 0.16)

    s += min(0.25, f["phrase_hits"] * 0.06)

    pc = f["p_cv"]
    if pc <= 0.25:
        s += 0.12
    elif pc >= 0.55:
        s -= 0.05

    bf = f["bullet_frac"]
    if bf >= 0.30:
        s += 0.20
    elif bf >= 0.15:
        s += 0.08

    t = f["ttr"]
    if t <= 0.50:
        s += 0.10
    elif t >= 0.70:
        s -= 0.05

    return max(0.03, min(0.97, s))


def _wobble(text):
    # tiny deterministic offset so different texts with same variance differ
    h = int(_text_hash(text)[:6], 16)
    return ((h % 100) - 50) / 2000  # +/-0.025
