"""Storage mount inventory tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.storage import _is_relevant_partition, collect_storage_mounts


def test_skips_pseudo_and_docker_mounts():
    assert not _is_relevant_partition(
        SimpleNamespace(mountpoint="/proc", fstype="proc", device="proc", opts="")
    )
    assert not _is_relevant_partition(
        SimpleNamespace(mountpoint="/sys", fstype="sysfs", device="sysfs", opts="")
    )
    assert not _is_relevant_partition(
        SimpleNamespace(mountpoint="/run", fstype="tmpfs", device="tmpfs", opts="")
    )
    assert not _is_relevant_partition(
        SimpleNamespace(
            mountpoint="/var/lib/docker/overlay2/abc",
            fstype="overlay",
            device="overlay",
            opts="",
        )
    )


def test_keeps_real_mounts():
    assert _is_relevant_partition(
        SimpleNamespace(mountpoint="/", fstype="ext4", device="/dev/sda1", opts="rw")
    )
    assert _is_relevant_partition(
        SimpleNamespace(
            mountpoint="/mnt/media", fstype="xfs", device="/dev/sdb1", opts="rw"
        )
    )


def test_collect_storage_mounts_skips_inaccessible():
    parts = [
        SimpleNamespace(mountpoint="/", fstype="ext4", device="/dev/sda1", opts="rw"),
        SimpleNamespace(
            mountpoint="/mnt/dead", fstype="ext4", device="/dev/sdc1", opts="rw"
        ),
        SimpleNamespace(mountpoint="/proc", fstype="proc", device="proc", opts=""),
    ]

    def fake_usage(path: str):
        if path == "/mnt/dead":
            raise OSError("disconnected")
        if path == "/":
            return SimpleNamespace(
                total=100_000_000_000,
                used=35_000_000_000,
                free=65_000_000_000,
                percent=35.0,
            )
        raise AssertionError(path)

    with (
        patch("app.storage.psutil.disk_partitions", return_value=parts),
        patch("app.storage.psutil.disk_usage", side_effect=fake_usage),
        patch("app.storage.sys.platform", "linux"),
    ):
        mounts = collect_storage_mounts()

    assert len(mounts) == 1
    assert mounts[0].mountpoint == "/"
    assert mounts[0].percent == 35.0
    assert mounts[0].tone == "good"
    assert "free" in mounts[0].free_display.lower() or "GB" in mounts[0].free_display


def test_high_usage_tone():
    parts = [
        SimpleNamespace(mountpoint="/", fstype="ext4", device="/dev/sda1", opts="rw"),
    ]

    with (
        patch("app.storage.psutil.disk_partitions", return_value=parts),
        patch(
            "app.storage.psutil.disk_usage",
            return_value=SimpleNamespace(total=100, used=94, free=6, percent=94.0),
        ),
        patch("app.storage.sys.platform", "linux"),
    ):
        mounts = collect_storage_mounts()

    assert mounts[0].tone == "bad"
