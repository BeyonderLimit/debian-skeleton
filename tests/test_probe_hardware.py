from __future__ import annotations

from pathlib import Path

import pytest

from debian_skeleton.models import BlockDevice, DiskInfo, MemoryInfo
from debian_skeleton.probe.context import ProbeContext, ProbeEnv
from debian_skeleton.probe.hardware import (
    classify_laptop,
    parse_lsblk,
    parse_meminfo,
    probe_hardware,
)
from debian_skeleton.runner import CommandResult
from support import FakeStatvfs, ScriptedRunner


def make_context(
    tmp_path: Path,
    *,
    runner: ScriptedRunner | None = None,
    statvfs: object | None = None,
) -> ProbeContext:
    return ProbeContext(
        ProbeEnv(
            root=tmp_path,
            runner=runner if runner is not None else ScriptedRunner({}),
            statvfs=statvfs if statvfs is not None else FakeStatvfs(),
        )
    )


def dpkg_ok(stdout: str) -> ScriptedRunner:
    return ScriptedRunner(
        {("dpkg",): CommandResult(argv=("dpkg",), returncode=0, stdout=stdout, stderr="")}
    )


# -- memory ---------------------------------------------------------------


def test_parse_meminfo_reads_kib_values_and_skips_garbage():
    text = (
        "MemTotal:       16384000 kB\n"
        "MemAvailable:   12288000 kB\n"
        "SwapTotal:       4194304 kB\n"
        "HugePages_Total:       0\n"
        "no separator\n"
        "Broken: not-a-number kB\n"
    )
    values = parse_meminfo(text)
    assert values["MemTotal"] == 16384000
    assert values["MemAvailable"] == 12288000
    assert values["SwapTotal"] == 4194304
    assert values["HugePages_Total"] == 0
    assert "no separator" not in values
    assert "Broken" not in values


def test_memory_missing_file_warns_and_returns_nones(tmp_path: Path):
    ctx = make_context(tmp_path)

    memory = probe_hardware(ctx).memory

    assert memory == MemoryInfo(None, None, None)
    assert any("proc/meminfo" in warning for warning in ctx.warnings)


def test_memory_missing_memavailable_is_none(tmp_path: Path):
    (tmp_path / "proc").mkdir()
    (tmp_path / "proc/meminfo").write_text("MemTotal: 100 kB\n")

    memory = probe_hardware(make_context(tmp_path)).memory

    assert memory == MemoryInfo(100, None, None)


# -- architecture -----------------------------------------------------------


def test_architecture_trims_dpkg_output(tmp_path: Path):
    ctx = make_context(tmp_path, runner=dpkg_ok("  arm64 \n"))

    assert probe_hardware(ctx).architecture == "arm64"


def test_architecture_nonzero_dpkg_warns_and_returns_none(tmp_path: Path):
    runner = ScriptedRunner(
        {
            ("dpkg",): CommandResult(
                argv=("dpkg",), returncode=127, stdout="", stderr="not found"
            )
        }
    )
    ctx = make_context(tmp_path, runner=runner)

    assert probe_hardware(ctx).architecture is None
    assert any("dpkg" in warning for warning in ctx.warnings)


def test_architecture_missing_command_warns_and_returns_none(tmp_path: Path):
    ctx = make_context(tmp_path, runner=ScriptedRunner({}))

    assert probe_hardware(ctx).architecture is None
    assert any("dpkg" in warning for warning in ctx.warnings)


# -- root filesystem ----------------------------------------------------------


def test_root_fs_byte_math_from_fake_statvfs(tmp_path: Path):
    statvfs = FakeStatvfs(f_bsize=4096, f_blocks=10, f_bfree=4, f_bavail=3)
    ctx = make_context(tmp_path, statvfs=statvfs)

    assert probe_hardware(ctx).root_fs == DiskInfo(
        mount="/",
        block_size=4096,
        total_bytes=40960,
        free_bytes=16384,
        available_bytes=12288,
    )


def test_root_fs_statvfs_failure_warns_and_returns_nones(tmp_path: Path):
    class FailingStatvfs:
        def __call__(self, path: Path):
            raise OSError(13, "Permission denied")

    ctx = make_context(tmp_path, statvfs=FailingStatvfs())

    assert probe_hardware(ctx).root_fs == DiskInfo("/", None, None, None, None)
    assert any("statvfs" in warning for warning in ctx.warnings)


# -- block devices -------------------------------------------------------------


def test_parse_lsblk_nests_children_and_handles_null_mountpoint():
    devices = parse_lsblk(
        """
        {"blockdevices": [
           {"name": "nvme0n1", "type": "disk", "size": 1024209543168,
            "mountpoint": null, "model": "Samsung SSD 970",
            "children": [
               {"name": "nvme0n1p1", "type": "part", "size": 536870912,
                "mountpoint": "/boot/efi", "model": null},
               {"name": "nvme0n1p3", "type": "part", "size": 1027604480,
                "mountpoint": "[SWAP]", "model": null}
            ]}
        ]}
        """
    )
    (disk,) = devices
    assert disk == BlockDevice(
        name="nvme0n1",
        type="disk",
        size_bytes=1024209543168,
        mountpoint=None,
        model="Samsung SSD 970",
        children=(
            BlockDevice("nvme0n1p1", "part", 536870912, "/boot/efi", None),
            BlockDevice("nvme0n1p3", "part", 1027604480, "[SWAP]", None),
        ),
    )


def test_parse_lsblk_empty_output():
    assert parse_lsblk('{"blockdevices": []}') == ()


def test_block_devices_unparseable_json_warns_and_returns_empty(tmp_path: Path):
    runner = ScriptedRunner(
        {
            ("lsblk",): CommandResult(
                argv=("lsblk",), returncode=0, stdout="lsblk: broken{", stderr=""
            )
        }
    )
    ctx = make_context(tmp_path, runner=runner)

    assert probe_hardware(ctx).block_devices == ()
    assert any("lsblk" in warning for warning in ctx.warnings)


# -- laptop classification ---------------------------------------------------


@pytest.mark.parametrize(
    ("batteries", "chassis", "expected"),
    [
        ((), None, None),
        ((), 2, None),  # DMI "Unknown"
        ((), 99, None),  # outside the SMBIOS types we trust
        (("BAT0",), 3, True),  # a battery wins over a fixed chassis
        ((), 10, True),
        ((), 3, False),
        ((), 23, False),
    ],
)
def test_classify_laptop_truth_table(batteries, chassis, expected):
    verdict, _evidence = classify_laptop(batteries, chassis)
    assert verdict is expected


def test_classify_laptop_records_all_evidence():
    verdict, evidence = classify_laptop(("BAT0", "BAT1"), 3)
    assert verdict is True
    assert evidence == (
        "battery present: BAT0, BAT1",
        "DMI chassis type 3 (Desktop)",
    )


# -- fixture end-to-end --------------------------------------------------------


def test_laptop_bookworm_fixture_hardware(make_env):
    env, _root = make_env("laptop-bookworm")
    hardware = probe_hardware(ProbeContext(env))
    assert hardware.architecture == "amd64"
    assert hardware.memory.total_kib == 16384000
    assert hardware.is_laptop is True
    assert hardware.block_devices[0].name == "nvme0n1"
    assert hardware.root_fs.total_bytes == 107374182400


def test_server_minimal_fixture_hardware(make_env):
    env, _root = make_env("server-minimal")
    hardware = probe_hardware(ProbeContext(env))
    assert hardware.is_laptop is False
    assert hardware.block_devices[0].name == "sda"
