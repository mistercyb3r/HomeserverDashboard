"""TP-Link router adapter tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.adapters.router import RouterAdapter, clear_router_cache
from app.schemas import ServiceStatus


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_router_cache()
    yield
    clear_router_cache()


@pytest.mark.asyncio
async def test_router_not_configured_without_url():
    snap = await RouterAdapter(base_url=None, password="secret").fetch()
    assert snap.status == ServiceStatus.NOT_CONFIGURED


@pytest.mark.asyncio
async def test_router_not_configured_without_password():
    snap = await RouterAdapter(base_url="http://192.168.0.1", password=None).fetch()
    assert snap.status == ServiceStatus.NOT_CONFIGURED
    assert snap.href == "http://192.168.0.1"


@pytest.mark.asyncio
async def test_router_parses_status_and_caches():
    status = SimpleNamespace(
        wan_ipv4_addr="203.0.113.10",
        clients_total=18,
        wifi_clients_total=14,
        wired_total=4,
        guest_clients_total=0,
        cpu_usage=0.12,
        mem_usage=0.41,
        wan_ipv4_uptime=90061,
        conn_type="dhcp",
        wifi_2g_enable=True,
        wifi_5g_enable=True,
        wifi_6g_enable=False,
    )
    with patch(
        "app.adapters.router._fetch_status_sync", return_value=status
    ) as fetch_mock:
        adapter = RouterAdapter(
            base_url="http://192.168.0.1",
            password="local-secret",
            username="admin",
        )
        first = await adapter.fetch()
        second = await adapter.fetch()

    assert first.status == ServiceStatus.ONLINE
    assert first.status_label == "Online"
    by_key = {m.key: m for m in first.metrics}
    assert by_key["wan"].display == "203.0.113.10"
    assert by_key["clients"].display == "18"
    assert by_key["cpu"].display == "12%"
    assert by_key["wifi"].display == "2.4G · 5G"
    assert first.uptime == "1d 1h"
    assert second.status == ServiceStatus.ONLINE
    assert fetch_mock.call_count == 1
    assert "local-secret" not in str(first.model_dump())


@pytest.mark.asyncio
async def test_router_login_failure():
    with patch(
        "app.adapters.router._fetch_status_sync",
        side_effect=RuntimeError("Login failed"),
    ):
        snap = await RouterAdapter(
            base_url="http://192.168.0.1", password="bad"
        ).fetch()
    assert snap.status == ServiceStatus.DEGRADED
    assert "Login failed" in (snap.error or "")
