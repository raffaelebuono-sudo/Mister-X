"""Thread-sicherer Event-Bus für JARVIS-Zustände.

Der Voice-Loop läuft synchron in `main.py`. Der WebSocket-Server läuft
in einem Hintergrund-Thread auf einer eigenen Asyncio-Schleife. Diese
Klasse vermittelt zwischen beiden:

  - `set_state()` ist sync und wird aus `main.py` aufgerufen.
  - Verbundene WebSocket-Clients bekommen jede Änderung als JSON.
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Optional, Set

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

    def snapshot(self) -> dict:
        return {"state": self._state.value, "message": self._message}

    # --- Vom Voice-Loop (sync) aufgerufen ---

    def set_state(self, state: JarvisState, message: Optional[str] = None) -> None:
        with self._lock:
            self._state = state
            self._message = message
        # Snapshot zum Auslöse-Zeitpunkt einfrieren, damit kurze
        # Übergänge (z. B. SUCCESS) nicht beim Broadcast überschrieben werden.
        payload = json.dumps({"state": state.value, "message": message})

        loop = self._loop
        if loop is None or not self._clients:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(payload), loop)
        except RuntimeError:
            # Loop läuft nicht mehr – ignorieren, kein Hard-Fail im Voice-Loop.
            pass

    # --- Intern ---

    async def _broadcast(self, payload: str) -> None:
        dead = []
        for client in list(self._clients):
            try:
                await client.send(payload)
            except Exception:
                dead.append(client)
        for c in dead:
            self.unregister(c)
