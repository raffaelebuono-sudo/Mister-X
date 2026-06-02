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
- **Stimmen 🔊**: Die Charaktere sprechen ihre Dialoge (Sprachausgabe des
  Browsers, **kein Key nötig**). Jeder Charakter bekommt eine eigene Tonhöhe.
- **Szenen bearbeiten ✏️**: Schauplatz, Stimmung, Erzähltext und einzelne
  Dialogzeilen lassen sich von Hand ändern, hinzufügen oder löschen.
- **Szene neu generieren 🎲**: Einzelne Szenen per KI neu erzeugen – optional
  mit einem Hinweis, wie sie anders werden soll.
- **Echte Anime-Bilder 🎨**: Pro Szene erzeugt eine Bild-KI ein echtes
  Anime-Bild (z. B. im Shonen-Piraten-Abenteuer-Look). Beim Erstellen einer
  Folge werden die Bilder automatisch gezeichnet; einzelne Bilder lassen sich
  neu erzeugen. Beim Anlegen der Serie wählst du den **Zeichenstil**.
  Ohne Bild-Key bleibt der Stimmungs-Hintergrund erhalten.
- **Konsistente Charaktere 🧍**: Jede Figur bekommt eine feste, generierte
  Aussehensbeschreibung (Haare, Augen, Kleidung …), die in jeden Bild-Prompt
  einfließt – so sehen Charaktere über alle Szenen ähnlich aus.
- **Bewegung & Überblendungen 🎬**: Im Player zoomt/schwenkt das Bild sanft
  (Ken-Burns-Effekt) mit weichen Übergängen.
- **Profi-Stimmen (ElevenLabs) 🗣️**: Mit `ELEVENLABS_API_KEY` sprechen die
  Charaktere mit natürlichen Stimmen (eine feste Stimme je Figur). Ohne Key
  übernimmt die kostenlose Browser-Sprachausgabe.
- **Video-Export (MP4) 🎞️**: Die ganze Folge wird zu einer echten Videodatei
  gerendert – Titelkarte, Szenen mit Ken-Burns-Bewegung, weiche Übergänge,
  eingebrannte Untertitel und (mit ElevenLabs) gesprochene Stimmen. Per
  Browser herunterladbar. Nutzt das mitgelieferte `ffmpeg` (imageio-ffmpeg).
- **Bewegte KI-Video-Clips 🎬 (optional)**: Mit `REPLICATE_API_TOKEN` wird pro
  Szene ein echter, BEWEGTER KI-Clip erzeugt (Image-to-Video) statt eines
  Standbilds mit Zoom. Beim Export aktivierbar. Langsam und kostenpflichtig.
- **KI-Hintergrundmusik 🎵 (optional)**: Ebenfalls über Replicate (MusicGen)
  wird je nach Stimmung der Folge ein Musiktrack erzeugt und leise unter die
  Stimmen gemischt.

> **Ehrlicher Hinweis zur Qualität:** Auch mit allen Optionen entsteht ein
> beeindruckender *KI-Anime-Short / Trailer* – **kein** Anime auf
> Netflix-Serien-Niveau. Das ist mit heutiger KI (lange, durchgehend
> konsistente, broadcast-fertige Folgen) nicht erreichbar, und Netflix
> lizenziert Inhalte von Studios statt sie hochladen zu lassen. Das Tool ist
> ideal für Ideen, Storyboards, Pitch-Reels und Social-Media-Clips.
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

### Welcher Key wofür?

| Funktion | Key | Pflicht? |
|----------|-----|----------|
| Folgen/Szenen schreiben (Story-KI) | `ANTHROPIC_API_KEY` | **Ja** (sonst Demo) |
| Echte Anime-Bilder pro Szene | `OPENAI_API_KEY` **oder** `GEMINI_API_KEY` | Nur für Bilder |
| Einfache Stimmen / Sprachausgabe | — (Browser, gratis) | Nein |
| Profi-Stimmen | `ELEVENLABS_API_KEY` | Nur für Profi-Stimmen |
| Video-Export (MP4) | — (`ffmpeg` ist mitgeliefert) | Nein |
| Bewegte KI-Video-Clips + KI-Musik | `REPLICATE_API_TOKEN` | Nur für Clips/Musik |

> **Hinweis zum Stil:** Bild-KIs blockieren meist Prompts, die einen lebenden
> Künstler oder eine geschützte Marke namentlich nennen (z. B. „Eiichiro Oda",
> „One Piece"). Das Studio beschreibt stattdessen den *Look* (kräftige
> Tuschelinien, expressive Figuren, leuchtende Farben, Shonen-Abenteuer) –
> das Ergebnis sieht dem Vorbild sehr ähnlich, ist aber rechtlich/technisch
> sauber.

### Bild-Anbieter

Es genügt **einer** der beiden Keys:

- **OpenAI** (`OPENAI_API_KEY`) – Modell `gpt-image-1`, sehr gute Anime-Qualität.
  Erfordert ein OpenAI-Konto mit aktivierter Abrechnung.
- **Google Gemini** (`GEMINI_API_KEY`) – Modell
  `gemini-2.0-flash-preview-image-generation`, mit kleinem Gratis-Kontingent.

Mit `IMAGE_PROVIDER=auto` (Standard) wählt das Studio automatisch den
vorhandenen Anbieter.

## Aufbau

| Datei | Zweck |
|-------|-------|
| `server.py` | FastAPI-Webserver + JSON-API |
| `generator.py` | KI-Logik (Claude) inkl. Demo-Fallback |
| `static/index.html` | Oberfläche |
| `static/style.css` | Anime-Design |
| `static/app.js` | Player & Steuerung |
| `data/` | gespeicherte Serien (nicht im Git) |
