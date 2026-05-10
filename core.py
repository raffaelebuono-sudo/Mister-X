"""JarvisCore – zentraler Orchestrator.

Bündelt Memory, Brain, Sprachausgabe, Tools, Aufgaben, Event-Bus,
Hintergrund-Agenten und Scheduler hinter einer einfachen Fassade.
Voice-Loop und Dashboard rufen die gleichen Methoden auf, sodass
Tipp- und Sprach-Eingaben absolut gleichberechtigt sind.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import List, Optional

from agents.agent import Agent
from agents.builtin import DEFAULT_AGENTS
from agents.scheduler import Scheduler
from agents.store import BriefingsStore
from brain.claude_client import ClaudeClient
from brain.memory import Memory
from brain.profile import UserProfile
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
        self.briefings = BriefingsStore(cfg.db_path)
        self.profile = UserProfile(cfg.db_path)

        # Registry erfährt den Core, damit Tool-Aufrufe (z. B. add_task,
        # run_agent, list_briefings) die Dashboards informieren können.
        self.tools = ToolRegistry(self)
        self.brain = ClaudeClient(
            memory=self.memory, tools=self.tools, profile=self.profile,
        )
        self.listener = Listener()
        self.speaker = Speaker()
        self._lock = threading.Lock()

        # Agenten registrieren und Scheduler aufsetzen
        self._agents: dict[str, Agent] = {}
        for agent in DEFAULT_AGENTS:
            self.register_agent(agent)
        self.scheduler = Scheduler()
        self._setup_scheduler()

        # Computer-Use-Agent (lazy initialisiert, da pyautogui Permissions braucht)
        self._computer_agent = None

    # --- Anfragen verarbeiten ---

    def process_text(self, text: str, *, speak: bool) -> str:
        text = text.strip()
        if not text:
            return ""
        with self._lock:
            self.bus.push_chat("user", text)
            self.bus.push_brain("thinking", f"verarbeite: {text[:60]}")
            self.bus.set_state(JarvisState.THINKING)
            try:
                reply = self.brain.ask(text)
            except Exception as exc:
                self.bus.set_state(JarvisState.ERROR, str(exc))
                self.bus.push_brain("error", str(exc))
                raise
            self.bus.push_chat("assistant", reply)

        if speak:
            self.bus.set_state(JarvisState.SPEAKING, reply)
            # Dem Dashboard sagen, dass die Sprachausgabe startet
            # (Länge wird genutzt, um die Kugel-Pulsation zu timen).
            self.bus.push_brain("speech_start", reply,
                                meta={"chars": len(reply)})
            self.speaker.say(reply)
            self.bus.push_brain("speech_end", "")

        # Im Hintergrund Fakten über den Benutzer extrahieren (Haiku, billig).
        threading.Thread(
            target=self._extract_facts_async,
            args=(text, reply),
            daemon=True,
        ).start()
        return reply

    # --- Langzeitgedächtnis ---

    def remember_fact(self, content: str, category: str = "sonstiges") -> str:
        new_id = self.profile.add(content, category)
        if new_id is None:
            return f"War mir bereits bekannt: {content}"
        return f"Gemerkt ({category}, ID {new_id}): {content}"

    def list_facts(self, category: str | None = None) -> str:
        facts = (self.profile.by_category(category) if category
                 else self.profile.all_facts())
        if not facts:
            return "Ich habe noch nichts Persönliches über dich gespeichert."
        if category:
            lines = [f"  {f['id']}. {f['content']}" for f in facts]
            return f"Was ich über dich weiß ({category}):\n" + "\n".join(lines)
        # Nach Kategorie gruppiert
        from brain.profile import LABELS
        from itertools import groupby
        out = ["Was ich über dich weiß:"]
        for cat, group in groupby(facts, key=lambda f: f["category"]):
            out.append(f"\n{LABELS.get(cat, cat)}:")
            for f in group:
                out.append(f"  {f['id']}. {f['content']}")
        return "\n".join(out)

    def forget_fact(self, fact_id: int | None = None,
                    content_substr: str | None = None) -> str:
        if fact_id is not None:
            return ("Vergessen." if self.profile.remove(int(fact_id))
                    else f"Kein Fakt mit ID {fact_id} gefunden.")
        if content_substr:
            n = self.profile.remove_by_content(content_substr)
            return f"{n} passende Fakten vergessen."
        return "Bitte fact_id oder content_substr angeben."

    def _extract_facts_async(self, user_text: str, reply: str) -> None:
        """Lässt Haiku im Hintergrund neue Fakten aus dem Gespräch extrahieren."""
        import json
        import re
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=self.cfg.anthropic_api_key)
            extractor_prompt = (
                "Hier ein kurzer Gesprächsausschnitt:\n\n"
                f"Benutzer: {user_text}\n"
                f"JARVIS: {reply}\n\n"
                "Extrahiere NEUE, dauerhafte Fakten über den BENUTZER. "
                "Nur Sachen, die länger als einen Tag relevant bleiben: "
                "Name, Wohnort, Beruf, Vorlieben, Beziehungen, Routinen, "
                "Gesundheit, laufende Projekte, Ziele.\n\n"
                "NICHT extrahieren: temporäre Anfragen, einmalige Aktionen, "
                "Floskeln, Wetterfragen, JARVIS' eigene Antworten.\n\n"
                "Antworte als JSON-Array. Erlaubte Kategorien: identitaet, "
                "vorlieben, beziehungen, projekte, routinen, ziele, "
                "gesundheit, sonstiges. Format:\n"
                '[{"category": "...", "content": "Kurzer Fakt-Satz"}]\n\n'
                "Wenn nichts Neues: leeres Array []. Antworte NUR mit JSON, "
                "ohne Markdown, ohne Erklärung."
            )
            response = client.messages.create(
                model=self.cfg.profile_extractor_model,
                max_tokens=512,
                messages=[{"role": "user", "content": extractor_prompt}],
            )
            raw = "".join(
                b.text for b in response.content if b.type == "text"
            ).strip()
            # Falls Markdown-Code-Fences trotzdem drin sind, entfernen.
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            try:
                items = json.loads(raw)
            except json.JSONDecodeError:
                return
            if not isinstance(items, list):
                return
            added = 0
            for f in items:
                if not isinstance(f, dict):
                    continue
                content = (f.get("content") or "").strip()
                category = (f.get("category") or "sonstiges").strip()
                if content and self.profile.add(content, category) is not None:
                    added += 1
            if added:
                print(f"[Profile] {added} neue Fakt(en) über dich gespeichert.")
        except Exception:
            # Stilles Fail – Profile-Extraktion darf den Voice-Loop nie stören.
            pass

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

    # --- Agenten ---

    def register_agent(self, agent: Agent) -> None:
        self._agents[agent.name] = agent.bind(self)

    def list_agent_names(self) -> List[str]:
        return list(self._agents.keys())

    def run_agent(self, name: str, instruction: str = "") -> str:
        """Lässt einen Agenten laufen und liefert sein Ergebnis."""
        agent = self._agents.get(name)
        if agent is None:
            return f"Unbekannter Agent: {name}. Verfügbar: {', '.join(self._agents)}"
        result = agent.run(instruction)
        # Dashboard live informieren
        self.bus.publish({
            "type": "briefing",
            "briefing": result,
            "unread_total": self.briefings.count_unread(),
        })
        return result["content"]

    def list_briefings(self, only_unread: bool = True, limit: int = 10) -> List[dict]:
        return (self.briefings.unread(limit) if only_unread
                else self.briefings.recent(limit))

    def mark_briefing_read(self, briefing_id: int) -> bool:
        return self.briefings.mark_read(briefing_id)

    def mark_all_briefings_read(self) -> int:
        return self.briefings.mark_all_read()

    # --- Computer Use ---

    def run_computer_task(self, task: str) -> str:
        """Lässt Claude den Mac direkt steuern, um die Aufgabe auszuführen."""
        if self._computer_agent is None:
            from agents.computer_agent import ComputerAgent
            self._computer_agent = ComputerAgent(self)
        prev_state = self.bus._state
        self.bus.set_state(JarvisState.THINKING, f"Computer-Use: {task[:60]}")
        self.bus.push_brain("computer", f"steuert Mac: {task[:80]}")
        try:
            result = self._computer_agent.run(task)
        except Exception as exc:
            self.bus.set_state(JarvisState.ERROR, str(exc))
            self.bus.push_brain("error", f"Computer-Use: {exc}")
            return f"Computer-Use fehlgeschlagen: {exc}"
        finally:
            self.bus.set_state(prev_state)
        self.bus.push_brain("computer_done", result[:120])
        # Als Briefing ablegen, damit der Verlauf erhalten bleibt
        self.briefings.add(
            "computer_use", f"Mac-Aktion: {task[:60]}", result,
        )
        return result

    # --- Scheduler ---

    def _setup_scheduler(self) -> None:
        for agent in self._agents.values():
            if not agent.schedule:
                continue
            self.scheduler.add(
                name=agent.name,
                spec=agent.schedule,
                callback=lambda a=agent: self._scheduled_run(a),
            )

    def _scheduled_run(self, agent: Agent) -> None:
        print(f"[Scheduler] Starte Agent '{agent.name}' "
              f"({datetime.now():%H:%M:%S}).")
        self.bus.push_brain("agent", f"{agent.name} läuft")
        try:
            result = agent.run(agent.default_instruction)
            self.bus.publish({
                "type": "briefing",
                "briefing": result,
                "unread_total": self.briefings.count_unread(),
            })
            self.bus.push_brain("agent_done",
                                f"{agent.name}: {result.get('title', '')}")
        except Exception as exc:
            print(f"[Scheduler] {agent.name}: {exc}")
            self.bus.push_brain("error", f"Agent {agent.name}: {exc}")

    def start_scheduler(self) -> None:
        self.scheduler.start()

    # --- Lifecycle ---

    def shutdown(self) -> None:
        self.scheduler.stop()
        self.brain.close()
        self.tasks.close()
        self.briefings.close()
        self.profile.close()
