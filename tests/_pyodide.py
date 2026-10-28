"""The ``web`` tests' runtime: the ``azurkit`` command under Pyodide on Node
(``tests/_pyodide.mjs``), from this checkout's wheel alone, as the site's
worker will run it. Each argument that names a file on disk is passed by
its path in Pyodide (its folder mounted) and given back as it was in the
output, so the output compares with CPython's."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import web_tools

ROOT = Path(__file__).resolve().parent.parent


def run(argv: list[str], wheel: Path) -> dict:
    """``{"code", "stdout", "stderr", "platform", "python", "azurkit"}`` of
    ``azurkit *argv`` under Pyodide."""
    mounts, passed, given = [], [], {}
    for arg in argv:
        if Path(arg).is_file():
            real, folder = Path(arg).resolve(), f"/mnt/{len(mounts)}"
            mounts.append([folder, str(real.parent)])
            given[f"{folder}/{real.name}"] = arg
            arg = f"{folder}/{real.name}"
        passed.append(arg)
    done = subprocess.run(["node", str(ROOT / "tests" / "_pyodide.mjs"), str(web_tools.pyodide_dir(ROOT)), str(wheel),
                           json.dumps({"mounts": mounts, "argv": passed})], capture_output=True, text=True, timeout=600)
    if done.returncode:
        raise RuntimeError(f"Pyodide on Node exited {done.returncode}: {done.stderr[-2000:]}")
    result = json.loads(done.stdout.splitlines()[-1])
    for stream in ("stdout", "stderr"):
        for there, arg in given.items():
            result[stream] = result[stream].replace(there, arg)
    return result
