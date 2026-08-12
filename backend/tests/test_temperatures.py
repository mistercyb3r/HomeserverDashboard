"""Temperature helper tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app import temperatures as temp_mod


def test_missing_sensors_returns_none():
    with (
        patch.object(
            temp_mod.psutil, "sensors_temperatures", create=True, return_value={}
        ),
        patch.object(temp_mod, "_cpu_temp_from_sysfs", return_value=None),
    ):
        assert temp_mod.cpu_temperature_c() is None


def test_prefers_package_label():
    entries = [
        SimpleNamespace(label="Package id 0", current=48.0),
        SimpleNamespace(label="Core 0", current=55.0),
        SimpleNamespace(label="Core 1", current=56.0),
    ]
    with patch.object(
        temp_mod.psutil,
        "sensors_temperatures",
        create=True,
        return_value={"coretemp": entries},
    ):
        assert temp_mod.cpu_temperature_c() == 48.0


def test_nvme_temperature():
    with patch.object(
        temp_mod.psutil,
        "sensors_temperatures",
        create=True,
        return_value={
            "nvme": [SimpleNamespace(label="Composite", current=37.0)],
        },
    ):
        assert temp_mod.nvme_temperature_c() == 37.0
