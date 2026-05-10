"""Wrapper, der JARVIS für den LaunchAgent-Modus startet.

Derzeit identisch zu `python main.py`, existiert als eigener Eintrag,
um die Daemon-Konfiguration unabhängig vom Haupt-Skript ändern zu
können (z. B. ohne Banner, mit anderem Logger-Level).
"""

from __future__ import annotations

import sys

from main import main


if __name__ == "__main__":
    sys.exit(main())
