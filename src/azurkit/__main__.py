"""``python -m azurkit``, and the frozen app's entry (``scripts/freeze.py``):
with no arguments it opens the page (``azurkit.app``), with ``serve`` it
serves the page without opening it, and with any other arguments it is the
``azurkit`` command. In the frozen app, the app's engine process
(``azurkit.app.engine``) is this executable spawned again, which
``freeze_support`` runs; each process first arms the tests' dumps of its
stacks, when they ask (:mod:`azurkit._stacks`)."""

import multiprocessing
import sys

if __name__ == "__main__":
    from azurkit import _stacks

    _stacks.arm()   # the tests' dumps of each thread's stack, when they ask: before a spawned child's own start
    multiprocessing.freeze_support()
    argv = sys.argv[1:]
    if argv in ([], ["serve"]):
        from azurkit.app import main
    else:
        from azurkit.cli import main
    sys.exit(main(argv))
