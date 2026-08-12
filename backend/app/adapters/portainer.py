"""Minimal Portainer link adapter — reachability + Open URL only."""

from __future__ import annotations

import httpx

from app.adapters.base import (
    ServiceAdapter,
    metric,
    not_configured_snapshot,
    offline_snapshot,
    utcnow,
)
from app.schemas import Metric, ServiceSnapshot, ServiceStatus


class PortainerAdapter(ServiceAdapter):
    id = "portainer"
    name = "Portainer"
    description = "Container management UI"
    icon = "layout"

    def __init__(self, *, base_url: str | None, timeout: float = 5.0) -> None:
        self._base_url = (base_url or "").rstrip("/") or None
        self._timeout = timeout

    def is_configured(self) -> bool:
        return bool(self._base_url)

    def open_url(self) -> str | None:
        return self._base_url

    async def fetch(self) -> ServiceSnapshot:
        if not self.is_configured():
            return not_configured_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                message="Set PORTAINER_URL or configure the service URL in Settings",
            )

        try:
            # Home-lab Portainer almost always uses a self-signed HTTPS cert.
            # This adapter only checks reachability; Open still goes to the URL.
            async with httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
                verify=False,
            ) as client:
                response = await client.get(self._base_url)
                online = response.status_code < 500
        except httpx.HTTPError as exc:
            return offline_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                url=self._base_url,
                href=self._base_url,
                open_label="Open Portainer",
                error=str(exc),
                status=ServiceStatus.DEGRADED,
                status_label="Unavailable",
            )

        if not online:
            return offline_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                url=self._base_url,
                href=self._base_url,
                open_label="Open Portainer",
                error=f"Portainer returned HTTP {response.status_code}",
                status=ServiceStatus.DEGRADED,
                status_label="Unavailable",
            )

        metrics: list[Metric] = [
            metric(
                "endpoint", "Endpoint", self._base_url, display="Ready", primary=True
            )
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
            uptime=None,
            url=self._base_url,
            href=self._base_url,
            open_label="Open Portainer",
            last_updated=utcnow(),
            last_success_at=utcnow(),
            configured=True,
            error=None,
        )
