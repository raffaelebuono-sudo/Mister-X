"""Sprachausgabe für JARVIS.

Bevorzugt ElevenLabs (natürliche deutsche Stimme), fällt sonst auf den
macOS `say`-Befehl zurück. Probiert mehrere deutsche Stimmen durch
('Anna', 'Petra', 'Yannick', 'Markus') und nimmt zur Not die System-
Standardstimme – damit JARVIS nie stumm bleibt.
"""

from __future__ import annotations

import shutil
import subprocess

from config import get_config

# Bevorzugte deutsche macOS-Stimmen, in Reihenfolge der Präferenz.
GERMAN_VOICES = ("Anna", "Petra", "Yannick", "Markus", "Helena")


class Speaker:
    """Spricht Texte über den Lautsprecher aus."""

    def __init__(self) -> None:
        cfg = get_config()
        self._eleven_key = cfg.elevenlabs_api_key
        self._eleven_voice = cfg.elevenlabs_voice_id
        self._eleven_client = None
        if self._eleven_key and self._eleven_voice:
            self._eleven_client = self._init_elevenlabs(self._eleven_key)
        # Beim ersten Aufruf wird die beste verfügbare Stimme bestimmt.
        self._cached_voice: str | None = None

    @staticmethod
    def _init_elevenlabs(api_key: str):
        try:
            from elevenlabs.client import ElevenLabs
            return ElevenLabs(api_key=api_key)
        except ImportError:
            print("[Speaker] elevenlabs nicht installiert – nutze macOS 'say'.")
            return None

    def say(self, text: str) -> None:
        """Sprich `text` aus. Wirft keine Ausnahme, wenn kein Audio möglich ist."""
        if not text:
            return
        if self._eleven_client is not None:
            try:
                self._say_elevenlabs(text)
                return
            except Exception as exc:
                print(f"[Speaker] ElevenLabs-Fehler: {exc} – nutze 'say' als Fallback.")
        self._say_macos(text)

    def _say_elevenlabs(self, text: str) -> None:
        from elevenlabs import play
        audio = self._eleven_client.text_to_speech.convert(
            voice_id=self._eleven_voice,
            model_id="eleven_multilingual_v2",
            text=text,
        )
        play(audio)

    def _say_macos(self, text: str) -> None:
        # Auf macOS: 'say' mit einer deutschen Stimme, Fallback auf System-Default.
        # Auf anderen Systemen: nur ausgeben, kein Audio.
        if not shutil.which("say"):
            print(f"[JARVIS spricht] {text}")
            return

        voice = self._cached_voice or self._pick_voice()
        if voice:
            result = subprocess.run(
                ["say", "-v", voice, text], capture_output=True, text=True,
            )
            if result.returncode == 0:
                self._cached_voice = voice
                return
            print(f"[Speaker] 'say -v {voice}' fehlgeschlagen ({result.stderr.strip()})"
                  f" – nutze System-Stimme.")

        # Letzter Fallback: ohne -v, nimmt die System-Standardstimme.
        result = subprocess.run(["say", text], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[Speaker] 'say' insgesamt fehlgeschlagen: {result.stderr.strip()}")
            print(f"[JARVIS spricht] {text}")

    def _pick_voice(self) -> str | None:
        """Bestimmt die erste verfügbare deutsche Stimme."""
        try:
            result = subprocess.run(
                ["say", "-v", "?"], capture_output=True, text=True, check=False,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None
        installed = {
            line.split()[0]
            for line in result.stdout.splitlines()
            if line.strip()
        }
        for voice in GERMAN_VOICES:
            if voice in installed:
                return voice
        return None
