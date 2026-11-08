"""Both hosts (Steps 4.1b2, 4.1d2): the site runs the wheel under Pyodide,
and the app (D732) is a PyInstaller onedir (``scripts/freeze.py``; on macOS
``AzurKit.app``). The gate, ``azurkit verify``, gives the same verdicts on
CPython, under Pyodide 314 on Node and from the frozen app, and the frozen
app's page builds each ported pack's G1 case with the native engine. The
app runs read-only with a fresh HOME, writes nothing into itself or outside
platformdirs' folders (and the build it saves), and holds no Unicorn, zig,
capstone or GPL code. Its page server answers only on 127.0.0.1 and only to
its launch's token, and takes the engine's calls only from its own page."""

from __future__ import annotations

import base64
import collections
import contextlib
import hashlib
import http.client
import importlib.metadata
import io
import json
import multiprocessing
import operator
import os
import plistlib
import socket
import re
import shlex
import struct
import subprocess
import sys
import textwrap
import threading
import time
import types
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from pathlib import Path

import platformdirs
import pytest

import azurkit
from azurkit import __main__ as _entry  # noqa: F401 (the frozen app's entry; fullsuite picks this file for it)
from azurkit import app, cli, sdk
from azurkit.app import engine
from azurkit.core import gate, iso, native, progress
from azurkit.core.progress import record as progress_record
from azurkit.edits import manifest as edits
from azurkit.edits.layer import Change, Layer
from azurkit.tools import mods
from azurkit.tools.characters import pool
from azurkit.tools.randomizer import tracking
from azurkit.tools.randomizer.planner import fill as planner_fill
from azurkit.tools.randomizer.planner import loader
from scripts import freeze, record_goldens
from devkit.xemu import queue
from tests import _g1, _page, _perf, _speed
from tests._xiso import fill, image
from tests.test_randomizer import BROWSED, TRACKER, _profile, shows_gems, tracker_states

ROOT = Path(__file__).resolve().parent.parent
NEVER = ("unicorn", "capstone", "zig", "tkinter", "_tkinter", "_gdbm", "_dbm")
OURS = {"azurkit", "__main__", "web", freeze.ICON.name}
# The bootloader is under PyInstaller's Bootloader Exception; the loader and runtime hooks it bundles are Apache-2.0.
PYINSTALLER_RUNTIME = ("pyimod", "pyiboot", "pyi_rth_", "_pyi_rth_utils")
# The libraries beside the app with no distribution's name, by how their lowercased names start (a wheel's carry a hash),
# and whose: on Linux what numpy's wheel links (read from its ELF files), the system's ones PyInstaller's exclude list
# keeps and the wheel's own, which PyInstaller lays at the top; on Windows Python's own build's and Microsoft's C
# runtime (NOTICE.md has each).
MICROSOFT = "Microsoft's C runtime (its redistribution terms)"
LINKED = {"libstdc++.so.6": "GCC's C++ runtime (its Runtime Library Exception)",
          "libgcc_s.so.1": "GCC's runtime (its Runtime Library Exception)", "libz.so.1": "zlib (Zlib)",
          "libgfortran-": "GCC's Fortran runtime (its Runtime Library Exception)",
          "libquadmath-": "GCC's libquadmath (LGPL-2.1-or-later)", "libscipy_openblas": "OpenBLAS (BSD-3-Clause)",
          "api-ms-win-": MICROSOFT, "ucrtbase.": MICROSOFT, "vcruntime140": MICROSOFT, "msvcp140": MICROSOFT,
          "libcrypto-": "OpenSSL (Apache-2.0)", "libssl-": "OpenSSL (Apache-2.0)", "libffi-": "libffi (MIT)",
          "zlib1.": "zlib (Zlib)"}
WINDOW_REFUSED = f"azurkit: no window while {app.NO_WINDOW} is set (the tests' mode)\n"


def cpython(*argv: str) -> dict:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return {"code": code, "stdout": out.getvalue(), "stderr": err.getvalue()}


@pytest.fixture(scope="module")
def verify_argv(tmp_path_factory, usa_iso, europe_iso) -> list[str]:
    """``azurkit verify`` of both vanilla images, an image whose
    ``default.xbe`` isn't vanilla, and a file that is no image."""
    tmp = tmp_path_factory.mktemp("images")
    (modded := tmp / "modded.iso").write_bytes(image({"default.xbe": fill("x", 20)}))
    (blank := tmp / "blank.iso").write_bytes(bytes(40 * 2048))
    return ["verify", *(arg for path in (usa_iso, europe_iso, modded, blank) for arg in ("--iso", str(path)))]


@pytest.fixture(scope="module")
def verdicts(verify_argv) -> dict:
    """CPython's: two vanilla images and two refusals."""
    found = cpython(*verify_argv)
    assert (found["code"], found["stdout"].count("\n"), found["stderr"].count("\n")) == (1, 2, 2), found
    return found


def test_the_gate_gives_the_same_verdicts_under_pyodide(verify_argv, verdicts, pyodide):
    """The wheel alone (no dependencies, as the site loads it) under Pyodide
    on Node reads both images through the gate and refuses the others with
    CPython's words."""
    got = pyodide(*verify_argv)
    assert (got["platform"], got["python"].rpartition(".")[0], got["azurkit"]) == (
        "emscripten", "3.14", "/lib/python3.14/site-packages/azurkit/__init__.py")
    assert {key: got[key] for key in verdicts} == verdicts


def _licence(dist: str) -> str:
    meta = importlib.metadata.metadata(dist)
    return (meta.get("License-Expression") or (meta.get("License") or "").partition("\n")[0]
            or "; ".join(c for c in meta.get_all("Classifier") or [] if c.startswith("License ::")) or "none given")


def _owners(app_path: Path) -> dict[str, str]:
    """Each top-level name the app holds (a module in its archives, or a
    file or folder beside them) and whose code it is, with its licence."""
    from PyInstaller.archive.readers import CArchiveReader
    pkg = CArchiveReader(str(freeze.executable(app_path)))
    names = {name.split(".")[0] for name in pkg.open_embedded_archive("PYZ.pyz").toc} | set(pkg.toc) - {"PYZ.pyz"}
    folders = freeze.folders(app_path)
    with zipfile.ZipFile(next(f / "base_library.zip" for f in folders if (f / "base_library.zip").exists())) as zf:
        names |= {name.split("/")[0].removesuffix(".pyc") for name in zf.namelist()}
    names |= {path.name for folder in folders for path in folder.iterdir()} - {"base_library.zip"}
    dists = importlib.metadata.packages_distributions()
    owners = {}
    for name in names:
        module = name.split(".")[0] if name.endswith(".pyd") else name   # Windows' extension modules lie at the top
        linked = next((owner for start, owner in LINKED.items() if name.lower().startswith(start)), None)
        if name in OURS:
            owners[name] = "AzurKit (MIT)"
        elif name.startswith(PYINSTALLER_RUNTIME):
            owners[name] = "PyInstaller's runtime (Apache-2.0)"
        elif (module in sys.stdlib_module_names or name.startswith(("_sysconfigdata_", "libpython"))
              or re.fullmatch(r"python3\d*\.dll", name)):
            owners[name] = "Python (PSF-2.0)"
        elif name.endswith(".dist-info"):   # a distribution's metadata (numpy's, which PyInstaller's hook keeps)
            dist = name.removesuffix(".dist-info").rsplit("-", 1)[0]
            owners[name] = f"{dist} ({_licence(dist)})"
        elif name.endswith(".libs"):   # a wheel's own libraries (numpy's on Linux and Windows), under no module's name
            dist = name.removesuffix(".libs")
            owners[name] = f"{dist} ({_licence(dist)})"
        elif linked:
            owners[name] = linked
        else:
            owners[name] = ", ".join(f"{d} ({_licence(d)})" for d in sorted(set(dists.get(module, ())))) or "unknown"
    return owners


def _tree(root: Path) -> dict[str, tuple[int, int, int]]:
    """Each path under ``root``: its mode, size and modification time."""
    tree = {}
    for path in [root, *root.rglob("*")]:
        st = path.lstat()
        tree[path.relative_to(root).as_posix()] = (st.st_mode, st.st_size, st.st_mtime_ns)
    return tree


@pytest.fixture(scope="module")
def frozen_app(tmp_path_factory):
    """The app, frozen from this checkout and made read-only while the
    tests run: its path, and its tree as frozen."""
    tmp = tmp_path_factory.mktemp("frozen")
    built = subprocess.run([sys.executable, str(ROOT / "scripts" / "freeze.py"), "--dist", str(tmp / "dist"),
                            "--work", str(tmp / "work")], capture_output=True, text=True, timeout=900)
    assert built.returncode == 0, built.stderr[-3000:]
    app_path = Path(built.stdout.splitlines()[-1])
    writable = [p for p in [app_path, *app_path.rglob("*")] if not p.is_symlink()]
    for path in writable:
        path.chmod(path.stat().st_mode & ~0o222)
    try:
        yield app_path, _tree(app_path)
    finally:
        for path in writable:
            path.chmod(path.stat().st_mode | 0o200)


def _head() -> str:
    """This checkout's HEAD, as its git gives it: the commit the app's About names."""
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()


ANSWERING = (app._Handler.do_GET.__code__, app._Handler.do_POST.__code__)
ANSWERED_S = 30
"""s a test waits at its end (:func:`_answered`) for a closed app server to answer the requests it took before its
close (:func:`_answering`): a Live map test's page posts its marks every 0.7 s to its close, over at most 6 kept
connections (a browser's to a host), so 6 config writes queued on one lock, each a read and a replace past Windows'
refusals while its scanner holds the file (``app.WAITS``: 1.55 s each), 19 s at most (Step 4.5d)."""


def _answering() -> list[str]:
    """The paths of the requests a closed app server is still answering: socketserver waits for none of its daemon
    threads at ``Server.close``, and a call past its ``closed`` check runs on (its own check refuses only later ones)."""
    paths = []
    for frame in sys._current_frames().values():
        while frame is not None and frame.f_code not in ANSWERING:
            frame = frame.f_back
        if frame is not None and (handler := frame.f_locals["self"]).server.closed:
            paths.append(handler.path.partition("?")[0])
    return paths


def _answered() -> None:
    """Every closed app server has answered the requests it took (:func:`_answering`), within :data:`ANSWERED_S`."""
    end = time.monotonic() + ANSWERED_S
    while busy := _answering():
        assert time.monotonic() < end, f"a closed app server still answers {busy} after {ANSWERED_S} s"
        time.sleep(0.02)


TRAY_DISC = app.xemu.tray_disc   # the module's own, which the fixture below fakes for the app


@pytest.fixture(autouse=True)
def _no_xemu_in_the_tray(monkeypatch):
    """No test here reads this computer's running xemus: Live's tick asks for the disc in a running xemu's tray
    (``api/tray``), which a test that plays one fakes."""
    monkeypatch.setattr(app.xemu, "tray_disc", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def _closed_servers_answered(monkeypatch):
    """Each test here ends once its closed servers have answered (:func:`_answered`), before its ``monkeypatch``
    puts the user folders back (Step 4.5d): this fixture takes it, so its end runs first. socketserver waits for none
    of a server's daemon threads at ``Server.close``, and the app finds its folders at each read and write, so a
    request still running then wrote where the folders were next: the user's own (the run's HOME) or, past the next
    test's :func:`_home`, that test's. The other floors' test's page posts its marks with Show collected on to its
    close, and such a late ``api/tracked`` (its config's replace refused as Windows refuses one) opened the collected
    spot's test's page with Show collected on, its collected spot left on the map dimmed: the one way found to that
    test's failure on GitHub's Windows Firefox."""
    yield
    _answered()


def _home(monkeypatch, home: Path) -> None:
    """This process's user folders, and its children's, under ``home``:
    HOME, and every folder platformdirs finds the app's config, data, cache
    and downloads in before HOME, whatever the host sets: no XDG_*_HOME (a
    GitHub Linux runner sets XDG_CONFIG_HOME, so every test's app.json was
    one file there, Step 4.4ci2) and, on Windows, whose known folders don't
    follow HOME, platformdirs' WIN_PD_OVERRIDE_* and USERPROFILE. First it
    waits until every server closed before it has answered (:func:`_answered`,
    Step 4.5d), so a late write lands in the folders it had; each test's end
    waits too (:func:`_closed_servers_answered`)."""
    _answered()
    monkeypatch.setenv("HOME", str(home))
    for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(name, raising=False)
    if os.name == "nt":
        monkeypatch.setenv("USERPROFILE", str(home))
        for kind in ("APPDATA", "LOCAL_APPDATA", "DOWNLOADS"):
            monkeypatch.setenv(f"WIN_PD_OVERRIDE_{kind}", str(home / kind))


def test_a_closed_servers_late_write_lands_in_its_own_tests_home_not_the_next_ones(tmp_path, monkeypatch, pytester):
    """Step 4.5d: in a run of two tests with this file's fixture, a page's
    ``api/tracked`` the first test's server took just before its close, its
    write held past that test's end (as Windows' scanner holds the config
    open), lands in that test's config: the run's own (``base``) and the
    next test's have none."""
    _home(monkeypatch, tmp_path / "base")
    pytester.makepyfile(test_x="""
        import os
        import threading
        from pathlib import Path

        from tests.test_hosts import _closed_servers_answered, _home, _page, _post, app  # noqa: F401 (the fixture)

        HOMES, POSTERS, REPLIES = Path(os.environ["HOME"]).parent, [], []

        def test_leaves_a_write_held_past_its_servers_close(monkeypatch):
            _home(monkeypatch, HOMES / "a")
            held, go, remember = threading.Event(), threading.Event(), app._remember

            def held_write(**kept):
                held.set()
                go.wait(30)
                remember(**kept)
            monkeypatch.setattr(app, "_remember", held_write)
            server, kept = app.serve(_page.WEB), {"marks": {}, "collected": True}
            POSTERS.append(threading.Thread(target=_post, args=(server.url, "api/tracked", {"tracker": kept}, REPLIES)))
            POSTERS[0].start()
            assert held.wait(30)
            server.close()
            threading.Timer(0.3, go.set).start()

        def test_moves_the_user_folders(monkeypatch):
            _home(monkeypatch, HOMES / "b")
            POSTERS[0].join(30)
            assert REPLIES == [{}]
    """)
    pytester.runpytest_inprocess("-p", "no:cacheprovider").assert_outcomes(passed=2)
    written = {}
    for name in ("base", "a", "b"):
        _home(monkeypatch, tmp_path / name)
        if (config := app._config()).exists():
            written[name] = json.loads(config.read_text(encoding="utf-8")).get("tracker")
    assert written == {"a": {"marks": {}, "collected": True}}


class Sandbox:
    """Where the frozen app runs: a fresh HOME and TMPDIR, an empty working
    folder, no image variables and the tests' no-window mode (:attr:`env`;
    this process's HOME too). :meth:`left` lists what was written there
    outside platformdirs' folders."""

    def __init__(self, tmp_path: Path, monkeypatch):
        self.home, self.tmp, self.cwd = tmp_path / "home", tmp_path / "tmp", tmp_path / "cwd"
        for folder in (self.home, self.tmp, self.cwd):
            folder.mkdir()
        _home(monkeypatch, self.home)
        self.env = {k: v for k, v in os.environ.items() if k not in ("AZURKIT_ISO", "AZURKIT_ISO_EUROPE")}
        self.env |= {"TMPDIR": str(self.tmp), app.NO_WINDOW: "1"}
        monkeypatch.delenv("AZURKIT_ISO", raising=False)
        monkeypatch.delenv("AZURKIT_ISO_EUROPE", raising=False)
        self.dirs = platformdirs.PlatformDirs("AzurKit", appauthor=False)

    def run(self, app_path: Path, *argv: str, timeout: int = 300) -> dict:
        done = subprocess.run([str(freeze.executable(app_path)), *argv], capture_output=True, text=True,
                              env=self.env, cwd=self.cwd, timeout=timeout)
        return {"code": done.returncode, "stdout": done.stdout, "stderr": done.stderr}

    @contextlib.contextmanager
    def serving(self, app_path: Path):
        """``AzurKit serve``: the page's address while it serves; it must
        then end cleanly when its input does."""
        with subprocess.Popen([str(freeze.executable(app_path)), "serve"], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env,
                              cwd=self.cwd) as served:
            try:
                url = served.stdout.readline().strip()
                assert url.startswith("http://127.0.0.1:"), served.stderr.read()
                yield url
            except BaseException as exc:
                _ended_with(served, exc)
                raise
            served.stdin.close()
            assert (served.wait(30), served.stderr.read()) == (0, "")

    def left(self) -> list[Path]:
        kept = [Path(getattr(self.dirs, f"user_{kind}_dir")) for kind in ("data", "config", "cache", "state", "log")]
        return [*self.cwd.iterdir(), *(p for p in [*self.home.rglob("*"), *self.tmp.rglob("*")]
                                       if p.is_file() and not any(map(p.is_relative_to, kept)))]


def _ended_with(served: subprocess.Popen, exc: BaseException) -> None:
    """Kill the app ``served`` a test's failure ``exc`` stopped, and note on it whether it had already ended (one that
    died printing nothing reads apart from a live one) and the end of what it printed to its stderr, line by line:
    tests.yml prints a failure's first 40 E lines, each cut at 240 characters, so a traceback's end, its exception, has to
    fit both."""
    state = "was still running" if (code := served.poll()) is None else f"had ended, code {code}"
    served.kill()
    with contextlib.suppress(subprocess.TimeoutExpired, ValueError, OSError):
        exc.add_note(f"the app {state}; its stderr:\n" + served.communicate(timeout=30)[1][-1000:])


def _children(pid: int) -> list[int]:
    """The process ``pid``'s children, on each OS."""
    command = (["powershell", "-NoProfile", "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}').ProcessId"] if os.name == "nt"
               else ["pgrep", "-P", str(pid)])
    return [int(found) for found in subprocess.run(command, capture_output=True, text=True).stdout.split()]


def _descendants(pid: int) -> list[int]:
    """The process ``pid``'s whole tree below it: on Windows a venv's ``python.exe`` is a redirector whose one child is
    the real Python, so the app's engine is its grandchild there."""
    return [found for child in _children(pid) for found in (child, *_descendants(child))]


def test_a_processs_descendants_reach_its_grandchildren():
    """:func:`_descendants`, what ``test_quitting_the_app_mid_save...`` notes of the app's engines: on Windows the app's
    direct child isn't an engine, so its children alone read the same whether an engine hangs or respawns."""
    def over(code: str) -> str:   # a process that runs ``code`` in a child
        return f"import subprocess, sys; subprocess.run([sys.executable, '-c', {code!r}])"

    tree_of_three = over(over("import sys; print(1, flush=True); sys.stdin.read()"))
    with subprocess.Popen([sys.executable, "-c", tree_of_three], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as parent:
        try:
            assert parent.stdout.readline().strip() == "1"   # the last process has started
            tree = _descendants(parent.pid)
            assert len(tree) > len(_children(parent.pid)) >= 1
        finally:
            parent.stdin.close()


def test_a_failures_note_ends_with_the_exception_the_app_printed_on_lines_ci_keeps():
    """:func:`_ended_with`: the note is the end of the app's stderr as its own lines, not one line's repr of it, which
    CI's cut at 240 characters would end long before the exception. Past what the note keeps, within a pipe's 4 KiB on
    Windows (100 frames' CRLFs passed it: the child stopped in its print, this test in its readline, for the job's 3 h)."""
    frames = "\n".join(f'  File "frame_{i}.py", line {i}, in frame' for i in range(50))
    code = f"import sys; print({frames!r} + '\\nOSError: the cause', file=sys.stderr, flush=True); print('up', flush=True); sys.stdin.read()"
    served = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
    assert served.stdout.readline() == "up\n"
    failure = AssertionError("the page timed out")
    _ended_with(served, failure)
    note = failure.__notes__[0].splitlines()
    assert (note[0], note[-1]) == ("the app was still running; its stderr:", "OSError: the cause") and 2 < len(note) < 30
    assert max(map(len, note)) < 240
    silent = subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
    silent.wait(30)
    failure = AssertionError("the page timed out")
    _ended_with(silent, failure)
    assert failure.__notes__ == ["the app had ended, code 3; its stderr:\n"]


def test_ci_prints_each_failure_though_a_summary_outruns_its_head():
    """CI's steps run under bash's -e and pipefail, where a ``head`` that closes its pipe early fails its pipeline
    (141): each such line says ``|| true``, or the step stops before the lines after it print the failures."""
    lines = [line.strip() for file in (Path(__file__).parents[1] / ".github" / "workflows").glob("*.yml")
             for line in file.read_text(encoding="utf-8").splitlines() if "| head" in line]
    assert lines and [line for line in lines if not line.endswith("|| true")] == []


def test_the_frozen_app_runs_read_only_and_gives_the_same_verdicts(frozen_app, tmp_path, verify_argv, verdicts,
                                                                    monkeypatch):
    """The app holds no Unicorn, zig, capstone or GPL code (each name in it
    is Python's, PyInstaller's runtime, AzurKit's, a distribution's whose
    licence isn't GPL or a library :data:`LINKED` names, libquadmath's LGPL
    the one GNU licence, in numpy's Linux wheel; the runtime's readline is
    editline). On macOS its
    icon is AzurKit's: the .icns its Info.plist names is ``freeze.ICON``,
    byte for byte. Run read-only, with a fresh HOME and TMPDIR from an empty
    folder and the tests' no-window mode, its window path exits 1 at once,
    and it gives CPython's verdicts, finds the images' folder through
    platformdirs under that HOME, and leaves itself, that folder, HOME and
    TMPDIR as they were but for platformdirs' folders."""
    app_path, before = frozen_app
    owners = _owners(app_path)
    assert [name for name in owners if name.lower().startswith(NEVER)] == []
    held = sorted(f"{name}: {owner}" for name, owner in owners.items()
                  if ("GPL" in owner and owner != LINKED["libquadmath-"]) or owner == "unknown")
    assert not held, "\n".join(textwrap.wrap(", ".join(held), 200))   # lines CI keeps, where a dict's diff is cut at 40
    assert "readline" not in sys.builtin_module_names or __import__("readline").backend == "editline"
    if app_path.suffix == ".app":
        plist = plistlib.loads((app_path / "Contents" / "Info.plist").read_bytes())
        icon = app_path / "Contents" / "Resources" / plist["CFBundleIconFile"]
        assert (icon.name, icon.read_bytes() == freeze.ICON.read_bytes()) == (freeze.ICON.name, True)

    box = Sandbox(tmp_path, monkeypatch)
    assert box.run(app_path, timeout=30) == {"code": 1, "stdout": "", "stderr": WINDOW_REFUSED}   # the window path
    assert box.run(app_path, *verify_argv) == verdicts
    none = cpython("verify")
    assert none["code"] == 1 and f"put it at {box.dirs.user_data_path / 'usa.iso'}\n" in none["stderr"]
    assert box.dirs.user_data_path.is_relative_to(box.home)
    assert box.run(app_path, "verify") == none
    assert _tree(app_path) == before
    assert box.left() == []


def test_the_frozen_apps_page_builds_each_ported_packs_g1_golden_and_saves_cpythons_image(
        frozen_app, tmp_path, monkeypatch, browser, usa_iso, europe_iso):
    """``AzurKit serve`` from the frozen app (read-only, in a fresh HOME,
    TMPDIR and empty folder, in the tests' no-window mode) serves the page
    with the app's engine and its favicon, here driven in headless Chromium
    and in WebKit (the macOS window's engine): the page reads each image's own vanilla
    values of the sliders at its XBE's sites (``api/vanilla``), each ported
    pack builds its G1 case on both releases with CPython's report (one
    that requires others, with them), and Save
    (offered in the Downloads folder) writes the USA build of every pack
    where the page names, CPython's image byte for byte, but never over a
    file that is there; Copy link gives the site's link to that build's
    recipe and hashes (``sdk.preset_encode``), and the saved build, typed
    as the image, offers its recipe (``sdk.open_build``), which ticks every
    pack again. The page opens dark (D897), and its toggle picks light. The
    next launch starts from the image the last build read, opens in the
    theme the page picked, from its first paint (the app's own theme.js),
    and with the page's setup as it was left: every pack ticked (D915; all
    three remembered in platformdirs' config folder: the page's address, and
    so its storage, is new each launch); its ``host.json`` names the commit
    it was frozen from (About's: this checkout's HEAD). No CSP violation, no
    request but to the app's own server, and the app, the folder, HOME and
    TMPDIR are as they were but for platformdirs' folders and the saved build."""
    app_path, before = frozen_app
    box = Sandbox(tmp_path, monkeypatch)
    out = tmp_path / "out" / f"{usa_iso.stem} (AzurKit).iso"
    out.parent.mkdir()
    context, requests = browser.new_context(), []
    context.on("request", lambda request: requests.append(request.url))
    try:
        with box.serving(app_path) as url:
            page = context.new_page()
            _page.load(page, url)
            _page.until(page, "() => globalThis.azurkit?.ready", 60)
            assert page.evaluate("() => [azurkit.app, azurkit.dialogs]") == [True, False]
            _page.check_icons(page)
            for release, path in ((gate.USA, usa_iso), (gate.EUROPE, europe_iso)):
                cases = _g1.cases(release)
                _page.fill(page, "iso-path", str(path))
                assert _page.until(page, f"() => azurkit.vanilla?.release === '{release.name}' && azurkit.vanilla"
                                   ) == sdk.vanilla(str(path))
                for name, pack in mods.PACKS.items():   # one that requires others is built with them
                    _page.build(page, [name])
                    report = _page.built(page)
                    if not pack.requires:
                        _g1.check(report["result"], cases[name], name)
                    packs = {other: {} for other in (name, *pack.requires)}
                    assert report == sdk.image({"iso": str(path), "packs": packs})[1], name
            _page.fill(page, "iso-path", str(usa_iso))
            _page.build(page, list(mods.PACKS))
            report = _page.built(page)
            assert page.evaluate("() => document.querySelector('#out-path').value") == str(
                box.dirs.user_downloads_path / out.name)
            _page.fill(page, "out-path", str(out))
            saved = _save(page)
            made, _ = sdk.image({"iso": str(usa_iso), "packs": {name: {} for name in mods.PACKS}})
            with open(out, "rb") as f:
                sha256 = hashlib.file_digest(f, "sha256").hexdigest()
            assert saved == report | {"out": str(out), "size": made.size, "sha256": sha256}
            assert (out.stat().st_size, sha256) == (made.size, made.sha256())
            assert _save(page) == f"{out} exists: choose another name, or delete it first"
            _page.click(page, "share")
            assert _page.until(page, "() => azurkit.link") == app.SITE + sdk.preset_encode(
                {"packs": {name: {} for name in mods.PACKS}}, report)
            _page.tick(page, [])
            _page.fill(page, "iso-path", str(out))
            assert _page.until(page, "() => azurkit.opened") == json.loads(json.dumps(sdk.open_build(str(out))))
            _page.click(page, "load-build")
            assert list(_page.ticked(page)) == list(mods.PACKS)
            setup = {"ticked": list(mods.PACKS), "values": {}, "xbr": []}   # the recipe loaded becomes it (D915)
            assert _page.until(page, f"""async () => {{ const setup = (await (await fetch('host.json')).json()).setup;
                return setup?.ticked.length === {len(mods.PACKS)} && setup; }}""") == setup
            assert page.evaluate("() => azurkit.theme") == "dark"
            _page.click(page, "theme")
            assert _page.until(page, "async () => (await (await fetch('host.json')).json()).theme === 'light'")
            _page.check_csp(page)
        origin = url.partition("/?")[0]
        assert [seen for seen in requests if not seen.startswith(f"{origin}/")] == []
        with box.serving(app_path) as url:
            with urllib.request.urlopen(url.replace("/?token=", "/host.json?token="), timeout=30) as reply:
                host = json.load(reply)
            assert [host["iso"], host["theme"], host["setup"], host["commit"]] == [
                str(usa_iso), "light", setup, _head()]
            page = context.new_page()
            assert _page.first_paint(page, url) == ["light", "rgb(232, 236, 241)"]
            assert page.evaluate("() => [azurkit.theme, document.documentElement.dataset.theme]") == ["light"] * 2
            assert [list(_page.ticked(page)), page.evaluate("() => document.querySelector('#status').textContent")] == [
                list(mods.PACKS), f"Restored your last setup: {len(mods.PACKS)} packs on. Reset to defaults clears it."]
    finally:
        context.close()
        out.unlink(missing_ok=True)
    assert _tree(app_path) == before
    assert box.left() == []


def _get(url: str, path: str) -> bytes:
    """GET ``path`` from the page at ``url`` (its token in the query)."""
    parts = urllib.parse.urlsplit(url)
    with urllib.request.urlopen(f"http://{parts.netloc}/{path}?{parts.query}", timeout=60) as reply:
        return reply.read()


def test_the_frozen_app_loads_this_platforms_compiled_library(frozen_app, tmp_path, monkeypatch):
    """Step 4.3r4e: the frozen app reports this platform's library loaded,
    not the Python twins (Linux's ``.so`` was left out of the app, so that
    app ran them with no error)."""
    box = Sandbox(tmp_path, monkeypatch)
    got = freeze.report(frozen_app[0], env=box.env, cwd=box.cwd)
    assert (got["loaded"], got["library"], got["kernels"]) == (True, native.target(), list(native.KERNELS))


def test_the_frozen_app_serves_the_pictures_the_page_ships(frozen_app, tmp_path, monkeypatch):
    """Step 4.3f (D961): the frozen app (read-only, in a fresh HOME, no
    image) answers ``api/art`` with the tracker's shipped index (with the
    detail pictures' factors, Step 4.3l) and serves each of its pictures
    (the detail pictures too) and the Characters tab's from the bundle, the
    checkout's files byte for byte, and leaves itself as it was."""
    app_path, before = frozen_app
    box, v = Sandbox(tmp_path, monkeypatch), tracking.ART_VERSION
    shipped = record_goldens.kept_files((record_goldens.ART, record_goldens.PICTURES))
    with box.serving(app_path) as url:
        replies = []
        _post(url, "api/art", {}, replies)
        served = {rel: _get(url, rel.removeprefix("web/")) for rel in shipped if rel != "web/art/index.json"}
    named = json.loads(shipped["web/art/index.json"])
    assert replies == [{"version": v, "index": json.loads(shipped[f"web/art/{v}/maps.json"]),
                        "icons": named["icons"], "detail": named["detail"]}]
    assert any(rel.startswith(f"web/art/{v}/detail/") for rel in served)
    assert served == {rel: data for rel, data in shipped.items() if rel in served} and len(served) == len(shipped) - 1
    assert _tree(app_path) == before


def test_the_frozen_app_dresses_the_player_in_a_species_body_as_its_golden(frozen_app, tmp_path, monkeypatch, usa_iso):
    """``AzurKit build --character`` from the frozen app (the swap, its data
    and numpy in the bundle), read-only in a fresh HOME and TMPDIR, writes
    G3's keylord case: each file G3 records is its golden's, and the app and
    the sandbox are as they were but for the build it wrote. So does its
    page's Build and Save (``AzurKit serve``: the swap in the app's engine
    process, its parallel work in that process's pool, both spawned from
    the bundle, Step 4.3i)."""
    app_path, before = frozen_app
    box = Sandbox(tmp_path, monkeypatch)
    out = tmp_path / "out" / "keylord.iso"
    out.parent.mkdir()
    case = "randomize-full:player-character=keylord"
    golden = record_goldens.recorded("pipelines.json")[case]

    def files() -> dict[str, str]:
        with iso.Reader(out) as r:
            return {f: hashlib.sha256(r.read(f)).hexdigest() for f in golden if f != "ISO"}
    done = box.run(app_path, "build", "--iso", str(usa_iso), "--out", str(out), "--character",
                   json.dumps({"species": "keylord"}), timeout=900)
    try:
        assert done["code"] == 0, done["stderr"][-2000:]
        assert files() == {f: sha for f, sha in golden.items() if f != "ISO"}
        out.unlink()
        with box.serving(app_path) as url:
            built, saved = [], []
            _post(url, "api/build", {"iso": str(usa_iso), "character": {"species": "keylord"}, "packs": {
                name: {} for name, pack in mods.PACKS.items() if pack.default_on}}, built, timeout=900)
            _post(url, "api/save", {"recipe": built[0]["recipe"], "out": str(out), "build": built[0]["build"]},
                  saved, timeout=900)
        assert saved[0]["saved"]["out"] == str(out), saved
        assert files() == {f: sha for f, sha in golden.items() if f != "ISO"}
    finally:
        out.unlink(missing_ok=True)
    assert _tree(app_path) == before
    assert box.left() == []


def _save(page) -> dict | str:
    """Click Save: what the engine saved, or the page's refusal."""
    page.evaluate("() => { azurkit.saved = null; document.querySelector('#save').click(); }")
    return _page.until(page, """() => azurkit.saved || document.querySelector("#status").classList.contains("error")
                                && document.querySelector("#status").textContent""")


def test_the_apps_window_path_exits_at_once_under_the_tests(monkeypatch, tmp_path):
    """No test opens a window or a browser tab on the owner's screen (D839):
    the run sets the no-window mode, under which ``app.main`` serves nothing
    and never reaches the window or the browser (the session checks it first,
    with all three planted to raise), and ``python -m azurkit`` with no
    arguments (the page) exits 1 within seconds. ``serve`` reaches neither
    in any mode: it prints the page's address and stops when its input
    ends. The stores it installs (``app.swapcache``) are this test's
    folder's, its engine process's too, and gone after it."""
    from azurkit.app import swapcache
    from azurkit.tools import characters

    assert os.environ.get(app.NO_WINDOW)
    monkeypatch.setattr(gate, "STAMPS", gate.STAMPS)   # put back after the test: no later test writes the user's
    monkeypatch.setattr(characters, "CACHE", characters.CACHE)
    monkeypatch.setattr(swapcache, "root", lambda: tmp_path / "cache")
    monkeypatch.setattr(swapcache, "key_file", lambda: tmp_path / "data" / "cache.key")
    _home(monkeypatch, tmp_path)   # the engine process's platformdirs

    def opened(*args, **kwargs):
        raise AssertionError("the window path ran under the tests")
    monkeypatch.setattr(app, "_window", opened)
    monkeypatch.setattr(app.webbrowser, "open", opened)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    for mode in ({}, {app.NO_WINDOW: ""}):
        with monkeypatch.context() as m, contextlib.redirect_stdout(io.StringIO()) as out:
            m.setattr(os, "environ", os.environ | mode)
            assert app.main(["serve"]) == 0
        assert out.getvalue().startswith("http://127.0.0.1:")
        assert all(p.is_relative_to(tmp_path) for p in (gate.STAMPS.file, characters.CACHE.kept.folder,
                                                        characters.CACHE.kept.signer.file))
    monkeypatch.setattr(app, "serve", opened)
    assert app.main() == 1

    done = subprocess.run([sys.executable, "-m", "azurkit"], capture_output=True, text=True, timeout=30)
    assert (done.returncode, done.stdout, done.stderr) == (1, "", WINDOW_REFUSED)


def test_the_trackers_spoiler_on_a_shaped_plan_takes_its_openers_from_the_engine_once_and_no_view_ahead_asks(monkeypatch, tmp_path):
    """The engine works a shaped plan's openers out ahead: the server's process, which holds a Logic of its own, doesn't
    again (5 s with no record); only a click asks, as a parked job ahead would hold the lock a View waits on."""
    from azurkit.tools.randomizer.planner.settings import Settings, share_encode

    _home(monkeypatch, tmp_path)
    asked = []

    class Beside(engine.Here):
        def call(self, job, *args, progress=None, fore=None):
            asked.append(job)
            return super().call(job, *args, progress=progress, fore=fore)
    server = app.serve(_page.WEB, Beside())
    try:
        recipe = {"seed": "1", "share": share_encode(Settings(3, "hard", {}, seed_difficulty=3), [])}
        assert server.prefetch({"gen": 1, "recipe": recipe, "view": {"spoiler": True}}) == {"ahead": True}
        plan = server.plan({"recipe": recipe})["plan"]
        assert asked == ["plan"] and server.slots.job("view") is None
        shown = server.track({"given": {"plan": plan, "spoiler": True}})
        assert asked[1:] == ["openers"] and shown["head"]["requires"]["openers"]
        assert server.track({"given": {"plan": plan, "spoiler": True, "marks": {"collected": []}}})["head"]["requires"][
            "openers"] == shown["head"]["requires"]["openers"] and asked[1:] == ["openers"]
    finally:
        server.close()
        # The plan's openers ahead reach on, low, past the close (a Here engine's; the app's end with its process): left
        # running on a busy machine they counted kernel calls into a later test's host.json (Step 4.4ci55).
        for thread in threading.enumerate():
            if thread.name == "azurkit-openers":
                thread.join(120)
                assert not thread.is_alive()


def test_the_apps_window_opens_on_the_remembered_themes_ground(monkeypatch):
    """The window shows the remembered theme's ground (``web/app.css``'s
    ``--bg``) until the page draws, so a player who picked light never
    sees a dark first frame (D897); a stand-in pywebview records the
    window, so none opens (D839)."""
    grounds = re.findall(r"--bg: (#[0-9a-f]{6})", (_page.WEB / "app.css").read_text(encoding="utf-8"))
    opened = []

    class Closing:
        def __iadd__(self, handler):
            return self

    webview, errors = types.ModuleType("webview"), types.ModuleType("webview.errors")
    errors.WebViewException = type("WebViewException", (Exception,), {})
    webview.errors = errors
    webview.create_window = lambda **window: opened.append(window) or types.SimpleNamespace(
        events=types.SimpleNamespace(closing=Closing()))
    webview.start = lambda **options: None
    monkeypatch.setitem(sys.modules, "webview", webview)
    monkeypatch.setitem(sys.modules, "webview.errors", errors)
    for theme in app.THEMES:
        monkeypatch.setattr(app, "_kept", lambda: {"theme": theme})
        assert app._window(types.SimpleNamespace(url="http://127.0.0.1:1/", quit=None, window=None))
    assert [window["background_color"] for window in opened] == grounds == ["#0d1117", "#e8ecf1"]


def test_the_apps_page_answers_only_its_launchs_token_on_127_0_0_1(tmp_path):
    """The first request carries the token in its URL and gets it back as
    a cookie; later ones carry the cookie, which a second launch's leaves
    alone. Without either, with another host named, or outside the page's
    folder, the server refuses. ``host.json`` names the app's engine; the
    engine takes a call only as JSON from the page's own origin, and the
    file dialogs only in a window; ``api/theme`` refuses a theme the page
    has none of, by name."""
    page = tmp_path / "page"
    page.mkdir()
    (page / "index.html").write_text("<title>t</title>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("s", encoding="utf-8")
    server, second = app.serve(page), app.serve(page)

    def get(path: str, to: app.Server | None = None, data: bytes | None = None,
            **headers: str) -> tuple[int, str | None, bytes]:
        request = urllib.request.Request(f"http://{(to or server).host}{path}", data, headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.headers.get("Set-Cookie"), response.read()
        except urllib.error.HTTPError as refused:
            return refused.code, None, b""

    try:
        assert server.url == f"http://127.0.0.1:{server.server_port}/?token={server.token}"
        status, cookie, body = get(f"/?token={server.token}")
        assert (status, body) == (200, b"<title>t</title>")
        assert cookie == f"{server.cookie}={server.token}; Path=/; HttpOnly; SameSite=Strict"
        sent = {"Cookie": f"{server.cookie}={server.token}"}
        assert get("/index.html", **sent)[:2] == (200, None)
        jar = dict(c.partition(";")[0].split("=", 1) for c in (cookie, get(f"/?token={second.token}", second)[1]))
        assert get("/", Cookie="; ".join(f"{k}={v}" for k, v in jar.items()))[0] == 200   # a browser's jar, by host
        assert [get(path, **headers)[0] for path, headers in (
            ("/", {}), ("/?token=x", {}), ("/", {"Cookie": f"{server.cookie}=x"}),
            ("/", sent | {"Host": f"rebound.example:{server.server_port}"}),
            ("/?token=%C3%A9", {}), ("/../secret.txt", sent), ("/%2e%2e/secret.txt", sent), ("/a%00b", sent),
            ("/none.js", sent))] == [
            403, 403, 403, 403, 403, 404, 404, 404, 404]
        host = json.loads(get("/host.json", **sent)[2])
        assert (host["engine"], host["dialogs"], host["catalog"]) == ("app", False, sdk.catalog())
        own, as_json = {"Origin": f"http://{server.host}"}, {"Content-Type": "application/json"}
        assert get("/api/cancel", data=b"{}", **sent, **own, **as_json)[::2] == (200, b"{}")
        assert json.loads(get("/api/theme", data=b'{"theme": "blue"}', **sent, **own, **as_json)[2]) == {
            "refused": "theme: 'blue' is none of dark, light"}
        assert [get(path, data=b"{}", **headers)[0] for path, headers in (
            ("/api/cancel", own | as_json), ("/api/cancel", sent | own | {"Content-Type": "text/plain"}),
            ("/api/cancel", sent | {"Origin": "http://evil.example"} | as_json),
            ("/api/choose", sent | own | as_json), ("/api/none", sent | own | as_json))] == [403, 403, 403, 404, 404]
    finally:
        server.close()
        second.close()


def test_a_read_of_the_apps_config_never_costs_a_write_of_it_what_it_remembers(tmp_path, monkeypatch):
    """Windows refuses to replace a file that is open: a read in this process
    waits for the write, and the write outlasts a moment another process
    holds it. The refusal was swallowed, and the frozen page's setup was lost
    for good (run 41372636477's Windows job)."""
    _home(monkeypatch, tmp_path / "home")
    real, refused = Path.replace, []

    def replace(self, target):
        if len(refused) < 3:
            refused.append(target)
            raise PermissionError(13, "held open")
        return real(self, target)
    monkeypatch.setattr(Path, "replace", replace)
    app._remember(theme="light")
    assert (len(refused), app._kept()) == (3, {"theme": "light"})
    with app._REMEMBERING:
        reader = threading.Thread(target=app._kept, daemon=True)
        reader.start()
        reader.join(0.2)
        assert reader.is_alive()
    reader.join(10)
    assert not reader.is_alive()


def test_what_the_app_cant_remember_it_says_on_its_stderr_and_goes_on(tmp_path, monkeypatch, capsys):
    """A lost setup was silent: a frozen page's poll for it ran on with an empty stderr (run 41372636477's Windows job),
    so a next run couldn't name its cause. ``serving`` holds a clean end's stderr empty, so it fails by this line."""
    (tmp_path / "a file").write_text("", encoding="utf-8")
    monkeypatch.setattr(app, "_config", lambda: tmp_path / "a file" / "app.json")
    app._remember(setup={"seed": "1"}, theme="light")
    assert capsys.readouterr().err.startswith("azurkit: can't remember setup, theme: ")
    with open(os.devnull, encoding="utf-8") as closed:
        pass
    monkeypatch.setattr(sys, "stderr", closed)   # a build goes on with no stderr left to say it on
    app._remember(theme="light")


def test_a_config_read_refused_for_a_moment_costs_no_remembered_setting_and_one_refused_past_the_waits_writes_nothing(
        tmp_path, monkeypatch, capsys):
    """Windows refuses to read a file another process holds open for a moment (a virus scanner on the config just
    replaced), and such a read was taken for an empty config: the next remember (a build's image path) wrote its own key
    alone, the player's setup lost, a likely cause of a relaunch with no setup (run 41678038275, Step 4.4ci16). The read
    is tried again on the replace's waits, a page's (host.json) too; one refused past them writes nothing and says why;
    a file that holds no settings is written over, and said."""
    _home(monkeypatch, tmp_path / "home")
    setup = {"ticked": ["fps_unlock"]}
    app._remember(setup=setup, theme="light")
    real, held = Path.read_text, [0]

    def read_text(self, *args, **kwargs):
        if self == app._config() and held[0]:
            held[0] -= 1
            raise PermissionError(13, "held open")
        return real(self, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read_text)
    held[0] = 3
    app._remember(iso="a.iso")
    assert (held[0], capsys.readouterr().err) == (0, "")
    held[0] = 2
    assert app._kept() == {"setup": setup, "theme": "light", "iso": "a.iso"}
    held[0] = len(app.WAITS)
    app._remember(theme="dark")
    assert (held[0], capsys.readouterr().err) == (0, "azurkit: can't remember theme: [Errno 13] held open\n")
    assert app._kept() == {"setup": setup, "theme": "light", "iso": "a.iso"}   # nothing written
    app._config().write_text("[]", encoding="utf-8")
    app._remember(theme="dark")
    assert (app._kept(), capsys.readouterr().err) == ({"theme": "dark"}, "azurkit: the config held no settings (a JSON "
                                                      "list, not an object): remembering theme writes it over\n")


def test_the_app_remembers_the_pages_setup_in_its_config_beside_the_theme(tmp_path, monkeypatch):
    """``api/setup`` remembers the page's setup (D915) in the app's config,
    beside the theme, written whole; ``host.json`` gives it to the next
    page, the config read once (Step 4.4ci16), and ``api/restore`` gives back what of it still applies, the rest
    named (``sdk.restore``). ``null`` forgets it, and a setup holding
    anything but pack and setting names, numbers and config.xbr ``set``
    cells (an image's path as a pack or setting name, a ``replace_bytes``,
    a character's recipe file) is refused by name, the config as it was."""
    _home(monkeypatch, tmp_path / "home")   # where the app remembers
    (page := tmp_path / "page").mkdir()
    (page / "index.html").write_text("<title>t</title>", encoding="utf-8")
    server = app.serve(page)

    def call(path: str, body: object = None) -> dict:
        if body is None:
            with urllib.request.urlopen(server.url.replace("/?", f"/{path}?"), timeout=10) as reply:
                return json.load(reply)
        replies = []
        _post(server.url, path, body, replies)
        return replies[0]

    cell = {"op": "set", "file": "gamedata/config.xbr", "table": "critters_damage", "entity": "golem",
            "prop": "hitPoints", "value": 321}
    setup = {"ticked": ["fps_unlock", "qol_retired"], "values": {"fps_unlock": {"target_fps": 120}}, "xbr": [cell]}
    refused = {   # a path or game bytes anywhere in a setup
        "setup: an object of ticked, values, xbr, randomizer, character, community only, or null": {"ticked": [], "iso": "/a.iso"},
        "setup: ticked holds pack names only": {"ticked": ["/a.iso"]},
        "setup: values holds {pack: {setting: number}} only": {"values": {"fps_unlock": {"target_fps": "/a.iso"}}},
        "setup: xbr holds config.xbr set operations only (Q174)": {"xbr": [
            {"op": "replace_bytes", "file": "gamedata/config.xbr", "offset": 0, "value": "00", "expected": "00"}]},
        "xbr op 1 (set): no key 'expected' (its keys: op, file, table, entity, prop, value)": {
            "xbr": [cell | {"expected": "00"}]},
        "setup: randomizer: not an object of on, seed, settings, obsidian_cost": {"randomizer": {"iso": "/a.iso"}},
        "setup: the character (a character travels by name and numbers (Q174), never its recipe file's path "
        "(variant_file): share a built-in or community variant)": {"character": {"species": "a", "variant_file": "/a"}},
    }

    def kept() -> list:
        """The config, and the files in its folder."""
        return [json.loads(app._config().read_text(encoding="utf-8")),
                sorted(p.name for p in app._config().parent.iterdir())]

    try:
        assert [call("api/theme", {"theme": "light"}), call("api/setup", {"setup": setup})] == [{}, {}]
        assert kept() == [{"theme": "light", "setup": setup}, ["app.json"]]
        with monkeypatch.context() as counting:   # host.json reads the config once, its theme and start image too
            reads, real = [], Path.read_text
            counting.setattr(Path, "read_text", lambda path, *args, **kwargs: (
                reads.append(path) if path == app._config() else None, real(path, *args, **kwargs))[1])
            host = call("host.json")
        assert [reads, host["theme"], host["setup"]] == [[app._config()], "light", setup]
        assert call("api/restore", {"setup": setup}) == sdk.restore(setup) == {
            "ticked": ["fps_unlock"], "values": {"fps_unlock": {"target_fps": 120}}, "xbr": [cell],
            "dropped": ["qol_retired (no such pack)"]}
        assert [call("api/setup", {"setup": given}) for given in refused.values()] == [
            {"refused": why} for why in refused]
        assert kept() == [{"theme": "light", "setup": setup}, ["app.json"]]
        assert call("api/setup", {"setup": None}) == {}
        assert [kept(), call("host.json")["setup"]] == [[{"theme": "light"}, ["app.json"]], None]
    finally:
        server.close()


def _beamlord_source(tmp_path: Path, monkeypatch) -> Path:
    """A folder source (a clone of Azurik-Custom-Content) listing Beamlord alone, an empty content folder, the app's
    config under ``tmp_path`` and no source from the environment."""
    from azurkit.tools.characters import _player_variants, content

    _home(monkeypatch, tmp_path / "home")   # where the app remembers
    monkeypatch.delenv(sdk.SOURCE_ENV, raising=False)
    monkeypatch.setattr(content, "ROOT", tmp_path / "content")
    source = tmp_path / "clone"
    recipe = json.dumps({"beamlord": json.loads(_player_variants.BUILTIN.read_text(encoding="utf-8"))["beamlord"]})
    (source / "variants/beamlord").mkdir(parents=True)
    (source / "variants/beamlord/variant.json").write_text(recipe, encoding="utf-8")
    (source / "manifest.json").write_text(json.dumps(content.filled({
        "format": content.FORMAT, "schema_version": 1, "entries": [{
            "id": "beamlord", "kind": "variant", "title": "Beamlord", "author": "Azurik-Modding-Hub", "licence": "MIT",
            "version": 1, "files": [{"path": "variants/beamlord/variant.json"}], "requires": []}]},
        lambda path: (source / path).read_bytes())), encoding="utf-8")
    return source


def test_the_apps_characters_tab_installs_from_a_folder_source_and_draws_a_models_two_pictures(
        tmp_path, monkeypatch, usa_iso):
    """The app's half of the Characters tab (Step 4.3d): ``api/content`` reads Azurik-Custom-Content from a folder
    (a clone), ``api/install`` copies an entry into the content folder, every file checked, and ``api/pickers``
    lists its variant marked community; ``api/content_source`` remembers the folder for the next page
    (``host.json``); ``api/preview`` draws the chosen model from the front and from behind, two PNGs."""
    source = _beamlord_source(tmp_path, monkeypatch)
    (page := tmp_path / "page").mkdir()
    (page / "index.html").write_text("<title>t</title>", encoding="utf-8")
    server = app.serve(page)

    def call(path: str, body: dict) -> dict:
        replies = []
        _post(server.url, path, body, replies)
        return replies[0]
    try:
        read = call("api/content", {"source": str(source)})
        assert [(e["id"], e["state"]) for e in read["entries"]] == [("beamlord", "install")] and read["why"] is None
        installed = call("api/install", {"id": "beamlord", "source": str(source)})
        assert [(e["id"], e["state"], e["installed"]) for e in installed["entries"]] == [("beamlord", "installed", 1)]
        view = call("api/pickers", {"given": {"iso": str(usa_iso), "character": {"species": "beamlord"},
                                              "content": {"manifest": read["manifest"]}}})
        assert [v["name"] for e in view["community"] for v in e["variants"]] == ["beamlord"]
        assert view["chosen"]["community"] == "beamlord" and view["chosen"]["info"][-1][1].startswith(
            "community beamlord v1, recipe 628f6d09ad7b")
        assert call("api/content_source", {"source": str(source)}) == {}
        with urllib.request.urlopen(server.url.replace("/?", "/host.json?"), timeout=10) as reply:
            assert json.load(reply)["content_source"] == str(source)
        drawn = call("api/preview", {"recipe": {"iso": str(usa_iso), "character": {"species": "keylord"}}})
        pictures = [base64.b64decode(drawn[v]) for v in ("front", "back")]
        assert all(len(png) > 1000 and png[1:4] == b"PNG" for png in pictures) and pictures[0] != pictures[1]
    finally:
        server.close()


def test_the_apps_characters_tab_lists_the_community_models_under_the_species_beside_content_from(
        browser, tmp_path, monkeypatch):
    """D1035 in the app's page: the community entries (its remembered folder source's Beamlord, with its Install
    button) sit under the species list and above Content from and its Reset, all in the list's column, at every
    width (``test_site.py``'s ``CHARS_LAYOUT``, which the site's Characters test reads too); Install installs it. The
    Weapon box's Preview works as on the site (``weapon_previews``)."""
    from tests.test_site import CHARS_LAYOUT, weapon_previews

    app._remember(content_source=str(_beamlord_source(tmp_path, monkeypatch)))
    server = app.serve(_page.WEB)
    try:
        page = browser.new_page()
        page.goto(server.url)
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        _page.click(page, "tab-characters")
        entry = """document.querySelector('#char-community .entry[data-entry="beamlord"]')"""
        _page.until(page, f"() => {entry}?.querySelector('button')?.textContent === 'Install'", 120)
        weapon_previews(page)
        for width in (1280, 1024, 900, 700):
            page.set_viewport_size({"width": width, "height": 800})
            assert page.evaluate(CHARS_LAYOUT) == [True] * 4, width
        page.evaluate(f"() => {entry}.querySelector('button').click()")
        _page.until(page, f"() => {entry}?.querySelector('.model[data-model=\"beamlord\"]')", 120)
        assert page.evaluate(CHARS_LAYOUT)[3] is True
        _page.check_csp(page)
        page.close()
    finally:
        server.close()


def test_the_apps_saves_read_a_folder_and_an_hdd_image_and_save_a_new_folder_by_path(tmp_path, monkeypatch):
    """The app's Saves (Step 4.7e): ``api/saves`` opens a slot's folder and an HDD image's slots by path, a network path
    refused before anything opens; an edit saves as a new folder, never over one there; a BIOS file too large to be
    one is refused before it is read; no zip, the site's."""
    from azurkit.tools import saves as savekit

    from tests import test_saves as made

    _home(monkeypatch, tmp_path / "home")
    monkeypatch.setattr(app, "_downloads", lambda: tmp_path / "downloads")
    (tmp_path / "downloads").mkdir()
    (page := tmp_path / "page").mkdir()
    (page / "index.html").write_text("<title>t</title>", encoding="utf-8")
    folder = tmp_path / "slot" / made.ID
    for path, data in made._files().items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_bytes(data)
    hdd = made._qcow2(tmp_path / "hdd.qcow2", made._Fatx({"UDATA": {"4d530007": {made.ID: made._slot_tree(1)}}}).chunks())
    big = tmp_path / "big.bin"
    with open(big, "wb") as f:
        f.truncate(17 << 20)
    server = app.serve(page)

    def call(given: dict) -> dict:
        replies = []
        _post(server.url, "api/saves", {"given": given}, replies)
        return replies[0]
    try:
        assert "never read" in call({"do": "open", "folder": "//host/share/slot"})["refused"]
        assert "never read" in call({"do": "open", "image": "/net/host/hdd.qcow2"})["refused"]
        assert [s["id"] for s in call({"do": "open", "image": str(hdd)})["slots"]] == [made.ID]
        assert [s["id"] for s in call({"do": "open", "folder": str(folder)})["slots"]] == [made.ID]
        assert call({"do": "edit", "id": made.ID, "edits": [{"file": "magic.sav", "line": 0, "value": "2"}]})["changes"]
        assert "the app reads your files by path" in call({"do": "zip", "id": made.ID})["refused"]
        assert "is no BIOS file" in call({"do": "sign", "id": made.ID, "iso": str(hdd), "flash_file": str(big)})["refused"]
        saved = call({"do": "save", "id": made.ID})
        assert saved == {"out": str(tmp_path / "downloads" / made.ID)}
        assert savekit.Slot.read(saved["out"]).files["magic.sav"].startswith(b"fileversion=1\n2\n")
        assert "exists" in call({"do": "save", "id": made.ID})["refused"]
    finally:
        server.close()


def test_the_apps_replace_files_holds_the_picked_file_and_refuses_a_share_or_an_unpicked_path(tmp_path, monkeypatch, usa_iso):
    """The app's Replace files (Step 4.7d, SEC-11): ``api/replace`` makes the picked file's entry and holds its path for
    this launch; a network share, a device path and a file the build owns are refused with nothing read; a build takes
    the file the server holds, whatever path a page sends (a recipe's own ``picked`` is dropped, a Save's with no
    ``files`` too), and its reply carries no computer path; a recipe naming a file not picked here stops by name."""
    from azurkit.edits import files

    _home(monkeypatch, tmp_path / "home")
    (page := tmp_path / "page").mkdir()
    (page / "index.html").write_text("<title>t</title>", encoding="utf-8")
    mine = tmp_path / "mine.bin"
    mine.write_bytes(b"mine" * 1000)
    other = tmp_path / "other.bin"
    other.write_bytes(b"other" * 1000)
    server = app.serve(page)

    def call(path: str, body: dict) -> dict:
        replies = []
        _post(server.url, path, body, replies)
        return replies[0]
    name = "gamedata/config.xbr"
    try:
        for given in ("//host/share/x", "\\\\host\\share\\x", "\\\\?\\C:\\x", "/net/host/x"):
            assert "never read" in call("api/replace", {"path": name, "file": given})["refused"], given
        assert "the packs' file" in call("api/replace", {"path": "default.xbe", "file": str(mine)})["refused"]
        entry = call("api/replace", {"path": name, "file": str(mine)})["entry"]
        assert entry == files.entry(name, mine.read_bytes())
        lost = files.entry("gamedata/fx.xbr", b"x")
        assert "isn't picked in this session" in call("api/build", {"iso": str(usa_iso), "packs": {}, "files": [lost]})["refused"]
        built = call("api/build", {"iso": str(usa_iso), "packs": {}, "files": [entry], "picked": {name: str(other)}})
        assert built["report"]["result"][name] == entry["sha256"] and "picked" not in built["recipe"]
        assert str(mine) not in json.dumps(built)
        saved = []
        monkeypatch.setattr(server.engine, "call", lambda job, recipe, *_, **__: saved.append((job, recipe)) or {})
        plain = {"iso": str(usa_iso), "packs": {}}
        call("api/save", {"recipe": plain | {"picked": {name: str(other)}}, "out": str(tmp_path / "saved.iso")})
        assert saved == [("save", plain)]
    finally:
        server.close()


def test_the_apps_patches_tab_installs_a_community_pack_and_builds_it_with_its_packs_locked(
        browser, tmp_path, monkeypatch, usa_iso):
    """The app's community group (Step 4.3k): an empty list says so; a folder source's pack lists with its tick greyed
    (Install it first) until its Install, then its tick sets and locks the built-in rows it names, a Build carries its
    layer, a relaunch restores it with the rows as they were before it, and its untick gives them back. The setup's
    way to the relaunch is held at each step by name (Step 4.4ci16): Windows' WebKit once relaunched to the rows
    unlocked with no status (no "Restored your last setup"), so with no setup to restore (run 41678038275)."""
    from azurkit.tools.characters import content

    from tests import test_community as made

    _home(monkeypatch, tmp_path / "home")
    source, _ = made._installed(tmp_path, monkeypatch, {"hard": made.HARD})
    (empty := tmp_path / "none").mkdir()
    (empty / "manifest.json").write_text(json.dumps({"format": content.FORMAT, "schema_version": 1, "entries": []}),
                                         encoding="utf-8")
    app._remember(content_source=str(empty))
    row = """document.querySelector('.cpack[data-community="hard"]')"""
    hp = """document.getElementById("player_max_hp.starting_hp")"""

    def kept(when: str) -> None:   # the app's config holds the setup with the pack (api/setup, 250 ms after a change)
        end = time.monotonic() + 60
        while (app._kept().get("setup") or {}).get("community") != [{"id": "hard"}]:
            assert time.monotonic() < end, f"{when}: the app's config holds no setup with hard in 60 s: {app._kept()}"
            time.sleep(0.1)

    for launch in (1, 2):
        server = app.serve(_page.WEB)
        try:
            page = browser.new_page()
            page.goto(server.url)
            _page.until(page, "() => globalThis.azurkit?.ready", 120)
            if launch == 2:
                assert page.evaluate("() => azurkit.remembered?.community ?? null") == [{"id": "hard"}], (
                    f"the relaunch's page has no setup with hard to restore: {app._kept()}")
            if launch == 1:
                page.evaluate("() => { document.getElementById('community-group').open = true; }")
                _page.until(page, "() => document.getElementById('community-note').textContent.startsWith('No community')",
                            60)
                page.evaluate(f"""() => {{ const b = document.getElementById('community-source'); b.value = {json.dumps(
                    str(source))}; b.dispatchEvent(new Event('change', {{ bubbles: true }})); }}""")
                _page.until(page, f"() => {row}?.querySelector('input').disabled && {row}.textContent.includes('Install it first')",
                            60)
                page.evaluate(f"() => {row}.querySelector('button').click()")
                _page.until(page, f"() => {row}?.querySelector('input') && !{row}.querySelector('input').disabled", 60)
                assert page.evaluate("() => document.getElementById('char-source').value") == str(source)   # one setting
                page.evaluate(f"""() => {{ const b = {hp}; b.closest('.pack').querySelector('input[data-pack]').click();
                    b.value = '175'; b.dispatchEvent(new Event('input', {{ bubbles: true }})); }}""")
                page.evaluate(f"() => {row}.querySelector('input').click()")
            _page.until(page, f"() => {hp}.value === '150' && {hp}.disabled && {hp}.closest('.pack').classList.contains('owned')"
                              f" && {hp}.closest('.pack').querySelector('input[data-pack]').disabled", 60)
            if launch == 1:
                kept("launch 1's tick")
            if launch == 2:
                page.evaluate(f"() => {row}.querySelector('input').click()")
                _page.until(page, f"() => {hp}.value === '175' && !{hp}.disabled", 60)
                page.evaluate(f"() => {row}.querySelector('input').click()")
            _page.fill(page, "iso-path", str(usa_iso))
            _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
            page.evaluate("() => document.getElementById('build').click()")
            _page.until(page, "() => azurkit.build || document.getElementById('status').classList.contains('error')", 300)
            assert "community hard" in [la["id"] for la in page.evaluate("() => azurkit.build.report.layers")]
            assert page.evaluate("() => azurkit.build.recipe.community")[0]["id"] == "hard"
            assert " · community hard" in page.evaluate("() => document.getElementById('status').textContent")
            _page.until(page, "() => azurkit.kept?.includes('community')", 60)   # remembered a moment after the change
            kept(f"launch {launch}'s build")   # the build's own remember (the image's path) keeps the rest
            _page.check_csp(page)
            page.close()
        finally:
            server.close()
    assert app._kept()["setup"]["values"]["player_max_hp"]["starting_hp"] == 175   # as it was before the pack


def test_the_apps_characters_tab_remembers_show_objects_across_a_relaunch(browser, tmp_path, monkeypatch):
    """D1034 in the app's page: Show objects, off at first (102 species listed, the count line naming the 76 objects
    hidden), ticked is remembered in the app's config (``api/show_objects``), so the next launch's page lists all 178;
    unticked, the config forgets it; ``api/show_objects`` refuses anything but true or false, the config as it was."""
    _home(monkeypatch, tmp_path / "home")
    shown = """() => [document.getElementById("char-objects").checked, document.getElementById("char-count").textContent
        .split(" · ")[0], document.querySelectorAll("#char-species .model").length]"""
    for launch, ticked in ((1, False), (2, True)):
        server = app.serve(_page.WEB)
        try:
            page = browser.new_page()
            page.goto(server.url)
            _page.until(page, "() => globalThis.azurkit?.ready", 120)
            _page.click(page, "tab-characters")
            _page.until(page, "() => azurkit.characters.state.view", 120)
            assert page.evaluate(shown) == ([True, "178 species, 73 not yet tested", 178] if ticked
                                            else [False, "102 species, 76 objects hidden", 102]), launch
            _page.click(page, "char-objects")
            want = None if ticked else True
            for _ in range(50):   # the app's engine writes it a moment after the click
                if app._kept().get("show_objects") is want:
                    break
                time.sleep(0.1)
            assert app._kept().get("show_objects") is want, launch
            _page.check_csp(page)
            page.close()
            if launch == 2:
                replies = []
                _post(server.url, "api/show_objects", {"show": "yes"}, replies)
                assert replies == [{"refused": "show_objects: show is true or false"}]
                assert "show_objects" not in app._kept()
        finally:
            server.close()


def test_a_slow_app_launch_shows_its_stages_on_the_bar_and_a_quick_one_none(browser, tmp_path, monkeypatch):
    """D980, past 1 s an op shows where it is: a launch whose server had run ``SLOW_LAUNCH`` by its ``host.json``
    answer (``age``; Step 4.4ci56: a launch on a busy computer passed 1 s with nothing shown) shows its stages on the
    bar, a third (the host read) and two thirds (the page drawn: its remembered setup's restore in flight), until the
    page is ready; a quick one shows none."""
    _home(monkeypatch, tmp_path / "home")
    app._remember(setup={"ticked": []})
    bar = """() => { const seen = globalThis.__bar = [];
      new MutationObserver(() => { const p = document.getElementById("progress");
        if (p && !p.closest("[hidden]")) seen.push(p.getAttribute("value")); })
        .observe(document, { subtree: true, childList: true, attributes: true, attributeFilter: ["hidden", "value"] });
    }"""
    server = app.serve(_page.WEB)
    try:
        page = browser.new_page()
        page.add_init_script(f"({bar})()")
        for started, shown in ((10, []), (-10, ["33", "67"])):   # the launch's start 10 s ahead (quick), 10 s ago
            server.started = time.monotonic() + started
            page.goto(server.url)
            _page.until(page, "() => globalThis.azurkit?.ready", 120)
            assert [v for v in dict.fromkeys(page.evaluate("() => globalThis.__bar")) if v] == shown
            assert page.evaluate("() => document.getElementById('progress-row').hidden")
        _page.check_csp(page)
    finally:
        server.close()


def test_the_apps_about_names_its_version_and_commit_or_says_no_git_can_name_it(browser, tmp_path, monkeypatch):
    """About shows the version and the commit AzurKit was built from (D992's release check, item 7), from what the
    host knows, never a fetch: the app run from this checkout names its HEAD (``host.json``'s ``commit``:
    ``azurkit.commit`` asks this computer's git), About its first 12 digits; reloaded where no git runs, ``host.json``
    names none and About says plainly that its commit is unknown, true of any build or checkout without git."""
    _home(monkeypatch, tmp_path / "home")
    head, version = _head(), azurkit.__version__
    about = """async () => [(await (await fetch("host.json")).json()).commit,
        document.getElementById("about-version").textContent]"""
    server = app.serve(_page.WEB)
    try:
        page = browser.new_page()
        azurkit.commit.cache_clear()
        page.goto(server.url)
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        assert page.evaluate(about) == [head, f"This is AzurKit {version}, built from commit {head[:12]}."]
        monkeypatch.setenv("PATH", str(tmp_path / "no-git"))   # a folder that isn't there: no git to run
        azurkit.commit.cache_clear()
        page.reload()
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        assert page.evaluate(about) == [
            None, f"This is AzurKit {version}, its commit is unknown (built or run without git)."]
        _page.check_csp(page)
    finally:
        server.close()
        azurkit.commit.cache_clear()


def test_the_apps_server_types_each_file_from_its_table_never_the_systems_guess(tmp_path, monkeypatch):
    """A browser refuses a module served as anything but JavaScript, and on Windows ``mimetypes`` reads the registry,
    which often says ``text/plain``: the page would never start. The app's answers are its own table's."""
    import mimetypes

    monkeypatch.setattr(mimetypes, "guess_type", lambda *args, **kwargs: ("text/plain", None))
    _home(monkeypatch, tmp_path / "home")
    server = app.serve()
    try:
        query = urllib.parse.urlsplit(server.url).query
        for name, kind in (("app.mjs", "text/javascript"), ("sw.js", "text/javascript"), ("index.html", "text/html"),
                           ("favicon-32.png", "image/png")):
            with urllib.request.urlopen(f"http://{server.host}/{name}?{query}", timeout=60) as reply:
                assert (name, reply.headers["Content-Type"]) == (name, kind)
    finally:
        server.close()


def _post(url: str, call: str, body: dict, replies: list, timeout: float = 120) -> None:
    """POST ``body`` to the engine's ``call`` (``api/save``, say) from the
    page at ``url`` (its token in the query); its reply goes in ``replies``
    if it comes in ``timeout`` s in all: the socket's own timeout bounds each
    read alone, and a call past ``app.KEEP`` sends a space each ``KEEP`` s."""
    host, query = urllib.parse.urlsplit(url).netloc, f"?{urllib.parse.urlsplit(url).query}"
    request = urllib.request.Request(f"http://{host}/{call}{query}", json.dumps(body).encode(),
                                     {"Origin": f"http://{host}", "Content-Type": "application/json"})
    end, data = time.monotonic() + timeout, b""
    with contextlib.suppress(OSError), urllib.request.urlopen(request, timeout=timeout) as reply:
        while chunk := reply.read1(1 << 16):   # the app may quit before it answers
            if time.monotonic() > end:
                raise TimeoutError(f"no answer in {timeout} s: {call}")
            data += chunk
        replies.append(json.loads(data))


def test_a_long_call_never_leaves_its_connection_quiet_the_5_s_firefox_aborts_one_after_a_network_change(
        tmp_path, monkeypatch):
    """Step 4.4ci36: Firefox aborts every connection that carried no byte in the 5 s after the computer's network
    changes (``network.http.network-changed.timeout``; this Mac's IPv6 changed every 1-8 min), and a call's answer went
    only once the call was done, so a plan file's spoiler and Track this seed, both in flight at one change, failed
    with "NetworkError" in 4.4ci27's slowed pure tier (three 240 s calls here, all at the change, 5.2 s after it). A
    call past ``app.KEEP`` s sends its answer's headers and a space each ``KEEP`` s until its answer, which reads as
    the call's JSON and ends at the close of its connection, which the app makes though the connection is HTTP/1.1's,
    kept (Step 4.5b); a quick call's answer keeps its length (here its connection closes as the client asks)."""
    _home(monkeypatch, tmp_path / "home")
    pause = [0.0]

    def checked(iso: str, progress) -> dict:
        time.sleep(pause[0])
        return {"files": 0}
    monkeypatch.setattr(sdk, "verify_all", checked)
    server = app.serve(_page.WEB)
    heard = []
    try:
        for pause[0] in (0.0, 6.0):   # the slow call past Firefox's 5 s
            body = json.dumps({"iso": str(tmp_path / "usa.iso")}).encode()
            close = "" if pause[0] else "Connection: close\r\n"   # the quick call's client ends its kept connection
            with socket.create_connection(("127.0.0.1", server.server_port), timeout=30) as conn:
                conn.sendall(f"POST /api/verify_all?token={server.token} HTTP/1.1\r\nHost: {server.host}\r\n"
                             f"{close}"
                             f"Origin: http://{server.host}\r\nContent-Type: application/json\r\n"
                             f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
                came, data = [time.monotonic()], b""
                while chunk := conn.recv(1 << 16):
                    came.append(time.monotonic())
                    data += chunk
            head, _, answer = data.partition(b"\r\n\r\n")
            heard.append((head.split(b"\r\n")[0], b"Content-Length:" in head, json.loads(answer),
                          max(b - a for a, b in zip(came, came[1:])) < 5, came[-1] - came[0] >= pause[0]))
    finally:
        server.close()
    assert heard == [(b"HTTP/1.1 200 OK", True, {"files": 0}, True, True),
                     (b"HTTP/1.1 200 OK", False, {"files": 0}, True, True)], heard


def test_the_apps_server_holds_a_burst_of_connects_and_answers_a_pages_files_over_one_kept_connection(
        tmp_path, monkeypatch):
    """Step 4.5b: the app's server keeps a connection for the page's next request (HTTP/1.1, no Nagle delay) and its
    listen queue is the system's longest, the two levers the site's test server needed on GitHub's Windows runner
    (``tests/_static.py``): a page asks for its files at once, and with socketserver's queue of 5 Windows refused a
    connect past it (ECONNREFUSED) where macOS and Linux drop it for a retry. 32 connects made before the app accepts
    any are each answered; over one kept connection the page, a file and a quick call come whole, and once the app
    has closed, that connection's next request is refused and closes it, as a new connection would be."""
    _home(monkeypatch, tmp_path / "home")
    page = tmp_path / "page"
    page.mkdir()
    (page / "index.html").write_text("<title>t</title>", encoding="utf-8")
    (page / "app.mjs").write_text("export {};", encoding="utf-8")
    accepting, accept = threading.Event(), app.Server.get_request

    def held(self):   # the app accepts no connect until the burst is made
        accepting.wait(30)
        return accept(self)
    monkeypatch.setattr(app.Server, "get_request", held)
    server, burst, got = app.serve(page), [], []
    try:
        burst += [socket.create_connection(("127.0.0.1", server.server_port), timeout=10) for _ in range(32)]
        accepting.set()
        for sock in burst:
            sock.sendall(f"GET /?token={server.token} HTTP/1.0\r\nHost: {server.host}\r\n\r\n".encode())
        answers = {(answer.partition(b"\r\n")[0], answer.rpartition(b"\r\n\r\n")[2])
                   for answer in (sock.makefile("rb").read() for sock in burst)}
        connection, sent = http.client.HTTPConnection(server.host, timeout=10), {"Cookie": f"{server.cookie}={server.token}"}
        call = sent | {"Origin": f"http://{server.host}", "Content-Type": "application/json"}
        for method, path, body, headers in (("GET", f"/?token={server.token}", None, {}), ("GET", "/app.mjs", None, sent),
                                            ("POST", "/api/cancel", b"{}", call), ("GET", "/app.mjs", None, sent)):
            if len(got) == 3:
                server.close()
            connection.request(method, path, body, headers)
            port = connection.sock.getsockname()[1]
            reply = connection.getresponse()
            got.append((reply.status, reply.read() if reply.status == 200 else b"", reply.will_close, port))
        connection.close()
    finally:
        accepting.set()
        if not server.closed:
            server.close()
        for sock in burst:
            sock.close()
    assert (len(burst), answers) == (32, {(b"HTTP/1.1 200 OK", b"<title>t</title>")}), answers
    assert [row[:3] for row in got] == [(200, b"<title>t</title>", False), (200, b"export {};", False),
                                        (200, b"{}", False), (403, b"", True)] and len({row[3] for row in got}) == 1, got


def test_a_tests_call_ends_at_its_timeout_while_the_app_keeps_its_connection_alive(tmp_path, monkeypatch):
    """Step 4.4ci36: a call past ``app.KEEP`` s sends a space each ``KEEP`` s until its answer, so the socket's timeout,
    each read's, never ended a call that never answers: a hung engine call waited for CI's 90 min stall watch where it
    failed its test by name in ``_post``'s 120 s. ``_post`` reads its answer in its timeout in all."""
    _home(monkeypatch, tmp_path / "home")
    release = threading.Event()

    def checked(iso: str, progress) -> dict:
        release.wait(6)   # a call that outlasts the client's 2 s
        return {"files": 0}
    monkeypatch.setattr(sdk, "verify_all", checked)
    server, replies = app.serve(_page.WEB), []
    try:
        t0 = time.monotonic()
        _post(server.url, "api/verify_all", {"iso": str(tmp_path / "usa.iso")}, replies, timeout=2)
        took = time.monotonic() - t0
    finally:
        release.set()
        server.close()
    assert replies == [] and 2 <= took < 6, (replies, took)


def test_serves_engine_answers_while_serve_waits_on_its_input(tmp_path, monkeypatch):
    """``serve``'s blocked read of its input (a pipe, here) doesn't hold the engine it spawns at that engine's start, as
    it did on Windows (:func:`azurkit.app._input_kept_from_children`), and the input's end still ends it."""
    _home(monkeypatch, tmp_path)
    replies: list = []
    with subprocess.Popen([sys.executable, "-m", "azurkit", "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True) as served:
        try:
            _post(served.stdout.readline().strip(), "api/plan_spoiler", {"plan": {}}, replies)
            assert "refused" in replies[0]   # by the engine, which read the logic first
        except BaseException as exc:
            _ended_with(served, exc)
            raise
        served.stdin.close()
        assert (served.wait(60), served.stderr.read()) == (0, "")


def test_quitting_the_app_mid_save_leaves_nothing_where_it_saves(tmp_path, monkeypatch, usa_iso):
    """Quitting while a save writes cancels it and waits until it has
    removed its part file, before the app can exit (D35): when ``serve``'s
    input ends (the way out of the window and the browser fallback too), and
    when the window's closing event fires (its close button, and Cmd-Q,
    after which no ``finally`` runs). Nothing is left where it saved. Both
    run the save in the app's engine process (``app.engine.Spawned``)."""
    import webview
    _home(monkeypatch, tmp_path / "home")   # where the app remembers the image
    out = tmp_path / "out"
    out.mkdir()
    recipe = {"iso": str(usa_iso), "packs": {"fps_unlock": {}}}

    def save_until_writing(url: str, name: str) -> None:
        """POST a save to the page's server at ``url`` and return once it writes."""
        host, query = urllib.parse.urlsplit(url).netloc, f"?{urllib.parse.urlsplit(url).query}"   # the token
        replies: list = []
        threading.Thread(target=_post, args=(url, "api/save", {"recipe": recipe, "out": str(out / name)}, replies),
                         daemon=True).start()
        end = time.monotonic() + 120
        while True:
            with urllib.request.urlopen(f"http://{host}/api/progress{query}", timeout=10) as reply:
                step = json.load(reply)
            if step["done"]:
                return
            assert time.monotonic() < end, f"the save never started writing: its progress {step}, {replies}"
            time.sleep(0.05)

    with subprocess.Popen([sys.executable, "-m", "azurkit", "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, env=os.environ | {"HOME": str(tmp_path / "home")}) as served:
        try:
            url = served.stdout.readline().strip()
            first_engines = _descendants(served.pid)
            try:
                save_until_writing(url, "served.iso")
            except AssertionError as exc:   # a hung engine's the same process, one that dies at its start another's
                exc.add_note(f"the app's engine processes: {first_engines} at the start, {_descendants(served.pid)} at the end")
                raise
        except BaseException as exc:
            _ended_with(served, exc)
            raise
        served.stdin.close()
        assert (served.wait(60), served.stderr.read()) == (0, "")
    assert list(out.iterdir()) == []

    server, left = app.serve(engine=engine.Spawned()), []

    def start(**kwargs) -> None:   # the window: a save writes, then the window closes
        save_until_writing(server.url, "window.iso")
        assert server.window.events.closing.set() is False   # the close goes ahead
        left.extend(out.iterdir())
    window = types.SimpleNamespace(events=types.SimpleNamespace(closing=webview.event.Event(None, True)))
    monkeypatch.setattr(webview, "create_window", lambda **kwargs: window)
    monkeypatch.setattr(webview, "start", start)
    try:
        assert app._window(server)
    finally:
        server.close()
    assert left == []


def test_an_answer_worked_out_long_is_kept_when_it_answers_so_a_quit_right_after_it_loses_none(tmp_path, monkeypatch):
    """Step 4.4bc: the app's store writes behind the answer, and a quit ends
    its engine process at once (D1012), so a reshape's dress (minutes, its plan
    kept as its build answered) was lost to a quit right after Built and worked
    out again at the next launch (A32/capped's 86-149 s takes). An answer worked
    out for ``swapcache.LONG`` or more is written before its call answers, even
    when another call (the engine's own thread) missed that key just before: a
    process that ends the moment its long answer and then a quick one are out
    keeps the long one, which the next process's same ask reads with no work,
    and the quick one stays behind its answer, lost to that end."""
    from azurkit.app import swapcache
    from azurkit.tools import characters

    folder, key, long, quick = tmp_path / "cache", tmp_path / "cache.key", "a" * 64, "b" * 64
    ended = subprocess.run([sys.executable, "-c", textwrap.dedent(f"""
        import os, sys, threading, time
        from azurkit.app import swapcache
        from azurkit.tools import characters
        swapcache.LONG, characters.CACHE = 0.2, swapcache.Folder(sys.argv[1], key=sys.argv[2])
        slow = lambda found: (time.sleep(0.5), found.encode())[1]   # each answer's bytes, made slowly by the writer
        def work():   # long, and another call asks for the same key on its own thread as it ends
            time.sleep(0.3)
            other = threading.Thread(target=characters.CACHE.get, args=({long!r},))
            other.start(), other.join()
            return "long"
        characters._kept({long!r}, work, slow, bytes.decode)
        characters._kept({quick!r}, lambda: "quick", slow, bytes.decode)
        os._exit(0)   # as a quit ends the app's engine process: at once
        """), str(folder), str(key)], capture_output=True, text=True, timeout=120)
    assert (ended.returncode, ended.stderr) == (0, "")
    monkeypatch.setattr(characters, "CACHE", swapcache.Folder(folder, key=key))   # the next launch's
    assert characters._kept(long, lambda: pytest.fail("worked out again"), str.encode, bytes.decode) == "long"
    assert characters.CACHE.get(quick) is None


def test_closing_the_app_during_a_long_build_returns_within_2_s_and_leaves_no_part_file(tmp_path, monkeypatch):
    """Closing the app (``Server.quit``, the window's closing hook: its
    close button and Cmd-Q) never waits on a build (AZ-823): mid-build it
    returns at once, and the build's answer and a save queued behind it (a
    second tab's) are refused. Mid-save it cancels the save and waits for it
    to remove its part file, ``app.QUIT_WAIT`` in all; a save whose disk
    stalls past that has its part file removed by the close (D35) and then
    fails, so nothing is left where it saved, even if the app exits then."""
    _home(monkeypatch, tmp_path / "home")
    out, release = tmp_path / "out", threading.Event()
    out.mkdir()
    planning, stalled = threading.Event(), threading.Event()

    def image(recipe, progress=None, spoiler=True):   # a long build (the engine leaves a seed's spoiler for later)
        planning.set()
        release.wait(60)
        return types.SimpleNamespace(size=0), {}

    class Disk(io.BytesIO):   # a save's image, whose next read after its first chunk stalls
        def read(self, size=-1):
            if self.tell():
                stalled.set()
                release.wait(60)
            return super().read(size)
    made = types.SimpleNamespace(source=tmp_path / "in.iso", size=2 * iso.CHUNK,
                                 open=lambda: Disk(bytes(2 * iso.CHUNK)))
    monkeypatch.setattr(sdk, "image", image)
    monkeypatch.setattr(sdk, "build", lambda recipe, to, progress: {"sha256": iso.pack(made, to, progress=progress)})

    def close(server: app.Server, started: threading.Event, *calls: tuple[str, dict]) -> tuple[float, list, list]:
        """Make the first call, then the others (queued behind it) once it
        has ``started``, and close: the seconds the close took, what was in
        ``out`` once it returned, and the calls' replies."""
        replies = [[] for _ in calls]
        threads = [threading.Thread(target=_post, args=(server.url, *call, got)) for call, got in zip(calls, replies)]
        threads[0].start()
        assert started.wait(60)
        for thread in threads[1:]:
            thread.start()
            time.sleep(0.3)
        began = time.monotonic()
        server.quit()
        took, left = time.monotonic() - began, sorted(p.name for p in out.iterdir())
        release.set()
        for thread in threads:
            thread.join(120)
        release.clear()
        server.close()
        return took, left, [reply for got in replies for reply in got]

    save = ("api/save", {"recipe": {}, "out": str(out / "a.iso")})
    took, left, replies = close(app.serve(), planning, ("api/build", {"iso": str(tmp_path / "in.iso")}), save)
    assert (took < 0.5, left, replies) == (True, [], [{"refused": app.QUITTING}] * 2)
    took, left, replies = close(app.serve(), stalled, save)
    assert (took < 2, left, replies) == (True, [], [{"refused": "Cancelled: nothing was written"}])
    assert list(out.iterdir()) == []


def _ended(pid: int, within: float = 10) -> bool:
    """The process ``pid`` has ended (and been reaped) within ``within`` seconds."""
    end = time.monotonic() + within
    while time.monotonic() < end:
        if not queue.alive(pid):
            return True
        time.sleep(0.05)
    return False


def test_a_pool_child_grown_past_the_line_leaves_with_its_results_and_a_small_one_stays():
    """Step 4.3r4c: a child whose part took it past ``procpool.RETIRE`` hands
    every result back and leaves, so that part's heap goes back to the OS
    (Windows, with no peak to read, keeps it: a named flaw); the next child
    stays for the next call, however big its parent has grown by then (Linux's
    ``getrusage`` would start it at its parent's peak)."""
    from azurkit.app import procpool

    procpool.stop()
    size = procpool.RETIRE + (16 << 20)
    try:
        assert [len(got) for got in procpool.map_(operator.mul, b"x", [size])] == [size]
        assert len(procpool._IDLE) == (sys.platform == "win32")
        procpool.stop()
        assert procpool.map_(operator.add, 1, [2]) == [3]
        assert len(procpool._IDLE) == 1
    finally:
        procpool.stop()


def _spun(here: int, seconds: float) -> bool:   # a pool item: ``seconds`` on the pool's clock; whether it ran in ``here``
    from azurkit.app import procpool

    began = procpool.CLOCK()
    while procpool.CLOCK() - began < seconds:
        pass
    return os.getpid() == here


def test_the_pool_times_a_small_item_by_a_clock_that_sees_under_a_millisecond():
    """Step 4.4bh: ``procpool.CLOCK`` times each item a small call runs
    here. Windows' CPU clock moves only at each tick of about 15.6 ms, so
    an item under one read 0 and a dear one ran in the engine; there the
    pool takes the wall clock, which moves by less than a millisecond, as
    the CPU clock does elsewhere."""
    from azurkit.app import procpool

    steps, last, end = [], procpool.CLOCK(), time.monotonic() + 10
    while len(steps) < 20 and time.monotonic() < end:
        if (now := procpool.CLOCK()) != last:
            steps.append(now - last)
            last = now
    assert steps and min(steps) < 0.001, steps


def test_a_small_pool_call_with_no_idle_child_runs_here_and_starts_none(monkeypatch):
    """Step 4.4bh: a costed call that would start a child runs its items
    here, the cheapest first, while they stay under ``procpool.SMALL`` CPU
    seconds: a G4 match's 35 clips, 1-3 ms each, started 16 children for
    2.6 CPU-s. Its answers are the same list; a call whose next item would
    pass it by ``cost`` splits the rest, and one with no cost (its first
    item may be its dearest) or a low one (work ahead, which would hold the
    engine's GIL beside the player's ask) splits all, as before."""
    from azurkit.app import procpool

    made, child = [], procpool._Child
    monkeypatch.setattr(procpool, "_Child", type("Counted", (child,), {
        "__init__": lambda self: (made.append(1), child.__init__(self))[1]}))
    monkeypatch.delenv(procpool.CORES, raising=False)
    procpool.stop()
    here, dear = os.getpid(), [0.3, 0.01, 0.3]
    try:
        assert (procpool.map_(_spun, here, [0.0] * 35, lambda n: 35 - n), made) == ([True] * 35, [])
        assert procpool.map_(_spun, here, dear, lambda n: dear[n]) == [False, True, False] and len(made) == 2
        procpool.stop()
        assert procpool.map_(_spun, here, [0.0, 0.0]) == [False, False] and len(made) == 4
        procpool.stop()
        low = []
        ahead = threading.Thread(target=lambda: (procpool.Low()(True), low.append(procpool.map_(
            _spun, here, [0.0] * 2, lambda n: 1))))
        ahead.start()
        ahead.join(60)
        assert low == [[False, False]] and len(made) == 6
    finally:
        procpool.stop()


def test_a_call_beside_every_held_core_takes_one_child_and_never_waits_for_them(monkeypatch):
    """Step 4.3r4c: ``$AZURKIT_CORES`` caps the children across the process,
    not a call's alone, so a call asking for 2 beside a ``later``'s call
    holding both cores splits over 1; but it takes that one at once, past the
    cap, and answers before any held part comes home (G4 beside a capped
    dress: 18.75 s waiting for a part, 3.27 s not)."""
    from azurkit.app import procpool

    splits, split, home = [], procpool._split, []
    monkeypatch.setattr(procpool, "_split", lambda count, parts, cost: (splits.append(parts), split(count, parts, cost))[1])
    monkeypatch.setenv(procpool.CORES, "3")
    procpool.stop()
    try:
        procpool.map_(operator.add, 1, [1, 2, 3])   # idle children, so no spawn runs out the parts' time below
        monkeypatch.setenv(procpool.CORES, "2")
        splits.clear()
        held = procpool.later(procpool.map_, operator.call, time.sleep, [1.5, 1.5], None, home.append)
        while not splits:
            time.sleep(0.01)
        assert procpool.map_(operator.add, 1, [2, 3]) == [3, 4]
        assert not home and splits == [2, 1]
        assert held.result() == [None, None] and procpool._BUSY.busy == 0
    finally:
        procpool.stop()


def test_the_apps_engine_process_answers_small_asks_during_a_build_and_cancel_stops_it(tmp_path, monkeypatch,
                                                                                       usa_iso):
    """Step 4.3i: the app's builds run in its engine process
    (``app.engine.Spawned``), so the server's own answers (the species list,
    the setup, the build's progress: its stage's ``core.progress`` record)
    come within 0.5 s while keylord builds (her swap's calls are small, so
    worked out in that process: ``procpool.SMALL``); Cancel refuses the build at once and
    stops it at its next record, so the same process, its logic and its
    pool, takes the next Build (``app.ahead``, D1007), and closing the app
    ends it."""
    _home(monkeypatch, tmp_path / "home")
    server = app.serve(_page.WEB, engine.Spawned())
    first, replies = server.engine.pid, []

    def ask(path: str, body: dict) -> tuple[float, dict]:
        got, began = [], time.monotonic()
        _post(server.url, path, body, got)
        return time.monotonic() - began, got[0]

    host, query = urllib.parse.urlsplit(server.url).netloc, urllib.parse.urlsplit(server.url).query

    def progressed() -> dict:
        with urllib.request.urlopen(f"http://{host}/api/progress?{query}", timeout=10) as reply:
            return json.load(reply)

    try:
        ask("api/pickers", {"given": {}})   # the species list read once, as the page's first ask reads it
        building = threading.Thread(target=_post, args=(server.url, "api/build", {
            "iso": str(usa_iso), "packs": {}, "character": {"species": "keylord"}}, replies))
        building.start()
        # Waited for while the build runs (Step 4.4ci19's measures: the build takes about 4 s here, 25-69 s under
        # taskpolicy -b and nice 19 beside a load of 30-49): its first record, the build's Python, 0.3 s after the post
        # here and up to 7.8 s so slowed, the engine process's start first (2.9-4.6 s from its spawn), where a fixed
        # 1.5 s found no stage yet. Her swap starts no pool child (its calls are small, Step 4.4bh), so nothing more is
        # waited for. A build that ends first says what it gave.
        while building.is_alive() and progressed()["calls"].get("build", {}).get("stage") is None:
            time.sleep(0.05)
        assert building.is_alive(), f"the build ended before its first record: {replies}"
        took = [ask("api/pickers", {"given": {}}), ask("api/setup", {"setup": {"ticked": ["fps_unlock"]}})]
        assert all(s < 0.5 or s < 0.5 * _speed.factor() for s, _ in took) and took[1][1] == {}, took
        step = progressed()
        assert step["calls"]["build"]["stage"] in progress.STAGES and step["stage"] == step["calls"]["build"]["stage"]
        assert building.is_alive(), f"the build ended before its cancel: {replies}"
        assert ask("api/cancel", {})[1] == {}
        building.join(5)
        assert (building.is_alive(), replies) == (False, [{"refused": "Cancelled: nothing was built"}])
        assert server.engine.pid == first
        took, built = ask("api/build", {"iso": str(usa_iso), "packs": {}})
        assert built["size"] == sdk.image({"iso": str(usa_iso), "packs": {}})[0].size, built
        last = server.engine.pid
    finally:
        server.close()
    assert _ended(last)


def _until(test, within: float = 120) -> None:
    end = time.monotonic() + within
    while not test():
        assert time.monotonic() < end
        time.sleep(0.05)


@pytest.mark.parametrize("packs, more", [({"fps_unlock": {}}, {}), ({}, {"randomizer": {"seed": "2"}})],
                         ids=["packs", "a seed"])
def test_the_apps_build_takes_the_build_ahead_of_its_recipe_after_it_mid_flight_and_once_another_stopped_it(
        tmp_path, monkeypatch, usa_iso, packs, more):
    """The app's work ahead (D1007, ``app.ahead``): the page's settled setup
    built ahead (``api/speculate``, at its change ``gen``) is its Build's,
    taken after it ended, mid-flight, or remade once a newer change's
    recipe stopped it at its next record, each the plain Build's image and
    report; an offer of an older change is dropped. On a machine with room
    for it (``test_ahead.py`` holds ``ahead.room``): the peak a Here build
    reports is this whole test process's, which is over its line under 16 GiB.
    A pack's build here ends within 30 ms, as fast as the next call reaches
    the server (on a Windows runner the stop came after the job's last
    record), so the job taken mid-flight and the one stopped wait at their
    first record until their click or stop has come."""
    _home(monkeypatch, tmp_path / "home")
    monkeypatch.setattr(app.ahead, "room", lambda peak: True)
    images, image, holds = [], sdk.image, []

    def imaged(*args, progress, **kwargs):
        images.append(1)
        hold = holds.pop() if holds else None

        def first(step: dict) -> None:
            nonlocal hold
            if hold is not None:
                hold, held = None, hold
                _until(held)
            progress(step)
        return image(*args, progress=first, **kwargs)
    monkeypatch.setattr(sdk, "image", imaged)
    server = app.serve(_page.WEB)
    a, c = {"iso": str(usa_iso), "packs": packs, **more}, {"iso": str(usa_iso), "packs": {"fps_unlock": {"fps": 30}}}

    def built(recipe: dict) -> tuple[str, dict]:
        got = []
        _post(server.url, "api/build", recipe, got)
        kept = engine._BUILT[got[0]["build"]]
        assert kept.ended.wait(60)
        return kept.sha, got[0]["report"]

    def ahead(gen: int, recipe: dict, wait: bool = True) -> None:
        got = []
        _post(server.url, "api/speculate", {"gen": gen, **recipe}, got)
        assert got == [{"ahead": True}] and (not wait or server.slots.job("build").done.wait(120))
    try:
        plain = built(a)
        ahead(1, c)
        ahead(2, a)
        took = [built(a), len(images)]   # after it ended: nothing built again
        ahead(3, c)
        holds.append(lambda: server.slots.job("build").state == "taken")
        ahead(4, a, wait=False)
        took += [built(a), len(images)]  # mid-flight
        ahead(5, c)
        reached, go = threading.Event(), threading.Event()
        holds.append(lambda: reached.set() or go.is_set())
        ahead(6, a, wait=False)
        stopped = server.slots.job("build")
        _until(reached.is_set)
        ahead(7, c, wait=False)          # stops it mid-flight
        late = []
        _post(server.url, "api/speculate", {"gen": 6, **a}, late)
        ahead(8, a, wait=False)
        go.set()
        took += [built(a)]               # remade
        assert stopped.done.wait(120) and isinstance(stopped.error, engine.Cancelled) and late == [{"ahead": False}]
        assert took == [plain, 3, plain, 5, plain]
    finally:
        server.close()
        engine._drop()


def test_a_seed_build_stopped_at_any_stage_leaves_nothing_half_kept(usa_iso):
    """A job ahead stopped at its next record, in any stage of a seed's
    build, keeps nothing that changes the next: the build after each stop
    gives the plain build's image and report (``app.ahead``'s promise)."""
    here, recipe = engine.Here(), {"iso": str(usa_iso), "packs": {}, "randomizer": {"seed": "2"}}

    def plain() -> tuple[str, dict]:
        got = here.call("image", recipe)
        kept = engine._BUILT[got["build"]]
        assert kept.ended.wait(120)
        return kept.sha, got["report"]
    try:
        whole, stages = plain(), []   # first: a first build's check and logic read are stages no other has
        here.call("image", recipe, progress=lambda step: stages.append(step["stage"]))

        def stop(stage: str):
            def progress(step: dict) -> None:
                if step["stage"] == stage:
                    raise engine.Cancelled
            return progress
        for stage in dict.fromkeys(stages):
            with pytest.raises(engine.Cancelled):
                here.call("image", recipe, progress=stop(stage))
            assert plain() == whole, stage
        assert len(set(stages)) >= 3, stages
    finally:
        engine._drop()


def test_a_cancel_mid_fill_then_build_keeps_the_engine_and_its_fill_and_answers_the_plain_build(
        tmp_path, monkeypatch, usa_iso):
    """The player's Cancel during a seed's fill (D1007): refused at once, the
    engine's process the same, its job going on; the Build after it takes
    that job back: the plain build's report."""
    _home(monkeypatch, tmp_path / "home")
    server = app.serve(_page.WEB, engine.Spawned())
    first, recipe, replies, again = server.engine.pid, {"iso": str(usa_iso), "packs": {},
                                                         "randomizer": {"seed": "2"}}, [], []
    try:
        building = threading.Thread(target=_post, args=(server.url, "api/build", recipe, replies))
        building.start()
        _until(lambda: (job := server.slots.job("build")) is not None and (job.step or {}).get("stage") == "plan",
               within=300)
        job, began = server.slots.job("build"), time.monotonic()
        _post(server.url, "api/cancel", {}, [])
        building.join(5)
        assert replies == [{"refused": "Cancelled: nothing was built"}] and time.monotonic() - began < 5
        _post(server.url, "api/build", recipe, again, timeout=300)
        assert server.slots.job("build") is job or job.step["stage"] != "plan"   # taken back, unless its fill had ended
        assert server.engine.pid == first
        assert again[0]["report"] == sdk.image(recipe, spoiler=False)[1]
    finally:
        server.close()


def test_the_apps_track_takes_the_seed_planned_ahead_and_its_first_view(tmp_path, monkeypatch):
    """A seed typed and settled is planned ahead (``api/prefetch``, as
    Track asks it: ``{seed, share}``) and that plan's first tracker view
    read, so Track (``api/plan``) and the tracker's first ask take them:
    each the plain answer, each worked out once."""
    _home(monkeypatch, tmp_path / "home")
    calls, plan, tracker = [], sdk.plan, sdk.tracker
    monkeypatch.setattr(sdk, "plan", lambda *args, **kwargs: calls.append("plan") or plan(*args, **kwargs))
    monkeypatch.setattr(sdk, "tracker", lambda *args, **kwargs: calls.append("view") or tracker(*args, **kwargs))
    server, recipe = app.serve(_page.WEB), {"seed": "azurkit", "share": "AZR-AAEA"}
    try:
        got = []
        _post(server.url, "api/prefetch", {"gen": 1, "recipe": recipe, "view": {"spoiler": False, "gems": False}}, got)
        assert got == [{"ahead": True}] and server.slots.job("plan").done.wait(120)
        _until(lambda: server.slots.job("view") is not None and server.slots.job("view").done.is_set())
        _post(server.url, "api/plan", {"recipe": recipe}, got)
        given = {"plan": got[1]["plan"], "marks": {}, "spoiler": False, "gems": False}
        _post(server.url, "api/tracker", {"given": given}, got)
        assert calls == ["plan", "view"]
        assert (got[1]["plan"], got[2]) == (plan(recipe), tracker(given))
    finally:
        server.close()


@pytest.mark.parametrize("call", ["match", "preview"])
def test_a_dress_beside_a_build_ahead_stops_that_build_and_answers_plain(tmp_path, monkeypatch, call):
    """G4's match or a preview beside a heavy build ahead (review D1 of Step
    4.3r4g): holding that build through the dress passed D1017's 6 GiB (6.12-6.32
    GiB on 8 GiB, 5.13 stopped first), so it ends at its next record, nothing
    takes its slot, and the call answers as it does alone."""
    _home(monkeypatch, tmp_path / "home")
    server, recipe = app.serve(_page.WEB), {"iso": "/a.iso", "packs": {}, "character": {"species": "booblord"}}
    running = threading.Event()

    def build(job) -> None:
        while True:
            job.progress(progress_record("dress"))
            running.set()
            time.sleep(0.01)
    asked = []
    monkeypatch.setattr(server.engine, "call", lambda *args, progress=None: asked.append(args) or {"plain": True})
    try:
        assert server.slots.offer("build", 1, "ahead", build) and running.wait(60)
        job, got = server.slots.job("build"), []
        _post(server.url, f"api/{call}", {"recipe": recipe}, got)
        assert got == [{"plain": True}] and asked == [(call, recipe)]
        assert job.done.wait(60) and isinstance(job.error, engine.Cancelled) and server.slots.job("build") is job
    finally:
        server.close()


def test_randomize_ticked_with_no_seed_in_the_apps_page_stops_the_build_ahead(browser, tmp_path, monkeypatch, usa_iso):
    """A change that leaves the page nothing to build (review D2 of Step
    4.3r4g: Randomize with no seed; no image, a refused body and an opened
    build return the same way) drops the build ahead at its next record, not
    at its end, and nothing takes its slot."""
    _home(monkeypatch, tmp_path / "home")
    server = app.serve(_page.WEB)

    def build(job) -> None:
        while True:
            job.progress(progress_record("dress"))
            time.sleep(0.01)
    try:
        page = browser.new_page()
        page.goto(server.url)
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        _page.fill(page, "iso-path", str(usa_iso))
        _page.until(page, "() => azurkit.vanilla")
        _until(lambda: server.slots.job("build") is not None and server.slots.job("build").done.is_set())
        assert server.slots.offer("build", server.slots.gen, "ahead", build)
        job = server.slots.job("build")
        page.evaluate("""() => {
            const on = document.getElementById("rando-on");
            document.getElementById("rando-seed").value = "";
            on.checked = true;
            on.dispatchEvent(new Event("change", { bubbles: true }));
        }""")
        assert job.done.wait(60) and isinstance(job.error, engine.Cancelled) and server.slots.job("build") is job
        # The page's api/setup has been sent: its check reads the logic (seconds), and left running it would write this
        # setup into the next test's HOME, whose page would restore Randomize ticked (run 41372636477's data edits test).
        _until(lambda: app._kept().get("setup", {}).get("randomizer"))
        page.close()
    finally:
        server.close()


def test_a_kill_of_a_quiet_job_cancels_it_and_runs_the_call_the_player_waits_on_again():
    """A job ahead that reaches no record ends the engine's process
    (``Spawned.cancel``): that job, no click following it, is cancelled, and
    the call the player waits on beside it runs again in the next process, to
    the plain answer (not "AzurKit is quitting", review H1 of Step 4.3w)."""
    spawned, recipe = engine.Spawned(), {"seed": "azurkit", "share": "AZR-AAEA"}
    seen, answers = threading.Event(), {}
    followed, quiet = threading.Event(), threading.Event()
    followed.set()

    def call(name: str, fore: threading.Event) -> None:
        try:
            answers[name] = spawned.call("plan", recipe, progress=lambda step: seen.set(), fore=fore)
        except BaseException as exc:
            answers[name] = exc
    try:
        first, threads = spawned.pid, [threading.Thread(target=call, args=each)
                                       for each in (("click", followed), ("ahead", quiet))]
        for thread in threads:
            thread.start()
        assert seen.wait(120)
        spawned.cancel()
        for thread in threads:
            thread.join(120)
        assert isinstance(answers["ahead"], engine.Cancelled) and spawned.pid != first
        assert answers["click"] == sdk.plan(recipe)
    finally:
        spawned.close()


def test_a_cancels_next_engine_reads_the_logic_then_builds_then_reads_the_image_for_its_pictures(monkeypatch):
    """After Cancel the app's next engine gets the warms the page asked (the
    image picked first, then the Randomizer tab's logic) and the next Build
    at once: it reads the randomizer's logic, builds the seed, and only then
    reads the image as the pictures do, so neither the logic's read nor the
    build waits on the pictures' Python ("Cancel a build, then Build", A29:
    about 0.3 s; Step 4.3 round 3). The build's kernel count comes before
    its answer: the build counts its own, on counts of the test's own (it
    read ones an earlier test left in this process, and with none the
    engine sends no count, so its wait never ended: Step 4.4ci16). The
    engine hands its swaps' parallel work to its pool once, as it starts
    (``procpool.install``: Step 4.4bh's small calls start no child, so no
    build test sees one)."""
    from azurkit.app import procpool

    log, installed = [], []

    def step(name: str, seconds: float = 0.0) -> None:
        log.append(name)
        time.sleep(seconds)
        log.append(f"{name} done")
    monkeypatch.setattr(engine, "orphaned", lambda: None)   # the loop on a thread of this process, not its own
    monkeypatch.setattr(procpool, "install", lambda: installed.append(1))
    monkeypatch.setattr(sdk, "randomizer_logic", lambda progress=None: step("logic", 0.2))
    monkeypatch.setattr(sdk, "pickers", lambda given: step("pictures"))
    monkeypatch.setattr(native, "CALLS", collections.Counter())

    def build(recipe) -> dict:
        native.CALLS["kernel"] += 1   # the seed's fill reaches through the kernel
        step("build", 0.2)
        return {}
    monkeypatch.setitem(engine.JOBS, "image", engine._warmed(build))
    here, there = multiprocessing.Pipe()
    loop = threading.Thread(target=engine._main, args=(there,), daemon=True)
    loop.start()
    for message in engine._warm_messages({"image": ("in.iso",), "randomizer": ()}):
        here.send(message)
    here.send(("call", 1, "image", ({"iso": "in.iso", "randomizer": {"seed": "2"}},), False, None))

    def heard() -> tuple:
        assert here.poll(10), f"the engine sent nothing more in 10 s: {log}"
        return here.recv()
    assert (heard(), heard()[:2]) == (("calls", 1, {"kernel": 1}), ("done", 1))   # the counts before the answer
    end = time.monotonic() + 10
    while "pictures done" not in log and time.monotonic() < end:
        time.sleep(0.01)
    here.close()
    loop.join(10)
    assert (log, loop.is_alive(), engine._BUILDS, installed) == (
        ["logic", "logic done", "build", "build done", "pictures", "pictures done"], False, 0, [1])


def test_the_apps_engine_counts_the_swaps_items_on_the_stage_its_call_reported_last(monkeypatch):
    """``pool.TICK``, set by the app's engine as it follows a call (Step
    4.3m): the swap's items done of total, on the stage the call reported
    last (its dress's line), each percent once; on a counted step they count
    inside it, never back; a call no one follows counts nothing, and another
    thread's work isn't its."""
    def dress(recipe, progress=None):
        if progress is not None:
            progress(progress_record("dress", "Dressing keylord"))
        return pool.each(lambda shared, item: item + shared, 1, list(range(8)))

    def counted(recipe, progress):   # the match's "the dress, 2 of 5": two pools inside its step
        progress(progress_record("dress", "Dressing keylord", 1, 5))
        pool.each(lambda shared, item: item, None, list(range(8)))
        pool.each(lambda shared, item: item, None, list(range(8)))
        progress(progress_record("dress", "Dressing keylord", 2, 5))

    monkeypatch.setattr(pool, "TICK", pool.TICK)
    monkeypatch.setattr(pool, "MAP", None)
    monkeypatch.setitem(engine.JOBS, "dress", dress)
    seen = []
    assert engine.Here().call("dress", {}, progress=seen.append) == list(range(1, 9))
    assert [(r["label"], r["done"], r["total"]) for r in seen] == [("Dressing keylord", 0, 0), *(
        ("Dressing keylord", k, 8) for k in range(1, 9))]
    assert engine.Here().call("dress", {}) == list(range(1, 9))
    other = threading.Thread(target=pool.each, args=(lambda shared, item: item, None, [0] * 8))
    other.start()
    other.join()
    assert len(seen) == 9
    monkeypatch.setitem(engine.JOBS, "counted", counted)
    seen.clear()
    engine.Here().call("counted", {}, progress=seen.append)
    assert [r["percent"] for r in seen] == [20, 22, 25, 27, 30, 32, 35, 37, 40, 40]


def test_the_apps_save_writes_the_image_its_build_made_planned_once_and_hashed_from_the_build_on(
        tmp_path, monkeypatch, usa_iso):
    """Step 4.3i: Save (``api/save`` with the build's id) writes the image
    its Build made, kept in the engine and hashed there from the moment it
    was made, without planning it again: the build's report with the
    output's path, size and sha256, as ``sdk.build`` gives them. A save
    whose build the engine keeps no more (another recipe's Build since, or
    a kill's new process) builds its recipe again: the same image."""
    _home(monkeypatch, tmp_path / "home")
    planned, plan = [], sdk._plan
    monkeypatch.setattr(sdk, "_plan", lambda *args, **kwargs: planned.append(1) or plan(*args, **kwargs))
    server, recipe = app.serve(_page.WEB), {"iso": str(usa_iso), "packs": {"fps_unlock": {}}}
    out = tmp_path / "out"
    out.mkdir()
    try:
        built = []
        _post(server.url, "api/build", recipe, built)
        kept = engine._BUILT[built[0]["build"]]
        assert kept.ended.wait(60) and len(planned) == 1   # hashed before Save asks
        saved, again = [], []
        _post(server.url, "api/save", {"recipe": built[0]["recipe"], "out": str(out / "a.iso"),
                                       "build": built[0]["build"]}, saved)
        assert len(planned) == 1
        made, _ = sdk.image(recipe)
        with open(out / "a.iso", "rb") as f:
            sha256 = hashlib.file_digest(f, "sha256").hexdigest()
        assert saved == [{"saved": built[0]["report"] | {"out": str(out / "a.iso"), "size": made.size,
                                                          "sha256": kept.sha}}]
        assert (sha256, (out / "a.iso").stat().st_size) == (kept.sha, made.size)
        _post(server.url, "api/build", {"iso": str(usa_iso), "packs": {}}, built)
        assert list(engine._BUILT) == [built[1]["build"]]   # another recipe's Build drops the last one's image
        _post(server.url, "api/save", {"recipe": built[0]["recipe"], "out": str(out / "b.iso"),
                                       "build": built[0]["build"]}, again)
        assert (len(planned), again[0]["saved"]["sha256"]) == (4, kept.sha)
    finally:
        server.close()
        engine._drop()


def test_a_second_launch_of_the_app_hashes_no_image_it_checked_and_dresses_no_body_it_matched(tmp_path, monkeypatch,
                                                                                            usa_iso):
    """Step 4.3i: the app's stores (``app.swapcache``, in the user cache
    folder) keep across launches the images the gate vouched for
    (``gate.STAMPS``) and a character's G4 match (``tools.characters.CACHE``,
    the swap's key): a second launch's pick of the same image hashes
    nothing, and its G4 dresses nothing, the same answers. Without the
    stores (``serve``'s), each launch works them out again."""
    from azurkit.app import swapcache
    from azurkit.tools import characters

    monkeypatch.setattr(gate, "STAMPS", None)
    monkeypatch.setattr(characters, "CACHE", None)
    hashed, dressed, digests, dress = [], [], sdk._digests, sdk._dress
    monkeypatch.setattr(sdk, "_digests", lambda *args: hashed.append(1) or digests(*args))
    monkeypatch.setattr(sdk, "_dress", lambda recipe: dressed.append(1) or dress(recipe))
    recipe = {"iso": str(usa_iso), "packs": {}, "character": {"species": "keylord"}}

    def launch() -> tuple[dict, dict]:   # this process's memos gone, as a new launch's
        sdk._STAMPS.clear()
        sdk._MATCHES.clear()
        return sdk.vanilla(str(usa_iso)), engine.JOBS["match"](recipe, progress=told.append)
    told = []
    try:
        first = launch()
        assert (hashed, dressed) == ([1], [1]) and told[0]["stage"] == "dress"   # the job's progress reaches its dress
        swapcache.install(tmp_path / "cache", tmp_path / "cache.key")
        assert launch() == first and (hashed, dressed) == ([1, 1], [1, 1])
        swapcache.install(tmp_path / "cache", tmp_path / "cache.key")   # the next launch's stores, on the same folder
        told.clear()
        assert launch() == first and (hashed, dressed) == ([1, 1], [1, 1]) and not told
    finally:
        sdk._STAMPS.clear()
        sdk._MATCHES.clear()


def test_the_apps_cache_folder_loads_only_what_this_install_wrote_there(tmp_path, monkeypatch):
    """SEC-4 (Step 4.3i): each file the app's stores write in the user cache
    folder (``app.swapcache``: the store's entries, the swap's pickled
    answers among them, and the images' stamps) carries an HMAC-SHA256
    under this install's own key
    (``cache.key``, 32 bytes made once, mode 0600, in the user data folder,
    never the cache folder a shared "speed-up" zip unpacks into). A pickle
    planted there that would run code is a miss and never loads, and so is a
    file copied from another install's cache, an older AzurKit's pickle
    (removed by the next write), a stamp for an image this install never
    checked, and every file once the key is gone; this install's own
    entries hit."""
    import pickle
    import stat

    from azurkit.app import swapcache
    from azurkit.tools import characters

    ran = tmp_path / "ran"

    class Planted:   # unpickling it makes ``ran``
        def __reduce__(self):
            return os.mkdir, (str(ran),)

    key, mine_key, their_key = hashlib.sha256(b"an answer").hexdigest(), tmp_path / "mine.key", tmp_path / "theirs.key"
    mine, theirs = swapcache.Folder(tmp_path / "cache", key=mine_key), swapcache.Folder(tmp_path / "x", key=their_key)
    entry, older = mine.kept.file("swap", key), tmp_path / "cache" / "swap" / f"{key}.pickle"
    assert not swapcache.key_file().is_relative_to(swapcache.root())
    mine.put(key, b"mine")
    assert swapcache.settle() and mine.get(key) == b"mine" and len(mine_key.read_bytes()) == 32
    assert os.name != "posix" or stat.S_IMODE(mine_key.stat().st_mode) == 0o600   # modes say nothing on Windows
    theirs.put(key, b"theirs")
    assert swapcache.settle()
    entry.write_bytes(theirs.kept.file("swap", key).read_bytes())
    assert mine.get(key) is None and theirs.get(key) == b"theirs"
    entry.write_bytes(pickle.dumps(Planted()))
    older.write_bytes(pickle.dumps(Planted()))   # 4.3i's file of it
    monkeypatch.setattr(characters, "CACHE", mine)
    text = str.encode, bytes.decode
    assert characters._kept(key, lambda: "worked out", *text) == "worked out" and not ran.exists()
    assert characters._kept(key, lambda: "again", *text) == "worked out"   # what it kept, this install's
    assert swapcache.settle() and not older.exists() and not ran.exists()

    stamps, their_stamps = (swapcache.Stamps(tmp_path / "stamps.json", key=mine_key),
                            swapcache.Stamps(tmp_path / "x" / "stamps.json", key=their_key))
    stamps.put("checked", "usa")
    their_stamps.put("never checked", "usa")
    assert stamps.get("checked") == "usa" and stamps.get("never checked") is None
    (tmp_path / "stamps.json").write_text(json.dumps({"checked": "usa", "never checked": "usa"}))   # forged
    assert stamps.get("checked") is stamps.get("never checked") is None
    (tmp_path / "stamps.json").write_bytes((tmp_path / "x" / "stamps.json").read_bytes())
    assert stamps.get("never checked") is None
    stamps.put("checked", "usa")
    mine.put(key, b"mine")
    assert swapcache.settle()
    mine_key.unlink()   # a new launch without its key: nothing it finds is its own
    assert swapcache.Folder(tmp_path / "cache", key=mine_key).get(key) is None
    assert swapcache.Stamps(tmp_path / "stamps.json", key=mine_key).get("checked") is None



@pytest.mark.parametrize("host", ["site", "app"])
def test_the_store_keeps_its_kinds_in_one_budget_and_reads_no_torn_or_altered_entry(host, tmp_path, monkeypatch):
    """D1015 (Step 4.3r): the store (``azurkit.store``; the site's sealed by
    a sha256, the app's ``app.swapcache.Kept`` by an HMAC under the
    install's key and written behind) keeps JSON, AZKP1 and the swap's bytes
    in one folder a kind under one budget across them: a write past it
    removes the least recently used entry (read or written), whatever its
    kind, and an older AzurKit's pickle, but nothing else (the stamps,
    another tool's folder, a kind's file of another name, the install's
    key; Clear neither). An entry torn short, altered, headless or moved to
    another key is a miss, never decoded; a value its kind can't hold is
    refused by name, writing nothing. The app's put answers before its write
    (the writer, a daemon thread a quit never waits on), and a get
    meanwhile answers from what it holds."""
    from azurkit import store
    from azurkit.app import swapcache

    folder, key = tmp_path / "cache", tmp_path / "data" / "cache.key"
    a, b, c, d = (hashlib.sha256(bytes([i])).hexdigest() for i in range(4))
    plan, dress, swap = "x" * 998, store.AZKP1 + b"\1" * 994, b"\2" * 1000   # each 1000 bytes as its kind keeps it
    most = 2 * (store.HEAD + 1000) + 100   # two of them and a small one
    kept = store.Store(folder, most) if host == "site" else swapcache.Kept(folder, most, key)
    settle = (lambda: True) if host == "site" else swapcache.settle
    for other in (folder / "stamps.json", folder / "builds" / f"{a}.kept", folder / "swap" / "notes.txt"):
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text("not the store's")
    (folder / "swap" / f"{d}.pickle").write_bytes(b"an older AzurKit's")
    assert kept.put("plans", a, plan) and kept.put("dresses", b, dress) and settle()
    for kind, at, ago in (("plans", a, 60), ("dresses", b, 120)):
        os.utime(kept.file(kind, at), (time.time() - ago,) * 2)
    assert kept.get("dresses", b) == dress   # read: the newest used, the plan the oldest
    assert kept.put("swap", c, swap) and settle()
    assert [kept.get("plans", a), kept.get("dresses", b), kept.get("swap", c)] == [None, dress, swap]
    assert {k: v["entries"] for k, v in kept.usage().items() if v["size"]} == {"dresses": 1, "swap": 1}
    assert not (folder / "swap" / f"{d}.pickle").exists()

    entry = kept.file("dresses", b)
    whole = entry.read_bytes()
    for bad in (whole[:-1], whole[:-1] + bytes([whole[-1] ^ 1]), whole[:store.HEAD - 1]):   # torn, altered, headless
        entry.write_bytes(bad)
        assert kept.get("dresses", b) is None
    kept.file("dresses", d).write_bytes(whole)   # moved to another key
    assert kept.get("dresses", d) is None
    kept.file("dresses", d).unlink()
    entry.write_bytes(whole)
    assert kept.get("dresses", b) == dress
    for kind, at, value, why in (("plans", d, float("nan"), "JSON"), ("memos", d, None, "None"),
                                 ("dresses", d, b"\1" * 10, "AZKP1"), ("swap", d, "text", "bytes"),
                                 ("nothing", d, 1, "no kind"), ("plans", "../x", 1, "hex digest")):
        with pytest.raises(ValueError, match=why):
            kept.put(kind, at, value)
    assert settle() and not any((folder / kind / f"{d}.kept").exists() for kind in store.KINDS if kind != "dresses")

    if host == "app":
        written, write = threading.Event(), store.Store.write
        monkeypatch.setattr(store.Store, "write", lambda self, *args: written.wait(30) and write(self, *args))
        assert kept.put("memos", d, {"view": [1]}) and not kept.file("memos", d).exists()
        assert kept.get("memos", d) == {"view": [1]} and swapcache._BEHIND.thread.daemon
        written.set()
        assert settle() and swapcache.Kept(folder, most, key).get("memos", d) == {"view": [1]}
        made = []   # a put of what makes its bytes: made once, behind the answer (a get before the writer answered from them)
        assert kept.put("swap", d, lambda: made.append(1) or b"made") and settle() and made == [1]
        assert kept.get("swap", d) == b"made"
        assert kept.put("swap", a, lambda: 1 / 0) and settle() and kept.get("swap", a) is None   # can't be made: a miss
    assert kept.clear(["swap"]) == ["swap"] and kept.get("swap", c) is None and kept.get("dresses", b) == dress
    kept.clear()
    assert sum(v["size"] for v in kept.usage().values()) == 0
    assert all(f.read_text() == "not the store's"
               for f in (folder / "stamps.json", folder / "builds" / f"{a}.kept", folder / "swap" / "notes.txt"))
    assert host == "site" or len(key.read_bytes()) == swapcache.KEY

def test_the_apps_api_builds_the_randomizer_tabs_seed_as_modkit_and_saves_its_spoiler(tmp_path, monkeypatch, usa_iso):
    """From the app's api in-process (Step 4.2c1): ``api/randomizer`` gives
    the Randomizer tab's view (``sdk.randomizer_settings``); ``api/build``
    with the tab's randomizer (seed 2, D144's defaults) and the packs on by
    default makes G3's seed case file by file, its logic verified, the
    plan ``api/plan`` makes of its seed (Track this seed's) its plan, its
    spoiler left out (the build shows sooner): ``api/spoiler`` gives the
    build's spoiler (Modkit's ``--spoiler`` file), which the engine makes
    from the plan it kept, and writes it where the page names, never over a
    file that is there, and ``api/settings_file`` the tab's settings
    file (D144); ``api/setup`` keeps the tab's setup (D915). Step 4.2c2:
    ``api/tracker`` gives Modkit's tracker verdicts at each state, Live's
    kit too, on the build's plan (its report's) and the max plan, and
    ``api/tracked`` remembers the plan and its marks, refusing anything
    else by name."""
    _home(monkeypatch, tmp_path / "home")   # where the app remembers
    server = app.serve(_page.WEB)
    defaults = sdk.catalog()["randomizer"]["defaults"]
    packs = {name: {} for name, pack in mods.PACKS.items() if pack.default_on}
    golden = record_goldens.recorded("pipelines.json")["randomize-full:seed=2,default"]

    def call(path: str, body: dict) -> dict:
        replies = []
        _post(server.url, path, body, replies, timeout=900)   # a randomized build plans and reads back 700 MB
        return replies[0]

    try:
        assert call("api/randomizer", {"given": {"settings": defaults, "packs": packs}}) == sdk.randomizer_settings(
            {"settings": defaults, "packs": packs})
        built = call("api/build", {"iso": str(usa_iso), "packs": packs, "xbr": [],
                                   "randomizer": {"seed": "2", "settings": defaults}})
        report = built["report"]
        assert report["result"] == {f: sha for f, sha in golden.items() if f != "ISO"}
        assert (report["randomizer"]["seed"], report["randomizer"]["logic_verified"]) == ("2", True)
        assert built["recipe"]["randomizer"] == {"seed": "2", "settings": defaults}
        assert call("api/plan", {"recipe": {"seed": "2", "settings": defaults}}) == {"plan": report["plan"]}
        assert "spoiler" not in report
        lines = sdk.spoiler(report["plan"])["lines"]   # the build's: its verdict after the head line (test_randomizer)
        text = "\n".join([lines[0], "logic_verified: true", *lines[1:]]) + "\n"
        assert call("api/spoiler", {}) == {"text": text}
        out = tmp_path / "seed 2 spoiler.txt"
        assert call("api/spoiler", {"out": str(out)}) == {"spoiler": {"out": str(out), "size": len(text.encode())}}
        assert out.read_text(encoding="utf-8") == text
        assert call("api/spoiler", {"out": str(out)}) == {
            "refused": f"{out} exists: choose another name, or delete it first"}
        saved = tmp_path / "settings.toml"   # Step 4.2c2: Save settings (D144)
        assert call("api/settings_file", {"out": str(saved), "settings": defaults}) == {"saved": {
            "out": str(saved), "size": len(sdk.randomizer_settings({"settings": defaults})["file"].encode())}}
        assert sdk.randomizer_settings({"file": saved.read_text(encoding="utf-8")})["settings"] == defaults
        assert call("api/settings_file", {"out": str(saved), "settings": defaults}) == {
            "refused": f"{saved} exists: choose another name, or delete it first"}
        setup = {"ticked": list(packs), "values": {}, "xbr": [],
                 "randomizer": {"on": True, "seed": "2", "settings": defaults}}
        assert call("api/setup", {"setup": setup}) == {}
        assert json.loads(app._config().read_text(encoding="utf-8"))["setup"] == setup

        def view(doc, marks, spoiler, kit=None):   # Step 4.2c2: the tracker from the app's api
            return call("api/tracker", {"given": {"plan": doc, "marks": marks, "spoiler": spoiler, "kit": kit,
                                                  "gems": shows_gems(marks)}})

        assert report["plan"] == _profile("default")
        for name in ("default", "max"):
            doc = _profile(name)
            for state, marks, kit in tracker_states(view, doc):
                for spoiler in (False, True):
                    key = f"{name}/{state}/{'spoiler' if spoiler else 'plain'}"
                    got = hashlib.sha256(tracking.digest(view(doc, marks, spoiler, kit)).encode()).hexdigest()
                    assert got[:32] == TRACKER[key], key
        tracked = {"plan": report["plan"], "marks": {report["plan"]["sha256"]: {"collected": ["w1/g0/r1717"]}}}
        assert call("api/tracked", {"tracker": tracked}) == {}
        assert call("api/tracked", {"tracker": tracked | {"iso": str(usa_iso)}}) == {
            "refused": "tracker: an object of plan, marks, endpoints, gems and collected only, or null"}
        assert call("api/tracked", {"tracker": tracked | {"endpoints": "gdb:1234"}})["refused"].startswith(
            "tracker: endpoints: 'gdb:1234': Live reads no gdbstub")
        assert app.Server.host_info(server)["tracker"] == tracked
    finally:
        server.close()


def test_live_in_the_apps_page_marks_what_the_game_shows_taken_and_follows_the_player(browser, tmp_path, monkeypatch):
    """Step 4.2c2 (D249; the app's alone, D882): in the app's page (its
    server in-process, headless), Live on for the tracked plan merges what
    the game shows into each tracker ask: a take marks its spot live (a
    blue check), the reach holds the element levels the game holds (R1.41:
    Modkit's verdicts with that kit), the status line names the level and
    the last take, Follow shows the player's level with "you are here" and
    Find me shows it again; another seed's game is named (red), a lost link
    says so and keeps the marks, and Live reconnects on the marks' journal;
    an error that ends Live unticks it, says why and gives the marks'
    tracker again (Modkit's). Endpoints Live can't read (a gdbstub, D257)
    are refused by name. The game is a scripted session (Modkit's ``live.Session``'s updates);
    Modkit's own Follower and reads, installed by the sync, give the events
    (R1.41b's two recordings replayed through them mark what Modkit's mark:
    the step's evidence)."""
    from azurkit.tools.randomizer.live import game, link

    _home(monkeypatch, tmp_path / "home")
    doc = _profile("default")
    (tmp_path / "plan.json").write_text(json.dumps(doc), encoding="utf-8")
    near = sorted(loc for loc, s in sdk.tracker({"plan": doc})["spots"].items() if s["state"] == "near")[0]
    level, kit = sdk.tracker({"plan": doc})["spots"][near]["level"], {"air": 0, "water": 1, "fire": 1, "earth": 0}
    at = game.Reading("running", game.REGIONS[0], level=level, settle=1, at=(1.0, 2.0, 3.0), yaw=0.5,
                      inv={"level.water": 1, "level.fire": 1, "obsi": 2})
    gates = {"other": threading.Event(), "lost": threading.Event(), "broken": threading.Event()}
    opened = []

    class Session:   # a running game, scripted: a take, the player standing, another seed's level, the link lost
        period = 0.02

        def __init__(self, xemu, spots, journal):
            opened.append((xemu, dict(journal)))
            if len(opened) > 1:   # the link back, broken: an error Live doesn't go on from
                gates["broken"].wait(60)
                raise RuntimeError("the scripted xemu broke")
            self.left = [game.Update(at, (game.Took(near, 0.5),))]

        def describe(self) -> str:
            return "xemu, scripted"

        def poll(self):
            if self.left:
                return self.left.pop(0)
            if gates["lost"].is_set():
                raise link.LinkLost("the scripted game ended")
            if gates["other"].is_set():
                return game.Update(game.Reading("running", game.REGIONS[0], level=level, settle=2, mismatch=True))
            return game.Update(at)

        def close(self) -> None:
            pass

    monkeypatch.setattr(game, "Session", Session)
    monkeypatch.setattr(link, "open_first", lambda eps: "xemu")
    monkeypatch.setattr(app.pictures, "folder", lambda: tmp_path / "no-maps")   # no pictures: the chips show
    server = app.serve(_page.WEB)
    shown = """() => [document.getElementById("track-dot").textContent, document.getElementById("track-dot").className,
                      document.getElementById("track-line").textContent, azurkit.tracker.state.level,
                      document.querySelector("#track-level .you")?.textContent ?? null]"""
    try:
        page = browser.new_page()
        page.goto(server.url)
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        _page.click(page, "tab-randomizer")
        _page.click(page, "rando-view-tracker")
        page.set_input_files("#track-open", str(tmp_path / "plan.json"))
        _page.until(page, "() => azurkit.tracker.state.view && !azurkit.tracker.state.running", 300)
        _page.fill(page, "track-endpoints", "gdb:1234")
        page.evaluate("() => document.getElementById('track-endpoints').dispatchEvent(new Event('change'))")
        _page.click(page, "track-live")
        _page.until(page, "() => !document.getElementById('track-live').checked")
        assert page.evaluate("() => document.getElementById('status').textContent").startswith(
            "Endpoints: 'gdb:1234': Live reads no gdbstub")
        _page.fill(page, "track-endpoints", "")
        page.evaluate("() => document.getElementById('track-endpoints').dispatchEvent(new Event('change'))")
        clicked = time.monotonic()   # the scripted take comes after the click, on this process's clock (the server's)
        _page.click(page, "track-live")
        # What the page shows as it first shows the take. Each ask (every 0.7 s) writes Live's line anew, with the
        # take's age as it then is, so the test bounds that age by its own clock since the click (Step 4.4ci45: Windows'
        # Firefox read "0:12 ago" where the test wanted under 10 s, from an ask 12 s after the take)
        dot, state, line, follows, you = _page.until(
            page, f"() => azurkit.tracker.state.live?.here && azurkit.tracker.state.marks.live && ({shown})()")
        since = time.monotonic() - clicked
        view = page.evaluate("() => azurkit.tracker.state.view")
        assert tracking.digest(view) == tracking.digest(sdk.tracker(
            {"plan": doc, "marks": {"collected": [near], "live": {near: 0.5}}, "kit": kit, "held": dict(at.inv)}))
        assert (dot, state, follows, you) == ("●", "live", level, "● you are here")
        item = sdk.tracker({"plan": doc, "spoiler": True})["spots"][near]["name"]
        took, _, ago = line.rpartition(", ")
        age = re.fullmatch(r"(\d+):([0-5]\d) ago", ago)
        assert took == f"{level} · USA · xemu, scripted · last: {item} ({level})" and age, line
        assert 60 * int(age[1]) + int(age[2]) <= since, (line, since)   # the take's age, never older than Live
        assert page.evaluate(f"() => document.querySelector(`#track-level .spot[data-loc='{near}']`).className").split()[:2] == [
            "spot", "live"]   # (and "fresh" while its pickup flashes)
        page.evaluate("() => document.querySelector('#track-level .back').click()")   # by hand: Follow goes off
        assert page.evaluate("() => [azurkit.tracker.state.level, document.getElementById('track-follow').checked]") == [
            None, False]
        _page.click(page, "track-find")
        assert page.evaluate("() => azurkit.tracker.state.level") == level
        gates["other"].set()
        _page.until(page, "() => document.getElementById('track-dot').className === 'other'")
        assert page.evaluate("() => document.getElementById('track-levels').textContent").startswith(
            "xemu runs another seed or build")
        gates["lost"].set()
        _page.until(page, "() => document.getElementById('track-dot').className === 'lost'")
        assert page.evaluate("() => azurkit.tracker.state.marks") == {"collected": [near], "live": {near: 0.5}}
        gates["broken"].set()
        _page.until(page, "() => !document.getElementById('track-live').checked && !azurkit.tracker.state.live"
                          " && !azurkit.tracker.state.running && !azurkit.tracker.state.queue.length")
        assert page.evaluate("() => document.getElementById('track-line').textContent") == (
            "Live stopped: the scripted xemu broke")
        assert opened == [("xemu", {"slot": None, "newest": None}), ("xemu", {"slot": None, "newest": 0.5})]
        assert tracking.digest(page.evaluate("() => azurkit.tracker.state.view")) == tracking.digest(
            sdk.tracker({"plan": doc, "marks": {"collected": [near], "live": {near: 0.5}}}))
        _page.check_csp(page)
        page.close()
    finally:
        server.close()


# A level map's canvas, as the tests read it: what each overlay the pointer finds says (its tip), and a click there
MAP_HITS = "() => azurkit.tracker.map.hits.map((h) => h.tip)"
# Each floor button's text: its lines, and how far its middle sits from its radio's
FLOOR_BUTTONS = """() => [...document.querySelectorAll("#map-floors label")].map((label) => {
    const radio = label.querySelector("input").getBoundingClientRect(), text = document.createRange();
    text.selectNodeContents(label.lastChild);
    const box = text.getBoundingClientRect();
    return [text.getClientRects().length, Math.abs(box.top + box.bottom - radio.top - radio.bottom) / 2];
})"""
COUNTER = "() => document.getElementById('track-count').textContent"
MAP_CLICK = """([x, y]) => {
    const map = azurkit.tracker.map, c = document.getElementById("map-canvas"), r = c.getBoundingClientRect();
    const [cx, cy] = map.at(x, y), at = { clientX: r.left + cx, clientY: r.top + cy, bubbles: true };
    c.dispatchEvent(new PointerEvent("pointerdown", at));
    c.dispatchEvent(new PointerEvent("pointerup", at));
}"""


def test_the_apps_tracker_shows_a_levels_shipped_map_and_lives_gem_takes_remove_its_dots(
        browser, tmp_path, monkeypatch):
    """Step 4.2c3 (R1.43, D928): the app's page shows the tracker's
    pictures it ships (Step 4.3f: ``api/art`` and ``art/<version>/``, from
    its bundle or the checkout, no image read), the world map as soon as
    the Tracker shows, then a level's map in place of its chips once a click
    on the world map opens it: its tracked spots (a click on one
    marks it), a click on an exit opens the level it leads to, the wheel
    zooms about the pointer and a double click on ground fits it again, w1
    zoomed past its pixels draws its floor's detail picture (Step 4.3l, from
    the same folder), and a smaller window fits it smaller. With Gems on, each gem spot of the
    floor shown is a dot, the floor buttons (each on one line, its text on
    its radio's middle, badged with its spots not collected yet) and the count say how many are left, the counter
    row the gems taken of all (R1.43's words), and Live (the app's: a
    scripted game taking a gem) takes its dot away. No CSP violation."""
    from azurkit.tools.randomizer.live import game, link

    _home(monkeypatch, tmp_path / "home")
    doc = _profile("default")
    (tmp_path / "plan.json").write_text(json.dumps(doc), encoding="utf-8")
    first = sdk.tracker({"plan": doc, "gems": True})
    near = sorted(loc for loc, s in first["spots"].items() if s["state"] == "near")[0]
    level = first["spots"][near]["level"]
    index = json.loads((app.pictures.folder() / "maps.json").read_text(encoding="utf-8"))
    at = game.Reading("running", game.REGIONS[0], level=level, settle=1, at=(1.0, 2.0, 3.0), yaw=0.5)
    gem = {}   # the gem the game takes: the first of the floor the map opens on, once the map is drawn

    class Session:   # a running game, scripted: the player takes the gem
        period = 0.02

        def __init__(self, xemu, spots, journal):
            assert any(s.loc == gem["id"] and s.gem for s in spots.spots)   # Live reads the gem spots with Gems on
            self.left = [game.Update(at, (game.Gem(gem["id"], 1, 0.75),))]

        def describe(self) -> str:
            return "xemu, scripted"

        def poll(self):
            return self.left.pop(0) if self.left else game.Update(at)

        def close(self) -> None:
            pass

    monkeypatch.setattr(game, "Session", Session)
    monkeypatch.setattr(link, "open_first", lambda eps: "xemu")
    server = app.serve(_page.WEB)
    try:
        page = browser.new_page(viewport={"width": 1100, "height": 820})
        page.goto(server.url)
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        _page.click(page, "tab-randomizer")
        _page.click(page, "rando-view-tracker")
        _page.until(page, "() => !document.getElementById('track-maps').hidden && azurkit.tracker.map.level === null"
                          " && Boolean(azurkit.tracker.map.pictures?.[0]?.bitmap)", 60)   # before any plan
        page.set_input_files("#track-open", str(tmp_path / "plan.json"))
        _page.until(page, "() => azurkit.tracker.state.view && !azurkit.tracker.state.running", 300)
        assert page.evaluate("() => azurkit.tracker.art.status.error") is None
        entry = index["levels"][level]
        gem |= next(g for g in sorted(entry["gems"], key=lambda g: g["id"]) if g["at"][2] == entry["main"])
        x, y, w, h = index["world"]["levels"][level]
        page.evaluate(MAP_CLICK, [x + w / 2, y + h / 2])   # the level on the world map
        _page.until(page, f"() => azurkit.tracker.map.level === '{level}' && azurkit.tracker.map.hits.length")
        assert page.evaluate("() => document.getElementById('track-level').hidden") is True
        place = next(i["at"] for i in entry["items"] + entry["spots"] if i["id"] == near)
        assert place[2] == entry["main"] and "Item spot: reachable now" in page.evaluate(MAP_HITS)
        page.evaluate(MAP_CLICK, place[:2])
        _page.until(page, f"() => !azurkit.tracker.state.running && azurkit.tracker.state.marks.collected?.includes('{near}')")
        exit_ = next(x for x in entry["exits"] if any(p[2] == entry["main"] for p in x["at"]))
        page.evaluate(MAP_CLICK, next(p for p in exit_["at"] if p[2] == entry["main"])[:2])
        assert page.evaluate("() => [azurkit.tracker.state.level, azurkit.tracker.map.level]") == [exit_["to"]] * 2
        page.evaluate("(level) => azurkit.tracker.map.show(level, true)", level)
        fitted = page.evaluate("() => azurkit.tracker.map.fitted")
        page.evaluate("""() => { const c = document.getElementById("map-canvas"), r = c.getBoundingClientRect();
            c.dispatchEvent(new WheelEvent("wheel", { deltaY: -300, clientX: r.left + 100, clientY: r.top + 100,
                                                      bubbles: true, cancelable: true })); }""")
        assert page.evaluate("() => azurkit.tracker.map.s") > fitted * 1.5
        page.evaluate("""() => { const c = document.getElementById("map-canvas"), r = c.getBoundingClientRect();
            const at = { clientX: r.left + 2, clientY: r.bottom - 2, bubbles: true };
            c.dispatchEvent(new PointerEvent("pointerdown", at)); c.dispatchEvent(new PointerEvent("pointerup", at));
            c.dispatchEvent(new MouseEvent("dblclick", at)); }""")
        assert page.evaluate("() => azurkit.tracker.map.s") == fitted
        page.evaluate("() => { const m = azurkit.tracker.map; m.show('w1', true); m.view(m.top()); }")
        _page.until(page, "() => azurkit.tracker.map.drawnFor.level === 'w1' && azurkit.tracker.map.drawnFor.detail", 60)
        page.evaluate("(level) => azurkit.tracker.map.show(level, true)", level)
        page.set_viewport_size({"width": 900, "height": 640})
        _page.until(page, f"() => azurkit.tracker.map.fitted < {fitted}")
        _page.click(page, "track-gems")
        _page.until(page, "() => azurkit.tracker.state.view.gems && !azurkit.tracker.state.running")
        dots = sum(1 for g in entry["gems"] if g["at"][2] == entry["main"])
        tips = page.evaluate(MAP_HITS)
        assert sum(t is not None and t.split(" ")[0].lower() in ("diamond", "emerald", "ruby", "sapphire") for t in tips) == dots
        floors = page.evaluate("""() => [...document.querySelectorAll('#map-floors label')].map((l) => [
            [...l.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim(),
            l.querySelector(".left")?.textContent ?? null])""")
        states = page.evaluate("() => azurkit.tracker.state.view.spots")
        left = [sum(1 for i in entry["items"] + entry["spots"] if i["at"][2] == k
                    and states[i["id"]]["state"] not in ("got", "live")) for k in range(len(entry["floors"]))]
        assert len(entry["floors"]) < 2 or (floors[entry["main"]][0] == f"{entry['main'] + 1} · {dots}"
                                            and [b for _, b in floors] == [str(n) if n else None for n in left])
        assert [b for b in page.evaluate(FLOOR_BUTTONS) if b[0] != 1 or b[1] > 1] == []
        gems = sum(n for _, n in first["gems"]["counts"].values())
        _page.until(page, f"() => ({COUNTER})().endsWith(' · Gems 0 of {gems}')")
        page.evaluate("() => document.getElementById('track-follow').click()")   # Follow off: the floor shown stays
        _page.click(page, "track-live")
        _page.until(page, f"() => azurkit.tracker.state.view.gems.spots['{gem['id']}'].taken === 1"
                          " && !azurkit.tracker.state.running")
        _page.until(page, f"() => azurkit.tracker.map.hits.filter((h) => /^(Diamond|Emerald|Ruby|Sapphire)/"
                          f".test(h.tip ?? '')).length === {dots - 1}")
        assert page.evaluate("() => azurkit.tracker.state.marks.gems") == {gem["id"]: [0.75]}
        _page.until(page, f"() => ({COUNTER})().endsWith(' · Gems 1 of {gems}')")
        _page.check_csp(page)
        page.close()
    finally:
        server.close()


def test_the_apps_tracker_opens_any_levels_map_with_the_vanilla_games_items_before_a_plan(browser, tmp_path, monkeypatch):
    """Step 4.4u3: the app's page, with no plan tracked and no image, opens
    the level picked on Map with the vanilla game's spots (its engine's
    tracker with no plan, ``api/tracker``): each ringed plain with its
    vanilla item's icon, its tip naming that item, a click on it marking
    nothing; another level picked switches; a plan opened then shows the
    level browsed with the plan's spots. No CSP violation."""
    _home(monkeypatch, tmp_path / "home")
    (tmp_path / "plan.json").write_text(json.dumps(_profile("default")), encoding="utf-8")
    bare = sdk.tracker({})
    server = app.serve(_page.WEB)
    try:
        page = browser.new_page(viewport={"width": 1100, "height": 820})
        page.goto(server.url)
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        _page.click(page, "tab-randomizer")
        _page.click(page, "rando-view-tracker")
        _page.until(page, "() => !document.getElementById('track-pick').disabled", 300)
        for level in ("w1", "e6"):
            page.select_option("#track-pick", level)
            _page.until(page, f"() => azurkit.tracker.map.level === '{level}' "
                              "&& azurkit.tracker.map.pictures.every((p) => p.bitmap)", 60)
            at, picked, _, spots, tips = page.evaluate(BROWSED)
            assert (at, picked, [m["loc"] for m in spots], {m["ring"] for m in spots}) == (
                level, level, sorted(loc for loc, s in bare["spots"].items() if s["level"] == level), {"vanilla"})
            assert tips and all(not act and tip.split(" · ")[0] in {s["name"] for s in bare["spots"].values()}
                                for tip, act in tips)
        page.set_input_files("#track-open", str(tmp_path / "plan.json"))
        _page.until(page, "() => azurkit.tracker.state.view && !azurkit.tracker.state.running", 300)
        at, _, _, spots, _ = page.evaluate(BROWSED)
        assert at == "e6" and spots and {m["ring"] for m in spots} <= {"near", "skip", "far"}
        _page.check_csp(page)
        page.close()
    finally:
        server.close()


class _Played:
    """A running game for the app's Live, scripted by the test: the player's level and place (``at``, the feet), and
    the takes the next poll reports (``takes``)."""

    def __init__(self, level: str, at: tuple):
        self.level, self.at, self.takes = level, at, []


def _live_map(browser, tmp_path, monkeypatch, played: _Played, doc: dict):
    """The app's page (its server in-process, headless) tracking ``doc`` with Live on over ``played``'s game: (the
    server, the page), once Live sees the player."""
    from azurkit.tools.randomizer.live import game, link

    _home(monkeypatch, tmp_path / "home")
    (tmp_path / "plan.json").write_text(json.dumps(doc), encoding="utf-8")

    class Session:
        period = 0.02

        def __init__(self, xemu, spots, journal):
            pass

        def describe(self) -> str:
            return "xemu, scripted"

        def poll(self):
            takes, played.takes = tuple(played.takes), []
            return game.Update(game.Reading("running", game.REGIONS[0], level=played.level, settle=1, at=played.at,
                                            yaw=0.0), takes)

        def close(self) -> None:
            pass

    monkeypatch.setattr(game, "Session", Session)
    monkeypatch.setattr(link, "open_first", lambda eps: "xemu")
    server = app.serve(_page.WEB)
    page = browser.new_page(viewport={"width": 1100, "height": 820})
    page.goto(server.url)
    _page.until(page, "() => globalThis.azurkit?.ready", 120)
    _page.click(page, "tab-randomizer")
    _page.click(page, "rando-view-tracker")
    page.set_input_files("#track-open", str(tmp_path / "plan.json"))
    _page.until(page, "() => azurkit.tracker.state.view && !azurkit.tracker.state.running", 300)
    _page.click(page, "track-live")
    _page.until(page, f"() => azurkit.tracker.state.live?.here === '{played.level}'"
                      f" && azurkit.tracker.map.level === '{played.level}'")
    return server, page


# Whether Live's last reading the page shows puts the player at ``at`` (the scripted game's place, through the app)
SEEN = """(at) => azurkit.tracker.state.live?.seen?.at.every((v, k) => Math.abs(v - at[k]) < 1e-6)"""


def _floor_table(level: str):
    """``level``'s shipped floor table (``floors.json``, maps.storeys' packing): (its maps.json entry, each pixel's
    code as rows, {(px, py): [(lowest, highest, floor)]} of the pixels on several floors)."""
    import numpy as np

    root = app.pictures.folder()
    entry = json.loads((root / "maps.json").read_text())["levels"][level]
    shipped = json.loads((root / "floors.json").read_text())
    raw = zlib.decompress(base64.b64decode(shipped["levels"][level]))
    (w, h), unit = entry["size"], shipped["unit"]
    code = np.frombuffer(raw[:w * h], np.uint8)
    many = np.flatnonzero(code == 255)
    count = np.frombuffer(raw[w * h:w * h + len(many)], np.uint8).astype(int)
    n, at = int(count.sum()), w * h + len(many)
    step = np.frombuffer(raw[at:at + 2 * n], np.uint8).astype(int)
    lo = np.cumsum(np.where((v := step[:n] | step[n:] << 8) >= 0x8000, v - 0x10000, v)) * unit
    span = np.frombuffer(raw[at + 2 * n:at + 3 * n], np.uint8) * unit
    floor = np.frombuffer(raw[at + 3 * n:at + 4 * n], np.uint8)
    first = np.r_[0, np.cumsum(count)]
    storeys = {(int(p % w), int(p // w)): [(float(lo[i]), float(lo[i] + span[i]), int(floor[i]))
                                           for i in range(first[k], first[k + 1])] for k, p in enumerate(many)}
    return entry, code.reshape(h, w), storeys


def test_follow_shows_the_floor_the_player_stands_on_and_keeps_a_floor_picked_by_hand(browser, tmp_path, monkeypatch):
    """Step 4.3 live tracker (the owner, 2026-11-01: "can you make it
    automatically switch to the floor the player is on?"): with Follow
    on, the app's map shows the floor under the player's feet by the
    shipped floor table (floors.json), the floor all of their pixel's
    storeys are on, else the storey nearest their height: in w2 the
    ledge the owner stood on (floor 2, its main floor water there), a
    pixel with two floors' storeys by height, and at a seam the floor
    they were on holds while its ground lies within 2 m. A floor picked
    by hand stays until the player's floor changes, and with Follow off
    the map keeps the floor shown wherever they go. In the town temple
    (the tower's lock rewards), a player on its floor coming into town
    sees town-5, though town's main floor has ground above and below."""
    import numpy as np

    entry, code, storeys = _floor_table("w2")
    (x0, y1, s), main = entry["frame"], entry["main"]
    world = lambda px, py, z=0.0: (x0 + (px + 0.5) / s, y1 - (py + 0.5) / s, z)   # noqa: E731 (a pixel's middle)
    r = int(np.ceil(2 * s)) + 2

    def alone(px, py, floor):   # every pixel round it within r all on that floor (or none)
        box = code[max(py - r, 0):py + r + 1, max(px - r, 0):px + r + 1]
        return bool(np.isin(box, (0, floor + 1)).all())
    upper = next(k for k in range(len(entry["floors"])) if k != main)
    ys, xs = np.nonzero(code == main + 1)
    far = next((x, y) for x, y in zip(xs, ys) if alone(x, y, main))
    seam = next((x, y, x + dx) for x, y in zip(xs, ys) for dx in (-1, 1)
                if 0 <= x + dx < code.shape[1] and code[y, x + dx] == upper + 1)

    def apart(xy, a, b):   # every pixel round it holds a's and b's storeys alone, b's over 2 m above a's lowest
        sts = [storeys.get((xy[0] + dx, xy[1] + dy)) for dy in range(-r, r + 1) for dx in range(-r, r + 1)]
        return all(st and {f for *_, f in st} == {a[2], b[2]} and all(lo - a[0] > 2 for lo, _, f in st if f == b[2])
                   for st in sts)
    stacked = next((xy, a, b) for xy, st in sorted(storeys.items()) for a in st for b in st
                   if a[2] != b[2] and b[0] - a[1] > 4 and apart(xy, a, b))
    played = _Played("w2", (-51.546, -84.284, 8.063))   # the owner's ledge: floor 2 (w2-2), the main floor water
    server, page = _live_map(browser, tmp_path, monkeypatch, played, _profile("default"))

    def stand(at, floor=None) -> int:
        played.at = tuple(float(v) for v in at)
        _page.until(page, f"() => ({SEEN})({json.dumps(list(played.at))})"
                    + (f" && azurkit.tracker.map.floor === {floor}" if floor is not None else ""))
        return page.evaluate("() => azurkit.tracker.map.floor")

    try:
        _page.until(page, "() => azurkit.tracker.map.floor === 1")
        assert stand(world(seam[2], seam[1]), upper) == upper
        assert stand(world(seam[0], seam[1])) == upper   # the seam: the floor they came from holds
        assert stand(world(*far), main) == main
        (px, py), a, b = stacked
        assert stand(world(px, py, b[0]), b[2]) == b[2] and stand(world(px, py, a[0]), a[2]) == a[2]
        assert stand(world(*far), main) == main
        page.evaluate(f"() => document.querySelector(\"#map-floors input[data-floor='{upper}']\").click()")
        assert stand(world(far[0], far[1], 0.25)) == upper   # picked by hand: theirs is the same
        page.evaluate("() => document.getElementById('track-follow').click()")   # Follow off
        assert stand(world(seam[2], seam[1])) == upper and stand(world(*far)) == upper
        page.evaluate(f"() => document.querySelector(\"#map-floors input[data-floor='{main}']\").click()")
        assert stand(world(seam[2], seam[1])) == main
        page.evaluate("() => document.getElementById('track-follow').click()")   # Follow on: into town, its main shown
        town, _, at_town = _floor_table("town")
        (tx0, ty1, ts), temple = town["frame"], town["floors"].index("town-5")
        px, py, _ = next(i["at"] for i in town["items"] if i["id"] == "town/g1/r15")
        z = next(lo for lo, _, f in at_town[(int(px), int(py))] if f == temple)   # the temple's floor at the reward
        played.level, played.at = "town", (tx0 + px / ts, ty1 - py / ts, z)
        _page.until(page, f"() => azurkit.tracker.map.level === 'town' && azurkit.tracker.map.floor === {temple}")
        _page.check_csp(page)
        page.close()
    finally:
        server.close()


def test_follow_eases_to_the_player_past_the_views_middle_and_a_refresh_never_moves_a_zoomed_map(
        browser, tmp_path, monkeypatch):
    """Step 4.3 live tracker (the owner: "every time the map refreshes while
    i am zoomed in, it is shaking"): Live's reads of a player standing
    still jitter, and none of them moves a zoomed map (Follow on, the
    player in the middle of the view) or the map's room (Live's bar keeps
    its size from poll to poll, the ask's "…" or none, at any width); a player who walks out of the view's
    middle has the map ease after them (several frames, then centred);
    with Follow off a refresh never moves the zoomed map."""
    entry = json.loads((app.pictures.folder() / "maps.json").read_text())["levels"]["w2"]
    (x0, y1, s), (w, h) = entry["frame"], entry["size"]
    middle = (x0 + w / 2 / s, y1 - h / 2 / s, 0.0)
    played = _Played("w2", middle)
    server, page = _live_map(browser, tmp_path, monkeypatch, played, _profile("default"))
    view = """() => { const m = azurkit.tracker.map, r = document.getElementById("map-room").getBoundingClientRect();
                      return [m.s, ...m.o, r.top, r.height, ...m.at(...m.pixel(azurkit.tracker.state.live.seen))]; }"""

    def stand(at) -> list:
        played.at = tuple(float(v) for v in at)
        _page.until(page, f"() => ({SEEN})({json.dumps(list(played.at))}) && !azurkit.tracker.map.ease")
        return page.evaluate(view)

    try:
        page.evaluate("() => { const m = azurkit.tracker.map; m.view(m.fitted * 4); "
                      "m.see(...m.pixel(azurkit.tracker.state.live.seen), true); }")
        held = stand(middle)
        for k in range(6):   # the reads' jitter, a few cm each poll
            assert stand((middle[0] + 0.04 * (-1) ** k, middle[1] - 0.03 * k % 2, 0.01 * k))[:5] == held[:5]
        page.evaluate("() => { const m = azurkit.tracker.map; m.drawn = []; const draw = m.draw.bind(m); "
                      "m.draw = () => { draw(); m.drawn.push(m.o[0]); }; }")   # each frame's view
        after = stand((middle[0] + 60, middle[1], 0.0))   # out of the view's middle
        frames = page.evaluate("() => azurkit.tracker.map.drawn")
        cw = page.evaluate("() => azurkit.tracker.map.room()[0]")
        between = {o for o in frames if held[1] < o < after[1]}
        assert len(between) >= 3 and frames[-1] == after[1] and abs(after[5] - cw / 2) < 2
        page.evaluate("() => document.getElementById('track-follow').click()")   # Follow off
        moved = stand((middle[0] + 60, middle[1] + 80, 0.0))
        assert stand((middle[0] + 60, middle[1] - 80, 0.0))[:5] == moved[:5] == after[:5]
        busy = """() => { const st = document.getElementById("track-status"), was = st.textContent;
            const top = (text) => { st.textContent = text; return document.getElementById("map-room")
                .getBoundingClientRect().top; };
            const out = [top(""), top("\u2026")]; st.textContent = was; return out; }"""
        for width in (640, 900, 1040, 1380):   # where Live's bar wraps, or doesn't
            page.set_viewport_size({"width": width, "height": 820})
            idle, asking = page.evaluate(busy)
            assert idle == asking, width
        _page.check_csp(page)
        page.close()
    finally:
        server.close()


def test_other_floors_items_show_faintly_fainter_with_distance_with_no_tooltip_or_click(browser, tmp_path, monkeypatch):
    """D1044 (the owner: "yes, faintly, more faint the further away the floor
    is, and hovering over them should not have a tooltip"): a level's map
    draws each tracked spot of its other floors on the floor shown, fainter
    the further its floor; no tooltip over one and a click marks nothing;
    the floor buttons' counts stay; Items off hides them, and a collected one
    shows only with Show collected."""
    doc = _profile("default")
    index = json.loads((app.pictures.folder() / "maps.json").read_text(encoding="utf-8"))["levels"]
    spots = sdk.tracker({"plan": doc})["spots"]
    where = {i["id"]: i["at"] for e in index.values() for i in e["items"] + e["spots"]}
    floors = {}   # level -> floor -> its tracked spots
    for loc, s in spots.items():
        if loc in where:
            floors.setdefault(s["level"], {}).setdefault(where[loc][2], []).append(loc)
    level, shown = next((lv, f) for lv, on in sorted(floors.items()) for f in sorted(on)
                        if len({abs(g - f) for g in on if g != f}) >= 2)
    others = {loc: abs(where[loc][2] - shown) for f, locs in floors[level].items() if f != shown for loc in locs}
    x0, y1, sc = index[level]["frame"]
    player = (x0 + where[next(iter(others))][0] / sc, y1 - where[next(iter(others))][1] / sc, 0.0)
    server, page = _live_map(browser, tmp_path, monkeypatch, _Played(level, player), doc)
    read = """() => { const m = azurkit.tracker.map; return m.faint; }"""
    try:
        page.evaluate("() => document.getElementById('track-follow').click()")   # Follow off: the floor stays
        page.evaluate(f"() => {{ const m = azurkit.tracker.map; m.floor = {shown}; m.draw(); }}")
        faint = page.evaluate(read)
        assert set(faint) == set(others)
        by = {d: {faint[loc] for loc, n in others.items() if n == d} for d in set(others.values())}
        steps = sorted(by)
        assert all(len(by[d]) == 1 for d in steps) and all(0 < min(by[d]) < 1 for d in steps)
        assert all(min(by[a]) > min(by[b]) for a, b in zip(steps, steps[1:]))

        loc = next(loc for loc in others if page.evaluate("""([x, y]) => { const m = azurkit.tracker.map,
            [cx, cy] = m.at(x, y); return !m.hits.some((h) => Math.hypot(h.x - cx, h.y - cy) < (h.r || 0) + 14); }""",
            where[loc][:2]))
        got = page.evaluate("""([x, y]) => { const m = azurkit.tracker.map, c = document.getElementById("map-canvas");
            const r = c.getBoundingClientRect(), [cx, cy] = m.at(x, y);
            c.dispatchEvent(new PointerEvent("pointermove", { clientX: r.left + cx, clientY: r.top + cy, bubbles: true }));
            return document.getElementById("map-tip").hidden; }""", where[loc][:2])
        assert got is True
        page.evaluate(MAP_CLICK, where[loc][:2])   # a click on a shown spot would ask the engine as it returns
        _page.until(page, "() => !azurkit.tracker.state.running && !azurkit.tracker.state.queue.length")
        assert not page.evaluate("() => azurkit.tracker.state.marks.collected?.length")

        counts = page.evaluate("""() => [...document.querySelectorAll("#map-floors label")].map((l) => Number(
            l.querySelector(".left")?.textContent ?? 0))""")
        assert counts == [len(floors[level].get(k, ())) for k in range(len(index[level]["floors"]))]

        page.evaluate("(loc) => azurkit.tracker.ask({ toggle: loc })", loc)   # collected: off, then dimmed
        _page.until(page, "() => azurkit.tracker.state.marks.collected?.length === 1")
        _page.until(page, f"() => !(({read})())[{json.dumps(loc)}]")
        page.evaluate("() => document.getElementById('track-collected').click()")
        _page.until(page, f"() => (({read})())[{json.dumps(loc)}] < {faint[loc]}")
        page.evaluate("""() => document.querySelector('#map-switches input[data-kind="item"]').click()""")
        assert page.evaluate(read) == {}
    finally:
        page.close()
        server.close()


# From now on, what the tracker shows at each change of its page (``globalThis.shown``): the Got line's text and
# animation (null while it is hidden), the flashing Got count's text and its animations (null while none flashes) and
# the map's tips at spot ``loc``, read as the change is made, not when a later look of the test's comes: the count
# flashes 0.9 s, which a slowed runner's two reads outlasted (4.4ci27's slowed pure tier read it gone)
SHOWN = """(loc) => {
    globalThis.shown = [];
    const tips = () => { const m = azurkit.tracker.map, e = m.entry(m.level);
        const at = [...e.items, ...e.spots].find((i) => i.id === loc).at, [x, y] = m.at(at[0], at[1]);
        return m.hits.filter((h) => h.act && Math.hypot(h.x - x, h.y - y) < 1).map((h) => h.tip); };
    new MutationObserver(() => {
        const line = document.getElementById("track-got"), got = document.querySelector("#track-count .got.fresh");
        shown.push([line.hidden ? null : [line.textContent, getComputedStyle(line).animationName],
                    got ? [got.textContent, got.getAnimations().length] : null, tips()]);
    }).observe(document.getElementById("tracker"), { subtree: true, childList: true, characterData: true,
                                                   attributes: true });
}"""


def test_a_collected_spot_leaves_the_map_and_a_live_pickup_flashes_and_says_what_was_got(browser, tmp_path, monkeypatch):
    """Step 4.3 live tracker (the owner, 2026-11-01: "when an item is
    collected on the tracker, can you remove it from the map, with a toggle
    option for showing them instead? And make it more noticeable when they
    are collected"): a spot marked collected (a click, or Live) leaves the
    level's map; Show collected (remembered, by the app too) shows it again,
    dimmed and clickable; a Live pickup flashes its spot a moment before it leaves,
    flashes the Got count and says "Got: <item> · <level>" for a few
    seconds; with reduced motion the line and the count are a plain
    highlight, nothing animated."""
    from azurkit.tools.randomizer.live import game

    doc = _profile("default")
    index = json.loads((app.pictures.folder() / "maps.json").read_text(encoding="utf-8"))["levels"]
    spots = sdk.tracker({"plan": doc, "spoiler": True})["spots"]
    where = {i["id"]: i["at"] for e in index.values() for i in e["items"] + e["spots"]}
    on_main = {}   # each level's tracked spots on its main floor
    for loc, s in sorted(spots.items()):
        if loc in where and where[loc][2] == index[s["level"]]["main"]:
            on_main.setdefault(s["level"], []).append(loc)
    level, clicked, got, still = next((lv, near[0], *[loc for loc in locs if loc != near[0]][:2])
                                      for lv, locs in on_main.items() if len(locs) >= 3
                                      and (near := [loc for loc in locs if spots[loc]["state"] == "near"]))
    x0, y1, sc = index[level]["frame"]
    played = _Played(level, (x0 + where[got][0] / sc, y1 - where[got][1] / sc, 0.0))
    server, page = _live_map(browser, tmp_path, monkeypatch, played, doc)
    drawn = """(loc) => { const m = azurkit.tracker.map, e = m.entry(m.level);
        const at = [...e.items, ...e.spots].find((i) => i.id === loc).at, [x, y] = m.at(at[0], at[1]);
        return m.hits.filter((h) => h.act && Math.hypot(h.x - x, h.y - y) < 1).map((h) => h.tip); }"""
    try:
        page.evaluate("() => document.getElementById('track-follow').click()")   # Follow off: the floor stays
        page.evaluate(f"() => {{ const m = azurkit.tracker.map; m.floor = {index[level]['main']}; m.draw(); }}")
        assert page.evaluate(drawn, clicked)   # reachable now: on the map
        page.evaluate(MAP_CLICK, where[clicked][:2])
        _page.until(page, f"() => azurkit.tracker.state.marks.collected?.includes('{clicked}')"
                          " && !azurkit.tracker.state.running")
        assert page.evaluate(drawn, clicked) == []
        _page.click(page, "track-collected")
        assert page.evaluate(drawn, clicked) == [f"{spots[clicked]['name']}: collected"]
        assert page.evaluate("() => azurkit.tracker.state.kept.collected") is True
        end = time.monotonic() + 30   # the app keeps it with the marks (api/tracked), for the page it opens next
        while not (app.Server.host_info(server)["tracker"] or {}).get("collected") and time.monotonic() < end:
            time.sleep(0.05)
        kept = app.Server.host_info(server)["tracker"] or {}
        assert [kept.get("collected"), clicked in kept["marks"][doc["sha256"]]["collected"]] == [True, True]
        _page.click(page, "track-collected")
        page.evaluate(SHOWN, got)
        played.takes.append(game.Took(got, 0.5))
        first = "() => shown.find((s) => s[0])"   # the change that shows the Got line
        assert _page.until(page, first) == [[f"Got: {spots[got]['name']} · {level}", "track-got"], ["Collected 2", 1],
                                            [f"{spots[got]['name']}: collected (live)"]]   # flashing, on the map
        _page.until(page, f"() => !({drawn})('{got}').length && document.getElementById('track-got').hidden", 30)
        page.emulate_media(reduced_motion="reduce")
        page.evaluate(SHOWN, still)
        played.takes.append(game.Took(still, 0.6))
        line, count, _ = _page.until(page, first)
        assert [line[1], count and count[1]] == ["none", 0], (line, count)   # a plain highlight, nothing animated
        _page.check_csp(page)
        page.close()
    finally:
        server.close()


def test_live_opens_each_session_on_the_marks_journal_and_reads_the_game_again_after_a_reset(tmp_path, monkeypatch):
    """Step 4.2c2's review (Modkit's tracker window): with Live on, the
    marks keep the saved slot the game last showed, and each session Live
    opens (the link back after it was lost, Live off and on) checks the
    game against the marks' journal (that slot, the newest live mark's day
    clock): an earlier save of that slot loaded meanwhile unmarks what Live
    marked after it (Modkit's Follower gives the Reload). Reset with Live on
    reads the game again, so what the game holds is marked again at the
    next poll. Once the link is lost, the player isn't placed ("here")."""
    from azurkit.tools.randomizer.live import game, link

    _home(monkeypatch, tmp_path / "home")
    monkeypatch.setattr(app.live, "RETRY_S", 0.05)
    doc = _profile("default")
    spots = sdk.tracker({"plan": doc})["spots"]
    near = sorted(loc for loc, s in spots.items() if s["state"] == "near")[0]
    table = game.spot_table(tracking.tracker_of(doc))
    field = {s.loc: s.field for s in table.spots}
    held = next(s.loc for s in table.spots if s.field and s.field != field[near])   # an item the game holds
    slot = "u:\\AAAAAAAAAAAA\\"
    gates, opened, resynced = {"lost": threading.Event(), "back": threading.Event()}, [], []

    def reading(clock: float, inv: dict) -> game.Reading:
        return game.Reading("running", game.REGIONS[0], level=spots[near]["level"], settle=1, clock=clock, slot=slot,
                            inv=inv, at=(1.0, 2.0, 3.0), yaw=0.0)

    class Session:   # the first: a take at day clock 0.3; the next: that slot's earlier save (0.1), read by Modkit's
        period = 0.02

        def __init__(self, xemu, spots, journal):
            opened.append(dict(journal))
            self.first, self.follower, self.took = len(opened) == 1, game.Follower(spots, journal), False

        def describe(self) -> str:
            return "xemu, scripted"

        def poll(self):
            if not self.first:
                r = reading(0.1, {field[held]: 1})
                return game.Update(r, tuple(self.follower.step(r)))
            if gates["lost"].is_set():
                raise link.LinkLost("xemu quit")
            took, self.took = () if self.took else (game.Took(near, 0.3),), True
            return game.Update(reading(0.3, {}), took)

        def resync(self) -> None:
            resynced.append(len(opened))
            self.follower.resync.set()

        def close(self) -> None:
            pass

    def open_first(endpoints):
        if gates["lost"].is_set() and not gates["back"].is_set():
            raise link.LiveError("no xemu answers")
        return "xemu"

    monkeypatch.setattr(game, "Session", Session)
    monkeypatch.setattr(link, "open_first", open_first)
    server, marks = app.serve(_page.WEB), {}

    def ask(**extra) -> dict:
        nonlocal marks
        replies = []
        _post(server.url, "api/tracker", {"given": {"plan": doc, "marks": marks, **extra}}, replies)
        marks = replies[0]["marks"]
        return replies[0]

    def until(test) -> dict:
        end = time.monotonic() + 60
        while not test(reply := ask()) and time.monotonic() < end:
            time.sleep(0.05)
        return reply

    try:
        _post(server.url, "api/live", {"on": True, "plan": doc, "marks": {}}, replies := [])
        assert replies == [{}]
        reply = until(lambda r: r["marks"].get("live"))
        assert (reply["marks"], reply["live"]["here"]) == ({"collected": [near], "live": {near: 0.3}, "slot": slot}, True)
        gates["lost"].set()
        reply = until(lambda r: r["live"]["status"] == "connecting")
        assert (reply["marks"]["collected"], reply["live"]["here"]) == ([near], False)
        gates["back"].set()
        reply = until(lambda r: near not in r["marks"]["collected"])
        assert opened == [{"slot": None, "newest": None}, {"slot": slot, "newest": 0.3}]
        assert near not in reply["marks"]["collected"] and held in reply["marks"]["collected"]
        assert ask(reset=True)["marks"] == {"collected": [], "slot": slot} and resynced == [2]
        assert held in until(lambda r: held in r["marks"]["collected"])["marks"]["collected"]
        _post(server.url, "api/live", {"on": False}, [])
        _post(server.url, "api/live", {"on": True, "plan": doc, "marks": marks}, [])
        end = time.monotonic() + 60
        while len(opened) < 3 and time.monotonic() < end:
            time.sleep(0.05)
        assert opened[2:] == [{"slot": slot, "newest": None}]
    finally:
        _post(server.url, "api/live", {"on": False}, [])
        server.close()



class _Ram:
    """A running game's guest RAM as Live's reads walk it (``live.game``; the USA release's addresses): the
    level, the player's entity (its clock and last contact point) and critter (its body centre) and, for
    ``names`` ({record: the species its critterGenerator names}), each spot's node in the level's main graph
    (its attributes at node + 0x80); ``gone``'s [start, end) ranges are unmapped."""

    SCENE, PD, CRITTER, ENTITY, INV, GRAPH, VEC, NODES = (0x100000 * k for k in range(1, 9))

    def __init__(self, level: str, names: dict[int, str] | None = None, records: int = 8):
        from azurkit.tools.randomizer.live import game, recipes

        self.mem: dict[int, int] = {}
        self.gone: list[tuple[int, int]] = []
        region, names = game.REGIONS[0], names or {}
        self.put(game.HEADER, "4s", b"XBEH")
        self.put(game.HEADER + 0x158, "I", region.thunk_va)
        self.put(region.va(recipes.SCENE_PTR), "I", self.SCENE)
        self.put(self.SCENE + game.SCENE_DEVICE, "II", 0, self.PD)
        self.put(self.PD + recipes.PD_LEVEL, "32s", f"levels/water/{level}".encode())
        for at, value in ((recipes.PD_PLAYER, self.CRITTER), (game.PD_GRAPH, self.GRAPH), (recipes.PD_INV, self.INV)):
            self.put(self.PD + at, "I", value)
        self.put(self.INV + game.INV_PD, "I", self.PD)
        self.put(self.CRITTER + game.CR_ENTITY, "I", self.ENTITY)
        self.put(self.CRITTER + recipes.CR_QUAT, "4f", 0, 0, 0, 1)
        self.put(self.CRITTER + recipes.CR_HP, "ii", 150, 175)
        self.put(self.GRAPH + game.GRAPH_VEC, "II", self.VEC, self.VEC + 4 * records)
        for record, species in names.items():
            node = self.NODES + 0x100 * record
            self.put(self.VEC + 4 * record, "I", node)
            self.put(node, "I", region.va(game.ADDRESSES["generator"]))
            self.put(node + game.NODE_ATTRS, "I", node + 0x80)
            self.put(node + game.NODE_OWNER, "I", region.va(game.ADDRESSES["owner"]))
            self.put(node + game.NODE_SPECIES, "I", node + 0x60)
            self.put(node + 0x60, "I", node + 0xA0)
            self.put(node + 0xA0, f"{game.NAME_MAX}s", species.encode())
        self.clock = 100.0

    def put(self, va: int, fmt: str, *values) -> None:
        for i, b in enumerate(struct.pack("<" + fmt, *values)):
            self.mem[va + i] = b

    def player(self, contact: tuple, body: tuple) -> None:
        """The player a poll later: the clock on, their last contact point and body centre where given."""
        from azurkit.tools.randomizer.live import game, recipes

        self.clock += 0.5
        self.put(self.ENTITY + game.ENT_CLOCK, "dI", self.clock, self.CRITTER)
        self.put(self.ENTITY + game.ENT_CLOCK + 0x20, "3f", *contact)
        self.put(self.CRITTER + recipes.CR_BODY, "3f", *body)

    def read(self, va: int, n: int) -> bytes:
        if any(lo < va + n and va < hi for lo, hi in self.gone):
            raise OSError(f"{va:#x}: unmapped")
        return bytes(self.mem.get(va + i, 0) for i in range(n))

    def read_many(self, wants: list) -> list:
        out = []
        for va, n in wants:
            try:
                out.append(self.read(va, n))
            except OSError:
                out.append(None)
        return out


def test_live_places_the_player_at_their_body_not_where_they_last_touched_the_ground():
    """Live places the player at the critter's body centre (+0x15C, 1 m
    over the feet), not at the entity's +0x38, the last contact point,
    which holds still in the air and while swimming: in a play session's
    w2 it stayed 14 m (13 px) from the player through a fall."""
    from azurkit.tools.randomizer.live import game

    ram = _Ram("w2")
    ram.player(contact=(-139.27, -119.59, 6.04), body=(-130.89, -108.38, -2.54))
    reading = game.Game(ram, game.SpotTable({}, ())).read()
    assert reading.level == "w2" and reading.at == pytest.approx((-130.89, -108.38, -3.54), abs=1e-4)


def test_live_stays_on_its_level_while_a_spots_counts_dont_read():
    """A poll whose read of one spot's counts finds no page (its
    attributes moved, or their page unmapped) is no unload: Live stays
    settled on the level, where it read "loading" at every poll while the
    player stood still in a play session's w2, keeps that spot's last
    count and reads its node's attributes pointer again, so its next take
    still counts; only the level's graph gone from pd is an unload."""
    from azurkit.tools.randomizer.live import game

    spots = tuple(game.Spot(f"w2/g0/r{k}", "w2", 0, k, "obsidian", "S", species="obsidian", vanilla="obsidian")
                  for k in (1, 2))
    ram, attrs = _Ram("w2", {1: "obsidian", 2: "obsidian"}), 0x900000   # each spot's attributes at attrs + 0x40 k
    for k in (1, 2):
        ram.put(_Ram.NODES + 0x100 * k + game.NODE_ATTRS, "I", attrs + 0x40 * k)
        ram.put(attrs + 0x40 * k + game.ATTR_COUNTS, "3f", 1, 1, 0)
    live = game.Game(ram, game.SpotTable({"w2": game.LevelSpots("w2", 0, 8, spots)}, spots))

    def poll():
        ram.player(contact=(0.0, 0.0, 0.0), body=(0.0, 0.0, 1.0))   # standing still
        r = live.read()
        return r.state, r.settle, dict(r.dead)

    assert [poll() for _ in range(2)][1] == ("running", 1, {"w2/g0/r1": 0, "w2/g0/r2": 0})
    ram.gone.append((attrs + 0x40, attrs + 0x80))   # record 1's attributes moved on: their old page reads nothing
    ram.put(_Ram.NODES + 0x100 + game.NODE_ATTRS, "I", attrs + 0x200)
    ram.put(attrs + 0x200 + game.ATTR_COUNTS, "3f", 1, 0, 1)
    assert [poll(), poll()] == [("running", 1, {"w2/g0/r1": 0, "w2/g0/r2": 0}),
                                ("running", 1, {"w2/g0/r1": 1, "w2/g0/r2": 0})]
    ram.put(_Ram.PD + game.PD_GRAPH, "I", 0)
    assert poll()[:2] == ("loading", 0)


def test_live_places_the_player_while_xemu_runs_another_seed_or_build():
    """Step 4.2c2's late review (Modkit's follow_game places the player at
    every reading, another seed's or build's too): while xemu runs another
    seed or build, the page still shows where the player stands ("here"),
    so the world map's ring, "you are here" and Follow stay."""
    from azurkit.tools.randomizer.live import game

    feed = app.live.Feed(_profile("default"), None)
    feed._update(game.Update(game.Reading("running", game.REGIONS[0], level="w1", settle=1, mismatch=True,
                                          at=(1.0, 2.0, 3.0), yaw=0.0)))
    live = feed.take()[1]
    assert (live["status"], live["here"], live["seen"]["level"]) == ("other", True, "w1")


def test_lives_line_on_another_seed_or_build_counts_the_spots_that_differ_and_names_what_to_check():
    """While xemu runs another seed or build, Live's line names the level
    and how many of the item spots it read hold other items than the
    tracked plan's (seed and share string), and what to check against the
    build (the seed, the share string's settings, the packs, the body worn)
    or how to track the build itself; where each spot holds the base
    game's item, it says the image isn't randomized."""
    from azurkit.tools.randomizer.live import game

    spots = tuple(game.Spot(f"w2/g0/r{k}", "w2", 0, k, item, "S", species=item, vanilla=vanilla)
                  for k, item, vanilla in ((1, "power_water", "power_water"), (2, "obsidian", "diamond"),
                                           (3, "all_fuel", "emerald")))
    table, plan = game.SpotTable({"w2": game.LevelSpots("w2", 0, 8, spots)}, spots), _profile("default")

    def line(names: dict[int, str]) -> tuple:
        ram = _Ram("w2", names)
        live = game.Game(ram, table)
        for _ in range(2):   # a level settles on its second running poll
            ram.player(contact=(0.0, 0.0, 0.0), body=(0.0, 0.0, 1.0))
            reading = live.read()
        feed = app.live.Feed(plan, None)
        feed._update(game.Update(reading))
        return reading.odd, feed.take()[1]["status"], feed.text

    odd, status, text = line({1: "power_water", 2: "diamond", 3: "all_fuel"})
    assert (odd, status) == ((1, 3, False), "other")
    assert text == (f"xemu runs another seed or build: 1 of the 3 item spots Live read in w2 hold other items than "
                    f"seed {plan['seed']}'s plan (share string {plan['share']}): check the seed, the share string's "
                    "settings, the packs' movement and the body worn on the Characters tab (its size folds into the "
                    "walk and roll) against the build's, or track the build itself (Tools: Open a build…, Track this "
                    "build).")
    odd, status, text = line({1: "power_water", 2: "diamond", 3: "emerald"})
    assert (odd, status) == ((2, 3, True), "other") and text == (
        "xemu runs another seed or build: the 3 item spots Live read in w2 hold the base game's items, so the image "
        "isn't randomized: boot the randomized build you track.")


def test_lives_line_with_no_xemu_names_only_what_the_page_offers(monkeypatch):
    """Step 4.1k (the retire inventory's F1): with no xemu answering, Live's
    line on any OS (macOS's too) names the QMP argument to start xemu with
    and the page's Endpoints box, never the Tk window's right-click admin
    attach or its click-to-copy launch line; the link's other texts name
    the box and the argument the same way."""
    from azurkit.tools.randomizer.live import link

    texts = [*(link.no_xemu(p) for p in ("darwin", "linux", "win32")), link.not_xemu("127.0.0.1:4444"),
             link.monitor_not_qmp("127.0.0.1:4444")]
    shown = [app.live.page_text(text) for text in texts]
    assert shown[:3] == [app.live.NO_XEMU] * 3 and link.QMP_ARG in app.live.NO_XEMU and link.QMP_ARG in shown[4]
    assert [t for t in shown if "Endpoints…" in t or any(w in t.lower() for w in ("right-click", "copy", "hover",
                                                                                  "admin"))] == []
    assert 'id="track-endpoints"' in (_page.WEB / "index.html").read_text(encoding="utf-8")

    def nothing(endpoints):
        raise link.LiveError(link.no_xemu("darwin"))

    monkeypatch.setattr(app.live, "RETRY_S", 0.05)
    monkeypatch.setattr(link, "open_first", nothing)
    feed = app.live.Feed(_profile("default"), None).start()
    try:
        end = time.monotonic() + 30
        while (live := feed.take()[1])["text"] != app.live.NO_XEMU and time.monotonic() < end:
            time.sleep(0.02)
        assert (live["status"], live["text"]) == ("connecting", app.live.NO_XEMU)
    finally:
        feed.stop()

# ---------------------------------------------------------------- Play and the macOS admin attach (Modkit's, the app's)

XEMU_COMMIT = b"0123456789abcdef0123456789abcdef01234567"
# a library's version first (2.0.0 in the fork's binary), then xemu's own just before its commit
FORK_BODY = (b"\x002.0.0\x00a library\x00its text\x00\x000.15.1-51-g68b69fc3ca\x00" + XEMU_COMMIT + b"\x00" + bytes(16)
             + b"XEMU_RAM_SHM=name\x00")
UPSTREAM_BODY = b"\x001.3.2\x00 release universal\x000.8.136\x00master\x00" + XEMU_COMMIT + b"\x00"


def _fake_xemu(root: Path, where: str, body: bytes) -> Path:
    """A macOS-style ``xemu.app`` whose binary holds ``body`` (version strings, and the fork's marker or not)."""
    bundle = root / where / "xemu.app"
    (bundle / "Contents" / "MacOS").mkdir(parents=True)
    (bundle / "Contents" / "MacOS" / "xemu").write_bytes(body)
    return bundle


def _listener() -> socket.socket:
    """A loopback TCP listener (any OS) for the helper's loop: the protocol is the one its unix socket serves."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    return srv


def test_play_finds_xemu_tells_the_fork_from_upstream_and_launches_it_private_with_the_build(tmp_path):
    """Modkit's Play (D256, the owner: "Yes, add Play"): it finds the player's
    xemu (a running one's bundle, this OS's standard places, Spotlight; only
    the player's own processes, never another account's, an automated one,
    D248, or an agent sandbox, so Play's attach offer, D274, is never theirs;
    on Windows its running xemu.exe, so Play starts no second one; the one
    picked last only while it exists), ordered and deduplicated, reading
    xemu's own version (not a library's) and whether it is the fork from its
    binary (the XEMU_RAM_SHM marker), never a game byte. It launches the
    chosen one with the build in the tray and a private QMP socket (a unix
    socket on macOS and Linux, a loopback port on Windows and for Flatpak,
    whose /tmp is its own) plus the fork's shared RAM under a private name,
    changing no xemu setting, and hands Live those explicit endpoints: shared
    RAM first (no pause) for the fork, QMP alone for upstream. Live tracks the
    disc a running xemu holds open (D261), and a second Play knows its own
    xemu still runs by its private QMP socket."""
    from azurkit.tools.randomizer.live.link import Endpoint

    xemu = app.xemu
    fork = _fake_xemu(tmp_path, "a", FORK_BODY)
    upstream = _fake_xemu(tmp_path, "b", UPSTREAM_BODY)
    probes = xemu.Probes(
        running=lambda _p: [(fork / "Contents" / "MacOS" / "xemu", 77)], dirs=lambda _p, _h: [tmp_path / "a"],
        spotlight=lambda _p: [upstream, fork],          # repeats of the fork are deduplicated
        which=lambda _n: None, flatpak=lambda: False, remembered=tmp_path / "gone.app")
    found = xemu.discover("darwin", probes)
    assert [x.label for x in found] == ["xemu 0.15.1-51-g68b69fc3ca (fork, running)", "xemu 0.8.136"]
    v016 = _fake_xemu(tmp_path, "v", FORK_BODY.replace(b"0.15.1-51-g68b69fc3ca", b"0.16"))
    assert xemu.describe(v016).label == "xemu 0.16 (fork)"    # an x.y release
    assert [(x.path, x.pid) for x in found] == [(fork, 77), (upstream, None)]   # the running one's bundle
    sandbox = "/private/tmp/azx-grp.a1b2/xemu.app/Contents/MacOS/xemu"     # an agent's xemu sandbox
    ps = {"comm": f"  77 501 /A/xemu.app/Contents/MacOS/xemu\n  78 501 /B/xemu.app/Contents/MacOS/xemu\n"
                  f"  79 501 /bin/zsh\n  80 501 {sandbox}\n  81 502 /C/xemu.app/Contents/MacOS/xemu\n",
          "args": "  77 501 /A/xemu.app/Contents/MacOS/xemu\n"
                  "  78 501 /B/xemu.app/Contents/MacOS/xemu -name xemu-fork-auto\n"
                  f"  80 501 {sandbox} -config_path /private/tmp/azx-grp.a1b2/xemu.toml\n"
                  "  81 502 /C/xemu.app/Contents/MacOS/xemu\n"}            # 81: another account's
    fake_ps = lambda argv, **_k: types.SimpleNamespace(stdout=ps[argv[-1].split(",")[-1].rstrip("=")])   # noqa: E731
    assert xemu.running_xemus("darwin", run=fake_ps, uid=501) == [(Path("/A/xemu.app/Contents/MacOS/xemu"), 77)]
    tasks = types.SimpleNamespace(stdout='"xemu.exe","4242","Console","1","180,000 K"\n')
    assert xemu.running_xemus("win32", run=lambda *_a, **_k: tasks) == [(Path("xemu.exe"), 4242)]
    assert xemu.describe(Path("xemu.exe")).version == ""             # no path: nothing read

    iso = tmp_path / "seed.iso"
    run = tmp_path / "run"
    run.mkdir()
    mac = xemu.plan_launch(found[0], iso, run, platform="darwin", shm_name="azurik-play-aa")
    sock = str(run / "qmp.sock")
    assert mac.argv == ["open", "-n", "-a", str(fork), "--env", "XEMU_RAM_SHM=azurik-play-aa",
                        "--args", "-dvd_path", str(iso), "-qmp", f"unix:{sock},server=on,wait=off"]
    assert mac.env == {} and [str(e) for e in mac.endpoints] == ["shm:azurik-play-aa", f"qmp:unix:{sock}"]
    up = xemu.plan_launch(found[1], iso, run, platform="darwin")
    assert "--env" not in up.argv and [e.kind for e in up.endpoints] == ["qmp"]
    win = xemu.plan_launch(found[0], iso, run, platform="win32", port=5123, shm_name="azurik-play-bb")
    assert win.argv == [str(found[0].exe), "-dvd_path", str(iso), "-qmp", "tcp:127.0.0.1:5123,server=on,wait=off"]
    assert win.env == {"XEMU_RAM_SHM": "azurik-play-bb"}
    assert [e.kind for e in win.endpoints] == ["shm", "qmp"] and win.endpoints[1].target == ("127.0.0.1", 5123)
    lin = xemu.plan_launch(found[0], iso, run, platform="linux", shm_name="azurik-play-cc")
    assert lin.argv[0] == str(found[0].exe) and lin.env == {"XEMU_RAM_SHM": "azurik-play-cc"}
    flat = xemu.plan_launch(xemu.describe(Path(xemu.BUNDLE_ID), flatpak=True), iso, run, platform="linux", port=5124)
    assert flat.argv[:3] == ["flatpak", "run", xemu.BUNDLE_ID] and flat.endpoints[0].target[1] == 5124

    iso.write_bytes(b"a built ISO")
    lsof = types.SimpleNamespace(stdout=f"p77\nfcwd\nn/\nf9\nn{tmp_path / 'xemu.toml'}\nf12\nn{iso}\n")
    assert xemu.disc_in_tray(77, "darwin", run=lambda *_a, **_k: lsof) == iso
    assert TRAY_DISC("darwin", running=probes.running, tray=lambda _pid, _p: None) is None
    assert TRAY_DISC("darwin", running=probes.running, tray=lambda _pid, _p: iso) == iso
    qmp = _listener()
    played = [Endpoint("shm", "azurik-play-aa", True), Endpoint("qmp", qmp.getsockname(), True)]
    assert xemu.answers(played) and not xemu.answers(None)    # Play's xemu runs
    qmp.close()
    assert not xemu.answers(played)                           # it quit


class _GuestRam:
    """A guest RAM image of the test's own, as the helper reads it (physical): a page directory at CR3 that maps
    itself, 4 KiB pages given frames as they are written, and one 4 MiB page."""

    def __init__(self, size: int = 64 << 20):
        from azurkit.tools.randomizer.live import pages

        self.pages, self.ram, self.next = pages, bytearray(size), 0x100000   # the next free frame
        self.u32_at(pages.CR3 + 4 * (pages.PDE_BASE >> 22), pages.CR3 | 1)

    def u32_at(self, pa: int, v: int) -> None:
        struct.pack_into("<I", self.ram, pa, v)

    def map(self, va: int) -> int:
        """The frame of ``va``'s page, given one if it has none."""
        pde_at = self.pages.CR3 + 4 * (va >> 22)
        if not (pde := struct.unpack_from("<I", self.ram, pde_at)[0]) & 1:
            pde, self.next = self.next | 1, self.next + self.pages.PAGE
            self.u32_at(pde_at, pde)
        pte_at = (pde & 0xFFFFF000) + 4 * ((va >> 12) & 0x3FF)
        if not (pte := struct.unpack_from("<I", self.ram, pte_at)[0]) & 1:
            pte, self.next = self.next | 1, self.next + self.pages.PAGE
            self.u32_at(pte_at, pte)
        return pte & 0xFFFFF000

    def write(self, va: int, data: bytes) -> None:
        for at in range(va, va + len(data)):
            self.ram[self.map(at) + (at & 0xFFF)] = data[at - va]

    def read(self, va: int, n: int) -> bytes:
        return self.pages.ram_reader(self.ram, self.pages.CR3)(va, n)


def test_the_mac_admin_helper_serves_read_only_physical_reads_to_the_app_alone_and_lets_it_reconnect(monkeypatch):
    """Modkit's admin attach (D257, the owner: "ask for authentication on
    mac"): the macOS helper reads xemu's memory read-only and streams only
    the physical byte ranges Live asks for; the app walks the guest's page
    tables over them (``link.MacHelperLink``), so the same guest VAs come back
    as shared RAM and QMP give, an unmapped page is None, and no write ever
    goes to the helper. It serves one connection after another (Live off and
    on again, a lost link: no new prompt) and only the app's own process (its
    pid), and stops once it is told to go; it reads only a process of the
    app's user (its uids, read before anything else: never another
    account's); the page-directory check that validates a region is the one
    the real helper runs as root, in Python 3.9, from a file the app copies
    and never imports."""
    import ast

    from azurkit.app import live_helper
    from azurkit.tools.randomizer.live import link

    ram = _GuestRam()
    ram.write(0x10FF0, bytes(range(0x80)))                                 # two neighbours on far-apart frames
    ram.u32_at(ram.pages.CR3 + 4 * (0x00800000 >> 22), 0x02000000 | 0x81)  # a 4 MiB page
    ram.ram[0x02000000:0x02000100] = bytes(range(256))
    reader = lambda pa, n: bytes(ram.ram[pa:pa + n])                       # noqa: E731 (a physical read)
    assert live_helper.validate(reader, len(ram.ram)) == ram.pages.CR3
    assert live_helper.validate(reader, 1234) is None                      # not an Xbox RAM size
    assert not live_helper.maps_itself(reader, 0x10000)                    # not a page directory
    tree = ast.parse(app.xemu.HELPER_SRC.read_text(encoding="utf-8"), feature_version=(3, 9))   # the CLT's Python
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names} | {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imported <= set(app.xemu._PY_PROBE.partition("\n")[0].removeprefix("import ").split(", "))   # root vets them
    a, b = socket.socketpair()
    with a, b:                                                             # no peer pid without unix sockets
        assert live_helper.peer_pid(a) == (None if sys.platform == "win32" else os.getpid())
    assert live_helper.owner(os.getpid()) == ((os.getuid(),) * 2 if sys.platform == "darwin" else None)

    reads, stop = [], threading.Event()
    srv, bad = _listener(), _listener()
    logged = lambda pa, n: (reads.append((pa, n)), reader(pa, n))[1]       # noqa: E731
    monkeypatch.setattr(live_helper, "TICK_S", 0.05)                       # how soon a waiting helper sees "go"
    helpers = [threading.Thread(target=live_helper.listen, daemon=True,
                                args=(s, logged, len(ram.ram), lambda _c, ok=ok: ok, lambda: not stop.is_set()))
               for s, ok in ((srv, True), (bad, False))]
    for t in helpers:
        t.start()
    ep = link.Endpoint("helper", srv.getsockname(), True)
    wants = [(0x10FF0, 0x20), (0x00800010, 0x80), (0x11030, 0x10)]
    try:
        for _again in range(2):                                            # a second link, the same helper
            linked = link.open_first([ep])
            assert linked.label() == "xemu, admin helper"
            assert [linked.read(va, n) for va, n in wants] == [ram.read(va, n) for va, n in wants]
            assert linked.read_many([*wants, (0x30000, 4)]) == [ram.read(va, n) for va, n in wants] + [None]
            linked.close()
        assert reads and all(n <= live_helper.READ_MAX for _pa, n in reads)   # never more than a page
        with pytest.raises(link.LiveError, match="can't read xemu: peer is not the app"):
            link.open_first([link.Endpoint("helper", bad.getsockname(), True)])   # another process: refused
    finally:
        stop.set()
        for t in helpers:
            t.join(5)
        srv.close()
        bad.close()
    assert not any(t.is_alive() for t in helpers)                          # told to go, each helper returned


def test_the_mac_helper_runs_a_root_owned_copy_on_macos_own_root_owned_python_never_the_apps(tmp_path):
    """Modkit's admin attach (D257): the admin command copies the helper into
    a root-owned temp dir, locks the copy down and runs that copy detached,
    with an interpreter root alone may change (its binary and every module it
    loads, with each folder above them: never the app's own, whose
    interpreter and standard library the user owns) in isolated mode, without
    site, in an empty environment; it reads one pid and serves only the app's
    process. A build with the hardened runtime is refused. D310: Xcode's
    Python is taken too, under /Applications, which the admin group may write
    (root:admin 0775); no other folder above it may be."""
    from azurkit.tools.randomizer.live.errors import LiveError

    xemu = app.xemu
    src = tmp_path / "live_helper.py"
    src.write_text("print('hi')\n", encoding="utf-8")
    py = "/Library/Developer/CommandLineTools/usr/bin/python3"
    cmd = xemu.mac_helper_command(4321, tmp_path / "s.sock", 501, 999, py, src=src)
    assert "mktemp -d" in cmd and 'chmod 700 "$d"' in cmd and 'chmod 500 "$d/helper.py"' in cmd
    assert f"/bin/cp {shlex.quote(str(src))} " in cmd and f'/usr/bin/env -i {py} -I -S "$d/helper.py"' in cmd   # the copy is run
    assert "--pid 4321" in cmd and "--uid 501" in cmd and "--peer 999" in cmd
    assert "nohup" in cmd and cmd.rstrip().endswith("& echo $!")

    files = [py, "/Library/Developer/CommandLineTools/lib/os.py"]
    probe = lambda argv, **_k: types.SimpleNamespace(stdout="" if "xcode-select" in argv[0] else json.dumps(files))  # noqa: E731
    root = lambda _p: types.SimpleNamespace(st_uid=0, st_mode=0o40755)    # noqa: E731
    assert xemu.root_python(run=probe, stat=root) == py
    for odd in (types.SimpleNamespace(st_uid=501, st_mode=0o40755), types.SimpleNamespace(st_uid=0, st_mode=0o40775)):
        stat = lambda p, odd=odd: odd if p == "/Library/Developer" else root(p)   # noqa: E731
        with pytest.raises(LiveError, match="Command Line Tools"):
            xemu.root_python(run=probe, stat=stat)                     # the user's, or a group may write it
    assert not xemu._roots_alone(os.path.realpath(sys.executable), os.stat)   # the app's own: never

    xcode = "/Applications/Xcode.app/Contents/Developer/usr/bin/python3"
    only_xcode = lambda argv, **_k: types.SimpleNamespace(   # noqa: E731  (no Command Line Tools)
        stdout=json.dumps([xcode, "/Applications/Xcode.app/Contents/Developer/Library/os.py"]) if xcode in argv
        else "")
    taken = []
    for gid, mode in ((80, 0o40775), (20, 0o40775), (80, 0o40777)):     # admin's; staff's; anyone's
        stat = lambda p, gid=gid, mode=mode: (types.SimpleNamespace(st_uid=0, st_gid=gid, st_mode=mode)  # noqa: E731
                                              if p == "/Applications" else root(p))
        try:
            taken.append(xemu.root_python(run=only_xcode, stat=stat))
        except LiveError:
            taken.append(None)
    assert taken == [xcode, None, None]

    runtime = lambda *_a, **_k: types.SimpleNamespace(stderr="CodeDirectory v=20400 flags=0x10000(runtime) hashes=1")
    adhoc = lambda *_a, **_k: types.SimpleNamespace(stderr="CodeDirectory v=20400 flags=0x2(adhoc) hashes=1")
    assert xemu.hardened_runtime(src, run=runtime) is True      # the signed upstream build: refused
    assert xemu.hardened_runtime(src, run=adhoc) is False       # the fork's ad-hoc build: readable


def test_play_launches_the_found_xemu_private_with_the_saved_build_and_live_reads_it_first_or_offers_to_attach(
        tmp_path, monkeypatch):
    """Modkit's Play (D256; the app's alone, D882): ``api/play`` finds the
    player's xemu and launches the only one with the saved build in its tray
    and a private QMP socket (the fork's shared RAM too), remembers the pick,
    and Live reads those private endpoints before the Endpoints box's; Play's
    own xemu still running, a second Play launches nothing. Several found:
    the page picks one (the one picked last first); none: it names where.
    D274 (the owner: "Offer to attach"): with the player's xemu already
    running Play starts no second one and offers to attach where the app can
    (macOS), else says to quit it; ``api/attach`` reads it through the admin
    helper (D257: one password prompt; a hardened build refused by name), and
    a later Play gets Live on it with no second prompt. The helper's and
    Play's private folders go when the app quits. The discovery, the launch
    and the helper are faked: no xemu runs and nothing prompts."""
    from dataclasses import replace

    from azurkit.app import play
    from azurkit.tools.randomizer.live import link

    _home(monkeypatch, tmp_path / "home")
    xemu, iso = app.xemu, tmp_path / "seed.iso"
    iso.write_bytes(b"a saved build")
    bundle = tmp_path / "xemu.app"
    (bundle / "Contents" / "MacOS").mkdir(parents=True)
    fake = xemu.Xemu(bundle, bundle / "Contents" / "MacOS" / "xemu", "0.15.1", fork=True)
    other = xemu.Xemu(tmp_path / "up.app", tmp_path / "up.app" / "Contents" / "MacOS" / "xemu", "0.8.136")
    (tmp_path / "up.app").mkdir()
    found, launched, helpers, here, ours, tried = [replace(fake, running=True, pid=77), other], [], [], [False], [False], []
    monkeypatch.setattr(xemu, "discover", lambda probes=None: list(found))
    monkeypatch.setattr(xemu, "answers", lambda eps: ours[0] and bool(eps))
    monkeypatch.setattr(xemu, "spawn", launched.append)
    monkeypatch.setattr(xemu, "can_attach", lambda: here[0])
    monkeypatch.setattr(xemu, "attachable", lambda: [x for x in found if x.running])

    def helper(pid, run_dir):                     # the admin prompt and the root helper, faked
        helpers.append(pid)
        (run_dir / "helper.sock").touch()
        return link.Endpoint("helper", str(run_dir / "helper.sock"), True)

    def nothing(endpoints):
        tried.append([str(e) for e in endpoints])
        raise link.LiveError("no xemu answers")

    monkeypatch.setattr(xemu, "start_helper", helper)
    monkeypatch.setattr(link, "open_first", nothing)
    server = app.serve(_page.WEB)

    def call(name: str, body: dict) -> dict:
        replies = []
        _post(server.url, f"api/{name}", body, replies)
        return replies[0]

    def live_tries() -> list[str]:   # the endpoints Live's feed tries first, as it starts
        tried.clear()
        call("live", {"on": True, "plan": _profile("default"), "marks": {}})
        end = time.monotonic() + 30
        while not tried and time.monotonic() < end:
            time.sleep(0.02)
        call("live", {"on": False})
        return tried[0]

    try:
        assert call("play", {"iso": str(tmp_path / "gone.iso")}) == {
            "refused": f"{tmp_path / 'gone.iso'}: no saved build there: save the build first, then press Play"}
        running = {"running": ["xemu 0.15.1 (fork, running)"], "attach": False, "text": play.NO_ATTACH}
        assert call("play", {"iso": str(iso)}) == running                  # no attach here: quit it first
        assert call("attach", {}) == {"refused": play.NO_ATTACH}
        here[0] = True
        assert call("play", {"iso": str(iso)}) == running | {"attach": True, "text": play.ATTACH}
        found[0] = replace(found[0], hardened=True)
        assert call("attach", {}) == {"refused": play.HARDENED}
        found[0] = replace(found[0], hardened=False)
        assert call("attach", {}) == {"attached": "xemu 0.15.1 (fork, running)"} and helpers == [77]
        helped = server.player.helper[2]
        assert call("play", {"iso": str(iso)}) == {"tracking": "helper"} and helpers == [77]   # no second prompt
        assert live_tries()[0] == f"helper:{helped / 'helper.sock'}"
        assert not launched                                                # never a second xemu

        found[:] = [other, fake]                                           # none running: several found
        assert call("play", {"iso": str(iso)}) == {"choose": [{"label": "xemu 0.8.136", "path": str(other.path)},
                                                              {"label": "xemu 0.15.1 (fork)", "path": str(bundle)}],
                                                   "picked": 0}
        assert call("play", {"iso": str(iso), "xemu": str(bundle)}) == {"launched": "xemu 0.15.1 (fork)"}
        launch = launched[0]
        shm = launch.endpoints[0].target
        assert "-dvd_path" in launch.argv and str(iso) in launch.argv
        assert f"XEMU_RAM_SHM={shm}" in launch.argv or launch.env == {"XEMU_RAM_SHM": shm}   # macOS: open --env
        assert [e.kind for e in launch.endpoints] == ["shm", "qmp"] and shm.startswith(xemu.SHM_PREFIX)
        assert app._kept()["xemu"] == str(bundle) and launch.scratch.is_dir() and not helped.exists()
        assert live_tries()[:2] == [str(e) for e in launch.endpoints]      # Play's first, then the box's
        assert call("play", {"iso": str(iso)})["picked"] == 1             # the one picked last, first
        ours[0] = True
        assert call("play", {"iso": str(iso)}) == {"tracking": "played"} and len(launched) == 1
        ours[0], found[:] = False, []
        assert call("play", {"iso": str(iso)}) == {"none": play.NONE_FOUND}
        assert call("play", {"iso": str(iso), "xemu": str(tmp_path / "nowhere")}) == {
            "refused": f"{tmp_path / 'nowhere'}: no xemu there"}
    finally:
        server.close()
    assert launched and not launched[0].scratch.exists()                  # Play's folder goes with the app


def test_each_build_in_the_app_keeps_its_log_with_its_recipe_and_report_or_why_it_failed_and_its_save(
        tmp_path, monkeypatch):
    """Modkit's build logs (its Build page's, kept on disk): each Build the
    app runs writes a log in this user's log folder,
    ``build-<time>[-seed<seed>].log``: its header (the image, the packs, the
    seed and share string, the whole recipe), then the build's report (its
    plan left out) or why it failed, and each save of it. ``api/logs`` names
    the folder and the last log and opens either in this computer's own
    viewer (faked: nothing opens); Storage lists the logs and clears them.
    The engine's build and save are canned: no image is read or written."""
    _home(monkeypatch, tmp_path / "home")
    opened = []
    monkeypatch.setattr(app.logs, "reveal", opened.append)
    report = {"label": "USA", "layers": [{"id": "pack fps_unlock", "sites": 1, "bytes": 4}], "conflicts": [],
              "notes": [], "randomizer": {"seed": "7", "share": "S"}, "result": {"default.xbe": "ab" * 32},
              "plan": {"sha256": "p" * 64, "placements": {"spot": "item"}}}

    class Canned(engine.Here):
        def call(self, job, *args, progress=None, fore=None):
            if job == "image":
                if "broken" in args[0]["packs"]:
                    raise ValueError("packs: no pack 'broken'")
                return {"report": report, "size": 5, "build": "b1", "peak": 0}
            if job == "save":
                return {"out": args[1], "size": 5, "sha256": "cd" * 32}
            return super().call(job, *args, progress=progress, fore=fore)

    server = app.serve(_page.WEB, Canned())

    def call(name: str, body: dict) -> dict:
        replies = []
        _post(server.url, f"api/{name}", body, replies)
        return replies[0]

    image = str(tmp_path / "usa.iso")
    try:
        assert call("logs", {}) == {"folder": str(app.logs.folder()), "last": None}
        assert call("logs", {"open": "last"}) == {"refused": "No build log yet: build first"}
        built = call("build", {"iso": image, "packs": {"fps_unlock": {}}, "randomizer": {"seed": "7", "share": "S"}})
        assert call("save", {"recipe": built["recipe"], "out": str(tmp_path / "out.iso"), "build": "b1"})["saved"][
            "out"] == str(tmp_path / "out.iso")
        assert call("build", {"iso": image, "packs": {"broken": {}}}) == {"refused": "packs: no pack 'broken'"}
        first, failed = sorted(app.logs.folder().glob("build-*.log"), key=lambda p: "seed" not in p.name)
        assert first.name.endswith("-seed7.log") and "seed" not in failed.name
        text = first.read_text(encoding="utf-8")
        assert text.startswith(f"# AzurKit build log\n# started   : ") and f"# image     : {image}\n" in text
        assert "# packs     : fps_unlock\n# randomizer: seed 7, share S\n" in text
        assert '# recipe    : {"packs": {"fps_unlock": {}}, "randomizer": {"seed": "7", "share": "S"}}' in text
        logged = json.loads(text.partition("report: ")[2].partition("\n# ---")[0])
        assert logged == {k: v for k, v in report.items() if k != "plan"}   # the seed's plan left out
        assert f"saved {tmp_path / 'out.iso'} · 5 bytes · sha256 {'cd' * 32}\n" in text
        assert "failed: packs: no pack 'broken'\n" in failed.read_text(encoding="utf-8")
        assert call("logs", {"open": "folder"}) == {"folder": str(app.logs.folder()), "last": str(failed)}
        assert call("logs", {"open": "last"})["last"] == str(failed) and opened == [app.logs.folder(), failed]
        assert call("logs", {"open": "elsewhere"}) == {"refused": "logs: open is folder or last"}
        assert "logs" in {e["name"] for e in call("storage", {})["entries"]}
        assert "logs" in call("storage", {"clear": True})["cleared"] and not [*app.logs.folder().glob("*.log")]
    finally:
        server.close()


def test_play_on_the_apps_page_tracks_the_saved_builds_seed_with_live_on_and_live_tracks_the_seed_in_xemus_tray(
        browser, tmp_path, monkeypatch):
    """The app's Play and Attach… (Modkit's Play button and its Tracker's
    tray seed, D256, D261, D274; the app's alone, D882): Play, greyed until a
    build is saved, launches xemu with the saved build and tracks that build's
    seed on the Randomizer tab with Live on, Play's private endpoints tried
    first; with xemu already running it asks in a small dialog whether to
    attach, and Attach reads that xemu through the admin helper, Live on.
    Live ticked by hand first tracks the seed of the AzurKit build in a
    running xemu's tray when it isn't the one shown. The Tools tab names the
    folder each build's log is kept in. The discovery, the launch, the
    helper, the tray and the game are faked: no xemu runs, nothing prompts."""
    from dataclasses import replace

    from azurkit.app import play
    from azurkit.tools.randomizer.live import link

    _home(monkeypatch, tmp_path / "home")
    monkeypatch.setattr(app.pictures, "folder", lambda: tmp_path / "no-maps")   # no pictures: the chips show
    files = {"gamedata/config.xbr": fill("a", 64)}   # USA's name, ours bytes
    vanilla = tmp_path / "vanilla.iso"
    vanilla.write_bytes(image(files))
    monkeypatch.setenv(gate.USA.env, str(vanilla))
    at = vanilla.stat()
    stamp = gate.Stamp(gate.USA, vanilla, at.st_size, at.st_mtime_ns, False, at.st_ctime_ns)
    change = Change("gamedata/config.xbr", 0, hashlib.sha256(files["gamedata/config.xbr"][:4]).hexdigest(), b"AAAA",
                    "a 1")
    played, trayed = _profile("default"), _profile("strict")
    for name, doc in (("saved", played), ("tray", trayed)):
        edits.build(stamp, [Layer("randomizer", "randomizer", "plan", {"seed": doc["seed"], "share": doc["share"]},
                                  [change])], tmp_path / f"{name}.iso")
    bundle = tmp_path / "xemu.app"
    fake = app.xemu.Xemu(bundle, bundle / "Contents" / "MacOS" / "xemu", "0.15.1", fork=True)
    found, launched, helpers, tray, tried = [fake], [], [], [None], []
    monkeypatch.setattr(app.xemu, "discover", lambda probes=None: list(found))
    monkeypatch.setattr(app.xemu, "answers", lambda eps: False)
    monkeypatch.setattr(app.xemu, "spawn", launched.append)
    monkeypatch.setattr(app.xemu, "can_attach", lambda: True)
    monkeypatch.setattr(app.xemu, "attachable", lambda: [x for x in found if x.running])
    monkeypatch.setattr(app.xemu, "tray_disc", lambda: tray[0])

    def helper(pid, run_dir):
        helpers.append(pid)
        (run_dir / "helper.sock").touch()
        return link.Endpoint("helper", str(run_dir / "helper.sock"), True)

    def nothing(endpoints):
        tried.append([str(e) for e in endpoints])
        raise link.LiveError("no xemu answers")

    monkeypatch.setattr(app.xemu, "start_helper", helper)
    monkeypatch.setattr(link, "open_first", nothing)
    server = app.serve(_page.WEB)
    live = "(sha) => azurkit.tracker.state.plan?.sha256 === sha && document.getElementById('track-live').checked"
    try:
        page = browser.new_page()
        page.goto(server.url)
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        button = "() => [document.getElementById('play').hidden, document.getElementById('play').disabled, " \
                 "document.getElementById('play').title, document.getElementById('track-attach').hidden]"
        assert page.evaluate(button) == [False, True, "Save a build first, then play it in xemu", False]
        page.evaluate("(given) => { azurkit.played = given; document.getElementById('play').disabled = false; }",
                      {"out": str(tmp_path / "saved.iso"), "plan": played})   # what a Save of that build sets
        _page.click(page, "play")
        _page.until(page, f"() => ({live})({json.dumps(played['sha256'])}) && azurkit.tab === 'randomizer'", 300)
        assert page.evaluate("() => document.getElementById('status').textContent") == (
            f"Started xemu 0.15.1 (fork) with saved.iso: tracking seed {played['seed']}, Live on")
        assert len(launched) == 1 and str(tmp_path / "saved.iso") in launched[0].argv
        end = time.monotonic() + 30
        while not tried and time.monotonic() < end:
            time.sleep(0.02)
        assert tried[0][:2] == [str(e) for e in launched[0].endpoints]   # Play's xemu first

        found[0] = replace(fake, running=True, pid=77)                    # the player's own xemu runs
        _page.click(page, "play")
        assert _page.until(page, "() => document.getElementById('xemu-ask').open && "
                                 "document.getElementById('xemu-ask-text').textContent") == play.ATTACH
        tried.clear()
        _page.click(page, "xemu-ask-yes")
        _page.until(page, "() => document.getElementById('status').textContent.startsWith('Attached to')")
        end = time.monotonic() + 30   # Play's feed may retry (every RETRY_S) before the attach replaces it
        while not any(t[0].startswith("helper:") for t in tried) and time.monotonic() < end:
            time.sleep(0.02)
        assert helpers == [77] and any(t[0].startswith("helper:") for t in tried) and len(launched) == 1

        _page.click(page, "track-live")                                    # off, then on by hand
        _page.until(page, "() => !azurkit.tracker.state.live")
        tray[0] = tmp_path / "tray.iso"                                   # another seed's build in xemu's tray
        _page.click(page, "track-live")
        _page.until(page, f"() => ({live})({json.dumps(trayed['sha256'])})", 300)
        assert page.evaluate("() => document.getElementById('status').textContent") == (
            f"Tracking seed {trayed['seed']} (tray.iso in xemu's tray): the Randomizer tab's Tracker")
        _page.click(page, "tab-tools")
        assert _page.until(page, "() => document.getElementById('tools-logs-line').textContent") == (
            f"Each build's log is kept in {app.logs.folder()}")
        _page.check_csp(page)
        page.close()
    finally:
        server.close()


# The tracker's looks (Step 4.2c2's looks seat), as the page measures them: WCAG's contrast ratio of each world-map
# badge's text with the ground it sits on, [what, ratio]; each shown item icon (the Settings item rows', a level's
# chips') and the picture it wears; whether the plan file's control is the tab's button (no native "No file chosen");
# and the width the Endpoints field's placeholder needs, and the room the field has for it.
TRACKER_LOOKS = """() => {
    const rgb = (text) => text.match(/[\\d.]+/g).slice(0, 3).map(Number);
    const lum = (c) => c.map((v) => v / 255).map((v) => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
        .reduce((sum, v, i) => sum + [0.2126, 0.7152, 0.0722][i] * v, 0);
    const ratio = (a, b) => { const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };
    const badges = [...document.querySelectorAll("#track-world .badge")].filter((b) => b.checkVisibility())
        .map((b) => [`${b.closest(".cell").dataset.level} ${b.className}`, ratio(rgb(getComputedStyle(b).color),
                                                                              rgb(getComputedStyle(b).backgroundColor))]);
    const icons = [...document.querySelectorAll("#rando-items .glyph, #track-level .glyph:not(.dot)")]
        .map((g) => [g.className, getComputedStyle(g).backgroundImage]);
    const open = document.getElementById("track-open"), ends = document.getElementById("track-endpoints");
    const style = getComputedStyle(ends), pen = document.createElement("canvas").getContext("2d");
    pen.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    return { badges, icons, file: [open.checkVisibility(), open.closest("label").checkVisibility(),
                                   open.closest("label").innerText.trim()],
             endpoints: [pen.measureText(ends.placeholder).width,
                         ends.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)] };
}"""
# The Table with Spoiler on: each Where cell's text and tip, and how far the Where head's text sits from its cells'
# text (px); then scrolled down its tab, whether the Level table's column heads are still what shows at their place.
TRACKER_TABLE = """() => {
    const left = (el) => { const r = document.createRange(); r.selectNodeContents(el); return r.getBoundingClientRect().left; };
    const where = [...document.querySelectorAll("#track-items td.where")];
    const cell = where.find((c) => c.textContent);
    return [where.filter((c) => c.textContent).map((c) => [c.textContent, c.title]),
            Math.abs(left(document.querySelector("#track-items th.where")) - left(cell))];
}"""
TRACKER_HEADS = """() => {
    const pane = document.getElementById("randomizer");
    pane.scrollTop = 600;
    return [pane.scrollTop, [...document.querySelectorAll("#track-places thead th")].every((th) => {
        const box = th.getBoundingClientRect();
        return document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2)?.closest("th") === th;
    })];
}"""


def test_the_trackers_page_reads_in_the_light_theme_and_its_table_and_bars_show_whole(browser, tmp_path, monkeypatch):
    """Step 4.2c2's looks (in the app's page, the site's the same): in the
    light theme each world-map badge's count reads (at least 4.5:1); a spot
    not shown is a plain dot, so no icon spoils the seed, and with Spoiler
    each item icon wears the icon sheet's tile (the fire barrier its own
    drawing); the plan file's control is the tab's "Open a plan file…" button, with no native
    "No file chosen" beside a tracked plan; the Endpoints field holds its
    whole placeholder; with Spoiler on the Table's Where head sits over its
    cells' text and a Where cut short shows whole in its tip; and scrolled
    down, the Level table's column heads stay in view under the tab's
    caption."""
    _home(monkeypatch, tmp_path / "home")
    doc = _profile("default")
    (tmp_path / "plan.json").write_text(json.dumps(doc), encoding="utf-8")
    level = next(s["level"] for s in sdk.tracker({"plan": doc, "spoiler": True})["spots"].values() if s["icon"].startswith("key_"))
    monkeypatch.setattr(app.pictures, "folder", lambda: tmp_path / "no-maps")   # no pictures: the chips show
    server = app.serve(_page.WEB)
    try:
        page = browser.new_page()
        page.goto(server.url)
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        _page.click(page, "theme")
        _page.click(page, "tab-randomizer")
        _page.until(page, "() => document.documentElement.dataset.theme === 'light' "
                          "&& document.querySelectorAll('#rando-items .glyph').length")
        _page.click(page, "rando-view-tracker")
        page.set_input_files("#track-open", str(tmp_path / "plan.json"))
        _page.until(page, "() => azurkit.tracker.state.view && !azurkit.tracker.state.running")
        page.evaluate("(level) => document.querySelector(`#track-world .cell[data-level='${level}']`).click()", level)
        _page.until(page, "() => document.querySelector('#track-level .spot')")
        assert page.evaluate("() => [...new Set([...document.querySelectorAll('#track-level .glyph')].map((g) => "
                             "`${g.className} ${getComputedStyle(g).backgroundImage}`))]") == ["glyph dot none"]
        page.evaluate("() => document.querySelector('#track-level .back').click()")
        _page.click(page, "track-spoiler")
        page.evaluate("(level) => document.querySelector(`#track-world .cell[data-level='${level}']`).click()", level)
        _page.until(page, "() => !azurkit.tracker.state.running && document.querySelector('#track-level .glyph[class*=key_]')"
                          " && document.querySelector('#track-world .badge:not(.near):not(.skip):not(:empty)')")
        page.evaluate("() => document.querySelector('#track-level .back').click()")
        looks = page.evaluate(TRACKER_LOOKS)
        page.evaluate("(level) => document.querySelector(`#track-world .cell[data-level='${level}']`).click()", level)
        looks["icons"] += page.evaluate(TRACKER_LOOKS)["icons"]
        assert [b for b in looks["badges"] if b[1] < 4.5] == [] and len(looks["badges"]) == len(
            sdk.tracker({"plan": doc})["status"]["levels"])
        assert [i for i in looks["icons"] if i[0] != "glyph fire_barrier" and f"{tracking.ART_VERSION}/icons.png" not in i[1]
                ] == [] and {"glyph key_life1", "glyph gem_diamond", "glyph power_ammo", "glyph ice_block",
                             "glyph acid_block", "glyph crystal", "glyph frag_air_1"} <= {i[0] for i in looks["icons"]}
        assert looks["file"] == [False, True, "Open a plan file…"]
        assert looks["endpoints"][0] <= looks["endpoints"][1], looks["endpoints"]
        _page.click(page, "track-table")
        where, apart = page.evaluate(TRACKER_TABLE)
        assert where and all(text == tip for text, tip in where) and apart < 1, (where, apart)
        assert page.evaluate(TRACKER_HEADS) == [600, True]
        _page.check_csp(page)
        page.close()
    finally:
        server.close()


def test_the_apps_saves_never_replace_the_image_its_build_read_nor_a_file_another_dialog_chose(tmp_path, monkeypatch):
    """Each of the app's saves (the image's ``api/save``, ``api/spoiler``,
    ``api/settings_file``: one ``writable``, SEC-16) refuses the image the
    randomized build read (D36), even once its save dialog chose it (its
    Replace confirmed), and a file there that a dialog chose for another
    save, or whose own dialog was cancelled since; each leaves it as it was."""
    _home(monkeypatch, tmp_path / "home")
    picked, other = tmp_path / "picked.iso", tmp_path / "other.txt"
    picked.write_bytes(bytes(64))
    other.write_bytes(b"kept")
    monkeypatch.setattr(sdk, "image", lambda recipe, progress=None, spoiler=True: (types.SimpleNamespace(size=64),
                                                                                   {"plan": {"sha256": "2"}}))
    monkeypatch.setattr(sdk, "spoiler", lambda plan, built=False: {"lines": ["seed 2"], "text": "seed 2\n"})
    answers = []
    server, replies = app.serve(_page.WEB), []
    server.window = types.SimpleNamespace(create_file_dialog=lambda *args, **kwargs: answers.pop(0))
    saves = {"out": ("api/save", {"recipe": {}, "build": None}), "spoiler": ("api/spoiler", {}),
             "settings": ("api/settings_file", {"settings": {}})}
    try:
        _post(server.url, "api/build", {"iso": str(picked)}, replies)
        for kind, (call, body) in saves.items():
            for answer, kind_asked, out in ((picked, kind, picked), (other, "spoiler" if kind != "spoiler" else "out",
                                                                     other), (None, kind, other)):
                answers.append(str(answer) if answer else None)
                _post(server.url, "api/choose", {"kind": kind_asked, "path": str(out)}, replies)
                _post(server.url, call, body | {"out": str(out)}, replies)
    finally:
        server.close()
    vanilla = {"refused": f"{picked}: it is a vanilla image, which AzurKit never writes over"}
    there = {"refused": f"{other} exists: choose another name, or delete it first"}
    assert replies[1:] == [{"path": str(picked)}, vanilla, {"path": str(other)}, there, {"path": None}, there] * 3
    assert (picked.read_bytes(), other.read_bytes()) == (bytes(64), b"kept")


def test_the_apps_tools_open_a_build_extract_to_a_new_path_and_clear_only_what_they_name(tmp_path, monkeypatch):
    """The Tools tab's app calls (Step 4.7c): ``api/open`` reads an AzurKit
    build's recipe (``sdk.open_build`` of the files it changed), ``api/info``
    says it is one, ``api/files`` lists its files and ``api/extract`` writes
    one to a new path, its size and sha256 the file's; never over the image
    it reads or a vanilla image, even once the save dialog chose it, nor
    over a file the dialog didn't choose, nor a name the image hasn't (D36).
    ``api/storage`` lists what the app keeps by name, and Clear removes those
    entries and nothing else: an image in the user data folder, beside the
    config, or in an entry's folder stays, and so does the folder (SEC-10)."""
    _home(monkeypatch, tmp_path / "home")
    files = {"gamedata/config.xbr": fill("a", 64), "movies/Credits.bik": fill("c", 32)}   # USA's names, ours bytes
    vanilla, built = tmp_path / "vanilla.iso", tmp_path / "built.iso"
    vanilla.write_bytes(image(files))
    monkeypatch.setenv(gate.USA.env, str(vanilla))   # the release's own image: no save writes over it
    at = vanilla.stat()
    stamp = gate.Stamp(gate.USA, vanilla, at.st_size, at.st_mtime_ns, False, at.st_ctime_ns)
    change = Change("gamedata/config.xbr", 0, hashlib.sha256(files["gamedata/config.xbr"][:4]).hexdigest(), b"AAAA",
                    "a 1")
    edits.build(stamp, [Layer("pack fps_unlock", "mods", "packs", {"pack": "fps_unlock", "params": {"target_fps": 120}},
                              [change])], built)
    images = {path: path.read_bytes() for path in (vanilla, built)}
    answers, replies = [], []
    server = app.serve(_page.WEB)
    server.window = types.SimpleNamespace(create_file_dialog=lambda *args, **kwargs: answers.pop(0))

    def call(path: str, body: dict) -> dict:
        replies.clear()
        _post(server.url, path, body, replies)
        return replies[0]

    def chosen(path: Path) -> None:   # the save dialog chose path (its Replace confirmed)
        answers.append(str(path))
        assert call("api/choose", {"kind": "extract", "path": str(path)}) == {"path": str(path)}

    out, there = tmp_path / "config.xbr", tmp_path / "there.txt"
    there.write_bytes(b"kept")
    data = platformdirs.user_data_path("AzurKit", appauthor=False)
    try:
        assert call("api/open", {"iso": str(built)}) == {"preset": json.loads(json.dumps(sdk.open_build(str(built), whole=False)))}
        assert call("api/info", {"iso": str(built)}) | {"version": None} == {
            "release": "usa", "label": "USA", "size": len(images[built]), "kind": "build", "whole": False,
            "version": None, "layers": ["1 pack"]}
        listed = {path: size for path, _, size in call("api/files", {"iso": str(built)})["files"]}
        assert (listed["gamedata/config.xbr"], listed["movies/Credits.bik"], "azurkit.json" in listed) == (64, 32, True)
        made = b"AAAA" + files["gamedata/config.xbr"][4:]
        assert call("api/extract", {"iso": str(built), "path": "gamedata/config.xbr", "out": str(out)}) == {
            "out": str(out), "size": 64, "sha256": hashlib.sha256(made).hexdigest()}
        assert out.read_bytes() == made
        refused = [call("api/extract", {"iso": str(built), "path": "gamedata/config.xbr", "out": str(out)}),
                   call("api/extract", {"iso": str(built), "path": "gamedata/config.xbr", "out": str(there)}),
                   call("api/extract", {"iso": str(built), "path": "nope.bin", "out": str(tmp_path / "nope")})]
        chosen(built)
        refused.append(call("api/extract", {"iso": str(built), "path": "gamedata/config.xbr", "out": str(built)}))
        chosen(vanilla)
        refused.append(call("api/extract", {"iso": str(built), "path": "gamedata/config.xbr", "out": str(vanilla)}))
        assert refused == [{"refused": f"{out} exists: choose another name, or delete it first"},
                           {"refused": f"{there} exists: choose another name, or delete it first"},
                           {"refused": "nope.bin: the image has no such file"},
                           {"refused": f"{built}: it is the image it extracts from, which AzurKit never writes over"},
                           {"refused": f"{vanilla}: it is a vanilla image, which AzurKit never writes over"}]
        assert {path: path.read_bytes() for path in images} == images and there.read_bytes() == b"kept"
        assert not (tmp_path / "nope").exists() and not list(tmp_path.glob("*.part"))

        kept = {app._config(): b"{}", app.swapcache.root() / "stamps.json": b"{}",
                app.swapcache.root() / "swap" / "k.pickle": b"swap", data / "content" / "v" / "m.glb": b"g",
                gate.data_path(gate.USA): b"image", data / "content" / "held.iso": b"i"}
        for path, value in kept.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        names = ["settings", "stamps", "swap", "content"]
        listed = call("api/storage", {})["entries"]
        assert [(e["name"], e["size"]) for e in listed] == list(zip(names, [2, 2, 4, 2], strict=True))
        cleared = call("api/storage", {"clear": True})
        assert (cleared["cleared"], [(e["name"], e["size"]) for e in cleared["entries"]]) == (names, [("content", 1)])
        assert [path for path in kept if path.exists()] == [gate.data_path(gate.USA), data / "content" / "held.iso"]
        assert gate.data_path(gate.USA).read_bytes() == b"image" and data.is_dir()
    finally:
        server.close()


def test_a_randomized_build_moves_the_tracker_to_its_exact_plan_and_each_plans_marks_stay_with_it(
        browser, tmp_path, monkeypatch, usa_iso):
    """D1043: after a randomized Build the tracker holds that build's own
    plan, its worn body's size folded in, with that plan's marks (none yet);
    the marks on the plan tracked before stay with it, there again when it
    is opened again, one made on its map while the new plan's first answer
    is on its way too. The same plan built again keeps its marks and the map
    shown."""
    _home(monkeypatch, tmp_path / "home")
    older, worn = _profile("default"), {"species": "balthazar"}
    (tmp_path / "plan.json").write_text(json.dumps(older), encoding="utf-8")
    index = json.loads((app.pictures.folder() / "maps.json").read_text(encoding="utf-8"))["levels"]
    where = {i["id"]: i["at"] for e in index.values() for i in e["items"] + e["spots"]}
    near = sorted(loc for loc, s in sdk.tracker({"plan": older})["spots"].items() if s["state"] == "near" and loc in where
                  and where[loc][2] == index[s["level"]]["main"])
    first, second = near[:2]
    shown = sdk.tracker({"plan": older})["spots"][second]["level"]
    settled = "() => !azurkit.tracker.state.running && !azurkit.tracker.state.queue.length && azurkit.tracker.state.view"
    head = "() => azurkit.tracker.state.view?.head.sha256 === %s && !azurkit.tracker.state.running"
    marks = "(sha) => azurkit.tracker.state.kept.marks[sha]?.collected ?? []"
    server = app.serve(_page.WEB)
    try:
        page = browser.new_page(viewport={"width": 1100, "height": 820})
        page.goto(server.url)
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        _page.fill(page, "iso-path", str(usa_iso))
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        _page.click(page, "tab-randomizer")
        _page.click(page, "rando-view-tracker")
        page.set_input_files("#track-open", str(tmp_path / "plan.json"))
        _page.until(page, head % json.dumps(older["sha256"]), 300)
        page.evaluate("(loc) => azurkit.tracker.ask({ toggle: loc })", first)
        _page.until(page, "() => azurkit.tracker.state.marks.collected?.length === 1", 60)

        _page.click(page, "rando-view-settings")
        _page.click(page, "rando-on")
        _page.fill(page, "rando-seed", "2")
        page.evaluate("(worn) => azurkit.characters.set(worn)", worn)
        page.evaluate("() => { azurkit.build = null; document.getElementById('build').click(); }")
        _page.until(page, "() => azurkit.build", 900)
        plan = page.evaluate("() => azurkit.build.report.plan")
        _page.until(page, head % json.dumps(plan["sha256"]), 300)
        on = {name: {} for name, pack in mods.PACKS.items() if pack.default_on}
        assert plan["share"] == sdk.randomizer_settings({"settings": sdk.catalog()["randomizer"]["defaults"], "packs": on,
                                                         "character": worn, "iso": str(usa_iso)})["share"]
        assert plan["share"] != older["share"]   # the size's fold is in it
        assert page.evaluate("() => azurkit.tracker.state.plan") == plan
        assert page.evaluate("() => azurkit.tracker.state.marks.collected ?? []") == []
        assert page.evaluate(marks, older["sha256"]) == [first]

        page.evaluate("(loc) => azurkit.tracker.ask({ toggle: loc })", second)
        _page.until(page, "() => azurkit.tracker.state.marks.collected?.length === 1", 60)
        page.evaluate("(level) => { azurkit.tracker.state.level = level; azurkit.tracker.draw(); }", shown)
        page.evaluate("() => { azurkit.build = null; document.getElementById('build').click(); }")
        _page.until(page, "() => azurkit.build", 900)
        _page.until(page, settled, 60)
        assert page.evaluate("() => [azurkit.tracker.state.marks.collected, azurkit.tracker.state.level]") == [
            [second], shown]

        page.set_input_files("#track-open", str(tmp_path / "plan.json"))   # the older plan's marks are back
        _page.until(page, head % json.dumps(older["sha256"]), 60)
        assert page.evaluate("() => azurkit.tracker.state.marks.collected") == [first]
        page.evaluate("(level) => azurkit.tracker.map.show(level, true)", shown)
        _page.click(page, "rando-view-tracker")
        _page.until(page, f"() => azurkit.tracker.map.drawnFor?.level === {json.dumps(shown)}", 60)
        page.evaluate("""(given) => { azurkit.tracker.open(given.plan); (%s)(given.at); }""" % MAP_CLICK.strip(),
                      {"plan": plan, "at": where[second][:2]})   # on the older plan's map, the new plan on its way
        _page.until(page, head % json.dumps(plan["sha256"]), 60)
        _page.until(page, settled, 60)
        assert sorted(page.evaluate(marks, older["sha256"])) == sorted([first, second])
        assert page.evaluate("() => azurkit.tracker.state.marks.collected") == [second]
        page.close()
    finally:
        server.close()


def test_a_reshape_shows_the_nearest_shape_marked_preview_at_once_and_its_exact_pictures_replace_it(
        browser, tmp_path, monkeypatch, usa_iso):
    """D1011: a shape slider's move shows at once the nearest shape the page
    holds, marked Preview (her shipped pictures, then a shape it has drawn);
    the exact pictures are asked of the engine, with those shapes, once the
    slider rests and no Build runs, one dress at a time for the shape asked
    last, and replace it, unmarked; a refused dress leaves the Preview marked,
    saying why; the same shape again is exact at once with no ask, her own
    shape her shipped pictures, held since her pick (drawn in the move's own
    call, with no request), and a build's character holds the shapes."""
    _home(monkeypatch, tmp_path / "home")
    view = sdk.pickers({"iso": None, "character": {"species": "garret4"}})
    view["chosen"] |= {"name": "booblord", "variant": "booblord", "shapes": [{"name": "bust", "title": "Bust size"}]}
    drawn = {side: base64.b64encode((_page.WEB / "characters" / f"nice_noreht.{side}.png").read_bytes()).decode()
             for side in ("front", "back")}
    asked, answers, held = [], [drawn, {"refused": "It ran out of memory"}, drawn], []

    def pickers(route) -> None:
        route.fulfill(json=view | {"character": route.request.post_data_json["given"]["character"]})

    def preview(route) -> None:
        asked.append(route.request.post_data_json["recipe"]["character"])
        answer = answers[min(len(asked), len(answers)) - 1]
        if len(asked) == 3:   # a dress still running, below
            held.append(lambda: route.fulfill(json=answer))
        else:
            route.fulfill(json=answer)
    pixels = """() => ["char-front", "char-back"].map((id) => document.getElementById(id).getContext("2d")
        .getImageData(0, 0, 160, 160).data.reduce((n, v) => n + v, 0))"""
    moved = """(value) => { const b = document.getElementById("char-shape:bust"); b.value = value;
        b.dispatchEvent(new Event("change")); }"""
    def shows(x: float | None, preview: bool) -> str:
        shape = json.dumps([["bust", x]] if x else [], separators=(",", ":"))
        return f"""() => {{ const s = azurkit.characters.state.shown; return s?.shape === {json.dumps(shape)} && s.preview
            === {json.dumps(preview)} && document.getElementById("char-previews").hasAttribute("data-preview")
            === {json.dumps(preview)}; }}"""
    note = "() => document.getElementById('char-preview-note').textContent"
    server = app.serve(_page.WEB)
    try:
        page = browser.new_page()
        for path, answer in (("pickers", pickers), ("preview", preview),
                             ("speculate", lambda route: route.fulfill(json={"ahead": False})),
                             ("prefetch", lambda route: route.fulfill(json={"ahead": False}))):
            page.route(f"**/api/{path}", answer)
        page.goto(server.url)
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        _page.fill(page, "iso-path", str(usa_iso))
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        _page.click(page, "tab-characters")
        _page.until(page, "() => azurkit.characters.state.view", 60)
        page.evaluate("() => azurkit.characters.set({ species: 'booblord' })")
        _page.until(page, """() => azurkit.characters.state.shown?.name === 'booblord'""", 60)
        hers = page.evaluate(pixels)

        page.evaluate(moved, "1.25")
        page.evaluate(moved, "1.3")   # the slider goes on: no dress of the shape it passed
        _page.until(page, shows(1.3, True), 10)
        assert page.evaluate(_perf.PREVIEWED)   # the gate's done-states, A59's and S51's
        assert page.evaluate(pixels) == hers and page.evaluate(note).startswith("Preview:")
        assert page.evaluate("() => azurkit.characters.character()") == {"species": "booblord", "shapes": {"bust": 1.3}}
        _page.until(page, shows(1.3, False), 30)
        assert page.evaluate(_perf.EXACT)   # A60's, A61's, S52's and S53's
        assert asked == [{"species": "booblord", "shapes": {"bust": 1.3}}] and page.evaluate(note).startswith("From the")
        exact = page.evaluate(pixels)
        assert exact != hers

        page.evaluate("() => { azurkit.building = true; }")   # a Build goes first
        page.evaluate(moved, "1.35")
        _page.until(page, shows(1.35, True), 10)
        assert page.evaluate(pixels) == exact   # the nearest now is the shape drawn
        page.wait_for_timeout(4000)
        assert len(asked) == 1
        page.evaluate("() => { azurkit.building = false; }")
        _page.until(page, "() => document.getElementById('char-preview-note').textContent === "
                          "'Preview: It ran out of memory'", 30)
        assert page.evaluate(shows(1.35, True)) and len(asked) == 2

        page.evaluate(moved, "1.3")
        _page.until(page, shows(1.3, False), 10)
        assert page.evaluate(pixels) == exact and len(asked) == 2
        # her own shape: drawn in the move's own call, no request (run 42122369507's Intel runner waited past 10 s for
        # her pictures from the app's server, which runs in this process)
        assert page.evaluate(f"(value) => {{ ({moved})(value); return ({shows(None, False)})(); }}", "1")
        assert page.evaluate(pixels) == hers and len(asked) == 2

        page.evaluate(moved, "1.4")
        while not held:   # the dress asked (Playwright's route runs inside this wait)
            page.wait_for_timeout(100)
        page.evaluate(moved, "1.45")   # a shape moved as a dress ends rests first: it may be one the slider is passing
        held.pop()()
        wanted = _page.until(page, "() => !azurkit.characters.state.dressing && [azurkit.characters.state.wanted?.shape]", 30)
        assert wanted == ['[["bust",1.45]]'] and len(asked) == 3
        _page.until(page, shows(1.45, False), 30)
        assert len(asked) == 4
        page.close()
    finally:
        server.close()


def test_the_apps_tools_track_an_opened_randomized_build_on_its_own_plan(browser, tmp_path, monkeypatch):
    """Track this build (the Tools tab's Open a build…): an opened build
    that holds a randomizer layer is tracked on its own plan, replayed from
    the seed and share string its manifest holds, nothing retyped; the
    Randomizer tab's Tracker shows it. A build with no randomizer greys the
    button with the line that says why."""
    _home(monkeypatch, tmp_path / "home")
    monkeypatch.setattr(app.pictures, "folder", lambda: tmp_path / "no-maps")
    files = {"gamedata/config.xbr": fill("a", 64)}   # USA's name, ours bytes
    vanilla = tmp_path / "vanilla.iso"
    vanilla.write_bytes(image(files))
    monkeypatch.setenv(gate.USA.env, str(vanilla))
    at = vanilla.stat()
    stamp = gate.Stamp(gate.USA, vanilla, at.st_size, at.st_mtime_ns, False, at.st_ctime_ns)
    change = Change("gamedata/config.xbr", 0, hashlib.sha256(files["gamedata/config.xbr"][:4]).hexdigest(), b"AAAA",
                    "a 1")
    doc = _profile("default")
    seeded = Layer("randomizer", "randomizer", "plan", {"seed": doc["seed"], "share": doc["share"]}, [change])
    plain = Layer("pack fps_unlock", "mods", "packs", {"pack": "fps_unlock", "params": {}}, [change])
    for name, layer in (("seeded", seeded), ("plain", plain)):
        edits.build(stamp, [layer], tmp_path / f"{name}.iso")
    server = app.serve(_page.WEB)
    try:
        page = browser.new_page()
        page.goto(server.url)
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        button = "() => [document.getElementById('tools-open-track').disabled, document.getElementById(" \
                 "'tools-open-track').title]"

        def opened(name: str) -> list:
            _page.click(page, "tab-tools")
            _page.fill(page, "tools-open-path", str(tmp_path / f"{name}.iso"))
            _page.click(page, "tools-open")
            _page.until(page, f"() => document.getElementById('tools-open-line').textContent.startsWith('{name}.iso:')")
            return page.evaluate(button)

        assert opened("seeded") == [False, "The tracker on this build's own plan (its seed and share string)"]
        _page.click(page, "tools-open-track")
        assert _page.until(page, "() => azurkit.tracker.state.view && !azurkit.tracker.state.running"
                                 " && azurkit.tracker.state.plan.sha256", 300) == doc["sha256"]
        assert page.evaluate("() => [azurkit.tab, document.getElementById('tracker').hidden, document.getElementById("
                             "'status').textContent]") == ["randomizer", False, f"Tracking seed {doc['seed']} "
                                                           "(seeded.iso): the Randomizer tab's Tracker"]
        assert opened("plain") == [True, "This build isn't randomized: it has no plan to track"]
        _page.check_csp(page)
        page.close()
    finally:
        server.close()


def test_calls_waiting_on_the_engines_cold_logic_read_count_its_checks_and_never_fall_back_inside_a_stage(tmp_path,
                                                                                                           monkeypatch):
    """A plan file's spoiler and a seed's plan asked while the engine's
    warm-up (the Tools or Randomizer tab's opening starts it) reads the
    randomizer's logic cold, a launch's first read: each one's records count
    the logic's checks ("Reading the randomizer's logic (checking the
    levels, 5 of 15)"), the spoiler's through ``api/progress``, then go on
    in their own stages, a percent never lower than the one before it in a
    stage (the warm-up counts on a seed plan's scale), so the bar moves and
    never goes back (D982, D1008; Step 4.7c)."""
    _home(monkeypatch, tmp_path / "home")
    monkeypatch.setattr(loader, "_KEPT", {})   # nothing in this process has read the logic yet
    plan = record_goldens.recorded(record_goldens.PLANS)["default"]["plan"]
    server, replies, seen, planned, seeded = app.serve(_page.WEB), [], [], [], []

    class Followed(dict):   # each record api/progress serves: a poll misses the last stage's 0.1 s on a starved thread
        def __setitem__(self, ident: object, call: tuple[str, dict]) -> None:
            super().__setitem__(ident, call)
            if call[0] == "plan_spoiler":
                seen.append(call[1])
    server.calls = Followed()
    try:
        engine._WARM.acquire()   # as the engine's loop takes it for a warm message
        engine._WARMING[:] = [progress_record("plan", "Reading the randomizer's logic")]
        threading.Thread(target=engine._warm_logic, daemon=True).start()
        asking = threading.Thread(target=_post, args=(server.url, "api/plan_spoiler", {"plan": plan}, replies))
        seeding = threading.Thread(target=lambda: seeded.append(engine.JOBS["plan"]({"seed": "2"},
                                                                                    progress=planned.append)))
        asking.start(), seeding.start()
        asking.join(), seeding.join()
    finally:
        server.close()

    def back(steps: list[dict]) -> list:   # a percent lower than the one before it in the same stage
        return [(a, b) for a, b in zip(steps, steps[1:])
                if a["stage"] == b["stage"] and None not in (a["percent"], b["percent"]) and b["percent"] < a["percent"]]
    read = {s["percent"] for s in seen if s["stage"] == "plan" and s["percent"] is not None}
    checked = any(s["label"].startswith("Reading the randomizer's logic (") for s in planned)
    assert (len(read) >= 3, back(seen), seen[-1]["stage"], len(replies[0]["lines"]) > 9, checked, back(planned),
            len(seeded)) == (True, [], "spoiler", True, True, [], 1), (seen, planned)


# The bottom bar from now on: ``bars`` is the bar at each change, [ms since now, its value (null: a moving stripe), its
# line], or null while it is hidden; given a button's id, now is its click, in the same call (a click in a call of its own
# came 259 ms after it on a loaded 3-core runner, run 41521288667: the round trip, not the page)
BARS = """(click) => {
    globalThis.bars = [];
    const t = globalThis.barsAt = performance.now();
    new MutationObserver(() => {
        const hidden = document.getElementById("progress-row").hidden;
        bars.push(hidden ? null : [performance.now() - t, document.getElementById("progress").getAttribute("value"),
                                   document.getElementById("progress-line").textContent]);
    }).observe(document.querySelector("footer"), { subtree: true, childList: true, characterData: true,
                                                   attributes: true });
    if (click) document.getElementById(click).click();
}"""
# Evaluated after BARS, on its clock: ``picking.picked`` is the ms of the page's next change event, a file's pick as the
# page hears it (Playwright's set_input_files is a call of its own: on GitHub's Intel Mac runner the bar came 1430 ms
# after BARS's clock, run 41678038275, the round trip's, not the page's), and ``picking.requests`` [ms, path] of each
# request the page makes from now on
PICKING = """() => {
    const real = globalThis.fetch.bind(globalThis);
    globalThis.picking = { picked: null, requests: [] };
    document.addEventListener("change", () => { picking.picked ??= performance.now() - barsAt; }, true);
    globalThis.fetch = (resource, options) => {
        picking.requests.push([performance.now() - barsAt, String(resource)]);
        return real(resource, options);
    };
}"""


def test_the_apps_track_this_seed_bar_follows_its_plan_from_the_click_and_the_fill_moves_it_through_its_reaches(
        browser, tmp_path, monkeypatch):
    """Step 4.3 train B3 (A23, D980): in the app's page, Track this seed's
    bar is its plan's from the click, polled at once as a build's (it used
    to wait 750 ms, by when a quick fill had told its last count), and the
    fill's count moves it through the time its reaches take (each item a
    reach places a step, the rest at once its last: counted by spots, the
    bar sat under 37 % until the plan was written), its records the one
    stream's (``core.progress.note``, folded into the plan's stage). Its
    fill reaches by the compiled reach's Python twin (``AZURKIT_NATIVE=0``,
    a host the library doesn't load on): the kernel's fill ends inside one
    of the bar's polls, its Track under D980's 1 s, so it owes no moving bar."""
    _home(monkeypatch, tmp_path / "home")
    monkeypatch.setattr(planner_fill, "_LAST_FILL", [None])   # the seed's fill not kept from another test: it fills
    monkeypatch.setenv("AZURKIT_NATIVE", "0")
    monkeypatch.setattr(native, "_LIB", None)
    server = app.serve(_page.WEB)
    try:
        page = browser.new_page()
        page.goto(server.url)
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        _page.click(page, "tab-randomizer")
        _page.until(page, "() => azurkit.rando.view?.share", 300)
        _page.fill(page, "rando-seed", "2")
        page.evaluate(BARS, "track-seed")
        _page.until(page, "() => document.getElementById('track-head').textContent.trim()", 300)
        bars = page.evaluate("() => bars")
        page.close()
    finally:
        server.close()
    shown = [b for b in bars if b is not None]
    counted = {int(b[1]) for b in shown if b[1] is not None and "(placing the items, " in b[2]}
    assert (shown[0][0] < 250, shown[0][2].startswith("Planning the seed"), len(counted) >= 2,
            max(counted, default=0) >= 50) == (True, True, True, True), bars


def test_the_apps_plan_file_spoiler_bar_follows_the_logic_read_from_the_pick(browser, tmp_path, monkeypatch):
    """Step 4.3 round 3 (A54 under 4 cores, D980): in the app's page, a
    plan file's spoiler asked while the engine still reads the randomizer's
    logic cold shows its bar from the pick and polls it at once, as Track's
    plan (it waited 750 ms to ask, so a spoiler done at 1.1 s showed one
    value), so the logic's counted checks move it. Each on the page's own
    clock and order (Step 4.4ci16): it asks for the spoiler within 500 ms of
    the pick it hears, the bar shows the ask's own line before its first
    poll (a kind it doesn't follow shows only after a poll, or at 1 s), and
    that poll comes under the 750 ms the old wait took."""
    _home(monkeypatch, tmp_path / "home")
    monkeypatch.setattr(loader, "_KEPT", {})   # nothing in this process has read the logic yet
    plan = tmp_path / "azurkit plan.json"
    plan.write_text(json.dumps(record_goldens.recorded(record_goldens.PLANS)["default"]["plan"]), encoding="utf-8")
    server = app.serve(_page.WEB)
    try:
        page = browser.new_page()
        page.goto(server.url)
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        _page.click(page, "tab-tools")
        page.evaluate(BARS)
        page.evaluate(PICKING)
        page.set_input_files("#tools-plan-file", str(plan))
        _page.until(page, "() => azurkit.tools.state.spoiler", 300)
        bars, picking = page.evaluate("() => [bars, picking]")
        assert page.evaluate(_perf.CALLS) == native.report()   # what the perf gate's native assert reads as a page leaves
        page.close()
    finally:
        server.close()
    shown = [b for b in bars if b is not None]
    asked = next(ms for ms, path in picking["requests"] if path == "api/plan_spoiler")
    polled = next(ms for ms, path in picking["requests"] if path == "api/progress" and ms >= asked)
    first = next(b for b in shown if b[0] >= asked)
    assert (asked - picking["picked"] < 500, first[1:] == [None, "Writing the spoiler…"], first[0] <= polled,
            polled - asked < 750, len({b[1] for b in shown}) >= 2) == (True, True, True, True, True), (picking, bars)


def test_the_apps_bar_polls_any_asks_record_from_its_click_so_a_counted_1_2_s_call_moves_before_1_s(
        browser, tmp_path, monkeypatch):
    """Step 4.4bb (A11, D980): in the app's page every ask in flight has its
    record polled from its click, not from 750 ms, by when a G4 match's bar
    took its second value past 1 s and a 1.4 s match could show only one.
    Verify every file, a kind the bar doesn't follow from the click, its
    record counting 12 steps over 1.2 s, moves the bar to its second value
    within 1 s of its ask, on the page's own clock. Its image's path is a full
    one on every OS (Windows refused '/nowhere/usa.iso', no drive, at once:
    run 41981438506's bars [])."""
    _home(monkeypatch, tmp_path / "home")

    def counted(iso: str, progress) -> dict:   # 12 steps, 0.1 s apart
        for done in range(13):
            progress(progress_record("check", sdk.CHECK_ALL, done, 12))
            time.sleep(0.1)
        return {"files": 0}
    monkeypatch.setattr(sdk, "verify_all", counted)
    server = app.serve(_page.WEB)
    try:
        page = browser.new_page()
        page.goto(server.url)
        _page.until(page, "() => globalThis.azurkit?.ready && !azurkit.asks.size", 120)
        page.evaluate(BARS)
        page.evaluate(PICKING)
        page.evaluate("(iso) => { azurkit.verified = null; azurkit.engine.call('verify_all', { iso })"
                      ".then((reply) => { azurkit.verified = reply; }); }", str(tmp_path / "usa.iso"))
        _page.until(page, "() => azurkit.verified && !azurkit.asks.size", 60)
        bars, picking, verified = page.evaluate("() => [bars, picking, azurkit.verified]")
        page.close()
    finally:
        server.close()
    assert verified == {"files": 0}, verified   # the counted call's answer, not a refusal
    asked = next(ms for ms, path in picking["requests"] if path == "api/verify_all")
    values = {}   # each value the bar took, at the ms it first took it
    for b in bars:
        if b is not None and b[1] is not None:
            values.setdefault(b[1], b[0])
    assert len(values) >= 2 and sorted(values.values())[1] - asked < 1000, (picking, bars)


def test_the_apps_data_edits_join_the_build_and_outlive_a_relaunch(browser, tmp_path, monkeypatch, usa_iso):
    """Step 4.7a in the app's page: a Data tab edit made before an image
    (api/data, api/data_edit) is the setup the app remembers (api/setup),
    so the next launch's page holds it, its cell marked ● and the Patches
    tab's line naming it; once the image's path is typed, Build applies it
    after the packs, its config.xbr CPython's of the same recipe."""
    from tests.test_site import DATA_CELL, DATA_EDIT
    _home(monkeypatch, tmp_path / "home")
    hp = next(c for s in sdk.data({"what": "view", "kind": "player"})["sections"] for b in s["blocks"]
              for _, cells in b["rows"] for c in cells if c and c.get("name") == "initial hp")
    _, col, row = hp["ref"]
    op = sdk.data_edit({"edit": {"table": "settings_foo", "col": col, "row": row, "value": "500"}})["op"]
    cell = ["settings_foo", "initial hp"]
    for launch in (1, 2):
        server = app.serve(_page.WEB)
        try:
            page = browser.new_page()
            page.goto(server.url)
            _page.until(page, "() => globalThis.azurkit?.ready", 120)
            if launch == 1:
                _page.click(page, "tab-data")
                _page.until(page, f"() => azurkit.data.state.answer && ({DATA_CELL})({json.dumps(cell)})")
                page.evaluate(DATA_EDIT, [*cell, "500"])
                _page.until(page, "() => azurkit.xbr.length === 1")
                for _ in range(50):   # the page remembers its setup a moment after a change (api/setup)
                    if app._kept().get("setup", {}).get("xbr"):
                        break
                    time.sleep(0.1)
                assert app._kept()["setup"]["xbr"] == [op]
            else:
                assert _page.until(page, "() => azurkit.xbr.length && azurkit.xbr") == [op]
                assert page.evaluate("() => document.getElementById('xbr-note').textContent") == (
                    "The Data tab holds 1 config.xbr edit, which each build applies.")
                _page.click(page, "tab-data")
                assert _page.until(page, f"() => azurkit.data.state.answer && ({DATA_CELL})({json.dumps(cell)})"
                                   )[:2] == ["● 500", "cell changed"]
                _page.fill(page, "iso-path", str(usa_iso))
                _page.until(page, "() => azurkit.vanilla")
                page.evaluate("() => document.querySelector('#build').click()")
                built = _page.built(page)
                defaults = {p["name"]: {} for p in sdk.catalog()["packs"] if p["default_on"]}
                _, report = sdk.image({"iso": str(usa_iso), "packs": defaults, "xbr": [op]})
                assert built["result"]["gamedata/config.xbr"] == report["result"]["gamedata/config.xbr"]
                assert built["result"] == report["result"]
            _page.check_csp(page)
            page.close()
        finally:
            server.close()
