"""Mikrofon-Aufnahme + Whisper-Transkription.

Nimmt für eine bestimmte Dauer Audio vom Standard-Mikrofon auf und gibt
das transkribierte Deutsch als String zurück. Das Whisper-Modell wird
einmal geladen und dann wiederverwendet.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import whisper
from scipy.io import wavfile

from config import get_config


class Listener:
    """Hört über das Mikrofon und transkribiert mit Whisper."""

    def __init__(self) -> None:
        cfg = get_config()
        self._sample_rate = cfg.sample_rate
        self._language = cfg.whisper_language
        # Whisper-Modell beim Start einmal laden – das dauert paar Sekunden
        print(f"[Listener] Lade Whisper-Modell '{cfg.whisper_model}' ...")
        self._model = whisper.load_model(cfg.whisper_model)
        print("[Listener] Whisper bereit.")

    def record(self, seconds: float) -> np.ndarray:
        """Nimmt `seconds` Sekunden vom Standard-Mikrofon auf (Mono, 16 kHz)."""
        frames = int(seconds * self._sample_rate)
        audio = sd.rec(
            frames,
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
        )
        sd.wait()
        return audio.flatten()

    def transcribe(self, audio: np.ndarray) -> str:
        """Transkribiert Audio (int16, Mono) zu Deutsch mit Whisper."""
        # Whisper erwartet float32 im Bereich [-1.0, 1.0]
        audio_float = audio.astype(np.float32) / 32768.0
        result = self._model.transcribe(
            audio_float,
            language=self._language,
            fp16=False,
        )
        return str(result.get("text", "")).strip()

    def listen_and_transcribe(self, seconds: float) -> str:
        """Bequeme Methode: Aufnahme + Transkription in einem Schritt."""
        audio = self.record(seconds)
        return self.transcribe(audio)

    @staticmethod
    def save_wav(audio: np.ndarray, path: Optional[Path] = None) -> Path:
        """Speichert eine Aufnahme zur Diagnose als WAV-Datei."""
        if path is None:
            path = Path(tempfile.gettempdir()) / "jarvis_last.wav"
        cfg = get_config()
        wavfile.write(str(path), cfg.sample_rate, audio)
        return path
