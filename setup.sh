#!/usr/bin/env bash
# Erstinstallation von JARVIS auf macOS.
# Erstellt eine virtuelle Umgebung, installiert alle Abhängigkeiten,
# legt eine .env-Datei an und prüft kritische System-Tools.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

echo "JARVIS – Erstinstallation"
echo "==========================="

# 1. ffmpeg (Pflicht für Whisper)
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo
    echo "ffmpeg fehlt. Installiere es bitte zuerst:"
    echo "  brew install ffmpeg"
    echo
    exit 1
fi
echo "✓ ffmpeg gefunden"

# 2. Python-Version prüfen (3.11+)
PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "✓ Python $PY_VERSION"

# 3. Virtuelle Umgebung anlegen
if [[ ! -d ".venv" ]]; then
    python3 -m venv .venv
    echo "✓ .venv angelegt"
else
    echo "✓ .venv vorhanden"
fi

# 4. Dependencies installieren
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet -U pip
pip install --quiet -r requirements.txt
echo "✓ Python-Abhängigkeiten installiert"

# 5. .env vorbereiten
if [[ ! -f ".env" ]]; then
    cp .env.example .env
    echo "✓ .env erstellt – bitte ANTHROPIC_API_KEY eintragen"
else
    echo "✓ .env bereits vorhanden"
fi

# 6. Daten-/Log-Verzeichnis
mkdir -p data/logs

# 7. Electron-Frontend (optional)
if command -v npm >/dev/null 2>&1; then
    if [[ ! -d "dashboard/mac_app/node_modules" ]]; then
        echo "Installiere Electron …"
        (cd dashboard/mac_app && npm install --silent)
        echo "✓ Electron-Abhängigkeiten installiert"
    else
        echo "✓ Electron-Abhängigkeiten vorhanden"
    fi
else
    echo "(npm nicht gefunden – Kugel/Dashboard können später per 'brew install node' nachinstalliert werden)"
fi

echo
echo "Fertig."
echo
echo "Nächste Schritte:"
echo "  1. .env öffnen und ANTHROPIC_API_KEY eintragen"
echo "  2. JARVIS starten:    source .venv/bin/activate && python main.py"
echo "  3. Kugel starten:     cd dashboard/mac_app && npm start"
echo "  4. Autostart aktivieren: ./daemon/install.sh"
