"""``python -m devkit re ghidra-serve start|status|stop``: a read-only
COPY of a Ghidra project, served headlessly over the stock GhydraMCP HTTP
API, so agents get decompiles, xrefs and the ``ghidra-*`` verbs with no
owner action (Modkit's Step 2.13c, ported in Step 4.11d2). Stdlib only but
``platformdirs``.

- **Never the owner's project.** :func:`start` copies the ``.gpr`` and
  ``.rep`` (reading them only) into ``<state>/<port>/project/`` as
  ``AzurikServe``, so ``GET /program`` names ``AzurikServe:/default.xbe``.
  The copy is reused while the project and the copy both match its stamp.
  It may be made while the owner's GUI holds the project (Q202): the
  project's fingerprint before and after the copy must match (one retry).
- **Read-only.** ``AzurikServe.java`` marks the program temporary, so no
  save route can persist anything (AZ-193); HTTP writes stay in memory
  (``status`` says dirty) and vanish at stop.
- **127.0.0.1 only**, whatever ``launch.properties`` says (CRITIQUE).
- **One serve per port**, by default :data:`SERVE_PORT` (agents' serves
  take 8212-8229; the owner's GUI 8192 and 8193), its state in
  ``ghidra-serve/<port>/`` in the user cache folder (:func:`state_root`;
  copies can be made again), run with the ``.tools`` Ghidra
  (:func:`tools_dir`). Not under ``.tools``: Ghidra refuses a project path
  with a folder whose name starts with ``.``, which also rules out a cache
  folder under a hidden one (Linux's ``~/.cache``: there ``start`` refuses
  by name). A busy port is refused, naming what answers there (Q200: no
  fallback). Refusals write nothing.
- **Detached** in its own process group; :func:`stop` touches the stop
  file, then kills the group. A failed or interrupted start kills it, and
  a failure raises with the log's tail (D35).
- **Known by pid and start time.** ``serve.json`` outlives a serve that
  ends by itself (``--max-seconds``, a crash, a reboot); a process that
  later reuses its pid is never taken for it, nor signalled.
- ``ghidra-snapshot`` refuses a serve that is dirty or stale
  (:func:`unfit_for_snapshot`).
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .ghidra_project import ProjectError, copy_project, fingerprint, lock_state

__all__ = ["COPY", "DEFAULT_MAX_SECONDS", "SCRIPTS", "SERVE_PORT", "ServeError", "ensure_copy",
           "headless_exe", "main", "remembered_project", "start", "state_root", "status", "stop",
           "tools_dir", "unfit_for_snapshot"]

ROOT = Path(__file__).resolve().parents[2]   # the checkout
SCRIPTS = Path(__file__).resolve().parent / "ghidra_scripts"   # AzurikServe.java, ApplyPlan.java, ...
COPY = "AzurikServe"
SERVE_PORT = 8212  # the first of agents' serve ports (8212-8229; Modkit's agents took 8194-8211)
DEFAULT_MAX_SECONDS = 7200  # Q201: a forgotten serve ends after 2 h; 0 = no limit
_HOST = "127.0.0.1"
_CHILDREN: dict[int, subprocess.Popen] = {}  # the serves this process started


class ServeError(RuntimeError):
    """A start, status or stop that can't go ahead; the verb exits 2."""


def _main_checkout() -> Path:
    """The main checkout of the repository this one is a worktree of (or
    this one), asked of git's common directory."""
    try:
        common = Path(subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return ROOT
    return common.parent if common.name == ".git" else ROOT


def tools_dir() -> Path:
    """The ``.tools`` whose Ghidra the serves, ``ghidra-apply`` and the
    tests run: this checkout's own once ``bootstrap.py --with re`` filled it
    (a lane trying a new pin), else the main checkout's, which a lane
    worktree shares, as it shares the web tests' (``scripts/web_tools.py``)."""
    own = ROOT / ".tools"
    return own if (own / "ghidra").is_dir() else _main_checkout() / ".tools"


def headless_exe() -> Path:
    """:func:`tools_dir`'s ``analyzeHeadless``."""
    return tools_dir() / "ghidra" / "support" / ("analyzeHeadless.bat" if os.name == "nt" else "analyzeHeadless")


def state_root() -> Path:
    """The serves' state, ``ghidra-serve/`` in the user cache folder (beside
    ``ghidra-apply/``'s work): copies and Ghidra's settings, never a tracked
    path."""
    from platformdirs import user_cache_path
    return user_cache_path("AzurKit", appauthor=False) / "ghidra-serve"


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def _write_json(path: Path, obj: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def remembered_project(root: Path | None = None) -> Path | None:
    """The ``--project`` the last start used (``<state root>/source.json``,
    in the user cache, so no home path lands in a tracked file)."""
    saved = _read_json((root or state_root()) / "source.json")
    return Path(saved["project"]) if saved else None


def ensure_copy(project: Path, port_dir: Path) -> tuple[Path, str]:
    """The copy's ``.gpr``, and ``reused`` or ``copied (<why>)``. A copy is
    reused only while the project and the copy both match its stamp.
    Otherwise it is made again, and the project's fingerprint before and
    after the copy must match (a GUI save during the copy tears it): one
    retry, then a refusal that keeps the old copy."""
    try:
        now = fingerprint(project)
    except ProjectError as exc:
        raise ServeError(str(exc)) from None
    copy_gpr = port_dir / "project" / f"{COPY}.gpr"
    stamp = _read_json(port_dir / "stamp.json") or {}
    why = "first copy"
    if copy_gpr.is_file() and stamp.get("project") == str(project):
        if stamp.get("fingerprint") != now:
            why = "the project changed"
        else:
            try:
                same = fingerprint(copy_gpr) == now
            except ProjectError:  # torn, e.g. by an interrupted re-copy
                same = False
            if same:
                return copy_gpr, "reused"
            why = "the copy changed"
    new = port_dir / "project.new"
    for _ in range(2):
        shutil.rmtree(new, ignore_errors=True)
        copy_project(project, new, COPY)
        after = fingerprint(project)
        if after == now:
            break
        now = after
    else:
        shutil.rmtree(new, ignore_errors=True)
        raise ServeError(f"{project} changed while it was copied, twice (Ghidra saving?): "
                         "start again once it has saved")
    shutil.rmtree(port_dir / "project", ignore_errors=True)
    os.replace(new, port_dir / "project")
    _write_json(port_dir / "stamp.json", {"project": str(project), "fingerprint": now})
    return copy_gpr, f"copied ({why})"


def _program_at(port: int) -> dict | None:
    """``GET /program``'s result on the port ({} when no program is open),
    or None when no GhydraMCP answers there."""
    try:
        with urllib.request.urlopen(f"http://{_HOST}:{port}/program", timeout=2) as r:
            body = r.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()
    except (OSError, http.client.HTTPException):  # e.g. an SSH banner: BadStatusLine
        return None
    try:
        return json.loads(body).get("result") or {}
    except (ValueError, AttributeError):
        return None


def _listening(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1.0)
        return s.connect_ex((_HOST, port)) == 0


def _identity(pid: int) -> str | None:
    """When the process ``pid`` started, as an opaque string, or None when
    no such process runs: with the pid it names one process, not whichever
    later reuses the number."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        handle, code = wintypes.HANDLE(handle), wintypes.DWORD()
        times = [wintypes.FILETIME() for _ in range(4)]  # creation, exit, kernel, user
        try:
            ok = (kernel32.GetProcessTimes(handle, *map(ctypes.byref, times))
                  and kernel32.GetExitCodeProcess(handle, ctypes.byref(code)))
        finally:
            kernel32.CloseHandle(handle)
        if not ok or code.value != 259:  # STILL_ACTIVE
            return None
        return f"{times[0].dwHighDateTime:08x}{times[0].dwLowDateTime:08x}"
    if os.path.exists("/proc/self/stat"):  # Linux: field 22, clock ticks since boot (procps's
        try:  # lstart adds a boot time that a wall-clock step moves)
            return Path(f"/proc/{pid}/stat").read_bytes().rpartition(b")")[2].split()[19].decode()
        except (OSError, IndexError):
            return None
    try:  # the same text from any shell: lstart is local time
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True,
                             text=True, env={**os.environ, "LC_ALL": "C", "TZ": "UTC0"}).stdout
    except OSError:
        return None
    return out.strip() or None


def _ours(served: dict) -> bool:
    """Whether the serve ``serve.json`` records still runs: its first
    process, known by pid and start time (a child of this process is
    reaped first)."""
    child = _CHILDREN.get(served["pid"])
    if child is not None and child.poll() is not None:
        return False
    recorded = served.get("identity")
    return recorded is not None and _identity(served["pid"]) == recorded


def _group_alive(pid: int) -> bool:
    """Whether anything of a serve's process group (Windows: its process)
    still runs; only asked once :func:`_ours` said the group is the serve's,
    and while it lives no new process gets its number. A child of this
    process is reaped first, so the group check sees only what is left of
    it (the JVM under ``analyzeHeadless``)."""
    child = _CHILDREN.get(pid)
    if child is not None and child.poll() is None:
        return True
    if os.name == "nt":
        return _identity(pid) is not None
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def _end(pid: int, grace: float) -> str:
    """Give a serve that :func:`_ours` recognised ``grace`` seconds to stop
    by itself, then kill its group; return how it ended."""
    kills = ([("taskkill", None)] if os.name == "nt"
             else [("SIGTERM", signal.SIGTERM), ("SIGKILL", signal.SIGKILL)])
    for how, sig in [("stop file", None)] + kills:
        if how == "taskkill":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
        elif sig is not None:
            try:
                os.killpg(pid, sig)
            except ProcessLookupError:
                pass
            except PermissionError:
                raise ServeError(f"not allowed to signal process group {pid}") from None
        deadline = time.monotonic() + (grace if how == "stop file" else 10.0)
        while _group_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        if not _group_alive(pid):
            _CHILDREN.pop(pid, None)
            return how
    raise ServeError(f"process {pid} survived {kills[-1][0]}")


def _busy(port: int) -> str:
    """What answers on a busy port (Q200: no fallback port)."""
    program = _program_at(port)
    pid = (program or {}).get("programId") or ""
    what, advice = (("something that is not Ghidra", "pass --port N") if program is None
                    else (f"the owner's GUI ({pid})", "use it directly, or pass --port N")
                    if pid.startswith("Azurik Ghidra:")
                    else (f"another serve's copy ({pid})", "use it, or pass --port N")
                    if pid.startswith(f"{COPY}:")
                    else (f"a Ghidra serving {pid or 'no program'}", "pass --port N"))
    return f"port {port} is busy: {what} answers on {_HOST}:{port}; {advice}"


def _refusal(project: Path, port: int, port_dir: Path, max_seconds: int, *,
             ghidra: bool) -> str | None:
    """Why ``start`` must not go ahead; checked before anything is written.
    ``ghidra``: the real analyzeHeadless runs, with its launcher's and
    project paths' limits (a test's fake has neither)."""
    if not 0 < port < 65536:
        return f"--port {port} is not a TCP port"
    if max_seconds < 0:
        return "--max-seconds must be 0 (no limit) or more"
    if port_dir.parent in project.parents:
        return f"{project} is a serve's own copy: pass the real project"
    if project.parent in port_dir.parents:
        return f"the serve's state folder {port_dir} is inside the project's folder"
    if ghidra and any(c.isspace() for c in str(port_dir)):  # launch.sh/.bat word-split options
        return f"the serve's state folder can't contain whitespace: {port_dir}"
    if ghidra and any(part.startswith(".") for part in port_dir.parts):
        return f"Ghidra refuses a project under a folder whose name starts with '.': {port_dir}"
    served = _read_json(port_dir / "serve.json")
    if served and _ours(served):
        return (f"already serving a copy on port {port} (pid {served['pid']}): "
                f"`python -m devkit re ghidra-serve stop --port {port}` first")
    return _busy(port) if _listening(port) else None


def _log_tail(run: Path, lines: int = 40) -> str:
    try:
        text = (run / "stdout.log").read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return "(no log)"
    return "\n".join(text.splitlines()[-lines:])


def start(project: Path, port: int = SERVE_PORT, *, root: Path | None = None,
          headless: list[str] | None = None, program: str = "default.xbe",
          max_seconds: int = DEFAULT_MAX_SECONDS, maxmem: str = "2G",
          timeout: float = 300.0) -> dict:
    """Copy the project if needed, start the serve detached and return its
    record once ``GET /program`` answers. ``headless`` replaces
    ``.tools``' ``analyzeHeadless`` (a test's fake)."""
    root = root or state_root()
    port_dir = root / str(port)
    project = project.expanduser().resolve()
    if why := _refusal(project, port, port_dir, max_seconds, ghidra=headless is None):
        raise ServeError(why)
    if headless is None:
        exe = headless_exe()
        if not exe.is_file():
            raise ServeError(f"no {exe}: run `uv run bootstrap.py --with re` in the main checkout")
        headless = [str(exe)]
    t0 = time.monotonic()
    copy_gpr, copied = ensure_copy(project, port_dir)
    _write_json(root / "source.json", {"project": str(project)})
    run = port_dir / "run"
    shutil.rmtree(run, ignore_errors=True)
    for sub in ("tmp", "home", "settings", "cache"):
        (run / sub).mkdir(parents=True)
    options = [f"-Djava.io.tmpdir={run / 'tmp'}", f"-Duser.home={run / 'home'}",
               f"-Dapplication.settingsdir={run / 'settings'}",
               f"-Dapplication.cachedir={run / 'cache'}",
               f"-Dghidra.user.scripts.dir={run / 'home'}",
               f"-Dghidra.mcp.bind.host={_HOST}", "-Dghidra.mcp.cors.origin=http://127.0.0.1:1"]
    env = {**os.environ, "GHIDRA_HEADLESS_JAVA_OPTIONS": " ".join(options),
           "GHIDRA_HEADLESS_MAXMEM": maxmem, "GHYDRA_BIND_HOST": _HOST}
    argv = [*headless, str(copy_gpr.parent), COPY, "-process", program, "-noanalysis",
            "-readOnly", "-scriptPath", str(SCRIPTS),
            "-postScript", "AzurikServe.java", str(port), str(run / "stop"),
            str(run / "ready.json"), str(max_seconds), "-log", str(run / "headless.log")]
    detach = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
              if os.name == "nt" else {"start_new_session": True})
    proc, served = None, {}
    try:  # a failed or interrupted start (Ctrl-C, a test's timeout) leaves nothing running,
        with open(run / "stdout.log", "wb") as out:
            proc = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=subprocess.STDOUT, **detach)
        served = {"pid": proc.pid, "identity": _identity(proc.pid), "port": port,
                  "program": program, "project": str(project), "copy": copied,
                  "started": time.time(), "max_seconds": max_seconds}
        _write_json(port_dir / "serve.json", served)
        deadline = time.monotonic() + timeout
        probe, gap = 0.0, 0.25  # a port that doesn't answer yet: asked again after 0.25 s, 0.5 s, then each 1 s
        while time.monotonic() < deadline and proc.poll() is None:
            if (run / "ready.json").is_file() and time.monotonic() >= probe:
                if _program_at(port) is not None:
                    served["seconds"] = round(time.monotonic() - t0, 1)
                    _write_json(port_dir / "serve.json", served)
                    return served
                probe, gap = time.monotonic() + gap, min(2 * gap, 1.0)  # AZ-312
            time.sleep(0.25)
        failed = (f"analyzeHeadless exited {proc.returncode} before serving"
                  if proc.poll() is not None
                  else f"port {port} did not answer within {timeout:g} s")
    finally:  # even when the interrupt came as Popen returned, before `served` was set
        if proc is not None:  # this process reaps it: in the cleanup, or at a later stop
            _CHILDREN[proc.pid] = proc
        for _ in range(3 if proc is not None and "seconds" not in served else 0):
            try:  # `uv run` passes a Ctrl-C on ~0.2 s after the terminal's [verified]
                _end(proc.pid, 0)
            except KeyboardInterrupt:
                continue
            (port_dir / "serve.json").unlink(missing_ok=True)
            break
    raise ServeError(f"{failed}; the end of {run / 'stdout.log'}:\n{_log_tail(run)}")


def status(port: int = SERVE_PORT, root: Path | None = None) -> dict:
    """The serve on ``port``: ``running``; while it runs, ``dirty`` (its
    program changed in memory since it became ready), ``stale`` (the
    project changed since the copy was made) and ``lock`` (whether a
    Ghidra holds the project: :func:`.ghidra_project.lock_state`)."""
    port_dir = (root or state_root()) / str(port)
    served = _read_json(port_dir / "serve.json")
    if served is None or not _ours(served):
        return {"port": port, "running": False}
    ready = _read_json(port_dir / "run" / "ready.json") or {}
    stamp = _read_json(port_dir / "stamp.json") or {}
    project = Path(served["project"])
    try:
        stale = fingerprint(project) != stamp.get("fingerprint")
    except ProjectError:
        stale = True
    return {**served, "running": True,
            "dirty": ready.get("modificationNumber") != ready.get("readyModificationNumber"),
            "stale": stale, "lock": lock_state(project)}


def stop(port: int = SERVE_PORT, root: Path | None = None, *, timeout: float = 60.0) -> dict:
    """Stop the serve on ``port``: the stop file first, then its process
    group. Says how it ended."""
    port_dir = (root or state_root()) / str(port)
    served = _read_json(port_dir / "serve.json")
    if served is None:
        return {"port": port, "stopped": False}
    ours = _ours(served)
    if (port_dir / "run").is_dir():  # also ends a JVM whose launcher died
        (port_dir / "run" / "stop").touch()
    how = _end(served["pid"], timeout) if ours else "had already exited"
    (port_dir / "serve.json").unlink()
    return {"port": port, "stopped": True, "how": how}


def unfit_for_snapshot(port: int, root: Path | None = None) -> str | None:
    """Why ``ghidra-snapshot`` must not read the serve that owns ``port``:
    its program holds in-memory edits (dirty) or its copy predates the
    project's last save (stale). None when no serve of ours runs there
    (the owner's GUI, say)."""
    s = status(port, root)
    bad = [word for word in ("dirty", "stale") if s.get(word)]
    if not bad:
        return None
    return (f"the serve on port {port} is {' and '.join(bad)}: a snapshot would not be the "
            f"project's; `python -m devkit re ghidra-serve stop --port {port}`, then start it again")


def main(argv: list[str]) -> int:
    """Exit 0 done, 2 refused (nothing written)."""
    from .ghidra_apply import lock_text

    p = argparse.ArgumentParser(
        prog="python -m devkit re ghidra-serve",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Copies the project (reading it only) into ghidra-serve/<port>/ in the user cache folder and\n"
            "serves the copy with .tools' Ghidra over the stock GhydraMCP HTTP API on 127.0.0.1, so the\n"
            "ghidra-* verbs (--port N) and the bridge (instances_use(N)) work with no owner action. Nothing\n"
            "can be saved: HTTP writes stay in memory (status says dirty) and vanish at stop. A busy port\n"
            "is refused, naming what answers there."),
        epilog=(
            "Examples:\n"
            "  python -m devkit re ghidra-serve start --project '<folder>/My Project.gpr'\n"
            "  python -m devkit re ghidra-serve status\n"
            "  python -m devkit re ghidra-serve stop --port 8213"))
    p.add_argument("action", choices=["start", "status", "stop"])
    p.add_argument("--project", default=None, help="the project's .gpr (only read); default: the one the last "
                                                   "start used")
    p.add_argument("--port", type=int, default=SERVE_PORT,
                   help=f"the port to serve on (default {SERVE_PORT}; agents' serves take 8212-8229; a busy port is "
                        "refused)")
    p.add_argument("--max-seconds", type=int, default=DEFAULT_MAX_SECONDS,
                   help="stop by itself after this long (default 7200 = 2 h; 0 = no limit)")
    p.add_argument("--maxmem", default="2G", help="the JVM's maximum heap (default 2G)")
    p.add_argument("--timeout", type=float, default=None,
                   help="seconds start waits for the port to answer (default 300), or stop waits before it "
                        "kills the serve (default 60)")
    args = p.parse_args(argv)
    wait = {} if args.timeout is None else {"timeout": args.timeout}
    port = args.port
    try:
        if args.action == "start":
            project = Path(args.project) if args.project else remembered_project()
            if project is None:
                raise ServeError("pass --project <name>.gpr (no earlier start to reuse)")
            s = start(project, port, max_seconds=args.max_seconds, maxmem=args.maxmem, **wait)
            print(f"serving a COPY: {COPY}:/{s['program']} on 127.0.0.1:{s['port']} "
                  f"(pid {s['pid']}; {s['copy']}; ready in {s['seconds']} s)")
            print(f"  the ghidra-* verbs: --port {s['port']}")
            print(f"  the ghidra MCP bridge: instances_use({s['port']})")
            print(f"  stop it: python -m devkit re ghidra-serve stop --port {s['port']}")
        elif args.action == "status":
            s = status(port)
            if not s["running"]:
                print(f"ghidra-serve: not running on port {port}")
                return 0
            print(f"ghidra-serve: alive on 127.0.0.1:{s['port']} (pid {s['pid']}), "
                  f"serving a COPY of {s['project']}")
            print("  DIRTY: its program holds in-memory edits every client sees" if s["dirty"]
                  else "  clean: no in-memory edits since it started")
            print("  STALE: the project changed since the copy was made" if s["stale"]
                  else "  current: the copy matches the project")
            print(f"  the project's lock: {lock_text(s['lock'])}")
        else:
            s = stop(port, **wait)
            print(f"ghidra-serve: stopped on port {port} ({s['how']})" if s["stopped"]
                  else f"ghidra-serve: not running on port {port}")
    except ServeError as exc:
        print(f"ghidra-serve: {exc}", file=sys.stderr)
        return 2
    return 0
