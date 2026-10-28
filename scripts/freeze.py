"""Freeze the app (D732): a PyInstaller onedir of ``python -m azurkit``
(``src/azurkit/__main__.py``: the page with no arguments, ``serve``, else the
``azurkit`` command) with the page (``web/``), from this checkout's
environment. On macOS the onedir is a windowed app, ``AzurKit.app``.

    uv run --locked python scripts/freeze.py --dist DIR [--work DIR]

It prints the app's path: ``DIR/AzurKit.app`` on macOS, else the folder
``DIR/AzurKit``. PyInstaller writes only under ``--dist`` and ``--work``
(its cache too, which would otherwise go in the user's Library). The app
leaves out what never ships (:data:`EXCLUDE`: Tk, Unicorn, capstone, zig,
and the standard library's GPL-linked modules). Its icon is PyInstaller's
default, which comes with its bootloader (the Bootloader Exception).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "AzurKit"
BUNDLE_ID = "io.github.azurik-modding-hub.azurkit"
MACOS = sys.platform == "darwin"
EXCLUDE = ("tkinter", "_tkinter", "unicorn", "capstone", "ziglang", "readline", "dbm", "_dbm", "_gdbm")


def freeze(dist: Path, work: Path) -> Path:
    """Build the app in ``dist``, with PyInstaller's files in ``work``; returns its path."""
    os.environ["PYINSTALLER_CONFIG_DIR"] = str(work / "config")
    from PyInstaller.__main__ import run

    run(["--noconfirm", "--clean", "--onedir", "--name", NAME, "--log-level", "WARN",
         *(("--windowed", "--osx-bundle-identifier", BUNDLE_ID) if MACOS else ()),
         "--distpath", str(dist), "--workpath", str(work), "--specpath", str(work),
         "--paths", str(ROOT / "src"), "--collect-data", "azurkit", "--add-data", f"{ROOT / 'web'}{os.pathsep}web",
         *(arg for module in EXCLUDE for arg in ("--exclude-module", module)),
         str(ROOT / "src" / "azurkit" / "__main__.py")])
    if MACOS:
        shutil.rmtree(dist / NAME)   # the onedir the bundle was made from: the bundle holds all of it
        return dist / f"{NAME}.app"
    return dist / NAME


def executable(app: Path) -> Path:
    """The app's program (in an ``.app``, its ``Contents/MacOS``)."""
    return app / "Contents" / "MacOS" / NAME if app.suffix == ".app" else app / NAME


def folders(app: Path) -> list[Path]:
    """The folders that hold the app's libraries and data."""
    if app.suffix == ".app":
        return [app / "Contents" / "Frameworks", app / "Contents" / "Resources"]
    return [app / "_internal"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dist", type=Path, required=True, help="where the app's folder goes")
    ap.add_argument("--work", type=Path, help="PyInstaller's build files (default: a temporary folder)")
    args = ap.parse_args(argv)
    if args.work:
        print(freeze(args.dist.resolve(), args.work.resolve()))
        return 0
    with tempfile.TemporaryDirectory(prefix="azurkit-freeze.") as work:
        print(freeze(args.dist.resolve(), Path(work)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
