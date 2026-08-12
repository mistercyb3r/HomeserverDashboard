"""API and health aggregation tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.adapters.base import metric
from app.dashboard import compute_system_health
from app.schemas import ServiceSnapshot, ServiceStatus, SystemHealthLevel


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "1.1.1"


def test_dashboard_includes_server(client):
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    payload = response.json()
    assert "system_health" in payload
    assert "overview" in payload
    assert "storage" in payload
    assert isinstance(payload["storage"], list)
    ids = [s["id"] for s in payload["services"]]
    assert "server" in ids
    server = next(s for s in payload["services"] if s["id"] == "server")
    assert server["status"] in {"online", "degraded"}
    assert server.get("uptime")
    assert server["metrics"]
    for m in server["metrics"]:
        assert "last_updated" not in m
        assert "available" in m
        if not m["available"]:
            assert m["display"] in {"Unavailable", "Not configured", "Not available"}
    assert "weather" in payload
    assert "quick_links" in payload
    assert payload.get("app_version") == "1.1.1"
    overview_keys = [m["key"] for m in payload["overview"]]
    assert "cpu" in overview_keys
    assert "ram" in overview_keys
    assert "temp" in overview_keys
    assert "uptime" in overview_keys
    temp = next(m for m in server["metrics"] if m["key"] == "temp")
    if not temp["available"]:
        assert temp["display"] == "Not available"
        assert server["status"] in {"online", "degraded"}
    if payload["storage"]:
        mount = payload["storage"][0]
        assert "mountpoint" in mount
        assert "percent" in mount
        assert "free_display" in mount
        assert "summary" in mount
        assert mount["mountpoint"] not in {
            "/etc/hostname",
            "/etc/hosts",
            "/etc/resolv.conf",
            "/data",
        }


def test_settings_lists_future_services(client):
    response = client.get("/api/settings")
    assert response.status_code == 200
    payload = response.json()
    ids = {s["id"] for s in payload["services"]}
    assert "jellyfin" in ids
    assert "docker" in ids
    assert "portainer" in ids
    assert "immich" in ids
    docker = next(s for s in payload["services"] if s["id"] == "docker")
    assert docker["implemented"] is True
    assert docker["config_kind"] == "socket"
    portainer = next(s for s in payload["services"] if s["id"] == "portainer")
    assert portainer["implemented"] is True
    immich = next(s for s in payload["services"] if s["id"] == "immich")
    assert immich["implemented"] is False
    assert immich["enabled"] is False


def test_settings_toggle_service(client):
    response = client.put(
        "/api/settings",
        json={"services": {"jellyfin": {"enabled": False}}},
    )
    assert response.status_code == 200
    jellyfin = next(s for s in response.json()["services"] if s["id"] == "jellyfin")
    assert jellyfin["enabled"] is False

    dashboard = client.get("/api/dashboard").json()
    assert all(s["id"] != "jellyfin" for s in dashboard["services"])


def test_unconfigured_jellyfin_and_starpulse(client, monkeypatch):
    monkeypatch.delenv("JELLYFIN_URL", raising=False)
    monkeypatch.delenv("STARPULSE_URL", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()

    # Ensure config has no URLs
    client.put(
        "/api/settings",
        json={
            "services": {
                "jellyfin": {"enabled": True, "url": None},
                "starpulse": {"enabled": True, "url": None},
                "starlink": {"enabled": True, "url": None},
            }
        },
    )
    dashboard = client.get("/api/dashboard").json()
    by_id = {s["id"]: s for s in dashboard["services"]}
    assert by_id["jellyfin"]["status"] == "not_configured"
    assert by_id["starpulse"]["status"] == "not_configured"
    assert by_id["starlink"]["status"] == "not_configured"


def _snap(service_id: str, status: ServiceStatus) -> ServiceSnapshot:
    return ServiceSnapshot(
        id=service_id,
        name=service_id.title(),
        status=status,
        status_label=status.value,
        metrics=[metric("x", "X", 1)],
        last_updated=datetime.now(UTC),
    )


def test_system_health_operational():
    health = compute_system_health(
        [_snap("server", ServiceStatus.ONLINE), _snap("jellyfin", ServiceStatus.ONLINE)]
    )
    assert health.level == SystemHealthLevel.OPERATIONAL
    assert "operational" in health.label.lower()


def test_system_health_attention():
    health = compute_system_health(
        [
            _snap("server", ServiceStatus.ONLINE),
            _snap("starlink", ServiceStatus.DEGRADED),
        ]
    )
    assert health.level == SystemHealthLevel.ATTENTION
    assert "attention" in health.label.lower()


def test_system_health_critical():
    health = compute_system_health(
        [
            _snap("server", ServiceStatus.ONLINE),
            _snap("jellyfin", ServiceStatus.OFFLINE),
        ]
    )
    assert health.level == SystemHealthLevel.CRITICAL
    assert "offline" in health.label.lower()


def test_system_health_ignores_unconfigured():
    health = compute_system_health(
        [
            _snap("server", ServiceStatus.ONLINE),
            _snap("jellyfin", ServiceStatus.NOT_CONFIGURED),
            _snap("starpulse", ServiceStatus.NOT_CONFIGURED),
        ]
    )
    assert health.level == SystemHealthLevel.OPERATIONAL
    assert health.not_configured_count == 2


def test_system_health_only_unconfigured():
    health = compute_system_health(
        [
            _snap("jellyfin", ServiceStatus.NOT_CONFIGURED),
            _snap("starpulse", ServiceStatus.NOT_CONFIGURED),
        ]
    )
    assert health.level == SystemHealthLevel.UNKNOWN
    assert "configured" in health.label.lower()


@pytest.mark.asyncio
async def test_jellyfin_adapter_not_configured():
    from app.adapters.jellyfin import JellyfinAdapter

    adapter = JellyfinAdapter(base_url=None, api_key=None)
    snap = await adapter.fetch()
    assert snap.status == ServiceStatus.NOT_CONFIGURED


@pytest.mark.asyncio
async def test_starpulse_adapter_parses_health(httpx_mock=None):
    pytest.importorskip("httpx")
    from unittest.mock import MagicMock, patch

    from app.adapters.starpulse import StarPulseAdapter

    health_payload = {
        "status": "ok",
        "version": "1.0.0",
        "uptime_seconds": 12,
        "setup_complete": True,
        "starlink_connected": True,
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = health_payload

    about_response = MagicMock()
    about_response.status_code = 200
    about_response.json.return_value = {
        "version": "1.0.0",
        "uptime_seconds": 187200,
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[mock_response, about_response])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.adapters.starpulse.httpx.AsyncClient", return_value=mock_client):
        adapter = StarPulseAdapter(base_url="http://starpulse.local:8000")
        snap = await adapter.fetch()

    assert snap.status == ServiceStatus.ONLINE
    assert snap.version == "1.0.0"
    assert snap.uptime == "2d 4h"
    assert snap.href == "http://starpulse.local:8000"
    starlink_metric = next(m for m in snap.metrics if m.key == "starlink")
    assert starlink_metric.available is True
    assert "connected" in starlink_metric.display.lower()
