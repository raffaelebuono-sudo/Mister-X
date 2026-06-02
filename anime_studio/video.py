"""Video-Export: macht aus einer Folge eine echte MP4-Datei.

Pro Dialogzeile entsteht ein Standbild (Szenenbild der Bild-KI oder ein
Stimmungs-Hintergrund) mit eingebrannten Untertiteln. ffmpeg fuegt einen
sanften Ken-Burns-Zoom und weiche Ein-/Ausblendungen hinzu und haengt – wenn
ElevenLabs aktiv ist – die gesprochenen Stimmen darunter. Alle Clips werden
zu einer Folge zusammengefuegt.

Benoetigt ffmpeg (wird ueber das Paket imageio-ffmpeg mitgeliefert) und
Pillow. Beides ist in requirements.txt eingetragen.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from . import audio

BASE_DIR = Path(__file__).resolve().parent
MEDIA_DIR = BASE_DIR / "data" / "media"
IMAGES_DIR = BASE_DIR / "data" / "images"

W, H = 1280, 720
FPS = 25
ACCENT = (255, 93, 143)

# Stimmungsfarben (oben -> unten) – Fallback, wenn kein KI-Bild da ist
MOOD_COLORS = {
    "ruhig": ((59, 111, 176), (28, 43, 74)),
    "froehlich": ((255, 183, 77), (255, 126, 179)),
    "spannend": ((123, 47, 247), (26, 0, 51)),
    "traurig": ((58, 74, 107), (16, 19, 31)),
    "episch": ((195, 20, 50), (36, 11, 54)),
    "romantisch": ((255, 106, 136), (255, 153, 172)),
    "duester": ((35, 37, 38), (10, 10, 18)),
    "geheimnisvoll": ((31, 64, 55), (22, 19, 31)),
}


def available() -> bool:
    return _ffmpeg_exe() is not None


def _ffmpeg_exe() -> str | None:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = shutil.which("ffmpeg")
        return exe


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1: skalierbar
    except Exception:  # pragma: no cover
        return ImageFont.load_default()


def _gradient(mood: str) -> Image.Image:
    top, bottom = MOOD_COLORS.get(mood, MOOD_COLORS["ruhig"])
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(W):
            px[x, y] = (r, g, b)
    return img


def _cover(img: Image.Image) -> Image.Image:
    """Bild formatfuellend auf W x H zuschneiden."""
    img = img.convert("RGB")
    iw, ih = img.size
    scale = max(W / iw, H / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - W) // 2, (nh - H) // 2
    return img.crop((left, top, left + W, top + H))


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _base_image(scene: dict[str, Any]) -> Image.Image:
    img_path = scene.get("image")
    if img_path:
        # gespeicherter Web-Pfad '/images/<serie>/<datei>' -> echte Datei
        rel = img_path.lstrip("/").split("/", 1)[-1]  # '<serie>/<datei>'
        f = IMAGES_DIR / rel
        if f.exists():
            try:
                return _cover(Image.open(f))
            except Exception:
                pass
    return _gradient(scene.get("mood", "ruhig"))


def _draw_overlay(
    location: str, speaker: str, emotion: str, text: str, out: Path
) -> None:
    """Transparente Text-Ebene (Chip + Untertitel) – liegt FEST ueber dem
    zoomenden Bild, wird also nicht vom Ken-Burns-Effekt beschnitten."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Schauplatz-Chip oben links
    if location:
        f_loc = _font(26)
        tw = draw.textlength(location, font=f_loc)
        draw.rounded_rectangle([24, 22, 24 + tw + 28, 22 + 44], 14, fill=(0, 0, 0, 150))
        draw.text((38, 30), location, font=f_loc, fill=(255, 255, 255, 255))

    # Untertitel-Bereich unten
    if text:
        f_name = _font(28)
        f_text = _font(38)
        margin = 60
        max_w = W - 2 * margin
        lines = _wrap(draw, text, f_text, max_w)
        line_h = 50
        box_h = 40 + (28 if speaker else 0) + len(lines) * line_h
        box_top = H - box_h - 36
        draw.rounded_rectangle(
            [margin - 20, box_top, W - margin + 20, H - 28], 18, fill=(8, 8, 22, 220)
        )
        y = box_top + 18
        if speaker:
            label = speaker + (f"  ({emotion})" if emotion else "")
            draw.text((margin, y), label, font=f_name, fill=ACCENT + (255,))
            y += 40
        for ln in lines:
            draw.text((margin, y), ln, font=f_text, fill=(245, 243, 255, 255))
            y += line_h

    img.save(out)


def _title_overlay(series: dict[str, Any], episode: dict[str, Any], out: Path) -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 90))
    draw = ImageDraw.Draw(img)
    f_small = _font(30)
    f_big = _font(60)
    title = series.get("title", "Anime")
    epline = f"Folge {episode.get('number', 1)}: {episode.get('episode_title', '')}"
    tw = draw.textlength(title, font=f_big)
    draw.text(((W - tw) / 2, H / 2 - 80), title, font=f_big, fill=(255, 255, 255, 255))
    ew = draw.textlength(epline, font=f_small)
    draw.text(((W - ew) / 2, H / 2 + 10), epline, font=f_small, fill=ACCENT + (255,))
    img.save(out)


def _estimate_duration(text: str) -> float:
    words = max(1, len(text.split()))
    return max(2.2, min(9.0, words * 0.42 + 0.8))


def _make_clip(ffmpeg: str, bg: Path, overlay: Path, audio_path: Path | None,
               duration: float, idx: int, out: Path) -> None:
    """Baut einen Clip: zoomender Hintergrund + feste Text-Ebene + Ton."""
    total = max(2, int(duration * FPS))
    # Ken-Burns: langsamer Zoom, Richtung wechselt je Clip
    if idx % 2 == 0:
        z = "min(zoom+0.0009,1.18)"
    else:
        z = "if(lte(zoom,1.0),1.18,max(1.001,zoom-0.0009))"
    fade_out = max(0.0, duration - 0.4)
    # input 0 = Hintergrund, input 1 = Audio, input 2 = Text-Ebene
    if audio_path:
        inputs = ["-loop", "1", "-i", str(bg), "-i", str(audio_path),
                  "-loop", "1", "-i", str(overlay)]
    else:
        inputs = ["-loop", "1", "-i", str(bg),
                  "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                  "-loop", "1", "-i", str(overlay)]
    filt = (
        f"[0:v]scale=2560:1440:force_original_aspect_ratio=increase,crop=2560:1440,"
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={total}:s={W}x{H}:fps={FPS}[zb];"
        f"[zb][2:v]overlay=0:0,"
        f"fade=t=in:st=0:d=0.4,fade=t=out:st={fade_out:.2f}:d=0.4,"
        f"format=yuv420p[v]"
    )
    cmd = [
        ffmpeg, "-y", *inputs, "-t", f"{duration:.2f}",
        "-filter_complex", filt, "-map", "[v]", "-map", "1:a", "-r", str(FPS),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-preset", "veryfast", "-c:a", "aac", "-ar", "44100", "-ac", "2",
        "-b:a", "128k", str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def build_episode_video(series: dict[str, Any], episode: dict[str, Any]) -> str | None:
    """Baut die Folge als MP4 und gibt den Web-Pfad zurueck (z.B. /media/..)."""
    ffmpeg = _ffmpeg_exe()
    if not ffmpeg:
        return None

    work = Path(tempfile.mkdtemp(prefix="anime_vid_"))
    clips: list[Path] = []
    try:
        # Titelkarte (Hintergrund-Gradient + feste Titel-Ebene)
        first_mood = (episode.get("scenes") or [{}])[0].get("mood", "episch")
        tc_bg = work / "title_bg.png"
        _gradient(first_mood).save(tc_bg)
        tc_ov = work / "title_ov.png"
        _title_overlay(series, episode, tc_ov)
        tc_clip = work / "clip_title.mp4"
        _make_clip(ffmpeg, tc_bg, tc_ov, None, 2.6, 0, tc_clip)
        clips.append(tc_clip)

        idx = 1
        for scene in episode.get("scenes", []):
            dialogue = scene.get("dialogue", [])
            # Szene ohne Dialog -> ein Frame mit Erzaehltext
            items = dialogue or [{"speaker": "", "emotion": "",
                                  "text": scene.get("narration", "…")}]
            bg = work / f"bg_{idx}.png"
            _base_image(scene).save(bg)  # Hintergrund (einmal pro Szene wiederverwendbar)
            for line in items:
                text = line.get("text", "")
                speaker = line.get("speaker", "")
                emotion = line.get("emotion", "")
                overlay = work / f"ov_{idx}.png"
                _draw_overlay(scene.get("location", ""), speaker, emotion, text, overlay)

                audio_path = None
                duration = _estimate_duration(text)
                if speaker and text and audio.available():
                    res = audio.synthesize_to_file(text, speaker, work)
                    if res:
                        audio_path, duration = res
                        duration += 0.6  # kleine Pause am Ende

                clip = work / f"clip_{idx}.mp4"
                _make_clip(ffmpeg, bg, overlay, audio_path, duration, idx, clip)
                clips.append(clip)
                idx += 1

        # Alle Clips zusammenfuegen (gleiche Codec-Parameter -> copy)
        listfile = work / "list.txt"
        listfile.write_text(
            "\n".join(f"file '{c.as_posix()}'" for c in clips), encoding="utf-8"
        )
        safe = "".join(c for c in series["id"] if c.isalnum() or c in "-_")
        out_dir = MEDIA_DIR / safe
        out_dir.mkdir(parents=True, exist_ok=True)
        out_name = f"folge{episode.get('number', 1)}_{uuid.uuid4().hex[:6]}.mp4"
        out_path = out_dir / out_name
        subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
             "-c", "copy", str(out_path)],
            check=True, capture_output=True,
        )
        return f"/media/{safe}/{out_name}"
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        print("[anime_studio] ffmpeg-Fehler:",
              (exc.stderr or b"").decode(errors="ignore")[-800:])
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)
