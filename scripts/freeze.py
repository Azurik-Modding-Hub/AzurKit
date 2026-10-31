"""Freeze the app (D732): a PyInstaller onedir of ``python -m azurkit``
(``src/azurkit/__main__.py``: the page with no arguments, ``serve``, else the
``azurkit`` command) with the page (``web/``), from this checkout's
environment. On macOS the onedir is a windowed app, ``AzurKit.app``.

    uv run --locked python scripts/freeze.py --dist DIR [--work DIR]

It prints the app's path: ``DIR/AzurKit.app`` on macOS, else the folder
``DIR/AzurKit``. PyInstaller writes only under ``--dist`` and ``--work``
(its cache too, which would otherwise go in the user's Library). The app
leaves out what never ships (:data:`EXCLUDE`: Tk, Unicorn, capstone, zig,
and the standard library's GPL-linked modules). On macOS its icon is
AzurKit's (:data:`ICON`, the mark on an azure tile, D892; ``assets/icon/``
rebuilds it). It carries the checked randomizer database
(``web_tools.ship_database``, keyed by the data alone, as the frozen app
keys it: its planner is in its archive, not files), so its Randomizer tab
doesn't check the database first (Step 4.3g).
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
ICON = ROOT / "assets" / "icon" / "AzurKit.icns"   # the .app's icon (its Info.plist's CFBundleIconFile)
EXCLUDE = ("tkinter", "_tkinter", "unicorn", "capstone", "ziglang", "readline", "dbm", "_dbm", "_gdbm")


def freeze(dist: Path, work: Path) -> Path:
    """Build the app in ``dist``, with PyInstaller's files in ``work``; returns its path."""
    os.environ["PYINSTALLER_CONFIG_DIR"] = str(work / "config")
    sys.path.insert(0, str(ROOT / "scripts"))
    import web_tools
    from PyInstaller.__main__ import run

    from azurkit.tools.randomizer import dbcache

    shipped = web_tools.ship_database(work / "shipped", planner=False)

    run(["--noconfirm", "--clean", "--onedir", "--name", NAME, "--log-level", "WARN",
         *(("--windowed", "--osx-bundle-identifier", BUNDLE_ID, "--icon", str(ICON)) if MACOS else ()),
         "--distpath", str(dist), "--workpath", str(work), "--specpath", str(work),
         "--paths", str(ROOT / "src"), "--collect-data", "azurkit", "--add-data", f"{ROOT / 'web'}{os.pathsep}web",
         "--add-data", f"{shipped}{os.pathsep}{web_tools.SHIPPED}",
         *(arg for module in EXCLUDE for arg in ("--exclude-module", module)),
         str(ROOT / "src" / "azurkit" / "__main__.py")])
    if MACOS:
        shutil.rmtree(dist / NAME)   # the onedir the bundle was made from: the bundle holds all of it
    app = dist / f"{NAME}.app" if MACOS else dist / NAME
    data = next(d for f in folders(app) if (d := f / "azurkit/tools/randomizer/data").is_dir())
    if dbcache.entry(data, None).name != shipped.stem:
        raise SystemExit(f"the app's randomizer data isn't what its shipped database {shipped.name} was made from")
    return app


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
