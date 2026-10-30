"""Reach's geometry: a level's collision as columns of solid spans.

The first stage of the reach model (REORG_PLAN Phase R1, Step R1.3a),
ported as a model from the randomizer evidence's reach v6
(``randomizer-plan-2026-10-10`` at ``d54313d``, ``reach/reach.py``):

1. :class:`Level`: every collision triangle in world space
   (:mod:`azurik_mod.xbr.collision`), with its owner's category (static,
   static platform, rig, toggled solid, water, damage, push or trigger
   volume), its collision word and its normal.
2. :func:`raster`: a Recast-style raster at :data:`CELL` m.  For every
   triangle and every column whose closed square its XY projection
   meets, the triangle's exact z-range over the clipped polygon.
3. :class:`Spans`: the solid pieces of each column merged into spans
   (pieces closer than :data:`MERGE_EPS` join).  :class:`Volumes` keeps
   a set of volume owners' z-ranges per column, and :class:`Obstacles`
   the non-floor pieces the walk erodes against.
4. :class:`Air`: the air between the spans of every column, joined into
   components: a body that passes between two places stays in one, so a
   sealed room is its own component.

Authoring only, with numpy (a runtime dependency since AZ-810; Q289): the
planner and the writer never import this package.  Coordinates stay in
memory; nothing here prints or stores one (RANDOMIZER_PLAN §4.4).
Labels: [verified] a command or capture; [verified static] code or
config read; [inferred]; [proposal] a policy number.
"""

from __future__ import annotations

import collections
import math
import struct
from pathlib import Path

import numpy as np

from azurkit.tools.randomizer.draft import envelope
from azurkit.tools.randomizer.art import collision, nodes

CELL = 0.5            # column size, m [proposal]: the body radius, so one cell of erosion is 0.5 m
MERGE_EPS = 0.1       # solid pieces of a column closer than this merge into one span, m
FACE_EPS = 0.05       # a span's lowest or highest piece faces up (nz > this) or down (nz < -this); else a wall
BODY_R = envelope.BODY_RADIUS             # 0.5 [verified config] garret4 collisionRadius
SLOPE_LAND = envelope.LAND_NORMAL_Z       # 0.6 [verified static 0x8C132]: a landing needs nz > 0.6
AIR_PASS_M = 1.5      # [inferred] adjacent columns' air gaps join when they overlap this much: the 2.0 m body
                      # less the walking step (0.35) and the head tolerance (0.1) a flight's ends allow

CAT_STATIC, CAT_PSTATIC, CAT_RIG, CAT_TOGGLE, CAT_WATER, CAT_DAMAGE, CAT_PUSH, CAT_TRIGGER = range(8)
CAT_NAME = ("static", "platform", "rig", "toggled", "water", "damage", "push", "trigger")
SOLID_CATS = (CAT_STATIC, CAT_PSTATIC, CAT_RIG, CAT_TOGGLE)


def components(n: int, a, b) -> np.ndarray:
    """The connected components of the undirected graph on ``n`` nodes with
    edges ``a[k]``-``b[k]``: each node's label (int32), the components
    numbered in the order of their lowest node.  Roots hook to the lower root across
    each edge, then every node jumps to its root, until no edge joins two
    roots; a node's root is then its component's lowest node."""
    parent = np.arange(n, dtype=np.int64)
    a = np.asarray(a, dtype=np.int64)
    b = np.asarray(b, dtype=np.int64)
    while len(a):
        ra, rb = parent[a], parent[b]
        cut = ra != rb
        if not cut.any():
            break
        a, b, ra, rb = a[cut], b[cut], ra[cut], rb[cut]
        np.minimum.at(parent, np.maximum(ra, rb), np.minimum(ra, rb))
        while True:
            up = parent[parent]
            if np.array_equal(up, parent):
                break
            parent = up
    return np.unique(parent, return_inverse=True)[1].astype(np.int32)


class RadiusIndex:
    """All pairs within a radius ``r`` of a fixed point set (x, y), from a
    grid of r-wide buckets: :meth:`pairs` gives them sorted by query point,
    then by indexed point, with the exact distance."""

    def __init__(self, xy: np.ndarray, r: float):
        self.r, self.xy = float(r), np.asarray(xy, dtype=np.float64)
        b = np.floor(self.xy / self.r).astype(np.int64)
        self.key = self._key(b[:, 0], b[:, 1])
        self.order = np.argsort(self.key, kind="stable")
        self.skey = self.key[self.order]

    @staticmethod
    def _key(bx, by):
        return (bx + (1 << 24)) * (1 << 26) + (by + (1 << 24))

    def pairs(self, q: np.ndarray):
        """(query index, point index, distance) of every pair whose squared
        distance is at most r^2."""
        q = np.asarray(q, dtype=np.float64)
        qb = np.floor(q / self.r).astype(np.int64)
        qi, pj = [], []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                k = self._key(qb[:, 0] + dx, qb[:, 1] + dy)
                lo = np.searchsorted(self.skey, k, "left")
                cnt = np.searchsorted(self.skey, k, "right") - lo
                rep = np.repeat(np.arange(len(q)), cnt)
                pos = lo[rep] + (np.arange(len(rep)) - np.repeat(np.cumsum(cnt) - cnt, cnt))
                qi.append(rep)
                pj.append(self.order[pos])
        qi, pj = np.concatenate(qi), np.concatenate(pj)
        dx = q[qi, 0] - self.xy[pj, 0]
        dy = q[qi, 1] - self.xy[pj, 1]
        sq = dx * dx + dy * dy
        keep = sq <= self.r * self.r
        qi, pj, sq = qi[keep], pj[keep], sq[keep]
        o = np.lexsort((pj, qi))
        return qi[o], pj[o], np.sqrt(sq[o])


# --------------------------------------------------------------------------- the level
class Level:
    """One level's collision as triangle arrays in world space (in memory):
    ``P`` (n, 3, 3), each triangle's owner index, collision word, normal z
    (the ``(p1 - p0) x (p2 - p0)`` winding: floors face up) and area, and
    the column grid over it.  ``owners`` holds one dict per ``tern`` owner,
    sorted by the tern's TOC index, with its category ``cat`` and whether
    it is ``present`` at load as its stored attributes say (a driven
    gameSolid, damage or pushEnable is decoded from the wiring later).
    ``graphs`` are the level's node graphs (:func:`nodes.graphs`), which the
    wiring and the anchors read; a hand-built level has none."""

    def __init__(self, name: str, owners: list[collision.Owner], graphs=()):
        self.name = name
        self.graphs = list(graphs)
        self.owners = []
        P, own = [], []
        for oi, ow in enumerate(owners):
            o = {"oi": oi, "kind": ow.kind, "name": ow.name, "tern": ow.tern, "G": ow.graph, "R": ow.record,
                 "attrs": ow.attrs or {}, "word": ow.word, "moved": ow.moved, "approx": ow.approx,
                 "driven": ow.driven, "world": ow.world}
            if ow.kind == "levl":
                o["cat"], o["present"] = CAT_STATIC, True
            else:
                w, a = ow.word, ow.attrs
                solid = bool(w & collision.W_SOLID)
                if "gameSolid" in ow.driven:
                    o["cat"], o["present"] = CAT_TOGGLE, a.get("gameSolid", 0.0) != 0.0
                elif solid:
                    o["cat"], o["present"] = (CAT_RIG if (ow.moved or ow.approx) else CAT_PSTATIC), True
                elif w & collision.W_WATER:
                    o["cat"], o["present"] = CAT_WATER, True
                elif a.get("damage", 0.0) != 0.0 or "damage" in ow.driven:
                    o["cat"], o["present"] = CAT_DAMAGE, a.get("damage", 0.0) != 0.0
                elif a.get("pushEnable", 0.0) != 0.0 or "pushEnable" in ow.driven:
                    o["cat"], o["present"] = CAT_PUSH, a.get("pushEnable", 0.0) != 0.0
                else:
                    o["cat"], o["present"] = CAT_TRIGGER, True
                o["hazard"] = solid and a.get("damage", 0.0) != 0.0
                o["climbable"] = bool(w & collision.W_CLIMBABLE) and solid
            self.owners.append(o)
            for word, p0, p1, p2 in ow.triangles():
                P.append((p0, p1, p2))
                own.append((oi, word))
        self.P = np.array(P, dtype=np.float64).reshape(-1, 3, 3)
        ow_ = np.array(own, dtype=np.int64).reshape(-1, 2)
        self.tri_owner = ow_[:, 0].astype(np.int32)
        self.tri_word = ow_[:, 1].astype(np.int32)
        n = np.cross(self.P[:, 1] - self.P[:, 0], self.P[:, 2] - self.P[:, 0])
        ln = np.linalg.norm(n, axis=1)
        self.tri_nz = np.where(ln > 0, n[:, 2] / np.maximum(ln, 1e-12), 0.0)
        self.tri_area = ln / 2
        self.tri_cat = np.array([o["cat"] for o in self.owners], dtype=np.int8)[self.tri_owner]
        self.x0 = math.floor(self.P[:, :, 0].min()) - 2.0
        self.y0 = math.floor(self.P[:, :, 1].min()) - 2.0
        self.NX = int((self.P[:, :, 0].max() - self.x0) / CELL) + 3
        self.NY = int((self.P[:, :, 1].max() - self.y0) / CELL) + 3
        self.by_name = collections.defaultdict(list)
        self.by_rec = {}
        for o in self.owners:
            if o["kind"] == "platform":
                self.by_name[o["name"]].append(o["oi"])
                self.by_rec[(o["G"], o["R"])] = o["oi"]

    @classmethod
    def read(cls, iso: Path, name: str, schema: nodes.Schema | None = None) -> Level:
        """``gamedata/<name>.xbr`` of ``iso`` (the caller checks it is the
        vanilla ISO).  Without ``schema`` it is read from the ISO's
        ``default.xbe``."""
        from azurkit.tools.randomizer.ports import XisoReader

        with XisoReader(iso) as rd:
            if schema is None:
                schema = nodes.Schema(bytes(rd.read_file("default.xbe")))
            data = bytes(rd.read_file(f"gamedata/{name}.xbr"))
        graphs = nodes.graphs(data, schema)
        return cls(name, collision.owners(data, schema, graphs), graphs)

    def tris_of(self, oi: int) -> np.ndarray:
        return np.nonzero(self.tri_owner == oi)[0]

    def col(self, x, y):
        """The column index of each point (x, y)."""
        ix = np.floor((np.asarray(x) - self.x0) / CELL).astype(np.int64)
        iy = np.floor((np.asarray(y) - self.y0) / CELL).astype(np.int64)
        return iy * self.NX + ix

    def cxy(self, col):
        """The centre (x, y) of each column."""
        col = np.asarray(col)
        return self.x0 + (col % self.NX + 0.5) * CELL, self.y0 + (col // self.NX + 0.5) * CELL

    def oids(self, cat: int, present_only: bool = False) -> list[int]:
        return [o["oi"] for o in self.owners if o["cat"] == cat and (o["present"] or not present_only)]

    def rec_points(self, gid: str):
        """(world points, approximate) of a generated id ``<level>/g<G>/r<R>``
        (in memory only): a generator's gen points through its parent's
        matrix, else the record's own world translation."""
        _, gs, rs = gid.split("/")
        g = self.graphs[int(gs[1:])]
        i = int(rs[1:])
        if g.types[i] == "critterGenerator":
            st, n = g.list_at(i, 0x2C)
            pts = [struct.unpack_from("<3f", g.s, st + 12 * q) for q in range(min(n, 400))] or [(0.0, 0.0, 0.0)]
            par = g.parent(i)
            m, ap = g.world(par) if par is not None else (nodes.IDENTITY, False)
            return [nodes.apply(m, p) for p in pts], ap
        m, ap = g.world(i)
        return [(m[0][3], m[1][3], m[2][3])], ap

    def mover_of(self, oi: int):
        """(names of the records whose links move owner oi's ancestor transforms, the moved plugs)."""
        o = self.owners[oi]
        if o["kind"] != "platform":
            return [], []
        g = self.graphs[o["G"]]
        inc = g.incoming()
        srcs, axes = set(), set()
        for a in g.ancestors(o["R"]):
            for lk, _ in inc.get(a, ()):
                pn = g.plug_name(a, lk.dst_plug)
                if pn in collision.TRS_PLUGS:
                    srcs.add(g.names[lk.src])
                    axes.add(pn)
        return sorted(srcs), sorted(axes)

    TURNS = (math.pi / 2, math.pi, 3 * math.pi / 2)   # a rotation whose range isn't decoded: a whole turn

    @staticmethod
    def _turns(g, lk, k):
        """The offsets from its rest value a rotate plug takes through link
        ``lk`` (the k-th of its source): a timer's currentTime over its
        start-stop span or a randomNumber's output over its min-max range
        (13 samples, against its current value) or a switch's,
        damper's or combiner's output 0 and 1 through the link's curve; a
        curve past its keys in a cycling mode (levels.Curve models only
        constant and linear) spans its keys' values, plus each cycle's offset
        in mode 4 over the timer's span; else :data:`TURNS`."""
        from azurkit.tools.randomizer import levels as L      # the randomizer's level semantics (no cycle at import)

        src, st = lk.src, g.types[lk.src]
        if st not in ("timer", "switch", "damper", "combiner", "randomNumber") or \
                (st == "timer" and g.plug_name(src, lk.src_plug) != "currentTime"):
            return Level.TURNS
        a = dict(zip(g.schema.types[st].attrs, g.attrs(src)))
        t0, t1 = (a.get("startTime", 0.0), a.get("stopTime", 0.0)) if st == "timer" else \
            (a.get("minNumber", 0.0), a.get("maxNumber", 1.0)) if st == "randomNumber" else (0.0, 1.0)
        try:
            cv = L.link_curve(g, src, k)

            def f(x):
                return L.link_value(cv, x, lk.weight, lk.factor)
            if st in ("timer", "randomNumber"):     # a timer's span, or a random number's range (a wobble)
                v0 = f(a.get("currentTime", t0) if st == "timer" else a.get("output", t0))
                return tuple({f(t0 + (t1 - t0) * q / 12.0) - v0 for q in range(13)} - {0.0}) if t1 > t0 else ()
            d = f(1.0) - f(0.0)
            return (d, -d) if d else ()
        except ValueError:          # a cycling infinity mode
            vs = [kk[1] for kk in cv.keys]
            span = (max(vs) - min(vs)) * abs(lk.factor)
            period = (cv.keys[-1][0] - cv.keys[0][0]) / abs(lk.weight) if lk.weight else 0.0
            if 4 in (cv.pre, cv.post) and period > 0:
                span += math.ceil(abs(t1 - t0) / period) * abs(vs[-1] - vs[0]) * abs(lk.factor)
            return (span, -span) if span else ()
        except struct.error:
            return Level.TURNS

    def lifts(self, oi: int) -> bool:
        """Do the plugs that links move on owner oi's ancestors carry its deck
        (its faces with nz >= 0.8) up or down, level (AZ-353)?  Each such
        translate plug is moved 1 m, each rotate plug through the offsets its
        links give (:meth:`_turns`; a whole turn where they aren't decoded),
        by :meth:`nodes.Graph.world_posed`: one that turns the deck over
        makes it machinery (a gear, axle, drum or jaw), and one must lift
        it: a translation mostly vertical (at least half its distance), or
        a rotation that lifts it more than 1 m (an upright carrier under
        inherit mode 2: e5's wheels).  A deck slid sideways, turned about
        the vertical or scaled is no lift."""
        o = self.owners[oi]
        if o["kind"] != "platform" or not o["moved"]:
            return False
        t = np.nonzero((self.tri_owner == oi) & (self.tri_nz >= envelope.STEP_NORMAL_Z))[0]
        if not len(t):
            return False
        g, R = self.graphs[o["G"]], o["R"]
        P = np.concatenate((self.P[t].reshape(-1, 3), np.ones((3 * len(t), 1))), axis=1)
        local = np.linalg.solve(np.array(g.world(R)[0]), P.T)
        area = self.tri_area[t]
        c0 = P[:, :3].reshape(-1, 3, 3).mean(1)
        lift = False
        for a in g.ancestors(R):
            if not g.schema.is_a(g.types[a], "transform"):
                continue
            poses = collections.defaultdict(set)
            for lk, k in g.incoming().get(a, ()):
                pn = g.plug_name(a, lk.dst_plug)
                if pn.startswith("translate"):
                    poses[pn].add(1.0)
                elif pn.startswith("rotate"):
                    poses[pn].update(self._turns(g, lk, k))
            for pn, ds in sorted(poses.items()):
                for d in sorted(ds):
                    Q = (np.array(g.world_posed(R, a, pn, d)) @ local)[:3].T.reshape(-1, 3, 3)
                    n = np.cross(Q[:, 1] - Q[:, 0], Q[:, 2] - Q[:, 0])
                    nz = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12)
                    if area[nz >= envelope.STEP_NORMAL_Z].sum() < 0.9 * area.sum():
                        return False        # turned over: machinery
                    dv = ((Q.mean(1) - c0) * area[:, None]).sum(0) / area.sum()
                    lift = lift or (abs(dv[2]) >= 0.5 * np.linalg.norm(dv) > 1e-6 if pn.startswith("translate")
                                    else abs(dv[2]) > 1.0)
        return lift

    def driver_of(self, oi: int, plugs) -> list[str]:
        """Names of the records whose links drive ``plugs`` of owner oi."""
        o = self.owners[oi]
        if o["kind"] != "platform":
            return []
        g = self.graphs[o["G"]]
        return sorted({g.names[lk.src] for lk, _ in g.incoming().get(o["R"], ())
                       if g.plug_name(o["R"], lk.dst_plug) in plugs})


def raster(lv: Level, tris, chunk: int = 1_500_000):
    """(col, zlo, zhi, tri, bx0, bx1, by0, by1) for every (triangle, column)
    whose closed square the triangle's XY projection meets: the triangle's
    exact z-range over the clipped polygon, and the clipped polygon's XY box
    in that column.  ``tri`` holds the indices of ``tris``' triangles."""
    tris = np.asarray(tris, dtype=np.int64)
    if len(tris) == 0:
        e = np.zeros(0, dtype=np.float32)
        return (e.astype(np.int64), e, e, e.astype(np.int32), e, e, e, e)
    P = lv.P[tris]
    x0, y0 = lv.x0, lv.y0
    lo = np.floor((P[:, :, :2].min(1) - (x0, y0)) / CELL).astype(np.int64)
    hi = np.floor((P[:, :, :2].max(1) - (x0, y0)) / CELL).astype(np.int64)
    nx = hi[:, 0] - lo[:, 0] + 1
    ny = hi[:, 1] - lo[:, 1] + 1
    n = nx * ny
    cum = np.cumsum(n)
    out = []
    start = 0
    while start < len(n):
        base = cum[start - 1] if start else 0
        end = max(int(np.searchsorted(cum, base + chunk, "right")), start + 1)
        sl = slice(start, end)
        t = np.repeat(np.arange(start, end), n[sl])
        k = np.arange(len(t)) - np.repeat(np.cumsum(n[sl]) - n[sl], n[sl])
        ix = lo[t, 0] + k % nx[t]
        iy = lo[t, 1] + k // nx[t]
        X0 = x0 + ix * CELL
        X1 = X0 + CELL
        Y0 = y0 + iy * CELL
        Y1 = Y0 + CELL
        A, B, C = P[t, 0], P[t, 1], P[t, 2]
        acc = [np.full(len(t), v) for v in (np.inf, -np.inf, np.inf, -np.inf, np.inf, -np.inf)]

        def take(valid, x, y, z):
            for m, (f, v) in enumerate(((np.minimum, z), (np.maximum, z), (np.minimum, x), (np.maximum, x),
                                        (np.minimum, y), (np.maximum, y))):
                acc[m] = np.where(valid, f(acc[m], v), acc[m])

        for V in (A, B, C):        # the vertices inside the square
            take((V[:, 0] >= X0) & (V[:, 0] <= X1) & (V[:, 1] >= Y0) & (V[:, 1] <= Y1), V[:, 0], V[:, 1], V[:, 2])
        with np.errstate(divide="ignore", invalid="ignore"):
            for U, V in ((A, B), (B, C), (C, A)):      # the edges' crossings of the square's sides
                d = V - U
                for axis, L, M0, M1 in ((0, X0, Y0, Y1), (0, X1, Y0, Y1), (1, Y0, X0, X1), (1, Y1, X0, X1)):
                    tt = (L - U[:, axis]) / d[:, axis]
                    q = U[:, 1 - axis] + tt * d[:, 1 - axis]
                    xx, yy = (L, q) if axis == 0 else (q, L)
                    take((tt >= 0) & (tt <= 1) & (q >= M0) & (q <= M1), xx, yy, U[:, 2] + tt * d[:, 2])
            den = (B[:, 1] - C[:, 1]) * (A[:, 0] - C[:, 0]) + (C[:, 0] - B[:, 0]) * (A[:, 1] - C[:, 1])
            ok = np.abs(den) > 1e-9
            dens = np.where(ok, den, 1.0)
            for X, Y in ((X0, Y0), (X1, Y0), (X0, Y1), (X1, Y1)):    # the square's corners inside the triangle
                l1 = ((B[:, 1] - C[:, 1]) * (X - C[:, 0]) + (C[:, 0] - B[:, 0]) * (Y - C[:, 1])) / dens
                l2 = ((C[:, 1] - A[:, 1]) * (X - C[:, 0]) + (A[:, 0] - C[:, 0]) * (Y - C[:, 1])) / dens
                l3 = 1 - l1 - l2
                take(ok & (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9), X, Y,
                     l1 * A[:, 2] + l2 * B[:, 2] + l3 * C[:, 2])
        zmin, zmax, bx0, bx1, by0, by1 = acc
        keep = np.isfinite(zmin)
        f32 = np.float32
        out.append(((iy[keep] * lv.NX + ix[keep]), zmin[keep].astype(f32), zmax[keep].astype(f32),
                    tris[t[keep]].astype(np.int32), bx0[keep].astype(f32), bx1[keep].astype(f32),
                    by0[keep].astype(f32), by1[keep].astype(f32)))
        start = end
    return tuple(np.concatenate(z) for z in zip(*out))


class Spans:
    """The merged solid spans of every column, sorted by (column, bottom),
    with an index by column.  ``toptri`` is the triangle that gives a span's
    top (a floor-like piece wins a near tie); ``botface`` / ``topface`` say
    whether its lowest and highest pieces face up (+1), down (-1) or
    neither (0)."""

    def __init__(self, lv: Level, col, zlo, zhi, tri, *boxes):
        order = np.lexsort((zlo, col))
        col, zlo, zhi, tri = col[order], zlo[order], zhi[order], tri[order]
        off = 5000.0
        key = col.astype(np.float64) * 1e4 + (zhi + off)
        cm = np.maximum.accumulate(key) - col.astype(np.float64) * 1e4 - off
        prev_cm = np.concatenate(([-np.inf], cm[:-1]))
        prev_col = np.concatenate(([-1], col[:-1]))
        start = (col != prev_col) | (zlo > prev_cm + MERGE_EPS)
        sid = np.cumsum(start) - 1
        st = np.nonzero(start)[0]
        self.col = col[st]
        self.bot = zlo[st]
        self.top = np.maximum.reduceat(zhi, st) if len(st) else zhi[:0]
        floorish = lv.tri_nz[tri] >= SLOPE_LAND
        score = zhi + np.where(floorish, 0.12, 0.0)
        o2 = np.lexsort((score, sid))
        last = np.concatenate((np.nonzero(np.diff(sid[o2]))[0], [len(o2) - 1])) if len(o2) else st
        self.toptri = tri[o2[last]]
        o3 = np.lexsort((zhi, sid))
        last3 = np.concatenate((np.nonzero(np.diff(sid[o3]))[0], [len(o3) - 1])) if len(o3) else st

        def face(t_):
            return np.where(lv.tri_nz[t_] > FACE_EPS, 1, np.where(lv.tri_nz[t_] < -FACE_EPS, -1, 0)).astype(np.int8)

        self.botface = face(tri[st])
        self.topface = face(tri[o3[last3]])
        self.n = len(self.col)
        self.ucol, self.ustart, self.ucount = np.unique(self.col, return_index=True, return_counts=True)
        self.maxper = int(self.ucount.max()) if self.n else 0

    def range_of(self, cols):
        """(start, count) of each column's spans (count 0 where it has none)."""
        if not self.n:
            z = np.zeros(len(cols), dtype=np.int64)
            return z, z
        k = np.minimum(np.searchsorted(self.ucol, cols), len(self.ucol) - 1)
        hit = self.ucol[k] == cols
        return np.where(hit, self.ustart[k], 0), np.where(hit, self.ucount[k], 0)


def _clip_z(V, n, z, keep_above):
    """Each convex polygon ``V[i, :n[i]]`` (m, k, 3) clipped to z >= ``z[i]``
    (``keep_above``) or z <= ``z[i]``: (m, 2k, 3) and the new counts."""
    m, k = V.shape[:2]
    idx = np.arange(k)
    valid = idx[None, :] < n[:, None]
    nxt = np.where(idx[None, :] + 1 < n[:, None], idx[None, :] + 1, 0)
    W = np.take_along_axis(V, nxt[:, :, None], axis=1)
    side = (V[:, :, 2] - z[:, None]) * (1 if keep_above else -1)
    wside = (W[:, :, 2] - z[:, None]) * (1 if keep_above else -1)
    ins, wins = side >= 0, wside >= 0
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(side != wside, side / (side - wside), 0.0)
    X = V + t[:, :, None] * (W - V)
    out = np.stack((V, X), axis=2).reshape(m, 2 * k, 3)
    ok = np.stack((valid & ins, valid & (ins != wins)), axis=2).reshape(m, 2 * k)
    order = np.argsort(~ok, axis=1, kind="stable")
    return np.take_along_axis(out, order[:, :, None], axis=1), ok.sum(1)


def tri_band_dist2(T, lo, hi, px, py):
    """The squared XY distance from each point (px, py) to the part of
    triangle ``T[i]`` (m, 3, 3) between heights lo and hi (inf where none
    is): the triangle clipped to the band, projected, a convex polygon (a
    wall's is a segment) the point is inside of (0) or nearest an edge of."""
    m = len(T)
    if not m:
        return np.zeros(0)
    V, n = _clip_z(np.asarray(T, dtype=np.float64), np.full(m, 3), np.asarray(lo, dtype=np.float64), True)
    V, n = _clip_z(V, n, np.asarray(hi, dtype=np.float64), False)
    k = V.shape[1]
    idx = np.arange(k)
    valid = idx[None, :] < n[:, None]
    nxt = np.where(idx[None, :] + 1 < n[:, None], idx[None, :] + 1, 0)
    ax, ay = V[:, :, 0] - px[:, None], V[:, :, 1] - py[:, None]
    W = np.take_along_axis(V, nxt[:, :, None], axis=1)
    ex, ey = W[:, :, 0] - V[:, :, 0], W[:, :, 1] - V[:, :, 1]
    ll = ex * ex + ey * ey
    with np.errstate(divide="ignore", invalid="ignore"):
        u = np.clip(np.where(ll > 0, -(ax * ex + ay * ey) / ll, 0.0), 0.0, 1.0)
    d2 = np.where(valid, (ax + u * ex) ** 2 + (ay + u * ey) ** 2, np.inf).min(1)
    cr = np.where(valid, ex * ay - ey * ax, 0.0)      # the point's side of each edge
    inside = (n >= 3) & ((valid <= (cr >= 0)).all(1) | (valid <= (cr <= 0)).all(1)) & (np.abs(cr).sum(1) > 0)
    return np.where(n == 0, np.inf, np.where(inside, 0.0, d2))


class Obstacles:
    """The raster pieces of non-floor solid faces (nz below the profile's
    floor threshold) with each piece's XY box inside its column, sorted by
    column: what a walkable sample erodes against.  A piece of an inclined
    face (``INCLINE_NZ`` <= nz) reaches only ``INCLINE_R``; walls, steep
    faces and ceilings reach the body radius, measured to the face itself
    within the body's band (AZ-360: a thin diagonal rail's box fills its
    column, which broke town's rope-bridge deck into fragments), its box a
    first test."""

    INCLINE_NZ, INCLINE_R = 0.5, 0.3   # [inferred] the body slides on an inclined face (town's trough bridges)

    def __init__(self, lv: Level, pairs, mask, floor_nz: float):
        col, zlo, zhi, tri, bx0, bx1, by0, by1 = pairs
        m = mask & (lv.tri_nz[tri] < floor_nz)
        sel = np.nonzero(m)[0][np.argsort(col[m], kind="stable")]
        self.P = lv.P
        self.col, self.zlo, self.zhi, self.tri = col[sel], zlo[sel], zhi[sel], tri[sel]
        self.bx0, self.bx1, self.by0, self.by1 = bx0[sel], bx1[sel], by0[sel], by1[sel]
        self.r2 = np.where(lv.tri_nz[tri[sel]] >= self.INCLINE_NZ, self.INCLINE_R ** 2,
                           BODY_R ** 2).astype(np.float32)
        self.u, self.a, self.c = np.unique(self.col, return_index=True, return_counts=True)

    def near(self, cols, cx, cy, lo, hi, r):
        """True where a piece in column ``cols[i]`` overlaps (lo, hi) in z and
        its face, within that band, comes within its reach (at most r) of
        (cx, cy)."""
        res = np.zeros(len(cols), dtype=bool)
        if not len(self.u):
            return res
        k = np.minimum(np.searchsorted(self.u, cols), len(self.u) - 1)
        idx = np.nonzero(self.u[k] == cols)[0]
        a, c = self.a[k[idx]], self.c[k[idx]]
        j = 0
        while len(idx):
            s = a + j
            dx = np.maximum(np.maximum(self.bx0[s] - cx[idx], cx[idx] - self.bx1[s]), 0.0)
            dy = np.maximum(np.maximum(self.by0[s] - cy[idx], cy[idx] - self.by1[s]), 0.0)
            reach = np.minimum(self.r2[s], r * r)
            ok = (self.zlo[s] < hi[idx]) & (self.zhi[s] > lo[idx]) & (dx * dx + dy * dy < reach)
            q = np.nonzero(ok)[0]
            if len(q):
                i_ = idx[q]
                ok[q] = tri_band_dist2(self.P[self.tri[s[q]]], lo[i_], hi[i_], cx[i_], cy[i_]) < reach[q]
            res[idx[ok]] = True
            j += 1
            keep = (c > j) & ~ok
            idx, a, c = idx[keep], a[keep], c[keep]
        return res


class Volumes:
    """The z-interval of each (column, owner) of a set of volume owners
    (water, damage, push or trigger volumes)."""

    def __init__(self, lv: Level, oids):
        oids = list(oids)
        tris = np.nonzero(np.isin(lv.tri_owner, oids))[0] if oids else np.zeros(0, dtype=np.int64)
        col, zlo, zhi, tri = raster(lv, tris)[:4]
        own = lv.tri_owner[tri] if len(tri) else np.zeros(0, dtype=np.int32)
        key = col * 100000 + own
        if len(key):
            u, inv = np.unique(key, return_inverse=True)
            lo = np.full(len(u), np.inf)
            hi = np.full(len(u), -np.inf)
            np.minimum.at(lo, inv, zlo)
            np.maximum.at(hi, inv, zhi)
            self.col, self.own, self.lo, self.hi = u // 100000, (u % 100000).astype(np.int32), lo, hi
        else:
            self.col = self.own = self.lo = self.hi = np.zeros(0)
        o = np.argsort(self.col, kind="stable")
        self.col, self.own, self.lo, self.hi = self.col[o], self.own[o], self.lo[o], self.hi[o]
        self.ucol, self.ustart, self.ucount = np.unique(self.col, return_index=True, return_counts=True)
        self.maxper = int(self.ucount.max()) if len(self.ucount) else 0

    def query(self, cols, zlo, zhi, owners=None):
        """For each i: the owner of a volume in column ``cols[i]`` that
        overlaps [zlo, zhi] (the first in column order; -1 for none) and
        that volume's top."""
        res = np.full(len(cols), -1, dtype=np.int64)
        top = np.full(len(cols), np.nan)
        if not len(self.ucol):
            return res, top
        k = np.minimum(np.searchsorted(self.ucol, cols), len(self.ucol) - 1)
        hit = self.ucol[k] == cols
        a = np.where(hit, self.ustart[k], 0)
        c = np.where(hit, self.ucount[k], 0)
        for j in range(self.maxper):
            v = (j < c) & (res < 0)
            s = np.where(v, a + j, 0)
            ok = v & (self.lo[s] <= zhi) & (self.hi[s] >= zlo)
            if owners is not None:
                ok &= np.isin(self.own[s], owners)
            res = np.where(ok, self.own[s], res)
            top = np.where(ok, self.hi[s], top)
        return res, top


class Air:
    """The air between the solid spans of every column, joined into
    components: two 4-neighbour columns' gaps join when they overlap by
    ``T``; a gap next to a column with no solid (or the grid's edge) joins
    the outside (``VOID``).  A body that moves between two places stays in
    one component, so a flight, a walk into water or a pickup whose two ends
    lie in different components can only pass through a solid.  Gap ids:
    s < n is the gap above span s, n + k the gap under column ``ucol[k]``'s
    first span, ``VOID`` = n + len(ucol)."""

    BIG, ZC = 1.0e5, 4.0e4     # composite keys col * BIG + z, z clipped to +/- ZC

    def __init__(self, lv: Level, spans: Spans, T: float = AIR_PASS_M):
        self.sp, NX = spans, lv.NX
        n, uc, us = spans.n, spans.ucol, spans.ustart
        m = len(uc)
        same_next = np.concatenate((spans.col[1:] == spans.col[:-1], [False]))
        above_hi = np.where(same_next, np.concatenate((spans.bot[1:], [np.inf])), np.inf).astype(np.float64)
        g_col = np.concatenate((spans.col, uc)).astype(np.int64)
        g_lo = np.concatenate((spans.top.astype(np.float64), np.full(m, -np.inf)))
        g_hi = np.concatenate((above_hi, spans.bot[us].astype(np.float64)))
        N = n + m
        self.n, self.N, self.VOID = n, N, N
        self.kbot = spans.col.astype(np.float64) * self.BIG + np.clip(spans.bot, -self.ZC, self.ZC)
        order = np.lexsort((g_lo, g_col))
        clo, chi = np.clip(g_lo, -self.ZC, self.ZC), np.clip(g_hi, -self.ZC, self.ZC)
        klo = g_col[order] * self.BIG + clo[order]
        khi = g_col[order] * self.BIG + chi[order]
        tall = (g_hi - g_lo) >= T

        def has_cols(c):
            k = np.searchsorted(uc, c)
            return (k < m) & (uc[np.minimum(k, max(m - 1, 0))] == c)

        ix = g_col % NX
        ncell = NX * (int(g_col.max()) // NX + 2) if N else 0
        ia, ib = [], []
        for d in (1, NX):
            nc = g_col + d
            ok = tall & has_cols(nc) & ((ix != NX - 1) if d == 1 else True)
            lower = np.searchsorted(khi, nc * self.BIG + clo + T, "right")
            upper = np.searchsorted(klo, nc * self.BIG + chi - T, "left")
            cnt = np.where(ok, np.maximum(upper - lower, 0), 0)
            rep = np.repeat(np.arange(N), cnt)
            k = lower[rep] + (np.arange(len(rep)) - np.repeat(np.cumsum(cnt) - cnt, cnt))
            gb = order[k]
            good = (np.minimum(g_hi[rep], g_hi[gb]) - np.maximum(g_lo[rep], g_lo[gb])) >= T
            ia.append(rep[good])
            ib.append(gb[good])
        for d, edge in ((1, NX - 1), (-1, 0), (NX, None), (-NX, None)):
            nc = g_col + d
            void = tall & (((nc < 0) | (nc >= ncell)) | ~has_cols(nc))
            if edge is not None:
                void |= tall & (ix == edge)
            q = np.nonzero(void)[0]
            ia.append(q)
            ib.append(np.full(len(q), self.VOID))
        ia, ib = np.concatenate(ia), np.concatenate(ib)
        self.comp = components(N + 1, ia, ib)
        self.uc, self.m = uc, m
        self.joins = int(len(ia))
        self.n_components = int(self.comp.max()) + 1

    def gap_at(self, cols, z):
        """The gap holding height z in each column (-1 inside a solid; VOID
        for a column with no solid)."""
        cols = np.asarray(cols, dtype=np.int64)
        z = np.asarray(z, dtype=np.float64)
        sp = self.sp
        k = np.searchsorted(self.kbot, cols * self.BIG + np.clip(z, -self.ZC, self.ZC), "right") - 1
        kc = np.maximum(k, 0)
        valid = (k >= 0) & (sp.col[kc] == cols)
        inside = valid & (z < sp.top[kc])
        u = np.searchsorted(self.uc, cols)
        has = (u < self.m) & (self.uc[np.minimum(u, max(self.m - 1, 0))] == cols)
        bottom = np.where(has, self.n + np.minimum(u, max(self.m - 1, 0)), self.VOID)
        return np.where(valid, np.where(inside, -1, kc), bottom)

    def comp_of(self, gaps):
        gaps = np.asarray(gaps)
        return np.where(gaps >= 0, self.comp[np.maximum(gaps, 0)], -1)
