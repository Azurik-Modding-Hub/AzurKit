"""The site and its tools: Pyodide's core, pinned by URL, size and sha256
(WEB §6.3), and Chromium for the ``web`` tests, both in the main checkout's
``.tools/`` (git-ignored, shared by every lane); and the site itself
(:func:`site`), the folder a static host serves.

    uv run --locked python scripts/web_tools.py               # fetch both (uv run bootstrap.py does too)
    uv run --locked python scripts/web_tools.py --site DIR    # the site, in DIR (a new folder)

Only the five files the runtime loads are kept (:data:`FILES`). Chromium is
Playwright's headless shell at the revision the locked ``playwright`` names,
in ``.tools/playwright`` (``PLAYWRIGHT_BROWSERS_PATH``), never the user's
cache; its installer (the ``playwright`` package's) runs on the ``node``
on PATH. Stdlib only.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = "314.0.7"
URL = f"https://github.com/pyodide/pyodide/releases/download/{VERSION}/pyodide-core-{VERSION}.tar.bz2"
SIZE = 6_757_104
SHA256 = "2abdcc2e35208af406e07724cffa85bc582ced97e9028383ecf5462541393f95"
FILES = ("pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")
SHELL = "chromium-headless-shell"


def _tools(root: Path) -> Path:
    """``.tools`` in the main checkout of the repository ``root`` is in (a
    lane's is its main checkout's)."""
    common = subprocess.run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent / ".tools"


def pyodide_dir(root: Path = ROOT) -> Path:
    """Where Pyodide's core lives: ``.tools/pyodide-<version>``."""
    return _tools(root) / f"pyodide-{VERSION}"


def missing(root: Path = ROOT) -> list[str]:
    """The core's files that aren't there."""
    folder = pyodide_dir(root)
    return [name for name in FILES if not (folder / name).is_file()]


def fetch(root: Path = ROOT) -> Path:
    """Download the core, check its size and sha256, and keep :data:`FILES`."""
    folder = pyodide_dir(root)
    if not missing(root):
        return folder
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
    return folder


def browsers_dir(root: Path = ROOT) -> Path:
    """``PLAYWRIGHT_BROWSERS_PATH`` for the tests: ``.tools/playwright``."""
    return _tools(root) / "playwright"


def chromium_dir(root: Path = ROOT) -> Path:
    """The headless shell's folder, at the revision the locked playwright names."""
    spec = importlib.util.find_spec("playwright")
    if spec is None or spec.origin is None:
        raise SystemExit("the playwright package isn't installed: uv sync --locked")
    browsers = json.loads((Path(spec.origin).parent / "driver/package/browsers.json").read_text(encoding="utf-8"))
    revision = next(b["revision"] for b in browsers["browsers"] if b["name"] == SHELL)
    return browsers_dir(root) / f"{SHELL.replace('-', '_')}-{revision}"


def chromium_missing(root: Path = ROOT) -> bool:
    return not (chromium_dir(root) / "INSTALLATION_COMPLETE").is_file()


def fetch_chromium(root: Path = ROOT) -> Path:
    """Install the headless shell with playwright's own installer, run on
    the ``node`` on PATH, into :func:`browsers_dir`."""
    if chromium_missing(root):
        spec = importlib.util.find_spec("playwright")
        cli = Path(spec.origin).parent / "driver/package/cli.js"
        subprocess.run(["node", str(cli), "install", "--only-shell", "chromium"], check=True, timeout=900,
                       env=os.environ | {"PLAYWRIGHT_BROWSERS_PATH": str(browsers_dir(root))})
    return chromium_dir(root)


def wheel(out: Path, root: Path = ROOT) -> Path:
    """The checkout's wheel, built into ``out``."""
    subprocess.run(["uv", "build", "--offline", "--quiet", "--wheel", "--out-dir", str(out), str(root)],
                   check=True, capture_output=True, timeout=300)
    (built,) = out.glob("azurkit-*.whl")
    return built


def site(out: Path, root: Path = ROOT, built: Path | None = None) -> Path:
    """The site in the new folder ``out``: ``web/``'s files, Pyodide's
    core in ``pyodide/``, the wheel (``built``, else built now) and
    ``host.json``, which tells the page its engine is the site's and names
    the wheel and its sha256 for the worker's fetch (``integrity``). The
    app's server answers ``host.json`` itself (``azurkit.app``)."""
    shutil.copytree(root / "web", out)
    if lost := missing(root):
        raise SystemExit(f"Pyodide {VERSION} lacks {', '.join(lost)}: run `uv run bootstrap.py`")
    shutil.copytree(pyodide_dir(root), out / "pyodide")
    built = shutil.copy2(built, out) if built else wheel(out, root)
    digest = base64.b64encode(hashlib.sha256(Path(built).read_bytes()).digest()).decode()
    (out / "host.json").write_text(json.dumps({"engine": "site", "wheel": Path(built).name,
                                               "integrity": f"sha256-{digest}"}) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--site", type=Path, metavar="DIR", help="write the site to DIR (a new folder)")
    args = ap.parse_args()
    if args.site:
        print(f"the site: {site(args.site)}")
    else:
        print(f"Pyodide {VERSION}: {fetch()}")
        print(f"Chromium (the web tests'): {fetch_chromium()}")
    sys.exit(0)
