"""Langzeitgedächtnis: was JARVIS dauerhaft über den Benutzer weiß.

Anders als das Gesprächs-`Memory` (letzte 20 Q/A-Paare) speichert das
`UserProfile` strukturierte Fakten über den Benutzer (Name, Vorlieben,
Personen, Projekte, Pläne, Routinen). Diese werden bei JEDEM Gespräch
in den System-Prompt injiziert, sodass JARVIS sich "an alles erinnert",
auch über Sitzungen und Tage hinweg.

Schema (eine Tabelle in derselben SQLite-DB):
    profile_facts(id, category, content, added_at, last_referenced)
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS profile_facts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT    NOT NULL,
    content         TEXT    NOT NULL UNIQUE,
    added_at        TEXT    NOT NULL,
    last_referenced TEXT
);
CREATE INDEX IF NOT EXISTS idx_profile_category ON profile_facts(category);
"""

# Kategorien, die JARVIS verwenden darf. Andere werden als 'sonstiges'
# einsortiert.
CATEGORIES = (
    "identitaet",        # Name, Wohnort, Beruf, Alter
    "vorlieben",         # mag/mag nicht, Gewohnheiten
    "beziehungen",       # Familie, Freunde, Kollegen
    "projekte",          # laufende Arbeiten, Vorhaben
    "routinen",          # wiederkehrende Pläne, Schedule-Patterns
    "ziele",             # Wünsche, Pläne für die Zukunft
    "gesundheit",        # Allergien, Medikamente, Sport
    "sonstiges",
)

# Anzeige-Labels für den System-Prompt
LABELS = {
    "identitaet":  "Identität",
    "vorlieben":   "Vorlieben & Gewohnheiten",
    "beziehungen": "Beziehungen",
    "projekte":    "Projekte",
    "routinen":    "Routinen & Termine",
    "ziele":       "Ziele & Pläne",
    "gesundheit":  "Gesundheit",
    "sonstiges":   "Sonstiges",
}


class UserProfile:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # --- Schreiben ---

    def add(self, content: str, category: str = "sonstiges") -> Optional[int]:
        """Fügt einen Fakt hinzu. Liefert ID, oder None bei Duplikat."""
        content = content.strip()
        if not content:
            return None
        if category not in CATEGORIES:
            category = "sonstiges"
        try:
            cur = self._conn.execute(
                "INSERT INTO profile_facts (category, content, added_at) "
                "VALUES (?, ?, ?)",
                (category, content, _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            # Duplikat (UNIQUE constraint) – nur Zeitstempel aktualisieren.
            self._conn.execute(
                "UPDATE profile_facts SET last_referenced = ? WHERE content = ?",
                (_now(), content),
            )
            self._conn.commit()
            return None

    def remove(self, fact_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM profile_facts WHERE id = ?", (fact_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def remove_by_content(self, content_substr: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM profile_facts WHERE content LIKE ?",
            (f"%{content_substr}%",),
        )
        self._conn.commit()
        return cur.rowcount

    # --- Lesen ---

    def all_facts(self) -> List[dict]:
        rows = self._conn.execute(
            "SELECT id, category, content, added_at FROM profile_facts "
            "ORDER BY category, id"
        ).fetchall()
        return [
            {"id": r[0], "category": r[1], "content": r[2], "added_at": r[3]}
            for r in rows
        ]

    def by_category(self, category: str) -> List[dict]:
        rows = self._conn.execute(
            "SELECT id, content FROM profile_facts WHERE category = ? "
            "ORDER BY id",
            (category,),
        ).fetchall()
        return [{"id": r[0], "content": r[1]} for r in rows]

    def count(self) -> int:
        (n,) = self._conn.execute(
            "SELECT COUNT(*) FROM profile_facts"
        ).fetchone()
        return int(n)

    def to_prompt_text(self, max_facts_per_category: int = 30) -> str:
        """Erzeugt den Text-Block, der in den System-Prompt eingehängt wird."""
        if self.count() == 0:
            return ""
        lines = ["# Was du über den Benutzer weißt"]
        for cat in CATEGORIES:
            facts = self.by_category(cat)
            if not facts:
                continue
            lines.append(f"\n## {LABELS[cat]}")
            for f in facts[:max_facts_per_category]:
                lines.append(f"- {f['content']}")
        return "\n".join(lines)

    def close(self) -> None:
        self._conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
