#!/usr/bin/env bash
# Entfernt den JARVIS-LaunchAgent.

set -euo pipefail

LABEL="com.jarvis.assistant"
TARGET="$HOME/Library/LaunchAgents/${LABEL}.plist"

if [[ -f "$TARGET" ]]; then
    launchctl unload "$TARGET" 2>/dev/null || true
    rm -f "$TARGET"
    echo "Entfernt: $TARGET"
else
    echo "Kein LaunchAgent installiert (nichts zu tun)."
fi
