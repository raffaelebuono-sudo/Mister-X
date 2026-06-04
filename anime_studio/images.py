"""Bild-Generator fuer Anime-Szenen.

Erzeugt zu einer Szene ein echtes Anime-Bild ueber eine Bild-KI. Unterstuetzt
zwei Anbieter, je nachdem welcher API-Key gesetzt ist:

* OpenAI   (gpt-image-1)   -> OPENAI_API_KEY
* Google   (Gemini/Imagen) -> GEMINI_API_KEY

Ist kein Key gesetzt (oder ein Fehler tritt auf), wird None zurueckgegeben –
die Website faellt dann auf den Stimmungs-Hintergrund zurueck.
"""

from __future__ import annotations

import base64
import os
import uuid
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

IMAGES_DIR = Path(__file__).resolve().parent / "data" / "images"

# Standard-Kunststil: an One Piece / Shonen-Abenteuer angelehnt, OHNE einen
# lebenden Kuenstler oder eine geschuetzte Marke namentlich zu nennen
# (das wuerde von den Bild-KIs blockiert).
DEFAULT_STYLE = (
    "classic shonen pirate-adventure anime style, bold confident ink "
    "outlines, exaggerated expressive characters, dynamic poses, vibrant "
    "saturated colors, cel shading, adventurous late-90s/2000s anime look, "
    "high detail, clean line art, dramatic lighting"
)

OPENAI_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
GEMINI_MODEL = os.getenv(
    "GEMINI_IMAGE_MODEL", "gemini-2.0-flash-preview-image-generation"
)


def provider() -> str | None:
    """Welcher Anbieter ist nutzbar? 'openai', 'gemini' oder None."""
    pref = os.getenv("IMAGE_PROVIDER", "auto").lower()
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_gemini = bool(os.getenv("GEMINI_API_KEY"))
    if pref == "openai":
        return "openai" if has_openai else None
    if pref == "gemini":
        return "gemini" if has_gemini else None
    # auto
    if has_openai:
        return "openai"
    if has_gemini:
        return "gemini"
    return None


def available() -> bool:
    return provider() is not None


def build_prompt(
    series: dict[str, Any], scene: dict[str, Any], style: str | None = None
) -> str:
    """Baut aus einer Szene einen Bild-Prompt."""
    style = style or series.get("art_style") or DEFAULT_STYLE
    location = scene.get("location", "")
    mood = scene.get("mood", "")

    # Charaktere der Szene (aus den Sprechern) mit Rollen-Beschreibung
    speakers: list[str] = []
    for line in scene.get("dialogue", []):
        sp = line.get("speaker")
        if sp and sp not in speakers and sp != "???":
            speakers.append(sp)
    chardb = {c["name"]: c for c in series.get("characters", [])}
    # Aussehen einbeziehen -> konsistente Charaktere ueber alle Szenen
    desc_parts = []
    for n in speakers[:3]:
        c = chardb.get(n, {})
        look = c.get("appearance")
        if look:
            desc_parts.append(f"{n} ({look})")
        elif c.get("role"):
            desc_parts.append(f"{n} ({c['role']})")
        else:
            desc_parts.append(n)
    chars_desc = "; ".join(desc_parts)

    parts = [
        f"Anime key visual. {style}.",
        f"Scene: {location}." if location else "",
        f"Mood: {mood}." if mood else "",
        f"Characters present: {chars_desc}." if chars_desc else "",
        (scene.get("narration") or "")[:200],
        "Cinematic composition, landscape, no text, no watermark, no speech bubbles.",
    ]
    return " ".join(p for p in parts if p).strip()


def _dominant_character(series: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any] | None:
    """Figur mit den meisten Sprechzeilen in der Szene (fuer LoRA-Routing)."""
    counts: dict[str, int] = {}
    for line in scene.get("dialogue", []):
        sp = line.get("speaker")
        if sp and sp != "???":
            counts[sp] = counts.get(sp, 0) + 1
    if not counts:
        return None
    top = max(counts, key=counts.get)
    for c in series.get("characters", []):
        if c.get("name") == top:
            return c
    return None


def generate_scene_image(
    series: dict[str, Any], scene: dict[str, Any]
) -> str | None:
    """Erzeugt ein Bild fuer die Szene und gibt den Web-Pfad zurueck.

    Rueckgabe z.B. '/images/<serie>/<datei>.png' oder None bei Fehler/kein Key.
    """
    # Konsistenz-Weg: Hat die Hauptfigur der Szene ein trainiertes LoRA,
    # erzeugen wir das Bild ueber ihr Spezialmodell -> gleiche Figur ueberall.
    from . import lora
    main = _dominant_character(series, scene)
    if main and lora.ready(main):
        prompt = build_prompt(series, scene, style=series.get("art_style"))
        data = lora.generate_image(main, prompt)
        if data:
            return _save(series["id"], data)
        # sonst: normaler Weg unten

    prov = provider()
    if not prov:
        return None
    prompt = build_prompt(series, scene)
    try:
        if prov == "openai":
            data = _openai_image(prompt)
        else:
            data = _gemini_image(prompt)
    except Exception as exc:  # pragma: no cover - haengt vom Netz/Key ab
        print(f"[anime_studio] Bild-Fehler ({prov}): {exc}")
        return None
    if not data:
        return None
    return _save(series["id"], data)


def _save(series_id: str, png_bytes: bytes) -> str:
    safe = "".join(c for c in series_id if c.isalnum() or c in "-_")
    folder = IMAGES_DIR / safe
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:12]}.png"
    (folder / name).write_bytes(png_bytes)
    return f"/images/{safe}/{name}"


# --------------------------------------------------------------------------
# OpenAI (gpt-image-1)
# --------------------------------------------------------------------------

def _openai_image(prompt: str) -> bytes | None:
    key = os.getenv("OPENAI_API_KEY")
    resp = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": OPENAI_MODEL,
            "prompt": prompt,
            "size": "1536x1024",
            "n": 1,
        },
        timeout=120,
    )
    resp.raise_for_status()
    out = resp.json()
    b64 = out["data"][0].get("b64_json")
    if b64:
        return base64.b64decode(b64)
    url = out["data"][0].get("url")
    if url:
        return requests.get(url, timeout=60).content
    return None


# --------------------------------------------------------------------------
# Google Gemini / Imagen
# --------------------------------------------------------------------------

def _gemini_image(prompt: str) -> bytes | None:
    key = os.getenv("GEMINI_API_KEY")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={key}"
    )
    resp = requests.post(
        url,
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
        },
        timeout=120,
    )
    resp.raise_for_status()
    out = resp.json()
    for cand in out.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    return None
