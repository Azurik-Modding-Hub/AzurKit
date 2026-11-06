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
    module's importers and the takers of the conftest fixtures that call it."""
    picked, touched, later = set(SMOKE), set(), set()
    for rel in changed:
        if "::" in rel:
            path, _, name = rel.partition("::")
            if (units := getattr(deps, "session_units", None)) is None or (module_of(path), name) in units:
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
