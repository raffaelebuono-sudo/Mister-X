"""Aufgaben & Erinnerungen – persistent in der gleichen SQLite-DB.

Eine Aufgabe besteht aus Titel, optionalem Fälligkeitsdatum (ISO-String)
und Erledigt-Flag. Die Funktionen liefern menschenlesbare Strings zurück,
da sie direkt von Claude verwendet werden.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    due_at       TEXT,
    done         INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL,
    completed_at TEXT
);
"""


class TaskManager:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: WebSocket-Server läuft in eigenem Thread.
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # --- Schreiben ---

    def add(self, title: str, due_at: Optional[str] = None) -> str:
        title = title.strip()
        if not title:
            return "Titel der Aufgabe fehlt."
        now = _now()
        cursor = self._conn.execute(
            "INSERT INTO tasks (title, due_at, created_at) VALUES (?, ?, ?)",
            (title, due_at, now),
        )
        self._conn.commit()
        suffix = f" (fällig: {due_at})" if due_at else ""
        return f"Aufgabe gespeichert (ID {cursor.lastrowid}): {title}{suffix}"

    def complete(self, task_id: int) -> str:
        cursor = self._conn.execute(
            "UPDATE tasks SET done = 1, completed_at = ? WHERE id = ? AND done = 0",
            (_now(), task_id),
        )
        self._conn.commit()
        if cursor.rowcount == 0:
            return f"Keine offene Aufgabe mit ID {task_id} gefunden."
        return f"Aufgabe {task_id} erledigt."

    # --- Lesen ---

    def list_open(self, limit: int = 20) -> str:
        rows = self._conn.execute(
            "SELECT id, title, due_at FROM tasks "
            "WHERE done = 0 ORDER BY due_at IS NULL, due_at ASC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return _format_list("Offene Aufgaben", rows)

    def list_recent(self, limit: int = 20) -> str:
        rows = self._conn.execute(
            "SELECT id, title, due_at FROM tasks ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return _format_list("Letzte Aufgaben", rows)

    def close(self) -> None:
        self._conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _format_list(title: str, rows: List[tuple]) -> str:
    if not rows:
        return f"{title}: keine."
    lines = [f"{title}:"]
    for row in rows:
        task_id, t, due = row
        due_str = f" – fällig {due}" if due else ""
        lines.append(f"  {task_id}. {t}{due_str}")
    return "\n".join(lines)
