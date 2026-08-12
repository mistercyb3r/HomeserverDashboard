"""Weather fetch + cache tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.weather import clear_weather_cache, fetch_weather


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_weather_cache()
    yield
    clear_weather_cache()


@pytest.mark.asyncio
async def test_weather_thetford_uses_default_coords_without_geocode():
    forecast = MagicMock()
    forecast.raise_for_status = MagicMock()
    forecast.json.return_value = {
        "current": {
            "temperature_2m": 18.2,
            "apparent_temperature": 17.1,
            "weather_code": 0,
        },
        "daily": {
            "temperature_2m_max": [21.0],
            "temperature_2m_min": [12.0],
            "precipitation_probability_max": [20],
        },
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get = AsyncMock(return_value=forecast)

    with patch("app.weather.httpx.AsyncClient", return_value=mock_client):
        info = await fetch_weather(location="Thetford, Norfolk, UK")

    assert info.available is True
    assert info.temperature_c == 18.2
    # Only forecast call — no geocode request.
    assert mock_client.get.await_count == 1
    called_url = str(mock_client.get.await_args.args[0])
    assert "forecast" in called_url


@pytest.mark.asyncio
async def test_weather_unavailable_on_http_error():
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("offline"))

    with patch("app.weather.httpx.AsyncClient", return_value=mock_client):
        info = await fetch_weather(
            location="Thetford, Norfolk, UK",
            latitude=52.41,
            longitude=0.75,
        )

    assert info.available is False
    assert "Weather unavailable" in (info.error or "") or info.error


@pytest.mark.asyncio
async def test_weather_disabled():
    info = await fetch_weather(location="Thetford, Norfolk, UK", enabled=False)
    assert info.available is False
    assert info.error == "Weather disabled"


@pytest.mark.asyncio
async def test_weather_parses_and_caches():
    forecast = MagicMock()
    forecast.raise_for_status = MagicMock()
    forecast.json.return_value = {
        "current": {
            "temperature_2m": 18.2,
            "apparent_temperature": 17.1,
            "weather_code": 0,
        },
        "daily": {
            "temperature_2m_max": [21.0],
            "temperature_2m_min": [12.0],
            "precipitation_probability_max": [20],
        },
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get = AsyncMock(return_value=forecast)

    with patch("app.weather.httpx.AsyncClient", return_value=mock_client):
        first = await fetch_weather(
            location="Thetford, Norfolk, UK",
            latitude=52.41,
            longitude=0.75,
            cache_seconds=600,
        )
        second = await fetch_weather(
            location="Thetford, Norfolk, UK",
            latitude=52.41,
            longitude=0.75,
            cache_seconds=600,
        )

    assert first.available is True
    assert first.temperature_c == 18.2
    assert first.feels_like_c == 17.1
    assert first.high_c == 21.0
    assert first.low_c == 12.0
    assert first.rain_probability == 20
    assert first.icon
    assert second.available is True
    assert mock_client.get.await_count == 1
