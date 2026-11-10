"""Freeze the app (D732): a PyInstaller onedir of ``python -m azurkit``
(``src/azurkit/__main__.py``: the page with no arguments, ``serve``, else the
``azurkit`` command) with the page (``web/``), from this checkout's
environment. On macOS the onedir is a windowed app, ``AzurKit.app``.

    uv run --locked python scripts/freeze.py --dist DIR [--work DIR] [--check]

It prints the app's path: ``DIR/AzurKit.app`` on macOS, else the folder
``DIR/AzurKit``. PyInstaller writes only under ``--dist`` and ``--work``
(its cache too, which would otherwise go in the user's Library). The app
leaves out what never ships (:data:`EXCLUDE`: Tk, Unicorn, capstone, zig,
cryptography, pywin32 and the standard library's GPL-linked modules). On macOS its icon is
AzurKit's (:data:`ICON`, the mark on an azure tile, D892; ``assets/icon/``
rebuilds it). It carries the checked randomizer database
(``web_tools.ship_database``, keyed by the data alone, as the frozen app
keys it: its planner is in its archive, not files), so its Randomizer tab
doesn't check the database first (Step 4.3g). It carries this platform's
compiled library (``core/native.py``), named on its own because
``--collect-data`` skips every ``.so`` (Python's extension suffix) and
``--collect-binaries`` every ``.so`` not named ``lib*`` (Step 4.3r4e); macOS's
build rewrites and re-signs it, so its sha12 there isn't the committed file's.
From a git checkout it carries the commit it was frozen from
(``azurkit.STAMP``), which its About shows. It carries Live's macOS admin
helper as a file (``azurkit/app/live_helper.py``: the attach copies it for
root to run, and nothing imports it, so ``--collect-data`` leaves it out).
``--check`` then runs the app (``serve``: no window, in this user's folders,
so a CI runner's) and refuses one whose report says the library didn't load.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "AzurKit"
BUNDLE_ID = "io.github.azurik-modding-hub.azurkit"
MACOS = sys.platform == "darwin"
ICON = ROOT / "assets" / "icon" / "AzurKit.icns"   # the .app's icon (its Info.plist's CFBundleIconFile)
EXCLUDE = ("tkinter", "_tkinter", "unicorn", "capstone", "ziglang", "cryptography", "readline", "dbm", "_dbm",
           "_gdbm", "win32pdh", "win32api", "win32con", "win32job", "pywintypes", "pythoncom", "win32com")
# cryptography: devkit's mcp brings it, and pywebview imports it when it is installed. pywin32's modules: mcp brings
# pywin32 on Windows, where numpy.testing's memusage imports win32pdh (in a function the app never calls), which put
# pywin32's win32/ and pywin32_system32/ in the app with a licence its own check can't name.


def freeze(dist: Path, work: Path, check: bool = False) -> Path:
    """Build the app in ``dist``, with PyInstaller's files in ``work``; returns
    its path. ``check``: refuse an app whose compiled library doesn't load."""
    os.environ["PYINSTALLER_CONFIG_DIR"] = str(work / "config")
    sys.path.insert(0, str(ROOT / "scripts"))
    import web_tools
    from PyInstaller.__main__ import run

    import azurkit
    from azurkit.core import native
    from azurkit.tools.randomizer import dbcache

    if (library := native.target()) is None:
        raise SystemExit(native.report()["why"])
    shipped = web_tools.ship_database(work / "shipped", planner=False)
    stamped = ()   # the commit it was built from, which About shows (azurkit.commit)
    if (head := azurkit.head(ROOT)) is not None:
        (stamp := work / "stamp" / azurkit.STAMP).parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(f"{head}\n", encoding="utf-8")
        stamped = ("--add-data", f"{stamp}{os.pathsep}azurkit")

    run(["--noconfirm", "--clean", "--onedir", "--name", NAME, "--log-level", "WARN",
         *(("--windowed", "--osx-bundle-identifier", BUNDLE_ID, "--icon", str(ICON)) if MACOS else ()),
         "--distpath", str(dist), "--workpath", str(work), "--specpath", str(work),
         "--paths", str(ROOT / "src"), "--collect-data", "azurkit", "--add-data", f"{ROOT / 'web'}{os.pathsep}web",
         "--add-data", f"{shipped}{os.pathsep}{web_tools.SHIPPED}", *stamped,
         "--add-data", f"{ROOT / 'src' / 'azurkit' / 'app' / 'live_helper.py'}{os.pathsep}azurkit/app",
         "--add-binary", f"{native.FOLDER / library}{os.pathsep}azurkit/core/_native",
         *(arg for module in EXCLUDE for arg in ("--exclude-module", module)),
         str(ROOT / "src" / "azurkit" / "__main__.py")])
    if MACOS:
        shutil.rmtree(dist / NAME)   # the onedir the bundle was made from: the bundle holds all of it
    app = dist / f"{NAME}.app" if MACOS else dist / NAME
    data = next(d for f in folders(app) if (d := f / "azurkit/tools/randomizer/data").is_dir())
    if dbcache.entry(data, None).name != shipped.stem:
        raise SystemExit(f"the app's randomizer data isn't what its shipped database {shipped.name} was made from")
    if not any((f / "azurkit/app/live_helper.py").is_file() for f in folders(app)):
        raise SystemExit("the app lacks Live's admin helper (azurkit/app/live_helper.py), which its attach copies")
    if check and not (loaded := report(app))["loaded"]:
        raise SystemExit(f"the app runs the Python twins, not its compiled library: {loaded['why']}")
    return app


def executable(app: Path) -> Path:
    """The app's program (in an ``.app``, its ``Contents/MacOS``; on Windows, its ``.exe``)."""
    if app.suffix == ".app":
        return app / "Contents" / "MacOS" / NAME
    return app / (f"{NAME}.exe" if sys.platform == "win32" else NAME)


def folders(app: Path) -> list[Path]:
    """The folders that hold the app's libraries and data."""
    if app.suffix == ".app":
        return [app / "Contents" / "Frameworks", app / "Contents" / "Resources"]
    return [app / "_internal"]


def report(app: Path, **popen) -> dict:
    """The app's own report of its compiled kernels (``sdk.catalog``'s
    ``native``), from its ``serve``; ``popen``: how to run it (``env``, ``cwd``)."""
    with subprocess.Popen([str(executable(app)), "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                          **popen) as served:
        url = urllib.parse.urlsplit(served.stdout.readline().strip())
        with urllib.request.urlopen(f"http://{url.netloc}/host.json?{url.query}", timeout=120) as host:
            return json.load(host)["catalog"]["native"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dist", type=Path, required=True, help="where the app's folder goes")
    ap.add_argument("--work", type=Path, help="PyInstaller's build files (default: a temporary folder)")
    ap.add_argument("--check", action="store_true",
                    help="then run the app (no window; in this user's folders) and refuse it unless its library loads")
    args = ap.parse_args(argv)
    if args.work:
        print(freeze(args.dist.resolve(), args.work.resolve(), args.check))
        return 0
    with tempfile.TemporaryDirectory(prefix="azurkit-freeze.") as work:
        print(freeze(args.dist.resolve(), Path(work), args.check))
    return 0


if __name__ == "__main__":
    sys.exit(main())
