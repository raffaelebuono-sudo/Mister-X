"""Read-only System-Inspektion für den Security-Watcher und für JARVIS allgemein.

Liefert kompakte, vorlesbare Strings (Top-Prozesse, aktive
Netzwerkverbindungen, jüngste Logins). Alle Funktionen sind reine
Read-only-Abfragen über psutil – keine Eingriffe ins System.
"""

from __future__ import annotations

import subprocess
from typing import List

import psutil


def top_processes(limit: int = 10, sort_by: str = "cpu") -> str:
    """Top-N Prozesse nach CPU oder RAM."""
    snapshot: List[dict] = []
    for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info", "exe"]):
        try:
            info = p.info
            mem_mb = (info.get("memory_info").rss / (1024 * 1024)
                      if info.get("memory_info") else 0)
            snapshot.append({
                "pid": info.get("pid"),
                "name": info.get("name") or "?",
                "user": info.get("username") or "?",
                "cpu": info.get("cpu_percent") or 0.0,
                "mem_mb": mem_mb,
                "exe": info.get("exe") or "",
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    key = "cpu" if sort_by != "ram" else "mem_mb"
    snapshot.sort(key=lambda x: x[key], reverse=True)
    rows = snapshot[: max(1, min(limit, 50))]

    lines = [f"Top-{len(rows)} Prozesse nach {sort_by.upper()}:"]
    for r in rows:
        lines.append(
            f"  PID {r['pid']:>6}  {r['name'][:24]:<24}  "
            f"CPU {r['cpu']:>5.1f}%  RAM {r['mem_mb']:>7.1f}MB  "
            f"({r['user']})"
        )
    return "\n".join(lines)


def network_connections(limit: int = 15) -> str:
    """Aktive Netzwerkverbindungen (TCP/UDP)."""
    try:
        conns = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        return ("Zugriff auf Netzwerkverbindungen verweigert. "
                "Auf macOS: Terminal/Python in Bedienungshilfen erlauben.")

    rows = []
    for c in conns:
        if not c.raddr:
            continue
        try:
            pname = psutil.Process(c.pid).name() if c.pid else "?"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pname = "?"
        rows.append({
            "pid": c.pid or 0, "name": pname,
            "local": f"{c.laddr.ip}:{c.laddr.port}",
            "remote": f"{c.raddr.ip}:{c.raddr.port}",
            "status": c.status,
        })

    rows.sort(key=lambda x: x["name"])
    rows = rows[:limit]

    if not rows:
        return "Keine offenen Verbindungen."
    lines = [f"Aktive Netzwerk-Verbindungen ({len(rows)}):"]
    for r in rows:
        lines.append(
            f"  {r['name'][:20]:<20} PID {r['pid']:>6}  "
            f"{r['local']} → {r['remote']}  {r['status']}"
        )
    return "\n".join(lines)


def recent_logins(limit: int = 10) -> str:
    """Jüngste Logins auf dem Mac (über `last`-Befehl)."""
    try:
        result = subprocess.run(
            ["last", "-{}".format(int(limit))],
            capture_output=True, text=True, timeout=5,
        )
    except Exception as exc:
        return f"Konnte 'last' nicht ausführen: {exc}"
    if result.returncode != 0:
        return f"'last' meldet Fehler: {result.stderr.strip()}"
    return f"Jüngste Logins:\n{result.stdout.strip()}"


def listening_ports() -> str:
    """Welche Programme lauschen auf welchen Ports?"""
    try:
        conns = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        return "Zugriff verweigert."
    rows = []
    seen = set()
    for c in conns:
        if c.status != "LISTEN":
            continue
        key = (c.laddr.port, c.pid)
        if key in seen:
            continue
        seen.add(key)
        try:
            pname = psutil.Process(c.pid).name() if c.pid else "?"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pname = "?"
        rows.append((c.laddr.port, pname, c.pid or 0))
    rows.sort()
    if not rows:
        return "Keine offenen Listening-Ports."
    lines = ["Listening Ports:"]
    for port, name, pid in rows:
        lines.append(f"  :{port:<5}  {name[:24]:<24} (PID {pid})")
    return "\n".join(lines)
