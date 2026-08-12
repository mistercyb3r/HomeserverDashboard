"""Dashboard aggregation and system health."""

from __future__ import annotations

import asyncio
from typing import Any

from app.adapters.registry import AdapterRegistry
from app.config import Settings
from app.schemas import (
    ActivityItem,
    DashboardResponse,
    OverviewMetric,
    QuickLink,
    ServiceSnapshot,
    ServiceStatus,
    SystemHealth,
    SystemHealthLevel,
    WeatherInfo,
)
from app.storage import collect_storage_mounts
from app.weather import fetch_weather


def compute_system_health(services: list[ServiceSnapshot]) -> SystemHealth:
    """Score health from current configured services only.

    Unconfigured integrations are listed on the dashboard but do not change
    the global status — they are simply not part of the picture yet.
    """
    online = 0
    attention = 0
    offline = 0
    not_configured = 0

    for service in services:
        if service.status == ServiceStatus.NOT_CONFIGURED:
            not_configured += 1
        elif service.status == ServiceStatus.ONLINE:
            online += 1
        elif service.status == ServiceStatus.DEGRADED:
            attention += 1
        elif service.status == ServiceStatus.OFFLINE:
            offline += 1
        else:
            attention += 1

    configured = online + attention + offline
    total = len(services)

    if configured == 0:
        level = SystemHealthLevel.UNKNOWN
        label = "No services configured"
    elif offline > 0:
        level = SystemHealthLevel.CRITICAL
        label = f"{offline} service{'s' if offline != 1 else ''} offline"
    elif attention > 0:
        level = SystemHealthLevel.ATTENTION
        label = (
            "1 service requires attention"
            if attention == 1
            else f"{attention} services require attention"
        )
    else:
        level = SystemHealthLevel.OPERATIONAL
        label = "All systems operational"

    return SystemHealth(
        level=level,
        label=label,
        online_count=online,
        attention_count=attention,
        offline_count=offline,
        not_configured_count=not_configured,
        total_enabled=total,
    )


def _bar_from_percent(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return None


def _find_metric(snapshot: ServiceSnapshot, key: str) -> OverviewMetric:
    for item in snapshot.metrics:
        if item.key == key:
            bar = (
                _bar_from_percent(item.value) if key in {"cpu", "ram", "disk"} else None
            )
            tone = None
            detail = item.detail
            if key == "disk" and bar is not None:
                if bar >= 92:
                    tone = "bad"
                elif bar >= 85:
                    tone = "warn"
                if not detail:
                    free = next(
                        (m for m in snapshot.metrics if m.key == "disk_free"), None
                    )
                    if free and free.available:
                        detail = free.display
            if (
                key == "temp"
                and item.available
                and isinstance(item.value, (int, float))
            ):
                if float(item.value) >= 90:
                    tone = "bad"
                elif float(item.value) >= 80:
                    tone = "warn"
            return OverviewMetric(
                key=item.key,
                label=item.label,
                value=item.value,
                display=item.display,
                unit=item.unit,
                available=item.available,
                bar=bar,
                detail=detail,
                tone=tone,
            )
    return OverviewMetric(key=key, label=key, display="Unavailable", available=False)


def build_overview(services: list[ServiceSnapshot]) -> list[OverviewMetric]:
    server = next((s for s in services if s.id == "server"), None)
    starlink = next((s for s in services if s.id == "starlink"), None)

    overview: list[OverviewMetric] = []
    if server:
        overview.extend(
            [
                _find_metric(server, "cpu"),
                _find_metric(server, "ram"),
                _find_metric(server, "temp"),
                _find_metric(server, "uptime"),
            ]
        )
        nvme = _find_metric(server, "nvme_temp")
        if nvme.available:
            overview.append(nvme)
        net_down = _find_metric(server, "net_down")
        net_up = _find_metric(server, "net_up")
        if net_down.available or net_up.available:
            display = "Unavailable"
            if net_down.available and net_up.available:
                display = f"↓ {net_down.display}  ↑ {net_up.display}"
            elif net_down.available:
                display = f"↓ {net_down.display}"
            elif net_up.available:
                display = f"↑ {net_up.display}"
            overview.append(
                OverviewMetric(
                    key="network",
                    label="Network",
                    value=net_down.value if net_down.available else net_up.value,
                    display=display,
                    available=net_down.available or net_up.available,
                )
            )
    else:
        for key, label in [
            ("cpu", "CPU"),
            ("ram", "RAM"),
            ("temp", "Temp"),
            ("uptime", "Uptime"),
        ]:
            overview.append(OverviewMetric(key=key, label=label, display="Unavailable"))

    if starlink and starlink.status != ServiceStatus.NOT_CONFIGURED:
        overview.append(
            OverviewMetric(
                key="starlink",
                label="Starlink",
                value=starlink.status.value,
                display=starlink.status_label,
                available=True,
            )
        )

    return overview


def build_activity(services: list[ServiceSnapshot]) -> list[ActivityItem]:
    """Build a short live status list from the current snapshots only."""
    items: list[ActivityItem] = []
    for service in services:
        if service.status == ServiceStatus.NOT_CONFIGURED:
            continue

        if service.status == ServiceStatus.ONLINE:
            if service.id == "server":
                text = "Server online"
            elif service.id == "jellyfin":
                streams = next((m for m in service.metrics if m.key == "streams"), None)
                text = (
                    f"Jellyfin · {streams.display}"
                    if streams and streams.available
                    else "Jellyfin online"
                )
            elif service.id == "docker":
                running = next((m for m in service.metrics if m.key == "running"), None)
                text = (
                    f"Docker · {running.display}"
                    if running and running.available
                    else "Docker online"
                )
            elif service.id == "starpulse":
                link = next((m for m in service.metrics if m.key == "starlink"), None)
                text = (
                    f"StarPulse · {link.display}"
                    if link and link.available
                    else "StarPulse connected"
                )
            elif service.id == "starlink":
                text = f"Starlink · {service.status_label}"
            else:
                text = f"{service.name} online"
            items.append(ActivityItem(tone="good", text=text))
        elif service.status == ServiceStatus.DEGRADED:
            if service.id == "server":
                disk = next((m for m in service.metrics if m.key == "disk"), None)
                free = next((m for m in service.metrics if m.key == "disk_free"), None)
                if (
                    disk
                    and disk.available
                    and isinstance(disk.value, (int, float))
                    and float(disk.value) >= 85
                ):
                    text = f"Storage {disk.display}"
                    if free and free.available:
                        text = f"{text} · {free.display}"
                    items.append(ActivityItem(tone="warn", text=text))
                    continue
            items.append(ActivityItem(tone="warn", text=f"{service.name} degraded"))
        elif service.status == ServiceStatus.OFFLINE:
            items.append(ActivityItem(tone="bad", text=f"{service.name} offline"))
        else:
            items.append(ActivityItem(tone="muted", text=f"{service.name} unknown"))
    return items[:8]


def build_quick_links(services: list[ServiceSnapshot]) -> list[QuickLink]:
    links: list[QuickLink] = []
    seen: set[str] = set()
    for service in services:
        if service.status == ServiceStatus.NOT_CONFIGURED:
            continue
        url = service.href or service.url
        if not url or url.startswith("/"):
            continue
        if url in seen:
            continue
        seen.add(url)
        links.append(QuickLink(id=service.id, label=service.name, url=url))
    return links


async def collect_dashboard(
    *,
    registry: AdapterRegistry,
    config: dict[str, Any],
    server_name: str,
    settings: Settings | None = None,
) -> DashboardResponse:
    from app.adapters.base import utcnow

    adapters = registry.enabled_adapters(config)
    snapshots = list(await asyncio.gather(*[adapter.fetch() for adapter in adapters]))
    order = {adapter.id: index for index, adapter in enumerate(adapters)}
    snapshots.sort(key=lambda s: order.get(s.id, 999))

    host_fs = settings.host_fs_root if settings else None
    try:
        storage = collect_storage_mounts(host_fs_root=host_fs)
    except Exception:  # noqa: BLE001
        storage = []

    weather: WeatherInfo | None = None
    if settings is not None:
        try:
            weather = await fetch_weather(
                location=settings.weather_location,
                latitude=settings.weather_latitude,
                longitude=settings.weather_longitude,
                cache_seconds=settings.weather_cache_seconds,
                timeout=settings.http_timeout_seconds,
                enabled=settings.weather_enabled,
            )
        except Exception:  # noqa: BLE001
            weather = WeatherInfo(
                available=False,
                location=settings.weather_location,
                error="Weather unavailable",
            )

    return DashboardResponse(
        server_name=server_name,
        generated_at=utcnow(),
        refresh_interval_seconds=int(config.get("refresh_interval_seconds") or 10),
        system_health=compute_system_health(snapshots),
        overview=build_overview(snapshots),
        storage=storage,
        services=snapshots,
        activity=build_activity(snapshots),
        weather=weather,
        quick_links=build_quick_links(snapshots),
    )


__all__ = [
    "build_activity",
    "build_overview",
    "build_quick_links",
    "collect_dashboard",
    "compute_system_health",
]
