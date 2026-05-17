"""Wetter über Open-Meteo – kostenlos, ohne API-Key.

Liefert aktuelle Werte + Vorschau für heute/morgen, fertig für die
Anzeige im Dashboard und zum Vorlesen.
"""

from __future__ import annotations

from typing import Optional

import requests

# WMO-Wettercodes → (deutscher Text, Symbol)
_WMO = {
    0:  ("Klar", "☀️"),
    1:  ("Überwiegend klar", "🌤️"),
    2:  ("Teilweise bewölkt", "⛅"),
    3:  ("Bedeckt", "☁️"),
    45: ("Nebel", "🌫️"),
    48: ("Reifnebel", "🌫️"),
    51: ("Leichter Niesel", "🌦️"),
    53: ("Niesel", "🌦️"),
    55: ("Starker Niesel", "🌧️"),
    61: ("Leichter Regen", "🌦️"),
    63: ("Regen", "🌧️"),
    65: ("Starker Regen", "🌧️"),
    66: ("Gefrierender Regen", "🌧️"),
    67: ("Starker gefr. Regen", "🌧️"),
    71: ("Leichter Schnee", "🌨️"),
    73: ("Schnee", "🌨️"),
    75: ("Starker Schnee", "❄️"),
    77: ("Schneegriesel", "🌨️"),
    80: ("Leichte Schauer", "🌦️"),
    81: ("Schauer", "🌧️"),
    82: ("Heftige Schauer", "⛈️"),
    85: ("Schneeschauer", "🌨️"),
    86: ("Starke Schneeschauer", "❄️"),
    95: ("Gewitter", "⛈️"),
    96: ("Gewitter mit Hagel", "⛈️"),
    99: ("Schweres Gewitter", "⛈️"),
}


def describe(code: int) -> tuple[str, str]:
    return _WMO.get(int(code), ("Unbekannt", "•"))


def get_weather(lat: float, lon: float, city: str = "") -> Optional[dict]:
    """Holt aktuelles Wetter + Min/Max heute & morgen. None bei Fehler."""
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code,wind_speed_10m,"
                           "relative_humidity_2m,apparent_temperature",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                "forecast_days": 2,
                "timezone": "auto",
            },
            timeout=10,
        )
        resp.raise_for_status()
        d = resp.json()
    except Exception:
        return None

    cur = d.get("current", {})
    daily = d.get("daily", {})
    code = cur.get("weather_code", 0)
    desc, icon = describe(code)

    def _day(i):
        try:
            dcode = daily["weather_code"][i]
            ddesc, dicon = describe(dcode)
            return {
                "max": round(daily["temperature_2m_max"][i]),
                "min": round(daily["temperature_2m_min"][i]),
                "desc": ddesc, "icon": dicon,
            }
        except (KeyError, IndexError, TypeError):
            return None

    return {
        "city": city,
        "temp": round(cur.get("temperature_2m", 0)),
        "feels": round(cur.get("apparent_temperature", 0)),
        "desc": desc,
        "icon": icon,
        "wind": round(cur.get("wind_speed_10m", 0)),
        "humidity": round(cur.get("relative_humidity_2m", 0)),
        "today": _day(0),
        "tomorrow": _day(1),
    }


def get_weather_text(lat: float, lon: float, city: str = "") -> str:
    w = get_weather(lat, lon, city)
    if not w:
        return "Wetterdaten sind gerade nicht verfügbar."
    place = f"in {w['city']} " if w["city"] else ""
    txt = (f"Aktuell {place}{w['temp']} Grad, {w['desc']}, "
           f"gefühlt {w['feels']} Grad, Wind {w['wind']} km/h.")
    if w["today"]:
        txt += f" Heute {w['today']['min']} bis {w['today']['max']} Grad."
    if w["tomorrow"]:
        txt += (f" Morgen {w['tomorrow']['desc']}, "
                f"{w['tomorrow']['min']} bis {w['tomorrow']['max']} Grad.")
    return txt
