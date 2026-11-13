"""The D26 tiers, the empty skip allow-list, xdist's groups and a failed test's one rerun (``tests/conftest.py``)."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
OPT_OUTS = " and not ghidra${{ runner.os != 'macOS' && ' and not xemu' || '' }}"
"""What each CI tier leaves out by marker: Ghidra's tests on every leg, the xemu harness's on Linux and Windows."""


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
    from scripts import ci_matrix
    text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    flags = re.findall(r"--numprocesses=\$\{\{ matrix\.(?:workers|pure) \}\} (--dist=loadgroup --max-worker-restart=0)",
                       text)
    rows = [row for event in ("push", "pull_request")
            for kind in ci_matrix.rows(event, ci_matrix.REPOSITORY, "refs/heads/main").values() for row in kind]
    assert len(flags) == 3 and rows and all(row["workers"] >= 1 and row.get("pure", 1) >= 1 for row in rows)
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


def test_a_failed_test_runs_once_more_and_one_that_passes_it_is_a_recorded_flake_that_fails_nothing(
        pytester, monkeypatch, tmp_path):
    """D1170 (``tests/_rerun.py``): a test whose call or fixture setup or
    teardown fails runs once more at once, on xdist's workers too, and a
    passing one never again; each counts as passed once. One that passes its
    rerun is flaky: its run passes, the summary names it with its first try's
    error after the tier lines (CI's log prints from them on),
    ``AZURKIT_FLAKES``' file gets a line for it as its rerun ends (in the order
    they end), and the receipt keeps it and
    appends it to the flake ledger beside the receipts (``fullsuite.ledger``,
    ``describe``); one that fails twice fails the run."""
    from scripts import fullsuite

    pytester.makeconftest("from tests.conftest import *  # noqa: F403\n")
    pytester.makepyfile(test_r="""
        import os

        import pytest

        def tried(name):
            with open(os.environ["TRIES"], "a") as f:
                f.write(name + "\\n")
            with open(os.environ["TRIES"]) as f:
                return f.read().split().count(name)

        @pytest.fixture(scope="module")
        def shaky():
            assert tried("shaky") > 1, "its first setup failed"

        def test_once():
            assert tried("once") > 1, "the first try failed"

        def test_setup(shaky):
            tried("setup")

        @pytest.fixture
        def sticky():
            yield
            assert tried("sticky") > 1, "its first teardown failed"

        def test_teardown(sticky):
            pass

        def test_steady():
            tried("steady")

        def test_always():
            assert tried("always") < 0, "every try fails"
    """)
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    flaky = [["test_r.py::test_once", "call: AssertionError: the first try failed"],
             ["test_r.py::test_setup", "setup: AssertionError: its first setup failed"],
             ["test_r.py::test_teardown", "teardown: AssertionError: its first teardown failed"]]
    for args, code, outcomes in ((("-n", "2"), 1, {"passed": 4, "failed": 1, "rerun": 4}),
                                 (("-k", "not always"), 0, {"passed": 4, "rerun": 3, "deselected": 1})):
        tries, flakes = tmp_path / f"tries{code}", tmp_path / f"flakes{code}.tsv"
        monkeypatch.setenv("TRIES", str(tries))
        monkeypatch.setenv("AZURKIT_FLAKES", str(flakes))
        run = pytester.runpytest_subprocess("-p", "no:cacheprovider", *args, timeout=300)
        out = run.stdout.str()
        assert (run.ret, {k: n for k, n in run.parseoutcomes().items() if k != "warnings"}) == (code, outcomes), out
        assert Counter(tries.read_text().split()) == {"once": 2, "shaky": 2, "setup": 1, "sticky": 2, "steady": 1} | (
            {"always": 2} if code else {}), args
        assert sorted(line.split("\t") for line in flakes.read_text(encoding="utf-8").splitlines()) == flaky, args
        assert out.index("vanilla: 0 run") < out.index("flaky: 3 passed on their one rerun") < out.index(
            "test_r.py::test_setup: setup: AssertionError: its first setup failed"), out
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    meta = receipts / "suite-k.meta"
    flakes.rename(meta.with_suffix(".flakes"))
    m = fullsuite.ledger(meta, {"key": "k", "head": "f" * 40, "branch": "p2/x", "mode": "changed", "state": "done",
                                "exit_code": 0, "subject": "s", "pytest_args": []})
    assert [[f["test"], f["why"]] for f in m["flakes"]] == flaky and not meta.with_suffix(".flakes").exists()
    assert [[row["test"], row["why"], row["key"], row["branch"]] for row in map(json.loads, (
        receipts / fullsuite.FLAKE_LEDGER).read_text(encoding="utf-8").splitlines())] == [
        [*row, "k", "p2/x"] for row in flaky]
    assert "flaky: 3 passed on their one rerun" in fullsuite.describe(m, meta) and fullsuite.status_code(m) == 0


def test_a_stopped_run_keeps_each_failed_trys_error_lines_and_a_finished_runs_log_prints_a_flakes_whole(
        pytester, monkeypatch, tmp_path):
    """Step 4.37k: each failed try's error lines (where it failed, then its
    ``E`` lines, each cut at ``_rerun.WIDTH``) go to ``AZURKIT_FLAKES``'
    sibling (``_rerun.FAILED``) as its report comes, and a flaky test's line
    to that file as its rerun ends, so a run stopped before its end (a cap, a
    cancelled job: CI's slowed sweep lost its errors so, 4.37f's 8.8) keeps
    them; a finished run's summary prints a flaky test's first error whole
    under its line, past the 200 characters its line keeps (4.37f's C.14).
    The pytest a test runs (this one's) writes neither of its run's files."""
    from tests import _rerun

    pytester.makeconftest("from tests.conftest import *  # noqa: F403\n")
    pytester.makepyfile(test_r="""
        import os

        def tried(name):
            with open(os.environ["TRIES"], "a") as f:
                f.write(name + "\\n")
            with open(os.environ["TRIES"]) as f:
                return f.read().split().count(name)

        def test_always():
            assert tried("always") < 0, "every try fails\\nand says so on two lines"

        def test_once():
            assert tried("once") > 1, "the first try failed: " + "x" * 300

        def test_stop():
            os._exit(3)   # the run stops: no summary, no session's end
    """)
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    whole = "AssertionError: the first try failed: " + "x" * 300
    for args, code in ((), 3), (("-k", "not stop"), 1):
        tries, flakes = tmp_path / f"tries{code}", tmp_path / f"flakes{code}.tsv"
        monkeypatch.setenv("TRIES", str(tries))
        monkeypatch.setenv("AZURKIT_FLAKES", str(flakes))
        run = pytester.runpytest_subprocess("-p", "no:cacheprovider", *args, timeout=300)
        out = run.stdout.str()
        assert run.ret == code, out
        assert [line.split("\t") for line in flakes.read_text(encoding="utf-8").splitlines()] == [
            ["test_r.py::test_once", f"call: {whole}"[:_rerun.WHY]]], out
        failed = [json.loads(line) for line in
                  flakes.with_suffix(_rerun.FAILED).read_text(encoding="utf-8").splitlines()]
        assert [(row["test"], row["when"], row["try"]) for row in failed] == [
            ("test_r.py::test_always", "call", 1), ("test_r.py::test_always", "call", 2),
            ("test_r.py::test_once", "call", 1)], failed
        assert [row["lines"][:3] for row in failed[:2]] == [
            ["at test_r.py:10", "AssertionError: every try fails", "  and says so on two lines"]] * 2, failed
        assert max(len(line) for row in failed for line in row["lines"]) <= _rerun.WIDTH
        assert "".join(failed[2]["lines"][1:3]) == whole, failed[2]   # whole, on lines of WIDTH
        assert ("flaky: 1 passed" in out) == (code == 1), out
    lines = out.splitlines()
    at = lines.index(f"  test_r.py::test_once: call: {whole}"[:2 + len("test_r.py::test_once: ") + _rerun.WHY])
    assert lines[at + 1:at + 4] == ["    at test_r.py:13", f"    {whole[:_rerun.WIDTH]}",
                                    f"    {whole[_rerun.WIDTH:]}"], lines[at:]


def test_a_module_browser_that_stopped_answering_is_launched_again_for_its_rerun_and_the_next_test(
        pytester, monkeypatch, tmp_path):
    """D1260 (``tests/conftest.py``'s ``pytest_runtest_setup``): once a
    module's ``browser`` stopped answering (``tests/_page.py``'s ``stalled``
    closed its Playwright connection), the test whose call stalled still
    fails its first try by name (D1072), and its rerun and the module's next
    test each set up on the browser launched again, the stopped one's
    teardown run first and a warning naming it: the test is flaky, never
    failed twice, and the next one passes (on CI run 43431651205 both failed
    twice at once, on the stopped browser)."""
    pytester.makeconftest("from tests.conftest import pytest_runtest_setup  # noqa: F401\n\n"
                          "pytest_plugins = ['tests._rerun']\n")
    pytester.makepyfile(test_b="""
        import os
        import types

        import pytest

        def said(event):
            with open(os.environ["EVENTS"], "a") as f:
                f.write(event + "\\n")

        @pytest.fixture(scope="module", params=["webkit"])
        def browser(request):   # a stand-in for tests/conftest.py's, one a browser's name: on a connection of its own
            connection = types.SimpleNamespace(_closed_error=None)
            said("launch")
            yield types.SimpleNamespace(_impl_obj=types.SimpleNamespace(_connection=connection))
            said("close")

        def test_stalls(browser):   # its first try's call stalls and _page.stalled closes the connection
            assert browser._impl_obj._connection._closed_error is None, "a stopped browser"
            said("try")
            with open(os.environ["EVENTS"]) as f:
                if f.read().split().count("try") == 1:
                    stopped = RuntimeError("the browser stopped answering: the call")
                    browser._impl_obj._connection._closed_error = stopped
                    raise AssertionError("no answer in 120 s: the call")

        def test_next(browser):
            assert browser._impl_obj._connection._closed_error is None, "a stopped browser"
    """)
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    monkeypatch.setenv("EVENTS", str(events := tmp_path / "events"))
    run = pytester.runpytest_subprocess("-p", "no:cacheprovider", timeout=300)
    out = run.stdout.str()
    assert (run.ret, {k: n for k, n in run.parseoutcomes().items() if k != "warnings"}) == (
        0, {"passed": 2, "rerun": 1}), out
    assert events.read_text().split() == ["launch", "try", "close", "launch", "try", "close"], out
    assert "test_b.py::test_stalls[webkit]: call: AssertionError: no answer in 120 s: the call" in out
    assert out.count("the module's browser stopped answering (the browser stopped answering: the call): "
                     "launched again") == 1, out


def test_ci_reruns_a_failed_test_once_and_its_job_summary_lists_each_that_passed_its_rerun():
    """D1170 on CI: each tier's pytest (the pure job's, a macOS runner's
    folded pure tier, the vanilla tier, whose Linux run resets its
    environment and so names the variable) appends each test that passed its
    one rerun to ``AZURKIT_FLAKES``, one file in the runner's temp folder, and
    pytest's exit stays 0, so the job is green; each job then writes that
    file into its summary, whatever came before (``python -m tests._rerun``):
    a heading with the count, then each test's id and first try's error;
    nothing when no test was flaky."""
    from tests import _rerun

    text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    env = "        env:\n          AZURKIT_FLAKES: ${{ runner.temp }}/flakes.tsv   #"
    summary = ('        if: always()\n        run: if [ -s "$RUNNER_TEMP/flakes.tsv" ]; then uv run --locked python -m '
               'tests._rerun "$RUNNER_TEMP/flakes.tsv" >> "$GITHUB_STEP_SUMMARY"; fi\n')
    for kind in ("pure", "vanilla"):
        steps = re.split(r"(?m)^      - ", _jobs(text)[kind].split("    steps:\n", 1)[1])[1:]
        tiers = [at for at, step in enumerate(steps) if re.search(r"uv run --locked pytest |-m pytest ", step)]
        written = [at for at, step in enumerate(steps) if summary in step]
        assert tiers and all(env in steps[at] for at in tiers), kind
        assert len(written) == 1 and written[0] > max(tiers), kind
    assert 'AZURKIT_FLAKES="$AZURKIT_FLAKES" .venv/bin/python -m pytest "$@"' in text
    rows = "t.py::test_b[x]\tcall: AssertionError: late\nt.py::test_a\tsetup: OSError: busy\n"
    assert _rerun.summary(rows) == ("### Flaky: 2 passed on their one rerun (D1170: recorded, not a block)\n\n"
                                    "- `t.py::test_a`: setup: OSError: busy\n"
                                    "- `t.py::test_b[x]`: call: AssertionError: late\n")
    assert _rerun.summary("") == ""


def test_the_ci_vanilla_tiers_parts_are_disjoint_and_whole_cut_by_measured_seconds_each_xdist_group_in_one(
        pytester, monkeypatch, tmp_path):
    """``tests.yml`` runs each runner's vanilla tier as N jobs at once (Step 4.4ci35: Intel's took up to 2:56 in one),
    each ``--shard=LABEL:K/N`` (``scripts/ci_shards.py``): its matrix holds each label's parts 1..N once, on one image
    and worker count, each label in ``tests/ci_durations.json``. That table comes from the jobs' logs (gh's, each line
    under its job's name): each test the ``--durations`` lines name, its phases summed and averaged over the jobs, the
    rest at the mean of each job's test time on its workers less those, over the tests it ran that they leave out. A
    part keeps the selected tests in their run order, cut where the largest part's seconds are least and the parts
    closest to even, an xdist_group's tests in the part of its first even from another module; the parts are disjoint,
    whole, and the summary says which, with the whole's ids' sha256, under xdist too. Part 1's ``head`` (a macOS
    runner's pure tier, which that part runs first, Step 4.4dx5: the pytest result before the tier's command in its
    log, its seconds times the tier's workers) counts in that part's seconds, so it takes that much less of the tier."""
    from scripts import ci_matrix, ci_shards
    text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    rows = ci_matrix.rows("push", ci_matrix.REPOSITORY, "refs/heads/main")["vanilla"]
    table = json.loads(ci_shards.TABLE.read_text(encoding="utf-8"))
    by_label: dict[str, list] = {}
    for row in rows:
        by_label.setdefault(row["label"], []).append((row["os"], row["workers"], row["shards"], row["shard"]))
    assert by_label and set(by_label) == set(table), (sorted(by_label), sorted(table))
    for label, parts in by_label.items():   # one image and worker count, parts 1..N once
        assert len({p[:3] for p in parts}) == 1, parts
        assert sorted(p[3] for p in parts) == list(range(1, parts[0][2] + 1)), parts
    name, = re.findall(r"name: (vanilla and europe \(.*\))\n", text)
    assert ci_shards.JOB.match(name.replace("${{ matrix.label }}", "macos-x86_64").replace(
        "${{ matrix.shard }}", "2").replace("${{ matrix.shards }}", "3"))
    shard = "--shard=${{ matrix.label }}:${{ matrix.shard }}/${{ matrix.shards }} "
    assert text.count(f"tier -m \"vanilla{OPT_OUTS}\" {shard}") == 1

    job1, job2 = "vanilla and europe (fake-os, 1 of 2)", "vanilla and europe (fake-os, 2 of 2)"
    at = "2026-11-05T22:32:42Z"
    summary = {job1: ["90.00s call     test_a.py::test_long", "30.00s setup    test_a.py::test_grouped_a@built",
                      "10.00s call     test_a.py::test_grouped_a@built",
                      "7 passed, 6 deselected in 100.00s (0:01:40)", 2],
               job2: ["110.00s call     test_a.py::test_long", "20.00s call     test_b.py::test_grouped_b@built",
                      "4 passed, 1 failed, 8 deselected, 1 warning in 160.00s (0:02:40)", 1]}
    lines = [f"{job1}\tSet up job\t{ci_shards.BOM}{at} Current runner version", "pure (fake-os)\tThe pure tier\t"
             f"{at} tier -m vanilla --numprocesses=9", f"pure (fake-os)\tThe pure tier\t{at} = 9 passed in 9.00s =",
             f"{job1}\tThe pure tier\t{at} ===== 20 passed, 13 deselected in 30.00s (0:00:30) ====="]
    for job, (*timed, result, workers) in summary.items():
        lines += [f"{job}\tThe vanilla and europe tiers\t{at} \x1b[36;1mtier -m \"vanilla and not ghidra and not xemu\" "
                  f"--shard=fake-os:1/2 -o x --numprocesses={workers} --dist=loadgroup\x1b[0m",
                  f"{job}\tThe vanilla and europe tiers\t  more"]
        for _ in range(2):   # the step prints its summary twice: its log's tail, then the summary
            lines += [f"{job}\tThe vanilla and europe tiers\t{at} {line}" for line in [
                "vanilla: 7 run", "===== slowest 60 durations =====", *timed, "", "(3 durations < 60s hidden.)",
                f"===== {result} ====="]]
    (log := tmp_path / "run.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (measured := tmp_path / "table.json").write_text('{"other-os": {"rest": 5, "tests": {}}}', encoding="utf-8")
    assert ci_shards.main([str(log), f"--table={measured}"]) == 0
    assert json.loads(measured.read_text(encoding="utf-8")) == {"fake-os": {"head": 60, "rest": 12, "tests": {
        "test_a.py::test_grouped_a": 40, "test_a.py::test_long": 100, "test_b.py::test_grouped_b": 20}},
        "other-os": {"rest": 5, "tests": {}}}   # rest: ((2 * 100 - 130) / 5 + (160 - 130) / 3) / 2; head: 2 * 30

    pytester.makeconftest("from tests.conftest import *  # noqa: F403\n")
    pytester.makepyfile(test_a="""
        import pytest

        @pytest.mark.parametrize("n", range(6))
        def test_short(n):
            pass

        @pytest.mark.xdist_group("built")
        def test_grouped_a():
            pass

        def test_long():
            pass
    """, test_b="""
        import pytest

        @pytest.mark.xdist_group("built")
        def test_grouped_b():
            pass

        @pytest.mark.parametrize("n", range(4))
        def test_more(n):
            pass
    """)
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    whole = [*(f"test_a.py::test_short[{n}]" for n in range(6)), "test_a.py::test_grouped_a", "test_a.py::test_long",
             "test_b.py::test_grouped_b", *(f"test_b.py::test_more[{n}]" for n in range(4))]
    digest = hashlib.sha256("\n".join(whole).encode()).hexdigest()[:12]
    # The runs' seconds: shorts and mores 12 each, the group 40 + 20, test_long 100: 132 | 100 | 48 (not 72 | 160 | 48),
    # and after part 1's head of 60, 60 + 36 | 96 | 148
    assert ci_shards.split([12] * 6 + [60, 100] + [12] * 4, 3) == [0, 7, 8]
    want = [whole[:3], [*whole[3:7], "test_b.py::test_grouped_b"], ["test_a.py::test_long", *whole[-4:]]]
    got = []
    for k in (1, 2, 3):
        run = pytester.runpytest_subprocess("-p", "no:cacheprovider", "--collect-only", "-q", f"--shard=fake-os:{k}/3",
                                            f"--shard-table={measured}")
        got.append(re.findall(r"^(test_[ab]\.py::\S+)$", run.stdout.str(), re.M))
        assert f"shard {k} of 3 (fake-os): {len(want[k - 1])} of the 13 tests selected (their ids' sha256 {digest})" \
               in run.stdout.str(), run.stdout.str()
    assert got == want and sorted(sum(got, [])) == sorted(whole)
    run = pytester.runpytest_subprocess("-p", "no:cacheprovider", "-n", "2", "--dist", "loadgroup", "-v",
                                        "--shard=fake-os:2/3", f"--shard-table={measured}")
    run.assert_outcomes(passed=5)
    workers = re.findall(r"^\[(gw\d)\] .*PASSED test_[ab]\.py::test_grouped_[ab]@built\b", run.stdout.str(), re.M)
    assert len(workers) == 2 and len(set(workers)) == 1, run.stdout.str()
    out = run.stdout.str()
    assert re.search(rf"^web: 0 run\n(?:.*\n)*?shard 2 of 3 \(fake-os\): 5 of the 13 tests selected \(their ids' sha256 "
                     rf"{digest}\), each xdist_group in one shard, about 1 min on 2 workers; each shard's measured s: "
                     r"60 \+ 36, 96, 148$", out, re.M), out
    bad = pytester.runpytest_subprocess("-p", "no:cacheprovider", "--shard=nowhere:1/2", f"--shard-table={measured}")
    assert bad.ret == pytest.ExitCode.USAGE_ERROR and "table.json has no nowhere (it has fake-os, other-os)" in \
        bad.stderr.str(), bad.stderr.str()


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


def _jobs(text: str) -> dict[str, str]:
    """``tests.yml``'s jobs: ``{name: its lines}``."""
    return {job.split(":", 1)[0]: job for job in re.split(r"(?m)^  (?=[\w-]+:\n)", text.split("\njobs:\n", 1)[1])}


def _vanilla_runs(text: str):
    """The vanilla job's ``if:`` as a function of the event, the repository and the ref."""
    rule = re.search(r"(?m)^    if: (.+)$", _jobs(text)["vanilla"])[1]

    def runs(event: str, repository: str, ref: str) -> bool:
        expr = (rule.replace("github.event_name", repr(event)).replace("github.repository", repr(repository))
                .replace("github.ref", repr(ref)).replace("&&", " and ").replace("||", " or "))
        return eval(expr, {"__builtins__": {}, "startsWith": str.startswith})
    return runs


def test_the_ci_vanilla_tier_reads_the_game_data_only_on_a_push_to_main_or_a_lane_branch_of_this_repository():
    """D1123: the vanilla tier, the only job that reads the gamedata environment's deploy key, runs on a push to main
    or to a lane branch (p2/*) of this repository and on nothing else: not a pull request, not a fork's push, not
    another branch. tests.yml's push trigger names the same two, and no other job names the environment."""
    text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert re.search(r"(?m)^  push:\n    branches: \[main, 'p2/\*\*'\]$", text)
    keyed = [name for name, job in _jobs(text).items() if re.search(r"(?m)^    environment: gamedata$", job)]
    assert keyed == ["vanilla"], keyed
    runs = _vanilla_runs(text)
    ours = "Azurik-Modding-Hub/AzurKit"
    assert runs("push", ours, "refs/heads/main") and runs("push", ours, "refs/heads/p2/4.4ci40-lane-ci")
    assert not runs("pull_request", ours, "refs/heads/main")
    assert not runs("push", "someone/AzurKit", "refs/heads/main")
    assert not runs("push", ours, "refs/heads/feature")
    assert not runs("push", ours, "refs/tags/p2/x")


def test_ci_runs_the_pure_tier_once_on_each_runner_and_a_push_asks_for_at_most_5_macos_jobs(
        monkeypatch, tmp_path, capsys):
    """Step 4.4dx5: GitHub runs 5 macOS jobs at once here, and a push asked for 7 (the pure job's two macOS rows and
    the vanilla tier's 5 parts), two of which waited 20-33 min for a slot on the run's critical path. ``tests.yml``'s
    first job writes both matrices (``scripts/ci_matrix.py``, its ``$GITHUB_OUTPUT`` lines read here): where the
    vanilla tier runs (its job's own ``if:``) each macOS runner's part 1 runs its pure tier first, so for a push to
    main, a lane's push and a pull request alike the pure tier runs once on each runner, and a push asks for 5 macOS
    jobs. That step runs in the vanilla job, whose first step starts harden-runner's block, after the setup and before
    the tier's folder, the content, the key and the images, with the pure job's command on the pure tier's workers;
    ``tests/ci_durations.json`` gives each such runner's part 1 a head, the pure tier's seconds."""
    from scripts import ci_matrix, ci_shards
    text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    jobs, runs = _jobs(text), _vanilla_runs(text)
    images = {image for image, *_ in ci_matrix.RUNNERS.values()}
    for case, (event, repository, ref, macos) in enumerate((
            ("push", ci_matrix.REPOSITORY, "refs/heads/main", 5),
            ("push", ci_matrix.REPOSITORY, "refs/heads/p2/4.4dx5-mac-slots", 5),
            ("pull_request", ci_matrix.REPOSITORY, "refs/pull/7/merge", 2),
            ("push", "someone/AzurKit", "refs/heads/main", 2))):
        out = tmp_path / f"output{case}"
        for name, value in (("GITHUB_EVENT_NAME", event), ("GITHUB_REPOSITORY", repository), ("GITHUB_REF", ref),
                            ("GITHUB_OUTPUT", str(out))):
            monkeypatch.setenv(name, value)
        assert ci_matrix.main() == 0 and capsys.readouterr().out.startswith("pure: ")
        got = {kind: json.loads(rows) for kind, rows in re.findall(r"(?m)^(pure|vanilla)=(.*)$", out.read_text())}
        assert got == ci_matrix.rows(event, repository, ref) and bool(got["vanilla"]) == runs(event, repository, ref)
        pure = [row["os"] for row in got["pure"]] + [row["os"] for row in got["vanilla"] if row.get("pure")]
        assert sorted(pure) == sorted(images), (ref, pure)
        assert sum(row["os"].startswith("macos-") for rows in got.values() for row in rows) == macos, (ref, got)
    assert re.search(r"(?m)^      - id: rows\n        run: uv run --no-project --python 3\.14 python -I "
                     r"scripts/ci_matrix\.py$", jobs["matrix"])
    for kind in ("pure", "vanilla"):
        assert "    needs: matrix\n" in jobs[kind], kind
        assert f"      {kind}: ${{{{ steps.rows.outputs.{kind} }}}}\n" in jobs["matrix"], kind
        assert f"        include: ${{{{ fromJSON(needs.matrix.outputs.{kind}) }}}}" in jobs[kind], kind
    steps = re.split(r"(?m)^      - ", jobs["vanilla"].split("    steps:\n", 1)[1])[1:]
    assert re.search(r"uses: step-security/harden-runner@\S+ +# \S+\n +with:\n +egress-policy: block\n", steps[0])
    folded, = [at for at, step in enumerate(steps) if "        if: matrix.pure\n" in step]
    command = (r"\n +(uv run --locked pytest -m \"not vanilla" + re.escape(OPT_OUTS)
               + r"\" .*--numprocesses=\$\{\{ matrix\.\w+ \}\} .*)")
    alone, = re.findall(command, jobs["pure"])
    assert re.findall(command, steps[folded]) == [alone.replace("matrix.workers", "matrix.pure")]
    at = {mark: next(i for i, step in enumerate(steps) if mark in step)
          for mark in ("uv sync --locked", "scripts/web_tools.py", "ci_resources.py --room", "Azurik-Custom-Content",
                       "GAMEDATA_DEPLOY_KEY", "image parts usa.iso")}
    assert max(at["uv sync --locked"], at["scripts/web_tools.py"]) < folded < min(
        at[mark] for mark in ("ci_resources.py --room", "Azurik-Custom-Content", "GAMEDATA_DEPLOY_KEY",
                              "image parts usa.iso")), (folded, at)
    table = json.loads(ci_shards.TABLE.read_text(encoding="utf-8"))
    assert {label for label, measured in table.items() if measured.get("head", 0) > 0} == ci_matrix.FOLDED


# Step 4.28b: Modkit's suite guards, ported lean.


def test_a_macs_failed_pure_tier_still_runs_its_vanilla_part_and_fails_the_job():
    """Step 4.46a: a Mac's part 1 folds the pure tier in ahead of its
    vanilla part, whose steps skipped when it failed (one pure test hid
    each Mac's part 1 in three of main's runs in a row). The folded step goes
    on past a failure (``continue-on-error``), no step after it but those
    that run whatever happened has an ``if:``, and the last fails the job
    for it."""
    steps = re.split(r"(?m)^      - ", _jobs((ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"))["vanilla"].split("    steps:\n", 1)[1])[1:]
    folded, = [at for at, step in enumerate(steps) if "        if: matrix.pure\n" in step]
    assert "        id: pure\n" in steps[folded] and "        continue-on-error: true\n" in steps[folded]
    guards = [re.search(r"(?m)^        if: (.+)$", step) for step in steps[folded + 1:]]
    assert {g[1] for g in guards[:-1] if g} == {"always()"}, guards
    assert guards[-1][1] == "${{ !cancelled() && steps.pure.outcome == 'failure' }}" and steps[-1].endswith(
        "exit 1\n")


def test_the_ci_vanilla_tier_keeps_its_temp_folder_in_the_tier_folder_on_every_runner():
    """Step 4.46a: the tier's tests write their builds to their temp
    folders, which the room check and the last step's delete reach only in
    the tier's folder: Windows' went to C:'s %TEMP% (12.1 GiB left of
    27.6 in run 42629595161). Each runner's ``tier()`` gives pytest
    ``TMPDIR`` there."""
    text = _jobs((ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))["vanilla"]
    tiers = re.findall(r"(?ms)^            tier\(\) \{.*?^            \}$", text)
    assert len(tiers) == 2 and all('TMPDIR="$TIER_ROOM/tmp" ' in tier for tier in tiers), tiers


def test_every_vanilla_job_reads_the_content_commit_the_workflow_pins():
    """Step 4.46a: each vanilla part cloned Azurik-Custom-Content's main as
    it stood when that part started (one run's parts 146 min apart), so a
    content push could test other content than the commit's, or two in one
    run. The content step fetches the one commit ``CONTENT_COMMIT`` names
    (a full sha) and no workflow clones a branch of it."""
    text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    step, = [s for s in re.split(r"(?m)^      - ", _jobs(text)["vanilla"]) if s.startswith("name: Azurik-Custom-")]
    assert re.search(r"(?m)^          CONTENT_COMMIT: [0-9a-f]{40}   # ", step), step
    assert ('fetch --quiet --depth 1 https://github.com/Azurik-Modding-Hub/Azurik-Custom-Content.git "$CONTENT_COMMIT"'
            ' && git -C "$RUNNER_TEMP/content" checkout --quiet FETCH_HEAD; }') in step
    assert not [p.name for p in (ROOT / ".github" / "workflows").glob("*.yml")
                if re.search(r"git clone [^\n]*Azurik-Custom-Content", p.read_text(encoding="utf-8"))]


def test_a_europe_mark_without_vanilla_stops_the_run_and_the_europe_fixture_marks_both(pytester, monkeypatch):
    """Modkit's Step RG.3 (D26 a release): a Europe test is a vanilla one
    too, so ``-m "not vanilla"`` leaves it out: a run that collects a test
    marked ``europe`` alone stops before any test, naming it, and one taking
    ``europe_iso`` is left out by ``-m "not vanilla"`` and by ``-m "not
    europe"`` alike."""
    pytester.makeconftest("from tests.conftest import *  # noqa: F403\n")
    pytester.makepyfile(test_e="""
        import pytest

        @pytest.mark.europe
        def test_alone():
            pass
    """)
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    stopped = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    assert stopped.ret == 4
    assert ("test_e.py::test_alone: a europe test is vanilla too (use the europe_iso fixture)"
            in stopped.stdout.str() + stopped.stderr.str())
    pytester.makepyfile(test_e="def test_reads_europe(europe_iso):\n    pass\n")
    for opt_out in ("not vanilla", "not europe"):
        pytester.runpytest_subprocess("-p", "no:cacheprovider", "-m", opt_out).assert_outcomes(deselected=1)


def test_the_tests_that_start_a_ghidra_server_share_one_xdist_worker():
    """Modkit's AZ-312: a full run under ``-n 8`` hit an XNU TCP deadlock (a
    worker's mock-server thread in ``close()``) that cut the Mac's network
    until a reboot. A test that starts a Ghidra server (a
    ``MockGhidraServer`` or ``ghidra_serve.start``), itself or through its
    module's helpers and fixtures, carries ``xdist_group("ghidra_sockets")``
    (by its module's ``pytestmark`` or a mark of its own, a module constant
    such as ``SOCKETS`` too) and no other group: xdist joins every group a
    test carries into one name, a group of its own. So ``--dist loadgroup``
    runs them on one worker, one after another. Modkit's guard grouped every
    ``socketserver`` and ``http.server`` start too; the app's and the site's
    servers stay spread over the workers on purpose (the host tests'
    in-process ``app.serve``, ``test_site.py``'s ``_static.Files``,
    ``test_dev_tools.py``'s fetch server and ``tests/_page.py``'s server
    processes): in one group the host tier would run on one worker."""
    import ast

    starts = {"MockGhidraServer", "ghidra_serve.start"}

    def names(node: ast.AST) -> set:
        found = set()
        for n in ast.walk(node):
            found.add(getattr(n, "id", None) or getattr(n, "attr", None) or getattr(n, "arg", None))
            if getattr(n, "attr", "") == "start" and getattr(getattr(n, "value", None), "id", "") == "ghidra_serve":
                found.add("ghidra_serve.start")
        return found

    def groups(marks: list) -> set:
        return {a.value for mark in marks for n in ast.walk(mark) if getattr(getattr(n, "func", None), "attr", "")
                == "xdist_group" for a in [*n.args[:1], *(k.value for k in n.keywords if k.arg == "name")]
                if isinstance(a, ast.Constant)}

    tests, ungrouped = [], []
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        consts = {t.id: s.value for s in tree.body if isinstance(s, ast.Assign) for t in s.targets
                  if isinstance(t, ast.Name)}
        defs = {d.name: d for d in tree.body if isinstance(d, (ast.FunctionDef, ast.ClassDef))}
        starting: set[str] = set()
        while more := {name for name, d in defs.items() if name not in starting and names(d) & (starts | starting)}:
            starting |= more   # and each helper or fixture that starts one, and so on
        for name in sorted(n for n in starting if n.startswith(("test_", "Test"))):
            tests.append(f"{path.name}::{name}")
            carried = [*([consts["pytestmark"]] if "pytestmark" in consts else []),
                       *(consts.get(getattr(mark, "id", None), mark) for mark in defs[name].decorator_list)]
            if groups(carried) != {"ghidra_sockets"}:
                ungrouped.append(tests[-1])
    assert tests and ungrouped == []


def test_no_test_finds_an_image_itself_but_through_the_fixtures():
    """Modkit's AZ-057 and AZ-086: a test that found an image itself (the
    sibling ``(USA).xiso`` tree) bypassed the fixtures and skipped quietly
    in another checkout. Only conftest's ``usa_iso`` and ``europe_iso``
    (the D26 gate) and the resolver's own tests (``test_gate.py``) find
    one: no other test module calls ``gate.find``, reads ``AZURKIT_ISO`` or
    ``AZURKIT_ISO_EUROPE`` from the environment or names Modkit's tree."""
    import ast

    variables, tree_name = {"AZURKIT_ISO", "AZURKIT_ISO_EUROPE"}, "Rise of Perathia " + "(USA).xiso"
    found = []
    for path in sorted((ROOT / "tests").glob("*.py")):
        if path.name in ("conftest.py", "test_gate.py"):
            continue
        for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"), str(path))):
            called = ast.unparse(n.func) if isinstance(n, ast.Call) else ""
            if (called == "gate.find" or called in ("os.environ.get", "os.getenv") and n.args
                    and getattr(n.args[0], "value", None) in variables
                    or isinstance(n, ast.Subscript) and ast.unparse(n.value) == "os.environ"
                    and isinstance(n.ctx, ast.Load) and getattr(n.slice, "value", None) in variables
                    or isinstance(n, ast.Constant) and isinstance(n.value, str) and tree_name in n.value):
                found.append(f"{path.name}:{n.lineno}")
    assert found == []


def _read_only(root: Path, writable: bool) -> None:
    for p in (root, *root.rglob("*")):
        p.chmod(p.stat().st_mode | 0o200 if writable else p.stat().st_mode & ~0o222)


def test_the_shim_tests_write_only_their_own_temp_folders(tmp_path):
    """Modkit's AZ-082: the shim tests wrote into the checkout (a scaffold's
    pack, built objects) and the user's cache (zig's). Run in a read-only
    copy of the checkout's tracked files, with every per-user folder at one
    empty folder, the shim tests (``test_shims.py``, ``test_re_shims.py``:
    a shim compiled against the facts, the planner, the inspector,
    test-for-va) pass and that folder stays empty. Their vanilla tests are
    left out, so it needs no image and runs on every CI system."""
    import os
    import subprocess
    import sys

    copy, home = tmp_path / "copy", tmp_path / "home"
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True, timeout=60).stdout
    copied = [rel for rel in listed.decode().split("\0") if rel and (ROOT / rel).is_file()]
    for rel in copied:
        (copy / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, copy / rel)
    for git in (["init", "-q"], ["add", "-f", "--pathspec-from-file=-", "--pathspec-file-nul"]):   # its index
        subprocess.run(["git", "-C", str(copy), *git], input="\0".join(copied).encode(), capture_output=True,
                       check=True, timeout=120)
    home.mkdir()
    users = ("HOME", "USERPROFILE", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
             "LOCALAPPDATA", "APPDATA", "WIN_PD_OVERRIDE_LOCAL_APPDATA", "WIN_PD_OVERRIDE_APPDATA")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")} | dict.fromkeys(users, str(home)) | {
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(copy / "src")}   # the copy's package, not the checkout's
    _read_only(copy, False)
    try:
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", "not vanilla",
                               "tests/test_shims.py", "tests/test_re_shims.py"], cwd=copy, env=env,
                              capture_output=True, text=True, timeout=280)
    finally:
        _read_only(copy, True)
    written = sorted(p.relative_to(home).as_posix() for p in home.rglob("*"))
    assert (done.returncode, written) == (0, []), done.stdout[-4000:] + done.stderr[-2000:]
    assert " passed" in done.stdout and "vanilla: 0 run" in done.stdout


def test_git_in_a_test_writes_its_own_repo_never_the_one_an_exported_git_dir_names(pytester, monkeypatch, tmp_path):
    """Modkit's AZ-542: ``git rebase -x`` exports GIT_DIR to its command, so
    under a per-commit restack a test's ``git init``, commits and
    ``update-ref`` in its tmp_path wrote the lane's repository. With each
    variable that points git at a repository (``git rev-parse
    --local-env-vars`` and GIT_NAMESPACE) naming a scratch bare one, a test
    that makes and commits to its own repository passes, sees none of them,
    and the bare one is untouched (``tests/conftest.py`` drops them)."""
    import subprocess

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, timeout=60)

    def files() -> dict[str, bytes]:
        return {p.relative_to(bare).as_posix(): p.read_bytes() for p in bare.rglob("*") if p.is_file()}

    before = files()
    variables = [*subprocess.run(["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True,
                                 check=True, timeout=60).stdout.split(), "GIT_NAMESPACE"]
    pytester.makeconftest("from tests.conftest import *  # noqa: F403\n")
    pytester.makepyfile(test_git=f"""
        import os
        import subprocess

        def test_makes_and_commits_to_its_own_repo(tmp_path):
            def git(*args):
                subprocess.run(["git", "-C", str(tmp_path), *args], check=True, timeout=60)
            git("init", "-q")
            git("config", "user.name", "t")
            git("config", "user.email", "t@example.invalid")
            (tmp_path / "f").write_text("f", encoding="utf-8")
            git("add", "f")
            git("commit", "-qm", "f")
            git("update-ref", "refs/remotes/origin/main", "HEAD")
            assert (tmp_path / ".git" / "refs" / "remotes" / "origin" / "main").is_file()
            assert not set({variables!r}) & os.environ.keys()
    """)
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    for name in variables:
        monkeypatch.setenv(name, str(bare))
    pytester.runpytest_subprocess("-p", "no:cacheprovider").assert_outcomes(passed=1)
    assert files() == before
