"""Simulator Level 3's input search (Step X.7, D170): an input string that takes the player from a start to a goal
under the game's own code (:mod:`devkit.sim.l3`).  Generic: it knows a simulator (``step``, ``save``, ``reset``),
rows (``pos``, ``state``, ``hp``, ``zone``) and a :class:`Goal`; the randomizer's goal on its reach model is
``devkit.rando.draft.l3_goal.RouteGoal``, passed in as a factory by name (:func:`solve`).

A string is a list of :class:`Seg`: ``n`` ticks of one world heading (or the stick at rest) with Y held for the
segment's first ``hold`` ticks (a jump; in the air with air armor, a flap), BLACK for its first ``roll`` ticks (a
roll; Y during it, a roll jump) or LT+Y for its first ``cast`` ticks (the air armor, cast on the release: a recast
refills the gauge, not the jump's flap count).  What a real pad gives (X.4,
:mod:`devkit.sim.inputs`): the camera turns toward the heading at most ``CAM_RATE`` a tick (the right stick)
and the left stick stays inside the pad's round gate, so the game's heading (camera yaw + the stick's angle) is the
segment's and the speed 7.0 m/s times the stick.  :func:`pads` makes a string L3's per-tick pads from a camera yaw,
:func:`segments` any pads the run-length JSON ``l3.pads`` reads (what ``xemu_oracle.py replay`` replays;
with the rows, the camera as the exact f32 pair the input builder read), and :func:`string_sha12` names it.

:func:`search` is Go-Explore over cells.  The archive keeps, for each cell of the goal's (:meth:`Goal.cell`: the
zone, a coarse position, on the ground or in the air), the shortest string that got there and its cost to go; a
cell's state (the pages that differ from the snapshot) is saved the first time the search returns to it.  Seed
strings (the route planner's, or earlier winners) run first, each segment's end entering the archive, so a seed
that misses still leaves its trail.  Each round picks a cell (less cost to go and fewer visits first), resets to it
in milliseconds and explores from it: segments that follow the goal's guidance (:meth:`Goal.toward`: a heading,
whether to jump, for a run-up the ticks to the takeoff, and whether to cast the air armor first: then a short
segment of LT+Y at that heading, Step R1.29e), else a random heading, with a jump now and then.  Each
segment's end is a candidate cell.  A run that dies (state 7 or HP 0), stays in the air longer than ``Limits.fall``
ticks or raises an ``L3Error`` (a game assert, a fault, a runaway step) ends that branch only; faults are counted, by
kind and site (:attr:`Result.fault_sites`, ``L3Error.site``: Step X.52).  A branch that takes a level exit ends there
like a death (Step X.52b): on the row whose step fired a levelSwitch (``Row.exit``; the goal still tests that row) or
at the unload's entry (``l3.LevelExit``), before any save, load, wait or taint; it is no fault, and the result counts
such branches by the level they load (:attr:`Result.exits`; a miss's ``why`` names them, :func:`exits_text`).
The first row the goal accepts ends the search; the winner is re-run from the start (and ``Goal.settle`` ticks at
rest after it must still be in the goal, and the body must live through a goal's ``survive`` ticks after that and
then land alive, at rest or holding its last stick, :func:`lands_alive`: a pickup taken on the way to a death is
none, AZ-571, AZ-627) before it is returned.  A result carries the taint of every run it explored (``L3.taint``: a
file read, a clock, a high page, an RDTSC or a kernel call L3 doesn't model, and each kernel call's game caller and
NtCreateFile's file, ``L3.taint_at``): a search that found nothing is evidence of absence only when that set is
empty.

Stalls (Step X.52): a search keeps its best cost to go every ``Limits.steps / 20`` steps (:attr:`Result.curve`), and
one that ends without the goal names its stall (:attr:`Result.stall`, :func:`stall_of`): the archive's least-cost cell,
its row's state, whether the best cost was still falling (the step of its last fall by :data:`PLATEAU_S` and its fall
over the last :data:`FALL_STEPS` steps, Step X.52b) and, from a goal that answers ``ahead(row)`` (``RouteGoal``'s: the
stage, no zone, off the graph, a walk or an edge, and the first region edge on its cheapest way, by id, kind,
confidence and the zones at its ends, or the walk's first zone change, or off the graph the zone the fallback steers
to), where it stalled; never positions.  ``Limits.plateau`` ends a seed whose best cost to go
hasn't fallen by :data:`PLATEAU_S` in that many steps, ``plateau at <the edge>``: a cut of the same run, so it takes
no part in the problem's identity.  :func:`robustness` re-runs a winner under
jitter (each jump a 30 fps tick earlier or later, at the build's frame rate the same time; every heading a few
degrees off): the share that still reaches the goal.

The flap budget (Step R1.8g, D183): ``Limits.flaps`` caps the flaps in any one jump (the game's own per-jump
counter entity+0xD8, a row's ``obs.flaps_used``; the armor caps it too, at its Flaps 1/2/5): the search never presses Y
in the air at the cap, and a branch past it ends.  A winner's :attr:`Result.flaps` is the most it used in one jump.
The kit (:attr:`Segment.kit`): the element levels written in RAM at the start (R2, a step's ``writes`` the replayer
writes too) and, with air, the armor cast by input (LT+Y), so one snapshot serves every kit.

Reproducible: the budget is emulated steps (``Limits.steps``; ``wall_cap_s`` is a safety net whose verdict,
``wall-cap``, is never a proof of absence; by default the steps at :data:`WALL_RATE` a second, Step X.52b), the
random stream is ``random.Random(seed)``, the archive iterates in insertion order, so the same start, goal, limits and
seed give the same string.  :func:`solve` runs one search per
seed on a persistent worker pool (:mod:`devkit.reach.l3_pool`, which also runs many problems at once) with seeds
derived from the problem (:func:`problem_sha12`: the snapshot's metadata hash, the start, the goal and the search's
shape) and merges them in seed order: the winner is the lowest seed index that reached, whatever finished first.

Chained segments (D172, R1.16): a :class:`Segment` names its start (a snapshot, a teleport, settle ticks, earlier
strings as a prefix); the certification script snapshots in xemu, searches here, replays the winner there from the
same halted state and snapshots again exactly where the replay halts (``Sandbox.snapshot(here=True)``), each
snapshot linked to its parent.  Dev tooling (Unicorn is a dev dependency).
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import struct
import time
from dataclasses import dataclass, field
from typing import Callable, NamedTuple, Protocol

from devkit.sim.inputs import CAM_RATE, camera, stick as _stick
from devkit.sim.l3 import L3Error, LevelExit, Pad, engine, fault_site, meta_sha12, read_meta, snapshot_path
from devkit.sim.l3 import pads as l3_pads
from devkit.sim.obs import SETTLED, settled  # noqa: F401 (one settled rule, AZ-737: its importers read it here)

AIRBORNE = frozenset({2, 0x102})     # entity+0x94: in the air, the air attack move
SWIMMING = 6
DEAD = 7
JUMP_HOLD = 6                        # Y held this many ticks for a jump (the harness's capture)
ROLL_TAP = 3                         # BLACK tapped this many ticks for a roll (sitting rjc5's black_tap)
CAST_WAIT = 2                        # ticks at rest after the kit's LT+Y: the armor is on the tick after the release
PLATEAU_S = 0.1                      # a best cost to go this much lower counts as progress (Limits.plateau)
FALL_STEPS = 10_000                  # a stall's window for "still falling?" (Step X.52b)
WALL_RATE = 4.0                      # steps a second: a run's wall cap by default is its steps at this rate (Step
                                     # X.52b), under the slowest whole steps measured (R1.29f's r3053: 5.8-6.2 a
                                     # second, cut at 23-30 k of 30 k steps by a fixed 4,000 s cap)
LAND_CAP = 300                       # [proposal] ticks at rest a goal's survive window waits for the body to land
                                     # (AZ-627): 10 s at 30 fps; a fall at rest has landed or killed well before it
                                     # (a 65 m fall, the game's mid-air death, takes 3.6 s)
__all__ = ["CAM_RATE", "WALL_RATE", "Seg", "Limits", "Result", "Segment", "search", "solve", "robustness", "pads",
           "segments", "string_sha12", "expand", "start_of", "run_segs", "confirm", "problem_sha12", "buttons",
           "most_flaps", "seg_list", "flaps_of", "stall_name", "stall_of", "exits_text", "lands_alive", "LAND_CAP"]


class Seg(NamedTuple):
    """``n`` ticks of the game heading ``heading`` (radians: the player faces (-sin h, cos h)) at full stick, or
    the stick at rest (``None``), with Y held for the first ``hold`` ticks, BLACK for the first ``roll`` (a roll)
    and LT+Y for the first ``cast`` (the armor cast on the release; it wins over ``hold``)."""
    n: int
    heading: float | None
    hold: int = 0
    roll: int = 0
    cast: int = 0


def seg_list(s) -> list | dict:
    """A segment as a JSON list: ``[n, heading, hold]``, with ``roll`` and ``cast`` only when it has them (so a
    string without either keeps the form, and the problem identity, Step X.7 wrote); an ``l3.pads`` segment (a
    found string's) as it is."""
    if isinstance(s, dict):
        return s
    s = list(Seg(*s))
    return s if s[3] or s[4] else s[:3]


def buttons(s: Seg, t: int) -> frozenset:
    """The buttons ``s`` holds on its tick ``t``."""
    b = {"lt", "y"} if t < s.cast else {"y"} if t < s.hold else set()
    return frozenset(b | {"black"}) if t < s.roll else frozenset(b)


def stick(heading: float | None, cam: float) -> tuple[float, float]:
    """The left stick that moves the player along ``heading`` under a camera at ``cam`` (radians), as a real pad
    gives it (:func:`devkit.sim.inputs.stick`)."""
    return _stick(heading, cam)


def expand(segs, cam: float) -> tuple[list[Pad], float]:
    """(one pad per tick, the camera yaw after them) for ``segs`` from a camera at ``cam``."""
    out = []
    for s in segs:
        s = Seg(*s)
        for t in range(s.n):
            cam = camera(cam, s.heading)
            out.append(Pad(stick(s.heading, cam), buttons(s, t), cam))
    return out, cam


def pads(segs, cam: float) -> list[Pad]:
    """One pad per tick for ``segs`` from a camera at ``cam``."""
    return expand(segs, cam)[0]


def segments(pad_list, rows=None) -> list[dict]:
    """The run-length JSON (``{"n", "stick", "buttons", "cam" | "yaw"}``) of per-tick pads: what ``l3.pads`` and
    the xemu replayer read.  With ``rows`` (the L3 rows the pads produced) the camera is the exact f32 pair the
    input builder read (``cam``), else the pad's yaw; floats are exact (JSON keeps their repr)."""
    out: list[dict] = []
    for k, p in enumerate(pad_list):
        d = {"stick": list(p.stick), **({"buttons": sorted(p.buttons)} if p.buttons else {})}
        if rows is not None and rows[k].cam is not None:
            d["cam"] = list(struct.unpack("<2f", rows[k].cam))
        elif p.cam is not None:
            d["cam"] = list(p.cam)
        else:
            d["yaw"] = p.yaw
        if out and {k_: v for k_, v in out[-1].items() if k_ != "n"} == d:
            out[-1]["n"] += 1
        else:
            out.append({"n": 1, **d})
    return out


def string_sha12(pad_list, prefix: bytes = b"", rows=None) -> str:
    """sha256[:12] of per-tick pads' canonical JSON (after ``prefix``, e.g. a teleport's place request)."""
    return hashlib.sha256(prefix + json.dumps(segments(pad_list, rows), sort_keys=True).encode()).hexdigest()[:12]


class Goal(Protocol):
    """``settle``: ticks at rest a winner must stay in the goal; ``toward``: (heading or None, jump now) and, as an
    optional third item, how many ticks to keep that heading (a run-up that ends at a takeoff), and a fourth, True
    to cast the air armor now (LT+Y: a spent gauge before a flap flight).  Optional: ``survive``, ticks after the
    settle the body must live through, and then land alive (AZ-571, AZ-627; 0 when absent: no window)."""
    settle: int

    def reached(self, row) -> bool: ...
    def cost(self, row) -> float: ...
    def toward(self, row) -> tuple: ...
    def cell(self, row) -> tuple: ...
    # optional: ``ahead(row) -> dict``, the stall record of the search's best row (:attr:`Result.stall`)


@dataclass
class Limits:
    """A search's budget and shape.  The budget: ``steps`` emulated ticks (what decides the outcome),
    ``wall_cap_s`` a safety net (None: ``steps`` at :data:`WALL_RATE` a second, :meth:`wall_s`), ``ticks`` the longest
    string, ``cells`` the archive's size, ``exhaust`` the rounds
    with no new cell after which the start's reach counts as explored.  The shape: ``seg`` a segment's ticks,
    ``hold`` Y's ticks in a jump, ``rollout`` the segments explored after each return, ``pursue`` the share of
    segments that follow the guidance, ``fall`` the most ticks in the air, ``temp`` the cost (s) over the best at
    which a cell's pick weight falls by e; ``flaps`` the most flaps in one jump (None: what the armor gives),
    ``roll`` and ``cast`` the share of segments that start with a roll or an armor cast (0: never), ``dive`` the
    share of segments in the water (swimming) that hold BLACK throughout: a dive (A, B and BLACK sink at the
    species' walkSpeed, RE_MOVEMENT; Step R1.29: a pickup under the surface).  ``plateau`` (Step X.52): the steps
    with no new best cost to go (lower by :data:`PLATEAU_S`) after which a seed ends, ``plateau at <edge>``
    (None: never); like ``steps``, a budget: no part of the problem's shape."""
    steps: int = 300_000
    wall_cap_s: float | None = None
    ticks: int = 2400
    cells: int = 20000                   # town's open hub filled 4,000 in one search (x7)
    exhaust: int = 800
    seg: int = 8
    hold: int = JUMP_HOLD
    rollout: int = 16
    pursue: float = 0.6
    fall: int = 120
    temp: float = 4.0
    flaps: int | None = None
    roll: float = 0.0
    cast: float = 0.0
    dive: float = 0.0
    plateau: int | None = None

    def wall_s(self) -> float:
        """The wall cap in seconds: ``wall_cap_s``, else the steps at :data:`WALL_RATE` a second (a slow scene's
        run is cut by its rate, not by a fixed cap)."""
        return self.steps / WALL_RATE if self.wall_cap_s is None else self.wall_cap_s

    def shape(self) -> dict:
        """The fields that change the search's character (not its budget): part of a problem's identity (the
        flap budget and the move shares only when set, so an X.7 problem keeps its identity)."""
        out = {k: getattr(self, k) for k in ("ticks", "cells", "exhaust", "seg", "hold", "rollout", "pursue",
                                              "fall", "temp")}
        if self.flaps is not None:
            out["flaps"] = self.flaps
        return out | {k: v for k, v in (("roll", self.roll), ("cast", self.cast), ("dive", self.dive)) if v}


@dataclass
class Result:
    reached: bool
    segs: list = field(default_factory=list)
    ticks: int = 0
    rounds: int = 0
    steps: int = 0
    cells: int = 0
    seconds: float = 0.0
    best_cost: float = math.inf
    why: str = ""
    cam: float = 0.0          # the camera yaw the string starts from
    faults: int = 0           # rollouts an L3Error ended
    taint: set = field(default_factory=set)   # what any explored run read that the simulator doesn't model
    flaps: int | None = None  # a winner's most flaps in one jump
    capped: int = 0           # cells whose string had reached ``Limits.ticks`` when it stopped (never picked again)
    fault_sites: dict = field(default_factory=dict)   # L3Error.site -> rollouts it ended
    taint_at: dict = field(default_factory=dict)      # kernel taint -> its sites (L3.taint_at)
    curve: list = field(default_factory=list)         # [steps, best cost to go] every Limits.steps / 20
    stall: dict | None = None # not reached: the best cell's cost, ticks and the goal's ``ahead`` (ids, no positions)
    exits: dict = field(default_factory=dict)         # level -> branches that ended at its exit (Step X.52b)

    def fault(self, exc) -> None:
        """Count an ``L3Error`` that ended a rollout, by its site."""
        self.faults += 1
        site = fault_site(exc)
        self.fault_sites[site] = self.fault_sites.get(site, 0) + 1

    def ended(self, rows, err) -> None:
        """Count how a branch ended (Step X.52b): an ``L3Error`` by its site (a fault), but a level exit by the level
        it loads: a fire on its last row (``Row.exit``: the level, else the movie) or the unload's stop
        (``l3.LevelExit``: ``unload``), never as a fault."""
        if isinstance(err, LevelExit):
            to = "unload"
        elif err is not None:
            return self.fault(err)
        elif rows and (ex := getattr(rows[-1], "exit", None)) is not None:
            to = ex[0] or ex[1] or "?"
        else:
            return
        self.exits[to] = self.exits.get(to, 0) + 1

    def seen(self, sim) -> None:
        """Take in what the simulator's run so far read that it doesn't model (``taint``, ``taint_at``)."""
        self.taint.update(getattr(sim, "taint", ()))
        for k, v in getattr(sim, "taint_at", {}).items():
            self.taint_at.setdefault(k, set()).update(v)

    def summary(self) -> dict:
        """Counts, ticks, ids and the faults' and kernel taints' code sites only (no positions), with the engine
        that ran it (``l3.engine``, Step X.52b: two results compare only on one engine and with no faults)."""
        return {"reached": self.reached, "why": self.why, "ticks": self.ticks, "segments": len(self.segs),
                "flaps": self.flaps,
                "rounds": self.rounds, "steps": self.steps, "cells": self.cells, "capped": self.capped,
                "faults": self.faults,
                "fault_sites": dict(sorted(self.fault_sites.items(), key=lambda kv: (-kv[1], kv[0]))),
                "exits": dict(sorted(self.exits.items())), "taint": sorted(self.taint),
                "taint_at": {k: sorted(v) for k, v in sorted(self.taint_at.items())},
                "seconds": round(self.seconds, 1),
                "steps_per_s": round(self.steps / self.seconds) if self.seconds else 0,
                "best_cost_s": None if math.isinf(self.best_cost) else round(self.best_cost, 1),
                "curve": self.curve, "stall": self.stall, "engine": engine()}


def exits_text(exits: dict) -> str:
    """The branches that left the level, in words (Step X.52b): ``3 branches fired levels/earth/e2``, with each
    level's count when there are several; empty for none."""
    n = sum(exits.values())
    if not n:
        return ""
    to = next(iter(exits)) if len(exits) == 1 else ", ".join(f"{k} ({v})" for k, v in sorted(exits.items()))
    return f"{n} branch{'es' if n != 1 else ''} fired {to}"


def stall_of(goal, row, cost: float, ticks: int, falls: list, last: int, steps: int) -> dict:
    """A run's stall record (Steps X.52, X.52b): the best cell's cost to go (``cost``) and ticks, its row's state
    (entity+0x94), ``last_fall`` the step of the best cost's last fall by :data:`PLATEAU_S`, ``fall_10k_s`` its fall
    over the run's last :data:`FALL_STEPS` steps (``falls``: each new best's (step, cost), the start's first; still
    falling at :data:`PLATEAU_S` or more) and the goal's ``ahead(row)`` when it has one.  Ids and costs only."""
    ref = next((c for k, c in reversed(falls) if k <= steps - FALL_STEPS), falls[0][1])
    fell = ref - cost
    ahead = getattr(goal, "ahead", None)
    return {"cost_s": None if math.isinf(cost) else round(cost, 1), "ticks": ticks, "state": row.state,
            "last_fall": last, "fall_10k_s": round(fell, 1) if math.isfinite(fell) else None,
            **(ahead(row) if ahead else {})}


def stall_name(stall: dict | None) -> str:
    """A stall record's place in words: its edge (``#24 jump (assumed) f3.Z012>f3.Z254``; ``flying #24 ...`` for a
    row in the air on it, ``(geometry, doubted: blocked)`` for an edge the light trick graph doubts, Step X.53), the
    walk to the goal (from its zone, into the first other), off the goal's graph; ``the best cell`` when the goal
    names none; off the graph with the zone the fallback steers to and the way on from there, and a cell on no floor
    of the model or in no zone (AZ-538) said first."""
    st = stall or {}
    z = st.get("zone")
    if st.get("edge") is not None:
        ends = f" {st.get('from') or '?'}>{st.get('to') or '?'}" if st.get("from") or st.get("to") else ""
        fly = {"flying": "flying ", "riding": "riding "}.get(st.get("stage"), "")
        doubt = f", doubted: {st['doubt']}" if st.get("doubt") else ""
        out = f"{fly}#{st['edge']} {st.get('kind')} ({st.get('conf')}{doubt}){ends}"
    elif st.get("kind") == "walk":
        out = "the walk to the goal" + (f" from {z}" if z and "steer" not in st else "") + (
            f" into {st['into']}" if st.get("into") else "")
    elif st.get("kind"):
        out = f"{st['kind']}" + (f" in {z}" if z else "")
    else:
        out = "the best cell" + (f" in {z}" if z else "")
    if "steer" in st and st.get("kind") != "off the graph":
        out = f"off the graph{f' in {z}' if z else ''}, steered to {st['steer'] or 'no zone'}: {out}"
    return {"no zone": f"in no zone: {out}", "on no floor": f"on no floor: {out}",
            "no goal vertex": f"no goal vertex: {out}"}.get(st.get("stage"), out)


class _Entry:
    """A cell's best string; its state is saved when the search first returns to it (from ``base``, a saved
    entry, by the segments after ``base.segs``), so a cell costs nothing until then."""
    __slots__ = ("segs", "ticks", "cost", "state", "row", "visits", "air", "base", "cam")

    def __init__(self, segs, ticks, cost, state, row, air, cam, base=None):
        self.segs, self.ticks, self.cost, self.state, self.row, self.air = segs, ticks, cost, state, row, air
        self.cam, self.base, self.visits = cam, base, 0


def _dead(row) -> bool:
    return row.state == DEAD or row.hp <= 0


def flaps_of(row) -> int:
    """The row's per-jump flap count (the game's counter entity+0xD8, ``obs.flaps_used``; 0 for a row that
    carries none)."""
    o = getattr(row, "obs", None)
    return o.flaps_used if o is not None else getattr(row, "flaps", 0)


def run_segs(sim, segs, cam: float, goal: Goal | None = None, air: int = 0, fall: int = 10**9,
             flaps: int | None = None):
    """Run ``segs`` from the sim's state now and a camera at ``cam``: (rows, the index of the first row the goal
    accepts or None, the ticks in the air at the end, whether the branch ended (it died, fell too long, flapped
    more than ``flaps`` times in one jump, took a level exit, ``Row.exit``, on a row the goal doesn't accept, or the
    step raised ``L3Error``), the camera after, the ``L3Error`` or None)."""
    rows = []
    for s in segs:
        s = Seg(*s)
        for t in range(s.n):
            cam = camera(cam, s.heading)
            try:
                row = sim.step(Pad(stick(s.heading, cam), buttons(s, t), cam))
            except L3Error as exc:
                return rows, None, air, True, cam, exc
            rows.append(row)
            air = air + 1 if row.state in AIRBORNE else 0
            if _dead(row) or air > fall or flaps is not None and flaps_of(row) > flaps:
                return rows, None, air, True, cam, None
            if goal is not None and goal.reached(row):
                return rows, len(rows) - 1, air, False, cam, None
            if getattr(row, "exit", None) is not None:      # a level exit: the branch ends on its row (Step X.52b)
                return rows, None, air, True, cam, None
    return rows, None, air, False, cam, None


def lands_alive(sim, cam: float, survive: int = 0, cap: int = LAND_CAP, held: Pad | None = None,
                air: bool = False) -> str | None:
    """Whether the body, from the sim's state now (camera ``cam``), lands alive (AZ-627): None once it has lived
    ``survive`` ticks and is settled (:func:`settled`; a fall's damage is the game's on its landing tick), or
    has lived ``cap`` ticks; else why not, ``dies`` (state 7 or HP 0), ``faults`` (an ``L3Error``) or ``leaves the
    level`` (a level exit).  The stick rests; with ``held`` (a pad: its stick and camera, no button) it holds that
    pad while the body is in the air (``air``: it is now) and rests once it isn't."""
    rest = Pad(stick(None, cam), frozenset(), cam)
    held = held._replace(buttons=frozenset()) if held is not None else rest
    for t in range(1, cap + 1):
        try:
            row = sim.step(held if air else rest)
        except L3Error:
            return "faults"
        if _dead(row):
            return "dies"
        if getattr(row, "exit", None) is not None:
            return "leaves the level"
        if t >= survive and settled(row):
            return None
        air = row.state in AIRBORNE
    return None


def _rewind(sim, state) -> None:
    """``sim.reset(state)`` keeping the taint read since (``L3.taint``, ``taint_at``): every run a confirm makes is
    the result's (``Result.seen`` reads the simulator after it)."""
    taint, taint_at = set(getattr(sim, "taint", ())), {k: set(v) for k, v in getattr(sim, "taint_at", {}).items()}
    sim.reset(state)
    if hasattr(sim, "taint"):
        sim.taint.update(taint)
        for k, v in taint_at.items():
            sim.taint_at.setdefault(k, set()).update(v)


def confirm(sim, start, segs, cam: float, goal: Goal) -> int | None:
    """Re-run ``segs`` from ``start`` (camera ``cam``): its tick count when the goal accepts its last row (and
    only that one), still accepts the player after ``goal.settle`` ticks at rest and the body after them lives the
    goal's ``survive`` ticks and lands alive (:func:`lands_alive`, AZ-571, AZ-627: a touch on the way to a death,
    also one high over a lethal drop, is none), at rest or, in the air, holding the string's last stick (a touch
    mid-jump over a gap the body clears only on the stick), else None."""
    sim.reset(start)
    rows, hit, _, bad, after, _ = run_segs(sim, segs, cam, goal)
    if bad or hit is None or hit != len(rows) - 1:
        return None
    last = rows[-1]
    if goal.settle:
        rest, _, _, bad, _, _ = run_segs(sim, [Seg(goal.settle, None)], after)
        if bad or not goal.reached(last := rest[-1]):
            return None
    if n := getattr(goal, "survive", 0):
        at = sim.save()
        if lands_alive(sim, after, n) is not None:
            if last.state not in AIRBORNE:
                return None
            _rewind(sim, at)
            if lands_alive(sim, after, n, held=expand(segs, cam)[0][-1], air=True) is not None:
                return None
    return len(rows)


def most_flaps(sim, start, segs, cam: float) -> int:
    """The most flaps ``segs`` makes in one jump from ``start`` (the game's per-jump counter)."""
    sim.reset(start)
    return max((flaps_of(r) for r in run_segs(sim, segs, cam)[0]), default=0)


def _trim(segs, ticks: int) -> list:
    """The segments of a string cut at ``ticks``."""
    out, t = [], 0
    for s in segs:
        s = Seg(*s)
        if t + s.n >= ticks:
            out.append(s._replace(n=ticks - t, hold=min(s.hold, ticks - t)))
            return out
        out.append(s)
        t += s.n
    return out


def search(sim, start, start_row, goal: Goal, limits: Limits = Limits(), *, cam: float = 0.0, seed: int = 0,
           seeds=(), log: Callable[[str], None] | None = None, stop: Callable[[], bool] | None = None) -> Result:
    """Go-Explore from ``start`` (a state of ``sim``; ``start_row`` its row; ``cam`` the camera yaw there) to
    ``goal`` (the module docstring) within ``limits.steps`` emulated ticks.  ``seeds``: strings (lists of
    :class:`Seg` or ``(n, heading, hold)`` tuples) to try first.  Returns the first string that reaches the goal
    and confirms, cut at the reaching tick, or why it stopped (``exhausted``, ``the step budget ran out``,
    ``wall-cap``, ``every cell is at the tick limit``, ``cancelled`` once ``stop()`` says so between rounds)."""
    rng = random.Random(seed)
    t0 = time.monotonic()
    res = Result(False, cam=cam)

    def seen(out):                           # every run's taint goes into the result
        res.seen(sim)
        return out
    if (anchor := getattr(goal, "anchor", None)) is not None:     # the start's cost floors an off-graph row's (X.53)
        anchor(start_row)
    root = _Entry([], 0, goal.cost(start_row), start, start_row, 0, cam)
    archive: dict[tuple, _Entry] = {goal.cell(start_row): root}
    res.best_cost = root.cost
    mark = max(1, limits.steps // 20)
    nxt = [mark]                  # the curve's next point
    low = [root.cost, 0]          # the best cost to go at the last progress (PLATEAU_S lower), and its step
    falls = [(0, root.cost)]      # each new best cost to go and its step (the stall's "still falling?")

    def s1(c):                    # a cost to go as kept (no infinity in JSON)
        return None if math.isinf(c) else round(c, 1)

    def point():
        while res.steps >= nxt[0]:
            res.curve.append([res.steps, s1(res.best_cost)])
            nxt[0] += mark

    def finish(why, segs=None):
        if segs is not None:
            res.reached, res.segs, res.ticks = True, [Seg(*s) for s in segs], sum(Seg(*s).n for s in segs)
            res.flaps = most_flaps(sim, start, res.segs, cam)
        else:                                # the stall: the least-cost cell (the first such) and the edge ahead
            best = min(archive.values(), key=lambda e: e.cost)
            res.stall = stall_of(goal, best.row, best.cost, best.ticks, falls, low[1], res.steps)
            why = f"plateau at {stall_name(res.stall)}" if why == "plateau" else why
            why += f"; {exits_text(res.exits)}" if res.exits else ""
        point()
        if not res.curve or res.curve[-1][0] != res.steps:
            res.curve.append([res.steps, s1(res.best_cost)])
        res.why, res.cells, res.seconds = why, len(archive), time.monotonic() - t0
        res.capped = sum(e.ticks >= limits.ticks for e in archive.values())
        return res

    fresh = [0]       # the last round that found a new cell

    def offer(segs, ticks, row, air, cam_, base):
        c = goal.cell(row)
        e = archive.get(c)
        if e is None:
            fresh[0] = res.rounds
        if (e is None and len(archive) < limits.cells) or (e is not None and ticks < e.ticks):
            archive[c] = _Entry(list(segs), ticks, goal.cost(row), None, row, air, cam_, base)
            if archive[c].cost < res.best_cost:
                res.best_cost = archive[c].cost
                falls.append((res.steps, res.best_cost))
            if res.best_cost <= low[0] - PLATEAU_S:
                low[:] = [res.best_cost, res.steps]

    def back_to(e) -> bool:
        if e.state is None:
            sim.reset(e.base.state)
            rows, _, _, bad, _, err = seen(run_segs(sim, e.segs[len(e.base.segs):], e.base.cam))
            res.steps += len(rows)
            if err is not None:            # the way there faults now (it didn't when offered): drop the cell
                res.ended(rows, err)
                return False
            e.state, e.base = sim.save(), None
        else:
            sim.reset(e.state)
        return True

    for s in seeds:                   # a seed runs segment by segment, each end a cell: a miss leaves its trail
        sim.reset(start)
        segs, ticks, row, air, cam_ = [], 0, start_row, 0, cam
        for seg in s:
            seg = Seg(*seg)
            rows, hit, air, bad, cam_, err = seen(run_segs(sim, [seg], cam_, goal, air, limits.fall, limits.flaps))
            res.steps += len(rows)
            res.ended(rows, err)
            if hit is not None:
                cut = segs + [seg._replace(n=hit + 1, hold=min(seg.hold, hit + 1))]
                if seen(confirm(sim, start, cut, cam, goal)) is not None:
                    return finish("a seed string", cut)
                break
            if bad or not rows or ticks + seg.n >= limits.ticks:
                break
            segs.append(seg)
            ticks += seg.n
            row = rows[-1]
            offer(segs, ticks, row, air, cam_, root)

    while res.steps < limits.steps:
        if time.monotonic() - t0 > limits.wall_s():
            return finish("wall-cap")
        if stop is not None and stop():
            return finish("cancelled")
        res.rounds += 1
        ents = list(archive.values())
        best = min(e.cost for e in ents)
        w = [math.exp(-min((e.cost - best) / limits.temp, 50.0)) / math.sqrt(1 + e.visits)
             if e.ticks < limits.ticks else 0.0 for e in ents]
        if not any(w):
            return finish("every cell is at the tick limit")
        if res.rounds - fresh[0] > limits.exhaust:
            return finish(f"exhausted: no new cell in {limits.exhaust} rounds")
        if limits.plateau and res.steps - low[1] >= limits.plateau:
            return finish("plateau")
        e = rng.choices(ents, weights=w)[0]
        e.visits += 1
        if not back_to(e):
            archive.pop(goal.cell(e.row), None)
            continue
        segs, ticks, row, air, cam_ = list(e.segs), e.ticks, e.row, e.air, e.cam
        for _ in range(limits.rollout):
            if ticks >= limits.ticks:
                break
            guide = goal.toward(row) if rng.random() < limits.pursue else (None, False)
            heading, jump, hint = guide[0], guide[1], (guide[2] if len(guide) > 2 else None)
            if len(guide) > 3 and guide[3]:           # the guide asks for the air armor (a spent gauge before a
                seg = Seg(1 + CAST_WAIT, heading, 0, 0, 1)    # flap flight): LT+Y, on 2 ticks after
            else:
                if heading is None or rng.random() < 0.15:
                    heading = rng.uniform(-math.pi, math.pi) if rng.random() < 0.9 else None
                    jump, hint = rng.random() < 0.3, None
                else:
                    heading += rng.gauss(0.0, 0.15)
                    jump = jump or rng.random() < 0.15
                if hint:                              # a run-up: end the segment at the takeoff, give or take a tick
                    n = max(1, min(hint + rng.randint(-1, 1), 4 * limits.seg))
                else:
                    n = limits.seg if rng.random() < 0.8 else rng.randint(1, 2 * limits.seg)
                if limits.flaps is not None and row.state in AIRBORNE and flaps_of(row) >= limits.flaps:
                    jump = False                      # at the flap budget: no more flaps in this jump
                roll = min(ROLL_TAP, n) if limits.roll and rng.random() < limits.roll else 0
                cast = 1 if limits.cast and rng.random() < limits.cast else 0
                if limits.dive and row.state == SWIMMING and rng.random() < limits.dive:
                    roll, jump, cast = n, False, 0    # BLACK held throughout: a dive
                seg = Seg(n, heading, min(limits.hold, n) if jump and not cast else 0, roll, cast)
            rows, hit, air, bad, cam_, err = seen(run_segs(sim, [seg], cam_, goal, air, limits.fall, limits.flaps))
            res.steps += len(rows)
            res.ended(rows, err)
            if hit is not None:
                cut = segs + [seg._replace(n=hit + 1, hold=min(seg.hold, hit + 1))]
                if seen(confirm(sim, start, cut, cam, goal)) is not None:
                    return finish("reached", cut)
                break
            if bad:
                break
            segs.append(seg)
            ticks += seg.n
            row = rows[-1]
            offer(segs, ticks, row, air, cam_, e)
        point()
        if log and res.rounds % 200 == 0:
            log(f"round {res.rounds}: {len(archive)} cells, best cost {res.best_cost:.1f} s, "
                f"{res.steps / (time.monotonic() - t0):.0f} steps/s")
    return finish("the step budget ran out")


def jittered(segs, *, trials: int = 16, degrees: float = 2.0, seed: int = 0, rate: float = 30.0) -> list[list]:
    """:func:`robustness`'s ``trials`` jittered copies of ``segs`` (each jump pressed a 30 fps tick earlier or
    later, at random: at ``rate`` ticks a second, the build's frame rate, ``round(rate / 30)`` ticks, the same time
    (AZ-388), moved between it and the segment before; every heading up to ``degrees`` off; 2 s at rest after: 60
    ticks at 30 fps, AZ-406), the same for the same ``seed`` wherever they run (``l3_pool`` runs a winner's trials as
    tasks)."""
    rng, k = random.Random(seed), max(1, round(rate / 30.0))
    out = []
    segs = [Seg(*s) for s in segs]
    for _ in range(trials):
        jit = [s._replace(heading=None if s.heading is None else s.heading + math.radians(rng.uniform(-degrees, degrees)))
               for s in segs]
        for i in range(1, len(jit)):
            if jit[i].hold or jit[i].roll or jit[i].cast:
                d = rng.randint(-1, 1) * k
                if jit[i - 1].n + d >= 1 and jit[i].n - d >= 1:
                    jit[i - 1], jit[i] = jit[i - 1]._replace(n=jit[i - 1].n + d), \
                        jit[i]._replace(n=jit[i].n - d, hold=min(jit[i].hold, jit[i].n - d))
        out.append(jit + [Seg(60 * k, None)])
    return out


def trial(sim, start, jit, goal: Goal, *, cam: float = 0.0) -> bool:
    """Whether one jittered copy (:func:`jittered`) reaches the goal from ``start`` and stays (``goal.settle``)."""
    jit = [Seg(*s) for s in jit]
    sim.reset(start)
    hit = run_segs(sim, jit, cam, goal)[1]
    return hit is not None and confirm(sim, start, _trim(jit, hit + 1), cam, goal) is not None


def robustness(sim, start, segs, goal: Goal, *, cam: float = 0.0, trials: int = 16, degrees: float = 2.0,
               seed: int = 0, rate: float = 30.0) -> float:
    """The share of ``trials`` jittered copies of ``segs`` (:func:`jittered`, at the build's frame ``rate``) that
    still reach the goal from ``start`` and stay (``goal.settle``)."""
    return sum(trial(sim, start, jit, goal, cam=cam)
               for jit in jittered(segs, trials=trials, degrees=degrees, seed=seed, rate=rate)) / trials


# -- chained segments (D172) -----------------------------------------------------------------------------------------

@dataclass
class Segment:
    """One segment of a chain (D172): its start.  The snapshot ``snapshot`` in the private store ``store`` (taken
    in xemu where the chain is: after the last segment's replay, or a placed set-up), an optional teleport onto a
    floor (``(feet, yaw, cell)``, private), ``settle`` ticks at rest, ``kit`` (the element levels written in RAM,
    R2, and with air the armor cast by LT+Y: Step R1.8g) and ``prefix``, earlier strings run in L3
    ((n, heading, hold) tuples: a spot's way back after its way in; or a found string's ``l3.pads`` segments, its
    camera exact: a chained start, Step TD.2).  ``scene``: whole steps (a snapshot taken at
    the scene tick); ``overlay``: a modded build's code and config cells laid over the snapshot.  The goal is the
    search's (:func:`solve`'s factory)."""
    snapshot: str
    teleport: tuple | None = None
    settle: int = 20
    prefix: list = field(default_factory=list)
    store: str | None = None
    scene: bool = False
    kit: dict | None = None
    overlay: object = None           # a build laid over the snapshot (devkit.sim.overlay.Overlay; Step X.11)
    tail: list = field(default_factory=list)   # pads run after the prefix (``l3.pads`` segments: a douse, Step
                                               # R1.29e, and the strings after it); the camera ends at the last's


def start_of(sim, seg: Segment):
    """(state, row, camera yaw, the pads and rows that set it up) after ``seg``'s teleport, settle ticks, kit,
    prefix and tail; the camera starts where the snapshot's is."""
    pads_, rows = [], []
    if seg.teleport is not None:
        feet, yaw, cell = seg.teleport
        rows.append(sim.teleport(tuple(feet), yaw, cell=cell))
        pads_.append(Pad())
    for _ in range(seg.settle):
        rows.append(sim.step(Pad()))
        pads_.append(Pad())
    if seg.kit is not None:                  # R2's levels at one step's entry; with air, the cast by input
        rows.append(sim.step(writes=sim.kit_writes(seg.kit)))
        pads_.append(Pad())
        if seg.kit.get("air"):
            cast = [Pad(buttons=frozenset({"lt", "y"}))] + [Pad()] * CAST_WAIT
            rows += [sim.step(p) for p in cast]
            pads_ += cast
    if not rows:
        raise ValueError("a segment needs a teleport or settle ticks to read its start")
    cx, cy = struct.unpack("<2f", rows[-1].cam)
    cam = math.atan2(-cx, cy)
    if seg.prefix and isinstance(seg.prefix[0], dict):     # a found string (l3.pads segments): a chained start
        more = l3_pads(seg.prefix)
        rows += [sim.step(p) for p in more]
        pads_ += more
        cx, cy = struct.unpack("<2f", rows[-1].cam) if rows[-1].cam else more[-1].cam
        cam = math.atan2(-cx, cy)
    elif seg.prefix:
        more, cam = expand(seg.prefix, cam)
        rows += [sim.step(p) for p in more]
        pads_ += more
    if seg.tail:                             # a closed-loop action's fixed pads, and what follows it (Step R1.29e)
        more = l3_pads(seg.tail)
        rows += [sim.step(p) for p in more]
        pads_ += more
        cam = more[-1].yaw if more[-1].yaw is not None else cam
    return sim.save(), rows[-1], cam, pads_, rows


def problem_sha12(seg: Segment, goal_spec: dict, limits: Limits) -> str:
    """The problem's identity: the snapshot's metadata hash, the start (teleport, settle, prefix, mode), the goal
    factory's spec and the search's shape (not its budget); its seeds derive from it."""
    doc = {"meta": meta_sha12(read_meta(snapshot_path(seg.snapshot, seg.store))), "teleport": seg.teleport,
           "settle": seg.settle, "prefix": [seg_list(s) for s in seg.prefix], "scene": seg.scene,
           "goal": goal_spec, "shape": limits.shape(), **({"kit": seg.kit} if seg.kit is not None else {}),
           **({"tail": seg.tail} if seg.tail else {}),
           **({"overlay": seg.overlay.sha12} if seg.overlay else {})}
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:12]


def derived_seed(problem: str, i: int) -> int:
    """Seed ``i`` of a problem: int(sha256(problem:i)[:16], 16), the same in any orchestration."""
    return int(hashlib.sha256(f"{problem}:{i}".encode()).hexdigest()[:16], 16)


def solve(seg: Segment, goal_spec: dict, xbe: bytes, *, limits: Limits = Limits(), seeds: int = 8,
          processes: int = 8, strings=(), trials: int = 16, pool=None, rate: float = 30.0) -> dict:
    """Search ``seg`` to the goal ``goal_spec`` makes (``{"module", "factory", "kwargs"}``: a callable by name,
    so a worker builds its own; e.g. the randomizer's ``l3_goal.make_goal``): one Go-Explore per seed (seed ``i``
    = :func:`derived_seed` of :func:`problem_sha12`), each to its step budget or its first confirmed hit, on
    ``pool`` (an :class:`devkit.reach.l3_pool.Pool` on ``seg``'s snapshot) or a pool of ``processes`` made for
    it.  The merge is in seed order: the winner is the lowest index that reached, whatever finished first or how
    many workers ran; higher indices still running are then stopped.  A CPU-heavy batch job, it gives way to a
    waiting xemu sitting (``xemu_queue.BatchToken``, Step X.8: one seed in flight while a ticket waits).
    ``strings``: seed strings every search tries first; ``rate``: the build's frame rate, the winner's robustness
    trials' (:func:`jittered`).  Returns the winner (its segments, the camera yaw it
    starts from, its robustness) or every seed's reason, with counts and taint only."""
    from devkit.reach.l3_pool import Pool, Problem, solve_many
    own = pool is None
    pool = pool or Pool(seg.snapshot, xbe, store=seg.store, workers=min(processes, seeds), name="l3 search")
    try:
        return solve_many(pool, [Problem(seg, goal_spec, limits, seeds, list(strings), trials, rate)])[0]
    finally:
        if own:
            pool.close()
