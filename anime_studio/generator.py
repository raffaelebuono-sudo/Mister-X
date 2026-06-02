"""KI-Anime-Generator.

Wandelt Stichworte zur Handlung in eine strukturierte Anime-Folge um
(Szenen, Hintergründe, Stimmung, Charaktere, Dialoge). Nutzt die
Claude-API (Anthropic). Ist kein API-Key gesetzt, springt ein
Demo-Generator ein, damit die Website trotzdem funktioniert.
"""

from __future__ import annotations

import json
import os
import random
import re
from typing import Any

from dotenv import load_dotenv

# .env aus dem Projekt-Wurzelverzeichnis laden (eine Ebene über diesem Ordner)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

try:  # Anthropic ist optional – ohne Key läuft der Demo-Modus
    from anthropic import Anthropic
except Exception:  # pragma: no cover
    Anthropic = None  # type: ignore

MODEL = os.getenv("ANIME_MODEL", "claude-sonnet-4-6")

# Erlaubte Stimmungen (steuern Hintergrundfarben im Player)
MOODS = [
    "ruhig", "froehlich", "spannend", "traurig",
    "episch", "romantisch", "duester", "geheimnisvoll",
]

SYSTEM_PROMPT = """\
Du bist ein erfahrener Anime-Regisseur und Drehbuchautor (im Stil bekannter \
japanischer Serien). Aus den Stichworten des Nutzers erschaffst du eine \
mitreissende Anime-Folge auf DEUTSCH.

Beachte den bisherigen Serienverlauf (falls vorhanden) und die Charaktere, \
damit die Handlung fortlaufend und konsistent bleibt – wie bei einer echten \
Anime-Serie Folge fuer Folge.

Du antwortest AUSSCHLIESSLICH mit gueltigem JSON in genau diesem Schema \
(keine Erklaerung, kein Markdown, keine Code-Fences):

{
  "episode_title": "Titel der Folge",
  "synopsis": "1-2 Saetze Zusammenfassung der Folge",
  "scenes": [
    {
      "location": "Schauplatz, z.B. 'Dach der Oberschule bei Sonnenuntergang'",
      "mood": "eine von: ruhig, froehlich, spannend, traurig, episch, romantisch, duester, geheimnisvoll",
      "narration": "kurzer Erzaehltext, der die Szene einleitet",
      "dialogue": [
        {"speaker": "Charaktername", "emotion": "z.B. wuetend/froehlich/nervoes", "text": "Gesprochener Satz"}
      ]
    }
  ],
  "new_characters": [
    {"name": "Name", "role": "kurze Beschreibung der Rolle"}
  ],
  "cliffhanger": "Spannender Ausblick auf die naechste Folge"
}

Regeln:
- 4 bis 7 Szenen pro Folge.
- Jede Szene hat mehrere Dialogzeilen, lebendig und charakterstark.
- Nutze vorhandene Charaktere; neue nur wenn die Handlung sie braucht.
- 'mood' MUSS exakt einer der erlaubten Werte sein.
- Gib NUR das JSON-Objekt zurueck.
"""


def _has_api_key() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY")) and Anthropic is not None


def _extract_json(text: str) -> dict[str, Any]:
    """Robust das erste JSON-Objekt aus einer Antwort herausziehen."""
    text = text.strip()
    # Code-Fences entfernen, falls das Modell doch welche setzt
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Keine JSON-Struktur in der Antwort gefunden.")
    return json.loads(text[start : end + 1])


def _build_context(series: dict[str, Any]) -> str:
    """Baut den Kontext-Block (Serie, Charaktere, bisherige Folgen)."""
    lines = [
        f"Serientitel: {series.get('title', 'Unbenannt')}",
        f"Genre: {series.get('genre', 'unbestimmt')}",
    ]
    chars = series.get("characters", [])
    if chars:
        roster = ", ".join(
            f"{c['name']} ({c.get('role', 'Charakter')})" for c in chars
        )
        lines.append(f"Bekannte Charaktere: {roster}")
    episodes = series.get("episodes", [])
    if episodes:
        lines.append("\nBisheriger Verlauf:")
        for ep in episodes:
            num = ep.get("number", "?")
            title = ep.get("episode_title", "")
            syn = ep.get("synopsis", "")
            lines.append(f"  Folge {num}: {title} – {syn}")
    return "\n".join(lines)


def generate_episode(series: dict[str, Any], keywords: str) -> dict[str, Any]:
    """Erzeugt aus Stichworten die naechste Folge einer Serie."""
    number = len(series.get("episodes", [])) + 1
    if _has_api_key():
        try:
            return _generate_with_claude(series, keywords, number)
        except Exception as exc:  # Fallback, falls die API streikt
            print(f"[anime_studio] Claude-Fehler, nutze Demo: {exc}")
    return _generate_demo(series, keywords, number)


def _generate_with_claude(
    series: dict[str, Any], keywords: str, number: int
) -> dict[str, Any]:
    client = Anthropic()
    context = _build_context(series)
    user_msg = (
        f"{context}\n\n"
        f"Erstelle jetzt FOLGE {number}.\n"
        f"Stichworte / gewuenschte Handlung dieser Folge:\n{keywords}\n"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = "".join(
        block.text for block in resp.content if getattr(block, "type", "") == "text"
    )
    episode = _extract_json(raw)
    return _normalise(episode, number)


def _normalise(episode: dict[str, Any], number: int) -> dict[str, Any]:
    """Stellt sicher, dass das Episoden-Objekt sauber und vollstaendig ist."""
    episode.setdefault("episode_title", f"Folge {number}")
    episode.setdefault("synopsis", "")
    episode.setdefault("cliffhanger", "")
    episode.setdefault("new_characters", [])
    episode["number"] = number
    scenes = episode.get("scenes") or []
    for sc in scenes:
        sc.setdefault("location", "Unbekannter Ort")
        sc.setdefault("narration", "")
        sc.setdefault("dialogue", [])
        if sc.get("mood") not in MOODS:
            sc["mood"] = "ruhig"
        for line in sc["dialogue"]:
            line.setdefault("speaker", "???")
            line.setdefault("emotion", "")
            line.setdefault("text", "")
    episode["scenes"] = scenes
    return episode


def _normalise_scene(scene: dict[str, Any]) -> dict[str, Any]:
    scene.setdefault("location", "Unbekannter Ort")
    scene.setdefault("narration", "")
    scene.setdefault("dialogue", [])
    if scene.get("mood") not in MOODS:
        scene["mood"] = "ruhig"
    for line in scene["dialogue"]:
        line.setdefault("speaker", "???")
        line.setdefault("emotion", "")
        line.setdefault("text", "")
    return scene


SCENE_SYSTEM = """\
Du bist Anime-Drehbuchautor. Schreibe EINE einzelne Szene auf DEUTSCH neu, \
passend zum Kontext der Folge. Antworte AUSSCHLIESSLICH mit gueltigem JSON \
(keine Erklaerung, kein Markdown) in genau diesem Schema:

{
  "location": "Schauplatz",
  "mood": "eine von: ruhig, froehlich, spannend, traurig, episch, romantisch, duester, geheimnisvoll",
  "narration": "kurzer Erzaehltext",
  "dialogue": [ {"speaker": "Name", "emotion": "Gefuehl", "text": "Satz"} ]
}
"""


def regenerate_scene(
    series: dict[str, Any],
    episode: dict[str, Any],
    scene_index: int,
    hint: str = "",
) -> dict[str, Any]:
    """Erzeugt eine einzelne Szene einer Folge neu."""
    if _has_api_key():
        try:
            return _regen_scene_claude(series, episode, scene_index, hint)
        except Exception as exc:  # pragma: no cover
            print(f"[anime_studio] Szenen-Regen-Fehler, nutze Demo: {exc}")
    # Demo-Fallback: zufaellige neue Szene
    chars = [c["name"] for c in series.get("characters", [])] or ["Akira", "Yuki"]
    loc, mood = random.choice(_DEMO_LOCATIONS)
    sp = random.sample(chars, min(2, len(chars)))
    dialogue = [{"speaker": sp[0], "emotion": "ueberrascht",
                 "text": hint or "Etwas Unerwartetes geschieht!"}]
    if len(sp) > 1:
        dialogue.append({"speaker": sp[1], "emotion": "entschlossen",
                         "text": "Dann lass es uns gemeinsam angehen!"})
    return _normalise_scene(
        {"location": loc, "mood": mood,
         "narration": "(Demo) Eine frisch gewuerfelte Szene.",
         "dialogue": dialogue}
    )


def _regen_scene_claude(
    series: dict[str, Any], episode: dict[str, Any], scene_index: int, hint: str
) -> dict[str, Any]:
    client = Anthropic()
    context = _build_context(series)
    old = episode.get("scenes", [])[scene_index]
    user_msg = (
        f"{context}\n\n"
        f"Folge: {episode.get('episode_title', '')} – {episode.get('synopsis', '')}\n"
        f"Die bisherige Szene {scene_index + 1} war:\n{json.dumps(old, ensure_ascii=False)}\n\n"
        f"Schreibe diese Szene neu."
        + (f" Beachte dabei: {hint}" if hint else "")
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SCENE_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = "".join(
        b.text for b in resp.content if getattr(b, "type", "") == "text"
    )
    return _normalise_scene(_extract_json(raw))


# --------------------------------------------------------------------------
# Demo-Generator (ohne API-Key) – damit die Seite immer etwas zeigt
# --------------------------------------------------------------------------

_DEMO_LOCATIONS = [
    ("Dach der Oberschule bei Sonnenuntergang", "ruhig"),
    ("Verlassene U-Bahn-Station", "geheimnisvoll"),
    ("Schlachtfeld unter rotem Himmel", "episch"),
    ("Kirschbluetenallee im Fruehling", "romantisch"),
    ("Regennasse Stadt bei Nacht", "duester"),
    ("Belebtes Klassenzimmer", "froehlich"),
    ("Bergspitze ueber den Wolken", "spannend"),
]


def _generate_demo(
    series: dict[str, Any], keywords: str, number: int
) -> dict[str, Any]:
    chars = [c["name"] for c in series.get("characters", [])] or [
        "Akira", "Yuki", "Sensei"
    ]
    words = [w for w in re.split(r"[\s,]+", keywords) if w][:6] or ["Geheimnis"]
    n_scenes = random.randint(4, 5)
    scenes = []
    locs = random.sample(_DEMO_LOCATIONS, min(n_scenes, len(_DEMO_LOCATIONS)))
    for i in range(n_scenes):
        loc, mood = locs[i % len(locs)]
        topic = words[i % len(words)]
        speakers = random.sample(chars, min(2, len(chars)))
        dialogue = [
            {
                "speaker": speakers[0],
                "emotion": "entschlossen",
                "text": f"Wir muessen uns dem Thema '{topic}' stellen!",
            }
        ]
        if len(speakers) > 1:
            dialogue.append(
                {
                    "speaker": speakers[1],
                    "emotion": "nervoes",
                    "text": f"Aber ist das wegen {topic} nicht viel zu gefaehrlich?",
                }
            )
        dialogue.append(
            {
                "speaker": speakers[0],
                "emotion": "mutig",
                "text": "Egal was kommt – wir geben nicht auf!",
            }
        )
        scenes.append(
            {
                "location": loc,
                "mood": mood,
                "narration": f"Die Szene fuehrt unsere Helden zu '{topic}'.",
                "dialogue": dialogue,
            }
        )
    return _normalise(
        {
            "episode_title": f"Das Geheimnis von {words[0].capitalize()}",
            "synopsis": (
                f"(Demo-Modus – ohne API-Key) Folge {number} rund um die "
                f"Stichworte: {keywords}."
            ),
            "scenes": scenes,
            "new_characters": [],
            "cliffhanger": "Was wird im naechsten Kapitel geschehen...?",
        },
        number,
    )


# --------------------------------------------------------------------------
# Charakter-Aussehen (fuer konsistente Bilder ueber alle Szenen)
# --------------------------------------------------------------------------

_APPEARANCE_SYSTEM = """\
Du beschreibst das feste visuelle Aussehen von Anime-Charakteren fuer einen \
Bild-Generator. Antworte AUSSCHLIESSLICH mit gueltigem JSON: ein Objekt, das \
jedem Namen eine kurze, praegnante ENGLISCHE Aussehensbeschreibung zuordnet \
(Haarfarbe/-stil, Augenfarbe, Hautton, typische Kleidung, Alter, besondere \
Merkmale). Beispiel:
{"Akira": "teenage boy, spiky black hair, golden eyes, red jacket, scar on cheek"}
Keine Erklaerung, nur das JSON-Objekt.
"""

_DEMO_HAIR = ["spiky black", "long silver", "short blue", "wild red", "tied blonde", "messy brown"]
_DEMO_EYES = ["golden", "emerald green", "crimson", "deep blue", "violet", "amber"]
_DEMO_OUTFIT = ["a red captain's coat", "a blue school uniform", "light samurai armor",
                "a green traveler's cloak", "a black combat outfit", "white robes"]


def _demo_appearance(name: str) -> str:
    h = sum(ord(c) for c in name)
    return (
        f"anime character, {_DEMO_HAIR[h % len(_DEMO_HAIR)]} hair, "
        f"{_DEMO_EYES[(h // 3) % len(_DEMO_EYES)]} eyes, "
        f"wearing {_DEMO_OUTFIT[(h // 7) % len(_DEMO_OUTFIT)]}"
    )


def generate_appearances(series: dict[str, Any]) -> dict[str, str]:
    """Erzeugt feste Aussehensbeschreibungen fuer Charaktere ohne 'appearance'."""
    missing = [c for c in series.get("characters", []) if not c.get("appearance")]
    if not missing:
        return {}
    names = [c["name"] for c in missing]
    result: dict[str, str] = {}
    if _has_api_key():
        try:
            client = Anthropic()
            roster = "\n".join(
                f"- {c['name']} ({c.get('role', 'Charakter')})" for c in missing
            )
            msg = (
                f"Serie: {series.get('title', '')} (Genre: {series.get('genre', '')}).\n"
                f"Beschreibe das Aussehen dieser Charaktere:\n{roster}"
            )
            resp = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=_APPEARANCE_SYSTEM,
                messages=[{"role": "user", "content": msg}],
            )
            raw = "".join(
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            )
            result = _extract_json(raw)
        except Exception as exc:  # pragma: no cover
            print(f"[anime_studio] Aussehen-Fehler, nutze Demo: {exc}")
    # Luecken mit Demo fuellen
    for name in names:
        if not result.get(name):
            result[name] = _demo_appearance(name)
    return result
