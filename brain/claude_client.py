"""Claude-Anbindung – das Gehirn von JARVIS.

Nutzt die offizielle Anthropic-Bibliothek. Der System-Prompt wird per
Prompt-Caching übergeben, damit wiederholte Anfragen günstiger sind.
"""

from __future__ import annotations

from typing import List

from anthropic import Anthropic
from anthropic.types import MessageParam

from brain.system_prompt import SYSTEM_PROMPT
from config import get_config


class ClaudeClient:
    """Kleiner Wrapper um die Anthropic-API mit Gesprächs-Historie."""

    def __init__(self) -> None:
        cfg = get_config()
        self._client = Anthropic(api_key=cfg.anthropic_api_key)
        self._model = cfg.claude_model
        self._max_tokens = cfg.claude_max_tokens
        self._history: List[MessageParam] = []

    def ask(self, user_text: str) -> str:
        """Sendet `user_text` an Claude und liefert die Antwort als Text."""
        self._history.append({"role": "user", "content": user_text})

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    # Prompt-Caching spart Tokens bei jedem Folgegespräch
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=self._history,
        )

        # Antworttext aus den Content-Blöcken zusammenfügen
        reply_parts = [block.text for block in response.content if block.type == "text"]
        reply = "".join(reply_parts).strip()

        self._history.append({"role": "assistant", "content": reply})
        return reply

    def reset(self) -> None:
        """Setzt die Gesprächs-Historie zurück (z. B. neuer Tag)."""
        self._history.clear()
