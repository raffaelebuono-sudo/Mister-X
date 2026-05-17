"""Ziele-Speicher: langfristige Vorhaben, die JARVIS eigenständig verfolgt.

Anders als 'tasks' (konkrete To-dos mit Fälligkeit) sind 'goals'
fortlaufende Missionen, an denen der Executive-Agent immer wieder
ein Stück weiterarbeitet, z. B.:
  - "Beobachte KI-News und fasse Wichtiges zusammen"
  - "Recherchiere nach und nach die besten E-Bike-Ladegeräte"
  - "Erinnere mich an Bewegung, wenn ich lange am Mac sitze"

Schema:
    goals(id, title, detail, status, source, created_at, last_worked_at)
"""

from __future__ import annotations

import sqlite3

from storage import open_db
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT    NOT NULL UNIQUE,
    detail        TEXT,
    status        TEXT    NOT NULL DEFAULT 'active',  -- active|paused|done
    source        TEXT    NOT NULL DEFAULT 'user',    -- user|executive
    created_at    TEXT    NOT NULL,
    last_worked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
"""


class GoalStore:
    def __init__(self, db_path: Path) -> None:
        self._conn = open_db(db_path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def add(self, title: str, detail: str = "", source: str = "user") -> Optional[int]:
        title = title.strip()
        if not title:
            return None
        try:
            cur = self._conn.execute(
                "INSERT INTO goals (title, detail, source, created_at) "
                "VALUES (?, ?, ?, ?)",
                (title, detail.strip(), source, _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None  # gibt es schon

    def complete(self, goal_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE goals SET status = 'done' WHERE id = ? AND status != 'done'",
            (goal_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def pause(self, goal_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE goals SET status = 'paused' WHERE id = ?", (goal_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def mark_worked(self, goal_id: int) -> None:
        self._conn.execute(
            "UPDATE goals SET last_worked_at = ? WHERE id = ?",
            (_now(), goal_id),
        )
        self._conn.commit()

    def active(self) -> List[dict]:
        rows = self._conn.execute(
            "SELECT id, title, detail, last_worked_at FROM goals "
            "WHERE status = 'active' ORDER BY last_worked_at IS NOT NULL, "
            "last_worked_at ASC, id ASC"
        ).fetchall()
        return [
            {"id": r[0], "title": r[1], "detail": r[2], "last_worked_at": r[3]}
            for r in rows
        ]

    def all(self) -> List[dict]:
        rows = self._conn.execute(
            "SELECT id, title, detail, status, source FROM goals ORDER BY id"
        ).fetchall()
        return [
            {"id": r[0], "title": r[1], "detail": r[2],
             "status": r[3], "source": r[4]}
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
