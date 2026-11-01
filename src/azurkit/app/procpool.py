"""The app's process pool (Step 4.3i): the swap's parallel work
(``tools.characters.pool``'s :data:`~azurkit.tools.characters.pool.MAP` and
``LATER``), which the engine may not hold itself (``tests/test_contracts.py``),
in the app's engine process (:mod:`.engine`).

Modkit's split (``azurik_mod/assets/pool.py``): a call's items in up to
:func:`workers` parts, runs of the order, or by their cost the dearest first,
each to the part with the least, a part a spawned child. The results are the
function's on each item in order, whichever child ran it, so what a build
writes doesn't depend on the split; a part whose child fails runs here, in
order, raising here what the function raises. The children stay for the next
call (at most :func:`workers` idle; one that grew past :data:`RETIRE` leaves
after its part), end with their parent (they watch it),
and pass their work through pipes alone: no semaphore, so a killed engine
leaves none behind."""

from __future__ import annotations

import multiprocessing
import multiprocessing.connection
import os
import sys
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

MOST = 16
"""The most children a call splits over (Modkit's)."""
CORES = "AZURKIT_CORES"
"""A positive whole number: the most cores AzurKit's parallel work takes (the capped profile's, D984)."""
RETIRE = 256 << 20
"""A child whose resident size has peaked past this many bytes leaves once
it has sent a part's results, so the heap that part grew goes back to the
OS (a collection or the allocator's trim returns none of it) and the next
call takes a fresh child: booblord's jiggle keying leaves each of 4
children holding 250-512 MB through the rest of her dress."""

_CONTEXT = multiprocessing.get_context("spawn")
_IDLE: list[_Child] = []
_LOCK = threading.Lock()


def workers() -> int:
    """``min(MOST, this process's CPUs, $AZURKIT_CORES)``; a value of it
    that isn't a positive whole number is not a cap."""
    most = min(MOST, os.process_cpu_count() or 1)
    try:
        cap = int(os.environ.get(CORES, ""))
    except ValueError:
        return most
    return min(most, cap) if cap > 0 else most


class _Child:
    """One spawned child and its pipe."""

    def __init__(self):
        self.conn, there = _CONTEXT.Pipe()
        self.process = _CONTEXT.Process(target=_work, args=(there,), name="azurkit-pool", daemon=True)
        self.process.start()
        there.close()

    def stop(self) -> None:
        self.conn.close()   # its loop ends on the closed pipe
        self.process.join(1)
        if self.process.is_alive():
            self.process.kill()
            self.process.join()


def _split(count: int, parts: int, cost: Callable[[int], float] | None) -> list[list[int]]:
    """``count`` items' indices in ``parts`` parts: runs of the order, or by
    ``cost`` the dearest first, each to the part with the least (Modkit's)."""
    if cost is None:
        return [list(range(w * count // parts, (w + 1) * count // parts)) for w in range(parts)]
    loads, out = [0.0] * parts, [[] for _ in range(parts)]
    for n in sorted(range(count), key=lambda n: (-cost(n), n)):
        w = loads.index(min(loads))
        out[w].append(n)
        loads[w] += cost(n)
    return out


def _take(count: int) -> list[_Child]:
    """``count`` children: idle ones first, then new ones (fewer when one can't start)."""
    with _LOCK:
        taken = _IDLE[len(_IDLE) - min(count, len(_IDLE)):]
        del _IDLE[len(_IDLE) - len(taken):]
    try:
        while len(taken) < count:
            taken.append(_Child())
    except OSError:
        pass
    return taken


def _give(children: list[_Child]) -> None:
    """Keep ``children`` for the next call, up to :func:`workers` idle; stop the rest."""
    with _LOCK:
        kept = [c for c in children if c.process.is_alive()][:max(0, workers() - len(_IDLE))]
        _IDLE.extend(kept)
    for child in children:
        if child not in kept:
            child.stop()


def map_(fn: Callable, shared, items: list, cost: Callable[[int], float] | None = None,
         tick: Callable[[int], object] | None = None) -> list:
    """``[fn(shared, item) for item in items]``, split over children (the
    module's docstring); ``tick(k)`` as each part's ``k`` items come back."""
    results: list = [None] * len(items)
    if not items:
        return results
    parts = [part for part in _split(len(items), min(workers(), len(items)), cost) if part]
    children, here, broken, waiting = _take(len(parts)), [], [], {}
    try:
        for n, part in enumerate(parts):
            child = children[n] if n < len(children) else None
            try:
                if child is None:
                    raise OSError("no child")
                child.conn.send((fn, shared, [items[i] for i in part], RETIRE))   # its line: this process's
                waiting[child.conn] = (child, part)
            except Exception:   # no child, or fn or its items don't pickle: here
                here += part
        while waiting:
            for conn in multiprocessing.connection.wait(list(waiting)):
                child, part = waiting.pop(conn)
                try:
                    kind, got = conn.recv()
                except Exception:   # it died, or its answer doesn't read here
                    kind, got = "failed", None
                    broken.append(child)
                if kind == "leaving":   # done, and the child ends: never kept idle
                    kind = "done"
                    broken.append(child)
                if kind == "done":
                    for i, value in zip(part, got):
                        results[i] = value
                    if tick is not None:
                        tick(len(part))
                else:
                    here += part
    finally:   # a child still at a part (this call was interrupted) is stopped, never kept with its answer due
        broken += [child for child, _ in waiting.values()]
        _give([child for child in children if child not in broken])
        for child in broken:
            child.stop()
    for i in sorted(here):   # in order: the first item that raises is the one a loop here meets first
        results[i] = fn(shared, items[i])
        if tick is not None:
            tick(1)
    return results


def later(fn: Callable, *args) -> Future:
    """``fn(*args)`` on a thread of its own, so the caller works on while it
    waits on children (Modkit's): its future."""
    pool = ThreadPoolExecutor(1)
    try:
        return pool.submit(fn, *args)
    finally:
        pool.shutdown(wait=False)


def install() -> int:
    """Hand the swap this pool (from two workers on; with one it runs as
    before, in order, here): the workers a call takes."""
    from azurkit.tools.characters import pool

    if (count := workers()) >= 2:
        pool.MAP, pool.LATER = map_, later
    return count


def stop() -> None:
    """Stop the idle children (the rest stop as their calls end)."""
    with _LOCK:
        idle = _IDLE[:]
        _IDLE.clear()
    for child in idle:
        child.stop()


def _peak() -> int:
    """This process's peak resident size in bytes, 0 where it can't be read
    (Windows, whose children stay, as before): macOS's ``getrusage``; Linux's
    ``VmHWM``, as its ``getrusage`` starts a spawned child at its parent's
    peak (exec keeps it), past the line whatever the child did."""
    if sys.platform == "darwin":
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    try:
        with open("/proc/self/status") as status:
            return next(int(line.split()[1]) * 1024 for line in status if line.startswith("VmHWM:"))
    except (OSError, StopIteration):
        return 0


def _work(conn) -> None:
    """A child: each part's results, or ``failed`` (its items then run in
    the parent), holding none of a part's inputs or results while it waits
    for the next; ``leaving`` with the results, then gone, once it has
    peaked at the line its parent sent with the part (the parent's
    :data:`RETIRE`) or past it."""
    from .engine import orphaned

    orphaned()
    while True:
        try:
            fn, shared, items, line = conn.recv()
        except (EOFError, OSError):
            return
        except Exception:   # a part that doesn't unpickle here
            conn.send(("failed", None))
            continue
        try:
            out = ("done", [fn(shared, item) for item in items])
        except BaseException:
            out = ("failed", None)
        fn = shared = items = None   # the part's inputs, never held while this child waits for the next part
        leaving = out[0] == "done" and _peak() >= line
        try:
            conn.send(("leaving", out[1]) if leaving else out)
        except Exception:   # results that don't pickle
            conn.send(("failed", None))
            leaving = False
        out = None   # nor its results
        if leaving:
            return
