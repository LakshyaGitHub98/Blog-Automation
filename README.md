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

Needs **two terminals**: the API backend and the Next.js dashboard.

**1) Backend** (port 8000):

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env     # add GROQ_API_KEY from https://console.groq.com (fastest)
.venv\Scripts\python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
# or: start.bat   (runs run.py -> uvicorn --reload)
```

Runs synchronously with SQLite + mock detector — no Redis, no Postgres, no GPU.

**Local Ollama (free, offline, no GPU)**: install from https://ollama.com,
then `ollama pull qwen2.5:7b`. Set in `.env`:

```powershell
LLM_PROVIDER=local
LLM_PROVIDER_PRIORITY=local,groq
LOCAL_MODEL=qwen2.5:7b
LOCAL_TIMEOUT_SECONDS=600   # CPU generation is slow; never let it time out
LOCAL_NUM_CTX=8192          # prompt + 2048-token output must fit
```

Then restart the backend. First generation loads the model (takes a minute);
subsequent ones reuse it. The `.env` already ships local-first.

**2) Frontend** (port 3000):

```powershell
cd web
npm install
npm run dev
```

`web/next.config.ts` proxies `/api/*` to the backend, so open **http://localhost:3000**.
Production: `cd web && npm run build && npm start`.

## Quick start (docker compose)

```bash
docker compose up --build
```

API on http://localhost:8000. Compose overrides `DATABASE_URL` (Postgres) and
`REDIS_URL` (async worker). Everything else comes from `.env`.

## Config (`.env`)

| Var | Default | Meaning |
|-----|---------|---------|
| `LLM_PROVIDER` | `local` | `groq` \| `nvidia` \| `openai` \| `local` (primary) |
| `LOCAL_MODEL` | `qwen2.5:7b` | Ollama model (`ollama pull qwen2.5:7b`) |
| `LOCAL_BASE_URL` | `http://localhost:11434/v1` | Ollama OpenAI-compatible endpoint |
| `LOCAL_TIMEOUT_SECONDS` | `600` | per-call timeout for local (CPU is slow) |
| `LOCAL_NUM_CTX` | `8192` | Ollama context window (prompt + output must fit) |
| `GROQ_API_KEY` | — | fast key from console.groq.com (recommended) |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model |
| `NVIDIA_API_KEY` | — | key from build.nvidia.com (fallback) |
| `LLM_PROVIDER_PRIORITY` | `local,groq` | provider failover order |
| `LLM_TIMEOUT_SECONDS` | `30` | max seconds per LLM call before failover |
| `LLM_RATE_LIMIT_RETRIES` | `3` | auto-retry count on provider 429 rate limits (honors `Retry-After`) |
| `NVIDIA_TIMEOUT_SECONDS` | `15` | cap for the slow NVIDIA NIM fallback so it can't stall the pipeline |
| `MAX_ITERATIONS` | `2` | max eval/humanize rounds (draft counts as round 0) |
| `MIN_HUMANIZE_PASSES` | `1` | always run at least this many humanize rewrites, even if the draft already passes |
| `MAX_TOKENS` | `2048` | LLM response cap (~1200-1500 word blog); keeps free-tier TPM happy |
| `DATABASE_URL` | empty → SQLite | set for Postgres |
| `REDIS_URL` | empty → bg thread | set for async Celery |
| `DETECTOR_MODE` | `mock` | `mock` \| `colab` |
| `DETECTOR_RESULTS_PATH` | `detector_results.json` | scores from Colab batch |
| `HUMANIZE_THRESHOLD` | `0.6` | stop when overall AI-score ≤ threshold |
| `JOB_STALE_SECONDS` | `900` | auto-fail queued/generating jobs older than this |
| `LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `LOG_FILE` | `logs/app.log` | rotating log file (console + file) |

## API

- `POST /api/generate` `{"topic": "...", "threshold": 0.6, "max_iterations": 3}`
  → `{request_id, status: queued}` (always async; polls `/api/status` — a background
  thread runs the pipeline in-process when Redis is not configured)
- `GET /api/status/{id}` — poll while generating (includes `stage`, `elapsed_seconds`)
- `GET /api/posts`, `GET /api/posts/{id}` — history + revision scores

## Detector workflow (self-hosted, no local GPU)

The pipeline's built-in `mock` detector is a dev heuristic — it can pass while
real detectors (GPTZero, ZeroGPT, etc.) still flag the output. Validate with
**Binoculars**, the best open-source detector, scored for free on a Colab GPU:

1. Export the paragraphs of a post to `texts.json`:
   ```powershell
   .venv\Scripts\python -m tools.colab_export --post <post_id>
   # or from a file:  python -m tools.colab_export --file post.txt
   ```
2. Open https://colab.research.google.com, upload `texts.json` and
   `scripts/colab/binoculars_score.py`, run it on the free T4 runtime.
3. Download `scores.json` into the project root.
4. Set `DETECTOR_MODE=colab` and restart. The pipeline scores against
   Binoculars; paragraphs not yet scored fall back to the mock heuristic and a
   warning tells you to export/score them.
5. Check any final text against the real scores without running the pipeline:
   ```powershell
   .venv\Scripts\python -m tools.colab_validate --post <post_id>
   .venv\Scripts\python -m tools.colab_validate --file final.txt
   ```
   It prints a per-paragraph report, flags anything over the threshold, and
   lists paragraphs that still have no Binoculars score.

Because humanize rewrites change the text, each new version has new hashes —
for the tightest loop, run the automated pipeline with `DETECTOR_MODE=mock`,
then validate the final output with `colab_validate`, and run one more targeted
humanize pass on any flagged paragraphs before re-validating.

## Threshold tuning

```bash
.venv\Scripts\python -m tools.benchmark --count 10 --human-file human.txt
```

Prints a false-positive curve (human flagged as AI vs AI caught) and a
recommended `HUMANIZE_THRESHOLD`.

## Troubleshooting

- **`Errno 10048` when starting the backend** — port 8000 is already in use by a
  leftover uvicorn. Find and kill it, then retry:
  ```powershell
  netstat -ano | findstr :8000     # last column = PID
  taskkill /PID <PID> /F
  ```
- **`429` rate-limit errors (Groq/NVIDIA)** — the free tiers cap tokens/minute
  (Groq: 12k TPM). The pipeline now retries automatically up to
  `LLM_RATE_LIMIT_RETRIES` times and honors the provider's `Retry-After` header.
  If a job still fails with "rate limited", wait ~60s and generate again.
  Space out back-to-back generations, keep `MAX_TOKENS=2048`, and lower
  `MAX_ITERATIONS` if you need many posts per minute.
- **NVIDIA timeouts** — NIM free endpoints are slow; the fallback is capped at
  `NVIDIA_TIMEOUT_SECONDS=15` so it can't stall the pipeline. Prefer Groq
  (`LLM_PROVIDER_PRIORITY=groq,nvidia`). Verify your key is valid at
  https://build.nvidia.com.
- **`no LLM provider configured`** — set at least one key in `.env`
  (`GROQ_API_KEY`, `NVIDIA_API_KEY`, or `OPENAI_API_KEY`).
- **Dashboard shows no posts / API unreachable** — the Next.js dev server only
  proxies to `127.0.0.1:8000`; make sure the backend is running first (or set
  `API_BASE_URL` in `web/` to point at a remote backend).

## Notes

- NVIDIA NIM free tier is for development/prototyping (rate-limited, ~1k
  credits). It is OpenAI-compatible, so swapping providers is just env change.
- The pipeline never scrapes or copies source text — it generates from a topic,
  so output is original by construction. The eval loop only measures how
  natural it sounds.
- Mock detector is a burstiness heuristic (dev only) so the loop is testable
  without a GPU.
