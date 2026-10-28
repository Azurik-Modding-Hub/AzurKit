"""Pyodide for the ``web`` tests: its core, pinned by URL, size and sha256
(WEB §6.3), in the main checkout's ``.tools/`` (git-ignored, shared by every
lane).

    uv run --locked python scripts/web_tools.py     # fetch it (uv run bootstrap.py does too)

Only the five files the runtime loads are kept (:data:`FILES`). Stdlib only.
"""

from __future__ import annotations

import hashlib
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


def pyodide_dir(root: Path = ROOT) -> Path:
    """Where Pyodide's core lives: ``.tools/pyodide-<version>`` in the main
    checkout of the repository ``root`` is in (a lane's is its main
    checkout's)."""
    common = subprocess.run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent / ".tools" / f"pyodide-{VERSION}"


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


if __name__ == "__main__":
    print(f"Pyodide {VERSION}: {fetch()}")
    sys.exit(0)
