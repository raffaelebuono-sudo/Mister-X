"""Thread-sichere gemeinsame SQLite-Schicht für alle JARVIS-Stores.

Mehrere Komponenten (Memory, Tasks, Profile, Briefings, Goals) greifen
aus verschiedenen Threads (Voice-Loop, WebSocket, Scheduler, Executive,
Fakten-Extraktion) auf dieselbe jarvis.db zu – teils gleichzeitig auf
DASSELBE Connection-Objekt. Das ist mit sqlite3 nicht sicher
(„database is locked", „cannot start a transaction within a
transaction").

Lösung:
  - WAL + busy_timeout (entspannt Leser/Schreiber auf Datei-Ebene),
  - ein PROZESSWEITER Lock, der jeden DB-Zugriff serialisiert.
Da alles eine einzige kleine DB-Datei ist und Operationen im
Millisekunden-Bereich liegen, ist die Serialisierung unkritisch und
beseitigt sämtliche Lock-/Transaktions-Races zuverlässig.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_GLOBAL_DB_LOCK = threading.RLock()


class _Result:
    """Vorab materialisiertes Ergebnis – sicher außerhalb des Locks nutzbar."""

    def __init__(self, rows, lastrowid, rowcount):
        self._rows = rows
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class LockedConnection:
    """Schlanke Hülle um sqlite3.Connection, die jeden Zugriff serialisiert."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, params=()) -> _Result:
        with _GLOBAL_DB_LOCK:
            cur = self._conn.execute(sql, params)
            rows = cur.fetchall() if cur.description else []
            res = _Result(rows, cur.lastrowid, cur.rowcount)
            # Schreibzugriffe sofort committen, damit kein offener
            # Transaktions-Zustand zwischen Threads geteilt wird.
            if cur.description is None:
                self._conn.commit()
            return res

    def executescript(self, script: str) -> None:
        with _GLOBAL_DB_LOCK:
            self._conn.executescript(script)
            self._conn.commit()

    def commit(self) -> None:
        with _GLOBAL_DB_LOCK:
            self._conn.commit()

    def close(self) -> None:
        with _GLOBAL_DB_LOCK:
            self._conn.close()


def open_db(db_path: Path) -> LockedConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(db_path), check_same_thread=False, timeout=30.0,
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.commit()
    return LockedConnection(conn)
