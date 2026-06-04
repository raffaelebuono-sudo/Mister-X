"""Anime-Studio – Webserver.

Stellt die Website bereit und bietet eine kleine JSON-API, um Serien
anzulegen und Folge fuer Folge neue Anime-Episoden zu erzeugen.

Start:
    python -m anime_studio.server
    # oder
    uvicorn anime_studio.server:app --reload --port 8800
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import generator
from . import images
from . import audio
from . import video
from . import clips as clips_mod
from . import music as music_mod
from . import lora as lora_mod

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
IMAGES_DIR = DATA_DIR / "images"
MEDIA_DIR = DATA_DIR / "media"
CLIPS_DIR = DATA_DIR / "clips"
DATA_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)
MEDIA_DIR.mkdir(exist_ok=True)
CLIPS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Anime-Studio")


# --------------------------------------------------------------------------
# Mini-Datenspeicher: jede Serie als JSON-Datei unter data/
# --------------------------------------------------------------------------

def _series_path(series_id: str) -> Path:
    # nur sichere Zeichen zulassen
    safe = "".join(c for c in series_id if c.isalnum() or c in "-_")
    return DATA_DIR / f"{safe}.json"


def _load(series_id: str) -> dict[str, Any]:
    path = _series_path(series_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Serie nicht gefunden.")
    return json.loads(path.read_text(encoding="utf-8"))


def _save(series: dict[str, Any]) -> None:
    path = _series_path(series["id"])
    path.write_text(
        json.dumps(series, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --------------------------------------------------------------------------
# Request-Modelle
# --------------------------------------------------------------------------

class CharacterIn(BaseModel):
    name: str
    role: str = "Charakter"


class SeriesIn(BaseModel):
    title: str
    genre: str = "Abenteuer"
    characters: list[CharacterIn] = []
    art_style: str = ""


class EpisodeIn(BaseModel):
    keywords: str


class EpisodeEdit(BaseModel):
    episode: dict[str, Any]


class SceneRegen(BaseModel):
    scene_index: int
    hint: str = ""


class ExportOptions(BaseModel):
    use_clips: bool = False
    use_music: bool = False


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------

@app.get("/api/status")
def status() -> dict[str, Any]:
    """Zeigt, ob ein echter API-Key aktiv ist oder der Demo-Modus laeuft."""
    return {
        "demo_mode": not generator._has_api_key(),
        "model": generator.MODEL,
        "images_enabled": images.available(),
        "image_provider": images.provider(),
        "voices_enabled": audio.available(),
        "video_enabled": video.available(),
        "clips_enabled": clips_mod.available(),
        "music_enabled": music_mod.available(),
        "lora_enabled": lora_mod.available(),
    }


@app.get("/api/series")
def list_series() -> list[dict[str, Any]]:
    out = []
    for path in sorted(DATA_DIR.glob("*.json")):
        try:
            s = json.loads(path.read_text(encoding="utf-8"))
            out.append(
                {
                    "id": s["id"],
                    "title": s["title"],
                    "genre": s.get("genre", ""),
                    "episode_count": len(s.get("episodes", [])),
                }
            )
        except Exception:
            continue
    return out


@app.post("/api/series")
def create_series(data: SeriesIn) -> dict[str, Any]:
    series = {
        "id": uuid.uuid4().hex[:10],
        "title": data.title.strip() or "Meine Anime-Serie",
        "genre": data.genre.strip() or "Abenteuer",
        "characters": [c.model_dump() for c in data.characters],
        "art_style": data.art_style.strip() or images.DEFAULT_STYLE,
        "episodes": [],
    }
    _apply_appearances(series)
    _save(series)
    return series


def _apply_appearances(series: dict[str, Any]) -> None:
    """Erzeugt fehlende Aussehensbeschreibungen und traegt sie ein."""
    looks = generator.generate_appearances(series)
    for c in series.get("characters", []):
        if not c.get("appearance") and looks.get(c["name"]):
            c["appearance"] = looks[c["name"]]


@app.get("/api/series/{series_id}")
def get_series(series_id: str) -> dict[str, Any]:
    return _load(series_id)


@app.delete("/api/series/{series_id}")
def delete_series(series_id: str) -> dict[str, str]:
    path = _series_path(series_id)
    if path.exists():
        path.unlink()
    return {"status": "geloescht"}


@app.post("/api/series/{series_id}/episode")
def create_episode(series_id: str, data: EpisodeIn) -> dict[str, Any]:
    series = _load(series_id)
    keywords = data.keywords.strip()
    if not keywords:
        raise HTTPException(status_code=400, detail="Bitte Stichworte angeben.")

    episode = generator.generate_episode(series, keywords)
    episode["keywords"] = keywords
    series.setdefault("episodes", []).append(episode)

    # neue Charaktere ins Serien-Ensemble uebernehmen
    known = {c["name"].lower() for c in series.get("characters", [])}
    for nc in episode.get("new_characters", []):
        if nc.get("name") and nc["name"].lower() not in known:
            series["characters"].append(
                {"name": nc["name"], "role": nc.get("role", "Charakter")}
            )
            known.add(nc["name"].lower())

    _apply_appearances(series)  # neue Figuren bekommen ein festes Aussehen
    _save(series)
    return {"episode": episode, "series": series}


def _find_episode(series: dict[str, Any], number: int) -> int:
    for i, ep in enumerate(series.get("episodes", [])):
        if ep.get("number") == number:
            return i
    raise HTTPException(status_code=404, detail="Folge nicht gefunden.")


def _find_character(series: dict[str, Any], name: str) -> dict[str, Any]:
    for c in series.get("characters", []):
        if c.get("name", "").lower() == name.lower():
            return c
    raise HTTPException(status_code=404, detail="Figur nicht gefunden.")


@app.post("/api/series/{series_id}/character/{name}/train-lora")
def train_lora(series_id: str, name: str) -> dict[str, Any]:
    """Startet das LoRA-Training fuer eine Figur (langsam, kostenpflichtig)."""
    if not lora_mod.available():
        raise HTTPException(
            status_code=400,
            detail="LoRA braucht REPLICATE_API_TOKEN und REPLICATE_USERNAME.",
        )
    series = _load(series_id)
    character = _find_character(series, name)
    try:
        st = lora_mod.start_training(series, character)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Training-Fehler: {exc}")
    _save(series)
    return {"lora": st}


@app.get("/api/series/{series_id}/character/{name}/lora")
def lora_status(series_id: str, name: str) -> dict[str, Any]:
    """Fragt den aktuellen LoRA-Trainingsstatus einer Figur ab."""
    series = _load(series_id)
    character = _find_character(series, name)
    st = lora_mod.refresh_status(character)
    _save(series)
    return {"lora": st}


@app.put("/api/series/{series_id}/episode/{number}")
def update_episode(
    series_id: str, number: int, data: EpisodeEdit
) -> dict[str, Any]:
    """Speichert manuell bearbeitete Szenen/Dialoge einer Folge."""
    series = _load(series_id)
    idx = _find_episode(series, number)
    episode = generator._normalise(data.episode, number)
    episode["keywords"] = series["episodes"][idx].get("keywords", "")
    series["episodes"][idx] = episode
    _save(series)
    return {"episode": episode, "series": series}


@app.post("/api/series/{series_id}/episode/{number}/regen-scene")
def regen_scene(
    series_id: str, number: int, data: SceneRegen
) -> dict[str, Any]:
    """Generiert eine einzelne Szene einer Folge neu (mit optionalem Hinweis)."""
    series = _load(series_id)
    idx = _find_episode(series, number)
    episode = series["episodes"][idx]
    scenes = episode.get("scenes", [])
    if not (0 <= data.scene_index < len(scenes)):
        raise HTTPException(status_code=400, detail="Ungueltige Szene.")
    new_scene = generator.regenerate_scene(
        series, episode, data.scene_index, data.hint
    )
    scenes[data.scene_index] = new_scene
    episode["scenes"] = scenes
    series["episodes"][idx] = episode
    _save(series)
    return {"episode": episode, "series": series}


@app.post("/api/series/{series_id}/episode/{number}/scene-image")
def scene_image(
    series_id: str, number: int, data: SceneRegen
) -> dict[str, Any]:
    """Erzeugt ein KI-Bild fuer eine einzelne Szene und speichert den Pfad."""
    if not images.available():
        raise HTTPException(
            status_code=400,
            detail="Kein Bild-Key gesetzt (OPENAI_API_KEY oder GEMINI_API_KEY).",
        )
    series = _load(series_id)
    idx = _find_episode(series, number)
    episode = series["episodes"][idx]
    scenes = episode.get("scenes", [])
    if not (0 <= data.scene_index < len(scenes)):
        raise HTTPException(status_code=400, detail="Ungueltige Szene.")
    url = images.generate_scene_image(series, scenes[data.scene_index])
    if not url:
        raise HTTPException(status_code=502, detail="Bild konnte nicht erzeugt werden.")
    scenes[data.scene_index]["image"] = url
    episode["scenes"] = scenes
    series["episodes"][idx] = episode
    _save(series)
    return {"image": url, "scene_index": data.scene_index}


@app.post("/api/series/{series_id}/episode/{number}/line-audio")
def line_audio(series_id: str, number: int, data: SceneRegen) -> dict[str, Any]:
    """Erzeugt (oder liefert) die Sprachaufnahme einer Dialogzeile.

    Nutzt 'scene_index' und 'hint' (=Zeilenindex als Text) aus SceneRegen.
    """
    if not audio.available():
        raise HTTPException(status_code=400, detail="Kein ELEVENLABS_API_KEY gesetzt.")
    series = _load(series_id)
    idx = _find_episode(series, number)
    scenes = series["episodes"][idx].get("scenes", [])
    if not (0 <= data.scene_index < len(scenes)):
        raise HTTPException(status_code=400, detail="Ungueltige Szene.")
    try:
        line_index = int(data.hint or "0")
    except ValueError:
        line_index = 0
    dialogue = scenes[data.scene_index].get("dialogue", [])
    if not (0 <= line_index < len(dialogue)):
        raise HTTPException(status_code=400, detail="Ungueltige Zeile.")
    line = dialogue[line_index]
    if line.get("audio"):
        return {"audio": line["audio"]}
    folder = MEDIA_DIR / "lines" / "".join(
        c for c in series_id if c.isalnum() or c in "-_"
    )
    res = audio.synthesize_to_file(line.get("text", ""), line.get("speaker", ""), folder)
    if not res:
        raise HTTPException(status_code=502, detail="Sprachausgabe fehlgeschlagen.")
    path, _ = res
    url = "/media/" + str(path.relative_to(MEDIA_DIR)).replace(os.sep, "/")
    line["audio"] = url
    series["episodes"][idx]["scenes"][data.scene_index]["dialogue"][line_index] = line
    _save(series)
    return {"audio": url}


@app.post("/api/series/{series_id}/episode/{number}/export")
def export_video(
    series_id: str, number: int, opts: ExportOptions | None = None
) -> dict[str, Any]:
    """Rendert die Folge als MP4 und gibt den Web-Pfad zurueck.

    opts.use_clips  -> bewegte KI-Video-Clips pro Szene (Replicate, langsam/teuer)
    opts.use_music  -> KI-Hintergrundmusik je Stimmung (Replicate)
    """
    if not video.available():
        raise HTTPException(status_code=400, detail="ffmpeg nicht verfuegbar.")
    opts = opts or ExportOptions()
    series = _load(series_id)
    idx = _find_episode(series, number)
    url = video.build_episode_video(
        series, series["episodes"][idx],
        use_clips=opts.use_clips, use_music=opts.use_music,
    )
    if not url:
        raise HTTPException(status_code=502, detail="Video konnte nicht erstellt werden.")
    series["episodes"][idx]["video"] = url
    _save(series)
    return {"video": url}


# --------------------------------------------------------------------------
# Statische Website + erzeugte Bilder/Videos
# --------------------------------------------------------------------------

app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")
app.mount("/clips", StaticFiles(directory=str(CLIPS_DIR)), name="clips")

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("ANIME_PORT", "8800"))
    print(f"Anime-Studio laeuft auf http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
