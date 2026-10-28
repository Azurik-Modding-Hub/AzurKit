"""Both hosts (Step 4.1b2): the site runs the wheel under Pyodide, and the
app (D732) is a PyInstaller onedir (``scripts/freeze.py``). The gate,
``azurkit verify``, gives the same verdicts on CPython, under Pyodide 314 on
Node and from the frozen app. The app runs read-only with a fresh HOME,
writes nothing into itself or outside platformdirs' folders, and holds no
Unicorn, zig, capstone or GPL code. Its page server answers only on
127.0.0.1 and only to its launch's token."""

from __future__ import annotations

import contextlib
import importlib.metadata
import io
import os
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import platformdirs
import pytest

from azurkit import __main__ as _entry  # noqa: F401 (the frozen app's entry; fullsuite picks this file for it)
from azurkit import app, cli
from scripts import freeze
from tests._xiso import fill, image

ROOT = Path(__file__).resolve().parent.parent
NEVER = ("unicorn", "capstone", "zig", "tkinter", "_tkinter", "_gdbm", "_dbm")
OURS = {"azurkit", "__main__", "web"}
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


def _owners(app_dir: Path) -> dict[str, str]:
    """Each top-level name the app holds (a module in its archives, or a
    file or folder in ``_internal/``) and whose code it is, with its licence."""
    from PyInstaller.archive.readers import CArchiveReader
    pkg = CArchiveReader(str(app_dir / freeze.NAME))
    names = {name.split(".")[0] for name in pkg.open_embedded_archive("PYZ.pyz").toc} | set(pkg.toc) - {"PYZ.pyz"}
    with zipfile.ZipFile(app_dir / "_internal" / "base_library.zip") as zf:
        names |= {name.split("/")[0].removesuffix(".pyc") for name in zf.namelist()}
    names |= {path.name for path in (app_dir / "_internal").iterdir()} - {"base_library.zip"}
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


def test_the_frozen_app_runs_read_only_and_gives_the_same_verdicts(tmp_path, verify_argv, verdicts, monkeypatch):
    """The onedir holds no Unicorn, zig, capstone or GPL code (each name in
    it is Python's, PyInstaller's runtime, AzurKit's or a distribution's
    whose licence isn't GPL; the runtime's readline is editline). Run
    read-only, with a fresh HOME and TMPDIR from an empty folder and the
    tests' no-window mode, its window path exits 1 at once, and it gives
    CPython's verdicts, finds the images' folder through platformdirs under
    that HOME, and leaves itself, that folder, HOME and TMPDIR as they were
    but for platformdirs' folders."""
    built = subprocess.run([sys.executable, str(ROOT / "scripts" / "freeze.py"), "--dist", str(tmp_path / "dist"),
                            "--work", str(tmp_path / "work")], capture_output=True, text=True, timeout=900)
    assert built.returncode == 0, built.stderr[-3000:]
    app_dir = Path(built.stdout.splitlines()[-1])
    owners = _owners(app_dir)
    assert [name for name in owners if name.lower().startswith(NEVER)] == []
    assert {name: owner for name, owner in owners.items() if "GPL" in owner or owner == "unknown"} == {}
    assert "readline" not in sys.builtin_module_names or __import__("readline").backend == "editline"

    home, tmp, cwd = tmp_path / "home", tmp_path / "tmp", tmp_path / "cwd"
    for folder in (home, tmp, cwd):
        folder.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("AZURKIT_ISO", "AZURKIT_ISO_EUROPE")}
    env |= {"HOME": str(home), "TMPDIR": str(tmp), app.NO_WINDOW: "1"}

    def frozen(*argv: str, timeout: int = 300) -> dict:
        done = subprocess.run([str(app_dir / freeze.NAME), *argv], capture_output=True, text=True, env=env, cwd=cwd,
                              timeout=timeout)
        return {"code": done.returncode, "stdout": done.stdout, "stderr": done.stderr}

    writable = [p for p in [app_dir, *app_dir.rglob("*")] if not p.is_symlink()]
    for path in writable:
        path.chmod(path.stat().st_mode & ~0o222)
    before = _tree(app_dir)
    try:
        assert frozen(timeout=30) == {"code": 1, "stdout": "", "stderr": WINDOW_REFUSED}   # the window path
        assert frozen(*verify_argv) == verdicts
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.delenv("AZURKIT_ISO", raising=False)
        monkeypatch.delenv("AZURKIT_ISO_EUROPE", raising=False)
        dirs = platformdirs.PlatformDirs("AzurKit", appauthor=False)
        none = cpython("verify")
        assert none["code"] == 1 and f"put it at {dirs.user_data_path / 'usa.iso'}\n" in none["stderr"]
        assert dirs.user_data_path.is_relative_to(home)
        assert frozen("verify") == none
        assert _tree(app_dir) == before
    finally:
        for path in writable:
            path.chmod(path.stat().st_mode | 0o200)
    kept = [Path(getattr(dirs, f"user_{kind}_dir")) for kind in ("data", "config", "cache", "state", "log")]
    assert list(cwd.iterdir()) == []
    assert [p for p in [*home.rglob("*"), *tmp.rglob("*")] if p.is_file() and not any(map(p.is_relative_to, kept))] == []


def test_the_apps_window_path_exits_at_once_under_the_tests(monkeypatch):
    """No test opens a window or a browser tab on the owner's screen (D839):
    the run sets the no-window mode, under which ``python -m azurkit`` with
    no arguments (the page) exits 1 within seconds, and ``app.main`` serves
    nothing and never reaches the window or the browser."""
    assert os.environ.get(app.NO_WINDOW)
    done = subprocess.run([sys.executable, "-m", "azurkit"], capture_output=True, text=True, timeout=30)
    assert (done.returncode, done.stdout, done.stderr) == (1, "", WINDOW_REFUSED)

    def opened(*args, **kwargs):
        raise AssertionError("the window path ran under the tests")
    for name in ("serve", "_window"):
        monkeypatch.setattr(app, name, opened)
    monkeypatch.setattr(app.webbrowser, "open", opened)
    assert app.main() == 1


def test_the_apps_page_answers_only_its_launchs_token_on_127_0_0_1(tmp_path):
    """The first request carries the token in its URL and gets it back as
    a cookie; later ones carry the cookie, which a second launch's leaves
    alone. Without either, with another host named, or outside the page's
    folder, the server refuses."""
    page = tmp_path / "page"
    page.mkdir()
    (page / "index.html").write_text("<title>t</title>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("s", encoding="utf-8")
    server, second = app.serve(page), app.serve(page)

    def get(path: str, to: app.Server | None = None, **headers: str) -> tuple[int, str | None, bytes]:
        request = urllib.request.Request(f"http://{(to or server).host}{path}", headers=headers)
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
    finally:
        server.close()
        second.close()
