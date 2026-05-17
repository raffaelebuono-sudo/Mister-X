"""JarvisCore – zentraler Orchestrator.

Bündelt Memory, Brain, Sprachausgabe, Tools, Aufgaben, Event-Bus,
Hintergrund-Agenten und Scheduler hinter einer einfachen Fassade.
Voice-Loop und Dashboard rufen die gleichen Methoden auf, sodass
Tipp- und Sprach-Eingaben absolut gleichberechtigt sind.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import List, Optional

from agents.agent import Agent
from agents.builtin import DEFAULT_AGENTS
from agents.scheduler import Scheduler
from agents.goals import GoalStore
from agents.store import BriefingsStore
from brain.claude_client import ClaudeClient
from brain.cloud_fallback import CloudFallbackBrain
from brain.local_brain import LocalBrain
from brain.memory import Memory
from brain.profile import UserProfile
from config import Config
from events.bus import EventBus
from events.state import JarvisState
from tools.registry import ToolRegistry
from tools.task_manager import TaskManager
from voice.listener import Listener
from voice.speaker import Speaker
from health import HealthMonitor, OfflineError


class JarvisCore:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.bus = EventBus()
        self.health = HealthMonitor(self.bus)
        self.memory = Memory(cfg.db_path)
        self.tasks = TaskManager(cfg.db_path)
        self.briefings = BriefingsStore(cfg.db_path)
        self.profile = UserProfile(cfg.db_path)
        self.goals = GoalStore(cfg.db_path)

        # Registry erfährt den Core, damit Tool-Aufrufe (z. B. add_task,
        # run_agent, list_briefings) die Dashboards informieren können.
        self.tools = ToolRegistry(self)
        self.brain = ClaudeClient(
            memory=self.memory, tools=self.tools, profile=self.profile,
        )
        self.cloud_fallback = (
            CloudFallbackBrain(
                cfg.openai_api_key, cfg.openai_model,
                cfg.gemini_api_key, cfg.gemini_model,
            )
            if cfg.cloud_fallback_enabled else None
        )
        self.local_brain = (
            LocalBrain(cfg.local_brain_url, cfg.local_brain_model)
            if cfg.local_brain_enabled else None
        )
        self.listener = Listener()
        self.speaker = Speaker()
        self._lock = threading.Lock()
        # Lock-Screen: Voice-Loop wartet hierauf, Dashboard entsperrt es.
        self._unlock_event = threading.Event()

        # Agenten registrieren und Scheduler aufsetzen
        self._agents: dict[str, Agent] = {}
        for agent in DEFAULT_AGENTS:
            self.register_agent(agent)
        self.scheduler = Scheduler()
        self._setup_scheduler()

        # Computer-Use-Agent (lazy initialisiert, da pyautogui Permissions braucht)
        self._computer_agent = None

        # Welcome-Bookkeeping: Wann lief das letzte Begrüßungs-Briefing?
        self._last_welcome: Optional[datetime] = None
        self._welcome_cooldown = timedelta(minutes=cfg.welcome_cooldown_minutes)

        # Executive-Bookkeeping: Tagesbudget für autonome Aktionen.
        self._exec_budget_date: Optional[str] = None
        self._exec_actions_today: int = 0

        # Ops-Center-Bookkeeping
        self._started_at = datetime.now()
        self._weather: Optional[dict] = None
        self._stats_date: Optional[str] = None
        self._conversations_today: int = 0
        self._tasks_done_today: int = 0

    def _roll_stats_day(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        if self._stats_date != today:
            self._stats_date = today
            self._conversations_today = 0
            self._tasks_done_today = 0

    # --- Ops-Center-Daten ---

    def refresh_weather(self) -> Optional[dict]:
        from tools import weather as weather_mod
        w = weather_mod.get_weather(
            self.cfg.weather_lat, self.cfg.weather_lon, self.cfg.weather_city,
        )
        if w:
            self._weather = w
        return self._weather

    def weather_snapshot(self) -> Optional[dict]:
        return self._weather

    def agents_status(self) -> list:
        jobs = {j["name"]: j for j in self.scheduler.list_jobs()}
        out = []
        for name, agent in self._agents.items():
            job = jobs.get(name)
            last = job["last_run"] if job else None
            out.append({
                "name": name,
                "description": agent.description,
                "scheduled": agent.schedule is not None or name == "executive",
                "last_run": last.isoformat(timespec="seconds") if last else None,
            })
        return out

    def goals_data(self) -> list:
        return self.goals.active()

    def daily_stats(self) -> dict:
        self._roll_stats_day()
        up = datetime.now() - self._started_at
        h, rem = divmod(int(up.total_seconds()), 3600)
        m = rem // 60
        return {
            "conversations_today": self._conversations_today,
            "tasks_done_today": self._tasks_done_today,
            "briefings_unread": self.briefings.count_unread(),
            "goals_active": len(self.goals.active()),
            "uptime": f"{h}h {m}m",
        }

    def recent_news(self, limit: int = 8) -> list:
        """Schlagzeilen aus News-Agenten-Briefings für den Ticker."""
        items = self.briefings.recent(40)
        news_agents = ("news_watcher", "morning_briefing")
        out = []
        for b in items:
            if b["agent"] in news_agents:
                line = (b.get("content") or b.get("title") or "").strip()
                line = line.replace("\n", " ")
                if line:
                    out.append(line[:200])
            if len(out) >= limit:
                break
        return out

    # --- Anfragen verarbeiten ---

    def process_text(self, text: str, *, speak: bool) -> str:
        text = text.strip()
        if not text:
            return ""
        self._roll_stats_day()
        self._conversations_today += 1
        with self._lock:
            self.bus.push_chat("user", text)
            self.bus.push_brain("thinking", f"verarbeite: {text[:60]}")
            self.bus.set_state(JarvisState.THINKING)
            try:
                # Resilient: Retry mit Backoff, sauberes Degradieren offline.
                reply = self.health.resilient(
                    lambda: self.brain.ask(text),
                    retries=self.cfg.api_retries,
                    base_delay=self.cfg.api_retry_base_delay,
                    label="Claude-Anfrage",
                )
            except OfflineError:
                self.bus.push_brain("health", "Claude nicht erreichbar")
                # Fallback-Kette: Cloud-Anbieter → lokales Modell → aufgeben
                cloud_reply = self._try_cloud_fallback(text)
                if cloud_reply:
                    self.bus.push_brain(
                        "cloud_fallback", "Antwort vom Fallback-Anbieter")
                    reply = cloud_reply
                    self.bus.push_chat("assistant", reply)
                else:
                    local_reply = self._try_local_brain(text)
                    if local_reply:
                        self.bus.push_brain(
                            "local_brain",
                            "Antwort vom lokalen Modell (Offline-Modus)")
                        reply = local_reply
                        self.bus.push_chat("assistant", reply)
                    else:
                        self.bus.set_state(JarvisState.ERROR, "offline")
                        reply = ("Ich komme gerade weder an Claude noch an "
                                 "einen anderen Anbieter oder ein lokales "
                                 "Modell. Ich versuche es automatisch nochmal.")
                        self.bus.push_chat("assistant", reply)
                        if speak:
                            self.bus.set_state(JarvisState.SPEAKING, reply)
                            self.speaker.say(reply)
                        return reply
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

    def _try_cloud_fallback(self, text: str) -> Optional[str]:
        """Fallback auf OpenAI/Gemini, wenn Claude (Anthropic) ausfällt.

        Gleiche Qualitätsklasse wie Claude. Persistiert bei Erfolg selbst
        ins Gedächtnis, da der reguläre brain.ask()-Pfad übersprungen wurde.
        """
        if self.cloud_fallback is None or not self.cloud_fallback.is_configured():
            return None
        try:
            from brain.system_prompt import SYSTEM_PROMPT
            history = self.memory.recent_messages(self.cfg.memory_pairs)
            reply = self.cloud_fallback.ask(SYSTEM_PROMPT, history, text)
            if reply:
                self.memory.add_user(text)
                self.memory.add_assistant(reply)
                return reply
            return None
        except Exception as exc:
            print(f"[CloudFallback] fehlgeschlagen: {exc}")
            return None

    def _try_local_brain(self, text: str) -> Optional[str]:
        """Fallback auf das lokale Ollama-Modell, wenn die Cloud weg ist.

        Liefert die Antwort oder None, wenn kein lokales Modell verfügbar
        ist. Persistiert bei Erfolg selbst ins Gesprächs-Gedächtnis,
        da der reguläre brain.ask()-Pfad übersprungen wurde.
        """
        if self.local_brain is None:
            return None
        try:
            if not self.local_brain.is_available():
                return None
            from brain.system_prompt import SYSTEM_PROMPT
            history = self.memory.recent_messages(self.cfg.memory_pairs)
            reply = self.local_brain.ask(SYSTEM_PROMPT, history, text)
            if reply:
                self.memory.add_user(text)
                self.memory.add_assistant(reply)
                return reply
            return None
        except Exception as exc:
            print(f"[LocalBrain] Fallback fehlgeschlagen: {exc}")
            return None

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
        self._roll_stats_day()
        self._tasks_done_today += 1
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
        try:
            result = agent.run(instruction)
        except OfflineError:
            self.bus.push_brain("health", f"Agent {name}: offline")
            return ("Ich komme gerade nicht ins Internet, deshalb kann ich "
                    "diesen Bericht jetzt nicht erstellen. Ich versuche es "
                    "automatisch nochmal, sobald die Verbindung wieder steht.")
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

    # --- Welcome-Logik ---

    def should_welcome(self) -> bool:
        """True, wenn die letzte Begrüßung lang genug her ist (oder noch nie war)."""
        if self._last_welcome is None:
            return True
        return (datetime.now() - self._last_welcome) >= self._welcome_cooldown

    def mark_welcomed(self) -> None:
        self._last_welcome = datetime.now()

    # --- Lock-Screen ---

    def lock(self) -> None:
        """Sperrt JARVIS und sagt dem Dashboard, den Lock-Screen zu zeigen."""
        self._unlock_event.clear()
        self.bus.publish({"type": "locked"})

    def is_unlocked(self) -> bool:
        return self._unlock_event.is_set()

    def wait_for_unlock(self) -> None:
        """Blockiert, bis im Dashboard der korrekte Code eingegeben wurde."""
        self._unlock_event.wait()

    def verify_unlock(self, code: str) -> bool:
        """Vom WebSocket aufgerufen, wenn im Dashboard ein Code kommt."""
        if (code or "").strip() == self.cfg.activation_code:
            self._unlock_event.set()
            self.bus.publish({"type": "unlocked"})
            return True
        self.bus.publish({"type": "unlock_failed"})
        return False

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
        # Executive: eigenes Intervall mit hartem Tagesbudget.
        if self.cfg.executive_enabled:
            self.scheduler.add(
                name="executive",
                spec={"interval_minutes": int(self.cfg.executive_interval_hours * 60)},
                callback=self._run_executive,
            )

    def _exec_budget_ok(self) -> bool:
        today = datetime.now().strftime("%Y-%m-%d")
        if self._exec_budget_date != today:
            self._exec_budget_date = today
            self._exec_actions_today = 0
        return self._exec_actions_today < self.cfg.executive_daily_budget

    def _run_executive(self) -> None:
        """Eigenständiger Antrieb: entscheidet + tut die EINE beste Aktion."""
        if not self._exec_budget_ok():
            print("[Executive] Tagesbudget erschöpft – überspringe.")
            return
        agent = self._agents.get("executive")
        if agent is None:
            return
        context = self._executive_context()
        self.bus.push_brain("executive", "denkt nach …")
        try:
            result = agent.run(context)
        except Exception as exc:
            print(f"[Executive] Fehler: {exc}")
            self.bus.push_brain("error", f"Executive: {exc}")
            return
        text = (result.get("content") or "").strip()
        # 'PASS' = bewusst nichts getan; kein Briefing, kein Budgetverbrauch.
        if text.upper().startswith("PASS"):
            self.bus.push_brain("executive", "nichts Sinnvolles zu tun – pausiert")
            return
        self._exec_actions_today += 1
        self.bus.publish({
            "type": "briefing",
            "briefing": result,
            "unread_total": self.briefings.count_unread(),
        })
        self.bus.push_brain(
            "executive_done",
            f"Aktion {self._exec_actions_today}/{self.cfg.executive_daily_budget}: "
            f"{text[:80]}",
        )

    def _executive_context(self) -> str:
        """Baut den Entscheidungs-Kontext für den Executive-Agenten."""
        goals = self.goals.active()
        goals_txt = "\n".join(
            f"  - [{g['id']}] {g['title']}"
            + (f" – {g['detail']}" if g['detail'] else "")
            + (f" (zuletzt bearbeitet: {g['last_worked_at']})"
               if g['last_worked_at'] else " (noch nie bearbeitet)")
            for g in goals
        ) or "  (keine aktiven Ziele)"

        tasks = self.open_tasks_data()
        tasks_txt = "\n".join(
            f"  - {t['title']}" + (f" (fällig {t['due_at']})" if t['due_at'] else "")
            for t in tasks[:10]
        ) or "  (keine offenen Aufgaben)"

        facts = self.profile.all_facts()
        facts_txt = "\n".join(f"  - {f['content']}" for f in facts[:20]) \
            or "  (noch nichts über den Benutzer bekannt)"

        recent = self.briefings.recent(5)
        recent_txt = "\n".join(f"  - {b['title']}" for b in recent) \
            or "  (keine)"

        now = datetime.now().strftime("%A, %d.%m.%Y, %H:%M")
        return (
            f"Aktueller Kontext (Zeit: {now}).\n\n"
            f"AKTIVE ZIELE:\n{goals_txt}\n\n"
            f"OFFENE AUFGABEN:\n{tasks_txt}\n\n"
            f"WAS JARVIS ÜBER DEN BENUTZER WEISS:\n{facts_txt}\n\n"
            f"LETZTE BRIEFINGS:\n{recent_txt}\n\n"
            "Entscheide jetzt die EINE sinnvollste proaktive Handlung "
            "(oder 'PASS')."
        )

    # --- Ziele (Selbst-Steuerung) ---

    def add_goal(self, title: str, detail: str = "", source: str = "user") -> str:
        gid = self.goals.add(title, detail, source)
        if gid is None:
            return f"Dieses Ziel verfolge ich bereits: {title}"
        return f"Neues Ziel gesetzt ({gid}): {title}"

    def list_goals(self) -> str:
        goals = self.goals.active()
        if not goals:
            return "Ich verfolge aktuell keine eigenständigen Ziele."
        lines = ["Aktive Ziele:"]
        for g in goals:
            lines.append(f"  {g['id']}. {g['title']}"
                         + (f" – {g['detail']}" if g['detail'] else ""))
        return "\n".join(lines)

    def complete_goal(self, goal_id: int) -> str:
        return ("Ziel als erledigt markiert."
                if self.goals.complete(int(goal_id))
                else f"Kein aktives Ziel mit ID {goal_id}.")

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
        self.goals.close()
