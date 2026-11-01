"""The host's own speed, for the few tests that hold a quick answer to a bound
in seconds: a shared CI runner or a loaded machine is slower than the Mac the
bounds were set on, and that says nothing of the code. A bound scaled by
:func:`factor` still fails on what grows with its input (a quadratic takes
minutes where it's asked for a tenth of a second)."""

from __future__ import annotations

import hashlib
import json
import time

REFERENCE = 0.025
"""The seconds :func:`work` takes on the gate's Mac, unloaded."""


def work() -> float:
    """The seconds a small mix of what the bounded answers do takes now: Python's objects, JSON and a hash."""
    start = time.perf_counter()
    json.loads(json.dumps([{"id": k} for k in range(50_000)]))
    hashlib.sha256(bytes(16 << 20)).digest()
    return time.perf_counter() - start


def factor() -> float:
    """How many times slower than the bounds' Mac this host is now (the quickest of three runs), at least 1."""
    return max(1.0, min(work() for _ in range(3)) / REFERENCE)
