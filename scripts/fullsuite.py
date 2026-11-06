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
files, the gate's test, whose USA and Europe cases make every receipt
show both tiers run (D26), and the scan of every tracked file for a home
path (:data:`SCAN`). A change in a folder the tests read by path
(:data:`DATA`: the goldens, the workflows, the kernels) picks its readers. Only what every session runs
(:func:`graph_of`'s ``every_run``: conftest's and its plugins' top levels and hooks and all they reach) or a path no
rule covers makes it the whole suite; what only a conftest fixture runs picks the tests that take it, and so does a
change to such a module (conftest too) in functions only fixtures or tests call (:func:`narrowed`). The meta's
``mode`` says which. A changed-area run drives the page in
:data:`CHANGED_BROWSERS` alone (``--browsers``, ``tests/conftest.py``), a
whole one in every browser (D970); the meta's ``browsers`` says which.

Once a changed-area run's pytest passes, its flake stage (Step 4.4dx2,
:func:`flake_stage`) runs each test function the changes add or edit
(:func:`edited_tests`: a changed ``def test*``, not a helper)
:data:`FLAKE_RUNS` times at CI's runners' pace (:func:`slowed`), inside the
same lock and within :data:`FLAKE_CAP`, copying the wheel and database the
run built (its build cache, ``<meta>.cache``); a failure fails the receipt
with the test, the run and its output's tail, as does a case with no
passing run by the cap, and the receipt's ``flake`` block keeps the tests,
runs, each run's wall time and slowing. A whole run has none.

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
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import perf  # noqa: E402
import web_tools  # noqa: E402

LINT = ("tests/test_contracts.py", "tests/test_leak_guard.py")
#: It reads every tracked text file, whatever changed (a workflow, a kernel, a comment).
SCAN = "tests/test_agent_files.py::test_no_tracked_text_holds_a_home_path_or_cites_the_private_evidence_folder"
SMOKE = (*LINT, "tests/test_gate.py", SCAN)   # every changed-area run's; test_gate reads both images
CAP = 1800        # a run's cap on a host whose load is at most its CPU count (cap()): ~3x a whole run on 8 workers
CAP_SCALE = 2.0   # and at most this many times it, on a loaded one
DURATIONS = "--durations=12"   # the slowest tests, at the log's end (never in the keyed pytest_args)
WORKERS = 8   # pytest-xdist's workers; --dist loadgroup keeps a group (tests/conftest.py's) on one (D991)
FINAL = {"done", "capped", "error"}
PERF_CAP = 4 * 3600    # the perf stage's cap (main's full record times every op in every profile)
PERF_WAIT = 3 * 3600   # how long it waits for the load to fall under perf.LOAD_LINE
WHOLE = {"pyproject.toml", "uv.lock", ".python-version", "tests/conftest.py", "tests/skip_allowlist.toml"}
#: Every run loads them (conftest and its pytest_plugins): what a session runs of them is whole (:func:`graph_of`).
SESSION = {"tests.conftest", "tests._byte_safe", "scripts.ci_shards"}
CONFTEST = "tests.conftest"   # its fixtures run only for the tests that take them: graph()'s "tests.conftest::NAME"
PY_DIRS = ("src", "scripts", "tests", "devkit", "nativekit", "shimkit", "assets")   # every tracked .py's but the root's
WHEEL = "tests/test_wheel.py"                      # builds the wheel from every file under src/ and installs it
#: The test files that run every module under src/ outside the import graph: the wheel's, and those whose tests
#: take the pyodide, browser or frozen_app fixture (the wheel under Pyodide, the site in a browser, the frozen app).
SRC_TESTS = (WHEEL, "tests/test_characters.py", "tests/test_hosts.py", "tests/test_native.py",
             "tests/test_randomizer.py", "tests/test_service_worker.py", "tests/test_site.py")
DOCS = (".md", ".txt")
ABOUT = "tests/test_site.py::test_the_page_opens_dark_with_its_areas_tabs_the_packs_in_groups_and_build_always_in_view"
#: A path's own tests (a folder's ends in "/"), what reads it outside the import graph: the page (web/) is the
#: site's, its service worker's, the app's (it serves it and freezes it in) and the favicons'; the About tab restates
#: LICENSE and NOTICE.md, and the wheel carries them and README.md (pyproject's license-files and readme). A module run
#: as a program by its path (``tests/_static.py``, the site tests' file server) is read by graph() as an import.
RULES = (("web/", ("tests/test_site.py", "tests/test_service_worker.py", "tests/test_hosts.py", "tests/test_icon.py")),
         ("LICENSE", (ABOUT, WHEEL)), ("NOTICE.md", (ABOUT, WHEEL)), ("README.md", (WHEEL,)))
#: The folders the tests read by path, not by import: AzurKit's goldens, the workflows, the kernels' C sources
#: (``nativekit`` builds them) and the libraries built from them (``azurkit.core.native`` loads them). Each is named
#: by the modules that hold its last name as a string (``ROOT / "tests" / "goldens"``: ``scripts/record_goldens.py``),
#: so a change in it picks the test files that reach one of them (:func:`graph`).
DATA = ("tests/goldens/", ".github/", "native/", "src/azurkit/core/_native/")
CHANGED_BROWSERS = ("chromium",)   # a changed-area run's (D970: a whole run drives the page in every browser)
SUMMARY = re.compile(r"^=+ (\d+ (?:passed|failed|errors?|skipped|deselected).*? in [\d.]+s.*?) =+$", re.M)
TIER = re.compile(r"^(vanilla|europe): (\d+) run$", re.M)
PYTEST = ("uv", "run", "--locked", "pytest")   # the worktree's own pytest (uv finds its environment)
#: The flake stage (Step 4.4dx2): most lost CI rounds were tests a stack had just added or edited that failed only on
#: CI's slow runners, so a changed-area run runs each such test again and again at their pace.
FLAKE_RUNS = 5      # one that fails a run in three passes all five 13 % of the time ((2/3)^5); a run is a pytest start
FLAKE_WORKERS = 3   # tests.yml runs the pure tier, the page's tests in it, on 3 workers on CI's Intel runners
FLAKE_LOOPS = 4     # busy loops at nice 10 beside taskpolicy -b: the pure tier so took 39 min here, CI's 36 (4.4ci27)
FLAKE_UTILITY_LOOPS = 12  # busy loops in its class beside the utility clamp: about CI's Intel pace at load 60 (4.4dx4)
FLAKE_QUIET = 3.0   # s: PROBE's most under taskpolicy -b for a run to start under it (slowed(); Step 4.4dx4)
PROBE = "for _ in range(600):\n    sum(range(200000))\n"   # 0.86 s here at nice 10 on an idle performance core
FLAKE_CAP = 840     # the stage's wall: a run still going at it is ended, and none starts its longest so far won't fit in
FLAKE_MANY = 20     # past this many tests, five runs can't fit the cap: each runs once, slowed, and the receipt says so
FLAKE_TAIL = 40     # a failing run's last lines in the receipt, each cut at 240 characters
FAILED = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.M)
#: A case's outcome in a verbose run's output, as xdist's workers print it (``[gw0] [ 50%] PASSED t.py::t[x]``) or
#: pytest alone (``t.py::t[x] PASSED [ 50%]``); a case's id may hold spaces (``t.py::t[a linked folder]``).
OUTCOME = re.compile(r"^\[gw\d+\] \[ *\d+%\] (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) (\S+::.*?) *$"
                     r"|^(\S+::.*?) (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b", re.M)
#: The group a worker under ``--dist loadgroup`` adds to an xdist group's case id (``t.py::t[x]@frozen_app``,
#: ``tests/conftest.py``), which its collection without workers doesn't: past the id's last ``]``, ``/`` or ``:``.
GROUP = re.compile(r"@[^@\[\]/:]*$")
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


def _roots(source: str | ast.AST | list) -> list:
    return [ast.parse(source)] if isinstance(source, str) else source if isinstance(source, list) else [source]


def _base(node: ast.ImportFrom, module: str | None, package: bool) -> str | None:
    """The module a ``from ... import`` names, a relative one resolved against
    ``module`` (``package``: an ``__init__``), or None when it can't be."""
    if not node.level:
        return node.module
    if module is None:
        return None
    parts = module.split(".")[:None if package else -1]
    parts = parts[:len(parts) - node.level + 1]
    return ".".join([*parts, *([node.module] if node.module else [])]) or None


def imports(source: str | ast.AST | list, module: str | None = None, package: bool = False) -> set[str]:
    """Every module a Python source (or its nodes) imports, its parent packages
    included; a relative import resolved against ``module`` (:func:`_base`)."""
    names = set()
    for node in (n for root in _roots(source) for n in ast.walk(root)):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and (base := _base(node, module, package)):
            names |= {base, *(f"{base}.{alias.name}" for alias in node.names)}
    return {".".join(name.split(".")[:i]) for name in names for i in range(1, name.count(".") + 2)}


def reads(source: str | ast.AST) -> set[str]:
    """Each of :data:`DATA`'s folders a Python source names: one of its
    string constants is the folder's last name (``"goldens"``)."""
    names = {node.value for root in _roots(source) for node in ast.walk(root) if isinstance(node, ast.Constant)}
    return {folder for folder in DATA if folder.rstrip("/").rpartition("/")[2] in names}


def _runs(tree: ast.AST, rel: str) -> set[str]:
    """The modules a source runs as programs by their paths: a string (no
    docstring, no space) that is a Python file's path, ends in "/" and it, or
    is the name of one beside it (``Path(__file__).with_name("_static.py")``),
    whether or not the file is there (a deleted one's users still name it). A
    test file named so is pytest's to run, not a program."""
    docs = {id(node.body[0].value) for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)}
    folder, out = rel.rpartition("/")[0], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(text := node.value, str) and id(node) not in docs \
                and text and not any(c.isspace() for c in text):
            ends = {text, *(text[i + 1:] for i, c in enumerate(text) if c == "/"), f"{folder}/{text}".lstrip("/")}
            out |= {m for o in ends if o != rel and (m := module_of(o)) and not m.startswith("tests.test_")}
    return out


def _chains(nodes: list) -> set[str]:
    """The names the nodes read, each whole (``web_tools.missing``,
    ``close_browser``, ``web_tools`` when the module itself is passed on)."""
    walked = [n for root in nodes for n in ast.walk(root)]
    inner, out = {id(n.value) for n in walked if isinstance(n, ast.Attribute)}, set()
    for n in walked:
        if isinstance(n, (ast.Attribute, ast.Name)) and id(n) not in inner:
            parts = []
            while isinstance(n, ast.Attribute):
                parts, n = [n.attr, *parts], n.value
            if isinstance(n, ast.Name):
                out.add(".".join([n.id, *parts]))
    return out


def _main_guard(node: ast.stmt) -> bool:
    """``if __name__ == "__main__":``."""
    return (isinstance(node, ast.If) and isinstance(t := node.test, ast.Compare) and isinstance(t.left, ast.Name)
            and t.left.id == "__name__" and len(t.comparators) == 1 and isinstance(t.comparators[0], ast.Constant)
            and t.comparators[0].value == "__main__")


DYNAMIC = {"globals", "vars", "locals", "eval", "exec", "sys.modules"}   # a function reading one runs its module's all


def _scope(tree: ast.Module, module: str, package: bool) -> dict:
    """A module's parts for :func:`_reach`: what its top level imports and reads
    (its classes whole, its functions' decorators and defaults), each top-level
    function's own imports and reads, and the names its imports bind."""
    aliases: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):   # "import a.b" binds a, "import a.b as c" binds c to a.b
            for a in node.names:
                aliases.setdefault(a.asname or a.name.partition(".")[0], set()).add(
                    a.name if a.asname else a.name.partition(".")[0])
        elif isinstance(node, ast.ImportFrom) and (base := _base(node, module, package)):
            for a in node.names:
                aliases.setdefault(a.asname or a.name, set()).add(f"{base}.{a.name}")
    top, funcs = [], {}
    for node in tree.body:
        if _main_guard(node):   # its program's, not run on import
            continue
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top.append(node)
            continue
        top += [*node.decorator_list, *node.args.defaults, *filter(None, node.args.kw_defaults)]
        marks = [d.func if isinstance(d, ast.Call) else d for d in node.decorator_list]
        autouse = any(isinstance(d, ast.Call) and any(k.arg == "autouse" and not (isinstance(k.value, ast.Constant)
                      and k.value.value is False) for k in d.keywords) for d in node.decorator_list)
        funcs[node.name] = {"imports": imports(node.body, module, package), "chains": _chains(node.body),
                            "decorated": bool(marks),
                            "params": {a.arg for a in ast.walk(node.args) if isinstance(a, ast.arg)},
                            "fixture": not autouse and any(c == "fixture" or c.endswith(".fixture")
                                                           for c in _chains(marks))}
    return {"imports": imports(top, module, package), "chains": _chains(top), "funcs": funcs, "aliases": aliases}


def _resolve(scopes: dict, module: str, chain: str, depth: int = 0) -> list[tuple[str, str | None]]:
    """What ``chain`` read in ``module`` names: ``(module, function)``,
    ``(module, "*")`` for a module passed on whole, ``(module, None)`` for
    anything else of one (a class, a value: its top level)."""
    head, _, rest = chain.partition(".")
    if head in scopes[module]["funcs"]:
        return [(module, head)]
    out = []
    for target in scopes[module]["aliases"].get(head, ()) if depth < 8 else ():
        full = [*target.split("."), *filter(None, rest.split("."))]
        if found := next((i for i in range(len(full), 0, -1) if ".".join(full[:i]) in scopes), None):
            mod = ".".join(full[:found])
            out += [(mod, "*")] if found == len(full) else [
                (mod, None), *_resolve(scopes, mod, ".".join(full[found:]), depth + 1)]
    return out


def _reach(scopes: dict, modules=(), units=(), seen: tuple = (frozenset(), frozenset())) -> tuple[set, set]:
    """``(modules, functions)`` a run executes from ``modules`` (imported) and
    ``units`` (called), past ``seen``: an imported module runs its top level, its
    pytest hooks and its decorated functions (but conftest's fixtures), a called
    function its imports and every function and module it names."""
    seen_m, seen_u = set(seen[0]), set(seen[1])
    todo = [("m", m) for m in modules] + [("u", u) for u in units]
    while todo:
        kind, item = todo.pop()
        if kind == "m":
            for name in (".".join(item.split(".")[:i]) for i in range(1, item.count(".") + 2)):
                if name in seen_m:
                    continue
                seen_m.add(name)
                if (s := scopes.get(name)) is None:
                    continue
                todo += [("m", m) for m in s["imports"]]
                todo += [("u", u) for c in s["chains"] for u in _resolve(scopes, name, c)]
                todo += [("u", (name, f)) for f, fn in s["funcs"].items() if f.startswith("pytest_") or f in (
                    "__getattr__", "__dir__") or fn["decorated"] and not (name == CONFTEST and fn["fixture"])]
        elif item not in seen_u:
            seen_u.add(item)
            mod, f = item
            todo.append(("m", mod))
            if mod not in scopes or f is None:
                continue
            every = scopes[mod]["funcs"]
            if f == "*" or (fn := every.get(f)) is None:
                todo += [("u", (mod, g)) for g in every] if f == "*" else []
                continue
            todo += [("m", m) for m in fn["imports"]]
            todo += [("u", u) for c in fn["chains"] for u in _resolve(scopes, mod, c)]
            todo += [("u", (mod, g)) for g in every] if fn["chains"] & DYNAMIC else []
    return seen_m, seen_u


def _names(tree: ast.AST, fixtures: set[str]) -> set[str]:
    """The conftest fixtures a source may take: a parameter or a string of that
    name, or where it asks for one by a name it computes, each the name may be
    (``request.getfixturevalue(f"{release}_iso")``: those ending in ``_iso``;
    one with no constant ends: every one)."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
        elif isinstance(node, ast.Call) and isinstance(call := node.func, ast.Attribute) \
                and call.attr == "getfixturevalue":
            for arg in (a for a in node.args if not isinstance(a, ast.Constant)):
                parts = arg.values if isinstance(arg, ast.JoinedStr) and arg.values else [None]
                ends = [v.value if isinstance(v, ast.Constant) else "" for v in (parts[0], parts[1:] and parts[-1])]
                found |= {f for f in fixtures if f.startswith(ends[0]) and f.endswith(ends[-1])
                          and len(f) >= len(ends[0]) + len(ends[-1])}
    return found & fixtures


class Graph(dict):
    """:func:`graph_of`'s ``{module: what it uses}``; :attr:`every_run`: the
    modules (and DATA folders) every run's session executes or reads, whatever
    tests it selects; :attr:`session_units`: the ``(module, function)`` it calls;
    :attr:`fixture_units`: each other one a conftest fixture calls, to the
    fixtures (``tests.conftest::NAME``) that do."""
    every_run: frozenset[str] = frozenset()
    session_units: frozenset[tuple[str, str]] = frozenset()
    fixture_units: dict[tuple[str, str], set[str]]


def graph_of(files: dict[str, str]) -> Graph:
    """``{module: the modules it imports or runs by path, the DATA folders it
    reads and the conftest fixtures it may take}`` over ``files`` (``{path:
    source}``). A conftest fixture is a module of its own
    (``tests.conftest::NAME``) using what only it runs: its body's imports and
    the functions it names, past the session's. :attr:`Graph.every_run` is what
    :data:`SESSION`'s modules run as each session loads them (:func:`_reach`):
    conftest's and its plugins' top levels, what those import, their hooks and
    the functions and modules those name, however deep."""
    mods = {rel: module_of(rel) for rel in files}
    trees = {rel: ast.parse(text) for rel, text in files.items()}
    scopes = {mods[rel]: _scope(tree, mods[rel], rel.endswith("__init__.py")) for rel, tree in trees.items()}
    runs = {mods[rel]: _runs(tree, rel) for rel, tree in trees.items()}
    deps = Graph({mods[rel]: imports(tree, mods[rel], rel.endswith("__init__.py")) | reads(tree) | runs[mods[rel]]
                  for rel, tree in trees.items()})
    seen = _reach(scopes, modules=SESSION)   # and the folders and programs its modules name by path
    deps.every_run = frozenset(seen[0] | {f for m in seen[0] & deps.keys() for f in deps[m] & set(DATA) | runs[m]})
    deps.session_units, deps.fixture_units = frozenset(seen[1]), {}
    fixtures = {f for f, fn in scopes[CONFTEST]["funcs"].items() if fn["fixture"]} if CONFTEST in scopes else set()
    for f in fixtures:
        own = _reach(scopes, units=[(CONFTEST, f)], seen=seen)
        deps[f"{CONFTEST}::{f}"] = (own[0] - seen[0]) | {
            f"{CONFTEST}::{g}" for g in scopes[CONFTEST]["funcs"][f]["params"] & fixtures - {f}}
        for unit in own[1] - seen[1]:
            deps.fixture_units.setdefault(unit, set()).add(f"{CONFTEST}::{f}")
    for rel, tree in trees.items():
        if mods[rel] != CONFTEST:
            deps[mods[rel]] |= {f"{CONFTEST}::{f}" for f in _names(tree, fixtures)}
    return deps


def graph(wt: Path) -> Graph:
    """:func:`graph_of` over every Python file under :data:`PY_DIRS` and at the root."""
    paths = [p for d in PY_DIRS for p in (wt / d).rglob("*.py")] + sorted(wt.glob("*.py"))
    return graph_of({p.relative_to(wt).as_posix(): p.read_text(encoding="utf-8") for p in paths})


def parts(rel: str, old: str | None, new: str | None) -> list[str]:
    """A module's change from ``old`` to ``new`` as the top-level functions it
    changes (``rel::NAME``; none for its docstring, comments or layout alone),
    or ``[rel]`` when anything else differs: its top level (imports, classes,
    values, its ``__main__`` block, its functions' decorators and defaults
    but literal ones, which run as it loads: removing ``autouse`` would leave
    the head tree's takers short of the tests the fixture ran for), a function
    gone or defined twice, or either side missing or unparsable."""
    def runs(node):   # a literal (120, -1, ("a", 2)) runs nothing as its module loads
        try:
            ast.literal_eval(node)
        except (ValueError, TypeError, RecursionError):
            return True
        return False

    def split(text):
        body = ast.parse(text).body
        body = body[1:] if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) else body
        funcs = [n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        made = {n.name: m for n in funcs if (m := [ast.dump(d) for d in (
            *n.decorator_list, *n.args.defaults, *filter(None, n.args.kw_defaults)) if runs(d)])}
        return [ast.dump(n) for n in body if n not in funcs], made, {n.name: ast.dump(n) for n in funcs}, len(funcs)
    try:
        (*top_a, fa, na), (*top_b, fb, nb) = split(old), split(new)
    except (SyntaxError, TypeError, ValueError):   # TypeError: a side missing
        return [rel]
    if top_a != top_b or len(fa) != na or len(fb) != nb or fa.keys() - fb.keys():
        return [rel]
    return [f"{rel}::{name}" for name in sorted(fb) if fa.get(name) != fb[name]]


def narrowed(wt: Path, base: str, changed: list[str], deps: dict) -> list[str]:
    """``changed`` with each module every session runs (``deps.every_run``) as
    the functions its change against ``base`` changes (:func:`parts`)."""
    out = []
    for rel in changed:
        if module_of(rel) in getattr(deps, "every_run", ()):
            new = (wt / rel).read_text(encoding="utf-8") if (wt / rel).is_file() else None
            out += parts(rel, git(wt, "show", f"{base}:{rel}", check=False) or None, new)
        else:
            out.append(rel)
    return out


def plan(changed: list[str], deps: dict[str, set[str]]) -> list[str] | None:
    """The test files (or tests) to run for the ``changed`` paths, or ``None``
    for the whole suite: each changed test file, each test file that imports a
    changed module directly or through others (or runs it by its path, or takes
    a conftest fixture that runs it: :func:`graph_of`), each that reaches a
    module reading a changed :data:`DATA` folder (``deps``' folder entries),
    :data:`SRC_TESTS` for a change under src/, a path's :data:`RULES` tests,
    and :data:`SMOKE`; nothing more for other docs. A change to the suite's
    configuration, to what every session runs (``deps.every_run``; for a plain
    dict, :data:`SESSION` and all it imports), to a path no rule covers (a
    Python file outside :data:`PY_DIRS` and the root, which :func:`graph`
    doesn't read, is one) or a deleted module no module still names is the
    whole suite (a renamed one is
    its old path deleted, :func:`prepare` lists both; a deleted test file
    drops only its own tests). The session checks the app's no-window mode in a Python of its
    own, so the app isn't what every session runs. A function of such a module
    (``path::NAME``, :func:`narrowed`) the session doesn't call picks its
    module's importers and the takers of the conftest fixtures that call it;
    any other path holding "::" (a file's own name) is the whole suite."""
    picked, touched, later = set(SMOKE), set(), set()
    for rel in changed:
        if "::" in rel:   # narrowed()'s part of an every_run module, or else a path whose name holds "::"
            path, _, name = rel.partition("::")
            if module_of(path) not in getattr(deps, "every_run", ()) or not name.isidentifier() \
                    or (module_of(path), name) in deps.session_units:
                return None
            later |= {module_of(path), *deps.fixture_units.get((module_of(path), name), ())}
            picked.update(SRC_TESTS if path.startswith("src/") else ())
            continue
        if rel in WHOLE or rel.endswith(".py") and "/" in rel and rel.partition("/")[0] not in PY_DIRS:
            return None   # a Python file graph() doesn't read: what it imports and what runs it are unknown
        if own := next((tests for path, tests in RULES
                        if rel == path or path.endswith("/") and rel.startswith(path)), ()):
            picked.update(own)
            continue
        if folder := next((folder for folder in DATA if rel.startswith(folder)), None):
            touched.add(folder)   # its readers are the modules whose deps name it
            picked.update(SRC_TESTS if rel.startswith("src/") else ())
            continue
        if rel.endswith(DOCS) or rel in (".gitignore", perf.CEILINGS):   # the perf list: the perf stage reads it
            continue
        if (module := module_of(rel)) is None:
            return None
        if module not in deps and not module.startswith("tests.test_") and not any(
                module in uses for uses in deps.values()):
            return None   # a deleted module no module names: who ran it isn't in the head tree
        touched.add(module)
        picked.update(SRC_TESTS if rel.startswith("src/") else ())
    if (every := getattr(deps, "every_run", None)) is None:
        every, todo = set(), list(SESSION)
        while todo:
            if (m := todo.pop()) not in every:
                every.add(m)
                todo += deps.get(m, ())
    if touched & every:
        return None
    touched |= later
    while more := {m for m, uses in deps.items() if m not in touched and uses & touched}:
        touched |= more
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
                                    f"{f.get('wall_s')} s" + (f" (each {', '.join(map(str, f['walls']))} s)"
                                                              if f.get("walls") else "")
                                    + (f" ({f['note']})" if f.get("note") else "")))
        for failure in f.get("failures", [])[:12]:
            line += f"\n    {failure['test']} " + (f"capped: no passing run within {f.get('cap_s')} s"
                                                   if failure.get("capped") else f"failed in run {failure['run']}")
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
    changed = sorted(set(git(wt, "diff", "--no-renames", "--name-only", base).split() + untracked)) if base else []
    if changed_area and base:
        selection = plan(narrowed(wt, base, changed, deps := graph(wt)), deps)
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


def _env(cache: Path | None = None) -> dict[str, str]:
    """This environment for a run in another worktree: uv finds that one's
    own; with ``cache``, the folder its wheel and database builds keep their
    files in (``web_tools.CACHE``)."""
    return {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"} | ({web_tools.CACHE: str(cache)} if cache else {})


def lint(wt: Path) -> tuple[bool, str]:
    done = subprocess.run(["uv", "run", "--locked", "pytest", "-q", *LINT], cwd=wt, capture_output=True, text=True,
                          timeout=240, env=_env())
    return done.returncode == 0, done.stdout + done.stderr


def command(m: dict) -> list[str]:
    """The run's pytest command: its selection (none: the whole suite), a
    changed-area run's browsers, on :data:`WORKERS` workers, and the slowest
    tests at the log's end."""
    browsers = [f"--browsers={','.join(m['browsers'])}"] if isinstance(m.get("browsers"), list) else []
    return [*niced(10), *PYTEST, *m["pytest_args"], *browsers,
            f"--numprocesses={WORKERS}", "--dist=loadgroup", DURATIONS]


def niced(level: int) -> list[str]:
    """The prefix that runs a command at nice ``level`` (none on Windows, which has no nice)."""
    return ["nice", "-n", str(level)] if os.name == "posix" else []


def slowings() -> list[tuple[list[str], list[str], int]]:
    """The flake runs' slowings, slowest first: each run's prefix, its busy
    loops' prefix and how many. On macOS its background policy
    (``taskpolicy -b``: the efficiency cores alone, at the lowest CPU and I/O
    priority) under nice 19 beside :data:`FLAKE_LOOPS` at nice 10, then its
    utility clamp (``taskpolicy -c utility``) under nice 19 beside
    :data:`FLAKE_UTILITY_LOOPS` in that class; elsewhere nice 19 beside
    :data:`FLAKE_LOOPS` at nice 10."""
    if sys.platform != "darwin":
        return [(niced(19), niced(10), FLAKE_LOOPS)]
    utility = ["taskpolicy", "-c", "utility", *niced(19)]
    return [(["taskpolicy", "-b", *niced(19)], niced(10), FLAKE_LOOPS), (utility, utility, FLAKE_UTILITY_LOOPS)]


def slowed() -> tuple[tuple[list[str], list[str], int], dict[str, float | None]]:
    """The slowing (:func:`slowings`) that runs a flake run at about CI's
    Intel runners' pace, and what chose it: the first whose :data:`PROBE`
    (a fixed CPU-bound loop timed under it) ends within
    :data:`FLAKE_QUIET`, else the last; ``{prefix: the probe's s, None past
    the bound}``. ``taskpolicy -b`` keeps CI's pace on a quiet box, but on a
    busy one its processes starve behind every other's: its one-time builds
    took over 900 s where they take 8 s, and at load 45 two runs of two
    tests that pass in 48 s ended at 240-300 s with 1 case of 6 passed and 3
    failed (Step 4.4dx4), while the utility clamp ran them at CI's pace."""
    options, probed = slowings(), {}
    for option in options[:-1]:
        t0 = time.time()
        try:
            subprocess.run([*option[0], sys.executable, "-I", "-c", PROBE], stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=FLAKE_QUIET)
            probed[" ".join(option[0])] = round(time.time() - t0, 2)
            return option, probed
        except subprocess.TimeoutExpired:
            probed[" ".join(option[0])] = None
    return options[-1], probed


def case_id(said: str) -> str:
    """A case's id as its collection names it: a worker's, without its group (:data:`GROUP`)."""
    return GROUP.sub("", said)


def flake_command(tests: list[str], prefix: list[str]) -> list[str]:
    """A flake run's pytest command: the tests in every browser their
    parameters name (no ``--browsers``), under ``prefix`` (:func:`slowed`),
    on :data:`FLAKE_WORKERS`, each case's outcome on a line as it ends
    (``-v``, :data:`OUTCOME`)."""
    return [*prefix, *PYTEST, *tests, "-v", "-rfE", f"--numprocesses={FLAKE_WORKERS}", "--dist=loadgroup"]


def descendants(pid: int) -> list[int]:
    """The processes under ``pid`` (POSIX ``ps``'s parent ids): its children, theirs and so on."""
    rows = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True).stdout.split()
    children: dict[int, list[int]] = {}
    for child, parent in zip(rows[::2], rows[1::2]):
        children.setdefault(int(parent), []).append(int(child))
    found, todo = [], [pid]
    while todo:
        found += (more := children.get(todo.pop(), []))
        todo += more
    return found


def end(proc: subprocess.Popen) -> int:
    """End a run started in a session of its own: it, every process under it
    (its workers and drivers, and the browsers Playwright starts in
    sessions of their own) and its session's group; its exit code."""
    if os.name != "posix":   # Windows: taskkill ends its tree
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        return proc.wait()
    for pid in [proc.pid, *descendants(proc.pid)]:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    return proc.wait()


def runner(meta: Path) -> int:
    """The detached run: wait for the lock, then :func:`run`."""
    import fcntl   # POSIX's: only the run locks (the module loads on Windows)

    deadline = time.time() + 60
    while (m := load(meta)) is None or m.get("runner_pid") != os.getpid():   # its queuer names it first
        if time.time() > deadline:
            return 1
        time.sleep(0.05)
    with open(meta.parent / "lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run(meta, m)
    return 0


def run(meta: Path, m: dict) -> dict:
    """Run pytest, then its :func:`stages`, and write the receipt. The run
    and its flake stage share one build cache (``<meta>.cache``, removed
    after), so the stage's slowed runs copy the wheel and database the run
    built (``web_tools.kept``)."""
    load5 = os.getloadavg()[1] if hasattr(os, "getloadavg") else 0.0
    m |= {"state": "running", "started_at": now(), "load": round(load5, 1), "cap_s": cap(load5)}
    save(meta, m)
    t0, capped, cache = time.time(), False, meta.with_suffix(".cache")
    try:
        with open(meta.with_suffix(".log"), "a", encoding="utf-8") as log:
            proc = subprocess.Popen(command(m), cwd=m["worktree"], stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True, env=_env(cache))
            try:
                code = proc.wait(timeout=m["cap_s"])
            except subprocess.TimeoutExpired:
                code, capped = end(proc), True
        text = meta.with_suffix(".log").read_text(encoding="utf-8", errors="replace")
        tiers = dict(TIER.findall(text))
        summary = SUMMARY.findall(text)
        m |= {"exit_code": code, "wall_s": round(time.time() - t0, 1), "summary": summary[-1] if summary else None,
              "vanilla_run": int(tiers["vanilla"]) if "vanilla" in tiers else None,
              "europe_run": int(tiers["europe"]) if "europe" in tiers else None}
        if code == 0 and not capped:
            m = stages(meta, m)
    finally:
        shutil.rmtree(cache, ignore_errors=True)
    m |= {"state": "capped" if capped else "done", "finished_at": now()}
    save(meta, m)
    return m


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
    (once past :data:`FLAKE_MANY` tests) by :func:`flake_command`, each
    under the slowing :func:`slowed` picks as it starts, beside that
    slowing's busy loops, each run's output appended to the log and its wall
    time and slowing kept. Nothing built once is built
    slowed: the runs copy the wheel and database the gate's run built (its
    cache, ``<meta>.cache``: ``web_tools.kept``), and their cases are
    collected first at the gate's nice 10 (a collection past the cap is
    ended as a run is). It stops at the first failing run, naming each
    test it failed with the output's tail. The stage's wall is
    :data:`FLAKE_CAP`: no run starts that its longest run so far won't
    fit in, and a run still going at it is ended with every process under
    it (:func:`end`): each case it failed so far fails the block (one that
    passed an earlier run too), and each case with no passing run by then
    fails it by name, capped."""
    tests, t0 = m["flake_tests"], time.time()
    deadline, out = t0 + FLAKE_CAP, meta.with_suffix(".flake.out")
    env = _env(meta.with_suffix(".cache")) | {"PYTHONUNBUFFERED": "1"}   # each outcome's line out before an end
    block = {"tests": tests, "runs": 1 if len(tests) > FLAKE_MANY else FLAKE_RUNS, "done": 0, "failures": [],
             "walls": [], "slowed": [], "workers": FLAKE_WORKERS, "cap_s": FLAKE_CAP}
    if block["runs"] < FLAKE_RUNS:
        block["note"] = f"{len(tests)} tests, past {FLAKE_MANY}: one slowed run each"
    with subprocess.Popen([*niced(10), *PYTEST, "--collect-only", "-q", *tests], cwd=m["worktree"], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, env=env,
                          start_new_session=True) as listing:   # a session of its own: end() reaches uv's python
        try:
            ids, err = listing.communicate(timeout=FLAKE_CAP)
            code, said = listing.returncode, ids + err
        except subprocess.TimeoutExpired:
            end(listing)
            code, ids, said = f"past {FLAKE_CAP} s", "", "".join(listing.communicate())   # what it said so far
    if code or not (cases := re.findall(r"^(\S+::.*?) *$", ids, re.M)):
        tail = [line[:240] for line in said.splitlines()[-FLAKE_TAIL:]]
        block["failures"] = [{"test": f"(their collection: exit {code})", "run": 0, "tail": tail}]
        return block | {"passed": False, "wall_s": round(time.time() - t0, 1)}
    block["cases"], passed, tail, ended = len(cases), set(), [], False
    loop, loops = LOOP.format(secs=FLAKE_CAP + 60), []
    try:
        for run in range(1, block["runs"] + 1):
            if block["walls"] and time.time() + max(block["walls"]) > deadline:
                block["note"] = f"{run - 1} of {block['runs']} runs within the stage's {FLAKE_CAP} s"
                break
            (prefix, beside, count), probed = slowed()
            slowing = f"{' '.join(prefix)}, {count} loops at {' '.join(beside) or 'its own priority'}"
            block["slowed"].append({"slowing": slowing, "probes": probed})
            loops = [subprocess.Popen([*beside, sys.executable, "-c", loop], stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(count)]
            t1, ended, command = time.time(), False, flake_command(tests, prefix)
            with open(out, "w", encoding="utf-8") as sink:
                proc = subprocess.Popen(command, cwd=m["worktree"], stdout=sink, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, start_new_session=True, env=env)
                try:
                    code = proc.wait(timeout=max(0.1, deadline - time.time()))
                except subprocess.TimeoutExpired:
                    code, ended = end(proc), True
            block["walls"].append(round(time.time() - t1, 1))
            for proc in loops:   # a loop has no children: its own kill ends it (none if it ended by itself)
                proc.kill()
                proc.wait()
            text = out.read_text(encoding="utf-8", errors="replace")
            outcomes = [(case_id(b or c), a or d) for a, b, c, d in OUTCOME.findall(text)]
            passed |= {case for case, said in outcomes if said == "PASSED"}
            how = f"exit {code}" + (f", ended at the stage's {FLAKE_CAP} s" if ended else "")
            with open(meta.with_suffix(".log"), "a", encoding="utf-8") as log:
                log.write(f"\n==== flake run {run} of {block['runs']}, slowed ({block['slowed'][-1]['slowing']}; probes "
                          f"{probed}), {how} in {block['walls'][-1]} s ====\n{text}")
            tail = [line[:240] for line in text.splitlines()[-FLAKE_TAIL:]]
            if ended:   # its failures so far fail the block: one that passed an earlier run is a flake all the same
                named = [case for case, said in outcomes if said in ("FAILED", "ERROR")]
                block["failures"] = [{"test": test, "run": run, "tail": tail} for test in dict.fromkeys(named)]
                block["note"] = f"run {run} ended at the stage's {FLAKE_CAP} s"
                break
            block["done"] = run
            if code:
                named = [case_id(test) for test in FAILED.findall(text)] or [f"(the run: {how})"]
                block["failures"] = [{"test": test, "run": run, "tail": tail} for test in dict.fromkeys(named)]
                break
        named = {failure["test"] for failure in block["failures"]}
        if (ended or not named) and (left := [case for case in cases if case not in passed | named]):
            block["failures"] += [{"test": case, "run": len(block["walls"]), "tail": tail, "capped": True}
                                  for case in left]
            block["note"] = "; ".join(filter(None, (block.get("note"), f"capped: {len(left)} of {len(cases)} cases "
                                                    f"without a passing run within the stage's {FLAKE_CAP} s")))
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
