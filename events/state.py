"""JARVIS-Zustände (für die Kugel, das Dashboard und den Web-Client).

Alle UI-Komponenten reagieren auf diese sechs Zustände. Werte sind
absichtlich stabile Strings, damit sie 1:1 über JSON ans Frontend gehen
und dort als Keys in `states.js` wieder auftauchen.
"""

from __future__ import annotations

from enum import Enum


class JarvisState(str, Enum):
    SLEEPING = "sleeping"     # Wartet auf Wake-Phrase
    LISTENING = "listening"   # Hört aktiv zu (nimmt Befehl auf)
    THINKING = "thinking"     # Wartet auf Claude-Antwort / führt Tools aus
    SPEAKING = "speaking"     # Spricht Antwort aus
    ERROR = "error"           # Fehler aufgetreten
    SUCCESS = "success"       # Aufgabe erfolgreich abgeschlossen
