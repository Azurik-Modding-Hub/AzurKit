"""The D26 tiers, the empty skip allow-list and xdist's groups (``tests/conftest.py``)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_a_vanilla_test_without_its_image_stops_the_run_and_an_unlisted_skip_fails(pytester, monkeypatch, tmp_path):
    """A run that selects a USA test while ``AZURKIT_ISO`` names a file that
    isn't the vanilla image stops before any test runs, and so does one that
    selects a web test without Node; ``-m "not vanilla and not web"`` runs
    the pure tier, where a skip and an xfail fail the run and the summary
    still counts the tiers."""
    pytester.makeconftest("from tests.conftest import *  # noqa: F403\n")
    pytester.makepyfile(test_x="""
        import pytest

        def test_reads_the_image(usa_iso):
            pass

        def test_runs_under_pyodide(pyodide):
            pass

        def test_skips():
            pytest.skip("no tool here")

        @pytest.mark.xfail(reason="known red")
        def test_fails_expectedly():
            assert False

        def test_pure():
            pass
    """)
    (fake := tmp_path / "usa.iso").write_bytes(bytes(64))
    monkeypatch.setenv("AZURKIT_ISO", str(fake))
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    for workers in ((), ("-n", "2")):   # and on xdist's workers (D991)
        stopped = pytester.runpytest_subprocess("-p", "no:cacheprovider", *workers)
        assert stopped.ret == 4, workers
        assert f"{fake} is not the vanilla USA image" in stopped.stdout.str() + stopped.stderr.str()
        assert "test_pure PASSED" not in stopped.stdout.str()
    pure = pytester.runpytest_subprocess("-p", "no:cacheprovider", "-m", "not vanilla and not web", "-rA")
    pure.assert_outcomes(passed=1, failed=2, deselected=2)
    out = pure.stdout.str()
    assert "skip not in tests/skip_allowlist.toml: no tool here" in out
    assert "skip not in tests/skip_allowlist.toml: known red" in out
    assert "vanilla: 0 run" in out and "europe: 0 run" in out and "web: 0 run" in out
    monkeypatch.setenv("PATH", str(tmp_path))
    web = pytester.runpytest_subprocess("-p", "no:cacheprovider", "-m", "web")
    assert web.ret == 4 and "web tests need Node" in web.stdout.str() + web.stderr.str()


def test_under_loadgroup_the_frozen_apps_tests_share_one_worker_and_keep_their_allowed_skips(pytester, monkeypatch):
    """Under ``--dist loadgroup`` every test that takes the frozen app runs
    on one xdist worker (one freeze a run, D991), and an allow-listed skip
    among them stays allowed under its grouped id."""
    pytester.makeconftest("from tests.conftest import *  # noqa: F403\n"
                          "from tests import conftest\n"
                          "conftest.ALLOWED_SKIPS['test_g.py::test_listed'] = 'allowed here'\n")
    pytester.makepyfile(test_g="""
        import pytest

        @pytest.fixture(scope="module")
        def frozen_app():
            pass

        @pytest.mark.parametrize("n", range(4))
        def test_frozen(frozen_app, n):
            pass

        def test_listed(frozen_app):
            pytest.skip("allowed here")

        @pytest.mark.parametrize("n", range(4))
        def test_other(n):
            pass
    """)
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    run = pytester.runpytest_subprocess("-p", "no:cacheprovider", "-n", "4", "--dist", "loadgroup", "-v")
    run.assert_outcomes(passed=8, skipped=1)
    workers = re.findall(r"^\[(gw\d+)\] .*\b(?:PASSED|SKIPPED) test_g\.py::test_(?:frozen\[\d\]|listed)@frozen_app\b",
                         run.stdout.str(), re.M)
    assert len(workers) == 5 and len(set(workers)) == 1, run.stdout.str()


def test_a_worker_killed_under_either_ci_tiers_flags_ends_the_run_and_names_its_test(pytester, monkeypatch):
    """``tests.yml`` runs both tiers on each matrix row's workers. A worker
    killed there (a runner short of memory) ends the run with a FAILED line
    naming its test: left to replace it, xdist 3.8 under ``loadgroup`` never
    ends the run, so the job would sit to its cap with nothing printed."""
    text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    flags = re.findall(r"--numprocesses=\$\{\{ matrix\.workers \}\} (--dist=loadgroup --max-worker-restart=0)", text)
    assert len(flags) == 2 and len(re.findall(r"\{os: [\w.-]+, label: [\w-]+, workers: [1-9]\}", text)) == 8
    pytester.makeconftest("from tests.conftest import *  # noqa: F403\n")
    pytester.makepyfile(test_d="import os\n\ndef test_passes():\n    pass\n\ndef test_dies():\n    os._exit(9)\n")
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    for workers in (1, 2):
        run = pytester.runpytest_subprocess("-p", "no:cacheprovider", f"--numprocesses={workers}", *flags[0].split(),
                                            timeout=120)
        assert run.ret == pytest.ExitCode.TESTS_FAILED, run.stdout.str()
        run.stdout.fnmatch_lines(["FAILED test_d.py::test_dies - worker 'gw*' crashed*"])


def test_the_ci_vanilla_tiers_printed_summary_names_its_slowest_tests(pytester, monkeypatch):
    """``tests.yml``'s vanilla tier prints only its log's tail and its summary from conftest's ``vanilla: N run`` on,
    and that summary holds pytest's ``--durations`` (each test phase past a minute, the slowest 60): run 41779807138's
    Intel tier took 293 min where 4a178cc's took 159, and its log named no test's time."""
    text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    flags, = re.findall(r"--max-worker-restart=0 (--durations=\d+ --durations-min=\d+) >", text)
    assert text.count("sed -n '/^vanilla: /,$p' \"$log\" | head -n 200") == 1
    pytester.makeconftest("from tests.conftest import *  # noqa: F403\n")
    pytester.makepyfile(test_t="import time\n\ndef test_takes_a_while():\n    time.sleep(0.3)\n")
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    run = pytester.runpytest_subprocess("-p", "no:cacheprovider", "--numprocesses=1", *flags.split(),
                                        "--durations-min=0.2", timeout=120)
    lines = run.stdout.str().splitlines()
    printed = lines[next(i for i, line in enumerate(lines) if line.startswith("vanilla: ")):][:200]
    assert any(re.search(r"slowest \d+ durations", line) for line in printed), run.stdout.str()
    assert any(re.match(r"\d+\.\d+s call +test_t\.py::test_takes_a_while$", line) for line in printed), printed


def test_the_ci_tier_takes_the_roomiest_disk_frees_unused_toolchains_when_short_and_stops_by_name_below_its_need(
        tmp_path, monkeypatch, capsys):
    """``tests.yml``'s tier folder, before the images land (``scripts/ci_resources.py --room``): on the disk with the
    most free room, once that holds the two images and the most the tier's writes took (run 41981438506's Linux runner,
    on AWS, had 9.5 GiB free past the images where each Azure one had 78.3, and fell to 3.8). Short of that and a
    margin, the toolchains it names go first, each one's freed room printed; still short, it stops by name and makes
    nothing. It prints labels and numbers, never a path."""
    from scripts import ci_resources
    text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert text.index("scripts/ci_resources.py --room --env=\"$GITHUB_ENV\"") < text.index("image parts usa.iso")
    gib, need = 1 << 30, 14 << 30
    disks = {"root": 0, "eph": 0, "toolchain": False}
    spare = tmp_path / "root" / "toolchain"

    def usage(path):   # each folder's disk by its first part under tmp_path; a toolchain deleted frees root 25 GiB
        disk = Path(path).relative_to(tmp_path).parts[0]
        freed = disk == "root" and disks["toolchain"] and not spare.exists()
        return shutil._ntuple_diskusage(0, 0, disks[disk] + 25 * gib * freed)
    monkeypatch.setattr(ci_resources.shutil, "disk_usage", usage)
    for root, eph, toolchain, chosen in ((9, 66, True, "eph"), (80, 66, True, "root"), (12, None, True, "root"),
                                         (9, None, False, None)):
        for made in ("root", "eph", "env"):
            shutil.rmtree(tmp_path / made, ignore_errors=True)
        (tmp_path / "root").mkdir()
        if eph is not None:
            (tmp_path / "eph").mkdir()
        if toolchain:
            spare.mkdir()
            (spare / "bin").write_bytes(b"\0")
        disks.update(root=root * gib, eph=(eph or 0) * gib, toolchain=toolchain)
        (tmp_path / "env").mkdir()
        env = tmp_path / "env" / "github_env"
        code = ci_resources.main(["--room", f"--env={env}", f"--need={need}", f"runner={tmp_path / 'root' / 'tier'}",
                                  f"mnt={tmp_path / 'eph' / 'tier'}", f"--spare=toolchain={spare}"])
        out = capsys.readouterr().out
        assert str(tmp_path) not in out, out
        assert re.match(r"room before the images: runner [\d.]+ GiB free(, mnt [\d.]+ GiB free)?; the tier needs 14\.0 "
                        r"\(the two images and the most its writes took\), 19\.0 with its margin\n", out), out
        assert spare.exists() == (toolchain and max(root, eph or 0) >= 19), out
        if chosen is None:
            assert code == 1 and not env.exists() and not (tmp_path / "root" / "tier").exists(), out
            assert out.endswith("::error::the tier needs 14.0 GiB free on one disk, and the roomiest (runner) has 9.0: "
                                "stopping before the images land\n"), out
            continue
        folder = tmp_path / chosen / "tier"
        assert code == 0 and env.read_text(encoding="utf-8") == f"TIER_ROOM={folder}\n", out
        assert (folder / "iso").is_dir() and (folder / "tmp").is_dir(), out
        label = {"root": "runner", "eph": "mnt"}[chosen]
        assert out.endswith(f"the tier's folder: {label}\n"), out
        if root < 19 and eph is None:
            assert "toolchain: freed 25.0 GiB\nroom after freeing the unused toolchains: runner 37.0 GiB free\n" in out
