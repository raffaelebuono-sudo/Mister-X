"""Einheitlicher FastAPI-Server für JARVIS.

Vereint:
  - WebSocket-Endpoint `/ws` (gleiches Protokoll wie zuvor) für Kugel
    und Electron-Dashboard
  - REST-API (`/api/...`) für mobile Clients ohne WebSocket
  - Statisches Mobile-Frontend unter `/`

Läuft in einem eigenen Thread mit eigener asyncio-Schleife, damit der
Voice-Loop in `main.py` weiterhin synchron bleiben darf.
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dashboard.web_server.api import chat as chat_api
from dashboard.web_server.api import status as status_api
from dashboard.web_server.api import tasks as tasks_api

if TYPE_CHECKING:
    from core import JarvisCore


STATIC_DIR = Path(__file__).resolve().parent / "static"


class _WSWrapper:
    """Macht FastAPIs WebSocket bus-kompatibel (`.send(text)`)."""

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws

    async def send(self, text: str) -> None:
        await self._ws.send_text(text)


def _build_app(core: "JarvisCore") -> FastAPI:
    app = FastAPI(title="JARVIS", docs_url=None, redoc_url=None)

    app.include_router(chat_api.build_router(core))
    app.include_router(status_api.build_router(core))
    app.include_router(tasks_api.build_router(core))

    if STATIC_DIR.exists():
        app.mount(
            "/static",
            StaticFiles(directory=str(STATIC_DIR)),
            name="static",
        )

        @app.get("/")
        def index():
            return FileResponse(STATIC_DIR / "index.html")

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        client = _WSWrapper(websocket)
        core.bus.register(client)
        try:
            await client.send(json.dumps(core.bus.state_snapshot(), ensure_ascii=False))
            await client.send(json.dumps(
                {"type": "history", "messages": core.chat_history(50)},
                ensure_ascii=False,
            ))
            await client.send(json.dumps(
                {"type": "tasks", "tasks": core.open_tasks_data()},
                ensure_ascii=False,
            ))
            while True:
                raw = await websocket.receive_text()
                await _on_client_message(core, raw)
        except WebSocketDisconnect:
            pass
        finally:
            core.bus.unregister(client)

    return app


async def _on_client_message(core: "JarvisCore", raw: str) -> None:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return
    kind = msg.get("type")
    if kind == "chat":
        text = (msg.get("content") or "").strip()
        speak = bool(msg.get("speak", False))
        if text:
            asyncio.create_task(asyncio.to_thread(_safe_chat, core, text, speak))
    elif kind == "add_task":
        title = (msg.get("title") or "").strip()
        if title:
            await asyncio.to_thread(core.add_task, title, msg.get("due_at") or None)
    elif kind == "complete_task":
        tid = msg.get("task_id")
        if isinstance(tid, int):
            await asyncio.to_thread(core.complete_task, tid)
    elif kind == "request_history":
        core.bus.push_history(core.chat_history(50))
    elif kind == "request_tasks":
        core.bus.push_tasks(core.open_tasks_data())


def _safe_chat(core: "JarvisCore", text: str, speak: bool) -> None:
    try:
        core.process_text(text, speak=speak)
    except Exception as exc:
        print(f"[Web] Fehler bei process_text: {exc}")


class WebServer:
    """Startet die FastAPI-App in einem Hintergrund-Thread."""

    def __init__(
        self,
        core: "JarvisCore",
        host: str = "0.0.0.0",
        port: int = 8080,
    ) -> None:
        self._core = core
        self._host = host
        self._port = port
        self._thread: Optional[threading.Thread] = None
        self._server: Optional[uvicorn.Server] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="jarvis-web", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._core.bus.attach_loop(loop)
        app = _build_app(self._core)
        config = uvicorn.Config(
            app, host=self._host, port=self._port,
            log_level="warning", lifespan="off",
        )
        self._server = uvicorn.Server(config)
        print(f"[Web] http://{self._host}:{self._port}  (WS: /ws)")
        loop.run_until_complete(self._server.serve())
        loop.close()
