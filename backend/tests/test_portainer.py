"""Portainer adapter tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.adapters.portainer import PortainerAdapter
from app.schemas import ServiceStatus


@pytest.mark.asyncio
async def test_portainer_not_configured():
    snap = await PortainerAdapter(base_url=None).fetch()
    assert snap.status == ServiceStatus.NOT_CONFIGURED


@pytest.mark.asyncio
async def test_portainer_online_disables_tls_verify():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch(
        "app.adapters.portainer.httpx.AsyncClient", return_value=mock_client
    ) as client_cls:
        snap = await PortainerAdapter(base_url="https://portainer.local:9443").fetch()

    client_cls.assert_called_once()
    kwargs = client_cls.call_args.kwargs
    assert kwargs.get("verify") is False
    assert snap.status == ServiceStatus.ONLINE
    assert snap.error is None


@pytest.mark.asyncio
async def test_portainer_ssl_error_surfaces_as_unavailable():
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get = AsyncMock(
        side_effect=httpx.ConnectError("CERTIFICATE_VERIFY_FAILED")
    )

    with patch("app.adapters.portainer.httpx.AsyncClient", return_value=mock_client):
        snap = await PortainerAdapter(base_url="https://portainer.local:9443").fetch()

    assert snap.status == ServiceStatus.DEGRADED
    assert snap.status_label == "Unavailable"
    assert "CERTIFICATE_VERIFY_FAILED" in (snap.error or "")
