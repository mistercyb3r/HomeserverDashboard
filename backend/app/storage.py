"""Lightweight mounted-filesystem inventory via psutil.

Shows real host filesystems only — no Docker bind junk, no folder walks.
"""

from __future__ import annotations

import os
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
    "/var/lib/kubelet",
)

# Single-file / config binds Docker injects into containers.
_SKIP_EXACT_MOUNTS = {
    "/etc/hostname",
    "/etc/hosts",
    "/etc/resolv.conf",
    "/etc/timezone",
    "/etc/localtime",
    "/data",  # app config volume — same disk as host root when bind-mounted
}


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


def _host_fs_root(override: str | None = None) -> str | None:
    """Optional host root bind (e.g. /hostfs) for containers."""
    if override is not None:
        raw = str(override).strip().rstrip("/")
    else:
        raw = (os.environ.get("HOST_FS_ROOT") or "").strip().rstrip("/")
    return raw or None


def _display_mountpoint(mountpoint: str, host_root: str | None) -> str:
    if not host_root:
        return mountpoint
    if mountpoint == host_root:
        return "/"
    prefix = host_root + "/"
    if mountpoint.startswith(prefix):
        return "/" + mountpoint[len(prefix) :].lstrip("/")
    return mountpoint


def _is_under_host_root(mountpoint: str, host_root: str | None) -> bool:
    if not host_root:
        return True
    return mountpoint == host_root or mountpoint.startswith(host_root + "/")


def _is_relevant_partition(
    part: Any, *, host_root: str | None = None, allow_overlay_root: bool = False
) -> bool:
    mountpoint = str(getattr(part, "mountpoint", "") or "")
    fstype = str(getattr(part, "fstype", "") or "").lower()
    device = str(getattr(part, "device", "") or "")

    if not mountpoint:
        return False

    if host_root and not _is_under_host_root(mountpoint, host_root):
        # When viewing hostfs, ignore the container's own root/overlay mounts.
        return False

    display = _display_mountpoint(mountpoint, host_root)

    if display in _SKIP_EXACT_MOUNTS:
        return False
    if display.startswith("/etc/") or display == "/etc":
        return False
    if any(display == p or display.startswith(p + "/") for p in _SKIP_MOUNT_PREFIXES):
        return False
    if "overlay" in display or "/docker/" in display:
        return False
    if "containers/overlay" in display:
        return False

    # Skip non-directory binds (Docker injects files as mounts).
    try:
        if not os.path.isdir(mountpoint):
            return False
    except OSError:
        return False

    if fstype in _PSEUDO_FSTYPES:
        # Container root is often overlay — only keep it when not using hostfs.
        if (
            allow_overlay_root
            and not host_root
            and display == "/"
            and fstype == "overlay"
        ):
            return True
        return False

    if sys.platform == "win32":
        return bool(device) or display.endswith(":\\") or len(display) <= 3
    return bool(fstype or device)


def _device_key(mountpoint: str, device: str) -> str:
    try:
        st = os.stat(mountpoint)
        return f"dev:{st.st_dev}"
    except OSError:
        return f"path:{device or mountpoint}"


def collect_storage_mounts(*, host_fs_root: str | None = None) -> list[StorageMount]:
    """Return distinct host filesystems; never raises — skips bad mounts individually."""
    mounts: list[StorageMount] = []
    host_root = _host_fs_root(host_fs_root)
    allow_overlay_root = host_root is None

    try:
        partitions = psutil.disk_partitions(all=True)
    except Exception:  # noqa: BLE001
        return []

    candidates: list[tuple[str, str, str | None, str | None, Any]] = []
    for part in partitions:
        try:
            if not _is_relevant_partition(
                part, host_root=host_root, allow_overlay_root=allow_overlay_root
            ):
                continue
            mountpoint = str(part.mountpoint)
            display = _display_mountpoint(mountpoint, host_root)
            try:
                usage = psutil.disk_usage(mountpoint)
            except (PermissionError, FileNotFoundError, OSError):
                continue
            if usage.total <= 0:
                continue
            candidates.append(
                (
                    display,
                    mountpoint,
                    str(part.device) or None,
                    str(part.fstype) or None,
                    usage,
                )
            )
        except Exception:  # noqa: BLE001
            continue

    # One entry per underlying device — prefer the shortest mountpoint ("/" over binds).
    by_device: dict[str, tuple[str, str, str | None, str | None, Any]] = {}
    for display, mountpoint, device, fstype, usage in candidates:
        key = _device_key(mountpoint, device or "")
        existing = by_device.get(key)
        if existing is None:
            by_device[key] = (display, mountpoint, device, fstype, usage)
            continue
        prev_display = existing[0]
        if display == "/" or (prev_display != "/" and len(display) < len(prev_display)):
            by_device[key] = (display, mountpoint, device, fstype, usage)

    for display, _mountpoint, device, fstype, usage in by_device.values():
        percent = round(float(usage.percent), 1)
        total_display = _format_bytes(usage.total)
        used_display = _format_bytes(usage.used)
        free_display = _format_bytes(usage.free)
        mounts.append(
            StorageMount(
                mountpoint=display,
                device=device,
                fstype=fstype,
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

    def sort_key(item: StorageMount) -> tuple[int, str]:
        mp = item.mountpoint
        if mp in {"/", "C:\\", "C:/"}:
            return (0, mp)
        return (1, mp.lower())

    mounts.sort(key=sort_key)
    return mounts
