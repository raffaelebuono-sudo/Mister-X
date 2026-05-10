"""JARVIS – Hauptprogramm.

Ablauf:
  1. Whisper, Speaker, Tools und Claude initialisieren
  2. Auf Wake-Phrase „Guten Morgen JARVIS" warten
  3. Begrüßen, Frage aufnehmen, an Claude schicken
     (Claude darf Tools wie Web-Suche oder System-Status nutzen)
  4. Antwort aussprechen, dann zurück zu Schritt 2

Läuft im Terminal – UI, Kugel und Web-Server folgen in Phase 4–6.
"""

from __future__ import annotations

import sys

from brain.claude_client import ClaudeClient
from brain.memory import Memory
from config import get_config
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

       Phase 3 – Sprache + Gedächtnis + Tools
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

    print(f"[JARVIS] Bereit. Wartet auf Wake-Phrase: '{cfg.wake_phrase}'.")
    print("[JARVIS] Mit Strg+C beenden.")

    try:
        while True:
            wake.wait_for_wake(on_chunk=_log_chunk)
            print("[JARVIS] Wake-Phrase erkannt.")
            speaker.say("Guten Morgen. Wie kann ich helfen?")

            command = listener.listen_and_transcribe(cfg.command_seconds).strip()
            if not command:
                speaker.say("Ich habe nichts gehört.")
                continue

            print(f"[Du] {command}")
            try:
                reply = brain.ask(command)
            except Exception as exc:
                print(f"[JARVIS] Claude-Fehler: {exc}")
                speaker.say("Es gab ein Problem mit der Anfrage.")
                continue

            print(f"[JARVIS] {reply}")
            speaker.say(reply)
    except KeyboardInterrupt:
        print("\n[JARVIS] Bis später.")
        return 0
    finally:
        brain.close()
        tasks.close()


def _log_chunk(text: str) -> None:
    if text:
        print(f"  ... gehört: {text!r}")


if __name__ == "__main__":
    sys.exit(main())
