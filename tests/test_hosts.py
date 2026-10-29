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
from scripts import freeze
from tests import _g1, _page
from tests._xiso import fill, image

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
    cells, anywhere in it (an image's path, a ``replace_bytes``), is refused
    by name, the config as it was."""
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
        "setup: an object of ticked, values, xbr only, or null": {"ticked": [], "iso": "/a.iso"},
        "setup: ticked holds pack names only": {"ticked": ["/a.iso"]},
        "setup: values holds {pack: {setting: number}} only": {"values": {"fps_unlock": {"target_fps": "/a.iso"}}},
        "setup: xbr holds config.xbr set operations only (Q174)": {"xbr": [
            {"op": "replace_bytes", "file": "gamedata/config.xbr", "offset": 0, "value": "00", "expected": "00"}]},
        "xbr op 1 (set): no key 'expected' (its keys: op, file, table, entity, prop, value)": {
            "xbr": [cell | {"expected": "00"}]},
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


def _post(url: str, call: str, body: dict, replies: list) -> None:
    """POST ``body`` to the engine's ``call`` (``api/save``, say) from the
    page at ``url`` (its token in the query); its reply goes in ``replies``."""
    host, query = urllib.parse.urlsplit(url).netloc, f"?{urllib.parse.urlsplit(url).query}"
    request = urllib.request.Request(f"http://{host}/{call}{query}", json.dumps(body).encode(),
                                     {"Origin": f"http://{host}", "Content-Type": "application/json"})
    with contextlib.suppress(OSError), urllib.request.urlopen(request, timeout=120) as reply:
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
