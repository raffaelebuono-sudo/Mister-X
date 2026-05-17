"""Zentrale Tool-Registry für Claude-Tool-Use.

Wird vom `JarvisCore` mit einer Referenz auf sich selbst initialisiert,
damit Tool-Aufrufe (z. B. `add_task`) zugleich die UI über den Event-Bus
informieren können.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List

from tools import mac_control, system_inspect, system_monitor, web_search

if TYPE_CHECKING:  # nur für Type-Checker, keine Laufzeit-Abhängigkeit
    from core import JarvisCore


@dataclass(frozen=True)
class _Tool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    fn: Callable[..., str]


class ToolRegistry:
    def __init__(self, core: "JarvisCore") -> None:
        self._core = core
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
        core = self._core
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
                        "query": {"type": "string", "description": "Die Suchanfrage."},
                        "max_results": {
                            "type": "integer", "minimum": 1, "maximum": 10,
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
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
                fn=lambda name: mac_control.open_app(name),
            ),
            _Tool(
                name="open_url",
                description="Öffnet eine URL im Standard-Browser.",
                input_schema={
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
                fn=lambda url: mac_control.open_url(url),
            ),
            _Tool(
                name="open_file",
                description="Öffnet eine Datei mit der Standard-Anwendung.",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                fn=lambda path: mac_control.open_file(path),
            ),
            _Tool(
                name="add_task",
                description=(
                    "Legt eine Aufgabe oder Erinnerung an. Optional ein "
                    "Fälligkeitsdatum als ISO-String (z. B. 2026-05-12T18:00)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "due_at": {"type": "string"},
                    },
                    "required": ["title"],
                },
                fn=lambda title, due_at=None: core.add_task(title, due_at),
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
                fn=lambda limit=20: core.list_open_tasks(),
            ),
            _Tool(
                name="complete_task",
                description="Markiert eine Aufgabe per ID als erledigt.",
                input_schema={
                    "type": "object",
                    "properties": {"task_id": {"type": "integer"}},
                    "required": ["task_id"],
                },
                fn=lambda task_id: core.complete_task(int(task_id)),
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
            _Tool(
                name="top_processes",
                description=(
                    "Liefert die Top-Prozesse auf dem Mac nach CPU- oder "
                    "RAM-Verbrauch (read-only). Nutzbar für Security-Agenten "
                    "oder Performance-Diagnose."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                        "sort_by": {"type": "string", "enum": ["cpu", "ram"]},
                    },
                },
                fn=lambda limit=10, sort_by="cpu": system_inspect.top_processes(limit, sort_by),
            ),
            _Tool(
                name="network_connections",
                description=(
                    "Listet aktive ein- und ausgehende Netzwerkverbindungen "
                    "(welche Apps reden gerade mit welchen Servern). "
                    "Wichtig für Sicherheits-Audits."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    },
                },
                fn=lambda limit=15: system_inspect.network_connections(limit),
            ),
            _Tool(
                name="listening_ports",
                description=(
                    "Welche Programme lauschen auf welchen Ports. Wichtig "
                    "um zu erkennen, ob etwas Verdächtiges einen Port offen hat."
                ),
                input_schema={"type": "object", "properties": {}},
                fn=lambda: system_inspect.listening_ports(),
            ),
            _Tool(
                name="recent_logins",
                description=(
                    "Liefert die letzten Logins auf dem Mac (über 'last'). "
                    "Hilfreich für Security-Audits."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    },
                },
                fn=lambda limit=10: system_inspect.recent_logins(limit),
            ),
            _Tool(
                name="run_agent",
                description=(
                    "Startet einen Hintergrund-Agenten on-demand und liefert "
                    "sein Briefing zurück. Verfügbare Agenten: morning_briefing "
                    "(Tagesüberblick), news_watcher (aktuelle News), "
                    "note_taker (Fakten aus dem Verlauf extrahieren)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name des Agenten"},
                        "instruction": {
                            "type": "string",
                            "description": "Optionale spezifische Anweisung für den Agenten.",
                        },
                    },
                    "required": ["name"],
                },
                fn=lambda name, instruction="": core.run_agent(name, instruction),
            ),
            _Tool(
                name="list_briefings",
                description=(
                    "Listet die letzten Briefings, die JARVIS-Hintergrund-Agenten "
                    "erstellt haben (z. B. Morgenbriefing, News-Watcher). "
                    "Standardmäßig nur ungelesene."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "only_unread": {"type": "boolean"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    },
                },
                fn=lambda only_unread=True, limit=10: _format_briefings(
                    core.list_briefings(only_unread, limit)
                ),
            ),
            _Tool(
                name="remember",
                description=(
                    "Speichert einen dauerhaften Fakt über den Benutzer im "
                    "Langzeitgedächtnis. Nutze dies, wenn der Benutzer dir "
                    "etwas Persönliches mitteilt, das in Zukunft relevant "
                    "bleibt: Name, Wohnort, Vorlieben, Beziehungen, Projekte, "
                    "Routinen, Gesundheits-Infos. Kategorie wählen aus: "
                    "identitaet, vorlieben, beziehungen, projekte, routinen, "
                    "ziele, gesundheit, sonstiges."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Kurzer Satz mit dem Fakt.",
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "identitaet", "vorlieben", "beziehungen",
                                "projekte", "routinen", "ziele", "gesundheit",
                                "sonstiges",
                            ],
                        },
                    },
                    "required": ["content"],
                },
                fn=lambda content, category="sonstiges": core.remember_fact(
                    content, category,
                ),
            ),
            _Tool(
                name="list_facts",
                description=(
                    "Listet alle (oder einer Kategorie) Fakten, die JARVIS "
                    "über den Benutzer gespeichert hat."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Optional: nur diese Kategorie.",
                        },
                    },
                },
                fn=lambda category=None: core.list_facts(category),
            ),
            _Tool(
                name="forget_fact",
                description=(
                    "Löscht einen Fakt aus dem Langzeitgedächtnis. Entweder "
                    "nach exakter ID oder nach einem Stichwort im Inhalt."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "fact_id": {"type": "integer"},
                        "content_substr": {"type": "string"},
                    },
                },
                fn=lambda fact_id=None, content_substr=None: core.forget_fact(
                    fact_id, content_substr,
                ),
            ),
            _Tool(
                name="add_goal",
                description=(
                    "Setzt ein langfristiges Ziel, das JARVIS eigenständig "
                    "weiterverfolgt (anders als eine einmalige Aufgabe). "
                    "Nutze dies, wenn der Benutzer sagt 'behalte X im Auge', "
                    "'verfolge Y für mich', 'recherchiere nach und nach Z'."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Kurzer Ziel-Titel."},
                        "detail": {"type": "string", "description": "Optional: Details/Kontext."},
                    },
                    "required": ["title"],
                },
                fn=lambda title, detail="": core.add_goal(title, detail, "user"),
            ),
            _Tool(
                name="list_goals",
                description="Listet die aktiven, eigenständig verfolgten Ziele.",
                input_schema={"type": "object", "properties": {}},
                fn=lambda: core.list_goals(),
            ),
            _Tool(
                name="complete_goal",
                description="Markiert ein eigenständig verfolgtes Ziel als erledigt.",
                input_schema={
                    "type": "object",
                    "properties": {"goal_id": {"type": "integer"}},
                    "required": ["goal_id"],
                },
                fn=lambda goal_id: core.complete_goal(int(goal_id)),
            ),
            _Tool(
                name="computer_use",
                description=(
                    "Steuert den Mac direkt, um eine Aufgabe auszuführen "
                    "(öffnet Apps, klickt, tippt, scrollt). Verwende dieses "
                    "Tool, wenn der Benutzer eine konkrete Aktion auf seinem "
                    "Mac ausgeführt haben will. Beispiele: "
                    "'Öffne Safari und suche Pizza in Wien', "
                    "'Erstelle eine neue Notiz', 'Spiele in Spotify Lo-Fi'. "
                    "Gib die Aufgabe in einem klaren Satz an. Kostet pro "
                    "Aufgabe einige Cent in Tokens und dauert 10-60 Sekunden."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "Klare Beschreibung der Aufgabe in einem Satz.",
                        },
                    },
                    "required": ["task"],
                },
                fn=lambda task: core.run_computer_task(task),
            ),
            _Tool(
                name="mark_briefings_read",
                description=(
                    "Markiert ein einzelnes Briefing oder alle als gelesen."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "briefing_id": {
                            "type": "integer",
                            "description": "ID eines Briefings; wenn weggelassen, alles als gelesen markieren.",
                        },
                    },
                },
                fn=lambda briefing_id=None: (
                    f"Briefing {briefing_id} als gelesen markiert."
                    if briefing_id is not None and core.mark_briefing_read(int(briefing_id))
                    else f"{core.mark_all_briefings_read()} Briefings als gelesen markiert."
                ),
            ),
        ]


def _format_briefings(items: list) -> str:
    if not items:
        return "Keine Briefings."
    lines = []
    for it in items:
        lines.append(
            f"#{it['id']} [{it['agent']}] {it['title']}\n  {it['content']}"
        )
    return "\n\n".join(lines)
