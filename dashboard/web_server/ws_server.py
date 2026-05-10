"""WebSocket-Server: bidirektionale Brücke zwischen Backend und UI.

Server -> Client (alle Nachrichten haben ein `type`-Feld):
  - state    : aktueller JARVIS-Zustand
  - chat     : neue Chat-Nachricht (role=user|assistant)
  - history  : initialer Verlauf beim Verbinden
  - tasks    : aktuelle offene Aufgaben
  - system   : System-Stats (CPU/RAM/...)

Client -> Server (Eingaben aus dem Dashboard):
  - chat            : { content, speak? }
  - add_task        : { title, due_at? }
  - complete_task   : { task_id }
  - request_history : (re-sendet history)
  - request_tasks   : (re-sendet tasks)
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Optional, Protocol

import websockets

from events.bus import EventBus


class _CoreLike(Protocol):
    bus: EventBus
    def process_text(self, text: str, *, speak: bool) -> str: ...
    def add_task(self, title: str, due_at: Optional[str] = ...) -> str: ...
    def complete_task(self, task_id: int) -> str: ...
    def chat_history(self, limit: int = ...) -> list: ...
    def open_tasks_data(self) -> list: ...


class WSServer:
    def __init__(self, core: _CoreLike, host: str = "127.0.0.1", port: int = 8765) -> None:
        self._core = core
        self._bus = core.bus
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

    async def _handler(self, ws) -> None:
        self._bus.register(ws)
        try:
            await self._initial_sync(ws)
            async for raw in ws:
                await self._on_client_message(raw)
        finally:
            self._bus.unregister(ws)

    async def _initial_sync(self, ws) -> None:
        await ws.send(json.dumps(self._bus.state_snapshot(), ensure_ascii=False))
        await ws.send(json.dumps(
            {"type": "history", "messages": self._core.chat_history(50)},
            ensure_ascii=False,
        ))
        await ws.send(json.dumps(
            {"type": "tasks", "tasks": self._core.open_tasks_data()},
            ensure_ascii=False,
        ))

    async def _on_client_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        kind = msg.get("type")
        # Schwere Operationen (Claude-Call) laufen in einem Worker-Thread,
        # damit der Event-Loop für andere Clients antwortbereit bleibt.
        if kind == "chat":
            text = (msg.get("content") or "").strip()
            speak = bool(msg.get("speak", False))
            if text:
                asyncio.create_task(asyncio.to_thread(self._safe_chat, text, speak))
        elif kind == "add_task":
            title = (msg.get("title") or "").strip()
            due_at = msg.get("due_at") or None
            if title:
                await asyncio.to_thread(self._core.add_task, title, due_at)
        elif kind == "complete_task":
            task_id = msg.get("task_id")
            if isinstance(task_id, int):
                await asyncio.to_thread(self._core.complete_task, task_id)
        elif kind == "request_history":
            self._bus.push_history(self._core.chat_history(50))
        elif kind == "request_tasks":
            self._bus.push_tasks(self._core.open_tasks_data())

    def _safe_chat(self, text: str, speak: bool) -> None:
        try:
            self._core.process_text(text, speak=speak)
        except Exception as exc:
            print(f"[WS] Fehler bei process_text: {exc}")
