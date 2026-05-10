"""System-Monitor – CPU, RAM, Akku, Festplatte, Uptime.

Liefert kompakte deutsche Strings, die JARVIS direkt vorlesen kann.
"""

from __future__ import annotations

import time
from typing import Dict

import psutil


_PROCESS_START = time.time()


def get_status() -> Dict[str, str]:
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    boot = psutil.boot_time()
    uptime = _format_duration(time.time() - boot)
    jarvis_uptime = _format_duration(time.time() - _PROCESS_START)

    battery_str = "kein Akku erkannt"
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if battery is not None:
        plug = "am Strom" if battery.power_plugged else "auf Akku"
        battery_str = f"{round(battery.percent)} Prozent, {plug}"

    return {
        "cpu": f"{cpu:.0f}%",
        "ram": f"{mem.percent:.0f}% von {_human_bytes(mem.total)}",
        "disk": f"{disk.percent:.0f}% von {_human_bytes(disk.total)} belegt",
        "battery": battery_str,
        "system_uptime": uptime,
        "jarvis_uptime": jarvis_uptime,
    }


def get_status_text() -> str:
    s = get_status()
    return (
        f"CPU: {s['cpu']}, RAM: {s['ram']}, "
        f"Festplatte: {s['disk']}, Akku: {s['battery']}, "
        f"System läuft seit {s['system_uptime']}, "
        f"JARVIS läuft seit {s['jarvis_uptime']}."
    )


def _human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} Tagen")
    if hours:
        parts.append(f"{hours} Stunden")
    if minutes or not parts:
        parts.append(f"{minutes} Minuten")
    return ", ".join(parts)
