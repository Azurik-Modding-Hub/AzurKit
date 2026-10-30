"""The landing tools: ``scripts/fullsuite.py``'s changed-area plan and
``scripts/land.py``'s gate: a fast-forward and a passing receipt."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from scripts import fullsuite, land

ROOT = Path(__file__).resolve().parent.parent
SMOKE = sorted(fullsuite.SMOKE)


def test_the_changed_area_plan_picks_importers_and_falls_back_to_the_whole_suite():
    """A changed module selects every test file that reaches it through
    imports; src/ adds the files that run the whole package (SRC_TESTS);
    docs select only the smoke files (the lint files, the oracle's test and
    the gate's, whose USA and Europe cases make every receipt run both
    tiers); the suite's configuration, what every session
    loads and an unknown path make it whole. The session loads only
    what tests/conftest.py imports (it checks the app in a Python of its
    own), so here a change to the sdk is changed-area."""
    deps = {"azurkit": set(), "azurkit.core": {"azurkit"}, "azurkit.core.iso": {"azurkit", "azurkit.core"},
            "azurkit.core.gate": {"azurkit", "azurkit.core"},
            "azurkit.sdk": {"azurkit", "azurkit.core", "azurkit.core.iso"},
            "tests.conftest": {"azurkit", "azurkit.core", "azurkit.core.gate"},
            "tests.test_sdk": {"azurkit", "azurkit.sdk"}, "tests.test_oracle": {"azurkit.core.iso"},
            "tests.test_wheel": {"azurkit"}, "tests.test_other": {"json"}}
    assert "tests/test_oracle.py" in SMOKE
    assert any("pytest.mark.europe" in (ROOT / f).read_text(encoding="utf-8") for f in SMOKE)   # D26
    assert fullsuite.plan(["src/azurkit/core/iso.py"], deps) == sorted(
        {*SMOKE, "tests/test_sdk.py", *fullsuite.SRC_TESTS})
    assert fullsuite.plan(["tests/test_other.py", "AGENTS.md", "tests/sdk_api.txt"], deps) == sorted(
        {*SMOKE, "tests/test_other.py"})
    assert fullsuite.plan(["bootstrap.py"], deps) == SMOKE
    for whole in ("pyproject.toml", "uv.lock", "tests/conftest.py", "src/azurkit/core/gate.py", "assets/icon/a.icns"):
        assert fullsuite.plan([whole], deps) is None, whole
    assert fullsuite.plan(["src/azurkit/sdk.py"], fullsuite.graph(ROOT)) is not None


def test_a_change_in_the_oracle_or_the_goldens_picks_the_test_files_that_read_them():
    """tests/oracle/ and tests/goldens/ are read by path, not imported: a
    change in one picks each test file that reaches a module naming it
    (``scripts/oracle_sync.py``'s ORACLE, ``scripts/record_goldens.py``'s
    GOLDENS, ``tests/test_art.py``'s own), not the smoke files alone."""
    deps = fullsuite.graph(ROOT)
    oracle = fullsuite.plan(["tests/oracle/models/probes.json", "tests/oracle/ORACLE.toml"], deps)
    assert {f"tests/test_{name}.py" for name in ("characters", "hosts", "shims", "randomizer", "art", "site",
                                                 "packs")} <= set(oracle) - set(SMOKE)
    goldens = fullsuite.plan(["tests/goldens/packs.json"], deps)
    assert {f"tests/test_{name}.py" for name in ("packs", "builds", "shims", "xbr", "fps_unlock")} <= set(goldens)
    assert "tests/test_art.py" not in goldens and "tests/test_xbr.py" not in oracle


def test_the_page_picks_the_site_app_and_icon_tests_and_the_docs_they_restate_pick_theirs():
    """D970: a change under web/ selects the site's, the app's and the
    favicons' test files; LICENSE and NOTICE.md the About tab's test (inside
    its file when that is picked whole) and the wheel's, README.md the
    wheel's, any other doc only the smoke files. Each rule names a test file
    and test that exist, and SRC_TESTS every test file whose tests run the
    package outside the import graph (the pyodide, browser and frozen_app
    fixtures) besides the wheel's."""
    deps = {"tests.test_site": {"json"}, "tests.test_hosts": {"json"}, "tests.test_wheel": {"json"}}
    page = ["tests/test_hosts.py", "tests/test_icon.py", "tests/test_site.py"]
    assert fullsuite.plan(["web/app.mjs", "web/favicon.ico"], deps) == sorted({*SMOKE, *page})
    assert fullsuite.plan(["NOTICE.md"], deps) == sorted({*SMOKE, fullsuite.ABOUT, "tests/test_wheel.py"})
    assert fullsuite.plan(["LICENSE", "web/index.html"], deps) == sorted({*SMOKE, *page, "tests/test_wheel.py"})
    assert fullsuite.plan(["README.md", "AGENTS.md", "CLAUDE.md"], deps) == sorted({*SMOKE, "tests/test_wheel.py"})
    assert fullsuite.plan(["AGENTS.md", "docs/plan.md"], deps) == SMOKE
    for test in {test for _, tests in fullsuite.RULES for test in tests}:
        file, _, name = test.partition("::")
        assert f"\ndef {name}(" in (ROOT / file).read_text(encoding="utf-8") if name else (ROOT / file).is_file(), test
    runs = {f"tests/{p.name}" for p in (ROOT / "tests").glob("test_*.py") if re.search(
        r"^def test_\w+\([^)]*\b(pyodide|browser|frozen_app)\b", p.read_text(encoding="utf-8"), re.M)}
    assert sorted({fullsuite.WHEEL, *runs}) == sorted(fullsuite.SRC_TESTS)


def test_a_changed_area_run_drives_the_page_in_chromium_alone_and_a_whole_run_in_every_browser(
        tmp_path, monkeypatch, pytester):
    """D970: a changed-area run's receipt names Chromium and its pytest
    command asks for it alone (``--browsers``), keyed so a receipt for other
    browsers is another; a whole run's names every browser and asks for no
    narrowing. The ``browser`` fixture runs a test in each browser it is
    given, every one by default."""
    _, lane, _, _ = _repo(tmp_path, monkeypatch)
    (lane / "README.md").write_text("a doc\n", encoding="utf-8")
    _git(lane, "add", "README.md")
    _git(lane, "commit", "-q", "-m", "a doc")
    changed, whole = fullsuite.prepare(lane, True, "main"), fullsuite.prepare(lane, False, "main")
    assert (changed["mode"], changed["browsers"], whole["mode"], whole["browsers"]) == (
        "changed", ["chromium"], "full", "all")
    asks = {run: [a for a in fullsuite.command(m) if a.startswith("--browsers")]
            for run, m in (("changed", changed), ("whole", whole))}
    assert asks == {"changed": ["--browsers=chromium"], "whole": []}
    monkeypatch.setattr(fullsuite, "CHANGED_BROWSERS", ("webkit",))
    assert fullsuite.prepare(lane, True, "main")["key"] != changed["key"]
    pytester.makeconftest("from tests.conftest import *  # noqa: F403\n\n\n"
                          "def pytest_deselected(items):\n    print('ran in', *(item.nodeid for item in items))\n")
    pytester.makepyfile(test_x="def test_page(browser):\n    pass\n")
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    for run, ids in (("changed", "[chromium]"), ("whole", "[chromium] test_x.py::test_page[webkit]")):
        done = pytester.runpytest_subprocess("-p", "no:cacheprovider", "-s", "--collect-only", "-m", "not web",
                                             *asks[run])   # collected and deselected: no browser starts
        assert f"ran in test_x.py::test_page{ids}\n" in done.stdout.str(), run


def test_the_cap_scales_with_the_load_per_cpu_up_to_twice():
    """A run's cap is CAP while the host's 5-minute load is at most one per
    CPU, then grows with it, up to twice CAP (Step 4.1g2)."""
    assert [fullsuite.cap(load5, 24) for load5 in (0, 24, 36, 48, 96)] == [4500, 4500, 6750, 9000, 9000]


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def _repo(tmp_path, monkeypatch):
    """A repository whose main has one commit, a lane worktree on ``p2/x``
    and an empty receipts folder: ``(repo, lane, receipts, main's commit)``."""
    repo, lane, receipts = tmp_path / "repo", tmp_path / "lanes" / "x", tmp_path / "receipts"
    monkeypatch.setenv("AZURKIT_RECEIPTS", str(receipts))
    receipts.mkdir()
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    _git(repo, "commit", "-q", "--allow-empty", "-m", "a")
    _git(repo, "worktree", "add", "-q", "-b", "p2/x", str(lane), "main")
    return repo, lane, receipts, _git(repo, "rev-parse", "HEAD")


def _receipt(receipts, head, **fields):
    m = {"key": f"{head[:12]}-0", "head": head, "clean": True, "state": "done", "exit_code": 0, "mode": "full",
         "base": None, "finished_at": "2026-10-28T00:00:00", "vanilla_run": 2, "europe_run": 1} | fields
    (receipts / f"suite-{m['key']}.meta").write_text(json.dumps(m), encoding="utf-8")


def test_land_fast_forwards_main_only_with_a_passing_receipt_and_removes_the_lane(tmp_path, monkeypatch):
    repo, lane, receipts, base = _repo(tmp_path, monkeypatch)
    _git(lane, "commit", "-q", "--allow-empty", "-m", "b")
    top = _git(lane, "rev-parse", "HEAD")
    _git(repo, "branch", "p2/y", base)
    for refused in ({"exit_code": 1}, {"vanilla_run": 0}, {"europe_run": None}):   # D26: both tiers ran
        _receipt(receipts, top, **refused)
        assert land.land(repo, "p2/x")[0] == 1, refused
    _receipt(receipts, top[:11] + "f", clean=False)
    assert land.land(repo, "p2/x")[0] == 1
    _receipt(receipts, top, mode="changed", base=base)
    assert land.land(repo, "p2/x") == (0, f"land: moved main {base[:12]} -> {top[:12]} (p2/x; receipt "
                                          f"{top[:12]}-0, changed)")
    assert _git(repo, "rev-parse", "main") == top and not lane.exists()
    assert _git(repo, "branch", "--list", "p2/x") == ""
    _git(repo, "switch", "-q", "p2/y")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "c")
    _receipt(receipts, _git(repo, "rev-parse", "HEAD"))
    code, why = land.land(repo, "p2/y")
    assert code == 1 and "doesn't fast-forward from main" in why
