#!/usr/bin/env python3
"""2D-Animations-Engine – animierte Puppen-Figuren.

Das Herzstück des Serien-Generators: Figuren werden NICHT als Standbild
gezeichnet, sondern aus einzelnen Körperteilen (Kopf, Augen, Mund, Rumpf,
Arme, Beine) zu jedem Zeitpunkt neu posiert. Dadurch entsteht echte
Bewegung:

  • Lauf-Zyklus      (Beine + Arme schwingen, Körper wippt)
  • Idle-Atmung      (leichtes Auf-/Ab-Wippen im Stehen)
  • Blinzeln         (Augenlider schließen sich periodisch)
  • Gesten           (Arme heben sich beim Sprechen)
  • Lippen-Sync      (Mund öffnet sich nach Audio-Lautstärke)

Die Engine ist rein prozedural (Pillow + numpy), läuft offline und hält
die Figuren über die ganze Folge konsistent.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from PIL import Image, ImageDraw


# =========================================================================
#  Farben / Hilfen
# =========================================================================
def hex_to_rgb(color: str, default=(120, 160, 220)) -> tuple[int, int, int]:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", (color or "").strip())
    if not m:
        return default
    h = m.group(1)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _shade(c: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(v * factor))) for v in c)


# =========================================================================
#  Figur (Puppe)
# =========================================================================
@dataclass
class Character:
    """Eine animierbare 2D-Figur mit eigenem Aussehen."""
    name: str
    body_color: tuple[int, int, int] = (239, 83, 80)
    skin_color: tuple[int, int, int] = (255, 224, 189)
    scale: float = 1.0                 # Größe relativ zur Bildhöhe
    voice: str | None = None           # ElevenLabs-Voice-ID / macOS-Stimme
    # interner, deterministischer Phasen-Versatz für lebendige Vielfalt
    phase: float = 0.0

    @classmethod
    def from_spec(cls, spec: dict, index: int) -> "Character":
        palette = [
            "#ef5350", "#42a5f5", "#66bb6a", "# ab47bc".replace(" ", ""),
            "#ffa726", "#26c6da", "#ec407a", "#8d6e63",
        ]
        color = spec.get("color") or palette[index % len(palette)]
        return cls(
            name=str(spec.get("name", f"Figur {index+1}")).strip(),
            body_color=hex_to_rgb(color),
            scale=float(spec.get("scale", 1.0)),
            voice=spec.get("voice"),
            phase=(index * 1.7) % (2 * math.pi),
        )


@dataclass
class Pose:
    """Zustand einer Figur zu einem Zeitpunkt (wird je Frame berechnet)."""
    x: float                 # Fuß-Mittelpunkt X (Pixel)
    ground_y: float          # Boden-Linie Y (Pixel), Füße stehen hier
    facing: int = 1          # 1 = nach rechts, -1 = nach links
    walk_phase: float = 0.0  # 0..2π Lauf-Zyklus
    bob: float = 0.0         # vertikaler Wipp-Versatz
    mouth_open: float = 0.0  # 0 (zu) .. 1 (offen)  -> Lippen-Sync
    eye_open: float = 1.0    # 0 (zu) .. 1 (offen)  -> Blinzeln
    arm_raise: float = 0.0   # 0 (unten) .. 1 (Geste/erhoben)
    walking: bool = False


def draw_character(draw: ImageDraw.ImageDraw, ch: Character, pose: Pose,
                   frame_h: int) -> None:
    """Zeichnet die Figur in der gegebenen Pose auf das ImageDraw."""
    # Grundmaße aus Bildhöhe abgeleitet, damit alles mitskaliert
    unit = frame_h * 0.0016 * ch.scale * 100 / 100  # ~Pixel pro "Einheit"
    H = frame_h * 0.32 * ch.scale                    # Gesamthöhe der Figur
    cx = pose.x
    feet = pose.ground_y - pose.bob

    leg_len = H * 0.34
    torso_h = H * 0.34
    torso_w = H * 0.26
    head_r = H * 0.17

    hip_y = feet - leg_len
    shoulder_y = hip_y - torso_h
    head_cy = shoulder_y - head_r * 0.9

    body = ch.body_color
    body_dark = _shade(body, 0.78)

    # --- Beine (Lauf-Zyklus) ---
    swing = math.sin(pose.walk_phase) * (H * 0.16 if pose.walking else 0.0)
    swing2 = math.sin(pose.walk_phase + math.pi) * (H * 0.16 if pose.walking else 0.0)
    leg_w = max(3, int(torso_w * 0.30))
    for dx, sw in ((-torso_w * 0.28, swing), (torso_w * 0.28, swing2)):
        foot_x = cx + dx + sw
        lift = max(0.0, math.sin(pose.walk_phase + (0 if sw is swing else math.pi)))
        foot_y = feet - (H * 0.06 * lift if pose.walking else 0)
        draw.line([(cx + dx, hip_y), (foot_x, foot_y)], fill=body_dark, width=leg_w)
        # Fuß (Zehen zeigen in Blickrichtung; Koordinaten sortiert)
        toe = leg_w * 1.4 * pose.facing
        fx0, fx1 = sorted((foot_x - leg_w, foot_x + toe))
        draw.ellipse([fx0, foot_y - leg_w * 0.5, fx1, foot_y + leg_w * 0.5],
                     fill=_shade(body, 0.6))

    # --- Rumpf ---
    draw.rounded_rectangle(
        [cx - torso_w / 2, shoulder_y, cx + torso_w / 2, hip_y + 2],
        radius=torso_w * 0.4, fill=body)

    # --- Arme (Gegenschwung + Gesten-Anhebung) ---
    arm_w = max(3, int(torso_w * 0.26))
    arm_len = H * 0.30
    raise_a = pose.arm_raise * (math.pi * 0.22)
    for side, base_swing in ((-1, swing2), (1, swing)):
        sx = cx + side * torso_w * 0.5
        # Schwung im Gehen, sonst leichtes Wippen; plus Gesten-Anheben
        ang = (base_swing / (H + 1e-6)) * 2.2 if pose.walking else math.sin(
            pose.walk_phase * 0.5) * 0.12
        ang_total = ang - raise_a * side * 0.0 + raise_a
        hx = sx + math.sin(ang_total) * arm_len * side
        hy = shoulder_y + math.cos(ang_total) * arm_len - raise_a * arm_len * 0.6
        draw.line([(sx, shoulder_y + arm_w), (hx, hy)], fill=body_dark, width=arm_w)
        draw.ellipse([hx - arm_w * 0.7, hy - arm_w * 0.7,
                      hx + arm_w * 0.7, hy + arm_w * 0.7], fill=ch.skin_color)

    # --- Kopf ---
    draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r],
                 fill=ch.skin_color, outline=_shade(ch.skin_color, 0.8), width=2)

    # --- Augen (mit Blinzeln) ---
    eye_dx = head_r * 0.42
    eye_dy = -head_r * 0.12
    eye_r = max(2, head_r * 0.16)
    for ex in (-eye_dx, eye_dx):
        ecx = cx + ex + pose.facing * head_r * 0.12
        ecy = head_cy + eye_dy
        # Weißes Auge
        draw.ellipse([ecx - eye_r, ecy - eye_r, ecx + eye_r, ecy + eye_r],
                     fill=(255, 255, 255), outline=(40, 40, 40))
        # Pupille
        pr = eye_r * 0.55
        draw.ellipse([ecx - pr + pose.facing * pr * 0.4, ecy - pr,
                      ecx + pr + pose.facing * pr * 0.4, ecy + pr], fill=(30, 30, 30))
        # Lid (Blinzeln): deckt Auge je nach eye_open ab
        lid = (1.0 - pose.eye_open)
        if lid > 0.02:
            draw.rectangle([ecx - eye_r - 1, ecy - eye_r - 1,
                            ecx + eye_r + 1, ecy - eye_r + 2 * eye_r * lid],
                           fill=ch.skin_color)

    # --- Mund (Lippen-Sync) ---
    mouth_w = head_r * 0.7
    mouth_y = head_cy + head_r * 0.42
    open_h = max(1.5, head_r * 0.5 * pose.mouth_open)
    if pose.mouth_open < 0.12:
        # geschlossen: kurze Linie / leichtes Lächeln
        draw.arc([cx - mouth_w / 2, mouth_y - mouth_w * 0.3,
                  cx + mouth_w / 2, mouth_y + mouth_w * 0.3],
                 start=20, end=160, fill=(120, 40, 40), width=max(2, int(head_r * 0.08)))
    else:
        draw.ellipse([cx - mouth_w / 2, mouth_y - open_h / 2,
                      cx + mouth_w / 2, mouth_y + open_h / 2],
                     fill=(90, 30, 30))

    # --- Namensschild über dem Kopf (dezent) ---
    # (Untertitel/Sprecher werden separat eingeblendet; hier nichts.)


# =========================================================================
#  Hintergründe (pro Schauplatz, einmal gezeichnet, dann wiederverwendet)
# =========================================================================
_LOCATION_PRESETS = {
    "raumschiff": {"sky": ((10, 12, 40), (30, 20, 60)), "ground": (40, 44, 60),
                   "stars": True},
    "weltraum":   {"sky": ((5, 5, 25), (12, 10, 45)), "ground": (20, 22, 38),
                   "stars": True},
    "nacht":      {"sky": ((20, 24, 70), (60, 50, 110)), "ground": (30, 40, 35),
                   "stars": True},
    "wald":       {"sky": ((135, 206, 235), (200, 230, 255)), "ground": (60, 110, 50),
                   "stars": False},
    "stadt":      {"sky": ((150, 190, 230), (230, 230, 240)), "ground": (90, 95, 105),
                   "stars": False},
    "innen":      {"sky": ((210, 200, 185), (190, 175, 160)), "ground": (120, 95, 70),
                   "stars": False},
    "tag":        {"sky": ((135, 206, 250), (255, 235, 200)), "ground": (124, 179, 66),
                   "stars": False},
}


def _location_key(text: str) -> str:
    t = (text or "").lower()
    for key in _LOCATION_PRESETS:
        if key in t:
            return key
    if any(w in t for w in ("schiff", "brücke", "cockpit", "station", "deck")):
        return "raumschiff"
    if any(w in t for w in ("all", "space", "planet", "stern")):
        return "weltraum"
    if any(w in t for w in ("zimmer", "raum", "büro", "küche", "bar")):
        return "innen"
    return "tag"


def render_background(width: int, height: int, location: str, seed: int = 0) -> Image.Image:
    preset = _LOCATION_PRESETS[_location_key(location)]
    img = Image.new("RGB", (width, height), preset["sky"][1])
    draw = ImageDraw.Draw(img)
    horizon = int(height * 0.72)
    top, bot = preset["sky"]
    for y in range(horizon):
        t = y / max(1, horizon)
        col = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (width, y)], fill=col)
    draw.rectangle([0, horizon, width, height], fill=preset["ground"])
    # Boden-Schatten-Kante
    draw.line([(0, horizon), (width, horizon)], fill=_shade(preset["ground"], 1.3), width=2)

    if preset["stars"]:
        rng = _Rng(seed + 1)
        for _ in range(80):
            sx = rng.randint(0, width); sy = rng.randint(0, int(horizon * 0.9))
            r = rng.choice([1, 1, 2])
            draw.ellipse([sx, sy, sx + r, sy + r], fill=(255, 255, 255))
        # Planet
        pr = int(width * 0.08)
        draw.ellipse([width - pr * 3, int(height * 0.12), width - pr,
                      int(height * 0.12) + 2 * pr], fill=(120, 90, 200))
    else:
        # Sonne + Wolken
        draw.ellipse([int(width * 0.12), int(height * 0.10),
                      int(width * 0.12) + int(width * 0.10),
                      int(height * 0.10) + int(width * 0.10)], fill=(255, 241, 150))
        for k in range(3):
            wx = int(width * (0.45 + 0.18 * k)); wy = int(height * (0.16 + 0.05 * (k % 2)))
            for dx in (-40, 0, 40):
                draw.ellipse([wx + dx - 38, wy - 20, wx + dx + 38, wy + 22],
                             fill=(255, 255, 255))
    return img


class _Rng:
    """Winziger deterministischer RNG (kein globaler random-State)."""
    def __init__(self, seed: int):
        self.s = (seed * 2654435761 + 1) & 0xFFFFFFFF

    def _next(self) -> int:
        self.s = (1103515245 * self.s + 12345) & 0x7FFFFFFF
        return self.s

    def randint(self, a: int, b: int) -> int:
        return a + self._next() % max(1, (b - a + 1))

    def choice(self, seq):
        return seq[self._next() % len(seq)]
