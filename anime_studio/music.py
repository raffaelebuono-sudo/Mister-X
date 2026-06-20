"""KI-Hintergrundmusik je Stimmung ueber Replicate (MusicGen).

Erzeugt einen passenden Musiktrack fuer eine Folge, der im Video-Export leise
unter Stimmen/Dialog gemischt wird. Braucht REPLICATE_API_TOKEN. Ohne Token
ist das Modul inaktiv und das Video bleibt ohne Musik.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv

from . import clips  # nutzt denselben Replicate-Aufruf

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

MUSIC_DIR = Path(__file__).resolve().parent / "data" / "music"
MUSIC_MODEL = os.getenv("REPLICATE_MUSIC_MODEL", "meta/musicgen")

# Stimmung -> kurze, englische Musikbeschreibung fuer MusicGen
MOOD_MUSIC = {
    "ruhig": "calm peaceful anime soundtrack, soft piano and strings",
    "froehlich": "cheerful upbeat anime opening, bright playful melody",
    "spannend": "tense suspenseful anime score, driving percussion",
    "traurig": "sad emotional anime piano theme, melancholic strings",
    "episch": "epic orchestral anime battle theme, powerful drums and brass",
    "romantisch": "gentle romantic anime theme, warm piano and violin",
    "duester": "dark ominous anime ambient, low drones and tension",
    "geheimnisvoll": "mysterious anime soundtrack, ethereal pads and bells",
}


def available() -> bool:
    return clips.available()


def dominant_mood(episode: dict) -> str:
    moods = [s.get("mood", "ruhig") for s in episode.get("scenes", [])]
    if not moods:
        return "episch"
    return max(set(moods), key=moods.count)


def generate(episode: dict, duration: int = 30) -> Path | None:
    """Erzeugt einen Musiktrack passend zur Folge. Gibt den Dateipfad zurueck."""
    if not available():
        return None
    mood = dominant_mood(episode)
    prompt = MOOD_MUSIC.get(mood, MOOD_MUSIC["episch"])
    payload = {
        "prompt": prompt,
        "duration": max(8, min(int(duration), 60)),
        "output_format": "mp3",
    }
    try:
        output = clips._run(MUSIC_MODEL, payload)
    except Exception as exc:  # pragma: no cover - haengt von Netz/Key ab
        print(f"[anime_studio] Musik-Fehler: {exc}")
        return None
    url = output[0] if isinstance(output, list) else output
    if not isinstance(url, str):
        return None
    try:
        data = requests.get(url, timeout=120).content
    except Exception as exc:  # pragma: no cover
        print(f"[anime_studio] Musik-Download-Fehler: {exc}")
        return None
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    path = MUSIC_DIR / f"{uuid.uuid4().hex[:10]}.mp3"
    path.write_bytes(data)
    return path
