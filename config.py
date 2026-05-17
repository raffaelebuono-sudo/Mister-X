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
    # Extended Thinking: JARVIS denkt vor komplexen Antworten sichtbar
    # nach (bessere Lagebeurteilung). budget_tokens = Denk-Spielraum.
    thinking_enabled: bool = True
    thinking_budget: int = 1024

    # --- ElevenLabs (Premium-Stimme, optional) ---
    # Nur der API-Key reicht – wenn keine voice_id gesetzt ist, wählt
    # JARVIS automatisch eine Stimme aus dem Konto. turbo_v2_5 ist
    # schnell und kann Deutsch (gut für flüssige Reaktion).
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None
    elevenlabs_model: str = "eleven_turbo_v2_5"
    # macOS-Stimme erzwingen (z. B. eine geladene Premium-Siri-Stimme).
    # Leer = automatische Auswahl der besten deutschen Stimme.
    mac_voice: str | None = None

    # --- Whisper ---
    whisper_model: str = "base"   # tiny|base|small|medium|large
    whisper_language: str = "de"

    # --- Audio ---
    sample_rate: int = 16000
    wake_chunk_seconds: float = 4.0    # Dauer eines Wake-Word-Lauschfensters
    command_seconds: float = 10.0      # Dauer der eigentlichen Aufnahme nach Wake-Word

    # --- Aktivierung ---
    # "code"  : JARVIS schläft, bis im Terminal der Code eingegeben wird.
    #           Kein Mikro-Mithören im Leerlauf → keine Fehlalarme.
    # "voice" : klassisch per Wake-Phrase / Klatschen.
    activation_mode: str = "code"
    activation_code: str = "1234"   # über .env: JARVIS_ACTIVATION_CODE

    # --- Wake-Phrase (nur relevant bei activation_mode = "voice") ---
    wake_phrase: str = "jarvis"

    # --- Klatsch-Aktivierung ---
    # Doppel-Klatschen aktiviert JARVIS ebenfalls. Pro Audio-Chunk werden
    # RMS-Peaks gesucht und die Abstände zwischen zwei aufeinanderfolgenden
    # Peaks in Millisekunden geprüft.
    clap_enabled: bool = True
    clap_threshold: float = 0.35       # RMS-Schwelle 0..1 (0.35 = recht laut)
    clap_min_count: int = 2            # mindestens Doppel-Klatschen
    clap_min_gap_ms: int = 120         # Minimal-Abstand zwischen Klatschern
    clap_max_gap_ms: int = 700         # Maximal-Abstand

    # --- Konversations-Modus ---
    # Nach der Wake-Phrase nimmt JARVIS Folgefragen an, ohne dass die
    # Wake-Phrase wiederholt werden muss. Erst nach dieser Zahl stiller
    # Aufnahme-Runden (oder einer Verabschiedung) geht er wieder schlafen.
    silent_rounds_until_sleep: int = 2

    # --- Persönlichkeit ---
    assistant_name: str = "JARVIS"

    # --- Gedächtnis (Phase 2) ---
    db_path: Path = PROJECT_ROOT / "data" / "jarvis.db"
    memory_pairs: int = 20   # Anzahl Q/A-Paare als Kontext

    # --- Web-Server (Phase 4 + 6) ---
    # 0.0.0.0, damit das iPhone im gleichen WLAN zugreifen kann.
    web_host: str = "0.0.0.0"
    web_port: int = 8080

    # --- Electron-Kugel ---
    # Wenn True, wird die schwebende Kugel automatisch beim Start mitgestartet.
    auto_start_orb: bool = True

    # --- Computer Use (Claude steuert den Mac direkt, Beta-Feature) ---
    # Anthropic-Beta-String und Tool-Typ; ggf. anpassen, wenn Anthropic
    # eine neuere Version veröffentlicht.
    computer_use_model: str = "claude-sonnet-4-6"
    computer_use_beta: str = "computer-use-2025-01-24"
    computer_use_tool_type: str = "computer_20250124"
    computer_use_max_steps: int = 30
    computer_use_max_tokens: int = 2048

    # --- Langzeitgedächtnis: Auto-Extraktion von Fakten ---
    # Haiku ist deutlich billiger als Sonnet (~5×) und reicht völlig,
    # um Fakten aus einem Gesprächs-Turn zu extrahieren.
    profile_extractor_model: str = "claude-haiku-4-5-20251001"

    # --- Welcome-Briefing ---
    # Jede Aktivierung triggert ein Briefing – aber innerhalb dieser
    # Schutz-Zeit antwortet JARVIS nur kurz mit 'Ja?', damit er sich
    # nicht wiederholt, wenn du gerade aktiv mit ihm redest.
    welcome_cooldown_minutes: int = 5

    # --- Resilienz / Autonomie ---
    # Wie oft Cloud-Aufrufe bei Netzwerkfehlern wiederholt werden,
    # bevor JARVIS in den eingeschränkten Modus geht.
    api_retries: int = 3
    api_retry_base_delay: float = 2.0      # Sekunden, verdoppelt sich je Versuch

    # --- Selbst-Steuerung (Executive-Agent) ---
    # JARVIS arbeitet eigenständig an den 'goals' weiter. Intervall +
    # hartes Tagesbudget begrenzen Kosten und verhindern Spam.
    executive_enabled: bool = True
    executive_interval_hours: float = 3.0
    executive_daily_budget: int = 6        # max. autonome Aktionen pro Tag

    # --- Ops-Center: Wetter + Ambient-Daten ---
    # Standort fürs Wetter (Open-Meteo, kostenlos, kein Key).
    # Default: Wien. Eigene Koordinaten von z. B. latlong.net holen.
    weather_lat: float = 48.2085   # Wien 1010, Innere Stadt (Stephansplatz)
    weather_lon: float = 16.3721
    weather_city: str = "Wien"
    # Wie oft Wetter im Hintergrund aktualisiert wird (Sekunden).
    weather_refresh_seconds: int = 600
    # Wie oft Agenten-/Ziele-/Statistik-Kacheln gepusht werden (Sekunden).
    ambient_refresh_seconds: int = 30

    # --- Multi-Cloud-Fallback (Claude-Niveau) ---
    # Greift, wenn Anthropic ausfällt, aber Internet noch geht.
    # Keys via .env: OPENAI_API_KEY / GEMINI_API_KEY.
    cloud_fallback_enabled: bool = True
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"

    # --- Lokales Fallback-Gehirn (Ollama) ---
    # Letzte Reserve, wenn auch kein anderer Cloud-Anbieter geht
    # (= echtes Offline). Modell vorher ziehen: ollama pull llama3.2
    # Für MacBook Air mit 8GB: 'llama3.2' (3B). Mit 16GB: 'llama3.1'.
    local_brain_enabled: bool = True
    local_brain_url: str = "http://127.0.0.1:11434"
    local_brain_model: str = "llama3.2"
    # Watchdog: wenn der Voice-Loop länger als so viele Sekunden in
    # einer Iteration hängt, wird das geloggt (Hänger-Erkennung).
    watchdog_timeout_seconds: int = 180

    @classmethod
    def from_env(cls) -> "Config":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY fehlt. Bitte in der .env-Datei eintragen."
            )
        kwargs = dict(
            anthropic_api_key=api_key,
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY") or None,
            elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID") or None,
            mac_voice=os.getenv("JARVIS_MAC_VOICE") or None,
        )
        # Optionale .env-Overrides
        code = os.getenv("JARVIS_ACTIVATION_CODE", "").strip()
        if code:
            kwargs["activation_code"] = code
        mode = os.getenv("JARVIS_ACTIVATION_MODE", "").strip()
        if mode in ("code", "voice"):
            kwargs["activation_mode"] = mode
        # Multi-Cloud-Fallback-Keys
        kwargs["openai_api_key"] = os.getenv("OPENAI_API_KEY") or None
        kwargs["gemini_api_key"] = os.getenv("GEMINI_API_KEY") or None
        return cls(**kwargs)


CONFIG: Config | None = None


def get_config() -> Config:
    global CONFIG
    if CONFIG is None:
        CONFIG = Config.from_env()
    return CONFIG
