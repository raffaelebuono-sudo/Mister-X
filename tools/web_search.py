"""Web-Suche über die Tavily-API.

Tavily liefert in einem einzigen API-Call kompakte, nach Relevanz
gewichtete Web-Snippets – ideal als Such-Tool für ein Sprachmodell.
"""

from __future__ import annotations

import os
from typing import List

import requests


TAVILY_URL = "https://api.tavily.com/search"


class WebSearchError(RuntimeError):
    """Fehler beim Aufruf der Web-Suche."""


def search(query: str, max_results: int = 5) -> str:
    """Sucht im Web und liefert eine kompakte Zusammenfassung als Text."""
    api_key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not api_key:
        raise WebSearchError(
            "TAVILY_API_KEY fehlt. In der .env-Datei eintragen, um die "
            "Web-Suche zu nutzen."
        )

    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max(1, min(max_results, 10)),
        "include_answer": True,
        "search_depth": "basic",
    }

    try:
        response = requests.post(TAVILY_URL, json=payload, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise WebSearchError(f"Tavily nicht erreichbar: {exc}") from exc

    data = response.json()
    return _format(data, query)


def _format(data: dict, query: str) -> str:
    parts: List[str] = [f"Suche: {query}"]
    answer = (data.get("answer") or "").strip()
    if answer:
        parts.append(f"Zusammenfassung: {answer}")

    results = data.get("results") or []
    for i, item in enumerate(results, start=1):
        title = (item.get("title") or "").strip()
        content = (item.get("content") or "").strip()
        url = (item.get("url") or "").strip()
        snippet = content[:240] + ("…" if len(content) > 240 else "")
        parts.append(f"{i}. {title}\n   {snippet}\n   Quelle: {url}")

    if len(parts) == 1:
        parts.append("Keine Ergebnisse.")
    return "\n\n".join(parts)
