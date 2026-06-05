"""Manga-Seiten-Generator (klassischer Schwarz-Weiss-Stil).

Verwandelt eine generierte Folge (Szenen + Dialoge) in echte Manga-Seiten:
Panels in klassischem Raster-Layout, Sprechblasen mit Sprech-Spitze,
Erzaehl-Kaesten, Seitenrahmen – Leserichtung rechts nach links.

Funktioniert OHNE API-Key (Panels als Screentone-Platzhalter). Mit Bild-Key
werden die Panels zu echter S/W-Manga-Linienkunst.

Export: PNG-Seiten, ein PDF und eine CBZ-Datei (fuer Manga-Reader-Apps).
"""

from __future__ import annotations

import os
import uuid
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from . import images as imgmod

MANGA_DIR = Path(__file__).resolve().parent / "data" / "manga"

PAGE_W, PAGE_H = 1240, 1754  # A4-Verhaeltnis, ~150 dpi
MARGIN = 46
GUTTER = 18
BORDER = 5            # Panel-Rahmenstaerke
INK = (20, 20, 20)
PAPER = (250, 249, 245)
BUBBLE = (255, 255, 255)


def available() -> bool:
    return True  # Layout geht immer; Bilder optional


# --------------------------------------------------------------------------
# Schrift
# --------------------------------------------------------------------------

def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except Exception:  # pragma: no cover
        return ImageFont.load_default()


_REPL = {
    "—": "-", "–": "-", "…": "...",
    "„": '"', "“": '"', "”": '"', "«": '"', "»": '"',
    "‚": "'", "‘": "'", "’": "'",
}


def _san(text: str) -> str:
    for k, v in _REPL.items():
        text = text.replace(k, v)
    return text


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in _san(text).split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# --------------------------------------------------------------------------
# Layout-Vorlagen (Bruchteile des Inhaltsbereichs, in Leserichtung r->l)
# --------------------------------------------------------------------------

LAYOUTS: dict[int, list[tuple[float, float, float, float]]] = {
    1: [(0, 0, 1, 1)],
    2: [(0, 0, 1, 0.5), (0, 0.5, 1, 0.5)],
    3: [(0, 0, 1, 0.42),
        (0.5, 0.42, 0.5, 0.58), (0, 0.42, 0.5, 0.58)],
    4: [(0.5, 0, 0.5, 0.5), (0, 0, 0.5, 0.5),
        (0.5, 0.5, 0.5, 0.5), (0, 0.5, 0.5, 0.5)],
    5: [(0.5, 0, 0.5, 0.32), (0, 0, 0.5, 0.32),
        (0, 0.32, 1, 0.36),
        (0.5, 0.68, 0.5, 0.32), (0, 0.68, 0.5, 0.32)],
    6: [(0.5, 0, 0.5, 0.34), (0, 0, 0.5, 0.34),
        (0.5, 0.34, 0.5, 0.32), (0, 0.34, 0.5, 0.32),
        (0.5, 0.66, 0.5, 0.34), (0, 0.66, 0.5, 0.34)],
}


def _rects(count: int) -> list[tuple[int, int, int, int]]:
    """Panel-Rechtecke in Pixeln fuer eine Seite mit 'count' Panels."""
    count = max(1, min(count, 6))
    cw = PAGE_W - 2 * MARGIN
    ch = PAGE_H - 2 * MARGIN
    out = []
    for fx, fy, fw, fh in LAYOUTS[count]:
        x = MARGIN + int(fx * cw) + GUTTER // 2
        y = MARGIN + int(fy * ch) + GUTTER // 2
        w = int(fw * cw) - GUTTER
        h = int(fh * ch) - GUTTER
        out.append((x, y, w, h))
    return out


# --------------------------------------------------------------------------
# Panel-Bild
# --------------------------------------------------------------------------

def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    img = img.convert("L")  # Graustufen -> Manga-Look
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h)).convert("RGB")


def _screentone(w: int, h: int, seed: int) -> Image.Image:
    """Platzhalter-Panel ohne KI: heller Screentone mit Punktraster."""
    shade = 232 - (seed % 4) * 14
    img = Image.new("RGB", (w, h), (shade, shade, shade))
    d = ImageDraw.Draw(img)
    step = 14
    for yy in range(0, h, step):
        for xx in range((yy // step % 2) * step // 2, w, step):
            d.ellipse([xx, yy, xx + 3, yy + 3], fill=(shade - 40, shade - 40, shade - 40))
    return img


def _panel_image(panel: dict[str, Any], w: int, h: int, seed: int) -> Image.Image:
    cached = panel.get("_img")
    if isinstance(cached, Image.Image):
        return _cover(cached, w, h)
    return _screentone(w, h, seed)


# --------------------------------------------------------------------------
# Sprechblasen & Kaesten
# --------------------------------------------------------------------------

def _bubble(draw: ImageDraw.ImageDraw, cx: int, top: int, max_w: int,
            text: str, font, tail_down: bool = True) -> int:
    """Zeichnet eine Sprechblase zentriert auf cx ab y=top. Gibt Unterkante zurueck."""
    lines = _wrap(draw, text, font, max_w - 40)
    lh = (font.size + 6) if hasattr(font, "size") else 18
    tw = max((draw.textlength(ln, font=font) for ln in lines), default=10)
    bw = int(min(max_w, tw + 40))
    bh = int(len(lines) * lh + 26)
    left = int(cx - bw / 2)
    box = [left, top, left + bw, top + bh]
    draw.ellipse(box, fill=BUBBLE, outline=INK, width=3)
    if tail_down:  # kleine Sprech-Spitze nach unten
        tx = cx - 10
        draw.polygon([(tx, box[3] - 4), (tx + 20, box[3] - 4), (cx - 4, box[3] + 22)],
                     fill=BUBBLE, outline=INK)
        draw.line([(tx, box[3] - 2), (cx - 4, box[3] + 22)], fill=INK, width=3)
        draw.line([(tx + 20, box[3] - 2), (cx - 4, box[3] + 22)], fill=INK, width=3)
    y = top + 14
    for ln in lines:
        lw = draw.textlength(ln, font=font)
        draw.text((cx - lw / 2, y), ln, font=font, fill=INK)
        y += lh
    return box[3] + (26 if tail_down else 6)


def _caption(draw: ImageDraw.ImageDraw, x: int, y: int, max_w: int,
             text: str, font) -> None:
    """Erzaehl-Kasten oben links im Panel."""
    lines = _wrap(draw, text, font, max_w - 24)[:3]
    lh = (font.size + 5) if hasattr(font, "size") else 17
    bw = int(min(max_w, max((draw.textlength(ln, font=font) for ln in lines), default=10) + 24))
    bh = int(len(lines) * lh + 16)
    draw.rectangle([x, y, x + bw, y + bh], fill=(255, 255, 255), outline=INK, width=2)
    yy = y + 8
    for ln in lines:
        draw.text((x + 12, yy), ln, font=font, fill=INK)
        yy += lh


# --------------------------------------------------------------------------
# Seite zeichnen
# --------------------------------------------------------------------------

def _draw_panel(page: Image.Image, draw: ImageDraw.ImageDraw,
                rect: tuple[int, int, int, int], panel: dict[str, Any],
                seed: int) -> None:
    x, y, w, h = rect
    art = _panel_image(panel, w, h, seed)
    page.paste(art, (x, y))
    draw.rectangle([x, y, x + w, y + h], outline=INK, width=BORDER)

    cap_font = _font(20)
    bub_font = _font(21)

    narration = panel.get("narration")
    if narration:
        _caption(draw, x + 10, y + 10, min(w - 20, 360), narration, cap_font)

    bubbles = panel.get("bubbles", [])
    cx = x + w // 2
    top = y + (76 if narration else 22)
    for line in bubbles[:3]:
        speaker = line.get("speaker", "")
        text = line.get("text", "")
        if not text:
            continue
        full = f"{speaker}: {text}" if speaker and speaker != "???" else text
        top = _bubble(draw, cx, top, min(w - 30, 460), full, bub_font) + 12
        if top > y + h - 60:
            break


def _render_page(panels: list[dict[str, Any]], page_no: int) -> Image.Image:
    page = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
    draw = ImageDraw.Draw(page)
    for i, (rect, panel) in enumerate(zip(_rects(len(panels)), panels)):
        _draw_panel(page, draw, rect, panel, seed=page_no * 7 + i)
    # Seitenzahl unten + Leserichtungs-Hinweis
    f = _font(18)
    draw.text((MARGIN, PAGE_H - MARGIN + 8), f"- {page_no} -", font=f, fill=INK)
    return page


def _cover_page(series: dict[str, Any], episode: dict[str, Any]) -> Image.Image:
    page = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
    draw = ImageDraw.Draw(page)
    draw.rectangle([MARGIN, MARGIN, PAGE_W - MARGIN, PAGE_H - MARGIN],
                   outline=INK, width=8)
    title = _san(series.get("title", "Manga"))
    tf = _font(84)
    tw = draw.textlength(title, font=tf)
    draw.text(((PAGE_W - tw) / 2, 360), title, font=tf, fill=INK)
    sf = _font(40)
    sub = _san(f"Kapitel {episode.get('number', 1)}: {episode.get('title', '')}")
    sw = draw.textlength(sub, font=sf)
    draw.text(((PAGE_W - sw) / 2, 480), sub, font=sf, fill=INK)
    hint = "<-- Bitte von rechts nach links lesen"
    hf = _font(24)
    hw = draw.textlength(hint, font=hf)
    draw.text(((PAGE_W - hw) / 2, PAGE_H - 220), hint, font=hf, fill=INK)
    return page


# --------------------------------------------------------------------------
# Panels aus der Folge ableiten
# --------------------------------------------------------------------------

def _scene_image(series: dict[str, Any], scene: dict[str, Any],
                 use_ai: bool) -> Image.Image | None:
    """S/W-Manga-Bild fuer eine Szene (einmal pro Szene)."""
    if use_ai and imgmod.available():
        prompt = imgmod.build_prompt(series, scene, style=imgmod.MANGA_STYLE)
        data = imgmod.generate_from_prompt(prompt)
        if data:
            import io
            try:
                return Image.open(io.BytesIO(data))
            except Exception:  # pragma: no cover
                return None
    # vorhandenes Szenenbild als Graustufe nutzen, falls vorhanden
    web = scene.get("image")
    if web:
        local = imgmod.IMAGES_DIR / web.lstrip("/").split("/", 1)[-1]
        if local.exists():
            try:
                return Image.open(local)
            except Exception:  # pragma: no cover
                return None
    return None


def _build_panels(series: dict[str, Any], episode: dict[str, Any],
                  use_ai: bool) -> list[dict[str, Any]]:
    panels: list[dict[str, Any]] = []
    for scene in episode.get("scenes", []):
        art = _scene_image(series, scene, use_ai)
        dialogue = scene.get("dialogue", []) or []
        narration = scene.get("narration", "")
        if not dialogue:
            panels.append({"_img": art, "bubbles": [], "narration": narration})
            continue
        # max. 2 Sprechblasen pro Panel -> Szene ggf. auf mehrere Panels verteilen
        for i in range(0, len(dialogue), 2):
            panels.append({
                "_img": art,
                "bubbles": dialogue[i:i + 2],
                "narration": narration if i == 0 else "",
            })
    return panels or [{"_img": None, "bubbles": [], "narration": "…"}]


def _paginate(panels: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Verteilt Panels auf Seiten (3-5 Panels je Seite, leicht variierend)."""
    pages, i, n = [], 0, len(panels)
    pattern = [4, 3, 5, 4, 6, 3]
    p = 0
    while i < n:
        take = pattern[p % len(pattern)]
        remaining = n - i
        if remaining - take == 1:  # keine 1-Panel-Restseite
            take += 1
        pages.append(panels[i:i + take])
        i += take
        p += 1
    return pages


# --------------------------------------------------------------------------
# Oeffentliche API
# --------------------------------------------------------------------------

def build_episode_manga(series: dict[str, Any], episode: dict[str, Any],
                        use_ai: bool = False) -> dict[str, Any] | None:
    """Baut die Folge als Manga-Kapitel. Gibt {pages, pdf, cbz} (Web-Pfade)."""
    panels = _build_panels(series, episode, use_ai)
    layout_pages = _paginate(panels)

    safe = "".join(c for c in series["id"] if c.isalnum() or c in "-_")
    out_dir = MANGA_DIR / safe / f"kap{episode.get('number', 1)}_{uuid.uuid4().hex[:6]}"
    out_dir.mkdir(parents=True, exist_ok=True)

    images: list[Image.Image] = [_cover_page(series, episode)]
    for idx, page_panels in enumerate(layout_pages, start=1):
        images.append(_render_page(page_panels, idx))

    page_paths: list[str] = []
    files: list[Path] = []
    for i, im in enumerate(images):
        fn = out_dir / f"seite_{i:02d}.png"
        im.save(fn)
        files.append(fn)
        page_paths.append(f"/manga/{safe}/{out_dir.name}/{fn.name}")

    # PDF (alle Seiten)
    pdf_path = out_dir / "manga.pdf"
    images[0].save(pdf_path, "PDF", save_all=True,
                   append_images=images[1:], resolution=150.0)

    # CBZ (ZIP der PNGs)
    cbz_path = out_dir / "manga.cbz"
    with zipfile.ZipFile(cbz_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)

    base = f"/manga/{safe}/{out_dir.name}"
    return {
        "pages": page_paths,
        "pdf": f"{base}/manga.pdf",
        "cbz": f"{base}/manga.cbz",
    }
