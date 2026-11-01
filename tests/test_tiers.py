"""The D26 tiers, the empty skip allow-list and xdist's groups (``tests/conftest.py``)."""

from __future__ import annotations

import re
from pathlib import Path

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
