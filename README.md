# JARVIS – Persönlicher KI-Assistent

Persönlicher KI-Assistent auf Deutsch, läuft auf macOS. Spricht und
versteht Deutsch (Whisper + ElevenLabs/`say`), erinnert sich an
vergangene Gespräche (SQLite), kann Tools aufrufen (Web-Suche,
macOS-Steuerung, Aufgaben, System-Status), zeigt eine schwebende
Three.js-Kugel über allen Fenstern, hat ein vollständiges Dashboard
sowie ein mobiles Web-Interface fürs iPhone.

## Voraussetzungen

- macOS (für `say`-Sprachausgabe und die Mac-App)
- Python 3.11 oder neuer
- `ffmpeg` (von Whisper benötigt): `brew install ffmpeg`
- Node.js + npm (für Kugel/Dashboard): `brew install node`
- Funktionierendes Mikrofon
- Anthropic-API-Key

## Schnellstart

```bash
./setup.sh
# Dann .env öffnen und ANTHROPIC_API_KEY eintragen
source .venv/bin/activate
python main.py
```

In einem zweiten Terminal die Kugel starten:

```bash
cd dashboard/mac_app && npm start
```

Beim ersten Start lädt Whisper das Modell (`base`, ~150 MB) herunter.
Danach wartet JARVIS auf die Wake-Phrase **„Guten Morgen JARVIS"** und
antwortet auf die folgende Frage. Mit `Strg+C` beenden.

## Manuelle Installation

```bash
brew install ffmpeg node
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ANTHROPIC_API_KEY eintragen
cd dashboard/mac_app && npm install && cd ../..
python main.py
```

## Projektstruktur (Phase 1)

```
.
├── main.py                  # Haupt-Loop (Wake-Word → Frage → Antwort)
├── config.py                # Konfiguration aus .env
├── brain/
│   ├── claude_client.py     # Claude-API mit Gesprächs-Historie
│   └── system_prompt.py     # JARVIS-Persönlichkeit
├── voice/
│   ├── listener.py          # Mikrofon + Whisper
│   ├── speaker.py           # ElevenLabs / macOS 'say'
│   └── wake_word.py         # „Guten Morgen JARVIS"-Erkennung
├── tools/
│   ├── registry.py          # Tool-Schemas & Dispatch für Claude
│   ├── web_search.py        # Tavily Web-Suche
│   ├── mac_control.py       # macOS-Steuerung (Apps, URLs, Dateien)
│   ├── task_manager.py      # Aufgaben & Erinnerungen (SQLite)
│   └── system_monitor.py    # CPU, RAM, Akku, Disk, Uptime
└── data/
    └── jarvis.db            # SQLite – Gedächtnis und Aufgaben
```

## Tools, die JARVIS nutzen kann (Phase 3)

Claude entscheidet selbst, welches Tool zur Anfrage passt:

| Tool | Wofür |
|------|-------|
| `web_search` | News, Wetter, Aktuelles (braucht `TAVILY_API_KEY`) |
| `open_app` / `open_url` / `open_file` | macOS-Steuerung |
| `add_task` / `list_tasks` / `complete_task` | Aufgaben & Erinnerungen |
| `system_status` | CPU, RAM, Akku, Disk, Uptime |

## Visuelle Kugel (Phase 4)

Die schwebende Kugel ist eine Electron-App in `dashboard/mac_app/`. Sie
verbindet sich per WebSocket zum Python-Backend und animiert sich
zustandsabhängig (sleeping/listening/thinking/speaking/error/success).

```bash
# In einem zweiten Terminal, während main.py läuft:
cd dashboard/mac_app
npm install        # einmalig
npm start          # öffnet die Kugel
```

- **Verschieben**: Kugel mit gedrückter Maustaste ziehen.
- **Klick**: öffnet das Dashboard-Fenster.
- WebSocket-Endpunkt: `ws://127.0.0.1:8080/ws` (Port in `config.py`).

## Dashboard (Phase 5)

Das Dashboard zeigt den vollständigen Status und erlaubt Tipp-Eingaben
parallel zur Sprache.

- **Status-Bar oben**: aktueller Zustand und letzte Nachricht
- **Chat (Mitte)**: kompletter Verlauf, Texteingabe unten,
  Häkchen „vorlesen" steuert TTS pro Tipp-Eingabe
- **System-Monitor (rechts)**: CPU/RAM/Festplatte/Akku live (alle 2 s)
- **Aufgaben (unten)**: aktive Aufgaben als Karten, Sofort-Erledigen-Button,
  Schnell-Hinzufügen mit optionalem Fälligkeitsdatum
- **Sidebar (links)**: Schnellaktionen (News, Wetter, Kalender, Erinnerung,
  Einstellungen)

Voice und Dashboard nutzen denselben `JarvisCore` und denselben
`Memory`-Speicher, sodass eine getippte Frage und eine gesprochene
Frage gleichberechtigt sind.

## iPhone Web-Interface (Phase 6)

JARVIS startet automatisch einen FastAPI-Server auf `http://0.0.0.0:8080`.
Ist das iPhone im selben WLAN, ist JARVIS unter
`http://<IP-des-Macs>:8080` oder `http://jarvis.local:8080`
erreichbar (sofern Bonjour läuft).

- **`/`** — Mobile Web-Frontend (Tabs: Chat, Aufgaben, Status)
- **`/ws`** — Gleicher WebSocket-Pfad wie für die Electron-App
- **REST**:
  - `GET /api/status` — JARVIS- und System-Status
  - `GET /api/history?limit=N` — Chat-Verlauf
  - `POST /api/chat` — `{ "content": "...", "speak": false }`
  - `GET /api/tasks` — offene Aufgaben
  - `POST /api/tasks` — `{ "title": "...", "due_at": null }`
  - `POST /api/tasks/{id}/complete`

Hinweis: Da der Server an `0.0.0.0` lauscht, ist er für alle Geräte im
WLAN sichtbar – das ist genau gewollt für den iPhone-Zugriff. Wer das
nicht will, setzt `web_host = "127.0.0.1"` in `config.py`.

## Phasen-Plan

| Phase | Inhalt | Status |
|------:|--------|--------|
| 1 | Sprachkern (Whisper, Claude, TTS) | ✅ |
| 2 | SQLite-Gedächtnis & Persönlichkeits-Tuning | ✅ |
| 3 | Tools: Web-Suche, macOS-Steuerung, Aufgaben, System-Monitor | ✅ |
| 4 | Visuelle Kugel (Electron + Three.js) | ✅ |
| 5 | Vollständiges Dashboard | ✅ |
| 6 | iPhone Web-Interface | ✅ |
| 7 | 24/7-Betrieb (LaunchAgent), Logging, Polishing | ✅ |
| 8 | Friday-Mode: Hintergrund-Agenten, Scheduler, Briefings | ✅ |

## Friday-Mode: Hintergrund-Agenten (Phase 8)

JARVIS hat jetzt eigene Agenten, die im Hintergrund arbeiten. Jeder Agent
hat seine eigene Persönlichkeit, läuft mit eigenem Claude-Stream
(unabhängig vom Haupt-Gedächtnis) und kann auf alle Tools zugreifen.

| Agent | Zweck | Zeitplan |
|-------|-------|----------|
| `morning_briefing` | News + Aufgaben als Tagesüberblick | täglich 7:00 |
| `news_watcher` | Eine wichtige News-Headline zusammenfassen | alle 4 h |
| `note_taker` | Fakten aus dem Verlauf extrahieren | nur auf Anfrage |

Ergebnisse landen als **Briefings** in der Datenbank. JARVIS ruft sie über
die Tools `list_briefings`, `run_agent` und `mark_briefings_read` auf.

**Beispiele:**
- *„Jarvis, was ist neu?"* → liest dir die ungelesenen Briefings vor
- *„Jarvis, mach mir jetzt eine Morgenbriefing"* → startet den Agenten on-demand
- *„Jarvis, fasse meine letzten Gespräche zusammen"* → lässt den `note_taker` laufen

Der Scheduler tickt einmal pro Minute. Wenn JARVIS zur geplanten Zeit nicht
läuft, wird der nächste Lauf einfach beim nächsten Match nachgeholt.

## Autostart (Phase 7)

JARVIS kann beim Login automatisch im Hintergrund starten:

```bash
./daemon/install.sh        # legt ~/Library/LaunchAgents/com.jarvis.assistant.plist an
launchctl list | grep jarvis    # Status prüfen
./daemon/uninstall.sh      # wieder entfernen
```

Logs landen in `data/logs/`:

| Datei | Inhalt |
|-------|--------|
| `jarvis.log` (rotierend, 5 MB × 3) | Anwendungs-Log |
| `launchd.out.log` / `launchd.err.log` | stdout/stderr aus LaunchAgent |

## Hinweise

- **API-Keys** stehen ausschließlich in der `.env`-Datei (nicht im Code).
- **Sprachausgabe**: Ohne `ELEVENLABS_API_KEY` nutzt JARVIS die deutsche
  macOS-Stimme „Anna" über den `say`-Befehl.
- **Whisper-Modell**: In `config.py` steht `whisper_model = "base"`.
  Für bessere Qualität auf `small` oder `medium` setzen – aber langsamer.
- **Mikrofon-Berechtigung**: macOS fragt beim ersten Start nach Mikrofon-
  Zugriff. Im LaunchAgent-Modus muss diese Berechtigung manuell unter
  *Systemeinstellungen → Datenschutz → Mikrofon* erteilt werden.
