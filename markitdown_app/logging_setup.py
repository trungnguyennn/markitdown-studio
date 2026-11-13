"""Rotating file log shared by both editions (no UI imports here)."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import ORG_NAME

LOG_FORMAT = "%(asctime)s  %(levelname)-8s %(name)s: %(message)s"
PANEL_FORMAT = "%(asctime)s  %(message)s"
PANEL_DATEFMT = "%H:%M:%S"


def log_directory() -> Path:
    if sys.platform == "darwin":
        path = Path.home() / "Library" / "Logs" / ORG_NAME  # shown in Console.app
    else:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / ORG_NAME / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging() -> Path:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    log_file = log_directory() / "app.log"
    try:
        handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(handler)
    except OSError:
        # Logging must never stop the app from starting.
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    # Third-party libraries can be chatty at INFO.
    for noisy in ("pdfminer", "PIL", "urllib3", "charset_normalizer", "magika"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return log_file


def is_panel_record(record: logging.LogRecord) -> bool:
    """Records tagged extra={'file_only': True} go to the log file only."""
    return not getattr(record, "file_only", False)
