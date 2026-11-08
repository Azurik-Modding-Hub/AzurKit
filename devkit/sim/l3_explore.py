"""The trick explorer (Step TD.1, D253; the trick-discovery plan §3.2): Go-Explore over L3 with two cell resolutions,
two strings per cell, a finer move set and a bandit, on :mod:`devkit.reach.l3_pool`.

It sits beside :mod:`devkit.sim.l3_search` (whose problems keep their identities) and, like it, knows only a
simulator (``step``, ``save``, ``reset``), rows (``pos``, ``state``, ``hp``, ``obs``) and a guide passed in by name
(the randomizer's ``draft.l3_goal.make_zone_guide`` / ``make_trick_goal``).  A guide answers ``zone(row)`` (None
outside every zone; a top above a zone's floor is outside it), ``region(row)`` (the floor region the feet are on,
a pseudo-region's match) and
``column_top(row)``; a target problem's guide also ``reached``, ``cost`` (the cost to go over its guidance graph),
``toward`` and ``settle``.

**Cells.**  A state's *place* cell is (region, x // 2 m, y // 2 m, feet z // 1.5 m), the region its zone (the
guide's: on a floor, only the logic floor the feet are on), else the phys floor region it stands on (a
pseudo-region's match, so a merge or a later settle never re-keys a place), else ``oob``; its *dynamic* cell, at a
4 m (3 m in height) place, adds the state class (:data:`CLASS`), a log speed bucket up to 300 m/s (in the catch
0x101 a linear one of the charge, :func:`charge`, so each Y there makes a new cell), the sign of vz in the air, the
flaps left and whether the air gauge is full.  A state is new when either cell is.  **Retention:** each cell keeps
two strings, its shortest and the one with the most potential (speed, the charge in the catch, then flaps left,
then gauge), so a charged hang isn't replaced by a quicker plain climb.

**Moves.**  Primitives: 1-32 ticks (8 most often) of a world heading in 24 sectors with noise, or the stick at rest;
magnitude 0.35, 0.7 or 1.0; at most one press, Y, BLACK, a cast (LT+Y the air shield, LT+Y+B the lightning shield:
:data:`CASTS`) or (at low weight) A, B, X or RT, at any tick offset,
held 1-12 ticks; in the water a dive (BLACK held).  On a goal pick, ``Limits.pursue`` of the moves follow the guide
instead (``toward``, as ``l3_search``'s): its heading at full stick for the run-up's ticks it gives, Y held
:data:`JUMP_HOLD` ticks where it says jump, now and then a press in the air (a flap).  The
camera turns toward the heading at most ``inputs.CAM_RATE`` a tick and the stick is solved under it (a real pad's,
:func:`devkit.sim.inputs.stick`).  Options (:class:`Option`; Step TD.3's are :mod:`devkit.sim.l3_options`,
all registered by default) are closed-loop moves that react to each tick's row; they come by spec
(``Limits.options``) and fire where their runtime precondition holds.
A bandit per state class shares the draws among the arms (the press kinds and the options) by the new cells each
tick of theirs found.

**Limits.**  Each arm declares an airborne allowance (a primitive's :data:`PRIM_AIR`); the airborne run's cap is the
largest allowance among the arms used since the takeoff, at most ``Limits.air`` (2,000 ticks).  The game's own
deaths (states 7 and 8, HP 0: the mid-air fall rule 0x8BE00 among them) and an ``L3Error`` end a branch, and so
does a level exit (Step X.52b, as ``l3_search``'s: the fire's row, the guide testing it first, or the unload's stop,
``l3.LevelExit``), which is no fault and taints nothing: ``Result.exits`` counts them by level.  Strings
run up to ``Limits.ticks`` (12,000).  Saved states sit in a compressed LRU (``Limits.lru`` of them; an evicted one
is rebuilt from its nearest kept ancestor by its pads).

**Selection.**  A target problem mixes goal picks (by the guide's cost to go, ``exp(-(c - best) / temp)`` over
``sqrt(1 + visits)``) and novelty picks ``Limits.goal`` / the rest; a discovery problem (no ``reached``) makes
novelty picks only: ``1 / sqrt(1 + visits)`` times the cell's recent productivity times its priors (height above
the column's highest floor, outside every zone, a rare state class, high speed; a guide's ``site_prior``: an
unvisited mined site's nearness, ``draft.sites.Prior``), half of them among the strings the place cells hold and
half among the dynamic cells', so the finer table doesn't swamp the frontier.

**Contacts, regions and transitions (Step TD.4).**  Each row's touched face (``obs.contact``: the face the stored
contact normal belongs to, :mod:`devkit.sim.faces`, on the guide's ``level``) is tallied by face and state class
(``Result.touched``, private; the census's ``draft.sites.census``), and so are the trigger, push and damage volumes
its body centre is in (``faces.Volumes``: ``Result.entered``); a found string's faces are its ``used``.  Per region
(a zone, a pseudo-region's ``R<n>``, ``oob``) the new cells and the picks since its last one: a region is saturated
after ``Limits.idle`` picks with none (``Result.regions``); each step, row by row, from a zone stood in to another
(``Result.transitions``: the count, the first string's ticks and the steps spent) is the logic's edges' record.

**Pseudo-regions.**  A settle outside every zone (state 0 for :data:`SETTLE_TICKS` ticks under
:data:`SETTLE_MPS`) opens one, matched to the floor region it stands on (``guide.region``); settles a walking string
joins (no airborne tick between them) merge.  They are counted; nothing is exported.  The first string that stood
in each zone and the one that opened each pseudo-region are kept (``Result.firsts``, for the private store: a
find's seed for its confirmation, the plan §3.7).

**Ablations** (``Limits.ablate``, the pilot's §4): ``speed`` keys the dynamic cell without its speed bucket,
``options`` draws no option, ``sites`` ignores the guide's ``site_prior`` (whose visited sites are each
exploration's own); any other name is refused.  **The blind protocol** (the plan §4): the explorer refuses a start
from an X.36 snapshot or file (:data:`BLIND`).  :func:`split` cuts a long string at settle
points into D172 pieces that each replay within the long-replay gate.

**Starts.**  A problem's start is an ``l3_search.Segment``: natural (a snapshot: an arrival, a chain's parked "here")
or placed (an R6 teleport): a find from a placed start is reported ``partial`` (D119, Q267).

**Verdicts.**  ``found`` (the guide accepted a row and the string, re-run from the start, still reaches and holds
``settle`` ticks at rest), ``saturated`` (no new cell in ``Limits.exhaust`` rounds), ``not found within budget``
(the step budget ran out; tainted means inconclusive; a discovery problem's: ``budget spent``), ``wall-cap`` or
``cancelled``; a problem's verdict over seeds none of which found names the branches that left the level
(``not found within budget; 12 branches fired levels/earth/e2``: no branch that stayed reached it), and a target
problem's seed that didn't find keeps its stall (``Result.stall``, Step X.52b: ``l3_search.stall_of``'s record of its
least-cost entry: its stage and place by the guide's ``ahead``, its state, whether the best cost still fell).
Reproducible: the budget is
emulated ticks, the random stream ``random.Random(seed)``, every container iterates in insertion order, so a seed
gives the same cells and strings.  Results carry counts, metres, zone ids and string hashes; the string itself
(``l3.pads`` segments) is for the private store.  A pool task gives way between rounds while an xemu sitting waits
for a slot (``xemu_queue.give_way``: a task runs for hours, so the batch token's per-task cap alone can't).  Dev
tooling (Unicorn is a dev dependency).
"""

from __future__ import annotations

import collections
import hashlib
import importlib
import json
import math
import pickle
import random
import time
import zlib
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Callable

import numpy as np

from devkit.sim.faces import Faces, Volumes
from devkit.sim.inputs import camera, stick
from devkit.sim.l3 import L3Error, LevelExit, Pad, engine, fault_site
from devkit.sim.l3_search import (PLATEAU_S, WALL_RATE, Segment, derived_seed, exits_text, problem_sha12,
                                      segments, stall_of, start_of, string_sha12)
from devkit.sim.obs import contact as _obs_contact

AIRBORNE = frozenset({2, 0x102})
DEAD = frozenset({7, 8})
SWIMMING = 6
STOOD = frozenset({0, SWIMMING})          # a zone counts as reached standing or swimming in it (RouteGoal's rule)
WALKING = frozenset({0, 3, 4, 0x100})     # a walking string joins two settles: no airborne tick between them
CLASS = {0: "ground", 5: "ground", 3: "slope", 4: "slide", 2: "air", 0x102: "air", 0x101: "catch", 1: "climb",
         6: "swim", 0x100: "0x100"}       # the state classes (entity+0x94; 5 is the zipline ride), else "other"
CHARGE = 4.6434          # m/s a Y adds in the catch along the stored normal (RE_MOVEMENT "The contact rules")
CATCH_STEP = 0.95 * CHARGE   # the catch's bucket: under a press's least step along the wall's horizontal normal
                             # (CHARGE x |n_xy| >= 0.966 CHARGE at the catch's |nz| < 0.2588) [computed]
SPEED_MIN, SPEED_MAX, SPEED_RATIO = 0.5, 300.0, 1.3   # the log speed buckets: under 0.5 m/s is 0, then x1.3 each
PLACE_M, PLACE_Z, DYN_M, DYN_Z = 2.0, 1.5, 4.0, 3.0
SETTLE_TICKS, SETTLE_MPS = 10, 0.5
BLIND = ("x36-",)        # the blind protocol: no start from X.36's snapshots (the plan §4; compared case-blind)
ABLATE = frozenset({"speed", "options", "sites"})
GATE_TICKS = 5000        # the longest string a D172 piece runs (TD.0's long-replay gate: 5,214 exact in xemu)
SECTORS = 24
MAGS = (0.35, 0.7, 1.0)
HOLD_MAX = 12
PRIM_AIR = 300           # [proposal] a primitive's airborne allowance (ticks); Step X.7's search ended at 120
JUMP_HOLD = 6            # Y held this many ticks for a guided jump (l3_search's)
FLAP_P = 0.15            # [proposal] a guided move's chance of a press at a random tick (a flap in the air), as X.7's
ATTACKS = ("a", "b", "x", "rt")
CASTS = (frozenset({"lt", "y"}), frozenset({"lt", "y", "b"}))   # the air shield and the lightning shield (air 1 +
                         # fire 1; R1.8p's arch): LT with Y, or with Y and B, pressed together and released
ARMS = {"walk": 1.0, "y": 1.0, "black": 0.5, "cast": 0.5, "attack": 0.15, "dive": 0.5}   # the primitives' priors
_BUTTONS = {"walk": frozenset(), "y": frozenset({"y"}), "black": frozenset({"black"}), "dive": frozenset({"black"}),
            **{b: frozenset({b}) for b in ATTACKS}}
OPTIONS = tuple({"module": "devkit.sim.l3_options", "factory": f}      # Step TD.3's options, by spec
                for f in ("Hoist", "SlopeHop", "SteepWalk", "RollChain"))
__all__ = ["Limits", "Option", "Result", "Problem", "explore", "explore_many", "cells", "state_class", "potential",
           "speed_bucket", "charge", "split"]


@dataclass
class Limits:
    """An exploration's budget and shape: ``steps`` emulated ticks (decides the outcome), ``wall_cap_s`` a safety net
    (None: ``steps`` at ``l3_search.WALL_RATE`` a second, Step X.52b), ``ticks`` the longest string, ``air`` the
    airborne cap over every allowance, ``cells`` the archive's size (place plus dynamic cells), ``exhaust`` rounds with
    no new cell after which it is saturated, ``rollout`` moves a pick explores, ``seg`` the commonest primitive's ticks
    (``seg_max`` the longest), ``pursue`` the share of a goal pick's moves that follow the guide, ``goal`` the share of
    goal picks in a target problem, ``temp`` the goal pick's cost temperature (s), ``lru`` the saved states kept,
    ``save_every`` the ticks along a string after which a new entry's state is saved at once (else on its first pick),
    ``options`` the option specs (``{"module", "factory", "kwargs"}``; by default :data:`OPTIONS`), ``ablate`` the
    ablations (:data:`ABLATE`), ``idle`` a region's picks with no new cell after which it is saturated (reported
    only)."""
    steps: int = 2_000_000
    wall_cap_s: float | None = None
    ticks: int = 12_000
    air: int = 2000
    cells: int = 400_000
    exhaust: int = 4000
    rollout: int = 16
    seg: int = 8
    seg_max: int = 32
    pursue: float = 0.5
    goal: float = 0.5
    temp: float = 4.0
    lru: int = 20_000
    save_every: int = 64
    options: tuple = OPTIONS
    ablate: tuple = ()
    idle: int = 400

    def __post_init__(self):
        if isinstance(self.ablate, str) or not set(self.ablate) <= ABLATE:
            raise ValueError(f"ablate {self.ablate!r}: a list of {sorted(ABLATE)} only")
        self.ablate = tuple(sorted(set(self.ablate)))

    def wall_s(self) -> float:
        """The wall cap in seconds: ``wall_cap_s``, else the steps at ``l3_search.WALL_RATE`` a second."""
        return self.steps / WALL_RATE if self.wall_cap_s is None else self.wall_cap_s

    def shape(self) -> dict:
        """What changes the exploration's character (not its budget): part of a problem's identity."""
        return {"explore": 2, **{k: getattr(self, k) for k in ("ticks", "air", "cells", "exhaust", "rollout", "seg",
                                                                "seg_max", "pursue", "goal", "temp")},
                "options": [json.dumps(o, sort_keys=True) for o in self.options],
                **({"ablate": list(self.ablate)} if self.ablate else {})}


class Option:
    """A closed-loop move (Step TD.3 builds them: the plan's CatchCharge, Release, SlopeHop, SteepWalk, RollChain,
    Hoist, AimedDescent): it fires wherever :meth:`applies` holds for the row it starts from and reacts to each
    tick's row (its state, contact normal, speed), never to a site constant.  ``air``: its airborne allowance
    (ticks); ``weight``: its prior in the bandit; ``most``: the most ticks it runs."""
    name = "option"
    air = PRIM_AIR
    weight = 1.0
    most = 240

    def applies(self, row) -> bool:
        return True

    def begin(self, row, rng: random.Random):
        """Its plan for this firing (drawn from ``rng`` only)."""
        return None

    def act(self, plan, row, t: int):
        """Tick ``t``'s input after ``row``: (world heading or None, stick magnitude, buttons), or None when done."""
        return None


def option(spec: dict) -> Option:
    """The option a spec names (``{"module", "factory", "kwargs"}``)."""
    return getattr(importlib.import_module(spec["module"]), spec["factory"])(**spec.get("kwargs", {}))


# -- cells -----------------------------------------------------------------------------------------------------------

def state_class(state: int) -> str:
    return CLASS.get(state, "other")


def _obs(row):
    return getattr(row, "obs", None)


def speed(row) -> float:
    o = _obs(row)
    return math.hypot(*o.vel) if o is not None else 0.0


def charge(row) -> float | None:
    """In the catch (0x101), the velocity along the stored contact normal's horizontal direction: the catch writes
    no velocity, so the entry's speed into the wall stays, and each Y adds :data:`CHARGE` along the normal
    (RE_MOVEMENT "The contact rules"), so this rises by a press's step each Y where the speed need not; else None
    (also with no normal read)."""
    o = _obs(row)
    n = getattr(o, "normal", None)
    if row.state != 0x101 or n is None:
        return None
    h = math.hypot(n[0], n[1])
    return (o.vel[0] * n[0] + o.vel[1] * n[1]) / h if h > 1e-6 else None


def speed_bucket(row) -> int:
    """The log bucket of the row's speed (0 under :data:`SPEED_MIN`, capped at :data:`SPEED_MAX`); in the catch a
    linear one of its :func:`charge` (:data:`CATCH_STEP`), so each charging press is a new cell."""
    v = speed(row)
    if row.state == 0x101:
        q = charge(row)
        return 1000 + math.floor(min(v if q is None else q, SPEED_MAX) / CATCH_STEP)
    if v < SPEED_MIN:
        return 0
    return 1 + int(math.log(min(v, SPEED_MAX) / SPEED_MIN) / math.log(SPEED_RATIO))


def flaps_left(row) -> int:
    o = _obs(row)
    if o is None:
        return 0
    return max(0, (o.flaps or 0) - (o.flaps_used or 0))


def gauge_full(row) -> bool:
    o = _obs(row)
    return o is None or o.gauge is None or o.gauge >= 0.999


def potential(row) -> tuple:
    """A string's potential at its end: (speed, in the catch its :func:`charge`; flaps left, gauge)."""
    o, q = _obs(row), charge(row)
    return speed(row) if q is None else q, flaps_left(row), (1.0 if o is None or o.gauge is None else float(o.gauge))


def cells(row, region, speed: bool = True) -> tuple[tuple, tuple]:
    """(place cell, dynamic cell) of a row in ``region`` (its zone, a pseudo-region's key or ``oob``); without
    ``speed`` (the ablation) the dynamic cell's speed bucket is 0."""
    x, y, z = row.pos[0], row.pos[1], row.pos[2] - 1.0
    vz = _obs(row).vel[2] if _obs(row) is not None else 0.0
    air = row.state in AIRBORNE
    place = (region, math.floor(x / PLACE_M), math.floor(y / PLACE_M), math.floor(z / PLACE_Z))
    dyn = (region, math.floor(x / DYN_M), math.floor(y / DYN_M), math.floor(z / DYN_Z), state_class(row.state),
           speed_bucket(row) if speed else 0, (vz > 0) - (vz < 0) if air else 0, flaps_left(row), gauge_full(row))
    return place, dyn


# -- the archive -----------------------------------------------------------------------------------------------------

class Entry:
    """A kept state: its ``pads`` since ``parent`` (another entry, None for the start), the string's ticks, its last
    row and camera yaw, the airborne run and its cap, the settle run and the walk's pseudo-region at its end, its
    zone, and ``dist`` the ticks since the last state saved on its chain."""
    __slots__ = ("idx", "parent", "pads", "ticks", "row", "cam", "air", "cap", "settle", "walk", "cls", "zone",
                 "dist", "last")

    def __init__(self, idx, parent, pads, ticks, row, cam, air, cap, settle, walk, zone=None):
        self.idx, self.parent, self.pads, self.ticks, self.row, self.cam = idx, parent, pads, ticks, row, cam
        self.air, self.cap, self.settle, self.walk, self.zone = air, cap, settle, walk, zone
        self.cls = state_class(row.state)
        self.dist = (parent.dist if parent is not None else 0) + len(pads)
        self.last = None             # the last zone its string stood in

    def string(self) -> list:
        """Every pad from the start to this entry."""
        parts, e = [], self
        while e is not None:
            parts.append(e.pads)
            e = e.parent
        return [p for part in reversed(parts) for p in part]


class _Grow:
    """A growable numeric column (the selection's per-entry values)."""

    def __init__(self, fill: float = 0.0, dtype=np.float64):
        self.a, self.n, self.fill = np.full(1024, fill, dtype=dtype), 0, fill

    def append(self, v) -> None:
        if self.n == len(self.a):
            self.a = np.concatenate((self.a, np.full(len(self.a), self.fill, dtype=self.a.dtype)))
        self.a[self.n] = v
        self.n += 1

    def view(self) -> np.ndarray:
        return self.a[:self.n]


CLASSES = tuple(dict.fromkeys([*CLASS.values(), "other"]))


class Archive:
    """The explorer's cells and their strings: every kept :class:`Entry` and, per place and dynamic cell
    (:func:`cells`), its two slots, the shortest string and the one of most :func:`potential`.  ``cap`` bounds the
    cells.  Per entry the columns the selection reads: references from cells (0: replaced everywhere, kept only
    as a parent), ticks, state class."""

    def __init__(self, cap: int = 400_000, speed: bool = True):
        self.cap, self.speed = cap, speed
        self.place: dict[tuple, list] = {}
        self.dyn: dict[tuple, list] = {}
        self.entries: list[Entry] = []
        self.refs = (_Grow(0, np.int64), _Grow(0, np.int64))          # slots held: in place cells, dynamic cells
        self.ticks, self.cls = _Grow(0, np.int64), _Grow(0, np.int64)

    def add(self, e: Entry) -> None:
        self.entries.append(e)
        for col in self.refs:
            col.append(0)
        self.ticks.append(e.ticks)
        self.cls.append(CLASSES.index(e.cls))

    def drop_last(self) -> None:
        self.entries.pop()
        for col in (*self.refs, self.ticks, self.cls):
            col.n -= 1

    def live(self, table: int | None = None) -> np.ndarray:
        """The entries some slot holds: of the place cells (``table`` 0), the dynamic ones (1), or either."""
        if table is not None:
            return self.refs[table].view() > 0
        return (self.refs[0].view() > 0) | (self.refs[1].view() > 0)

    def offer(self, e: Entry, region) -> int:
        """Offer ``e`` (the last entry added) to its two cells in ``region``: the new cells it makes, or -1 when
        no slot took it (neither new, shorter nor of more potential)."""
        new, kept, pot = 0, False, potential(e.row)
        for table, key, refs in zip((self.place, self.dyn), cells(e.row, region, self.speed),
                                    (r.view() for r in self.refs)):
            slot = table.get(key)
            if slot is None:
                if len(self.place) + len(self.dyn) < self.cap:
                    table[key] = [e.idx, e.idx]
                    refs[e.idx] += 2
                    new += 1
                    kept = True
                continue
            if e.ticks < self.entries[slot[0]].ticks:
                refs[slot[0]] -= 1
                slot[0] = e.idx
                refs[e.idx] += 1
                kept = True
            if pot > potential(self.entries[slot[1]].row):
                refs[slot[1]] -= 1
                slot[1] = e.idx
                refs[e.idx] += 1
                kept = True
        return new if kept else -1

    def digest(self) -> str:
        """sha256[:12] of every cell's key and its two strings (their ticks and hashes): the determinism check."""
        h = hashlib.sha256()
        for table in (self.place, self.dyn):
            for key, (a, b) in table.items():
                h.update(repr((key, *(f(self.entries[i]) for i in (a, b) for f in (
                    lambda e: e.ticks, lambda e: string_sha12(e.string()))))).encode())
        return h.hexdigest()[:12]


class _States:
    """The saved states, compressed, the most recently used ``cap`` kept (the start's always)."""

    def __init__(self, cap: int):
        self.cap, self.d = cap, collections.OrderedDict()
        self.root = None

    def put(self, idx: int, state) -> None:
        if idx == 0:
            self.root = state
            return
        self.d[idx] = zlib.compress(pickle.dumps(state, protocol=5), 1)
        self.d.move_to_end(idx)
        while len(self.d) > self.cap:
            self.d.popitem(last=False)

    def get(self, idx: int):
        if idx == 0:
            return self.root
        b = self.d.get(idx)
        if b is None:
            return None
        self.d.move_to_end(idx)
        return pickle.loads(zlib.decompress(b))


class _Bandit:
    """Per state class, each arm's draws, ticks and new cells; an arm's weight is its prior times its rate of new
    cells per tick (Laplace-smoothed) over the best eligible arm's, never under a tenth of its prior."""

    def __init__(self, priors: dict):
        self.priors = priors
        self.stats: dict = {}

    def draw(self, cls: str, arms: list, rng: random.Random) -> str:
        rates = [self._rate(cls, a) for a in arms]
        top = max(rates)
        w = [self.priors[a] * max(0.1, r / top) for a, r in zip(arms, rates)]
        return rng.choices(arms, weights=w)[0]

    def _rate(self, cls, arm) -> float:
        d, t, n = self.stats.get((cls, arm), (0, 0, 0))
        return (n + 1.0) / (t + 32.0)

    def credit(self, cls: str, arm: str, ticks: int, new: int) -> None:
        d, t, n = self.stats.get((cls, arm), (0, 0, 0))
        self.stats[(cls, arm)] = (d + 1, t + ticks, n + new)


@dataclass
class Result:
    verdict: str = ""
    found: bool = False
    pads: list = field(default_factory=list)     # the found string's pads (private)
    rows: list = field(default_factory=list)     # its rows from the confirming re-run (private)
    ticks: int = 0
    rounds: int = 0
    steps: int = 0
    place: int = 0
    dyn: int = 0
    entries: int = 0
    pseudo: int = 0
    settles: int = 0
    zones: dict = field(default_factory=dict)    # zone -> [the string's ticks, the steps spent] when first stood in
    classes: dict = field(default_factory=dict)  # state class -> dynamic cells
    top_speed: float = 0.0
    rise_m: float = 0.0
    seconds: float = 0.0
    faults: int = 0
    fault_sites: dict = field(default_factory=dict)   # L3Error.site -> branches it ended (Step X.52)
    exits: dict = field(default_factory=dict)         # level -> branches that ended at its exit (Step X.52b)
    taint: set = field(default_factory=set)
    taint_at: dict = field(default_factory=dict)      # kernel taint -> its sites (L3.taint_at)
    curve: list = field(default_factory=list)    # (steps, cells) every Limits.steps / 20
    bandit: dict = field(default_factory=dict)
    best_cost: float = math.inf
    firsts: dict = field(default_factory=dict)   # zone or pseudo-region match -> its first string's pads (private)
    archive: str | None = None                   # Archive.digest, when asked for
    touched: dict = field(default_factory=dict)  # (face id, state class) -> ticks (private: the census's)
    entered: dict = field(default_factory=dict)  # (volume id, state class) -> ticks (private: the census's)
    used: list = field(default_factory=list)     # the found string's touched faces (private)
    regions: dict = field(default_factory=dict)  # region -> [new cells, picks, saturated]
    transitions: dict = field(default_factory=dict)   # "zone>zone" -> [count, the string's ticks, the steps spent]
    stall: dict | None = None    # a target problem not found: l3_search.stall_of's record of its least-cost entry

    def summary(self) -> dict:
        """Counts, metres, zone ids and the string's hash (no positions), with the engine that ran it (``l3.engine``,
        Step X.52b)."""
        return {"verdict": self.verdict, "found": self.found, "ticks": self.ticks, "rounds": self.rounds,
                "steps": self.steps, "cells": {"place": self.place, "dynamic": self.dyn}, "entries": self.entries,
                "pseudo_regions": self.pseudo, "settles_outside": self.settles,
                "zones": dict(sorted(self.zones.items())), "classes": dict(sorted(self.classes.items())),
                "top_speed_mps": round(self.top_speed, 1), "rise_m": round(self.rise_m, 1),
                "seconds": round(self.seconds, 1),
                "ticks_per_s": round(self.steps / self.seconds) if self.seconds else 0, "faults": self.faults,
                "fault_sites": dict(sorted(self.fault_sites.items(), key=lambda kv: (-kv[1], kv[0]))),
                "exits": dict(sorted(self.exits.items())),
                "taint": sorted(self.taint), "taint_at": {k: sorted(v) for k, v in sorted(self.taint_at.items())},
                "curve": self.curve,
                "best_cost_s": None if math.isinf(self.best_cost) else round(self.best_cost, 1),
                "bandit": {f"{c}/{a}": list(v) for (c, a), v in sorted(self.bandit.items())},
                "faces_touched": len({f for f, _ in self.touched}), "regions": dict(sorted(self.regions.items())),
                "transitions": dict(sorted(self.transitions.items())), "stall": self.stall, "engine": engine(),
                **({"string_sha12": string_sha12(self.pads, rows=self.rows or None)} if self.found else {})}


class _Explorer:
    def __init__(self, sim, start, start_row, guide, limits: Limits, cam: float, seed: int, options, stop, log,
                 pause=None):
        self.sim, self.start, self.guide, self.lim, self.stop, self.log = sim, start, guide, limits, stop, log
        self.pause = pause
        self.rng = random.Random(seed)
        self.target = callable(getattr(guide, "reached", None))
        self.options = {} if "options" in limits.ablate else {f"opt:{o.name}": o for o in options}
        lv = getattr(guide, "level", None)
        self.faces, self.vols = (Faces.of_level(lv), Volumes.of_level(lv)) if lv is not None else (None, None)
        self.touched: collections.Counter = collections.Counter()
        self.entered: collections.Counter = collections.Counter()
        self.sites_seen: set = set()             # the site prior's visited sites, this exploration's own
        self.reg_new, self.reg_picks, self.reg_idle = (collections.Counter() for _ in range(3))
        self.bandit = _Bandit({**ARMS, **{k: o.weight for k, o in self.options.items()}})
        self.res = Result()
        self.t0 = time.monotonic()
        self.z0 = start_row.pos[2]
        self.arch = Archive(limits.cells, "speed" not in limits.ablate)
        self.cost, self.visits, self.prod, self.prior = _Grow(math.inf), _Grow(), _Grow(1.0), _Grow(1.0)
        self.states = _States(limits.lru)
        self.pseudo: dict = {}                   # match key -> pseudo-region id
        self.parent_of: list[int] = []           # union-find over pseudo-region ids
        self.fresh = 0                           # the last round that found a new cell
        self.best: Entry | None = None           # a target problem's least-cost entry (the first such), its stall
        self.falls: list = []                    # each new best cost to go and its step
        self.low = (math.inf, 0)                 # the best cost at its last fall by PLATEAU_S, and that step
        if self.target and (anchor := getattr(guide, "anchor", None)) is not None:   # the start's cost floors an
            anchor(start_row)                                                   # off-graph row's (Step X.53)
        root = self._entry(None, (), 0, start_row, cam, 0, PRIM_AIR, 0, None, None)
        self.states.put(0, start)
        self.arch.offer(root, self._region(root))
        self._note(root)

    # -- pseudo-regions
    def _find(self, i: int) -> int:
        while self.parent_of[i] != i:
            self.parent_of[i] = self.parent_of[self.parent_of[i]]
            i = self.parent_of[i]
        return i

    def _key(self, row) -> str:
        """A row's pseudo-region match: ``R<n>``, the phys floor region it stands on, else ``C<x>.<y>.<z>``, its
        2 m place (private: a position)."""
        r = self.guide.region(row) if hasattr(self.guide, "region") else None
        return f"R{r}" if r is not None else "C" + ".".join(map(str, cells(row, None)[0][1:]))

    def _settled(self, row, walk, string):
        """A settle (the row has stood still SETTLE_TICKS ticks): outside every zone it opens or joins the
        pseudo-region of the floor region it stands on (a new one keeps ``string()``, its first string), merged
        with ``walk``'s (the last settle a walking string came from); returns the walk's pseudo-region from here
        (None inside a zone)."""
        if self.guide.zone(row) is not None:
            return None
        key = self._key(row)
        pid = self.pseudo.get(key)
        if pid is None:
            pid = self.pseudo[key] = len(self.parent_of)
            self.parent_of.append(pid)
            self.res.firsts[key] = string()
        self.res.settles += 1
        if walk is not None and self._find(walk) != self._find(pid):
            self.parent_of[self._find(walk)] = self._find(pid)
        return pid

    def _region(self, e: Entry) -> str:
        if e.zone is not None:
            return e.zone
        key = self._key(e.row)
        return key if key[0] == "R" else "oob"

    # -- the archive
    def _entry(self, parent, pads, ticks, row, cam, air, cap, settle, walk, last) -> Entry:
        e = Entry(len(self.arch.entries), parent, tuple(pads), ticks, row, cam, air, cap, settle, walk,
                  self.guide.zone(row))
        e.last = last if parent is not None else (e.zone if row.state in STOOD else None)
        self.arch.add(e)
        self.cost.append(self.guide.cost(row) if self.target else 0.0)
        self.visits.append(0.0)
        self.prod.append(1.0)
        self.prior.append(self._prior(e))
        return e

    def _drop_last(self) -> None:
        self.arch.drop_last()
        for col in (self.cost, self.visits, self.prod, self.prior):
            col.n -= 1

    def _prior(self, e: Entry) -> float:
        """Height above the column's highest floor (standing, not flying), outside every zone, high speed and, when
        the guide has one (and no ``sites`` ablation), its ``site_prior`` (an unvisited mined site's nearness); the
        rare class is applied per round."""
        row, p = e.row, 1.0
        if hasattr(self.guide, "site_prior") and "sites" not in self.lim.ablate:
            p *= self.guide.site_prior(row, self.sites_seen)
        if row.state not in AIRBORNE and hasattr(self.guide, "column_top"):
            top = self.guide.column_top(row)
            if top is not None:
                p *= 1.0 + min(max(row.pos[2] - 1.0 - top, 0.0) / 5.0, 2.0)
        if e.zone is None:
            p *= 2.0
        return p * (1.0 + min(speed(row) / 20.0, 2.0))

    def _note(self, e: Entry) -> None:
        if e.zone is not None and e.row.state in STOOD and e.zone not in self.res.zones:
            self.res.zones[e.zone] = [e.ticks, self.res.steps]
            self.res.firsts[e.zone] = e.string()
        self.res.top_speed = max(self.res.top_speed, speed(e.row))
        self.res.rise_m = max(self.res.rise_m, e.row.pos[2] - self.z0)
        if self.target and (c := float(self.cost.view()[e.idx])) < self.res.best_cost:
            self.res.best_cost, self.best = c, e
            self.falls.append((self.res.steps, c))
            if c <= self.low[0] - PLATEAU_S:
                self.low = (c, self.res.steps)

    # -- contacts
    def _face(self, row):
        o = _obs(row)
        return _obs_contact(o, self.faces) if self.faces is not None and o is not None else None

    def _touch(self, row) -> None:
        if (f := self._face(row)) is not None:
            self.touched[(f.id, state_class(row.state))] += 1
        if self.vols is not None:
            for v in self.vols.holding(row.pos):
                self.entered[(v, state_class(row.state))] += 1

    def _stood(self, row, last, ticks):
        """The last zone the string stood in after ``row`` (``ticks`` into it): a step from ``last`` into another
        zone stood in is a transition."""
        if row.state not in STOOD or (z := self.guide.zone(row)) is None:
            return last
        if last is not None and z != last:
            self.res.transitions.setdefault(f"{last}>{z}", [0, ticks, self.res.steps])[0] += 1
        return z

    # -- running
    def _seen(self):
        self.res.taint.update(getattr(self.sim, "taint", ()))
        for k, v in getattr(self.sim, "taint_at", {}).items():
            self.res.taint_at.setdefault(k, set()).update(v)

    def _fault(self, exc) -> None:
        if isinstance(exc, LevelExit):          # the unload's stop: a level exit, no fault (Step X.52b)
            return self._exit("unload")
        self.res.faults += 1
        site = fault_site(exc)
        self.res.fault_sites[site] = self.res.fault_sites.get(site, 0) + 1

    def _exit(self, to: str) -> None:
        self.res.exits[to] = self.res.exits.get(to, 0) + 1

    def _back_to(self, e: Entry) -> bool:
        """The simulator at ``e``'s state: from the LRU, else rebuilt from its nearest kept ancestor."""
        st = self.states.get(e.idx)
        if st is not None:
            self.sim.reset(st)
            return True
        chain, a = [], e
        while (st := self.states.get(a.idx)) is None:
            chain.append(a)
            a = a.parent
        self.sim.reset(st)
        for b in reversed(chain):
            for p in b.pads:
                try:
                    self.sim.step(p)
                except L3Error as exc:
                    self._fault(exc)
                    self._seen()
                    return False
                self.res.steps += 1
        self._seen()
        self.states.put(e.idx, self.sim.save())
        e.dist = 0
        return True

    def _pick(self):
        """A goal pick or a novelty pick (the module docstring): (entry, whether a goal pick)."""
        a = self.arch
        live = a.live() & (a.ticks.view() < self.lim.ticks)
        visits = self.visits.view()
        goal = self.target and self.rng.random() < self.lim.goal
        if goal:
            c = self.cost.view()
            fin = live & np.isfinite(c)
            if fin.any():
                w = np.where(fin, np.exp(-np.minimum((c - c[fin].min()) / self.lim.temp, 50.0)), 0.0)
                w = w / np.sqrt(1.0 + visits)
            else:
                goal, w = False, None
        if not goal:                      # half the picks among the place cells' strings, half the dynamic cells'
            t = int(self.rng.random() < 0.5)
            if (one := live & a.live(t)).any():
                live = one
            cls = a.cls.view()
            n = np.bincount(cls[live], minlength=len(CLASSES)).astype(np.float64)
            w = self.prior.view() * (1.0 + 1.0 / np.sqrt(np.maximum(n[cls], 1.0))) * (0.1 + self.prod.view()) \
                / np.sqrt(1.0 + visits)
        w = np.where(live, w, 0.0)
        tot = float(w.sum())
        if tot <= 0.0:
            return None, goal
        c_ = np.cumsum(w)
        return a.entries[min(int(np.searchsorted(c_, self.rng.random() * tot, "right")), len(c_) - 1)], goal

    def _arms(self, row) -> list[str]:
        arms = [a for a in ARMS if a != "dive" or row.state == SWIMMING]
        return arms + [k for k, o in self.options.items() if o.applies(row)]

    def _pursue(self, row):
        """A move that follows the guide (``toward``: a heading, whether to jump now, and the ticks of a run-up
        to a takeoff), or None when it gives no heading."""
        rng, lim = self.rng, self.lim
        g = self.guide.toward(row)
        if g[0] is None:
            return None
        heading, jump, hint = g[0] + rng.gauss(0.0, 0.05), g[1], (g[2] if len(g) > 2 else None)
        n = max(1, min(hint + rng.randint(-1, 1), lim.seg_max)) if hint else \
            lim.seg if rng.random() < 0.5 else rng.randint(1, lim.seg_max)
        if jump:
            n = max(n, JUMP_HOLD)
            return [(heading, 1.0, _BUTTONS["y"] if t < JUMP_HOLD else frozenset()) for t in range(n)]
        flap = rng.randrange(n) if rng.random() < FLAP_P else -1
        return [(heading, 1.0, _BUTTONS["y"] if t == flap else frozenset()) for t in range(n)]

    def _primitive(self, arm: str, row):
        """A primitive move's per-tick inputs: (heading, magnitude, buttons) each."""
        rng, lim = self.rng, self.lim
        n = lim.seg if rng.random() < 0.5 else rng.randint(1, lim.seg_max)
        heading = None
        if rng.random() >= 0.1:
            k = rng.randrange(SECTORS)
            heading = (k + rng.uniform(-0.5, 0.5)) * 2 * math.pi / SECTORS - math.pi
        mag = rng.choice(MAGS)
        if arm == "walk":
            return [(heading, mag, frozenset())] * n
        if arm == "dive":
            return [(heading, mag, _BUTTONS["dive"])] * n
        b = rng.choice(CASTS) if arm == "cast" else _BUTTONS[rng.choice(ATTACKS) if arm == "attack" else arm]
        off, hold = rng.randrange(n), rng.randint(1, HOLD_MAX)
        n = min(max(n, off + hold), lim.seg_max)       # a press may lengthen the move, never past seg_max
        return [(heading, mag, b if off <= t < off + hold else frozenset()) for t in range(n)]

    def _confirm(self, pads) -> list | None:
        """The rows of ``pads`` re-run from the start when the guide accepts its last row only and still holds the
        player after ``settle`` ticks at rest; else None."""
        g, sim = self.guide, self.sim
        sim.reset(self.start)
        rows = []
        try:
            for k, p in enumerate(pads):
                rows.append(sim.step(p))
                if g.reached(rows[-1]) and k < len(pads) - 1:
                    return None
            if not rows or not g.reached(rows[-1]):
                return None
            rest = [sim.step(Pad((0.0, 0.0), frozenset(), pads[-1].yaw)) for _ in range(getattr(g, "settle", 0))]
        except L3Error:
            return None
        return rows if not rest or g.reached(rest[-1]) else None

    def _rollout(self, e: Entry, goal: bool):
        """Explore from ``e``: up to ``Limits.rollout`` moves; the confirmed winner's (pads, rows), else None."""
        sim, lim, res = self.sim, self.lim, self.res
        row, cam, air, cap, settle, walk, last = e.row, e.cam, e.air, e.cap, e.settle, e.walk, e.last
        base, since, ticks, made = e, [], e.ticks, 0
        for _ in range(lim.rollout):
            if ticks >= lim.ticks:
                break
            cls = state_class(row.state)
            moves = self._pursue(row) if goal and self.rng.random() < lim.pursue else None
            arm = "pursue" if moves is not None else self.bandit.draw(cls, self._arms(row), self.rng)
            opt = self.options.get(arm)
            plan = opt.begin(row, self.rng) if opt is not None else None
            if moves is None and opt is None:
                moves = self._primitive(arm, row)
            allow = opt.air if opt is not None else PRIM_AIR
            n, bad = 0, False
            for t in range(opt.most if opt is not None else len(moves)):
                mv = opt.act(plan, row, t) if opt is not None else moves[t]
                if mv is None:
                    break
                heading, mag, buttons = mv
                cam = camera(cam, heading)
                pad = Pad(stick(heading, cam, mag), buttons, cam)
                try:
                    row = sim.step(pad)
                except L3Error as exc:
                    self._fault(exc)
                    bad = True
                    break
                res.steps += 1
                n += 1
                since.append(pad)
                self._touch(row)
                last = self._stood(row, last, ticks + n)
                if row.state in AIRBORNE:
                    cap = allow if air == 0 else max(cap, allow)
                    air += 1
                else:
                    air = 0
                if row.state in DEAD or row.hp <= 0 or air > min(cap, lim.air):
                    bad = True
                    break
                settle = settle + 1 if row.state == 0 and speed(row) < SETTLE_MPS else 0
                if row.state not in WALKING:
                    walk = None
                if settle == SETTLE_TICKS:
                    walk = self._settled(row, walk, lambda: base.string() + since)
                if self.target and self.guide.reached(row):
                    pads = base.string() + since
                    rows = self._confirm(pads)
                    self._seen()
                    if rows is not None:
                        if (z := self.guide.zone(row)) is not None:
                            res.zones.setdefault(z, [len(pads), res.steps])
                        return pads, rows
                    bad = True
                    break
                if (ex := getattr(row, "exit", None)) is not None:   # a level exit: the branch ends on its row
                    self._exit(ex[0] or ex[1] or "?")
                    bad = True
                    break
                if ticks + n >= lim.ticks:
                    break
            self._seen()
            ticks += n
            if bad or not n:
                self.bandit.credit(cls, arm, n, 0)
                break
            new = self._entry(base, since, ticks, row, cam, air, cap, settle, walk, last)
            reg = self._region(new)
            got = self.arch.offer(new, reg)
            if got > 0:
                self.reg_new[reg] += got
                self.reg_idle[reg] = 0
            self.bandit.credit(cls, arm, n, max(got, 0))
            self._note(new)
            if got > 0:
                self.fresh = res.rounds
            if got >= 0:
                made += got
                base, since = new, []
                if new.dist >= lim.save_every:      # a long chain since the last saved state: save this one now
                    self.states.put(new.idx, sim.save())
                    new.dist = 0
            else:                                   # not kept: the string goes on from the last kept entry
                self._drop_last()
        p = self.prod.view()
        p[e.idx] = 0.7 * p[e.idx] + 0.3 * min(made, 5) / 5.0
        return None

    def run(self) -> Result:
        lim, res = self.lim, self.res
        mark = max(1, lim.steps // 20)
        nxt = mark
        while res.steps < lim.steps:
            if self.pause is not None:
                self.t0 += self.pause()           # time given way to a sitting doesn't count against the wall cap
            if time.monotonic() - self.t0 > lim.wall_s():
                return self._finish("wall-cap")
            if self.stop is not None and self.stop():
                return self._finish("cancelled")
            if res.rounds - self.fresh > lim.exhaust:
                return self._finish("saturated")
            res.rounds += 1
            e, goal = self._pick()
            if e is None:
                return self._finish("saturated")
            self.visits.view()[e.idx] += 1
            reg = self._region(e)
            self.reg_picks[reg] += 1
            self.reg_idle[reg] += 1
            if not self._back_to(e):
                for col in self.arch.refs:
                    col.view()[e.idx] = 0
                continue
            won = self._rollout(e, goal)
            if won is not None:
                res.found, (res.pads, res.rows), res.ticks = True, won, len(won[0])
                res.used = sorted({f.id for r in res.rows if (f := self._face(r)) is not None})
                return self._finish("found")
            while res.steps >= nxt:
                res.curve.append([res.steps, len(self.arch.place) + len(self.arch.dyn)])
                nxt += mark
            if self.log and res.rounds % 500 == 0:
                self.log(f"round {res.rounds}: {len(self.arch.place)} place / {len(self.arch.dyn)} dynamic cells, "
                         f"{res.steps / (time.monotonic() - self.t0):.0f} ticks/s")
        return self._finish("not found within budget" if self.target else "budget spent")

    def _finish(self, why: str) -> Result:
        res, a = self.res, self.arch
        res.verdict = why
        res.place, res.dyn, res.entries = len(a.place), len(a.dyn), len(a.entries)
        res.pseudo = len({self._find(i) for i in range(len(self.parent_of))})
        res.classes = dict(collections.Counter(k[4] for k in a.dyn))
        res.bandit = dict(self.bandit.stats)
        res.touched, res.entered = dict(self.touched), dict(self.entered)
        res.regions = {r: [self.reg_new[r], self.reg_picks[r], self.reg_idle[r] >= self.lim.idle]
                       for r in sorted(set(self.reg_new) | set(self.reg_picks))}
        if self.target and not res.found and self.best is not None:
            res.stall = stall_of(self.guide, self.best.row, res.best_cost, self.best.ticks, self.falls, self.low[1],
                                 res.steps)
        res.seconds = time.monotonic() - self.t0
        return res


def explore(sim, start, start_row, guide, limits: Limits = Limits(), *, cam: float = 0.0, seed: int = 0,
            options=(), stop: Callable[[], bool] | None = None, log: Callable[[str], None] | None = None,
            digest: bool = False, pause: Callable[[], float] | None = None) -> Result:
    """Explore from ``start`` (a state of ``sim``; ``start_row`` its row, ``cam`` the camera yaw there) under
    ``guide`` (the module docstring) within ``limits.steps`` emulated ticks; ``options``: :class:`Option`\\ s the
    bandit may draw; ``pause()`` runs between rounds (the seconds it waited).  ``digest``: the result's
    ``archive`` is :meth:`Archive.digest` (the determinism check)."""
    ex = _Explorer(sim, start, start_row, guide, limits, cam, seed, options, stop, log, pause)
    res = ex.run()
    if digest:
        res.archive = ex.arch.digest()
    return res


# -- pool tasks ------------------------------------------------------------------------------------------------------

@dataclass
class Problem:
    """An exploration problem: ``seg``'s start (its snapshot the pool's), the guide's spec, the limits and
    ``seeds`` explorations (seed ``i`` derived from the problem); a placed start (a teleport) makes its finds
    partial."""
    seg: Segment
    guide_spec: dict
    limits: Limits = field(default_factory=Limits)
    seeds: int = 1


def blind(*starts) -> None:
    """The blind protocol (the plan §4): refuse a start from X.36 (:data:`BLIND`, by name, any part of a path):
    a :class:`Segment` from an X.36 snapshot or a store under an X.36 folder, or a start file (a path) there."""
    for s in starts:
        for name in ((s.snapshot, s.store) if isinstance(s, Segment) else (s,)):
            if name is not None and any(part.lower().startswith(BLIND) for part in PurePath(str(name)).parts):
                raise ValueError(f"{str(name)!r} is an X.36 snapshot or file: the explorer reads none (the blind "
                                 "protocol)")


def explore_task(w, seg: Segment, guide_spec: dict, limits: Limits, i: int, seed: int, slot: int,
                 digest: bool = False) -> dict:
    """One seed's exploration from ``seg``'s start on a pool worker (``l3_pool.Worker``): its summary, its string
    and each zone's and pseudo-region's first string (``l3.pads`` segments: for the private store) and camera yaw;
    it stops between rounds once flag ``slot`` is set, and gives way there while an xemu sitting waits.  A start
    that raises ``L3Error`` here fails this seed's run at its start (Step X.52b, as ``l3_pool.search_task``'s):
    verdict ``start: <the error>``, its site counted, tainted ``failed:start`` (it refutes nothing)."""
    from devkit.xemu.queue import give_way
    blind(seg)
    sim = w.sim(seg.scene, deep=False, overlay=seg.overlay)
    guide = w.goal(guide_spec)
    try:
        start, row, cam, _, _ = start_of(sim, seg)
    except L3Error as exc:
        res = Result(verdict=f"start: {exc}", taint={"failed:start", *getattr(sim, "taint", ())}, faults=1,
                     fault_sites={fault_site(exc): 1})
        return {"index": i, "seed": seed, "partial": seg.teleport is not None, **res.summary(), "cam": 0.0,
                "string": None, "firsts": {}, "touched": [], "used": [], "entered": []}

    def stop() -> bool:
        return bool(w.stop[slot])
    res = explore(sim, start, row, guide, limits, cam=cam, seed=seed, options=[option(o) for o in limits.options],
                  stop=stop, digest=digest, pause=lambda: give_way(stop))
    return {"index": i, "seed": seed, "partial": seg.teleport is not None, **res.summary(), "cam": cam,
            **({"archive": res.archive} if digest else {}),
            "string": segments(res.pads, res.rows) if res.found else None,
            "firsts": {k: segments(v) for k, v in res.firsts.items()},
            "touched": [[f, c, n] for (f, c), n in sorted(res.touched.items())], "used": res.used,
            "entered": [[f, c, n] for (f, c), n in sorted(res.entered.items())]}


def _verdict(rs: list[dict]) -> str:
    """The verdict over seeds none of which found: the first's ``start: <the error>`` when every seed's start
    failed, saturated when every seed is, else a wall cap or a cancel if any seed ended so, else the budget's (``not
    found within budget``; a discovery problem's ``budget spent``); with the branches that left the level, by the
    level they load (Step X.52b: ``; 12 branches fired levels/earth/e2``)."""
    vs = [r["verdict"] for r in rs]
    if vs and all(v.startswith("start: ") for v in vs):
        return vs[0]
    exits = collections.Counter()
    for r in rs:
        exits.update(r.get("exits") or {})
    left = f"; {exits_text(exits)}" if exits else ""
    if vs and all(v == "saturated" for v in vs):
        return "saturated" + left
    return (next((v for v in ("cancelled", "wall-cap") if v in vs), None) or next(
        (v for v in vs if v in ("not found within budget", "budget spent")), "not found within budget")) + left


def explore_many(pool, problems: list[Problem], *, digest: bool = False) -> list[dict]:
    """Each problem's explorations on ``pool`` at once, under a ``BatchToken``: per problem, the winner (the lowest
    seed index that found; its higher seeds still running are then stopped) and the summaries of the seeds up to
    it (every seed's when none found, so the totals don't depend on the worker count), with the verdict over them
    (``found``, else :func:`_verdict`; ``inconclusive`` when a run is tainted), the zones they reached (the least
    ticks) and, private, each zone's and pseudo-region's first string (the shortest).  On any exit every seed still
    running is stopped at its next round."""
    from devkit.reach.l3_pool import SLOTS
    from devkit.xemu.queue import BatchToken
    if len(problems) > SLOTS:
        raise ValueError(f"at most {SLOTS} problems at once")
    for p in problems:
        blind(p.seg)
        if (p.seg.snapshot, p.seg.store and str(p.seg.store)) != (pool.snapshot, pool.store):
            raise ValueError(f"a problem starts at snapshot {p.seg.snapshot!r}; this pool serves {pool.snapshot!r}")
    names = [problem_sha12(p.seg, p.guide_spec, p.limits) for p in problems]
    todo = collections.deque((i, j) for i, p in enumerate(problems) for j in range(p.seeds))
    runs: list[dict[int, dict]] = [{} for _ in problems]
    win: list[int | None] = [None] * len(problems)
    for i in range(len(problems)):
        pool.stop[i] = 0

    def decide(i: int) -> None:
        for j in range(problems[i].seeds):
            if j not in runs[i]:
                return
            if runs[i][j]["found"]:
                win[i] = j
                break
        else:
            win[i] = -1
        pool.stop[i] = 1

    running: dict = {}
    try:
        with BatchToken(pool.name, pool.workers) as tok:
            while todo or running:
                while todo and len(running) < tok.allowed():
                    i, j = todo.popleft()
                    if win[i] is not None:
                        continue
                    p = problems[i]
                    running[pool.submit(explore_task, p.seg, p.guide_spec, p.limits, j, derived_seed(names[i], j),
                                        i, digest)] = (i, j)
                if not running:
                    continue
                done = tok.wait(running)
                for f in done:
                    i, j = running.pop(f)
                    runs[i][j] = f.result()
                    if win[i] is None:
                        decide(i)
    finally:
        for i in range(len(problems)):
            pool.stop[i] = 1
    out = []
    for i, name in enumerate(names):
        rs = [runs[i][j] for j in range(win[i] + 1 if win[i] >= 0 else problems[i].seeds)]
        w_ = rs[-1] if win[i] >= 0 else None
        exits = collections.Counter()
        for r in rs:
            exits.update(r.get("exits") or {})
        zones: dict = {}
        firsts: dict = {}
        touched: collections.Counter = collections.Counter()
        entered: collections.Counter = collections.Counter()
        moves: dict = {}
        for r in rs:
            for z, (t, s) in r["zones"].items():
                if z not in zones or t < zones[z][0]:
                    zones[z] = [t, s]
            for f, c, n in r["touched"]:
                touched[(f, c)] += n
            for f, c, n in r["entered"]:
                entered[(f, c)] += n
            for k, (n, t, s) in r["transitions"].items():
                m = moves.setdefault(k, [0, t, s])
                m[0] += n
                m[1:] = min(m[1:], [t, s])
            for k, segs in r["firsts"].items():
                if k not in firsts or sum(x["n"] for x in segs) < sum(x["n"] for x in firsts[k]):
                    firsts[k] = segs
        out.append({"problem": name, "engine": engine(), "verdict": "found" if w_ else _verdict(rs),
                    "found": w_ is not None, "exits": dict(sorted(exits.items())),
                    "inconclusive": w_ is None and any(r["taint"] for r in rs),
                    "partial": problems[i].seg.teleport is not None,
                    "winner": w_ and {k: v for k, v in w_.items() if k not in ("firsts", "touched", "entered")},
                    "zones": dict(sorted(zones.items())), "steps": sum(r["steps"] for r in rs),
                    "runs": [{k: v for k, v in r.items()
                              if k not in ("string", "firsts", "touched", "used", "entered")} for r in rs],
                    "transitions": dict(sorted(moves.items())),
                    "saturated": sorted({g for r in rs for g, (_, _, sat) in r["regions"].items() if sat}),
                    "firsts": firsts, "touched": [[f, c, n] for (f, c), n in sorted(touched.items())],
                    "entered": [[f, c, n] for (f, c), n in sorted(entered.items())],
                    "used": w_["used"] if w_ else []})
    return out


def split(rows, *, most: int = GATE_TICKS, settle: int = SETTLE_TICKS) -> list[dict]:
    """A string's D172 pieces (Step TD.4b): ``rows`` its L3 rows (one per pad); each piece ``{"start", "ticks",
    "settled"}`` (the pads ``[start, start + ticks)``) runs at most ``most`` ticks and ends at the last settle point
    in its reach (a row ending ``settle`` ticks in state 0 under :data:`SETTLE_MPS`: the player at rest, where the
    next piece's xemu replay starts from the halted guest, D172), else at ``most`` (``settled`` false: the chain
    joins in motion, which counts only from the snapshot where the last piece's replay halted); the last piece ends
    with the string (``settled`` when it ends at rest)."""
    ends, run = [], 0
    for k, r in enumerate(rows):
        run = run + 1 if r.state == 0 and speed(r) < SETTLE_MPS else 0
        if run >= settle:
            ends.append(k + 1)
    out, at, j = [], 0, 0
    while len(rows) - at > most:
        while j < len(ends) and ends[j] <= at:
            j += 1
        best = None
        while j < len(ends) and ends[j] - at <= most:
            best, j = ends[j], j + 1
        cut = best if best is not None else at + most
        out.append({"start": at, "ticks": cut - at, "settled": best is not None})
        at = cut
    out.append({"start": at, "ticks": len(rows) - at, "settled": bool(ends) and ends[-1] == len(rows)})
    return out
