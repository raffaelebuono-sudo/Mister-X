"""Claude-Anbindung – das Gehirn von JARVIS.

Nutzt die offizielle Anthropic-Bibliothek. Der System-Prompt wird per
Prompt-Caching übergeben, damit wiederholte Anfragen günstiger sind.
Vergangene Gespräche werden über `Memory` aus SQLite geladen, sodass
JARVIS sich an frühere Sitzungen erinnert (Phase 2).
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from anthropic import Anthropic
from anthropic.types import MessageParam

from brain.memory import Memory
from brain.system_prompt import SYSTEM_PROMPT
from config import get_config


class ClaudeClient:
    """Wrapper um die Anthropic-API mit persistentem Gedächtnis."""

    def __init__(self, memory: Memory | None = None) -> None:
        cfg = get_config()
        self._client = Anthropic(api_key=cfg.anthropic_api_key)
        self._model = cfg.claude_model
        self._max_tokens = cfg.claude_max_tokens
        self._memory = memory if memory is not None else Memory(cfg.db_path)
        self._memory_pairs = cfg.memory_pairs

    def ask(self, user_text: str) -> str:
        """Sendet `user_text` an Claude und liefert die Antwort als Text."""
        # Historie aus DB holen + die aktuelle Frage anhängen
        history: List[MessageParam] = self._memory.recent_messages(self._memory_pairs)
        history.append({"role": "user", "content": user_text})

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=[
                {
                    "type": "text",
                    "text": self._build_system_prompt(),
                    # Prompt-Caching spart Tokens bei jedem Folgegespräch
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=history,
        )

        reply = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

        # Erst nach erfolgreicher Antwort beide Seiten persistieren
        self._memory.add_user(user_text)
        self._memory.add_assistant(reply)
        return reply

    def _build_system_prompt(self) -> str:
        """Hängt aktuellen Zeitstempel an den statischen Prompt – hilft bei
        Fragen wie „Welcher Tag ist heute?".
        """
        now = datetime.now().strftime("%A, %d.%m.%Y, %H:%M")
        return f"{SYSTEM_PROMPT}\n\nAktuelle Zeit: {now}\n"

    def close(self) -> None:
        self._memory.close()
