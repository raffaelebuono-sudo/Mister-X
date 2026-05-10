"""Einfacher Cron-ähnlicher Scheduler für Agenten.

Unterstützt zwei Schedule-Typen:
  - {"hour": 7, "minute": 0}    : jeden Tag um diese Uhrzeit
  - {"interval_minutes": 240}   : alle 240 Minuten (ab Start)

Läuft in einem eigenen Daemon-Thread und tickt einmal pro Minute.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional


class Scheduler:
    def __init__(self) -> None:
        self._jobs: List[Dict] = []
        self._last_run: Dict[str, datetime] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # --- API ---

    def add(self, name: str, spec: dict, callback: Callable[[], None]) -> None:
        self._jobs.append({"name": name, "spec": spec, "callback": callback})

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop, name="jarvis-scheduler", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def list_jobs(self) -> List[dict]:
        return [
            {
                "name": j["name"],
                "spec": j["spec"],
                "last_run": self._last_run.get(j["name"]),
            }
            for j in self._jobs
        ]

    def run_now(self, name: str) -> bool:
        for job in self._jobs:
            if job["name"] == name:
                self._safe_run(job)
                return True
        return False

    # --- intern ---

    def _loop(self) -> None:
        # Erster Tick nach 5 Sekunden, danach alle 60 Sekunden.
        time.sleep(5)
        while not self._stop.is_set():
            now = datetime.now()
            for job in self._jobs:
                if self._should_run(job, now):
                    self._safe_run(job)
            self._stop.wait(60)

    def _should_run(self, job: dict, now: datetime) -> bool:
        spec = job["spec"]
        last = self._last_run.get(job["name"])

        if "interval_minutes" in spec:
            iv = int(spec["interval_minutes"])
            if last is None:
                # Beim Start NICHT sofort triggern – erst nach erstem Intervall.
                self._last_run[job["name"]] = now
                return False
            return (now - last).total_seconds() >= iv * 60

        if "hour" in spec:
            target_h = int(spec["hour"])
            target_m = int(spec.get("minute", 0))
            if now.hour == target_h and now.minute == target_m:
                if last is None or (now - last).total_seconds() > 60:
                    return True

        return False

    def _safe_run(self, job: dict) -> None:
        try:
            job["callback"]()
        except Exception as exc:
            print(f"[Scheduler] {job['name']} fehlgeschlagen: {exc}")
        self._last_run[job["name"]] = datetime.now()
