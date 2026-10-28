"""``python -m azurkit``, and the frozen app's entry (``scripts/freeze.py``):
with no arguments it opens the page (``azurkit.app``), with ``serve`` it
serves the page without opening it, and with any other arguments it is the
``azurkit`` command."""

import sys

if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv in ([], ["serve"]):
        from azurkit.app import main
    else:
        from azurkit.cli import main
    sys.exit(main(argv))
