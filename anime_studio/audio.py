"""Sprachausgabe (Text-to-Speech) ueber ElevenLabs.

Erzeugt aus einer Dialogzeile eine Audiodatei mit einer natuerlich klingenden
Stimme. Pro Charakter wird stabil eine Stimme aus einem kleinen Pool gewaehlt,
damit Figuren wiedererkennbar klingen.

Ohne ELEVENLABS_API_KEY ist das Modul inaktiv (available() == False); die
Website nutzt dann die kostenlose Browser-Sprachausgabe, und der Video-Export
erzeugt ein stummes Video mit eingebrannten Untertiteln.
"""

from __future__ import annotations

import io
import os
import uuid
import wave
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

AUDIO_DIR = Path(__file__).resolve().parent / "data" / "audio"
MODEL_ID = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
SAMPLE_RATE = 24000  # passend zu output_format pcm_24000

# Kleiner Pool oeffentlicher ElevenLabs-Standardstimmen (gemischt m/w)
VOICE_POOL = [
    "TxGEqnHWrfWFTfGW9XjX",  # Josh
    "EXAVITQu4vr4xnSDxMaL",  # Bella
    "ErXwobaYiN019PkySvjV",  # Antoni
    "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "2EiwWnXFnvU5JabPnv8n",  # Clyde
    "AZnzlk1XvdvUeBnXmlld",  # Domi
]


def available() -> bool:
    return bool(os.getenv("ELEVENLABS_API_KEY"))


def voice_for(speaker: str) -> str:
    forced = os.getenv("ELEVENLABS_VOICE_ID")
    if forced:
        return forced
    h = sum(ord(c) for c in (speaker or "?"))
    return VOICE_POOL[h % len(VOICE_POOL)]


def _pcm_to_wav(pcm: bytes) -> bytes:
    """Rohes 16-bit-Mono-PCM in einen WAV-Container packen."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def synthesize(text: str, speaker: str) -> tuple[bytes, float] | None:
    """Erzeugt WAV-Bytes + Dauer (Sekunden) fuer eine Zeile. None bei Fehler."""
    if not available() or not text.strip():
        return None
    key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = voice_for(speaker)
    url = (
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        f"?output_format=pcm_{SAMPLE_RATE}"
    )
    try:
        resp = requests.post(
            url,
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": MODEL_ID,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=90,
        )
        resp.raise_for_status()
        pcm = resp.content
    except Exception as exc:  # pragma: no cover - haengt von Netz/Key ab
        print(f"[anime_studio] TTS-Fehler: {exc}")
        return None
    duration = len(pcm) / 2 / SAMPLE_RATE  # 16-bit mono
    return _pcm_to_wav(pcm), duration


def synthesize_to_file(text: str, speaker: str, folder: Path) -> tuple[Path, float] | None:
    """Wie synthesize(), speichert das WAV aber als Datei und gibt den Pfad zurueck."""
    out = synthesize(text, speaker)
    if not out:
        return None
    wav_bytes, duration = out
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex[:12]}.wav"
    path.write_bytes(wav_bytes)
    return path, duration
