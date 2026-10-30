"""Reach's walkable floors and their regions.

The second stage of the reach model (Step R1.3a; reach v6, ``Walk``):
per profile, the span tops a body can stand on, eroded by the body
radius against walls, joined into regions where a body walks between
them.  The reach model builds two profiles (:data:`DERIVED`):

* ``logic``, the player tiers: a floor faces up at least
  ``STEP_NORMAL_Z`` (walk calls the step-up below 0.8), with 2.0 m of
  head room; rig decks, toggled solids (unless allowed), hazard solids
  and slippery faces steeper than :data:`SLIP_FLAT_NZ` (the body slides
  back down them: AZ-359) are no floor, and
  a body standing in a damage volume that is there is removed;
* ``phys``, R_phys's physical bound for the trap check: any landable
  face (nz > 0.6), 1.0 m of room, the s6 step-up of 0.65 m, rig decks at
  their rest pose, toggled and hazard solids and slippery faces.

A third, ``walk_game`` (Step TD.1), is guidance only: the trick explorer's
light trick graph (``l3_goal.TrickRouter``) costs its walks by it, and
the reach model never builds it, so no derived file depends on it: the
game's own walk, a non-slippery face steeper than the logic's floors
down to the slope state's 0.7071 (the jump 0x89060 takes the normal
branch at nz <= 0.7071; walk's friction and step-ups run above it), a
slippery one only at :data:`SLIP_FLAT_NZ`, the s6 step-up of 0.65 m and
rig decks at their rest pose (:func:`guidance_walk`).

A floor under more than ``wade`` m of water is a seabed (swum, not
walked); a shallower one is wading floor.  Authoring only (numpy, a
runtime dependency); coordinates stay in memory.
"""

from __future__ import annotations

import numpy as np

from azurkit.tools.randomizer.draft import envelope
from azurkit.tools.randomizer.draft.geometry import (
    BODY_R, CAT_RIG, CAT_TOGGLE, CELL, Level, Obstacles, Spans, Volumes, components)
from azurkit.tools.randomizer.art import collision

SLIP_FLAT_NZ = 0.998  # a slippery floor this flat is walked both ways (its own regions, joined to the others by
                      # `modelled` walk edges); a steeper one is no floor, only a one-way slide down it (moves.slide_edges)
                      # [verified L3, Step X.16: a 3 s walk up the fall line makes 1 m of headway in 81-100 % of the
                      # samples of each band from nz 0.998 up (w2, w1, town), 68 % at 0.995-0.998, under 20 % below (AZ-359)]
WALK_GAME_NZ = 0.7071  # the slope state's bound: the jump 0x89060 takes the normal branch at nz <= 0.7070999742 [verified
                       # static, RE_MOVEMENT "The contact rules"]; a non-slippery face steeper than it is walked in game
PROFILES = {
    # logic: the player tiers. Height 2.0 = 2 x radius x aspect 2.0 [inferred: how the sweep uses the aspect is
    # undecoded]; climb 0.35 [inferred: the walking step is unmeasured; anything higher is a `step` edge, a jump]
    "logic": {"floor_nz": envelope.STEP_NORMAL_Z, "height": 2.0, "climb": 0.35, "wade": 1.0,
              "rig_floor": False, "toggle_floor": False, "slippery": "flat", "hazard_floor": False,
              "tiers": ("safe", "standard", "hard", "frame_perfect")},
    # phys: R_phys. Any landable face, rig floors at rest pose, slippery; the s6 step-up 0.65 m
    "phys": {"floor_nz": envelope.LAND_NORMAL_Z, "height": 1.0, "climb": 0.65, "wade": 1.0,
             "rig_floor": True, "toggle_floor": True, "slippery": True, "hazard_floor": True,
             "tiers": ("phys",)},
    # walk_game (Step TD.1): the trick explorer's guidance only (never the derive's: DERIVED). The game's walk: any
    # non-slippery face over WALK_GAME_NZ, a slippery one at SLIP_FLAT_NZ, the s6 step-up, rig decks at rest pose
    "walk_game": {"floor_nz": WALK_GAME_NZ, "height": 2.0, "climb": 0.65, "wade": 1.0,
                  "rig_floor": True, "toggle_floor": False, "slippery": "flat", "hazard_floor": False,
                  "tiers": ("phys",)},
}
DERIVED = ("logic", "phys")   # the profiles the reach model builds (its zones, edges and exports read only these)


def csr(cols):
    """(unique columns, start, count, largest count) of a column-sorted array."""
    u, a, c = np.unique(cols, return_index=True, return_counts=True)
    return u, a, c, (int(c.max()) if len(c) else 0)


def lookup(u, a, c, cols):
    """(start, count) of each column in a :func:`csr` index (count 0 where absent)."""
    if not len(u):
        z = np.zeros(len(cols), dtype=np.int64)
        return z, z
    k = np.minimum(np.searchsorted(u, cols), len(u) - 1)
    hit = u[k] == cols
    return np.where(hit, a[k], 0), np.where(hit, c[k], 0)


class Walk:
    """The walkable samples (one per span top that qualifies, sorted by
    column) and their regions for one profile and one solid-span state.

    ``reg`` numbers the regions by size (largest first; a tie goes to the
    one with the lower first sample); an eroded sample has -1 and adopts an
    adjacent region in ``reg_soft`` (for anchors and items near walls).
    ``cross`` lists the region pairs a walk joins across a slippery /
    plain floor boundary.  ``toggle_ok`` names toggled solids that are
    floors in this state (the logic profile's other toggled solids are
    not)."""

    def __init__(self, lv: Level, spans: Spans, prof: str, water: Volumes, damage_oids, damage_vol: Volumes | None,
                 obst: Obstacles, toggle_ok=None):
        p = PROFILES[prof]
        self.prof, self.p, self.lv = prof, p, lv
        s = spans
        tt = s.toptri
        cat, nz, word, own = lv.tri_cat[tt], lv.tri_nz[tt], lv.tri_word[tt], lv.tri_owner[tt]
        hazard = np.array([o.get("hazard", False) for o in lv.owners], dtype=bool)
        ok = nz >= p["floor_nz"]
        if not p["rig_floor"]:
            ok &= cat != CAT_RIG
        if not p["toggle_floor"]:
            ok &= (cat != CAT_TOGGLE) | (np.isin(own, list(toggle_ok)) if toggle_ok else False)
        slip_all = (word & collision.W_SLIPPERY) != 0
        if p["slippery"] is False:
            ok &= ~slip_all
        elif p["slippery"] == "flat":
            ok &= ~slip_all | (nz >= SLIP_FLAT_NZ)
        if not p["hazard_floor"]:
            ok &= ~hazard[own]
        same_next = np.concatenate((s.col[1:] == s.col[:-1], [False]))
        ceil = np.where(same_next, np.concatenate((s.bot[1:], [np.inf])), np.inf)
        ok &= (ceil - s.top) >= p["height"]
        idx = np.nonzero(ok)[0]
        col, z, ceil = s.col[idx], s.top[idx].astype(np.float64), ceil[idx]
        top_owner = own[idx]
        slip = slip_all[idx] if p["slippery"] == "flat" else np.zeros(len(idx), dtype=bool)
        # water: deep -> a seabed (swum, not walked); shallow -> wading floor
        wown, wtop = water.query(col, z - 0.05, z)
        deep = (wown >= 0) & (wtop - z > p["wade"])
        self.seabed = {"col": col[deep], "z": z[deep], "water": wown[deep]}
        wading = (wown >= 0) & ~deep
        # a damage volume there in this state: the body stands in it -> a hazard sample (removed for logic)
        hz = np.zeros(len(col), dtype=bool)
        hazard_owner = np.full(len(col), -1, dtype=np.int64)
        if damage_vol is not None and len(damage_oids):
            hazard_owner, _ = damage_vol.query(col, z, z + p["height"], owners=np.array(list(damage_oids)))
            hz = hazard_owner >= 0
        keep = ~deep & (~hz if prof == "logic" else np.ones(len(col), dtype=bool))
        gone = ~deep & hz & ~keep
        self.hz_col, self.hz_z, self.hz_ceil, self.hz_own = col[gone], z[gone], ceil[gone], hazard_owner[gone]
        self.removed_hazard = int((hz & ~deep).sum()) if prof == "logic" else 0
        self.col, self.z, self.ceil = col[keep], z[keep], ceil[keep]
        self.sidx = idx[keep]                 # the span each sample stands on (its air gap is that span's: Air)
        self.top_owner, self.wading, self.slip = top_owner[keep], wading[keep], slip[keep]
        self.hazard_owner = hazard_owner[keep]
        n = len(self.col)
        # erosion against walls: a non-floor solid piece within the body radius (XY) of the sample centre, in the
        # body band (climb .. height), in its own or an 8-neighbour column
        NX = lv.NX
        ix = self.col % NX
        cx, cy = lv.cxy(self.col)
        band = min(p["height"], 2.0)
        wall = np.zeros(n, dtype=bool)
        lo_b, hi_b = self.z + p["climb"], self.z + band
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nix = ix + dx
                q = np.nonzero((nix >= 0) & (nix < NX) & ~wall)[0]
                hit = obst.near(self.col[q] + dx + dy * NX, cx[q], cy[q], lo_b[q], hi_b[q], BODY_R)
                wall[q[hit]] = True
        self.eroded = wall
        # connections to the 4 forward neighbours (+x, +y and both diagonals; undirected): within the walking step,
        # with the body's height of shared room; across a slippery / plain boundary they are `cross` links
        u, a, c, mx = csr(self.col)
        ei, ej, xi, xj = [], [], [], []
        conn = np.zeros(n, dtype=np.int8)
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            valid = (ix + dx < NX) & ~wall
            aa, cc = lookup(u, a, c, np.where(valid, self.col + dx + dy * NX, -1))
            for k in range(mx):
                v = valid & (k < cc)
                j = np.where(v, aa + k, 0)
                ok = v & ~wall[j] & (np.abs(self.z[j] - self.z) <= p["climb"]) & \
                    ((np.minimum(self.ceil, self.ceil[j]) - np.maximum(self.z, self.z[j])) >= p["height"])
                same = self.slip == self.slip[j]
                ii = np.nonzero(ok & same)[0]
                ei.append(ii)
                ej.append(j[ii])
                ii = np.nonzero(ok & ~same)[0]
                xi.append(ii)
                xj.append(j[ii])
        ei, ej, xi, xj = (np.concatenate(x) if x else np.zeros(0, dtype=np.int64) for x in (ei, ej, xi, xj))
        for x in (ei, ej, xi, xj):
            np.add.at(conn, x, 1)
        self.conn = conn
        self.links, self.xlinks = (ei, ej), (xi, xj)     # the sample links (the route planner walks them)
        lab = np.where(wall, -1, components(n, ei, ej))
        good = lab >= 0
        cnt = np.bincount(lab[good], minlength=lab.max() + 1 if n else 0)
        first = np.full(len(cnt), n, dtype=np.int64)
        np.minimum.at(first, lab[good], np.nonzero(good)[0])
        present = np.nonzero(cnt)[0]
        order = present[np.lexsort((first[present], -cnt[present]))]
        remap = np.full(len(cnt), -1, dtype=np.int64)
        remap[order] = np.arange(len(order))
        self.reg = np.where(good, remap[np.maximum(lab, 0)], -1)
        self.nreg = len(order)
        self.reg_count = np.bincount(self.reg[self.reg >= 0], minlength=self.nreg)
        self.reg_soft = self.reg.copy()
        for _ in range(2):
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                valid = (ix + dx >= 0) & (ix + dx < NX) & (self.reg_soft < 0)
                aa, cc = lookup(u, a, c, np.where(valid, self.col + dx + dy * NX, -1))
                for k in range(mx):
                    v = valid & (k < cc) & (self.reg_soft < 0)
                    j = np.where(v, aa + k, 0)
                    ok = v & (self.reg_soft[j] >= 0) & (np.abs(self.z[j] - self.z) <= p["climb"])
                    self.reg_soft = np.where(ok, self.reg_soft[j], self.reg_soft)
        self.border = (~wall) & (conn < 8)
        ra, rb = self.reg[xi], self.reg[xj]
        m = (ra >= 0) & (rb >= 0) & (ra != rb)
        self.cross = sorted(set(zip(ra[m].tolist(), rb[m].tolist())))
        self.reg_slip = np.zeros(self.nreg, dtype=bool)
        if self.nreg:
            self.reg_slip[self.reg[(self.reg >= 0) & self.slip]] = True
        self.u, self.a, self.c, self.mx = u, a, c, mx
        self.x, self.y = lv.cxy(self.col)

    def area(self, r: int) -> float:
        return float(self.reg_count[r]) * CELL * CELL


def guidance_walk(reach, prof: str = "walk_game") -> Walk:
    """A built reach model's floors under a guidance profile (``walk_game``): its spans, water, damage and
    obstacles as the reach model's own profiles use them (Step TD.1; the reach model keeps no such walk)."""
    obst = Obstacles(reach.lv, reach.pairs, reach.pmask, PROFILES[prof]["floor_nz"])
    return Walk(reach.lv, reach.spans, prof, reach.water_vol, reach.dmg_present, reach.damage_vol, obst)
