"""The reach engine's targeted pass (Steps R2.16a-c; the R2.16 design §1): aims at each derived jump and flap zone
edge's flight, and the refinement on what a run left.

An aimed job (:func:`aim_jobs`, :func:`refine_jobs`) is a runner job (``runner``'s module docstring) with a
``target`` (the derived flight's landing moved on along the flight onto its region and its floor face,
``Nodes.snap``), ``aim`` (the unsnapped point the held aims steer at), ``from`` (its edge's from-zone: a start that
settles in it counts, on any node, ``graph.Graph``) and ``stop`` (its air level, to-zone and zoning: the job ends at
its first :func:`hit` whose body stays there :mod:`.hold`'s 60 idle ticks on).  :func:`run_job` runs it.  First its
target on L3's own floor (:func:`floor`, Step R2.16d): where a body placed at the target doesn't stand in its
to-zone, every aim steers at the nearest point of the
:data:`SCAN_M` grid round it where one does (at least :data:`INTERIOR` of its 4 neighbours standing there too, else
the nearest): the engine's face list misses floors L3 stands on up to a body radius past a face's edge, and
``Nodes.snap`` wants a point half a metre inside a face, which a narrow ledge can't give (the diagnosis: for 68 of
75 sampled misses the target didn't stand, and L3 stood the to-zone a median 0.5 m off); none within reach is L3's
answer for the edge's landing (``rec["floor"]``).  Its starts as the runner's, then, when every one falls, the
:data:`RING` around its first, kept only where the body settles in its from-zone (Step R2.16c's skeptic, S5: the
face list ``Nodes.starts`` reads misses floors L3 stands on, and for 28 of 32 sampled edges whose starts all fell a
body stood 0.25 m off); each macro under :class:`Aim`, which steers once airborne by the predictive landing control
(:func:`landing`): each tick it predicts by the air laws (the randomizer's ``physics.py``: the 0.6^dt blend toward air
control x stick, gravity; no walls) where the feet come down through the target's height with the stick held at the
target, at rest or away from it, takes the one that lands nearest, and flaps only while the stick at the target
would still land short; with ``hold`` (R0's aims, kept beside them: on w1's slice they still found 60 edges the
control missed) the stick is held at the job's unsnapped ``aim`` and every planned flap flies; ``curve`` radians off
the target for the first :data:`TURN` airborne ticks (a 2-segment string turning to it).  Back on something, the
stick rests; then, while no launch of the job has hit, the same launches again with the stick walking the body
toward the target while it is over :data:`HOME_M` from it (:data:`HOME_TICKS` at most), else holding against a slide
away from it while that is over :data:`BRAKE_V` (:data:`BRAKE_TICKS` at most), else at rest (Step R2.16d, the
diagnosis's fix 2: of 211 misses that first touched down on the target or in its to-zone and left, 164 left falling;
on its sample, in place of the resting stick, it found 6 misses and lost 4 of 100 control finds, so it runs after
them); then those steered :data:`SHORT_OF_M` short of the target, still walked at it once down (the diagnosis's fix
3: the predictive control overshoots, and 20 of 25 sampled short misses passed within 1 m over the target); then,
where a start of its own stood, the certificate's own aims under the control (``cert``: :func:`aims`, none held)
from the same feet at each of :data:`TURNS` off the job's heading (the diagnosis's fix 4), each such start's ``yaw``
recorded; then every launch from up to :data:`STARTS_N` other points of the from-zone L3 stands a body on within
:data:`SCAN_M` of the takeoff (:func:`other_starts`), each a takeoff facing the target (the diagnosis's fix 5); none
standing there, with none of the job's own starts standing either, is L3's answer for the edge's takeoff
(``rec["from_floor"]``).  These two place in the cells its own starts stood in, the snapshot's and the takeoff's
nearest only.  Last, for a job with ``env`` (a jump with flaps: its certificate's flap ticks on the envelope's
schedule, ``physics.Envelope.schedule``, :func:`aim_jobs`), the certificate's aims from its own starts again, each
flap on that schedule (:class:`Sched`; Step R2.16e: of 94 sampled misses with a flap-jump certificate, the flap law's
timing found none, the schedule's 49).  Each outcome's ``pass`` says which of the six launched it.

Passes 2-6 run for the derived modelled edges (:data:`MORE`; the bar's) and for a job that asks (``more``: Step
R2.19f+'s g1, :func:`more`), so a probe-needed aim takes pass 1 unless its job asks.  :func:`retarget` aims at what a
run's graph left (g1's three classes).  Its code is keyed apart from the fan's (``cache.AIM_FILES``): a change here
re-runs the aims, never R0's fan.
Positions stay in memory and the private cache.
"""

from __future__ import annotations

import functools
import math

import numpy as np

from azurkit.tools.randomizer.draft.geometry import CELL
from devkit.rando.physics import AC_AIR, AC_PLAIN, Physics, envelope
from devkit.reach.engine import hold
from devkit.reach.engine.macros import JUMP_LEAD, R0, SWIMMING, Y, Macro, _feet, _flaps, _Run, min_rank, settled
from devkit.reach.engine.runner import START_XY, START_Z, _job, fan_jobs, find_start, here_cell, place, run_macros
from devkit.sim.inputs import heading_to, wrap
from devkit.sim.l3 import L3Error

FLAPS_OF_RANK = {1: 1, 2: 2, 3: 5}   # an aim's flaps at its certificate's air rank (the shield's Flaps)
RING = tuple((0.25 * i, 0.25 * j) for i, j in ((1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, 1), (-1, -1), (1, -1)))
                                     # the 0.25 m grid's 8 points around a start, nearest first (the skeptic's S5)
TURN = 10                            # [proposal] an aim's curved first leg lasts this many airborne ticks
CURVE = math.radians(35.0)           # [proposal] an aim's curved leg's offset
SHORT_M = 0.3                        # [proposal] an aim flaps while the stick at its target lands this far short
                                     # (R2.16b's diagnosis probe P)
AIR_CONTROL = {"k0": AC_PLAIN, "air3": AC_AIR}   # each branch's air control (physics.py: 12 with a shield's Flaps)
INSIDE_M = (1.5, 1.0, 0.5)           # [proposal] an aim's target this far past the derived landing sample, on its
                                     # region
SCAN_M, SCAN_STEP = 2.5, 0.5         # [the diagnosis's] L3's floor round a target: this far, on this grid
INTERIOR = 3                         # [the diagnosis's] of a floor point's 4 grid neighbours, this many standing too
SHORT_OF_M = 1.5                     # [the diagnosis's] the third pass steers this far short of the target
TURNS = tuple(math.radians(d) for d in (12.0, -12.0, 25.0, -25.0))   # [the diagnosis's] the fourth pass's headings
STARTS_N, STARTS_SCAN, STARTS_APART = 3, 12, 0.4   # [the diagnosis's] the fifth pass's takeoffs, of the first this
                                                   # many standing points, this far apart (m)
MORE = ("modelled",)                 # [default, D665, D661] the confidences whose aims run passes 2-5 (the bar's: w1's
                                     # 4,337 probe-needed aims held 3 in 4 of the misses those passes ran for)
GATE_M = 3.0                         # [proposal, g1] :func:`retarget`'s class c: a pass-1 landing or first touch-down
                                     # this near its to-zone's floor
HOME_M, HOME_TICKS = 0.5, 30         # [the diagnosis's] after the touch-down, walk at the target while this far off
BRAKE_V, BRAKE_TICKS = 0.3, 20       # [the diagnosis's] then hold against a slide this fast (m/s)
_N4 = ((SCAN_STEP, 0.0), (-SCAN_STEP, 0.0), (0.0, SCAN_STEP), (0.0, -SCAN_STEP))
_SCAN = sorted(((i * SCAN_STEP, j * SCAN_STEP) for i in range(-5, 6) for j in range(-5, 6)
                if math.hypot(i, j) * SCAN_STEP <= SCAN_M + 1e-9), key=lambda o: (math.hypot(*o), o))
_LAW = Physics()


def aims(kind: str, kit: str, flaps: int) -> tuple[Macro, ...]:
    """The targeted pass's aims at a derived flight (the design §1; R2.16b's diagnosis): ``kind`` at it straight,
    curved left and curved right under the predictive control, a run jump pressed at the takeoff (lead 0) and
    straight at ``macros.JUMP_LEAD`` too; and R0's three held at it (``hold``)."""
    lead = 0.0 if kind == "runjump" else JUMP_LEAD
    out = tuple(Macro(kind, kit, flaps, c, lead) for c in (0.0, CURVE, -CURVE))
    out += (Macro(kind, kit, flaps),) if kind == "runjump" else ()
    return out + tuple(Macro(kind, kit, flaps, c, hold=True) for c in (0.0, CURVE, -CURVE))


def refine(kind: str, kit: str, flaps: int) -> tuple[Macro, ...]:
    """A MAY pair's aims (R2.16b: the refinement on what R0 left MAY): every R0 launch at the target (run jumps at
    the takeoff), the roll jump with one and with two rolls in the edge's kit and flaps (and with no air in rank
    0's), and with flaps 2 or more the edge's own launch recasting."""
    out = [m._replace(lead=0.0) if m.kind == "runjump" else m for m in R0]
    out += [Macro("rolljump", k, f, 0.0, 0.0, n) for k, f in dict.fromkeys(((kit, flaps), ("k0", 0)))
            for n in (1, 2)]
    if flaps >= 2:
        out.append(Macro(kind, kit, flaps, 0.0, 0.0 if kind == "runjump" else JUMP_LEAD, recast=True))
    return tuple(dict.fromkeys(out))


def landing(feet, vel, target, toward: float, ac: float) -> float | None:
    """Where a body in the air (``feet``, ``vel``) comes down through ``target``'s height with the stick held
    ``toward`` (1 at the target, 0 at rest, -1 away; air control ``ac``), by the air laws in closed form
    (``physics.Physics``: x after m ticks of the blend, z after m ticks of gravity; no walls, roofs or flaps): its
    signed distance past the target along the line to it (short: negative), or None if the feet never come down
    through that height."""
    dx, dy = target[0] - feet[0], target[1] - feet[1]
    d = math.hypot(dx, dy)
    if d < 1e-6:
        return 0.0
    ux, uy = dx / d, dy / d
    law = _LAW
    a, b, c = -law.dt * law.gdt / 2, law.dt * (vel[2] - law.gdt / 2), feet[2] - target[2]
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    m = math.ceil((-b - math.sqrt(disc)) / (2 * a))     # the first tick at or under the height, on the way down
    if m < 1:
        return None
    t = ac * toward
    along = law.x_after(m, vel[0] * ux + vel[1] * uy, t)
    return along - d


def _steer(prev, target, kit: str) -> tuple[int, float | None]:
    """The predictive landing control's choice this tick (:func:`landing`): the stick toward the target (1), at
    rest (0) or away (-1), whichever lands nearest; and where the stick at the target lands (None: never down)."""
    o = prev.obs
    f, ac = _feet(prev), AIR_CONTROL[kit]
    got = {s: landing(f, o.vel, target, s, ac) for s in (1, 0, -1)}
    best = min((s for s in got if got[s] is not None), key=lambda s: abs(got[s]), default=1)
    return best, got[1]


class Aim(_Run):
    """An aim's controller (the module docstring): R0's on the ground, steered at ``target`` once airborne, then
    with ``home`` walked or held at it, else at rest."""

    def __init__(self, *a, home=None) -> None:
        super().__init__(*a)
        self.home = home

    def seen(self, pad, row) -> str | None:
        if self.first is not None and any(pad.stick):     # walked or braked once down: no tick at rest yet (the
            self.still = -1                                # review's F1: a run is state 0 too)
        return super().seen(pad, row)

    def steer(self, t: int, prev) -> tuple[float | None, bool, bool]:
        m, target, took = self.m, self.target, self.took
        if self.first is not None:
            return self._landed(t - self.first, prev), True, True
        if target is None or took is None:
            return self.heading, True, True
        if m.hold:
            return heading_to(_feet(prev), target) + (m.curve if t - took < TURN else 0.0), True, True
        if prev.obs is None:
            return self.heading, True, True
        s, fwd = _steer(prev, target, m.kit)
        to = heading_to(_feet(prev), target)
        h = to + (m.curve if t - took < TURN else 0.0) if s == 1 else None if s == 0 else to + math.pi
        return h, s == 1, fwd is None or fwd < -SHORT_M

    def _landed(self, k: int, prev) -> float | None:
        """The stick ``k`` ticks after the first touch-down: at ``home`` while over :data:`HOME_M` off, else
        against a slide away from it over :data:`BRAKE_V`, else at rest (None)."""
        if self.home is None or prev.obs is None:
            return None
        f, (vx, vy) = _feet(prev), prev.obs.vel[:2]
        dx, dy = self.home[0] - f[0], self.home[1] - f[1]
        if k < HOME_TICKS and math.hypot(dx, dy) > HOME_M:
            return heading_to(f, self.home)
        if k < BRAKE_TICKS and math.hypot(vx, vy) > BRAKE_V and vx * dx + vy * dy < 0.0:
            return heading_to((0.0, 0.0), (-vx, -vy))
        return None


class Sched(Aim):
    """An aim whose flaps fly on the envelope's schedule (``physics.Envelope.schedule``, the frame-perfect flight
    the derive certifies; the sixth pass): its k-th flap on the first tick at least ``sched[k]`` ticks after its
    takeoff that a press can go (Y released, under the macro's flaps), every one flown, not
    ``macros.flap_due``'s timing under the landing control's gate (R2.16e's probe: that timing found 0 of 94 sampled
    misses with a flap-jump certificate, the schedule's 49)."""

    def __init__(self, *a, home=None, sched=()) -> None:
        super().__init__(*a, home=home)
        self.pend = list(sched)

    def steer(self, t: int, prev) -> tuple[float | None, bool, bool]:
        h, follow, _ = super().steer(t, prev)
        return h, follow, False                        # the flap law never flies: :meth:`pad` flaps

    def pad(self):
        p, m, rows = super().pad(), self.m, self.rows
        if (self.pend and self.took is not None and self.first is None and not p.buttons
                and self.presses < m.flaps + 2 and _flaps(rows[-1]) < m.flaps and "y" not in self.pads[-1].buttons
                and len(rows) - self.took >= self.pend[0]):
            self.pend.pop(0)
            self.presses += 1
            return p._replace(buttons=Y)
        return p


def hit(o: dict, start: dict, job: dict, zone_at) -> bool:
    """Whether outcome ``o``, launched from ``start`` (what the start search gave), ends aimed job ``job`` (its
    ``stop``) as a witness the graph counts for the job's edge: the start settled in the job's from-zone and the
    landing in the stop's to-zone (``zone_at``, ``nodes.Zones.zone_at`` of the stop's zoning, as the graph names
    zones) at its air rank or under (``macros.min_rank``)."""
    s = job["stop"]
    return (o["end"] == "settled" and min_rank(o) <= s["air"]
            and zone_at(start["settled"], False, False) == job["from"]
            and zone_at(o["land"], o["land_state"] == 6, False) == s["to"])      # 6: swimming, the graph's rule


def ringed(sim, feet_list, heading: float, cells, home: str | None = None, zone_at=None) -> dict:
    """``runner.find_start`` of ``feet_list``, then with ``home`` (a from-zone) and ``zone_at`` the first of the
    :data:`RING` around ``feet_list``'s first x ``cells`` that stands in ``home`` (``ring`` set)."""
    st = find_start(sim, feet_list, heading, cells)
    if "cell" in st or home is None or zone_at is None or not feet_list:
        return st
    x, y, z = feet_list[0]
    st = find_start(sim, [(x + a, y + b, z) for a, b in RING], heading, cells,
                    lambda g: zone_at(g, False, False) == home, st["tries"])
    return st | ({"ring": True} if "cell" in st else {})


def stands(sim, p, heading: float, cells) -> tuple | None:
    """Where a body placed at ``p`` (``runner.place``, in the first of ``cells`` that takes it) is settled
    within ``runner.START_XY`` and ``START_Z`` of it: (its settled feet, its state), else None."""
    for c in cells:
        try:
            r = place(sim, p, heading, c)
        except L3Error:
            continue
        g = _feet(r)
        if settled(r) and math.hypot(g[0] - p[0], g[1] - p[1]) <= START_XY and abs(g[2] - p[2]) <= START_Z:
            return g, r.state
    return None


def floor(sim, p, zone: str, heading: float, cells, zone_at) -> dict:
    """L3's floor of ``zone`` round ``p`` (the module docstring): ``{"to": True}`` when a body placed at ``p``
    stands (or swims) in ``zone``; else the nearest :data:`_SCAN` point where one does with :data:`INTERIOR` of its
    4 grid neighbours in ``zone`` too (else the nearest that stands at all): ``snap`` its settled feet, ``m`` how
    far, ``to`` whether any stood; ``placements`` the points tried."""
    got: dict[tuple, tuple | None] = {}

    def at(o):
        if o not in got:
            q = stands(sim, (p[0] + o[0], p[1] + o[1], p[2]), heading, cells)
            got[o] = q[0] if q is not None and zone_at(q[0], q[1] == SWIMMING, False) == zone else None
        return got[o]
    if at((0.0, 0.0)) is not None:
        return {"to": True, "placements": 1}
    first, inside = None, set(_SCAN)
    for o in _SCAN[1:]:
        if (g := at(o)) is None:
            continue
        first = first or (o, g)
        if sum(at((o[0] + a, o[1] + b)) is not None for a, b in _N4 if (o[0] + a, o[1] + b) in inside) >= INTERIOR:
            first = (o, g)
            break
    if first is None:
        return {"to": False, "placements": len(got)}
    return {"to": True, "snap": list(first[1]), "m": round(math.hypot(*first[0]), 2), "placements": len(got)}


def run_job(sim, job: dict, touch=None, here: int | None = None, zone_at=None) -> dict:
    """Run aimed job ``job`` (the module docstring; ``runner.run_job``'s record, and ``floor`` what
    :func:`floor` gave): its macros in order under :class:`Aim`, the held ones at its ``aim``, the rest at its
    ``target`` (each at L3's floor point instead where the target doesn't stand); with ``zone_at`` it ends once one
    of them :func:`hit` s and its body stays (``hold.replay``, the answer kept as the outcome's ``hold``: a hit that
    leaves its to-zone at rest is none), and while none has, for a job :func:`more` passes, the same
    launches again walked or held at the target once down (``Aim``'s ``home``; from the same saved starts), then so
    steered :data:`SHORT_OF_M` short of it (:func:`short_of`), then its certificate's aims (``cert``) so at each of
    :data:`TURNS` off its heading, then every launch so from :func:`other_starts`' takeoffs facing the target, then
    with ``env`` the certificate's aims from its own starts so, flapping on that schedule (:class:`Sched`)."""
    here = here_cell(sim) if here is None else here
    stop = job.get("stop") is not None and zone_at is not None
    rec = {"key": job["key"], "id": job["id"], "heading": job["heading"], "starts": {}, "outcomes": []}
    target, held = job["target"], job.get("aim", job["target"])
    twin = job.get("twin", {})
    if stop:
        cells = list(dict.fromkeys([*job.get("target_cells", ())[:1], here]))
        rec["floor"] = (dict(twin["floor"], placements=0) if "floor" in twin else
                        floor(sim, target, job["stop"]["to"], job["heading"], cells, zone_at))
        if "snap" in rec["floor"]:                     # the held aims keep the unsnapped aim where the target stood
            target = held = rec["floor"]["snap"]
    ms, memo = [Macro(*m) for m in job["macros"]], {}

    def find(sim_, feet, h, cells_):
        for k, st in twin.get("starts", {}).items():    # the twin's answer to the same search: placed, not searched
            if h == job["heading"] and cells_ == cells and feet == job["starts"][k]:
                if "cell" in st:
                    place(sim_, st["feet"], h, st["cell"])
                return dict(st, tries=int("cell" in st))
        return ringed(sim_, feet, h, cells_, job.get("from") if job.get("stop") else None, zone_at)

    cells = [here] + [c for c in job["cells"] if c != here]
    found = []

    def held_hit(o: dict, st: dict, h: float) -> bool:
        if found or not hit(o, st, job, zone_at):      # one that stays ends the job: the rest of its family run
            return bool(found)
        o["hold"] = hold.replay(sim, st, h, o)
        if hold.stays(o["hold"], job["stop"]["to"], zone_at):
            found.append(o)
        return bool(found)

    def launch(n: int, home, at=None, macros=ms, heading=job["heading"], name="", memo_=memo,
               takeoff=job["takeoff_feet"], starts=job["starts"], cells_=cells, sched=None) -> bool:
        k = len(rec["outcomes"])
        got = run_macros(sim, rec, macros, heading, takeoff, starts, cells_, touch, find=find, memo=memo_, name=name,
                         ctl=functools.partial(Aim, home=home) if sched is None else
                         functools.partial(Sched, home=home, sched=sched),
                         target=lambda m: at if at is not None else held if m.hold else target,
                         done=(lambda o, st: held_hit(o, st, heading)) if stop else None)
        for o in rec["outcomes"][k:]:
            o["pass"] = n
        return got
    if (launch(1, None) or not stop or not more(job) or launch(2, target)
            or launch(3, target, short_of(target, job["takeoff_feet"]))):
        return rec
    own = [m for m in aims(*job["cert"]) if not m.hold] if job.get("cert") else []
    stood = [st["cell"] for st in rec["starts"].values() if "cell" in st]
    near = list(dict.fromkeys(stood + cells[:2]))      # where its own starts stood, the snapshot's, the nearest

    def turned(n: int, h: float, name: str, **kw) -> bool:
        got = launch(n, target, heading=h, name=name, memo_={}, cells_=near, **kw)
        for k, st in rec["starts"].items():
            if k.endswith(name):
                st["yaw"] = h
        return got
    if any(turned(4, wrap(job["heading"] + d), f"@h{round(math.degrees(d)):+d}", macros=own)
           for d in TURNS if own and stood and not twin):   # a twin flew these (its own pass 4)
        return rec
    picks, n = other_starts(sim, job["takeoff_feet"], job["heading"], target, job["from"], near, zone_at)
    rec["from_floor"] = {"stood": n or len(stood)}
    for k, t in enumerate(picks):
        h = heading_to(t, target)
        dx, dy = -math.sin(h), math.cos(h)
        starts = {"run": [[t[0] - b * dx, t[1] - b * dy, t[2]] for b in (1.0, 0.5)] + [list(t)],
                  "stand": [[t[0] - 0.3 * dx, t[1] - 0.3 * dy, t[2]], list(t)]}
        if turned(5, h, f"@s{k}", takeoff=list(t), starts=starts):
            return rec
    if own and job.get("env"):                         # the certificate's aims from its own starts, flapping on the
        launch(6, target, macros=own, sched=job["env"])   # envelope's schedule
    return rec


def more(job: dict) -> bool:
    """Whether aimed job ``job`` runs passes 2-6: its edge's confidence is one of :data:`MORE`, or it asks
    (``more``: Step R2.19f+'s g1; :func:`retarget` sets it)."""
    return bool(job.get("more")) or job.get("edge", "").rsplit(":", 1)[-1] in MORE


def other_starts(sim, takeoff, heading: float, target, zone: str, cells, zone_at) -> tuple[list, int]:
    """Up to :data:`STARTS_N` takeoffs where L3 stands a body (state 0) in ``zone`` within :data:`SCAN_M` of
    ``takeoff`` (the :data:`SCAN_STEP` grid, nearest first, the first :data:`STARTS_SCAN` that stand): the one
    nearest ``target``, the one farthest on along ``heading`` and the middle one by distance to ``target``, each
    :data:`STARTS_APART` from the others (their settled feet); and how many stood."""
    found = []
    for o in _SCAN:
        g = stands(sim, (takeoff[0] + o[0], takeoff[1] + o[1], takeoff[2]), heading, cells)
        if g is not None and g[1] == 0 and zone_at(g[0], False, False) == zone:
            found.append(tuple(g[0]))
            if len(found) >= STARTS_SCAN:
                break
    by_target = sorted(found, key=lambda p: math.hypot(p[0] - target[0], p[1] - target[1]))
    along = sorted(found, key=lambda p: (takeoff[0] - p[0]) * math.sin(heading)
                   + (p[1] - takeoff[1]) * math.cos(heading))
    picks = []
    for p in (by_target[:1] + along[-1:] + by_target[len(by_target) // 2:][:1]) if found else ():
        if all(math.dist(p, q) > STARTS_APART for q in picks):
            picks.append(p)
    return picks[:STARTS_N], len(found)


def short_of(target, takeoff, m: float | None = None) -> list:
    """``target`` moved :data:`SHORT_OF_M` (or ``m``) back toward ``takeoff`` across, at its height."""
    m = SHORT_OF_M if m is None else m
    dx, dy = target[0] - takeoff[0], target[1] - takeoff[1]
    d = math.hypot(dx, dy)
    k = min(m, d) / d if d > 1e-6 else 0.0
    return [target[0] - k * dx, target[1] - k * dy, target[2]]


def _flights(nodes, kinds, confs) -> dict[tuple, dict]:
    """Per (from zone, to zone, kind, confidence), the reach model's best region edge with a witness flight
    (``E["logic"]``: least ranks, then gap)."""
    R = nodes.R
    best: dict[tuple, dict] = {}
    for (a, b), es in R.E["logic"].items():
        za, zb = int(R.zone_of[a]), int(R.zone_of[b])
        for e in es:
            if za == zb or e.get("kind") not in kinds or e.get("conf") not in confs or not e.get("w"):
                continue
            k = (za, zb, e["kind"], e["conf"])
            if k not in best or (sum(e["ranks"]), e.get("gap", 0.0)) < (sum(best[k]["ranks"]), best[k].get("gap", 0.0)):
                best[k] = e
    return best


def aim_jobs(nodes, derived: dict, kinds=("jump", "flap"), confs=("modelled", "probe-needed"), only=None,
             macro_set=aims, prefix: str = "a", sched: bool = True, more_of=()) -> list[dict]:
    """The targeted pass (the design §1): per derived zone edge of ``kinds`` and ``confs`` (with ``only``, those
    whose ``from>to:kind:confidence`` it holds), its best region edge's witness flight in the reach model (its
    takeoff and landing samples) as the aims of ``macro_set`` (:func:`aims`; :func:`refine` for a MAY pair) from its
    takeoff at its landing (moved on along the flight onto its region, :func:`_inside`, then onto its floor face,
    ``Nodes.snap``), at its cheapest tier's certificate: rank 0 in kit ``k0`` with no flap, else ``air3`` with the
    rank's flaps (the certificate's cap when it has one), a running or a standing takeoff as the certificate says;
    its starts over a floor face in its from-zone (``Nodes.starts``); ids ``<prefix><derived edge index>``, ``edge``
    the derived edge, ``from`` its from-zone, ``stop`` its air level, to-zone and the zoning that names it (the job
    ends at its first :func:`hit`; none when it asks for more than air), ``target_cells`` the cell to place a body
    at its target in (:func:`floor`; the snapshot's own after it), ``cert`` the certificate's kind, kit and flaps,
    and with ``sched``, for a :data:`MORE` edge whose certificate jumps with flaps, ``env`` its flap ticks after the
    takeoff on the envelope's schedule (``physics.Envelope.schedule`` of the derived certificate's rank, headroom
    and flap cap, to the target's height over the takeoff; :func:`run_job`'s last pass).  An edge ``more_of`` holds
    (``from>to:kind:confidence``) asks for every pass (``more``, :func:`more`) and gets ``env`` as a :data:`MORE`
    edge's."""
    from devkit.rando.draft.author import dnf
    from azurkit.tools.randomizer.planner.proofs import zoning
    from devkit.reach.engine.nodes import Takeoff
    lw, zoned = nodes.logic, zoning(derived)[:12]
    zone = {f"{nodes.level}.Z{int(z):03d}": int(z) for z in np.unique(nodes.R.zone_of)}
    best = _flights(nodes, kinds, confs)
    out = []
    for n, d in enumerate(derived.get("edges", ())):
        if d["kind"] not in kinds or d.get("confidence") not in confs or d["from"] not in zone or d["to"] not in zone:
            continue
        edge = f"{d['from']}>{d['to']}:{d['kind']}:{d['confidence']}"
        if only is not None and edge not in only:
            continue
        e = best.get((zone[d["from"]], zone[d["to"]], d["kind"], d["confidence"]))
        if e is None:
            continue
        i, j = e["w"]
        src = (float(lw.x[i]), float(lw.y[i]), float(lw.z[i]))
        if (r := nodes.region_at(src)) is None:
            continue
        moved = _inside(nodes, src, j)
        dst = nodes.snap(moved, d["to"]) or moved
        cert = next((c for c in e.get("certs") or () if c is not None and c.rank < 4), None)
        rank = cert.rank if cert is not None else min(e["ranks"])
        flaps = 0 if rank == 0 else cert.flaps if cert is not None and cert.flaps is not None else FLAPS_OF_RANK[rank]
        kind = ("walkoff" if cert is not None and cert.walk_off else
                "runjump" if cert is None or cert.run else "standjump")
        t = Takeoff(-1, -1, r, src, heading_to(src, dst), tuple(nodes.cells([src])[0]))
        airs = [max((a[1] for a in term), default=0) for term in dnf(d.get("requires", "true"))
                if all(a[0] == "air" for a in term)]
        stop = {"air": min(airs), "to": d["to"], "zoning": zoned} if airs else None
        kit = "k0" if rank == 0 else "air3"
        c, asks = d.get("cert") or {}, edge in more_of
        env = (list(envelope().schedule(int(c["rank"]), float(dst[2] - src[2]), c.get("headroom"), c.get("flaps")))
               if sched and stop and (d["confidence"] in MORE or asks) and kind != "walkoff" and flaps > 0
               and c.get("rank") is not None else [])
        out.append(_job(nodes, t, t.heading, macro_set(kind, kit, flaps), d["from"], id=f"{prefix}{n}", edge=edge,
                        target=list(dst), aim=list(moved), stop=stop, target_cells=nodes.cells([dst])[0][:1],
                        cert=[kind, kit, flaps], **{"from": d["from"]}, **({"env": env} if env else {}),
                        **({"more": True} if asks else {})))
    return out


def unscheduled(rec: dict) -> dict:
    """Record ``rec`` as the refinement is sampled on it: without its last pass's outcomes (the envelope's schedule,
    :class:`Sched`), so an edge only that pass finds is refined as before it ran, and the refinement's jobs, whose
    launches find other edges too, are the ones they were (Step R2.16e: refined no more, one such job's find of
    another edge was lost).  That pass runs last, so the outcomes kept keep their indices."""
    if not any(o.get("pass") == 6 for o in rec["outcomes"]):
        return rec
    return dict(rec, outcomes=[o for o in rec["outcomes"] if o.get("pass") != 6])


def refined(verdicts) -> dict[str, str]:
    """The derived edges a refinement aims at (``from>to:kind:confidence`` to the from-zone): the rows of
    ``verdicts`` (``verdict.zone_edges``') with an air term that are MAY, found only above their kit (``over``: Step
    R2.16c's skeptic, S4: refined, 19 of w1's 73 such reach their edge at kit), or N/A for no launch from their
    from-zone or a floor fault."""
    return {f"{v['from']}>{v['to']}:{v['kind']}:{v['confidence']}": v["from"] for v in verdicts
            if "air" in v and (v["verdict"] == "MAY" or v.get("over") or v.get("why", "").startswith("not attempted")
                               or v.get("fault"))}


TWIN = ("takeoff_feet", "heading", "starts", "cells", "target", "aim", "target_cells", "stop", "edge", "from")


def twinned(job: dict, twin: dict, rec: dict) -> dict:
    """Refinement job ``job`` given its aim twin (``twin``, the aims' job at the same edge, and ``rec``, its record)
    when they agree on every field of :data:`TWIN` (else ``job``): with none of the twin's macros (their launches
    from the same starts at the same target gave the twin's outcomes; L3 is deterministic) and ``twin`` the twin's
    floor answer and its own starts' answers, which :func:`run_job` takes in place of searching again (and runs no
    fourth pass: the twin flew the certificate's turned aims)."""
    if any(job.get(k) != twin.get(k) for k in TWIN):
        return job
    got = {"starts": {k: rec["starts"][k] for k in ("run", "stand") if k in rec["starts"]}}
    if "floor" in rec:
        got["floor"] = {k: v for k, v in rec["floor"].items() if k != "placements"}
    return dict(job, macros=[m for m in job["macros"] if m not in twin["macros"]], twin=got)


def refine_jobs(nodes, derived: dict, verdicts, min_area: float, regions=None, twins=None) -> list[dict]:
    """The refinement (Step R2.16b) on the derived jump and flap zone edges a run left unfound or found only above
    their kit (:func:`refined` of ``verdicts``): each one's aims with :func:`refine`'s launches (ids ``r<derived
    edge index>``; with ``regions``, those taking off from these walkable regions only, a slice; with ``twins``, the
    aims' job and record by derived edge index, each :func:`twinned`), and R0's fan and the roll jumps from the
    walkable regions under ``min_area`` (which R0's fan skips) in their from-zones (ids ``s<takeoff>h<k>``)."""
    want, twins = refined(verdicts), twins or {}
    jobs = [twinned(j, *twins[j["id"][1:]]) if j["id"][1:] in twins else j
            for j in aim_jobs(nodes, derived, only=set(want), macro_set=refine, prefix="r", sched=False)
            if regions is None or j["region"] in regions]
    zones, w = {j["from"] for j in jobs} if regions is not None else set(want.values()), nodes.walk
    area = w.reg_count * CELL * CELL
    small = {r for r in range(w.nreg) if area[r] < min_area}
    ts = [t for t in nodes.takeoffs(min_area=0.0, regions=small) if nodes.zone_at(t.feet, False, False) in zones]
    fan = R0 + tuple(m for m in refine("runjump", "air3", 5) if m.kind == "rolljump")
    return jobs + [dict(j, id="s" + j["id"][1:]) for j in fan_jobs(nodes, ts, fan)]


def _floor_samples(nodes) -> dict[str, np.ndarray]:
    """Each zone's logic-walk floor samples ((n, 3): the zone's floor, :func:`retarget`'s class c gate), once."""
    if getattr(nodes, "_zone_floor", None) is None:
        lw = nodes.logic
        j = np.nonzero(lw.reg_soft >= 0)[0]
        P = np.stack([lw.x[j], lw.y[j], lw.z[j]], axis=1).astype(np.float64)
        if (zo := getattr(nodes.R, "zone_of", None)) is not None:   # the reach model's zoning: its zone a region
            zone = np.array([f"{nodes.level}.Z{int(z):03d}" for z in np.asarray(zo)[lw.reg_soft[j]]], dtype=object)
        else:                                                        # none (a hand-built level): ``zone_at``'s
            zone = np.array([nodes.zone_at(tuple(p), False, False) for p in P], dtype=object)
        nodes._zone_floor = {z: P[zone == z] for z in set(zone.tolist()) if z is not None}
    return nodes._zone_floor


def _re_aim(nodes, jid: str, za: str, zb: str, rank: int, src, dst, zoned: str, asks: bool) -> dict | None:
    """A run jump's aim from ``src`` at ``dst`` (onto ``zb``'s floor, ``Nodes.snap``) in rank ``rank``'s kit (k0 and
    no flap at rank 0, else air3 with the rank's Flaps), ending at its first hit at that rank; ``asks``: every pass
    (``more``).  None where ``src`` is on no walkable region."""
    from devkit.reach.engine.nodes import Takeoff
    if (region := nodes.region_at(src)) is None:
        return None
    to = nodes.snap(dst, zb) or tuple(dst)
    kit, flaps = ("k0", 0) if rank == 0 else ("air3", FLAPS_OF_RANK[rank])
    t = Takeoff(-1, -1, region, tuple(src), heading_to(src, to), tuple(nodes.cells([src])[0]))
    return _job(nodes, t, t.heading, aims("runjump", kit, flaps), za, id=jid, edge=f"{za}>{zb}:retarget:nd",
                target=list(to), aim=list(dst), stop={"air": rank, "to": zb, "zoning": zoned},
                target_cells=nodes.cells([to])[0][:1], cert=["runjump", kit, flaps], **{"from": za},
                **({"more": True} if asks else {}))


def retarget(nodes, derived: dict, g, recs: dict, jobs: dict, frame=(), verdicts=(), gate_m: float = GATE_M) \
        -> list[dict]:
    """Step R2.19f+'s g1: aims at what a run's graph ``g`` (its hold done; ``recs`` and ``jobs`` its records and jobs
    by key) left, ids ``g<class><n>``:

    - a: each pair of ``frame`` (the truth frame's non-derived k0 pairs, (from zone, to zone)) the graph holds only
      over air rank 0: a rank-0 aim (k0, no flap) from that witness's takeoff at its landing;
    - b: each zone rank the hold left with no witness (and none under it): an aim at the to-zone's floor nearest its
      best candidate's rejected landing, from that candidate's takeoff, in that rank's kit, every pass (``more``);
    - c (and its refinement, d): each probe-needed derived edge of ``verdicts`` (``verdict.zone_edges``') unfound at
      its kit whose aim's pass-1 landing or first touch-down came within ``gate_m`` of its to-zone's floor (the
      records', so choosing costs no run): its aims and its refinement (twinned to that aim), every pass."""
    from azurkit.tools.randomizer.planner.proofs import zoning
    zoned, out, seen = zoning(derived)[:12], [], set()

    def take(w) -> tuple:
        rec = recs[w["job"]]
        o = rec["outcomes"][w["outcome"]]
        st = rec["starts"][o["start"]]
        return (o.get("took") or st.get("settled") or st["feet"]), o["land"]
    for za, zb in frame:
        got = g.zones.get((za, zb), {})
        if got and min(got) > 0 and ("a", za, zb) not in seen:
            src, land = take(got[min(got)])
            if (j := _re_aim(nodes, f"ga{len(out)}", za, zb, 0, src, land, zoned, False)) is not None:
                seen.add(("a", za, zb))
                out.append(j)
    for (za, zb), ranks in sorted(g.cands.items()):
        held = g.zones.get((za, zb), {})
        for r, ws in sorted(ranks.items()):
            if r in held or any(x < r for x in held) or not ws or ("b", za, zb) in seen:
                continue
            src, land = take(ws[0])
            if (j := _re_aim(nodes, f"gb{len(out)}", za, zb, r, src, land, zoned, True)) is not None:
                seen.add(("b", za, zb))
                out.append(j)
    left = {f"{v['from']}>{v['to']}:{v['kind']}:{v['confidence']}" for v in verdicts
            if v.get("confidence") == "probe-needed" and "air" in v and (v["verdict"] != "FOUND" or v.get("over"))}
    floors, near, twins = _floor_samples(nodes), set(), {}
    for key, j in jobs.items():
        e = j.get("edge")
        if e not in left or j["id"][0] != "a" or (rec := recs.get(key)) is None:
            continue
        F = floors.get(e.split(":")[0].split(">")[1])
        pts = [p for o in rec["outcomes"] if o.get("pass") == 1 for p in (o.get("land"), o.get("first")) if p]
        if F is not None and len(F) and pts and min(float(np.min(np.linalg.norm(F - np.asarray(p), axis=1)))
                                                   for p in pts) <= gate_m:
            near.add(e)
            twins[e] = (j, rec)
    if near:
        out += aim_jobs(nodes, derived, only=near, prefix="gc", more_of=near)
        out += [twinned(r, *twins[r["edge"]]) for r in
                aim_jobs(nodes, derived, only=near, macro_set=refine, prefix="gd", sched=False, more_of=near)]
    return out


def _inside(nodes, src, j: int) -> tuple:
    """A derived flight's landing sample ``j`` (the logic walk's), moved the first of :data:`INSIDE_M` metres on
    along the flight (from ``src``) that stays on its region: the derive lands its flights on 2 m border bins, and
    a body steered at a border lands on the brink (the smoke slice's aims fell past 1 m short)."""
    lw = nodes.logic
    p = (float(lw.x[j]), float(lw.y[j]), float(lw.z[j]))
    d = math.hypot(p[0] - src[0], p[1] - src[1])
    for m in INSIDE_M if d > 1e-6 else ():
        q = (p[0] + m * (p[0] - src[0]) / d, p[1] + m * (p[1] - src[1]) / d, p[2])
        v = nodes.locate(q, False, lw, False)
        if 0 <= v < len(lw.col) and lw.reg_soft[v] == lw.reg_soft[j]:
            return q[0], q[1], float(lw.z[v])
    return p
