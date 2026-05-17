"""Lokales Fallback-Gehirn über Ollama.

Wird nur benutzt, wenn die Cloud (Anthropic) nicht erreichbar ist –
dann antwortet JARVIS mit einem lokalen Modell weiter, statt stumm
zu bleiben. Qualität ist niedriger als Claude, dafür ohne Internet
und ohne Kosten.

Voraussetzung: Ollama läuft (https://ollama.com) und das konfigurierte
Modell ist gezogen, z. B.:  ollama pull llama3.2

Kein Tool-Use, keine Profil-Injektion-Komplexität – bewusst schlank,
weil kleine lokale Modelle damit ohnehin schlecht umgehen.
"""

from __future__ import annotations

from typing import List, Optional

import requests


class LocalBrain:
    def __init__(self, base_url: str, model: str) -> None:
        self._url = base_url.rstrip("/")
        self._model = model

    def is_available(self) -> bool:
        """True, wenn der Ollama-Server erreichbar ist."""
        try:
            r = requests.get(f"{self._url}/api/tags", timeout=2)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def ask(
        self,
        system: str,
        history: List[dict],
        user_text: str,
        timeout: float = 120.0,
    ) -> str:
        """Schickt System-Prompt + Verlauf + Frage an Ollama, liefert Antwort.

        `history`: Liste aus {"role": "user"|"assistant", "content": str}.
        """
        messages = [{"role": "system", "content": system}]
        for m in history:
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and isinstance(content, str):
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_text})

        resp = requests.post(
            f"{self._url}/api/chat",
            json={"model": self._model, "messages": messages, "stream": False},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return (data.get("message") or {}).get("content", "").strip()
