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

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
DATA_DIR.mkdir(exist_ok=True)

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


class EpisodeIn(BaseModel):
    keywords: str


class EpisodeEdit(BaseModel):
    episode: dict[str, Any]


class SceneRegen(BaseModel):
    scene_index: int
    hint: str = ""


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------

@app.get("/api/status")
def status() -> dict[str, Any]:
    """Zeigt, ob ein echter API-Key aktiv ist oder der Demo-Modus laeuft."""
    return {
        "demo_mode": not generator._has_api_key(),
        "model": generator.MODEL,
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
        "episodes": [],
    }
    _save(series)
    return series


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

    _save(series)
    return {"episode": episode, "series": series}


def _find_episode(series: dict[str, Any], number: int) -> int:
    for i, ep in enumerate(series.get("episodes", [])):
        if ep.get("number") == number:
            return i
    raise HTTPException(status_code=404, detail="Folge nicht gefunden.")


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


# --------------------------------------------------------------------------
# Statische Website
# --------------------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("ANIME_PORT", "8800"))
    print(f"Anime-Studio laeuft auf http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
