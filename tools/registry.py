"""Zentrale Tool-Registry für Claude-Tool-Use.

Bündelt alle JARVIS-Tools, liefert Anthropic-kompatible Schemas
(`schemas()`) und führt Tool-Aufrufe aus (`dispatch()`).

Ein neues Tool hinzufügen: Funktion oben implementieren, in `_TOOLS`
unten eintragen – fertig.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from tools import mac_control, system_monitor, web_search
from tools.task_manager import TaskManager


@dataclass(frozen=True)
class _Tool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    fn: Callable[..., str]


class ToolRegistry:
    def __init__(self, tasks: TaskManager) -> None:
        self._tasks = tasks
        self._tools: Dict[str, _Tool] = {t.name: t for t in self._build()}

    # --- Anthropic-Integration ---

    def schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in self._tools.values()
        ]

    def dispatch(self, name: str, arguments: Dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"Unbekanntes Tool: {name}"
        try:
            return tool.fn(**(arguments or {}))
        except TypeError as exc:
            return f"Falsche Argumente für {name}: {exc}"
        except Exception as exc:
            return f"Fehler in {name}: {exc}"

    # --- Tool-Definitionen ---

    def _build(self) -> List[_Tool]:
        return [
            _Tool(
                name="web_search",
                description=(
                    "Sucht im Web nach aktuellen Informationen, News, "
                    "Wetter, Sportergebnissen oder Wissensfragen, deren "
                    "Antwort sich häufig ändert. Nutzt Tavily."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Die Suchanfrage in natürlicher Sprache.",
                        },
                        "max_results": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "description": "Maximale Anzahl Ergebnisse (Standard 5).",
                        },
                    },
                    "required": ["query"],
                },
                fn=lambda query, max_results=5: web_search.search(query, max_results),
            ),
            _Tool(
                name="open_app",
                description="Öffnet eine macOS-App (z. B. Safari, Calendar, Mail).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "App-Name"},
                    },
                    "required": ["name"],
                },
                fn=lambda name: mac_control.open_app(name),
            ),
            _Tool(
                name="open_url",
                description="Öffnet eine URL im Standard-Browser.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL inklusive https://"},
                    },
                    "required": ["url"],
                },
                fn=lambda url: mac_control.open_url(url),
            ),
            _Tool(
                name="open_file",
                description="Öffnet eine Datei mit der Standard-Anwendung.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Pfad zur Datei"},
                    },
                    "required": ["path"],
                },
                fn=lambda path: mac_control.open_file(path),
            ),
            _Tool(
                name="add_task",
                description=(
                    "Legt eine Aufgabe oder Erinnerung an. Optional "
                    "ein Fälligkeitsdatum als ISO-String (z. B. "
                    "2026-05-12T18:00)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Worum geht es?"},
                        "due_at": {
                            "type": "string",
                            "description": "Optional: Fälligkeit als ISO-Datum/Zeit.",
                        },
                    },
                    "required": ["title"],
                },
                fn=lambda title, due_at=None: self._tasks.add(title, due_at),
            ),
            _Tool(
                name="list_tasks",
                description="Listet offene Aufgaben.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                },
                fn=lambda limit=20: self._tasks.list_open(limit),
            ),
            _Tool(
                name="complete_task",
                description="Markiert eine Aufgabe per ID als erledigt.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer", "description": "Aufgaben-ID"},
                    },
                    "required": ["task_id"],
                },
                fn=lambda task_id: self._tasks.complete(int(task_id)),
            ),
            _Tool(
                name="system_status",
                description=(
                    "Liefert den aktuellen Mac-Systemstatus: CPU, RAM, "
                    "Festplatte, Akku, Uptime."
                ),
                input_schema={"type": "object", "properties": {}},
                fn=lambda: system_monitor.get_status_text(),
            ),
        ]
