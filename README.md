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
| 9 | Computer Use: Claude steuert den Mac direkt | ✅ |
| 10 | Langzeitgedächtnis: JARVIS lernt dich kennen | ✅ |
| 11 | HUD-Dashboard, Klatsch-/Code-Aktivierung, Brain-Feed | ✅ |
| 12 | Agenten-Armee + Welcome-Ritual + System-Inspektion | ✅ |
| 13 | Autonomie-Fundament: Resilienz, Selbst-Überwachung | ✅ |
| 14 | Lokales Fallback-Gehirn (Ollama, offline) | ✅ |
| 15 | Multi-Cloud-Fallback (OpenAI/Gemini auf Claude-Niveau) | ✅ |
| 16 | Selbst-Steuerung: Ziele + Executive-Agent | ✅ |
| 17 | Operations Center: Wetter, News-Ticker, Agenten-Grid | ✅ |

## Operations Center (Phase 17)

Das Dashboard ist jetzt ein echtes Lagezentrum mit Live-Kacheln:

- **Wetter** (Open-Meteo, kostenlos, kein API-Key) – aktuell + heute/
  morgen, Standort in `config.py` (`weather_lat/lon/city`, Default Wien).
  Auch als Tool `weather` für gesprochene Wetterfragen.
- **News-Ticker** – laufende Schlagzeilen aus den News-Agenten.
- **Agenten-Grid** – alle Hintergrund-Agenten mit Live/Idle-Status
  und letztem Lauf.
- **Ziele-Tracker** – was der Executive gerade eigenständig verfolgt.
- **Tages-Statistiken** in der Topbar – Gespräche, erledigte Aufgaben,
  offene Briefings, aktive Ziele, Uptime.
- Backend pusht Wetter alle 10 min, restliche Kacheln alle 30 s.

Einstellbar in `config.py`: `weather_refresh_seconds`,
`ambient_refresh_seconds`.

## Selbst-Steuerung (Phase 16)

JARVIS arbeitet eigenständig weiter, auch ohne Befehl:

- **Ziele** (`goals`): fortlaufende Missionen statt einmaliger To-dos.
  Per Sprache setzen: *„Jarvis, behalte KI-News im Auge"*,
  *„recherchiere nach und nach gute E-Bike-Ladegeräte"*.
- **Executive-Agent**: läuft alle paar Stunden (Default 3 h),
  schaut auf Ziele + Profil + offene Aufgaben + letzte Briefings und
  entscheidet selbst die EINE sinnvollste proaktive Handlung – oder
  pausiert bewusst (`PASS`), wenn nichts ansteht. Kein Aktionismus.
- **Harte Grenzen**: max. `executive_daily_budget` (Default 6)
  autonome Aktionen pro Tag → keine Kosten-/Spam-Explosion. Niemals
  destruktive Aktionen. Ergebnisse landen als Briefing und erreichen
  dich erst beim nächsten Online-Kommen (kein Reinquatschen).
- Fair: das am längsten vernachlässigte Ziel wird zuerst bedient.

Einstellbar in `config.py`: `executive_enabled`,
`executive_interval_hours`, `executive_daily_budget`.

## Gehirn-Fallback-Kette (Phase 14 + 15)

JARVIS bleibt antwortfähig, auch wenn etwas ausfällt. Reihenfolge:

1. **Claude Sonnet 4.6** (Anthropic) — primär, volle Tool-/Profil-Power
2. **OpenAI / Gemini** — wenn Anthropic streikt, Internet aber geht.
   Gleiche Qualitätsklasse. Keys via `.env`:
   `OPENAI_API_KEY`, `GEMINI_API_KEY` (einer reicht).
3. **Lokales Modell (Ollama)** — echtes Offline, schwächer, Notnagel.
4. **Klartext-Hinweis**, dass gerade gar nichts geht (kein Crash).

Jede Stufe greift nur, wenn die darüber ausfällt; sobald Claude
wieder erreichbar ist, läuft automatisch alles wieder primär.

## Geplant: Externer Server-Brain (Phase 16, Hardware nötig)

Für echte Cloud-Unabhängigkeit auf nahezu Claude-Niveau – noch nicht
gebaut, weil Hardware fehlt. Bauplan, wenn du investierst:

- **Hardware**: Mini-PC / Mac Studio / Server mit GPU, 48 GB+ RAM
  (z. B. RTX 4090 24 GB oder Mac Studio M-Ultra). Modell:
  Llama 3.3 70B oder Qwen 2.5 72B (quantisiert).
- **Software dort**: Ollama oder vLLM als OpenAI-kompatibler Endpoint.
- **Anbindung hier**: Der bestehende `LocalBrain` zeigt dann statt auf
  `127.0.0.1:11434` auf die Server-IP im Heimnetz
  (`local_brain_url` in `config.py`). Kein neuer Code nötig –
  die Fallback-Kette nimmt ihn automatisch als Stufe 3.
- **Optional**: WireGuard-VPN, damit der Server-Brain auch von
  unterwegs erreichbar ist.

Realistische Kosten: 2.000–4.000 € einmalig. Qualität: nahe Claude,
nicht gleich. Erst sinnvoll, wenn Internet-Unabhängigkeit Priorität hat.

## Lokales Fallback-Gehirn (Phase 14)

Wenn die Cloud (Anthropic) nicht erreichbar ist, antwortet JARVIS
mit einem **lokalen Modell** weiter, statt stumm zu bleiben. Sobald
die Verbindung zurück ist, schaltet er automatisch wieder auf Claude.

Einrichten (einmalig):

```bash
# 1. Ollama installieren
brew install ollama
# 2. Ollama-Dienst starten (eigenes Terminal, läuft im Hintergrund)
ollama serve
# 3. Modell ziehen – für MacBook Air 8GB: llama3.2 (3B, ~2GB)
ollama pull llama3.2
```

In `config.py` einstellbar: `local_brain_model` (z. B. `llama3.1`
bei 16GB RAM), `local_brain_enabled`, `local_brain_url`.

Hinweis: Das lokale Modell ist deutlich schwächer als Claude und
hat keine Tools/kein Profil – es ist ein Notnagel für Offline-Phasen,
kein Ersatz. Auf einem lüfterlosen MacBook Air ist es spürbar
langsamer; deshalb nur als Fallback aktiv, nicht als Hauptgehirn.

## Langzeitgedächtnis (Phase 10)

JARVIS merkt sich dauerhaft, was er über dich weiß: Name, Wohnort,
Vorlieben, Beziehungen, Projekte, Routinen, Ziele, Gesundheit. Diese
Fakten werden bei JEDEM Gespräch in den System-Prompt eingehängt –
JARVIS „erinnert sich an alles", auch über Sitzungen und Tage hinweg.

**Wie es funktioniert:**

1. **Automatische Extraktion**: Nach jedem Gespräch läuft im Hintergrund
   ein Claude-Haiku-Aufruf (deutlich billiger als Sonnet), der das Gespräch
   nach neuen dauerhaften Fakten durchsucht und sie in `data/jarvis.db`
   speichert.

2. **Explizit per Sprache**: *„Jarvis, merk dir: ich wohne in Wien"* →
   er ruft das `remember`-Tool auf und legt es ab.

3. **Abrufen**: *„Was weißt du über mich?"* → `list_facts`-Tool.

4. **Vergessen**: *„Jarvis, vergiss dass ich in Wien wohne"* → `forget_fact`.

**Kategorien:** `identitaet`, `vorlieben`, `beziehungen`, `projekte`,
`routinen`, `ziele`, `gesundheit`, `sonstiges`.

**Datenspeicher**: alles lokal in `data/jarvis.db` (in `.gitignore`).
Du behältst die volle Kontrolle, kannst Fakten jederzeit vergessen oder
die Datei komplett löschen.

## Computer Use – Claude steuert den Mac (Phase 9)

JARVIS kann jetzt selbst Apps öffnen, klicken, tippen und Screenshots
analysieren. Ausgelöst über das Tool `computer_use`. Beispiele:

- *„Jarvis, öffne Safari und such mir Pizza in Wien"*
- *„Jarvis, erstelle eine neue Notiz mit dem Titel Einkaufsliste"*
- *„Jarvis, pause meine Musik"*

### Erforderliche Berechtigungen (einmalig)

macOS muss der App, von der aus Python gestartet wird (Terminal,
iTerm, oder dem Python-Binary), zwei Rechte erteilen:

1. **Bedienungshilfen**: *Systemeinstellungen → Datenschutz & Sicherheit →
   Bedienungshilfen* → Häkchen für Terminal/iTerm/Python.
2. **Bildschirmaufnahme**: *Systemeinstellungen → Datenschutz & Sicherheit →
   Bildschirm- & Audioaufnahme* → Häkchen für Terminal/iTerm/Python.

Beim ersten Aufruf von `computer_use` zeigt macOS automatisch einen
Dialog – einmalig erlauben, danach geht's.

### Sicherheits-Stops

- pyautogui-FAILSAFE: Maus oben-links in die Ecke schieben → bricht alles ab.
- Schritt-Limit: 30 (in `config.py:computer_use_max_steps` änderbar).
- System-Prompt verbietet destruktive Aktionen ohne klare Anweisung.

### Kosten

Jede Aufgabe schickt mehrere Screenshots an Claude (Bilder = mehr Tokens).
Realistisch: 5–30 Cent pro Aufgabe. In `config.py` lassen sich Modell,
Token-Limit und Schrittzahl anpassen.

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

## Animierter Serien-Generator (`episode_generator.py`)

Erzeugt **ganze animierte Folgen** mit Figuren, die sich bewegen und reden
(Stil: 2D-Sitcom à la *Lower Decks*). Die KI schreibt das komplette
Drehbuch, dann werden die Figuren prozedural animiert und vertont.

```bash
# Kurze Test-Folge (~2 Min)
python episode_generator.py --idea "Sternenflotten-Crew voller Chaos" --minutes 2

# Lange Folge (Ziel 40 Min) mit echten Stimmen
python episode_generator.py --idea "Detektiv-Katze im All" --minutes 40 --voice

# Aus vorhandenem Drehbuch neu rendern (ohne Claude-Aufruf)
python episode_generator.py --script-json output/serien/.../drehbuch.json
```

Was passiert:

1. **Drehbuch** – Claude schreibt in Teilen Serien-Bibel, Figuren,
   Szenen-Outline und pro Szene die vollen Dialoge. So sind auch lange
   Folgen möglich (`--minutes` steuert die Ziel-Länge).
2. **Animation** (`animation_engine.py`) – jede Figur wird aus Körperteilen
   pro Frame neu posiert: **Lauf-Zyklus, Wippen, Blinzeln, Gesten** und
   **Lippen-Sync**. Figuren bleiben über die ganze Folge konsistent.
3. **Stimmen** – mit `--voice` bekommt jede Figur eine eigene Stimme
   (ElevenLabs falls `ELEVENLABS_API_KEY`, sonst macOS `say`); der Mund
   bewegt sich nach der echten Audio-Lautstärke. Ohne TTS: prozedurale
   Lippen-Bewegung.
4. **Schnitt** – jede Szene wird zu einem vertonten Clip; alle Szenen +
   Titelkarte werden per `ffmpeg` zur fertigen `.mp4` montiert.

Wichtige Optionen: `--minutes` (Ziel-Länge), `--voice` (echte Stimmen),
`--lang`, `--width`/`--height`/`--fps`, `--script-json` (neu rendern).

> **Ehrlich:** Das Ergebnis ist ein sauberer, vollständig animierter
> Cartoon mit sprechenden Figuren – aber **keine** Studio-Qualität wie das
> echte *Lower Decks*. Eine 40-Minuten-Folge zu rendern dauert je nach
> Rechner spürbar (viele Tausend Frames). `ffmpeg`, `numpy` und `Pillow`
> sind erforderlich.

---

## 2D-Standbild-Serien (`series_generator.py`)

Schlankere Variante: aus einer Idee Drehbuch (Claude) → 2D-Bilder pro Szene
→ optionale Erzähler-Stimme → fertiges `.mp4` (Slideshow mit Untertiteln).
Gut für schnelle Storyboards.

```bash
# Eine Folge – läuft sofort, ohne extra Bild-Key (Pillow-2D-Panels)
python series_generator.py --idea "Eine mutige Maus im Weltraum"

# Drei Folgen, je 6 Szenen, mit Erzähler-Stimme
python series_generator.py --idea "Detektiv-Katze löst Fälle" \
    --episodes 3 --scenes 6 --narrate

# Nur Drehbuch + Bilder, kein Video (schnell)
python series_generator.py --idea "Roboter lernt kochen" --no-video
```

Wichtigste Optionen (deutsche Aliase in Klammern):

| Option | Bedeutung | Standard |
|--------|-----------|----------|
| `--idea` (`--konzept`) | Serien-Idee (Pflicht) | – |
| `--episodes` (`--folgen`) | Anzahl Folgen | 1 |
| `--scenes` (`--szenen`) | Szenen pro Folge | 5 |
| `--style` (`--stil`) | Visueller Stil | flacher Cartoon |
| `--lang` (`--sprache`) | Sprache der Texte | Deutsch |
| `--narrate` | Erzähler-Stimme erzeugen | aus |
| `--no-video` | nur Drehbuch + Bilder | aus |
| `--width` / `--height` / `--fps` | Video-Format | 1280×720, 24 fps |
| `--seconds-per-scene` | Dauer je Szene | 4.0 s |

**Bildquelle:** Ist `OPENAI_API_KEY` gesetzt, werden die Szenen über die
OpenAI-Bild-API generiert. Andernfalls zeichnet das Skript stimmige
2D-Comic-Panels mit Pillow – läuft also ohne zusätzlichen Key.
**Video** benötigt `ffmpeg`; fehlt es, werden Drehbuch und Bilder trotzdem
erzeugt und der Video-Schritt sauber übersprungen.

Alles landet unter `output/serien/<serientitel>/` (Drehbuch als
`drehbuch.json`, je Folge ein Ordner mit `frames/` und `.mp4`).
