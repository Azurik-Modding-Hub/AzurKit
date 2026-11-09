"""devkit's dispatcher: ``python -m devkit [AREA [VERB [ARGS ...]]]``, run
from the checkout's root.

With no area (or ``-h``) it lists the areas, with an area alone (or ``AREA
-h``) that area's verbs, and exits 0. With a verb it imports
``devkit.<area>.<verb>`` (a hyphen in the verb is an underscore in the
module's name) and exits with what its ``main(ARGS)`` returns. An area that
is a command of its own (its package has a ``main``: ``doctor``) runs it
with the rest, ``python -m devkit AREA [ARGS ...]``. An unknown area or
verb is one ``devkit: ...`` line on stderr and exit 2.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys

import devkit

HELP = ("-h", "--help")


def areas() -> list[str]:
    """devkit's areas: its subpackages' names, sorted."""
    return sorted(info.name for info in pkgutil.iter_modules(devkit.__path__) if info.ispkg)


def _table(rows: dict[str, str]) -> str:
    width = max(map(len, rows), default=0)
    return "".join(f"  {name:<{width}}  {line}\n" for name, line in rows.items()) or "  (none yet)\n"


def _first(doc: str | None) -> str:
    """A docstring's first paragraph, on one line."""
    return " ".join((doc or "").strip().split("\n\n")[0].split())


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):   # a ? for what the console's code page (cp1252) has no byte for (AZ-190)
        sys.stdout.reconfigure(errors="replace")
    names = areas()
    if not argv or argv[0] in HELP:
        rows = {name: _first(importlib.import_module(f"devkit.{name}").__doc__) for name in names}
        print(f"usage: python -m devkit AREA VERB [ARGS ...]\n\nthe areas:\n{_table(rows)}", end="")
        return 0
    area, *rest = argv
    if area not in names:
        print(f"devkit: no area {area!r} (the areas: {', '.join(names) or 'none yet'})", file=sys.stderr)
        return 2
    module = importlib.import_module(f"devkit.{area}")
    if hasattr(module, "main"):   # an area that is a command of its own
        return module.main(rest)
    verbs = getattr(module, "VERBS", {})
    if not rest or rest[0] in HELP:
        print(f"usage: python -m devkit {area} VERB [ARGS ...]\n\nits verbs:\n{_table(verbs)}", end="")
        return 0
    verb, *args = rest
    if verb not in verbs:
        print(f"devkit: the {area} area has no verb {verb!r} (its verbs: {', '.join(verbs) or 'none yet'})",
              file=sys.stderr)
        return 2
    return importlib.import_module(f"devkit.{area}.{verb.replace('-', '_')}").main(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
