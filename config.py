"""Zentrale JARVIS-Konfiguration.

Lädt Einstellungen aus Umgebungsvariablen (.env-Datei) und stellt sie
allen Modulen über das `Config`-Objekt bereit.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# .env aus dem Projekt-Wurzelverzeichnis laden
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Config:
    # --- Claude / Anthropic ---
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-6"
    claude_max_tokens: int = 1024

    # --- ElevenLabs (optional) ---
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None

    # --- Whisper ---
    whisper_model: str = "base"   # tiny|base|small|medium|large
    whisper_language: str = "de"

    # --- Audio ---
    sample_rate: int = 16000
    wake_chunk_seconds: float = 4.0    # Dauer eines Wake-Word-Lauschfensters
    command_seconds: float = 10.0      # Dauer der eigentlichen Aufnahme nach Wake-Word

    # --- Wake-Phrase ---
    wake_phrase: str = "guten morgen jarvis"

    # --- Persönlichkeit ---
    assistant_name: str = "JARVIS"

    # --- Gedächtnis (Phase 2) ---
    db_path: Path = PROJECT_ROOT / "data" / "jarvis.db"
    memory_pairs: int = 20   # Anzahl Q/A-Paare als Kontext

    # --- WebSocket-Server (Phase 4) ---
    ws_host: str = "127.0.0.1"
    ws_port: int = 8765

    @classmethod
    def from_env(cls) -> "Config":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY fehlt. Bitte in der .env-Datei eintragen."
            )
        return cls(
            anthropic_api_key=api_key,
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY") or None,
            elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID") or None,
        )


CONFIG: Config | None = None


def get_config() -> Config:
    global CONFIG
    if CONFIG is None:
        CONFIG = Config.from_env()
    return CONFIG
