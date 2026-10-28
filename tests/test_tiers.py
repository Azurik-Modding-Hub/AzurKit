"""The D26 tiers and the empty skip allow-list (``tests/conftest.py``)."""

from __future__ import annotations

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
    stopped = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    assert stopped.ret == 4
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
