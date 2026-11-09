"""is this machine ready to build, test and develop AzurKit? one line a check (a command of its own)

``python -m devkit doctor [--uninstall-hints]``: Modkit's ``azurik-mod
doctor``, ported in Step 4.24a, its checks pointed at AzurKit's own tools.
Each check prints one line, ``ok`` or ``FAIL`` (an optional tool is ``ok``
either way, saying it is optional): Python 3.14, uv and ``uv.lock`` in sync,
each release's image through the resolver and the whole gate (a stamp of an
earlier pass isn't trusted), the pinned zig compiling a probe to the pinned
pentium3 code, the MCP server's import, FastL3's libunicorn, the web tests'
Node, Pyodide and browsers, Blender, ffmpeg, the xemu oracle's fork build,
and the RE tools in ``.tools`` (their ``.ok`` stamps against
``devkit/re/tools.toml``, the Ghidra endpoint, the project's lock). Then the
free disk's line (``ok``, or ``warn`` under :data:`MIN_FREE_DISK`), the
leak-guard hook's (``ok`` or ``warn``) and a ``warn`` for a checkout in a
cloud-synced folder; exit 1 when a check fails. It reads only: it writes no
file but zig's probe in a temporary folder of its own, never a hook or git
config. ``--uninstall-hints`` lists every place outside the checkout that
AzurKit, its setup or its tools may write. The area's reference is
``devkit/doctor/README.md``."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import importlib.metadata
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The Xbox's CPU is a Pentium III: SSE but no SSE2. Built as shimkit builds a shim (its FLAGS, -mcpu=pentium3), this
# double multiply-add is x87 code; a pentium4 build would emit SSE2 and hash otherwise. Only .text is hashed. Modkit's
# doctor pinned the same code for the same zig (ziglang 0.16.0) and flags.
PROBE_C = "double probe(double a, double b) { return a * b + 1.0; }\n"
PROBE_TEXT_SHA256 = "d7d1eec8cc5f931f0d2deaefbcfd2ce476a0f006e4492f9b0ea267943051fa49"
# Below this much free where builds, test runs and xemu sittings write, one may run out of room: a build is 2.6 GB,
# a test run about 2 GiB and a sitting 10-27 GiB.
MIN_FREE_DISK = 50 * 2**30


def run(root: Path = ROOT) -> int:
    """Print one line a check for the checkout at ``root``; 1 if a check
    failed, else 0."""
    from azurkit.core import gate

    checks = [("Python 3.14", _python), ("uv", _uv_version), ("uv.lock in sync", lambda: _lock(root)),
              *((f"{r.label} image", lambda r=r: _image(r)) for r in gate.RELEASES),
              ("zig", _zig), ("mcp", _mcp), ("libunicorn", _unicorn), ("web tools", lambda: _web(root)),
              ("Blender", _blender), ("ffmpeg", _ffmpeg), ("xemu", _xemu), ("RE tools", lambda: _tools(root))]
    if (_tools_dir(root) / "ghidra").is_dir():
        checks += [("Ghidra endpoint", _ghidra), ("Ghidra project", _ghidra_project)]
    failed = 0
    for name, check in checks:
        try:
            print(f"ok    {name}: {check()}")
        except Exception as exc:  # a doctor reports every failure; it never stops at the first
            failed += 1
            print(f"FAIL  {name}: {exc}")
    print(_disk_line())
    print(_hook_line(root))
    for warning in _sync_root(root):
        print(f"warn  {warning}")
    if failed:
        print(f"doctor: {failed} check(s) failed")
    return 1 if failed else 0


def uninstall_hints() -> list[str]:
    """Every place outside the checkout that AzurKit, its setup or its tools
    may write, each with what writes it and how to remove it; a folder two
    share is listed once, with each."""
    from platformdirs import user_cache_dir, user_config_dir, user_data_dir, user_log_dir

    uv = _uv()

    def uv_out(*args: str) -> str:
        return _check_output([uv, *args]) if uv else "(uv not found)"
    data, cache = user_data_dir("AzurKit", appauthor=False), user_cache_dir("AzurKit", appauthor=False)
    hints = [
        f"{uv_out('cache', 'dir')}  uv's package cache, shared with other uv projects: `uv cache clean`",
        f"{uv_out('python', 'dir')}  uv-managed Pythons: `uv python uninstall 3.14`",
        f"{uv or 'uv'}  uv itself, and any `uv self update` (`uv self update <old version>` reverts one)",
        f"{cache}  the app's kept image checks and dresses (at most about 5 GB), the randomizer database's cache, "
        "Blender jobs' bodies, the reach engine's and FastL3's caches and libunicorn builds, the derive's kept "
        "flights, xemu's shader and sha256 caches and the Ghidra serves' copies: delete the folder",
        f"{data}  a usa.iso or europe.iso you placed there, or links to a checkout's images",
        f"{data}  your variants (variants/, or $AZURKIT_VARIANTS): copy out any you want to keep",
        f"{data}  installed community content (content/) and the cache's key (cache.key)",
        f"{data}  the guest RAM snapshots (l3-snapshots/), the reach engine's truth set (reach-truth/) and the link "
        "to the xemu oracle's fixtures (xemu-fixtures): never the fixtures themselves",
        f"{user_config_dir('AzurKit', appauthor=False)}  the app's settings (app.json): your setup, theme and "
        "tracker marks",
        f"{user_log_dir('AzurKit', appauthor=False)}  the app's build logs",
        f"{Path(tempfile.gettempdir()) / f'{getpass.getuser()}-ghidra'}  Ghidra's temp folder, if you run Ghidra",
        f"{Path.home() / '.claude.json'}  the local-scope `ghidra` MCP entry, if you added it: "
        "`claude mcp remove --scope local ghidra`",
    ]
    if sys.platform == "darwin":
        hints.append(f"{Path.home() / 'Library' / 'WebKit' / 'org.webkit.Playwright'}  the site's build files "
                     "Playwright's WebKit keeps for the web tests: delete the folder")
    by_folder: dict[str, list[str]] = {}
    for hint in hints:
        folder, what = hint.split("  ", 1)
        by_folder.setdefault(folder, []).append(what)
    return [f"{folder}  {'; '.join(whats)}" for folder, whats in by_folder.items()]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m devkit doctor",
                                 description="Check that this machine is ready to build, test and develop AzurKit: "
                                             "one line a check, exit 1 when one fails.")
    ap.add_argument("--uninstall-hints", action="store_true",
                    help="list every place outside the checkout AzurKit, its setup or its tools may write")
    args = ap.parse_args(argv)
    if args.uninstall_hints:
        print("Deleting the checkout removes .venv and .tools/ (the main checkout's: Pyodide, the browsers, Ghidra). "
              "Outside it:")
        print("\n".join(uninstall_hints()))
        return 0
    return run()


def _python() -> str:
    where = f"{sys.version.split()[0]} at {sys.executable}"
    if sys.version_info[:2] != (3, 14):
        raise RuntimeError(f"{where}; AzurKit runs on Python 3.14 only: use `uv run --locked`")
    return where


def _uv() -> str | None:
    return os.environ.get("UV") or shutil.which("uv")


def _uv_version() -> str:
    if not (uv := _uv()):
        raise RuntimeError("uv not found on PATH: https://docs.astral.sh/uv/")
    return f"{_check_output([uv, '--version'])} at {uv}"


def _lock(root: Path) -> str:
    """A stale lock first (``uv sync --locked`` can't fix that), then the
    environment against the lock (``--inexact``: what ``uv run --group re``
    adds isn't drift)."""
    if not (uv := _uv()):
        raise RuntimeError("uv not found on PATH")
    if subprocess.run([uv, "lock", "--check"], cwd=root, capture_output=True, timeout=120).returncode:
        raise RuntimeError("uv.lock is missing or stale for pyproject.toml (`uv lock` updates it)")
    done = subprocess.run([uv, "sync", "--locked", "--check", "--inexact"], cwd=root, capture_output=True, text=True,
                          timeout=120)
    if done.returncode:
        raise RuntimeError(f"{_last_line(done.stderr)} (`uv sync --locked` fixes it)")
    return "uv.lock matches pyproject.toml and the environment"


def _image(release) -> str:
    """``release``'s image through the resolver and the whole gate, every
    file read (the suite needs both, D26)."""
    from azurkit.core import gate

    if (found := gate.find(release)) is None:
        raise RuntimeError(gate.missing(release))
    gate.verify(found, releases=(release,))
    return f"{found}: the vanilla {release.label} image, every file as its manifest has it"


def _zig() -> str:
    """The pinned zig, and the probe built as shimkit builds a shim, in a
    temporary folder (zig's cache too)."""
    import shimkit
    from azurkit.core import coff

    version = _check_output([str(shimkit.zig()), "version"])
    with tempfile.TemporaryDirectory(prefix="azurkit-doctor-") as tmp:
        source = Path(tmp, "probe.c")
        source.write_text(PROBE_C, encoding="utf-8")
        text = next(s for s in coff.parse(shimkit.compile(source)).sections if s.name == ".text")
    if (digest := hashlib.sha256(text.data).hexdigest()) != PROBE_TEXT_SHA256:
        raise RuntimeError(f"zig {version}: the pentium3 probe's .text hashes to {digest[:12]}, "
                           f"not {PROBE_TEXT_SHA256[:12]}")
    return f"zig {version}; the pentium3 probe compiles to the pinned code"


def _mcp() -> str:
    import devkit.mcp.serve  # noqa: F401  (the azurik MCP server's import: the mcp package's API it uses)
    return f"mcp {importlib.metadata.version('mcp')}; the azurik MCP server imports"


def _unicorn() -> str:
    """The libunicorn the reach engine's FastL3 workers load: the patched
    build with its switches once ``python -m devkit reach build-unicorn``
    made it, else the wheel's."""
    from devkit.reach import l3_fast

    got = l3_fast.probe()
    if not got["switches"]:
        return (f"the stock wheel's, sha12 {got['sha12']} (optional: `python -m devkit reach build-unicorn` builds "
                "FastL3's)")
    if Path(got["lib"]).resolve() != (l3_fast.library() / l3_fast.LIB_NAME).resolve():
        raise RuntimeError(f"a FastL3 worker would load {got['lib']}, not the patched build: "
                           "`python -m devkit reach build-unicorn` builds it again")
    return f"patched {got['lib']}, sha12 {got['sha12']} ({' '.join(f'{k}={v}' for k, v in got['switches'].items())})"


def _web(root: Path) -> str:
    """What the web tier needs (``scripts/web_tools.py``): Node on PATH,
    Pyodide's pinned core and wheels, and each browser, in the main checkout's
    ``.tools``."""
    from scripts import web_tools

    lost = [] if shutil.which("node") else ["node (not on PATH)"]
    if missing := web_tools.missing(root):
        lost.append(f"Pyodide {web_tools.VERSION} ({', '.join(missing[:3])})")
    lost += [label for engine, (_, label) in web_tools.BROWSERS.items() if web_tools.browser_missing(engine, root)]
    if lost:
        raise RuntimeError(f"missing: {'; '.join(lost)} (`uv run bootstrap.py` in the main checkout fetches them)")
    return f"Node, Pyodide {web_tools.VERSION} and {', '.join(label for _, label in web_tools.BROWSERS.values())}"


def _blender() -> str:
    from devkit.models.preview import find_blender

    try:
        return str(find_blender())
    except ValueError:
        return "not found (optional: the model verbs' renders and the glTF round trip use it; $AZURIK_BLENDER)"


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "not on PATH (optional: `movies frames` and the model MP4s use it)"


def _xemu() -> str:
    from devkit.xemu.oracle import FIXTURES, FORK_APP

    if FORK_APP.is_dir():
        return f"the fork build {FORK_APP.name} in the oracle's fixtures ({FIXTURES})"
    return (f"no fork build at {FORK_APP} (optional: the xemu oracle's fixtures, $AZURIK_XEMU_FIXTURES; "
            "devkit/xemu/README.md)")


def _tools_dir(root: Path) -> Path:
    """The ``.tools`` the RE verbs run (``ghidra_serve.tools_dir``: this
    checkout's once filled, else the main checkout's); another ``root``'s own."""
    from devkit.re import ghidra_serve

    return ghidra_serve.tools_dir() if root == ROOT else root / ".tools"


def _tools(root: Path) -> str:
    """Once any is installed: each ``.tools/<name>/.ok`` stamp must read
    ``"<version> <sha256>"`` of the host's ``devkit/re/tools.toml`` asset, and
    no extension ``bootstrap.py --with re`` unzipped into ``.tools/ghidra``
    may also sit in its settings folder (an "Install Extensions" copy):
    Ghidra doesn't start with a module twice."""
    import bootstrap

    tools = tomllib.loads((root / "devkit" / "re" / "tools.toml").read_text(encoding="utf-8"))["tools"]
    dot = _tools_dir(root)
    if not any((dot / name).exists() for name in tools):
        return "not installed (optional: `uv run bootstrap.py --with re` in the main checkout)"
    host = bootstrap.host_platform()
    stale = []
    for name, tool in tools.items():
        asset = tool["assets"].get(host) or tool["assets"].get("any")
        stamp = dot / name / ".ok"
        have = stamp.read_text(encoding="utf-8").strip() if stamp.is_file() else None
        if asset is None or have != f"{tool['version']} {asset['sha256']}":
            stale.append(name)
    twice = [p for p in sorted((dot / "ghidra-home").glob("*/*/Extensions/*"))
             if (dot / "ghidra" / "Ghidra" / "Extensions" / p.name).exists()]
    problems = ([f"{', '.join(stale)}: .ok stamp missing or not the {host} version and sha256 in tools.toml "
                 "(`uv run bootstrap.py --with re` fixes it)"] if stale else []) + [
        f"{p.relative_to(dot).as_posix()} duplicates .tools/ghidra's {p.name}: delete it" for p in twice]
    if problems:
        raise RuntimeError("; ".join(problems))
    return f"{len(tools)} .ok stamps match tools.toml in {dot}"


def _ghidra() -> str:
    """The endpoint the Ghidra verbs use. Ghidra needn't be running, busy or
    have a program open; only something that doesn't speak JSON there fails."""
    from devkit.re.ghidra_client import GhidraClient, GhidraClientError

    client = GhidraClient(timeout=2)
    try:
        program = client.program_info().name
    except GhidraClientError as exc:
        if exc.code == "CONNECTION_ERROR":
            return f"nothing on {client.base_url} (optional: `python -m devkit re ghidra-serve start`)"
        if exc.code == "NON_JSON_RESPONSE":
            raise RuntimeError(f"{client.base_url} answers, but not as Ghidra: {exc}") from exc
        return f"{client.base_url} serves no program yet (busy, or none open): {exc}"
    return f"{client.base_url} serves {program}"


def _ghidra_project() -> str:
    """Whether a Ghidra holds the project ``ghidra-serve`` last copied (the
    passive lock probe: ``ghidra-apply`` writes only a closed project)."""
    from devkit.re.ghidra_project import lock_state
    from devkit.re.ghidra_serve import remembered_project

    if (gpr := remembered_project()) is None:
        return "none known yet (`python -m devkit re ghidra-serve start --project <name>.gpr` remembers it)"
    lock = lock_state(gpr)
    state = {"held": f"open in pid {lock.pid}" if lock.pid else "open in a Ghidra",
             "stale": "closed (stale lock files)",
             "unknown": "unknown (Windows has no passive lock probe)"}.get(lock.state, "closed")
    return f"{state}: {gpr}"


def _disk_line(path: str | None = None) -> str:
    """The disk free on the volume of ``path`` (the temp folder: builds, test
    runs and xemu sittings write there): ``ok``, or ``warn`` below
    :data:`MIN_FREE_DISK`."""
    path = path or tempfile.gettempdir()
    free = shutil.disk_usage(path).free
    if free < MIN_FREE_DISK:
        return (f"warn  disk: {free / 2**30:.1f} GiB free on {path}'s volume, under {MIN_FREE_DISK // 2**30} GiB: "
                "a build, a test run or an xemu sitting may run out of room")
    return f"ok    disk: {free / 2**30:.0f} GiB free on {path}'s volume"


def _hook_line(root: Path) -> str:
    """Whether git runs the leak guard on a push from ``root``: the
    ``pre-push`` git runs is the hook ``uv run bootstrap.py`` writes (its
    mark line, ``bootstrap.HOOK``'s up to its id, so an older text of it
    counts, said), wherever ``core.hooksPath`` puts it, or hands each push
    over to that hook in the repository's own hooks folder (it names the
    mark's header, as an agent's ``~/.git-hooks/pre-push`` does). Reads only;
    it never writes a hook or git config."""
    import bootstrap

    line = next(line for line in bootstrap.HOOK.splitlines() if "leak-guard pre-push hook" in line)
    mark = line[:line.index("(AzurKit") + len("(AzurKit")]
    header = mark.lstrip("# ").split(" (")[0]

    def older(hook: Path) -> str:
        return ("" if hook.read_text(encoding="utf-8", errors="replace") == bootstrap.HOOK
                else " (an older text than bootstrap.py's: `uv run bootstrap.py` writes it again)")

    def git(*args: str) -> str:
        try:
            return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30).stdout
        except (OSError, subprocess.SubprocessError):  # no git: a doctor never stops
            return ""

    def holds(hook: Path, text: str) -> bool:
        return (hook.is_file() and os.access(hook, os.X_OK)
                and text in hook.read_text(encoding="utf-8", errors="replace"))
    paths = git("rev-parse", "--path-format=absolute", "--git-path", "hooks/pre-push", "--git-common-dir")
    if len(paths.splitlines()) != 2:
        return f"warn  leak-guard hook: not hooked: git reads no hooks folder for {root}"
    hook, common = (Path(line).resolve() for line in paths.splitlines())
    own = (common / "hooks" / "pre-push").resolve()
    if holds(hook, mark):
        return f"ok    leak-guard hook: {hook} runs the leak guard on each push{older(hook)}"
    why = "someone else's hook" if own.exists() else "missing (`uv run bootstrap.py` writes it)"
    if hook == own:
        return f"warn  leak-guard hook: not hooked: {own} is {why}"
    setting = git("config", "--show-scope", "--show-origin", "--get", "core.hooksPath").strip()
    scope, origin, value = setting.split("\t", 2) if setting.count("\t") == 2 else ("unset", "-", "-")
    where = f"core.hooksPath = {value} ({scope} setting, {origin})"
    if not holds(hook, header):
        return (f"warn  leak-guard hook: not hooked: {where} makes git run {hook}, which doesn't hand a push over to "
                f"the leak guard at {own}")
    if holds(own, mark):
        return f"ok    leak-guard hook: {where}; its pre-push hands each push to {own}, the leak guard{older(own)}"
    return f"warn  leak-guard hook: not hooked: {where}; its pre-push hands each push to {own}, which is {why}"


def _sync_root(root: Path) -> list[str]:
    """Cloud sync would upload .venv, .tools/ and the builds a checkout holds."""
    real = root.resolve()
    synced = any(p in ("Mobile Documents", "CloudStorage") or p.startswith("OneDrive") for p in real.parts)
    if not synced and sys.platform == "darwin":  # iCloud's "Desktop & Documents Folders"
        for folder, key in (("Documents", "FXICloudDriveDocuments"), ("Desktop", "FXICloudDriveDesktop")):
            if real.is_relative_to(Path.home() / folder):
                done = subprocess.run(["defaults", "read", "com.apple.finder", key], capture_output=True, text=True,
                                      timeout=10)
                synced = done.stdout.strip() == "1"
    return [f"sync root: {real} is in a cloud-synced folder; move the checkout out of it"] if synced else []


def _check_output(cmd: list[str]) -> str:
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if done.returncode:
        raise RuntimeError(_last_line(done.stderr))
    return done.stdout.strip()


def _last_line(text: str) -> str:
    return (text.strip().splitlines() or ["failed with no output"])[-1]
