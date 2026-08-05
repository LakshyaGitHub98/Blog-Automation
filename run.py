"""Single-command dev runner.

- If REDIS_URL is set: spawns a celery worker + uvicorn (matches docker setup).
- If REDIS_URL is empty: runs uvicorn only; /api/generate runs the pipeline
  synchronously in-process (no docker, no redis needed).
"""
import subprocess
import sys
import time

from config import settings


def main():
    procs = []

    if settings.redis_url:
        print("[run] REDIS_URL set -> starting celery worker")
        procs.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "celery",
                    "-A",
                    "apps.worker.tasks:celery_app",
                    "worker",
                    "--loglevel=info",
                    "--pool=solo",
                ]
            )
        )
    else:
        print("[run] no REDIS_URL -> synchronous mode (no worker)")

    port = "8000"
    procs.append(
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "apps.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                port,
                "--reload",
            ]
        )
    )

    print(f"[run] API at http://127.0.0.1:{port}")
    try:
        while True:
            for p in procs:
                if p.poll() is not None:
                    raise SystemExit(f"process exited: {p.args}")
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
