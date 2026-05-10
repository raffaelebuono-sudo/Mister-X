"""JarvisCore – zentraler Orchestrator.

Bündelt Memory, Brain, Sprachausgabe, Tools, Aufgaben und Event-Bus
hinter einer einfachen Fassade. Voice-Loop und Dashboard rufen die
gleichen Methoden auf, sodass Tipp- und Sprach-Eingaben absolut
gleichberechtigt sind.

Thread-Sicherheit: `process_text` ist serialisiert (ein Lock), damit
parallele Anfragen aus Voice-Loop und Dashboard nicht denselben
Claude-Call gleichzeitig auslösen.
"""

from __future__ import annotations

import threading
from typing import List, Optional

from brain.claude_client import ClaudeClient
from brain.memory import Memory
from config import Config
from events.bus import EventBus
from events.state import JarvisState
from tools.registry import ToolRegistry
from tools.task_manager import TaskManager
from voice.listener import Listener
from voice.speaker import Speaker


class JarvisCore:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.bus = EventBus()
        self.memory = Memory(cfg.db_path)
        self.tasks = TaskManager(cfg.db_path)
        # Registry erfährt den Core, damit Tool-Aufrufe (z. B. add_task)
        # die Dashboards informieren können.
        self.tools = ToolRegistry(self)
        self.brain = ClaudeClient(memory=self.memory, tools=self.tools)
        self.listener = Listener()
        self.speaker = Speaker()
        self._lock = threading.Lock()

    # --- Anfragen verarbeiten ---

    def process_text(self, text: str, *, speak: bool) -> str:
        """End-to-End-Verarbeitung einer Frage.

        Pusht Chat- und State-Events an alle verbundenen Clients.
        """
        text = text.strip()
        if not text:
            return ""
        with self._lock:
            self.bus.push_chat("user", text)
            self.bus.set_state(JarvisState.THINKING)
            try:
                reply = self.brain.ask(text)
            except Exception as exc:
                self.bus.set_state(JarvisState.ERROR, str(exc))
                raise
            self.bus.push_chat("assistant", reply)

        if speak:
            self.bus.set_state(JarvisState.SPEAKING, reply)
            self.speaker.say(reply)
        self.bus.set_state(JarvisState.SUCCESS)
        return reply

    # --- Aufgaben (mit Event-Push) ---

    def add_task(self, title: str, due_at: Optional[str] = None) -> str:
        result = self.tasks.add(title, due_at)
        self._publish_tasks()
        return result

    def complete_task(self, task_id: int) -> str:
        result = self.tasks.complete(task_id)
        self._publish_tasks()
        return result

    def list_open_tasks(self) -> str:
        return self.tasks.list_open()

    def open_tasks_data(self) -> List[dict]:
        rows = self.tasks._conn.execute(
            "SELECT id, title, due_at FROM tasks WHERE done = 0 "
            "ORDER BY due_at IS NULL, due_at ASC, id DESC LIMIT 100"
        ).fetchall()
        return [{"id": r[0], "title": r[1], "due_at": r[2]} for r in rows]

    def _publish_tasks(self) -> None:
        self.bus.publish({"type": "tasks", "tasks": self.open_tasks_data()})

    # --- Chat-Verlauf ---

    def chat_history(self, limit: int = 50) -> List[dict]:
        return self.memory.recent_with_ts(limit)

    # --- Lifecycle ---

    def shutdown(self) -> None:
        self.brain.close()
        self.tasks.close()
