"""Step R2.19h1: rigs, lifts and toggled solids in the reach engine's first all-level run (the R2.19 plan's
§R2.19h, D845, D847).  A rig is a solid platform owner a link moves (``triggers.Triggers.rigs``).

**The recorder** (:func:`record`): :data:`RECORD` whole steps (scene and player, FastL3) from a level's start
snapshot with the pad at rest, each rig's deck read where the game collides with it each tick
(``triggers.Runtime.deck``/``pose``): its pose table.  A deck **moves** when a corner of its box leaves its first
pose by :data:`EPS`; it **cycles** with the least lag at which every corner comes back within :data:`PERIOD_M` over
the whole recording (its period), else its table is a **path** held at its last row.  A wired rig that stands still
is **toggled** by RAM pokes (:func:`poked`: ``Triggers.tries``, each term of its start in turn, a pad's pulse
released :data:`RELEASE` ticks then held :data:`PULSE`, R2.19h2's witness) and recorded the same way from the poke,
up to :data:`POKE_TICKS` or :data:`REST` still ticks.  Cached per snapshot (:func:`recording`), private.

**Deciding a deck** (:func:`decide`, D847): ``cycles``, ``path`` (it moves from load), ``static`` (never moves: the
frozen world is the game's), ``toggled`` (a term of its start moved it: the link carries that term; a mover's own
input only, the start's whole condition) are decided; ``parked``, by name with its reason, is every other: an
undecoded start (``Start.leaves``), a read start no poke moved, no collision object.  A parked rig makes no rig link,
and a witness touching one parked for an undecoded trigger is out of logic (D847, :class:`Router`) until a rigs-only
re-run decodes it.

**Hops and links** (:func:`search`, the order of work, never a witness): on the native kernel with every decided
moving deck posed at the clock (``reach_native.World.movers``), from each zone's :data:`TAKEOFFS_N` takeoffs nearest
a deck (within :data:`RANGE_M`, :data:`DROP_M` under to :data:`RISE_M` over it), every :data:`EVERY` th tick of its
span (a cycle, or the path and its rest), headed at the deck's centre and :data:`TURN` either side, the engine's
R0 launches (``macros.launches`` under ``runner``'s start, kit and align, ``backend.KernelSim``): a **board** lands
on the deck (the feet on a top face of it at that tick); from a body put on the deck's top the same way, an
**alight** settles in another zone; a **link** joins them by the ride window: a board's landing ridden on the kernel
(the deck carries it) to each later tick an alight of its kit landed from, its launch run from where the body is.

**The witness** (D845, :func:`trip`): every counted rig link is a FastL3 whole-step **trip** from the snapshot (the
toggled deck's pokes at tick 0, idle whole steps to the phase, R6 onto the start, the kit, the string: board, ride,
alight, then ``hold.HOLD`` idle ticks) that boards the deck and stays in the to-zone.  A hop is made the same way
(board: the feet on the deck at its live pose on any tick; alight: the to-zone held).  The truth sample
(:func:`truth`) is FastL3's own controllers in whole steps from random takeoffs, headings, launches and phases.

**The router** (:class:`Router`, :func:`replay_trip`), on a zone witness: one whose path touches a rig parked for
an undecoded trigger is out of logic, its confirm's touches too, kept or not (D847: its pair takes its next
candidate); of those its frozen-world hold kept (a trip only restricts: no trip rescues one the hold or the kernel
confirm dropped), one touching another parked rig keeps its witness and names the rig (``parked``, PLAN-v2 §1.5d,
a trip's witness too); one a rig moving within its window touches at its load
pose, or crosses on its swept path (:func:`sweep_task`: its path's boxes against the rig's posed box each row of the
window, swept only where it passes within :data:`NEAR_XY` of where the rig goes), is replayed in whole steps from the
snapshot, idle first for each :data:`EVERY` th tick up to :data:`PHASES` tries (the phase loop): it counts only where
one stays, and its witness then owes that idle wait before its R6 (``wait``); one no moving rig meets keeps its
frozen-world witness.

Positions, poses and strings stay in memory and the private cache; outputs hold names, counts, ticks and sha12s.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import struct
from pathlib import Path

import numpy as np

from devkit.reach.engine import cache, runner
from devkit.reach.engine.macros import AIRBORNE, BACK_RUN, BACK_STAND, KITS, R0, align, launches, settled
from devkit.sim import l3
from devkit.sim.l3 import L3Error, Pad

RECORD = 3600        # [the plan's] whole steps a level's recording runs (2 min; a5's longest cycle is 3,240)
EVERY = 15           # [the plan's] a phase every half second of a deck's span
EPS = 0.05           # [R2.19h2's] a deck moved: a box corner this far from its first pose
PERIOD_M = 0.02      # [the prototype's] a cycle: every corner back within this at the lag, the whole recording
REST = 30            # [R2.19h2's] a poked deck at rest: no corner 2 cm a tick for this many ticks
POKE_TICKS = 900     # [proposal] a poked run's whole steps at most
RELEASE, PULSE = 3, 6   # [R2.19h2's] a pad's pulse held at 0 these ticks, then at 1 these
POKE_TRIES = 3       # [R2.19h2's] a start's terms tried in turn, then the movers' own inputs
CAP_US = 120_000_000    # [R2.19h2's] a whole step's wall-clock cap (a stream load under load: rig_triggers.py)
RANGE_M = 14.0       # [the prototype's] a takeoff this near a deck's swept footprint (XY) boards it
DROP_M, RISE_M = 17.0, 6.0   # [the prototype's envelope] a takeoff's feet at most this over / under a deck's top
TAKEOFFS_N = 4       # [the prototype's] a zone's takeoffs nearest a deck that board it
TURN = math.radians(25.0)    # [the prototype's] the headings: at the deck and this either side
TOP_NZ = 0.8         # a deck's top faces (posed)
ON_DZ = 0.15         # [proposal] feet this near a posed top face over it stand on the deck
BEST = 2             # [proposal] the board hits a hop keeps for the ride (distinct phases, fewest ticks first)
TRIPS = 3            # [proposal] a link's kernel candidates tried in whole steps, best first, until one holds
PHASES = 8           # [proposal] the router's phase loop: a routed witness tried after this many waits at most
OFF_TICKS = 30       # [proposal] a ride ends once the body has been off the deck this many ticks
END_M = 0.5          # [backend's] a whole-step replay this near its witness's landing is the same launch
NEAR_XY = 6.0        # [proposal] a witness's points this near (across) where a moving rig goes: its path is swept
SWEEP_TICKS = 10     # [proposal] a swept path's ticks a box
EVERYWHERE = [[-1e9] * 3 + [1e9] * 3]   # a sweep that faulted: its path may be anywhere (every moving rig near it)
DECIDED = ("cycles", "path", "static", "toggled")


def load(level: str):
    """``level``'s ``geometry.Level`` and its :class:`~.triggers.Triggers` (R2.19h2's reading of its wiring)."""
    from devkit.sim.ports import resolve_vanilla_iso
    from devkit.rando.draft.export import derive_inputs
    from azurkit.tools.randomizer.draft.geometry import Level
    from azurkit.tools.randomizer.draft.wiring import Wiring
    from azurkit.tools.randomizer.planner.loader import load_database
    from devkit.reach.engine.triggers import Triggers
    db = load_database()
    lv = Level.read(resolve_vanilla_iso(), level)
    ins = derive_inputs(level, db.tricks, db.levels.get(level, {}), db.generated)
    return lv, Triggers(lv, Wiring(lv, db.generated.get(level, {}), ins["level"]))


def _code12(*parts) -> str:
    """sha256[:12] of the L3 core, ``triggers.py`` and ``parts`` (functions by their source, else their repr)."""
    import inspect
    root = Path(__file__).resolve().parents[3]
    h = hashlib.sha256(cache.core().encode() + cache.code_bytes(root / "devkit/reach/engine/triggers.py"))
    for x in parts:
        h.update((inspect.getsource(x) if callable(x) else repr(x)).encode())
    return h.hexdigest()[:12]


def code12() -> str:
    """The recording's code (its cache key): the recorder's functions and constants, the triggers' reading and the
    L3 core (the search and the trips change no recording)."""
    return _code12(record, poked, _steps, _local, _corners, posed, recording, fresh, record_task, poke_task,
                   (RECORD, EPS, REST, POKE_TICKS, RELEASE, PULSE, POKE_TRIES, CAP_US, PULSE_PLUGS))


def trip_code12() -> str:
    """The router's trips' code (their answers' cache key, beside the recording's sha12)."""
    return _code12(replay_trip, Clock, _place, _steps, fresh, trip_hold_task, (EVERY, PHASES, END_M, CAP_US))


# -- the recorder ---------------------------------------------------------------------------------------------------

def _local(lv, oi: int) -> np.ndarray:
    """Owner ``oi``'s triangles in its own frame (its load-time world matrix's inverse, column vectors)."""
    W = np.array(lv.owners[oi]["world"], dtype=np.float64)
    P = lv.P[lv.tris_of(oi)].reshape(-1, 3)
    return ((np.linalg.inv(W) @ np.c_[P, np.ones(len(P))].T)[:3].T).reshape(-1, 3, 3)


def _corners(loc: np.ndarray) -> np.ndarray:
    pts = loc.reshape(-1, 3)
    lo, hi = pts.min(0), pts.max(0)
    return np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
                    + [pts.mean(0)])


def posed(c: np.ndarray, M) -> np.ndarray:
    """Local points ``c`` (n, 3) at pose row ``M`` (16 floats, row vectors)."""
    M = np.asarray(M, dtype=np.float64).reshape(4, 4)
    return c @ M[:3, :3] + M[3, :3]


def _steps(sim, n: int, read, rt=None, pokes=(), stop=None):
    """``n`` whole steps at rest (``pokes`` held: a pulse released :data:`RELEASE` ticks, then all :data:`PULSE`),
    ``read()`` after each; (the reads, why it stopped).  ``stop(reads)``: True ends the run."""
    out, why = [read()], "ticks"
    free = [q._replace(value=0.0) for q in pokes if q.plug in PULSE_PLUGS]
    if rt is not None and pokes:
        rt.hold(free)
    try:
        for k in range(n):
            if rt is not None and pokes:
                if k == RELEASE:
                    rt.hold(list(pokes))
                if k == RELEASE + PULSE:
                    rt.hold([])
            sim.step(Pad(), timeout_us=CAP_US)
            out.append(read())
            if stop is not None and stop(out):
                why = "rest"
                break
    except l3.LevelExit:
        why = "level exit"
    except L3Error as e:
        why = f"fault: {l3.fault_site(e)}"
    if rt is not None:
        rt.hold([])
    return out, why


PULSE_PLUGS = ("touch", "actionButton", "whack", "joystickOn", "magic", "teleported")


def record(sim, lv, T, ticks: int = RECORD) -> dict:
    """The baseline (the module docstring) on scene FastL3 ``sim``: per rig with a collision object, its pose rows
    (``ticks`` + 1, 16) float32; and the rigs with none."""
    from devkit.reach.engine.triggers import Runtime
    sim.reset()
    rt = Runtime(sim, lv)
    objs, none = {}, []
    for oi in T.rigs():
        o = lv.owners[oi]
        obj = rt.deck(o["G"], o["R"]) if o["G"] in rt.graph else None
        (none.append(oi) if obj is None else objs.__setitem__(oi, obj))
    keys = list(objs)

    def read():
        return [rt.pose(objs[oi]) for oi in keys]
    rows, why = _steps(sim, ticks, read)
    arr = np.asarray(rows, dtype=np.float32)                      # (n, decks, 16)
    sim.reset()
    return {"poses": {oi: arr[:, j] for j, oi in enumerate(keys)}, "none": none, "stop": why,
            "steps": len(rows) - 1}


def period(C: np.ndarray) -> int | None:
    """The least lag at which every corner of ``C`` ((n, k, 3): a deck's posed corners a tick) comes back within
    :data:`PERIOD_M` over the whole table, None when none under half of it."""
    n = len(C)
    back = np.nonzero(np.abs(C - C[0]).max(axis=(1, 2)) <= PERIOD_M)[0]
    for L in back[back >= EVERY]:
        if L > n // 2:
            break
        if np.abs(C[L:] - C[:-L]).max() <= PERIOD_M:
            return int(L)
    return None


def moved(C: np.ndarray) -> float:
    return float(np.linalg.norm(C - C[0], axis=-1).max()) if len(C) else 0.0


def poked(make, lv, T, oi: int, base: np.ndarray, ticks: int = POKE_TICKS) -> dict:
    """Rig ``oi``'s toggled recording (the module docstring), each try on a scene FastL3 that has never run
    (``make()``: :func:`fresh`), ``base`` its baseline poses: the first try (``Triggers.tries``) whose run takes its
    deck :data:`EPS` off the baseline, run on to rest: its poses from the snapshot, the term (``plug:name``), whether
    it was the start's own (``condition``) or a mover's input (``source``), the tick it left and the try's stop;
    ``witnessed`` False when none did."""
    from devkit.reach.engine.triggers import Runtime
    o = lv.owners[oi]
    c = _corners(_local(lv, oi))
    bc = np.array([posed(c, M) for M in base])
    out = {"witnessed": False, "tries": []}
    for pokes in T.tries(oi)[:POKE_TRIES]:
        sim = make()
        rt = Runtime(sim, lv)
        obj = rt.deck(o["G"], o["R"])
        state = {"at": None, "still": 0}

        def stop(rows):
            k = len(rows) - 1
            v = posed(c, rows[-1])
            ref = bc[min(k, len(bc) - 1)]
            if state["at"] is None:
                if np.linalg.norm(v - ref, axis=-1).max() > EPS:
                    state["at"] = k
                return False
            state["still"] = state["still"] + 1 if np.linalg.norm(v - posed(c, rows[-2]), axis=-1).max() < 0.02 else 0
            return state["still"] >= REST
        rows, why = _steps(sim, ticks, lambda: rt.pose(obj), rt, pokes, stop)
        term = sorted(f"{p.plug}:{lv.graphs[p.G].names[p.R]}" for p in pokes)
        of = "+".join(sorted({p.of for p in pokes}))
        out["tries"].append({"term": term, "of": of, "tick": state["at"], "stop": why, "steps": len(rows) - 1})
        if state["at"] is not None:
            out.update(witnessed=True, poses=np.asarray(rows, dtype=np.float32), term=term, of=of, tick=state["at"],
                       pokes=[tuple(p) for p in pokes])
            break
    return out


def decide(lv, T, rec: dict, toggles: dict) -> dict:
    """Each rig's verdict (the module docstring; D847): ``how`` (``cycles``, ``path``, ``static``, ``toggled``,
    ``parked``), ``why`` (a parked rig's reason, by name), its start's kind, ``period``, ``moved_m`` (the farthest
    a box corner went), a toggled rig's ``term`` and ``of``.  ``rec`` :func:`record`'s, ``toggles`` :func:`poked`'s
    by rig (those tried)."""
    out = {}
    for oi in T.rigs():
        o, st = lv.owners[oi], T.rig(oi)
        d = {"name": o["name"], "start": st.kind + (" (partial)" if st.kind == "wired" and st.leaves else ""),
             "leaves": sorted(st.leaves)}
        if oi in rec["none"]:
            out[oi] = d | {"how": "parked", "why": "no collision object"}
            continue
        c = _corners(_local(lv, oi))
        C = np.array([posed(c, M) for M in rec["poses"][oi]])
        mv = moved(C)
        d["moved_m"] = round(mv, 2)
        if mv > EPS:
            per = period(C)
            d |= {"how": "cycles", "period": per} if per else {"how": "path"}
        elif st.kind == "undecoded":
            d |= {"how": "parked", "why": "trigger undecoded: " + ", ".join(sorted(st.leaves))}
        elif st.kind in ("load", "never"):
            d["how"] = "static"
        elif oi not in toggles:
            d |= {"how": "parked", "why": "trigger read, not poked (not a deck of a hop)"}
        elif not toggles[oi]["witnessed"]:
            d |= {"how": "parked", "why": "trigger read, no poke moved it"}
        else:
            t = toggles[oi]
            d |= {"how": "toggled", "term": t["term"], "of": t["of"], "tick": t["tick"],
                  "moved_m": round(moved(np.array([posed(c, M) for M in t["poses"]])), 2)}
        out[oi] = d
    return out


def recording(level: str, snap: dict, pool=None, decks=None) -> tuple[dict, dict, str]:
    """``level``'s recording on snapshot ``snap`` (:func:`record`, and :func:`poked` for each of ``decks`` (owner
    ids; default every exported rig) that is read but stands still), made once per snapshot and code into the
    level's cache folder (``pool``, a fast L3 pool on ``snap``, asked only then): (its doc, the verdicts
    :func:`decide` gives, its sha12)."""
    import gzip
    import pickle
    p = cache.folder(level) / f"rigs-{snap['meta_sha12']}-{code12()}.pkl.gz"
    if p.exists():
        doc = pickle.loads(gzip.decompress(p.read_bytes()))
    else:
        if pool is None:
            raise FileNotFoundError(f"{level}: no rig recording for this snapshot and code (run the rigs stage)")
        rec = pool.map(record_task, [(level,)])[0]
        lv, T = load(level)
        if decks is None:
            from devkit.rando.draft.author import read_derived
            decks = T.exported(read_derived(level).get("rigs", []))
        want = [oi for oi in decks if oi in rec["poses"] and T.rig(oi).kind in ("wired",)
                and moved(np.array([posed(_corners(_local(lv, oi)), M) for M in rec["poses"][oi]])) <= EPS]
        toggles = dict(zip(want, pool.map(poke_task, [(level, oi, rec["poses"][oi]) for oi in want]))) if want else {}
        doc = {"level": level, "snapshot": snap["label"], "rec": rec, "toggles": toggles}
        cache.write_bytes(p, gzip.compress(pickle.dumps(doc, protocol=pickle.HIGHEST_PROTOCOL), 6, mtime=0))
    lv, T = load(level)
    return doc, decide(lv, T, doc["rec"], doc["toggles"]), hashlib.sha256(p.read_bytes()).hexdigest()[:12]


# -- pool tasks (module level: ``l3_pool.Pool`` runs them in its workers) ----------------------------------------

_LV: dict = {}


def _level(level: str):
    if _LV.get("name") != level:
        _LV.clear()
        _LV.update(name=level, lt=load(level))
    return _LV["lt"]


def fresh(w):
    """Pool worker ``w``'s scene FastL3, new (``l3_pool.Worker.sim``'s ``fresh``: about 1.4 CPU-s with its first
    steps) and :func:`capped`: a reset doesn't undo all of a long run (R2.19h1's fix: w1's polySurfaceShape459 poke
    moved its deck on a new scene FastL3, twice on one, and not after a 3,600-step recording on it), so every run
    the stage and the router count starts on one."""
    return capped(w.sim(True, deep=False, fresh=True))


def record_task(w, level: str) -> dict:
    lv, T = _level(level)
    return record(fresh(w), lv, T)


def poke_task(w, level: str, oi: int, base) -> dict:
    lv, T = _level(level)
    return poked(lambda: fresh(w), lv, T, oi, base)


# -- the decks in the kernel ---------------------------------------------------------------------------------------

class Deck:
    """A decided moving deck: its owner, its triangles in its frame, its pose table and span (``cyc``: a cycle of
    ``span`` rows; else a path, its rest the last row), its pokes (a toggled deck's, at tick 0)."""

    def __init__(self, lv, oi: int, verdict: dict, rows, pokes=()) -> None:
        self.oi, self.name, self.how = oi, verdict["name"], verdict["how"]
        self.local = _local(lv, oi)
        self.rows = np.asarray(rows, dtype=np.float64).reshape(-1, 16)
        self.cyc = verdict.get("period") is not None
        self.span = int(verdict["period"]) if self.cyc else len(self.rows)
        self.pokes = list(pokes)
        n = np.cross(self.local[:, 1] - self.local[:, 0], self.local[:, 2] - self.local[:, 0])
        self._n = n / np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]

    def row(self, t: int) -> np.ndarray:
        k = t % self.span if self.cyc else min(max(t, 0), len(self.rows) - 1)
        return self.rows[k]

    def top(self, t: int) -> np.ndarray:
        """The deck's top faces at tick ``t`` (world, (k, 3, 3))."""
        M = self.row(t).reshape(4, 4)
        up = (self._n @ M[:3, :3])[:, 2] >= TOP_NZ
        return self.local[up] @ M[:3, :3] + M[3, :3]

    def centre(self, t: int) -> np.ndarray:
        top = self.top(t)
        return top.reshape(-1, 3).mean(0) if len(top) else posed(self.local.reshape(-1, 3), self.row(t)).mean(0)

    def on(self, feet, t: int) -> bool:
        """Whether ``feet`` stand on a top face of the deck at tick ``t`` (over it, within :data:`ON_DZ`)."""
        return _over(self.top(t), feet)

    def phases(self) -> range:
        return range(0, self.span + (0 if self.cyc else 1), EVERY)


def _until_rest(rows, lv, oi: int, path: bool):
    """A path's rows up to :data:`EVERY` ticks past its last move (it rests there: the table holds its last row);
    a cycle's whole."""
    if not path:
        return rows
    c = _corners(_local(lv, oi))
    C = np.array([posed(c, M) for M in rows])
    step = np.linalg.norm(np.diff(C, axis=0), axis=-1).max(-1) if len(C) > 1 else np.zeros(0)
    last = int(np.nonzero(step > 0.002)[0].max()) + 1 if (step > 0.002).any() else 0
    return rows[: min(len(rows), last + EVERY + 1)]


def _over(tris: np.ndarray, p) -> bool:
    if not len(tris):
        return False
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    x, y = p[0], p[1]

    def side(u, v):
        return (v[:, 0] - u[:, 0]) * (y - u[:, 1]) - (v[:, 1] - u[:, 1]) * (x - u[:, 0])
    s0, s1, s2 = side(a, b), side(b, c), side(c, a)
    inside = ((s0 >= 0) & (s1 >= 0) & (s2 >= 0)) | ((s0 <= 0) & (s1 <= 0) & (s2 <= 0))
    if not inside.any():
        return False
    n = np.cross(b - a, c - a)
    ok = inside & (np.abs(n[:, 2]) > 1e-9)
    z = a[:, 2] - (n[:, 0] * (x - a[:, 0]) + n[:, 1] * (y - a[:, 1])) / np.where(ok, n[:, 2], 1.0)
    return bool((ok & (np.abs(p[2] - z) <= ON_DZ)).any())


def exported(level: str) -> list[int]:
    """The derive's exported rigs of ``level`` (``Triggers.exported``: MOVES' 166 over all levels, R2.19h2's unit)."""
    from devkit.rando.draft.author import read_derived
    return _level(level)[1].exported(read_derived(level).get("rigs", []))


def decks(level: str, doc: dict, verdicts: dict, only=None) -> list[Deck]:
    """The decided moving decks (cycles, path, toggled) of a recording (:func:`recording`) among ``only`` (owner
    ids; default the derive's exported rigs, :func:`exported`: the stage's decks [default D115]; the other rig
    owners are recorded and decided, searched once the router routes a witness to one)."""
    lv, _ = _level(level)
    only = set(exported(level) if only is None else only)
    out = []
    for oi, v in sorted(verdicts.items()):
        if oi not in only:
            continue
        if v["how"] in ("cycles", "path"):
            out.append(Deck(lv, oi, v, _until_rest(doc["rec"]["poses"][oi], lv, oi, v["how"] == "path")))
        elif v["how"] == "toggled":
            t = doc["toggles"][oi]
            from devkit.reach.engine.triggers import Poke
            out.append(Deck(lv, oi, v, t["poses"], [Poke(*p) for p in t["pokes"]]))
    return out


_KW: dict = {}


def kernel_world(level: str, absent, ds: list[Deck]):
    """The level's kernel world less its rigs and the census's ``absent`` platforms (its faces' springboard heights
    beside), the decks ``ds`` its movers (once a process per level and deck set); its push and water volumes set."""
    from devkit.reach import native as N
    k = (level, tuple(sorted(absent)), tuple(d.oi for d in ds))
    if _KW.get("k") != k:
        lv, T = _level(level)
        gone = sorted(set(absent) | set(T.rigs()))
        w = N.World(*N.solid(lv, gone), spring=N.springs(lv, gone))
        w.movers([d.local for d in ds], [lv.tri_word[lv.tris_of(d.oi)] for d in ds], [d.rows for d in ds],
                 [d.cyc for d in ds], [N.spring_of(lv.owners[d.oi]) for d in ds])
        _KW.clear()
        _KW.update(k=k, w=w, f=N.Fields(N.fields(lv)))
    _KW["w"].fields(_KW["f"])
    return _KW["w"]


def _rigsim(l3sim, w, base):
    """A ``backend.KernelSim`` whose placements start at the clock ``phase`` and whose flags end the candidate."""
    from devkit.reach.native import backend as KB

    class RigSim(KB.KernelSim):
        phase = 0

        def teleport(self, feet, yaw, *, cell=None):
            row = super().teleport(feet, yaw, cell=cell)
            self.p.tick = self.phase + 1          # R6's own tick is a whole step of the world too
            return row

        def to_l3(self):
            raise KB.Flagged("the kernel stops", "kernel:start")

    return RigSim(l3sim, w, base)


def _family(ms):
    out = {}
    for m in ms:
        out.setdefault(m._replace(flaps=0), []).append(m)
    return list(out.values())


def _start(ks, nodes, t, heading: float, stands: bool, zone, cells):
    feet = nodes.starts(t, heading, BACK_STAND if stands else BACK_RUN, zone)
    return runner.find_start(ks, feet, heading, cells)


def _launch(ks, st, heading: float, fam, takeoff=None):
    """``fam`` (macros differing in flaps) from start ``st`` on ``ks``: their launches, the clock at the launch's
    start and the pads from the placement's settle on (kit, align)."""
    kit = runner.set_kit(ks, fam[0].kit)
    turn, _, cam = align(ks, runner._cam(kit[-1]), heading)
    t0 = int(ks.p.tick)
    feet = tuple(st["feet"])
    tk = takeoff if takeoff is not None else feet
    back = (tk[0] - feet[0]) * -math.sin(heading) + (tk[1] - feet[1]) * math.cos(heading)
    ks.launching = True
    try:
        gos = launches(ks, fam, heading, cam, feet, back)
    finally:
        ks.launching = False
    return gos, t0, turn


def _boarded(deck: Deck, go, t0: int) -> int | None:
    """The row index at which ``go`` (a launch from clock ``t0``, from a start off the deck) first stands on
    ``deck``: a jump, a fall or a walk onto it (a deck flush with the floor)."""
    for j, r in enumerate(go.rows):
        if r.state not in AIRBORNE and deck.on(runner._feet(r), t0 + j + 1):
            return j
    return None


def off_decks(lv, takeoffs) -> list:
    """``takeoffs`` less those whose feet stand on a rig's top at its load pose (the frozen world's deck regions:
    a body there is on the deck already, so it neither boards it nor is somewhere to alight)."""
    from azurkit.tools.randomizer.draft.geometry import CAT_RIG
    rig = np.array([o["cat"] == CAT_RIG and o["kind"] != "levl" for o in lv.owners])[lv.tri_owner]
    tops = lv.P[rig & (lv.tri_nz >= TOP_NZ)]
    return [t for t in takeoffs if not _over(tops, t.feet)]


def capped(sim):
    """``sim`` (a scene FastL3) with every step under :data:`CAP_US` unless a call names its own cap: L3's own caps
    are wall-clock (a render's 5 s), and a step that loads from the stream maps each allocation as a region, slower
    the more a process has mapped, so under load a trip's step passed one and the trip ended at a fault no game
    made (R2.19h2's finding; here a fifth of a5's truth trials)."""
    if not getattr(sim, "_capped", False):
        step = sim.step

        def step_capped(pad=Pad(), **k):
            k.setdefault("timeout_us", CAP_US)
            return step(pad, **k)
        sim.step, sim._capped = step_capped, True
    return sim


def near(nodes, deck: Deck, takeoffs) -> dict:
    """Each zone's :data:`TAKEOFFS_N` takeoffs nearest ``deck``'s swept footprint (the module docstring)."""
    pts = np.concatenate([deck.top(t).reshape(-1, 3) for t in deck.phases()] or [np.zeros((0, 3))])
    if not len(pts):
        return {}
    lo, hi = pts.min(0), pts.max(0)
    by: dict = {}
    for t in takeoffs:
        f = t.feet
        dx = max(lo[0] - f[0], 0.0, f[0] - hi[0])
        dy = max(lo[1] - f[1], 0.0, f[1] - hi[1])
        if math.hypot(dx, dy) > RANGE_M or not (lo[2] - DROP_M <= f[2] <= hi[2] + RISE_M):
            continue
        z = nodes.zone_at(f, False, False)
        if z is not None:
            by.setdefault(z, []).append((math.hypot(dx, dy), t))
    return {z: [t for _, t in sorted(v, key=lambda x: (x[0], x[1].i))[:TAKEOFFS_N]] for z, v in by.items()}


def _toward(src, dst) -> float:
    return math.atan2(-(dst[0] - src[0]), dst[1] - src[1])


def search(ks, nodes, deck: Deck, takeoffs, kits=("k0", "air3")) -> dict:
    """The kernel's hops and links round ``deck`` (the module docstring; ``ks`` a :func:`_rigsim` on the world
    whose mover ``deck.m`` is the deck): ``board`` hits by from-zone, ``alight`` hits by to-zone, ``links`` by
    (from, to), each a candidate the trips run (private: feet, headings, pads)."""
    zones = near(nodes, deck, takeoffs)
    m = getattr(deck, "m", 0)
    board, alight, links = {}, {}, {}
    fams = [f for f in _family(R0) if f[0].kit in kits]
    for za, ts in zones.items():
        for ph in deck.phases():
            c = deck.centre(ph)
            for t in ts:
                for dh in (0.0, TURN, -TURN):
                    h = _toward(t.feet, c) + dh
                    for fam in fams:
                        ks.phase = ph
                        st = _start(ks, nodes, t, h, fam[0].stands, za, t.cells)
                        if "cell" not in st:
                            continue
                        if deck.on(st["settled"], int(ks.p.tick)):
                            continue                      # this start stands on the deck now
                        try:
                            gos, t0, turn = _launch(ks, st, h, fam, t.feet)
                        except L3Error:
                            continue
                        for mac, go in zip(fam, gos):
                            j = _boarded(deck, go, t0)
                            if j is not None:
                                stays = go.end == "settled" and deck.on(runner._feet(go.rows[-1]), t0 + len(go.rows))
                                board.setdefault(za, []).append(
                                    {"phase": ph, "feet": st["feet"], "cell": st["cell"], "yaw": h, "kit": mac.kit,
                                     "macro": mac.name, "pads": turn + go.pads, "at": t0 + j + 1, "ticks": len(go.rows),
                                     "stays": stays, "takeoff": t.i})
    for ph in deck.phases():
        top = deck.top(ph)
        if not len(top):
            continue
        feet = tuple(top.reshape(-1, 3).mean(0))
        for zb, ts in zones.items():
            goal = min((t.feet for t in ts), key=lambda f: math.dist(f, feet))
            for dh in (0.0, TURN, -TURN):
                h = _toward(feet, goal) + dh
                for fam in fams:
                    ks.phase = ph
                    st = _on_deck(ks, deck, feet, h, ts[0].cells[0], m)
                    if st is None:
                        continue
                    try:
                        gos, t0, turn = _launch(ks, st, h, fam)
                    except L3Error:
                        continue
                    for mac, go in zip(fam, gos):
                        last = go.rows[-1] if go.rows else None
                        if last is None or go.end != "settled":
                            continue
                        if nodes.zone_at(runner._feet(last), last.state == 6, False) == zb:
                            at = t0 % deck.span if deck.cyc else t0
                            alight.setdefault(zb, []).append({"phase": ph, "feet": list(feet), "cell": st["cell"],
                                                              "yaw": h, "kit": mac.kit, "macro": mac.name,
                                                              "pads": turn + go.pads, "ticks": len(go.rows),
                                                              "heading": h, "fam": mac, "bucket": at // EVERY})
    for za, hits in board.items():
        hits.sort(key=_rank)
        kept, seen = [], set()
        for b in hits:
            if b["phase"] not in seen and len(kept) < BEST:
                kept.append(b)
                seen.add(b["phase"])
        for b in kept:
            for zb, al in alight.items():
                if zb == za:
                    continue
                got = _ride(ks, deck, m, b, [a for a in al if a["kit"] == b["kit"]], nodes, zb)
                if got is not None:
                    links.setdefault((za, zb), []).append(got)
    for v in alight.values():
        for a in v:
            a.pop("fam")
    return {"board": board, "alight": alight, "links": {f"{a}>{b}": v[:TRIPS] for (a, b), v in links.items()}}


def _on_deck(ks, deck: Deck, feet, yaw: float, cell: int, m: int) -> dict | None:
    """R6 onto ``feet`` (a deck's top) and the settle on the kernel: the start when the body then stands on mover
    ``m`` (a moving deck carries it, so ``runner.find_start``'s stand-where-put rule doesn't apply), else None."""
    ks.reset()
    try:
        ks.teleport(tuple(feet), yaw, cell=cell)
        for _ in range(runner.SETTLE_START):
            ks.step(Pad())
    except L3Error:
        return None
    return {"feet": list(feet), "cell": int(cell)} if ks.p.state == 0 and _on(ks, deck, m) else None


def _on(ks, deck: Deck, m: int) -> bool:
    """Whether the kernel's body stands on ``deck`` (mover ``m``): its floor contact is the deck's, or its feet are
    on the deck's top at the clock (a deck flush with a floor: the floor's face, tested first, wins the tie)."""
    return ks.p.on == m or (ks.p.state == 0 and deck.on(runner._feet(ks._row()), int(ks.p.tick)))


def _rank(hit: dict) -> tuple:
    """A board hit's order: one that settles on the deck first, then the fewest ticks, the earliest phase."""
    return not hit.get("stays", True), hit["ticks"], hit["phase"]


def _ride(ks, deck: Deck, m: int, b: dict, al: list, nodes, zb: str) -> dict | None:
    """Board hit ``b`` ridden on the kernel to each later phase an alight of ``al`` landed from, that alight run from
    where the body is: the first link that settles in ``zb``, its whole string (board, idle, alight), else None."""
    if not al:
        return None
    ks.phase = b["phase"]
    ks.reset()
    try:
        runner.place(ks, b["feet"], b["yaw"], b["cell"])
        runner.set_kit(ks, b["kit"])
        for p in b["pads"]:
            ks.step(p)
    except L3Error:
        return None
    if not _on(ks, deck, m):
        return None
    by = {}
    for a in al:
        by.setdefault(a["bucket"], []).append(a)
    idle, off = [], 0
    end = int(ks.p.tick) + deck.span
    while int(ks.p.tick) < end and off <= OFF_TICKS:
        off = 0 if _on(ks, deck, m) else off + 1
        t = int(ks.p.tick)
        ph = t % deck.span if deck.cyc else t
        for a in by.get(ph // EVERY, ()) if ph % EVERY == 0 and not off else ():
            here = ks.save()
            fam = [a["fam"]]
            cam = runner._cam(ks._row())
            turn, _, cam = align(ks, cam, a["heading"])
            ks.launching = True
            try:
                go = launches(ks, fam, a["heading"], cam, runner._feet(ks._row()), 0.0)[0]
            except L3Error:
                go = None
            finally:
                ks.launching = False
            if go is not None and go.end == "settled" and go.rows and \
                    nodes.zone_at(runner._feet(go.rows[-1]), go.rows[-1].state == 6, False) == zb:
                ks.reset(here)
                return {"phase": b["phase"], "feet": b["feet"], "cell": b["cell"], "yaw": b["yaw"], "kit": b["kit"],
                        "board": b["macro"], "alight": a["macro"], "ride": len(idle),
                        "pads": b["pads"] + idle + turn + go.pads}
            ks.reset(here)
        try:
            ks.step(Pad())
        except L3Error:
            return None
        idle.append(Pad())
    return None


# -- the witnesses: FastL3 whole-step trips (D845) -----------------------------------------------------------------

class Clock:
    """A scene FastL3 ``sim``'s world from the snapshot (``pokes`` held at tick 0, :func:`_steps`' rule) at a tick,
    stepped forward and saved as trips ask for later ticks (one saved state)."""

    def __init__(self, sim, rt=None, pokes=()) -> None:
        self.sim, self.rt, self.pokes, self.steps = sim, rt, list(pokes), 0
        self._base()

    def _base(self) -> None:
        self.sim.reset()
        self.t = 0
        if self.pokes and self.rt is not None:          # a toggled deck's pokes: their window first (phase 0 is the
            self.t = RELEASE + PULSE + 1                # snapshot's tick; a phase inside the window starts after it)
            _steps(self.sim, self.t, lambda: None, self.rt, self.pokes)
            self.steps += self.t
        self.state = self.sim.save()

    def at(self, t: int) -> None:
        if t < self.t:
            self._base()
        self.sim.reset(self.state)
        if t > self.t:
            for _ in range(t - self.t):
                self.sim.step(Pad(), timeout_us=CAP_US)
            self.steps += t - self.t
            self.t, self.state = t, self.sim.save()


def _place(sim, feet, yaw: float, cell: int):
    """R6 onto ``feet`` from the state now (no reset) and :data:`runner.SETTLE_START` ticks at rest; the last row."""
    sim.teleport(tuple(feet), yaw, cell=cell)
    row = None
    for _ in range(runner.SETTLE_START):
        row = sim.step(Pad())
    return row


def trip(clock: Clock, rt, deck_obj, deck: Deck, c: dict, nodes, to: str | None, hold: int = 60) -> dict:
    """Candidate ``c`` (a board, alight or link: its phase, start, kit and pads) as a FastL3 whole-step trip from the
    clock at its phase (the module docstring): whether the feet stood on the deck (``rt.pose`` of ``deck_obj`` each
    tick) after leaving the floor (``boarded``), and with ``to`` whether the body then held ``hold`` idle ticks
    settled in zone ``to`` (``stays``); its whole steps."""
    sim = clock.sim
    ticks = 0
    try:
        clock.at(int(c["phase"]))         # the idle to its phase may reach a level exit (f2's): no trip
        row = _place(sim, c["feet"], c["yaw"], c["cell"])
        rows = runner.set_kit(sim, c["kit"])
        ticks += runner.SETTLE_START + len(rows)
        boarded = False
        if deck_obj is not None and _over(_live_top(deck, rt.pose(deck_obj)), runner._feet(row)):
            deck_obj = None                       # it stands on the deck already: no board (an alight's start)
        for p in l3.pads(c["segments"]) if "segments" in c else c["pads"]:
            row = sim.step(p, timeout_us=CAP_US)
            ticks += 1
            if not boarded and row.state not in AIRBORNE and deck_obj is not None:
                boarded = _over(_live_top(deck, rt.pose(deck_obj)), runner._feet(row))
        for _ in range(hold if to is not None else 0):
            row = sim.step(Pad(), timeout_us=CAP_US)
            ticks += 1
    except L3Error as e:
        return {"fault": l3.fault_site(e), "ticks": ticks, "boarded": False, "stays": False}
    f = runner._feet(row)
    stays = to is not None and settled(row) and nodes.zone_at(f, row.state == 6, False) == to
    return {"boarded": boarded, "stays": bool(stays), "ticks": ticks, "state": row.state}


def _live_top(deck: Deck, M) -> np.ndarray:
    M = np.asarray(M, dtype=np.float64).reshape(4, 4)
    up = (deck._n @ M[:3, :3])[:, 2] >= TOP_NZ
    return deck.local[up] @ M[:3, :3] + M[3, :3]


def string_sha12(c: dict) -> str:
    """A trip's witness hash: its phase, start, kit and every pad (positions stay private; a toggled deck's pokes
    are its verdict's term, beside it in the link)."""
    doc = {"phase": c["phase"], "feet": [round(x, 4) for x in c["feet"]], "yaw": round(c["yaw"], 6), "cell": c["cell"],
           "kit": c["kit"], "pads": [[list(p.stick), sorted(p.buttons), p.yaw, p.cam] for p in c["pads"]]}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode()).hexdigest()[:12]


# -- the router's trips --------------------------------------------------------------------------------------------

def window(o_ticks: int) -> int:
    """A witness's span in whole steps from the snapshot: the placement's settle, the kit, its string and the hold."""
    return runner.SETTLE_START + 40 + int(o_ticks) + 60


def path_boxes(path) -> np.ndarray:
    """A body path's boxes (centres a tick apart): each :data:`SWEEP_TICKS` ticks' (and the next one's, so the
    segment between is inside) box, grown by the kernel body (0.5 m round, 1.0 m up and down), (n, 6) lo then hi."""
    from devkit.reach import native as N
    P = np.asarray(path, dtype=np.float64).reshape(-1, 3)
    grow = np.array([N.RH, N.RH, N.RV])
    return np.array([np.r_[q.min(0) - grow, q.max(0) + grow]
                     for q in (P[k:k + SWEEP_TICKS + 1] for k in range(0, len(P), SWEEP_TICKS))]).reshape(-1, 6)


def _meet(a: np.ndarray, b: np.ndarray) -> bool:
    """Whether a box of ``a`` ((n, 6)) meets a box of ``b`` ((m, 6))."""
    return bool(((a[:, None, :3] <= b[None, :, 3:]) & (b[None, :, :3] <= a[:, None, 3:])).all(-1).any())


class Router:
    """The router's reading of a level's recording (:func:`recording`: ``rec`` and its ``verdicts``) for a zone
    witness whose frozen-world hold kept it (PLAN-v2 §1.5b, D845, D847): :meth:`decide`."""

    def __init__(self, lv, verdicts: dict, rec: dict) -> None:
        self.verdicts = verdicts
        self.far, self.lo, self.hi, self.box = {}, {}, {}, {}
        for oi, v in verdicts.items():
            if v["how"] not in ("cycles", "path"):
                continue
            c = _corners(_local(lv, oi))
            P = np.array([posed(c, M) for M in rec["poses"][oi]])               # (rows, 9, 3)
            self.far[oi] = np.maximum.accumulate(np.linalg.norm(P - P[0], axis=-1).max(-1))
            self.box[oi] = np.concatenate([P.min(1), P.max(1)], 1)              # its posed box a row
            self.lo[oi] = np.minimum.accumulate(P.min(1))                       # rows 0..t's union
            self.hi[oi] = np.maximum.accumulate(P.max(1))

    def _moving(self, ticks: int) -> list[int]:
        """The cycles and path rigs that move within a witness's window (:func:`window`) of ``ticks``."""
        w = window(ticks)
        return [oi for oi, f in self.far.items() if f[min(w, len(f) - 1)] > EPS]

    def near(self, points, ticks: int) -> bool:
        """Whether a witness through ``points`` (its start, takeoff, first landing and landings) passes within
        :data:`NEAR_XY` (across: no height bound) of where a rig moving within its window goes then: its path is
        swept (:func:`sweep_task`) [proposal]."""
        P = np.asarray([p for p in points if p is not None], dtype=np.float64)[:, :2]
        lo, hi, w = P.min(0) - NEAR_XY, P.max(0) + NEAR_XY, window(ticks)
        for oi in self._moving(ticks):
            k = min(w, len(self.lo[oi]) - 1)
            if (self.lo[oi][k, :2] <= hi).all() and (lo <= self.hi[oi][k, :2]).all():
                return True
        return False

    def decide(self, got: dict, route: dict | None, ticks: int, stays: bool, boxes=None, points=()) -> tuple:
        """What the router makes of a witness's frozen hold answer ``got`` (its movers ``route``, its string's
        ``ticks``; ``stays``: that answer kept the body in its to-zone; ``boxes``: its swept path,
        :func:`path_boxes`, None while not swept; ``points``: :meth:`near`'s):

        - ``("out", answer)``: its path touches a rig parked for an undecoded trigger (D847: out of logic), kept
          or not: not the same, so the pair takes its next candidate, and its confirm's touches, MAY and node edge
          go too;
        - ``("as", got)``: the frozen answer stands as it is; it failed (no trip rescues a witness its frozen hold
          or kernel confirm dropped: a trip only restricts, D845), or no moving rig meets it; a parked rig its
          path touches named in ``parked`` (PLAN-v2 §1.5d);
        - ``("sweep", None)``: it passes near a moving rig, its path not swept yet;
        - ``("trip", (rigs, names))``: those moving rigs touch it at their load pose or cross its swept path within
          its window: it counts only where its whole-step trip (:func:`replay_trip`) holds, ``names`` the parked
          rigs its path touches (:meth:`tripped`'s ``parked``)."""
        touched = (route or {}).get("rigs", ())
        parked = [oi for oi in touched if self.verdicts.get(oi, {}).get("how") == "parked"]
        names = sorted({self.verdicts[oi]["name"] for oi in parked})
        if any(self.verdicts[oi]["start"] == "undecoded" for oi in parked):
            return "out", {k: v for k, v in got.items() if k != "outcome"} | {"same": False, "parked": names}
        if not stays:
            return "as", got
        moving = self._moving(ticks)
        owed = {oi for oi in touched if oi in moving}
        if self.near(points, ticks):
            if boxes is None:
                return "sweep", None
            w = window(ticks)
            owed |= {oi for oi in moving if _meet(np.asarray(boxes).reshape(-1, 6), self.box[oi][: w + 1])}
        if owed:
            return "trip", (sorted(owed), names)
        return "as", got | ({"parked": names} if names else {})

    @staticmethod
    def tripped(got: dict, t: dict, parked=()) -> dict:
        """Frozen answer ``got`` with its whole-step trip's ``t`` (:func:`replay_trip`): the trip's landing, the same
        only where the trip held (its confirm's touches, MAY and node edge going with it where it didn't), the
        trip (its ``wait``: the idle ticks the witness owes before its R6, ``graph.confirmed``) and the parked rigs
        its path touches (``parked``: :meth:`decide`'s trip names, PLAN-v2 §1.5d)."""
        ok = bool(t.get("same")) and bool(t.get("settled"))
        out = got if ok else {k: v for k, v in got.items() if k != "outcome"}
        return out | {k: t[k] for k in ("land", "state", "settled") if k in t} | {"same": ok, "trip": t} | (
            {"parked": list(parked)} if parked else {})


def sweep_code12() -> str:
    """The swept paths' code (their cache key beside the hold's)."""
    return _code12(sweep, path_boxes, (SWEEP_TICKS,))


def sweep_key(hold_key: str) -> str:
    doc = {"hold": hold_key, "code": sweep_code12()}
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:12]


def sweep(sim, st: dict, heading: float, o: dict) -> dict:
    """Witness ``o`` of start ``st`` replayed from the snapshot as the hold does (``hold.replay``: R6, the kit, the
    string, ``hold.HOLD`` idle ticks) on ``sim`` (FastL3), its body path from the kit on as :func:`path_boxes`
    (``boxes``), or its ``fault``; its L3 ticks."""
    from devkit.reach.engine import hold
    path, ticks = [], runner.SETTLE_START
    try:
        runner.place(sim, st["feet"], st.get("yaw", heading), st["cell"])
        rows = runner.set_kit(sim, o["kit"])
        path += [r.pos for r in rows]
        for p in [*l3.pads(o["segments"]), *[Pad()] * hold.HOLD]:
            path.append(sim.step(p).pos)
    except L3Error as e:
        return {"fault": l3.fault_site(e), "ticks": ticks + len(path)}
    return {"boxes": path_boxes(path).round(3).tolist(), "ticks": ticks + len(path)}


def sweep_task(w, items: list, base: str) -> int:
    """A pool task: :func:`sweep` each (job key, outcome) of ``items`` on the worker's FastL3, each cached under
    :func:`sweep_key`; their L3 ticks."""
    from devkit.reach.engine import hold
    b, rec, ticks = Path(base), None, 0
    (b / "sweep").mkdir(mode=0o700, exist_ok=True)
    sim = w.sim(False, deep=False)
    sim = getattr(sim, "l3", sim)
    for job, k in items:
        rec = rec if rec is not None and rec["key"] == job else cache.get(b, job)
        o = rec["outcomes"][k]
        got = sweep(sim, rec["starts"][o["start"]], rec["heading"], o)
        cache.put(b / "sweep", sweep_key(hold.key(job, k)), got)
        ticks += got["ticks"]
    return ticks


def replay_trip(make, st: dict, heading: float, o: dict, waits=PHASES) -> dict:
    """Witness ``o`` of start ``st`` replayed in FastL3 whole steps from the snapshot, each try on a new scene FastL3
    (``make()``: :func:`fresh`), idle first 0, :data:`EVERY`, 2 :data:`EVERY` ... ticks (``waits`` tries): the
    first try that ends within :data:`END_M` of its landing, settled, then ``hold.HOLD`` ticks on;
    ``hold.replay``'s answer (``land``, ``state``, ``settled``, ``same``) with ``wait`` the idle ticks before it
    and ``tries``."""
    from devkit.reach.engine import hold
    pads = l3.pads(o["segments"])
    got, ticks, steps = None, 0, 0
    for k in range(waits):
        clock = Clock(make())
        sim = clock.sim
        try:
            clock.at(k * EVERY)
            _place(sim, st["feet"], st.get("yaw", heading), st["cell"])
            ticks += runner.SETTLE_START + len(runner.set_kit(sim, o["kit"]))
            row = None
            for p in pads:
                row, ticks = sim.step(p, timeout_us=CAP_US), ticks + 1
            same = row is not None and math.dist(runner._feet(row), o["land"]) <= END_M
            for _ in range(hold.HOLD):
                row, ticks = sim.step(Pad(), timeout_us=CAP_US), ticks + 1
        except L3Error as e:
            got = {"fault": str(getattr(e, "site", "other")), "ticks": ticks, "wait": k * EVERY, "tries": k + 1}
            continue
        finally:
            steps += clock.steps
        got = {"land": list(runner._feet(row)), "state": row.state, "settled": settled(row), "same": same,
               "ticks": ticks, "wait": k * EVERY, "tries": k + 1}
        if same and settled(row):
            break
    got["steps"] = steps + ticks
    return got


def _seed(*parts) -> int:
    return int(hashlib.sha256(json.dumps(parts, default=str).encode()).hexdigest()[:8], 16)


def truth_trials(nodes, deck: Deck, takeoffs, n: int, hits=(), seed: int = 19) -> list[dict]:
    """``n`` random board trials of ``deck`` (the module docstring), drawn by ``seed``: half ``uniform`` (a zone's
    takeoff near it, a heading at its centre +-40 degrees, an R0 launch, a phase of its span), half ``near`` the
    kernel's board ``hits`` (a hit's takeoff, its heading +-10 degrees, any R0 launch of its kit, its phase +-15
    ticks) [default D115: the uniform half alone makes a hop a hundred trials; the near half measures the order's
    loss where the kernel saw a window, so recall is given by stratum]."""
    zones = near(nodes, deck, takeoffs)
    if not zones:
        return []
    rnd = random.Random(_seed(seed, deck.oi))
    flat = [(z, t) for z, ts in sorted(zones.items()) for t in ts]
    by_i = {t.i: (z, t) for z, t in flat}
    hits = [h for h in hits if h["takeoff"] in by_i]
    out = []
    for k in range(n):
        if k % 2 and hits:
            b = rnd.choice(hits)
            z, t = by_i[b["takeoff"]]
            ph = max(0, b["phase"] + rnd.randint(-EVERY, EVERY))
            h = b["yaw"] + rnd.uniform(-math.radians(10), math.radians(10))
            mac = rnd.choice([i for i, m in enumerate(R0) if m.kit == b["kit"]])
            out.append({"zone": z, "takeoff": t.i, "phase": ph, "yaw": h, "macro": mac, "stratum": "near"})
            continue
        z, t = rnd.choice(flat)
        ph = rnd.randrange(0, max(1, deck.span))
        h = _toward(t.feet, deck.centre(ph)) + rnd.uniform(-math.radians(40), math.radians(40))
        out.append({"zone": z, "takeoff": t.i, "phase": ph, "yaw": h, "macro": rnd.randrange(len(R0)),
                    "stratum": "uniform"})
    return out


def truth_trial(clock: Clock, rt, deck_obj, deck: Deck, nodes, t, c: dict) -> dict:
    """One truth trial (:func:`truth_trials`' ``c`` from takeoff ``t``) on FastL3's own controllers in whole steps
    from the clock at its phase: whether it boarded the deck (the feet on its live top after leaving the floor)."""
    sim = clock.sim
    m = R0[c["macro"]]
    feet = nodes.starts(t, c["yaw"], BACK_STAND if m.stands else BACK_RUN, c["zone"])
    try:
        clock.at(int(c["phase"]))
        row = _place(sim, feet[0], c["yaw"], t.cells[0])
        if deck_obj is not None and _over(_live_top(deck, rt.pose(deck_obj)), runner._feet(row)):
            return {"boarded": False, "start": "on the deck"}
        kit = runner.set_kit(sim, m.kit)
        _, _, cam = align(sim, runner._cam(kit[-1]), c["yaw"])
        back = (t.feet[0] - feet[0][0]) * -math.sin(c["yaw"]) + (t.feet[1] - feet[0][1]) * math.cos(c["yaw"])
        boarded = False
        step = sim.step

        def watched(pad=Pad(), **k):
            nonlocal boarded
            r = step(pad, **k)
            if not boarded and r.state not in AIRBORNE and deck_obj is not None:
                boarded = _over(_live_top(deck, rt.pose(deck_obj)), runner._feet(r))
            return r
        sim.step = watched
        try:
            launches(sim, [m], c["yaw"], cam, tuple(feet[0]), back)
        finally:
            sim.step = step
    except L3Error as e:
        return {"boarded": False, "fault": l3.fault_site(e)}
    return {"boarded": boarded}


# -- the stage's pool tasks ------------------------------------------------------------------------------------------

_REC: dict = {}


def _stage(level: str, rec_path: str, reach: str, absent):
    """This worker's level for the stage: the recording (its doc, verdicts, decks), the nodes, the takeoffs and the
    kernel world with every decided moving deck a mover (deck ``i`` mover ``i``), once a process."""
    import gzip
    import pickle

    from devkit.reach import models
    from devkit.reach.engine.nodes import Nodes
    if _REC.get("k") != (level, rec_path):
        lv, T = _level(level)
        doc = pickle.loads(gzip.decompress(Path(rec_path).read_bytes()))
        verdicts = decide(lv, T, doc["rec"], doc["toggles"])
        ds = decks(level, doc, verdicts)
        for i, d in enumerate(ds):
            d.m = i
        nodes = Nodes(models.read(reach))
        _REC.clear()
        every = nodes.takeoffs()
        _REC.update(k=(level, rec_path), doc=doc, verdicts=verdicts, decks={d.oi: d for d in ds}, nodes=nodes,
                    takeoffs=every, off=off_decks(lv, every), absent=list(absent))
    return _REC


def search_task(w, level: str, rec_path: str, reach: str, absent, oi: int) -> dict:
    """:func:`search` round deck ``oi`` on this worker's kernel (its CPU and kernel ticks counted)."""
    import time

    from devkit.reach.native import backend as KB
    S = _stage(level, rec_path, reach, absent)
    ds = list(S["decks"].values())
    world = kernel_world(level, S["absent"], ds)
    ks = _rigsim(w.sim(False, deep=False), world, KB.base(w.sim(False, deep=False)))
    t0 = time.process_time()
    got = search(ks, S["nodes"], S["decks"][oi], S["off"])
    return got | {"oi": oi, "cpu_s": round(time.process_time() - t0, 2), "kernel_ticks": ks.ticks}


def trip_task(w, level: str, rec_path: str, reach: str, absent, oi: int, items: list) -> list:
    """Deck ``oi``'s whole-step trips (:func:`trip`) and truth trials (:func:`truth_trial`), in phase order on one
    :class:`Clock` on a new scene FastL3 (:func:`fresh`): each item ``(kind, key, candidate, to)``, ``kind`` board,
    alight, link or truth; one that holds there counts (``ok``) only where it holds again alone on another new one
    from the snapshot (``fresh``: that run's answer); a ``key`` whose earlier candidate already counted is skipped (a
    hop or link needs one witness).  Each result its item's kind, key, answers, the witness's sha12 and the whole
    steps it took."""
    import time

    from devkit.reach.engine.triggers import Runtime
    S = _stage(level, rec_path, reach, absent)
    lv, _ = _level(level)
    d = S["decks"][oi]
    o = lv.owners[oi]

    def run(clock, rt, obj, kind, c, to):
        if kind == "truth":
            got = truth_trial(clock, rt, obj, d, S["nodes"], S["takeoffs"][c["takeoff"]], c)
            return got, got["boarded"]
        got = trip(clock, rt, obj, d, c, S["nodes"], to)
        ok = got["stays"] if kind in ("alight", "link") else got["boarded"]
        return got, ok and (kind != "link" or got["boarded"])

    def on_fresh():
        sim = fresh(w)
        rt = Runtime(sim, lv)
        obj = rt.deck(o["G"], o["R"])
        return Clock(sim, rt, d.pokes), rt, obj
    clock, rt, obj = on_fresh()
    done, out = set(), []
    for kind, key, c, to in sorted(items, key=lambda x: (int(x[2]["phase"]), x[0], x[1])):
        if (kind, key) in done:
            continue
        t0, s0 = time.process_time(), clock.steps
        got, ok = run(clock, rt, obj, kind, c, to)
        steps = clock.steps - s0 + got.get("ticks", 0)
        again = None
        if ok:                    # it counts only where it holds alone on a new FastL3, from the snapshot
            c2, rt2, obj2 = on_fresh()
            again, ok = run(c2, rt2, obj2, kind, c, to)
            steps += c2.steps + again.get("ticks", 0)
        if ok and kind != "truth":
            done.add((kind, key))
        out.append({"kind": kind, "key": key, "ok": bool(ok), "answer": got, "fresh": again,
                    "sha12": None if kind == "truth" else string_sha12(c), "phase": int(c["phase"]),
                    "cpu_s": round(time.process_time() - t0, 3), "steps": steps})
    return out


def trip_hold_key(hold_key: str, rec12: str) -> str:
    """A router trip's cache key: its witness's hold key, the recording's sha12 and this code."""
    doc = {"hold": hold_key, "rec": rec12, "code": trip_code12()}
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:12]


def trip_hold_task(w, items: list, base: str, rec12: str) -> int:
    """A pool task: :func:`replay_trip` each (job key, outcome, its hold answer's landing) of ``items`` in whole
    steps, each answer cached under :func:`trip_hold_key`; their whole steps."""
    from devkit.reach.engine import hold
    b, rec, steps = Path(base), None, 0
    (b / "trip").mkdir(mode=0o700, exist_ok=True)
    for job, k, land in items:
        rec = rec if rec is not None and rec["key"] == job else cache.get(b, job)
        o = dict(rec["outcomes"][k], land=land)
        got = replay_trip(lambda: fresh(w), rec["starts"][o["start"]], rec["heading"], o)
        cache.put(b / "trip", trip_hold_key(hold.key(job, k), rec12), got)
        steps += got["steps"]
    return steps
