"""Sprachausgabe für JARVIS.

Bevorzugt ElevenLabs (natürliche deutsche Stimme), fällt sonst auf den
macOS `say`-Befehl mit der deutschen Stimme „Anna" zurück.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Optional

from config import get_config


class Speaker:
    """Spricht Texte über den Lautsprecher aus."""

    def __init__(self) -> None:
        cfg = get_config()
        self._eleven_key = cfg.elevenlabs_api_key
        self._eleven_voice = cfg.elevenlabs_voice_id
        self._eleven_client = None
        if self._eleven_key and self._eleven_voice:
            self._eleven_client = self._init_elevenlabs(self._eleven_key)

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

    @staticmethod
    def _say_macos(text: str) -> None:
        # Auf macOS: 'say -v Anna' für deutsche Stimme.
        # Auf anderen Systemen: nur ausgeben, kein Audio.
        if shutil.which("say"):
            subprocess.run(["say", "-v", "Anna", text], check=False)
        else:
            print(f"[JARVIS spricht] {text}")
