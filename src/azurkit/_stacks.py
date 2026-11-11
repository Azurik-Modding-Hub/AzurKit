"""Each thread's stack, dumped where the tests ask (Step 4.37i): with
:data:`FOLDER` set, :func:`arm` has this process's ``faulthandler`` write
every thread's stack to ``<pid>.txt`` there each :data:`EVERY` s (by a C
thread, so a thread that holds the GIL is written too), the file's first line
``pid P of Q`` (Q its parent), each dump headed ``Timeout (...)!``. Only the
tests set it (the frozen app's sandbox), so a served call that never answers
names where each of the app's processes stood: the frozen app's entry arms
each process it starts as its first act (``azurkit.__main__``, before
``freeze_support``: its engine and the pool's children too, so a child stuck
before its work is written), and ``app.main`` and ``app.engine.orphaned`` arm
those ``python -m azurkit`` starts. A player sets nothing and nothing is
written. The standard library alone: it runs before anything else loads."""

from __future__ import annotations

import os

FOLDER = "AZURKIT_STACKS"
"""The environment variable naming the folder the dumps go in."""
EVERY = 30
"""Seconds between a process's dumps."""
_FILE: list = []   # the open file faulthandler writes to: armed once a process


def arm() -> None:
    """Arm this process's dumps (the module's docstring); nothing where
    :data:`FOLDER` is unset, it is armed already, or its folder can't be
    written."""
    if not (folder := os.environ.get(FOLDER)) or _FILE:
        return
    import faulthandler

    try:
        file = open(os.path.join(folder, f"{os.getpid()}.txt"), "w", encoding="utf-8")   # kept: faulthandler's
        file.write(f"pid {os.getpid()} of {os.getppid()}\n")
        file.flush()
        faulthandler.dump_traceback_later(EVERY, repeat=True, file=file)
    except (OSError, ValueError, RuntimeError):
        return
    _FILE.append(file)
