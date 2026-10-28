"""The wheel: built from this checkout, it carries every file of the package
and nothing the leak guard refuses, and installs alone in a clean venv
(only its declared dependencies) where every module imports and the
``azurkit`` command runs."""

from __future__ import annotations

import os
import subprocess
import zipfile
from pathlib import Path

from azurkit import __version__
from tests import _leak_guard

ROOT = Path(__file__).resolve().parent.parent
IMPORT_ALL = ("import importlib, pkgutil, azurkit; "
              "[importlib.import_module(m.name) for m in pkgutil.walk_packages(azurkit.__path__, 'azurkit.')]")


def test_the_wheel_carries_the_package_and_installs_alone_in_a_clean_venv(tmp_path):
    def run(*argv: str) -> str:
        return subprocess.run(argv, capture_output=True, text=True, check=True, timeout=300).stdout
    run("uv", "build", "--offline", "--quiet", "--wheel", "--out-dir", str(tmp_path / "dist"), str(ROOT))
    (wheel,) = (tmp_path / "dist").glob("azurkit-*.whl")
    with zipfile.ZipFile(wheel) as zf:
        names = {n for n in zf.namelist() if not n.endswith("/")}
        assert [f"{n}: {why}" for n in sorted(names) if (why := _leak_guard.check_bytes(n, zf.read(n)))] == []
    tracked = set(run("git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard",
                      "src/azurkit").split())
    assert {n for n in names if not n.startswith(f"azurkit-{__version__}.dist-info/")} == {
        rel.removeprefix("src/") for rel in tracked}
    run("uv", "venv", "--quiet", "--python", "3.14", str(tmp_path / "venv"))
    scripts = tmp_path / "venv" / ("Scripts" if os.name == "nt" else "bin")
    python = str(scripts / "python")
    run("uv", "pip", "install", "--offline", "--quiet", "--python", python, str(wheel))
    run(python, "-I", "-c", IMPORT_ALL)
    assert run(str(scripts / "azurkit"), "--version").strip() == f"azurkit {__version__}"
