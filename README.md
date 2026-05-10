# JARVIS – Persönlicher KI-Assistent

Persönlicher KI-Assistent auf Deutsch, läuft auf macOS.

> Aktueller Stand: **Phase 1 – Sprachkern**. Spricht und versteht Deutsch,
> reagiert auf die Wake-Phrase „Guten Morgen JARVIS" und antwortet über
> Claude. UI, Dashboard, Kugel und iPhone-Zugriff folgen in späteren Phasen.

## Voraussetzungen

- macOS (für `say`-Sprachausgabe und später für die Mac-App)
- Python 3.11 oder neuer
- `ffmpeg` (von Whisper benötigt) – Installation: `brew install ffmpeg`
- Funktionierendes Mikrofon
- Anthropic-API-Key

## Installation

```bash
# 1. Virtuelle Umgebung erstellen
python3 -m venv .venv
source .venv/bin/activate

# 2. Abhängigkeiten installieren
pip install -r requirements.txt

# 3. Konfiguration
cp .env.example .env
# .env öffnen und ANTHROPIC_API_KEY eintragen
```

## Starten

```bash
python main.py
```

Beim ersten Start lädt Whisper das Modell (`base`, ~150 MB) herunter.
Danach wartet JARVIS auf die Wake-Phrase **„Guten Morgen JARVIS"** und
antwortet auf die folgende Frage.

Mit `Strg+C` beenden.

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
- **Klick**: öffnet das Dashboard-Fenster (Inhalt folgt in Phase 5).
- WebSocket-Endpunkt: `ws://127.0.0.1:8765` (in `config.py` änderbar).

## Phasen-Plan

| Phase | Inhalt | Status |
|------:|--------|--------|
| 1 | Sprachkern (Whisper, Claude, TTS) | ✅ |
| 2 | SQLite-Gedächtnis & Persönlichkeits-Tuning | ✅ |
| 3 | Tools: Web-Suche, macOS-Steuerung, Aufgaben, System-Monitor | ✅ |
| 4 | Visuelle Kugel (Electron + Three.js) | ✅ |
| 5 | Vollständiges Dashboard | offen |
| 6 | iPhone Web-Interface | offen |
| 7 | 24/7-Betrieb (LaunchAgent) | offen |

## Hinweise

- **API-Keys** stehen ausschließlich in der `.env`-Datei (nicht im Code).
- **Sprachausgabe**: Ohne `ELEVENLABS_API_KEY` nutzt JARVIS die deutsche
  macOS-Stimme „Anna" über den `say`-Befehl.
- **Whisper-Modell**: In `config.py` steht `whisper_model = "base"`.
  Für bessere Qualität auf `small` oder `medium` setzen – aber langsamer.
