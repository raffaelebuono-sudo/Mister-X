"""SQLite-basiertes Langzeit-Gedächtnis für JARVIS.

Speichert jedes Frage/Antwort-Paar dauerhaft und liefert die letzten
N Konversationen zurück, die der ClaudeClient als Kontext mitsendet.

Schema (eine Tabelle reicht):
    messages(id, ts, role, content)

`role` ist entweder 'user' oder 'assistant'. `ts` ist UTC-ISO8601.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from anthropic.types import MessageParam


SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT    NOT NULL,
    role    TEXT    NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_id ON messages(id);
"""


class Memory:
    """Persistentes Gesprächs-Gedächtnis."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        # check_same_thread=False: WebSocket-Server läuft in eigenem Thread.
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # --- Schreiben ---

    def add_user(self, content: str) -> None:
        self._insert("user", content)

    def add_assistant(self, content: str) -> None:
        self._insert("assistant", content)

    def _insert(self, role: str, content: str) -> None:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._conn.execute(
            "INSERT INTO messages (ts, role, content) VALUES (?, ?, ?)",
            (ts, role, content),
        )
        self._conn.commit()

    # --- Lesen ---

    def recent_messages(self, max_pairs: int = 20) -> List[MessageParam]:
        """Liefert die letzten `max_pairs` Q/A-Paare in chronologischer Reihenfolge.

        Wir holen `max_pairs * 2` Zeilen vom Ende und drehen sie um, damit die
        älteste zuerst kommt – Claude erwartet die Historie in Reihenfolge.
        """
        limit = max_pairs * 2
        cursor = self._conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        rows.reverse()
        return [{"role": role, "content": content} for role, content in rows]

    def recent_with_ts(self, limit: int = 50) -> List[dict]:
        """Wie `recent_messages`, aber inkl. Zeitstempel – für die UI."""
        cursor = self._conn.execute(
            "SELECT role, content, ts FROM messages ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        rows.reverse()
        return [
            {"role": role, "content": content, "ts": ts}
            for role, content, ts in rows
        ]

    def count(self) -> int:
        cursor = self._conn.execute("SELECT COUNT(*) FROM messages")
        (n,) = cursor.fetchone()
        return int(n)

    def close(self) -> None:
        self._conn.close()
