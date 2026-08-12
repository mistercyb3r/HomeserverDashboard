"""Tailscale status via the local tailscaled Unix socket API (read-only)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.adapters.base import (
    ServiceAdapter,
    metric,
    not_configured_snapshot,
    offline_snapshot,
    utcnow,
)
from app.schemas import Metric, ServiceSnapshot, ServiceStatus

DEFAULT_SOCKET = "/var/run/tailscale/tailscaled.sock"
ADMIN_URL = "https://login.tailscale.com/admin/machines"


def _format_bytes(num: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _pick_ip(ips: list[Any] | None) -> str | None:
    if not ips:
        return None
    for ip in ips:
        text = str(ip)
        if text.startswith("100."):
            return text
    return str(ips[0]) if ips else None


class TailscaleAdapter(ServiceAdapter):
    id = "tailscale"
    name = "Tailscale"
    description = "Private mesh VPN"
    icon = "shield"
    config_kind = "socket"

    def __init__(
        self,
        *,
        enabled: bool,
        socket_path: str | None,
        timeout: float = 5.0,
        admin_url: str | None = ADMIN_URL,
    ) -> None:
        self._enabled = enabled
        self._socket = (socket_path or "").strip() or None
        self._timeout = timeout
        self._admin_url = (admin_url or "").rstrip("/") or ADMIN_URL

    def is_configured(self) -> bool:
        return bool(self._enabled and self._socket)

    def open_url(self) -> str | None:
        return self._admin_url

    async def fetch(self) -> ServiceSnapshot:
        if not self._enabled or not self._socket:
            return not_configured_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                message="Enable Tailscale and mount the tailscaled socket",
                href=self._admin_url,
                open_label="Open admin",
            )

        if not os.path.exists(self._socket):
            return offline_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                url=self._admin_url,
                href=self._admin_url,
                open_label="Open admin",
                error="Tailscale socket not found",
                status=ServiceStatus.DEGRADED,
                status_label="Unavailable",
            )

        try:
            transport = httpx.AsyncHTTPTransport(uds=self._socket)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://local-tailscaled.sock",
                timeout=self._timeout,
            ) as client:
                response = await client.get("/localapi/v0/status")
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            return offline_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                url=self._admin_url,
                href=self._admin_url,
                open_label="Open admin",
                error=str(exc) or "Tailscale unavailable",
                status=ServiceStatus.DEGRADED,
                status_label="Unavailable",
            )

        return self._snapshot_from_status(payload)

    def _snapshot_from_status(self, payload: dict[str, Any]) -> ServiceSnapshot:
        backend = str(payload.get("BackendState") or "Unknown")
        self_node = payload.get("Self") or {}
        peers = payload.get("Peer") or {}
        if not isinstance(peers, dict):
            peers = {}

        online_peers = 0
        total_peers = 0
        for peer in peers.values():
            if not isinstance(peer, dict):
                continue
            total_peers += 1
            if peer.get("Online") or peer.get("Active"):
                online_peers += 1

        hostname = (
            str(self_node.get("HostName") or "").strip()
            or str(self_node.get("DNSName") or "").rstrip(".").split(".")[0]
            or None
        )
        ip = _pick_ip(self_node.get("TailscaleIPs") or payload.get("TailscaleIPs"))
        dns = str(self_node.get("DNSName") or "").rstrip(".") or None
        version = str(payload.get("Version") or "").split("-")[0] or None
        rx = self_node.get("RxBytes")
        tx = self_node.get("TxBytes")
        tailnet = None
        current = payload.get("CurrentTailnet") or {}
        if isinstance(current, dict):
            tailnet = str(current.get("Name") or "").strip() or None

        running = backend.lower() == "running" and bool(self_node.get("Online", True))
        if backend.lower() == "running":
            status = ServiceStatus.ONLINE
            status_label = "Connected" if running else "Running"
        elif backend.lower() in {"needslogin", "needsauth", "stopped", "nostate"}:
            status = ServiceStatus.DEGRADED
            status_label = backend
        else:
            status = ServiceStatus.DEGRADED
            status_label = backend or "Unavailable"

        metrics: list[Metric] = [
            metric(
                "state",
                "State",
                backend,
                display=status_label,
                primary=True,
            ),
            metric("ip", "IP", ip, display=ip, primary=True),
            metric(
                "peers",
                "Peers",
                online_peers,
                display=f"{online_peers} online / {total_peers}",
                primary=True,
            ),
            metric("hostname", "Host", hostname, display=hostname),
            metric("dns", "MagicDNS", dns, display=dns),
            metric("tailnet", "Tailnet", tailnet, display=tailnet),
            metric(
                "rx",
                "Received",
                int(rx) if isinstance(rx, (int, float)) else None,
                display=(
                    _format_bytes(float(rx)) if isinstance(rx, (int, float)) else None
                ),
            ),
            metric(
                "tx",
                "Sent",
                int(tx) if isinstance(tx, (int, float)) else None,
                display=(
                    _format_bytes(float(tx)) if isinstance(tx, (int, float)) else None
                ),
            ),
        ]

        return ServiceSnapshot(
            id=self.id,
            name=self.name,
            description=self.description,
            icon=self.icon,
            status=status,
            status_label=status_label,
            metrics=metrics,
            version=version,
            uptime=None,
            url=self._admin_url,
            href=self._admin_url,
            open_label="Open admin",
            last_updated=utcnow(),
            last_success_at=utcnow(),
            configured=True,
            error=None,
        )
