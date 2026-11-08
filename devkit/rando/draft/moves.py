"""Reach's region edges other than flights: swimming, climbing, slides and rides.

Part of the reach model (Step R1.3b; reach v6's ``WaterGrid``,
``swim_edges``, ``climb_edges``, ``slide_edges`` and ``rig_edges``):

* :class:`WaterGrid`: the swim water.  Per column the union of the water
  volumes' z intervals (merged only where two overlap or touch, AZ-356:
  never the hull from the lowest to the highest, which made e6's lake and
  the waterfall over it one swim) less the solid spans, cut into free
  intervals, and only the water above the column's lowest span counts
  (under it is the ground, whichever way it faces).  A gap above a down-facing top and below an
  up-facing bottom is the inside of a closed solid and holds no water.
  Each free interval at least 0.5 m deep is a water node; 4-neighbour
  nodes join where their intervals overlap by 0.5 m.  Nodes in a kill
  field are out, and nodes inside a current the stroke cannot beat join
  only each other (the carries follow them, :mod:`.reach`).
* :func:`swim_edges`: a land region and the water beside it (the drop
  to the surface swept; a shore two cells away only with no wall between;
  wading floor joins the water around it both ways).
* :func:`water_fall_edges`: one-way falls out of the water over its open
  bottom or its lip (AZ-356).
* :func:`climb_edges`: climbable faces, foot to top (probe-needed).
* :class:`Slopes` and :func:`slide_edges`: one-way slides down slippery
  faces along the fall line (frictionless at g sin(theta) [verified xemu
  calib §7]).
* :func:`rig_edges`: lifts whose motion is not decoded (probe-needed).

Authoring only (numpy); coordinates stay in memory.
"""

from __future__ import annotations

import collections

import numpy as np

from azurkit.tools.randomizer.draft import envelope
from devkit.rando.draft.flights import HEAD_TOL, _body, _hits
from azurkit.tools.randomizer.draft.floors import SLIP_FLAT_NZ, Walk, lookup
from azurkit.tools.randomizer.draft.geometry import (
    CAT_PSTATIC, CAT_RIG, CAT_STATIC, CELL, Level, Spans, Volumes, components, raster)
from azurkit.tools.randomizer.art import collision

SLIDE_NZ_MIN = 0.3        # [proposal] slippery faces 0.3 <= nz < SLIP_FLAT_NZ are slides (calib §7: g sin(theta))
SLIDE_DROP_M = 2.0        # [proposal] a step down the fall line of more than this leaves the face: a fall
LETHAL_FALL_M = envelope.FALL_STEPS[-1][0]   # 17 m [verified static]: the fall rule's last step (1000 HP)
RIG_DECK_M2 = (1.5, 400.0)     # a rig deck (up-facing faces) between these areas is a candidate lift
RIG_RING = 2                   # cells around the deck's footprint where its landings are looked for
WATER_TOUCH_M = 0.05           # [proposal] two water volumes' intervals in one column this close are one water (AZ-356)


def water_intervals(vol: Volumes):
    """(column, bottom, top) of each stretch of water in each column: the union of the volumes' z intervals there,
    merging only those that overlap or touch (AZ-356), sorted by (column, bottom)."""
    o = np.lexsort((vol.lo, vol.col))
    cols, los, his = [], [], []
    for c, a, b in zip(vol.col[o].astype(np.int64).tolist(), vol.lo[o].tolist(), vol.hi[o].tolist()):
        if cols and cols[-1] == c and a <= his[-1] + WATER_TOUCH_M:
            his[-1] = max(his[-1], b)
        else:
            cols.append(c)
            los.append(a)
            his.append(b)
    return np.array(cols, dtype=np.int64), np.array(los, dtype=np.float64), np.array(his, dtype=np.float64)


class WaterGrid:
    """The swim water (the module docstring).  Nodes are sorted by (column,
    bottom): ``col``, ``lo``, ``hi``, ``top`` (the volume's top), ``lab``
    (swim region, by area then first node; -1 in a kill field), ``count``
    (distinct columns per region), ``blk_own`` (the blocking current a node
    lies in, or -1) and ``n`` (regions)."""
    WATER_PASS_M = 0.5

    def __init__(self, lv: Level, water_vol: Volumes, damage_vol: Volumes, hazard_oids, spans: Spans | None = None,
                 block: Volumes | None = None):
        self.lv = lv
        P_ = self.WATER_PASS_M
        self.blocked = 0
        self.hazard_cols = self.void_cols = self.dry_cols = self.water_columns = 0
        self.land_cols = self.inside_gaps = 0
        self.inside_m = 0.0
        self.joins = 0
        if not len(water_vol.col):
            self._empty(0)
            return
        u, lo, hi = water_intervals(water_vol)      # one entry per stretch of water in a column (AZ-356)
        haz = np.zeros(len(u), dtype=bool)
        if len(hazard_oids):
            ho, _ = damage_vol.query(u, lo, hi, owners=np.array(sorted(hazard_oids)))
            haz = ho >= 0
        self.water_columns = len(np.unique(u))
        self.hazard_cols = int(haz.sum())
        nc, nl, nh = [], [], []
        if spans is not None:
            a, c = spans.range_of(u)
            has = c > 0
            a0 = np.where(has, a, 0)
            self.void_cols = int((has & (np.minimum(spans.bot[a0], hi) > lo + P_)).sum())
            self.land_cols = int((has & (spans.bot[a0] >= hi)).sum())
            cur = np.where(has, np.maximum(lo, spans.top[a0]), lo)
            for k in range(1, spans.maxper):
                v = k < c
                s_ = np.where(v, a + k, 0)
                gh = np.where(v, np.minimum(spans.bot[s_], hi), -np.inf)
                inside = v & (spans.topface[np.maximum(s_ - 1, 0)] < 0) & (spans.botface[s_] > 0)
                emit = v & (gh - cur >= P_)
                self.inside_gaps += int((emit & inside).sum())
                self.inside_m += float(np.where(emit & inside, gh - cur, 0.0).sum())
                emit &= ~inside
                nc.append(np.nonzero(emit)[0])
                nl.append(cur[emit])
                nh.append(gh[emit])
                cur = np.where(v, np.maximum(cur, spans.top[s_]), cur)
        else:
            cur = lo.copy()
        emit = (hi - cur) >= P_
        nc.append(np.nonzero(emit)[0])
        nl.append(cur[emit])
        nh.append(hi[emit])
        ci, nlo, nhi = np.concatenate(nc), np.concatenate(nl), np.concatenate(nh)
        o = np.lexsort((nlo, u[ci]))
        ci, nlo, nhi = ci[o], nlo[o], nhi[o]
        self.col, self.lo, self.hi, self.top = u[ci], nlo, nhi, hi[ci]
        self.haz = haz[ci]
        # water inside a current the swim stroke cannot beat is no free swimming: its nodes join only each other
        self.blk_own = np.full(len(ci), -1, dtype=np.int64)
        if block is not None and len(block.col):
            self.blk_own, _ = block.query(u[ci], nlo, nhi)
        self.blk = self.blk_own >= 0
        self.blocked = int(self.blk.sum())
        cut = self.haz
        self.dry_cols = int(len(np.unique(u)) - len(np.unique(u[ci])))
        n = len(ci)
        self._csr()
        if not n:       # water volumes but no node deep enough above the lowest span (e7)
            self.links = (self.col, self.col)
            self.lab = np.zeros(0, dtype=np.int64)
            self.n = 0
            self.lab_blocked = set()
            self.count = np.zeros(0, dtype=np.int64)
            return
        ia, ib = [], []
        for d in (1, lv.NX):
            a, c = self.range_of(self.col + d)
            for k in range(self.maxper):
                v = (k < c) & ~cut
                if d == 1:
                    v &= (self.col % lv.NX) != lv.NX - 1
                j = np.where(v, a + k, 0)
                ok = v & ~cut[j] & (self.blk_own == self.blk_own[j]) & \
                    ((np.minimum(self.hi, self.hi[j]) - np.maximum(self.lo, self.lo[j])) >= P_)
                ia.append(np.nonzero(ok)[0])
                ib.append(j[ok])
        ia, ib = np.concatenate(ia), np.concatenate(ib)
        self.joins = int(len(ia))
        self.links = (ia, ib)       # the node links (the route planner swims them)
        lab = np.where(cut, -1, components(n, ia, ib))
        # relabel by area (distinct columns, desc), then first node
        good = lab >= 0
        key = np.unique(lab[good].astype(np.int64) * (int(self.col.max()) + 1) + self.col[good])
        cnt = np.bincount(key // (int(self.col.max()) + 1), minlength=int(lab.max()) + 1 if n else 0)
        first = np.full(len(cnt), n)
        np.minimum.at(first, lab[good], np.nonzero(good)[0])
        pres = np.nonzero(cnt)[0]
        order = pres[np.lexsort((first[pres], -cnt[pres]))]
        remap = np.full(len(cnt), -1)
        remap[order] = np.arange(len(order))
        self.lab = np.where(good, remap[np.maximum(lab, 0)], -1)
        self.n = len(order)
        self.lab_blocked = set(self.lab[self.blk & (self.lab >= 0)].tolist())
        self.count = cnt[order]

    def _empty(self, n):
        z = np.zeros(0)
        self.col = np.zeros(0, dtype=np.int64)
        self.links = (self.col, self.col)
        self.lo = self.hi = self.top = z
        self.lab = np.zeros(0, dtype=np.int64)
        self.haz = self.blk = np.zeros(0, dtype=bool)
        self.lab_blocked = set()
        self.blk_own = np.zeros(0, dtype=np.int64)
        self.n = n
        self.count = np.zeros(0, dtype=np.int64)
        self._csr()

    def _csr(self):
        self.ucol, self.ustart, self.ucount = np.unique(self.col, return_index=True, return_counts=True)
        self.maxper = int(self.ucount.max()) if len(self.ucount) else 0

    def range_of(self, cols):
        if not len(self.ucol):
            z = np.zeros(len(cols), dtype=np.int64)
            return z, z
        k = np.minimum(np.searchsorted(self.ucol, cols), len(self.ucol) - 1)
        hit = self.ucol[k] == cols
        return np.where(hit, self.ustart[k], 0), np.where(hit, self.ucount[k], 0)

    def at(self, cols, zlo, zhi):
        """(swim label, the node's top) of the topmost water node of column
        cols[i] overlapping [zlo, zhi]; label -2 is a node in a kill field,
        -1 no water node there (dry, solid, under the seabed or too shallow)."""
        cols = np.asarray(cols, dtype=np.int64)
        res = np.full(len(cols), -1, dtype=np.int64)
        top = np.full(len(cols), np.nan)
        if not len(self.col):
            return res, top
        a, c = self.range_of(cols)
        zlo, zhi = np.broadcast_to(zlo, cols.shape), np.broadcast_to(zhi, cols.shape)
        for k in range(self.maxper):
            v = k < c
            s_ = np.where(v, a + k, 0)
            ok = v & (self.lo[s_] <= zhi) & (self.hi[s_] >= zlo)
            res = np.where(ok, np.where(self.lab[s_] >= 0, self.lab[s_], -2), res)
            top = np.where(ok, self.hi[s_], top)
        return res, top

    def at_node(self, cols, zlo, zhi):
        """The index of the node :meth:`at` reads, -1 for none."""
        cols = np.asarray(cols, dtype=np.int64)
        res = np.full(len(cols), -1, dtype=np.int64)
        if not len(self.col):
            return res
        a, c = self.range_of(cols)
        zlo, zhi = np.broadcast_to(zlo, cols.shape), np.broadcast_to(zhi, cols.shape)
        for k in range(self.maxper):
            v = k < c
            s_ = np.where(v, a + k, 0)
            ok = v & (self.lo[s_] <= zhi) & (self.hi[s_] >= zlo)
            res = np.where(ok, s_, res)
        return res


def swim_edges(lv: Level, w: Walk, wg: WaterGrid, base: int, spans=None, air=None, stats=None, pairs=None):
    """Land region <-> swim region edges (ids: land r, water base + k).
    With ``spans`` the drop from the land sample to the surface (and the
    climb back) is swept in the water column: a deck, a roof or the land
    sample's own floor between them blocks it; a water column two cells
    away joins only when the column between holds no solid in the body
    band; with ``air`` the land sample and the surface share an air
    component.  A wading sample joins the water nodes around it both ways.
    Where a land region enters a blocking current's water, the node is
    recorded in ``w.blk_entry`` (the carries go on from there).  A ``pairs``
    list gets (samples, their water nodes) of every step it finds (the
    route planner's shore links)."""
    p = w.p
    raw = {}
    NX = lv.NX
    ix = w.col % NX
    for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (0, 2), (0, -2)):
        nix = ix + dx
        valid = (nix >= 0) & (nix < NX) & (w.reg_soft >= 0)
        ncol = np.where(valid, w.col + dx + dy * NX, -1)
        lab, top = wg.at(ncol, w.z - 16.0, w.z + p["climb"])
        wade = w.wading & (top > w.z + p["climb"] + 0.05) & (top <= w.z + p["wade"] + 0.05)
        m = valid & (lab >= 0) & ((top <= w.z + p["climb"] + 0.05) | wade)
        if spans is not None and m.any():
            q = np.nonzero(m)[0]
            poke, roof = _body(spans, ncol[q], top[q], np.maximum(w.z[q], top[q]) + p["height"], p["height"])
            # the shore itself may rise from below the surface up to the land floor (what a climb-out climbs)
            bad = roof | (poke > np.maximum(w.z[q] - top[q], 0.0) + p["climb"])
            if abs(dx) == 2 or abs(dy) == 2:
                mid = w.col[q] + dx // 2 + (dy // 2) * NX
                wall_ = _hits(spans, mid, w.z[q] + p["climb"], w.z[q] + p["height"] - HEAD_TOL)
                if stats is not None:
                    stats["swim_through_wall"] = stats.get("swim_through_wall", 0) + int((wall_ & ~bad).sum())
                bad |= wall_
            if air is not None:
                split = air.comp_of(air.gap_at(ncol[q], np.maximum(w.z[q], top[q]) + p["climb"] + 0.02)) \
                    != air.comp_of(w.sidx[q])
                if stats is not None:
                    stats["swim_air_split"] = stats.get("swim_air_split", 0) + int((split & ~bad).sum())
                bad |= split
            m[q[bad]] = False
        if stats is not None:
            stats["swim_wading"] = stats.get("swim_wading", 0) + int((m & wade).sum())
        if not m.any():
            continue
        if pairs is not None:
            q = np.nonzero(m)[0]
            pairs.append((q, wg.at_node(ncol[q], w.z[q] - 16.0, w.z[q] + p["climb"])))
        if wg.lab_blocked:
            q = np.nonzero(m)[0]
            q = q[np.isin(lab[q], list(wg.lab_blocked))]
            if len(q):
                nd = wg.at_node(ncol[q], w.z[q] - 16.0, w.z[q] + p["climb"])
                ent = w.__dict__.setdefault("blk_entry", collections.defaultdict(set))
                for r_, n_ in zip(w.reg_soft[q].tolist(), nd.tolist()):
                    if n_ >= 0:
                        ent[int(r_)].add(int(n_))
        r = w.reg_soft[m]
        b = base + lab[m]
        above = w.z[m] - top[m]
        key = r.astype(np.int64) * 1_000_000 + b
        o = np.lexsort((above, key))
        first = np.concatenate(([True], key[o][1:] != key[o][:-1]))
        for q in o[first]:
            k2 = (int(r[q]), int(b[q]))
            raw[k2] = min(raw.get(k2, 99.0), float(above[q]))
    out = {}
    for (r, b), h in raw.items():
        out[(r, b)] = {"kind": "swim", "conf": "geometry", "dh": -max(h, 0.0), "ranks": [0, 0, 0, 0],
                       "why": "enter the water"}
        if b - base in wg.lab_blocked:
            continue        # out of a blocking current's water only with the push (Reach.current_edges)
        if h < 0:
            out[(b, r)] = {"kind": "swim", "conf": "modelled", "dh": h, "ranks": [0, 0, 0, 0],
                           "why": "wade out of the water (a floor at most 1 m under the surface)"}
        elif h <= p["climb"]:
            out[(b, r)] = {"kind": "swim", "conf": "modelled", "dh": h, "ranks": [0, 0, 0, 0],
                           "why": "walk out of the water (floor within the step height of the surface)"}
        elif h <= 1.0:
            out[(b, r)] = {"kind": "swim", "conf": "probe-needed", "dh": h, "ranks": [0, 0, 0, 0],
                           "why": "climb out of the water (unmeasured)"}
    return out


def water_fall_edges(lv: Level, w: Walk, wg: WaterGrid, base: int, spans: Spans):
    """One-way falls out of the water (AZ-356): out of a water node's open bottom (no floor within 0.5 m under it) the
    body sinks out and falls straight down its column, and over its lip (a 4-neighbour column with no water and no
    solid beside its interval) it swims out and falls down that column, onto the highest walk sample or the top of
    the water under the node's bottom, unless the fall (from the bottom; over a lip, from the surface) is lethal
    (17 m or more).  Water inside a blocking current leaves only with the push (``Reach.current_edges``)."""
    edges = {}
    if not wg.n or spans is None:
        return edges
    P_ = wg.WATER_PASS_M
    a, c = spans.range_of(wg.col)
    floor = np.full(len(wg.col), -np.inf)
    for k in range(spans.maxper):
        v = k < c
        s_ = np.where(v, a + k, 0)
        floor = np.maximum(floor, np.where(v & (spans.top[s_] <= wg.lo + 0.05), spans.top[s_], -np.inf))
    ok = (wg.lab >= 0) & ~wg.blk
    exits = [(np.nonzero(ok & (wg.lo - floor >= P_))[0], 0, False)]      # (nodes, the column step, over a lip)
    NX = lv.NX
    for d in (1, -1, NX, -NX):
        nb = wg.col + d
        side = ok & (wg.col % NX != NX - 1) if d == 1 else ok & (wg.col % NX != 0) if d == -1 else ok
        wa, wc = wg.range_of(nb)
        wet = np.zeros(len(wg.col), dtype=bool)
        for k in range(wg.maxper):
            v = (k < wc) & side
            j = np.where(v, wa + k, 0)
            wet |= v & (np.minimum(wg.hi, wg.hi[j]) - np.maximum(wg.lo, wg.lo[j]) > 0.0)
        q = np.nonzero(side & ~wet)[0]
        if len(q):
            q = q[~_hits(spans, nb[q], wg.lo[q], wg.hi[q])]
        exits.append((q, d, True))
    for q, d, lip in exits:
        if not len(q):
            continue
        cols, z0 = wg.col[q] + d, wg.lo[q]
        best_z, best_r = np.full(len(q), -np.inf), np.full(len(q), -1, dtype=np.int64)
        la, lc = lookup(w.u, w.a, w.c, cols)
        for k in range(w.mx):
            v = k < lc
            j = np.where(v, la + k, 0)
            hit = v & (w.reg[j] >= 0) & (w.z[j] <= z0 + 0.05) & (w.z[j] > best_z)
            best_z, best_r = np.where(hit, w.z[j], best_z), np.where(hit, w.reg[j], best_r)
        wa, wc = wg.range_of(cols)
        for k in range(wg.maxper):
            v = k < wc
            j = np.where(v, wa + k, 0)
            hit = v & (j != q) & (wg.lab[j] >= 0) & (wg.hi[j] <= z0 + 0.05) & (wg.hi[j] > best_z)
            best_z, best_r = np.where(hit, wg.hi[j], best_z), np.where(hit, base + wg.lab[j], best_r)
        drop = (wg.hi[q] if lip else z0) - best_z
        keep = (best_r >= 0) & (drop < LETHAL_FALL_M)
        why = ("swim out over the water's lip and fall" if lip else "sink out of the water's open bottom and fall") + \
            " straight down (AZ-356)"
        for i_, r_, h in zip(q[keep].tolist(), best_r[keep].tolist(), drop[keep].tolist()):
            key = (base + int(wg.lab[i_]), int(r_))
            if key[0] != key[1] and (key not in edges or -h > edges[key]["dh"]):
                edges[key] = {"kind": "drop", "conf": "geometry", "ranks": [0, 0, 0, 0], "dh": -float(h), "why": why}
    return edges


def climb_edges(lv: Level, w: Walk):
    """Climbable faces (static 0x8052 / 0x8013 chunks, climbable solid
    platforms): the regions at their foot -> the regions at their top.
    Climbing is outside the envelope: probe-needed.  Returns (edges, the
    climbable clusters)."""
    climb_tri = np.nonzero(((lv.tri_word & collision.W_CLIMBABLE) != 0) & ((lv.tri_word & collision.W_SOLID) != 0)
                           & np.isin(lv.tri_cat, [CAT_STATIC, CAT_PSTATIC]))[0]
    if not len(climb_tri):
        return {}, 0
    col, zlo, zhi, tri = raster(lv, climb_tri)[:4]
    u, inv = np.unique(col, return_inverse=True)
    lo = np.full(len(u), np.inf)
    hi = np.full(len(u), -np.inf)
    np.minimum.at(lo, inv, zlo)
    np.maximum.at(hi, inv, zhi)
    pos = {int(c): k for k, c in enumerate(u)}
    NX = lv.NX
    ia, ib = [], []
    for k, c in enumerate(u.tolist()):
        for d in (1, NX - 1, NX, NX + 1):
            j = pos.get(c + d)
            if j is not None and lo[j] <= hi[k] + 1 and hi[j] >= lo[k] - 1:
                ia.append(k)
                ib.append(j)
    lab = components(len(u), ia, ib)
    edges = {}
    ncl = int(lab.max()) + 1
    for cl in range(ncl):
        cs = u[lab == cl]
        zmin, zmax = lo[lab == cl].min(), hi[lab == cl].max()
        if zmax - zmin < 1.0:
            continue
        cset = set()
        for c in cs.tolist():
            for dx in (-2, -1, 0, 1, 2):
                for dy in (-2, -1, 0, 1, 2):
                    cset.add(c + dx + dy * NX)
        cc = np.array(sorted(cset))
        a, cnt = lookup(w.u, w.a, w.c, cc)
        foot, top = set(), set()
        for k in range(w.mx):
            v = k < cnt
            j = (a + k)[v]
            r = w.reg_soft[j]
            z = w.z[j]
            foot.update(r[(r >= 0) & (np.abs(z - zmin) <= 1.0)].tolist())
            top.update(r[(r >= 0) & (z >= zmax - 1.0) & (z <= zmax + 1.0)].tolist())
        for a_ in foot:
            for b_ in top:
                if a_ != b_:
                    e = edges.setdefault((a_, b_), {"kind": "climb", "conf": "probe-needed", "ranks": [0, 0, 0, 0],
                                                    "dh": float(zmax - zmin), "why": "climbable face (climbing unmeasured)"})
                    e["dh"] = max(e["dh"], float(zmax - zmin))
    return edges, ncl


class Slopes:
    """The slides' faces: slippery static faces with SLIDE_NZ_MIN <= nz <
    SLIP_FLAT_NZ (the logic walk never stands on them), each column's
    highest one (``sc``, ``sz``) with its fall line (``fx``, ``fy``)."""

    def __init__(self, lv: Level):
        self.lv = lv
        slip = np.nonzero(((lv.tri_word & collision.W_SLIPPERY) != 0) & ((lv.tri_word & collision.W_SOLID) != 0)
                          & np.isin(lv.tri_cat, [CAT_STATIC, CAT_PSTATIC]) & (lv.tri_nz >= SLIDE_NZ_MIN)
                          & (lv.tri_nz < SLIP_FLAT_NZ))[0]
        col, zlo, zhi, tri = raster(lv, slip)[:4]
        o = np.lexsort((zhi, col))
        last = np.concatenate((np.nonzero(np.diff(col[o]))[0], [len(o) - 1])) if len(o) else o
        self.sc, self.sz, st = col[o][last], zhi[o][last].astype(np.float64), tri[o][last]
        P = lv.P[st]
        n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
        n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        n = np.where(n[:, 2:3] < 0, -n, n)
        hxy = np.hypot(n[:, 0], n[:, 1])
        self.fx = np.where(hxy > 1e-6, n[:, 0] / np.maximum(hxy, 1e-9), 0.0)
        self.fy = np.where(hxy > 1e-6, n[:, 1] / np.maximum(hxy, 1e-9), 0.0)
        self.idx = {int(c): k for k, c in enumerate(self.sc.tolist())}

    BUMP_M = 0.5    # [proposal] up the fall line, a dip this deep in the next column is a bump of the face, not its top

    def under(self, p, below: float, above: float = 0.5) -> int:
        """The slope column (index) whose face lies ``below`` m or less under
        point ``p`` (or ``above`` over it): its own column, else the nearest
        of its 8 neighbours; -1 for none."""
        c0, NX = int(self.lv.col(p[0], p[1])), self.lv.NX
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            k = self.idx.get(c0 + dx + dy * NX, -1)
            if k >= 0 and -above <= p[2] - self.sz[k] <= below:
                return k
        return -1

    def follow(self, k: int, down: bool = True, max_steps: int = 600):
        """(x, y, z, k, steps) where the fall line from slope column ``k``
        ends: down it until the slide ends, turns uphill or drops more than
        SLIDE_DROP_M (the body leaves the face); or (``down`` False) up it
        until the slope ends or dips more than BUMP_M.  A step that stays in
        its column goes on along the same line."""
        lv, sz, sgn = self.lv, self.sz, 1.0 if down else -1.0
        x, y = lv.cxy(self.sc[k])
        x, y, z = float(x), float(y), float(sz[k])
        path, seen = 0, {int(self.sc[k])}
        while path < max_steps:
            x2, y2 = x + sgn * self.fx[k] * CELL, y + sgn * self.fy[k] * CELL
            c2 = int(lv.col(x2, y2))
            if c2 == int(self.sc[k]):       # a step that stays in its column (off the centre): on along its line
                x, y, path = x2, y2, path + 1
                continue
            k2 = self.idx.get(c2, -1)
            if k2 < 0 or c2 in seen or (sz[k2] > z + 0.3 or sz[k2] < z - SLIDE_DROP_M if down
                                        else sz[k2] < z - self.BUMP_M):
                break                       # off the slope, back on its own track (a pit), uphill, or over the top
            seen.add(c2)
            x, y, z, k = x2, y2, float(sz[k2]), k2
            path += 1
        return x, y, z, k, path

    def landing(self, w: Walk, wg: WaterGrid | None, x, y, z, k, acomp=None):
        """(node, its height) a slide that ends at (x, y, z) on column ``k``
        lands on: the highest walk sample at or below its height in the next
        column on the fall line or a neighbour (in air component ``acomp``
        when given), or the water there, unless the fall is lethal (17 m or
        more); None for none."""
        lv, NX = self.lv, self.lv.NX
        c_end = int(lv.col(x + self.fx[k] * CELL, y + self.fy[k] * CELL))
        best = None
        for dx in (0, 1, -1):
            for dy in (0, 1, -1):
                a, c = lookup(w.u, w.a, w.c, np.array([c_end + dx + dy * NX]))
                for q in range(int(c[0])):
                    j_ = int(a[0]) + q
                    if w.reg[j_] < 0 or w.z[j_] > z + 0.35 or w.z[j_] <= z - LETHAL_FALL_M:
                        continue
                    if acomp is not None and w.acomp[j_] != acomp:
                        continue
                    if best is None or w.z[j_] > best[1]:
                        best = (int(w.reg[j_]), float(w.z[j_]))
        if best is None and wg is not None and wg.n:
            lab, top = wg.at(np.array([c_end]), np.array([z - 30.0]), np.array([z + 0.35]))
            if lab[0] >= 0 and float(top[0]) > z - LETHAL_FALL_M:
                best = (w.nreg + int(lab[0]), float(top[0]))
        return best

    def top(self, w: Walk, k: int):
        """The walk region a slide through slope column ``k`` starts from:
        up the fall line to the slope's top, the region whose floor lies
        within 1 m of the face there (the highest), in the 3 x 3 columns at
        the top or the next one up; None for none."""
        lv, NX = self.lv, self.lv.NX
        x, y, z, kt, _ = self.follow(k, down=False)
        best = None
        for c in (int(self.sc[kt]), int(lv.col(x - self.fx[kt] * CELL, y - self.fy[kt] * CELL))):
            for dx in (0, 1, -1):
                for dy in (0, 1, -1):
                    a, n = lookup(w.u, w.a, w.c, np.array([c + dx + dy * NX]))
                    for q in range(int(n[0])):
                        j_ = int(a[0]) + q
                        if w.reg[j_] >= 0 and abs(w.z[j_] - z) <= 1.0 and (best is None or w.z[j_] > best[1]):
                            best = (int(w.reg[j_]), float(w.z[j_]))
        return None if best is None else best[0]


def slide_edges(lv: Level, w: Walk, slopes: Slopes, wg: WaterGrid | None, air=None, max_steps=600):
    """One-way slides down the :class:`Slopes`, frictionless along the fall
    line.  From each walk region beside a slide (its floor within 1 m of
    the slide's surface) the body follows the fall line (each column's own
    face, 0.5 m a step) until the slide ends, turns uphill or drops more
    than SLIDE_DROP_M (the body leaves the face); it lands as
    :meth:`Slopes.landing` says.  With ``air`` the landing shares the
    start's air component.  Steering is not used [proposal: the fall line
    only]."""
    if not len(slopes.sc):
        return {}
    sz, idx, NX = slopes.sz, slopes.idx, lv.NX
    starts = {}
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            nb = w.col + dx + dy * NX
            k = np.array([idx.get(int(c), -1) for c in nb.tolist()])
            ok = (k >= 0) & (w.reg >= 0)
            ok[ok] &= np.abs(w.z[ok] - sz[k[ok]]) <= 1.0
            for j_, kk in zip(np.nonzero(ok)[0].tolist(), k[ok].tolist()):
                r_ = int(w.reg[j_])
                if r_ not in starts or sz[kk] > starts[r_][1]:
                    starts[r_] = (kk, float(sz[kk]), j_)
    edges = {}
    for r_, (k0, z0, j0) in sorted(starts.items()):
        x, y, z, k, path = slopes.follow(k0, max_steps=max_steps)
        if path < 2 or z0 - z < 1.0:
            continue
        best = slopes.landing(w, wg, x, y, z, k, w.acomp[j0] if air is not None else None)
        if best is None or best[0] == r_:
            continue
        e = edges.get((r_, best[0]))
        dh = best[1] - z0
        if e is None or dh > e["dh"]:
            edges[(r_, best[0])] = {"kind": "slide", "conf": "modelled", "ranks": [0, 0, 0, 0], "dh": dh,
                                    "why": f"slide down a slippery slope ({path * CELL:.1f} m of fall line; frictionless at "
                                           f"g sin(theta), calib section 7)"}
    return edges


def rig_edges(lv: Level, w: Walk):
    """Lifts [inferred; probe-needed, class ``rig``]: a solid platform under a
    link-moved transform whose deck (faces with nz >= 0.8) is standable and
    whose movers carry it up or down level (:meth:`Level.lifts`: not a gear,
    axle or drum, nor a deck slid sideways; AZ-353) joins the walk regions
    over or beside the deck's footprint at different heights (a ride
    between its poses); ``Reach`` drops the guess where its decoded ride
    joins regions.  The motion range and what starts it
    are not decoded here; ``info`` lists each rig with its movers (names
    only)."""
    edges, info = {}, []
    up = lv.tri_nz >= envelope.STEP_NORMAL_Z
    cand = np.unique(lv.tri_owner[(lv.tri_cat == CAT_RIG) & up])
    for oi in cand.tolist():
        o = lv.owners[oi]
        t = np.nonzero((lv.tri_owner == oi) & up)[0]
        deck = float(lv.tri_area[t].sum())
        if not (RIG_DECK_M2[0] <= deck <= RIG_DECK_M2[1]) or not lv.lifts(oi):
            continue            # no deck, or nothing carries it up level (or only an undecoded mode)
        col = np.unique(raster(lv, t)[0])
        ring = range(-RIG_RING, RIG_RING + 1)
        cs = np.unique(np.concatenate([col + dx + dy * lv.NX for dx in ring for dy in ring]))
        a, c = lookup(w.u, w.a, w.c, cs)
        zs = collections.defaultdict(list)
        for k in range(w.mx):
            v = k < c
            s = (a + k)[v]
            r = w.reg_soft[s]
            for rr, zz in zip(r[r >= 0].tolist(), w.z[s][r >= 0].tolist()):
                zs[rr].append(zz)
        hz = {r: float(np.median(z)) for r, z in zs.items() if len(z) >= 3}
        movers, axes = lv.mover_of(oi)
        info.append({"oi": oi, "name": o["name"], "deck_m2": round(deck, 1), "movers": movers[:6], "axes": axes,
                     "regions": sorted(hz)})
        rs = sorted(hz)
        for ra in rs:
            for rb in rs:
                if ra != rb and 1.0 < abs(hz[ra] - hz[rb]) <= 40.0:
                    edges[(ra, rb)] = {"kind": "rig", "conf": "probe-needed", "ranks": [0, 0, 0, 0],
                                       "dh": hz[rb] - hz[ra], "via": o["name"],
                                       "why": f"ride {o['name']} (moved by {', '.join(movers[:3]) or '?'}; "
                                              f"its motion range and trigger are not decoded)"}
    return edges, info
