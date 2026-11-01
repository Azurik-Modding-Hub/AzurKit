"""The wheel: built from this checkout (``web_tools.wheel``), it carries
every file of the package, each module's bytecode and the checked
randomizer database (Step 4.3g), and nothing the leak guard refuses, and
installs alone in a clean venv (only its declared dependencies, at the
lock's versions, offline: ``web_tools.install``) where every
module imports, the ``azurkit`` command runs and the database loads as
shipped, never checked again."""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

from azurkit import __version__
from scripts import web_tools
from tests import _leak_guard

ROOT = Path(__file__).resolve().parent.parent
IMPORT_ALL = ("import importlib, pkgutil, azurkit; "
              "[importlib.import_module(m.name) for m in pkgutil.walk_packages(azurkit.__path__, 'azurkit.')]")
SHIPPED_ONLY = ("import sys; from azurkit.tools.randomizer import dbcache; "
                "from azurkit.tools.randomizer.planner.loader import DATA_DIR; "
                "dbcache.load(DATA_DIR, lambda root: sys.exit(f'{root}: checked, not the shipped database'))")


def test_the_wheel_carries_the_package_and_installs_alone_in_a_clean_venv(tmp_path):
    def run(*argv: str) -> str:
        return subprocess.run(argv, capture_output=True, text=True, check=True, timeout=300).stdout
    wheel = web_tools.wheel(tmp_path / "dist")
    with zipfile.ZipFile(wheel) as zf:
        names = {n for n in zf.namelist() if not n.endswith("/")}
        assert [f"{n}: {why}" for n in sorted(names) if (why := _leak_guard.check_bytes(n, zf.read(n)))] == []
    tracked = set(run("git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard",
                      "src/azurkit").split())
    package = {rel.removeprefix("src/") for rel in tracked}
    pyc = {f"{folder}/__pycache__/{name[:-3]}.{sys.implementation.cache_tag}.pyc"
           for folder, _, name in (rel.rpartition("/") for rel in package if rel.endswith(".py"))}
    (shipped,) = {n for n in names if n.startswith(f"{web_tools.SHIPPED}/") and n.endswith(".pickle")}
    assert {n for n in names if not n.startswith(f"azurkit-{__version__}.dist-info/")} == package | pyc | {shipped}
    python = web_tools.install(wheel, tmp_path / "venv")
    scripts = Path(python).parent
    run(python, "-I", "-c", IMPORT_ALL)
    run(python, "-I", "-c", SHIPPED_ONLY)
    assert run(str(scripts / "azurkit"), "--version").strip() == f"azurkit {__version__}"
