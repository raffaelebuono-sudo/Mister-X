"""KI-Video-Clips fuer Szenen (Image-to-Video) ueber Replicate.

Verwandelt das Standbild einer Szene in einen kurzen, BEWEGTEN Anime-Clip
(z. B. ueber Kling / Stable Video Diffusion auf Replicate). Damit wird aus der
"Standbild + Ken-Burns"-Folge ein echtes, bewegtes KI-Anime.

Braucht REPLICATE_API_TOKEN. Ohne Token ist das Modul inaktiv – der
Video-Export nutzt dann weiterhin den Ken-Burns-Effekt auf den Standbildern.

Hinweis: Die Eingabe-Schemata der Modelle aendern sich gelegentlich. Modell
und Parameter sind ueber Umgebungsvariablen einstellbar.
"""

from __future__ import annotations

import base64
import os
import time
import uuid
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

CLIPS_DIR = Path(__file__).resolve().parent / "data" / "clips"

# Standardmodell: ein Image-to-Video-Modell auf Replicate.
# Per .env aenderbar (z. B. "stability-ai/stable-video-diffusion").
VIDEO_MODEL = os.getenv("REPLICATE_VIDEO_MODEL", "kwaivgi/kling-v1.6-standard")
API = "https://api.replicate.com/v1"


def available() -> bool:
    return bool(os.getenv("REPLICATE_API_TOKEN"))


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}",
        "Content-Type": "application/json",
    }


def _data_uri(image_path: Path) -> str:
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    return f"data:image/png;base64,{b64}"


def _run(model: str, payload: dict[str, Any], timeout: int = 240) -> Any:
    """Startet eine Replicate-Prediction und wartet auf das Ergebnis."""
    owner, name = model.split("/", 1)
    url = f"{API}/models/{owner}/{name}/predictions"
    headers = {**_headers(), "Prefer": "wait"}
    resp = requests.post(url, headers=headers, json={"input": payload}, timeout=90)
    resp.raise_for_status()
    pred = resp.json()

    # Falls noch nicht fertig: pollen
    deadline = time.time() + timeout
    while pred.get("status") in ("starting", "processing"):
        if time.time() > deadline:
            raise TimeoutError("Replicate-Zeitlimit erreicht.")
        time.sleep(2.5)
        get_url = pred.get("urls", {}).get("get")
        if not get_url:
            break
        pred = requests.get(get_url, headers=_headers(), timeout=30).json()

    if pred.get("status") != "succeeded":
        raise RuntimeError(f"Replicate-Status: {pred.get('status')} {pred.get('error')}")
    return pred.get("output")


def scene_clip(
    series: dict[str, Any], scene: dict[str, Any], image_path: Path | None
) -> str | None:
    """Erzeugt einen bewegten Clip fuer die Szene. Gibt einen Web-Pfad zurueck."""
    if not available():
        return None
    style = series.get("art_style", "")
    motion = (
        f"{style}. Subtle natural motion, gentle camera movement, "
        f"anime scene: {scene.get('location', '')}, mood {scene.get('mood', '')}."
    )
    payload: dict[str, Any] = {"prompt": motion}
    if image_path and image_path.exists():
        # gaengige Feldnamen je nach Modell – wir setzen mehrere
        uri = _data_uri(image_path)
        payload["start_image"] = uri
        payload["image"] = uri
    try:
        output = _run(VIDEO_MODEL, payload)
    except Exception as exc:  # pragma: no cover - haengt von Netz/Key ab
        print(f"[anime_studio] KI-Video-Fehler: {exc}")
        return None

    video_url = output[0] if isinstance(output, list) else output
    if not isinstance(video_url, str):
        return None
    try:
        data = requests.get(video_url, timeout=120).content
    except Exception as exc:  # pragma: no cover
        print(f"[anime_studio] Clip-Download-Fehler: {exc}")
        return None
    return _save(series["id"], data)


def _save(series_id: str, data: bytes) -> str:
    safe = "".join(c for c in series_id if c.isalnum() or c in "-_")
    folder = CLIPS_DIR / safe
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:12]}.mp4"
    (folder / name).write_bytes(data)
    return f"/clips/{safe}/{name}"
