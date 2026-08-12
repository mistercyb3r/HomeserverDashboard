"""Starlink metrics sourced from StarPulse (no dish credentials needed)."""

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


def _bps_to_mbps(bps: float | None) -> float | None:
    if bps is None:
        return None
    return round(bps / 1_000_000, 1)


def _format_uptime(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


class StarlinkAdapter(ServiceAdapter):
    id = "starlink"
    name = "Starlink"
    description = "Live dish status via StarPulse"
    icon = "wifi"

    def __init__(self, *, starpulse_url: str | None, timeout: float = 5.0) -> None:
        self._starpulse_url = (starpulse_url or "").rstrip("/") or None
        self._timeout = timeout

    def is_configured(self) -> bool:
        return bool(self._starpulse_url)

    def open_url(self) -> str | None:
        # Open StarPulse rather than inventing a second Starlink UI.
        return self._starpulse_url

    async def fetch(self) -> ServiceSnapshot:
        if not self.is_configured():
            return not_configured_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                message="Configure StarPulse URL to read Starlink telemetry",
            )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # Confirm StarPulse itself is reachable.
                health = await client.get(f"{self._starpulse_url}/api/health")
                if health.status_code != 200:
                    return offline_snapshot(
                        service_id=self.id,
                        name=self.name,
                        description=self.description,
                        icon=self.icon,
                        url=self._starpulse_url,
                        error=f"StarPulse unreachable (HTTP {health.status_code})",
                    )

                status_resp = await client.get(
                    f"{self._starpulse_url}/api/starlink/status"
                )
                outages_today: int | None = None
                downtime_min: float | None = None
                try:
                    outages_resp = await client.get(
                        f"{self._starpulse_url}/api/starlink/outages"
                    )
                    if outages_resp.status_code == 200:
                        outages = outages_resp.json()
                        outages_today = outages.get("outages_today")
                        downtime_min = outages.get("total_downtime_minutes_last_7d")
                except httpx.HTTPError:
                    pass

                if status_resp.status_code == 404:
                    return ServiceSnapshot(
                        id=self.id,
                        name=self.name,
                        description=self.description,
                        icon=self.icon,
                        status=ServiceStatus.UNKNOWN,
                        status_label="No telemetry yet",
                        metrics=[
                            metric("connection", "Connection", None),
                            metric("download", "Download", None),
                            metric("upload", "Upload", None),
                            metric("latency", "Latency", None),
                        ],
                        version=None,
                        url=self._starpulse_url,
                        last_updated=utcnow(),
                        configured=True,
                        error="StarPulse has no telemetry samples yet",
                    )

                if status_resp.status_code != 200:
                    return offline_snapshot(
                        service_id=self.id,
                        name=self.name,
                        description=self.description,
                        icon=self.icon,
                        url=self._starpulse_url,
                        error=f"Starlink status returned HTTP {status_resp.status_code}",
                    )

                sample = status_resp.json()
        except httpx.HTTPError as exc:
            return offline_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                url=self._starpulse_url,
                error=str(exc),
            )

        connection_state = (sample.get("connection_state") or "UNKNOWN").upper()
        download = _bps_to_mbps(sample.get("download_bps"))
        upload = _bps_to_mbps(sample.get("upload_bps"))
        latency = sample.get("latency_ms")
        packet_loss = sample.get("ping_drop_rate")
        uptime = _format_uptime(sample.get("uptime_seconds"))

        if connection_state == "CONNECTED":
            status = ServiceStatus.ONLINE
            status_label = "Connected"
        elif connection_state in {"SEARCHING", "BOOTING"}:
            status = ServiceStatus.DEGRADED
            status_label = connection_state.title()
        else:
            status = ServiceStatus.OFFLINE
            status_label = connection_state.replace("_", " ").title()

        loss_display = None
        loss_available = packet_loss is not None
        if loss_available:
            # StarPulse stores drop rate as a fraction (0-1) or already percent.
            rate = float(packet_loss)
            pct = rate * 100 if rate <= 1 else rate
            loss_display = f"{pct:.1f}"

        outage_display = None
        if outages_today is not None:
            if downtime_min is not None:
                outage_display = f"{outages_today} today · {downtime_min:.0f}m / 7d"
            else:
                outage_display = f"{outages_today} today"

        metrics: list[Metric] = [
            metric("connection", "Connection", connection_state, display=status_label),
            metric(
                "download",
                "Download",
                download,
                unit="Mbps",
                display=None if download is None else f"↓ {download:.0f} Mbps",
                primary=True,
            ),
            metric(
                "upload",
                "Upload",
                upload,
                unit="Mbps",
                display=None if upload is None else f"↑ {upload:.0f} Mbps",
                primary=True,
            ),
            metric(
                "latency",
                "Latency",
                None if latency is None else round(float(latency), 1),
                unit="ms",
                display=None if latency is None else f"{float(latency):.0f} ms",
                primary=True,
            ),
            metric(
                "packet_loss",
                "Packet loss",
                packet_loss,
                unit="%",
                display=loss_display,
                available=loss_available,
            ),
            metric(
                "uptime",
                "Dish uptime",
                sample.get("uptime_seconds"),
                display=uptime,
                available=uptime is not None,
            ),
            metric(
                "outages",
                "Outages",
                outages_today,
                display=outage_display,
                available=outage_display is not None,
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
            version=sample.get("software_version"),
            uptime=uptime,
            url=self._starpulse_url,
            href=self._starpulse_url,
            open_label="Open StarPulse",
            last_updated=utcnow(),
            last_success_at=utcnow(),
            configured=True,
            error=None,
        )
