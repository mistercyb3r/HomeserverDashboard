"""Local host metrics via psutil."""

from __future__ import annotations

import os
import platform
import socket
import time
from typing import Any

import psutil

from app.adapters.base import ServiceAdapter, format_uptime_seconds, metric, utcnow
from app.schemas import Metric, ServiceSnapshot, ServiceStatus
from app.storage import BAD_PERCENT, WARN_PERCENT, collect_storage_mounts

_BOOT_TIME = psutil.boot_time()
_NET_PREV: dict[str, Any] = {"ts": None, "bytes_sent": 0, "bytes_recv": 0}


def _format_bytes(num: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(num)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def _format_rate(bytes_per_sec: float) -> str:
    return f"{_format_bytes(bytes_per_sec)}/s"


def _cpu_temp_c() -> float | None:
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, NotImplementedError, RuntimeError):
        return None
    if not temps:
        return None
    preferred = ("coretemp", "k10temp", "cpu_thermal", "acpi", "zenpower")
    for key in preferred:
        entries = temps.get(key)
        if entries:
            values = [t.current for t in entries if t.current is not None]
            if values:
                return round(sum(values) / len(values), 1)
    for entries in temps.values():
        values = [t.current for t in entries if t.current is not None]
        if values:
            return round(sum(values) / len(values), 1)
    return None


def _network_rates() -> tuple[float | None, float | None]:
    """Return (download_bps, upload_bps) since last sample, or None on first call."""
    counters = psutil.net_io_counters()
    now = time.monotonic()
    prev_ts = _NET_PREV["ts"]
    if prev_ts is None:
        _NET_PREV.update(
            ts=now,
            bytes_sent=counters.bytes_sent,
            bytes_recv=counters.bytes_recv,
        )
        return None, None
    elapsed = max(now - prev_ts, 0.001)
    down = (counters.bytes_recv - _NET_PREV["bytes_recv"]) / elapsed
    up = (counters.bytes_sent - _NET_PREV["bytes_sent"]) / elapsed
    _NET_PREV.update(
        ts=now,
        bytes_sent=counters.bytes_sent,
        bytes_recv=counters.bytes_recv,
    )
    return max(down, 0.0), max(up, 0.0)


class ServerAdapter(ServiceAdapter):
    id = "server"
    name = "Server"
    description = "Host CPU, memory, disk, and network"
    icon = "server"
    configurable = False

    def is_configured(self) -> bool:
        return True

    async def fetch(self) -> ServiceSnapshot:
        cpu = psutil.cpu_percent(interval=0.15)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(os.path.abspath(os.sep))
        mounts = collect_storage_mounts()
        worst_disk = max(
            [disk.percent, *[m.percent for m in mounts]], default=disk.percent
        )
        load: tuple[float, float, float] | None
        try:
            load = os.getloadavg()  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            load = None
        temp = _cpu_temp_c()
        down, up = _network_rates()
        uptime_seconds = time.time() - _BOOT_TIME
        uptime_display = format_uptime_seconds(uptime_seconds)
        hostname = socket.gethostname()
        os_name = f"{platform.system()} {platform.release()}"
        kernel = (
            platform.version() if platform.system() == "Windows" else platform.release()
        )

        metrics: list[Metric] = [
            metric(
                "cpu",
                "CPU",
                round(cpu, 1),
                unit="%",
                display=f"{cpu:.0f}%",
                primary=True,
            ),
            metric(
                "ram",
                "RAM",
                round(mem.percent, 1),
                unit="%",
                display=f"{mem.percent:.0f}%",
                primary=True,
            ),
            metric(
                "disk",
                "Storage",
                round(disk.percent, 1),
                unit="%",
                display=f"{disk.percent:.0f}%",
                primary=True,
                detail=f"{_format_bytes(disk.free)} free",
            ),
            metric(
                "disk_free",
                "Free",
                int(disk.free),
                display=f"{_format_bytes(disk.free)} free",
                primary=True,
            ),
            metric(
                "uptime",
                "Uptime",
                int(uptime_seconds),
                display=uptime_display,
                primary=worst_disk < WARN_PERCENT,
            ),
            metric(
                "temp",
                "CPU temp",
                temp,
                unit="°C",
                display=None if temp is None else f"{temp:.0f}",
            ),
            metric(
                "net_down",
                "Download",
                None if down is None else round(down, 1),
                display=None if down is None else _format_rate(down),
            ),
            metric(
                "net_up",
                "Upload",
                None if up is None else round(up, 1),
                display=None if up is None else _format_rate(up),
            ),
            metric("hostname", "Hostname", hostname, display=hostname),
            metric("os", "OS", os_name, display=os_name),
            metric("kernel", "Kernel", kernel, display=kernel),
            metric(
                "load",
                "Load avg",
                None if load is None else round(load[0], 2),
                display=(
                    None
                    if load is None
                    else f"{load[0]:.2f} / {load[1]:.2f} / {load[2]:.2f}"
                ),
            ),
        ]

        status = ServiceStatus.ONLINE
        status_label = "Online"
        if cpu >= 90 or mem.percent >= 92 or worst_disk >= BAD_PERCENT:
            status = ServiceStatus.DEGRADED
            if worst_disk >= BAD_PERCENT and cpu < 90 and mem.percent < 92:
                status_label = "Storage nearly full"
            else:
                status_label = "High resource usage"

        return ServiceSnapshot(
            id=self.id,
            name=self.name,
            description=self.description,
            icon=self.icon,
            status=status,
            status_label=status_label,
            metrics=metrics,
            version=platform.platform(),
            uptime=uptime_display,
            url=None,
            href=None,
            open_label=None,
            last_updated=utcnow(),
            last_success_at=utcnow(),
            configured=True,
            error=None,
        )
