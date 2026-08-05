#!/usr/bin/env bash
# One-command local startup (no docker needed).
set -e
if [ ! -d .venv ]; then
  echo "Creating virtual environment and installing deps..."
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python run.py
