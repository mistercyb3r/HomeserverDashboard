"""CPU / NVMe temperature helpers (psutil + optional sysfs)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import psutil

_CPU_SENSOR_KEYS = (
    "coretemp",
    "k10temp",
    "zenpower",
    "cpu_thermal",
    "acpitz",
    "acpi",
    "cpu0_thermal",
    "soc_thermal",
)

_PACKAGE_NAME_RE = re.compile(r"(package|tctl|tdie|cpu|soc|physical id)", re.IGNORECASE)


def _read_sysfs_millidegrees(path: Path) -> float | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        value = int(raw)
    except (OSError, ValueError):
        return None
    # hwmon/thermal use millidegrees Celsius
    if value > 1000:
        return round(value / 1000.0, 1)
    if 0 <= value <= 150:
        return float(value)
    return None


def _sys_root() -> Path:
    raw = (os.environ.get("HOST_SYS_ROOT") or "/sys").strip() or "/sys"
    return Path(raw)


def _cpu_temp_from_sysfs() -> float | None:
    sys_root = _sys_root()
    thermal = sys_root / "class" / "thermal"
    if thermal.is_dir():
        preferred: list[float] = []
        fallback: list[float] = []
        try:
            zones = sorted(thermal.glob("thermal_zone*"))
        except OSError:
            zones = []
        for zone in zones:
            typ = ""
            try:
                typ = (zone / "type").read_text(encoding="utf-8").strip().lower()
            except OSError:
                pass
            temp = _read_sysfs_millidegrees(zone / "temp")
            if temp is None:
                continue
            if any(token in typ for token in ("cpu", "pkg", "x86", "soc", "package")):
                preferred.append(temp)
            elif "acpi" in typ or typ.endswith("thermal"):
                fallback.append(temp)
        if preferred:
            return preferred[0]
        if fallback:
            return fallback[0]

    hwmon = sys_root / "class" / "hwmon"
    if hwmon.is_dir():
        try:
            chips = sorted(hwmon.glob("hwmon*"))
        except OSError:
            chips = []
        for chip in chips:
            name = ""
            try:
                name = (chip / "name").read_text(encoding="utf-8").strip().lower()
            except OSError:
                pass
            if name and name not in {
                "coretemp",
                "k10temp",
                "zenpower",
                "cpu_thermal",
                "acpitz",
            }:
                if "nvme" in name or "gpu" in name:
                    continue
            package: list[float] = []
            cores: list[float] = []
            for label_path in chip.glob("temp*_label"):
                try:
                    label = label_path.read_text(encoding="utf-8").strip()
                except OSError:
                    continue
                input_path = Path(str(label_path).replace("_label", "_input"))
                temp = _read_sysfs_millidegrees(input_path)
                if temp is None:
                    continue
                if _PACKAGE_NAME_RE.search(label):
                    package.append(temp)
                else:
                    cores.append(temp)
            if package:
                return package[0]
            if cores:
                return round(sum(cores) / len(cores), 1)
            # unlabeled temp1_input
            temp = _read_sysfs_millidegrees(chip / "temp1_input")
            if temp is not None and name in {
                "coretemp",
                "k10temp",
                "zenpower",
                "cpu_thermal",
                "acpitz",
                "",
            }:
                return temp
    return None


def _pick_from_entries(entries: list[Any]) -> float | None:
    if not entries:
        return None
    package = [
        e.current
        for e in entries
        if e.current is not None and e.label and _PACKAGE_NAME_RE.search(e.label)
    ]
    if package:
        return round(package[0], 1)
    values = [e.current for e in entries if e.current is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def cpu_temperature_c() -> float | None:
    """Best-effort CPU/package temperature in °C, or None if unavailable."""
    sensors_temperatures = getattr(psutil, "sensors_temperatures", None)
    temps = None
    if callable(sensors_temperatures):
        try:
            temps = sensors_temperatures(fahrenheit=False)
        except (AttributeError, NotImplementedError, RuntimeError, OSError, TypeError):
            temps = None

    if temps:
        for key in _CPU_SENSOR_KEYS:
            picked = _pick_from_entries(list(temps.get(key) or []))
            if picked is not None:
                return picked
        for key, entries in temps.items():
            if "nvme" in key.lower() or "gpu" in key.lower():
                continue
            picked = _pick_from_entries(list(entries or []))
            if picked is not None:
                return picked

    return _cpu_temp_from_sysfs()


def nvme_temperature_c() -> float | None:
    """Best-effort first NVMe temperature in °C, or None."""
    sensors_temperatures = getattr(psutil, "sensors_temperatures", None)
    temps = None
    if callable(sensors_temperatures):
        try:
            temps = sensors_temperatures(fahrenheit=False)
        except (AttributeError, NotImplementedError, RuntimeError, OSError, TypeError):
            temps = None
    if temps:
        for key, entries in temps.items():
            if "nvme" not in key.lower():
                continue
            values = [e.current for e in entries if e.current is not None]
            if values:
                return round(values[0], 1)

    sys_root = _sys_root()
    hwmon = sys_root / "class" / "hwmon"
    if not hwmon.is_dir():
        return None
    try:
        chips = sorted(hwmon.glob("hwmon*"))
    except OSError:
        return None
    for chip in chips:
        try:
            name = (chip / "name").read_text(encoding="utf-8").strip().lower()
        except OSError:
            continue
        if "nvme" not in name:
            continue
        temp = _read_sysfs_millidegrees(chip / "temp1_input")
        if temp is not None:
            return temp
    return None
