"""The randomizer's goal for simulator Level 3's input search (Step X.7, D170): a zone, a node or a pickup on a
level's route graph (:class:`~devkit.rando.draft.route.Router`), with the search's cost to go, its
guidance and its cells, and the route planner's plan as a seed string.  It implements ``devkit.sim.l3_search``'s
``Goal`` protocol structurally and imports nothing from ``sim``: the search gets it by name
(:func:`make_goal`, the factory ``l3_search.solve`` hands its workers), and seeds as plain ``(n, heading, hold)``
tuples (:func:`route_seed`).

The cost to go is Dijkstra's back from the goal over the router's links (walks, swims and the region edges usable
at the router's hardest tier with the kit's ``air`` level, every probe class admitted: the game decides what the
body can do).  Off that graph (a hand edge the derive never modelled: no path from the start), the cost and the
guidance fall back to the straight line to the nearest vertex the goal's field reaches plus that vertex's cost, so
the search is pulled toward the region the goal is reachable from and Go-Explore's cells do the rest.

The trick explorer's guidance (Step TD.1, ``devkit.sim.l3_explore``; guidance only, never logic): a discovery
problem's :class:`ZoneGuide` (the zone, the phys floor region a pseudo-region is matched to, the column's highest
floor) and a target problem's :class:`TrickGoal` on the light trick graph (:class:`TrickRouter`: the phys profile's
graph costed by the game's own walk, ``floors.walk_game``, its flights rechecked against one-sided faces, plus slope
hops and lip and rim lifts).  Factories :func:`make_zone_guide` and :func:`make_trick_goal`; nothing here names a
level or a site.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import math
import os
import pickle
import re
import sys
import time
from pathlib import Path

import numpy as np

from devkit.rando.draft import route as rt
from devkit.rando.draft.flights import RIM_LIFT, RIM_STEP_LIFT, SIDE_BAND, SIDE_M, _rim, _track_edges
from azurkit.tools.randomizer.draft.floors import SLIP_FLAT_NZ, WALK_GAME_NZ, guidance_walk, lookup
from azurkit.tools.randomizer.draft.geometry import CELL, SOLID_CATS, RadiusIndex, raster
from devkit.rando.physics import DESCENT_D, DESCENT_FACTOR, GRAVITY, H_AIR
from devkit.sim.obs import settled   # the one settled rule (AZ-737; obs needs no Unicorn)
from azurkit.tools.randomizer.art import collision

AIRBORNE = frozenset({2, 0x102})     # entity+0x94: in the air, the air attack move (l3_search's codes)
OFF_FLOOR = AIRBORNE | {1, 0x101}    # in the air, climbing, in the catch (entity+0x94)
SWIMMING = 6
DIVE_MPS = 5.0                       # the dive's speed: garret4's walkSpeed [verified xemu s6, RE_MOVEMENT]
DEAD = 7
CLIMBING = 1                         # entity+0x94: on a ladder or a climbable face
CLIMB_R = 4.0                        # [proposal] a climbing body this near a climb edge's link (horizontally) is on it
PROBES = ("swim-exit", "climb", "push", "current", "teleport", "door", "rig", "lip", "slippery", "sweep", "hazard",
          "bskip", "skip")           # every probe class (gates.probe_class)
FAR_S = 4.0                          # [proposal] the cost (s) added off the goal's reachable graph
DOUBT_S = 60.0                       # [proposal] the cost (s) a doubtful edge of the light trick graph adds (Step
                                     # X.53): over the 30-230 s ways measured at the stalls, so a measured way wins
                                     # where one exists and no start loses its way
JUMP_HOLD = 6                        # Y held this many ticks for a jump (the harness's capture)
JUMP_V0 = {0: math.sqrt(2 * 9.8 * 1.1), 1: math.sqrt(2 * 9.8 * 1.2)}   # [verified xemu] h 1.1, 1.2 with air power
TOUCH_M = 1.0                        # the player's touch query: 1 m round the body centre ([0x1980BC], 0x8C520)
SURVIVE = 10                         # ticks past a pickup's touch the body must live through (AZ-571), then land
                                     # alive, at rest or holding its last stick (l3_search.lands_alive, AZ-627): a
                                     # touch on the way to a death backs no pickup, and a spot's way back starts
                                     # there (an air kit's after its 3-tick RECAST)
FLAP_H = H_AIR                       # a flap's height with an air shield (0x83F90): d = peak_z + h - z (z the body
                                     # centre, the input position's frame), a flap at d <= 0 lifts nothing, and one
                                     # at d over DESCENT_D is a descent flap: half its launch speed (a quarter of its
                                     # rise), the gauge emptied and the shield dropped (0x893C0; 3.6 m under a floor
                                     # jump's takeoff, RE_MOVEMENT)
FLAP_MARGIN = 0.3                    # [proposal] the guide keeps this far inside both bounds
TRACK_M = 2.0                        # [proposal] a body this near a flight's track (horizontally) flies it
RIDE_M = 0.8                         # [proposal] a body this near a ride's source vertex (horizontally) stands for it
REACH_M = 1.0                        # [proposal] an arc this short of a flight's landing (horizontally) still lands
LAND_R = 0.5                         # [proposal] a body this near its landing (horizontally) keeps the flight's heading


def heading_to(p, q) -> float:
    """The game heading from p to q (it faces (-sin h, cos h))."""
    return math.atan2(-(q[0] - p[0]), q[1] - p[1])


def air_time(z: float, vz: float, zl: float, flaps: int = 0, ceil: float = -math.inf,
             g: float = GRAVITY) -> tuple[float, float] | None:
    """(the least, the most) seconds before feet at height ``z`` rising at ``vz`` come down to ``zl`` (AZ-621),
    None when they can't rise to it: the ballistic arc, a flap at its apex wherever it must rise further (each of
    ``flaps`` lifting min(``ceil`` - z, :data:`FLAP_H`), the game's wing_flap with ``ceil`` its ceiling peak_z + h in
    the feet's frame; one over ``physics.DESCENT_D`` under it lifts a quarter, the game halving its launch speed,
    ``physics.DESCENT_FACTOR``, and empties the gauge), and for the most, every flap left taken as the feet come
    down to ``zl``."""
    t = 0.0
    while (apex := z + max(vz, 0.0) ** 2 / (2 * g)) < zl:
        d = ceil - apex
        lift = min(d, FLAP_H) * (DESCENT_FACTOR ** 2 if d > DESCENT_D else 1.0)
        if flaps <= 0 or lift <= 0.0:
            return None
        t, z, vz, flaps = t + max(vz, 0.0) / g, apex, math.sqrt(2 * g * lift), 0 if d > DESCENT_D else flaps - 1
    t += (vz + math.sqrt(vz * vz + 2 * g * (z - zl))) / g
    lift = min(ceil - zl, FLAP_H)
    return t, t + (flaps * 2 * math.sqrt(2 * lift / g) if lift > 0.0 else 0.0)


def item_touch(engine, species: str) -> tuple[float, float, float] | None:
    """(R, Z, hz) of a pickup species, the game's touch (docs/RE_DATA.md "Pickups and exit triggers"): the player's
    tick asks its 1 m query (0x8C520 -> 0x60870) of each critter near the body centre, and the critter's test 0x418B0
    takes it when the body centre lies in the ellipsoid of horizontal radius R = r * pcr / cr + 1 and half-height
    Z = r * aspect + 1 round its bounds' centre, r = collisionRadius * scale (cr, its default 1.0; ``scale``,
    1.0; ``collisionAspectRatio``, 1.0; ``playerCollisionRadius`` pcr, cr: config.xbr's ``critters_engine``, read by
    0x49480); hz = r * aspect is the bounds' half-height (the item rests on it).  ``engine``: that table (a
    ``KeyedTableSection``); None when it has no such column."""
    def cell(prop: str):
        c = engine.find_cell(species, prop)
        return c.double_value if c is not None and c.type_code == 1 else None
    if species not in engine.col_names():
        return None
    cr = cell("collisionRadius") or 1.0
    r = cr * (cell("scale") or 1.0)
    aspect = cell("collisionAspectRatio") or 1.0
    pcr = cell("playerCollisionRadius") or cr
    return r * pcr / cr + TOUCH_M, r * aspect + TOUCH_M, r * aspect


def surface_below(lv, p, up: float = 0.5) -> float | None:
    """The height of the highest upward-facing collision triangle (any owner) straight below ``p``, from ``up`` m
    over it down; None when there is none."""
    V = lv.P
    a, b, c = V[:, 0], V[:, 1], V[:, 2]
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    ok = np.abs(d) > 1e-12
    d = np.where(ok, d, 1.0)
    l1 = ((b[:, 1] - c[:, 1]) * (p[0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (p[1] - c[:, 1])) / d
    l2 = ((c[:, 1] - a[:, 1]) * (p[0] - c[:, 0]) + (a[:, 0] - c[:, 0]) * (p[1] - c[:, 1])) / d
    l3 = 1.0 - l1 - l2
    z = l1 * a[:, 2] + l2 * b[:, 2] + l3 * c[:, 2]
    nz = np.cross(b - a, c - a)[:, 2]
    m = ok & (l1 >= 0) & (l2 >= 0) & (l3 >= 0) & (nz > 0) & (z <= p[2] + up)
    return float(z[m].max()) if m.any() else None


def item_centre(lv, p, hz: float) -> tuple[float, float, float]:
    """Where a pickup spawned at ``p`` rests, its bounds' centre: it falls onto the surface below (centre ``hz`` over
    it) unless its bottom already reaches it (it stays) [measured in L3 whole steps: 4 items of 4 species within
    4 mm; two keys sat 0.5 m higher, not modelled]."""
    s = surface_below(lv, p)
    return (float(p[0]), float(p[1]), s + hz if s is not None and p[2] - hz > s else float(p[2]))


def inside_mesh(V, p) -> bool:
    """The game's trigger test (0xD2A40, from a platform's 0x79D30): point ``p`` lies inside the mesh ``V`` (n x 3 x 3
    triangles) when the first triangle straight above it faces down ((v1 - v0) x (v2 - v0) has z < 0)."""
    a, b, c = V[:, 0], V[:, 1], V[:, 2]
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    ok = np.abs(d) > 1e-12
    d = np.where(ok, d, 1.0)
    l1 = ((b[:, 1] - c[:, 1]) * (p[0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (p[1] - c[:, 1])) / d
    l2 = ((c[:, 1] - a[:, 1]) * (p[0] - c[:, 0]) + (a[:, 0] - c[:, 0]) * (p[1] - c[:, 1])) / d
    l3 = 1.0 - l1 - l2
    t = l1 * a[:, 2] + l2 * b[:, 2] + l3 * c[:, 2] - p[2]
    m = ok & (l1 >= 0) & (l2 >= 0) & (l3 >= 0) & (t > 0)
    if not m.any():
        return False
    i = np.nonzero(m)[0][int(np.argmin(t[m]))]
    return bool(np.cross(b[i] - a[i], c[i] - a[i])[2] < 0)


def holds_body(router, obj: str) -> bool:
    """Whether a standing player's body centre (a walk vertex + 1 m) lies inside ``obj``'s mesh (:func:`inside_mesh`)
    at any walk vertex of the router near it: a trigger volume (d1's BeamShape r558), where the game's touch test
    fires on the ground; not a platform he stands on (the walkway generators' BaseShape, a 1.2 m box whose top is
    the walk surface, and their PressurePlateShape, a flat quad there), whose inside a body centre reaches only
    falling through its side (R1.16e's sitting: three d1 approaches that took the inside test fell to the player's
    death)."""
    p = object_points(router.lv, obj)
    V = p.reshape(-1, 3, 3) if len(p) % 3 == 0 and len(p) >= 3 else None
    if V is None:
        return False
    lo, hi = p.min(axis=0), p.max(axis=0)
    X, Y, Z = router.X, router.Y, router.Z
    near = np.nonzero((X >= lo[0]) & (X <= hi[0]) & (Y >= lo[1]) & (Y <= hi[1]) & (Z >= lo[2] - 2.0) & (Z <= hi[2]))[0]
    return any(inside_mesh(V, (X[i], Y[i], Z[i] + 1.0)) for i in near)       # the body centre: the feet + 1 m


class RouteGoal:
    """A goal on a level's route graph (``route.Router``): ``target`` a zone (``w2.Z013``), a list of zones, a
    level-file node, or a generated id (a pickup: touched from ``touch``, 0.75 m, around its point, up to 2.5 m
    under it; with ``touch`` :func:`item_touch`'s (R, Z, hz), the game's own touch instead: the body centre, HP
    above 0, in the ellipsoid round where the item rests, :func:`item_centre`); a pickup counts only when the body
    lives :data:`SURVIVE` ticks past its touch and then lands alive, at rest or holding its last stick
    (``survive``, AZ-571, AZ-627: ``l3_search.confirm``).
    The guidance (``toward``): on the ground ``look`` m along the cheapest way, or for a flight on it, a run-up onto
    its track (with the ticks to the takeoff) and a jump at the router's takeoff point (a drop walks off); before a
    flight that needs flaps, with the air gauge spent (under 1), a cast (a fourth item, True: the armor's LT+Y,
    which refills it).  In the air, along the flight the body is on (the goal's flight whose takeoff floor is the
    fall reference's height, whose track passes the body and whose landing its arc can still make: toward its
    landing, and over it on along the track, AZ-621), else toward the best vertex within reach; a flap (jump True)
    by the descent-flap rule (Step R1.29e): falling, flaps left in this jump and the gauge not empty, between the
    flap ceiling and the descent bound the game's own peak_z sets (entity+0x164: ``d = peak_z +`` :data:`FLAP_H`
    ``- z`` over 0, under ``physics.DESCENT_D``; a walk-off keeps the last jump's,
    a springboard's is its launch's), and short of the landing (under its height, or falling to it at the air
    speed would stop short of it).  ``casts`` False (the trick explorer's guides, whose moves cast nothing): no
    cast is asked, so a takeoff keeps its heading and jump.  Cells: the zone, the position on a ``cell_m`` grid
    (1.5 m in height), in the air or not, the flaps left in the jump (in the air) and whether the gauge is full, so
    a string that spent its flaps is no stand-in for one that kept them."""

    def __init__(self, router, target, *, air: int = 0, look: float = 2.0, cell_m: float = 2.0, settle: int = 10,
                 dive: bool = False, touch=0.75):
        disc = touch is None or isinstance(touch, (int, float))
        item = None if disc else tuple(touch)                         # (R, Z, hz): the item's own touch
        self.R, self.look, self.cell_m, self.dive, self.air = router, look, cell_m, dive, air
        self.reach = touch if disc and touch is not None else 0.75    # the disc's radius round its point
        targets = list(target) if isinstance(target, (list, tuple)) and target and isinstance(target[0], str) \
            else [] if isinstance(target, np.ndarray) else [target]
        gmask = target.astype(bool) if isinstance(target, np.ndarray) else np.zeros(router.V, dtype=bool)
        self.gp = self.band = self.touch = None
        for t in targets:
            m, gp, band = router.goal(t)
            if gp is not None and item is not None:       # the item's touch: the vertices whose standing body is in it
                R, Z, hz = item
                c = item_centre(router.lv, gp, hz)
                self.touch = (c, R, Z)
                tm = ((((router.X - c[0]) ** 2 + (router.Y - c[1]) ** 2) / (R * R)
                       + (router.Z + 1.0 - c[2]) ** 2 / (Z * Z)) <= 1.0) & (router.node_soft >= 0)
                m = tm if tm.any() else m
            gmask |= m
            if gp is not None:
                self.gp, self.band = gp, band
        self.touch_shape = item if self.touch is not None else None
        self.settle = 0 if self.gp is not None else settle
        self.survive = SURVIVE if self.gp is not None else 0
        self.zones = None if self.gp is not None else {
            f"{router.R.name}.Z{z:03d}" for t in targets for z in router._zones_of(t)}
        g = np.nonzero(gmask)[0]
        self.box = (router.X[g].min() - 2, router.X[g].max() + 2, router.Y[g].min() - 2, router.Y[g].max() + 2,
                    router.Z[g].min() - 3, router.Z[g].max() + 3) if len(g) else None
        eok = router.usable_edges(router.tiers[-1], air, PROBES)
        e = router.eid
        ok = (e == -1) | (e == rt.CROSS) | np.append(eok, False)[np.where(e >= 0, e, len(eok))]
        self.dist, self.nxt, self.link = self._dijkstra(g, ok)
        climb = np.array([x["kind"] == "climb" for _, _, x in router.edges] + [False], dtype=bool)
        c = np.nonzero(ok & (router.kind == rt.K_EDGE) & climb[np.where(e >= 0, e, len(climb) - 1)])[0]
        self._climbs = c[np.isfinite(self.dist[router.dst[c]])]     # the goal's climbs (links), for climbing rows
        ride = np.array([rt.BORDER_KINDS.get(x["kind"]) == "wait" for _, _, x in router.edges] + [False], dtype=bool)
        r = np.nonzero(ok & (router.kind == rt.K_EDGE) & ride[np.where(e >= 0, e, len(ride) - 1)])[0]
        self._rides = r[np.isfinite(self.dist[router.dst[r]])]       # the goal's rides (links), for riders (X.53)
        self.floor = None               # the start's cost once anchored (:meth:`anchor`)
        fin = np.nonzero(np.isfinite(self.dist))[0]        # the finite vertices on a 4 m grid, for off-graph rows
        key = (np.floor(router.X[fin] / 4).astype(np.int64) << 32) + np.floor(router.Y[fin] / 4).astype(np.int64)
        o = np.argsort(key, kind="stable")
        fin, key = fin[o], key[o]
        u, at, n = np.unique(key, return_index=True, return_counts=True)
        self._grid = {int(k): fin[i:i + c] for k, i, c in zip(u.tolist(), at.tolist(), n.tolist())}
        # one finite vertex per 3 m cell (its cheapest), for the straight-line fallback far off the graph
        k3 = np.stack([np.floor(router.X[fin] / 3), np.floor(router.Y[fin] / 3), np.floor(router.Z[fin] / 3)], 1)
        o = np.lexsort((self.dist[fin], k3[:, 2], k3[:, 1], k3[:, 0]))
        fin, k3 = fin[o], k3[o]
        rep = fin[np.r_[True, (k3[1:] != k3[:-1]).any(axis=1)]] if len(fin) else fin
        self._far_v, self._far_d = rep, self.dist[rep]
        self._far_xyz = np.stack([router.X[rep], router.Y[rep], router.Z[rep]], 1)
        # a goal with no vertex but a point (a pickup no floor holds): its direct line (Step X.53, AZ-593)
        self.aim = None if len(self._far_v) else (self.touch[0] if self.touch is not None else self.gp)
        self._flights: dict[int, tuple] = {}
        self._tracks = None             # the goal's flights (takeoff vertex, landing vertex), made on first use

    def _dijkstra(self, goals, ok):
        R = self.R
        k = np.nonzero(ok)[0]
        k = k[np.argsort(R.dst[k], kind="stable")]
        rptr = np.searchsorted(R.dst[k], np.arange(R.V + 1)).tolist()
        rsrc, rcost, rk = R.src[k].tolist(), R.cost[k].tolist(), k.tolist()
        dist, nxt, link = [math.inf] * R.V, [-1] * R.V, [-1] * R.V
        heap = [(0.0, g) for g in goals.tolist()]
        for _, g in heap:
            dist[g] = 0.0
        heapq.heapify(heap)
        while heap:
            d, v = heapq.heappop(heap)
            if d > dist[v]:
                continue
            for i in range(rptr[v], rptr[v + 1]):
                u = rsrc[i]
                nd = d + rcost[i]
                if nd < dist[u]:
                    dist[u], nxt[u], link[u] = nd, v, rk[i]
                    heapq.heappush(heap, (nd, u))
        return np.array(dist), np.array(nxt), np.array(link)

    def _far(self, feet) -> tuple[int, float]:
        """(vertex, cost): the finite vertex (one per 3 m cell) whose cost to go plus the straight line to it at
        walk speed is least, for a body off the goal's graph; (-1, inf) when the goal has no finite vertex."""
        if not len(self._far_v):
            return -1, math.inf
        d = np.sqrt(((self._far_xyz - np.asarray(feet, dtype=float)) ** 2).sum(axis=1))
        c = self._far_d + d / rt.WALK_MPS
        j = int(np.argmin(c))
        return int(self._far_v[j]), float(c[j])

    def _best_near(self, feet) -> int:
        """The finite vertex around ``feet`` (the 4 m grid cells about it, within 4 m in height) with the least
        cost to go plus the way to it at walk speed; -1 for none."""
        R = self.R
        gx, gy = int(feet[0] // 4), int(feet[1] // 4)
        parts = [q for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                 if (q := self._grid.get(((gx + dx) << 32) + gy + dy)) is not None]
        js = np.concatenate(parts) if parts else np.zeros(0, dtype=np.int64)
        js = js[np.abs(R.Z[js] - feet[2]) < 4]
        if not len(js):
            return -1
        d = np.hypot(R.X[js] - feet[0], R.Y[js] - feet[1]) + np.abs(R.Z[js] - feet[2])
        return int(js[int(np.argmin(self.dist[js] + d / rt.WALK_MPS))])

    def _place(self, row):
        """(feet, vertex, cost, how, link): where the goal's cost field holds the row (Step X.53).  ``how``:
        ``climb`` (state 1 on one of the goal's climbs: its top and the climb's cost still to go by height,
        :meth:`_on_link`, Step R1.29e), ``flight`` (in the air on one of the goal's flights whose landing its
        arc can still make: its landing and the time still to land, :meth:`_on_flight`, AZ-621), ``vertex`` (the
        vertex the feet stand on or the water holding them; a body in the air or off a floor, the floor under it;
        a standing or swimming body only the one at its feet, never one under a top it stands on), ``ride``
        (standing off the goal's field in one of the goal's rides' columns: its far end and the ride's cost still
        to go by height, as a climb's, Step X.53), ``near`` (the best finite vertex nearby, 2 s more) or ``far``
        (the straight line to where the goal's field reaches, :meth:`_far`; vertex -1 when the goal has no finite
        vertex).  ``cost``: the vertex's cost to go plus the way to it (``far``: the fallback's, :data:`FAR_S` not
        added); ``link``: the climb's, flight's or ride's link, else -1."""
        feet = (row.pos[0], row.pos[1], row.pos[2] - 1.0)
        if row.state == CLIMBING and (on := self._on_link(feet, self._climbs)) is not None:
            return feet, on[0], float(self.dist[on[0]]) + on[1], "climb", on[2]
        if row.state in AIRBORNE and (on := self._on_flight(row, feet)) is not None:
            return feet, on[0], float(self.dist[on[0]]) + on[1], "flight", on[2]
        v = self.R.locate(feet, prefer_water=row.state == SWIMMING, fallback=not settled(row))
        if v >= 0 and math.isfinite(self.dist[v]):
            return feet, v, float(self.dist[v]) + math.dist(feet, self.R.pt(v)) / rt.WALK_MPS, "vertex", -1
        if settled(row) and (on := self._on_link(feet, self._rides)) is not None:
            return feet, on[0], float(self.dist[on[0]]) + on[1], "ride", on[2]
        v = self._best_near(feet)
        if v >= 0:
            return feet, v, float(self.dist[v]) + math.dist(feet, self.R.pt(v)) / rt.WALK_MPS + 2.0, "near", -1
        j, c = self._far(feet)
        return feet, j, c, "far", -1

    def _vertex(self, row):
        """(feet, vertex, rest) of :meth:`_place`: the vertex the row's way goes on from, ``rest`` the way to it
        (vertex -1 off the goal's field: the far fallback)."""
        feet, v, c, how, _ = self._place(row)
        return (feet, -1, math.inf) if how == "far" else (feet, v, c - float(self.dist[v]))

    def _on_link(self, feet, k):
        """(the far end, the cost still to go from the far end's, the link) of the link among ``k`` a body is on: a
        link whose ends' heights hold the feet (a metre out) and which passes within :data:`CLIMB_R` of them, its
        cost interpolated by the feet's height between its ends, plus the way across to it at walk speed; the
        cheapest such, None for none.  A climbing body stands on no vertex: the floor under it (the way up to it
        at walk speed), the nearest vertex's cost and 2 s, or the far fallback and :data:`FAR_S` made its cost rise
        as it climbed (a5/g0/r1773's way back, R1.29c)."""
        R = self.R
        if not len(k):
            return None
        u, w = R.src[k], R.dst[k]
        zu, zw = R.Z[u], R.Z[w]
        ax, ay, bx, by = R.X[u], R.Y[u], R.X[w], R.Y[w]
        s = np.clip(((feet[0] - ax) * (bx - ax) + (feet[1] - ay) * (by - ay))
                    / np.maximum((bx - ax) ** 2 + (by - ay) ** 2, 1e-12), 0.0, 1.0)
        off = np.hypot(ax + s * (bx - ax) - feet[0], ay + s * (by - ay) - feet[1])
        ok = (off < CLIMB_R) & (feet[2] >= np.minimum(zu, zw) - 1.0) & (feet[2] <= np.maximum(zu, zw) + 1.0)
        if not ok.any():
            return None
        t = np.clip((feet[2] - zu) / np.where(np.abs(zw - zu) > 1e-6, zw - zu, 1.0), 0.0, 1.0)
        rest = (1.0 - t) * R.cost[k] + off / rt.WALK_MPS
        j = np.nonzero(ok)[0][int(np.argmin((self.dist[w] + rest)[ok]))]
        return int(w[j]), float(rest[j]), int(k[j])

    def finite_at(self, row) -> bool:
        """Whether the goal's cost field reaches the row (its vertex, or one within reach, has a finite cost)."""
        return self._place(row)[3] != "far"

    def anchor(self, start_row) -> None:
        """Set the search's start (Step X.53, AZ-578): when the goal's field reaches it, a row the field holds only
        by a vertex nearby or the far fallback never costs less than the start's cost plus :data:`FAR_S`, so a
        straight line through air, walls and floors no longer undercuts the graph (L18a's best fell 18.7 m under
        the dock, 15.9 s against the dock's 23.5 s).  A start off the field leaves the fallback as it is."""
        self.floor = None
        if self.finite_at(start_row):
            self.floor = self.cost(start_row)

    def _flight(self, k: int):
        """(takeoff, unit track, landing, jump?, flaps?) of region-edge link ``k``: the router's takeoff point (the
        takeoff floor's end on the track, 0.25 m back) for a flight, its source vertex for another edge; ``flaps``:
        a flap flight the hardest tier needs flaps for."""
        if k not in self._flights:
            R = self.R
            u, w = int(R.src[k]), int(R.dst[k])
            e = R.edges[int(R.eid[k])][2]
            act = rt.FLIGHT_KINDS.get(e["kind"])
            at = R._takeoff(u, w, e) if act else R.pt(u)
            q = R.pt(w)
            d = math.hypot(q[0] - at[0], q[1] - at[1]) or 1.0
            ranks = e.get("ranks") or [0]
            self._flights[k] = (at, ((q[0] - at[0]) / d, (q[1] - at[1]) / d), q, act in ("jump", "flap"),
                                act == "flap" and ranks[min(len(R.tiers), len(ranks)) - 1] > 0)
        return self._flights[k]

    @staticmethod
    def _arc(row, feet, q) -> float | None:
        """The seconds a body in the air still needs to land on ``q`` (a flight's landing vertex) by its arc
        (:func:`air_time`: its vertical speed, the flaps left in the jump with the gauge not empty under the flap
        ceiling peak_z + :data:`FLAP_H`), None when the arc can't (AZ-621): the feet can't rise to the landing's
        floor less the rim step-up (``flights.RIM_LIFT``), or the gap is over what the air speed (walk speed)
        covers before they fall under it, :data:`REACH_M` given.  The time: the gap at walk speed or the fall onto
        the landing's height, whichever is longer."""
        o = row.obs
        peak = o.peak_z
        left = max(0, (o.flaps or 0) - o.flaps_used) if o.gauge else 0
        ceil = peak + FLAP_H - 1.0 if peak is not None and math.isfinite(peak) and peak > -1e30 else -math.inf
        gap = math.hypot(q[0] - feet[0], q[1] - feet[1])
        reach = air_time(feet[2], o.vel[2], q[2] - RIM_LIFT, left, ceil)
        if reach is None or gap > reach[1] * rt.WALK_MPS + REACH_M:
            return None
        down = air_time(feet[2], o.vel[2], q[2], left, ceil)
        return max(gap / rt.WALK_MPS, (down or reach)[0])

    def _on_flight(self, row, feet):
        """(the landing vertex, the time still to land, the link) of the goal's flight the body in the air is on: a
        flight link of the cheapest ways whose takeoff floor stands at the fall reference's height (the floor the
        jump left, entity+0x168), whose track passes within :data:`TRACK_M` of the body and whose landing its arc
        can still make (:meth:`_arc`, AZ-621: a body that can't is costed and steered by the floor it falls to), the
        one with least cost to go from there; None for none (no fall reference, or no such flight)."""
        R, o = self.R, getattr(row, "obs", None)
        ref = None if o is None else o.fall_ref
        if ref is None or not math.isfinite(ref) or ref < -1e30:
            return None
        if self._tracks is None:
            u = np.nonzero(self.link >= 0)[0]
            k = self.link[u]
            fly = np.array([e["kind"] in rt.FLIGHT_KINDS and rt.FLIGHT_KINDS[e["kind"]] != "drop"
                            for _, _, e in R.edges] + [False], dtype=bool)
            m = (R.kind[k] == rt.K_EDGE) & fly[np.where(R.eid[k] >= 0, R.eid[k], len(fly) - 1)]
            self._tracks = (u[m], R.dst[k[m]], k[m])
        u, w, k = self._tracks
        here = np.abs(R.Z[u] - ref) < 0.6
        u, w, k = u[here], w[here], k[here]
        if not len(u):
            return None
        ax, ay, bx, by = R.X[u], R.Y[u], R.X[w], R.Y[w]
        L = np.maximum(np.hypot(bx - ax, by - ay), 1e-6)
        along = ((feet[0] - ax) * (bx - ax) + (feet[1] - ay) * (by - ay)) / L
        side = np.abs((feet[0] - ax) * (by - ay) - (feet[1] - ay) * (bx - ax)) / L
        best = None
        for j in np.nonzero((side < TRACK_M) & (along > -1.0) & (along < L + 1.0))[0].tolist():
            t = self._arc(row, feet, R.pt(int(w[j])))
            if t is not None and (best is None or self.dist[w[j]] + t < best[0]):
                best = (float(self.dist[w[j]]) + t, int(w[j]), t, int(k[j]))
        return None if best is None else best[1:]

    @staticmethod
    def flap_now(row, feet, q) -> bool:
        """The descent-flap rule (:class:`RouteGoal`): whether a body in the air flaps toward landing ``q``."""
        o = getattr(row, "obs", None)
        if o is None or not o.flaps or o.flaps_used >= o.flaps or not o.gauge or o.vel[2] >= 0:
            return False
        peak = o.peak_z
        if peak is None or not math.isfinite(peak) or peak < -1e30:
            return False
        if not FLAP_MARGIN < peak + FLAP_H - row.pos[2] < DESCENT_D - FLAP_MARGIN:
            return False
        dz, gap = feet[2] - q[2], math.hypot(q[0] - feet[0], q[1] - feet[1])
        if dz <= 0.0:
            return True
        vz, g = o.vel[2], 9.8
        return (vz + math.sqrt(vz * vz + 2 * g * dz)) / g * rt.WALK_MPS < gap

    casts = True        # whether the guide asks for a cast (the trick explorer's don't: :class:`_Explore`)

    def _cast_due(self, row) -> bool:
        """Whether a body about to fly flaps should recast first: an air kit's gauge under 1 (spent, or the shield
        dropped)."""
        o = getattr(row, "obs", None)
        return self.casts and bool(self.air) and o is not None and o.gauge is not None and o.gauge < 1.0 - 1e-6

    def zone(self, row) -> str | None:
        """The row's zone: L3's, else the router's at the feet, the explorer's rule (:class:`_Explore`, Step X.53):
        a body on a floor or swimming is in the zone of the floor its feet are on or the water holding it, never of
        a floor under a top it stands on (a rig's deck over the goal's floor reaches no zone goal); one off the
        floor (:data:`OFF_FLOOR`) in the zone under it."""
        if row.zone is not None:
            return row.zone
        return self.R.zone_at((row.pos[0], row.pos[1], row.pos[2] - 1.0), prefer_water=row.state == SWIMMING,
                              fallback=row.state in OFF_FLOOR)

    def reached(self, row) -> bool:
        if self.touch is not None:     # the game's touch: in any state, while the player has HP (0x8C520)
            (cx, cy, cz), R, Z = self.touch
            p = row.pos
            return row.hp > 0 and ((p[0] - cx) ** 2 + (p[1] - cy) ** 2) / (R * R) + (p[2] - cz) ** 2 / (Z * Z) <= 1.0
        if row.state in AIRBORNE or row.state == DEAD:
            return False
        feet = (row.pos[0], row.pos[1], row.pos[2] - 1.0)
        if self.gp is not None:
            return (math.hypot(feet[0] - self.gp[0], feet[1] - self.gp[1]) <= self.reach
                    and self.band[0] <= self.gp[2] - feet[2] <= self.band[1])
        b = self.box
        if not settled(row) or b is None or not (b[0] <= feet[0] <= b[1] and b[2] <= feet[1] <= b[3]
                                                 and b[4] <= feet[2] <= b[5]):
            return False
        return self.zone(row) in self.zones

    def cost(self, row) -> float:
        feet, v, c, how, _ = self._place(row)
        if how == "far":                # off the graph: the straight line to where the goal's field reaches
            if v < 0:
                return self._direct(row.pos) if self.aim is not None else 1e6
            c += FAR_S
        else:
            c += self._depth(row, feet)
        if self.floor is not None and how in ("near", "far"):     # never under the anchored start's (X.53)
            c = max(c, self.floor + FAR_S)
        return c

    def _direct(self, p) -> float:
        """A goal with no vertex (:attr:`aim`, Step X.53): the body centre ``p``'s way to its point, the horizontal
        gap at walk speed plus the height still to rise at :data:`RISE_MPS` (:class:`TrickExitGoal`'s form)."""
        a = self.aim
        return math.hypot(a[0] - p[0], a[1] - p[1]) / rt.WALK_MPS + max(0.0, a[2] - p[2]) / RISE_MPS

    def _depth(self, row, feet) -> float:
        """With ``dive`` (Step R1.29), a swimming row's dive still to go to a pickup under it, at the dive's
        5 m/s (RE_MOVEMENT): the route graph's water is its surface, so its cost there is the same at any depth."""
        if not self.dive or self.gp is None or row.state != SWIMMING:
            return 0.0
        return max(0.0, feet[2] - (self.gp[2] - self.band[0])) / DIVE_MPS

    def toward(self, row):
        if row.state in AIRBORNE:
            feet = (row.pos[0], row.pos[1], row.pos[2] - 1.0)
            on = self._on_flight(row, feet)
            v = on[0] if on is not None else self._best_near(feet)
            v = v if v >= 0 else self._far(feet)[0]
            if v < 0:
                return None, False
            q = self.R.pt(v)
            if on is not None and math.hypot(q[0] - feet[0], q[1] - feet[1]) < LAND_R:   # over the landing: on
                dx, dy = self._flight(on[2])[1]                                         # along the track (AZ-621)
                return math.atan2(-dx, dy), self.flap_now(row, feet, q)
            return heading_to(feet, q), self.flap_now(row, feet, q)
        R = self.R
        feet, v, _, how, link = self._place(row)
        if how == "far":
            to = R.pt(v) if v >= 0 else self.aim
            return (heading_to(feet, to), False) if to is not None else (None, False)
        if how == "ride":                # on a ride's deck: stand, and step off level with the far floor (X.53)
            q = R.pt(int(R.dst[link]))
            return (heading_to(feet, q), False) if abs(feet[2] - q[2]) <= R.climb else (None, False)
        walked, u, target = 0.0, v, None
        for _ in range(400):
            w = int(self.nxt[u])
            if w < 0:
                target = R.pt(u)
                break
            k = int(self.link[u])
            if int(R.kind[k]) == rt.K_EDGE:
                kind = R.edges[int(R.eid[k])][2]["kind"]
                if kind == "teleport":     # into its pad, not toward where it puts the player (Step X.53)
                    target = R.pads[int(R.eid[k])]
                    break
                if rt.BORDER_KINDS.get(kind) == "wait":      # a ride: onto its source vertex and stand there (X.53)
                    p = R.pt(u)
                    if math.hypot(p[0] - feet[0], p[1] - feet[1]) < RIDE_M:
                        return None, False
                    target = p
                    break
                at, (dx, dy), _, jump, flaps = self._flight(k)
                cast = flaps and self._cast_due(row)      # a flap flight with the gauge spent: recast first
                rx, ry = feet[0] - at[0], feet[1] - at[1]
                along, side = rx * dx + ry * dy, abs(rx * dy - ry * dx)
                if along > -0.2 and side < 0.8:            # at the takeoff: go, along the track (or cast, at rest)
                    return (None, False, None, True) if cast else (math.atan2(-dx, dy), jump)
                if side < 0.5 and along > -3.0:            # on the track behind it: run to the takeoff
                    return (math.atan2(-dx, dy), False, max(1, math.ceil((-along - 0.1) * 30 / rt.WALK_MPS)),
                            *((True,) if cast else ()))
                target = (at[0] - 1.5 * dx, at[1] - 1.5 * dy) if walked < self.look else R.pt(u)
                if cast:
                    return heading_to(feet, target), False, None, True
                break
            walked += math.dist(R.pt(u), R.pt(w))
            u = w
            if walked >= self.look:
                target = R.pt(u)
                break
        if target is None or math.hypot(target[0] - feet[0], target[1] - feet[1]) < 0.05:
            return None, False
        return heading_to(feet, target), False

    def ahead(self, row) -> dict:
        """The stall record of a search's best row (Step X.52, ``l3_search.Result.stall``): its zone and the first
        region edge on the goal's cheapest way from it, by its index in the router's ``edges``, its kind and
        confidence and the zones at its ends; ``edge`` None with kind ``walk`` when the way is walks to the goal
        (``into``: the first other zone on that walk, Step X.52b), ``off the graph`` when no vertex near the row
        has a cost and none has one at all.  ``stage`` (Step X.52b) says where the row stalled: ``flying`` (in the
        air on one of the goal's flights it can still land: the edge is that flight's, Step X.53, AZ-581, AZ-621;
        one its arc can't make is named from the floor it falls to), ``riding`` (standing on
        one of the goal's rides, its edge named, Step X.53), ``on no floor`` (it stands, or swims, on no floor of
        the model, a top the reach model doesn't hold: AZ-582's; the way is then the one from the vertex nearby or
        the fallback's, Step X.53), ``no goal vertex`` (the goal has no vertex, its cost the direct line to its
        point: kind ``the direct line``, Step X.53), ``no zone`` (it stands, or swims, where the zone rule reads
        none: AZ-538's rig decks and arrivals), ``off the graph`` (the far fallback's straight line: the way ahead
        is then the one from the vertex it steers to, ``steer`` its zone), ``walk`` or ``edge``.  Ids only, never
        positions."""
        R = self.R
        zone = self.zone(row)
        feet, u, _, how, link = self._place(row)
        stage = None
        if settled(row) and how in ("near", "far") \
                and R.locate(feet, prefer_water=row.state == SWIMMING, fallback=False) < 0:
            stage = "on no floor"
        elif zone is None and settled(row):
            stage = "no zone"
        out = {"zone": zone, "stage": stage, "edge": None, "kind": "off the graph", "conf": None, "from": None,
               "to": None}
        if how in ("flight", "ride"):
            return {**out, "stage": "flying" if how == "flight" else "riding", **self._edge_record(link)}
        if how == "far" and u < 0 and self.aim is not None:
            return {**out, "stage": "no goal vertex", "kind": "the direct line"}
        if how == "far":
            out["stage"] = out["stage"] or "off the graph"
            if u >= 0:
                out["steer"] = R.zone_at(R.pt(u), prefer_water=u >= R.ns)
        here, into = None, None
        for _ in range(R.V if u >= 0 else 0):
            z = R.zone_at(R.pt(u), prefer_water=u >= R.ns)
            here = here or z
            into = into or (z if z not in (None, here) else None)
            if (w := int(self.nxt[u])) < 0:
                return {**out, "stage": out["stage"] or "walk", "kind": "walk", "into": into}
            k = int(self.link[u])
            if int(R.kind[k]) == rt.K_EDGE:
                return {**out, "stage": out["stage"] or "edge", **self._edge_record(k)}
            u = w
        return out

    def _edge_record(self, k: int) -> dict:
        """A stall record's edge (:meth:`ahead`): link ``k``'s region edge by its index in the router's ``edges``,
        its kind, confidence and the zones at the link's ends, and why the router doubts it (``doubt``, the light
        trick graph's, Step X.53) when it does."""
        R = self.R
        e = R.edges[int(R.eid[k])][2]
        src, dst = int(R.src[k]), int(R.dst[k])
        why = getattr(R, "doubt", {}).get(int(R.eid[k]))
        return {"edge": int(R.eid[k]), "kind": e["kind"], "conf": e.get("conf"),
                "from": R.zone_at(R.pt(src), prefer_water=src >= R.ns),
                "to": R.zone_at(R.pt(dst), prefer_water=dst >= R.ns), **({"doubt": why} if why else {})}

    def cell(self, row) -> tuple:
        feet, o, air = (row.pos[0], row.pos[1], row.pos[2] - 1.0), getattr(row, "obs", None), row.state in AIRBORNE
        left = max(0, o.flaps - o.flaps_used) if air and o is not None and o.flaps is not None else None
        full = None if o is None or o.gauge is None else o.gauge >= 1.0 - 1e-6
        return (self.zone(row), int(feet[0] // self.cell_m), int(feet[1] // self.cell_m), int(feet[2] // 1.5),
                air, left, full)


class ExitGoal(RouteGoal):
    """A level exit's trigger (Step X.12): ``exit_id`` a generated exit (``w1/g0/r3352``) whose gate hint touches
    trigger meshes.  Reached in any state (a fall exit fires in the air) when the body centre is inside one of the
    meshes, the game's own touch (AZ-483: the player's query 0x60BD0 from 0x85587 at critter+0x15C, a platform's
    test 0x79D30 -> :func:`inside_mesh`), not the column under it.  The cost, guidance and cells are
    :class:`RouteGoal`'s toward the walk vertices in the meshes' columns, from their lowest point 2 m down to their
    highest 0.5 m up (else the reach nodes the derive anchors the exit to).  A gate beyond the touch (a switch, an
    ``and``, a timer, whose ``{>=N}`` seconds ``wait`` holds in ticks) only whole steps run: the levelSwitch's fire
    is the outcome there (``l3_certify``), and the chain driver's xemu replay confirms the load."""

    def __init__(self, router, exit_id: str, *, air: int = 0, **kw):
        R, lv, w = router.R, router.lv, router.w
        ex = next((e for e in R.gen.get("exits", []) if e["id"] == exit_id), None)
        if ex is None:
            raise KeyError(f"{R.name}: no exit {exit_id!r}")
        names = sorted({nm for kind, nm in R.HINT_NAMES.findall(ex.get("gate_hint") or "") if kind == "touch"})
        tris = [lv.tris_of(oi) for nm in names for oi in lv.by_name.get(nm, [])]
        if not tris:
            raise ValueError(f"{exit_id}: no trigger mesh to touch (its gate hint {ex.get('gate_hint')!r})")
        col, zlo, zhi = raster(lv, np.concatenate(tris))[:3]
        u, inv = np.unique(col, return_inverse=True)
        lo, hi = np.full(len(u), np.inf), np.full(len(u), -np.inf)
        np.minimum.at(lo, inv, zlo)
        np.maximum.at(hi, inv, zhi)
        self._band = dict(zip(u.tolist(), zip((lo - 2.0).tolist(), (hi + 0.5).tolist())))
        mask = np.zeros(router.V, dtype=bool)
        a, c = lookup(w.u, w.a, w.c, u)
        for k in range(w.mx):
            v = k < c
            j = (a + k)[v]
            mask[j[(w.z[j] >= lo[v] - 2.0) & (w.z[j] <= hi[v] + 0.5)]] = True
        if not mask.any():              # no floor inside it (a pit): the nodes the derive anchors the exit to
            mask = router.goal(exit_nodes(router, exit_id))[0]
        super().__init__(router, mask, air=air, **kw)
        self.settle, self.exit, self.dest = 0, exit_id, ex["dest"]
        self._meshes = [(V, V.reshape(-1, 3).min(axis=0), V.reshape(-1, 3).max(axis=0))
                        for V in (lv.P[t] for t in tris)]
        self.wait = max((round(float(x) * 30) for x in re.findall(r"currentTime\{>=([0-9.]+)\}",
                                                                    ex.get("gate_hint") or "")), default=0)

    def reached(self, row) -> bool:
        p = np.asarray(row.pos, dtype=float)    # the body centre: the point the game's touch query tests
        return any(bool((lo <= p).all() and (p <= hi).all()) and inside_mesh(V, p) for V, lo, hi in self._meshes)


def object_points(lv, obj: str) -> np.ndarray:
    """An object's world points (private): a mesh the level's collision holds by name (``LightShape``,
    ``HoseStuff:PublicJoystickShape``) or a generated id (``w2/g0/r1370``: its record's mesh, else its point)."""
    if "/" in obj:
        _, gs, rs = obj.split("/")
        oi = lv.by_rec.get((int(gs[1:]), int(rs[1:])))
        if oi is None:
            return np.array(lv.rec_points(obj)[0], dtype=float)
        ois = [oi]
    else:
        ois = lv.by_name.get(obj, [])
    tris = [lv.tris_of(oi) for oi in ois]
    if not tris or not sum(len(t) for t in tris):
        raise KeyError(f"{lv.name}: no mesh {obj!r}")
    return lv.P[np.concatenate(tris)].reshape(-1, 3)


class ObjectGoal(RouteGoal):
    """Within reach of an object (Step X.19: a minigame's console, a barrier's front, a keylock, a touch pad):
    ``obj`` as :func:`object_points` takes it.  Reached standing or swimming with the feet within ``radius`` m
    (horizontally) of the object's box and between 2 m under its lowest point and 1 m over its highest
    (``radius = 0``: inside its footprint, a pad to step on); ``side``: zones whose walk vertices only count (a
    barrier's near side).  ``inside``: the game's touch of a shape instead (AZ-483): the body centre inside its mesh
    (:func:`inside_mesh`), in any state.  The cost, guidance and cells are :class:`RouteGoal`'s toward those
    vertices."""

    def __init__(self, router, obj: str, *, radius: float = 2.0, side=None, air: int = 0, inside: bool = False,
                 **kw):
        p = object_points(router.lv, obj)
        self._mesh = p.reshape(-1, 3, 3) if inside and len(p) % 3 == 0 and len(p) >= 3 else None
        lo, hi = p.min(axis=0), p.max(axis=0)
        self.obj, self._box = obj, (lo[0] - radius, hi[0] + radius, lo[1] - radius, hi[1] + radius, lo[2] - 2.0,
                                    hi[2] + 1.0)
        b = self._box
        X, Y, Z = router.X, router.Y, router.Z
        mask = (X >= b[0]) & (X <= b[1]) & (Y >= b[2]) & (Y <= b[3]) & (Z >= b[4]) & (Z <= b[5])
        if side:
            mask &= router.goal(sorted(side)[0])[0] if len(side) == 1 else np.any(
                [router.goal(z)[0] for z in sorted(side)], axis=0)
        if not mask.any():
            raise ValueError(f"{obj}: no walk vertex within {radius} m of it" + (f" in {sorted(side)}" if side else ""))
        super().__init__(router, mask, air=air, **kw)
        self.settle = min(self.settle, 4)

    def reached(self, row) -> bool:
        if self._mesh is not None:
            return inside_mesh(self._mesh, row.pos)
        if not settled(row):
            return False
        b, feet = self._box, (row.pos[0], row.pos[1], row.pos[2] - 1.0)
        return b[0] <= feet[0] <= b[1] and b[2] <= feet[1] <= b[3] and b[4] <= feet[2] <= b[5]


def make_object_goal(reach: str, obj: str, *, prof: str = "logic", air: int = 0, radius: float = 2.0,
                     side=None, inside: bool = False) -> ObjectGoal:
    """The factory for an object (:class:`ObjectGoal`) on the pickled reach model ``reach``'s route graph."""
    return ObjectGoal(router_of(reach, prof, air), obj, radius=radius, side=side, air=air, inside=inside)


def route_seed(router, feet, target, *, air: int = 0, probes=PROBES) -> list[tuple]:
    """A seed string from the route planner's plan from ``feet`` to ``target`` (``Router.plan``: the hardest tier,
    the kit's ``air``, every probe class), as ``(n, heading, hold)`` tuples: each walk or swim way-point a segment
    of its heading and its ticks at walk speed (2 more for the speed ramp), a jump or flap the run to the takeoff
    then Y for :data:`JUMP_HOLD` ticks through the flight's ticks (a flap: three more presses), a drop the
    walk-off, a climb a push into the face, a ride 3 s at rest, a teleport the walk into its pad and 1 s there.
    [] when the planner has no route."""
    targets = list(target) if isinstance(target, (list, tuple)) and target and isinstance(target[0], str) \
        else [target]
    if "_lists" not in router.__dict__:      # load_router drops them (the workers' memory); the planner needs them
        router._lists = (router.indptr.tolist(), router.dst.tolist(), router.cost.tolist())
    route = None
    for tg in targets:                       # a zone set: the cheapest route to any of its zones
        r = router.plan(feet, tg, tier=router.tiers[-1], air=air, allow_probe=probes)
        if r is not None and r.reached and (route is None or r.cost_s < route.cost_s):
            route = r
    if route is None:
        return []
    segs: list[tuple] = []
    p = (float(feet[0]), float(feet[1]), float(feet[2]))

    def walk(q, extra: int = 2):
        nonlocal p
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        if d > 0.05:
            segs.append((math.ceil(d * 30 / rt.WALK_MPS) + extra, heading_to(p, q), 0))
        p = (q[0], q[1], q[2])

    for leg in route.legs:
        if leg.action in ("jump", "flap", "drop") and leg.at is not None:
            at, q = leg.at, leg.pts[-1]
            walk(at, 0)
            h = heading_to(at, q)
            v0 = 0.0 if leg.action == "drop" else JUMP_V0[1 if air >= 1 else 0]
            n = (rt.fall_ticks(v0, at[2] - q[2]) or 30) + 6
            if leg.action == "drop":
                segs.append((n, h, 0))
            elif leg.action == "jump":
                segs.append((n, h, JUMP_HOLD))
            else:
                segs += [(8, h, JUMP_HOLD)] + [(7, h, 2)] * 3 + [(max(n - 8, 4), h, 0)]
            p = (q[0], q[1], q[2])
        elif leg.action == "wait":
            segs.append((90, None, 0))
            p = leg.pts[-1]
        elif leg.action == "teleport":       # into the pad; the game puts the player at its spot
            walk(leg.pts[0])
            segs.append((30, None, 0))
            p = leg.pts[-1]
        else:
            for q in leg.pts:
                walk(q, 20 if leg.action == "climb" else 2)
    return segs


ROUTER_CODE = ("devkit/rando/draft", "devkit/rando/physics.py", "src/azurkit/tools/randomizer/draft",
               "src/azurkit/tools/randomizer/physics.py", "src/azurkit/tools/randomizer/art/collision.py")
# What a Router is built from besides its reach model (the checkout's paths): the draft's code and authoring
# (``_held``'s ``rig_held``) and physics.py's run and swim speeds (``route.WALK_MPS``, ``SWIM_MPS``: its cost field)
WRITING_S = 900.0     # a cache file's writer mark older than this is a dead writer's


def router_key(reach: str, prof: str) -> str:
    """A built ``Router``'s content key (Step X.95): the reach model file's path and identity (device, inode, size,
    mtime_ns, ctime_ns: a write or a rebuild changes them), ``prof``, the files of :data:`ROUTER_CODE` (each path and
    its bytes) and the Python and numpy versions; sha256[:16]."""
    st = os.stat(reach)
    h = hashlib.sha256(json.dumps([os.path.abspath(reach), st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns,
                                   st.st_ctime_ns, prof, np.__version__, list(sys.version_info[:2])]).encode())
    root = Path(__file__).resolve().parents[3]
    for rel in ROUTER_CODE:
        p = root / rel
        for f in sorted(q for q in p.rglob("*") if q.suffix in (".py", ".toml") and q.is_file()) if p.is_dir() else [p]:
            h.update(f"{f.relative_to(root).as_posix()}\n".encode() + f.read_bytes())
    return h.hexdigest()[:16]


def load_router(reach: str, prof: str = "logic"):
    """A ``Router`` for profile ``prof`` from a pickled reach model (the certification script keeps one per level
    in the private store).  Built once per content key (:func:`router_key`, Step X.95: d1's took 2 s to build and
    0.4 s to load, w1's 16.5 s and 0.8 s) and kept, the router with its reach model, in ``routers-azurkit/`` beside
    the reach model (the store's privacy: they hold positions; Modkit's own keys live in ``routers/`` there, which
    this keeps apart, Step 4.13d2), the newest key a model and profile only; one writer at a time (a ``.writing``
    mark), so a pool's workers building one router together write it once."""
    folder = Path(reach).resolve().parent / "routers-azurkit"
    stem = f"{Path(reach).stem}-{prof}-"
    try:
        cached = folder / f"{stem}{router_key(reach, prof)}.pkl"
    except OSError:
        cached = None
    if cached is not None and cached.is_file():
        try:
            with open(cached, "rb") as f:
                return pickle.load(f)
        except (OSError, EOFError, pickle.UnpicklingError, AttributeError, ImportError):
            pass                                           # a torn or unreadable file: build it again
    from devkit.reach import models
    router = rt.Router(models.read(reach), prof)
    router.__dict__.pop("_lists", None)
    if cached is not None:
        _keep_router(router, folder, stem, cached)
    return router


def _keep_router(router, folder: Path, stem: str, cached: Path) -> None:
    """Write ``router`` to ``cached`` (a temporary file, then a rename) unless another writer's mark stands, and
    remove the model and profile's older keys."""
    try:
        folder.mkdir(mode=0o700, exist_ok=True)
        folder.chmod(0o700)
        mark = cached.with_suffix(".writing")
        try:
            fd = os.open(mark, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if time.time() - mark.stat().st_mtime < WRITING_S:
                return                                     # another process writes it
            mark.unlink(missing_ok=True)
            fd = os.open(mark, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        tmp = cached.with_suffix(f".{os.getpid()}.tmp")
        try:
            with open(tmp, "wb") as f:
                pickle.dump(router, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, cached)
            for old in folder.glob(f"{stem}*.pkl"):
                if old != cached:
                    old.unlink(missing_ok=True)
        finally:
            tmp.unlink(missing_ok=True)
            mark.unlink(missing_ok=True)
    except (OSError, pickle.PicklingError, TypeError):
        pass                                               # a cache that can't be written is only slower


_SHARED: dict[tuple[str, str], object] = {}


def shared_router(reach: str, prof: str = "logic"):
    """:func:`load_router`, once per process for each reach model and profile: the factories' goals share it (a
    worker keeps a goal per target, and a router is gigabytes: town's 2.7 GB of phys_footprint each)."""
    if (reach, prof) not in _SHARED:
        _SHARED[(reach, prof)] = load_router(reach, prof)
    return _SHARED[(reach, prof)]


def router_of(reach: str, prof: str, air: int = 0):
    """The route graph a factory's goal runs on: profile ``prof``'s (:func:`shared_router`), or for ``trick`` the
    light trick graph at the kit's ``air`` level (:class:`TrickRouter`, Step X.53: certify's fallback when the
    logic's graph has no way from a leg's start), each built once per process."""
    return _trick_router(reach, air) if prof == "trick" else shared_router(reach, prof)


def make_goal(reach: str, target, *, prof: str = "logic", air: int = 0, settle: int = 10,
              dive: bool = False, touch=0.75) -> RouteGoal:
    """The factory ``l3_search.solve`` hands its workers: a :class:`RouteGoal` for ``target`` on the pickled reach
    model ``reach``'s route graph for profile ``prof`` (``trick``: the light trick graph, :func:`router_of`;
    ``settle``: the ticks at rest it must still hold;
    ``dive``: a swimming row's depth to a pickup under it counts; ``touch``: a pickup's reach in m around it, or
    its :func:`item_touch`)."""
    return RouteGoal(router_of(reach, prof, air), target, air=air, settle=settle, dive=dive, touch=touch)


def make_exit_goal(reach: str, exit_id: str, *, prof: str = "logic", air: int = 0) -> ExitGoal:
    """The factory for an exit (:class:`ExitGoal`) on the pickled reach model ``reach``'s route graph."""
    return ExitGoal(router_of(reach, prof, air), exit_id, air=air)


def exit_nodes(router, exit_id: str) -> frozenset:
    """The reach nodes the derive anchors exit ``exit_id`` to in the router's profile: the route planner's target
    for a seed string (:func:`route_seed`)."""
    return frozenset(n for n, ids in router.R.anchor[router.prof].items() if exit_id in ids)


# -- the trick explorer's guidance (Step TD.1; the trick-discovery plan §3.3) ---------------------------------------

KIT_NAMES = ("none", "air1", "air2", "air3")   # the envelope's kit per air level (flights.KITS)
JUMP_H = (1.1, 1.2)                  # a jump's height without and with air power (0x83F90, RE_MOVEMENT)
REP_M, REP_DZ = 2.0, 1.0             # [proposal] the hops' ends: one sample per 2 m column cell, 1 m of height, region
LIFT_R = 2.5                         # [proposal] a lip or rim lift lands within this (m, horizontally) of its border
HOP_R = (4.0, 7.0)                   # [proposal] a slope hop lands within this (m): without flaps, with
HOP_S = 1.0                          # [proposal] seconds a hop or lift costs over its length at walk speed
SWIM_JOIN_M = 1.5                    # [proposal] water of two swim regions this near (3-D) is joined (AZ-577)
SEG_CELL, SEG_STEP = 4.0, 1.0        # the one-sided test's grid (m) and its sampling of a path (m)
SEG_CHUNK = 2000                     # paths per vectorised block of the one-sided test (memory)


def _grid(lo, hi, cell: float):
    """A CSR grid of 3-D boxes' cells (``lo``, ``hi``: (n, 3) corners, ``cell`` m): (origin, (ny, nz), keys, start,
    item): the items in cell key ``(ix * ny + iy) * nz + iz`` are ``item[start[j]:start[j + 1]]``, ``keys[j]`` it."""
    blo, bhi = np.floor(lo / cell).astype(np.int64), np.floor(hi / cell).astype(np.int64)
    o = blo.min(axis=0) if len(blo) else np.zeros(3, np.int64)
    blo, bhi = blo - o, bhi - o
    ny, nz = (int(bhi[:, 1].max()) + 1, int(bhi[:, 2].max()) + 1) if len(bhi) else (1, 1)
    span = bhi - blo + 1
    count = span[:, 0] * span[:, 1] * span[:, 2]
    item = np.repeat(np.arange(len(lo)), count)
    k = np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
    sy, sz = np.repeat(span[:, 1], count), np.repeat(span[:, 2], count)
    ix = np.repeat(blo[:, 0], count) + k // (sy * sz)
    iy = np.repeat(blo[:, 1], count) + (k // sz) % sy
    iz = np.repeat(blo[:, 2], count) + k % sz
    key = (ix * ny + iy) * nz + iz
    order = np.argsort(key, kind="stable")
    keys, start = np.unique(key[order], return_index=True)
    return o, (ny, nz), keys, np.append(start, len(order)), item[order]


class OneSided:
    """A reach model's solid faces there at load, for :meth:`blocked`: a face stops a body only moving into its
    front (0xB9FA5, RE_MOVEMENT "The contact rules"), so a path that crosses faces only from behind passes; with
    ``both``, a face crossed from either side blocks (the site miner's open-air tests, ``draft.sites``)."""

    def __init__(self, reach, both: bool = False):
        self.both = both
        lv = reach.lv
        idx = np.nonzero(np.isin(lv.tri_cat, SOLID_CATS) & reach.present[lv.tri_owner])[0]
        P = lv.P[idx].astype(np.float64)
        self.a, self.e1, self.e2 = P[:, 0], P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]
        self.n = np.cross(self.e1, self.e2)                  # the front (floors up), unnormalised
        self.o, (self.ny, self.nz), self.keys, self.start, self.tri = _grid(P.min(axis=1), P.max(axis=1), SEG_CELL)

    def blocked(self, A, B) -> np.ndarray:
        """Per segment ``A[i]`` -> ``B[i]`` ((m, 3) each): whether it crosses a face into its front."""
        A, B = np.asarray(A, dtype=np.float64), np.asarray(B, dtype=np.float64)
        out = np.zeros(len(A), dtype=bool)
        for c0 in range(0, len(A), SEG_CHUNK):
            out[c0:c0 + SEG_CHUNK] = self._blocked(A[c0:c0 + SEG_CHUNK], B[c0:c0 + SEG_CHUNK])
        return out

    def _blocked(self, A, B):
        m = len(A)
        L = np.linalg.norm(B - A, axis=1)
        ns = np.clip(np.ceil(L / SEG_STEP).astype(np.int64) + 1, 2, 4096)
        seg = np.repeat(np.arange(m), ns)
        t = (np.arange(ns.sum()) - np.repeat(np.cumsum(ns) - ns, ns)) / np.repeat(ns - 1, ns)
        c = np.floor((A[seg] + (B[seg] - A[seg]) * t[:, None]) / SEG_CELL).astype(np.int64) - self.o
        ok = (c >= 0).all(axis=1) & (c[:, 1] < self.ny) & (c[:, 2] < self.nz)
        key = np.unique(seg[ok] * (1 << 40) + (c[ok, 0] * self.ny + c[ok, 1]) * self.nz + c[ok, 2])
        seg, key = key >> 40, key & ((1 << 40) - 1)
        j = np.searchsorted(self.keys, key)
        hit = (j < len(self.keys)) & (self.keys[np.minimum(j, len(self.keys) - 1)] == key)
        seg, j = seg[hit], j[hit]
        cnt = self.start[j + 1] - self.start[j]
        ps = np.repeat(seg, cnt)
        pt = self.tri[np.repeat(self.start[j], cnt) + np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)]
        u = np.unique(ps * (1 << 32) + pt)
        ps, pt = u >> 32, u & ((1 << 32) - 1)
        out = np.zeros(m, dtype=bool)
        if not len(ps):
            return out
        D = B[ps] - A[ps]
        front = np.einsum("ij,ij->i", D, self.n[pt]) < 0      # only a face met from its front can stop the body
        front |= self.both
        ps, pt, D = ps[front], pt[front], D[front]
        e1, e2 = self.e1[pt], self.e2[pt]
        h = np.cross(D, e2)
        det = np.einsum("ij,ij->i", e1, h)
        good = np.abs(det) > 1e-12
        f = 1.0 / np.where(good, det, 1.0)
        s_ = A[ps] - self.a[pt]
        uu = f * np.einsum("ij,ij->i", s_, h)
        q = np.cross(s_, e1)
        vv = f * np.einsum("ij,ij->i", D, q)
        tt = f * np.einsum("ij,ij->i", e2, q)
        cross = good & (uu >= 0) & (uu <= 1) & (vv >= 0) & (uu + vv <= 1) & (tt > 1e-6) & (tt < 1 - 1e-6)
        np.logical_or.at(out, ps[cross], True)
        return out


def named_skip(e) -> bool:
    """Whether a reach edge comes of a ``tricks.toml`` skip: a confirmed skip's atom, a barrier bypass (its held
    generated atom ranked against the confirmed ones) or a hand current crossing named for a skip."""
    return bool(e.get("skip_atom") or e.get("trick") == "bskip" or (e.get("current") or {}).get("skip"))


def jump_doubt(dz, nz, slip, against, *, h: float, flaps: float, apex: float, lift=None) -> np.ndarray:
    """Why the game's jump can't make a hop rising ``dz`` m from a face of normal z ``nz`` (``slip``: slippery;
    ``against``: it lands behind the face's normal, horizontally), per hop (Step X.53, the light trick graph's
    doubts): 1 past the rise the jump gives (0x89060: a slippery face, or one of nz <= 0.7071, takes the normal
    branch, 0x8917F-0x891D6, the compare at 0x8918B against 0.7071 at 0x198598, and rises ``h`` nz^2 plus the kit's
    ``flaps``; any other face the kit's ``apex``) plus ``lift``'s (a lift's step-up onto the ledge; None for a slope
    hop), 2 a normal-branch jump landing against the face's normal, else 0."""
    normal = np.asarray(slip, dtype=bool) | (np.asarray(nz) <= WALK_GAME_NZ)
    rise = np.where(normal, h * np.asarray(nz, dtype=np.float64) ** 2 + flaps, apex) + (0.0 if lift is None else lift)
    return np.where(np.asarray(dz) > rise + 1e-9, 1, np.where(normal & np.asarray(against, dtype=bool), 2, 0)).astype(
        np.int8)


class TrickRouter(rt.Router):
    """The light trick graph (Step TD.1, guidance only): the phys profile's route graph (every landable face, its
    flights by the envelope alone) for the kit's ``air`` level, its walks costed by the game's own walk
    (``floors.walk_game``: onto a face the game doesn't walk, ``PHYS_ONLY`` times more, and no walk climbs onto a
    face of nz <= 0.7071 or a slippery one under ``SLIP_FLAT_NZ``), each flight rechecked one-sided
    (:meth:`_recheck`), plus two edge families: slope hops (from a slope or slippery floor, the jump along its
    normal, a rise of h nz^2 plus what the kit's flaps add, onto any floor up to ``HOP_R`` away) and lip and rim
    lifts (from a floor's border onto a ledge up to the kit's apex plus the rim step-up ``RIM_LIFT`` higher, within
    ``LIFT_R``), and swim links between water of two swim regions within :data:`SWIM_JOIN_M` (AZ-577; the
    explorer's own presses dive).  An edge the game may not make is doubted, not dropped (Step X.53, AZ-591): it
    costs :data:`DOUBT_S` more and ``doubt`` (edge index -> why) names it in a stall: a flight every path of which
    crosses a solid face into its front (``blocked``) or that only paths crossing faces from behind keep while its
    body band doesn't clear (``one-sided``), a hop or lift past the rise the game's jump gives from its takeoff
    face (``past the jump's rise``, :meth:`_hops`), a slope hop against its takeoff face's normal (``against the
    takeoff's normal``), a ride of a rig the level's authoring holds (``held rig``: the plain router bans them)
    and a teleport whose other pads must be touched first (``pads first``: the explorer's start may not have them;
    Step X.53, AZ-592).  Under the blind protocol (the trick-discovery plan §4) it keeps no edge a
    ``tricks.toml`` skip made or ranked (:func:`named_skip`).  Every edge is optimistic; launches and descents are
    not modelled (the explorer's local search covers them).  Coordinates stay in memory."""

    WHY = {1: "blocked", 2: "one-sided"}
    HOP_WHY = {1: "past the jump's rise", 2: "against the takeoff's normal"}
    BAN_HELD = False          # the authoring's held rigs' rides are doubted here, not banned (``held rig``)

    def __init__(self, reach, air: int = 0):
        self.game, self.air = guidance_walk(reach), int(air)
        super().__init__(reach, "phys")
        self.__dict__.pop("_lists", None)            # the planner's lists (a cost field needs only the arrays)
        self.doubt: dict[int, str] = {}

        def links(pred):
            return (self.kind == rt.K_EDGE) & np.isin(self.eid, [k for k, (_, _, e) in enumerate(self.edges)
                                                                 if pred(e)])
        drop = links(named_skip)                      # the blind protocol: no edge a tricks.toml skip made or ranked
        extra = np.zeros(len(self.src))
        for k in self.held.tolist():                  # a rig the authoring holds: undecoded or gated, doubted (X.53)
            self.doubt[k] = "held rig"
        for k in self.pads:                           # a teleport that fires only once other pads were touched
            if self.edges[k][2].get("flags"):
                self.doubt[k] = "pads first"
        extra[(self.kind == rt.K_EDGE) & np.isin(self.eid, [k for k, y in self.doubt.items()
                                                             if y in ("held rig", "pads first")])] = DOUBT_S
        q = np.nonzero(links(lambda e: e["kind"] in rt.FLIGHT_KINDS) & ~drop)[0]
        if len(q):
            why = self._recheck(self.src[q], self.dst[q])
            for k, y in zip(self.eid[q[why > 0]].tolist(), why[why > 0].tolist()):
                self.doubt[k] = self.WHY[y]
            extra[q[why > 0]] = DOUBT_S
        hs, hd, hk, hw = self._hops()
        e0 = len(self.edges)
        self.edges += [(int(self.node[u]), int(self.node[v]), {
            "kind": "jump", "conf": "geometry", "ranks": [0, 0, 0, 0], "trick": ("slope-hop", "lift")[k],
            "profile": "sample to sample (the light trick graph)"}) for u, v, k in zip(hs.tolist(), hd.tolist(),
                                                                                      hk.tolist())]
        for i in np.nonzero(hw)[0].tolist():
            self.doubt[e0 + i] = self.HOP_WHY[int(hw[i])]
        ws, wd, wc = self._joins()
        keep = ~drop
        d = np.sqrt((self.X[hs] - self.X[hd]) ** 2 + (self.Y[hs] - self.Y[hd]) ** 2)
        src, dst = np.r_[self.src[keep], hs, ws], np.r_[self.dst[keep], hd, wd]
        kind = np.r_[self.kind[keep], np.full(len(hs), rt.K_EDGE, dtype=np.int8), np.full(len(ws), rt.K_SWIM,
                                                                                         dtype=np.int8)]
        eid = np.r_[self.eid[keep], e0 + np.arange(len(hs)), np.full(len(ws), -1, dtype=np.int64)]
        cost = np.r_[self.cost[keep] + extra[keep], d / rt.WALK_MPS + HOP_S + np.where(hw > 0, DOUBT_S, 0.0), wc]
        o = np.argsort(src, kind="stable")
        self.src, self.dst, self.kind, self.eid, self.cost = src[o], dst[o], kind[o], eid[o], cost[o]
        self.indptr = np.searchsorted(self.src, np.arange(self.V + 1))

    def _no_walk_up(self, top):
        lv = self.R.lv
        slip = (lv.tri_word[top] & collision.W_SLIPPERY) != 0
        return (slip & (lv.tri_nz[top] < SLIP_FLAT_NZ)) | (~slip & (lv.tri_nz[top] <= WALK_GAME_NZ))

    def _walk_ref(self):
        return self.game

    def _recheck(self, u, v) -> np.ndarray:
        """Per flight u -> v (vertices): 0 kept, 1 every path :meth:`_crosses` tries crosses a solid face into its
        front (``blocked``), 2 kept only by paths that cross faces from behind (every path crosses a face two-sided)
        while the body band (the paths moved ``flights.SIDE_M`` to each side, at the band ``SIDE_BAND`` over the
        feet) doesn't clear one-sided too (``one-sided``).  A flight whose ends lie under half a cell apart across
        (a drop straight down off a floor's edge: every path crosses the takeoff's own floor) is kept untested:
        1,929 of e2's 2,373 such drops were dropped, #7812 (the only way into e2.Z005) among them (Step X.53)."""
        out = np.zeros(len(u), dtype=np.int8)
        k = np.nonzero(np.hypot(self.X[v] - self.X[u], self.Y[v] - self.Y[u]) >= CELL / 2)[0]
        if not len(k):
            return out
        A = np.c_[self.X[u[k]], self.Y[u[k]], self.Z[u[k]] + 1.0]
        C = np.c_[self.X[v[k]], self.Y[v[k]], self.Z[v[k]] + 1.0]
        test = OneSided(self.R)
        blocked = self._crosses(A, C, test)
        out[k[blocked]] = 1
        r = np.nonzero(~blocked)[0]
        if len(r):
            test.both = True
            r = r[self._crosses(A[r], C[r], test)]       # every path crosses a face (from either side)
            test.both = False
        if len(r):
            dxy = C[r, :2] - A[r, :2]
            side = np.c_[-dxy[:, 1], dxy[:, 0]] / np.hypot(dxy[:, 0], dxy[:, 1])[:, None]
            band = np.zeros(len(r), dtype=bool)
            for sgn in (-1.0, 1.0):
                for h in SIDE_BAND:
                    off = np.c_[sgn * SIDE_M * side, np.full(len(r), h - 1.0)]
                    band |= self._crosses(A[r] + off, C[r] + off, test)
            out[k[r[band]]] = 2
        return out

    @staticmethod
    def _crosses(A, C, test) -> np.ndarray:
        """Whether every path tried from body centre ``A`` to ``C`` ((m, 3) each) crosses a solid face into its
        front by ``test`` (:class:`OneSided`; one clear path keeps the flight: optimistic): rising over the takeoff
        to 0.3 m over the higher end, across and down (a box), over an arch 1.2 m or 0.5 m over the higher end,
        rising over the takeoff to 0.3 m over the landing then across or across at the takeoff's height then down
        (by the ends' heights), or on the straight line.  On f6's logic flights the derive's two-sided sweep clears
        it drops 129 of 8,916 [measured, Step TD.1's review; one path alone, 425]."""
        dz, top, mid = C[:, 2] - A[:, 2], np.maximum(A[:, 2], C[:, 2]), (A[:, :2] + C[:, :2]) / 2
        bend = np.where((dz > 0.3)[:, None], np.c_[A[:, :2], C[:, 2] + 0.3],
                        np.where((dz < -0.3)[:, None], np.c_[C[:, :2], A[:, 2]], np.c_[mid, top + 0.5]))
        out = np.ones(len(A), dtype=bool)
        for via in ((np.c_[A[:, :2], top + 0.3], np.c_[C[:, :2], top + 0.3]), (np.c_[mid, top + 1.2],),
                    (np.c_[mid, top + 0.5],), (bend,), ()):
            k = np.nonzero(out)[0]
            if not len(k):
                break
            pts = [A[k], *(m[k] for m in via), C[k]]
            out[k] = np.any([test.blocked(P, Q) for P, Q in zip(pts, pts[1:])], axis=0)
        return out

    def _hops(self):
        """(takeoff, landing, family, doubt) vertex arrays of the slope hops (family 0) and the lip and rim lifts
        (1) between representative samples (:data:`REP_M`, :data:`REP_DZ`, per region).  ``doubt`` (Step X.53): 1
        where the rise passes what the game's jump gives from the takeoff face (0x89060: a slippery face, or one of
        nz <= 0.7071, takes the normal branch at 0x8917F-0x891D6, the compare at 0x8918B against 0.7071 at
        0x198598, a rise of h nz^2 plus the kit's flaps; any other face the kit's apex) plus, for a lift, the
        measured lip lift (``RIM_STEP_LIFT``, 0.4987 m) or the rim step-up (``RIM_LIFT``) where ``flights._rim``
        finds a sloped rim before the landing; 2 where a slope hop lands against its face's normal (behind it,
        horizontally); else 0.  Candidates still run to the apex plus ``RIM_LIFT``."""
        w, lv, ns = self.w, self.R.lv, self.ns
        js = np.nonzero(w.reg_soft >= 0)[0]
        key = np.stack([np.floor(w.x[js] / REP_M), np.floor(w.y[js] / REP_M), np.floor(w.z[js] / REP_DZ),
                        w.reg_soft[js]], 1).astype(np.int64)
        _, first = np.unique(key, axis=0, return_index=True)
        rep = js[np.sort(first)]
        top = self.R.spans.toptri[w.sidx[rep]]
        nz = lv.tri_nz[top].astype(np.float64)
        slip = (lv.tri_word[top] & collision.W_SLIPPERY) != 0
        slope = (nz <= WALK_GAME_NZ) | (slip & (nz < SLIP_FLAT_NZ))
        P = lv.P[top].astype(np.float64)
        nxy = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])[:, :2]
        apex = float(self.R.env.apex[("phys", KIT_NAMES[min(max(self.air, 0), 3)])])
        h = JUMP_H[self.air >= 1]
        flaps = max(0.0, apex - float(self.R.env.apex[("phys", "air_power" if self.air >= 1 else "none")]))
        xy = np.c_[w.x[rep], w.y[rep]].astype(np.float64)
        out = []
        for fam, take, r in ((0, np.nonzero(slope)[0], HOP_R[self.air >= 1]),
                             (1, np.nonzero(self.clear[rep] == 0)[0], LIFT_R)):
            if not len(take):
                continue
            qi, pj, _ = RadiusIndex(xy, r).pairs(xy[take])
            qi = take[qi]
            dz = w.z[rep[pj]] - w.z[rep[qi]]
            rise = h * nz[qi] ** 2 + flaps if fam == 0 else apex + RIM_LIFT
            low = 0.05 if fam == 0 else self.climb
            ok = (dz > low) & (dz <= rise) & (w.reg_soft[rep[pj]] >= 0) & (pj != qi)
            qi, pj, dz = qi[ok], pj[ok], dz[ok]
            against = (((xy[pj] - xy[qi]) * nxy[qi]).sum(axis=1) < 0) & (fam == 0)    # a slope hop's only
            lift = None
            if fam:                                    # the rim step-up where a sloped rim stands before the ledge
                lift = np.full(len(qi), RIM_STEP_LIFT)
                band = (jump_doubt(dz, nz[qi], slip[qi], against, h=h, flaps=flaps, apex=apex, lift=lift) == 1) & (
                    jump_doubt(dz, nz[qi], slip[qi], against, h=h, flaps=flaps, apex=apex, lift=RIM_LIFT) != 1)
                lift[self._rim_lifts(rep[qi], rep[pj], band)] = RIM_LIFT
            why = jump_doubt(dz, nz[qi], slip[qi], against, h=h, flaps=flaps, apex=apex, lift=lift)
            out.append((rep[qi], rep[pj], np.full(len(qi), fam, dtype=np.int64), why))
        if not out:
            z = np.zeros(0, dtype=np.int64)
            return z, z, z, np.zeros(0, dtype=np.int8)
        return tuple(np.concatenate(x) for x in zip(*out))

    def _rim_lifts(self, a, b, m) -> np.ndarray:
        """Per lift sample ``a`` -> ``b`` where ``m``: whether ``flights._rim`` finds a sloped rim before the landing
        (the rim step-up, ``RIM_LIFT``), so the lift may land that far under the ledge's top."""
        out = np.zeros(len(a), dtype=bool)
        w = self.w
        i = np.nonzero(m & (np.hypot(w.x[b] - w.x[a], w.y[b] - w.y[a]) >= CELL / 2))[0]
        if not len(i):
            return out
        xa, ya, za = (np.asarray(x[a[i]], dtype=np.float64) for x in (w.x, w.y, w.z))
        xb, yb, zb = (np.asarray(x[b[i]], dtype=np.float64) for x in (w.x, w.y, w.z))
        d = np.hypot(xb - xa, yb - ya)
        s0, s1 = _track_edges(self.R.lv, w, xa, ya, za, xb, yb, zb, d, self.climb)
        out[i] = _rim(self.R.lv, self.R.spans, xa, ya, za, xb, yb, zb, d, s0, s1, self.climb) >= RIM_LIFT
        return out

    def _joins(self):
        """(source, destination, cost) of swim links both ways between water vertices of two swim regions within
        :data:`SWIM_JOIN_M` (3-D) of each other, from each region's border nodes (AZ-577: w1's bay lies 1.4 m from
        w1.Z216's water with no swim edge between them)."""
        wg, ns = self.wg, self.ns
        z = np.zeros(0, dtype=np.int64)
        if not len(wg.col):
            return z, z, np.zeros(0)
        ia, ib = wg.links
        deg = np.bincount(np.r_[ia, ib], minlength=len(wg.col))
        n = np.nonzero((wg.lab >= 0) & (deg < deg.max()))[0] if len(ia) else np.nonzero(wg.lab >= 0)[0]
        if not len(n):
            return z, z, np.zeros(0)
        xy = np.c_[self.X[ns + n], self.Y[ns + n]]
        qi, pj, dxy = RadiusIndex(xy, SWIM_JOIN_M).pairs(xy)
        d = np.sqrt(dxy ** 2 + (self.Z[ns + n[qi]] - self.Z[ns + n[pj]]) ** 2)
        ok = (wg.lab[n[qi]] != wg.lab[n[pj]]) & (d <= SWIM_JOIN_M)
        return ns + n[qi[ok]], ns + n[pj[ok]], d[ok] / rt.SWIM_MPS


class _Explore:
    """What the explorer asks every guide: the zone (None outside every zone: a body on a floor or swimming is in
    the zone of the logic floor its feet are on, ``Router.locate``'s 1.0 m under to 0.5 m over, or of the water
    holding it, never of a floor under a top it stands on; one off the floor, :data:`OFF_FLOOR`, in the zone under
    it), the phys floor region the feet are on (a pseudo-region's match), the height of the column's highest
    logic floor and the level's collision (``level``: the explorer looks up the face each row touches, Step TD.4).
    With mined sites (the factories' ``sites``) also ``site_prior`` (``draft.sites.Prior``).  Its moves cast
    nothing, so as a route goal's mixin it asks no cast (:attr:`RouteGoal.casts`)."""
    casts = False

    @property
    def level(self):
        return self._reach.lv

    def _feet(self, row):
        return row.pos[0], row.pos[1], row.pos[2] - 1.0

    def zone(self, row) -> str | None:
        return self._loc.zone_at(self._feet(row), prefer_water=row.state == SWIMMING, fallback=row.state in OFF_FLOOR)

    def region(self, row) -> int | None:
        w = self._reach.W["phys"]
        v = self._loc.locate(self._feet(row), False, w, fallback=False)
        return int(w.reg_soft[v]) if 0 <= v < len(w.col) and w.reg_soft[v] >= 0 else None

    def column_top(self, row) -> float | None:
        lw = self._reach.W["logic"]
        a, c = lookup(lw.u, lw.a, lw.c, np.array([int(self._reach.lv.col(row.pos[0], row.pos[1]))]))
        return float(lw.z[int(a[0]):int(a[0]) + int(c[0])].max()) if c[0] else None


class _Locator:
    """What ``Router.locate`` and ``Router.zone_at`` read of a router, from a reach model alone (no route graph)."""

    locate = rt.Router.locate
    zone_at = rt.Router.zone_at

    def __init__(self, reach):
        self.R, self.lv, self.wg, self.w = reach, reach.lv, reach.wg, reach.W["phys"]


class ZoneGuide(_Explore):
    """A discovery problem's guide (Step TD.1): no target, no cost; the zone, the region and the column top of a
    reach model, without building a route graph."""

    def __init__(self, reach):
        self._reach, self._loc = reach, _Locator(reach)


class TrickGoal(_Explore, RouteGoal):
    """A target problem's guide (Step TD.1): :class:`RouteGoal`'s goal test, cost to go and guidance over the light
    trick graph (:class:`TrickRouter`), and the explorer's zone (so a zone goal is met on its own floor, not above
    it), region and column top."""

    def __init__(self, router: TrickRouter, target, **kw):
        RouteGoal.__init__(self, router, target, air=router.air, **kw)
        self._reach, self._loc = router.R, router


class TrickExitGoal(_Explore, ExitGoal):
    """A level exit's trigger on the light trick graph (Step TD.4b; the plan §4's P1): :class:`ExitGoal`'s goal
    test (the body centre inside one of its meshes, in any state) and cost field over :class:`TrickRouter`, with
    the explorer's zone, region and column top, and a cost from out of bounds: for a row outside every zone (a top
    no logic floor is under, the void over the sea) the least of the graph's cost and a direct one to the nearest
    mesh, its horizontal distance at walk speed plus the height still to rise to its bottom at :data:`RISE_MPS` (a
    fall into it costs nothing: optimistic), so such a row is pulled toward the trigger rather than back toward
    the floors (the straight-line fallback, X.12's failure); its guidance then heads for that point."""

    def __init__(self, router: TrickRouter, exit_id: str, **kw):
        ExitGoal.__init__(self, router, exit_id, air=router.air, **kw)
        self._reach, self._loc = router.R, router

    def _direct(self, row) -> tuple[float, tuple]:
        p = np.asarray(row.pos, dtype=float)
        best, at = math.inf, None
        for _, lo, hi in self._meshes:
            q = np.clip(p, lo, hi)
            c = math.hypot(*(q[:2] - p[:2])) / rt.WALK_MPS + max(0.0, lo[2] - p[2]) / RISE_MPS
            if c < best:
                best, at = c, tuple(q)
        return best, at

    def cost(self, row) -> float:
        c = RouteGoal.cost(self, row)
        return c if self.zone(row) is not None else min(c, self._direct(row)[0])

    def toward(self, row):
        if self.zone(row) is None:
            d, at = self._direct(row)
            if d < RouteGoal.cost(self, row):
                return heading_to((row.pos[0], row.pos[1], row.pos[2] - 1.0), at), False
        return RouteGoal.toward(self, row)


RISE_MPS = 1.0           # [proposal] a trick exit goal's rise to a trigger from out of bounds (a climb's pace, m/s)
_REACH: dict[str, object] = {}
_SITES: dict[tuple, object] = {}


def _reach_model(reach: str):
    if reach not in _REACH:
        from devkit.reach import models
        _REACH[reach] = models.read(reach)
    return _REACH[reach]


def _with_sites(guide, reach: str, air: int, sites: bool):
    """With ``sites``, the guide's ``site_prior`` over the reach model's mined sites at ``air`` (once per process)."""
    if sites:
        from devkit.rando.draft import sites as S
        if (reach, air) not in _SITES:
            r = _reach_model(reach)
            _SITES[(reach, air)] = S.mine(r.lv, reach=r, kit=air)
        guide.site_prior = S.Prior(_SITES[(reach, air)])
    return guide


def make_zone_guide(reach: str, *, air: int = 0, sites: bool = False) -> ZoneGuide:
    """The factory for a discovery problem's guide (:class:`ZoneGuide`) on the pickled reach model ``reach``;
    ``sites``: with the site prior (mined at the kit's ``air`` level)."""
    return _with_sites(ZoneGuide(_reach_model(reach)), reach, air, sites)


def _trick_router(reach: str, air: int) -> TrickRouter:
    if (reach, f"trick{air}") not in _SHARED:
        _SHARED[(reach, f"trick{air}")] = TrickRouter(_reach_model(reach), air)
    return _SHARED[(reach, f"trick{air}")]


def make_trick_goal(reach: str, target, *, air: int = 0, settle: int = 10, touch=0.75,
                    sites: bool = False) -> TrickGoal:
    """The factory for a target problem's guide (:class:`TrickGoal`): ``target`` (a zone, zones, a node or a
    location, as :class:`RouteGoal` takes it; ``touch`` a pickup's reach or its :func:`item_touch`) on the light
    trick graph of the pickled reach model ``reach`` for the kit's ``air`` level, built once per process;
    ``sites``: with the site prior."""
    return _with_sites(TrickGoal(_trick_router(reach, air), target, settle=settle, touch=touch), reach, air, sites)


def make_trick_exit_goal(reach: str, exit_id: str, *, air: int = 0, sites: bool = False) -> TrickExitGoal:
    """The factory for an exit's trigger on the light trick graph (:class:`TrickExitGoal`)."""
    return _with_sites(TrickExitGoal(_trick_router(reach, air), exit_id), reach, air, sites)
