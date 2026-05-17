"""JARVIS – Hauptprogramm.

Startet den `JarvisCore`, den FastAPI-Server (Kugel/Dashboard/iPhone),
einen Hintergrund-Thread, der periodisch den System-Status pusht, und
den eigentlichen Voice-Loop.

Voice und Text teilen sich denselben Core – getippte und gesprochene
Anfragen gehen den gleichen Weg.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

import logger as jarvis_logger
from config import get_config
from core import JarvisCore
from dashboard.web_server.server import WebServer
from events.state import JarvisState
from tools import system_monitor
from voice.wake_word import WakeWordDetector

PROJECT_ROOT = Path(__file__).resolve().parent
ORB_DIR = PROJECT_ROOT / "dashboard" / "mac_app"


BANNER = r"""
   _   _   _   _    _   _____ _____
  | | / \ | |_| \  / | |_   _/ ____|
  | |/ _ \| '_|\ \/ /    | | \___ \
 _|  / ___ \ |  \  /    _| |_____)|
(__)/_/   \_\_|  \/    |_____|____/

       Phase 7 – Sprache, Dashboard, iPhone, Autostart
"""

SYSTEM_STATS_INTERVAL = 2.0


def main() -> int:
    print(BANNER)
    log = jarvis_logger.setup()
    log.info("JARVIS startet …")

    try:
        cfg = get_config()
    except RuntimeError as exc:
        log.error("Konfigurations-Fehler: %s", exc)
        return 1

    try:
        core = JarvisCore(cfg)
    except Exception as exc:
        log.exception("Initialisierung von JarvisCore fehlgeschlagen: %s", exc)
        return 1

    web = WebServer(core, host=cfg.web_host, port=cfg.web_port)
    web.start()

    # Hintergrund-Agenten starten (Morning-Briefing, News-Watcher, ...)
    core.start_scheduler()
    log.info("Agenten-Scheduler läuft (%d Jobs).", len(core.scheduler.list_jobs()))

    # Schwebende Kugel automatisch mitstarten
    orb_proc = _start_orb(log) if cfg.auto_start_orb else None

    stop_flag = threading.Event()
    monitor = threading.Thread(
        target=_system_monitor_loop, args=(core, stop_flag), daemon=True,
    )
    monitor.start()

    wake = WakeWordDetector(core.listener)

    log.info("Bereit. Wake-Phrase: '%s'", cfg.wake_phrase)
    print(f"[JARVIS] Bereit. Wartet auf Wake-Phrase: '{cfg.wake_phrase}'.")
    print("[JARVIS] Mit Strg+C beenden.")
    core.bus.set_state(JarvisState.SLEEPING)

    try:
        while True:
            try:
                _voice_iteration(cfg, core, wake, log)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                # Eine fehlerhafte Iteration darf JARVIS nicht abstürzen lassen.
                log.exception("Fehler im Voice-Loop: %s", exc)
                core.bus.set_state(JarvisState.ERROR, str(exc))
    except KeyboardInterrupt:
        log.info("Beende JARVIS …")
        print("\n[JARVIS] Bis später.")
        return 0
    finally:
        stop_flag.set()
        _stop_orb(orb_proc, log)
        try: web.stop()
        except Exception: pass
        try: core.shutdown()
        except Exception: pass


def _voice_iteration(cfg, core: JarvisCore, wake: WakeWordDetector, log) -> None:
    """Eine Sitzung: einmal aufwecken, dann beliebig viele Folgefragen.

    Nach der Wake-Phrase bleibt JARVIS aktiv, bis er explizit verabschiedet
    wird ('tschüss', 'bis später', ...) oder das Programm beendet wird.
    Stille führt nicht zum Schlaf – er hört einfach weiter zu.
    """
    core.bus.set_state(JarvisState.SLEEPING)
    trigger = wake.wait_for_wake(on_chunk=_log_chunk)
    source = "clap" if trigger == "[clap]" else "wake_word"
    log.info("Aktivierung über %s.", source)

    # Dashboard sofort nach vorne holen
    core.bus.push_activate(source)

    # Beim "Online-Kommen" (Klatschen oder "Jarvis") ein Welcome-Briefing –
    # aber nur wenn die letzte Begrüßung lange genug her ist. Wenn du
    # gerade aktiv mit ihm redest, kommt nur ein kurzes "Ja?".
    if core.should_welcome():
        core.mark_welcomed()
        core.bus.set_state(JarvisState.THINKING, "Welcome-Briefing …")
        try:
            briefing_text = core.run_agent(
                "welcome_briefing",
                "Erstelle das Sofort-Briefing mit nur den neuen Informationen.",
            )
        except Exception as exc:
            log.exception("Welcome-Briefing fehlgeschlagen: %s", exc)
            briefing_text = "Ich bin da."
        core.bus.set_state(JarvisState.SPEAKING, briefing_text[:80])
        core.bus.push_brain("speech_start", briefing_text,
                            meta={"chars": len(briefing_text)})
        core.speaker.say(briefing_text)
        core.bus.push_brain("speech_end", "")
    else:
        core.bus.set_state(JarvisState.SPEAKING, "Ja?")
        core.speaker.say("Ja, wie kann ich helfen?")

    while True:
        core.bus.set_state(JarvisState.LISTENING)
        command = core.listener.listen_and_transcribe(cfg.command_seconds).strip()

        if not command:
            # Stille – einfach weiter zuhören, ohne aufzugeben.
            continue

        if _is_goodbye(command):
            log.info("Verabschiedung erkannt: %s", command)
            core.bus.set_state(JarvisState.SPEAKING)
            core.speaker.say("Bis später.")
            return

        log.info("Anfrage: %s", command)
        print(f"[Du] {command}")
        try:
            reply = core.process_text(command, speak=True)
            log.info("Antwort: %s", reply)
            print(f"[JARVIS] {reply}")
        except Exception as exc:
            log.exception("Verarbeitung fehlgeschlagen: %s", exc)
            core.bus.set_state(JarvisState.ERROR, str(exc))
            core.speaker.say("Es gab ein Problem mit der Anfrage.")


_GOODBYE_PHRASES = (
    "tschüss", "tschuess", "tschüß",
    "schlaf gut", "gute nacht",
    "bis später", "bis spaeter",
    "danke das wars", "danke das war's",
    "danke jarvis das wars", "danke jarvis das war's",
    "ende jarvis", "stopp jarvis", "stop jarvis", "ruhe jetzt",
)


def _is_goodbye(text: str) -> bool:
    t = text.lower().strip()
    return any(p in t for p in _GOODBYE_PHRASES)


def _system_monitor_loop(core: JarvisCore, stop_flag: threading.Event) -> None:
    log = jarvis_logger.get("monitor")
    while not stop_flag.wait(SYSTEM_STATS_INTERVAL):
        try:
            core.bus.push_system(system_monitor.get_status())
        except Exception as exc:
            # System-Monitor sollte den Voice-Loop nie hart fail lassen.
            log.warning("System-Monitor-Fehler: %s", exc)


def _log_chunk(text: str) -> None:
    if text:
        # Nur ausgeben, wenn überhaupt etwas verstanden wurde.
        print(f"  ... gehört: {text!r}")


def _start_orb(log) -> subprocess.Popen | None:
    """Startet die schwebende Kugel (Electron) als Hintergrundprozess.

    Wenn Electron oder die Abhängigkeiten fehlen, wird nur eine Warnung
    geloggt – JARVIS startet trotzdem.
    """
    electron = ORB_DIR / "node_modules" / ".bin" / "electron"
    if not electron.exists():
        log.warning(
            "Kugel nicht gestartet: Electron fehlt. "
            "Installation: cd dashboard/mac_app && npm install"
        )
        return None
    try:
        proc = subprocess.Popen(
            [str(electron), "."],
            cwd=str(ORB_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        log.info("Kugel gestartet (PID %d).", proc.pid)
        print("[Kugel] gestartet.")
        return proc
    except Exception as exc:
        log.warning("Kugel konnte nicht gestartet werden: %s", exc)
        return None


def _stop_orb(proc: subprocess.Popen | None, log) -> None:
    """Beendet die Kugel sauber, inklusive eventueller Kindprozesse."""
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        try: proc.kill()
        except Exception: pass
    log.info("Kugel beendet.")


if __name__ == "__main__":
    sys.exit(main())
