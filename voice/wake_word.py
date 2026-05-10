"""Erkennung der Wake-Phrase „Guten Morgen JARVIS".

Phase-1-Variante: Wir nehmen kontinuierlich kurze Audio-Fenster auf,
transkribieren mit Whisper und prüfen, ob die Wake-Phrase darin vorkommt.
Das ist nicht so effizient wie spezialisierte Wake-Word-Engines (z. B.
Porcupine), funktioniert aber ohne zusätzlichen Account.
"""

from __future__ import annotations

import re
from typing import Optional

from config import get_config
from voice.listener import Listener


def normalize(text: str) -> str:
    """Kleinbuchstaben + nur Buchstaben/Leerzeichen – robust gegen Satzzeichen."""
    return re.sub(r"[^a-zäöüß ]+", "", text.lower()).strip()


class WakeWordDetector:
    """Lauscht in Schleife, bis die Wake-Phrase erkannt wird."""

    def __init__(self, listener: Listener) -> None:
        cfg = get_config()
        self._listener = listener
        self._chunk_seconds = cfg.wake_chunk_seconds
        self._wake_phrase = normalize(cfg.wake_phrase)

    def wait_for_wake(self, on_chunk: Optional[callable] = None) -> str:
        """Blockiert, bis die Wake-Phrase im Mikrofon erkannt wird.

        `on_chunk` wird mit jedem transkribierten Fenster aufgerufen
        (z. B. zur Status-Anzeige oder zum Logging).
        Liefert den Text zurück, der die Wake-Phrase enthielt.
        """
        while True:
            text = self._listener.listen_and_transcribe(self._chunk_seconds)
            if on_chunk is not None:
                on_chunk(text)
            if self._contains_wake_phrase(text):
                return text

    def _contains_wake_phrase(self, text: str) -> bool:
        return self._wake_phrase in normalize(text)
