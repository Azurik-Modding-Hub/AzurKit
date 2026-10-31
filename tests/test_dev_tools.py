"""The landing tools: ``scripts/fullsuite.py``'s changed-area plan,
``scripts/perf.py``'s verdicts and ``scripts/land.py``'s gate: a
fast-forward, a passing receipt and its perf block."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import fullsuite, land, perf

ROOT = Path(__file__).resolve().parent.parent
SMOKE = sorted(fullsuite.SMOKE)


def test_the_changed_area_plan_picks_importers_and_falls_back_to_the_whole_suite():
    """A changed module selects every test file that reaches it through
    imports; src/ adds the files that run the whole package (SRC_TESTS);
    docs select only the smoke files (the lint files and the gate's test,
    whose USA and Europe cases make every receipt run both tiers); the
    suite's configuration, what every session
    loads and an unknown path make it whole. The session loads only
    what tests/conftest.py imports (it checks the app in a Python of its
    own), so here a change to the sdk is changed-area."""
    deps = {"azurkit": set(), "azurkit.core": {"azurkit"}, "azurkit.core.iso": {"azurkit", "azurkit.core"},
            "azurkit.core.gate": {"azurkit", "azurkit.core"},
            "azurkit.sdk": {"azurkit", "azurkit.core", "azurkit.core.iso"},
            "tests.conftest": {"azurkit", "azurkit.core", "azurkit.core.gate"},
            "tests.test_sdk": {"azurkit", "azurkit.sdk"}, "tests.test_gate": {"azurkit.core.iso"},
            "tests.test_wheel": {"azurkit"}, "tests.test_other": {"json"}}
    assert "tests/test_gate.py" in SMOKE
    assert any("pytest.mark.europe" in (ROOT / f).read_text(encoding="utf-8") for f in SMOKE)   # D26
    assert fullsuite.plan(["src/azurkit/core/iso.py"], deps) == sorted(
        {*SMOKE, "tests/test_sdk.py", *fullsuite.SRC_TESTS})
    assert fullsuite.plan(["tests/test_other.py", "AGENTS.md", "tests/sdk_api.txt"], deps) == sorted(
        {*SMOKE, "tests/test_other.py"})
    assert fullsuite.plan(["bootstrap.py"], deps) == fullsuite.plan(["tests/perf_ceilings.toml"], deps) == SMOKE
    for whole in ("pyproject.toml", "uv.lock", "tests/conftest.py", "src/azurkit/core/gate.py", "assets/icon/a.icns"):
        assert fullsuite.plan([whole], deps) is None, whole
    assert fullsuite.plan(["src/azurkit/sdk.py"], fullsuite.graph(ROOT)) is not None


def test_a_change_in_the_goldens_picks_the_test_files_that_read_them():
    """tests/goldens/ is read by path, not imported: a change in it picks
    each test file that reaches a module naming it
    (``scripts/record_goldens.py``'s GOLDENS), every family's (the packs',
    the characters', the randomizer's and its maps'), not the smoke files
    alone."""
    goldens = fullsuite.plan(["tests/goldens/rando_plans.json", "tests/goldens/probes.json"], fullsuite.graph(ROOT))
    assert {f"tests/test_{name}.py" for name in ("characters", "packs", "builds", "shims", "xbr", "fps_unlock",
                                                 "randomizer", "art", "hosts", "site")} <= set(goldens) - set(SMOKE)


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
    for run, ids in (("changed", "[chromium]"),
                     ("whole", "[chromium] test_x.py::test_page[webkit] test_x.py::test_page[firefox]")):
        done = pytester.runpytest_subprocess("-p", "no:cacheprovider", "-s", "--collect-only", "-m", "not web",
                                             *asks[run])   # collected and deselected: no browser starts
        assert f"ran in test_x.py::test_page{ids}\n" in done.stdout.str(), run


def test_the_cap_scales_with_the_load_per_cpu_up_to_twice():
    """A run's cap is CAP while the host's 5-minute load is at most one per
    CPU, then grows with it, up to twice CAP (Step 4.1g2)."""
    assert [fullsuite.cap(load5, 24) for load5 in (0, 24, 36, 48, 96)] == [6000, 6000, 9000, 12000, 12000]


def test_the_perf_gate_fails_an_unlisted_slow_op_reruns_a_spike_and_its_list_only_shrinks():
    """D981-D985 on fake timings: an op not in the list fails when its
    median is over 3 s (the capped profile's 9 s); an image's first check
    passes over it only with a moving bar (D982), and a listed one with a
    moving bar leaves the list; past 1 s an op shows progress unless it is
    a debt (D980); a listed op fails over its ceiling;
    an op over runs R more times and fails only if the median of all is
    still over (one spike can't fail it); the list may lower and drop but
    never add or raise against main's; changes reach the ops of their
    area."""
    def s(seconds, bar=0, progress=True):
        return {"s": seconds, "bar": bar, "progress": progress}
    slow, moving = [s(3.2), s(3.4), s(3.1)], [s(6.8, bar=5)] * 3
    assert [perf.judge(*case)["verdict"] for case in (
        (slow, 3.0), (slow, 9.0), (slow, 3.0, 4.0), ([s(4.7)] * 3, 3.0, 4.0), (moving, 3.0, None, False, True),
        (moving, 3.0, 29.3, False, True), ([s(6.8, bar=1)] * 3, 3.0, None, False, True),
        ([s(1.5, progress=False)] * 3, 3.0),
        ([s(1.5, progress=False)] * 3, 3.0, None, True), ([{**s(2.0), "error": "timed out"}], 3.0))] == [
        "over", "pass", "listed", "regressed", "bar", "bar", "over", "no progress", "pass", "error"]
    times = {"A12": [[5.0, 3.2, 2.6], [2.4, 2.5, 2.6]], "A15": [[4.0, 4.1, 4.2], [4.0, 4.0, 4.1]], "A24": [[290.0]]}
    asked = []

    def drive(run, targets):
        asked.append((run, dict(targets)))
        return {"samples": {op: [s(t) for batch in times[op][:1 + (n > perf.R)] for t in batch]
                            for op, n in targets.items()}}
    lst = {"ceilings": {"A24/app": 300.0}, "debts": [], "memory": {}, "untimed": {}}
    got, _, _ = perf.measure([("A12", "app"), ("A15", "app"), ("A24", "app")], drive, lst)
    assert {k: r["verdict"] for k, r in got.items()} == {"A12/app": "pass", "A15/app": "over", "A24/app": "listed"}
    assert asked == [("app", {"A12": 3, "A15": 3, "A24": 3}), ("app", {"A12": 6, "A15": 6})]
    main = {"ceilings": {"A15/app": 4.8, "S14/webkit": 21.0, "S03/lag": 29.3}, "debts": ["A15/app"], "memory": {},
            "untimed": {}}
    mine = {**main, "ceilings": {"A15/app": 5.0, "S14/webkit": 21.0, "A06/app": 9.0}, "debts": ["A15/app", "A06/app"]}
    assert perf.check_list(mine, main) == ["A06/app: added to the list (ceiling 9.0 s)",
                                           "A15/app: its ceiling raised, 4.8 -> 5.0 s", "A06/app: a new progress debt"]
    assert perf.check_list(mine, None) == []   # the first record
    results = {"A15/app": perf.judge([s(4.0)] * 3, 3.0, 4.8, True), "S14/webkit": perf.judge([s(2.0)] * 3, 3.0, 21.0),
               "A06/app": perf.judge([s(7.0, progress=False)] * 3, 3.0),
               "S03/lag": perf.judge(moving, 3.0, 29.3, False, True)}   # D982: a moving bar leaves the list
    assert perf.updated(main, results, {}, first=False) == {
        "ceilings": {"A15/app": 4.6}, "debts": [], "memory": {}, "untimed": {}}
    assert perf.updated(perf.listed(None), results, {}, first=True)["ceilings"] == {"A15/app": 4.6, "A06/app": 8.1}
    assert perf.listed(perf.render(main)) == main
    assert perf.select(["src/azurkit/tools/randomizer/x.py", "scripts/web_tools.py"]) == {
        *(("app", g) for g in ("randomizer", "tracker")), *(("site", g) for g in perf.GROUPS)}
    assert perf.select(["AGENTS.md", "tests/test_x.py"]) == set() and len(perf.select(["web/app.mjs"])) == 12


def test_the_lag_model_makes_each_of_the_workers_file_reads_late_and_stops_on_one_it_doesnt_know():
    """Safari's read model (the perf gate's lag run) makes every read of the
    player's File in ``web/worker.mjs`` 200 ms late, the blocks' FileReaderSync
    reads and the image check's awaited ones alike; a read it doesn't know
    stops the run, naming its line."""
    from tests import _perf

    text = (ROOT / "web" / "worker.mjs").read_text(encoding="utf-8")
    late = _perf.lagged(text)
    assert late.count(f"performance.now() + {_perf.LAG_MS}") == 1 and late.count(_perf._WAIT) == 2
    added = "const more = await file.slice(0, 1).arrayBuffer();"
    with pytest.raises(SystemExit, match=re.escape(repr(added))):
        _perf.lagged(text.replace("async function prime(", f"{added}\nasync function prime(", 1))


def test_update_ceilings_on_a_narrow_run_keeps_the_untimed_ops_it_doesnt_reach(tmp_path, monkeypatch):
    """``perf.py --update-ceilings`` on a run that reaches no untimed op
    (a lane lowering its own rows) keeps the list's untimed ops the registry
    still can't time, and drops only one the registry now times."""
    monkeypatch.setattr(perf.signal, "signal", lambda *_: None)
    monkeypatch.setattr(perf, "R", perf.R)
    monkeypatch.setattr(sys, "path", list(sys.path))
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    on_main = {"ceilings": {"A15/app": 6.1}, "debts": [], "memory": {}, "untimed": {"S15": "out of memory", "S14": "x"}}
    (repo / perf.CEILINGS).write_text(perf.render(on_main), encoding="utf-8")
    _git(repo, "add", perf.CEILINGS)
    _git(repo, "commit", "-q", "-m", "main")
    assert perf.main([str(repo), "--select", "app:tracker", "--ops", "NOOP", "--update-ceilings",
                      "--json", str(tmp_path / "perf.json")]) == 0
    assert perf.listed((repo / perf.CEILINGS).read_text(encoding="utf-8")) == {**on_main,
                                                                              "untimed": {"S15": "out of memory"}}


def test_the_perf_gates_app_is_the_worktrees_wheel_in_a_venv_reading_the_database_it_ships(tmp_path):
    """The perf gate's app profile runs the app as a player installs it
    (``_perf.venv``): the worktree's wheel in a scratch venv, whose app reads
    the randomizer database the wheel ships instead of checking it again as a
    checkout does (round 1's A06: 7.8 s from a worktree, 3.5 s frozen), and
    finds the worktree's page where the installed app looks for it."""
    from tests import _perf

    python = _perf.venv(ROOT, tmp_path / "app")
    code = ("import sys; from azurkit import app; from azurkit.tools.randomizer import dbcache; "
            "from azurkit.tools.randomizer.planner.loader import DATA_DIR; "
            "print(app.PAGE, dbcache.shipped(DATA_DIR) is not None, sys.prefix, sep='\\n')")
    page, shipped, prefix = subprocess.run([python, "-I", "-c", code], cwd=tmp_path, capture_output=True, text=True,
                                           check=True, timeout=300).stdout.splitlines()
    assert (shipped, Path(prefix).resolve()) == ("True", (tmp_path / "app" / "venv").resolve())
    assert sorted(f.relative_to(page) for f in Path(page).rglob("*")) == sorted(
        f.relative_to(ROOT / "web") for f in (ROOT / "web").rglob("*"))

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


def test_land_needs_a_passing_perf_block_for_src_or_web_a_list_that_only_shrinks_and_an_empty_one_to_release(
        tmp_path, monkeypatch):
    """D981: a stack changing src/ or web/ lands only on a receipt whose
    perf block passed; any stack, one changing only tests/perf_ceilings.toml
    too, is refused when its list adds an op or raises a ceiling against
    main's; ``--release`` refuses while the list holds an op."""
    repo, lane, receipts, base = _repo(tmp_path, monkeypatch)
    (lane / "src").mkdir()
    (lane / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (lane / "tests").mkdir()
    (lane / perf.CEILINGS).write_text(perf.render({"ceilings": {"A15/app": 4.8}, "debts": [], "memory": {},
                                                   "untimed": {}}), encoding="utf-8")
    _git(lane, "add", "src/a.py", perf.CEILINGS)
    _git(lane, "commit", "-q", "-m", "src")
    top = _git(lane, "rev-parse", "HEAD")
    _receipt(receipts, top)
    code, why = land.land(repo, "p2/x")
    assert code == 1 and "and a passing perf block" in why
    _receipt(receipts, top, perf_args=["--select", "app:build"], perf={"passed": False})
    assert land.land(repo, "p2/x")[0] == 1
    _receipt(receipts, top, perf_args=["--select", "app:build"], perf={"passed": True})
    code, why = land.land(repo, "p2/x", dry_run=True, release=True)
    assert code == 1 and "still lists 1 ops over their budget" in why
    assert land.land(repo, "p2/x")[0] == 0   # main had no list: the first record
    _git(repo, "switch", "-q", "-c", "p2/y")
    for ceilings, landed in (({"A15/app": 60.0}, False), ({"A15/app": 4.8, "A01/app": 9.0}, False),
                             ({"A15/app": 4.0}, True)):
        (repo / perf.CEILINGS).write_text(perf.render({"ceilings": ceilings, "debts": [], "memory": {},
                                                       "untimed": {}}), encoding="utf-8")
        _git(repo, "commit", "-q", "-m", "the list alone", perf.CEILINGS)
        _receipt(receipts, _git(repo, "rev-parse", "HEAD"), mode="changed", base=_git(repo, "rev-parse", "main"))
        code, why = land.land(repo, "p2/y", dry_run=True)
        assert (code == 0) == landed and (landed or "grows main's list" in why), why
        if not landed:
            _git(repo, "reset", "-q", "--hard", "main")


def test_a_browser_new_to_mains_perf_py_gets_one_first_record_and_nothing_else_grows(tmp_path, monkeypatch):
    """D994: a browser the stack's perf.py times and main's doesn't
    (``perf.new_browsers``) gets one first record: ``--update-ceilings``
    lists its over-budget ops and debts as measured, with no re-run, and
    land.py takes them against main's list; an op added in another context
    is still refused, and so is a new op of that browser once main's perf.py
    times it."""
    repo, _, receipts, _ = _repo(tmp_path, monkeypatch)

    def commit(browsers, lst, what):
        (repo / "scripts").mkdir(exist_ok=True)
        (repo / "tests").mkdir(exist_ok=True)
        (repo / "scripts" / "perf.py").write_text(f"BROWSERS = {browsers!r}\n", encoding="utf-8")
        (repo / perf.CEILINGS).write_text(perf.render(lst), encoding="utf-8")
        _git(repo, "add", "scripts/perf.py", perf.CEILINGS)
        _git(repo, "commit", "-q", "-m", what)
        _receipt(receipts, _git(repo, "rev-parse", "HEAD"), mode="changed", base=_git(repo, "rev-parse", "main"))
    on_main = {"ceilings": {"S05/webkit": 4.0}, "debts": [], "memory": {}, "untimed": {}}
    commit(("webkit", "chromium"), on_main, "main")
    asked = []

    def drive(run, targets):
        asked.append((run, dict(targets)))
        return {"samples": {op: [{"s": 5.0, "bar": 0, "progress": False}] * n for op, n in targets.items()}}
    got, _, _ = perf.measure([("S05", "webkit"), ("S05", "firefox")], drive, on_main, fresh={"firefox"})
    assert asked == [("webkit", {"S05": 3}), ("firefox", {"S05": 3}), ("webkit", {"S05": 6})]
    recorded = perf.updated(on_main, got, {}, False, {"firefox"})
    assert recorded == {**on_main, "ceilings": {"S05/webkit": 4.0, "S05/firefox": 5.8}, "debts": ["S05/firefox"]}
    _git(repo, "switch", "-q", "-c", "p2/y")
    commit(("webkit", "chromium", "firefox"), recorded, "firefox's first record")
    assert perf.new_browsers(repo, "main", "p2/y") == {"firefox"} and perf.new_browsers(repo, "p2/y", "main") == set()
    assert land.land(repo, "p2/y", dry_run=True)[0] == 0
    commit(("webkit", "chromium", "firefox"), {**recorded, "ceilings": {**recorded["ceilings"], "S07/webkit": 4.0}},
           "another op")
    code, why = land.land(repo, "p2/y", dry_run=True)
    assert code == 1 and why.endswith("grows main's list (D981): S07/webkit: added to the list (ceiling 4.0 s)"), why
    _git(repo, "reset", "-q", "--hard", "HEAD~1")
    assert land.land(repo, "p2/y")[0] == 0   # main's perf.py times firefox now
    _git(repo, "switch", "-q", "-c", "p2/z")
    commit(("webkit", "chromium", "firefox"), {**recorded, "ceilings": {**recorded["ceilings"], "S08/firefox": 4.0}},
           "a second record")
    code, why = land.land(repo, "p2/z", dry_run=True)
    assert code == 1 and "S08/firefox: added to the list" in why, why
