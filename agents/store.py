"""Persistente Briefings – Ergebnisse von Agenten-Läufen.

Schema:
    briefings(id, ts, agent, title, content, read)

Werte werden auf Deutsch und als Klartext gespeichert, damit JARVIS sie
direkt vorlesen kann.
"""

from __future__ import annotations

import sqlite3

from storage import open_db
from datetime import datetime, timezone
from pathlib import Path
from typing import List


SCHEMA = """
CREATE TABLE IF NOT EXISTS briefings (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT    NOT NULL,
    agent   TEXT    NOT NULL,
    title   TEXT    NOT NULL,
    content TEXT    NOT NULL,
    read    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_briefings_ts   ON briefings(ts DESC);
CREATE INDEX IF NOT EXISTS idx_briefings_read ON briefings(read);
"""


class BriefingsStore:
    def __init__(self, db_path: Path) -> None:
        self._conn = open_db(db_path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # --- Schreiben ---

    def add(self, agent: str, title: str, content: str) -> int:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cur = self._conn.execute(
            "INSERT INTO briefings (ts, agent, title, content) VALUES (?, ?, ?, ?)",
            (ts, agent, title, content),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def mark_read(self, briefing_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE briefings SET read = 1 WHERE id = ?", (briefing_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def mark_all_read(self) -> int:
        cur = self._conn.execute("UPDATE briefings SET read = 1 WHERE read = 0")
        self._conn.commit()
        return cur.rowcount

    # --- Lesen ---

    def unread(self, limit: int = 20) -> List[dict]:
        rows = self._conn.execute(
            "SELECT id, ts, agent, title, content FROM briefings "
            "WHERE read = 0 ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row(r) for r in rows]

    def recent(self, limit: int = 20) -> List[dict]:
        rows = self._conn.execute(
            "SELECT id, ts, agent, title, content FROM briefings "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row(r) for r in rows]

    def count_unread(self) -> int:
        (n,) = self._conn.execute(
            "SELECT COUNT(*) FROM briefings WHERE read = 0"
        ).fetchone()
        return int(n)

    def close(self) -> None:
        self._conn.close()


def _row(r) -> dict:
    return {"id": r[0], "ts": r[1], "agent": r[2], "title": r[3], "content": r[4]}
