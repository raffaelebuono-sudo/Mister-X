"""Claude-Anbindung – das Gehirn von JARVIS.

Phase 3: zusätzlich Tool-Use-Schleife.
JARVIS kann jetzt Web-Suche, macOS-Steuerung, Aufgaben und System-Monitor
über Claudes Tool-Use-Mechanismus aufrufen.

Persistiert wird in der DB nur der User-Text und der finale Assistenten-Text;
Zwischenschritte (tool_use / tool_result) werden nur innerhalb eines `ask()`
aufbewahrt und für die DB ignoriert, damit das Gedächtnis lesbar bleibt.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from anthropic import Anthropic
from anthropic.types import MessageParam

from brain.memory import Memory
from brain.profile import UserProfile
from brain.system_prompt import SYSTEM_PROMPT
from config import get_config
from tools.registry import ToolRegistry


MAX_TOOL_ITERATIONS = 8


class ClaudeClient:
    def __init__(
        self,
        memory: Memory | None = None,
        tools: ToolRegistry | None = None,
        profile: UserProfile | None = None,
    ) -> None:
        cfg = get_config()
        self._client = Anthropic(api_key=cfg.anthropic_api_key)
        self._model = cfg.claude_model
        self._thinking_enabled = cfg.thinking_enabled
        self._thinking_budget = cfg.thinking_budget
        # Bei aktivem Thinking muss max_tokens > budget_tokens sein.
        self._max_tokens = (
            max(cfg.claude_max_tokens, cfg.thinking_budget + 1024)
            if cfg.thinking_enabled else cfg.claude_max_tokens
        )
        self._memory = memory if memory is not None else Memory(cfg.db_path)
        self._memory_pairs = cfg.memory_pairs
        self._tools = tools
        self._profile = profile

    def ask(self, user_text: str) -> str:
        history: List[MessageParam] = self._memory.recent_messages(self._memory_pairs)
        history.append({"role": "user", "content": user_text})

        for _ in range(MAX_TOOL_ITERATIONS):
            kwargs = dict(
                model=self._model,
                max_tokens=self._max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": self._build_system_prompt(),
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=self._tools.schemas() if self._tools else [],
                messages=history,
            )
            if self._thinking_enabled:
                # Tiefere Lagebeurteilung vor der Antwort.
                kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": self._thinking_budget,
                }
            response = self._client.messages.create(**kwargs)

            # Assistenten-Antwort komplett (Text + Tool-Use-Blöcke) an die
            # Historie hängen, damit Claude sich auf eigene Tool-Aufrufe
            # beziehen kann.
            history.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break

            tool_results = self._run_tool_calls(response.content)
            history.append({"role": "user", "content": tool_results})
        else:
            # Tool-Schleife wurde nicht regulär verlassen – Notausgang.
            return ("Ich konnte die Anfrage nicht abschließen, "
                    "es gab zu viele Tool-Schritte.")

        reply = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

        self._memory.add_user(user_text)
        self._memory.add_assistant(reply)
        return reply

    def _run_tool_calls(self, blocks) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for block in blocks:
            if block.type != "tool_use":
                continue
            print(f"[Tool] {block.name}({block.input})")
            # Live-Event ans Dashboard (Brain-Activity-Feed)
            if self._tools is not None:
                try:
                    self._tools._core.bus.push_brain(
                        "tool", f"{block.name}({_short_args(block.input)})",
                    )
                except Exception:
                    pass
            output = (
                self._tools.dispatch(block.name, block.input)
                if self._tools
                else f"Tool {block.name} nicht verfügbar."
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                }
            )
        return results

    def _build_system_prompt(self) -> str:
        n = datetime.now()
        wd = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
              "Freitag", "Samstag", "Sonntag"][n.weekday()]
        time_ctx = (
            "AKTUELLE ZEIT (verbindlich – nutze AUSSCHLIESSLICH diese als "
            f"'jetzt' und 'heute'): {wd}, {n.strftime('%d.%m.%Y, %H:%M')} Uhr. "
            "Erfinde kein anderes Datum; jede Zeitangabe basiert exakt hierauf."
        )
        parts = [SYSTEM_PROMPT, f"\n{time_ctx}\n"]
        if self._profile is not None:
            profile_text = self._profile.to_prompt_text()
            if profile_text:
                parts.append("\n" + profile_text + "\n")
        return "\n".join(parts)

    def close(self) -> None:
        self._memory.close()


def _short_args(args: dict, max_len: int = 60) -> str:
    """Kurzfassung der Tool-Argumente für die Brain-Activity-Anzeige."""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        s = str(v).replace("\n", " ")
        if len(s) > max_len:
            s = s[:max_len] + "…"
        parts.append(f"{k}={s!r}")
    return ", ".join(parts)
