"""TP-Link Archer (AX73 etc.) status via local admin password — read-only."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.adapters.base import (
    ServiceAdapter,
    format_uptime_seconds,
    metric,
    not_configured_snapshot,
    offline_snapshot,
    utcnow,
)
from app.schemas import Metric, ServiceSnapshot, ServiceStatus

# Avoid logging into the router on every dashboard poll (kicks web UI sessions).
_CACHE_SECONDS = 45.0
_cache: dict[str, Any] = {"key": None, "expires_at": 0.0, "snapshot": None}


def _pct(value: Any) -> tuple[float | None, str | None]:
    try:
        if value is None:
            return None, None
        num = float(value)
        if 0.0 <= num <= 1.0:
            num *= 100.0
        num = round(num, 1)
        return num, f"{num:.0f}%"
    except (TypeError, ValueError):
        return None, None


def _wifi_label(status: Any) -> str:
    bands: list[str] = []
    if getattr(status, "wifi_2g_enable", None):
        bands.append("2.4G")
    if getattr(status, "wifi_5g_enable", None):
        bands.append("5G")
    if getattr(status, "wifi_6g_enable", None):
        bands.append("6G")
    return " · ".join(bands) if bands else "Off"


def _fetch_status_sync(
    *,
    host: str,
    password: str,
    username: str,
    verify_ssl: bool,
    timeout: int,
) -> Any:
    from tplinkrouterc6u import TplinkRouterProvider

    router = TplinkRouterProvider.get_client(
        host,
        password,
        username=username,
        verify_ssl=verify_ssl,
        timeout=timeout,
    )
    try:
        router.authorize()
        return router.get_status()
    finally:
        try:
            router.logout()
        except Exception:  # noqa: BLE001
            pass


class RouterAdapter(ServiceAdapter):
    id = "router"
    name = "Router"
    description = "TP-Link Archer AX73"
    icon = "router"

    def __init__(
        self,
        *,
        base_url: str | None,
        password: str | None,
        username: str = "admin",
        verify_ssl: bool = False,
        timeout: float = 12.0,
    ) -> None:
        self._base_url = (base_url or "").rstrip("/") or None
        self._password = (password or "").strip() or None
        self._username = (username or "admin").strip() or "admin"
        self._verify_ssl = verify_ssl
        self._timeout = max(5, int(timeout))

    def is_configured(self) -> bool:
        return bool(self._base_url and self._password)

    def open_url(self) -> str | None:
        return self._base_url

    async def fetch(self) -> ServiceSnapshot:
        if not self._base_url:
            return not_configured_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                message="Set TPLINK_URL (and local password) to enable the router card",
            )
        if not self._password:
            return not_configured_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                message="Set TPLINK_PASSWORD (local admin password, not TP-Link ID)",
                href=self._base_url,
                open_label="Open router",
            )

        cache_key = f"{self._base_url}|{self._username}"
        now = time.monotonic()
        cached = _cache.get("snapshot")
        if (
            cached is not None
            and _cache.get("key") == cache_key
            and now < float(_cache.get("expires_at") or 0)
        ):
            return cached

        try:
            status = await asyncio.to_thread(
                _fetch_status_sync,
                host=self._base_url,
                password=self._password,
                username=self._username,
                verify_ssl=self._verify_ssl,
                timeout=self._timeout,
            )
        except Exception as exc:  # noqa: BLE001
            return offline_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                url=self._base_url,
                href=self._base_url,
                open_label="Open router",
                error=str(exc) or "Router unavailable",
                status=ServiceStatus.DEGRADED,
                status_label="Unavailable",
            )

        snap = self._snapshot_from_status(status)
        _cache["key"] = cache_key
        _cache["snapshot"] = snap
        _cache["expires_at"] = time.monotonic() + _CACHE_SECONDS
        return snap

    def _snapshot_from_status(self, status: Any) -> ServiceSnapshot:
        wan = getattr(status, "wan_ipv4_addr", None) or getattr(
            status, "wan_ipv4_address", None
        )
        wan_text = str(wan) if wan else None
        clients = getattr(status, "clients_total", None)
        wifi_clients = getattr(status, "wifi_clients_total", None)
        wired = getattr(status, "wired_total", None)
        guest = getattr(status, "guest_clients_total", None)
        cpu_val, cpu_display = _pct(getattr(status, "cpu_usage", None))
        mem_val, mem_display = _pct(getattr(status, "mem_usage", None))
        uptime = format_uptime_seconds(getattr(status, "wan_ipv4_uptime", None))
        conn = getattr(status, "conn_type", None)
        conn_text = str(conn) if conn else None
        wifi = _wifi_label(status)

        metrics: list[Metric] = [
            metric("wan", "WAN", wan_text, display=wan_text, primary=True),
            metric(
                "clients",
                "Clients",
                clients,
                display=None if clients is None else str(clients),
                primary=True,
            ),
            metric("wifi", "Wi‑Fi", wifi, display=wifi, primary=True),
            metric(
                "wifi_clients",
                "Wi‑Fi clients",
                wifi_clients,
                display=None if wifi_clients is None else str(wifi_clients),
            ),
            metric(
                "wired",
                "Wired",
                wired,
                display=None if wired is None else str(wired),
            ),
            metric(
                "guest",
                "Guest",
                guest,
                display=None if guest is None else str(guest),
            ),
            metric("cpu", "CPU", cpu_val, unit="%", display=cpu_display),
            metric("ram", "RAM", mem_val, unit="%", display=mem_display),
            metric("uptime", "WAN uptime", uptime, display=uptime),
            metric("conn", "Connection", conn_text, display=conn_text),
        ]

        return ServiceSnapshot(
            id=self.id,
            name=self.name,
            description=self.description,
            icon=self.icon,
            status=ServiceStatus.ONLINE,
            status_label="Online",
            metrics=metrics,
            version=None,
            uptime=uptime,
            url=self._base_url,
            href=self._base_url,
            open_label="Open router",
            last_updated=utcnow(),
            last_success_at=utcnow(),
            configured=True,
            error=None,
        )


def clear_router_cache() -> None:
    _cache["key"] = None
    _cache["expires_at"] = 0.0
    _cache["snapshot"] = None
