"""The site and its tools: Pyodide's core, pinned by URL, size and sha256
(WEB §6.3), and the browsers the ``web`` tests drive the page in (Chromium
and WebKit, :data:`BROWSERS`), all in the main checkout's ``.tools/``
(git-ignored, shared by every lane); and the site itself (:func:`site`), the
folder a static host serves.

    uv run --locked python scripts/web_tools.py               # fetch them all (uv run bootstrap.py does too)
    uv run --locked python scripts/web_tools.py --site DIR    # the site, in DIR (a new folder)
    uv run --locked python scripts/web_tools.py --site DIR --content CLONE   # with a content repository's files
                                                     # in DIR/content-source/ (Content from: ./content-source/)

Only the five files the runtime loads are kept (:data:`FILES`), and the
wheels of the packages the site loads for a tab that needs them
(:data:`PACKAGES`: numpy, the tracker's maps and icons, Step 4.2c3), each
from Pyodide's CDN at the core's version and checked against the sha256 the
core's ``pyodide-lock.json`` gives it, so they are pinned with it. Each
browser is Playwright's build at the revision the locked ``playwright``
names (Chromium's headless shell; WebKit, Safari's engine), in
``.tools/playwright`` (``PLAYWRIGHT_BROWSERS_PATH``), never the user's
cache; their installer (the ``playwright`` package's) runs on the ``node``
on PATH. Stdlib only, but for a site's content, which ``azurkit``'s content
checks check (:func:`content_files`).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import platform
import py_compile
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
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
# The web tests' engines (Step 4.1d3): each test that takes the ``browser`` fixture runs in both. Each one's name in
# Playwright's browsers.json, and its label.
BROWSERS = {"chromium": ("chromium-headless-shell", "Chromium"), "webkit": ("webkit", "WebKit")}
SHIPPED = "azurkit/tools/randomizer/shipped"   # the checked randomizer database's folder (dbcache.SHIPPED)
UNSERVED = (".html", ".htm", ".shtml", ".xhtml", ".xht", ".svg", ".svgz", ".js", ".mjs", ".xml", ".xsl", ".xslt", ".rss",
            ".atom", ".rdf", ".mml")
"""The suffixes no content file on the site has: its host would serve each
as a page, a script or an XML document the browser renders (where an XHTML
``<script>`` runs) on the site's own origin, outside the page's CSP."""


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
        archive = Path(tmp) / "core.tar.bz2"
        with urllib.request.urlopen(URL, timeout=120) as response, open(archive, "wb") as out:
            shutil.copyfileobj(response, out)
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
        with urllib.request.urlopen(CDN + name, timeout=120) as response:
            data = response.read()
        if (got := hashlib.sha256(data).hexdigest()) != want:
            raise SystemExit(f"{CDN}{name}: sha256 {got[:12]}, not the lock's {want[:12]}")
        part = folder / f"{name}.part"
        part.write_bytes(data)
        part.replace(folder / name)
    return folder


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
    """Install ``engine`` (Chromium's headless shell, or WebKit) with
    playwright's own installer, run on the ``node`` on PATH, into
    :func:`browsers_dir`."""
    if browser_missing(engine, root):
        spec = importlib.util.find_spec("playwright")
        cli = Path(spec.origin).parent / "driver/package/cli.js"
        subprocess.run(["node", str(cli), "install", *(["--only-shell"] if engine == "chromium" else []), engine],
                       check=True, timeout=900, env=os.environ | {"PLAYWRIGHT_BROWSERS_PATH": str(browsers_dir(root))})
    return browser_dir(engine, root)


def wheel(out: Path, root: Path = ROOT) -> Path:
    """The checkout's wheel, built into ``out``, with what lets its engine
    start at once (Step 4.3g): each module's bytecode
    (``__pycache__/<name>.cpython-314.pyc``, unchecked-hash, so Pyodide
    imports it without compiling the source; the ``.py`` stays, for
    tracebacks) and the checked randomizer database
    (:func:`ship_database`, from the wheel's own files), in its RECORD."""
    subprocess.run(["uv", "build", "--offline", "--quiet", "--wheel", "--out-dir", str(out), str(root)],
                   check=True, capture_output=True, timeout=300)
    (built,) = out.glob("azurkit-*.whl")
    with zipfile.ZipFile(built) as zf:
        entries = [(info, zf.read(info)) for info in zf.infolist()]
    added = {}
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


def ship_database(out: Path, path: Path | None = None, planner: bool = True) -> Path:
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
    the wheel and its sha256 for the worker's fetch (``integrity``). The
    app's server answers ``host.json`` itself (``azurkit.app``). With
    ``content`` (a clone of Azurik-Custom-Content, before it is public:
    the page reads only its own origin until Step 4.4's CSP), its
    ``manifest.json`` and each file it lists in ``out/content-source/``,
    which the Characters tab's Content from ``./content-source/`` reads,
    each checked first (:func:`content_files`): a fault names the file and
    writes nothing (D35)."""
    published = {} if content is None else content_files(content)
    shelf = out.resolve() / "content-source"   # out is new, and copytree copies a link's target: no link below it
    if lost := [rel for rel in published if not (shelf / rel).resolve().is_relative_to(shelf)]:
        raise SystemExit(f"content {content}: {lost[0]} would land outside {shelf}")
    shutil.copytree(root / "web", out)
    if lost := missing(root):
        raise SystemExit(f"Pyodide {VERSION} lacks {', '.join(lost)}: run `uv run bootstrap.py`")
    shutil.copytree(pyodide_dir(root), out / "pyodide")
    built = shutil.copy2(built, out) if built else wheel(out, root)
    digest = base64.b64encode(hashlib.sha256(Path(built).read_bytes()).digest()).decode()
    (out / "host.json").write_text(json.dumps({"engine": "site", "wheel": Path(built).name,
                                               "integrity": f"sha256-{digest}"}) + "\n", encoding="utf-8")
    for rel, data in published.items():
        (out / "content-source" / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / "content-source" / rel).write_bytes(data)
    return out


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
    none ends in one of :data:`UNSERVED`. ``SystemExit`` names the first
    fault's file."""
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
            if f["path"].lower().endswith(UNSERVED):
                raise ValueError(f"{f['path']} is a {PurePosixPath(f['path']).suffix} file, which the site's host "
                                 "would serve as a page or a script")
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
    args = ap.parse_args()
    if args.site:
        print(f"the site: {site(args.site, content=args.content)}")
    else:
        print(f"Pyodide {VERSION}: {fetch()}")
        for engine, (_, label) in BROWSERS.items():
            print(f"{label} (the web tests'): {fetch_browser(engine)}")
    sys.exit(0)
