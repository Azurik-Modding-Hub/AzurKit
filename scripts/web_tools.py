"""The site and its tools: Pyodide's core, pinned by URL, size and sha256
(WEB §6.3), and the browsers the ``web`` tests drive the page in (Chromium,
WebKit and Firefox, :data:`BROWSERS`), all in the main checkout's ``.tools/``
(git-ignored, shared by every lane); and the site itself (:func:`site`), the
folder a static host serves.

    uv run --locked python scripts/web_tools.py               # fetch them all (uv run bootstrap.py does too)
    uv run --locked python scripts/web_tools.py --site DIR    # the site, in DIR (a new folder)
    uv run --locked python scripts/web_tools.py --site DIR --content CLONE   # with a content repository's files
                                                     # in DIR/content-source/ (Content from: ./content-source/)
    uv run --locked python scripts/web_tools.py --cache   # CI's cache key and folders of what it fetches (cache())

Only the five files the runtime loads are kept (:data:`FILES`), and the
wheels of the packages the site loads for a tab that needs them
(:data:`PACKAGES`: numpy, the tracker's maps and icons, Step 4.2c3), each
from Pyodide's CDN at the core's version and checked against the sha256 the
core's ``pyodide-lock.json`` gives it, so they are pinned with it. Each
browser is Playwright's build at the revision the locked ``playwright``
names (Chromium's headless shell; WebKit, Safari's engine; Firefox, D994), in
``.tools/playwright`` (``PLAYWRIGHT_BROWSERS_PATH``), never the user's
cache; their installer (the ``playwright`` package's) runs on the ``node``
on PATH. Stdlib only, but for a site's content, which ``azurkit``'s content
checks check (:func:`content_files`).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import importlib.metadata
import importlib.util
import json
import os
import platform
import py_compile
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
VERSION = "314.0.7"
URL = f"https://github.com/pyodide/pyodide/releases/download/{VERSION}/pyodide-core-{VERSION}.tar.bz2"
SIZE = 6_757_104
SHA256 = "2abdcc2e35208af406e07724cffa85bc582ced97e9028383ecf5462541393f95"
FILES = ("pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")
PACKAGES = ("numpy",)
CDN = f"https://cdn.jsdelivr.net/pyodide/v{VERSION}/full/"
TRIES = 6
"""How many times :func:`download` asks for a file before it fails by name (Step 4.4ci46; 6 since Step 4.5t)."""
WAIT = 15.0
"""The seconds :func:`download` waits after a failed ask, doubled after each up to :data:`MOST_WAIT`."""
MOST_WAIT = 120.0
"""The longest wait between two asks: 15, 30, 60, 120 and 120 s, 5 min 45 s in all (Step 4.5t: run 42467070736's
jobs lost Pyodide's core as GitHub's release downloads answered 504 for minutes, where 3 asks spanned 15 s)."""
CAP = 600.0
"""The seconds from :func:`download`'s first ask of a file that its waits stay within: no wait starts that would end
past it, so slow asks cost asks, not waits; the last ask, begun by then, may still run past it (each of its reads
waits up to its 120 s timeout)."""
# The web tests' engines (Step 4.1d3; Firefox D994): each test that takes the ``browser`` fixture runs in each. Each
# one's name in Playwright's browsers.json, and its label.
BROWSERS = {"chromium": ("chromium-headless-shell", "Chromium"), "webkit": ("webkit", "WebKit"),
            "firefox": ("firefox", "Firefox")}
SHIPPED = "azurkit/tools/randomizer/shipped"   # the checked randomizer database's folder (dbcache.SHIPPED)
CONTENT_KINDS = (".azkp", ".bin", ".glb", ".gltf", ".json", ".md", ".png", ".wav")
"""The suffixes a content file the site publishes may have, and no other
(none, or any other, is refused by name): the kinds the content repository
holds (a recipe or manifest, a clip, a sound, its notes, a variant's shipped
answer, ``.azkp``, which no type names, so it is served as
``application/octet-stream``) and those it is to hold (a glTF's buffers, a
texture), each of which its host serves as data,
not as a page, a script or an XML document the browser renders (where an
XHTML ``<script>`` runs) on the site's own origin, outside the page's CSP.
A Jekyll build renders any text kind with front matter (a ``.json``,
``.gltf`` or ``.md``) as a page: :func:`site`'s ``.nojekyll`` turns it off."""
CACHE = "AZURKIT_BUILD_CACHE"
"""The variable naming a folder that keeps what :func:`wheel` and
:func:`ship_database` build, by their inputs' sha256 (:func:`kept`): the
gate's run and its flake stage share one (``scripts/fullsuite.py``), so the
stage's slowed runs copy the gate's wheel and database, never build them
again slowed (Step 4.4dx4). Unset: each call builds."""
WORKER = "sw.js"   # the site's service worker (D1013): web/sw.js, with the release site() lists in it
RELEASE_LINE = "const RELEASE = null;"
"""The line of ``web/sw.js`` :func:`site` writes the release into: the
checkout's (the app's page's, which never registers it) lists none."""
UNLISTED = (WORKER, ".nojekyll")
"""What a site serves outside its release, with ``content-source/``: the
worker itself (a browser fetches it to look for an update), the empty
``.nojekyll`` and the content repository's files, read from the network
(each Install checks its own)."""
CSP = re.compile(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">')


def _tools(root: Path) -> Path:
    """``.tools`` in the main checkout of the repository ``root`` is in (a
    lane's is its main checkout's)."""
    common = subprocess.run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent / ".tools"


def pyodide_dir(root: Path = ROOT) -> Path:
    """Where Pyodide's core lives: ``.tools/pyodide-<version>``."""
    return _tools(root) / f"pyodide-{VERSION}"


def wheels(root: Path = ROOT) -> dict[str, str]:
    """``{file name: sha256}`` of :data:`PACKAGES`' wheels, as the core's lock names them."""
    lock = json.loads((pyodide_dir(root) / "pyodide-lock.json").read_text(encoding="utf-8"))["packages"]
    return {lock[name]["file_name"]: lock[name]["sha256"] for name in PACKAGES}


def missing(root: Path = ROOT) -> list[str]:
    """The core's files and :data:`PACKAGES`' wheels that aren't there."""
    folder = pyodide_dir(root)
    lost = [name for name in FILES if not (folder / name).is_file()]
    return lost or [name for name in wheels(root) if not (folder / name).is_file()]


def fetch(root: Path = ROOT) -> Path:
    """Download the core, check its size and sha256, and keep :data:`FILES`."""
    folder = pyodide_dir(root)
    if not missing(root):
        return folder
    if any(name not in FILES for name in missing(root)):   # the core is there: only a package's wheel is missing
        return fetch_wheels(root)
    with tempfile.TemporaryDirectory(prefix="azurkit-pyodide.") as tmp:
        archive = download(URL, Path(tmp) / "core.tar.bz2")
        with open(archive, "rb") as f:
            sha = hashlib.file_digest(f, "sha256").hexdigest()
        if (archive.stat().st_size, sha) != (SIZE, SHA256):
            raise SystemExit(f"{URL}: {archive.stat().st_size:,} B, sha256 {sha[:12]}; want {SIZE:,} B, "
                             f"{SHA256[:12]}")
        unpacked = Path(tmp) / "core"
        with tarfile.open(archive, "r:bz2") as tar:
            members = {Path(m.name).name: m for m in tar.getmembers() if m.isfile() and Path(m.name).name in FILES}
            if sorted(members) != sorted(FILES):
                raise SystemExit(f"{URL}: it lacks {sorted(set(FILES) - set(members))}")
            tar.extractall(unpacked, members=list(members.values()), filter="data")
        folder.mkdir(parents=True, exist_ok=True)
        for name, member in members.items():
            shutil.move(unpacked / member.name, folder / name)
    return fetch_wheels(root)


def fetch_wheels(root: Path = ROOT) -> Path:
    """Download each of :data:`PACKAGES`' wheels that isn't there, checked against the core's lock."""
    folder = pyodide_dir(root)
    for name, want in wheels(root).items():
        if (folder / name).is_file():
            continue
        part = download(CDN + name, folder / f"{name}.part")
        with open(part, "rb") as f:
            got = hashlib.file_digest(f, "sha256").hexdigest()
        if got != want:
            part.unlink()
            raise SystemExit(f"{CDN}{name}: sha256 {got[:12]}, not the lock's {want[:12]}")
        part.replace(folder / name)
    return folder


def download(url: str, out: Path, tries: int = TRIES) -> Path:
    """``url``'s body, whole, in ``out`` (Step 4.4ci46: CI's setup lost a job
    to one dropped answer). A dropped or slow answer (a connection refused,
    reset or timed out, a body short of its ``Content-Length``, a 5xx) is
    asked again, :data:`WAIT` s later, then twice that each time up to
    :data:`MOST_WAIT`, so the asks span minutes, as an outage of GitHub's
    release downloads does (Step 4.5t), up to ``tries`` asks or a wait that
    would end past :data:`CAP` s from the first; each failed ask says when
    the next comes and the bounds. Past them, or at once on another answer
    (a 404), it fails naming the URL, the asks, their time and the last
    error, and leaves nothing in ``out``."""
    start = time.monotonic()
    for ask in range(1, tries + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as response, open(out, "wb") as f:
                shutil.copyfileobj(response, f)
                length, got = response.headers.get("Content-Length"), f.tell()
            if length is not None and got != int(length):
                raise ConnectionError(f"the answer ended at {got:,} of its {int(length):,} B")
            return out
        except urllib.error.HTTPError as error:
            out.unlink(missing_ok=True)
            if error.code < 500:
                raise SystemExit(f"{url}: {error.code} {error.reason}") from error
            last: Exception = error
        except (OSError, http.client.HTTPException) as error:   # a cut body under read() is an IncompleteRead
            out.unlink(missing_ok=True)
            last = error
        wait, spent = min(WAIT * 2 ** (ask - 1), MOST_WAIT), time.monotonic() - start
        if ask == tries or spent + wait > CAP:
            break
        print(f"{url}: ask {ask} of {tries} failed ({last}); again in {wait:g} s ({tries} asks, no wait past "
              f"{CAP:g} s)", file=sys.stderr)
        time.sleep(wait)
    capped = f", and a {wait:g} s wait would pass the {CAP:g} s cap" if ask < tries else ""
    raise SystemExit(f"{url}: {ask} asks failed in {spent:.0f} s{capped}; the last: {last}")


def browsers_dir(root: Path = ROOT) -> Path:
    """``PLAYWRIGHT_BROWSERS_PATH`` for the tests: ``.tools/playwright``."""
    return _tools(root) / "playwright"


def _mac_host() -> str:
    """Playwright's host key on macOS 11 and later (its ``hostPlatform.ts``):
    ``mac<major>``, the major ``Darwin - 9`` up to Darwin 24 and
    ``min(Darwin + 1, 26)`` from Darwin 25, with ``-arm64`` on Apple silicon."""
    darwin = int(platform.release().split(".")[0])
    major = darwin - 9 if darwin < 25 else min(darwin + 1, 26)
    return f"mac{major}{'-arm64' if platform.machine() == 'arm64' else ''}"


def browser_dir(engine: str, root: Path = ROOT) -> Path:
    """The folder playwright installs ``engine`` (a :data:`BROWSERS` key) in
    on this machine: ``<name>-<revision>``, or for a host its
    ``revisionOverrides`` names (macOS 14's WebKit)
    ``<name>_<host>_special-<revision>``, dashes in the name made ``_``."""
    spec = importlib.util.find_spec("playwright")
    if spec is None or spec.origin is None:
        raise SystemExit("the playwright package isn't installed: uv sync --locked")
    browsers = json.loads((Path(spec.origin).parent / "driver/package/browsers.json").read_text(encoding="utf-8"))
    name = BROWSERS[engine][0]
    entry = next(b for b in browsers["browsers"] if b["name"] == name)
    host = _mac_host() if sys.platform == "darwin" else ""
    override = entry.get("revisionOverrides", {}).get(host)
    prefix = f"{name}_{host}_special" if override else name
    return browsers_dir(root) / f"{prefix.replace('-', '_')}-{override or entry['revision']}"


def browser_missing(engine: str, root: Path = ROOT) -> bool:
    return not (browser_dir(engine, root) / "INSTALLATION_COMPLETE").is_file()


def fetch_browser(engine: str, root: Path = ROOT) -> Path:
    """Install ``engine`` (Chromium's headless shell, WebKit or Firefox) with
    playwright's own installer, run on the ``node`` on PATH, into
    :func:`browsers_dir`."""
    if browser_missing(engine, root):
        spec = importlib.util.find_spec("playwright")
        cli = Path(spec.origin).parent / "driver/package/cli.js"
        subprocess.run(["node", str(cli), "install", *install_args(engine)], check=True, timeout=900,
                       env=os.environ | {"PLAYWRIGHT_BROWSERS_PATH": str(browsers_dir(root))})
    return browser_dir(engine, root)


def install_args(engine: str) -> list[str]:
    """``playwright install``'s arguments for ``engine``: Chromium's headless shell alone."""
    return [*(["--only-shell"] if engine == "chromium" else []), engine]


def cache(root: Path = ROOT) -> dict[str, str]:
    """CI's cache of what :func:`fetch` and :func:`fetch_browser` keep
    (Step 4.5t: run 42467070736's jobs failed as GitHub's release downloads
    answered Pyodide's core 504 for minutes; ``tests.yml`` restores it before
    this script runs and saves it after, so a run fetches nothing a run on its
    OS kept): its ``key``, from the exact versions (Pyodide's and its
    :data:`PACKAGES`, the locked playwright's, which names each browser's
    revision), the host (Playwright's builds differ by macOS release and
    Linux distribution, and by CPU) and a short digest of what is kept
    (:data:`FILES`, each of :data:`BROWSERS`' names and its
    :func:`install_args`, Chromium's ``--only-shell`` too), so an edit to what is kept
    moves it with no version moved, and its two folders, ``pyodide`` and
    ``browsers``, as paths from ``root``, POSIX style. Nothing of the game's
    is ever in them."""
    if sys.platform == "darwin":
        host = _mac_host().removesuffix("-arm64")
    elif sys.platform == "linux":
        release = platform.freedesktop_os_release()
        host = f"{release['ID']}{release.get('VERSION_ID', '')}"
    else:
        host = sys.platform
    kept = digest(repr((FILES, [(name, install_args(engine)) for engine, (name, _) in BROWSERS.items()])))[:8]
    versions = (f"pyodide{VERSION}", *PACKAGES, f"playwright{importlib.metadata.version('playwright')}", f"kept{kept}")
    return {"key": "-".join(("web-tools", host, platform.machine(), *versions)),
            "pyodide": Path(os.path.relpath(pyodide_dir(root), root)).as_posix(),
            "browsers": Path(os.path.relpath(browsers_dir(root), root)).as_posix()}


def digest(*parts: Path | str) -> str:
    """The sha256 (32 hex digits) of ``parts``: a folder's files (each one's
    path under it and bytes; ``__pycache__`` left out), a file's bytes (a
    missing one its name alone), a string as it is."""
    h = hashlib.sha256()
    for part in parts:
        if isinstance(part, str):
            h.update(b"s\0" + part.encode() + b"\0")
        elif part.is_dir():
            for path in sorted(part.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    h.update(f"f\0{path.relative_to(part).as_posix()}\0".encode())
                    h.update(hashlib.sha256(path.read_bytes()).digest())
        else:
            h.update(f"p\0{part.name}\0".encode())
            h.update(hashlib.sha256(part.read_bytes()).digest() if part.is_file() else b"")
    return h.hexdigest()[:32]


def kept(kind: str, key: str, out: Path, build) -> Path:
    """``build(out)``'s file, built once a ``key`` while :data:`CACHE` names
    a folder: the first call builds it, under a lock its other callers wait
    on, and keeps a copy in ``<folder>/<kind>-<key>/``; each later one copies
    that into ``out``. Unset, it builds."""
    if not (folder := os.environ.get(CACHE)):
        return build(out)
    shelf = Path(folder) / f"{kind}-{key}"
    shelf.mkdir(parents=True, exist_ok=True)
    with open(shelf / ".lock", "a", encoding="utf-8") as lock:
        if os.name == "posix":   # elsewhere two first calls both build: the copy's replace is atomic
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        if not (have := [p for p in shelf.iterdir() if not p.name.startswith(".")]):
            made = build(out)
            shutil.copyfile(made, part := shelf / f".{made.name}.part")
            os.replace(part, shelf / made.name)
            return made
    out.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copyfile(have[0], out / have[0].name))


def wheel(out: Path, root: Path = ROOT) -> Path:
    """:func:`_wheel`, kept by its inputs (:func:`kept`): the files under
    ``src/``, those the wheel's metadata names, this module and the commit
    it stamps."""
    import azurkit
    key = digest(root / "src", *(root / name for name in ("pyproject.toml", "README.md", "LICENSE", "NOTICE.md")),
                 Path(__file__), azurkit.head(root) or "", sys.version)
    return kept("wheel", key, out, lambda out: _wheel(out, root))


def _wheel(out: Path, root: Path = ROOT) -> Path:
    """The checkout's wheel, built into ``out``, with what lets its engine
    start at once (Step 4.3g): each module's bytecode
    (``__pycache__/<name>.cpython-314.pyc``, unchecked-hash, so Pyodide
    imports it without compiling the source; the ``.py`` stays, for
    tracebacks), the checked randomizer database
    (:func:`ship_database`, from the wheel's own files) and, from a git
    checkout, the commit it was built from (``azurkit.STAMP``, which About
    shows: ``azurkit.commit``), in its RECORD."""
    import azurkit
    subprocess.run(["uv", "build", "--offline", "--quiet", "--wheel", "--out-dir", str(out), str(root)],
                   check=True, capture_output=True, timeout=300)
    (built,) = out.glob("azurkit-*.whl")
    with zipfile.ZipFile(built) as zf:
        entries = [(info, zf.read(info)) for info in zf.infolist()]
    added = {} if (head := azurkit.head(root)) is None else {f"azurkit/{azurkit.STAMP}": f"{head}\n".encode()}
    with tempfile.TemporaryDirectory(prefix="azurkit-wheel.") as tmp:
        for info, data in entries:
            if not info.is_dir():
                (Path(tmp) / info.filename).parent.mkdir(parents=True, exist_ok=True)
                (Path(tmp) / info.filename).write_bytes(data)
        shipped = ship_database(Path(tmp) / SHIPPED, Path(tmp))
        added[f"{SHIPPED}/{shipped.name}"] = shipped.read_bytes()
        for info, _ in entries:
            if info.filename.endswith(".py"):
                folder, _, name = info.filename.rpartition("/")
                pyc = Path(tmp) / "module.pyc"
                py_compile.compile(str(Path(tmp) / info.filename), cfile=str(pyc), dfile=info.filename, doraise=True,
                                   invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
                added[f"{folder}/__pycache__/{name[:-3]}.{sys.implementation.cache_tag}.pyc"] = pyc.read_bytes()
    record = next(info.filename for info, _ in entries if info.filename.endswith(".dist-info/RECORD"))
    meta = record.rpartition("/")[0] + "/"
    with zipfile.ZipFile(built, "w") as zf:
        for info, data in entries:
            if not info.filename.startswith(meta):
                zf.writestr(info, data)
        for name, data in added.items():
            new = zipfile.ZipInfo(name, date_time=entries[0][0].date_time)
            new.compress_type, new.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            zf.writestr(new, data)
        for info, data in entries:
            if info.filename.startswith(meta) and info.filename != record:
                zf.writestr(info, data)
            elif info.filename == record:
                lines = [line for line in data.decode().splitlines() if line != f"{record},,"]
                lines += [f"{name},sha256={base64.urlsafe_b64encode(hashlib.sha256(blob).digest()).rstrip(b'=').decode()}"
                          f",{len(blob)}" for name, blob in added.items()]
                zf.writestr(info, "\n".join([*lines, f"{record},,", ""]))
    return built


def install(wheel: Path, venv: Path, root: Path = ROOT, env: dict[str, str] | None = None) -> str:
    """The checkout's ``wheel`` installed in a new venv at ``venv`` as a
    player's install has it, with only its declared dependencies, at the
    versions ``uv.lock`` pins: those (the project's own, no group, from
    ``uv export``'s ``pylock.toml``), then the wheel, which resolves against
    them. Offline, from the wheels ``uv sync --locked`` left in uv's cache: a
    locked sync fetches no index pages, so an install that resolves from the
    index finds none on a fresh runner (CI, Step 4.4ci2). The venv's python;
    ``RuntimeError`` gives uv's own words when a step fails."""
    def uv(*argv: str) -> None:
        done = subprocess.run(["uv", *argv], capture_output=True, text=True, timeout=300, env=env)
        if done.returncode:
            raise RuntimeError(f"uv {' '.join(argv[:2])}: {done.stderr.strip()[-2000:]}")
    uv("venv", "--quiet", "--python", "3.14", str(venv))
    python = str(venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    with tempfile.TemporaryDirectory(prefix="azurkit-lock.") as tmp:
        lock = Path(tmp) / "pylock.toml"
        uv("export", "--project", str(root), "--frozen", "--format", "pylock.toml", "--no-default-groups",
           "--no-emit-project", "--quiet", "-o", str(lock))
        uv("pip", "install", "--offline", "--quiet", "--python", python, "-r", str(lock))
    uv("pip", "install", "--offline", "--quiet", "--python", python, str(wheel))
    return python


def ship_database(out: Path, path: Path | None = None, planner: bool = True) -> Path:
    """:func:`_ship_database`, kept by its inputs (:func:`kept`): the files
    of the package it imports, ``planner`` and this module."""
    package = path / "azurkit" if path is not None else Path(importlib.util.find_spec("azurkit").origin).parent
    key = digest(package, f"planner={planner}", Path(__file__), sys.version)
    return kept("database", key, out, lambda out: _ship_database(out, path, planner))


def _ship_database(out: Path, path: Path | None = None, planner: bool = True) -> Path:
    """The checked randomizer database (``dbcache.ship``) written into the
    folder ``out`` by a child Python under PYTHONHASHSEED=0 (never ``-I``,
    which ignores it), importing the package from ``path`` (an unpacked
    wheel, whose files key it) or else this environment's; keyed by the
    data alone when not ``planner`` (the frozen app's key). Its file."""
    out.mkdir(parents=True, exist_ok=True)
    env = os.environ | {"PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}
    if path is not None:
        env["PYTHONPATH"] = os.pathsep.join([str(path), *filter(None, [os.environ.get("PYTHONPATH")])])
    code = ("import sys; from pathlib import Path; from azurkit.tools.randomizer import dbcache; "
            f"print(dbcache.ship(Path(sys.argv[1]){'' if planner else ', None'}))")
    done = subprocess.run([sys.executable, "-P", "-c", code, str(out)], env=env, stdout=subprocess.PIPE, text=True,
                          check=True, timeout=900)
    return Path(done.stdout.strip())


def site(out: Path, root: Path = ROOT, built: Path | None = None, content: Path | None = None) -> Path:
    """The site in the new folder ``out``: ``web/``'s files, Pyodide's
    core in ``pyodide/``, the wheel (``built``, else built now) and
    ``host.json``, which tells the page its engine is the site's and names
    the wheel and its sha256 for the worker's fetch (``integrity``), and an
    empty ``.nojekyll``, so a GitHub Pages build serves each file as it is
    and makes no page of one with front matter (a content ``.json``,
    ``.gltf`` or ``.md``). The app's server answers ``host.json`` itself
    (``azurkit.app``). With
    ``content`` (a clone of Azurik-Custom-Content: the perf's and the
    tests' copy; the released site reads the repository from GitHub, any
    https one the player sets, D1135), its
    ``manifest.json`` and each file it lists in ``out/content-source/``,
    which the Characters tab's Content from ``./content-source/`` reads,
    each checked first (:func:`content_files`): a fault names the file and
    writes nothing (D35). Its ``sw.js`` is ``web/sw.js`` with the site's
    :func:`release` on its :data:`RELEASE_LINE`, and the page's CSP, from
    ``web/index.html``, in it, each checked first too. Each file is new here, with today's time, not its source's: the
    site is often in a temp folder, and macOS's daily sweep (dirhelper, 03:35) deletes what looks 3 days old there, which
    would be Pyodide's core, its release's times, under a page still being served (run 41372636477's 42 failures)."""
    published = {} if content is None else content_files(content)
    worker, page = root / "web" / WORKER, root / "web" / "index.html"
    if (lines := (worker := worker.read_text(encoding="utf-8")).count(RELEASE_LINE)) != 1:
        raise SystemExit(f"{root / 'web' / WORKER}: holds {lines} lines {RELEASE_LINE!r}, not one")
    if len(policy := CSP.findall(page.read_text(encoding="utf-8"))) != 1:
        raise SystemExit(f"{page}: holds {len(policy)} Content-Security-Policy metas, not one")
    shelf = out.resolve() / "content-source"   # out is new, and copytree copies a link's target: no link below it
    if lost := [rel for rel in published if not (shelf / rel).resolve().is_relative_to(shelf)]:
        raise SystemExit(f"content {content}: {lost[0]} would land outside {shelf}")
    shutil.copytree(root / "web", out, copy_function=shutil.copy)
    if lost := missing(root):
        raise SystemExit(f"Pyodide {VERSION} lacks {', '.join(lost)}: run `uv run bootstrap.py`")
    shutil.copytree(pyodide_dir(root), out / "pyodide", copy_function=shutil.copy)
    with tempfile.TemporaryDirectory(prefix="azurkit-site.") as tmp:   # not in out: uv build leaves a .gitignore beside
        built = shutil.copy(built or wheel(Path(tmp), root), out)      # the wheel, and Pages' artifact drops dotfiles
    digest = base64.b64encode(hashlib.sha256(Path(built).read_bytes()).digest()).decode()
    (out / "host.json").write_text(json.dumps({"engine": "site", "wheel": Path(built).name,
                                               "integrity": f"sha256-{digest}"}) + "\n", encoding="utf-8", newline="\n")
    (out / ".nojekyll").write_bytes(b"")
    for rel, data in published.items():
        (out / "content-source" / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / "content-source" / rel).write_bytes(data)
    listed = json.dumps(release(out, policy[0]), sort_keys=True)
    (out / WORKER).write_text(worker.replace(RELEASE_LINE, f"const RELEASE = {listed};"), encoding="utf-8", newline="\n")
    return out


def release(out: Path, csp: str) -> dict:
    """The release of the site in ``out`` (``web/sw.js`` keeps it whole):
    ``files``, each file the site serves with it (all but
    :data:`UNLISTED` and ``content-source/``) by its path,
    ``{"sha256", "size"}``; ``csp``, the
    page's policy, which the worker sends as a header; and ``name``, the
    first 16 hex digits of the sha256 of ``files``' canonical JSON, so a
    release is new exactly when one of its files is."""
    files = {}
    for path in sorted(p for p in out.rglob("*") if p.is_file()):
        if (rel := path.relative_to(out).as_posix()) not in UNLISTED and not rel.startswith("content-source/"):
            data = path.read_bytes()
            files[rel] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    name = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    return {"name": name, "csp": csp, "files": files}


def content_files(clone: Path) -> dict[str, bytes]:
    """What :func:`site` publishes of the content clone ``clone``, each
    path's bytes, all read and checked before the site's first file is
    written: ``manifest.json`` passes ``content.check`` and each of its
    entries ``content.verify`` (each file's size and sha256 as listed, no
    disc image, a built-in variant's recipe the engine's), as an Install
    checks them; each listed path is a plain path (no trailing ``/``, no
    ``.`` part: what is checked is what is published); as the content
    repository's ``scripts/check.py`` holds, it has no ``:`` and is a
    regular file reached through
    real folders (``lstat``: a link anywhere on it is never followed); and
    its suffix is one of :data:`CONTENT_KINDS`, exactly. ``SystemExit``
    names the first fault's file."""
    from azurkit.tools.characters import content

    def read(rel: str, most: int) -> bytes:
        at, parts = clone, PurePosixPath(rel).parts
        for k, part in enumerate(parts, 1):
            at, last = at / part, k == len(parts)
            what = rel if last else f"{rel}'s folder {'/'.join(parts[:k])}"
            try:
                mode = os.lstat(at).st_mode
            except OSError:
                raise SystemExit(f"content {clone}: {what} is missing") from None
            if stat.S_ISLNK(mode):
                raise SystemExit(f"content {clone}: {what} is a link (never followed)")
            if not (stat.S_ISREG if last else stat.S_ISDIR)(mode):
                raise SystemExit(f"content {clone}: {what} is no regular {'file' if last else 'folder'}")
        if (size := os.lstat(at).st_size) > most:
            raise SystemExit(f"content {clone}: {rel} is {size:,} bytes, more than the {most:,} it may hold")
        return at.read_bytes()

    raw = read(content.MANIFEST, content.MAX_MANIFEST)
    try:
        manifest = content.check(raw)
        files = {}
        for f in (f for e in manifest["entries"] for f in e["files"]):
            if (plain := PurePosixPath(f["path"]).as_posix()) != f["path"]:
                raise ValueError(f"{f['path']} isn't a plain path: it would be published as {plain}")
            if ":" in f["path"]:
                raise ValueError(f"{f['path']} holds a ':', which no content path does")
            if (kind := PurePosixPath(f["path"]).suffix) not in CONTENT_KINDS:
                raise ValueError(f"{f['path']} is {f'a {kind}' if kind else 'a suffix-less'} file: the site publishes "
                                 f"only {', '.join(CONTENT_KINDS)} files")
            files[f["path"]] = read(f["path"], f["size"])
        for e in manifest["entries"]:
            content.verify(manifest, e["id"], files)
    except ValueError as exc:
        raise SystemExit(f"content {clone}: {exc}") from None
    return {content.MANIFEST: raw, **files}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--site", type=Path, metavar="DIR", help="write the site to DIR (a new folder)")
    ap.add_argument("--content", type=Path, metavar="CLONE",
                    help="with --site: a content repository's files in DIR/content-source/")
    ap.add_argument("--cache", action="store_true",
                    help="print CI's cache key and folders of what it fetches, as $GITHUB_OUTPUT's lines")
    args = ap.parse_args()
    if args.cache:
        sys.stdout.reconfigure(newline="\n")   # Windows' runner too: no \r in a key or a path
        print("".join(f"{name}={value}\n" for name, value in cache().items()), end="")
    elif args.site:
        print(f"the site: {site(args.site, content=args.content)}")
    else:
        print(f"Pyodide {VERSION}: {fetch()}")
        for engine, (_, label) in BROWSERS.items():
            print(f"{label} (the web tests'): {fetch_browser(engine)}")
    sys.exit(0)
