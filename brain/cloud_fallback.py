"""Multi-Cloud-Fallback-Gehirn.

Wenn Anthropic/Claude ausfällt (überlastet, Rate-Limit, Anbieter-
Störung), aber das Internet noch geht, antwortet JARVIS über einen
anderen Cloud-Anbieter auf vergleichbarem Qualitätsniveau:

  1. OpenAI  (gpt-4o / o-Modelle)   – wenn OPENAI_API_KEY gesetzt
  2. Google Gemini                  – wenn GEMINI_API_KEY gesetzt

Bewusst über `requests` direkt an die REST-APIs, ohne zusätzliche
SDKs. Kein Tool-Use – das bleibt dem Hauptgehirn (Claude) vorbehalten;
der Fallback ist für „weiterreden statt stumm sein" gedacht.
"""

from __future__ import annotations

from typing import List, Optional

import requests


class CloudFallbackBrain:
    def __init__(
        self,
        openai_key: Optional[str],
        openai_model: str,
        gemini_key: Optional[str],
        gemini_model: str,
    ) -> None:
        self._openai_key = openai_key
        self._openai_model = openai_model
        self._gemini_key = gemini_key
        self._gemini_model = gemini_model

    def is_configured(self) -> bool:
        return bool(self._openai_key or self._gemini_key)

    def ask(
        self,
        system: str,
        history: List[dict],
        user_text: str,
        timeout: float = 30.0,
    ) -> Optional[str]:
        """Versucht die konfigurierten Anbieter der Reihe nach.

        Liefert die erste erfolgreiche Antwort oder None.
        """
        if self._openai_key:
            try:
                return self._ask_openai(system, history, user_text, timeout)
            except Exception as exc:
                print(f"[CloudFallback] OpenAI fehlgeschlagen: {exc}")
        if self._gemini_key:
            try:
                return self._ask_gemini(system, history, user_text, timeout)
            except Exception as exc:
                print(f"[CloudFallback] Gemini fehlgeschlagen: {exc}")
        return None

    # --- OpenAI ---

    def _ask_openai(self, system, history, user_text, timeout) -> str:
        messages = [{"role": "system", "content": system}]
        for m in history:
            if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_text})

        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._openai_key}"},
            json={"model": self._openai_model, "messages": messages},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    # --- Google Gemini ---

    def _ask_gemini(self, system, history, user_text, timeout) -> str:
        # Gemini nutzt Rollen 'user' und 'model' (statt 'assistant').
        contents = []
        for m in history:
            role = m.get("role")
            content = m.get("content")
            if not isinstance(content, str):
                continue
            if role == "user":
                contents.append({"role": "user", "parts": [{"text": content}]})
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": content}]})
        contents.append({"role": "user", "parts": [{"text": user_text}]})

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._gemini_model}:generateContent?key={self._gemini_key}"
        )
        resp = requests.post(
            url,
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": contents,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
