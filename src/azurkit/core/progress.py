"""A long call's progress, as a host shows it (D980: a bar on both hosts).

The engine reports each named stage of a call as one record, a plain JSON
object a host renders the same way whether it polls it (the app's
``api/progress``) or the site's worker posts it::

    {"stage": "check", "label": "Checking your image", "done": 412, "total": 1001, "percent": 41}

``stage`` is one of :data:`STAGES` (a host may key a bar's look on it);
``label`` the line the player reads (``Applying fps_unlock``, ``Dressing
keylord``); ``done`` and ``total`` count the stage's units (bytes, packs:
``total`` 0 when the stage has no count) and ``percent`` is ``done`` of
``total`` rounded down, or ``None`` with no count. :class:`Steps` is what a
call reports through: it does nothing without a host's callback, and an
exception the callback raises (a cancel) goes up through the call, which
then writes nothing (D35). Nothing here starts a thread.
"""

from __future__ import annotations

from collections.abc import Callable

STAGES = {
    "check": "Checking your image",        # its build files hashed, the first time (D27, D982)
    "plan": "Planning the seed",           # the randomizer's fill
    "size": "Sizing",                      # a worn body's size, folded into the walk and roll
    "read": "Reading its files",
    "pack": "Applying",                    # each pack, done of total
    "dress": "Dressing",                   # the character layer (its swap)
    "data": "Applying the data edits",     # the mods file's xbr operations
    "layout": "Laying out the image",
    "judge": "Reading the build back",     # the randomizer's read-back against its plan
    "spoiler": "Writing the spoiler",
    "write": "Saving",                     # the image's bytes, done of total
}
"""Each stage a call reports, and its label's default words."""


def record(stage: str, label: str | None = None, done: int = 0, total: int = 0) -> dict:
    """The record of ``stage`` (one of :data:`STAGES`), its ``label``
    (:data:`STAGES`' words when ``None``), ``done`` of ``total``."""
    if stage not in STAGES:
        raise ValueError(f"progress: no stage {stage!r} (its stages: {', '.join(STAGES)})")
    return {"stage": stage, "label": STAGES[stage] if label is None else label, "done": done, "total": total,
            "percent": done * 100 // total if total > 0 else None}


class Steps:
    """A call's reporter: ``steps(stage, label, done, total)`` hands the
    host's ``report`` the stage's :func:`record`; without one it does
    nothing."""

    def __init__(self, report: Callable[[dict], object] | None = None):
        self.report = report

    def __bool__(self) -> bool:
        return self.report is not None

    def __call__(self, stage: str, label: str | None = None, done: int = 0, total: int = 0) -> None:
        if self.report is not None:
            self.report(record(stage, label, done, total))

    def counter(self, stage: str, label: str | None = None) -> Callable[[int, int], None] | None:
        """``(done, total) -> None`` reporting ``stage`` (the form a byte
        loop takes: ``iso.pack``'s, ``gate.verify``'s), or ``None`` without
        a host's callback."""
        if self.report is None:
            return None
        return lambda done, total: self(stage, label, done, total)
