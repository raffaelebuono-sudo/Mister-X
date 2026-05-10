"""Aktivierung: Wake-Phrase ODER Doppel-Klatschen.

Pro Audio-Chunk wird zuerst (sehr günstig) auf einen Klatsch-Peak
geprüft. Wird keiner gefunden, läuft die teurere Whisper-Transkription
und sucht nach der Wake-Phrase.

Klatsch-Detektion ist auf Doppel-Klatschen ausgelegt – zwei kurze,
laute Impulse innerhalb ~0,7 Sekunden – damit ein einzelner lauter
Knall (Tür, Stuhl) nicht versehentlich aktiviert.
"""

from __future__ import annotations

import re
from typing import Optional

import numpy as np

from config import get_config
from voice.listener import Listener


def normalize(text: str) -> str:
    return re.sub(r"[^a-zäöüß ]+", "", text.lower()).strip()


class WakeWordDetector:
    def __init__(self, listener: Listener) -> None:
        cfg = get_config()
        self._listener = listener
        self._chunk_seconds = cfg.wake_chunk_seconds
        self._wake_phrase = normalize(cfg.wake_phrase)
        self._sample_rate = cfg.sample_rate
        self._clap_enabled = cfg.clap_enabled
        self._clap_threshold = cfg.clap_threshold
        self._clap_min_count = cfg.clap_min_count
        self._clap_min_gap_ms = cfg.clap_min_gap_ms
        self._clap_max_gap_ms = cfg.clap_max_gap_ms

    def wait_for_wake(self, on_chunk: Optional[callable] = None) -> str:
        """Blockiert bis Wake-Phrase oder Klatschen erkannt wird.

        Liefert einen kurzen Hinweis-Text ('jarvis (clap)' / Transkription).
        """
        while True:
            audio = self._listener.record(self._chunk_seconds)

            # 1. Günstige Klatsch-Erkennung (Numpy, ms-schnell)
            if self._clap_enabled and self._detect_double_clap(audio):
                if on_chunk is not None:
                    on_chunk("[clap]")
                return "[clap]"

            # 2. Whisper-Transkription für Wake-Phrase
            text = self._listener.transcribe(audio)
            if on_chunk is not None:
                on_chunk(text)
            if self._contains_wake_phrase(text):
                return text

    def _contains_wake_phrase(self, text: str) -> bool:
        return self._wake_phrase in normalize(text)

    def _detect_double_clap(self, audio: np.ndarray) -> bool:
        """Sucht nach zwei kurzen, lauten Impulsen kurz hintereinander."""
        if audio.size == 0:
            return False
        # Auf [-1, 1] normalisieren, dann RMS pro 10ms-Fenster
        signal = audio.astype(np.float32) / 32768.0
        win = max(1, int(self._sample_rate * 0.01))   # 10 ms
        if signal.size < win * 3:
            return False
        # RMS-Envelope in 10ms-Schritten
        n_frames = signal.size // win
        frames = signal[: n_frames * win].reshape(n_frames, win)
        rms = np.sqrt(np.mean(frames ** 2, axis=1))

        # Peaks: lokale Maxima oberhalb des Schwellwerts mit Mindestabstand
        threshold = self._clap_threshold
        peak_indices = []
        i = 0
        min_gap = max(1, int(self._clap_min_gap_ms / 10))
        while i < rms.size:
            if rms[i] >= threshold:
                # Lokales Maximum bestimmen
                j = i
                while j + 1 < rms.size and rms[j + 1] > rms[j]:
                    j += 1
                peak_indices.append(j)
                i = j + min_gap
            else:
                i += 1

        if len(peak_indices) < self._clap_min_count:
            return False

        # Mindestens zwei Peaks innerhalb von clap_min_gap..clap_max_gap (ms)
        max_gap = max(1, int(self._clap_max_gap_ms / 10))
        for a, b in zip(peak_indices, peak_indices[1:]):
            gap = b - a
            if min_gap <= gap <= max_gap:
                return True
        return False
