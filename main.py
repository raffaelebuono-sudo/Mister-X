"""JARVIS – Hauptprogramm (Phase 1).

Ablauf:
  1. Whisper, Speaker und Claude initialisieren
  2. Auf Wake-Phrase „Guten Morgen JARVIS" warten
  3. Begrüßen, Frage aufnehmen, an Claude schicken
  4. Antwort aussprechen, dann zurück zu Schritt 2

Phase 1 läuft komplett im Terminal – ohne UI, ohne Kugel.
"""

from __future__ import annotations

import sys

from brain.claude_client import ClaudeClient
from config import get_config
from voice.listener import Listener
from voice.speaker import Speaker
from voice.wake_word import WakeWordDetector


BANNER = r"""
   _   _   _   _    _   _____ _____
  | | / \ | |_| \  / | |_   _/ ____|
  | |/ _ \| '_|\ \/ /    | | \___ \
 _|  / ___ \ |  \  /    _| |_____)|
(__)/_/   \_\_|  \/    |_____|____/

       Phase 1 – Sprachkern
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
    brain = ClaudeClient()
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


def _log_chunk(text: str) -> None:
    if text:
        print(f"  ... gehört: {text!r}")


if __name__ == "__main__":
    sys.exit(main())
