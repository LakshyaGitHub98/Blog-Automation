@echo off
REM One-command local startup (no docker needed).
if not exist .venv (
    echo Creating virtual environment and installing deps...
    python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python run.py
