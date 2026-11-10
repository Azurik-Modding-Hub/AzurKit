"""Lossless tick cuts in the reach engine's aimed jobs (Step R2.19a, from R2.17's emulator prototype; the pool's
workers take them with FastL3, ``devkit/reach/reach_engine.py --l3 fast``, by :func:`install`).

Two of an aimed job's L3 runs repeat ticks the job already stepped (``aim.run_job``; L3 is deterministic: the same
state and pads give the same rows and state):

- the second pass (``Aim``'s ``home``, the stick walked at the target once down) flies each first-pass launch again:
  until its first touch-down its controller gives the same pads (``home`` acts only after it).  So the first pass keeps
  the state and the controller at each launch's first touch-down, and the second resumes there; a first-pass launch
  that never touched down is the second pass's outcome as it stands (no tick);
- a hit's hold (``hold.replay``: its start placed again, its kit, its string, then ``hold.HOLD`` idle ticks) replays
  the string the simulator has just run: held from the launch's end instead, when the simulator still holds it, the
  same 60 idle ticks give the same answer (``same`` is the launch's own end), its ``ticks`` the replay's count (the
  placement's, the kit's and the string's ticks before the idle ones), so a record is ``aim.run_job``'s byte for
  byte whichever way it ran; :data:`STATS` counts what ran.

The driver cuts (Step R2.19l; every pool on both routes takes them, ``reach_engine.worker.setup``, by
:func:`install_driver`) give the same records with less work outside the launches:

- a launch's touches (``runner.outcome``'s ``Touch.at`` of each row's body centre) are found once a launch
  (:func:`touched`): each distinct position once, and ``Touch.at`` only for one a volume's box or a pickup's radius
  holds, every volume, pickup and position tested at once by the comparisons and elementwise float operations
  ``Touch.at`` makes;
- a placement's answer (``runner.place``: R6 and the 20-tick settle from the snapshot; the settled body's
  position, state and ``settled``, or that L3 faulted) is kept by a FastL3 worker (:func:`find_start`,
  :func:`stands`: ``aim``'s start searches and the floor and other-start scans, the kernel route's FastL3 stand
  tests too): a try whose kept answer doesn't stand is counted and not placed again, one that stands is placed
  again (its state starts the launches), a stand test reads it.  The key is the feet, the yaw, the cell and the
  simulator's mode (:data:`YAW_KEYED`: Step R2.19l's yaw check placed 10,500 points of seven levels at 4 yaws each
  and every answer was the same, bit for bit, but its bench's first e7 run stopped on 2 of 10,260 points two
  workers had placed at other yaws: a body that hangs off a ledge at 11 of 36 yaws, 12 answers, none standing).
  The answers persist (:func:`_store`): a file a
  worker process in the level's cache folder under the snapshot and the l3_impl (FastL3's code, library and
  switches) and the L3 core that gave them, each worker reading the others' new ones every :data:`STORE_S`, so
  every worker, stage and later run on the same code shares them.  About 1 kept answer in :data:`AUDIT_EVERY` is
  placed again at its own yaw and 1 batched launch in :data:`AUDIT_EVERY` tested row by row; a difference (or two
  answers for one key) stops the run (:class:`Drift`).  Base L3 places every time: its audit is the reference.

Records are the gate (Step R2.19a's bench: every record of round 1's four levels equal; Step R2.19l's: every record,
hold answer and edge of the kernel + backstop bench), so this file is in no cache key (``cache.AIM_FILES``).  So that
an edit to the code it copies (:data:`SHADOWS`, in those keys) can't leave the pool running the old copy under the
new key, :func:`install` and :func:`install_driver` each refuse while a source it copies has moved (:func:`stale`,
:data:`DRIVER_SHADOWS`): edit this file beside it, then pin its new hash.  Pure but for the simulator it drives.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import math
import os
import secrets
import time

import numpy as np

from devkit.reach.engine import aim, hold, macros, runner, worker
from devkit.reach.engine.macros import KITS, TICKS, Launch, _Run, _stepped, settled
from devkit.reach.engine.runner import START_XY, START_Z
from devkit.sim import faces, l3
from devkit.sim.l3 import L3Error, Pad, fault_site
from devkit.sim.l3_search import CAST_WAIT

_TOUCH: dict = {}       # this job's first-pass touch-downs: key -> (State, controller) or the whole Launch (no touch)
_HERE: list = [None]    # the outcome whose launch's end state the simulator holds now
_MOVED: list = [False]  # whether a hold has run the simulator since the last launches returned
_SECOND: list = [False] # whether this job may run a second pass (it stops, and aim.more says so)
STATS = {"resumed": 0, "reused": 0, "touch_saves": 0, "held_from_end": 0, "held_replayed": 0, "hold_ticks_cut": 0}
# The code the cuts copy or lean on and the sha256[:12] of its source when they last matched it (:func:`stale`):
# :func:`launches` copies ``macros.launches`` and the controllers' state (``_Run``, ``Aim``, ``Sched``) for a resume
# in ``aim.run_job``'s passes; :func:`run_macros` copies ``runner.run_macros``; :func:`replay` ``hold.replay`` and
# ``runner.set_kit``'s tick count; :func:`outcome` ``runner.outcome``'s touches, :func:`touched` ``Touch.at``,
# ``Volumes.holding``'s box and ``faces._spans``; :func:`find_start` and :func:`stands` copy theirs and lean on
# ``runner.place`` (from the snapshot: an answer is the placement's alone).
SHADOWS = {"macros.launches": "532616e695d1", "macros._Run": "0c03454d6eb9", "aim.Aim": "b44bb58d40d0",
           "aim.Sched": "3e601468d0b4", "aim.run_job": "67f26187b51b", "runner.run_macros": "2574e42b6605",
           "runner.set_kit": "5bef6ef8ca06", "hold.replay": "f17f2f1b17cf", "runner.outcome": "5236470f4546",
           "runner.Touch": "788833513dd4", "faces.Volumes.holding": "30a1a144cfd0",
           "runner.find_start": "edd55d59d8f4", "runner.place": "c3e2ea81827d", "aim.stands": "bbb40e2e4e0b",
           "faces._spans": "2008d1fe2e4c"}
_SHADOWED = {"macros.launches": macros.launches, "macros._Run": macros._Run, "aim.Aim": aim.Aim,
             "aim.Sched": aim.Sched, "aim.run_job": aim.run_job, "runner.run_macros": runner.run_macros,
             "runner.set_kit": runner.set_kit, "hold.replay": hold.replay, "runner.outcome": runner.outcome,
             "runner.Touch": runner.Touch, "faces.Volumes.holding": faces.Volumes.holding,
             "runner.find_start": runner.find_start, "runner.place": runner.place,
             "aim.stands": aim.stands, "faces._spans": faces._spans}   # as imported, before the installs
# The ones :func:`install_driver` copies or leans on (every pool, base too); :func:`install` copies the rest.
DRIVER_SHADOWS = ("runner.outcome", "runner.Touch", "faces.Volumes.holding", "faces._spans", "runner.find_start",
                  "runner.place", "aim.stands")


def stale(keys=None) -> list[str]:
    """The :data:`SHADOWS` (of ``keys``, default all) whose source has moved since this file was last checked
    against it."""
    return [k for k in (SHADOWS if keys is None else keys)
            if hashlib.sha256(inspect.getsource(_SHADOWED[k]).encode()).hexdigest()[:12] != SHADOWS[k]]


def _key(state, m, heading, cam, start, back, target, ctl) -> tuple:
    kw = getattr(ctl, "keywords", {}) or {}
    rest = tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in kw.items() if k != "home"))
    t = None if target is None else tuple(target)
    return (id(state), m, heading, cam, tuple(start), back, t, getattr(ctl, "func", ctl), rest)


def launches(sim, ms, heading, cam, start, back, *, target=None, ctl=None, state=None) -> tuple[list, int | None]:
    """``macros.launches`` with the first pass's touch-downs kept and the second's resumed (the module docstring):
    the launches, and the index of the one whose end state the simulator holds after (None: none)."""
    kw = getattr(ctl, "keywords", {}) or {}
    aimed = isinstance(getattr(ctl, "func", None), type) and issubclass(ctl.func, aim.Aim)
    record = aimed and _SECOND[0] and "home" in kw and kw["home"] is None and state is not None
    resume = aimed and kw.get("home") is not None and state is not None
    keys = [_key(state, m, heading, cam, start, back, target, ctl) for m in ms]
    runs = [(ctl or _Run)(m, heading, cam, start, back, target) for m in ms]
    ends, taints = ["ticks"] * len(ms), [frozenset()] * len(ms)
    out: list = [None] * len(ms)
    fresh, todo = [], []
    for i, k in enumerate(keys):
        got = _TOUCH.get(k) if resume else None
        if isinstance(got, Launch):                   # never touched down: the same launch, no tick
            out[i] = got
            STATS["reused"] += 1
        elif got is not None and got[0] is state:     # resumed at its first touch-down, its controller's copy
            _, st, c = got
            r = copy.copy(c)
            r.pads, r.rows, r.home = list(c.pads), list(c.rows), kw.get("home")
            runs[i] = r
            todo.append((st, [i], None))
            STATS["resumed"] += 1
        else:
            fresh.append(i)
    if fresh:
        todo.append((None, fresh, None))
    last = None
    while todo:
        st, group, pad = todo.pop()
        if st is not None:
            sim.reset(st)
        while group and len(runs[group[0]].rows) < TICKS:
            if pad is None:
                pads = [runs[i].pad() for i in group]
                pad = pads[0]
                apart = {}
                for i, p in zip(group, pads):
                    if p != pad:
                        apart.setdefault(p, []).append(i)
                if apart:
                    here = sim.save()
                    todo += [(here, g, p) for p, g in apart.items()]
                    group = [i for i, p in zip(group, pads) if p == pad]
            row = _stepped(sim, pad)
            if isinstance(row, str):
                for i in group:
                    ends[i] = row
                break
            saved = None
            for i in list(group):
                was = runs[i].first
                if (end := runs[i].seen(pad, row)) is not None:
                    ends[i], taints[i] = end, frozenset(getattr(sim, "taint", ()))
                    group.remove(i)
                    last = i
                elif record and was is None and runs[i].first is not None:   # its first touch-down, going on
                    if saved is None:
                        saved = sim.save()
                        STATS["touch_saves"] += 1
                    c = copy.copy(runs[i])
                    c.pads, c.rows = list(runs[i].pads), list(runs[i].rows)
                    _TOUCH[keys[i]] = (state, saved, c)
            pad = None
        for i in group:
            taints[i] = frozenset(getattr(sim, "taint", ()))
            if ends[i] == "ticks" and runs[i].settle is not None:
                ends[i] = "settled" if settled(runs[i].rows[-1]) else "unsettled"
            last = i
    for i in range(len(ms)):
        if out[i] is None:
            out[i] = Launch(runs[i].pads, runs[i].rows, ends[i], runs[i].first, taints[i])
            if record and runs[i].first is None:
                _TOUCH[keys[i]] = out[i]
    return out, (last if last is not None and out[last].first is not None else None)


def run_macros(sim, rec: dict, ms, heading: float, takeoff, starts: dict, cells, touch=None, *,
               find=runner.find_start, memo: dict | None = None, name: str = "", target=None, ctl=None,
               done=None) -> bool:
    """``runner.run_macros`` on :func:`launches` (its docstring); the outcome whose end the simulator holds is
    marked for :func:`replay`."""
    memo = {} if memo is None else memo
    ran = set()
    for n, m in enumerate(ms):
        if n in ran:
            continue
        family = [k for k in range(n, len(ms)) if k not in ran and ms[k]._replace(flaps=0) == m._replace(flaps=0)]
        ran.update(family)
        kind = "stand" if m.stands else "run"
        variant = kind + name
        if variant not in rec["starts"]:
            st = rec["starts"][variant] = find(sim, starts[kind], heading, cells)
            memo[variant] = sim.save() if "cell" in st else None
        if memo[variant] is None:
            continue
        st = rec["starts"][variant]
        if (variant, m.kit) not in memo:
            sim.reset(memo[variant])
            try:
                rows = runner.set_kit(sim, m.kit)
                turn, turned, cam = runner.align(sim, runner._cam(rows[-1]), heading)
            except L3Error:
                memo[(variant, m.kit)] = None
            else:
                memo[(variant, m.kit)] = (sim.save(), turn, turned, cam, rows[-1].hp,
                                          runner.witness_prefix(st["feet"], heading, st["cell"], m.kit))
        if (got := memo[(variant, m.kit)]) is None:
            continue
        state, turn, turned, cam, hp0, prefix = got
        back = ((takeoff[0] - st["feet"][0]) * -math.sin(heading)
                + (takeoff[1] - st["feet"][1]) * math.cos(heading))
        sim.reset(state)
        _HERE[0], _MOVED[0] = None, False
        gos, here = launches(sim, [ms[k] for k in family], heading, cam, tuple(st["feet"]), back,
                             target=None if target is None else target(m), ctl=ctl, state=state)
        k, stop = len(turn), False
        for j, (f, go) in enumerate(zip(family, gos)):
            o = runner.outcome(ms[f], turn + go.pads, turned + go.rows, go.end,
                               None if go.first is None else go.first + k, hp0, prefix, touch, go.taint) \
                | {"start": variant}
            rec["outcomes"].append(o)
            if j == here and not _MOVED[0]:
                _HERE[0] = o
            stop |= done is not None and done(o, st)
        _HERE[0] = None
        if stop:
            return True
    return False


_replay = hold.replay


def replay(sim, st: dict, heading: float, o: dict) -> dict:
    """``hold.replay``, held from the launch's end where the simulator still holds it (:func:`run_macros`)."""
    _MOVED[0] = True
    if _HERE[0] is not o:
        _HERE[0] = None
        STATS["held_replayed"] += 1
        return _replay(sim, st, heading, o)
    _HERE[0] = None
    STATS["held_from_end"] += 1
    before = (runner.SETTLE_START + 1 + (1 + CAST_WAIT if KITS[o["kit"]].get("air") else 0)   # runner.set_kit's
              + len(l3.pads(o["segments"])))
    STATS["hold_ticks_cut"] += before
    ticks = before
    try:
        row = None
        for _ in range(hold.HOLD):
            row, ticks = sim.step(Pad()), ticks + 1
    except L3Error as exc:
        return {"fault": str(getattr(exc, "site", "other")), "ticks": ticks}
    return {"land": list(runner._feet(row)), "state": row.state, "settled": settled(row), "same": True, "ticks": ticks}


_run_job = aim.run_job


def run_job(sim, job: dict, touch=None, here=None, zone_at=None) -> dict:
    """``aim.run_job`` with this job's touch-downs kept apart from the last job's."""
    _TOUCH.clear()
    _HERE[0] = None
    _SECOND[0] = job.get("stop") is not None and zone_at is not None and aim.more(job)
    try:
        return _run_job(sim, job, touch, here, zone_at)
    finally:
        _TOUCH.clear()
        _HERE[0] = None


def _refuse_stale(keys, escape: str = "") -> None:
    if moved := stale(keys):
        raise RuntimeError(f"reach_engine/fast.py copies {', '.join(moved)}, edited since: edit fast.py beside them "
                           f"and pin their new hashes in its SHADOWS{escape}")


def install() -> None:
    """Route ``aim``'s launches and holds through this module (a fast pool's worker setup, ``l3_pool.Pool``'s
    ``setup``); refused while :func:`stale` names one it copies (``--l3 base`` runs without them)."""
    _refuse_stale([k for k in SHADOWS if k not in DRIVER_SHADOWS], ", or run --l3 base")
    aim.run_macros = run_macros
    aim.run_job = run_job
    hold.replay = replay


# -- the driver cuts (Step R2.19l; the module docstring) -------------------------------------------------------------

AUDIT_EVERY = 200     # [PLAN-v3 R2.19l] about 1 kept placement answer and 1 batched launch in this many done again
YAW_KEYED = True      # [R2.19l's bench] a placement's answer is kept by its yaw too (the module docstring)
PICK_SLACK = 1e-6     # m: a pickup's box this much wider than its radius holds every point ``Touch.at`` finds near it
SPAN_ROWS = 256       # positions a volume's span test takes at once (memory: these x its faces)
KEPT_MAX = 400_000    # the answers a simulator keeps (the oldest go first): about 100 MB at most
STORE_S = 2.0         # a worker reads the answers other processes stored at most this often (s)
PLACED_ON: tuple = ()   # the simulator classes whose placement answers are kept (:func:`install_driver`)
DRIVER = {"launches": 0, "points": 0, "spanned": 0, "near_picks": 0, "touch_audits": 0, "placed": 0, "kept": 0,
          "skipped": 0, "place_audits": 0, "read": 0}   # this process's counts (the bench reads them)
_find_start, _stands, _outcome = runner.find_start, aim.stands, runner.outcome


class Drift(SystemExit):
    """A batched launch's touches or a kept placement answer that doing it again gives otherwise: the run stops (a
    ``SystemExit``: no job keeps it as its error, so the pool's caller raises it)."""


def _spans(V, P) -> np.ndarray:
    """``faces._spans`` of each point of ``P`` (n, 3) at once: its float64 operations, element for element, a point a
    row (no reduction, so each element is the one ``faces._spans`` computes for that point)."""
    a, b, c = V[:, 0], V[:, 1], V[:, 2]
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    ok = np.abs(d) > 1e-12
    d = np.where(ok, d, 1.0)
    px, py, pz = P[:, 0:1], P[:, 1:2], P[:, 2:3]
    l1 = ((b[:, 1] - c[:, 1]) * (px - c[:, 0]) + (c[:, 0] - b[:, 0]) * (py - c[:, 1])) / d
    l2 = ((c[:, 1] - a[:, 1]) * (px - c[:, 0]) + (a[:, 0] - c[:, 0]) * (py - c[:, 1])) / d
    l3 = 1.0 - l1 - l2
    m = ok & (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
    z = l1 * a[:, 2] + l2 * b[:, 2] + l3 * c[:, 2]
    return ((z >= pz) & m).any(axis=1) & ((z <= pz) & m).any(axis=1)


def touched(touch, rows) -> tuple[set, set]:
    """The volumes and pickups (ids) ``touch`` (``runner.Touch``) gives a launch's ``rows`` (``runner.outcome``'s:
    ``Touch.at`` of each row's body centre), found once a launch: each distinct position once; a volume whose box
    holds some (``Volumes.holding``'s comparisons, every volume and position at once) spans one (:func:`_spans`, its
    positions at once); a pickup within its radius of a position (``Touch.at``'s own test, for each position a box of
    the radius and :data:`PICK_SLACK` round a pickup holds); about 1 launch in :data:`AUDIT_EVERY` also row by row
    (``Touch.at``), a difference :class:`Drift`."""
    vols, picks = set(), set()
    pos = list(dict.fromkeys(r.pos for r in rows))
    DRIVER["launches"] += 1
    DRIVER["points"] += len(pos)
    if pos:
        P = np.asarray(pos, dtype=np.float64)
        Q = P[:, None]
        if touch.vol.ids:
            box = (touch.vol.lo <= Q).all(axis=2) & (Q <= touch.vol.hi).all(axis=2)
            for i in np.flatnonzero(box.any(axis=0)).tolist():
                k = np.flatnonzero(box[:, i])
                DRIVER["spanned"] += len(k)
                for j in range(0, len(k), SPAN_ROWS):
                    if _spans(touch.vol.V[i], P[k[j:j + SPAN_ROWS]]).any():
                        vols.add(touch.vol.ids[i])
                        break
        if len(touch.pick_pts):
            for j in np.flatnonzero((np.abs(touch.pick_pts - Q) <= touch.radius + PICK_SLACK)
                                    .all(axis=2).any(axis=1)).tolist():
                DRIVER["near_picks"] += 1
                p = np.asarray(pos[j], dtype=np.float64)
                picks.update(touch.pick_ids[i] for i in
                             np.nonzero(np.linalg.norm(touch.pick_pts - p, axis=1) <= touch.radius)[0])
    if DRIVER["launches"] % AUDIT_EVERY == 0:
        DRIVER["touch_audits"] += 1
        each = [touch.at(r.pos) for r in rows]
        if ({i for v, _ in each for i in v}, {i for _, p in each for i in p}) != (vols, picks):
            raise Drift("reach_engine.fast: a launch's touches found once differ from Touch.at's row by row: the run "
                        "stops (find why before another run)")
    return vols, picks


def outcome(m, pads, rows, end: str, first, hp0: int, place: bytes, touch, taint) -> dict:
    """``runner.outcome`` with the launch's touches found once (:func:`touched`)."""
    o = _outcome(m, pads, rows, end, first, hp0, place, None, taint)
    if touch is not None:
        vols, picks = touched(touch, rows)
        o["volumes"], o["picks"] = sorted(vols), sorted(picks)
    return o


def _at(sim, feet, yaw: float, cell) -> tuple:
    k = (getattr(sim, "scene", None), getattr(sim, "deep", None), tuple(float(v) for v in feet), int(cell))
    return k + (float(yaw),) if YAW_KEYED else k


def _store(sim) -> dict:
    """Where a simulator's placement answers persist (the module docstring), made and read whole on first use:
    ``placed/<the snapshot's meta sha12>-<sha12 of its l3_impl but the kernel's, and the L3 core's>`` in the level's
    cache folder (mode 700: answers hold positions), a file a process; no folder outside a pool worker (no
    ``worker.IMPL``) or for a simulator with no snapshot level."""
    st = sim.__dict__.get("_store")
    if st is None:
        impl = {k: v for k, v in worker.IMPL.items() if k != "kernel"}
        meta = getattr(getattr(sim, "snap", None), "meta", None) or {}
        st = sim.__dict__["_store"] = {"dir": None, "fd": None, "own": None, "seen": {}, "t": -math.inf}
        if impl and meta.get("level"):
            from devkit.reach.engine import cache
            d = (cache.folder(str(meta["level"]).rsplit("/", 1)[-1]) / "placed"
                 / f"{l3.meta_sha12(meta)}-{cache.sha12([impl, cache.core()])}")
            d.mkdir(mode=0o700, parents=True, exist_ok=True)
            d.parent.chmod(0o700)
            st["dir"] = d
    return st


def _keep(sim, key: tuple, got: tuple, write: bool) -> None:
    """``got`` kept for ``key`` (the oldest dropped past :data:`KEPT_MAX`), and with ``write`` added to the store; a
    different answer kept for it already is :class:`Drift`."""
    memo = sim.__dict__.setdefault("_placed", {})
    if (was := memo.get(key)) is not None:
        if repr(was) != repr(got):                     # repr: bit for bit (a -0.0, a NaN)
            raise Drift("reach_engine.fast: a placement's answer differs from the one kept for it: the run stops "
                        "(find why before another run; a yaw that matters: YAW_KEYED)")
        return
    if len(memo) >= KEPT_MAX:
        del memo[next(iter(memo))]
    memo[key] = got
    if write and (st := _store(sim))["dir"] is not None:
        if st["fd"] is None:
            st["own"] = f"{os.getpid()}-{secrets.token_hex(4)}.jsonl"
            st["fd"] = os.open(st["dir"] / st["own"], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.write(st["fd"], (json.dumps([list(key), list(got)]) + "\n").encode())


def _read(sim) -> None:
    """The answers the other processes added to this simulator's store since its last read (at most every
    :data:`STORE_S`; a line not yet whole waits for the next)."""
    st = _store(sim)
    if st["dir"] is None or (now := time.monotonic()) - st["t"] < STORE_S:
        return
    st["t"] = now
    for e in os.scandir(st["dir"]):   # a size from the file itself: Windows' listing gives the size a file had when
        # last closed, not what the process that still has it open has written since
        if e.name == st["own"] or not e.name.endswith(".jsonl") or os.stat(e.path).st_size <= st["seen"].get(e.name, 0):
            continue
        with open(e.path, "rb") as f:
            f.seek(off := st["seen"].get(e.name, 0))
            data = f.read()
        data = data[:data.rfind(b"\n") + 1]
        st["seen"][e.name] = off + len(data)
        for line in data.splitlines():
            k, a = json.loads(line)
            _keep(sim, (k[0], k[1], tuple(k[2]), *k[3:]), tuple(a) if a[0] == "fault" else (tuple(a[0]), *a[1:]),
                  False)
            DRIVER["read"] += 1


def _place(sim, feet, yaw: float, cell, kept: tuple | None = None) -> tuple:
    """``runner.place`` now: its answer (the settled row's ``(pos, state, settled)``, or ``("fault", site)``) and
    row (None on a fault), the answer kept and stored (not a step the watchdog stopped for time: the host's, not
    the game's); one that isn't ``kept`` (an answer kept for the same key) is :class:`Drift`."""
    DRIVER["placed"] += 1
    try:
        r = runner.place(sim, feet, yaw, cell)
    except L3Error as exc:
        got, r = ("fault", fault_site(exc)), None
        if got[1].startswith(worker.TIME_SITES):
            return got, r
    else:
        got = (tuple(r.pos), r.state, bool(aim.settled(r)))
    if kept is not None and repr(got) != repr(kept):
        raise Drift("reach_engine.fast: a placement placed again differs from its kept answer: the run stops (find "
                    "why before another run; a yaw that matters: YAW_KEYED)")
    _keep(sim, _at(sim, feet, yaw, cell), got, kept is None)
    return got, r


def _kept(sim, feet, yaw: float, cell) -> tuple | None:
    """The answer kept for this placement (:func:`_place`, the store's: :func:`_read`), else None; about 1 in
    :data:`AUDIT_EVERY` placed again at ``yaw`` first (a difference is :class:`Drift`)."""
    _read(sim)
    got = sim.__dict__.get("_placed", {}).get(_at(sim, feet, yaw, cell))
    if got is not None:
        DRIVER["kept"] += 1
        if DRIVER["kept"] % AUDIT_EVERY == 0:
            DRIVER["place_audits"] += 1
            _place(sim, feet, yaw, cell, got)
    return got


def _stood(got: tuple, f, ok) -> bool:
    """``runner.find_start``'s test of a placement's answer ``got`` onto ``f``."""
    if got[0] == "fault":
        return False
    pos, state, _ = got
    g = (pos[0], pos[1], pos[2] - 1.0)
    return (state == 0 and math.hypot(g[0] - f[0], g[1] - f[1]) <= START_XY and abs(g[2] - f[2]) <= START_Z
            and (ok is None or ok(g)))


def find_start(sim, feet_list, heading: float, cells, ok=None, tries: int = 0) -> dict:
    """``runner.find_start`` (``aim``'s start searches) with the placements' answers kept on a simulator of
    :data:`PLACED_ON` (the module docstring): a try whose kept answer doesn't stand is counted, not placed again."""
    if not isinstance(sim, PLACED_ON):
        return _find_start(sim, feet_list, heading, cells, ok, tries)
    for f in feet_list:
        for c in cells:
            tries += 1
            if (got := _kept(sim, f, heading, c)) is not None and not _stood(got, f, ok):
                DRIVER["skipped"] += 1
                continue
            got, r = _place(sim, f, heading, c, got)
            if _stood(got, f, ok):
                return {"feet": list(f), "cell": int(c), "settled": list(runner._feet(r)), "tries": tries,
                        "hp": r.hp, "cam": runner._cam(r), "place_sha12": runner.place_sha12(f, heading, c)}
    return {"tries": tries}


def stands(sim, p, heading: float, cells) -> tuple | None:
    """``aim.stands`` (the floor and other-start scans' test, the kernel route's FastL3 one) with the placements'
    answers kept on a simulator of :data:`PLACED_ON` (the module docstring)."""
    if not isinstance(sim, PLACED_ON):
        return _stands(sim, p, heading, cells)
    for c in cells:
        if (got := _kept(sim, p, heading, c)) is None:
            got = _place(sim, p, heading, c)[0]
        if got[0] == "fault":
            continue
        pos, state, still = got
        g = (pos[0], pos[1], pos[2] - 1.0)
        if still and math.hypot(g[0] - p[0], g[1] - p[1]) <= START_XY and abs(g[2] - p[2]) <= START_Z:
            return g, state
    return None


def install_driver(on: tuple | None = None) -> None:
    """Route every launch's outcome through :func:`outcome` and ``aim``'s start searches and stand tests through
    :func:`find_start` and :func:`stands`, keeping the placement answers of simulators of ``on`` (default FastL3's):
    every pool worker's setup (``worker.setup``, both routes); refused while :func:`stale` names one of
    :data:`DRIVER_SHADOWS`."""
    global PLACED_ON
    _refuse_stale(DRIVER_SHADOWS)
    if on is None:
        from devkit.reach.l3_fast import FastL3
        on = (FastL3,)
    PLACED_ON = tuple(on)
    runner.outcome = outcome
    aim.find_start, aim.stands = find_start, stands
