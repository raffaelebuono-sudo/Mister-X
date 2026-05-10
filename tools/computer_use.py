"""Direkte macOS-Steuerung für JARVIS (Computer Use).

Wrapper um `pyautogui` mit Retina-Skalierung: Wir melden Claude die
*logische* Bildschirmgröße, schicken Screenshots ebenfalls in dieser
Größe zurück und führen Klicks in logischen Koordinaten aus. Damit
passen Claudes Koordinaten und das, was tatsächlich auf dem Schirm
ist, zusammen.

Voraussetzungen auf macOS (einmalig im UI bestätigen):
  - Systemeinstellungen → Datenschutz → Bedienungshilfen → Terminal/Python
  - Systemeinstellungen → Datenschutz → Bildschirmaufnahme → Terminal/Python
"""

from __future__ import annotations

import base64
import io
import time
from typing import Tuple


class MacComputer:
    def __init__(self) -> None:
        # pyautogui erst hier importieren, damit Test-Setups ohne Display
        # nicht crashen.
        import pyautogui
        from PIL import Image
        self._pa = pyautogui
        self._Image = Image
        self._pa.PAUSE = 0.05         # Mini-Pause nach jeder Aktion
        self._pa.FAILSAFE = True      # Maus oben-links bricht alles ab
        self.width, self.height = self._pa.size()

    # --- Screenshot ---

    def screenshot_b64(self) -> str:
        img = self._pa.screenshot()
        # Auf Retina liefert macOS doppelte Auflösung – wir skalieren
        # zurück auf die logische Größe, die Claude kennt.
        if img.size != (self.width, self.height):
            img = img.resize((self.width, self.height), self._Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    # --- Maus ---

    def left_click(self, x: int, y: int) -> str:
        self._pa.click(x, y, button="left")
        return f"Klick links auf ({x}, {y})."

    def right_click(self, x: int, y: int) -> str:
        self._pa.click(x, y, button="right")
        return f"Klick rechts auf ({x}, {y})."

    def middle_click(self, x: int, y: int) -> str:
        self._pa.click(x, y, button="middle")
        return f"Mittelklick auf ({x}, {y})."

    def double_click(self, x: int, y: int) -> str:
        self._pa.doubleClick(x, y)
        return f"Doppelklick auf ({x}, {y})."

    def triple_click(self, x: int, y: int) -> str:
        self._pa.tripleClick(x, y)
        return f"Dreifachklick auf ({x}, {y})."

    def mouse_move(self, x: int, y: int) -> str:
        self._pa.moveTo(x, y, duration=0.1)
        return f"Maus auf ({x}, {y})."

    def left_click_drag(self, start: Tuple[int, int], end: Tuple[int, int]) -> str:
        self._pa.moveTo(start[0], start[1])
        self._pa.dragTo(end[0], end[1], duration=0.3, button="left")
        return f"Drag von {start} nach {end}."

    def cursor_position(self) -> str:
        x, y = self._pa.position()
        return f"Mausposition: ({x}, {y})"

    # --- Tastatur ---

    def type_text(self, text: str) -> str:
        # `typewrite` schreibt Klartext-ASCII; non-ASCII gehen via write.
        try:
            self._pa.typewrite(text, interval=0.02)
        except Exception:
            for ch in text:
                self._pa.write(ch)
        return f"Eingabe: {text!r}"

    def key(self, combo: str) -> str:
        # Beispiel: "cmd+l", "return", "cmd+shift+t"
        keys = [k.strip().lower() for k in combo.split("+") if k.strip()]
        # macOS: 'meta' / 'command' / 'cmd' bedeuten alle Cmd
        keys = ["command" if k in ("cmd", "meta") else k for k in keys]
        if len(keys) == 1:
            self._pa.press(keys[0])
        else:
            self._pa.hotkey(*keys)
        return f"Taste(n): {combo}"

    # --- Scroll & Wait ---

    def scroll(self, x: int, y: int, direction: str, amount: int) -> str:
        # Direction: 'up' | 'down' | 'left' | 'right'
        self._pa.moveTo(x, y, duration=0.1)
        delta = amount if direction in ("up", "right") else -amount
        if direction in ("left", "right"):
            self._pa.hscroll(delta)
        else:
            self._pa.scroll(delta)
        return f"Scrollen {direction} um {amount} bei ({x}, {y})."

    def wait(self, seconds: float) -> str:
        time.sleep(min(max(seconds, 0.0), 5.0))
        return f"Warte {seconds:.1f}s."
