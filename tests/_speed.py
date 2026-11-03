"""The host's own speed, for the few tests that hold a quick answer to a bound
in seconds: a shared CI runner or a loaded machine is slower than the Mac the
bounds were set on, and that says nothing of the code. A bound scaled by
:func:`factor` still fails on what grows with its input (a quadratic takes
minutes where it's asked for a tenth of a second)."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from pathlib import Path

REFERENCE = 0.025
"""The seconds :func:`work` takes on the gate's Mac, unloaded."""
WRITES = 0.003
"""The seconds :func:`writes` takes on the gate's Mac, unloaded (2.6-3.7 ms, the quickest of three, ten times)."""


def work() -> float:
    """The seconds a small mix of what the bounded answers do takes now: Python's objects, JSON and a hash."""
    start = time.perf_counter()
    json.loads(json.dumps([{"id": k} for k in range(50_000)]))
    hashlib.sha256(bytes(16 << 20)).digest()
    return time.perf_counter() - start


def factor() -> float:
    """How many times slower than the bounds' Mac this host is now (the quickest of three runs), at least 1."""
    return max(1.0, min(work() for _ in range(3)) / REFERENCE)


def writes(folder: Path) -> float:
    """The seconds writing three 5 MiB files into a new folder in ``folder`` and removing it take now."""
    data = bytes(5 << 20)
    start = time.perf_counter()
    part = Path(tempfile.mkdtemp(dir=folder))
    for k in range(3):
        (part / f"{k}.json").write_bytes(data)
    shutil.rmtree(part)
    return time.perf_counter() - start


def slower_writes(folder: Path) -> float:
    """The seconds more than the bounds' Mac this host takes now to write what an Install refused at its fourth 5 MiB
    file writes (:func:`writes`, the quickest of three), at least 0: added to a bound that covers those writes, as a
    file system can slow them far more than its CPU (Windows' runner: that Install took 0.282 s where :func:`factor`
    scaled its bound to 0.201 s, run 41521288667)."""
    return max(0.0, min(writes(folder) for _ in range(3)) - WRITES)
