"""Thread-sicherer Event-Bus für JARVIS-Events.

Der Voice-Loop ist sync, der WebSocket-Server async in einem eigenen
Thread. Diese Klasse vermittelt zwischen beiden:

  - Sync-Aufrufer (`set_state`, `push_chat`, `publish` usw.) lösen
    einen Broadcast an alle WebSocket-Clients aus.
  - Snapshots werden beim Auslösen eingefroren, damit kurze Übergänge
    nicht überschrieben werden.

Protokoll-Konvention: jede Nachricht hat ein `type`-Feld
(`state`, `chat`, `tasks`, `history`, `system`).
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from events.state import JarvisState


class EventBus:
    def __init__(self) -> None:
        self._state: JarvisState = JarvisState.SLEEPING
        self._message: Optional[str] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._clients: Set = set()
        self._lock = threading.Lock()

    # --- Vom WebSocket-Server aufgerufen ---

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def register(self, client) -> None:
        self._clients.add(client)

    def unregister(self, client) -> None:
        self._clients.discard(client)

    def state_snapshot(self) -> Dict[str, Any]:
        return {"type": "state", "state": self._state.value, "message": self._message}

    # --- Sync-API für den Voice-Loop und den Core ---

    def publish(self, payload: Dict[str, Any]) -> None:
        """Generischer Broadcast eines bereits strukturierten Events."""
        text = json.dumps(payload, ensure_ascii=False)
        loop = self._loop
        if loop is None or not self._clients:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(text), loop)
        except RuntimeError:
            # Loop läuft nicht mehr – Voice-Loop nicht hart fail lassen.
            pass

    def set_state(self, state: JarvisState, message: Optional[str] = None) -> None:
        with self._lock:
            self._state = state
            self._message = message
        self.publish({"type": "state", "state": state.value, "message": message})

    def push_chat(self, role: str, content: str) -> None:
        self.publish({
            "type": "chat",
            "role": role,
            "content": content,
            "ts": _now_iso(),
        })

    def push_tasks(self, tasks: List[dict]) -> None:
        self.publish({"type": "tasks", "tasks": tasks})

    def push_history(self, messages: List[dict]) -> None:
        self.publish({"type": "history", "messages": messages})

    def push_system(self, stats: Dict[str, Any]) -> None:
        self.publish({"type": "system", "stats": stats})

    def push_brain(self, kind: str, content: str = "", meta: Optional[dict] = None) -> None:
        """Live-Eintrag im 'Brain-Activity'-Feed des Dashboards.

        kind: z. B. 'tool', 'memory', 'agent', 'speech', 'thinking', 'computer'.
        content: kurze Beschreibung (eine Zeile).
        meta: optionale Zusatzdaten (z. B. Dauer, Token-Anzahl).
        """
        payload = {
            "type": "brain",
            "kind": kind,
            "content": content,
            "ts": _now_iso(),
        }
        if meta:
            payload["meta"] = meta
        self.publish(payload)

    def push_activate(self, source: str) -> None:
        """Signalisiert dem Dashboard, das Fenster nach vorne zu holen.

        source: 'wake_word' | 'clap'
        """
        self.publish({"type": "activate", "source": source, "ts": _now_iso()})

    # --- Intern ---

    async def _broadcast(self, text: str) -> None:
        dead = []
        for client in list(self._clients):
            try:
                await client.send(text)
            except Exception:
                dead.append(client)
        for c in dead:
            self.unregister(c)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
