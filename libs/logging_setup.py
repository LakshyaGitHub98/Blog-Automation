import logging
import os
from logging.handlers import RotatingFileHandler

from config import settings

_configured = False


def setup_logging():
    """Configure console + rotating file logging once (idempotent)."""
    global _configured
    if _configured:
        return

    level = getattr(logging, settings.log_level, logging.INFO)
    fmt = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    log_dir = os.path.dirname(settings.log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(
        settings.log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    for name in ("openai", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)

    _configured = True
    root.info("logging initialized -> %s (level=%s)", settings.log_file, settings.log_level)
