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
import contextlib
import hashlib
import importlib.metadata
import io
import json
import multiprocessing
import os
import plistlib
import re
import struct
import subprocess
import sys
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

from azurkit import __main__ as _entry  # noqa: F401 (the frozen app's entry; fullsuite picks this file for it)
from azurkit import app, cli, sdk
from azurkit.app import engine
from azurkit.core import gate, iso, progress
from azurkit.core.progress import record as progress_record
from azurkit.edits import manifest as edits
from azurkit.edits.layer import Change, Layer
from azurkit.tools import mods
from azurkit.tools.characters import pool
from azurkit.tools.randomizer import tracking
from azurkit.tools.randomizer.planner import fill as planner_fill
from azurkit.tools.randomizer.planner import loader
from scripts import freeze, record_goldens
from tests import _g1, _page
from tests._xiso import fill, image
from tests.test_randomizer import TRACKER, _profile, shows_gems, tracker_states

ROOT = Path(__file__).resolve().parent.parent
NEVER = ("unicorn", "capstone", "zig", "tkinter", "_tkinter", "_gdbm", "_dbm")
OURS = {"azurkit", "__main__", "web", freeze.ICON.name}
# The bootloader is under PyInstaller's Bootloader Exception; the loader and runtime hooks it bundles are Apache-2.0.
PYINSTALLER_RUNTIME = ("pyimod", "pyiboot", "pyi_rth_", "_pyi_rth_utils")
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
        if name in OURS:
            owners[name] = "AzurKit (MIT)"
        elif name.startswith(PYINSTALLER_RUNTIME):
            owners[name] = "PyInstaller's runtime (Apache-2.0)"
        elif name in sys.stdlib_module_names or name.startswith(("_sysconfigdata_", "libpython")):
            owners[name] = "Python (PSF-2.0)"
        elif name.endswith(".dist-info"):   # a distribution's metadata (numpy's, which PyInstaller's hook keeps)
            dist = name.removesuffix(".dist-info").rsplit("-", 1)[0]
            owners[name] = f"{dist} ({_licence(dist)})"
        else:
            owners[name] = ", ".join(f"{d} ({_licence(d)})" for d in sorted(set(dists.get(name, ())))) or "unknown"
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


def _home(monkeypatch, home: Path) -> None:
    """This process's user folders, and its children's, under ``home``:
    HOME, and every folder platformdirs finds the app's config, data, cache
    and downloads in before HOME, whatever the host sets: no XDG_*_HOME (a
    GitHub Linux runner sets XDG_CONFIG_HOME, so every test's app.json was
    one file there, Step 4.4ci2) and, on Windows, whose known folders don't
    follow HOME, platformdirs' WIN_PD_OVERRIDE_* and USERPROFILE."""
    monkeypatch.setenv("HOME", str(home))
    for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(name, raising=False)
    if os.name == "nt":
        monkeypatch.setenv("USERPROFILE", str(home))
        for kind in ("APPDATA", "LOCAL_APPDATA", "DOWNLOADS"):
            monkeypatch.setenv(f"WIN_PD_OVERRIDE_{kind}", str(home / kind))


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
            except BaseException:
                served.kill()
                raise
            served.stdin.close()
            assert (served.wait(30), served.stderr.read()) == (0, "")

    def left(self) -> list[Path]:
        kept = [Path(getattr(self.dirs, f"user_{kind}_dir")) for kind in ("data", "config", "cache", "state", "log")]
        return [*self.cwd.iterdir(), *(p for p in [*self.home.rglob("*"), *self.tmp.rglob("*")]
                                       if p.is_file() and not any(map(p.is_relative_to, kept)))]


def test_the_frozen_app_runs_read_only_and_gives_the_same_verdicts(frozen_app, tmp_path, verify_argv, verdicts,
                                                                    monkeypatch):
    """The app holds no Unicorn, zig, capstone or GPL code (each name in it
    is Python's, PyInstaller's runtime, AzurKit's or a distribution's whose
    licence isn't GPL; the runtime's readline is editline). On macOS its
    icon is AzurKit's: the .icns its Info.plist names is ``freeze.ICON``,
    byte for byte. Run read-only, with a fresh HOME and TMPDIR from an empty
    folder and the tests' no-window mode, its window path exits 1 at once,
    and it gives CPython's verdicts, finds the images' folder through
    platformdirs under that HOME, and leaves itself, that folder, HOME and
    TMPDIR as they were but for platformdirs' folders."""
    app_path, before = frozen_app
    owners = _owners(app_path)
    assert [name for name in owners if name.lower().startswith(NEVER)] == []
    assert {name: owner for name, owner in owners.items() if "GPL" in owner or owner == "unknown"} == {}
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
    so its storage, is new each launch). No CSP violation, no request but to
    the app's own server, and the app, the folder, HOME and TMPDIR are as they
    were but for platformdirs' folders and the saved build."""
    app_path, before = frozen_app
    box = Sandbox(tmp_path, monkeypatch)
    out = tmp_path / "out" / f"{usa_iso.stem} (AzurKit).iso"
    out.parent.mkdir()
    context, requests = browser.new_context(), []
    context.on("request", lambda request: requests.append(request.url))
    try:
        with box.serving(app_path) as url:
            page = context.new_page()
            page.goto(url)
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
            assert [host["iso"], host["theme"], host["setup"]] == [str(usa_iso), "light", setup]
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


def test_the_app_remembers_the_pages_setup_in_its_config_beside_the_theme(tmp_path, monkeypatch):
    """``api/setup`` remembers the page's setup (D915) in the app's config,
    beside the theme, written whole; ``host.json`` gives it to the next
    page, and ``api/restore`` gives back what of it still applies, the rest
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
        "setup: an object of ticked, values, xbr, randomizer, character only, or null": {"ticked": [], "iso": "/a.iso"},
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
        assert call("host.json")["setup"] == setup
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


def test_the_apps_characters_tab_installs_from_a_folder_source_and_draws_a_models_two_pictures(
        tmp_path, monkeypatch, usa_iso):
    """The app's half of the Characters tab (Step 4.3d): ``api/content`` reads Azurik-Custom-Content from a folder
    (a clone), ``api/install`` copies an entry into the content folder, every file checked, and ``api/pickers``
    lists its variant marked community; ``api/content_source`` remembers the folder for the next page
    (``host.json``); ``api/preview`` draws the chosen model from the front and from behind, two PNGs."""
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


def _post(url: str, call: str, body: dict, replies: list, timeout: float = 120) -> None:
    """POST ``body`` to the engine's ``call`` (``api/save``, say) from the
    page at ``url`` (its token in the query); its reply goes in ``replies``."""
    host, query = urllib.parse.urlsplit(url).netloc, f"?{urllib.parse.urlsplit(url).query}"
    request = urllib.request.Request(f"http://{host}/{call}{query}", json.dumps(body).encode(),
                                     {"Origin": f"http://{host}", "Content-Type": "application/json"})
    with contextlib.suppress(OSError), urllib.request.urlopen(request, timeout=timeout) as reply:
        replies.append(json.load(reply))   # the app may quit before it answers


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
        threading.Thread(target=_post, args=(url, "api/save", {"recipe": recipe, "out": str(out / name)}, []),
                         daemon=True).start()
        end = time.monotonic() + 120
        while True:
            with urllib.request.urlopen(f"http://{host}/api/progress{query}", timeout=10) as reply:
                if json.load(reply)["done"]:
                    return
            assert time.monotonic() < end, "the save never started writing"
            time.sleep(0.05)

    with subprocess.Popen([sys.executable, "-m", "azurkit", "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, env=os.environ | {"HOME": str(tmp_path / "home")}) as served:
        try:
            save_until_writing(served.stdout.readline().strip(), "served.iso")
        except BaseException:
            served.kill()
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
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def test_the_apps_engine_process_answers_small_asks_during_a_build_and_cancel_stops_it(tmp_path, monkeypatch,
                                                                                       usa_iso):
    """Step 4.3i: the app's builds run in its engine process
    (``app.engine.Spawned``), so the server's own answers (the species list,
    the setup, the build's progress: its stage's ``core.progress`` record)
    come within 0.5 s while keylord builds, its swap's work spread over that
    process's pool (``app.procpool``); Cancel ends that process at once, and
    its pool's children with it, the build is refused, another process
    takes the next Build, and closing the app ends it too."""
    _home(monkeypatch, tmp_path / "home")
    server = app.serve(_page.WEB, engine.Spawned())
    first, replies = server.engine.pid, []

    def ask(path: str, body: dict) -> tuple[float, dict]:
        got, began = [], time.monotonic()
        _post(server.url, path, body, got)
        return time.monotonic() - began, got[0]

    try:
        ask("api/pickers", {"given": {}})   # the species list read once, as the page's first ask reads it
        building = threading.Thread(target=_post, args=(server.url, "api/build", {
            "iso": str(usa_iso), "packs": {}, "character": {"species": "keylord"}}, replies))
        building.start()
        time.sleep(1.5)   # into the build's Python (it takes about 5 s)
        assert building.is_alive()
        took = [ask("api/pickers", {"given": {}}), ask("api/setup", {"setup": {"ticked": ["fps_unlock"]}})]
        assert [s < 0.5 for s, _ in took] == [True, True] and took[1][1] == {}, took[0][0]
        host, query = urllib.parse.urlsplit(server.url).netloc, urllib.parse.urlsplit(server.url).query
        with urllib.request.urlopen(f"http://{host}/api/progress?{query}", timeout=10) as reply:
            step = json.load(reply)
        assert step["calls"]["build"]["stage"] in progress.STAGES and step["stage"] == step["calls"]["build"]["stage"]
        end, pool = time.monotonic() + 10, []
        while building.is_alive() and not pool and time.monotonic() < end:
            pool = subprocess.run(["pgrep", "-P", str(first)], capture_output=True, text=True).stdout.split()
            time.sleep(0.05)
        assert pool and ask("api/cancel", {})[1] == {}
        building.join(5)
        assert (building.is_alive(), replies) == (False, [{"refused": "Cancelled: nothing was built"}])
        assert _ended(first) and all(_ended(int(pid)) for pid in pool) and server.engine.pid != first
        took, built = ask("api/build", {"iso": str(usa_iso), "packs": {}})
        assert built["size"] == sdk.image({"iso": str(usa_iso), "packs": {}})[0].size, built
        last = server.engine.pid
    finally:
        server.close()
    assert _ended(last)


def test_a_cancels_next_engine_reads_the_logic_then_builds_then_reads_the_image_for_its_pictures(monkeypatch):
    """After Cancel the app's next engine gets the warms the page asked (the
    image picked first, then the Randomizer tab's logic) and the next Build
    at once: it reads the randomizer's logic, builds the seed, and only then
    reads the image as the pictures do, so neither the logic's read nor the
    build waits on the pictures' Python ("Cancel a build, then Build", A29:
    about 0.3 s; Step 4.3 round 3)."""
    from azurkit.app import procpool

    log = []

    def step(name: str, seconds: float = 0.0) -> None:
        log.append(name)
        time.sleep(seconds)
        log.append(f"{name} done")
    monkeypatch.setattr(engine, "orphaned", lambda: None)   # the loop on a thread of this process, not its own
    monkeypatch.setattr(procpool, "install", lambda: None)
    monkeypatch.setattr(sdk, "randomizer_logic", lambda progress=None: step("logic", 0.2))
    monkeypatch.setattr(sdk, "pickers", lambda given: step("pictures"))
    monkeypatch.setitem(engine.JOBS, "image", engine._warmed(lambda recipe: step("build", 0.2) or {}))
    here, there = multiprocessing.Pipe()
    loop = threading.Thread(target=engine._main, args=(there,), daemon=True)
    loop.start()
    for message in engine._warm_messages({"image": ("in.iso",), "randomizer": ()}):
        here.send(message)
    here.send(("call", 1, "image", ({"iso": "in.iso", "randomizer": {"seed": "2"}},), False))
    assert here.recv()[:2] == ("done", 1)
    end = time.monotonic() + 10
    while "pictures done" not in log and time.monotonic() < end:
        time.sleep(0.01)
    here.close()
    loop.join(10)
    assert (log, loop.is_alive(), engine._BUILDS) == (
        ["logic", "logic done", "build", "build done", "pictures", "pictures done"], False, 0)


def test_the_apps_engine_counts_the_swaps_items_on_the_stage_its_call_reported_last(monkeypatch):
    """``pool.TICK``, set by the app's engine as it follows a call (Step
    4.3m): the swap's items done of total, on the stage the call reported
    last (its dress's line), each percent once; a call no one follows
    counts nothing, and another thread's work isn't its."""
    def dress(recipe, progress=None):
        if progress is not None:
            progress(progress_record("dress", "Dressing keylord"))
        return pool.each(lambda shared, item: item + shared, 1, list(range(8)))

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


def test_the_apps_save_writes_the_image_its_build_made_planned_once_and_hashed_from_the_build_on(
        tmp_path, monkeypatch, usa_iso):
    """Step 4.3i: Save (``api/save`` with the build's id) writes the image
    its Build made, kept in the engine and hashed there from the moment it
    was made, without planning it again: the build's report with the
    output's path, size and sha256, as ``sdk.build`` gives them. A save
    whose build the engine keeps no more (another Build's since, or a
    cancel's new process) builds its recipe again: the same image."""
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
        _post(server.url, "api/build", recipe, built)
        assert list(engine._BUILT) == [built[1]["build"]]   # a new Build drops the last one's image
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
        return sdk.vanilla(str(usa_iso)), engine.JOBS["match"](recipe)
    try:
        first = launch()
        assert (hashed, dressed) == ([1], [1])
        swapcache.install(tmp_path / "cache", tmp_path / "cache.key")
        assert launch() == first and (hashed, dressed) == ([1, 1], [1, 1])
        swapcache.install(tmp_path / "cache", tmp_path / "cache.key")   # the next launch's stores, on the same folder
        assert launch() == first and (hashed, dressed) == ([1, 1], [1, 1])
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
    assert stat.S_IMODE(mine_key.stat().st_mode) == 0o600
    theirs.put(key, b"theirs")
    assert swapcache.settle()
    entry.write_bytes(theirs.kept.file("swap", key).read_bytes())
    assert mine.get(key) is None and theirs.get(key) == b"theirs"
    entry.write_bytes(pickle.dumps(Planted()))
    older.write_bytes(pickle.dumps(Planted()))   # 4.3i's file of it
    monkeypatch.setattr(characters, "CACHE", mine)
    assert characters._kept(key, lambda: "worked out") == "worked out" and not ran.exists()
    assert characters._kept(key, lambda: "again") == "worked out"   # what it kept, this install's
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
            "refused": "tracker: an object of plan, marks, endpoints and gems only, or null"}
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
        _page.click(page, "track-live")
        _page.until(page, "() => azurkit.tracker.state.live?.here && azurkit.tracker.state.marks.live")
        view = page.evaluate("() => azurkit.tracker.state.view")
        assert tracking.digest(view) == tracking.digest(sdk.tracker(
            {"plan": doc, "marks": {"collected": [near], "live": {near: 0.5}}, "kit": kit, "held": dict(at.inv)}))
        dot, state, line, follows, you = page.evaluate(shown)
        assert (dot, state, follows, you) == ("●", "live", level, "● you are here")
        item = sdk.tracker({"plan": doc, "spoiler": True})["spots"][near]["name"]
        assert line.startswith(f"{level} · USA · xemu, scripted · last: {item} ({level}), 0:0")
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
    its radio's middle) and the count say how many are left, the counter
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
        floors = page.evaluate("() => [...document.querySelectorAll('#map-floors label')].map((l) => l.textContent.trim())")
        assert len(entry["floors"]) < 2 or floors[entry["main"]] == f"{entry['main'] + 1} · {dots}"
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
    the map keeps the floor shown wherever they go."""
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
    its size from poll to poll); a player who walks out of the view's
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
        _page.check_csp(page)
        page.close()
    finally:
        server.close()


def test_a_collected_spot_leaves_the_map_and_a_live_pickup_flashes_and_says_what_was_got(browser, tmp_path, monkeypatch):
    """Step 4.3 live tracker (the owner, 2026-11-01: "when an item is
    collected on the tracker, can you remove it from the map, with a toggle
    option for showing them instead? And make it more noticeable when they
    are collected"): a spot marked collected (a click, or Live) leaves the
    level's map; Show collected (remembered) shows it again, dimmed and
    clickable; a Live pickup flashes its spot a moment before it leaves,
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
        _page.click(page, "track-collected")
        played.takes.append(game.Took(got, 0.5))
        _page.until(page, "() => !document.getElementById('track-got').hidden")
        assert page.evaluate("() => document.getElementById('track-got').textContent") == (
            f"Got: {spots[got]['name']} · {level}")
        assert page.evaluate(drawn, got) == [f"{spots[got]['name']}: collected (live)"]   # flashing, on the map
        assert page.evaluate("() => [document.querySelector('#track-count .got.fresh')?.textContent,"
                             " getComputedStyle(document.getElementById('track-got')).animationName]") == [
            "Collected 2", "track-got"]
        _page.until(page, f"() => !({drawn})('{got}').length && document.getElementById('track-got').hidden", 30)
        page.emulate_media(reduced_motion="reduce")
        played.takes.append(game.Took(still, 0.6))
        _page.until(page, "() => !document.getElementById('track-got').hidden")
        assert page.evaluate("""() => [getComputedStyle(document.getElementById('track-got')).animationName,
            document.querySelector('#track-count .got.fresh')?.getAnimations().length]""") == ["none", 0]
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
    ``names`` ({record: the species its critterGenerator names}), each spot's node in the level's main graph."""

    SCENE, PD, CRITTER, ENTITY, INV, GRAPH, VEC, NODES = (0x100000 * k for k in range(1, 9))

    def __init__(self, level: str, names: dict[int, str] | None = None, records: int = 8):
        from azurkit.tools.randomizer.live import game, recipes

        self.mem: dict[int, int] = {}
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
        return bytes(self.mem.get(va + i, 0) for i in range(n))

    def read_many(self, wants: list) -> list:
        return [self.read(va, n) for va, n in wants]


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

# The tracker's looks (Step 4.2c2's looks seat), as the page measures them: WCAG's contrast ratio of each world-map
# badge's text and of each flat-filled item icon (the Settings item rows', a level's chips') with the ground it sits
# on, [what, ratio]; whether the plan file's control is the tab's button (no native "No file chosen"); and the width
# the Endpoints field's placeholder needs, and the room the field has for it.
TRACKER_LOOKS = """() => {
    const rgb = (text) => text.match(/[\\d.]+/g).slice(0, 3).map(Number);
    const lum = (c) => c.map((v) => v / 255).map((v) => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
        .reduce((sum, v, i) => sum + [0.2126, 0.7152, 0.0722][i] * v, 0);
    const ratio = (a, b) => { const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };
    const flat = (bg) => bg !== "transparent" && !/^rgba\\(.*, 0\\)$/.test(bg);
    const ground = (el) => {
        for (; el; el = el.parentElement) if (flat(getComputedStyle(el).backgroundColor)) return rgb(getComputedStyle(el).backgroundColor);
    };
    const badges = [...document.querySelectorAll("#track-world .badge")].filter((b) => b.checkVisibility())
        .map((b) => [`${b.closest(".cell").dataset.level} ${b.className}`, ratio(rgb(getComputedStyle(b).color),
                                                                              rgb(getComputedStyle(b).backgroundColor))]);
    const icons = [...document.querySelectorAll("#rando-items .glyph, #track-level .glyph:not(.dot)")]
        .filter((g) => flat(getComputedStyle(g).backgroundColor))
        .map((g) => [g.className, ratio(rgb(getComputedStyle(g).backgroundColor), ground(g.parentElement))]);
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
    light theme each world-map badge's count reads (at least 4.5:1) and
    each item icon stands out from its row or chip (at least 2:1); the plan
    file's control is the tab's "Open a plan file…" button, with no native
    "No file chosen" beside a tracked plan; the Endpoints field holds its
    whole placeholder; with Spoiler on the Table's Where head sits over its
    cells' text and a Where cut short shows whole in its tip; and scrolled
    down, the Level table's column heads stay in view under the tab's
    caption."""
    _home(monkeypatch, tmp_path / "home")
    doc = _profile("default")
    (tmp_path / "plan.json").write_text(json.dumps(doc), encoding="utf-8")
    level = next(s["level"] for s in sdk.tracker({"plan": doc, "spoiler": True})["spots"].values() if s["icon"] == "key")
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
        _page.click(page, "track-spoiler")
        page.evaluate("(level) => document.querySelector(`#track-world .cell[data-level='${level}']`).click()", level)
        _page.until(page, "() => !azurkit.tracker.state.running && document.querySelector('#track-level .glyph.key')"
                          " && document.querySelector('#track-world .badge:not(.near):not(.skip):not(:empty)')")
        page.evaluate("() => document.querySelector('#track-level .back').click()")
        looks = page.evaluate(TRACKER_LOOKS)
        page.evaluate("(level) => document.querySelector(`#track-world .cell[data-level='${level}']`).click()", level)
        looks["icons"] += page.evaluate(TRACKER_LOOKS)["icons"]
        assert [b for b in looks["badges"] if b[1] < 4.5] == [] and len(looks["badges"]) == len(
            sdk.tracker({"plan": doc})["status"]["levels"])
        assert [i for i in looks["icons"] if i[1] < 2] == [] and {"glyph key", "glyph gem_diamond", "glyph power_ammo",
            "glyph ice_block", "glyph acid_block", "glyph crystal"} <= {i[0] for i in looks["icons"]}
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
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
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


def test_the_apps_tools_track_an_opened_randomized_build_on_its_own_plan(browser, tmp_path, monkeypatch):
    """Track this build (the Tools tab's Open a build…): an opened build
    that holds a randomizer layer is tracked on its own plan, replayed from
    the seed and share string its manifest holds, nothing retyped; the
    Randomizer tab's Tracker shows it. A build with no randomizer greys the
    button with the line that says why."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
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
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(loader, "_KEPT", {})   # nothing in this process has read the logic yet
    plan = record_goldens.recorded(record_goldens.PLANS)["default"]["plan"]
    server, replies, seen, planned, seeded = app.serve(_page.WEB), [], [], [], []
    try:
        engine._WARM.acquire()   # as the engine's loop takes it for a warm message
        engine._WARMING[:] = [progress_record("plan", "Reading the randomizer's logic")]
        threading.Thread(target=engine._warm_logic, daemon=True).start()
        asking = threading.Thread(target=_post, args=(server.url, "api/plan_spoiler", {"plan": plan}, replies))
        seeding = threading.Thread(target=lambda: seeded.append(engine.JOBS["plan"]({"seed": "2"},
                                                                                    progress=planned.append)))
        asking.start(), seeding.start()
        while asking.is_alive() or seeding.is_alive():
            if (step := server.progress()["calls"].get("plan_spoiler")) and step not in seen[-1:]:
                seen.append(step)
            time.sleep(0.01)
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
# line], or null while it is hidden
BARS = """() => {
    globalThis.bars = [];
    const t = performance.now();
    new MutationObserver(() => {
        const hidden = document.getElementById("progress-row").hidden;
        bars.push(hidden ? null : [performance.now() - t, document.getElementById("progress").getAttribute("value"),
                                   document.getElementById("progress-line").textContent]);
    }).observe(document.querySelector("footer"), { subtree: true, childList: true, characterData: true,
                                                   attributes: true });
}"""


def test_the_apps_track_this_seed_bar_follows_its_plan_from_the_click_and_the_fill_moves_it_through_its_reaches(
        browser, tmp_path, monkeypatch):
    """Step 4.3 train B3 (A23, D980): in the app's page, Track this seed's
    bar is its plan's from the click, polled at once as a build's (it used
    to wait 750 ms, by when a quick fill had told its last count), and the
    fill's count moves it through the time its reaches take (each item a
    reach places a step, the rest at once its last: counted by spots, the
    bar sat under 37 % until the plan was written), its records the one
    stream's (``core.progress.note``, folded into the plan's stage)."""
    _home(monkeypatch, tmp_path / "home")
    monkeypatch.setattr(planner_fill, "_LAST_FILL", [None])   # the seed's fill not kept from another test: it fills
    server = app.serve(_page.WEB)
    try:
        page = browser.new_page()
        page.goto(server.url)
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        _page.click(page, "tab-randomizer")
        _page.until(page, "() => azurkit.rando.view?.share", 300)
        _page.fill(page, "rando-seed", "2")
        page.evaluate(BARS)
        _page.click(page, "track-seed")
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
    value), so the logic's counted checks move it."""
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
        page.set_input_files("#tools-plan-file", str(plan))
        _page.until(page, "() => azurkit.tools.state.spoiler", 300)
        bars = page.evaluate("() => bars")
        page.close()
    finally:
        server.close()
    shown = [b for b in bars if b is not None]
    assert (shown[0][0] < 500, shown[0][2].startswith(("Writing the spoiler", "Reading the randomizer's logic")),
            len({b[1] for b in shown}) >= 2) == (True, True, True), bars


def test_the_apps_data_edits_join_the_build_and_outlive_a_relaunch(browser, tmp_path, monkeypatch, usa_iso):
    """Step 4.7a in the app's page: a Data tab edit made before an image
    (api/data, api/data_edit) is the setup the app remembers (api/setup),
    so the next launch's page holds it, its cell marked ● and the Patches
    tab's line naming it; once the image's path is typed, Build applies it
    after the packs, its config.xbr CPython's of the same recipe."""
    from tests.test_site import DATA_CELL, DATA_EDIT
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
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
