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
    assert not _is_relevant_partition(
        SimpleNamespace(
            mountpoint="/etc/hostname", fstype="", device="/dev/sda1", opts="bind"
        )
    )
    assert not _is_relevant_partition(
        SimpleNamespace(
            mountpoint="/etc/hosts", fstype="", device="/dev/sda1", opts="bind"
        )
    )
    assert not _is_relevant_partition(
        SimpleNamespace(
            mountpoint="/data", fstype="ext4", device="/dev/sda1", opts="bind"
        )
    )


def test_keeps_real_mounts():
    with patch("app.storage.os.path.isdir", return_value=True):
        assert _is_relevant_partition(
            SimpleNamespace(
                mountpoint="/", fstype="ext4", device="/dev/sda1", opts="rw"
            )
        )
        assert _is_relevant_partition(
            SimpleNamespace(
                mountpoint="/mnt/media", fstype="xfs", device="/dev/sdb1", opts="rw"
            )
        )
        assert _is_relevant_partition(
            SimpleNamespace(
                mountpoint="/srv/media", fstype="ext4", device="/dev/sdc1", opts="rw"
            )
        )


def test_hostfs_prefix_filters_container_mounts_and_rewrites_paths():
    parts = [
        SimpleNamespace(mountpoint="/", fstype="overlay", device="overlay", opts="rw"),
        SimpleNamespace(
            mountpoint="/data", fstype="ext4", device="/dev/sda1", opts="bind"
        ),
        SimpleNamespace(
            mountpoint="/etc/hostname", fstype="", device="/dev/sda1", opts="bind"
        ),
        SimpleNamespace(
            mountpoint="/hostfs", fstype="ext4", device="/dev/sda1", opts="rw"
        ),
        SimpleNamespace(
            mountpoint="/hostfs/srv/media", fstype="xfs", device="/dev/sdb1", opts="rw"
        ),
        SimpleNamespace(
            mountpoint="/hostfs/data", fstype="ext4", device="/dev/sda1", opts="bind"
        ),
    ]

    def fake_usage(path: str):
        if path == "/hostfs":
            return SimpleNamespace(
                total=221_000_000_000,
                used=7_240_000_000,
                free=202_000_000_000,
                percent=4.0,
            )
        if path == "/hostfs/srv/media":
            return SimpleNamespace(
                total=4_000_000_000_000,
                used=1_000_000_000_000,
                free=3_000_000_000_000,
                percent=25.0,
            )
        if path == "/hostfs/data":
            # Same device as root — should be deduped away.
            return SimpleNamespace(
                total=221_000_000_000,
                used=7_240_000_000,
                free=202_000_000_000,
                percent=4.0,
            )
        raise AssertionError(path)

    def fake_stat(path: str):
        if path in {"/hostfs", "/hostfs/data"}:
            return SimpleNamespace(st_dev=1)
        if path == "/hostfs/srv/media":
            return SimpleNamespace(st_dev=2)
        return SimpleNamespace(st_dev=99)

    with (
        patch("app.storage.psutil.disk_partitions", return_value=parts),
        patch("app.storage.psutil.disk_usage", side_effect=fake_usage),
        patch("app.storage.os.path.isdir", return_value=True),
        patch("app.storage.os.stat", side_effect=fake_stat),
        patch("app.storage.sys.platform", "linux"),
        patch.dict("os.environ", {"HOST_FS_ROOT": "/hostfs"}, clear=False),
    ):
        mounts = collect_storage_mounts(host_fs_root="/hostfs")

    assert [m.mountpoint for m in mounts] == ["/", "/srv/media"]
    assert mounts[0].percent == 4.0
    assert mounts[1].percent == 25.0


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
        patch("app.storage.os.path.isdir", return_value=True),
        patch("app.storage.os.stat", return_value=SimpleNamespace(st_dev=1)),
        patch("app.storage.sys.platform", "linux"),
    ):
        mounts = collect_storage_mounts()

    assert len(mounts) == 1
    assert mounts[0].mountpoint == "/"
    assert mounts[0].percent == 35.0
    assert mounts[0].tone == "good"


def test_dedupes_bind_alias_on_same_device():
    parts = [
        SimpleNamespace(mountpoint="/", fstype="ext4", device="/dev/sda1", opts="rw"),
        SimpleNamespace(
            mountpoint="/mnt/root-alias", fstype="ext4", device="/dev/sda1", opts="bind"
        ),
    ]
    usage = SimpleNamespace(total=100, used=40, free=60, percent=40.0)

    with (
        patch("app.storage.psutil.disk_partitions", return_value=parts),
        patch("app.storage.psutil.disk_usage", return_value=usage),
        patch("app.storage.os.path.isdir", return_value=True),
        patch("app.storage.os.stat", return_value=SimpleNamespace(st_dev=10)),
        patch("app.storage.sys.platform", "linux"),
    ):
        mounts = collect_storage_mounts()

    assert len(mounts) == 1
    assert mounts[0].mountpoint == "/"


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
        patch("app.storage.os.path.isdir", return_value=True),
        patch("app.storage.os.stat", return_value=SimpleNamespace(st_dev=1)),
        patch("app.storage.sys.platform", "linux"),
    ):
        mounts = collect_storage_mounts()

    assert mounts[0].tone == "bad"
