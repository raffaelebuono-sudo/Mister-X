"""WebSocket-Server, der den aktuellen JARVIS-Zustand an alle Clients pusht.

Der Server läuft in einem eigenen Thread mit eigener asyncio-Schleife,
damit der Voice-Loop unverändert blockierend bleiben kann.

Protokoll:
  Server -> Client: {"state": "<state>", "message": "<optional>"}
  Beim Verbinden bekommt jeder Client direkt den aktuellen Zustand.
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Optional

import websockets

from events.bus import EventBus


class WSServer:
    def __init__(self, bus: EventBus, host: str = "127.0.0.1", port: int = 8765) -> None:
        self._bus = bus
        self._host = host
        self._port = port
        self._thread: Optional[threading.Thread] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="jarvis-ws", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)

    # --- intern ---

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._bus.attach_loop(self._loop)
        self._stop_event = asyncio.Event()
        try:
            self._loop.run_until_complete(self._serve())
        finally:
            self._loop.close()

    async def _serve(self) -> None:
        async with websockets.serve(self._handler, self._host, self._port):
            print(f"[WS] Server hört auf ws://{self._host}:{self._port}")
            await self._stop_event.wait()

    async def _handler(self, websocket) -> None:
        self._bus.register(websocket)
        try:
            await websocket.send(json.dumps(self._bus.snapshot()))
            async for _ in websocket:
                # Phase 4: nur Push vom Server – Client-Nachrichten ignorieren.
                pass
        finally:
            self._bus.unregister(websocket)
