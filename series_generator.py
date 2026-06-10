#!/usr/bin/env python3
"""2D-Serien-Generator – ganze Folgen aus einer einzigen Idee.

Eigenständiges Skript für das JARVIS-Projekt. Aus einem kurzen Konzept
("Eine mutige Maus erkundet den Weltraum") erzeugt es:

  1. ein Drehbuch  – Claude (Anthropic) schreibt Serien-Bibel + Folgen
                     mit Szenen, Dialogen, Bild-Prompts und Untertiteln
  2. 2D-Bilder     – pro Szene; entweder über die OpenAI-Bild-API
                     (wenn OPENAI_API_KEY gesetzt ist) oder als gerendertes
                     2D-Comic-Panel mit Pillow (läuft ohne weiteren Key)
  3. Erzähler      – optional gesprochene Erzählung (ElevenLabs oder macOS `say`)
  4. Video         – Frames + Audio werden per ffmpeg zu einer .mp4 montiert

Beispiele
---------
    # Eine Folge, läuft sofort (PIL-Bilder, kein extra Key nötig)
    python series_generator.py --idea "Eine mutige Maus im Weltraum"

    # Drei Folgen, je 6 Szenen, mit Erzähler-Stimme
    python series_generator.py --idea "Detektiv-Katze löst Fälle" \
        --episodes 3 --scenes 6 --narrate

    # Nur das Drehbuch, kein Video (schnell)
    python series_generator.py --idea "Roboter lernt kochen" --no-video

Voraussetzungen: ANTHROPIC_API_KEY in der .env. Für Video: ffmpeg.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path

# --- .env laden (gleiche Logik wie das restliche Projekt) ----------------
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:  # pragma: no cover - dotenv ist nur Komfort
    pass

PROJECT_ROOT = Path(__file__).resolve().parent


# =========================================================================
#  Datenmodelle
# =========================================================================
@dataclass
class Scene:
    index: int
    description: str          # Was in der Szene passiert (Regie)
    image_prompt: str         # Prompt für die Bildgenerierung
    caption: str              # Untertitel / Erzähltext für diese Szene
    dialogue: list[str] = field(default_factory=list)  # ["Name: Text", ...]


@dataclass
class Episode:
    number: int
    title: str
    logline: str
    scenes: list[Scene]


@dataclass
class Series:
    title: str
    genre: str
    style: str                # visueller Stil (z. B. "flacher Cartoon")
    synopsis: str
    characters: list[dict]    # [{"name":..., "look":..., "color":"#rrggbb"}]
    episodes: list[Episode]


# =========================================================================
#  1) Drehbuch mit Claude erzeugen
# =========================================================================
SCRIPT_SYSTEM = (
    "Du bist ein erfahrener Showrunner und Drehbuchautor für 2D-Animationsserien. "
    "Du lieferst ausschließlich gültiges JSON ohne Erklärungen davor oder danach."
)


def _build_prompt(idea: str, episodes: int, scenes: int, style: str, lang: str) -> str:
    return textwrap.dedent(
        f"""
        Entwickle eine 2D-Animationsserie auf Basis dieser Idee:
        "{idea}"

        Sprache aller Texte (Titel, Dialoge, Untertitel): {lang}.
        Visueller Stil: {style}.

        Erzeuge {episodes} zusammenhängende Folge(n) mit je {scenes} Szenen.
        Die Folgen sollen aufeinander aufbauen (durchgehender roter Faden).
        Jede Szene braucht einen kurzen, kindgerecht-klaren Untertitel
        und 0–2 Dialogzeilen im Format "Figur: Text".
        Der image_prompt beschreibt EIN 2D-Bild im genannten Stil
        (Englisch erlaubt, sehr bildhaft, ohne Text im Bild).

        Antworte NUR mit JSON nach exakt diesem Schema:
        {{
          "title": "Serientitel",
          "genre": "z. B. Abenteuer-Comedy",
          "style": "{style}",
          "synopsis": "2-3 Sätze Gesamthandlung",
          "characters": [
            {{"name": "Name", "look": "kurze Aussehensbeschreibung",
              "color": "#RRGGBB"}}
          ],
          "episodes": [
            {{
              "number": 1,
              "title": "Folgentitel",
              "logline": "Ein Satz worum es geht",
              "scenes": [
                {{
                  "description": "Regieanweisung der Szene",
                  "image_prompt": "bildhafter Prompt für ein 2D-Bild",
                  "caption": "kurzer Untertitel",
                  "dialogue": ["Figur: Text"]
                }}
              ]
            }}
          ]
        }}
        """
    ).strip()


def _extract_json(text: str) -> dict:
    """Robust: holt das erste JSON-Objekt aus Claudes Antwort."""
    text = text.strip()
    # ```json ... ``` Zäune entfernen
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # ersten { bis letzten } nehmen
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def generate_script(
    idea: str, episodes: int, scenes: int, style: str, lang: str,
    model: str, max_tokens: int, retries: int = 3,
) -> Series:
    try:
        import anthropic
    except ImportError:
        sys.exit("Fehlt: `pip install anthropic` (siehe requirements.txt).")

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY fehlt. Bitte in der .env-Datei eintragen.")

    client = anthropic.Anthropic(api_key=api_key)
    prompt = _build_prompt(idea, episodes, scenes, style, lang)

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=SCRIPT_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = "".join(
                block.text for block in resp.content
                if getattr(block, "type", None) == "text"
            )
            data = _extract_json(raw)
            return _parse_series(data, style)
        except Exception as exc:  # noqa: BLE001 - Netzwerk/JSON robust auffangen
            last_err = exc
            wait = 2.0 * attempt
            print(f"  ! Drehbuch-Versuch {attempt}/{retries} fehlgeschlagen "
                  f"({exc}). Neuer Versuch in {wait:.0f}s …")
            time.sleep(wait)
    raise RuntimeError(f"Drehbuch konnte nicht erzeugt werden: {last_err}")


def _parse_series(data: dict, style: str) -> Series:
    episodes: list[Episode] = []
    for e_i, ep in enumerate(data.get("episodes", []), start=1):
        scenes: list[Scene] = []
        for s_i, sc in enumerate(ep.get("scenes", []), start=1):
            scenes.append(
                Scene(
                    index=s_i,
                    description=str(sc.get("description", "")).strip(),
                    image_prompt=str(sc.get("image_prompt", "")).strip(),
                    caption=str(sc.get("caption", "")).strip(),
                    dialogue=[str(d).strip() for d in sc.get("dialogue", []) if str(d).strip()],
                )
            )
        episodes.append(
            Episode(
                number=int(ep.get("number", e_i)),
                title=str(ep.get("title", f"Folge {e_i}")).strip(),
                logline=str(ep.get("logline", "")).strip(),
                scenes=scenes,
            )
        )
    return Series(
        title=str(data.get("title", "Namenlose Serie")).strip(),
        genre=str(data.get("genre", "")).strip(),
        style=str(data.get("style", style)).strip(),
        synopsis=str(data.get("synopsis", "")).strip(),
        characters=list(data.get("characters", [])),
        episodes=episodes,
    )


# =========================================================================
#  2) Bilder erzeugen – OpenAI (falls Key) oder Pillow-Fallback
# =========================================================================
def _slug(text: str, maxlen: int = 40) -> str:
    s = re.sub(r"[^\w\-]+", "_", text.strip().lower(), flags=re.UNICODE)
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or "x")[:maxlen]


def generate_image_openai(prompt: str, out: Path, size: str = "1024x1024") -> bool:
    """Versucht OpenAI-Bildgenerierung. Gibt True bei Erfolg zurück."""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return False
    try:
        from openai import OpenAI
        import base64

        client = OpenAI(api_key=key)
        result = client.images.generate(
            model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
            prompt=prompt,
            size=size,
            n=1,
        )
        b64 = result.data[0].b64_json
        out.write_bytes(base64.b64decode(b64))
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  ! OpenAI-Bild fehlgeschlagen ({exc}); nutze Pillow-Fallback.")
        return False


# ---- Pillow-Fallback: ein 2D-Comic-Panel selbst zeichnen ----------------
def _font(size: int):
    from PIL import ImageFont

    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",      # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",   # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _hex(color: str, default=(120, 160, 220)) -> tuple[int, int, int]:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", (color or "").strip())
    if not m:
        return default
    h = m.group(1)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _palette(seed: int) -> dict:
    """Deterministische, freundliche Farbpalette pro Szene."""
    skies = [
        ((135, 206, 250), (255, 224, 178)),  # Tag
        ((25, 25, 112), (72, 61, 139)),       # Nacht
        ((255, 183, 178), (255, 218, 193)),   # Abendrot
        ((176, 224, 230), (224, 255, 255)),   # frisch
    ]
    grounds = [(124, 179, 66), (96, 125, 139), (141, 110, 99), (38, 50, 56)]
    top, bottom = skies[seed % len(skies)]
    ground = grounds[seed % len(grounds)]
    return {"top": top, "bottom": bottom, "ground": ground}


def render_panel_pil(scene: Scene, series: Series, out: Path,
                     width: int, height: int) -> None:
    """Zeichnet ein einfaches, aber stimmiges 2D-Szenen-Panel."""
    from PIL import Image, ImageDraw

    pal = _palette(scene.index + len(scene.caption))
    img = Image.new("RGB", (width, height), pal["bottom"])
    draw = ImageDraw.Draw(img)

    # Himmel-Verlauf (oben -> Horizont)
    horizon = int(height * 0.62)
    top, bot = pal["top"], pal["bottom"]
    for y in range(horizon):
        t = y / max(1, horizon)
        col = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (width, y)], fill=col)

    # Boden
    draw.rectangle([0, horizon, width, height], fill=pal["ground"])

    # Sonne/Mond
    sun = (255, 241, 118) if scene.index % 2 == 0 else (236, 239, 241)
    r = int(width * 0.07)
    cx = int(width * (0.2 + 0.12 * (scene.index % 4)))
    draw.ellipse([cx - r, int(height * 0.12) - r, cx + r, int(height * 0.12) + r],
                 fill=sun)

    # ein paar Wolken
    cloud = (255, 255, 255)
    for k in range(3):
        wx = int(width * (0.15 + 0.3 * k)) + (scene.index * 17 % 40)
        wy = int(height * (0.18 + 0.06 * (k % 2)))
        for dx in (-40, 0, 40):
            draw.ellipse([wx + dx - 35, wy - 20, wx + dx + 35, wy + 20], fill=cloud)

    # Figuren (eine pro Hauptcharakter, max. 3) als simple Cartoon-Körper
    chars = series.characters[:3] or [{"name": "?", "color": "#ef5350"}]
    n = len(chars)
    for i, ch in enumerate(chars):
        col = _hex(ch.get("color", ""))
        fx = int(width * (0.30 + 0.4 * (i / max(1, n - 1) if n > 1 else 0.0)))
        feet = horizon + int(height * 0.16)
        bw, bh = int(width * 0.07), int(height * 0.18)   # Körper
        draw.rounded_rectangle([fx - bw, feet - bh, fx + bw, feet],
                               radius=bw, fill=col)
        hr = int(width * 0.05)                            # Kopf
        hy = feet - bh - hr
        draw.ellipse([fx - hr, hy - hr, fx + hr, hy + hr], fill=col)
        # Augen
        eye = (33, 33, 33)
        draw.ellipse([fx - hr // 2 - 4, hy - 6, fx - hr // 2 + 4, hy + 2], fill=eye)
        draw.ellipse([fx + hr // 2 - 4, hy - 6, fx + hr // 2 + 4, hy + 2], fill=eye)

    _overlay_text(img, draw, scene, series, width, height)
    img.save(out, "PNG")


def _overlay_text(img, draw, scene: Scene, series: Series,
                  width: int, height: int) -> None:
    from PIL import Image

    pad = int(width * 0.03)

    # Serien-/Folgen-Label oben links
    label_font = _font(max(16, width // 40))
    draw.text((pad, pad), series.title.upper(), font=label_font,
              fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))

    # Dialog-Sprechblase (falls vorhanden)
    if scene.dialogue:
        dlg_font = _font(max(16, width // 42))
        text = "  •  ".join(scene.dialogue)
        wrapped = textwrap.fill(text, width=max(20, width // 18))
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=dlg_font)
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        bx, by = pad, int(height * 0.30)
        draw.rounded_rectangle(
            [bx - 10, by - 10, bx + bw + 20, by + bh + 20],
            radius=14, fill=(255, 255, 255, 230), outline=(0, 0, 0), width=2)
        draw.multiline_text((bx, by), wrapped, font=dlg_font, fill=(20, 20, 20))

    # Untertitel-Balken unten
    if scene.caption:
        cap_font = _font(max(18, width // 32))
        wrapped = textwrap.fill(scene.caption, width=max(24, width // 14))
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=cap_font)
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        bar_h = bh + 2 * pad
        overlay = Image.new("RGBA", (width, bar_h), (0, 0, 0, 160))
        img.paste(Image.alpha_composite(
            img.crop((0, height - bar_h, width, height)).convert("RGBA"), overlay),
            (0, height - bar_h))
        draw.multiline_text(
            ((width - bw) // 2, height - bar_h + pad), wrapped,
            font=cap_font, fill=(255, 255, 255), align="center")


def make_scene_image(scene: Scene, series: Series, out: Path,
                     width: int, height: int, use_openai: bool) -> None:
    """Erzeugt das Szenenbild. Bei OpenAI-Erfolg werden Untertitel/Dialog
    nachträglich einkopiert, damit beide Wege gleich aussehen."""
    if use_openai:
        size = "1024x1024" if width == height else "1792x1024"
        prompt = (f"{scene.image_prompt}. Style: {series.style}, 2D animation, "
                  f"flat colors, clean lines, no text in image.")
        if generate_image_openai(prompt, out, size):
            try:
                from PIL import Image, ImageDraw

                img = Image.open(out).convert("RGB").resize((width, height))
                _overlay_text(img, ImageDraw.Draw(img), scene, series, width, height)
                img.save(out, "PNG")
                return
            except Exception:
                return  # rohes OpenAI-Bild behalten
    render_panel_pil(scene, series, out, width, height)


# =========================================================================
#  3) Erzähler-Stimme (optional)
# =========================================================================
def narrate_episode(ep: Episode, out: Path) -> Path | None:
    """Erzeugt eine MP3/Audio-Spur. ElevenLabs > macOS `say` > nichts."""
    text = " ".join(s.caption for s in ep.scenes if s.caption).strip()
    if not text:
        return None

    # ElevenLabs
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if key:
        try:
            import requests

            voice = os.getenv("ELEVENLABS_VOICE_ID", "").strip() or "EXAVITQu4vr4xnSDxMaL"
            r = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                headers={"xi-api-key": key, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_multilingual_v2"},
                timeout=120,
            )
            if r.ok:
                mp3 = out.with_suffix(".mp3")
                mp3.write_bytes(r.content)
                return mp3
            print(f"  ! ElevenLabs HTTP {r.status_code}; versuche macOS `say`.")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! ElevenLabs fehlgeschlagen ({exc}); versuche macOS `say`.")

    # macOS `say`
    if shutil.which("say"):
        aiff = out.with_suffix(".aiff")
        try:
            subprocess.run(["say", "-o", str(aiff), text], check=True)
            if shutil.which("ffmpeg"):
                mp3 = out.with_suffix(".mp3")
                subprocess.run(["ffmpeg", "-y", "-i", str(aiff), str(mp3)],
                               check=True, capture_output=True)
                aiff.unlink(missing_ok=True)
                return mp3
            return aiff
        except Exception as exc:  # noqa: BLE001
            print(f"  ! `say` fehlgeschlagen ({exc}); ohne Erzähler.")
    else:
        print("  ! Keine TTS verfügbar (kein ELEVENLABS_API_KEY, kein `say`).")
    return None


# =========================================================================
#  4) Video mit ffmpeg montieren
# =========================================================================
def assemble_video(frames: list[Path], out: Path, fps: int,
                   seconds_per_scene: float, audio: Path | None) -> bool:
    if not shutil.which("ffmpeg"):
        print("  ! ffmpeg nicht gefunden – überspringe Video. "
              "(macOS: `brew install ffmpeg`)")
        return False

    # Concat-Demuxer-Liste: jedes Frame n Sekunden zeigen
    listfile = out.with_suffix(".txt")
    lines = []
    for fr in frames:
        lines.append(f"file '{fr.resolve().as_posix()}'")
        lines.append(f"duration {seconds_per_scene}")
    lines.append(f"file '{frames[-1].resolve().as_posix()}'")  # letztes Frame fixieren
    listfile.write_text("\n".join(lines), encoding="utf-8")

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile)]
    if audio and audio.exists():
        cmd += ["-i", str(audio), "-shortest"]
    cmd += [
        "-vf", f"fps={fps},format=yuv420p",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
    ]
    if audio and audio.exists():
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd.append(str(out))

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        listfile.unlink(missing_ok=True)
        return True
    except subprocess.CalledProcessError as exc:
        print(f"  ! ffmpeg-Fehler: {exc.stderr.decode(errors='ignore')[-500:]}")
        return False


# =========================================================================
#  Orchestrierung
# =========================================================================
def build_series(args) -> Path:
    print(f"🎬 Erzeuge Drehbuch mit {args.model} …")
    series = generate_script(
        idea=args.idea, episodes=args.episodes, scenes=args.scenes,
        style=args.style, lang=args.lang, model=args.model,
        max_tokens=args.max_tokens,
    )
    print(f"   → Serie: «{series.title}» ({series.genre}) "
          f"– {len(series.episodes)} Folge(n)")

    base = Path(args.output) / _slug(series.title)
    base.mkdir(parents=True, exist_ok=True)

    # Drehbuch als JSON sichern
    script_json = base / "drehbuch.json"
    script_json.write_text(
        json.dumps(_series_to_dict(series), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"   → Drehbuch gespeichert: {script_json}")

    use_openai = bool(os.getenv("OPENAI_API_KEY", "").strip()) and not args.no_openai_images
    if use_openai:
        print("   → Bildquelle: OpenAI-Bild-API")
    else:
        print("   → Bildquelle: Pillow-2D-Panels (kein Bild-API-Key nötig)")

    for ep in series.episodes:
        ep_dir = base / f"folge_{ep.number:02d}_{_slug(ep.title)}"
        frames_dir = ep_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n📺 Folge {ep.number}: «{ep.title}» – {len(ep.scenes)} Szenen")

        frames: list[Path] = []
        for scene in ep.scenes:
            fpath = frames_dir / f"szene_{scene.index:02d}.png"
            print(f"   • Szene {scene.index}: {scene.caption[:50]}")
            make_scene_image(scene, series, fpath, args.width, args.height, use_openai)
            frames.append(fpath)

        if args.no_video:
            continue

        audio = None
        if args.narrate:
            print("   • erzeuge Erzähler-Stimme …")
            audio = narrate_episode(ep, ep_dir / "narration")

        video = ep_dir / f"{_slug(ep.title)}.mp4"
        print("   • montiere Video …")
        if assemble_video(frames, video, args.fps, args.seconds_per_scene, audio):
            print(f"   ✓ Video: {video}")

    print(f"\n✅ Fertig! Alles unter: {base}")
    return base


def _series_to_dict(s: Series) -> dict:
    return {
        "title": s.title, "genre": s.genre, "style": s.style,
        "synopsis": s.synopsis, "characters": s.characters,
        "episodes": [
            {
                "number": e.number, "title": e.title, "logline": e.logline,
                "scenes": [
                    {
                        "index": sc.index, "description": sc.description,
                        "image_prompt": sc.image_prompt, "caption": sc.caption,
                        "dialogue": sc.dialogue,
                    }
                    for sc in e.scenes
                ],
            }
            for e in s.episodes
        ],
    }


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="2D-Serien-Generator – ganze Folgen aus einer Idee.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--idea", "--konzept", dest="idea", required=True,
                   help="Kurze Idee der Serie, z. B. 'Eine mutige Maus im Weltraum'.")
    p.add_argument("--episodes", "--folgen", dest="episodes", type=int, default=1,
                   help="Anzahl Folgen (Standard: 1).")
    p.add_argument("--scenes", "--szenen", dest="scenes", type=int, default=5,
                   help="Szenen pro Folge (Standard: 5).")
    p.add_argument("--style", "--stil", dest="style", default="flacher, bunter Cartoon-Stil",
                   help="Visueller Stil.")
    p.add_argument("--lang", "--sprache", dest="lang", default="Deutsch",
                   help="Sprache der Texte (Standard: Deutsch).")
    p.add_argument("--width", type=int, default=1280, help="Breite der Frames.")
    p.add_argument("--height", type=int, default=720, help="Höhe der Frames.")
    p.add_argument("--fps", type=int, default=24, help="Video-Bildrate.")
    p.add_argument("--seconds-per-scene", type=float, default=4.0,
                   help="Anzeigedauer je Szene in Sekunden.")
    p.add_argument("--narrate", action="store_true",
                   help="Erzähler-Stimme erzeugen (ElevenLabs oder macOS `say`).")
    p.add_argument("--no-video", action="store_true",
                   help="Nur Drehbuch + Bilder, kein Video.")
    p.add_argument("--no-openai-images", action="store_true",
                   help="OpenAI-Bild-API ignorieren, immer Pillow nutzen.")
    p.add_argument("--output", "--out", dest="output", default=str(PROJECT_ROOT / "output" / "serien"),
                   help="Ausgabeverzeichnis.")
    p.add_argument("--model", default=os.getenv("SERIES_MODEL", "claude-sonnet-4-6"),
                   help="Claude-Modell fürs Drehbuch.")
    p.add_argument("--max-tokens", type=int, default=8000,
                   help="Max. Tokens fürs Drehbuch (mehr Folgen → höher).")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        build_series(args)
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"Fehler: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
