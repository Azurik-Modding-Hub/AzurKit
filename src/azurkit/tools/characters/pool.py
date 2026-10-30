"""The swap's parallel work, in the host's hands (the plan's §2: a map the
host passes in): Modkit's ``assets/pool.py`` splits it over child
processes; the engine holds none (``tests/test_contracts.py``), so
:func:`each` runs it here, in order, unless a host gave :data:`MAP` its own
(the app may hand it a process pool; the site's worker runs it here). The
results are the function's on each item in order either way, so what a
build writes doesn't depend on the split."""

from __future__ import annotations

from collections.abc import Callable

LEAST = 8
"""Modkit's: the fewest items it splits (fewer run in the caller)."""
MAP: Callable[[Callable, object, list], list] | None = None
"""A host's ``map(fn, shared, items) -> [fn(shared, item) ...]``, or ``None``: here, in order."""


def each(fn: Callable, shared, items: list, cost: Callable[[int], float] | None = None, least: int = LEAST) -> list:
    """``[fn(shared, item) for item in items]``, by :data:`MAP` when a host gave one."""
    if MAP is not None and len(items) >= least:
        return list(MAP(fn, shared, items))
    return [fn(shared, item) for item in items]


class Later:
    """A result :func:`later` worked out: :meth:`result` gives it, or raises what the work raised."""

    def __init__(self, fn: Callable, args: tuple):
        try:
            self._value, self._error = fn(*args), None
        except Exception as exc:   # raised where Modkit's future raises it: at result()
            self._value, self._error = None, exc

    def result(self, timeout: float | None = None):
        if self._error is not None:
            raise self._error
        return self._value

    def done(self) -> bool:
        return True


def later(fn: Callable, *args) -> Later:
    """``fn(*args)``, worked out now (Modkit runs it on a thread while it works on)."""
    return Later(fn, args)
