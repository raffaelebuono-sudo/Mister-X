"""JARVIS – Hauptprogramm.

Ablauf:
  1. Whisper, Speaker, Tools, Claude und WebSocket-Server initialisieren
  2. Auf Wake-Phrase „Guten Morgen JARVIS" warten (State: SLEEPING)
  3. Begrüßen, Frage aufnehmen (LISTENING),
     an Claude schicken (THINKING), Antwort aussprechen (SPEAKING)
  4. Zurück zu Schritt 2

Der WebSocket-Server pusht jeden State-Wechsel an verbundene Clients
(Electron-Kugel, Web-Dashboard).
"""

from __future__ import annotations

import sys

from brain.claude_client import ClaudeClient
from brain.memory import Memory
from config import get_config
from dashboard.web_server.ws_server import WSServer
from events.bus import EventBus
from events.state import JarvisState
from tools.registry import ToolRegistry
from tools.task_manager import TaskManager
from voice.listener import Listener
from voice.speaker import Speaker
from voice.wake_word import WakeWordDetector


BANNER = r"""
   _   _   _   _    _   _____ _____
  | | / \ | |_| \  / | |_   _/ ____|
  | |/ _ \| '_|\ \/ /    | | \___ \
 _|  / ___ \ |  \  /    _| |_____)|
(__)/_/   \_\_|  \/    |_____|____/

       Phase 4 – Sprache + Gedächtnis + Tools + Kugel
"""


def main() -> int:
    print(BANNER)
    try:
        cfg = get_config()
    except RuntimeError as exc:
        print(f"Konfigurations-Fehler: {exc}")
        return 1

    listener = Listener()
    speaker = Speaker()
    memory = Memory(cfg.db_path)
    tasks = TaskManager(cfg.db_path)
    tools = ToolRegistry(tasks)
    brain = ClaudeClient(memory=memory, tools=tools)
    wake = WakeWordDetector(listener)

    bus = EventBus()
    ws = WSServer(bus, host=cfg.ws_host, port=cfg.ws_port)
    ws.start()

    print(f"[JARVIS] Bereit. Wartet auf Wake-Phrase: '{cfg.wake_phrase}'.")
    print("[JARVIS] Mit Strg+C beenden.")
    bus.set_state(JarvisState.SLEEPING)

    try:
        while True:
            bus.set_state(JarvisState.SLEEPING)
            wake.wait_for_wake(on_chunk=_log_chunk)
            print("[JARVIS] Wake-Phrase erkannt.")

            bus.set_state(JarvisState.SPEAKING, "Guten Morgen.")
            speaker.say("Guten Morgen. Wie kann ich helfen?")

            bus.set_state(JarvisState.LISTENING)
            command = listener.listen_and_transcribe(cfg.command_seconds).strip()
            if not command:
                bus.set_state(JarvisState.SPEAKING)
                speaker.say("Ich habe nichts gehört.")
                continue

            print(f"[Du] {command}")
            bus.set_state(JarvisState.THINKING)
            try:
                reply = brain.ask(command)
            except Exception as exc:
                print(f"[JARVIS] Claude-Fehler: {exc}")
                bus.set_state(JarvisState.ERROR, str(exc))
                speaker.say("Es gab ein Problem mit der Anfrage.")
                continue

            print(f"[JARVIS] {reply}")
            bus.set_state(JarvisState.SPEAKING, reply)
            speaker.say(reply)
            bus.set_state(JarvisState.SUCCESS)
    except KeyboardInterrupt:
        print("\n[JARVIS] Bis später.")
        return 0
    finally:
        ws.stop()
        brain.close()
        tasks.close()


def _log_chunk(text: str) -> None:
    if text:
        print(f"  ... gehört: {text!r}")


if __name__ == "__main__":
    sys.exit(main())
