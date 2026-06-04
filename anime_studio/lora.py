"""LoRA-Feintuning pro Figur ueber Replicate (FLUX).

Das ist der "Studio-Weg" zu echter Charakter-Konsistenz: Fuer eine Figur wird
ein kleines Spezialmodell (LoRA) trainiert. Danach sieht die Figur in jeder
generierten Szene gleich aus – derselbe Kopf, dieselbe Frisur, dieselbe Kleidung.

Ablauf:
  1. Trainingsbilder der Figur erzeugen (mehrere Blickwinkel, via FLUX schnell)
  2. Bilder zippen und zu Replicate hochladen (Files-API)
  3. Ziel-Modell auf dem Replicate-Account anlegen (falls noch nicht da)
  4. LoRA-Training starten (laeuft ~10-20 Min, kostet GPU-Zeit)
  5. Status pollen; wenn fertig, das trainierte Modell fuer Bilder nutzen

Braucht REPLICATE_API_TOKEN und REPLICATE_USERNAME (der trainierte LoRA wird
auf deinem Replicate-Account gespeichert). Ohne beides ist das Modul inaktiv.

Hinweis: Training ist langsam und kostenpflichtig. Generierung mit dem
trainierten Modell ist danach normal schnell.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from . import clips  # _run / _headers / API wiederverwenden

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

API = clips.API
# FLUX-Trainer auf Replicate (per .env aenderbar)
TRAINER = os.getenv("REPLICATE_LORA_TRAINER", "ostris/flux-dev-lora-trainer")
# Schnelles Text-zu-Bild-Modell fuer die Trainingsbilder
TRAIN_IMG_MODEL = os.getenv("REPLICATE_FLUX_MODEL", "black-forest-labs/flux-schnell")
TRAIN_STEPS = int(os.getenv("REPLICATE_LORA_STEPS", "1000"))


def username() -> str | None:
    return os.getenv("REPLICATE_USERNAME")


def available() -> bool:
    return clips.available() and bool(username())


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------

def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "figur"


def trigger_word(character: dict[str, Any]) -> str:
    return "CHR" + re.sub(r"[^A-Z0-9]", "", character.get("name", "X").upper())[:8]


def _dest_model(series: dict[str, Any], character: dict[str, Any]) -> str:
    name = f"as-{_slug(series.get('id', 'serie'))}-{_slug(character.get('name', 'figur'))}"
    return f"{username()}/{name[:60]}"


def _ensure_model(dest: str) -> None:
    """Legt das Ziel-Modell auf dem Account an, falls es noch nicht existiert."""
    owner, name = dest.split("/", 1)
    r = requests.get(f"{API}/models/{owner}/{name}", headers=clips._headers(), timeout=30)
    if r.status_code == 200:
        return
    requests.post(
        f"{API}/models",
        headers=clips._headers(),
        json={
            "owner": owner,
            "name": name,
            "visibility": "private",
            "hardware": "gpu-t4",
            "description": "Anime-Studio Charakter-LoRA",
        },
        timeout=30,
    )


def _latest_version(model: str) -> str:
    owner, name = model.split("/", 1)
    r = requests.get(f"{API}/models/{owner}/{name}", headers=clips._headers(), timeout=30)
    r.raise_for_status()
    ver = (r.json().get("latest_version") or {}).get("id")
    if not ver:
        raise RuntimeError(f"Keine Version fuer {model} gefunden.")
    return ver


def _upload_zip(data: bytes) -> str:
    """Laedt ein ZIP ueber die Replicate-Files-API hoch, gibt die URL zurueck."""
    token = os.getenv("REPLICATE_API_TOKEN")
    r = requests.post(
        f"{API}/files",
        headers={"Authorization": f"Token {token}"},
        files={"content": ("training.zip", data, "application/zip")},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["urls"]["get"]


# --------------------------------------------------------------------------
# Trainingsbilder
# --------------------------------------------------------------------------

_VIEWS = [
    "front portrait, neutral expression",
    "three-quarter view portrait",
    "side profile portrait",
    "full body standing pose",
    "smiling close-up",
    "dynamic action pose",
]


def _make_training_images(series: dict[str, Any], character: dict[str, Any]) -> bytes:
    """Erzeugt mehrere Ansichten der Figur und packt sie in ein ZIP."""
    from . import images as imgmod

    style = series.get("art_style") or imgmod.DEFAULT_STYLE
    look = character.get("appearance") or character.get("role") or character.get("name")
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, view in enumerate(_VIEWS):
            prompt = (
                f"Single anime character reference. {style}. "
                f"{character.get('name')}: {look}. {view}. "
                f"plain neutral background, full character visible, no text."
            )
            try:
                out = clips._run(TRAIN_IMG_MODEL, {
                    "prompt": prompt,
                    "num_outputs": 1,
                    "aspect_ratio": "1:1",
                    "output_format": "png",
                }, timeout=120)
            except Exception as exc:  # pragma: no cover - Netz/Key
                print(f"[anime_studio] LoRA-Trainingsbild-Fehler: {exc}")
                continue
            url = out[0] if isinstance(out, list) else out
            if not isinstance(url, str):
                continue
            try:
                png = requests.get(url, timeout=60).content
            except Exception:  # pragma: no cover
                continue
            zf.writestr(f"{i:02d}.png", png)
            count += 1
    if count < 2:
        raise RuntimeError("Zu wenige Trainingsbilder erzeugt.")
    return buf.getvalue()


# --------------------------------------------------------------------------
# Training starten / Status / Generierung
# --------------------------------------------------------------------------

def start_training(series: dict[str, Any], character: dict[str, Any]) -> dict[str, Any]:
    """Startet das LoRA-Training. Gibt den LoRA-Status fuer die Figur zurueck."""
    if not available():
        raise RuntimeError("Replicate-Token oder -Benutzername fehlt.")

    trigger = trigger_word(character)
    dest = _dest_model(series, character)
    _ensure_model(dest)

    zip_bytes = _make_training_images(series, character)
    zip_url = _upload_zip(zip_bytes)

    trainer_version = _latest_version(TRAINER)
    owner, name = TRAINER.split("/", 1)
    body = {
        "destination": dest,
        "input": {
            "input_images": zip_url,
            "trigger_word": trigger,
            "steps": TRAIN_STEPS,
            "lora_rank": 16,
            "caption_dropout_rate": 0.05,
        },
    }
    r = requests.post(
        f"{API}/models/{owner}/{name}/versions/{trainer_version}/trainings",
        headers=clips._headers(), json=body, timeout=60,
    )
    r.raise_for_status()
    tr = r.json()
    status = {
        "status": "training",
        "training_id": tr.get("id"),
        "get_url": tr.get("urls", {}).get("get"),
        "trigger": trigger,
        "model": dest,
    }
    character["lora"] = status
    return status


def refresh_status(character: dict[str, Any]) -> dict[str, Any]:
    """Fragt den Trainingsstatus bei Replicate ab und aktualisiert die Figur."""
    lora = character.get("lora")
    if not lora or lora.get("status") != "training":
        return lora or {"status": "none"}
    get_url = lora.get("get_url")
    if not get_url:
        return lora
    try:
        tr = requests.get(get_url, headers=clips._headers(), timeout=30).json()
    except Exception as exc:  # pragma: no cover
        print(f"[anime_studio] LoRA-Status-Fehler: {exc}")
        return lora
    st = tr.get("status")
    if st == "succeeded":
        out = tr.get("output") or {}
        version = out.get("version") if isinstance(out, dict) else None
        lora["status"] = "ready"
        lora["version"] = version or lora.get("model")
    elif st in ("failed", "canceled"):
        lora["status"] = "failed"
        lora["error"] = str(tr.get("error"))[:300]
    return lora


def ready(character: dict[str, Any]) -> bool:
    lora = character.get("lora") or {}
    return lora.get("status") == "ready"


def generate_image(character: dict[str, Any], prompt: str) -> bytes | None:
    """Erzeugt ein Bild mit dem trainierten Figur-LoRA. PNG-Bytes oder None."""
    lora = character.get("lora") or {}
    if lora.get("status") != "ready":
        return None
    version = lora.get("version") or lora.get("model")
    trigger = lora.get("trigger", "")
    full_prompt = f"{trigger} {prompt}".strip()
    payload = {
        "prompt": full_prompt,
        "num_outputs": 1,
        "aspect_ratio": "16:9",
        "output_format": "png",
    }
    try:
        if ":" in version:  # owner/name:hash -> Version-Prediction
            r = requests.post(
                f"{API}/predictions",
                headers={**clips._headers(), "Prefer": "wait"},
                json={"version": version.split(":", 1)[1], "input": payload},
                timeout=90,
            )
            r.raise_for_status()
            out = _poll(r.json())
        else:  # owner/name -> neueste Version des Ziel-Modells
            out = clips._run(version, payload, timeout=120)
    except Exception as exc:  # pragma: no cover
        print(f"[anime_studio] LoRA-Bild-Fehler: {exc}")
        return None
    url = out[0] if isinstance(out, list) else out
    if not isinstance(url, str):
        return None
    try:
        return requests.get(url, timeout=60).content
    except Exception:  # pragma: no cover
        return None


def _poll(pred: dict[str, Any], timeout: int = 180) -> Any:
    import time
    deadline = time.time() + timeout
    while pred.get("status") in ("starting", "processing"):
        if time.time() > deadline:
            raise TimeoutError("Replicate-Zeitlimit erreicht.")
        time.sleep(2.0)
        get_url = pred.get("urls", {}).get("get")
        if not get_url:
            break
        pred = requests.get(get_url, headers=clips._headers(), timeout=30).json()
    if pred.get("status") != "succeeded":
        raise RuntimeError(f"Status: {pred.get('status')} {pred.get('error')}")
    return pred.get("output")
