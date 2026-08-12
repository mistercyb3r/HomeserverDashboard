"""Tailscale adapter tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.tailscale import TailscaleAdapter
from app.schemas import ServiceStatus


@pytest.mark.asyncio
async def test_tailscale_not_configured():
    snap = await TailscaleAdapter(enabled=False, socket_path=None).fetch()
    assert snap.status == ServiceStatus.NOT_CONFIGURED


@pytest.mark.asyncio
async def test_tailscale_missing_socket():
    with patch("app.adapters.tailscale.os.path.exists", return_value=False):
        snap = await TailscaleAdapter(
            enabled=True, socket_path="/tmp/missing.sock"
        ).fetch()
    assert snap.status == ServiceStatus.DEGRADED
    assert "socket" in (snap.error or "").lower()


@pytest.mark.asyncio
async def test_tailscale_parses_status():
    payload = {
        "Version": "1.66.0-abc",
        "BackendState": "Running",
        "Self": {
            "HostName": "homeserver",
            "DNSName": "homeserver.tailnet.ts.net.",
            "Online": True,
            "TailscaleIPs": ["100.64.1.2"],
            "RxBytes": 2048,
            "TxBytes": 1024,
        },
        "Peer": {
            "a": {"HostName": "laptop", "Online": True},
            "b": {"HostName": "phone", "Online": False},
        },
        "CurrentTailnet": {"Name": "example.ts.net"},
    }
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = payload
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get = AsyncMock(return_value=mock_response)

    with (
        patch("app.adapters.tailscale.os.path.exists", return_value=True),
        patch("app.adapters.tailscale.httpx.AsyncHTTPTransport"),
        patch("app.adapters.tailscale.httpx.AsyncClient", return_value=mock_client),
    ):
        snap = await TailscaleAdapter(
            enabled=True, socket_path="/var/run/tailscale/tailscaled.sock"
        ).fetch()

    assert snap.status == ServiceStatus.ONLINE
    assert snap.status_label == "Connected"
    assert snap.version == "1.66.0"
    by_key = {m.key: m for m in snap.metrics}
    assert by_key["ip"].display == "100.64.1.2"
    assert by_key["peers"].display == "1 online / 2"
    assert by_key["hostname"].display == "homeserver"
