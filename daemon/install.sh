#!/usr/bin/env bash
# Installiert den JARVIS-LaunchAgent für den aktuellen Benutzer.
# JARVIS startet danach bei jedem Login automatisch im Hintergrund.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.jarvis.assistant"
TEMPLATE="$HERE/daemon/${LABEL}.plist.template"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET="$TARGET_DIR/${LABEL}.plist"

# Python aus venv bevorzugen
if [[ -x "$HERE/.venv/bin/python" ]]; then
    PYTHON="$HERE/.venv/bin/python"
else
    PYTHON="$(command -v python3)"
fi

if [[ -z "$PYTHON" ]]; then
    echo "Python wurde nicht gefunden. Bitte zuerst setup.sh ausführen." >&2
    exit 1
fi

mkdir -p "$TARGET_DIR" "$HERE/data/logs"

# Pfade ins Template einsetzen
sed -e "s|__PYTHON__|$PYTHON|g" \
    -e "s|__PROJECT__|$HERE|g" \
    "$TEMPLATE" > "$TARGET"

# Vorherige Instanz entladen (Fehler ignorieren) und neu laden
launchctl unload "$TARGET" 2>/dev/null || true
launchctl load "$TARGET"

echo "JARVIS LaunchAgent installiert:"
echo "  Plist : $TARGET"
echo "  Python: $PYTHON"
echo "  Logs  : $HERE/data/logs/"
echo
echo "Status pruefen:  launchctl list | grep $LABEL"
echo "Stoppen      :   launchctl unload $TARGET"
echo "Deinstallieren:  daemon/uninstall.sh"
