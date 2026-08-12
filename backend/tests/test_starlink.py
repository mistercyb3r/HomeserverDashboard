"""Starlink adapter unit tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.starlink import StarlinkAdapter
from app.schemas import ServiceStatus


@pytest.mark.asyncio
async def test_starlink_not_configured():
    adapter = StarlinkAdapter(starpulse_url=None)
    snap = await adapter.fetch()
    assert snap.status == ServiceStatus.NOT_CONFIGURED


@pytest.mark.asyncio
async def test_starlink_parses_status():
    health = MagicMock(status_code=200)
    health.json.return_value = {"status": "ok"}

    status = MagicMock(status_code=200)
    status.json.return_value = {
        "connection_state": "CONNECTED",
        "download_bps": 280_000_000,
        "upload_bps": 32_000_000,
        "latency_ms": 38.2,
        "ping_drop_rate": 0.012,
        "uptime_seconds": 3600,
        "software_version": "2024.01",
    }

    outages = MagicMock(status_code=200)
    outages.json.return_value = {
        "outages_today": 1,
        "outages_last_7d": 3,
        "total_downtime_minutes_last_7d": 12.5,
        "events": [],
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[health, status, outages])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.adapters.starlink.httpx.AsyncClient", return_value=mock_client):
        adapter = StarlinkAdapter(starpulse_url="http://starpulse.local:8000")
        snap = await adapter.fetch()

    assert snap.status == ServiceStatus.ONLINE
    assert snap.status_label == "Connected"
    by_key = {m.key: m for m in snap.metrics}
    assert by_key["download"].available is True
    assert by_key["download"].display == "↓ 280 Mbps"
    assert by_key["latency"].display == "38 ms"
    assert by_key["packet_loss"].available is True
    assert snap.url == "http://starpulse.local:8000"
    assert snap.open_label == "Open StarPulse"
