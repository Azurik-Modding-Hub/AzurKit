"""The landing tools: ``scripts/fullsuite.py``'s changed-area plan,
``scripts/perf.py``'s verdicts and ``scripts/land.py``'s gate: a
fast-forward, a passing receipt and its perf block."""

from __future__ import annotations

import dataclasses
import json
import os
import re
import signal
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

from scripts import fullsuite, land, perf
from tests import _perf

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
    page = ["tests/test_hosts.py", "tests/test_icon.py", "tests/test_service_worker.py", "tests/test_site.py"]
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
    assert all({f"--numprocesses={fullsuite.WORKERS}", "--dist=loadgroup"} <= set(fullsuite.command(m))
               for m in (changed, whole))   # D991: every run on xdist's workers, a group on one
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
    assert [fullsuite.cap(load5, 24) for load5 in (0, 24, 36, 48, 96)] == [1800, 1800, 2700, 3600, 3600]


def test_the_perf_gate_fails_an_unlisted_slow_op_reruns_a_spike_and_its_list_only_shrinks():
    """D981-D985 on fake timings: an op not in the list fails when its
    median is over 3 s (the capped profile's 9 s); an image's first check
    passes over it only with a moving bar (D982), and a listed one with a
    moving bar leaves the list; past 1 s an op shows progress unless it is
    a debt (D980), and a download, whose write the browser's own bar shows,
    does when its page part is within 1 s (the case keeps that part); a
    listed op fails over its ceiling;
    an op over runs R more times and fails only if the median of all is
    still over (one spike can't fail it); the list may lower and drop but
    never add or raise against main's; changes reach the ops of their
    area."""
    def s(seconds, bar=0, progress=True):
        return {"s": seconds, "bar": bar, "progress": progress}
    slow, moving = [s(3.2), s(3.4), s(3.1)], [s(6.8, bar=5)] * 3
    saved = lambda seconds, page: [{**s(seconds, progress=False), "page": page}] * 3   # noqa: E731
    assert [perf.judge(*case)["verdict"] for case in (
        (slow, 3.0), (slow, 9.0), (slow, 3.0, 4.0), ([s(4.7)] * 3, 3.0, 4.0), (moving, 3.0, None, False, True),
        (moving, 3.0, 29.3, False, True), ([s(6.8, bar=1)] * 3, 3.0, None, False, True),
        ([s(1.5, progress=False)] * 3, 3.0),
        ([s(1.5, progress=False)] * 3, 3.0, None, True), ([{**s(2.0), "error": "timed out"}], 3.0),
        (saved(1.3, 1.2), 3.0, None, False, False, True), (saved(1.3, 0.01), 3.0, None, False, False, True),
        (saved(3.3, 0.01), 3.0, None, False, False, True), (saved(1.3, 0.01), 3.0))] == [
        "over", "pass", "listed", "regressed", "bar", "bar", "over", "no progress", "pass", "error",
        "no progress", "pass", "over", "no progress"]
    assert perf.judge(saved(1.3, 0.01), 3.0, browser_bar=True)["page"] == [0.01] * 3
    empty, bars = {"ceilings": {}, "debts": set()}, [{**s(6.8, bar=5), "page": 0.01}] * 3
    assert {k: v["verdict"] for k, v in perf.verdicts(   # D1053: Firefox's whole Save passes on its bar, no other's
        [("S49", "firefox"), ("S49", "webkit")], {("firefox", "S49"): bars, ("webkit", "S49"): bars}, empty,
        browser_bars={"S49"}).items()} == {"S49/firefox": "bar", "S49/webkit": "over"}
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


def test_the_perf_gate_fails_a_run_whose_engine_answers_without_the_native_library_its_worktree_ships():
    """The perf gate's native assert (Step 4.3 native reach): each run's
    engine reports (``sdk.catalog``'s ``native``) are the library the
    worktree ships for the host, loaded, with its bytes' sha256[:12]; a
    twin's run, another library's bytes, no report, a twin's answer beside
    the library or no count of them fails, and a page whose engine runs
    without its library stops its pass (``Driver.engine``); a page leaving
    keeps its report, with the calls by then (``Driver.leave``)."""
    from azurkit.core import native
    app = perf.shipped(Path(perf.ROOT), native.target())
    site = perf.shipped(Path(perf.ROOT), perf.SIDE_MODULE)
    assert app[1] and site[1] and perf.shipped(Path(perf.ROOT), None) == (None, None)
    ran = {"loaded": True, "library": app[0], "sha12": app[1], "kernels": ["reach"], "why": None,
           "calls": {"kernel": 9, "twin": 0}}
    twin = {"loaded": False, "library": None, "sha12": None, "kernels": [], "why": "AZURKIT_NATIVE=0"}
    assert perf.native_failures({"app": [ran], "webkit": [ran | {"library": site[0], "sha12": site[1]}]},
                                {"app": app, "webkit": site}) == []
    assert perf.native_failures({"app": [twin], "webkit": [ran], "lag": []}, {"app": app, "webkit": site, "lag": site}) == [
        f"native app: the engine ran no library (AZURKIT_NATIVE=0), not the shipped {app[0]} ({app[1]})",
        "native lag: its engine reported no compiled kernels",
        f"native webkit: the engine ran {app[0]} ({app[1]}), not the shipped {site[0]} ({site[1]})"]
    assert perf.native_failures({"app": [ran | {"calls": {"kernel": 9, "twin": 2}}], "lag": [{k: v for k, v in ran.items() if k != "calls"}]},
                                {"app": app, "lag": app}) == [
        "native app: its Python twin answered 2 of the engine's reach calls",
        "native lag: its Python twin answered an unknown count of the engine's reach calls"]

    class Stub(_perf.Page):
        def __init__(self, report):
            self.report = report
            self.page = self
            self.closed = False

        def js(self, fn, arg=None):
            return self.report if fn in (_perf.NATIVE, _perf.CALLS) else pytest.fail(fn)

        def close(self):
            self.closed = True
    d = _perf.Driver(_perf.RUNS["app"], {}, Path(perf.ROOT), Path(perf.ROOT), None)
    d.engine(Stub(ran))
    with pytest.raises(RuntimeError, match=r"^the engine runs without its native library \(AZURKIT_NATIVE=0\)$"):
        d.engine(Stub(twin))
    assert d.native == [ran, twin]
    d.leave(leaving := Stub(answered := ran | {"calls": {"kernel": 9, "twin": 1}}))
    assert leaving.closed and d.native == [ran, twin, answered]


def test_the_lag_model_makes_each_of_the_workers_file_reads_late_and_stops_on_one_it_doesnt_know():
    """Safari's read model (the perf gate's lag run) makes every read of the
    player's File in ``web/worker.mjs`` and ``web/hasher.mjs`` 200 ms late, the blocks' FileReaderSync
    reads, the image check's awaited ones and Replace files' stream alike; a read or stream it doesn't know
    stops the run, naming its line. Its ``sw.js`` lists the texts it serves
    late, as the worker's install keeps no other bytes (D1013)."""
    import hashlib

    from scripts import web_tools
    from tests import _perf

    text = (ROOT / "web" / "worker.mjs").read_text(encoding="utf-8")
    late = _perf.lagged(text)
    assert late.count(f"performance.now() + {_perf.LAG_MS}") == 1 and late.count(_perf._WAIT) == 5
    files = {"worker.mjs": {"sha256": "0" * 64, "size": 1}, "app.mjs": {"sha256": "1" * 64, "size": 2}}
    sw = (ROOT / "web" / web_tools.WORKER).read_text(encoding="utf-8").replace(
        web_tools.RELEASE_LINE, f"const RELEASE = {json.dumps({'csp': '', 'files': files, 'name': 'n'})};")
    line = next(line for line in _perf.relisted(sw, {"/worker.mjs": late}).splitlines() if line.startswith("const RELEASE"))
    assert json.loads(line.removeprefix("const RELEASE = ").removesuffix(";"))["files"] == files | {"worker.mjs": {
        "sha256": hashlib.sha256(late.encode()).hexdigest(), "size": len(late.encode())}}
    hasher = (ROOT / "web" / "hasher.mjs").read_text(encoding="utf-8")
    assert _perf.lagged(hasher, _perf.HASHER_LAG).count(_perf._WAIT) == 1
    for added in ("const more = await file.slice(0, 1).arrayBuffer();", "const more = file.stream().getReader();"):
        with pytest.raises(SystemExit, match=re.escape(repr(added))):
            _perf.lagged(text.replace("async function prime(", f"{added}\nasync function prime(", 1))


def test_the_perf_gates_memory_counts_only_the_webkit_launchd_started_for_its_own_browser(monkeypatch):
    """The capped-site peak: a WebKit process that started during the run
    counts when ``launchctl print pid/N`` holds this run's mark in its PATH,
    or can't say (no record, or launchctl failing: counted, never laxer);
    another seat's doesn't, and its pid reused by ours, which started later,
    is asked about again and counted."""
    mine, theirs = f"PATH => {_perf.MARK}:/usr/bin", "PATH => /usr/bin"
    said = {"11": mine, "12": theirs, "13": "", "15": theirs}

    def launchctl(argv, **kwargs):
        asked.append(argv[-1])
        if argv[-1] == "pid/14":
            raise subprocess.TimeoutExpired(argv, 10)
        return types.SimpleNamespace(stdout=said[argv[-1].removeprefix("pid/")])
    asked: list[str] = []
    monkeypatch.setattr(_perf.subprocess, "run", launchctl)
    monkeypatch.setattr(_perf, "_launched", {})
    xpc = "/x/playwright/webkit-1/Contents/com.apple.WebKit.WebContent.xpc/Contents/MacOS/WebContent"
    rows = [(10, os.getpid(), "/x/playwright/driver/node", "t0"), (20, 10, "/x/pw_run", "t0"),
            *((pid, 1, xpc, "t0") for pid in (9, 11, 12, 13, 14, 15)), (16, 1, "/Applications/Safari.xpc/s", "t0")]
    before = {(9, "t0")}
    assert _perf.browser_pids(rows, before) == [20, 11, 13, 14]
    assert _perf.browser_pids(rows, before) == [20, 11, 13, 14] and len(asked) == 5   # each process asked about once
    said["15"] = mine
    assert _perf.browser_pids([(15, 1, xpc, "t1")], {(15, "t0")}) == [15]   # a pid reused: asked again, and not "before"


class _Stub(_perf.Page):
    """A page on a stub clock: each action's done-states (``costs``: ``{action:
    {done: ms}}``) true some ms after it, any other at once; the freeze
    probe's ``[due, ms]`` ticks."""

    def __init__(self, costs, ticks=()):
        super().__init__(types.SimpleNamespace(**dict.fromkeys(("goto", "set_input_files", "close"), lambda *a: None)))
        self.t, self.costs, self.ticks, self.at, self.clicks = 0.0, costs, list(ticks), {}, {}

    def now(self):
        return self.t

    def do(self, action, arg=None):
        self.clicks[action] = self.t
        self.at |= {done: self.t + ms for done, ms in self.costs.get(action, {}).items()}
        return self.t

    def js(self, fn, arg=None):   # an engine with its compiled kernels (Driver.engine)
        return {"loaded": True} if fn == _perf.NATIVE else self.do(fn, arg)

    def wait(self, done, timeout=900, arg=None):
        self.t = max(self.t, self.at.get(done, self.t))
        return self.t, True

    def poll(self, dones):
        return self.t, [self.t >= self.at.get(done, self.t) for done in dones]

    def settled(self):
        return self.t

    def events(self):
        self.late += [tick for tick in self.ticks if sum(tick) <= self.t]   # fired by now
        self.ticks = [tick for tick in self.ticks if sum(tick) > self.t]
        return []


def test_the_perf_gate_takes_a_starved_sample_once_more_names_it_and_counts_a_child_gone_mid_op(tmp_path, monkeypatch):
    """A sample past 1 s whose wall passes 1.3x its tree's CPU seconds is
    taken once more, then stands with its tag, one past 30 s at once, and the
    case names it with no verdict changed. A child gone mid-op keeps what it
    used, so it reads as no starved sample, and a pid reused is another
    process (ps stubbed)."""
    start, new = "Sun Nov  1 08:22:00 2026", "Sun Nov  1 09:00:00 2026"
    reads = iter(["1 0 10 0:10.00 {0} /a\n2 1 10 0:05.00 {0} /a\n3 0 10 9:00.00 {0} /other\n",
                  "1 0 10 0:10.50 {0} /a\n2 1 10 0:09.00 {0} /a\n",
                  "1 0 10 0:10.50 {0} /a\n2 1 0 0:00.00 {0} (a)\n",   # killed, not reaped yet: ps reads it as 0
                  "1 0 10 0:10.50 {0} /a\n",
                  "1 0 10 0:10.50 {0} /a\n2 1 10 0:01.00 {1} /a\n"])
    monkeypatch.setattr(_perf.subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(stdout=next(reads).format(start, new)))
    memory = _perf.Memory(lambda rows: [1])
    assert [memory.take() for _ in range(5)] == [15.0, 19.5, 19.5, 19.5, 20.5]
    assert not _perf.starved(4.5, 19.5 - 15.0)   # the child's 4 s stay though it exited

    spends = iter([1.0, 1.9, 1.0, 1.0, 0.1, 10.0, 1.0])
    meter = types.SimpleNamespace(used=0.0)
    meter.take = lambda: setattr(meter, "used", meter.used + next(spends)) or meter.used

    def timed(ms, target=9):
        p = _Stub({"go": {"done": ms}})
        d.targets["A12"] = target
        d.act(p, "A12", "go", "done")
    d = _perf.Driver(_perf.RUNS["app"], {}, tmp_path, tmp_path, None)
    d.memory = meter
    timed(2000)
    assert d.need("A12") and "A12" not in d.samples   # starved: not recorded yet
    timed(2000)
    assert d.samples["A12"] == [{"s": 2.0, "bar": 0, "progress": False, "late_ms": 0, "cpu": 1.9, "retook": 2.0}]
    d.samples.clear()
    timed(4000)
    timed(4000)
    assert [(s["cpu"], s["starved"], s["retook"]) for s in d.samples["A12"]] == [(1.0, True, 4.0)]
    timed(900)     # under 1 s: never named
    timed(40000)   # past 30 s: it runs once
    assert [(s["s"], s.get("starved")) for s in d.samples["A12"]] == [(4.0, True), (0.9, None), (40.0, True)]
    d.samples.clear()
    timed(5000)   # its second take never came: it stands
    assert "A12" not in d.samples
    d.finish()
    assert [s["s"] for s in d.samples["A12"]] == [5.0] and not d.retaking
    plain = {"s": 1.2, "bar": 0, "progress": True}
    named = [{"s": 4.0, "bar": 0, "progress": True, "cpu": 1.0, "starved": True}, plain, plain]
    got = perf.judge(named, 3.0)
    assert got["starved"] == [4.0] and "starved" not in perf.judge([plain] * 3, 3.0)
    untagged = [{k: v for k, v in s.items() if k != "starved"} for s in named]
    assert {k: v for k, v in got.items() if k != "starved"} == perf.judge(untagged, 3.0)


def test_the_perf_gate_clicks_3_s_after_a_change_and_fails_a_sample_whose_page_froze_in_a_gap(tmp_path):
    """D1006 and D1014 over a stub clock: a Track or Build after a change
    (an op with ``head_start``) is clicked 3 s after it and timed from the
    click (at once once the change's own wait passed 3 s; never a Build
    again); a tick of the freeze probe due in a gap (the head start, a
    dialog's wait) over 250 ms late fails the next sample, a head start's
    timed from the change, and one no sample takes stops the pass; a late
    tick under that, due in an action's own wait or before the gap only
    logs. One click's done-states race, each its own first true poll (the
    click's op takes its head start's freeze); a state made once is cloned
    anew."""
    def driven(costs, ticks):
        p = _Stub(costs, ticks)
        d = _perf.Driver(_perf.RUNS["app"], dict.fromkeys(("A12", "A16", "S18", "S19", "S20"), 9), tmp_path,
                         tmp_path / "usa.iso", None)
        d.sleep = lambda seconds: setattr(p, "t", p.t + seconds * 1000)
        d.fresh(p)
        return p, d

    def run(op, pick, dialog, ticks):   # a pick (the change), a dialog's wait, then Build: (its click, its sample)
        p, d = driven({"pick": {"picked": pick}, "build": {"built": 2000}}, ticks)
        d.act(p, None, "pick", "picked", change=True)
        if dialog:
            d.idle(p, "the save dialog", dialog)
        try:
            d.act(p, op, "build", "built")
            d.over()
        except RuntimeError as exc:
            return "stops", str(exc)
        s = d.samples[op][0]
        return p.clicks["build"], s["s"], s.get("error"), s.get("gap_ms"), s["late_ms"]
    froze = "the page froze 400 ms in "
    assert [run(*row) for row in (
        ("A12", 500, 0, []), ("A12", 4000, 0, []), ("A16", 500, 0, []),
        ("A12", 500, 0, [(1000, 400)]), ("A12", 500, 0, [(1000, 200)]), ("A12", 500, 0, [(300, 400)]),
        ("A12", 500, 0, [(3500, 400)]), ("A16", 500, 1.0, [(1000, 400)]), (None, 500, 1.0, [(1000, 400)]),
    )] == [
        (3000, 2.0, None, 0, 0), (4000, 2.0, None, None, 0), (500, 2.0, None, None, 0),
        (3000, 5.0, froze + "the head start before A12", 400, 0), (3000, 2.0, None, 200, 0), (3000, 2.0, None, 0, 0),
        (3000, 2.0, None, 0, 400), (1500, 2.0, froze + "the save dialog", 400, 0), ("stops", froze + "the save dialog"),
    ]
    p, d = driven({"seed": {"typed": 0}, "track": {"tracked": 5000, "world": 50, "art": 100}}, [(1000, 400)])
    d.act(p, None, "seed", "typed", change=True)
    d.race(p, "S18", "track", {"S19": "world", "S18": "tracked", "S20": "art"}, after={"S20": "S18"})
    assert p.clicks["track"] == 3000 and {op: (d.samples[op][0]["s"], d.samples[op][0].get("error")) for op in (
        "S18", "S19", "S20")} == {"S18": (8.0, froze + "the head start before S18"), "S19": (0.05, None),
                                  "S20": (0.0, None)}
    made = []
    one, two = (d.state("home", lambda f: (made.append(f), (f / "a").write_text("x"))) for _ in range(2))
    (one / "a").write_text("y")
    assert len(made) == 1 and one != two and (two / "a").read_text() == "x"


def test_the_sites_tracker_view_times_its_world_map_from_its_own_click_and_track_comes_after_the_head_start(
        tmp_path, monkeypatch):
    """S19 is the Tracker view's world map timed from the view's click (a
    tab's open: no head start of its own), so a slow first draw shows in it;
    Track (S18) is clicked 3 s after the typed seed, at once when the view's
    open took longer, and S20 counts from Track's done."""
    view, track = _perf.click("rando-view-tracker"), _perf.click("track-seed")
    costs = {view: {_perf.WORLD: 0}, track: {_perf.TRACKED: 5000, _perf.ART_DONE: 100}}
    pages = []

    def page(_):
        pages.append(_Stub(costs))
        return pages[-1]

    def tracked(world_ms):
        costs[view][_perf.WORLD], pages[:] = world_ms, []
        d = _perf.Driver(_perf.RUNS["webkit"], dict.fromkeys(("S18", "S19", "S20"), 9), tmp_path,
                         tmp_path / "usa.iso", None)
        d.sleep = lambda seconds: setattr(d.p, "t", d.p.t + seconds * 1000)
        _perf.site_track(d, types.SimpleNamespace(new_page=dict), "http://127.0.0.1:9800/")
        return round(pages[0].clicks[track]), {op: d.samples[op][0]["s"] for op in ("S18", "S19", "S20")}
    monkeypatch.setattr(_perf, "Page", page)
    assert [tracked(ms) for ms in (50, 30_000)] == [
        (3000, {"S18": 5.0, "S19": 0.05, "S20": 0.0}), (30_000, {"S18": 5.0, "S19": 30.0, "S20": 0.0})]


class _Seeds(_Stub):
    """The app's page over a stub clock as Build, Cancel and a pick make it:
    a build answers 3 s after its click, 0.5 s for a seed this engine
    process built (a kept plan), its first stage record 0.25 s after it; a
    Cancel ends the process; a model's pick, a change, forgets a build that
    has answered, so ``BUILT`` never comes again (the page's wait times out)."""

    def __init__(self):
        super().__init__({})
        self.seed, self.made, self.answers, self.staged, self.forgot, self.picks = "", set(), 0.0, 0.0, False, []

    def do(self, action, arg=None):
        if action == _perf.SEED_ASK:
            self.seed = "azurkit"
        elif typed := re.fullmatch(r".*getElementById\(\"rando-seed\"\); b\.value = \"(\w+)\".*", action, re.S):
            self.seed = typed[1]
        elif action in (_perf.build_js(), _perf.CANCEL_EARLY):
            self.answers = self.t + (500 if self.seed in self.made else 3000)
            self.staged, self.forgot = self.t + 250, False
            if action == _perf.CANCEL_EARLY:
                self.made, self.answers = set(), self.t   # the process killed, another spawned
            else:
                self.made.add(self.seed)
        elif action == _perf.model("keylord"):
            self.picks.append(self.t < self.answers)
            self.forgot = self.t >= self.answers
        return super().do(action, arg)

    js = do

    def wait(self, done, timeout=900, arg=None):
        if done == _perf.BUILT and self.forgot:
            raise TimeoutError(f"timed out after {timeout:.0f} s: {done[:100]}")
        at = {_perf.BUILT: self.answers, _perf.ANSWERED: self.answers, _perf.STAGED: self.staged}.get(done)
        self.t = max(self.t, at if at is not None else self.t)
        return self.t, True


def test_a_site_builds_sample_logs_its_steady_memory_beside_the_resident_peak(tmp_path):
    """D17: the gate's line stays the resident peak; a site build's sample
    also keeps the heap its engine reported plus its pieces' bytes (what a
    busy browser's caches don't inflate), beside the peak so far."""
    class Page(_Stub):
        def js(self, fn, arg=None):
            return 3 << 30 if fn == _perf.STEADY else super().js(fn, arg)
    d = _perf.Driver(_perf.RUNS["webkit"], {"S14": 1}, tmp_path, tmp_path, None)
    d.memory = types.SimpleNamespace(peak=5 << 30, used=4.0, take=lambda: 4.0)
    d.act(Page({}), "S14", _perf.build_js(), _perf.BUILT)
    assert (d.samples["S14"][0]["steady"], d.samples["S14"][0]["resident"]) == (3 << 30, 5 << 30)
    assert d.log[-1].endswith("steady 3.00 GiB peak 5.00 GiB")


def test_each_later_visit_on_the_site_opens_in_its_browser_opened_again_on_the_profile(tmp_path, monkeypatch):
    """Step 4.4m: S02's return visit and S64's build at a later visit open in the browser closed and opened again on
    the pass's profile, never beside the first visit's closed page: WebKit keeps that page's process, every page it
    held resident (a keylord build's 4.12 GiB), for the site's service worker while a page of the site is open, so
    the capped peak summed both visits (7.17 GiB, of which the closed page's footprint was 1.03 GiB)."""
    class Page(_Stub):
        def js(self, fn, arg=None):
            return True if fn == "() => crossOriginIsolated" else super().js(fn, arg)
    page = Page({})
    monkeypatch.setattr(_perf, "Page", lambda _: page)
    monkeypatch.setattr(_perf, "_download", lambda d, p, op: None)
    browsers = []   # each browser's pages, as they open

    def browser(old=None):
        browsers.append(pages := [])
        return types.SimpleNamespace(new_page=lambda: pages.append(len(browsers)))
    d = _perf.Driver(_perf.RUNS["webkit"], {"S02": 2}, tmp_path, tmp_path / "usa.iso", None)
    d.reopened = browser
    _perf.site_start(d, browser(), "http://127.0.0.1:9800/")
    assert (browsers, [s.get("error") for s in d.samples["S02"]]) == ([[1], [2], [3]], [None, None])


def test_the_engine_ready_again_after_a_seeds_build_is_timed_from_the_builds_answer(tmp_path, monkeypatch):
    """R24 (R14's twin): the next op's wait after a big build, the worker
    replaced, counts from the build's answer, not its click."""
    page = _Stub({_perf.build_js(): {_perf.BUILT: 5000, _perf.RESTED: 6200}})
    monkeypatch.setattr(_perf, "Page", lambda _: page)
    d = _perf.Driver(_perf.RUNS["webkit"], {"S24": 1, "R24": 1}, tmp_path, tmp_path / "usa.iso", None)
    d.sleep = lambda seconds: setattr(page, "t", page.t + seconds * 1000)
    _perf.site_seed(d, types.SimpleNamespace(new_page=dict), "http://127.0.0.1:9800/")
    assert (d.samples["S24"][0]["s"], d.samples["R24"][0]["s"]) == (5.0, 1.2)


def test_the_app_seed_pass_picks_its_model_while_a_build_runs_and_waits_for_that_builds_own_answer(tmp_path):
    """Step 4.3 train B3 (the gate's A27-A30 errors, 1,800 s each): A30's
    pick is a small ask made while a build runs, so its build is of a seed
    no build has made (one of a kept plan answers within the second A30
    used to wait), the pick comes at the build's first stage record, and
    the pass waits for that build's own answer, never ``azurkit.build``,
    which a pick after the answer forgets: the pass ends with every op
    sampled."""
    page = _Seeds()
    d = _perf.Driver(_perf.RUNS["app"], dict.fromkeys(("A27", "A28", "A29", "A30"), 1), tmp_path,
                     tmp_path / "usa.iso", None)
    d.sleep = lambda seconds: setattr(page, "t", page.t + seconds * 1000)
    app = types.SimpleNamespace(launch=lambda d, ctx, op: (d.fresh(page), page)[1], quit=lambda p=None: None)
    _perf.app_seed(d, app, None)
    d.over()
    assert (page.picks, {op: len(d.samples[op]) for op in ("A27", "A28", "A29", "A30")},
            [s.get("error") for op in ("A27", "A28", "A29", "A30") for s in d.samples[op]]) == (
        [True], dict.fromkeys(("A27", "A28", "A29", "A30"), 1), [None] * 4)


def test_update_ceilings_on_a_narrow_run_keeps_the_untimed_ops_it_doesnt_reach(tmp_path, monkeypatch):
    """``perf.py --update-ceilings`` on a run that reaches no untimed op
    (a lane lowering its own rows) keeps the list's untimed ops the registry
    still can't time, and drops only one the registry now times."""
    monkeypatch.setattr(perf.signal, "signal", lambda *_: None)
    monkeypatch.setattr(perf, "R", perf.R)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setitem(_perf.OPS, "S15", dataclasses.replace(_perf.OPS["S15"], untimed="out of memory"))
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


def test_the_perf_gate_logs_firefoxs_tree_peak_and_no_verdict_or_list_reads_it(tmp_path, monkeypatch):
    """Firefox's Save holds gigabytes in its parent, so its first record keeps
    the tree's peak (``tree_peaks``, the run's kept file too), even over 6 GiB;
    only the capped profile's peak is judged or listed, so this one fails
    nothing and adds nothing to the list."""
    from azurkit.core import gate
    from scripts import web_tools

    monkeypatch.setattr(perf.signal, "signal", lambda *_: None)
    monkeypatch.setattr(perf, "R", perf.R)
    monkeypatch.setattr(sys, "path", list(sys.path))
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    on_main = {"ceilings": {}, "debts": [], "memory": {}, "untimed": {}}
    (repo / perf.CEILINGS).write_text(perf.render(on_main), encoding="utf-8")
    _git(repo, "add", perf.CEILINGS)
    _git(repo, "commit", "-q", "-m", "main")
    peak = 7 * 2**30
    image = types.SimpleNamespace(stat=lambda: types.SimpleNamespace(st_size=gate.USA.iso_size))
    monkeypatch.setattr(gate, "find", lambda release: image)
    monkeypatch.setattr(web_tools, "wheel", lambda *a, **k: tmp_path / "wheel")
    monkeypatch.setattr(web_tools, "site", lambda *a, **k: tmp_path / "site")
    monkeypatch.setattr(perf, "native_failures", lambda *_: [])
    monkeypatch.setattr(_perf, "drive", lambda wt, spec, todo, *_: {
        "samples": {op: [{"s": 0.5, "bar": 0, "progress": False}] * n for op, n in todo.items()}, "native": [],
        "memory_peak": peak if spec.memory else None, "memory_shared": False, "log": []})
    assert perf.main([str(repo), "--select", "site:build", "--ops", "S05", "--profiles", "site", "--browsers", "firefox",
                      "--update-ceilings", "--keep", str(tmp_path / "keep"), "--json", str(tmp_path / "perf.json")]) == 0
    block = json.loads((tmp_path / "perf.json").read_text(encoding="utf-8"))
    assert (block["tree_peaks"], block["memory"], block["passed"]) == ({"firefox": peak}, {}, True)
    assert json.loads((tmp_path / "keep" / "firefox.json").read_text(encoding="utf-8"))["memory_peak"] == peak
    assert perf.listed((repo / perf.CEILINGS).read_text(encoding="utf-8")) == on_main


def test_the_perf_gates_scratch_is_out_of_reach_of_macoss_temp_sweep(tmp_path, monkeypatch):
    """macOS empties $TMPDIR daily of what looks 3 days old, and the app's venv in this scratch keeps uv's cache's times,
    so a run crossing 03:35 would lose its dependencies; Windows, which has no /tmp, takes its temp folder."""
    import tempfile

    from azurkit.core import gate
    from scripts import web_tools

    monkeypatch.setattr(perf.signal, "signal", lambda *_: None)
    monkeypatch.setattr(perf, "R", perf.R)
    monkeypatch.setattr(sys, "path", list(sys.path))
    image = types.SimpleNamespace(stat=lambda: types.SimpleNamespace(st_size=gate.USA.iso_size))
    monkeypatch.setattr(gate, "find", lambda release: image)
    made = []

    def wheel(path, _):
        made.append(path)
        raise InterruptedError("only the scratch's place is asked")
    monkeypatch.setattr(web_tools, "wheel", wheel)
    with pytest.raises(InterruptedError):
        perf.main([str(tmp_path), "--select", "site:build", "--ops", "S05", "--profiles", "site", "--browsers", "firefox"])
    assert made[0].parent.parent == Path(tempfile.gettempdir() if os.name == "nt" else "/tmp")
    assert not made[0].parent.exists()


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


def test_every_name_the_perf_registrys_functions_call_is_one_the_module_has():
    """tests/_perf.py's drivers run only inside the perf stage, so a helper
    a lane renames elsewhere (python_of, gone with 4.3n's wheel venv) leaves
    a driver that fails only there: each global name a function in the
    module reads is the module's or a builtin."""
    import builtins
    import symtable

    path = Path(_perf.__file__)
    have = set(vars(_perf)) | set(dir(builtins))

    def missing(table: symtable.SymbolTable) -> set[str]:
        out = {s.get_name() for s in table.get_symbols()
               if s.is_global() and s.is_referenced() and s.get_name() not in have}
        for child in table.get_children():
            out |= missing(child)
        return out

    top = symtable.symtable(path.read_text(encoding="utf-8"), str(path), "exec")   # its own names are the module's
    assert set().union(*(missing(child) for child in top.get_children())) == set()


def test_ci_resources_prints_the_lowest_room_by_label_and_never_a_path(tmp_path):
    """The runner's room as a CI tier ends (a run the runner shut down named nothing): each label's free disk and the
    free memory, in numbers; never the folders' paths."""
    (tmp_path / "stop").touch()
    done = subprocess.run([sys.executable, "-I", "scripts/ci_resources.py", str(tmp_path / "stop"), f"tier={tmp_path}"],
                          capture_output=True, text=True, timeout=60, cwd=Path(__file__).resolve().parent.parent)
    macos = (r"; Playwright's processes at most [\d.]+ GiB together, one [\d.]+ \([^/\\\n]*\)\n"
             r"--- what macOS wrote of Playwright's processes that ended: [^/\\\n]+\n"
             r"--- what WebKit's log says of a process that ended: [^/\\\n]+") if sys.platform == "darwin" else ""
    assert re.fullmatch(r"resources, the lowest of the tier in 0 min: tier [\d.]+ GiB free, temp [\d.]+ GiB free, "
                        rf"memory [\d.]+ GiB free \(memory of [\d.]+\){macos}\n", done.stdout), (done.stdout, done.stderr)


def test_ci_resources_names_playwrights_processes_footprints_and_what_macos_wrote_of_one_that_ended(tmp_path,
                                                                                                   monkeypatch):
    """A site test's WebKit page that died ("Target crashed", run 41744982709's Apple Silicon pure tier) named nothing
    of its memory: on macOS the watcher reads the footprint of each of Playwright's processes (its command under a
    playwright folder), the count jetsam and WebKit's memory kill read, and at the tier's end names each one that a
    crash report or a jetsam event since the tier began says ended, with its last footprint and the free memory then;
    another process's report, an older one and an unreadable one aren't taken for it. Names and numbers only."""
    from scripts import ci_resources
    me = (os.getpid(), 1, 5, "node", "/x/.tools/playwright/driver/node run-driver")
    read = ci_resources.footprints([me, (1, 0, 9, "launchd", "/sbin/launchd")])
    if sys.platform != "darwin":
        assert read == {}
    else:
        assert list(read) == [me[0]] and read[me[0]][0] == "node" and 0 < read[me[0]][1] <= read[me[0]][2]
    mine, system = tmp_path / "user", tmp_path / "system"
    for folder in (mine, system):
        folder.mkdir()
    monkeypatch.setattr(ci_resources, "REPORTS", (mine, system))

    def report(folder: Path, name: str, body: dict, age: float = 0) -> None:
        (folder / name).write_text('{"bug_type":"309"}\n' + json.dumps(body), encoding="utf-8")
        os.utime(folder / name, (time.time() - age,) * 2)
    gib, since = 1 << 30, time.time() - 120
    seen = {11: ("com.apple.WebKit.WebContent.Development", 2 * gib, 3 * gib, gib // 2),
            12: ("com.apple.WebKit.WebContent.Development", gib, gib, gib)}
    report(mine, "wc.ips", {"pid": 11, "exception": {"type": "EXC_BAD_ACCESS", "signal": "SIGSEGV"}}, age=3)
    report(mine, "other.ips", {"pid": 99, "exception": {"type": "EXC_CRASH", "signal": "SIGABRT"}}, age=2)
    report(mine, "old.ips", {"pid": 12, "exception": {"type": "EXC_CRASH", "signal": "SIGABRT"}}, age=600)
    (mine / "torn.ips").write_text("{}\n{", encoding="utf-8")   # being written
    report(system, "JetsamEvent.ips", {"memoryStatus": {"pageSize": 16384, "memoryPages": {"free": 32768}},
                                       "processes": [{"pid": 12, "name": "x", "reason": "vm-pageshortage"},
                                                     {"pid": 11, "name": "x"}, {"pid": 98, "reason": "per-process-limit"}]})
    said = ci_resources.reports(since, seen)
    assert said == [
        "com.apple.WebKit.WebContent.Development (id 11) crashed at 2 min: EXC_BAD_ACCESS (SIGSEGV); its footprint "
        "last read 2.00 GiB (its highest 3.00), memory then 0.5 GiB free",
        "a report of the user's unread (JSONDecodeError)",
        "com.apple.WebKit.WebContent.Development (id 12) killed by jetsam at 2 min: vm-pageshortage, memory 0.5 GiB "
        "free by its count; its footprint last read 1.00 GiB (its highest 1.00), memory then 1.0 GiB free"], said
    log = ("Timestamp               Ty Process[PID:TID]\n2026-11-04 00:36:51.123 E  Playwright[812:9a1] "   # a WebKit kill
           "[com.apple.WebKit:Process] 0x12ab - [pageProxyID=7, webPageID=8, PID=901] WebPageProxy::processDidTerminate: "
           "(pid 901), reason=ExceededMemoryLimit\n")
    monkeypatch.setattr(ci_resources.subprocess, "run", lambda *_, **__: types.SimpleNamespace(stdout=log))
    assert ci_resources.webkit_said(since) == ["00:36:51 Playwright: [pageProxyID=7, webPageID=8, PID=901] "
                                               "WebPageProxy::processDidTerminate: (pid 901), reason=ExceededMemoryLimit"]


def test_ci_resources_stops_a_tier_whose_log_stops_growing_its_workers_before_pytest_once_it_printed_the_logs_tail(
        tmp_path):
    """A CI tier that hangs names itself (run 41521288667: Windows' tier sat silent 3.5 h until the job's limit cut it
    off, its log never printed). A log that grows is never quiet; one that stays the same size for the stall time
    stops the tier: the watcher prints the log's last 200 lines, each cut at 240 characters, and the tier's processes
    under it with their ages, then ends xdist's workers (execnet's command line) and only after a while what is
    left, so pytest's controller still writes its summary and failures to the log (Step 4.4ci12's review, F1), and
    exits 3 once STOP exists, so the step fails with time left."""
    from execnet.gateway_io import popen_bootstrapline
    from scripts import ci_resources
    log, stop, stall = tmp_path / "pytest.log", tmp_path / "stop", ci_resources.STALL_S
    growth = ci_resources.Growth(str(log), now=0.0)
    log.write_text("collected\n")
    assert growth.quiet(stall) == 0.0                     # it appeared: grown
    assert growth.quiet(2 * stall - 1) == stall - 1       # still one test running
    log.write_text("collected\n.")
    assert growth.quiet(2 * stall) == 0.0                 # a test ended
    assert growth.quiet(3 * stall) == stall               # quiet for the stall time: stalled
    log.write_text("".join(f"line {i}\n" for i in range(300)) + "x" * 300 + "\n")
    fake = tmp_path / "tier.py"
    fake.write_text(f"""import os, subprocess, sys, time
if sys.argv[1] == "tier":   # the step's subshell, which only ends when it is ended
    subprocess.Popen([sys.executable, __file__, "pytest"])
else:   # pytest's controller: once its worker has ended, it writes its summary, then hangs
    worker = subprocess.Popen([sys.executable, "-u", "-c", {popen_bootstrapline!r}], stdin=subprocess.PIPE, text=True)
    worker.stdin.write(repr("import time; time.sleep(300)") + "\\n")
    worker.stdin.flush()
    print(os.getpid(), worker.pid, flush=True)
    worker.wait()
    with open({str(log)!r}, "a") as f:
        f.write("the summary\\n")
time.sleep(300)
""")
    tier = subprocess.Popen([sys.executable, str(fake), "tier"], stdout=subprocess.PIPE, text=True)
    controller, worker = map(int, tier.stdout.readline().split())
    watcher = subprocess.Popen([sys.executable, "-I", "scripts/ci_resources.py", str(stop), f"--watch={log}",
                                f"--tier={tier.pid}", "--stall=2", f"tier={tmp_path}"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=ROOT)
    try:
        tier.wait(timeout=90)
    finally:
        stop.touch()
        out, err = watcher.communicate(timeout=90)
        if tier.poll() is None:
            tier.kill()
            for pid in (controller, worker):
                try:
                    os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
                except OSError:
                    pass
        tier.stdout.close()
    assert watcher.returncode == 3, (out, err)
    printed = out.split("--- the tier's log hasn't grown in 0 min: the log's last 200 lines\n")[1]
    assert printed.split("\n--- the tier's processes")[0].split("\n") == [f"line {i}" for i in range(101, 300)] + [
        "x" * 240], out
    assert re.search(rf"^\S*python\S* \(id {tier.pid}\): 0 min, \d+ MiB$", out, re.M | re.I), out
    for pid in (controller, worker):
        assert re.search(rf"^ +\S*python\S* \(id {pid}\): 0 min, \d+ MiB$", out, re.M | re.I), out
    assert log.read_text().splitlines()[-1] == "the summary", out   # pytest outlived its worker
    assert "--- the tier stopped" in out, out                       # and was ended once it hung on
    for _ in range(50):
        if not {controller, worker} & {row[0] for row in ci_resources.processes()}:
            break
        time.sleep(0.2)
    else:
        raise AssertionError(f"pytest's controller {controller} or its worker {worker} still runs")
