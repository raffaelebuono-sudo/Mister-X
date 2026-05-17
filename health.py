"""Selbst-Überwachung und Ausfall-Resilienz für JARVIS.

Kernidee für Autonomie: JARVIS darf bei Internet-/API-Ausfällen NICHT
abstürzen. Stattdessen:
  - erkennt er den Zustand (online/offline, API ok/down),
  - wiederholt Aufrufe mit exponentiellem Backoff,
  - degradiert sauber (sagt Bescheid statt zu crashen),
  - meldet seinen Gesundheitszustand ans Dashboard.

`HealthMonitor` hält den Zustand, `resilient()` umhüllt riskante Calls.
"""

from __future__ import annotations

import socket
import threading
import time
from datetime import datetime
from typing import Any, Callable, Optional


class OfflineError(RuntimeError):
    """Wird geworfen, wenn ein Cloud-Call nach allen Retries scheitert."""


def is_online(host: str = "1.1.1.1", port: int = 53, timeout: float = 3.0) -> bool:
    """Schneller TCP-Connectivity-Check ohne externe Abhängigkeit."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _is_network_error(exc: BaseException) -> bool:
    """Heuristik: ist die Ausnahme ein vorübergehendes Netzwerk-/API-Problem?"""
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    network_markers = (
        "connection", "timeout", "timed out", "temporarily",
        "unavailable", "overloaded", "rate", "503", "502", "529",
        "apiconnection", "apitimeout", "apistatus",
    )
    return any(m in name for m in network_markers) or \
           any(m in msg for m in network_markers)


class HealthMonitor:
    def __init__(self, bus=None) -> None:
        self._bus = bus
        self._lock = threading.Lock()
        self.online: bool = True
        self.api_ok: bool = True
        self.last_api_success: Optional[datetime] = None
        self.last_api_error: Optional[str] = None
        self.consecutive_failures: int = 0
        self.total_failures: int = 0
        self.degraded_mode: bool = False

    # --- Zustandsänderungen ---

    def record_success(self) -> None:
        with self._lock:
            self.api_ok = True
            self.online = True
            self.last_api_success = datetime.now()
            self.consecutive_failures = 0
            if self.degraded_mode:
                self.degraded_mode = False
                self._emit("API wieder erreichbar – Normalbetrieb.")

    def record_failure(self, exc: BaseException) -> None:
        with self._lock:
            self.consecutive_failures += 1
            self.total_failures += 1
            self.last_api_error = f"{type(exc).__name__}: {exc}"
            # Nach 2 Fehlern in Folge: Online-Status aktiv prüfen
            if self.consecutive_failures >= 2:
                self.online = is_online()
                self.api_ok = False
                if not self.degraded_mode:
                    self.degraded_mode = True
                    self._emit(
                        "Eingeschränkter Modus – Cloud nicht erreichbar."
                    )

    def status(self) -> dict:
        return {
            "online": self.online,
            "api_ok": self.api_ok,
            "degraded": self.degraded_mode,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "last_api_success": (
                self.last_api_success.isoformat(timespec="seconds")
                if self.last_api_success else None
            ),
            "last_api_error": self.last_api_error,
        }

    def _emit(self, message: str) -> None:
        print(f"[Health] {message}")
        if self._bus is not None:
            try:
                self._bus.push_brain("health", message)
                self._bus.publish({"type": "health", "health": self.status()})
            except Exception:
                pass

    # --- Resilienter Aufruf ---

    def resilient(
        self,
        fn: Callable[[], Any],
        *,
        retries: int = 3,
        base_delay: float = 2.0,
        label: str = "Aufruf",
    ) -> Any:
        """Führt `fn` aus, mit Retry/Backoff bei Netzwerkfehlern.

        Erfolgsfall: Ergebnis zurück, Health auf 'gesund'.
        Dauerhafter Netzwerkfehler: OfflineError.
        Anderer Fehler (Bug, ungültige Eingabe): sofort weiterreichen.
        """
        last_exc: Optional[BaseException] = None
        for attempt in range(retries):
            try:
                result = fn()
                self.record_success()
                return result
            except Exception as exc:  # noqa: BLE001 – wir klassifizieren selbst
                if not _is_network_error(exc):
                    # Echter Programmfehler – nicht endlos retryen.
                    raise
                last_exc = exc
                self.record_failure(exc)
                if attempt < retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"[Health] {label} fehlgeschlagen "
                          f"(Versuch {attempt + 1}/{retries}), "
                          f"erneuter Versuch in {delay:.0f}s …")
                    time.sleep(delay)
        raise OfflineError(
            f"{label} nach {retries} Versuchen nicht erreichbar."
        ) from last_exc
