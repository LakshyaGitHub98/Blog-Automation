# blog-gen

AI blog generator + humanizer pipeline. Writes a blog post, then runs a
self-hosted detector eval loop to push AI-probability below a threshold —
content stays original (never copies source text), so plagiarism checkers pass
naturally.

## Architecture

```
CLI/dashboard → POST /api/generate → (Redis+Celery | inline)
  → Stage 1: draft (LLM)
  → Stage 2: humanize pass (LLM rewrite, flagged paragraphs)
  → Stage 3: detector eval loop (paragraph-level, max N iterations)
  → Postgres/SQLite: posts, revisions, eval_scores
```

- **Generation LLM**: NVIDIA NIM free endpoints (default), OpenAI, or local
  (Ollama/vLLM) — switched via `LLM_PROVIDER`.
- **Detector**: `DETECTOR_MODE=mock` (dev, no GPU) or `colab` (Binoculars
  scores produced on a free GPU, then consumed locally). Later swap in a
  self-hosted GPU box and point it at the same `scores.json` format.

## Quick start (no docker)

```powershell
start.bat
```

or manually:

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env     # add NVIDIA_API_KEY from https://build.nvidia.com
.venv\Scripts\python run.py
```

Open http://127.0.0.1:8000 — dashboard works, generation runs synchronously
(SQLite + mock detector, no Redis needed).

## Quick start (docker compose)

```bash
docker compose up --build
```

API on http://localhost:8000. Compose overrides `DATABASE_URL` (Postgres) and
`REDIS_URL` (async worker). Everything else comes from `.env`.

## Config (`.env`)

| Var | Default | Meaning |
|-----|---------|---------|
| `LLM_PROVIDER` | `nvidia` | `nvidia` \| `openai` \| `local` |
| `LLM_MODEL` | `meta/llama-3.3-70b-instruct` | NVIDIA model names change often — check https://build.nvidia.com |
| `NVIDIA_API_KEY` | — | key from build.nvidia.com (free credits) |
| `DATABASE_URL` | empty → SQLite | set for Postgres |
| `REDIS_URL` | empty → sync mode | set for async Celery |
| `DETECTOR_MODE` | `mock` | `mock` \| `colab` |
| `DETECTOR_RESULTS_PATH` | `detector_results.json` | scores from Colab batch |
| `HUMANIZE_THRESHOLD` | `0.6` | stop when overall AI-score ≤ threshold |
| `MAX_ITERATIONS` | `3` | max rewrite passes |

## API

- `POST /api/generate` `{"topic": "...", "threshold": 0.6, "max_iterations": 3}`
  → `{request_id, status}` (async) or full post (sync)
- `GET /api/status/{id}` — poll while generating
- `GET /api/posts`, `GET /api/posts/{id}` — history + revision scores

## Detector workflow (self-hosted, no local GPU)

1. Collect paragraphs to score into `texts.json` (JSON array of strings).
2. Open https://colab.research.google.com, upload `scripts/colab/binoculars_score.py`
   and `texts.json`, run it on the free T4 runtime.
3. Download `scores.json` to the project root.
4. Set `DETECTOR_MODE=colab` and restart. The pipeline scores against Binoculars.
5. Later: run `binoculars_score.py` on your own GPU box and point
   `DETECTOR_RESULTS_PATH` at its output.

## Threshold tuning

```bash
.venv\Scripts\python -m tools.benchmark --count 10 --human-file human.txt
```

Prints a false-positive curve (human flagged as AI vs AI caught) and a
recommended `HUMANIZE_THRESHOLD`.

## Notes

- NVIDIA NIM free tier is for development/prototyping (rate-limited, ~1k
  credits). It is OpenAI-compatible, so swapping providers is just env change.
- The pipeline never scrapes or copies source text — it generates from a topic,
  so output is original by construction. The eval loop only measures how
  natural it sounds.
- Mock detector is a burstiness heuristic (dev only) so the loop is testable
  without a GPU.
