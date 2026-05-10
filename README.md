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
└── data/
    └── jarvis.db            # SQLite-Gedächtnis (wird automatisch angelegt)
```

## Phasen-Plan

| Phase | Inhalt | Status |
|------:|--------|--------|
| 1 | Sprachkern (Whisper, Claude, TTS) | ✅ |
| 2 | SQLite-Gedächtnis & Persönlichkeits-Tuning | ✅ |
| 3 | Tools: Web-Suche, macOS-Steuerung, Aufgaben | offen |
| 4 | Visuelle Kugel (Electron + Three.js) | offen |
| 5 | Vollständiges Dashboard | offen |
| 6 | iPhone Web-Interface | offen |
| 7 | 24/7-Betrieb (LaunchAgent) | offen |

## Hinweise

- **API-Keys** stehen ausschließlich in der `.env`-Datei (nicht im Code).
- **Sprachausgabe**: Ohne `ELEVENLABS_API_KEY` nutzt JARVIS die deutsche
  macOS-Stimme „Anna" über den `say`-Befehl.
- **Whisper-Modell**: In `config.py` steht `whisper_model = "base"`.
  Für bessere Qualität auf `small` oder `medium` setzen – aber langsamer.
