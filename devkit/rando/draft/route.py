"""Routes over the reach model, for the xemu pilot (Step X.2).

A route from a point to a target in one level, at a difficulty tier and an
air level: A* over the reach model's own graph at the sample level.  Its
vertices are a profile's walk samples (:class:`~.floors.Walk`) and the swim
water's nodes (:class:`~.moves.WaterGrid`); its links are the walk's own
sample links (an eroded sample joins the 4-neighbours it adopts its region
from, at a cost), the water's own node links, the steps between land and
water that :func:`~.moves.swim_edges` finds, and every other region edge at
its witness (a flight's takeoff and landing samples) or, for an edge with
none (a slide, a climb, a gate, a door, a ride), at the closest pair of
the two regions' vertices; a teleport from the source's vertex nearest
its pad to the destination's nearest its spot (Step X.53).
:meth:`Reach.usable` decides which region edges a plan may take (the
tier, the air level, the admitted probe classes, the gates), less the
rides of the rigs the level's authoring holds (``[rig_held]``, Step X.53).
Updrafts and currents are not followed.

The path becomes legs, one action each: ``walk`` and ``swim`` (way-points;
the straight line between two is walkable or swimmable), ``jump`` (a jump
or a step: press jump at ``at``), ``flap`` (a jump that flaps), ``drop``
(walk off at ``at``), ``climb``, ``wait`` (stand on a ride) and
``teleport`` (walk into its pad, then on from where it puts you).  Walk
costs grow near a floor's border, so routes keep to the middle of stairs
and bridges.  Way-points are feet heights on land and the surface in water.
A jump onto a ledge within LIP_FROM_M of the kit's apex or above it is a
lip lift (Step X.4): its ``lip`` says so, and ``at`` stands in the tier's
takeoff window before the face (the run is at full speed).  A flight that
lands on a sloped face or a floor's border costs more (sitting x2: the
body slid off a hump, and died after drops onto ledges under 0.5 m wide).
Rides are lifts (the derive guesses none on machinery: AZ-353), and a
decoded ride's leg says what starts it.  Walking into a level exit's or
a camera's trigger costs EXIT_S unless the target is there.

Also the pilot's pad (Step X.4): :func:`stick`, the camera-relative
analog stick a real pad's round gate allows, and :func:`air_target`, the
air-control target that carries a body to a landing.

Dev tooling for ``scripts/xemu_route.py`` (the pilot); the randomizer's
planner and writer never import it.  Coordinates stay in memory.
"""

from __future__ import annotations

import heapq
import math
import re
import tomllib
from dataclasses import dataclass, field

import numpy as np

from azurkit.tools.randomizer.draft import envelope
from azurkit.tools.randomizer.draft.floors import PROFILES, lookup
from devkit.rando.draft.flights import _TIER, _plain_ledge, _track_edges
from devkit.rando.draft.gates import probe_class
from azurkit.tools.randomizer.draft.geometry import CAT_TRIGGER, CELL, raster
from devkit.rando.draft.moves import swim_edges
from azurkit.tools.randomizer.art import collision

WALK_MPS, SWIM_MPS = envelope.V_RUN, envelope.SWIM["target_mps"]   # [verified xemu s6] full-stick walk; the swim stroke's target
FLIGHT_KINDS = {"jump": "jump", "step": "jump", "flap": "flap", "drop": "drop"}
BORDER_KINDS = {"slide": "walk", "climb": "climb", "gate": "walk", "door": "walk", "rig": "wait"}
# link kinds
K_WALK, K_SOFT, K_SWIM, K_SHORE, K_EDGE = range(5)
CROSS = -2                               # a walk link across a slippery boundary (Walk.xlinks): `slip`
EDGE_S = {"jump": 1.0, "step": 0.8, "flap": 2.5, "drop": 0.6, "slide": 2.0, "climb": 4.0, "gate": 1.0,
          "door": 2.0, "rig": 15.0}      # [proposal] seconds a region edge costs on top of its length at walk speed
PROBE_S = 6.0                            # [proposal] extra seconds for a probe-needed edge
AVOID_S = 30.0                           # [proposal] extra seconds to enter a vertex where a walk stuck
TELEPORT_S = 1.0                         # [proposal] seconds a teleport costs on top of the walk into its pad
EXIT_S = 120.0                           # [proposal] extra seconds to step into a level exit's trigger or a camera
                                         # trigger (x4: f6's exit camera field walked the player away, the stick
                                         # ignored, 95 ticks; w2's LevelCameraTrigger02 held it 150 ticks and more)
SEIZE_NAMES = ("exit", "camera", "camfield")   # [proposal] trigger volumes named so take the player over
PHYS_ONLY = 4.0                          # [proposal] the cost factor of walking a floor only R_phys stands on
SLIP_UP_M = 0.02                         # [proposal] a walk link climbing more than this onto a slippery floor is out
SHORE_IN_S, SHORE_OUT_S = 0.5, 1.0       # [proposal] into and out of the water
NEAR_BORDER = (3.0, 1.5, 1.0)            # [proposal] walk cost factor by clearance 0 (border), 1, 2
RUNUP_M = (1.5, 0.75)                    # a run-up way-point this far behind a jump's takeoff, where the floor allows
SEG_MAX_M = 12.0                         # the longest straight way-point segment
STEP = CELL / 2                          # the line test's step
LIP_FROM_M = 0.15                        # [proposal] a jump onto a ledge above the kit's apex less this is a lip lift
WIDEN_RISE_M = 0.1                       # [proposal] a widened flight witness keeps its rise within this (Step X.53)
LIP_WANT_MAX_M = 2.4                     # [proposal] the takeoff stands at the window's middle, at most this far out
LAND_FLAT_NZ, LAND_SLOPE_S = 0.95, 3.0   # [proposal] seconds more for a flight landing on a face under this nz (x2)
LAND_EDGE_S = (3.0, 1.0, 0.0)            # [proposal] seconds more for a flight landing on clearance 0 (a border), 1, 2:
                                         # x2's 16 m drops onto ledges under 0.5 m wide died
# The pad's geometry (the round gate, the dead zone, the axis snap) is devkit.sim.inputs (Step X.7).
AIR_F = 0.6 ** (1 / 30)                  # the air blend a tick: v := T + (v - T) 0.6^dt (envelope)
G_TICK = 9.8 / 30                        # [verified xemu s6] vz falls 0.326667 a tick, then z += vz / 30


def wrap(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def fall_ticks(vz: float, dz: float, cap: int = 600) -> int:
    """Ticks until a body ``dz`` m above a landing height, rising at
    ``vz``, comes down to it (vz -= G_TICK, then z += vz / 30, a tick: the
    measured jump's 28 airborne ticks and 1.0235 m apex); 0 if it never
    does (below it and not rising above it)."""
    for k in range(1, cap + 1):
        vz -= G_TICK
        was, dz = dz, dz + vz / 30
        if dz <= 0 < was:
            return k
    return 0


def air_target(dx: float, dy: float, vx: float, vy: float, n: float) -> tuple:
    """The constant air-control target (m/s, world x/y) that carries a
    body from horizontal velocity (vx, vy) over (dx, dy) m in ``n`` ticks
    under the air blend: v_k = T + (v - T) f^k, so the travel is
    T (n/30 - g) + v g with g = f (1 - f^n) / (1 - f) / 30.  The stick is
    the target over the air control (+0x140)."""
    if n <= 0:
        return 0.0, 0.0
    g = AIR_F * (1 - AIR_F ** n) / (1 - AIR_F) / 30.0
    den = n / 30.0 - g
    return (dx - vx * g) / den, (dy - vy * g) / den


@dataclass
class Leg:
    """One action of a route: ``pts`` its way-points (the last ends it),
    ``at`` where a jump is pressed or a drop walks off, ``kind`` and
    ``conf`` the reach edge's (``walk`` / ``swim`` inside regions),
    ``node`` the reach node the leg ends in, ``clear`` the least walk
    clearance along it (0 border, 1, 2); ``lip`` for a lip lift: the
    deficit above the kit's apex, the tier's takeoff window before the
    blocked spot (face less the body radius), how far before it ``at``
    stands and how far the takeoff floor runs on past ``at`` (m);
    ``trigger`` for a ride: what starts it (:meth:`Router.trigger`)."""
    action: str
    pts: list
    at: tuple | None = None
    kind: str = "walk"
    conf: str = "geometry"
    node: int = -1
    clear: int = 2
    eid: int = -1
    src: int = -1
    edge: dict | None = field(default=None, repr=False)
    lip: dict | None = None
    trigger: list | None = None

    def summary(self) -> dict:
        """The leg without coordinates: action, kind, confidence, length (m)."""
        p = list(self.pts)
        if self.at is not None:
            p = [self.at] + p
        n = sum(math.dist(a, b) for a, b in zip(p, p[1:]))
        return {"action": self.action, "kind": self.kind, "conf": self.conf, "node": self.node,
                "pts": len(self.pts), "m": round(n, 1), **({"lip": self.lip} if self.lip else {}),
                **({"via": self.edge.get("via"), "trigger": [t["pad"] for t in self.trigger or ()]}
                   if self.action == "wait" and self.edge else {})}


@dataclass
class Route:
    """A plan: its legs, whether its end meets the target (``reached``),
    the end's distance to the target point (m; None for a zone), its cost
    (s), the vertices and links it takes."""
    legs: list
    reached: bool
    left_m: float | None
    cost_s: float
    verts: list
    links: list

    def summary(self) -> list:
        return [leg.summary() for leg in self.legs]


class Router:
    """A level's route graph (the module docstring) for one profile of a
    built :class:`~.reach.Reach`; :meth:`plan` routes on it."""

    BAN_HELD = True          # the authoring's held rigs' rides are out of the graph (the light trick graph doubts them)

    def __init__(self, reach, prof: str = "logic"):
        R = self.R = reach
        self.prof, self.lv = prof, R.lv
        w, wg = self.w, self.wg = R.W[prof], R.wg
        self.climb = PROFILES[prof]["climb"]
        self.tiers = PROFILES[prof]["tiers"]
        ns, nw = len(w.col), len(wg.col)
        self.ns, self.V = ns, ns + nw
        wx, wy = R.lv.cxy(wg.col) if nw else (np.zeros(0), np.zeros(0))
        self.X = np.concatenate((w.x, wx)).astype(np.float64)
        self.Y = np.concatenate((w.y, wy)).astype(np.float64)
        self.Z = np.concatenate((w.z, wg.hi)).astype(np.float64)
        wnode = np.where(wg.lab >= 0, w.nreg + wg.lab, -1) if nw else np.zeros(0, dtype=np.int64)
        self.node = np.concatenate((w.reg, wnode)).astype(np.int64)            # the reach node (-1: eroded / kill)
        self.node_soft = np.concatenate((w.reg_soft, wnode)).astype(np.int64)
        # clearance: 0 a border sample (fewer than 8 links), 1 interior, 2 interior with interior neighbours
        ei, ej = w.links
        inner = (w.conn == 8) & ~w.eroded
        deep = inner.copy()
        deep[ei[~inner[ej]]] = False
        deep[ej[~inner[ei]]] = False
        self.clear = np.concatenate((inner.astype(np.int8) + deep, np.full(nw, 2, dtype=np.int8)))
        src, dst, kind, eid = [], [], [], []

        def add(a, b, k, e):
            a, b = np.asarray(a, dtype=np.int64), np.asarray(b, dtype=np.int64)
            src.append(a)
            dst.append(b)
            kind.append(np.full(len(a), k, dtype=np.int8))
            eid.append(np.full(len(a), e, dtype=np.int64) if np.ndim(e) == 0 else np.asarray(e, dtype=np.int64))

        slip = self._no_walk_up(R.spans.toptri[w.sidx])

        def walks(a, b):
            up = slip[b] & (w.z[b] > w.z[a] + SLIP_UP_M)
            return a[~up], b[~up]

        add(*walks(np.r_[ei, ej], np.r_[ej, ei]), K_WALK, -1)
        xi, xj = w.xlinks
        add(*walks(np.r_[xi, xj], np.r_[xj, xi]), K_WALK, CROSS)
        si, sj = self._soft_links()
        add(*walks(np.r_[si, sj], np.r_[sj, si]), K_SOFT, -1)
        if nw:
            ia, ib = wg.links
            ok = (wg.lab[ia] >= 0) & (wg.lab[ib] >= 0)
            add(ns + np.r_[ia[ok], ib[ok]], ns + np.r_[ib[ok], ia[ok]], K_SWIM, -1)
        # the region edges, each by index; swim edges at the samples swim_edges steps from
        self.edges = []
        index = {}
        for (a_, b_), es in R.E[prof].items():
            for e in es:
                index[id(e)] = len(self.edges)
                self.edges.append((a_, b_, e))
        swim = {}
        for a_, b_, e in self.edges:
            if e["kind"] == "swim":
                swim.setdefault((a_, b_), []).append(index[id(e)])
        if nw:
            pairs = []
            swim_edges(R.lv, w, wg, w.nreg, R.spans if prof == "logic" else None,
                       R.air if prof == "logic" else None, None, pairs=pairs)
            s_ = np.concatenate([p[0] for p in pairs]) if pairs else np.zeros(0, dtype=np.int64)
            n_ = np.concatenate([p[1] for p in pairs]) if pairs else np.zeros(0, dtype=np.int64)
            keep = n_ >= 0
            s_, n_ = s_[keep], n_[keep]
            u = np.unique(s_ * nw + n_)
            s_, n_ = u // nw, u % nw
            for s, n in zip(s_.tolist(), n_.tolist()):
                r, b = int(w.reg_soft[s]), int(wnode[n])
                if r < 0 or b < 0:
                    continue
                for k in swim.get((r, b), ()):
                    add([s], [ns + n], K_SHORE, k)
                if w.z[s] - wg.hi[n] <= 1.0:      # out only where this floor is within the climb-out of the surface
                    for k in swim.get((b, r), ()):
                        add([ns + n], [s], K_SHORE, k)
        self.skipped = {}
        self.pads = {}           # a teleport edge's pad (its index -> the pad mesh's centre at its bottom)
        groups = None
        for k, (a_, b_, e) in enumerate(self.edges):
            kd = e["kind"]
            if kd in FLIGHT_KINDS and e.get("w") is not None:
                add(*([x] for x in self._widen(*e["w"])), K_EDGE, k)
            elif kd in BORDER_KINDS or kd == "teleport":
                groups = groups if groups is not None else self._groups()
                pr = self._closest(groups, a_, b_) if kd != "teleport" else self._teleport(groups, a_, b_, e)
                if pr is not None:
                    add([pr[0]], [pr[1]], K_EDGE, k)
                    if kd == "teleport":
                        self.pads[k] = pr[2]
                elif kd == "teleport":
                    self.skipped[kd] = self.skipped.get(kd, 0) + 1
            elif kd not in ("swim", "walk"):
                self.skipped[kd] = self.skipped.get(kd, 0) + 1
        self.held = self._held()
        src, dst, kind, eid = (np.concatenate(x) for x in (src, dst, kind, eid))
        o = np.argsort(src, kind="stable")
        self.src, self.dst, self.kind, self.eid = src[o], dst[o], kind[o], eid[o]
        self.indptr = np.searchsorted(self.src, np.arange(self.V + 1))
        self.cost = self._costs()
        self._lists = (self.indptr.tolist(), self.dst.tolist(), self.cost.tolist())
        self.exit_v = self._exit_mask()

    def _held(self) -> np.ndarray:
        """The region edges (indices) of the rides of the rigs the level's authoring holds out of logic
        (``draft/authoring/<level>.toml`` ``[rig_held]``: a probe-needed ``rig`` edge whose ``via`` it names, as
        ``author`` keeps it out of logic, Step X.53, AZ-592)."""
        from devkit.rando.draft.author import AUTHORING
        f = AUTHORING / f"{self.R.name}.toml"
        names = set(tomllib.loads(f.read_text(encoding="utf-8")).get("rig_held", {})) if f.is_file() else set()
        return np.array([k for k, (_, _, e) in enumerate(self.edges) if e.get("via") in names
                         and probe_class(e) == "rig"], dtype=np.int64)

    def _teleport(self, groups, a_, b_, e):
        """(source vertex, destination vertex, the pad's point) of a teleport edge (Step X.53, AZ-592): the source
        node's vertex nearest the pad its ``why`` names (``touch <name> (<kind>) -> ...``: of the meshes of that
        name, the one nearest the node; its point the centre of its box at its bottom) and the destination node's
        vertex nearest the playerLocation's spot (``teleporter``); None when either is missing."""
        A, B = groups.get(a_), groups.get(b_)
        m = re.match(r"touch (.+) \((\w+)\) -> ", e.get("why", ""))
        if A is None or B is None or m is None or not e.get("teleporter"):
            return None
        P, best = np.c_[self.X, self.Y, self.Z], None
        for oi in self.lv.by_name.get(m.group(1), ()):
            V = self.lv.P[self.lv.tris_of(oi)].reshape(-1, 3)
            if not len(V):
                continue
            c = np.array([(V[:, 0].min() + V[:, 0].max()) / 2, (V[:, 1].min() + V[:, 1].max()) / 2, V[:, 2].min()])
            d = ((P[A] - c) ** 2).sum(axis=1)
            j = int(np.argmin(d))
            if best is None or d[j] < best[0]:
                best = (float(d[j]), int(A[j]), tuple(float(x) for x in c))
        if best is None:
            return None
        spot = np.asarray(self.lv.rec_points(e["teleporter"])[0][0], dtype=np.float64)
        return best[1], int(B[int(np.argmin(((P[B] - spot) ** 2).sum(axis=1)))]), best[2]

    def _no_walk_up(self, top):
        """The samples (by their floor's triangle) no walk link climbs onto: a slippery floor or (R_phys) a face
        steeper than the step-up's, where the body slides back (sitting x2: w2's ice ramp, nz 0.95; e2's steep path,
        R_phys only)."""
        lv = self.R.lv
        return ((lv.tri_word[top] & collision.W_SLIPPERY) != 0) | (lv.tri_nz[top] < envelope.STEP_NORMAL_Z)

    def _walk_ref(self):
        """The walk whose floors a profile other than logic walks at the plain cost (:meth:`_costs`): logic's."""
        return self.R.W["logic"]

    def _exit_mask(self):
        """The walk vertices inside a trigger that takes the player over: a
        level exit's (the meshes its gate hint touches) and every trigger
        volume named as an exit's or a camera's (SEIZE_NAMES)."""
        lv, w = self.lv, self.w
        names = {nm for e in (getattr(self.R, "gen", None) or {}).get("exits", [])
                 for kind, nm in self.R.HINT_NAMES.findall(e.get("gate_hint") or "") if kind == "touch"}
        ois = {oi for nm in names for oi in lv.by_name.get(nm, [])}
        ois |= {o["oi"] for o in lv.owners if o["cat"] == CAT_TRIGGER
                and any(n in (o["name"] or "").lower() for n in SEIZE_NAMES)}
        m = np.zeros(self.V, dtype=bool)
        for oi in sorted(ois):
            col, zlo, zhi = raster(lv, lv.tris_of(oi))[:3]
            if not len(col):
                continue
            u, inv = np.unique(col, return_inverse=True)
            lo, hi = np.full(len(u), np.inf), np.full(len(u), -np.inf)
            np.minimum.at(lo, inv, zlo)
            np.maximum.at(hi, inv, zhi)
            a, c = lookup(w.u, w.a, w.c, u)
            for k in range(w.mx):
                v = k < c
                j = (a + k)[v]
                m[j[(w.z[j] >= lo[v] - 2.0) & (w.z[j] <= hi[v] + 0.5)]] = True
        return m

    # ---- the graph
    def _soft_links(self):
        """An eroded sample to the 4-neighbours its region comes from
        (``reg_soft``: same region, within the walking step)."""
        w, NX = self.w, self.lv.NX
        er = np.nonzero(w.eroded & (w.reg_soft >= 0))[0]
        ix = w.col[er] % NX
        si, sj = [], []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            valid = (ix + dx >= 0) & (ix + dx < NX)
            a, c = lookup(w.u, w.a, w.c, np.where(valid, w.col[er] + dx + dy * NX, -1))
            for k in range(w.mx):
                v = valid & (k < c)
                j = np.where(v, a + k, 0)
                ok = v & (w.reg_soft[j] == w.reg_soft[er]) & (np.abs(w.z[j] - w.z[er]) <= self.climb)
                si.append(er[ok])
                sj.append(j[ok])
        return (np.concatenate(si), np.concatenate(sj)) if si else (np.zeros(0, dtype=np.int64),) * 2

    def _sample_at(self, x, y, z, reg):
        """The walk sample of region ``reg`` in the column at (x, y) within the walking step of z (-1: none)."""
        w = self.w
        a, c = lookup(w.u, w.a, w.c, np.array([int(self.lv.col(x, y))]))
        for k in range(int(c[0])):
            j = int(a[0]) + k
            if w.reg[j] == reg and abs(float(w.z[j]) - z) <= self.climb:
                return j
        return -1

    def _widen(self, i, j):
        """A flight's witness moved sideways, perpendicular to its track, to
        the middle of the width over which both its ends stay on their
        floors (at most 2 m): the reach model keeps one witness per region
        pair, often at a floor's side.  The moved flight is not swept again,
        so it moves only while its rise stays within WIDEN_RISE_M of the
        witness's (Step X.53: on e2, 55 jumps passed the plain apex and 365
        drops passed 17 m only by widening; #7053 +0.93 -> +1.31 m)."""
        w = self.w
        if w.reg[i] < 0 or w.reg[j] < 0:
            return int(i), int(j)
        dx, dy = float(w.x[j] - w.x[i]), float(w.y[j] - w.y[i])
        d = math.hypot(dx, dy)
        if d < 1e-6:
            return int(i), int(j)
        px, py = -dy / d, dx / d
        side = {0: (int(i), int(j))}
        for sgn in (1, -1):
            for k in range(1, 9):
                o = sgn * k * CELL
                ii = self._sample_at(w.x[i] + px * o, w.y[i] + py * o, float(w.z[i]), w.reg[i])
                jj = self._sample_at(w.x[j] + px * o, w.y[j] + py * o, float(w.z[j]), w.reg[j])
                if ii < 0 or jj < 0:
                    break
                side[sgn * k] = (ii, jj)
        mid = max(-4, min(4, (max(side) + min(side)) // 2))
        ii, jj = side[mid]
        if mid and abs(float(w.z[jj] - w.z[ii]) - float(w.z[j] - w.z[i])) <= WIDEN_RISE_M \
                and self.line_ok(self.pt(i), self.pt(ii), False) and self.line_ok(self.pt(j), self.pt(jj), False):
            return side[mid]
        return int(i), int(j)

    def _groups(self):
        """reach node -> its vertices (sorted)."""
        o = np.argsort(self.node, kind="stable")
        nd = self.node[o]
        u, a, c = np.unique(nd, return_index=True, return_counts=True)
        return {int(n): o[s:s + k] for n, s, k in zip(u.tolist(), a.tolist(), c.tolist()) if n >= 0}

    def _closest(self, groups, a_, b_, cap=1500):
        """The closest (3D) pair of vertices of nodes a_ and b_: on strided
        subsets, then refined twice against the full sets."""
        A, B = groups.get(a_), groups.get(b_)
        if A is None or B is None:
            return None
        P = np.c_[self.X, self.Y, self.Z]
        sa = A[::max(1, len(A) // cap)]
        sb = B[::max(1, len(B) // cap)]
        d = ((P[sa, None, :] - P[None, sb, :]) ** 2).sum(-1)
        i, j = np.unravel_index(int(np.argmin(d)), d.shape)
        va, vb = int(sa[i]), int(sb[j])
        for _ in range(2):
            vb = int(B[np.argmin(((P[B] - P[va]) ** 2).sum(1))])
            va = int(A[np.argmin(((P[A] - P[vb]) ** 2).sum(1))])
        return va, vb

    def _costs(self):
        """Each link's cost in seconds (the walk's by the clearance it walks
        onto; in another profile than logic, PHYS_ONLY times more onto a
        floor the logic walk (:meth:`_walk_ref`) doesn't stand on: a steep or slippery face)."""
        a, b, k = self.src, self.dst, self.kind
        d = np.sqrt((self.X[a] - self.X[b]) ** 2 + (self.Y[a] - self.Y[b]) ** 2 + (self.Z[a] - self.Z[b]) ** 2)
        c = d / WALK_MPS * np.asarray(NEAR_BORDER)[self.clear[b]]
        if self.prof != "logic":
            lw, w = self._walk_ref(), self.w
            on = np.zeros(self.ns, dtype=bool)
            la, lc = lookup(lw.u, lw.a, lw.c, w.col)
            for q in range(lw.mx):
                v = q < lc
                j = np.where(v, la + q, 0)
                on |= v & (np.abs(lw.z[j] - w.z) <= 0.1)
            only = np.concatenate((~on, np.zeros(self.V - self.ns, dtype=bool)))
            c = np.where((k == K_WALK) & only[b], c * PHYS_ONLY, c)
        c = np.where(k == K_SOFT, d / WALK_MPS * NEAR_BORDER[0] * 2, c)
        c = np.where(k == K_SWIM, d / SWIM_MPS, c)
        c = np.where(k == K_SHORE, np.where(b >= self.ns, SHORE_IN_S, SHORE_OUT_S) + d / WALK_MPS, c)
        w = self.w
        self.nz = np.ones(self.V)                  # each vertex's floor normal z (water 1.0)
        self.nz[:self.ns] = self.R.lv.tri_nz[self.R.spans.toptri[w.sidx]]
        flat = self.nz >= LAND_FLAT_NZ
        for q in np.nonzero(k == K_SHORE)[0].tolist() + np.nonzero(k == K_EDGE)[0].tolist():
            e = self.edges[int(self.eid[q])][2]
            if k[q] == K_EDGE and e["kind"] == "teleport":      # the walk into its pad, then the jump across
                c[q] = math.dist(self.pt(a[q]), self.pads[int(self.eid[q])]) / WALK_MPS + TELEPORT_S
            elif k[q] == K_EDGE:
                c[q] = d[q] / WALK_MPS + EDGE_S.get(e["kind"], 2.0) + e.get("fall", 0) / 10.0
                if e["kind"] in FLIGHT_KINDS:
                    c[q] += LAND_EDGE_S[self.clear[b[q]]] + (0.0 if flat[b[q]] else LAND_SLOPE_S)
            if e.get("conf") == "probe-needed":
                c[q] += PROBE_S
        return c

    # ---- points and targets
    def locate(self, p, prefer_water: bool = False, w=None, fallback: bool = True) -> int:
        """The vertex at a point (feet height): the walk sample in its or a
        neighbouring column whose floor lies 1.0 m under to 0.5 m over the
        feet, else the water node holding them, else (``fallback``) the
        highest sample or water surface under them (a body in the air lands
        there); -1 for none.  ``w`` another profile's walk (its sample, or
        ``len(w.col)`` + the water node)."""
        w = self.w if w is None else w
        wg, lv, ns = self.wg, self.lv, len(w.col)
        c0 = int(lv.col(p[0], p[1]))
        cols = np.array([c0 + dx + dy * lv.NX for dy in (0, -1, 1) for dx in (0, -1, 1)])
        a, c = lookup(w.u, w.a, w.c, cols)
        js = np.concatenate([a[q] + np.arange(c[q]) for q in range(len(cols))]).astype(np.int64)
        land = water = None
        if len(js):
            dz = p[2] - w.z[js]
            dxy = np.hypot(w.x[js] - p[0], w.y[js] - p[1])
            ok = (dz >= -0.5) & (dz <= 1.0) & (w.reg_soft[js] >= 0)
            if ok.any():
                score = dxy + 2.0 * np.abs(dz) + np.where(w.eroded[js], 0.3, 0.0)
                land = int(js[ok][np.argmin(score[ok])])
        wa, wc = wg.range_of(np.array([c0])) if len(wg.col) else (np.zeros(1, dtype=np.int64),) * 2
        for q in range(int(wc[0])):
            n = int(wa[0]) + q
            if wg.lab[n] >= 0 and wg.lo[n] - 0.5 <= p[2] <= wg.hi[n] + 1.0:
                water = ns + n
        if land is not None and (water is None or not prefer_water):
            return land
        if water is not None:
            return water
        if not fallback:
            return -1
        best = (-math.inf, -1)
        if len(js):
            under = (w.z[js] <= p[2] + 0.5) & (w.reg_soft[js] >= 0)
            if under.any():
                j = int(js[under][np.argmax(w.z[js][under])])
                best = (float(w.z[j]), j)
        for q in range(int(wc[0])):
            n = int(wa[0]) + q
            if wg.lab[n] >= 0 and wg.hi[n] <= p[2] + 0.5 and wg.hi[n] > best[0]:
                best = (float(wg.hi[n]), ns + n)
        return best[1]

    def nearest(self, p, r: float = 3.0) -> int:
        """The linked vertex nearest p (3D) within r m, -1 for none."""
        m = (np.abs(self.X - p[0]) < r) & (np.abs(self.Y - p[1]) < r) & (np.abs(self.Z - p[2]) < r) & (self.node >= 0)
        js = np.nonzero(m)[0]
        if not len(js):
            return -1
        d = np.sqrt((self.X[js] - p[0]) ** 2 + (self.Y[js] - p[1]) ** 2 + (self.Z[js] - p[2]) ** 2)
        return int(js[np.argmin(d)]) if d.min() <= r else -1

    def node_at(self, p, prefer_water: bool = False) -> int:
        """The reach node at a point (-1: none)."""
        v = self.locate(p, prefer_water)
        return int(self.node_soft[v]) if v >= 0 else -1

    def zone_at(self, p, prefer_water: bool = False, fallback: bool = True) -> str | None:
        """The zone id (``<level>.Z<n>``) at a point (the logic profile's
        zones, whichever profile this is), when the reach has zones; without
        ``fallback``, only of a floor or water the feet are on (:meth:`locate`)."""
        zo = getattr(self.R, "zone_of", None)
        if zo is None:
            return None
        lw = self.R.W["logic"]
        v = self.locate(p, prefer_water, lw, fallback)
        if v < 0:
            return None
        n = int(lw.reg_soft[v]) if v < len(lw.col) else lw.nreg + int(self.wg.lab[v - len(lw.col)])
        return f"{self.R.name}.Z{int(zo[n]):03d}" if n >= 0 else None

    def goal(self, target):
        """(goal vertex mask, target point or None, the feet's band under
        it) for a point (x, y, z: the feet, within 0.5 m), a zone
        (``w2.Z013``), a node of the level file (``w2_z013``, through its
        ``zone:`` anchors), a generated id (``w2/g0/r1357``: its point; a
        pickup is touched from a floor 0.75 m around it, up to 2.5 m under it)
        or a set of reach nodes (a ride's pad, :meth:`trigger`)."""
        if isinstance(target, (set, frozenset)):
            return np.isin(self.node_soft, sorted(target)) & (self.node_soft >= 0), None, None
        band = (-0.5, 0.5)
        if isinstance(target, str) and "/" in target:
            target, band = tuple(self.lv.rec_points(target)[0][0]), (-0.5, 2.5)
        if isinstance(target, str):
            zones = self._zones_of(target)
            zo = self.R.zone_of
            if self.prof == "logic":
                nz = np.where(self.node >= 0, zo[np.maximum(self.node, 0)], -1)
                m = np.isin(nz, zones)
            else:            # the zones are the logic profile's: its samples' columns and heights, and its water
                lw = self.R.W["logic"]
                js = np.nonzero((lw.reg >= 0) & np.isin(zo[np.maximum(lw.reg, 0)], zones))[0]
                m = np.zeros(self.V, dtype=bool)
                a, c = lookup(self.w.u, self.w.a, self.w.c, lw.col[js])
                for k in range(self.w.mx):
                    v = k < c
                    j = (a + k)[v]
                    m[j[np.abs(self.w.z[j] - lw.z[js][v]) <= 0.1]] = True
                wl = np.nonzero(self.wg.lab >= 0)[0]
                m[self.ns + wl] = np.isin(zo[lw.nreg + self.wg.lab[wl]], zones)
            return m, None, None
        p = tuple(float(v) for v in target)
        dxy = np.hypot(self.X - p[0], self.Y - p[1])
        dz = p[2] - self.Z
        m = (dxy <= 0.75) & (dz >= band[0]) & (dz <= band[1]) & (self.node_soft >= 0)
        if not m.any():
            v = self.locate(p)
            if v >= 0:
                m[v] = True
        return m, p, band

    def trigger(self, e) -> list:
        """What starts a ride edge: per pad of its decoded condition
        (``flags``; a pad is a place to touch, an action button, a whack or
        a magic hit there) its atom, label and the reach nodes whose body
        touches it; [] when nothing is decoded (stand on the deck and wait)."""
        out = []
        for atom in e.get("flags", ()):
            out.append({"atom": atom, "kind": atom.split(":")[0], "pad": self.R.flagdef_label(atom),
                        "nodes": frozenset(int(n) for n in self.R.pad_nodes(atom, self.prof))})
        return out

    def probe_classes(self) -> tuple:
        """The probe classes the level's authoring admits into logic
        (``draft/authoring/<level>.toml`` ``probe``), else the ordinary
        movement the derive cannot measure (swim exits, climbs, doors, rides,
        the lip lift)."""
        from devkit.rando.draft.author import AUTHORING
        f = AUTHORING / f"{self.R.name}.toml"
        if f.is_file():
            return tuple(tomllib.loads(f.read_text(encoding="utf-8")).get("probe", ()))
        return ("swim-exit", "climb", "door", "rig", "lip")

    def _zones_of(self, name: str) -> list[int]:
        lvl = self.R.name
        if name.startswith(f"{lvl}.Z"):
            return [int(name.rsplit(".Z", 1)[1])]
        from devkit.rando.draft.author import DATA
        doc = tomllib.loads((DATA / "levels" / f"{lvl}.toml").read_text(encoding="utf-8"))
        for n in doc.get("node", []):
            if n["id"] == name:
                return [int(a.rsplit(".Z", 1)[1]) for a in n.get("anchors", []) if a.startswith(f"zone:{lvl}.Z")]
        raise KeyError(f"{lvl}: no zone or node {name!r}")

    # ---- planning
    def usable_edges(self, tier: str, air: int, allow_probe=(), gates_open: bool = False, fl=None,
                     ban=()) -> np.ndarray:
        ti = self.tiers.index(tier) if tier in self.tiers else len(self.tiers) - 1
        ok = np.array([self.R.usable(e, ti, air, set(allow_probe), gates_open, fl=fl)
                       and (gates_open or not e.get("over")) for _, _, e in self.edges], dtype=bool)
        if len(ban):
            ok[list(ban)] = False
        if self.BAN_HELD and len(self.held):
            ok[self.held] = False
        return ok

    def plan(self, start, target, *, tier: str = "hard", air: int = 0, allow_probe=(), gates_open: bool = False,
             fl=None, no_slip: bool = False, ban=(), avoid=(), start_vertex: int | None = None) -> Route | None:
        """The cheapest route from ``start`` (feet, or a vertex) to ``target``
        (:meth:`goal`); when no route meets it, the route to the reachable
        vertex closest to the target point (``reached`` False); None when
        the start is on no vertex (or a zone target is unreachable).
        ``ban``: region edges (indices) not to take; ``avoid``: (point,
        radius) discs whose vertices cost AVOID_S more to enter (where a walk stuck)."""
        s = self.locate(start) if start_vertex is None else start_vertex
        if s < 0:
            s = self.nearest(start)          # on a surface no profile floor holds (a steep face, an object)
        if s < 0:
            return None
        gmask, gp, _ = self.goal(target)
        eok = self.usable_edges(tier, air, allow_probe, gates_open, fl, ban)
        e = self.eid
        lok = (e == -1) | ((e == CROSS) & (not no_slip)) | np.append(eok, False)[np.where(e >= 0, e, len(eok))]
        ok = lok.tolist()
        indptr, dst, cost = self._lists
        if gp is not None:
            h = (np.sqrt((self.X - gp[0]) ** 2 + (self.Y - gp[1]) ** 2 + (self.Z - gp[2]) ** 2) / (2 * SWIM_MPS)).tolist()
        else:
            h = None
        goal = gmask.tolist()
        shut = np.zeros(self.V, dtype=bool)
        for q, r in avoid:
            shut |= np.hypot(self.X - q[0], self.Y - q[1]) + np.abs(self.Z - q[2]) * 0.5 < r
        shut[s] = False
        shut = shut.tolist()
        exits = (self.exit_v & ~gmask).tolist()
        g = {s: 0.0}
        prev = {s: (-1, -1)}
        heap = [(0.0, 0.0, s)]
        end = None
        while heap:
            _, gu, u = heapq.heappop(heap)
            if gu > g[u]:
                continue
            if goal[u]:
                end = u
                break
            for k in range(indptr[u], indptr[u + 1]):
                if not ok[k]:
                    continue
                v = dst[k]
                nd = gu + cost[k]
                if shut[v]:
                    nd += AVOID_S
                if exits[v] and not exits[u]:
                    nd += EXIT_S
                if nd < g.get(v, math.inf):
                    g[v] = nd
                    prev[v] = (u, k)
                    heapq.heappush(heap, (nd + (h[v] if h is not None else 0.0), nd, v))
        reached = end is not None
        if not reached:
            if gp is None:
                return None
            vs = np.fromiter(g.keys(), dtype=np.int64)
            dd = np.hypot(self.X[vs] - gp[0], self.Y[vs] - gp[1]) + np.abs(self.Z[vs] - gp[2])
            end = int(vs[np.argmin(dd)])
        verts, links = [end], []
        while prev[verts[-1]][0] >= 0:
            u, k = prev[verts[-1]]
            links.append(k)
            verts.append(u)
        verts.reverse()
        links.reverse()
        left = None if gp is None else float(math.dist(self.pt(end), gp))
        return Route(self.legs(verts, links, self.tiers.index(tier) if tier in self.tiers else 0, air), reached, left,
                     g[end], verts, links)

    def pt(self, v) -> tuple:
        return float(self.X[v]), float(self.Y[v]), float(self.Z[v])

    # ---- legs
    def legs(self, verts, links, ti: int = 2, air: int = 0) -> list:
        """The path as legs (the module docstring), each walk and swim leg's
        way-points thinned to straight walkable (swimmable) lines; a flap
        edge that tier ``ti`` flies with no air is a jump; a jump onto a
        ledge the kit (``air``) barely or doesn't clear is a lip lift."""
        out, cur = [], None
        for u, v, k in zip(verts, verts[1:], links):
            kd = int(self.kind[k])
            if kd == K_EDGE:
                if cur is not None:
                    out.append(cur)
                ek = int(self.eid[k])
                e = self.edges[ek][2]
                if e["kind"] == "teleport":          # into its pad; the game puts the player at the far end
                    out.append(Leg("teleport", [self.pads[ek], self.pt(v)], self.pt(u), "teleport", e.get("conf", "?"),
                                   int(self.node[v]), int(self.clear[v]), ek, u, e))
                    cur = None
                    continue
                act = FLIGHT_KINDS.get(e["kind"]) or BORDER_KINDS[e["kind"]]
                if act == "flap" and e["ranks"][min(ti, len(e["ranks"]) - 1)] == 0:
                    act = "jump"
                if act == "jump" and e.get("profile", "").startswith("walk-off"):
                    act = "drop"                     # the reach model's flight walks off: no jump
                at = self._takeoff(u, v, e) if act in ("jump", "flap", "drop") else self.pt(u)
                lip = self._lip(u, v, ti, air) if act == "jump" else None
                land = self.pt(v)
                if lip is not None:
                    at, land, lip = lip
                out.append(Leg(act, [land], at, e["kind"], e.get("conf", "?"), int(self.node[v]),
                               int(self.clear[v]), ek, u, e, lip,
                               self.trigger(e) if act == "wait" else None))
                cur = None
                continue
            act = "swim" if kd == K_SWIM or (kd == K_SHORE and v >= self.ns) else "walk"
            if kd == K_SHORE and v < self.ns:
                act = "swim"          # the way out ends the swim on the shore sample
            if cur is None or cur.action != act:
                if cur is not None:
                    out.append(cur)
                cur = Leg(act, [self.pt(u)], None, act, "geometry", int(self.node[u]), int(self.clear[u]))
                cur.verts = [u]
            cur.pts.append(self.pt(v))
            cur.verts.append(v)
            cur.node = int(self.node_soft[v])
            cur.clear = min(cur.clear, int(self.clear[v]))
            if kd == K_SHORE:
                e = self.edges[int(self.eid[k])][2]
                cur.conf = e.get("conf", cur.conf) if e.get("conf") == "probe-needed" else cur.conf
                if v < self.ns or cur.eid < 0:
                    cur.eid = int(self.eid[k])       # the way out (else in): what a stuck swim bans
        if cur is not None:
            out.append(cur)
        for leg in out:
            vs = getattr(leg, "verts", None)
            if vs is not None:
                leg.pts = [self.pt(vs[i]) for i in self._thin(vs, leg.action == "swim")]
                del leg.verts
        for i, leg in enumerate(out):
            if leg.action in ("jump", "flap", "drop") and i and out[i - 1].action == "walk":   # x4: a drop met from
                                                                                         # the side walked off sideways
                self._runup(out[i - 1], leg)
        return [leg for leg in out if leg.pts]

    def _takeoff(self, u, v, e):
        """Where a flight leaves: for an edge-shape flight or a walk-off,
        0.25 m before the takeoff floor ends on its track (the reach model's
        s0) or its region does, whichever comes first; else the takeoff
        sample."""
        p, q = self.pt(u), self.pt(v)
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        if d < 1e-6 or u >= self.ns or v >= self.ns or "sample to sample" in e.get("profile", "") or e.get("lip"):
            return p
        s0, _ = _track_edges(self.lv, self.w, *(np.array([x]) for x in (p[0], p[1], p[2], q[0], q[1], q[2], d)),
                             self.climb)
        u_ = ((q[0] - p[0]) / d, (q[1] - p[1]) / d)
        s, z = self.run_on(p, u_, int(self.node[u]), min(float(s0[0]), d))
        s = max(s - 0.25, 0.0)
        return p[0] + u_[0] * s, p[1] + u_[1] * s, z

    def _lip(self, u, v, ti: int, air: int):
        """(at, landing, lip) for a jump u -> v onto a ledge above the kit's
        apex less LIP_FROM_M, else None: the track moved sideways to the
        middle of the plain ledge's face; the takeoff the tier's window wants
        (its middle, at most LIP_WANT_MAX_M) before the blocked spot (the
        plain ledge's face less the body radius, else where the takeoff
        floor ends), on the takeoff floor; moved back along the track when
        the takeoff sample stands nearer the face, as far as the floor allows."""
        if u >= self.ns or v >= self.ns:
            return None
        p, q = self.pt(u), self.pt(v)
        tname = self.tiers[min(ti, len(self.tiers) - 1)]
        apex = self.R.env.apex.get((tname, "air_power" if air >= 1 else "none"))
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        if apex is None or q[2] - p[2] <= apex - LIP_FROM_M or d < 1e-6:
            return None
        ux, uy = (q[0] - p[0]) / d, (q[1] - p[1]) / d
        # the track through the middle of the face's width (sitting x4: f6.Z804's face is 0.75 m wide and its witness
        # track ran along one side of it), where the takeoff and landing floors carry the shifted track's ends
        offs = np.arange(-4, 5) * STEP
        sh = [o for o in offs.tolist() if _plain_ledge(self.lv, self.R.spans, *(np.array([x]) for x in (
            p[0] - uy * o, p[1] + ux * o, p[2], q[0] - uy * o, q[1] + ux * o, q[2], d)), self.climb)[0][0]]
        if sh:
            o = min(sh, key=lambda o_: abs(o_ - (min(sh) + max(sh)) / 2))
            p2, q2 = (p[0] - uy * o, p[1] + ux * o, p[2]), (q[0] - uy * o, q[1] + ux * o, q[2])
            if o and self.line_ok(p, p2, swim=False):
                p, q = p2, q2
        ok, face = _plain_ledge(self.lv, self.R.spans, *(np.array([x]) for x in (*p, *q, d)), self.climb)
        run, _ = self.run_on(p, (ux, uy), int(self.node[u]), d)
        blocked = float(face[0]) if ok[0] and np.isfinite(face[0]) else run + STEP / 2
        deficit = q[2] - p[2] - apex
        win = envelope.lip_lift_window(_TIER[tname], deficit) or (envelope.lip_row_m(envelope.LIP_LIFT_ROWS[-1][2]),
                                                                  envelope.lip_row_m(envelope.LIP_LIFT_ROWS[-1][1]))
        s = min(blocked - min((win[0] + win[1]) / 2, LIP_WANT_MAX_M), run - 0.25)
        while s < 0 and not self.line_ok((p[0] + ux * s, p[1] + uy * s, p[2]), p, swim=False):
            s = min(s + STEP, 0.0)
        return (p[0] + ux * s, p[1] + uy * s, p[2]), q, {"deficit_m": round(deficit, 2),
                                                      "window_m": [round(win[0], 2), round(win[1], 2)],
                                                      "before_m": round(blocked - s, 2), "floor_m": round(run - s, 2)}

    def run_on(self, p, u, reg: int, max_m: float = 6.0):
        """(how far, the height there) region ``reg``'s floor runs on from
        p along the unit direction u, each step within the walking step."""
        s, z = 0.0, p[2]
        while s + STEP <= max_m:
            j = self._sample_at(p[0] + u[0] * (s + STEP), p[1] + u[1] * (s + STEP), z, reg)
            if j < 0:
                break
            s, z = s + STEP, float(self.w.z[j])
        return s, z

    def _runup(self, walk: Leg, jump: Leg) -> None:
        """A way-point behind the takeoff, on its track, where the floor
        carries a straight run to it (the jump then leaves at full speed)."""
        at, q = jump.at, jump.pts[-1]
        d = math.hypot(q[0] - at[0], q[1] - at[1])
        if d < 1e-6:
            return
        ux, uy = (q[0] - at[0]) / d, (q[1] - at[1]) / d
        for r in RUNUP_M:
            p = (at[0] - ux * r, at[1] - uy * r, at[2])
            if self.line_ok(p, self.pt(jump.src), swim=False) and self.line_ok(walk.pts[-2], p, swim=False):
                walk.pts[-1] = p
                return

    def _thin(self, vs, swim: bool) -> list:
        """Indices of the way-points kept: greedily the farthest vertex the
        straight line still reaches (at most SEG_MAX_M), and the last."""
        keep, i, n = [0], 0, len(vs)
        while i < n - 1:
            best = i + 1
            for k in range(i + 2, n):
                if math.dist(self.pt(vs[i]), self.pt(vs[k])) > SEG_MAX_M:
                    break
                if self.line_ok(self.pt(vs[i]), self.pt(vs[k]), swim, min(self.clear[vs[i]], self.clear[vs[k]], 1)):
                    best = k
                elif k - best > 6:
                    break
            keep.append(best)
            i = best
        return keep

    def line_ok(self, p, q, swim: bool, clear: int = 0) -> bool:
        """Does the straight line p -> q stay on linked walk samples (each
        within the walking step of the last, of at least ``clear``; through a
        level exit's trigger only from or to it) or, with ``swim``, in live
        water of one swim region?"""
        lv, w, wg = self.lv, self.w, self.wg
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        n = max(int(d / STEP), 1)
        t = np.arange(n + 1) / n
        xs, ys = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        cols = lv.col(xs, ys)
        if swim:
            a, c = wg.range_of(cols)
            labs = set()
            for i in range(n + 1):
                ls = {int(wg.lab[a[i] + k]) for k in range(int(c[i]))} - {-1}
                if not ls:
                    return False
                labs = ls if not labs else labs & ls
                if not labs:
                    return False
            return True
        a, c = lookup(w.u, w.a, w.c, cols)
        z = p[2]
        ex, inex = getattr(self, "exit_v", None), []
        for i in range(n + 1):
            best = None
            for k in range(int(c[i])):
                j = int(a[i]) + k
                dz = abs(float(w.z[j]) - z)
                if dz <= self.climb + 1e-6 and w.reg[j] >= 0 and (best is None or dz < best[0]):
                    best = (dz, j)
            if best is None or self.clear[best[1]] < clear:
                return False
            z = float(w.z[best[1]])
            if ex is not None:
                inex.append(bool(ex[best[1]]))
        if inex and any(inex[1:-1]) and not (inex[0] or inex[-1]):
            return False
        return abs(z - q[2]) <= self.climb + 1e-6
