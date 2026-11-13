"""``python -m azurkit``, and the frozen app's entry (``scripts/freeze.py``):
with no arguments it opens the page (``azurkit.app``), with ``serve`` it
serves the page without opening it, and with any other arguments it is the
``azurkit`` command. In the frozen app, the app's engine process
(``azurkit.app.engine``) is this executable spawned again, which
``freeze_support`` runs; each process first gives itself the standard streams
it lacks (:func:`settle`: the Windows app is a windowed program, which Windows
starts with none), then arms the tests' dumps of its stacks, when they ask
(:mod:`azurkit._stacks`)."""

import multiprocessing
import os
import sys
from collections.abc import Callable
from typing import TextIO

LOG = "app.log"
"""The file in the app's log folder (the build logs', ``azurkit.app.logs.folder``, which the Tools tab opens) that
takes what the app prints where it has nowhere else to (:func:`settle`)."""
KEEP = 1 << 20
"""Bytes of :data:`LOG` the window's launch keeps: past them it starts the file again."""


def _parent_console() -> TextIO | None:
    """The console of the terminal this process was started from (Windows' ``AttachConsole``), opened for writing;
    None elsewhere, and where there is none (the window, started from Explorer, or its engine's process)."""
    if os.name != "nt":
        return None
    import ctypes
    attach = ctypes.WinDLL("kernel32").AttachConsole
    attach.argtypes = (ctypes.c_ulong,)
    if not attach(0xFFFFFFFF):   # ATTACH_PARENT_PROCESS
        return None
    try:
        return open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)   # kept: the streams'
    except OSError:
        return None


def settle(argv: list[str], attach: Callable[[], TextIO | None] = _parent_console) -> TextIO | None:
    """Give this process each standard stream it lacks, so nothing it prints is lost: the Windows app is a windowed
    program (``scripts/freeze.py``'s ``--windowed``, so no console window opens beside it), which Windows starts with
    no standard output or error unless whoever starts it hands it some (a pipe or a file: the tests', ``freeze.py
    --check``'s). A command's (any ``argv``) goes to the console of the terminal it was typed in (``attach``), when
    there is one; else, the window's too, to the end of :data:`LOG` in the app's log folder, where a crash's stack is
    written too (``faulthandler``): every process appends, so none writes over another's lines. Nothing where both
    streams are there (a terminal's, a pipe's, a console program's), or where the log can't be opened (``print`` then
    writes nowhere, as before). The stream it gave, or None."""
    if sys.stdout is not None and sys.stderr is not None:
        return None
    if (stream := attach() if argv else None) is None:
        from platformdirs import user_log_path
        try:
            (folder := user_log_path("AzurKit", appauthor=False)).mkdir(parents=True, exist_ok=True)
            if not argv and (log := folder / LOG).is_file() and log.stat().st_size > KEEP:   # the window's launch
                os.truncate(log, 0)   # starts it again, before its engine's process starts
            stream = open(folder / LOG, "a", encoding="utf-8", errors="replace", buffering=1)   # kept: the streams'
        except OSError:
            return None
        import faulthandler
        faulthandler.enable(stream)
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    return stream


if __name__ == "__main__":
    argv = sys.argv[1:]
    settle(argv)   # first: before anything prints
    from azurkit import _stacks

    _stacks.arm()   # the tests' dumps of each thread's stack, when they ask: before a spawned child's own start
    multiprocessing.freeze_support()
    if argv in ([], ["serve"]):
        from azurkit.app import main
    else:
        from azurkit.cli import main
    sys.exit(main(argv))
