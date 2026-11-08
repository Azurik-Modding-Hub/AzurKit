"""The engine's contracts: the sdk's API is its snapshot (``tests/sdk_api.txt``,
written by ``scripts/sdk_api.py``), import-linter's (``pyproject.toml``: the
layers and the four tools' independence) and the rules it can't express,
read from the AST: ``core``, ``edits`` and ``tools`` hold no threads, processes,
subprocesses, prints or exits (the web page's worker runs them as they are;
the app-only ``tools/randomizer/live/`` is exempt), only ``tools/characters``
and the randomizer's drawing (its maps and icons: ``tools/randomizer/art/`` and
the reach model's first stage, ``tools/randomizer/draft/``) import numpy, and
nothing imports capstone, unicorn, zig, Tk or ``devkit`` (none of them ships).
Beside them, the lint set's other rule: the developer log holds no bullet twice
(``scripts/devlog.py``, Step 4.4dx1)."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import tomllib
import zipfile
from pathlib import Path

from importlinter.cli import lint_imports

from scripts import devlog, sdk_api

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "azurkit"
ENGINE = ("core/", "edits/", "tools/")
APP_ONLY = ("tools/randomizer/live/",)
ENGINE_IMPORTS = {"threading", "_thread", "multiprocessing", "concurrent", "subprocess", "asyncio"}
ENGINE_CALLS = {"print", "exit", "quit", "sys.exit", "os._exit", "os.system", "os.popen", "os.fork", "os.forkpty",
                "os.kill"}
ENGINE_CALL_PREFIXES = ("os.spawn", "os.exec", "os.posix_spawn")
NEVER = {"capstone", "unicorn", "ziglang", "tkinter", "devkit"}
NUMPY_HOME = ("tools/characters/", "tools/randomizer/art/", "tools/randomizer/draft/")
# AZ-830: what reaches a swap's bytes rounds the same on every platform, its libm calls core/fdlibm.py's (the previews'
# drawer, draw.py, writes no built byte)
SAME_BITS = ("tools/characters/", "core/xbr/")
SAME_BITS_ASIDE = ("tools/characters/draw.py",)
LIBM = {"sin", "cos", "tan", "asin", "acos", "atan", "atan2", "exp", "expm1", "exp2", "log", "log2", "log10", "log1p",
        "pow", "cbrt", "sinh", "cosh", "tanh", "arcsin", "arccos", "arctan", "arctan2", "power", "float_power", "hypot"}


def violations(source: str, rel: str) -> list[str]:
    """``"<rel>:<line> <why>"`` for each contract the module ``rel`` (a path
    under ``src/azurkit/``) breaks."""
    engine = rel.startswith(ENGINE) and not rel.startswith(APP_ONLY)
    found = []
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
        for name in names:
            top = name.split(".")[0]
            if top in NEVER or (top == "numpy" and not rel.startswith(NUMPY_HOME)):
                found.append(f"{rel}:{node.lineno} imports {name}")
            elif engine and (top in ENGINE_IMPORTS or name in ENGINE_CALLS
                             or name.startswith(ENGINE_CALL_PREFIXES)):
                found.append(f"{rel}:{node.lineno} imports {name}")
        if engine and isinstance(node, ast.Call):
            called = ast.unparse(node.func)
            if called in ENGINE_CALLS or called.startswith(ENGINE_CALL_PREFIXES):
                found.append(f"{rel}:{node.lineno} calls {called}")
        if rel.startswith(SAME_BITS) and rel not in SAME_BITS_ASIDE:
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.attr in LIBM
                    and (node.value.id in ("np", "numpy") or node.value.id == "math" and node.attr != "hypot")):
                found.append(f"{rel}:{node.lineno} calls the platform's {node.value.id}.{node.attr} (fdlibm's)")
            elif (isinstance(node, (ast.BinOp, ast.AugAssign)) and isinstance(node.op, ast.Pow)
                  and not (isinstance(base := getattr(node, "left", getattr(node, "target", None)), ast.Constant)
                           and type(base.value) is int)):
                found.append(f"{rel}:{node.lineno} raises to a power by the platform's pow (fdlibm.sq, cube, pow)")
    return found


def test_the_sdk_api_is_its_snapshot():
    """Every UI calls the sdk alone, so its surface (each name in
    ``sdk.__all__``, its signature and its docstring) changes only with
    ``tests/sdk_api.txt``, whose diff shows the change."""
    assert sdk_api.SNAPSHOT.read_text(encoding="utf-8") == sdk_api.text(), "run scripts/sdk_api.py"


def test_the_developer_log_holds_no_bullet_twice():
    """Step 4.4dx1: ``docs/DEVLOG.md`` merges with git's union driver, which
    keeps a lane's edited bullet beside its old line; no release holds two
    bullets with one bold title or most of their words alike."""
    assert devlog.stale((ROOT / devlog.LOG).read_text(encoding="utf-8")) == []


def test_import_linter_contracts_hold(capsys):
    assert lint_imports(config_filename=str(ROOT / "pyproject.toml"), no_cache=True) == 0, capsys.readouterr().out


def test_the_engine_holds_no_threads_processes_prints_or_exits_numpy_stays_in_its_homes_and_swaps_call_no_libm():
    caught = {   # each form the rules name, in an engine module
        "import threading": "imports threading",
        "from concurrent.futures import ThreadPoolExecutor": "imports concurrent.futures",
        "import subprocess as sp": "imports subprocess",
        "from os import fork": "imports os.fork",
        "print('x')": "calls print",
        "import sys\nsys.exit(1)": "calls sys.exit",
        "os.execv('a', [])": "calls os.execv",
        "import numpy as np": "imports numpy",
        "from capstone import Cs": "imports capstone",
        "import devkit.xemu": "imports devkit.xemu",
    }
    for source, why in caught.items():
        assert any(v.endswith(why) for v in violations(source, "core/x.py")), source
    for source, why in {"math.sin(x)": "math.sin (fdlibm's)", "np.arctan2(y, x)": "np.arctan2 (fdlibm's)",
                        "x ** 2": "pow (fdlibm.sq, cube, pow)", "x **= 0.5": "pow (fdlibm.sq, cube, pow)"}.items():
        assert any(v.endswith(why) for v in violations(source, "tools/characters/x.py")), source   # AZ-830
    assert violations("2 ** 31 + math.hypot(x, y) + fdlibm.sin(x)", "core/xbr/x.py") == []
    assert violations("np.sin(x)", "tools/characters/draw.py") == violations("np.sin(x)", "tools/mods/x.py") == []
    assert violations("import numpy\nimport threading", "tools/randomizer/live/x.py") == [
        "tools/randomizer/live/x.py:1 imports numpy"]
    assert violations("import numpy\nprint(numpy)", "cli.py") == ["cli.py:1 imports numpy"]
    assert violations("import numpy", "tools/characters/body.py") == []
    assert violations("import numpy", "tools/randomizer/art/maps.py") == []
    assert violations("import numpy", "tools/randomizer/tracking.py") == ["tools/randomizer/tracking.py:1 imports numpy"]
    found = [v for path in sorted(SRC.rglob("*.py"))
             for v in violations(path.read_text(encoding="utf-8"), path.relative_to(SRC).as_posix())]
    assert found == []


HTML_SINKS = re.compile(r"\b(innerHTML|outerHTML|insertAdjacentHTML|createContextualFragment|parseFromString|srcdoc)\b"
                        r"|\bdocument\s*\.\s*write|javascript:", re.IGNORECASE)
"""What would parse text as HTML or run it as a URL's script in the page (D992's SEC-18)."""


def test_the_page_parses_no_text_as_html():
    """The page writes every text it shows with ``textContent`` and builds
    its nodes with the DOM's own calls: no file under ``web/`` (its
    modules, scripts and HTML) holds an HTML sink of :data:`HTML_SINKS`, so
    a name or a line from a manifest, a recipe or a mods file can't become
    markup or script on the site's origin (D992's SEC-18, kept for the
    Data, Tools, Saves and community tabs to come)."""
    for line in ("el.innerHTML = name", "x.insertAdjacentHTML('beforeend', s)", "document.write(s)",
                 "a.href = 'javascript:go()'", "new DOMParser().parseFromString(s, 'text/html')"):
        assert HTML_SINKS.search(line), line
    assert not HTML_SINKS.search("el.textContent = name; el.append(document.createElement('b'))")
    web = ROOT / "web"
    found = [f"{path.relative_to(ROOT).as_posix()}:{k} {m.group(0)}" for path in sorted(web.rglob("*"))
             if path.suffix in (".mjs", ".js", ".html")
             for k, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) for m in HTML_SINKS.finditer(line)]
    assert found == []


OWN_PLATFORM = {"fcntl", "grp", "posix", "pty", "pwd", "resource", "syslog", "termios", "tty",   # POSIX's
                "msvcrt", "nt", "winreg", "winsound", "_winapi"}                               # Windows'
"""Stdlib modules only one platform has: a module that imports one at its top fails to load on the other."""
TOP_IMPORT = re.compile(r"^(?:import\s+([\w., ]+)|from\s+([\w.]+)\s+import)", re.M)


def test_no_module_imports_one_platforms_own_module_at_its_top():
    """Every Python file of the checkout loads on macOS, Linux and Windows
    (CI tests all three, D1022): one that needs a module of
    :data:`OWN_PLATFORM` imports it in the function that uses it
    (``scripts/fullsuite.py``'s runner locks with ``fcntl``; Windows
    couldn't collect ``tests/test_dev_tools.py`` while the module imported
    it at its top, Step 4.4ci2)."""
    def tops(source: str) -> list[str]:   # an unindented import is a module's own (one in a block is indented)
        return [name for imported, origin in TOP_IMPORT.findall(source)
                for name in (map(str.strip, imported.split(",")) if imported else [origin])
                if name.split()[0].split(".")[0] in OWN_PLATFORM]
    assert tops("import fcntl\nimport os, pwd as p\nfrom msvcrt import getch\ndef f():\n    import termios\n") == [
        "fcntl", "pwd as p", "msvcrt"]
    found = [f"{path.relative_to(ROOT).as_posix()}: {name}" for path in sorted(ROOT.glob("*.py")) + sorted(
             p for d in ("src", "scripts", "tests", "devkit", "shimkit") for p in (ROOT / d).rglob("*.py"))
             for name in tops(path.read_text(encoding="utf-8"))]
    assert found == []


WORKFLOWS = ROOT / ".github" / "workflows"
USES = re.compile(r"^\s*(?:- )?uses:\s*(.*?)\s*$", re.M)
PINNED = re.compile(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}\s+#\s*v\d\S*\Z")
RELEASE_PERMISSIONS = {
    "check": {"contents": "read"}, "apps": {"contents": "read"}, "python": {"contents": "read"},
    "site": {"contents": "read"}, "sums": {}, "attest": {"id-token": "write", "attestations": "write"},
    "draft": {"contents": "write"}, "pypi": {"contents": "read", "attestations": "read", "id-token": "write"},
    "pages": {"pages": "write", "id-token": "write"}}
"""What each job of ``release.yml`` may do, and no more (a new job names its own)."""
DRY_RUN = {"check", "apps", "python", "site", "sums"}
"""The jobs of ``release.yml`` a dispatch runs (D1068's dry run)."""


def _release_jobs() -> dict[str, str]:
    """``release.yml``'s jobs, ``{id: its lines}``, comments left out."""
    text = re.sub(r"(?m)^\s*#.*\n", "", (WORKFLOWS / "release.yml").read_text(encoding="utf-8"))
    parts = re.split(r"(?m)^  ([a-z]+):\n", "\n" + text.split("\njobs:\n")[1])
    return dict(zip(parts[1::2], parts[2::2]))


def test_the_release_workflow_runs_only_on_a_v_tag_its_published_draft_or_a_dispatch_with_every_action_pinned_by_sha():
    """``release.yml`` (D1022, D885): its name and the pypi job's environment
    are what PyPI's pending publisher reads; it starts only on a v* tag, on
    a release's publishing and on a dispatch (D1068's dry run), never on a
    branch's push or a pull request; the first run ends in a draft and only
    the second uploads or deploys; each job holds :data:`RELEASE_PERMISSIONS`
    under an empty top; it reads no secret and no game image. Every action
    of every workflow is pinned by a commit's sha, its release beside it."""
    text = re.sub(r"(?m)^\s*#.*\n", "", (WORKFLOWS / "release.yml").read_text(encoding="utf-8"))
    head, jobs = text.split("\njobs:\n")
    assert head[head.index("on:\n"):head.index("permissions:")].split() == [
        "on:", "push:", "tags:", '["v*"]', "release:", "types:", "[published]", "workflow_dispatch:"]
    assert "permissions: {}" in head
    assert not re.search(r"secrets\.|gamedata|\.iso\b|AZURKIT_ISO|pull_request|workflow_run|branches:|inputs:", text, re.I)
    bodies = _release_jobs()
    assert {name: dict(re.findall(r"^      ([a-z-]+): (read|write)$", body[body.index("permissions:"):], re.M))
            for name, body in bodies.items()} == RELEASE_PERMISSIONS
    assert re.findall(r"(?m)^    environment: (\w+)$", jobs) == ["pypi"] and "environment: pypi" in bodies["pypi"]
    assert "pypa/gh-action-pypi-publish@" in bodies["pypi"] and "actions/deploy-pages@" in bodies["pages"]
    assert "--draft" in bodies["draft"] and "release create" in bodies["draft"]
    unpinned = [f"{path.name}: {use}" for path in sorted(WORKFLOWS.glob("*.yml"))
                for use in USES.findall(path.read_text(encoding="utf-8")) if not PINNED.fullmatch(use)]
    assert unpinned == []


DOWNLOAD = re.compile(r"\bgit clone\b|\bgit -C \S+ (?:-c \S+ )*(?:checkout|fetch)\b|\bplaywright install-deps\b")
"""A workflow's setup downloads with no retry of their own: a clone, a fetch, a partial clone's checkout (which may
fetch its files' blobs) and apt under Playwright's install-deps."""


def test_each_workflow_setup_download_with_no_retry_of_its_own_runs_through_one_bounded_retry_that_fails_by_name():
    """Step 4.4ci46: run 42255487123's Linux job failed when apt under
    ``playwright install-deps`` lost two packages to a mirror that closed the
    connection. In every workflow, a step that runs a :data:`DOWNLOAD`
    sources ``scripts/ci_retry.sh`` first and runs each as ``retry "WHAT"
    COMMAND``, on that line or in a function of the step's that a retry line
    names, whose commands are joined by ``&&`` (bash's -e is off inside it)
    and whose clone first deletes what a failed one left. ``retry`` tries 6
    times (``--tries=N``: N), each wait 30 s longer than the last, 7.5 min of
    waits (Step 4.5t: an outage of GitHub's release downloads lasted minutes),
    then fails the step naming WHAT and the last exit code."""
    helper = (ROOT / "scripts" / "ci_retry.sh").read_text(encoding="utf-8")
    assert "  local tries=6 what try=1 status=0\n  case $1 in --tries=*) tries=${1#--tries=}; shift ;; esac\n" in helper
    assert re.search(r'(?m)^  while \[ "\$try" -le "\$tries" \]; do\n    "\$@" && return 0\n    status=\$\?\n', helper)
    assert "      sleep $((try * 30))\n    fi\n    try=$((try + 1))\n  done\n" in helper
    assert helper.endswith('  echo "::error::$what failed $tries times (exit $status)"\n  return "$status"\n}\n')
    retried = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for step in re.split(r"(?m)^      - ", path.read_text(encoding="utf-8"))[1:]:
            lines = [line.strip() for line in step.splitlines() if not line.strip().startswith("#")]
            if not any(DOWNLOAD.search(line) for line in lines):
                continue
            calls = {m[2]: m[1] for line in lines if (m := re.match(r'retry (?:--tries=\d+ )?"([^"]+)" (\S+)', line))}
            bodies, name = {}, None
            for at, line in enumerate(lines):
                if start := re.match(r"(\w+)\(\) \{", line):
                    name = start[1]
                    bodies[name] = [re.sub(r"\s+#.*", "", line)]   # its comment left out
                elif name:
                    bodies[name].append(line)
                if DOWNLOAD.search(line):
                    where = f"{path.name}: {line}"
                    assert ". scripts/ci_retry.sh" in lines[:at], where
                    assert re.match(r'retry (--tries=\d+ )?"', line) or name in calls, where
                if name and (line == "}" or line.endswith("; }")):
                    name = None
            for function in calls.keys() & bodies.keys():
                body = "\n".join(bodies[function])
                commands = re.split(r"\s+&&\s+", body.split("{", 1)[1].rsplit("}", 1)[0].strip().rstrip(";"))
                assert not any(re.search(r";|\n", command) for command in commands), body
                for command in commands:
                    if "git clone" in command:
                        target = re.search(r' ("[^"]+")$', command)
                        assert target and commands[0] == f"rm -rf {target[1]}", body
            retried += [(path.name, what) for what in calls.values()]
    assert sorted(retried) == [("tests.yml", "Azurik-Custom-Content's clone"),
                               ("tests.yml", "the browsers' system libraries (playwright install-deps)"),
                               ("tests.yml", "the browsers' system libraries (playwright install-deps)"),
                               ("tests.yml", "the game data's $file"),
                               ("tests.yml", "the game data's tree")]


UV_SYNC = 'retry "uv sync" uv sync --locked --no-build'
"""Every workflow's one form of a sync (Step 4.4ci55)."""


def test_every_workflows_uv_sync_builds_nothing_and_runs_through_the_bounded_retry_before_any_uv_run():
    """Step 4.4ci55: run 42335356378's Intel job lost its ``uv sync`` to a
    request uv's own 3 retries gave up on after 48.8 s. Each workflow's
    every sync is :data:`UV_SYNC` (no ``uv sync`` in any other form), in a
    step that sources ``scripts/ci_retry.sh`` first, so it tries 6 times
    and fails by name; ``--no-build`` runs no package's own code and fails
    a package with no wheel by name. In each job a ``uv run`` (which syncs
    what isn't) comes only after that job's sync; a ``uv run --no-project``
    (Step 4.4dx5's matrix job: the standard library alone) syncs nothing."""
    synced = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = re.sub(r"(?m)^\s*#.*\n", "", path.read_text(encoding="utf-8"))
        jobs = re.split(r"(?m)^  [\w-]+:\n", text.split("\njobs:\n", 1)[1])[1:]
        for job in jobs:
            code = [line.strip() for line in job.splitlines() if not re.match(r"\s*(- )?name:", line)]
            syncs = [at for at, line in enumerate(code) if "uv sync" in line]
            assert [code[at] for at in syncs] == [UV_SYNC] * len(syncs), path.name
            assert all(code[at - 1] == ". scripts/ci_retry.sh" for at in syncs), path.name
            runs = [at for at, line in enumerate(code) if "uv run" in line and "uv run --no-project" not in line]
            assert not runs or (syncs and syncs[0] < runs[0]), f"{path.name}: {code[runs[0]]}"
            synced[path.name] = synced.get(path.name, 0) + len(syncs)
    assert synced == {"apps.yml": 1, "checks.yml": 2, "release.yml": 3, "tests.yml": 2}


WEB_CACHE = """          key: ${{ steps.web-tools.outputs.key }}
          path: |
            ${{ steps.web-tools.outputs.pyodide }}
            ${{ steps.web-tools.outputs.browsers }}
"""
"""The web tools' cache's key and folders, alike in its restore and its save (``web_tools.cache``)."""


def test_ci_keeps_what_web_tools_fetches_in_a_cache_keyed_by_its_versions_os_and_kept_files_a_missed_restore_emptied(
        monkeypatch):
    """Step 4.5t: run 42467070736's jobs (911040d) failed as GitHub's release
    downloads answered Pyodide's core 504 for minutes. In each ``tests.yml``
    job that runs ``scripts/web_tools.py``, a step before its fetch
    restores :data:`WEB_CACHE` (``actions/cache/restore``), the next removes
    its two folders on a miss alone (a restore cut short in its extraction
    leaves part files, never kept or saved), and the step after the fetch
    saves it on a miss alone, its key and two folders printed into the job's
    outputs by ``web_tools.py --cache`` the step before: Pyodide's folder and
    Playwright's browsers', nothing else, both saved before any step reads a
    secret or the tier's folder (no key or image is on the runner yet); no
    other step of any workflow names a cache action. The key names the exact
    versions (Pyodide's, its packages, the locked playwright's) and the host,
    and moves when what is kept does (a file of Pyodide's, an engine's name
    or its install, as Chromium's headless shell alone) with no version moved."""
    from importlib.metadata import version
    import platform

    from scripts import web_tools
    text = (WORKFLOWS / "tests.yml").read_text(encoding="utf-8")
    jobs = re.split(r"(?m)^  ([\w-]+):\n", text.split("\njobs:\n", 1)[1])
    cached = []
    for name, job in zip(jobs[1::2], jobs[2::2]):
        steps = re.split(r"(?m)^      - ", job)[1:]
        fetches = [at for at, step in enumerate(steps)
                   if "        run: uv run --locked python scripts/web_tools.py\n" in step]
        if not fetches:
            continue
        [at] = fetches
        key, restore, empty, save = steps[at - 3], steps[at - 2], steps[at - 1], steps[at + 1]
        assert "id: web-tools\n" in key and \
            'run: uv run --locked python scripts/web_tools.py --cache >> "$GITHUB_OUTPUT"\n' in key, name
        assert "id: web-cache\n" in restore and "uses: actions/cache/restore@" in restore, name
        assert "if: steps.web-cache.outputs.cache-hit != 'true'\n" in save and "uses: actions/cache/save@" in save, name
        assert empty.endswith("        if: steps.web-cache.outputs.cache-hit != 'true'\n        env:\n"
                              "          PYODIDE: ${{ steps.web-tools.outputs.pyodide }}\n"
                              "          BROWSERS: ${{ steps.web-tools.outputs.browsers }}\n"
                              '        run: rm -rf "$PYODIDE" "$BROWSERS"\n'), name
        assert restore.endswith(f"with:\n{WEB_CACHE}") and re.sub(r"(?m)^ *#.*\n", "", save).endswith(
            f"with:\n{WEB_CACHE}"), name
        assert not [s for s in steps[:at + 2] if re.search(r"secrets\.|TIER_ROOM|\.iso\b", s)], name
        cached.append(name)
    assert cached == ["pure", "vanilla"]
    caches = [f"{path.name}: {use}" for path in sorted(WORKFLOWS.glob("*.yml"))
              for use in USES.findall(path.read_text(encoding="utf-8")) if use.startswith("actions/cache")]
    assert len(caches) == 4 and all(use.startswith("tests.yml: actions/cache/") for use in caches), caches
    made = web_tools.cache(ROOT)
    assert {(ROOT / made[name]).resolve() for name in ("pyodide", "browsers")} == {
        web_tools.pyodide_dir(ROOT).resolve(), web_tools.browsers_dir(ROOT).resolve()} and set(made) == {
        "key", "pyodide", "browsers"}
    assert {f"pyodide{web_tools.VERSION}", *web_tools.PACKAGES, f"playwright{version('playwright')}",
            platform.machine()} <= set(made["key"].split("-")), made["key"]
    chromium = web_tools.BROWSERS["chromium"]
    for name, value in (("FILES", web_tools.FILES[:-1]), ("install_args", lambda engine: [engine]),
                        ("BROWSERS", web_tools.BROWSERS | {"chromium": ("chromium", chromium[1])})):
        with monkeypatch.context() as patched:
            patched.setattr(web_tools, name, value)
            assert web_tools.cache(ROOT)["key"] != made["key"], name
    assert web_tools.cache(ROOT)["key"] == made["key"]


GITHUB_ED25519 ="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
"""github.com's published ed25519 host key (``GET https://api.github.com/meta``'s ``ssh_keys``), the key
ssh.github.com serves on port 443 too."""


def test_the_game_datas_fetches_go_over_ssh_on_githubs_https_port_to_one_pinned_host_and_a_dead_connection_ends_its_try():
    """Step 4.4ci50: run 42313664434's Intel job lost port 22 to github.com
    for minutes (a connect timed out, a fetch was cut) and its third try sat
    2 h 11 min on a dead connection, so the job ended before any test. Every
    fetch of the game data (the clone, and each file's blob through its
    origin) goes to ``ssh://git@ssh.github.com:443/``, GitHub's documented
    route over its HTTPS port, and no workflow names the port-22 route; the
    one known host is ``[ssh.github.com]:443`` with :data:`GITHUB_ED25519`,
    checked strictly; ssh gives up a connect after 30 s and a connection
    silent 60 s, so ``scripts/ci_retry.sh``'s next try runs; and the vanilla
    job's egress block names ssh.github.com:443 and no port 22."""
    text = (WORKFLOWS / "tests.yml").read_text(encoding="utf-8")
    step = next(s for s in re.split(r"(?m)^      - ", text) if "${{ secrets.GAMEDATA_DEPLOY_KEY }}" in s)
    code = re.sub(r"(?m)^\s*#.*\n", "", step)
    assert re.findall(r"(?:ssh://)?git@[\w.:/-]+", code) == [
        "ssh://git@ssh.github.com:443/Azurik-Modding-Hub/AzurKit-gamedata.git"]
    assert not [path.name for path in WORKFLOWS.glob("*.yml")
                if re.search(r"git@github\.com[:/]", path.read_text(encoding="utf-8"))]
    assert re.findall(r'echo "([^"]*)" (>>?) "\$hosts"', code) == [(f"[ssh.github.com]:443 {GITHUB_ED25519}", ">")]
    ssh = re.search(r'export GIT_SSH_COMMAND="ssh -i \$key ((?:-o \w+=\S+ ?)+)"\n', code)
    assert dict(re.findall(r"-o (\w+)=(\S+)", ssh[1])) == {
        "IdentitiesOnly": "yes", "UserKnownHostsFile": "$hosts", "StrictHostKeyChecking": "yes",
        "ConnectTimeout": "30", "ServerAliveInterval": "15", "ServerAliveCountMax": "4"}
    hosts = re.search(r"allowed-endpoints: >-\n((?: {12}.*\n)+)", text.split("\n  vanilla:\n", 1)[1])[1].split()
    assert "ssh.github.com:443" in hosts and not [host for host in hosts if host.endswith(":22")]


def test_the_game_data_comes_a_file_a_fetch_each_retried_alone_and_its_checkout_after_that_fetch_fetches_nothing():
    """Step 4.5e: runs 42313664434 (Intel) and 42387860921 (Apple Silicon)
    lost the macOS runner's whole network for minutes 2.5 min into the Europe
    folder's one 2.1 GiB fetch (a sparse set's), and each of its 3 tries,
    1.5 min of waits apart, started that fetch over inside the outage. The
    clone holds the commit and its trees, no sparse set is left, and the
    root's three small files, then each file of the release's folder
    (``ls-tree``: a part is 90 MiB), come through ``part``, a retry of its
    own of 6 tries, 7.5 min of waits. Step 4.5h: ``part`` fetches the files'
    blobs in a ``git fetch`` of their own (the command git's lazy fetch runs,
    with no background maintenance left to hold the folder the step deletes)
    and then checks them out with lazy fetching off, since Git for Windows'
    FSCache, on across a checkout's files, served that checkout the object
    folder's listing from before its own lazy fetch, so it never saw the blob
    just fetched (the bdcf682 candidate's two Windows jobs: "unable to read
    sha1 file of .gitattributes", exit 255, all 6 tries)."""
    text = (WORKFLOWS / "tests.yml").read_text(encoding="utf-8")
    step = next(s for s in re.split(r"(?m)^      - ", text) if "${{ secrets.GAMEDATA_DEPLOY_KEY }}" in s)
    code = re.sub(r"(?m)^\s*#.*\n", "", step)
    assert "sparse" not in code
    assert re.findall(r"git clone (.*)", code) == [
        '--quiet --depth 1 --filter=blob:none --no-checkout '
        'ssh://git@ssh.github.com:443/Azurik-Modding-Hub/AzurKit-gamedata.git "$gd" &&']
    assert re.findall(r"(?m)^(.*)\bgit -C (.*) (checkout|fetch)\b(.*)$", code) == [
        ("              ", '"$gd" -c fetch.negotiationAlgorithm=noop', "fetch",
         " --quiet --no-tags --no-write-fetch-head --recurse-submodules=no --filter=blob:none --no-auto-maintenance"
         " origin $blobs &&"),
        ("              GIT_NO_LAZY_FETCH=1 ", '"$gd"', "checkout", ' --quiet HEAD -- "$@"')]
    assert re.search(r'(?m)^ +tree\(\) \{\n +rm -rf "\$gd" &&\n +git clone .*&&\n'
                     r' +part \.gitattributes reassemble\.py manifest\.json\n +\}\n', code)
    assert re.search(r'(?m)^ +part\(\) \{ .*\n +blobs="\$\(git -C "\$gd" rev-parse "\$\{@/#/HEAD:\}"\)" &&\n'
                     r' +git -C "\$gd" -c .* fetch .* origin \$blobs &&\n +GIT_NO_LAZY_FETCH=1 git .*\n +\}\n', code)
    assert re.findall(r"(?m)^ +(retry .*)$", code) == [
        'retry --tries=6 "the game data\'s tree" tree', 'retry --tries=6 "the game data\'s $file" part "$file"']
    loop = re.search(r'(?m)^ +files="\$\(git -C "\$gd" ls-tree -r --name-only HEAD -- "\$1"\)"\n(?: +.*\n)?'
                     r' +for file in \$files; do\n +retry --tries=6 "the game data\'s \$file" part "\$file"\n', code)
    assert loop


def test_a_dispatched_dry_run_builds_and_checksums_the_release_but_reaches_no_attestation_draft_pypi_or_pages():
    """D1068 (Step 4.4ci8): each job's ``if:`` and ``needs`` read under each
    event that starts ``release.yml``. A dispatch on main runs check, the
    four apps, the wheel and sdist, the site and ``SHA256SUMS``, none of
    them holding an id-token or a write, and never attest (Sigstore's
    public log), the draft, pypi or pages; a v* tag's push still runs
    everything to the draft, and the published draft's run check, the site,
    pypi and pages. No job overrides a skipped need (``always()``)."""
    bodies = _release_jobs()
    assert not re.search(r"always\(\)|failure\(\)|cancelled\(\)", "".join(bodies.values()))
    names = {"github.repository": "'Azurik-Modding-Hub/AzurKit'", "&&": " and ", "||": " or "}

    def runs(event: str, ref: str) -> set[str]:
        went: set[str] = set()
        for name, body in bodies.items():   # each job after those it needs
            when = re.search(r"(?m)^    if: (?:>-\n((?:      .*\n)+)|(.*)\n)", body)
            rule = " ".join("".join(when.groups(default="")).split()) if when else "True"
            for word, value in names.items() | {"github.event_name": repr(event), "github.ref": repr(ref)}.items():
                rule = rule.replace(word, value)
            need = re.search(r"(?m)^    needs: \[?([\w, ]+)\]?$", body)
            if eval(rule, {"__builtins__": {}, "startsWith": str.startswith}) and all(
                    n.strip() in went for n in (need[1].split(",") if need else ())):
                went.add(name)
        return went

    dry = runs("workflow_dispatch", "refs/heads/main")
    assert dry == DRY_RUN
    assert all(how == "read" for name in dry for how in RELEASE_PERMISSIONS[name].values())
    assert runs("push", "refs/tags/v0.9.0") == dry | {"attest", "draft"}
    assert runs("release", "refs/tags/v0.9.0") == {"check", "site", "pypi", "pages"}


def test_each_release_job_starts_behind_harden_runner_the_dry_runs_blocking_all_but_their_hosts_the_rest_auditing():
    """Step 4.4ci9: every job of ``release.yml`` starts with harden-runner,
    pinned as ``tests.yml``'s. The jobs a dry run reaches (:data:`DRY_RUN`)
    block every host but those they name; attest, draft, pypi and pages,
    which no dry run reaches, only audit, so a host no run has seen can't
    fail the first tag's run (their insights name the hosts for a block)."""
    pin = re.search(r"uses: (step-security/harden-runner@.*)", (WORKFLOWS / "tests.yml").read_text(encoding="utf-8"))[1]
    first = {name: body.split("    steps:\n", 1)[1].split("\n      - ", 1)[0] for name, body in _release_jobs().items()}
    assert {name: f"uses: {pin}\n" in step for name, step in first.items()} == dict.fromkeys(first, True)
    policy = {name: re.search(r"egress-policy: (\w+)", step)[1] for name, step in first.items()}
    assert policy == {name: "block" if name in DRY_RUN else "audit" for name in first}
    hosts = {name: re.findall(r"(?m)^ {12}(.*)$", step) for name, step in first.items()}
    assert all(re.fullmatch(r"[a-z0-9.-]+:\d+", host) for name in DRY_RUN for line in hosts[name] for host in line.split())
    assert [name for name in first if bool(hosts[name]) != (name in DRY_RUN)] == []


UV_RUNNERS = {"aarch64-apple-darwin": "tar.gz", "x86_64-apple-darwin": "tar.gz", "x86_64-pc-windows-msvc": "zip",
              "x86_64-unknown-linux-gnu": "tar.gz"}
"""uv's artifact for each runner the workflows run on, and its archive's format."""


def test_every_setup_uv_step_reads_its_manifest_inline_the_record_of_the_uv_it_installs_alike_in_every_workflow():
    """Step 4.4ci43: setup-uv v10.3.3 reads uv's manifest from
    releases.astral.sh in at most 5 s, its body too, and retries only a
    request that got no headers, so one slow answer failed a job (run
    42236495854's Intel job). Every setup-uv step of every workflow names
    ``manifest-file: ${{ env.SETUP_UV_MANIFEST }}``, a ``data:`` URL in the
    workflow's env that setup-uv reads without a request: one record, the
    version every step installs, an artifact for each runner from uv's own
    GitHub release with its sha256, and no ``#`` or ``%`` (a URL's fragment
    or escape would change it); the same record in every workflow."""
    manifests = set()
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        steps = [step for step in re.split(r"(?m)^(?=      - )", text)
                 if re.search(r"(?m)^ +(?:- )?uses: astral-sh/setup-uv@", step)]
        assert len(steps) == text.count("uses: astral-sh/setup-uv@"), path.name
        if not steps:
            continue
        named = r"(?m)^          manifest-file: \$\{\{ env\.SETUP_UV_MANIFEST \}\}$"
        assert all(re.search(named, step) for step in steps), path.name
        versions = {re.search(r'(?m)^          version: "([^"]+)"$', step)[1] for step in steps}
        block = re.search(r"(?m)^env:\n(?:  .*\n)*?  SETUP_UV_MANIFEST: >-\n((?:    .*\n)+)", text)
        manifest = " ".join(line.strip() for line in block[1].splitlines())   # YAML's folding
        assert manifest.startswith("data:application/x-ndjson,") and not set("#%") & set(manifest), path.name
        record = json.loads(manifest.split(",", 1)[1])
        assert {record["version"]} == versions, path.name
        version = record["version"]
        assert {a["platform"]: a["url"] for a in record["artifacts"]} == {
            platform: f"https://github.com/astral-sh/uv/releases/download/{version}/uv-{platform}.{form}"
            for platform, form in UV_RUNNERS.items()}, path.name
        assert all(a["archive_format"] == UV_RUNNERS[a["platform"]] and re.fullmatch(r"[0-9a-f]{64}", a["sha256"])
                   for a in record["artifacts"]), path.name
        manifests.add(manifest)
    assert len(manifests) == 1


def test_a_lane_branch_named_for_a_runner_runs_its_rows_and_linuxs_pure_tier_and_every_other_push_runs_every_row(
        monkeypatch, tmp_path, capsys):
    """Step 4.4dx9 (D1123's scope): two lanes' runs sat their 7 macOS jobs each on main's 5 slots, and one waited
    44-121 min. ``tests.yml``'s first job (``scripts/ci_matrix.py``, run here as CI runs it, its ``$GITHUB_OUTPUT``
    read back) gives a lane branch whose name ends in ``-arm64``, ``-intel``, ``-windows`` or ``-linux`` that runner's
    rows of main's (a macOS runner's pure tier in its part 1) and Linux's pure tier, nothing else; main, a lane branch
    named otherwise, a pull request and a fork's push run what they ran before, so main runs everything."""
    from scripts import ci_matrix

    def rows(event: str, ref: str, repository: str = ci_matrix.REPOSITORY) -> dict[str, list[dict]]:
        out = tmp_path / f"output{len(list(tmp_path.iterdir()))}"
        for name, value in (("GITHUB_EVENT_NAME", event), ("GITHUB_REPOSITORY", repository), ("GITHUB_REF", ref),
                            ("GITHUB_OUTPUT", str(out))):
            monkeypatch.setenv(name, value)
        assert ci_matrix.main() == 0 and capsys.readouterr().out.startswith("pure: ")
        return {kind: json.loads(got) for kind, got in re.findall(r"(?m)^(pure|vanilla)=(.*)$", out.read_text())}

    every, pull = rows("push", "refs/heads/main"), rows("pull_request", "refs/pull/9/merge")
    assert {row["label"] for row in every["vanilla"]} == set(ci_matrix.RUNNERS) and not pull["vanilla"]
    for branch, label in (("p2/4.4ci47-webkit-arm64", "macos-arm64"), ("p2/4.4ci48-memory-intel", "macos-x86_64"),
                          ("p2/4.4dx9-lanes-windows", "windows-x86_64"), ("p2/4.4dx9-lanes-linux", "linux-x86_64"),
                          ("p2/4.4x-macos-arm64", "macos-arm64")):
        got = rows("push", f"refs/heads/{branch}")
        assert got == {"pure": [row for row in every["pure"] if row["label"] in (label, "linux-x86_64")],
                       "vanilla": [row for row in every["vanilla"] if row["label"] == label]}, branch
        tiers = [row["label"] for row in got["pure"]] + [row["label"] for row in got["vanilla"] if "pure" in row]
        assert sorted(tiers) == sorted({label, "linux-x86_64"}), (branch, tiers)
    for branch in ("p2/4.4dx5-mac-slots", "p2/4.4ci47-arm64-crash", "p2/4.4x-ARM64", "p2/arm64", "p2/4.4x-arm64x"):
        assert rows("push", f"refs/heads/{branch}") == every, branch
    assert rows("push", "refs/heads/p2/4.4x-arm64", "someone/AzurKit") == pull


PROXY_TOOLS_MODULE = "d1539d95e1a713c068ca81d42e047b2c76568964cf277596d4e19efb22f476be"
"""The sha256 of ``proxy_tools/__init__.py`` in proxy-tools 0.1.0's sdist on PyPI (``proxy_tools-0.1.0.tar.gz``,
sha256 ``ccb3751f529c…``), its one release."""


def test_every_locked_package_but_the_project_has_a_wheel_and_proxy_tools_is_the_one_its_sdist_builds():
    """Step 4.4ci55: proxy-tools, pywebview's, has only an sdist, so every
    ``uv sync --locked`` built it, asking PyPI's index for setuptools, the
    one index ask a locked sync made: run 42335356378's Intel job failed on
    it before any test. Each package ``uv.lock`` pins but the project has a
    wheel, and proxy-tools' is ``vendor/``'s, the one file there, at the
    lock's sha256: its sdist's module unchanged, its METADATA's licence MIT."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))["package"]
    assert [p["name"] for p in lock if not p.get("wheels")] == ["azurkit"]
    vendored = [p for p in lock if "path" in p["source"]]
    assert [(p["name"], p["source"]["path"]) for p in vendored] == [
        ("proxy-tools", "vendor/proxy_tools-0.1.0-py3-none-any.whl")]
    wheel = ROOT / vendored[0]["source"]["path"]
    assert [path.name for path in wheel.parent.iterdir()] == [wheel.name]
    assert [w["hash"] for w in vendored[0]["wheels"]] == [f"sha256:{hashlib.sha256(wheel.read_bytes()).hexdigest()}"]
    with zipfile.ZipFile(wheel) as zf:
        meta = "proxy_tools-0.1.0.dist-info/"
        assert sorted(zf.namelist()) == [*(f"{meta}{name}" for name in ("METADATA", "RECORD", "WHEEL", "top_level.txt")),
                                         "proxy_tools/__init__.py"]
        assert hashlib.sha256(zf.read("proxy_tools/__init__.py")).hexdigest() == PROXY_TOOLS_MODULE
        assert "\nLicense: MIT\n" in zf.read(f"{meta}METADATA").decode()
