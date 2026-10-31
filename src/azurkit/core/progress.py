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
then writes nothing (D35). A loop deep in a call that has no ``Steps`` of
its own (the randomizer's fill) tells the call its thread runs a
:func:`note` ("placing the items, k of n"), which :func:`noting` folds into
the stage the call reported last, so each note is a record and a cancel
point too. Nothing here starts a thread.
"""

from __future__ import annotations

import contextlib
import contextvars
import re
from collections.abc import Callable, Iterator

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


# the fold of the call this thread runs (:func:`noting`'s): a context's, so each thread's own and no thread started
_TOLD: contextvars.ContextVar[Callable[[str], None] | None] = contextvars.ContextVar("told", default=None)


def note(text: str) -> None:
    """Tell the call this thread runs under :func:`noting` ``text``: a long
    loop's count ("placing the items, k of n"), a record of its stage and
    so a cancel point (the host's callback may raise through it); nothing
    when no call on this thread listens."""
    if (told := _TOLD.get()) is not None:
        told(text)


@contextlib.contextmanager
def noting(steps: Steps) -> Iterator[Steps]:
    """``steps`` for this thread's call, the :func:`note` calls made on this
    thread while it runs folded into the stage it reported last through the
    ``Steps`` this yields: that stage's ``label (note)``, a "k of n" note
    counted inside the stage's step (``done`` of ``total`` as ``done * n +
    k - 1`` of ``total * n``; ``k - 1`` of ``n`` in a stage with no count),
    so its bar moves on as the count does: a count that starts again (a
    retried fill attempt's, whose label names the attempt) takes it back to
    its own start. A call inside another's folds into its own stages until
    it ends."""
    if not steps:
        yield steps
        return
    last: list[dict] = []

    def heard(step: dict) -> None:
        last[:] = [step]
        steps.report(step)

    def told(text: str) -> None:
        if not last:   # no stage yet to fold it into
            return
        at, done, total = last[0], last[0]["done"], last[0]["total"]
        if count := re.search(r"(\d+) of (\d+)", text):
            k, n = map(int, count.groups())
            done, total = done * n + k - 1, max(total, 1) * n
        steps.report(record(at["stage"], f"{at['label']} ({text})", done, total))
    token = _TOLD.set(told)
    try:
        yield Steps(heard)
    finally:
        _TOLD.reset(token)
