"""The D26 tiers, the empty skip allow-list and xdist's groups (``tests/conftest.py``)."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
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
