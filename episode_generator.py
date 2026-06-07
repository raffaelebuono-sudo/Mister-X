#!/usr/bin/env python3
"""KI-Serien-Generator – ganze animierte Folgen.

Erzeugt eine komplette, vertonte 2D-Animationsfolge aus einer Idee:

  1. Drehbuch (Claude, in Teilen) – Serien-Bibel, Figuren, Szenen-Outline,
     dann pro Szene die vollen Dialoge & Regieanweisungen. Dadurch sind
     auch lange Folgen (Ziel-Minuten einstellbar) möglich.
  2. Stimmen – pro Figur eine eigene Stimme (ElevenLabs oder macOS `say`),
     mit Lippen-Sync nach Audio-Lautstärke. Ohne TTS: prozedurale Lippen.
  3. Animation – die animation_engine posiert die Figuren je Frame:
     laufen, gestikulieren, blinzeln, sprechen. Mehrere Figuren pro Szene.
  4. Schnitt – jede Szene wird zu einem Clip mit Tonspur, danach werden
     alle Szenen per ffmpeg zur fertigen Folge montiert.

Beispiele
---------
    # Kurze Test-Folge (~2 Min), läuft mit ANTHROPIC_API_KEY
    python episode_generator.py --idea "Sternenflotten-Crew voller Chaos" --minutes 2

    # Lange Folge (Ziel 40 Min) mit Stimmen
    python episode_generator.py --idea "Detektiv-Katze im All" --minutes 40 --voice

    # Aus vorhandenem Drehbuch neu rendern (ohne Claude-Aufruf)
    python episode_generator.py --script-json output/.../drehbuch.json

Voraussetzungen: ANTHROPIC_API_KEY (für neues Drehbuch), ffmpeg (Video),
numpy + Pillow. Stimmen optional über ELEVENLABS_API_KEY oder macOS `say`.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import animation_engine as ae

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:  # pragma: no cover
    pass

PROJECT_ROOT = Path(__file__).resolve().parent
SAMPLE_RATE = 22050

# Sprech-Tempo für die Zeit-Schätzung ohne TTS (Sekunden pro Wort)
SECONDS_PER_WORD = 0.42
GAP_BETWEEN_LINES = 0.35      # Sekunde Stille zwischen Dialogzeilen
SCENE_HEAD_TAIL = 0.6         # Stille-Polster am Szenen-Anfang/-Ende


# =========================================================================
#  Claude-Aufruf
# =========================================================================
def _claude(client, model: str, system: str, user: str, max_tokens: int,
            retries: int = 3) -> str:
    last = None
    for attempt in range(1, retries + 1):
        try:
            resp = client.messages.create(
                model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}],
            )
            return "".join(b.text for b in resp.content
                           if getattr(b, "type", None) == "text")
        except Exception as exc:  # noqa: BLE001
            last = exc
            wait = 2.0 * attempt
            print(f"  ! Claude-Versuch {attempt}/{retries}: {exc} – warte {wait:.0f}s")
            time.sleep(wait)
    raise RuntimeError(f"Claude-Aufruf fehlgeschlagen: {last}")


def _extract_json(text: str):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    for o, c in (("{", "}"), ("[", "]")):
        s, e = text.find(o), text.rfind(c)
        if s != -1 and e != -1 and (s < text.find("{") + 1 or o == text[s]):
            pass
    s, e = text.find("{"), text.rfind("}")
    a, b = text.find("["), text.rfind("]")
    # Wähle die äußerste Struktur
    if a != -1 and (s == -1 or a < s):
        return json.loads(text[a:b + 1])
    return json.loads(text[s:e + 1])


# =========================================================================
#  Drehbuch erzeugen (in Teilen → lange Folgen möglich)
# =========================================================================
BIBLE_SYSTEM = ("Du bist Showrunner für 2D-Animationsserien (Stil: erwachsene "
                "Sitcom wie 'Lower Decks'). Antworte ausschließlich mit gültigem JSON.")


def generate_bible(client, model: str, idea: str, lang: str, n_scenes: int) -> dict:
    user = f"""
Entwirf eine 2D-Animationsserie nach dieser Idee: "{idea}".
Sprache aller Texte: {lang}. Ton: humorvolle Sitcom mit durchgehender Handlung.

Liefere NUR JSON:
{{
  "title": "Serientitel",
  "genre": "z. B. Sci-Fi-Comedy",
  "episode_title": "Titel dieser Folge",
  "synopsis": "3-4 Sätze Handlung dieser Folge",
  "characters": [
    {{"name":"Name","role":"Funktion","color":"#RRGGBB",
      "voice_hint":"z.B. tief/hoch/nerdig"}}
  ],
  "scenes": [
    {{"location":"kurzer Schauplatz (z.B. Brücke, Maschinenraum, Bar)",
      "beat":"was in dieser Szene story-technisch passiert (1 Satz)",
      "characters":["Name1","Name2"]}}
  ]
}}
Erzeuge GENAU {n_scenes} Szenen mit rotem Faden (Anfang, Mitte, Pointe/Ende).
3 bis 6 Hauptfiguren.
""".strip()
    return _extract_json(_claude(client, model, BIBLE_SYSTEM, user, max_tokens=3000))


SCENE_SYSTEM = ("Du schreibst Drehbuch-Dialoge für eine animierte Sitcom. "
                "Antworte ausschließlich mit gültigem JSON-Array.")


def generate_scene_dialogue(client, model: str, bible: dict, scene: dict,
                            lang: str, target_words: int) -> list[dict]:
    chars = ", ".join(scene.get("characters", []) or
                      [c["name"] for c in bible["characters"]])
    user = f"""
Serie: "{bible.get('title')}" – Folge: "{bible.get('episode_title')}".
Schauplatz: {scene.get('location')}. Story-Beat: {scene.get('beat')}.
Anwesende Figuren: {chars}. Sprache: {lang}.

Schreibe lebendige, witzige Dialoge für DIESE Szene – ca. {target_words} Wörter
insgesamt (genug, um die Szene zu füllen). Wechsle die Sprecher natürlich.
Jede Zeile hat optional eine kurze Bewegung/Aktion.

Liefere NUR ein JSON-Array:
[
  {{"speaker":"Figurenname","line":"gesprochener Text",
    "action":"optional: geht|zeigt|lacht|kommt_rein|geht_raus|nickt"}}
]
""".strip()
    data = _extract_json(_claude(client, model, SCENE_SYSTEM, user, max_tokens=4000))
    out = []
    for d in data if isinstance(data, list) else []:
        line = str(d.get("line", "")).strip()
        if not line:
            continue
        out.append({
            "speaker": str(d.get("speaker", "")).strip() or "?",
            "line": line,
            "action": str(d.get("action", "")).strip().lower(),
        })
    return out


def build_script(idea: str, minutes: float, lang: str, model: str) -> dict:
    try:
        import anthropic
    except ImportError:
        sys.exit("Fehlt: `pip install anthropic`.")
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        sys.exit("ANTHROPIC_API_KEY fehlt (für neues Drehbuch). In .env eintragen.")
    client = anthropic.Anthropic(api_key=key)

    total_sec = minutes * 60.0
    avg_scene_sec = 90.0                     # ~1,5 Min pro Szene
    n_scenes = max(3, round(total_sec / avg_scene_sec))
    print(f"🎬 Drehbuch: {idea!r} → {n_scenes} Szenen für ~{minutes:g} Min")

    bible = generate_bible(client, model, idea, lang, n_scenes)
    print(f"   → «{bible.get('title')}» / Folge: «{bible.get('episode_title')}» "
          f"({len(bible.get('characters', []))} Figuren)")

    scene_sec = total_sec / max(1, len(bible.get("scenes", [])))
    target_words = max(40, int(scene_sec / SECONDS_PER_WORD))

    scenes_out = []
    for i, sc in enumerate(bible.get("scenes", []), start=1):
        print(f"   • Szene {i}/{len(bible['scenes'])}: {sc.get('location')} …")
        dialogue = generate_scene_dialogue(client, model, bible, sc, lang, target_words)
        scenes_out.append({
            "location": sc.get("location", "Innenraum"),
            "beat": sc.get("beat", ""),
            "characters": sc.get("characters", []),
            "dialogue": dialogue,
        })

    return {
        "title": bible.get("title", "Serie"),
        "genre": bible.get("genre", ""),
        "episode_title": bible.get("episode_title", "Folge 1"),
        "synopsis": bible.get("synopsis", ""),
        "lang": lang,
        "characters": bible.get("characters", []),
        "scenes": scenes_out,
    }


# =========================================================================
#  Stimmen / TTS
# =========================================================================
# Ein paar öffentliche ElevenLabs-Default-Voices für Abwechslung.
ELEVEN_VOICES = [
    "EXAVITQu4vr4xnSDxMaL",  # Sarah
    "TxGEqnHWrfWFTfGW9XjX",  # Josh
    "VR6AewLTigWG4xSOukaG",  # Arnold
    "pNInz6obpgDQGcFmaJgB",  # Adam
    "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "AZnzlk1XvdvUeBnXmlld",  # Domi
]
MAC_VOICES = ["Anna", "Markus", "Petra", "Yannick", "Viktor", "Helena"]


def assign_voices(characters: list[dict]) -> dict[str, str]:
    """Jede Figur bekommt eine eigene, stabile Stimme."""
    use_eleven = bool(os.getenv("ELEVENLABS_API_KEY", "").strip())
    pool = ELEVEN_VOICES if use_eleven else MAC_VOICES
    mapping = {}
    for i, c in enumerate(characters):
        name = str(c.get("name", f"Figur {i}"))
        mapping[name] = c.get("voice") or pool[i % len(pool)]
    return mapping


def tts_line(text: str, voice: str, out_wav: Path) -> float:
    """Synthese einer Zeile -> WAV bei SAMPLE_RATE mono. Gibt Dauer (s) zurück.
    Reihenfolge: ElevenLabs -> macOS `say` -> (None = keine Audio)."""
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    tmp = out_wav.with_suffix(".src")
    got = False
    if key and re.fullmatch(r"[A-Za-z0-9]+", voice or ""):
        try:
            import requests
            r = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                headers={"xi-api-key": key, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_multilingual_v2"}, timeout=120)
            if r.ok:
                tmp.write_bytes(r.content); got = True
            else:
                print(f"    ! ElevenLabs HTTP {r.status_code}")
        except Exception as exc:  # noqa: BLE001
            print(f"    ! ElevenLabs: {exc}")
    if not got and shutil.which("say"):
        try:
            subprocess.run(["say", "-v", voice if voice in MAC_VOICES else "Anna",
                            "-o", str(tmp), text], check=True)
            got = True
        except Exception as exc:  # noqa: BLE001
            print(f"    ! say: {exc}")
    if not got:
        return 0.0
    # nach WAV @ SAMPLE_RATE mono konvertieren
    subprocess.run(["ffmpeg", "-y", "-i", str(tmp), "-ar", str(SAMPLE_RATE),
                    "-ac", "1", str(out_wav)], check=True, capture_output=True)
    tmp.unlink(missing_ok=True)
    return _wav_duration(out_wav)


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _wav_samples(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        n = w.getnframes()
        raw = w.readframes(n)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


# =========================================================================
#  Schrift
# =========================================================================
def _font(size: int):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "/System/Library/Fonts/Helvetica.ttc"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


# =========================================================================
#  Szenen-Timeline aufbauen (mit oder ohne Stimme)
# =========================================================================
@dataclass
class Line:
    speaker: str
    text: str
    action: str
    start: float
    dur: float
    env: np.ndarray | None = None   # Lautstärke-Hüllkurve (für Lippen-Sync)
    wav: Path | None = None


def build_timeline(scene: dict, voices: dict[str, str], audio_dir: Path,
                   use_voice: bool, fps: int) -> tuple[list[Line], float]:
    lines: list[Line] = []
    t = SCENE_HEAD_TAIL
    for i, d in enumerate(scene.get("dialogue", [])):
        speaker, text = d["speaker"], d["line"]
        dur, env, wav = 0.0, None, None
        if use_voice:
            wav = audio_dir / f"l{i:03d}.wav"
            voice = voices.get(speaker) or next(iter(voices.values()), "Anna")
            dur = tts_line(text, voice, wav)
            if dur > 0:
                env = _envelope(_wav_samples(wav), dur, fps)
            else:
                wav = None
        if dur <= 0:  # Schätzung / prozedural
            dur = max(1.1, len(text.split()) * SECONDS_PER_WORD)
        lines.append(Line(speaker, text, d.get("action", ""), t, dur, env, wav))
        t += dur + GAP_BETWEEN_LINES
    total = t - GAP_BETWEEN_LINES + SCENE_HEAD_TAIL
    return lines, max(total, 1.5)


def _envelope(samples: np.ndarray, dur: float, fps: int) -> np.ndarray:
    """RMS-Hüllkurve je Frame, normiert auf 0..1 (für Mundöffnung)."""
    n_frames = max(1, int(dur * fps))
    win = max(1, len(samples) // n_frames)
    env = np.array([np.sqrt(np.mean(samples[i*win:(i+1)*win] ** 2) + 1e-9)
                    for i in range(n_frames)])
    if env.max() > 0:
        env = env / env.max()
    return np.clip(env * 1.4, 0, 1)


def _mouth_at(line: Line, local_t: float, fps: int) -> float:
    if line.env is not None and len(line.env):
        idx = min(len(line.env) - 1, int(local_t * fps))
        return float(line.env[idx])
    # prozedural: Mund flattert im Sprech-Tempo
    return max(0.0, math.sin(local_t * 19.0) * 0.5 + 0.5) * 0.85


# =========================================================================
#  Szene rendern
# =========================================================================
def _place_characters(names: list[str], width: int) -> dict[str, float]:
    """Verteilt anwesende Figuren gleichmäßig über die Bühne."""
    names = names or []
    n = max(1, len(names))
    pos = {}
    for i, nm in enumerate(names):
        frac = (i + 1) / (n + 1)
        pos[nm] = width * (0.18 + 0.64 * frac)
    return pos


def _draw_subtitle(img: Image.Image, speaker: str, text: str,
                   width: int, height: int) -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    font = _font(max(18, width // 38))
    name_font = _font(max(16, width // 46))
    import textwrap
    wrapped = textwrap.fill(text, width=max(28, width // 13))
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = int(width * 0.02)
    bar_h = bh + 3 * pad
    draw.rectangle([0, height - bar_h, width, height], fill=(0, 0, 0, 170))
    draw.text((pad, height - bar_h + pad // 2), speaker.upper() + ":",
              font=name_font, fill=(255, 214, 80))
    draw.multiline_text(((width - bw) // 2, height - bar_h + pad + bh // 4),
                        wrapped, font=font, fill=(255, 255, 255), align="center")


def render_scene(scene: dict, characters: dict[str, ae.Character],
                 voices: dict[str, str], out_dir: Path, idx: int,
                 width: int, height: int, fps: int, use_voice: bool) -> Path | None:
    frames_dir = out_dir / f"scene_{idx:03d}_frames"
    audio_dir = out_dir / f"scene_{idx:03d}_audio"
    frames_dir.mkdir(parents=True, exist_ok=True)
    if use_voice:
        audio_dir.mkdir(parents=True, exist_ok=True)

    lines, duration = build_timeline(scene, voices, audio_dir, use_voice, fps)
    present = scene.get("characters") or list(characters.keys())[:4]
    present = [p for p in present if p in characters] or list(characters.keys())[:1]
    positions = _place_characters(present, width)
    ground_y = int(height * 0.93)

    bg = ae.render_background(width, height, scene.get("location", "innen"), seed=idx)
    n_frames = int(duration * fps)

    # Hilfs-Index: welche Zeile läuft zu Zeit t?
    def active_line(t):
        for ln in lines:
            if ln.start <= t < ln.start + ln.dur:
                return ln
        return None

    for f in range(n_frames):
        t = f / fps
        img = bg.copy()
        draw = ImageDraw.Draw(img)
        cur = active_line(t)

        # Figuren von hinten nach vorne (einfach: feste Reihenfolge)
        for nm in present:
            ch = characters[nm]
            x = positions[nm]
            speaking = bool(cur and cur.speaker == nm)
            local_t = (t - cur.start) if speaking else 0.0
            mouth = _mouth_at(cur, local_t, fps) if speaking else 0.0
            # Blinzeln: ~alle 3,5s kurz
            blink_cycle = (t + ch.phase) % 3.5
            eye = 0.1 if blink_cycle < 0.12 else 1.0
            # Aktionen
            action = (cur.action if speaking else "")
            walking = "geht" in action or "kommt" in action
            wphase = t * 9 if walking else 0.0
            arm = 0.0
            if speaking and mouth > 0.45:
                arm = 0.5 + 0.3 * math.sin(t * 6)
            if "zeigt" in action:
                arm = 0.9
            facing = 1 if x < width / 2 else -1
            pose = ae.Pose(
                x=x, ground_y=ground_y, facing=facing,
                walk_phase=wphase, bob=math.sin(t * 5 + ch.phase) * (height * 0.004),
                mouth_open=mouth, eye_open=eye, arm_raise=arm, walking=walking)
            ae.draw_character(draw, ch, pose, height)

        # Serien-Label oben + Untertitel unten
        lab = _font(max(14, width // 50))
        draw.text((int(width * 0.02), int(height * 0.03)),
                  scene.get("_series_label", ""), font=lab,
                  fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
        if cur:
            _draw_subtitle(img, cur.speaker, cur.text, width, height)

        img.save(frames_dir / f"{f:05d}.png")

    # Tonspur der Szene zusammenbauen
    scene_audio = None
    if use_voice and any(ln.wav for ln in lines):
        scene_audio = out_dir / f"scene_{idx:03d}.wav"
        _mix_scene_audio(lines, duration, scene_audio)

    # Szene zu Clip rendern
    clip = out_dir / f"scene_{idx:03d}.mp4"
    cmd = ["ffmpeg", "-y", "-framerate", str(fps),
           "-i", str(frames_dir / "%05d.png")]
    if scene_audio and scene_audio.exists():
        cmd += ["-i", str(scene_audio)]
    cmd += ["-vf", "format=yuv420p", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if scene_audio and scene_audio.exists():
        cmd += ["-c:a", "aac", "-b:a", "160k", "-shortest"]
    cmd.append(str(clip))
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        print(f"    ! ffmpeg-Szene {idx}: {exc.stderr.decode(errors='ignore')[-300:]}")
        return None
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)
    return clip


def _mix_scene_audio(lines: list[Line], duration: float, out: Path) -> None:
    total = int(duration * SAMPLE_RATE) + SAMPLE_RATE
    track = np.zeros(total, dtype=np.float32)
    for ln in lines:
        if not ln.wav:
            continue
        s = _wav_samples(ln.wav)
        start = int(ln.start * SAMPLE_RATE)
        end = min(total, start + len(s))
        track[start:end] += s[:end - start]
    track = np.clip(track, -1, 1)
    pcm = (track * 32767).astype(np.int16)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())


# =========================================================================
#  Titel- / Abspann-Karte
# =========================================================================
def render_title_card(title: str, subtitle: str, out: Path, idx: int,
                      width: int, height: int, fps: int, seconds: float = 3.0) -> Path:
    frames_dir = out / f"scene_{idx:03d}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    n = int(seconds * fps)
    for f in range(n):
        img = Image.new("RGB", (width, height), (8, 10, 24))
        d = ImageDraw.Draw(img)
        rng = ae._Rng(f)
        for _ in range(120):
            x = rng.randint(0, width); y = rng.randint(0, height)
            d.ellipse([x, y, x + 1, y + 1], fill=(255, 255, 255))
        tf = _font(max(28, width // 16)); sf = _font(max(16, width // 40))
        tb = d.textbbox((0, 0), title, font=tf)
        d.text(((width - (tb[2]-tb[0]))//2, height*0.38), title, font=tf,
               fill=(255, 214, 80), stroke_width=3, stroke_fill=(0, 0, 0))
        sb = d.textbbox((0, 0), subtitle, font=sf)
        d.text(((width - (sb[2]-sb[0]))//2, height*0.52), subtitle, font=sf,
               fill=(220, 220, 230))
        img.save(frames_dir / f"{f:05d}.png")
    clip = out / f"scene_{idx:03d}.mp4"
    subprocess.run(["ffmpeg", "-y", "-framerate", str(fps),
                    "-i", str(frames_dir / "%05d.png"),
                    "-vf", "format=yuv420p", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(clip)],
                   check=True, capture_output=True)
    shutil.rmtree(frames_dir, ignore_errors=True)
    return clip


# =========================================================================
#  Folge zusammenbauen
# =========================================================================
def concat_clips(clips: list[Path], out: Path, fps: int) -> bool:
    listfile = out.with_suffix(".concat.txt")
    listfile.write_text("\n".join(f"file '{c.resolve().as_posix()}'" for c in clips),
                        encoding="utf-8")
    # Re-Encode beim Concat, damit Clips mit/ohne Audio sauber zusammenpassen
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
           "-vf", f"fps={fps},format=yuv420p", "-c:v", "libx264",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", str(out)]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        listfile.unlink(missing_ok=True)
        return True
    except subprocess.CalledProcessError as exc:
        print(f"  ! Concat-Fehler: {exc.stderr.decode(errors='ignore')[-400:]}")
        return False


def produce_episode(script: dict, args) -> Path:
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg fehlt – nötig für Video. (macOS: brew install ffmpeg)")

    base = Path(args.output) / _slug(script["title"]) / _slug(script.get("episode_title", "folge"))
    base.mkdir(parents=True, exist_ok=True)
    (base / "drehbuch.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

    characters = {c["name"]: ae.Character.from_spec(c, i)
                  for i, c in enumerate(script["characters"])}
    voices = assign_voices(script["characters"])
    label = f"{script['title']} – {script.get('episode_title','')}"

    use_voice = args.voice and not args.no_voice
    if use_voice and not (os.getenv("ELEVENLABS_API_KEY") or shutil.which("say")):
        print("  ! Keine TTS verfügbar – nutze prozedurale Lippen-Bewegung.")
        use_voice = False

    work = base / "_clips"
    work.mkdir(exist_ok=True)
    clips: list[Path] = []

    print(f"🎞️  Rendere «{label}» – {len(script['scenes'])} Szenen "
          f"({args.width}x{args.height}, {args.fps}fps, "
          f"Stimme: {'ja' if use_voice else 'prozedural'})")

    # Titel-Karte
    clips.append(render_title_card(script["title"], script.get("episode_title", ""),
                                   work, 0, args.width, args.height, args.fps))

    for i, scene in enumerate(script["scenes"], start=1):
        scene["_series_label"] = label
        print(f"   • Szene {i}/{len(script['scenes'])}: {scene.get('location')} "
              f"({len(scene.get('dialogue', []))} Zeilen)")
        clip = render_scene(scene, characters, voices, work, i,
                            args.width, args.height, args.fps, use_voice)
        if clip:
            clips.append(clip)

    out = base / f"{_slug(script.get('episode_title','folge'))}.mp4"
    print("   • montiere Folge …")
    if concat_clips(clips, out, args.fps):
        dur = _probe_duration(out)
        print(f"\n✅ Fertige Folge: {out}  (~{dur/60:.1f} Min)")
        if not args.keep_clips:
            shutil.rmtree(work, ignore_errors=True)
    return base


def _probe_duration(path: Path) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True)
        return float(r.stdout.strip() or 0)
    except Exception:
        return 0.0


def _slug(text: str, maxlen: int = 50) -> str:
    s = re.sub(r"[^\w\-]+", "_", (text or "x").strip().lower(), flags=re.UNICODE)
    return (re.sub(r"_+", "_", s).strip("_") or "x")[:maxlen]


# =========================================================================
#  CLI
# =========================================================================
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="KI-Serien-Generator – ganze animierte Folgen.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--idea", "--konzept", dest="idea",
                   help="Serien-Idee (für neues Drehbuch).")
    p.add_argument("--minutes", "--minuten", dest="minutes", type=float, default=3.0,
                   help="Ziel-Länge der Folge in Minuten (Standard 3).")
    p.add_argument("--lang", "--sprache", dest="lang", default="Deutsch")
    p.add_argument("--script-json", dest="script_json",
                   help="Vorhandenes Drehbuch laden statt Claude aufzurufen.")
    p.add_argument("--voice", "--stimme", dest="voice", action="store_true",
                   help="Echte Stimmen erzeugen (ElevenLabs oder macOS say).")
    p.add_argument("--no-voice", dest="no_voice", action="store_true",
                   help="Keine TTS – prozedurale Lippen-Bewegung.")
    p.add_argument("--width", type=int, default=854)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--fps", type=int, default=12)
    p.add_argument("--keep-clips", action="store_true",
                   help="Einzel-Szenen-Clips behalten (Debug).")
    p.add_argument("--output", "--out", dest="output",
                   default=str(PROJECT_ROOT / "output" / "serien"))
    p.add_argument("--model", default=os.getenv("SERIES_MODEL", "claude-sonnet-4-6"))
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.script_json:
            script = json.loads(Path(args.script_json).read_text(encoding="utf-8"))
            print(f"📂 Drehbuch geladen: {script.get('title')}")
        elif args.idea:
            script = build_script(args.idea, args.minutes, args.lang, args.model)
        else:
            sys.exit("Bitte --idea \"…\" oder --script-json <datei> angeben.")
        produce_episode(script, args)
    except KeyboardInterrupt:
        print("\nAbgebrochen."); return 130
    except Exception as exc:  # noqa: BLE001
        print(f"Fehler: {exc}"); return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
