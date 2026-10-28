"""Freeze the app (D732): a PyInstaller onedir of ``python -m azurkit``
(``src/azurkit/__main__.py``: the ``azurkit`` command with arguments, the
page with none) with the page (``web/``), from this checkout's environment.

    uv run --locked python scripts/freeze.py --dist DIR [--work DIR]

It prints the app's folder, ``DIR/AzurKit``. PyInstaller writes only under
``--dist`` and ``--work`` (its cache too, which would otherwise go in the
user's Library). The app leaves out what never ships (:data:`EXCLUDE`: Tk,
Unicorn, capstone, zig, and the standard library's GPL-linked modules).
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "AzurKit"
EXCLUDE = ("tkinter", "_tkinter", "unicorn", "capstone", "ziglang", "readline", "dbm", "_dbm", "_gdbm")


def freeze(dist: Path, work: Path) -> Path:
    """Build the onedir in ``dist``, with PyInstaller's files in ``work``; returns its folder."""
    os.environ["PYINSTALLER_CONFIG_DIR"] = str(work / "config")
    from PyInstaller.__main__ import run

    run(["--noconfirm", "--clean", "--onedir", "--name", NAME, "--log-level", "WARN",
         "--distpath", str(dist), "--workpath", str(work), "--specpath", str(work),
         "--paths", str(ROOT / "src"), "--collect-data", "azurkit", "--add-data", f"{ROOT / 'web'}{os.pathsep}web",
         *(arg for module in EXCLUDE for arg in ("--exclude-module", module)),
         str(ROOT / "src" / "azurkit" / "__main__.py")])
    return dist / NAME


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
