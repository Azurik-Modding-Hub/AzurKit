"""The swap's parallel work, in the host's hands (the plan's §2: a map the
host passes in): Modkit's ``assets/pool.py`` splits it over child
processes; the engine holds none (``tests/test_contracts.py``), so
:func:`each` runs it here, in order, unless a host gave :data:`MAP` its own
(the app hands it a process pool, ``azurkit.app.procpool``; the site's
worker runs it here), and :func:`later` works it out now unless a host gave
:data:`LATER` a thread. The results are the function's on each item in
order either way, so what a build writes doesn't depend on the split."""

from __future__ import annotations

from collections.abc import Callable

LEAST = 8
"""Modkit's: the fewest items it splits (fewer run in the caller)."""
MAP: Callable[..., list] | None = None
"""A host's ``map(fn, shared, items, cost, tick) -> [fn(shared, item) ...]``
(``cost(n)``: item ``n``'s, the dearest first; ``tick(k)``: ``k`` more
done), or ``None``: here, in order."""
LATER: Callable[..., object] | None = None
"""A host's ``later(fn, *args)``: what gives ``fn(*args)`` by ``result()``
(a thread's future, Modkit's), or ``None``: worked out now."""
TICK: Callable[[int, int], object] | None = None
"""A host's ``tick(done, total)`` as :func:`each`'s items finish (its progress), or ``None``."""


def each(fn: Callable, shared, items: list, cost: Callable[[int], float] | None = None, least: int = LEAST) -> list:
    """``[fn(shared, item) for item in items]``, by :data:`MAP` when a host
    gave one (from ``least`` items on), each item counted to :data:`TICK`."""
    done, tick = 0, TICK

    def ticked(count: int) -> None:
        nonlocal done
        done += count
        if tick is not None:
            tick(done, len(items))
    if MAP is not None and len(items) >= least:
        return list(MAP(fn, shared, items, cost, ticked))
    out = []
    for item in items:
        out.append(fn(shared, item))
        ticked(1)
    return out


class Later:
    """A result :func:`later` works out at its first :meth:`result`, from
    its arguments as they were handed over (pickled then: a caller may
    change them meanwhile, as a host's thread reads them at once), so work
    started ahead and never asked for (a cut whose LOD 0 changed before it
    was taken) costs nothing; :meth:`result` gives it, or raises what the
    work raised."""

    def __init__(self, fn: Callable, args: tuple):
        import pickle

        self._fn, self._args, self._done = fn, pickle.dumps(args, pickle.HIGHEST_PROTOCOL), False
        self._value = self._error = None

    def result(self, timeout: float | None = None):
        if not self._done:
            import pickle

            try:
                self._value = self._fn(*pickle.loads(self._args))
            except Exception as exc:   # raised where Modkit's future raises it: at result()
                self._error = exc
            self._fn = self._args = None
            self._done = True
        if self._error is not None:
            raise self._error
        return self._value

    def done(self) -> bool:
        return self._done


def later(fn: Callable, *args):
    """``fn(*args)``: on a host's :data:`LATER` (Modkit runs it on a thread
    while it works on), else worked out now."""
    if LATER is not None:
        return LATER(fn, *args)
    return Later(fn, args)
