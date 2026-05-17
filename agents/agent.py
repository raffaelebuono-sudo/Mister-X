"""Basis-Klasse für JARVIS-Hintergrund-Agenten.

Jeder Agent hat:
  - eigene Persönlichkeit (System-Prompt)
  - eigenen Claude-Client (kein gemeinsames Gedächtnis mit dem Haupt-JARVIS)
  - Zugriff auf alle Tools (Web-Suche, Aufgaben, System, ...) über die Registry
  - optional einen Zeitplan (cron-ähnlich)

Ergebnisse werden im `BriefingsStore` abgelegt, sodass JARVIS sie später
abrufen oder vorlesen kann.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from anthropic import Anthropic

if TYPE_CHECKING:
    from core import JarvisCore


MAX_TOOL_ITERATIONS = 8


@dataclass
class Agent:
    name: str
    description: str
    system_prompt: str
    # Beispiele für Schedules:
    #   {"hour": 7, "minute": 0}     – jeden Tag um 7:00
    #   {"interval_minutes": 240}    – alle 4 Stunden
    schedule: Optional[dict] = None
    default_instruction: str = ""
    use_tools: bool = True
    max_tokens: int = 1500
    title_template: str = "{name} – {timestamp}"
    _core: Optional["JarvisCore"] = field(default=None, repr=False, compare=False)

    def bind(self, core: "JarvisCore") -> "Agent":
        self._core = core
        return self

    def run(self, instruction: str = "") -> dict:
        """Führt den Agenten aus. Liefert das gespeicherte Briefing."""
        if self._core is None:
            raise RuntimeError("Agent ist nicht an einen JarvisCore gebunden.")

        cfg = self._core.cfg
        client = Anthropic(api_key=cfg.anthropic_api_key)
        prompt = (instruction or self.default_instruction or
                  "Erledige deine Aufgabe entsprechend deiner Rolle.")

        # Echte Uhrzeit verbindlich injizieren – sonst raten Agenten
        # das Datum ("springt von Tag zu Tag").
        from datetime import datetime
        _wd = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
               "Freitag", "Samstag", "Sonntag"][datetime.now().weekday()]
        time_ctx = (
            "AKTUELLE ZEIT (verbindlich – nutze AUSSCHLIESSLICH diese als "
            f"'jetzt' und 'heute'): {_wd}, "
            f"{datetime.now().strftime('%d.%m.%Y, %H:%M')} Uhr. "
            "Erfinde KEIN anderes Datum und keine andere Uhrzeit. "
            "Jede Zeitangabe muss exakt hierauf basieren.\n\n"
        )
        system_prompt = time_ctx + self.system_prompt

        messages = [{"role": "user", "content": prompt}]
        tools_param = self._core.tools.schemas() if self.use_tools else []

        # Resilienz: Agenten-Calls über den HealthMonitor des Core,
        # damit Netzwerk-Hänger nicht den Scheduler-Thread töten.
        health = getattr(self._core, "health", None)

        for _ in range(MAX_TOOL_ITERATIONS):
            def _call():
                return client.messages.create(
                    model=cfg.claude_model,
                    max_tokens=self.max_tokens,
                    system=system_prompt,
                    tools=tools_param,
                    messages=messages,
                )
            if health is not None:
                response = health.resilient(
                    _call,
                    retries=cfg.api_retries,
                    base_delay=cfg.api_retry_base_delay,
                    label=f"Agent {self.name}",
                )
            else:
                response = _call()
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                out = self._core.tools.dispatch(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": out,
                })
            messages.append({"role": "user", "content": tool_results})

        # Finalen Text aus dem letzten Response holen
        text = "".join(
            b.text for b in response.content if b.type == "text"
        ).strip() or "(keine Ausgabe)"

        from datetime import datetime
        title = self.title_template.format(
            name=self.description or self.name,
            timestamp=datetime.now().strftime("%d.%m. %H:%M"),
            instruction=prompt[:60],
        )

        bid = self._core.briefings.add(self.name, title, text)
        return {"id": bid, "agent": self.name, "title": title, "content": text}
