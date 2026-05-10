"""JARVIS – Hauptprogramm.

Startet den `JarvisCore`, den WebSocket-Server für Kugel und Dashboard,
einen Hintergrund-Thread, der periodisch den System-Status pusht, und
den eigentlichen Voice-Loop.

Voice und Text (Dashboard) teilen sich denselben Core – eine getippte
Frage und eine gesprochene Frage gehen den gleichen Weg.
"""

from __future__ import annotations

import sys
import threading
import time

from config import get_config
from core import JarvisCore
from dashboard.web_server.ws_server import WSServer
from events.state import JarvisState
from tools import system_monitor
from voice.wake_word import WakeWordDetector


BANNER = r"""
   _   _   _   _    _   _____ _____
  | | / \ | |_| \  / | |_   _/ ____|
  | |/ _ \| '_|\ \/ /    | | \___ \
 _|  / ___ \ |  \  /    _| |_____)|
(__)/_/   \_\_|  \/    |_____|____/

       Phase 5 – Vollständiges Dashboard
"""

SYSTEM_STATS_INTERVAL = 2.0  # Sekunden zwischen System-Pushes


def main() -> int:
    print(BANNER)
    try:
        cfg = get_config()
    except RuntimeError as exc:
        print(f"Konfigurations-Fehler: {exc}")
        return 1

    core = JarvisCore(cfg)
    ws = WSServer(core, host=cfg.ws_host, port=cfg.ws_port)
    ws.start()

    stop_flag = threading.Event()
    monitor = threading.Thread(
        target=_system_monitor_loop, args=(core, stop_flag), daemon=True,
    )
    monitor.start()

    wake = WakeWordDetector(core.listener)

    print(f"[JARVIS] Bereit. Wartet auf Wake-Phrase: '{cfg.wake_phrase}'.")
    print("[JARVIS] Mit Strg+C beenden.")
    core.bus.set_state(JarvisState.SLEEPING)

    try:
        while True:
            core.bus.set_state(JarvisState.SLEEPING)
            wake.wait_for_wake(on_chunk=_log_chunk)
            print("[JARVIS] Wake-Phrase erkannt.")

            core.bus.set_state(JarvisState.SPEAKING, "Guten Morgen.")
            core.speaker.say("Guten Morgen. Wie kann ich helfen?")

            core.bus.set_state(JarvisState.LISTENING)
            command = core.listener.listen_and_transcribe(cfg.command_seconds).strip()
            if not command:
                core.bus.set_state(JarvisState.SPEAKING)
                core.speaker.say("Ich habe nichts gehört.")
                continue

            print(f"[Du] {command}")
            try:
                reply = core.process_text(command, speak=True)
            except Exception as exc:
                print(f"[JARVIS] Fehler: {exc}")
                core.speaker.say("Es gab ein Problem mit der Anfrage.")
                continue

            print(f"[JARVIS] {reply}")
    except KeyboardInterrupt:
        print("\n[JARVIS] Bis später.")
        return 0
    finally:
        stop_flag.set()
        ws.stop()
        core.shutdown()


def _system_monitor_loop(core: JarvisCore, stop_flag: threading.Event) -> None:
    """Pusht alle paar Sekunden den System-Status an verbundene Clients."""
    while not stop_flag.wait(SYSTEM_STATS_INTERVAL):
        try:
            core.bus.push_system(system_monitor.get_status())
        except Exception:
            # System-Monitor sollte den Voice-Loop nie hart fail lassen.
            pass


def _log_chunk(text: str) -> None:
    if text:
        print(f"  ... gehört: {text!r}")


if __name__ == "__main__":
    sys.exit(main())
