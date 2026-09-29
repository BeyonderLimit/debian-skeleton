from __future__ import annotations

from debian_skeleton import apt
from debian_skeleton.models import Simulation
from debian_skeleton.runner import CommandResult
from support import ScriptedRunner


def _result(argv, stdout="", stderr="", returncode=0):
    return CommandResult(
        argv=argv, returncode=returncode, stdout=stdout, stderr=stderr
    )


# -- dpkg-query -----------------------------------------------------------------


def test_parse_dpkg_query_only_counts_installed_statuses():
    text = (
        "bash-completion\tii \n"
        "curl\tii \n"
        "labwc\tun \n"
        "old-package\trc \n"
        "half-configured\tiU \n"
        "line without any tab\n"
    )
    assert apt.parse_dpkg_query(text) == frozenset({"bash-completion", "curl"})


def test_parse_dpkg_query_empty():
    assert apt.parse_dpkg_query("") == frozenset()


# -- apt-cache policy -------------------------------------------------------------


def test_parse_policy_keeps_only_stanzas_with_real_candidates():
    stdout = (
        "rsync:\n"
        "  Installed: (none)\n"
        "  Candidate: 3.2.7-1\n"
        "  Version table:\n"
        " *** 3.2.7-1 500\n"
        "\n"
        "held-back:\n"
        "  Installed: (none)\n"
        "  Candidate: (none)\n"
        "  Version table:\n"
        "\n"
    )
    stderr = "N: Unable to locate package labwc\n"
    asked = ("rsync", "held-back", "labwc", "never-heard-of")
    assert apt.parse_policy(stdout, stderr, asked) == ("rsync",)


# -- apt-get --simulate ------------------------------------------------------------


def test_parse_simulate_sorts_inst_names_and_ignores_conf():
    text = (
        "Inst xterm (372-1 Debian:12.5/stable [amd64])\n"
        "Inst rsync (3.2.7-1 Debian:12.5/stable [amd64])\n"
        "Inst openbox (3.6.1-9 Debian:12.5/stable [amd64])\n"
        "Conf rsync (3.2.7-1 Debian:12.5/stable [amd64])\n"
        "The following NEW packages will be installed:\n"
    )
    assert apt.parse_simulate(text) == ("openbox", "rsync", "xterm")


def test_parse_unavailable_covers_both_error_forms_and_dedupes():
    text = (
        "E: Unable to locate package no-such-pkg-xyz\n"
        "E: Package 'ghost' has no installation candidate\n"
        "E: Unable to locate package no-such-pkg-xyz\n"
    )
    assert apt.parse_unavailable(text) == ("no-such-pkg-xyz", "ghost")


# -- --print-uris / apt-cache show --------------------------------------------------


def test_parse_print_uris_sums_byte_fields_tolerating_locale_commas():
    text = (
        "'http://deb/x.deb' x.deb 1,024 SHA256:aa\n"
        "'http://deb/y.deb' y.deb 4096 SHA256:bb\n"
        "not a uri line at all\n"
    )
    assert apt.parse_print_uris(text) == 5120


def test_parse_print_uris_none_when_no_debs():
    assert apt.parse_print_uris("") is None


def test_parse_apt_show_sums_installed_sizes_kib_to_bytes():
    text = "Package: a\nInstalled-Size: 1935\n\nPackage: b\nInstalled-Size: 65\n"
    assert apt.parse_apt_show(text) == (1935 + 65) * 1024


def test_parse_apt_show_skips_garbage_and_is_none_when_absent():
    assert apt.parse_apt_show("Package: a\nInstalled-Size: big\n") is None
    assert apt.parse_apt_show("") is None


# -- collectors over the runner seam -------------------------------------------------


def test_query_installed_reads_through_the_runner():
    runner = ScriptedRunner(
        {apt.DPKG_QUERY_ARGV: _result(("dpkg-query",), "curl\tii \n")}
    )
    assert apt.query_installed(runner) == frozenset({"curl"})


def test_query_installed_nonzero_or_unmapped_is_none():
    failing = ScriptedRunner(
        {apt.DPKG_QUERY_ARGV: _result(("dpkg-query",), returncode=100)}
    )
    assert apt.query_installed(failing) is None
    assert apt.query_installed(ScriptedRunner({})) is None


def test_check_available_matches_on_policy_prefix():
    policy = _result(("apt-cache", "policy"), "rsync:\n  Candidate: 3.2.7-1\n")
    runner = ScriptedRunner({("apt-cache", "policy"): policy})
    assert apt.check_available(runner, ("rsync", "labwc")) == ("rsync",)


def test_simulate_empty_packages_returns_zeroes_without_running_anything():
    assert apt.simulate(ScriptedRunner({}), ()) == Simulation((), 0, 0, ())


def test_simulate_unmapped_commands_return_none():
    assert apt.simulate(ScriptedRunner({}), ("rsync",)) is None


def test_simulate_all_unavailable_short_circuits_before_apt_get():
    policy = _result(("apt-cache", "policy"), "N: Unable to locate package labwc\n")
    sim = apt.simulate(ScriptedRunner({("apt-cache", "policy"): policy}), ("labwc",))
    assert sim == Simulation((), None, None, ("labwc",))


def test_simulate_full_pass_over_the_trixie_fixture(make_env):
    env, _root = make_env("desktop-trixie")
    assert apt.simulate(env.runner, ("labwc",)) == Simulation(
        ("labwc",), 350000, 1536000, ()
    )


# -- install argv (apply-time) ---------------------------------------------------


def test_install_argv_shape_mirrors_what_plan_simulated():
    argv = apt.apt_install_argv(("rsync", "task-xfce-desktop"))
    assert argv == (
        "apt-get", "--yes",
        "-o", "Dpkg::Options::=--force-confdef",
        "-o", "Dpkg::Options::=--force-confold",
        "install", "--", "rsync", "task-xfce-desktop",
    )
    assert "--no-install-recommends" not in argv  # would break plan/apply parity
