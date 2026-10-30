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

import contextlib
import hashlib
import importlib.metadata
import io
import json
import os
import plistlib
import re
import subprocess
import sys
import threading
import time
import types
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import platformdirs
import pytest

from azurkit import __main__ as _entry  # noqa: F401 (the frozen app's entry; fullsuite picks this file for it)
from azurkit import app, cli, sdk
from azurkit.core import gate, iso
from azurkit.tools import mods
from azurkit.tools.randomizer import tracking
from scripts import freeze
from scripts.oracle_sync import ORACLE
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


class Sandbox:
    """Where the frozen app runs: a fresh HOME and TMPDIR, an empty working
    folder, no image variables and the tests' no-window mode (:attr:`env`;
    this process's HOME too). :meth:`left` lists what was written there
    outside platformdirs' folders."""

    def __init__(self, tmp_path: Path, monkeypatch):
        self.home, self.tmp, self.cwd = tmp_path / "home", tmp_path / "tmp", tmp_path / "cwd"
        for folder in (self.home, self.tmp, self.cwd):
            folder.mkdir()
        self.env = {k: v for k, v in os.environ.items() if k not in ("AZURKIT_ISO", "AZURKIT_ISO_EUROPE")}
        self.env |= {"HOME": str(self.home), "TMPDIR": str(self.tmp), app.NO_WINDOW: "1"}
        monkeypatch.setenv("HOME", str(self.home))
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


def _save(page) -> dict | str:
    """Click Save: what the engine saved, or the page's refusal."""
    page.evaluate("() => { azurkit.saved = null; document.querySelector('#save').click(); }")
    return _page.until(page, """() => azurkit.saved || document.querySelector("#status").classList.contains("error")
                                && document.querySelector("#status").textContent""")


def test_the_apps_window_path_exits_at_once_under_the_tests(monkeypatch):
    """No test opens a window or a browser tab on the owner's screen (D839):
    the run sets the no-window mode, under which ``app.main`` serves nothing
    and never reaches the window or the browser (checked in-process first,
    with all three planted to raise), and ``python -m azurkit`` with no
    arguments (the page) exits 1 within seconds. ``serve`` reaches neither
    in any mode: it prints the page's address and stops when its input
    ends."""
    assert os.environ.get(app.NO_WINDOW)

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
    cells (an image's path as a pack or setting name, a ``replace_bytes``)
    is refused by name, the config as it was."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))   # where the app remembers
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
        "setup: an object of ticked, values, xbr, randomizer only, or null": {"ticked": [], "iso": "/a.iso"},
        "setup: ticked holds pack names only": {"ticked": ["/a.iso"]},
        "setup: values holds {pack: {setting: number}} only": {"values": {"fps_unlock": {"target_fps": "/a.iso"}}},
        "setup: xbr holds config.xbr set operations only (Q174)": {"xbr": [
            {"op": "replace_bytes", "file": "gamedata/config.xbr", "offset": 0, "value": "00", "expected": "00"}]},
        "xbr op 1 (set): no key 'expected' (its keys: op, file, table, entity, prop, value)": {
            "xbr": [cell | {"expected": "00"}]},
        "setup: randomizer: not an object of on, seed, settings, obsidian_cost": {"randomizer": {"iso": "/a.iso"}},
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
    after which no ``finally`` runs). Nothing is left where it saved."""
    import webview
    monkeypatch.setenv("HOME", str(tmp_path / "home"))   # where the app remembers the image
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

    server, left = app.serve(), []

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
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    out, release = tmp_path / "out", threading.Event()
    out.mkdir()
    planning, stalled = threading.Event(), threading.Event()

    def image(recipe):   # a long build
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


def test_the_apps_api_builds_the_randomizer_tabs_seed_as_modkit_and_saves_its_spoiler(tmp_path, monkeypatch, usa_iso):
    """From the app's api in-process (Step 4.2c1): ``api/randomizer`` gives
    the Randomizer tab's view (``sdk.randomizer_settings``); ``api/build``
    with the tab's randomizer (seed 2, D144's defaults) and the packs on by
    default makes G3's seed case file by file, its logic verified, with its
    spoiler; ``api/spoiler`` writes that spoiler where the page names, never
    over a file that is there, and ``api/settings_file`` the tab's settings
    file (D144); ``api/setup`` keeps the tab's setup (D915). Step 4.2c2:
    ``api/tracker`` gives Modkit's tracker verdicts at each state, Live's
    kit too, on the build's plan (its report's) and the max plan, and
    ``api/tracked`` remembers the plan and its marks, refusing anything
    else by name."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))   # where the app remembers
    server = app.serve(_page.WEB)
    defaults = sdk.catalog()["randomizer"]["defaults"]
    packs = {name: {} for name, pack in mods.PACKS.items() if pack.default_on}
    golden = json.loads((ORACLE / "rando/tests/goldens/pipelines.json").read_text(encoding="utf-8"))[
        "randomize-full:seed=2,default"]

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
        out = tmp_path / "seed 2 spoiler.txt"
        assert call("api/spoiler", {"out": str(out)}) == {"spoiler": {"out": str(out), "size": len(
            report["spoiler"].encode())}}
        assert out.read_text(encoding="utf-8") == report["spoiler"]
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

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
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
    monkeypatch.setattr(app.pictures.Drawing, "start", lambda self, iso: None)   # the maps aren't drawn: the chips show
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
        assert page.evaluate(f"() => document.querySelector(`#track-level .spot[data-loc='{near}']`).className") == "spot live"
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


def test_the_apps_tracker_draws_a_levels_map_from_the_image_and_lives_gem_takes_remove_its_dots(
        browser, tmp_path, monkeypatch, usa_iso):
    """Step 4.2c3 (D3; R1.43, D928): the app draws the tracker's pictures
    from the image it reads, the first time the Tracker shows (the icons and
    a level here), into platformdirs' cache folder, and the page shows the
    level's map in place of its chips: its tracked spots (a click on one
    marks it), a click on an exit opens the level it leads to, the wheel
    zooms about the pointer and a double click on ground fits it again, and
    a smaller window fits it smaller. With Gems on, each gem spot of the
    floor shown is a dot, the floor buttons (each on one line, its text on
    its radio's middle) and the count say how many are left, the counter
    row the gems taken of all (R1.43's words), and Live (the app's: a
    scripted game taking a gem) takes its dot away. No CSP violation."""
    from azurkit.tools.randomizer.live import game, link

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    doc = _profile("default")
    (tmp_path / "plan.json").write_text(json.dumps(doc), encoding="utf-8")
    first = sdk.tracker({"plan": doc, "gems": True})
    near = sorted(loc for loc, s in first["spots"].items() if s["state"] == "near")[0]
    level = first["spots"][near]["level"]
    monkeypatch.setattr(tracking, "ART_PARTS", ("icons", level))   # a level's map, not every level's (minutes)
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
        page.set_input_files("#track-open", str(tmp_path / "plan.json"))
        _page.until(page, "() => azurkit.tracker.state.view && !azurkit.tracker.state.running", 300)
        _page.until(page, "() => azurkit.tracker.art.status.done.length === 2 && !azurkit.tracker.art.status.drawing"
                          " || azurkit.tracker.art.status.error", 300)
        assert page.evaluate("() => azurkit.tracker.art.status.error") is None
        kept = app.pictures.folder()
        assert sorted(p.name for p in kept.glob("*.part.json")) == ["icons.part.json", f"{level}.part.json"]
        entry = json.loads((kept / f"{level}.part.json").read_text(encoding="utf-8"))["entry"]
        gem |= next(g for g in sorted(entry["gems"], key=lambda g: g["id"]) if g["at"][2] == entry["main"])
        page.evaluate("(level) => document.querySelector(`#track-world .cell[data-level='${level}']`).click()", level)
        _page.until(page, "() => !document.getElementById('track-maps').hidden && azurkit.tracker.map.hits.length")
        assert page.evaluate("() => document.getElementById('track-level').hidden") is True
        place = next(i["at"] for i in entry["items"] + entry["spots"] if i["id"] == near)
        assert place[2] == entry["main"] and "Item spot: reachable now" in page.evaluate(MAP_HITS)
        page.evaluate(MAP_CLICK, place[:2])
        _page.until(page, f"() => !azurkit.tracker.state.running && azurkit.tracker.state.marks.collected?.includes('{near}')")
        exit_ = next(x for x in entry["exits"] if any(p[2] == entry["main"] for p in x["at"]))
        page.evaluate(MAP_CLICK, next(p for p in exit_["at"] if p[2] == entry["main"])[:2])
        assert page.evaluate("() => [azurkit.tracker.state.level, document.getElementById('track-maps').hidden]") == [
            exit_["to"], True]   # its map isn't drawn here: its chips show
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


def test_the_apps_tracker_starts_no_drawing_until_the_typed_path_names_a_file(tmp_path, monkeypatch):
    """Step 4.2c3's looks: the page asks ``api/art`` to draw at each key
    typed in the image's field; a path that names no file yet (a folder, a
    name half typed, a path not yet full) starts no drawing and gives no
    error, so the line shows no raw OS error and no key is lost to a
    drawing of a half path; the whole path starts it."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    started = []
    monkeypatch.setattr(app.pictures.Drawing, "start", lambda self, iso: started.append(iso))
    (whole := tmp_path / "game.iso").touch()
    server = app.serve(_page.WEB)
    try:
        for typed in ("", "/", str(tmp_path), str(tmp_path / "ga"), "game.iso", str(whole)):
            replies = []
            _post(server.url, "api/art", {"iso": typed, "draw": True}, replies)
            assert [(r["drawing"], r["error"]) for r in replies] == [(None, None)], typed
        assert started == [str(whole)]
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

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
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
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    doc = _profile("default")
    (tmp_path / "plan.json").write_text(json.dumps(doc), encoding="utf-8")
    level = next(s["level"] for s in sdk.tracker({"plan": doc, "spoiler": True})["spots"].values() if s["icon"] == "key")
    monkeypatch.setattr(app.pictures.Drawing, "start", lambda self, iso: None)   # the maps aren't drawn: the chips show
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


def test_the_apps_spoiler_never_replaces_the_image_its_build_read(tmp_path, monkeypatch):
    """``api/spoiler`` refuses the image the randomized build read (D36),
    also one outside the data folder that the save dialog chose (its Replace
    confirmed), and leaves it as it was."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    picked = tmp_path / "picked.iso"
    picked.write_bytes(bytes(64))
    monkeypatch.setattr(sdk, "image", lambda recipe: (types.SimpleNamespace(size=64), {"spoiler": "seed 2"}))
    server, replies = app.serve(_page.WEB), []
    try:
        _post(server.url, "api/build", {"iso": str(picked)}, replies)
        server.chosen = picked   # the save dialog's answer
        _post(server.url, "api/spoiler", {"out": str(picked)}, replies)
    finally:
        server.close()
    assert (replies[1], picked.read_bytes()) == (
        {"refused": f"{picked}: it is a vanilla image, which AzurKit never writes over"}, bytes(64))
