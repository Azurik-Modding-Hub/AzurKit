"""The app's process pool (Step 4.3i): the swap's parallel work
(``tools.characters.pool``'s :data:`~azurkit.tools.characters.pool.MAP` and
``LATER``) and a shaped fill's attempts on threads (:class:`Beside`, the
planner's ``fill.BESIDE``), which the engine may not hold itself
(``tests/test_contracts.py``), in the app's engine process (:mod:`.engine`).

Modkit's split (``azurik_mod/assets/pool.py``): a call's items in up to
:func:`workers` parts, runs of the order, or by their cost the dearest first,
each to the part with the least, a part a spawned child. The results are the
function's on each item in order, whichever child ran it, so what a build
writes doesn't depend on the split; a part whose child fails runs here, in
order, raising here what the function raises. The children stay for the next
call (at most :func:`workers` idle; one that grew past :data:`RETIRE` leaves
after its part), end with their parent (they watch it),
and pass their work through pipes alone: no semaphore, so a killed engine
leaves none behind. :func:`workers` caps the children busy at once across
the process, not a call's alone: a ``later``'s call shares them with the
call it runs beside (:data:`_BUSY`), so ``$AZURKIT_CORES`` caps what the
process runs on (one finished is idle at once, for the call beside it). A
call never waits for them: with none free it takes one child past the cap,
so a small ask beside a dress answers within its 3 s. A costed call at
the click's priority that would start a child runs what it can of its items here first, within
:data:`SMALL` (a child costs more to start than such items to run). A
part of a low call (:class:`Low`: work ahead no click follows yet, D1007)
runs low in its child, and a :func:`later` thread as its caller does."""

from __future__ import annotations

import multiprocessing
import multiprocessing.connection
import os
import sys
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor

from azurkit.core import host, progress

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
SMALL = 0.25
"""CPU seconds: a call of two items or more with a ``cost``, not low, that finds
fewer children idle than it would split over runs its items here, the
cheapest first, while they stay under this (:func:`_small`), and splits the rest.
A child costs about 0.16 CPU-s to start: a G4 match's one map (35 clips,
1-3 ms each) started 16 for 2.6 CPU-s (Step 4.4bh). 0: every call splits."""
CLOCK = time.perf_counter if sys.platform == "win32" else time.process_time
"""What :func:`_small` times an item by: this process's CPU seconds, which a
busy computer doesn't stretch; on Windows the wall clock, as its CPU clock
(``GetProcessTimes``) moves only at each tick of about 15.6 ms: an item
under one read 0, and the next one's guess and the rest's floor with it,
so a dear item ran here (Step 4.4bh). A busy Windows splits sooner."""

_CONTEXT = multiprocessing.get_context("spawn")
_IDLE: list[_Child] = []
_LOCK = threading.Lock()
_THREAD = threading.local()   # .low: the thread's Low is down (lowered())


class Low:
    """A thread's background priority (``core.host``), lowered and put
    back on that thread alone (made on it: an OS sets a thread's own)."""

    def __init__(self):
        self.thread, self.was, self.on, self.stuck = threading.current_thread(), None, False, False

    def __call__(self, on: bool) -> None:
        """Lower the thread (``on``) or put it back, once each way."""
        if threading.current_thread() is not self.thread or on == self.on:
            return
        if on:
            self.was, self.on = host.background(), True
            _THREAD.low = self.was is not None
        else:
            self.on = False
            self.stuck = self.stuck or self.was is not None and not host.foreground(self.was)   # POSIX's: no way back
            _THREAD.low = self.stuck


def lowered() -> bool:
    """Whether the calling thread's :class:`Low` holds it low."""
    return getattr(_THREAD, "low", False)


def inherit() -> Callable[[], object]:
    """What a thread the caller starts calls first, to run as low as the
    caller does now: a thread starts at normal priority on macOS and Windows
    whatever its starter's. It ends low: that thread's its own."""
    low = lowered()
    return lambda: Low()(low)


def workers() -> int:
    """``min(MOST, this process's CPUs, $AZURKIT_CORES)``; a value of it
    that isn't a positive whole number is not a cap."""
    most = min(MOST, os.process_cpu_count() or 1)
    try:
        cap = int(os.environ.get(CORES, ""))
    except ValueError:
        return most
    return min(most, cap) if cap > 0 else most


class _Budget:
    """The children busy at once in this process (each call's parts), at
    most :func:`workers` but a call's one: :meth:`take` takes up to ``want``
    of those free, and one when none is, never waiting for a part elsewhere;
    :meth:`give` hands one back as its part comes home."""

    def __init__(self):
        self.busy, self.lock = 0, threading.Lock()

    def take(self, want: int) -> int:
        with self.lock:
            got = max(1, min(want, workers() - self.busy))
            self.busy += got
            return got

    def give(self, count: int = 1) -> None:
        with self.lock:
            self.busy -= count


_BUSY = _Budget()


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


def _small(fn: Callable, shared, items: list, cost: Callable[[int], float] | None,
           tick: Callable[[int], object] | None, results: list) -> list[int]:
    """The indices of ``items`` :func:`map_` has left to split, once a
    costed call that would start a child ran here, into ``results``, the
    items it could (:data:`SMALL`): in rising ``cost``, each while what they
    took (:data:`CLOCK`: this process's CPU seconds, which a busy computer
    doesn't stretch) and the next one's guess (the last one's by its ``cost``) or
    the rest's floor (the least one's each) come under it; none left when
    all did. A call with no ``cost`` splits as before: its first item may
    be its dearest (paint's two bakes take about 9 s each); so does a low
    one (:func:`lowered`: work ahead), whose items here would hold this
    process's GIL beside the call a player waits on (a model's pictures
    asked while the pick's dress runs ahead, A30, +0.07 s)."""
    if SMALL <= 0 or cost is None or len(items) < 2 or lowered() or len(_IDLE) >= min(workers(), len(items)):
        return list(range(len(items)))
    order = sorted(range(len(items)), key=lambda n: (cost(n), n))
    done, spent, least = set(), 0.0, float("inf")
    for k, n in enumerate(order):
        began = CLOCK()
        try:
            results[n] = fn(shared, items[n])
        except Exception:   # it raises in its turn, as a part's
            break
        took = CLOCK() - began
        done.add(n)
        if tick is not None:
            tick(1)
        if k + 1 == len(order):
            return []
        spent, least = spent + took, min(least, took)
        guess = took * cost(order[k + 1]) / cost(n) if cost(n) > 0 else SMALL
        if spent + max(guess, least * (len(order) - k - 1)) >= SMALL:
            break
    return [n for n in range(len(items)) if n not in done]


def map_(fn: Callable, shared, items: list, cost: Callable[[int], float] | None = None,
         tick: Callable[[int], object] | None = None) -> list:
    """``[fn(shared, item) for item in items]``, split over children (the
    module's docstring), or here when small (:data:`SMALL`); ``tick(k)``
    as each part's ``k`` items come back."""
    results: list = [None] * len(items)
    if not (left := _small(fn, shared, items, cost, tick, results)):
        return results
    held, low = _BUSY.take(min(workers(), len(left))), lowered()
    children, here, broken, waiting = [], [], [], {}
    try:
        parts = [[left[i] for i in part] for part in _split(len(left), held, None if cost is None else
                                                            lambda i: cost(left[i])) if part]
        _BUSY.give(held - len(parts))
        held = len(parts)
        children = _take(len(parts))
        for n, part in enumerate(parts):
            child = children[n] if n < len(children) else None
            try:
                if child is None:
                    raise OSError("no child")
                child.conn.send((fn, shared, [items[i] for i in part], RETIRE, low))   # its line: this process's
                waiting[child.conn] = (child, part)
            except Exception:   # no child, or fn or its items don't pickle: here
                here += part
                held -= 1
                _BUSY.give()
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
                if child not in broken:   # idle before its share goes back, so a call beside this one takes it
                    children.remove(child)
                    _give([child])
                held -= 1
                _BUSY.give()
                if kind == "done":
                    for i, value in zip(part, got):
                        results[i] = value
                    if tick is not None:
                        tick(len(part))
                else:
                    here += part
    finally:   # a child still at a part (this call was interrupted) is stopped, never kept with its answer due
        _BUSY.give(held)
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
    pool = ThreadPoolExecutor(1, initializer=inherit())
    try:
        return pool.submit(fn, *args)
    finally:
        pool.shutdown(wait=False)


class _Stopped(BaseException):
    """A fill has no more use for this thread's work (:class:`Beside`)."""


class Beside:
    """A shaped fill's work on threads beside its own (``fill.BESIDE``; its reaches leave the GIL): each job as soon as
    a thread is free, its answer read in order on the fill's thread, so what it decides is one thread's, at any width.
    That thread tells its notes meanwhile (``tick``: records, so cancel points); leaving, or :meth:`again`, stops what
    runs at its next note and what hasn't begun. Each thread runs as low as the fill's did at its last hand-out or
    wait (:class:`Low`): a click the fill hears at any note between two waits reaches them."""

    def __init__(self, width: int, tick: Callable[[], None]) -> None:
        self.width, self.tick, self.low = width, tick, lowered()
        self._open()

    def _open(self) -> None:
        self.stop, self.local = threading.Event(), threading.local()
        self.pool = ThreadPoolExecutor(self.width, thread_name_prefix="azurkit-attempt")

    def _close(self) -> None:
        self.stop.set()
        self.pool.shutdown(wait=False, cancel_futures=True)

    def __enter__(self) -> Beside:
        return self

    def __exit__(self, *_) -> None:
        self._close()

    def submit(self, fn: Callable, item) -> Future:
        self.low = lowered()
        return self.pool.submit(self._job, self.stop, self.local, fn, item)

    def _job(self, stop: threading.Event, local: threading.local, fn: Callable, item):
        if (low := getattr(local, "low", None)) is None:
            low = local.low = Low()

        def heard(_step: dict) -> None:
            if stop.is_set():
                raise _Stopped
            low(self.low)
        with progress.noting(progress.Steps(heard)) as steps:
            steps("plan")
            return fn(item)

    def answer(self, future: Future):
        """``future``'s answer, once it has one (its error raises here, in its turn)."""
        while True:
            self.low = lowered()   # each pass: a click at a candidate's note too, not only at a tick
            try:
                return future.result(0.1)
            except TimeoutError:
                self.tick()

    def again(self, fn: Callable, items: Sequence) -> list:
        """``fn`` of each of ``items``, what ran before dropped."""
        self._close()
        self._open()
        return [self.answer(future) for future in [self.submit(fn, item) for item in items]]


def install() -> int:
    """Hand the swap this pool (from two workers on; with one it runs as
    before, in order, here), and the sdk's hash pools :func:`inherit`: the
    workers a call takes."""
    from azurkit import sdk
    from azurkit.tools.characters import pool

    sdk.INHERIT = inherit
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


def _work(conn) -> None:
    """A child: each part's results, or ``failed`` (its items then run in
    the parent), holding none of a part's inputs or results while it waits
    for the next; ``leaving`` with the results, then gone, once it has
    peaked (``host.peak``) at the line its parent sent with the part (the
    parent's :data:`RETIRE`) or past it, or after a low part where POSIX's nice has
    no way back (it would answer the next click's parts low)."""
    from .engine import orphaned

    orphaned()
    while True:
        try:
            fn, shared, items, line, low = conn.recv()
        except (EOFError, OSError):
            return
        except Exception:   # a part that doesn't unpickle here
            conn.send(("failed", None))
            continue
        was = host.background() if low else None
        try:
            out = ("done", [fn(shared, item) for item in items])
        except BaseException:
            out = ("failed", None)
        host.foreground(was)
        fn = shared = items = None   # the part's inputs, never held while this child waits for the next part
        leaving = out[0] == "done" and (host.peak() >= line or low and sys.platform not in ("darwin", "win32"))
        try:
            conn.send(("leaving", out[1]) if leaving else out)
        except Exception:   # results that don't pickle
            conn.send(("failed", None))
            leaving = False
        out = None   # nor its results
        if leaving:
            return
