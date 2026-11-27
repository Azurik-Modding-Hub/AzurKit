"""The reach engine's slide launch (Step 4.83b; AZ-374 W): ``slidejump``, a launch family in a file of its own
(``macros.FAMILIES``: ``macros.controller`` is its one hook), keyed apart from the L3 core (``cache.SLIDE_FILES``), so
an edit here re-runs only the jobs that fly it.  Positions stay in memory and the private cache."""

from __future__ import annotations

KIND = "slidejump"


def controller(make):
    """The controller a ``slidejump`` launch runs under, made of ``make`` (``macros._Run``, or an aim's)."""
    return make
