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
from brain.system_prompt import SYSTEM_PROMPT
from config import get_config
from tools.registry import ToolRegistry


MAX_TOOL_ITERATIONS = 8


class ClaudeClient:
    def __init__(
        self,
        memory: Memory | None = None,
        tools: ToolRegistry | None = None,
    ) -> None:
        cfg = get_config()
        self._client = Anthropic(api_key=cfg.anthropic_api_key)
        self._model = cfg.claude_model
        self._max_tokens = cfg.claude_max_tokens
        self._memory = memory if memory is not None else Memory(cfg.db_path)
        self._memory_pairs = cfg.memory_pairs
        self._tools = tools

    def ask(self, user_text: str) -> str:
        history: List[MessageParam] = self._memory.recent_messages(self._memory_pairs)
        history.append({"role": "user", "content": user_text})

        for _ in range(MAX_TOOL_ITERATIONS):
            response = self._client.messages.create(
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
        now = datetime.now().strftime("%A, %d.%m.%Y, %H:%M")
        return f"{SYSTEM_PROMPT}\n\nAktuelle Zeit: {now}\n"

    def close(self) -> None:
        self._memory.close()
