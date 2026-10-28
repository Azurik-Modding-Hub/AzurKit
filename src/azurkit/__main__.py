"""``python -m azurkit``, and the frozen app's entry (``scripts/freeze.py``):
with arguments it is the ``azurkit`` command, with none it opens the page
(``azurkit.app``)."""

import sys

if __name__ == "__main__":
    if sys.argv[1:]:
        from azurkit.cli import main
    else:
        from azurkit.app import main
    sys.exit(main())
