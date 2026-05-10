"""Zentrales Logging für JARVIS.

Schreibt in `data/logs/jarvis.log` (rotierend, ca. 5 MB pro Datei,
3 Backups) und zusätzlich auf stderr für den interaktiven Betrieb.

Im Daemon-Modus (z. B. unter LaunchAgent) gehen Print-Ausgaben
verloren – über `logger.py` bleiben sie erhalten.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
LOG_DIR = PROJECT_ROOT / "data" / "logs"
LOG_FILE = LOG_DIR / "jarvis.log"

_INITIALIZED = False


def setup() -> logging.Logger:
    """Konfiguriert den Root-Logger einmalig und liefert ihn zurück."""
    global _INITIALIZED
    root = logging.getLogger()
    if _INITIALIZED:
        return root

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)

    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    root.setLevel(logging.INFO)

    # Drittanbieter weniger gesprächig machen
    for noisy in ("httpx", "httpcore", "anthropic", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _INITIALIZED = True
    return root


def get(name: str) -> logging.Logger:
    """Modul-spezifischen Logger zurückgeben (Setup wird ggf. nachgeholt)."""
    if not _INITIALIZED:
        setup()
    return logging.getLogger(name)
