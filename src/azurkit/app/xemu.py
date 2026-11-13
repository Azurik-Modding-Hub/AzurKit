"""Find the player's xemu and launch it for the app's Live (Modkit's
``live_launch``, D256; the app's alone, D882).

Play (the footer's button, beside Save) finds an xemu: a running one's path
first, then this OS's standard places (:func:`search_dirs`), a Spotlight lookup
on macOS, ``PATH`` and Flatpak on Linux, then the one the player picked last
(the app remembers it). It launches it with the saved build in the tray and a
**private** QMP socket (plus the fork's shared RAM), changing no xemu setting
and keeping the player's own config and saves, and hands Live those private
endpoints (:class:`Launch`), which it tries before the Endpoints box's. The fork
is told from upstream by its ``XEMU_RAM_SHM`` support (:func:`scan`), so the
fork's zero-pause shared RAM is preferred when it is there and QMP serves any
xemu.

Nothing here reads a game byte: :func:`scan` reads only xemu's own executable,
for its version string and that marker, and :func:`disc_in_tray` only the path
of the disc image a running xemu holds open (Live tracks that build's seed,
D261). The probes are injected so the app and the tests pass fakes; the real
ones (:func:`running_xemus`, :func:`spotlight`) run ``ps`` (``tasklist`` on
Windows) and ``mdfind`` and never touch the player's xemu config. Only the
player's own processes are listed, never another account's, an automated xemu
(``-name xemu-fork-auto``, D248) or an agent sandbox (an app in a ``/tmp/azx-*``
folder), so Play's offer to attach to a running xemu (D274) is the player's own.

The macOS admin attach (D257): :func:`start_helper` asks for the admin password
once and runs :mod:`.live_helper`, a read-only root helper, from a root-owned
copy on macOS's own root-owned Python (:func:`root_python`), never the app's.
"""

from __future__ import annotations

import csv
import getpass
import json
import os
import plistlib
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath

from azurkit.tools.randomizer.live.link import AUTOMATED, Endpoint, LiveError, _connect, _Probe

MARKER = b"XEMU_RAM_SHM"                 # only the fork's binary holds it (shared guest RAM)
_V = rb"\d+\.\d+(?:\.\d+)?(?:-\d+-g[0-9a-f]+)?"   # x.y.z, or x.y (the fork's v0.16 logs "0.16")
# xemu's own version string sits just before its commit (40 hex digits), maybe with its branch between; the
# first bare x.y.z in the binary is a library's (2.0.0 in the fork's).
_VERSION = re.compile(rb"\x00v?(" + _V + rb")\x00+(?:[\x21-\x7e]{1,64}\x00+)?[0-9a-f]{40}\x00")
_VERSION_V = re.compile(rb"\x00(v" + _V + rb")\x00")    # else QMP's package string, v0.15.1
_SCAN_CAP = 256 << 20                    # a universal binary, read once for its version and the marker
SHM_PREFIX = "azurik-play-"              # a per-launch name (<= 31 chars on macOS: 11 + 8 hex)
BUNDLE_ID = "app.xemu.xemu"
_SANDBOX = re.compile(r"(?:/private)?/tmp/azx-[^/]+/")   # an agent's xemu sandbox (the harness's app)


@dataclass(frozen=True)
class Xemu:
    """An xemu the player could play: ``path`` is what launches it (a macOS
    ``.app`` bundle, an executable, or the Flatpak id), ``exe`` the binary
    :func:`scan` read (None for Flatpak), ``version`` its version string ("" when
    unread), ``fork`` whether it supports the fork's shared RAM, ``running`` and
    ``pid`` a process already up, ``hardened`` whether its build has the hardened
    runtime (read only by :func:`attachable`)."""

    path: Path
    exe: Path | None
    version: str = ""
    fork: bool = False
    flatpak: bool = False
    running: bool = False
    pid: int | None = None
    hardened: bool = False

    @property
    def label(self) -> str:
        """How the chooser names it: ``xemu 0.15.1 (fork)``, ``xemu (Flatpak)``."""
        name = "xemu" + (f" {self.version.lstrip('v')}" if self.version else "")
        tags = [t for t in ("fork" if self.fork else "", "Flatpak" if self.flatpak else "",
                            "running" if self.running else "") if t]
        return f"{name} ({', '.join(tags)})" if tags else name

    @property
    def key(self) -> str:
        """What makes two finds the same xemu (its resolved binary, or the id)."""
        return BUNDLE_ID if self.flatpak else os.path.realpath(self.exe or self.path)


# ---------------------------------------------------------------- the binary

def executable(path: Path) -> Path:
    """The binary inside ``path``: a macOS ``.app``'s ``Contents/MacOS/<exe>``
    (its ``Info.plist``'s ``CFBundleExecutable``, else ``xemu``), else ``path``."""
    path = Path(path)
    if path.suffix == ".app":
        name = "xemu"
        try:
            plist = plistlib.loads((path / "Contents" / "Info.plist").read_bytes())
            name = plist.get("CFBundleExecutable") or name
        except (OSError, ValueError):
            pass
        return path / "Contents" / "MacOS" / name
    return path


def bundle_of(exe: Path) -> Path:
    """The ``.app`` a running macOS binary ``.../X.app/Contents/MacOS/x`` is in
    (what ``open -a`` launches), else ``exe``."""
    exe = Path(exe)
    app = exe.parent.parent.parent
    return app if app.suffix == ".app" and exe.parent.name == "MacOS" and exe.parent.parent.name == "Contents" \
        else exe


def scan(exe: Path | None) -> tuple[str, bool]:
    """``(version, fork)`` read from xemu's executable ``exe``: xemu's own version
    string (the one before its commit hash, else QMP's ``v``-prefixed one) and
    whether it holds :data:`MARKER` (the fork's shared RAM). ``("", False)`` when
    it can't be read (or is a bare name: Windows' ``tasklist`` gives no path).
    Reads no game byte: only xemu's own binary."""
    if exe is None or not Path(exe).is_absolute():
        return "", False
    try:
        with open(exe, "rb") as f:
            data = f.read(_SCAN_CAP)
    except OSError:
        return "", False
    m = _VERSION.search(data) or _VERSION_V.search(data)
    return (m.group(1).decode("latin-1") if m else ""), MARKER in data


def hardened_runtime(exe: Path, run: Callable[..., subprocess.CompletedProcess] | None = None) -> bool:
    """Whether the macOS binary ``exe`` is signed with the hardened runtime
    (``codesign -dv`` prints ``flags=...(runtime)``): a root helper can't read
    such a build's memory even as root, so the attach refuses it (D257). Reads
    nothing but the signature of a binary already on disk; never downloads."""
    run = run or subprocess.run
    try:
        out = run(["codesign", "-dv", "--verbose=2", str(exe)], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    line = next((ln for ln in (out.stderr or "").splitlines() if ln.startswith("CodeDirectory")), "")
    return "runtime" in line


def describe(path: Path, *, running: bool = False, pid: int | None = None, flatpak: bool = False) -> Xemu:
    """An :class:`Xemu` for ``path``, its version and fork read from its binary."""
    if flatpak:
        return Xemu(Path(path), None, flatpak=True, running=running, pid=pid)
    exe = executable(path)
    version, fork = scan(exe)
    return Xemu(Path(path), exe, version, fork, running=running, pid=pid)


# ---------------------------------------------------------------- the probes

def _ps(field: str, run, uid: int) -> dict[int, str]:
    """``{pid: field}`` of real user ``uid``'s processes (``ps -ax`` lists every account's)."""
    try:
        out = run(["ps", "-axww", "-o", f"pid=,ruid=,{field}="], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    rows = (line.split(None, 2) for line in out.splitlines())
    return {int(r[0]): r[2].strip() for r in rows if len(r) == 3 and r[0].isdigit() and r[1] == str(uid)}


NO_WINDOW = 0x08000000
"""Windows' ``CREATE_NO_WINDOW``: the app is a windowed program, which has no console, so a console program it starts
(``tasklist``) would open a console window of its own without it."""


def _tasklist(run, user: str) -> list[tuple[Path, int]]:
    """Windows: ``user``'s running ``xemu.exe`` processes, from ``tasklist`` (which
    names no path or command line: enough for Play to start no second one), with
    no console window (:data:`NO_WINDOW`)."""
    try:
        out = run(["tasklist", "/FI", "IMAGENAME eq xemu.exe", "/FI", f"USERNAME eq {user}", "/FO", "CSV",
                   "/NH"], capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [(Path(r[0]), int(r[1])) for r in csv.reader(out.splitlines())
            if len(r) > 1 and r[0].lower() == "xemu.exe" and r[1].isdigit()]


def running_xemus(platform: str = sys.platform, run=None, uid: int | None = None) -> list[tuple[Path, int]]:
    """Each running xemu the player started as ``(executable path, pid)``: from
    ``ps`` (macOS, Linux) only real user ``uid``'s (this process's), never another
    account's, an automated one (``-name xemu-fork-auto`` on its command line,
    D248) or an agent's sandbox (an app in a ``/tmp/azx-*`` folder); on Windows
    this user's ``xemu.exe`` from ``tasklist``, a bare name with no path."""
    run = run or subprocess.run
    if platform == "win32":
        return _tasklist(run, getpass.getuser())
    uid = os.getuid() if uid is None else uid
    comm, args = _ps("comm", run, uid), _ps("args", run, uid)
    return [(Path(c), pid) for pid, c in comm.items()
            if _is_xemu_exe(c) and not _SANDBOX.match(c) and f"-name {AUTOMATED}" not in args.get(pid, "")]


def _is_xemu_exe(comm: str) -> bool:
    """Whether a ``ps`` command path names xemu's binary (``.../xemu`` or
    ``.../xemu.app/Contents/MacOS/xemu``), not another program with xemu in a
    folder name."""
    return Path(comm).name in ("xemu", "xemu.exe")


def search_dirs(platform: str = sys.platform, home: Path | None = None) -> list[Path]:
    """The folders Play scans for an installed xemu, in order."""
    home = Path(home or Path.home())
    if platform == "darwin":
        return [Path("/Applications"), home / "Applications",
                home / "Documents" / "xemu-dev" / "xemu-macos" / "dist"]
    if platform == "win32":
        return [Path(p) for p in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                                  os.environ.get("LOCALAPPDATA")) if p]
    return []


def _scan_dir(d: Path, platform: str) -> list[Path]:
    """xemu under ``d`` (one level down too): the ``.app`` on macOS, ``xemu.exe``
    on Windows, a plain ``xemu`` on Linux."""
    name = {"darwin": "xemu.app", "win32": "xemu.exe"}.get(platform, "xemu")
    return [cand for base in (d, *_children(d)) if (cand := base / name).exists()]


def _children(d: Path) -> Iterable[Path]:
    try:
        return [c for c in d.iterdir() if c.is_dir()]
    except OSError:
        return []


def spotlight(platform: str = sys.platform) -> list[Path]:
    """xemu bundles Spotlight knows, by bundle id (macOS only)."""
    if platform != "darwin":
        return []
    try:
        out = subprocess.run(["mdfind", f"kMDItemCFBundleIdentifier == '{BUNDLE_ID}'"],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [Path(line) for line in out.splitlines() if line.strip().endswith(".app")]


def flatpak_installed(run: Callable[..., subprocess.CompletedProcess] | None = None) -> bool:
    """Whether Flatpak has xemu (Linux)."""
    run = run or subprocess.run
    try:
        return run(["flatpak", "info", BUNDLE_ID], capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@dataclass
class Probes:
    """The discovery's injectable sources (the app and the tests pass fakes)."""
    running: Callable[[str], list[tuple[Path, int]]] = staticmethod(running_xemus)
    dirs: Callable[[str, Path | None], list[Path]] = staticmethod(search_dirs)
    spotlight: Callable[[str], list[Path]] = staticmethod(spotlight)
    which: Callable[[str], str | None] = staticmethod(shutil.which)
    flatpak: Callable[[], bool] = staticmethod(flatpak_installed)
    remembered: Path | None = None
    home: Path | None = None


def discover(platform: str = sys.platform, probes: Probes | None = None) -> list[Xemu]:
    """Every xemu Play found, most useful first and deduplicated by binary: a
    running one, this OS's standard places, Spotlight (macOS), ``PATH`` and
    Flatpak (Linux), then the remembered pick. The caller launches the chosen
    one (or the only one), or asks for one when the list is empty."""
    probes = probes or Probes()
    found: list[Xemu] = []
    for path, pid in probes.running(platform):
        found.append(describe(bundle_of(path), running=True, pid=pid))
    for d in probes.dirs(platform, probes.home):
        found += [describe(hit) for hit in _scan_dir(d, platform)]
    found += [describe(hit) for hit in probes.spotlight(platform)]
    if platform not in ("darwin", "win32"):
        if (on_path := probes.which("xemu")):
            found.append(describe(Path(on_path)))
        if probes.flatpak():
            found.append(describe(Path(BUNDLE_ID), flatpak=True))
    if probes.remembered and Path(probes.remembered).exists():
        found.append(describe(Path(probes.remembered)))
    seen, out = set(), []
    for x in found:
        if x.key not in seen:
            seen.add(x.key)
            out.append(x)
    return out


def answers(endpoints) -> bool:
    """Whether the xemu Play started still runs: one of its private QMP
    ``endpoints`` takes a connection (closed at once, nothing sent), so a second
    Play turns Live on for it with no question and no prompt (D257)."""
    for ep in endpoints or ():
        if ep.kind == "qmp":
            try:
                _connect(ep).close()
            except _Probe:
                continue
            return True
    return False


def can_attach(platform: str = sys.platform) -> bool:
    """Whether the app can read an xemu the player started without Play (D274's
    offer): macOS through the admin attach (D257, :func:`start_helper`); Windows and
    Linux not until a process-memory reader there lands (this is its seam)."""
    return platform == "darwin"


def attachable(platform: str = sys.platform, probes: Probes | None = None) -> list[Xemu]:
    """The running xemus the macOS admin attach may read (D257): the player's own
    (never an automated one, D248), each with whether its build has the hardened
    runtime, which a root helper can't read."""
    probes = probes or Probes()
    out = []
    for path, pid in probes.running(platform):
        x = describe(bundle_of(path), running=True, pid=pid)
        out.append(replace(x, hardened=bool(x.exe) and hardened_runtime(x.exe)))
    return out


def tray_disc(platform: str = sys.platform, running=running_xemus, tray=None,
              accept: Callable[[Path], bool] = lambda _iso: True) -> Path | None:
    """The disc image in a running xemu's tray (the player's own xemu, D248;
    :func:`disc_in_tray`) that ``accept`` takes: the build whose seed Live
    tracks (D261, Modkit's ``tray_seed``, which passed over a disc with no
    placement file for the next running xemu's; an AzurKit build carries its
    recipe). None when no running xemu holds one it takes."""
    tray = tray or disc_in_tray
    for _exe, pid in running(platform):
        if (iso := tray(pid, platform)) is not None and accept(iso):
            return iso
    return None


# ---------------------------------------------------------------- the launch

@dataclass(frozen=True)
class Launch:
    """How to start xemu for Play: ``argv`` to run, ``env`` to add to it, the
    private ``endpoints`` Live reads, and the ``scratch`` dir to delete on exit."""
    argv: list[str]
    env: dict[str, str]
    endpoints: list[Endpoint]
    scratch: Path | None = field(default=None)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def plan_launch(xemu: Xemu, iso: Path, run_dir: Path, platform: str = sys.platform,
                shm_name: str | None = None, port: int | None = None) -> Launch:
    """Launch ``xemu`` with ``iso`` in the tray and a private QMP socket (a unix
    socket in ``run_dir`` on macOS and Linux, a loopback port on Windows and for
    Flatpak, whose ``/tmp`` is its own) plus the fork's shared RAM under a private
    name, changing no xemu setting. The endpoints are explicit, so Live reads this
    xemu whatever its ``-name``."""
    iso = str(iso)
    eps: list[Endpoint] = []
    env: dict[str, str] = {}
    if platform == "win32" or xemu.flatpak:
        port = port or _free_port()
        qmp = f"tcp:127.0.0.1:{port},server=on,wait=off"
        eps.append(Endpoint("qmp", ("127.0.0.1", port), True))
        args = ["-dvd_path", iso, "-qmp", qmp]
        if xemu.fork:
            env["XEMU_RAM_SHM"] = shm_name = shm_name or SHM_PREFIX + secrets.token_hex(4)
            eps.insert(0, Endpoint("shm", shm_name, True))
        argv = ["flatpak", "run", BUNDLE_ID, *args] if xemu.flatpak else [str(xemu.exe), *args]
        return Launch(argv, env, eps, run_dir)
    sock = str(Path(run_dir) / "qmp.sock")
    qmp = f"unix:{sock},server=on,wait=off"
    eps.append(Endpoint("qmp", sock, True))
    args = ["-dvd_path", iso, "-qmp", qmp]
    if xemu.fork:
        shm_name = shm_name or SHM_PREFIX + secrets.token_hex(4)
        env["XEMU_RAM_SHM"] = shm_name
        eps.insert(0, Endpoint("shm", shm_name, True))
    if platform == "darwin":
        # "open --env" sets the launched app's environment, so Popen's own need
        # not; "open -n" starts a fresh instance even when one is up.
        argv = ["open", "-n", "-a", str(xemu.path)]
        for key, value in env.items():
            argv += ["--env", f"{key}={value}"]
        argv += ["--args", *args]
        return Launch(argv, {}, eps, run_dir)
    return Launch([str(xemu.exe), *args], env, eps, run_dir)


def spawn(launch: Launch, wait: float = 1.5) -> None:
    """Start ``launch`` detached (off the page's thread: it waits). ``OSError``
    naming why when it didn't start: macOS ``open``'s own error, or an xemu that
    exited within ``wait`` s."""
    if launch.argv[0] == "open":                 # it returns once the app is launched, or says why not
        try:
            res = subprocess.run(launch.argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
        except subprocess.SubprocessError as exc:
            raise OSError(f"open didn't start xemu: {exc}") from None
        if res.returncode:
            raise OSError(f"open didn't start xemu: {(res.stderr or '').strip() or f'status {res.returncode}'}")
        return
    env = {**os.environ, **launch.env} if launch.env else None
    proc = subprocess.Popen(launch.argv, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        code = proc.wait(timeout=wait)
    except subprocess.TimeoutExpired:
        return                                   # it runs
    raise OSError(f"xemu exited at once (status {code})")


def disc_in_tray(pid: int, platform: str = sys.platform, run=None) -> Path | None:
    """The disc image (``.iso``, ``.xiso``) running xemu ``pid`` holds open: the
    build in its tray, so Live tracks that seed (D261). Only the player's own
    xemu's open files are listed (``lsof`` on macOS, ``/proc`` on Linux); None
    when there is none or it can't tell (Windows)."""
    names: list[str] = []
    if platform == "darwin":
        try:
            out = (run or subprocess.run)(["lsof", "-n", "-P", "-w", "-a", "-p", str(int(pid)), "-Fn"],
                                          capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        names = [line[1:] for line in out.splitlines() if line.startswith("n")]
    elif platform != "win32":
        fds = Path(f"/proc/{int(pid)}/fd")
        try:
            names = [os.readlink(fd) for fd in fds.iterdir()]
        except OSError:
            return None
    return next((Path(n) for n in names if n.lower().endswith((".iso", ".xiso")) and Path(n).is_file()), None)


# ---------------------------------------------------------------- the macOS admin helper (D257)

HELPER_SRC = Path(__file__).with_name("live_helper.py")   # the frozen app carries it as a file (scripts/freeze.py)
ROOT_PYTHONS = ("/Library/Developer/CommandLineTools/usr/bin/python3",    # then Xcode's, then xcode-select -p's
                "/Applications/Xcode.app/Contents/Developer/usr/bin/python3")
#: The folder above a root Python that the admin group may write too (D310: Xcode's, under /Applications, root:admin
#: 0775; its admins may get root anyway), and that group.
ADMIN_FOLDER, ADMIN_GID = "/Applications", 80
NEED_PYTHON = ("The admin attach runs macOS's own Python, which root alone may change: install the Command "
               "Line Tools (xcode-select --install), or quit xemu and press Play, which starts it readable.")
_PY_PROBE = ("import __future__, argparse, ctypes, json, os, shutil, socket, struct, sys, time\n"
             "fs = {os.path.realpath(f) for f in (getattr(m, '__file__', None) for m in list(sys.modules.values()))"
             " if f}\n"
             "lib = os.path.join(sys.prefix, 'Python')\n"
             "print(json.dumps([os.path.realpath(sys.executable), *sorted(fs | ({lib} if os.path.exists(lib) "
             "else set()))]))")


def _roots_alone(path: str, stat) -> bool:
    """Whether ``path`` and every folder above it are root's and writable by no
    one else (no group or other write bit; :data:`ADMIN_FOLDER` the admin
    group's too). The path is macOS's own, so it is walked as a POSIX path on
    any host."""
    p = PurePosixPath(path)
    for part in (p, *p.parents):
        try:
            st = stat(str(part))
        except OSError:
            return False
        group = 0o020 if str(part) == ADMIN_FOLDER and st.st_gid == ADMIN_GID else 0
        if st.st_uid != 0 or st.st_mode & 0o022 & ~group:
            return False
    return True


def root_python(run=None, stat=os.stat) -> str:
    """The interpreter the root helper runs: macOS's own Python 3 (the Command
    Line Tools', else Xcode's, D310, else ``xcode-select -p``'s) when its binary
    and every module the helper loads, with every folder above them, are root's
    alone (:func:`_roots_alone`); never the app's, whose interpreter and standard
    library the user owns. :class:`LiveError` (:data:`NEED_PYTHON`) when there is
    none."""
    run = run or subprocess.run
    cands = list(ROOT_PYTHONS)
    try:
        dev = run(["/usr/bin/xcode-select", "-p"], capture_output=True, text=True, timeout=10).stdout.strip()
        if dev and f"{dev}/usr/bin/python3" not in cands:
            cands.append(f"{dev}/usr/bin/python3")
    except (OSError, subprocess.SubprocessError):
        pass
    for exe in cands:
        try:
            out = run(["/usr/bin/env", "-i", exe, "-I", "-S", "-c", _PY_PROBE], capture_output=True, text=True,
                      timeout=20, cwd="/")
            files = json.loads(out.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            continue
        if files and all(_roots_alone(f, stat) for f in files):
            return files[0]
    raise LiveError(NEED_PYTHON)


def mac_helper_command(pid: int, sock: Path, uid: int, peer: int, python: str, src: Path = HELPER_SRC) -> str:
    """The privileged shell line the admin prompt runs: make a **root-owned**
    temp dir, copy the helper into it, lock the copy down, and run that copy
    detached as root with the root-owned ``python`` (:func:`root_python`) in
    isolated mode, no ``site`` and an empty environment (never the
    user-writable original or the app's interpreter), reading only xemu ``pid``
    and serving only the app's process ``peer`` on ``sock`` (``uid``'s)."""
    q = shlex.quote
    return (
        "set -e; "
        "d=$(/usr/bin/mktemp -d /var/tmp/azurik-live-helper.XXXXXX); "
        '/bin/chmod 700 "$d"; '
        f"/bin/cp {q(str(src))} \"$d/helper.py\"; "
        '/bin/chmod 500 "$d/helper.py"; '
        f"cd /; /usr/bin/nohup /usr/bin/env -i {q(python)} -I -S \"$d/helper.py\" "
        f"--pid {int(pid)} --socket {q(str(sock))} --uid {int(uid)} --peer {int(peer)} >/dev/null 2>&1 & echo $!"
    )


def _applescript_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def run_admin(command: str, run: Callable[..., subprocess.CompletedProcess] | None = None):
    """Run ``command`` as root behind one macOS admin prompt (``osascript ... with
    administrator privileges``). Not unit-tested: the real prompt is the
    player's (the discovery and the command string are the tested parts)."""
    run = run or subprocess.run
    script = f"do shell script {_applescript_string(command)} with administrator privileges"
    return run(["osascript", "-e", script], capture_output=True, text=True, timeout=120)


def start_helper(pid: int, run_dir: Path, run=None, wait: float = 10.0) -> Endpoint:
    """Ask for the admin password once and start the read-only root helper for
    xemu ``pid``, its socket in the app's private ``run_dir`` (made ``0700`` by
    the caller), serving this process only. Returns the ``helper`` endpoint
    once the socket is up; :class:`LiveError` when there is no root-owned Python,
    admin was refused, or the helper didn't start."""
    sock = Path(run_dir) / "helper.sock"
    res = run_admin(mac_helper_command(pid, sock, os.getuid(), os.getpid(), root_python()), run)
    if res.returncode != 0:
        raise LiveError(f"admin was refused or cancelled: {(res.stderr or '').strip() or 'no helper started'}")
    end = time.monotonic() + wait
    while not sock.exists():
        if time.monotonic() > end:
            raise LiveError("the admin helper didn't start (its socket never appeared)")
        time.sleep(0.05)
    return Endpoint("helper", str(sock), True)
