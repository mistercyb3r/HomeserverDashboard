"""Lightweight mounted-filesystem inventory via psutil.

No directory walks, no folder sizes, no background workers.
"""

from __future__ import annotations

import sys
from typing import Any

import psutil

from app.schemas import StorageMount

# Match server card / overview thresholds.
WARN_PERCENT = 85.0
BAD_PERCENT = 92.0

_PSEUDO_FSTYPES = {
    "autofs",
    "binfmt_misc",
    "bpf",
    "cgroup",
    "cgroup2",
    "configfs",
    "debugfs",
    "devpts",
    "devtmpfs",
    "efivarfs",
    "fusectl",
    "hugetlbfs",
    "mqueue",
    "nsfs",
    "overlay",
    "pipefs",
    "proc",
    "pstore",
    "ramfs",
    "rpc_pipefs",
    "securityfs",
    "squashfs",
    "sysfs",
    "tmpfs",
    "tracefs",
    "aufs",
    "fuse.lxcfs",
    "fuse.gvfsd-fuse",
}

_SKIP_MOUNT_PREFIXES = (
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/snap",
    "/var/lib/docker",
    "/var/lib/containerd",
    "/var/lib/containers",
)


def _format_bytes(num: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(num)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            if unit in {"GB", "TB", "PB"} and value >= 10:
                return f"{value:.0f} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} PB"


def _tone_for_percent(percent: float) -> str:
    if percent >= BAD_PERCENT:
        return "bad"
    if percent >= WARN_PERCENT:
        return "warn"
    return "good"


def _is_relevant_partition(part: Any) -> bool:
    mountpoint = str(getattr(part, "mountpoint", "") or "")
    fstype = str(getattr(part, "fstype", "") or "").lower()
    device = str(getattr(part, "device", "") or "")

    if not mountpoint:
        return False
    if fstype in _PSEUDO_FSTYPES:
        return False
    if any(
        mountpoint == p or mountpoint.startswith(p + "/") for p in _SKIP_MOUNT_PREFIXES
    ):
        return False
    if "overlay" in mountpoint or "/docker/" in mountpoint:
        return False
    if "containers/overlay" in mountpoint:
        return False
    if sys.platform == "win32":
        return bool(device) or mountpoint.endswith(":\\") or len(mountpoint) <= 3
    return bool(fstype or device)


def collect_storage_mounts() -> list[StorageMount]:
    """Return relevant mounts; never raises — skips bad mounts individually."""
    mounts: list[StorageMount] = []
    seen: set[str] = set()

    try:
        partitions = psutil.disk_partitions(all=True)
    except Exception:  # noqa: BLE001
        return []

    for part in partitions:
        try:
            if not _is_relevant_partition(part):
                continue
            mountpoint = str(part.mountpoint)
            if mountpoint in seen:
                continue
            try:
                usage = psutil.disk_usage(mountpoint)
            except (PermissionError, FileNotFoundError, OSError):
                continue
            if usage.total <= 0:
                continue
            percent = round(float(usage.percent), 1)
            total_display = _format_bytes(usage.total)
            used_display = _format_bytes(usage.used)
            free_display = _format_bytes(usage.free)
            mounts.append(
                StorageMount(
                    mountpoint=mountpoint,
                    device=str(part.device) or None,
                    fstype=str(part.fstype) or None,
                    total_bytes=int(usage.total),
                    used_bytes=int(usage.used),
                    free_bytes=int(usage.free),
                    percent=percent,
                    total_display=total_display,
                    used_display=used_display,
                    free_display=free_display,
                    summary=f"{used_display} / {total_display}",
                    tone=_tone_for_percent(percent),
                )
            )
            seen.add(mountpoint)
        except Exception:  # noqa: BLE001 - one bad mount never breaks inventory
            continue

    # Prefer root / system drive first, then alphabetical.
    def sort_key(item: StorageMount) -> tuple[int, str]:
        mp = item.mountpoint
        if mp in {"/", "C:\\", "C:/"}:
            return (0, mp)
        return (1, mp.lower())

    mounts.sort(key=sort_key)
    return mounts
