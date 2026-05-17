"""Sprachausgabe für JARVIS.

Priorität:
  1. ElevenLabs (natürliche Premium-Stimme) – sobald ein API-Key
     gesetzt ist. Eine voice_id ist optional; fehlt sie, wählt JARVIS
     automatisch die erste Stimme aus dem Konto.
  2. macOS `say` mit der besten verfügbaren deutschen Stimme
     (oder einer erzwungenen Stimme aus cfg.mac_voice).
  3. Reine Textausgabe, falls gar kein Audio möglich ist.
So bleibt JARVIS nie stumm.
"""

from __future__ import annotations

import shutil
import subprocess

from config import get_config

GERMAN_VOICES = ("Anna", "Petra", "Yannick", "Markus", "Helena")


class Speaker:
    def __init__(self) -> None:
        cfg = get_config()
        self._cfg = cfg
        self._eleven_key = cfg.elevenlabs_api_key
        self._eleven_voice = cfg.elevenlabs_voice_id
        self._eleven_model = cfg.elevenlabs_model
        self._eleven_client = None
        if self._eleven_key:
            self._eleven_client = self._init_elevenlabs(self._eleven_key)
        self._cached_voice: str | None = None

    # --- ElevenLabs ---

    def _init_elevenlabs(self, api_key: str):
        try:
            from elevenlabs.client import ElevenLabs
        except ImportError:
            print("[Speaker] Paket 'elevenlabs' nicht installiert "
                  "(pip install elevenlabs) – nutze macOS-Stimme.")
            return None
        try:
            client = ElevenLabs(api_key=api_key)
            if not self._eleven_voice:
                # Keine voice_id gesetzt → erste Stimme aus dem Konto.
                voices = client.voices.get_all().voices
                if voices:
                    self._eleven_voice = voices[0].voice_id
                    print(f"[Speaker] ElevenLabs-Stimme automatisch gewählt: "
                          f"{getattr(voices[0], 'name', self._eleven_voice)}")
            return client
        except Exception as exc:
            print(f"[Speaker] ElevenLabs-Init fehlgeschlagen: {exc} "
                  f"– nutze macOS-Stimme.")
            return None

    def _say_elevenlabs(self, text: str) -> None:
        from elevenlabs import play
        # Ausdrucksstarke Einstellung: niedrige stability = lebendiger
        # (nicht monoton/tot), style hebt die Betonung, speaker_boost
        # macht die Stimme präsenter.
        settings = {
            "stability": 0.35,
            "similarity_boost": 0.85,
            "style": 0.45,
            "use_speaker_boost": True,
        }
        try:
            audio = self._eleven_client.text_to_speech.convert(
                voice_id=self._eleven_voice,
                model_id=self._eleven_model,
                text=text,
                voice_settings=settings,
            )
        except TypeError:
            # Ältere SDK-Signatur ohne voice_settings-Kwarg.
            audio = self._eleven_client.text_to_speech.convert(
                voice_id=self._eleven_voice,
                model_id=self._eleven_model,
                text=text,
            )
        play(audio)

    # --- öffentliche API ---

    def say(self, text: str) -> None:
        if not text:
            return
        if self._eleven_client is not None and self._eleven_voice:
            try:
                self._say_elevenlabs(text)
                return
            except Exception as exc:
                print(f"[Speaker] ElevenLabs-Fehler: {exc} – Fallback 'say'.")
        self._say_macos(text)

    # --- macOS say ---

    def _say_macos(self, text: str) -> None:
        if not shutil.which("say"):
            print(f"[JARVIS spricht] {text}")
            return
        voice = self._cfg.mac_voice or self._cached_voice or self._pick_voice()
        if voice:
            result = subprocess.run(
                ["say", "-v", voice, text], capture_output=True, text=True,
            )
            if result.returncode == 0:
                self._cached_voice = voice
                return
            print(f"[Speaker] 'say -v {voice}' fehlgeschlagen "
                  f"({result.stderr.strip()}) – System-Stimme.")
        result = subprocess.run(["say", text], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[JARVIS spricht] {text}")

    def _pick_voice(self) -> str | None:
        try:
            result = subprocess.run(
                ["say", "-v", "?"], capture_output=True, text=True, check=False,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None
        installed = {
            line.split()[0] for line in result.stdout.splitlines() if line.strip()
        }
        for voice in GERMAN_VOICES:
            if voice in installed:
                return voice
        return None
