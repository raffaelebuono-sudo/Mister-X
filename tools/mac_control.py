"""macOS-Steuerung über `open` und AppleScript.

Phase-3-Umfang: Apps starten, URLs öffnen, Dateien öffnen, Calendar-App
aufrufen. Erweiterte Aktionen (z. B. echte Kalender-Abfrage) folgen,
sobald der Bedarf konkreter ist.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class MacControlError(RuntimeError):
    """Fehler bei der macOS-Steuerung."""


def _ensure_macos() -> None:
    if not shutil.which("open"):
        raise MacControlError(
            "macOS-Befehl 'open' nicht gefunden – diese Funktion läuft nur auf macOS."
        )


def open_app(name: str) -> str:
    """Öffnet eine Mac-App per Namen, z. B. 'Safari' oder 'Calendar'."""
    _ensure_macos()
    result = subprocess.run(
        ["open", "-a", name],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MacControlError(
            f"App '{name}' konnte nicht geöffnet werden: {result.stderr.strip()}"
        )
    return f"App '{name}' wurde geöffnet."


def open_url(url: str) -> str:
    """Öffnet eine URL im Standard-Browser."""
    _ensure_macos()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise MacControlError("URL muss mit http:// oder https:// beginnen.")
    subprocess.run(["open", url], check=False)
    return f"URL geöffnet: {url}"


def open_file(path: str) -> str:
    """Öffnet eine Datei mit der Standard-Anwendung."""
    _ensure_macos()
    p = Path(path).expanduser()
    if not p.exists():
        raise MacControlError(f"Datei existiert nicht: {p}")
    subprocess.run(["open", str(p)], check=False)
    return f"Datei geöffnet: {p}"


def run_applescript(script: str) -> str:
    """Führt ein AppleScript aus und gibt stdout zurück."""
    _ensure_macos()
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MacControlError(f"AppleScript-Fehler: {result.stderr.strip()}")
    return result.stdout.strip()
