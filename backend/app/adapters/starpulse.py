"""StarPulse adapter — health/version plus a short Starlink summary."""

from __future__ import annotations

import httpx

from app.adapters.base import (
    ServiceAdapter,
    format_uptime_seconds,
    metric,
    not_configured_snapshot,
    offline_snapshot,
    utcnow,
)
from app.schemas import Metric, ServiceSnapshot, ServiceStatus


class StarPulseAdapter(ServiceAdapter):
    id = "starpulse"
    name = "StarPulse"
    description = "Starlink telemetry dashboard"
    icon = "satellite"

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
                message="Set STARPULSE_URL or configure the service URL in Settings",
            )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                health = await client.get(f"{self._base_url}/api/health")
                if health.status_code != 200:
                    return offline_snapshot(
                        service_id=self.id,
                        name=self.name,
                        description=self.description,
                        icon=self.icon,
                        url=self._base_url,
                        href=self._base_url,
                        open_label="Open StarPulse",
                        error=f"StarPulse health returned HTTP {health.status_code}",
                        status=ServiceStatus.DEGRADED,
                        status_label="StarPulse unavailable",
                    )
                payload = health.json()
                version = payload.get("version")
                starlink_connected = payload.get("starlink_connected")

                # Prefer /api/about when available for a richer summary.
                about_version = None
                about_uptime = None
                try:
                    about = await client.get(f"{self._base_url}/api/about")
                    if about.status_code == 200:
                        about_json = about.json()
                        about_version = about_json.get("version")
                        about_uptime = about_json.get("uptime_seconds")
                except httpx.HTTPError:
                    about_version = None
                version = about_version or version
                uptime_display = format_uptime_seconds(about_uptime)

        except httpx.HTTPError as exc:
            return offline_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                url=self._base_url,
                href=self._base_url,
                open_label="Open StarPulse",
                error=str(exc),
                status=ServiceStatus.DEGRADED,
                status_label="StarPulse unavailable",
            )

        if starlink_connected is True:
            link_label = "Starlink connected"
            link_value = "connected"
        elif starlink_connected is False:
            link_label = "Starlink disconnected"
            link_value = "disconnected"
        else:
            link_label = "Unavailable"
            link_value = None

        metrics: list[Metric] = [
            metric(
                "starlink",
                "Starlink",
                link_value,
                display=link_label if link_value is not None else "Unavailable",
                available=link_value is not None,
                primary=True,
            ),
            metric(
                "version",
                "Version",
                version,
                display=None if version is None else f"v{version}",
                primary=True,
            ),
        ]

        status = ServiceStatus.ONLINE
        status_label = "Online"
        if starlink_connected is False:
            status = ServiceStatus.DEGRADED
            status_label = "Online · Starlink down"

        return ServiceSnapshot(
            id=self.id,
            name=self.name,
            description=self.description,
            icon=self.icon,
            status=status,
            status_label=status_label,
            metrics=metrics,
            version=version,
            uptime=uptime_display,
            url=self._base_url,
            href=self._base_url,
            open_label="Open StarPulse",
            last_updated=utcnow(),
            last_success_at=utcnow(),
            configured=True,
            error=None,
        )
