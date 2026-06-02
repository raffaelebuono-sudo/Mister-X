# 🌸 Anime-Studio

Eine Website, mit der du **deine eigenen Anime-Folgen erstellst**: Du gibst
Stichworte zur Handlung ein, die KI (Claude) macht daraus eine komplette Folge
mit Szenen, Schauplätzen, Stimmungen, Charakteren und Dialogen. Du schaust die
Folge anschließend in einem Player im Visual-Novel-Stil an – **Folge für Folge**,
mit fortlaufender, zusammenhängender Handlung.

## Funktionen

- **Serie anlegen**: Titel, Genre und Hauptcharaktere festlegen.
- **Folge generieren**: Stichworte eingeben → KI erstellt eine ganze Folge.
- **Fortlaufende Handlung**: Jede neue Folge kennt den bisherigen Verlauf und
  die Charaktere, sodass die Geschichte konsistent weitergeht.
- **Anime-Player**: Szenen mit stimmungsabhängigen Hintergründen,
  Charakter-Avataren und Dialog im Schreibmaschinen-Effekt. Mit Autoplay und
  Pfeiltasten-Steuerung (← → / Leertaste).
- **Speicherung**: Serien werden lokal als JSON unter `data/` abgelegt.
- **Demo-Modus**: Ohne API-Key läuft eine eingebaute Demo, damit du die Seite
  sofort testen kannst.

## Start

Im Projekt-Wurzelverzeichnis:

```bash
# Abhängigkeiten (sind großteils schon in requirements.txt)
pip install fastapi "uvicorn[standard]" anthropic python-dotenv

# Server starten
python -m anime_studio.server
```

Dann im Browser öffnen: **http://localhost:8800**

## Echte KI statt Demo

Für die volle Qualität brauchst du einen Anthropic-API-Key. Trage ihn in die
`.env`-Datei im Projekt-Wurzelverzeichnis ein (siehe `.env.example`):

```
ANTHROPIC_API_KEY=sk-ant-...
```

Optional kannst du das Modell überschreiben:

```
ANIME_MODEL=claude-sonnet-4-6
ANIME_PORT=8800
```

Oben rechts auf der Seite siehst du, ob die KI aktiv ist oder der Demo-Modus
läuft.

## Aufbau

| Datei | Zweck |
|-------|-------|
| `server.py` | FastAPI-Webserver + JSON-API |
| `generator.py` | KI-Logik (Claude) inkl. Demo-Fallback |
| `static/index.html` | Oberfläche |
| `static/style.css` | Anime-Design |
| `static/app.js` | Player & Steuerung |
| `data/` | gespeicherte Serien (nicht im Git) |
