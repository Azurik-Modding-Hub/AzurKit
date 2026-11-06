"""fullsuite: AzurKit's suite for one worktree, under a lock, in the
background, with a receipt (the twin of Modkit's ``fullsuite``).

    uv run --locked python scripts/fullsuite.py WORKTREE [--changed] [--base REF] [--wait SECS] [--force]
    uv run --locked python scripts/fullsuite.py WORKTREE --status [--changed] [--base REF]

It first runs the lint files (:data:`LINT`) in the foreground. A failure
prints their output and queues nothing (no receipt, exit 1). The run then
detaches: it waits for the lock (``<receipts>/lock``), runs ``nice -n 10 uv
run --locked pytest`` in the worktree on :data:`WORKERS` workers (pytest-xdist's
``--dist loadgroup``), killed after :func:`cap` seconds
(:data:`CAP`, more on a loaded host), and writes ``<receipts>/suite-<key>.meta``
(JSON) and ``.log``, whose tail lists the slowest tests. The script prints
the key and the meta's path; Modkit's ``waitfor`` reads that path too.
``--wait SECS`` waits up to SECS seconds. Its exit codes: 0 passed, 1 failed,
3 still running. On 3, issue the same command again: it rejoins the run.

``--changed`` runs only the test files that the worktree's changes against
``main`` (or ``--base``) pick (:func:`plan`), plus :data:`SMOKE`: the lint
files and the gate's test, whose USA and Europe cases make every receipt
show both tiers run (D26). A change in the data folder the tests read by
path (:data:`DATA`: the goldens) picks its readers. A path no rule covers makes it the whole suite; the meta's ``mode``
says which. A changed-area run drives the page in
:data:`CHANGED_BROWSERS` alone (``--browsers``, ``tests/conftest.py``), a
whole one in every browser (D970); the meta's ``browsers`` says which.

Once a changed-area run's pytest passes, its flake stage (Step 4.4dx2,
:func:`flake_stage`) runs each test function the changes add or edit
(:func:`edited_tests`: a changed ``def test*``, not a helper)
:data:`FLAKE_RUNS` times at CI's runners' pace, inside the same lock; a
failure fails the receipt with the test, the run and its output's tail,
and the receipt's ``flake`` block keeps the tests, runs and wall time. A
whole run has none.

Once pytest (and a flake stage) passes, the perf stage runs inside the same lock (D981,
``scripts/perf.py``): the player-facing ops the changes reach (perf.py's
``select``) in the app and the site in WebKit, or on main's own head every
op in every profile and browser; at nice 10, started once the
normal-priority load is under :data:`perf.LOAD_LINE` (it waits, and the
receipt's ``perf`` block says how long). A run whose changes reach no op
has no perf stage. A failing perf block fails the receipt.

The key is built from HEAD, a hash of the uncommitted diff and the untracked
files, the base, the mode, the selection, a changed-area run's browsers and
the perf stage's arguments.
A passing receipt with the same key is reused; ``--force`` runs again.
Receipts live in ``$AZURKIT_RECEIPTS``, else in ``azurkit-receipts/`` in the
repository's common git dir, shared by its worktrees. ``scripts/land.py``
reads them. Stdlib only; the run itself (:func:`runner`) is macOS and Linux's
(it locks with ``fcntl``, imported there, so the planning and receipt code the
tests import loads on Windows too, Step 4.4ci2).
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import perf  # noqa: E402

LINT = ("tests/test_contracts.py", "tests/test_leak_guard.py")
SMOKE = (*LINT, "tests/test_gate.py")   # every changed-area run's; test_gate reads both images
CAP = 1800        # a run's cap on a host whose load is at most its CPU count (cap()): ~3x a whole run on 8 workers
CAP_SCALE = 2.0   # and at most this many times it, on a loaded one
DURATIONS = "--durations=12"   # the slowest tests, at the log's end (never in the keyed pytest_args)
WORKERS = 8   # pytest-xdist's workers; --dist loadgroup keeps a group (tests/conftest.py's) on one (D991)
FINAL = {"done", "capped", "error"}
PERF_CAP = 4 * 3600    # the perf stage's cap (main's full record times every op in every profile)
PERF_WAIT = 3 * 3600   # how long it waits for the load to fall under perf.LOAD_LINE
WHOLE = {"pyproject.toml", "uv.lock", ".python-version", "tests/conftest.py", "tests/skip_allowlist.toml"}
SESSION = {"tests.conftest", "tests._byte_safe", "scripts.ci_shards"}   # every run loads them: what they import is whole
WHEEL = "tests/test_wheel.py"                      # builds the wheel from every file under src/ and installs it
#: The test files that run every module under src/ outside the import graph: the wheel's, and those whose tests
#: take the pyodide, browser or frozen_app fixture (the wheel under Pyodide, the site in a browser, the frozen app).
SRC_TESTS = (WHEEL, "tests/test_characters.py", "tests/test_hosts.py", "tests/test_native.py",
             "tests/test_randomizer.py", "tests/test_service_worker.py", "tests/test_site.py")
DOCS = (".md", ".txt")
ABOUT = "tests/test_site.py::test_the_page_opens_dark_with_its_areas_tabs_the_packs_in_groups_and_build_always_in_view"
#: A path's own tests (a folder's ends in "/"), what reads it outside the import graph: the page (web/) is the
#: site's, its service worker's, the app's (it serves it and freezes it in) and the favicons'; the About tab restates
#: LICENSE and NOTICE.md, and the wheel carries them and README.md (pyproject's license-files and readme);
#: tests/_static.py is the site's and its service worker's tests' file server, which they run as a program.
RULES = (("web/", ("tests/test_site.py", "tests/test_service_worker.py", "tests/test_hosts.py", "tests/test_icon.py")),
         ("LICENSE", (ABOUT, WHEEL)), ("NOTICE.md", (ABOUT, WHEEL)), ("README.md", (WHEEL,)),
         ("tests/_static.py", ("tests/test_site.py", "tests/test_service_worker.py")))
#: The data folders the tests read by path, not by import (AzurKit's goldens): each is named by the modules that hold
#: its last name as a string (``ROOT / "tests" / "goldens"``: ``scripts/record_goldens.py``), so a change in it picks
#: the test files that reach one of them (:func:`graph`).
DATA = ("tests/goldens/",)
CHANGED_BROWSERS = ("chromium",)   # a changed-area run's (D970: a whole run drives the page in every browser)
SUMMARY = re.compile(r"^=+ (\d+ (?:passed|failed|errors?|skipped|deselected).*? in [\d.]+s.*?) =+$", re.M)
TIER = re.compile(r"^(vanilla|europe): (\d+) run$", re.M)
PYTEST = ("uv", "run", "--locked", "pytest")   # the worktree's own pytest (uv finds its environment)
#: The flake stage (Step 4.4dx2): most lost CI rounds were tests a stack had just added or edited that failed only on
#: CI's slow runners, so a changed-area run runs each such test again and again at their pace.
FLAKE_RUNS = 5      # one that fails a run in three passes all five 13 % of the time ((2/3)^5); a run is a pytest start
FLAKE_WORKERS = 2   # tests.yml runs a runner's tier on 1-3 workers
FLAKE_LOOPS = 4     # busy loops beside it: the pure tier slowed so took 39 min here, CI's 36 (Step 4.4ci27)
FLAKE_CAP = 600     # no run starts past it: a changed run took 190-506 s (most of 40 receipts), a whole one 625-1056
FLAKE_MANY = 20     # past this many tests, five runs can't fit the cap: each runs once, slowed, and the receipt says so
FLAKE_TAIL = 40     # a failing run's last lines in the receipt, each cut at 240 characters
FAILED = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.M)
#: A busy loop that ends itself once its runner is gone or at its deadline, so none outlives a killed run.
LOOP = ("import os, time\nparent, end = os.getppid(), time.time() + {secs}\n"
        "while os.getppid() == parent and time.time() < end:\n    sum(range(100000))\n")


def git(wt: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True, encoding="utf-8",
                          check=check).stdout   # Windows' code page can't read the log's UTF-8 (Step 4.4dx1)


def receipts(wt: Path) -> Path:
    if env := os.environ.get("AZURKIT_RECEIPTS"):
        return Path(env)
    return Path(git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()) / "azurkit-receipts"


def module_of(rel: str) -> str | None:
    """The module a repository path holds (``src/azurkit/core/gate.py`` ->
    ``azurkit.core.gate``), or ``None`` for a file that isn't Python."""
    if not rel.endswith(".py"):
        return None
    parts = rel.removeprefix("src/").removesuffix(".py").split("/")
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def imports(source: str) -> set[str]:
    """Every module a Python source imports, its parent packages included."""
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names |= {node.module, *(f"{node.module}.{alias.name}" for alias in node.names)}
    return {".".join(name.split(".")[:i]) for name in names for i in range(1, name.count(".") + 2)}


def reads(source: str) -> set[str]:
    """Each of :data:`DATA`'s folders a Python source names: one of its
    string constants is the folder's last name (``"goldens"``)."""
    names = {node.value for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Constant)}
    return {folder for folder in DATA if folder.rstrip("/").rpartition("/")[2] in names}


def graph(wt: Path) -> dict[str, set[str]]:
    """``{module: the modules it imports and the DATA folders it reads}`` over src/, scripts/ and tests/."""
    files = [p for d in ("src", "scripts", "tests") for p in (wt / d).rglob("*.py")]
    return {module_of(p.relative_to(wt).as_posix()): imports(text := p.read_text(encoding="utf-8")) | reads(text)
            for p in files}


def plan(changed: list[str], deps: dict[str, set[str]]) -> list[str] | None:
    """The test files (or tests) to run for the ``changed`` paths, or ``None``
    for the whole suite: each changed test file, each test file that imports a
    changed module directly or through others, each that reaches a module
    reading a changed :data:`DATA` folder (``deps``' folder entries, :func:`graph`),
    :data:`SRC_TESTS` for a change under src/, a path's :data:`RULES` tests,
    and :data:`SMOKE`; nothing more for other docs. A change to the
    suite's configuration, to what every session loads (``tests/conftest.py``
    and what it imports: it runs the app's no-window check in a Python of its
    own, which every run's session holds) or to a path no rule covers is the
    whole suite."""
    picked, touched = set(SMOKE), set()
    for rel in changed:
        if rel in WHOLE:
            return None
        if own := next((tests for path, tests in RULES
                        if rel == path or path.endswith("/") and rel.startswith(path)), ()):
            picked.update(own)
            continue
        if folder := next((folder for folder in DATA if rel.startswith(folder)), None):
            touched.add(folder)   # its readers are the modules whose deps name it
            continue
        if rel.endswith(DOCS) or rel in (".gitignore", perf.CEILINGS):   # the perf list: the perf stage reads it
            continue
        if (module := module_of(rel)) is None:
            return None
        else:
            touched.add(module)
            picked.update(SRC_TESTS if rel.startswith("src/") else ())
    while more := {m for m, uses in deps.items() if m not in touched and uses & touched}:
        touched |= more
    if touched & SESSION:
        return None
    picked |= {f"{m.replace('.', '/')}.py" for m in touched if m.startswith("tests.test_") and m in deps}
    return sorted(t for t in picked if t.partition("::")[0] == t or t.partition("::")[0] not in picked)


def test_defs(source: str) -> dict[str, str]:
    """``{name: its source}`` of each module-level test function (pytest's
    ``test`` prefix) in ``source``, its decorators included."""
    lines = source.splitlines()
    return {node.name: "\n".join(lines[min(d.lineno for d in [node, *node.decorator_list]) - 1:node.end_lineno])
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test")}


def edited_tests(wt: Path, base: str, changed: list[str]) -> list[str]:
    """The test functions (``tests/test_x.py::test_y``) the ``changed``
    paths add or edit against ``base``: each of a changed test file's whose
    source in the worktree isn't word for word ``base``'s (a new one, a
    renamed one, an edited body or decorator). A helper's or a fixture's
    change, a test only moved and a deleted file add none."""
    found = []
    for rel in changed:
        name = rel.rpartition("/")[2]
        if rel.startswith("tests/") and name.startswith("test_") and name.endswith(".py") and (wt / rel).is_file():
            old = test_defs(git(wt, "show", f"{base}:{rel}", check=False))
            found += [f"{rel}::{test}" for test, source in test_defs((wt / rel).read_text(encoding="utf-8")).items()
                      if old.get(test) != source]
    return sorted(found)


def cap(load5: float | None = None, cpus: int | None = None) -> int:
    """A run's cap in seconds: :data:`CAP` scaled by the host's 5-minute load
    per CPU as it starts, x1 to x:data:`CAP_SCALE` (Modkit's Step X.82b).
    The page tests in WebKit are most of the whole suite, and they slow down
    as the host's load rises (Step 4.1g2)."""
    load5 = os.getloadavg()[1] if load5 is None else load5
    return round(CAP * min(CAP_SCALE, max(1.0, load5 / (cpus or os.cpu_count() or 1))))


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def load(meta: Path) -> dict | None:
    return json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else None


def save(meta: Path, m: dict) -> None:
    tmp = meta.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(meta)


def alive(pid: int | None) -> bool:
    try:
        return bool(pid) and os.kill(pid, 0) is None
    except OSError:
        return False


def state(m: dict) -> str:
    """The receipt's state, or ``orphaned`` when its runner died before it finished."""
    return "orphaned" if m["state"] not in FINAL and not alive(m.get("runner_pid")) else m["state"]


def flake_passed(m: dict) -> bool:
    """Whether the receipt's flake stage passed, or it has none (a whole run, or no test added or edited)."""
    return not m.get("flake_tests") or (m.get("flake") or {}).get("passed") is True


def status_code(m: dict | None) -> int:
    if m is None:
        return 2
    st = state(m)
    if st in ("queued", "running", "flake", "perf"):
        return 3
    perf_ok = not m.get("perf_args") or (m.get("perf") or {}).get("passed") is True
    return 0 if st == "done" and m["exit_code"] == 0 and flake_passed(m) and perf_ok else 1


def describe(m: dict, meta: Path) -> str:
    line = f"fullsuite {m['key']}: {state(m)}" + (f", exit {m['exit_code']}" if m.get("exit_code") is not None else "")
    line += f" [{m['subject']}, {m['mode']}{', ' + str(len(m['pytest_args'])) + ' files' if m['pytest_args'] else ''}"
    line += f"{', ' + ' '.join(m['browsers']) if isinstance(m.get('browsers'), list) else ''}]"
    if m.get("summary") is not None or state(m) in FINAL:
        line += (f"\n  {m.get('summary') or 'no summary line'}; vanilla: {m.get('vanilla_run')} run; "
                 f"europe: {m.get('europe_run')} run; wall {m.get('wall_s')} s of its cap {m.get('cap_s')} s "
                 f"(load {m.get('load')})")
    if m.get("flake_tests"):
        f = m.get("flake") or {}
        line += (f"\n  flake {len(m['flake_tests'])} tests x {f.get('runs', FLAKE_RUNS)} slowed: " + (
            "not run" if not f else f"{'passed' if f.get('passed') else 'failed'}, {f.get('done')} runs in "
                                    f"{f.get('wall_s')} s" + (f" ({f['note']})" if f.get("note") else "")))
        for failure in f.get("failures", [])[:12]:
            line += f"\n    {failure['test']} failed in run {failure['run']}"
        line += "".join(f"\n      {tail}" for tail in (f.get("failures") or [{}])[0].get("tail", [])[-12:])
    if m.get("perf_args"):
        p = m.get("perf") or {}
        line += (f"\n  perf {' '.join(m['perf_args'])}: " + ("not run" if not p else
                 f"{'passed' if p.get('passed') else 'failed'}, {len(p.get('cases', {}))} cases in {p.get('wall_s')} s "
                 f"after {p.get('load_wait_s')} s waiting for the load")
                 + "".join(f"\n    {f}" for f in p.get("failures", [])[:12]))
    return line + f"\n  meta {meta}\n  log {meta.with_suffix('.log')}"


def prepare(wt: Path, changed_area: bool, base_ref: str) -> dict:
    """The run's receipt fields before it runs: its key, mode, pytest
    arguments, browsers (``"all"``: every one, ``tests/conftest.py``'s
    default) and a changed-area run's flake stage's tests."""
    head = git(wt, "rev-parse", "HEAD").strip()
    base = git(wt, "rev-parse", "--verify", "-q", f"{base_ref}^{{commit}}", check=False).strip() or None
    diff = subprocess.run(["git", "-C", str(wt), "diff", "HEAD", "--binary"], capture_output=True, check=True).stdout
    untracked = sorted(filter(None, git(wt, "ls-files", "-z", "--others", "--exclude-standard").split("\0")))
    selection = None
    changed = sorted(set(git(wt, "diff", "--name-only", base).split() + untracked)) if base else []
    if changed_area and base:
        selection = plan(changed, graph(wt))
    mode, browsers = ("full", "all") if selection is None else ("changed", list(CHANGED_BROWSERS))
    flake = edited_tests(wt, base, changed) if mode == "changed" else []   # a whole run has no flake stage
    main = git(wt, "rev-parse", "--verify", "-q", "refs/heads/main", check=False).strip()
    if mode == "full" and head == main and not diff and not untracked:
        perf_args = ["--all"]   # main's full run: every op, every profile and browser
    else:
        pairs = perf.select(changed)
        perf_args = ["--select", ",".join(sorted(f"{h}:{g}" for h, g in pairs))] if pairs else []
    state_hash = hashlib.sha256(diff)
    for rel in untracked:
        state_hash.update(rel.encode() + b"\0" + ((wt / rel).read_bytes() if (wt / rel).is_file() else b""))
    keyed = [mode, None, None] if selection is None else [mode, base, selection, browsers]   # a whole run's as before
    keyed += [{"flake": FLAKE_RUNS, "tests": flake}] if flake else []
    state_hash.update(json.dumps(keyed + ([perf_args] if perf_args else [])).encode())
    return {"key": f"{head[:12]}-{state_hash.hexdigest()[:12]}", "head": head, "base": base, "mode": mode,
            "pytest_args": selection or [], "browsers": browsers, "perf_args": perf_args, "flake_tests": flake,
            "clean": not diff and not untracked,
            "worktree": str(wt),
            "branch": git(wt, "branch", "--show-current").strip(), "subject": git(wt, "log", "-1", "--format=%s").strip()}


def _env() -> dict[str, str]:
    """This environment for a run in another worktree: uv finds that one's own."""
    return {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}


def lint(wt: Path) -> tuple[bool, str]:
    done = subprocess.run(["uv", "run", "--locked", "pytest", "-q", *LINT], cwd=wt, capture_output=True, text=True,
                          timeout=240, env=_env())
    return done.returncode == 0, done.stdout + done.stderr


def command(m: dict) -> list[str]:
    """The run's pytest command: its selection (none: the whole suite), a
    changed-area run's browsers, on :data:`WORKERS` workers, and the slowest
    tests at the log's end."""
    browsers = [f"--browsers={','.join(m['browsers'])}"] if isinstance(m.get("browsers"), list) else []
    return ["nice", "-n", "10", *PYTEST, *m["pytest_args"], *browsers,
            f"--numprocesses={WORKERS}", "--dist=loadgroup", DURATIONS]


def niced(level: int) -> list[str]:
    """The prefix that runs a command at nice ``level`` (none on Windows, which has no nice)."""
    return ["nice", "-n", str(level)] if os.name == "posix" else []


def slowed() -> list[str]:
    """The prefix that runs a command at CI's runners' pace (Step 4.4ci27):
    macOS's lowest CPU and I/O priority (``taskpolicy -b``) under nice 19,
    nice 19 elsewhere."""
    return [*(["taskpolicy", "-b"] if sys.platform == "darwin" else []), *niced(19)]


def flake_command(tests: list[str]) -> list[str]:
    """A flake run's pytest command: the tests in every browser their
    parameters name (no ``--browsers``), slowed, on :data:`FLAKE_WORKERS`."""
    return [*slowed(), *PYTEST, *tests, "-rfE", f"--numprocesses={FLAKE_WORKERS}", "--dist=loadgroup"]


def runner(meta: Path) -> int:
    """The detached run: wait for the lock, run pytest, write the receipt."""
    import fcntl   # POSIX's: only the run locks (the module loads on Windows)

    deadline = time.time() + 60
    while (m := load(meta)) is None or m.get("runner_pid") != os.getpid():   # its queuer names it first
        if time.time() > deadline:
            return 1
        time.sleep(0.05)
    with open(meta.parent / "lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        load5 = os.getloadavg()[1]
        m |= {"state": "running", "started_at": now(), "load": round(load5, 1), "cap_s": cap(load5)}
        save(meta, m)
        t0, capped = time.time(), False
        with open(meta.with_suffix(".log"), "a", encoding="utf-8") as log:
            proc = subprocess.Popen(command(m), cwd=m["worktree"], stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True, env=_env())
            try:
                code = proc.wait(timeout=m["cap_s"])
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                code, capped = proc.wait(), True
        text = meta.with_suffix(".log").read_text(encoding="utf-8", errors="replace")
        tiers = dict(TIER.findall(text))
        summary = SUMMARY.findall(text)
        m |= {"exit_code": code, "wall_s": round(time.time() - t0, 1), "summary": summary[-1] if summary else None,
              "vanilla_run": int(tiers["vanilla"]) if "vanilla" in tiers else None,
              "europe_run": int(tiers["europe"]) if "europe" in tiers else None}
        if code == 0 and not capped:
            m = stages(meta, m)
        m |= {"state": "capped" if capped else "done", "finished_at": now()}
        save(meta, m)
    return 0


def stages(meta: Path, m: dict) -> dict:
    """The receipt after the stages that follow a passing pytest: the flake
    stage, then, once it passed (or with none), the perf stage."""
    if m.get("flake_tests"):
        save(meta, m := m | {"state": "flake"})
        m["flake"] = flake_stage(meta, m)
    if m.get("perf_args") and flake_passed(m):
        save(meta, m := m | {"state": "perf"})
        m["perf"] = perf_stage(meta, m)
    return m


def flake_stage(meta: Path, m: dict) -> dict:
    """The flake block: ``m["flake_tests"]`` run :data:`FLAKE_RUNS` times
    (once past :data:`FLAKE_MANY` tests) by :func:`flake_command`, beside
    :data:`FLAKE_LOOPS` busy loops at the gate's nice 10, each run's output
    appended to the log. It stops at the first failing run, naming each test
    it failed (or the run, killed past the run's cap ``m["cap_s"]``) with
    the output's tail, and starts no run once the stage's time and its
    longest run pass :data:`FLAKE_CAP`; the block says so."""
    tests, t0, walls = m["flake_tests"], time.time(), []
    block = {"tests": tests, "runs": 1 if len(tests) > FLAKE_MANY else FLAKE_RUNS, "done": 0, "failures": [],
             "workers": FLAKE_WORKERS, "loops": FLAKE_LOOPS, "slowed": " ".join(slowed())}
    if block["runs"] < FLAKE_RUNS:
        block["note"] = f"{len(tests)} tests, past {FLAKE_MANY}: one slowed run each"
    loop, loops, out = LOOP.format(secs=FLAKE_CAP + m["cap_s"] + 60), [], meta.with_suffix(".flake.out")
    try:
        for _ in range(FLAKE_LOOPS):
            loops.append(subprocess.Popen([*niced(10), sys.executable, "-c", loop], stdin=subprocess.DEVNULL,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        for run in range(1, block["runs"] + 1):
            if walls and time.time() - t0 + max(walls) > FLAKE_CAP:
                block["note"] = f"{run - 1} of {block['runs']} runs within the stage's {FLAKE_CAP} s"
                break
            t1, capped = time.time(), False
            with open(out, "w", encoding="utf-8") as sink:
                proc = subprocess.Popen(flake_command(tests), cwd=m["worktree"], stdout=sink, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, start_new_session=True, env=_env())
                try:
                    code = proc.wait(timeout=m["cap_s"])
                except subprocess.TimeoutExpired:
                    if os.name == "posix":   # its workers and browsers too: its session
                        os.killpg(proc.pid, signal.SIGKILL)
                    else:
                        proc.kill()
                    code, capped = proc.wait(), True
            walls.append(time.time() - t1)
            text = out.read_text(encoding="utf-8", errors="replace")
            how = f"exit {code}" + (f", killed past {m['cap_s']} s" if capped else "")
            with open(meta.with_suffix(".log"), "a", encoding="utf-8") as log:
                log.write(f"\n==== flake run {run} of {block['runs']}, slowed ({block['slowed']}, {FLAKE_LOOPS} "
                          f"loops), {how} ====\n{text}")
            block["done"] = run
            if code or capped:
                tail = [line[:240] for line in text.splitlines()[-FLAKE_TAIL:]]
                named = (not capped and FAILED.findall(text)) or [f"(the run: {how})"]
                block["failures"] = [{"test": test, "run": run, "tail": tail} for test in dict.fromkeys(named)]
                break
    finally:
        for proc in loops:   # a loop has no children: its own kill ends it (none if it ended by itself)
            proc.kill()
            proc.wait()
        out.unlink(missing_ok=True)
    return block | {"passed": not block["failures"], "wall_s": round(time.time() - t0, 1)}


def perf_stage(meta: Path, m: dict) -> dict:
    """The perf block: ``scripts/perf.py`` on the worktree once the
    normal-priority load is under :data:`perf.LOAD_LINE` (polled every 30 s,
    up to :data:`PERF_WAIT`), at nice 10, its output appended to the log."""
    t0 = time.time()
    while (load5 := perf.normal_load()) >= perf.LOAD_LINE:
        if time.time() - t0 > PERF_WAIT:
            return {"passed": False, "failures": [f"the load stayed at {load5} (>= {perf.LOAD_LINE}) for "
                                                  f"{PERF_WAIT} s: no perf run"], "load_wait_s": round(time.time() - t0)}
        time.sleep(30)
    waited, out = round(time.time() - t0, 1), meta.with_suffix(".perf.json")
    out.unlink(missing_ok=True)
    with open(meta.with_suffix(".log"), "a", encoding="utf-8") as log:
        log.write(f"\n==== perf {' '.join(m['perf_args'])} (normal-priority load {load5}, waited {waited} s) ====\n")
        log.flush()
        proc = subprocess.Popen(["nice", "-n", "10", "uv", "run", "--locked", "python", "scripts/perf.py", m["worktree"],
                                 *m["perf_args"], "--json", str(out)], cwd=m["worktree"], stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True, env=_env())
        try:
            proc.wait(timeout=PERF_CAP)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
    block = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {
        "passed": False, "failures": [f"perf.py wrote no result (exit {proc.returncode}): see the log"]}
    return block | {"load_wait_s": waited, "load": load5}


def wait(meta: Path, secs: float) -> dict | None:
    deadline = time.time() + secs
    while (m := load(meta)) and status_code(m) == 3 and time.time() < deadline:
        time.sleep(min(2.0, max(0.0, deadline - time.time())))
    return load(meta)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fullsuite", description=__doc__.split("\n\n")[0])
    ap.add_argument("worktree", type=Path, nargs="?")
    ap.add_argument("--changed", action="store_true", help="the changed area and the lint files (plan())")
    ap.add_argument("--base", default="main", help="what --changed compares against (default main)")
    ap.add_argument("--wait", type=float, metavar="SECS", help="wait up to SECS for the result")
    ap.add_argument("--status", action="store_true", help="print the receipt for this tree and mode, run nothing")
    ap.add_argument("--force", action="store_true", help="run again even when a passing receipt has the key")
    ap.add_argument("--run", type=Path, help=argparse.SUPPRESS)   # the detached runner
    args = ap.parse_args(argv)
    if args.run:
        return runner(args.run)
    if args.worktree is None:
        ap.error("WORKTREE is required")
    wt = args.worktree.resolve()
    fields = prepare(wt, args.changed, args.base)
    folder = receipts(wt)
    folder.mkdir(parents=True, exist_ok=True)
    meta = folder / f"suite-{fields['key']}.meta"
    m = load(meta)
    if args.status:
        print(describe(m, meta) if m else f"fullsuite {fields['key']}: no receipt")
        return status_code(m)
    if m is None or (status_code(m) != 3 and (args.force or status_code(m) != 0)):
        ok, out = lint(wt)
        if not ok:
            print(out[-6000:], end="")
            print("fullsuite: the lint files fail: fix them and queue again (no receipt)", file=sys.stderr)
            return 1
        if m is not None:
            meta.rename(meta.with_suffix(".meta.prev"))
        meta.with_suffix(".log").unlink(missing_ok=True)
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--run", str(meta)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        save(meta, m := fields | {"state": "queued", "created_at": now(), "exit_code": None, "runner_pid": proc.pid})
    if args.wait is not None:
        m = wait(meta, args.wait)
    print(describe(m, meta))
    return status_code(m)


if __name__ == "__main__":
    sys.exit(main())
