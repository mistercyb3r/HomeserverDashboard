"""Lightweight weather via Open-Meteo (no API key, short in-memory cache)."""

from __future__ import annotations

import time
from threading import Lock
from typing import Any

import httpx

from app.schemas import WeatherInfo

# WMO weather interpretation codes → compact label + emoji.
_WMO: dict[int, tuple[str, str]] = {
    0: ("Clear", "☀️"),
    1: ("Mainly clear", "🌤"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Fog", "🌫"),
    48: ("Fog", "🌫"),
    51: ("Drizzle", "🌦"),
    53: ("Drizzle", "🌦"),
    55: ("Drizzle", "🌦"),
    61: ("Rain", "🌧"),
    63: ("Rain", "🌧"),
    65: ("Rain", "🌧"),
    71: ("Snow", "❄️"),
    73: ("Snow", "❄️"),
    75: ("Snow", "❄️"),
    80: ("Showers", "🌦"),
    81: ("Showers", "🌦"),
    82: ("Showers", "🌧"),
    95: ("Thunderstorm", "⛈"),
    96: ("Thunderstorm", "⛈"),
    99: ("Thunderstorm", "⛈"),
}

_lock = Lock()
_cache: dict[str, Any] = {"expires_at": 0.0, "payload": None, "key": None}


def _unavailable(location: str, error: str | None = None) -> WeatherInfo:
    return WeatherInfo(
        available=False,
        location=location,
        error=error or "Weather unavailable",
    )


def _wmo_label(code: int | None) -> tuple[str | None, str | None]:
    if code is None:
        return None, None
    try:
        entry = _WMO.get(int(code))
    except (TypeError, ValueError):
        return None, None
    if not entry:
        return "Weather", "🌤"
    return entry[0], entry[1]


async def _geocode(
    client: httpx.AsyncClient, location: str
) -> tuple[float, float, str] | None:
    response = await client.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": location, "count": 1, "language": "en", "format": "json"},
    )
    response.raise_for_status()
    results = (response.json() or {}).get("results") or []
    if not results:
        return None
    row = results[0]
    lat = float(row["latitude"])
    lon = float(row["longitude"])
    parts = [
        str(row.get("name") or "").strip(),
        str(row.get("admin1") or "").strip(),
        str(row.get("country_code") or row.get("country") or "").strip(),
    ]
    label = ", ".join(p for p in parts if p) or location
    return lat, lon, label


async def fetch_weather(
    *,
    location: str,
    latitude: float | None = None,
    longitude: float | None = None,
    cache_seconds: int = 600,
    timeout: float = 5.0,
    enabled: bool = True,
) -> WeatherInfo:
    """Return cached or fresh weather. Never raises."""
    display_location = (location or "Thetford, Norfolk, UK").strip() or (
        "Thetford, Norfolk, UK"
    )
    if not enabled:
        return _unavailable(display_location, "Weather disabled")

    cache_key = f"{display_location}|{latitude}|{longitude}"
    now = time.monotonic()
    with _lock:
        if (
            _cache["payload"] is not None
            and _cache["key"] == cache_key
            and now < float(_cache["expires_at"])
        ):
            return _cache["payload"]

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            lat = latitude
            lon = longitude
            resolved_label = display_location
            if lat is None or lon is None:
                geo = await _geocode(client, display_location)
                if geo is None:
                    return _unavailable(display_location, "Location not found")
                lat, lon, resolved_label = geo

            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,apparent_temperature,weather_code",
                    "daily": (
                        "temperature_2m_max,temperature_2m_min,"
                        "precipitation_probability_max"
                    ),
                    "forecast_days": 1,
                    "timezone": "auto",
                },
            )
            response.raise_for_status()
            payload = response.json() or {}
    except Exception as exc:  # noqa: BLE001
        return _unavailable(display_location, str(exc) or "Weather unavailable")

    current = payload.get("current") or {}
    daily = payload.get("daily") or {}
    code = current.get("weather_code")
    condition, icon = _wmo_label(code if code is not None else None)

    def _num(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return round(float(value), 1)
        except (TypeError, ValueError):
            return None

    def _first(series: Any) -> Any:
        if isinstance(series, list) and series:
            return series[0]
        return None

    temp = _num(current.get("temperature_2m"))
    feels = _num(current.get("apparent_temperature"))
    high = _num(_first(daily.get("temperature_2m_max")))
    low = _num(_first(daily.get("temperature_2m_min")))
    rain = _first(daily.get("precipitation_probability_max"))
    try:
        rain_i = int(round(float(rain))) if rain is not None else None
    except (TypeError, ValueError):
        rain_i = None

    if temp is None:
        return _unavailable(resolved_label, "Weather unavailable")

    info = WeatherInfo(
        available=True,
        location=resolved_label,
        temperature_c=temp,
        feels_like_c=feels,
        high_c=high,
        low_c=low,
        condition=condition,
        icon=icon,
        rain_probability=rain_i,
        error=None,
    )
    with _lock:
        _cache["key"] = cache_key
        _cache["payload"] = info
        _cache["expires_at"] = time.monotonic() + max(60, int(cache_seconds))
    return info


def clear_weather_cache() -> None:
    with _lock:
        _cache["expires_at"] = 0.0
        _cache["payload"] = None
        _cache["key"] = None
