from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from debian_skeleton.models import (
    BlockDevice,
    DiskInfo,
    HardwareInfo,
    InstalledInfo,
    MemoryInfo,
    OsInfo,
    Probe,
    probe_to_json,
)
from debian_skeleton.probe import run_probe


def _laptop_bookworm(root: str) -> Probe:
    return Probe(
        root=root,
        os=OsInfo(
            id="debian",
            version_id="12",
            version_codename="bookworm",
            pretty_name="Debian GNU/Linux 12 (bookworm)",
            source_path="/etc/os-release",
        ),
        hardware=HardwareInfo(
            architecture="amd64",
            memory=MemoryInfo(16384000, 12288000, 4194304),
            root_fs=DiskInfo(
                mount="/",
                block_size=4096,
                total_bytes=107374182400,
                free_bytes=53687091200,
                available_bytes=47244640256,
            ),
            block_devices=(
                BlockDevice(
                    name="nvme0n1",
                    type="disk",
                    size_bytes=1024209543168,
                    mountpoint=None,
                    model="Samsung SSD 970",
                    children=(
                        BlockDevice("nvme0n1p1", "part", 536870912, "/boot/efi", None),
                        BlockDevice("nvme0n1p2", "part", 107374182400, "/", None),
                        BlockDevice("nvme0n1p3", "part", 1027604480, "[SWAP]", None),
                    ),
                ),
            ),
            is_laptop=True,
            laptop_evidence=(
                "battery present: BAT0",
                "DMI chassis type 10 (Notebook)",
            ),
        ),
        installed=InstalledInfo(
            x_sessions=("xfce",),
            wayland_sessions=("labwc",),
            xorg_path="/usr/bin/Xorg",
        ),
        warnings=(),
    )


def _server_minimal(root: str) -> Probe:
    return Probe(
        root=root,
        os=OsInfo(
            "debian", "12", "bookworm",
            "Debian GNU/Linux 12 (bookworm)", "/etc/os-release",
        ),
        hardware=HardwareInfo(
            architecture="amd64",
            memory=MemoryInfo(2097152, 1572864, 0),
            root_fs=DiskInfo("/", 4096, 21474836480, 16106127360, 15032385536),
            block_devices=(
                BlockDevice(
                    "sda", "disk", 214748364800, None, "WDC WD2003FYYS",
                    children=(BlockDevice("sda1", "part", 214748364800, "/", None),),
                ),
            ),
            is_laptop=False,
            laptop_evidence=("DMI chassis type 23 (Rack Mount Chassis)",),
        ),
        installed=InstalledInfo((), (), None),
        warnings=(),
    )


def _desktop_trixie(root: str) -> Probe:
    return Probe(
        root=root,
        os=OsInfo(
            "debian", "13", "trixie",
            "Debian GNU/Linux 13 (trixie)", "/etc/os-release",
        ),
        hardware=HardwareInfo(
            architecture="amd64",
            memory=MemoryInfo(8388608, 6291456, 2097152),
            root_fs=DiskInfo("/", 4096, 549755813888, 274877906944, 246960619520),
            block_devices=(
                BlockDevice(
                    "sda", "disk", 512110190592, None, "Kingston SA400M8",
                    children=(BlockDevice("sda1", "part", 511000000000, "/", None),),
                ),
            ),
            is_laptop=False,
            laptop_evidence=("DMI chassis type 3 (Desktop)",),
        ),
        installed=InstalledInfo((), ("labwc",), None),
        warnings=(),
    )


EXPECTED = {
    "laptop-bookworm": _laptop_bookworm,
    "server-minimal": _server_minimal,
    "desktop-trixie": _desktop_trixie,
}


@pytest.mark.parametrize("machine", sorted(EXPECTED))
def test_run_probe_matches_expected_snapshot(make_env, machine):
    env, root = make_env(machine)
    assert run_probe(env) == EXPECTED[machine](str(root))


def test_degraded_machine_never_crashes_and_warns(make_env):
    env, _root = make_env("degraded")

    probe = run_probe(env)

    assert probe.os.id is None
    assert probe.hardware.architecture is None
    assert probe.hardware.memory.total_kib is None
    assert probe.hardware.block_devices == ()
    assert probe.hardware.is_laptop is None
    assert len(probe.warnings) >= 3
    assert any("os-release" in warning for warning in probe.warnings)
    assert any("dpkg" in warning for warning in probe.warnings)
    assert any("lsblk" in warning for warning in probe.warnings)


def test_probe_is_frozen(make_env):
    env, _root = make_env("laptop-bookworm")
    probe = run_probe(env)
    with pytest.raises(FrozenInstanceError):
        probe.root = "/elsewhere"  # type: ignore[misc]


def test_probe_json_round_trip(make_env):
    env, _root = make_env("laptop-bookworm")
    probe = run_probe(env)
    payload = json.loads(probe_to_json(probe))
    assert payload["os"]["id"] == "debian"
    assert payload["hardware"]["is_laptop"] is True
    assert payload["hardware"]["block_devices"][0]["children"][1]["mountpoint"] == "/"
    assert payload["installed"]["x_sessions"] == ["xfce"]
    assert payload["warnings"] == []
