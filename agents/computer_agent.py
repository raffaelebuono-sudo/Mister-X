"""Computer-Use-Agent: lässt Claude den Mac direkt steuern.

Nutzt den Beta-Endpunkt `client.beta.messages.create` mit dem
`computer`-Tool. In jeder Iteration:
  1. Claude entscheidet eine Aktion (Screenshot, Klick, Tippen, ...).
  2. Wir führen sie auf dem Mac aus (`MacComputer`).
  3. Das Ergebnis (Bild oder Text) geht zurück an Claude.

Beendet wird, wenn Claude `stop_reason != 'tool_use'` setzt oder das
Schritte-Limit erreicht ist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from anthropic import Anthropic

from tools.computer_use import MacComputer

if TYPE_CHECKING:
    from core import JarvisCore


SYSTEM_PROMPT = """Du bist der Computer-Use-Agent für JARVIS. Du steuerst den Mac des Benutzers direkt: Klicks, Tastatur, Screenshots.

Ablauf:
1. Mach zuerst einen Screenshot, um zu sehen wo du bist.
2. Plane einen kleinen Schritt.
3. Führe ihn aus.
4. Mach einen neuen Screenshot, um das Ergebnis zu prüfen.
5. Wiederhole bis fertig.

Effizienz-Regeln:
- Nutze Tastenkürzel: Cmd+L für Browser-Adresszeile, Cmd+T neuer Tab, Cmd+Space für Spotlight, Cmd+Q zum Beenden.
- Spotlight (Cmd+Space) ist der schnellste Weg, Apps zu öffnen: 'safari'+Enter, 'mail'+Enter, ...
- Wenn du eine URL eingeben willst: erst Cmd+L, dann tippen, dann Enter.
- Bei Suchen: 'task in google' = Cmd+L, 'task in google'+Enter (Default-Suchmaschine).

Sicherheit:
- Mach NICHT etwas Destruktives (Datei löschen, Mail senden, Passwort eingeben), ohne dass es klar in der Anweisung steht.
- Wenn etwas nach 2 Versuchen nicht klappt: brich ab und erkläre kurz warum.
- Bei wichtigen Bestätigungs-Dialogen ('Wirklich löschen?'): NIE blind klicken, sondern abbrechen und nachfragen lassen.

Antwort-Format am Ende:
- Antworte auf Deutsch in 1-2 Sätzen, was du gemacht hast und was das Ergebnis ist.
"""


class ComputerAgent:
    """Eigenständiger Agent mit eigener Anthropic-Verbindung und Beta-Header."""

    def __init__(self, core: "JarvisCore") -> None:
        self._core = core
        self._client = Anthropic(api_key=core.cfg.anthropic_api_key)
        self._computer = MacComputer()

    def run(self, task: str, max_steps: int | None = None) -> str:
        cfg = self._core.cfg
        max_steps = max_steps or cfg.computer_use_max_steps

        messages: List[Dict[str, Any]] = [
            {"role": "user", "content": task},
        ]
        tool_def = {
            "type": cfg.computer_use_tool_type,
            "name": "computer",
            "display_width_px": self._computer.width,
            "display_height_px": self._computer.height,
            "display_number": 1,
        }

        last_response = None
        for step in range(max_steps):
            response = self._client.beta.messages.create(
                model=cfg.computer_use_model,
                max_tokens=cfg.computer_use_max_tokens,
                system=SYSTEM_PROMPT,
                tools=[tool_def],
                messages=messages,
                betas=[cfg.computer_use_beta],
            )
            last_response = response
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if block.type != "tool_use" or block.name != "computer":
                    continue
                result = self._dispatch(block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    **result,
                })
            messages.append({"role": "user", "content": tool_results})

        if last_response is None:
            return "Computer-Agent hat keinen Schritt ausgeführt."

        text = "".join(
            b.text for b in last_response.content if b.type == "text"
        ).strip()
        if not text:
            text = ("Aufgabe abgeschlossen."
                    if last_response.stop_reason != "tool_use"
                    else "Schritt-Limit erreicht ohne Abschluss.")
        return text

    # --- Aktion ausführen ---

    def _dispatch(self, action_input: Dict[str, Any]) -> Dict[str, Any]:
        action = action_input.get("action") or ""
        coord = action_input.get("coordinate")
        text = action_input.get("text")

        try:
            if action == "screenshot":
                img_b64 = self._computer.screenshot_b64()
                return {
                    "content": [{
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": img_b64,
                        },
                    }],
                }

            if action == "left_click" and coord:
                msg = self._computer.left_click(*coord)
            elif action == "right_click" and coord:
                msg = self._computer.right_click(*coord)
            elif action == "middle_click" and coord:
                msg = self._computer.middle_click(*coord)
            elif action == "double_click" and coord:
                msg = self._computer.double_click(*coord)
            elif action == "triple_click" and coord:
                msg = self._computer.triple_click(*coord)
            elif action == "mouse_move" and coord:
                msg = self._computer.mouse_move(*coord)
            elif action == "left_click_drag":
                start = action_input.get("start_coordinate")
                end = coord
                if not start or not end:
                    raise ValueError("left_click_drag braucht start_coordinate und coordinate")
                msg = self._computer.left_click_drag(tuple(start), tuple(end))
            elif action == "type" and text is not None:
                msg = self._computer.type_text(text)
            elif action == "key" and text is not None:
                msg = self._computer.key(text)
            elif action == "scroll":
                direction = action_input.get("scroll_direction", "down")
                amount = int(action_input.get("scroll_amount", 3))
                if coord:
                    msg = self._computer.scroll(coord[0], coord[1], direction, amount)
                else:
                    cx, cy = self._computer.width // 2, self._computer.height // 2
                    msg = self._computer.scroll(cx, cy, direction, amount)
            elif action == "wait":
                duration = float(action_input.get("duration", 1.0))
                msg = self._computer.wait(duration)
            elif action == "cursor_position":
                msg = self._computer.cursor_position()
            else:
                msg = f"Unbekannte oder unvollständige Aktion: {action}"

            return {"content": [{"type": "text", "text": msg}]}

        except Exception as exc:
            return {
                "is_error": True,
                "content": [{"type": "text", "text": f"Aktion fehlgeschlagen: {exc}"}],
            }
