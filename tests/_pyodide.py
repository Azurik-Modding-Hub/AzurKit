"""The ``web`` tests' runtime: the ``azurkit`` command under Pyodide on Node
(``tests/_pyodide.mjs``), from this checkout's wheel alone, as the site's
worker will run it. Each argument that names a file on disk is passed by
its path in Pyodide (its folder mounted) and given back as it was in the
output, so the output compares with CPython's."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from scripts import web_tools

ROOT = Path(__file__).resolve().parent.parent


def numpy() -> str:
    """The file name of Pyodide's numpy wheel beside its core, as the core's
    ``pyodide-lock.json`` pins it (its sha256 checked); ``RuntimeError``
    when it isn't there."""
    folder = web_tools.pyodide_dir(ROOT)
    pinned = json.loads((folder / "pyodide-lock.json").read_text(encoding="utf-8"))["packages"]["numpy"]
    wheel = folder / pinned["file_name"]
    if not wheel.is_file() or hashlib.sha256(wheel.read_bytes()).hexdigest() != pinned["sha256"]:
        raise RuntimeError(f"{wheel}: Pyodide's numpy wheel, which a swap under Pyodide loads, isn't there as the "
                           f"core's lock pins it (sha256 {pinned['sha256'][:12]})")
    return pinned["file_name"]


def run(argv: list[str], wheel: Path, *, image: dict | None = None, packages: tuple[str, ...] = ()) -> dict:
    """``{"code", "stdout", "stderr", "report", "platform", "python",
    "azurkit"}`` of ``azurkit *argv`` under Pyodide, or (``image``, a
    recipe) of ``sdk.image``, its report, with ``packages`` (wheels beside
    Pyodide's core) loaded first."""
    mounts, passed, given = [], [], {}

    def mounted(arg: str) -> str:
        if not Path(arg).is_file():
            return arg
        real, folder = Path(arg).resolve(), f"/mnt/{len(mounts)}"
        mounts.append([folder, str(real.parent)])
        given[f"{folder}/{real.name}"] = arg
        return f"{folder}/{real.name}"
    passed = [mounted(arg) for arg in argv]
    job = {"mounts": mounts, "argv": passed, "packages": list(packages)}
    if image is not None:
        job["image"] = image | {"iso": mounted(image["iso"])}
    done = subprocess.run(["node", str(ROOT / "tests" / "_pyodide.mjs"), str(web_tools.pyodide_dir(ROOT)), str(wheel),
                           json.dumps(job)], capture_output=True, text=True, timeout=1200)
    if done.returncode:
        raise RuntimeError(f"Pyodide on Node exited {done.returncode}: {done.stderr[-2000:]}")
    result = json.loads(done.stdout.splitlines()[-1])
    for stream in ("stdout", "stderr"):
        for there, arg in given.items():
            result[stream] = result[stream].replace(there, arg)
    return result
