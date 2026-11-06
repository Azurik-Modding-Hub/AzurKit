"""The vanilla tier's shards on CI (``.github/workflows/tests.yml``, Step 4.4ci35): each runner's tier runs as N jobs at
once, each a part of the tests it selects, so the tier ends in about an hour where it took up to 3 h in one job. This
module is the pytest plugin that cuts the parts (``tests/conftest.py`` loads it) and the script that writes the seconds
it cuts by, :data:`TABLE`, from the tier's CI logs.

    uv run --locked python scripts/ci_shards.py [--table PATH] [LABEL=]LOG ...

A LOG is ``gh run view RUN --log`` (each line under its job's name: every vanilla job of the run, each one's label read
from its name) or ``gh run view --job JOB --log``, or a job's raw log as ``LABEL=LOG``. Each job's ``--durations``
lines (each test phase past a minute) give those tests' seconds, and the rest of the job's test time on its workers,
over the tests it ran that they leave out, gives each of those its ``rest``. A label it reads replaces that label's
table, averaged over its jobs; the others stay. It prints test ids and numbers, nothing read from an image.

``pytest --shard=LABEL:K/N`` runs the K-th of N parts of what the run selects (after ``-m``), its tests in their run
order cut into N runs, every ``xdist_group``'s tests in the run of its first (one group on one worker, D991), by
LABEL's seconds (a test the table doesn't list counts its ``rest``): the largest run's seconds as small as they can
be, and of the cuts that give it, the one with the runs closest to even (the least sum of their squares). Every process
of each shard cuts the same collection the same way, so the parts are disjoint and their union is the whole; the
summary's ``shard`` line names its part, its count of the whole and the whole's ids' sha256, alike in each shard of a
runner."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "tests" / "ci_durations.json"
"""``{label: {"rest": s, "tests": {test id: s}}}``: each runner's measured seconds a test, whole seconds."""

SPEC = re.compile(r"(?P<label>[\w.-]+):(?P<k>\d+)/(?P<n>\d+)\Z")
JOB = re.compile(r"vanilla and europe \((?P<label>[\w.-]+)(?:, \d+ of \d+)?\)\Z")
STAMP = re.compile(r"\d{4}-\d\d-\d\dT[\d:.]+Z ?")
TIER = re.compile(r"tier -m vanilla .*?--numprocesses=(\d+)")   # the step's command, as GitHub prints it
SLOWEST = re.compile(r"=+ slowest (?:\d+ )?durations =+\Z")
PHASE = re.compile(r"(\d+(?:\.\d+)?)s +(?:setup|call|teardown) +(\S.*?)\s*\Z")
RESULT = re.compile(r"=+ (?P<counts>\d+ \w+(?:, \d+ \w+)*) in (?P<secs>\d+(?:\.\d+)?)s(?: \([\d:]+\))? =+\Z")
COUNT = re.compile(r"(\d+) (\w+)")
RAN = {"passed", "failed", "error", "errors", "skipped", "xfailed", "xpassed"}
GROUP = re.compile(r"@[\w.-]+\Z")   # xdist's group suffix on a grouped test's id (tests/conftest.py)
BOM = "\N{ZERO WIDTH NO-BREAK SPACE}"   # GitHub's log starts with one
SHARD = pytest.StashKey[tuple[str, int, int, dict]]()
_line: list[str] = []   # this run's shard line: its own, or under xdist a worker's


def split(weights: list[int], parts: int) -> list[int]:
    """Where each of ``parts`` runs of ``weights``, kept in order, starts: the largest run's sum as small as it can be
    and, of the cuts that give it, the one with the least sum of the runs' squared sums (the earliest cut on a tie)."""
    n = len(weights)
    at = [0, *itertools.accumulate(weights)]
    worst = [0, *[float("inf")] * n]   # worst[j]: the least largest run of the first j weights in the runs so far
    for _ in range(parts):
        worst = [min(max(worst[i], at[j] - at[i]) for i in range(j + 1)) for j in range(n + 1)]
    bound, best, back = worst[n], [0, *[float("inf")] * n], []
    for _ in range(parts):
        new, choice = [float("inf")] * (n + 1), [0] * (n + 1)
        for j in range(n + 1):
            for i in range(j + 1):
                if (run := at[j] - at[i]) <= bound and best[i] + run * run < new[j]:
                    new[j], choice[j] = best[i] + run * run, i
        best = new
        back.append(choice)
    starts, j = [], n
    for choice in reversed(back):
        starts.append(j := choice[j])
    return starts[::-1]


def _groups(item) -> str:
    return "_".join(sorted({str(m.args[0] if m.args else m.kwargs.get("name", "default"))
                            for m in item.iter_markers("xdist_group")}))


def _plain(item) -> str:
    """The test's id without the ``@group`` suffix tests/conftest.py gives a grouped one under ``--dist loadgroup``."""
    return item.nodeid.removesuffix(f"@{group}") if (group := _groups(item)) else item.nodeid


def pytest_addoption(parser):
    parser.addoption("--shard", metavar="LABEL:K/N",
                     help="run the K-th of N parts of the selected tests, cut in their run order by LABEL's measured "
                          "seconds, each xdist_group in one (scripts/ci_shards.py; tests.yml's vanilla tier)")
    parser.addoption("--shard-table", metavar="PATH", default=str(TABLE),
                     help="the seconds --shard cuts by (default: tests/ci_durations.json)")


def pytest_configure(config):
    if (spec := config.getoption("shard", None)) is None:
        return
    if not (m := SPEC.match(spec)) or not 1 <= int(m["k"]) <= int(m["n"]):
        raise pytest.UsageError(f"--shard takes LABEL:K/N with 1 <= K <= N, not {spec!r}")
    path = Path(config.getoption("shard_table"))
    table = json.loads(path.read_text(encoding="utf-8"))
    if m["label"] not in table:
        raise pytest.UsageError(f"--shard: {path.name} has no {m['label']} (it has {', '.join(sorted(table))})")
    config.stash[SHARD] = (m["label"], int(m["k"]), int(m["n"]), table[m["label"]])


@pytest.hookimpl(trylast=True)   # after -m deselects and pytest orders the run, with tests/conftest.py's groups made
def pytest_collection_modifyitems(config, items):
    if (spec := config.stash.get(SHARD, None)) is None:
        return
    label, k, n, measured = spec
    units: dict[str, list] = {}
    for item in items:
        units.setdefault(f"@{group}" if (group := _groups(item)) else item.nodeid, []).append(item)
    runs = list(units.values())
    weights = [sum(measured["tests"].get(_plain(item), measured["rest"]) for item in run) for run in runs]
    starts = [*split(weights, n), len(runs)]
    mine = {id(item) for run in runs[starts[k - 1]:starts[k]] for item in run}
    whole = len(items)
    digest = hashlib.sha256("\n".join(map(_plain, items)).encode()).hexdigest()[:12]
    workers = getattr(config, "workerinput", {}).get("workercount", 1)
    part = weights[starts[k - 1]:starts[k]]
    minutes = max(sum(part) / workers, max(part, default=0)) / 60   # no part ends before its longest run
    if dropped := [item for item in items if id(item) not in mine]:
        config.hook.pytest_deselected(items=dropped)
        items[:] = [item for item in items if id(item) in mine]
    _line[:] = [f"shard {k} of {n} ({label}): {len(items)} of the {whole} tests selected (their ids' sha256 {digest}), "
                f"each xdist_group in one shard, about {minutes:.0f} min on {workers} worker{'s' * (workers > 1)}; "
                f"each shard's measured s: {', '.join(str(sum(weights[a:b])) for a, b in itertools.pairwise(starts))}"]
    if hasattr(config, "workeroutput"):
        config.workeroutput["shard"] = _line[0]


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    """Under xdist the workers cut; the controller prints a worker's line."""
    if not _line and (line := getattr(node, "workeroutput", {}).get("shard")):
        _line.append(line)


@pytest.hookimpl(trylast=True)   # after tests/conftest.py's "vanilla: N run", where tests.yml's printed summary starts
def pytest_terminal_summary(terminalreporter):
    for line in _line:
        terminalreporter.write_line(line)


def jobs(arg: str) -> dict[str, tuple[str, list[str]]]:
    """``{job: (its label, its lines)}`` of a log's vanilla jobs, each line without its job's columns or its time."""
    label, path = m.groups() if (m := re.match(r"([\w.-]+)=(.+)\Z", arg)) and not Path(arg).exists() else (None, arg)
    lines = Path(path).read_text(encoding="utf-8", errors="replace").lstrip(BOM).splitlines()
    gh = bool(lines) and lines[0].count("\t") >= 2 and bool(STAMP.match(lines[0].split("\t", 2)[2].lstrip(BOM)))
    if not gh and label is None:
        raise SystemExit(f"ci_shards: {path} isn't gh's log of named jobs: give its label, LABEL={path}")
    out: dict[str, tuple[str, list[str]]] = {}
    name = ""
    for line in lines:
        if gh and line.count("\t") >= 2:   # a line of gh's: its job, its step, its text (a text's later lines: no time)
            name, _, line = line.split("\t", 2)
        if gh and not (job := JOB.match(name)):
            continue
        key, of = (name, job["label"]) if gh else (path, label)
        out.setdefault(key, (of, []))[1].append(STAMP.sub("", line.lstrip(BOM), count=1))
    return out


def timed(lines: list[str]) -> tuple[int, float, int, dict[str, float]] | None:
    """A job's workers, its tests' seconds and count, and ``{test: seconds}`` of those its ``--durations`` lines name
    (their phases summed; its first block, as tests.yml prints the summary twice), or None if its tier never ended."""
    workers = secs = ran = None
    listed: dict[str, float] = {}
    block = None
    for line in lines:
        if block is True:
            if m := PHASE.match(line):
                listed[test] = listed.get(test := GROUP.sub("", m[2]), 0) + float(m[1])
                continue
            block = False
        if workers is None and (m := TIER.search(line)):
            workers = int(m[1])
        elif block is None and SLOWEST.match(line):
            block = True
        elif secs is None and (m := RESULT.match(line)):
            secs, ran = float(m["secs"]), sum(int(c) for c, kind in COUNT.findall(m["counts"]) if kind in RAN)
    return None if workers is None or secs is None else (workers, secs, ran, listed)


def measure(args: list[str]) -> dict[str, dict]:
    """Each label's table from the logs' jobs that ended (each test's mean over the jobs that name it, the rest's over
    every job), printing what each label read."""
    seen: dict[str, list] = {}
    for arg in args:
        for job, (label, lines) in jobs(arg).items():
            if (got := timed(lines)) is None:
                print(f"ci_shards: {job}: no tier's command line or end in it, left out")
            else:
                seen.setdefault(label, []).append(got)
    out = {}
    for label, runs in sorted(seen.items()):
        tests: dict[str, list[float]] = {}
        for *_, listed in runs:
            for test, s in listed.items():
                tests.setdefault(test, []).append(s)
        rest = [(workers * secs - sum(listed.values())) / max(1, ran - len(listed))
                for workers, secs, ran, listed in runs]
        out[label] = {"rest": max(1, round(sum(rest) / len(rest))),
                      "tests": {test: max(1, round(sum(s) / len(s))) for test, s in sorted(tests.items())}}
        print(f"{label}: {len(runs)} job{'s' * (len(runs) > 1)}, {len(tests)} tests timed, the rest "
              f"{out[label]['rest']} s each")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("logs", nargs="+", metavar="[LABEL=]LOG")
    ap.add_argument("--table", type=Path, default=TABLE, help="the table to write (default: tests/ci_durations.json)")
    args = ap.parse_args(argv)
    if not (new := measure(args.logs)):
        print("ci_shards: no vanilla job in those logs ended", file=sys.stderr)
        return 1
    table = json.loads(args.table.read_text(encoding="utf-8")) if args.table.exists() else {}
    args.table.write_text(json.dumps(dict(sorted((table | new).items())), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {args.table.name}: {', '.join(sorted(table | new))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
