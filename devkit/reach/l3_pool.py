"""A persistent L3 worker pool per snapshot (Step X.10, D173's T5): many searches at once over the machine's cores.

A :class:`Pool` starts its processes once (``spawn``); each loads the snapshot once (a format 2 file's pages are a
read-only mapping, so every worker shares one copy in the page cache), builds an :class:`~devkit.sim.l3.L3`
per mode on first use and keeps goals by their spec, then serves tasks from one queue.  Every task starts from the
snapshot (``L3.reset()``; each step starts from the snapshot's CPU state), so a task's result depends only on its
arguments, never on which worker ran it or what it ran before: the same problems and seeds give the same winners
whatever the worker count.

:func:`solve_many` runs many search problems (each a :class:`Problem`: a start, a goal, limits, seeds) on one pool:
every seed of every problem is a task; a problem's winner is its lowest seed index that reached (as
:func:`devkit.sim.l3_search.solve`), decided once every lower index has finished, and its seeds still running
are then stopped between rounds (a shared flag) and the rest never start; only then is the winner graded, its
robustness trials (``l3_search.jittered``) run as tasks of their own across the pool (Step R1.16: no other seed's
string is graded, and a whole-step winner's eight trials take one trial's time).  The pool runs under
:class:`~devkit.xemu.queue.BatchToken`: while an xemu sitting waits for a slot it keeps one task in flight.
Errors stay with their seed (Step X.52): a seed whose start raises ``L3Error`` in its worker (a hang, a fault) is a
run that failed at its start (``why`` ``start: <the error>``, its site counted), and any other error a task raises
is that seed's run (``error: ...``, its site counted) or that trial's (``trial_errors`` on the winner, its robustness
the share of the trials that ran), so the batch goes on; only a broken pool ends it.  A failed run is tainted
(``failed:start``, ``failed:error``): it refutes nothing.  A pool started ``fast`` (Step R2.19a: the reach engine's)
builds :class:`~devkit.reach.l3_fast.FastL3` with no overlay, player ticks and (since Step R2.19b's whole-step
compare) whole steps (its steps, rows and memory are L3's; an overlay stays on L3), and runs its ``setup`` (a
module-level function) once in each worker.
Dev tooling (Unicorn is a dev dependency).
"""

from __future__ import annotations

import collections
import importlib
import json
import multiprocessing as mp
import os
import time
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from devkit.sim import l3, obs
from devkit.sim.l3_search import (Limits, Result, Segment, derived_seed, jittered, problem_sha12, search,
                                      seg_list, start_of, trial)

SLOTS = 4096          # stop flags: one per problem in flight (solve_many takes problems in batches of this many)
OVERLAYS = 4          # a worker keeps the simulators of this many overlays (a bisection's neighbours)
STARTS = 4            # a worker keeps this many problems' start states (a winner's trials share one)
_W: Worker | None = None


def default_workers() -> int:
    """The worker count by default: the cores, at most 16 (this Mac's performance cores)."""
    return max(1, min(16, os.cpu_count() or 1))


class Worker:
    """A pool process's state: the snapshot (loaded once), an L3 per mode and goals by spec, built on first use."""

    def __init__(self, label: str, store, xbe: bytes, stop, disc=None, fast: bool = False, setup=None) -> None:
        self.snap = l3.read_snapshot(l3.snapshot_path(label, store))
        self.xbe, self.stop, self.pid, self.disc, self.fast = xbe, stop, os.getpid(), disc, fast
        if setup is not None:
            setup()
        self._sims: dict[tuple, l3.L3] = {}
        self._goals: dict[str, object] = {}
        self._starts: dict[str, tuple] = {}

    def sim(self, scene: bool = False, deep: bool = True, overlay=None, fresh: bool = False) -> l3.L3:
        """The L3 of mode ``scene`` (with ``overlay``, a build laid over the snapshot:
        :mod:`devkit.sim.overlay`), reset to its start; ``deep`` observations or not (``L3.deep``); with
        ``fresh`` a new one that has never run (a reset doesn't undo all of a run: Step R2.19h1's toggled decks
        moved or not by what the worker's scene L3 had run before).  The last :data:`OVERLAYS` overlays'
        simulators are kept."""
        key = (scene, None if overlay is None else overlay.sha12)
        if fresh:
            self._sims.pop(key, None)
        if key not in self._sims:
            if overlay is not None and sum(k[1] is not None for k in self._sims) >= OVERLAYS:
                del self._sims[next(k for k in self._sims if k[1] is not None)]
            make = l3.L3
            if self.fast and overlay is None:
                from devkit.reach.l3_fast import FastL3 as make
            self._sims[key] = make(self.snap, self.xbe, scene=scene, overlay=overlay, disc=self.disc)
        sim = self._sims[key]
        sim.reset()
        sim.deep = deep
        return sim

    def goal(self, spec: dict):
        """The goal ``spec`` names (``{"module", "factory", "kwargs"}``), built once per worker."""
        key = json.dumps(spec, sort_keys=True)
        if key not in self._goals:
            self._goals[key] = getattr(importlib.import_module(spec["module"]), spec["factory"])(**spec["kwargs"])
        return self._goals[key]

    def start(self, seg: Segment, problem: str) -> tuple:
        """(the simulator, ``seg``'s start state, its camera yaw) for ``problem`` (its name), the start set up once
        (a back leg's prefix is a whole first leg) for the last :data:`STARTS` problems."""
        sim = self.sim(seg.scene, deep=False, overlay=seg.overlay)
        if problem not in self._starts:
            if len(self._starts) >= STARTS:
                del self._starts[next(iter(self._starts))]
            start, _, cam, _, _ = start_of(sim, seg)
            self._starts[problem] = (start, cam)
        return (sim, *self._starts[problem])


def _init(label, store, xbe, stop, disc, fast=False, setup=None) -> None:
    global _W
    _W = Worker(label, store, xbe, stop, disc, fast, setup)


def _call(fn: Callable, args: tuple):
    return fn(_W, *args)


class Pool:
    """``workers`` processes serving tasks on snapshot ``snapshot`` (a label in the private store ``store``) under
    ``xbe``, the game's file reads served from ``disc`` (the image in the tray: ``L3``'s ``disc``, a path).  A task
    is a module-level ``fn(worker, *args)``.  A pool started while a spawned process still imports its parent's
    main module (multiprocessing's ``_inheriting``, set before ``parent_process()`` is) is refused at once: that is
    a script without an ``if __name__ == "__main__":`` guard, which every worker it spawns would run again."""

    def __init__(self, snapshot: str, xbe: bytes, *, store: str | Path | None = None, workers: int | None = None,
                 name: str = "l3 pool", disc: str | Path | None = None, fast: bool = False,
                 setup: Callable | None = None) -> None:
        if getattr(mp.current_process(), "_inheriting", False):   # multiprocessing's own "importing main" test
            raise RuntimeError(f"an L3 pool ({name}) started inside a spawned worker process: the script that starts "
                               "it runs again in each worker it spawns; put its top-level code under "
                               "'if __name__ == \"__main__\":'")
        l3.read_meta(l3.snapshot_path(snapshot, store))           # a bad label fails here, not in every worker
        self.snapshot, self.store, self.name, self.fast = snapshot, None if store is None else str(store), name, fast
        self.workers = workers or default_workers()
        ctx = mp.get_context("spawn")
        self.stop = ctx.Array("b", SLOTS, lock=False)
        self._ex = ProcessPoolExecutor(self.workers, mp_context=ctx, initializer=_init,
                                       initargs=(snapshot, self.store, xbe, self.stop,
                                                 None if disc is None else str(disc), fast, setup))

    def __enter__(self) -> Pool:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        self._ex.shutdown(wait=True, cancel_futures=True)

    def submit(self, fn: Callable, *args):
        return self._ex.submit(_call, fn, args)

    def map(self, fn: Callable, argses) -> list:
        """``[fn(worker, *args) for args in argses]``, run on the pool under a :class:`BatchToken`."""
        from devkit.xemu.queue import BatchToken
        with BatchToken(self.name, self.workers) as tok:
            return list(tok.ordered(self._ex, _call, [(fn, tuple(a)) for a in argses]))

    def completed(self, fn: Callable, argses):
        """``fn(worker, *args)`` for each ``args`` of ``argses``, yielded as each finishes (in no set order), run on
        the pool under a :class:`BatchToken`: a caller that counts as results come keeps every worker busy to the
        end, where a :meth:`map` a chunk waits on the chunk's slowest task."""
        from devkit.xemu.queue import BatchToken
        with BatchToken(self.name, self.workers) as tok:
            for f in tok.completed(self._ex, _call, [(fn, tuple(a)) for a in argses]):
                yield f.result()


# -- tasks -------------------------------------------------------------------------------------------------------------

def pids(w: Worker) -> int:
    """The worker's process id (a test sees the pool keep its processes)."""
    return w.pid


def trace(w: Worker, scene: bool, segments: list[dict], writes=()) -> tuple[list[tuple], str | None]:
    """An input string (``l3.pads`` segments) run from the snapshot, ``writes`` ([k, va, hex] each) at their
    ticks: per row its k, state, HP, the digests of its body centre, state and HP (``obs.CORE``) and of its whole
    observation (no positions) and its taint; and the ``L3Error`` that ended it early, if one did."""
    sim = w.sim(scene)
    extra = collections.defaultdict(list)
    for k, va, data in writes:
        extra[k].append((va, bytes.fromhex(data)))
    out = []
    for k, pad in enumerate(l3.pads(segments)):
        try:
            r = sim.step(pad, writes=extra.get(k, ()))
        except l3.L3Error as e:
            return out, f"tick {k}: {e}"
        out.append((r.k, r.state, r.hp, obs.digest(r.obs, obs.CORE), obs.digest(r.obs), tuple(sorted(r.taint))))
    return out, None


@dataclass
class Problem:
    """A search problem: ``seg``'s start (its snapshot the pool's), the goal factory's spec, the search's limits,
    ``seeds`` searches (seed ``i`` derived from the problem), seed strings every search tries first and the
    robustness trials of its winner (the lowest seed index that reached; no other is graded)."""
    seg: Segment
    goal_spec: dict
    limits: Limits = field(default_factory=Limits)
    seeds: int = 8
    strings: list = field(default_factory=list)
    trials: int = 16
    rate: float = 30.0       # the build's frame rate its winner's trials jitter at (``l3_search.jittered``, AZ-388)


def _failed(i: int, seed: int, why: str, exc=None, sim=None) -> dict:
    """A seed's run that never searched (Step X.52): ``why``, the error's site and the run's taint, tainted
    ``failed:<start or error>`` too (a run that never searched is no refutation)."""
    res = Result(False, why=why, taint={f"failed:{why.split(':')[0]}"})
    if exc is not None:
        res.fault(exc)
        res.seen(sim)
    return {"index": i, "seed": seed, **res.summary(), "segs": [], "cam": 0.0, "start_cost_s": None,
            "start_zone": None, "on_graph": None}


def search_task(w: Worker, seg: Segment, goal_spec: dict, limits: Limits, i: int, seed: int, strings,
                slot: int) -> dict:
    """One seed's Go-Explore from ``seg``'s start: its summary (counts and taint), string and camera yaw; it stops
    between rounds once the problem's flag ``slot`` is set.  A start that raises ``L3Error`` here fails the run at
    its start (``start: <the error>``)."""
    sim = w.sim(seg.scene, deep=False, overlay=seg.overlay)
    goal = w.goal(goal_spec)
    try:
        start, row, cam, _, _ = start_of(sim, seg)
    except l3.L3Error as exc:
        return _failed(i, seed, f"start: {exc}", exc, sim)
    res = search(sim, start, row, goal, limits, cam=cam, seed=seed, seeds=strings, stop=lambda: w.stop[slot])
    return {"index": i, "seed": seed, **res.summary(), "segs": [seg_list(x) for x in res.segs], "cam": cam,
            "start_cost_s": round(goal.cost(row), 1), "start_zone": goal.zone(row) if hasattr(goal, "zone") else None,
            "on_graph": goal.finite_at(row) if hasattr(goal, "finite_at") else None}


def trial_task(w: Worker, seg: Segment, goal_spec: dict, problem: str, jit: list, cam: float) -> bool:
    """One robustness trial of a winner (a jittered copy, ``l3_search.jittered``) from ``seg``'s start."""
    sim, start, _ = w.start(seg, problem)
    return trial(sim, start, jit, w.goal(goal_spec), cam=cam)


def solve_many(pool: Pool, problems: list[Problem]) -> list[dict]:
    """Each problem's search (the module docstring), all on ``pool`` at once: per problem, the winner (its
    segments, the camera yaw it starts from, its robustness: the share of its trials that reach) or every seed's
    reason, the runs up to the winner (counts and taint only) and the seconds from its first task to its verdict
    (the winner graded)."""
    out: list[dict] = []
    for b in range(0, len(problems), SLOTS):
        out += _solve_batch(pool, problems[b:b + SLOTS])
    return out


def _solve_batch(pool: Pool, problems: list[Problem]) -> list[dict]:
    from devkit.xemu.queue import BatchToken
    for p in problems:
        if (p.seg.snapshot, p.seg.store and str(p.seg.store)) != (pool.snapshot, pool.store):
            raise ValueError(f"a problem starts at snapshot {p.seg.snapshot!r}; this pool serves {pool.snapshot!r}")
    names = [problem_sha12(p.seg, p.goal_spec, p.limits) for p in problems]
    todo = collections.deque((i, j) for i, p in enumerate(problems) for j in range(p.seeds))
    grading: collections.deque = collections.deque()     # (problem, jittered copy): a decided winner's trials, first
    graded: dict[int, list[int]] = {}                     # problem -> [trials that reached, trials left]
    runs: list[dict[int, dict]] = [{} for _ in problems]
    win: list[int | None] = [None] * len(problems)     # the winner's index, -1 for none, None while undecided
    t0: dict[int, float] = {}
    t1: dict[int, float] = {}
    for i in range(len(problems)):
        pool.stop[i] = 0

    def decide(i: int) -> None:
        for j in range(problems[i].seeds):
            if j not in runs[i]:
                return
            if runs[i][j]["reached"]:
                win[i] = j
                break
        else:
            win[i] = -1
        pool.stop[i] = 1                                 # its seeds still running stop at their next round
        w = runs[i].get(win[i])
        if w is not None and problems[i].trials > 0:     # grade the winner alone, its trials across the pool
            graded[i] = [0, problems[i].trials]
            grading.extend((i, jit) for jit in jittered(w["segs"], trials=problems[i].trials, seed=w["seed"],
                                                        rate=problems[i].rate))
        else:
            if w is not None:
                w["robustness"] = None
            t1[i] = time.monotonic()

    running: dict = {}
    with BatchToken(pool.name, pool.workers) as tok:
        while todo or grading or running:
            while (todo or grading) and len(running) < tok.allowed():
                if grading:
                    i, jit = grading.popleft()
                    p = problems[i]
                    running[pool.submit(trial_task, p.seg, p.goal_spec, names[i], [list(x) for x in jit],
                                        runs[i][win[i]]["cam"])] = (i, None)
                    continue
                i, j = todo.popleft()
                if win[i] is not None:
                    continue
                p = problems[i]
                t0.setdefault(i, time.monotonic())
                running[pool.submit(search_task, p.seg, p.goal_spec, p.limits, j, derived_seed(names[i], j),
                                    [[tuple(x) for x in s] for s in p.strings], i)] = (i, j)
            if not running:
                continue
            done = tok.wait(running)
            for f in done:
                i, j = running.pop(f)
                try:
                    got, err = f.result(), None
                except BrokenExecutor:
                    raise
                except Exception as exc:                 # the task's own error stays with its seed or trial
                    got, err = None, exc
                if j is None:                            # a winner's trial (one that raised: not graded)
                    g, won = graded[i], runs[i][win[i]]
                    g[0], g[1] = g[0] + bool(got), g[1] - 1
                    if err is not None:
                        won["trial_errors"] = won.get("trial_errors", 0) + 1
                    if not g[1]:
                        ran = problems[i].trials - won.get("trial_errors", 0)
                        won["robustness"] = g[0] / ran if ran else 0.0
                        t1[i] = time.monotonic()
                    continue
                runs[i][j] = got if err is None else _failed(j, derived_seed(names[i], j),
                                                             f"error: {type(err).__name__}: {err}", err)
                if win[i] is None:
                    decide(i)
    out = []
    for i, name in enumerate(names):
        last = win[i] if win[i] >= 0 else problems[i].seeds - 1
        rs = [runs[i][j] for j in range(last + 1)]
        w = rs[-1] if win[i] >= 0 else None
        out.append({"problem": name, "engine": l3.engine(), "reached": w is not None,
                    "seconds": round(t1[i] - t0[i], 1), "winner": w,
                    "runs": [{k: v for k, v in r.items() if k not in ("segs", "cam")} for r in rs]})
    return out
