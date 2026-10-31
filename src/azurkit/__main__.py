"""``python -m azurkit``, and the frozen app's entry (``scripts/freeze.py``):
with no arguments it opens the page (``azurkit.app``), with ``serve`` it
serves the page without opening it, and with any other arguments it is the
``azurkit`` command. In the frozen app, the app's engine process
(``azurkit.app.engine``) is this executable spawned again, which
``freeze_support`` runs."""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    argv = sys.argv[1:]
    if argv in ([], ["serve"]):
        from azurkit.app import main
    else:
        from azurkit.cli import main
    sys.exit(main(argv))
