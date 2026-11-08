"""The reach engine's nodes and takeoffs (Step R2.16a; the R2.16 design §2a), from a level's reach model.

Nodes: the game's walkable regions (``floors.walk_game``: a non-slippery face over nz 0.7071, a slippery one at
``SLIP_FLAT_NZ``, the s6 step-up, rig decks at rest pose: the walk the game does, wider than the logic's nz 0.8),
the R_phys profile's regions for any other landable floor (slides, steep and slippery faces, toggled solids), the
swim regions, and the volumes a body centre touches (the trigger, push and damage meshes, :class:`faces.Volumes`;
a pickup's point within :data:`PICK_M`).  A node's key is ``<level>/<profile>/<sha12>``, the sha256 of its sorted
cells (column and height to a quarter metre): it stays the same across derive versions that keep those cells.

Takeoffs: the boundary samples (the walk's ``border``: fewer than 8 linked neighbours) of every walkable region of
at least ``min_area``, one per ``spacing`` square of each region (the sample nearest its bin's mean), with the
outward normal (the sum of the directions to the 8 neighbour columns the region doesn't continue into, summed
over the bin), as a game heading.  A start for a heading stands ``back`` metres behind the takeoff on the same
region's floor, or where that column has none, over a floor face of the level (:class:`Faces`: the 0.5 m raster's
column may hold a floor the point itself is off, so L3's body placed there falls through, Step R2.16b's diagnosis)
on the takeoff's region or in its zone, at the nearest such point within :data:`SEARCH_M` (:meth:`Nodes.starts`);
an aim's target is moved onto its floor face the same way (:meth:`Nodes.snap`).  Each takeoff's cells (rooms) to place it in, nearest location first (:meth:`Nodes.cells`:
R6 keeps the player in the cell it names, AZ-382, AZ-488).

Positions stay in memory or the private cache: nothing here prints one.  Authoring only (numpy).
"""

from __future__ import annotations

import hashlib
import json
import math
import types
from typing import NamedTuple

import numpy as np

from devkit.rando.draft import route as rt
from azurkit.tools.randomizer.draft.floors import guidance_walk, lookup
from azurkit.tools.randomizer.draft.geometry import (CAT_DAMAGE, CAT_NAME, CAT_PUSH, CAT_RIG, CAT_TOGGLE,
                                                  CAT_TRIGGER, CELL, SOLID_CATS)

SPACING_M = 2.0       # [default, the design's R0] a takeoff every this many metres of a region's boundary
MIN_AREA_M2 = 4.0     # [default] a region smaller than this takes off from nowhere (it is still a landing)
PICK_M = 1.5          # [proposal] a body centre this near a pickup's point touches it (the touch is 1 m round the
                      # body centre, [0x1980BC]; the item's own radius on top, unread here)
SWIMMING = 6
FACE_NZ, FACE_DZ = 0.6, 0.6   # an upward face this flat or flatter (steeper is a wall, 0x8C12F) within this of a
                              # point's height is the floor under it (R2.16b's diagnosis: L3 stands on 91 of 94)
SEARCH_M = 0.75       # [proposal] a start off its floor face moves to the nearest point this near over one (the
                      # diagnosis's B2: 4 of 5 dropped aims' starts stood)
GRID_M = 0.25         # [proposal] the grid those points are on
SNAP_M, SNAP_IN_M = 2.0, 0.5  # [proposal] an aim's target off its floor face moves to the nearest point this near,
                              # this far inside its face all round, in its to-zone (the diagnosis's A)
_DIRS = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))


def _rings(r: float) -> list[tuple[float, float]]:
    """The :data:`GRID_M` grid's offsets within ``r`` metres, nearest first."""
    n = int(r / GRID_M)
    offs = [(i * GRID_M, j * GRID_M) for i in range(-n, n + 1) for j in range(-n, n + 1)
            if math.hypot(i, j) * GRID_M <= r + 1e-9]
    return sorted(offs, key=lambda o: (math.hypot(*o), o))


class Faces:
    """A level's floor faces: the upward faces (nz over :data:`FACE_NZ`) of its solid owners present at load
    (``geometry.SOLID_CATS``), on a 1 m grid; :meth:`floor_z` the height of the one under a point."""

    def __init__(self, lv) -> None:
        present = np.array([bool(o["present"]) for o in lv.owners] or [False])
        ok = np.isin(lv.tri_cat, SOLID_CATS) & (lv.tri_nz > FACE_NZ) & present[lv.tri_owner]
        self.T = T = np.asarray(lv.P[ok], dtype=np.float64)
        lo, hi = np.floor(T[:, :, :2].min(1)).astype(np.int64), np.floor(T[:, :, :2].max(1)).astype(np.int64)
        grid: dict[tuple[int, int], list[int]] = {}
        for k in range(len(T)):
            for gx in range(lo[k, 0], hi[k, 0] + 1):
                for gy in range(lo[k, 1], hi[k, 1] + 1):
                    grid.setdefault((gx, gy), []).append(k)
        self.grid = {key: np.asarray(v, dtype=np.int64) for key, v in grid.items()}

    def floor_z(self, x: float, y: float, z: float, dz: float = FACE_DZ) -> float | None:
        """The height of the floor face under (``x``, ``y``) nearest ``z``, within ``dz`` of it; None for none."""
        ks = self.grid.get((math.floor(x), math.floor(y)))
        if ks is None:
            return None
        a, b, c = self.T[ks, 0], self.T[ks, 1], self.T[ks, 2]
        v0, v1 = b - a, c - a
        d = v0[:, 0] * v1[:, 1] - v0[:, 1] * v1[:, 0]
        px, py = x - a[:, 0], y - a[:, 1]
        with np.errstate(divide="ignore", invalid="ignore"):
            u = (px * v1[:, 1] - py * v1[:, 0]) / d
            v = (v0[:, 0] * py - v0[:, 1] * px) / d
        zf = a[:, 2] + u * v0[:, 2] + v * v1[:, 2]
        ok = (np.abs(d) > 1e-12) & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (np.abs(zf - z) <= dz)
        return float(zf[ok][np.argmin(np.abs(zf[ok] - z))]) if ok.any() else None


class Takeoff(NamedTuple):
    """A boundary sample of a walkable region: its index in the takeoff list, its walk sample, its region, its
    feet (private), the outward normal as a game heading (it faces (-sin h, cos h)), and the cells (rooms) to
    place a start in, nearest location first."""
    i: int
    sample: int
    region: int
    feet: tuple[float, float, float]
    heading: float
    cells: tuple[int, ...]


def _region_keys(level: str, prof: str, col, z, reg, n: int) -> list[str]:
    """Each region's key: ``<level>/<prof>/`` and the sha256[:12] of its cells (column, height in quarter metres)
    sorted."""
    ok = reg >= 0
    c, zq, r = col[ok].astype(np.int64), np.round(np.asarray(z)[ok] * 4).astype(np.int64), reg[ok].astype(np.int64)
    o = np.lexsort((zq, c, r))
    c, zq, r = c[o], zq[o], r[o]
    cuts = np.searchsorted(r, np.arange(n + 1))
    out = []
    for k in range(n):
        a, b = cuts[k], cuts[k + 1]
        out.append(f"{level}/{prof}/" + hashlib.sha256(np.stack([c[a:b], zq[a:b]], 1).astype("<i8").tobytes())
                   .hexdigest()[:12])
    return out


class Nodes:
    """A level's nodes and takeoffs over its reach model ``reach`` (``reach.Reach``, built or unpickled): ``walk``
    the walk_game floors, ``phys`` and ``logic`` the model's own profiles, ``wg`` its swim water.  :meth:`node_at`
    and :meth:`zone_at` name where a body's feet are (it borrows ``Router.locate`` and ``Router.zone_at``, which
    read ``R``, ``lv``, ``wg`` and ``w``)."""

    locate = rt.Router.locate
    zone_at = rt.Router.zone_at

    def __init__(self, reach) -> None:
        self.R, self.lv, self.wg, self.level = reach, reach.lv, reach.wg, reach.name
        self.walk = self.w = guidance_walk(reach)
        self.phys, self.logic = reach.W["phys"], reach.W["logic"]
        w, p = self.walk, self.phys
        self.keys = {"walk_game": _region_keys(self.level, "walk_game", w.col, w.z, w.reg, w.nreg),
                     "phys": _region_keys(self.level, "phys", p.col, p.z, p.reg, p.nreg)}
        wg = self.wg
        self.keys["water"] = (_region_keys(self.level, "water", wg.col, wg.lo, wg.lab, wg.n)
                              if len(getattr(wg, "col", ())) else [])
        cat = np.array([o["cat"] for o in self.lv.owners], dtype=np.int64)
        self.frozen: dict[str, str] = {}      # node key -> why its floor is the snapshot's frozen world
        for prof, walk in (("walk_game", w), ("phys", p)):
            for c, why in ((CAT_RIG, "a rig deck at its rest pose"), (CAT_TOGGLE, "a toggled solid as loaded")):
                hit = (cat[walk.top_owner] == c) & (walk.reg >= 0)
                for r in np.unique(walk.reg[hit]).tolist():
                    self.frozen.setdefault(self.keys[prof][r], why)
        self._locs = self._faces = None

    # -- where a body is --
    def node_at(self, feet, state: int) -> str | None:
        """The node a body's feet are on (state ``state``, entity+0x94): the walkable region (``Router.locate``,
        1.0 m under to 0.5 m over the feet), else the water holding it (first for a swimmer), else R_phys's floor
        region; None in the air or on no floor."""
        ns = len(self.walk.col)
        v = self.locate(feet, state == SWIMMING, self.walk, False)
        if 0 <= v < ns and self.walk.reg_soft[v] >= 0:
            return self.keys["walk_game"][int(self.walk.reg_soft[v])]
        if v >= ns and self.wg.lab[v - ns] >= 0 and self.keys["water"]:
            return self.keys["water"][int(self.wg.lab[v - ns])]
        q = self.locate(feet, False, self.phys, False)
        if 0 <= q < len(self.phys.col) and self.phys.reg_soft[q] >= 0:
            return self.keys["phys"][int(self.phys.reg_soft[q])]
        return None

    def zone_gap(self, feet, swim: bool = False) -> float | None:
        """How far (m, across) the logic's floor sample that names a body's zone (``Router.zone_at``) lies from its
        feet (0 for water), None off every zone: over half a metre, the zone is a neighbouring column's."""
        lw = self.logic
        v = self.locate(feet, swim, lw, False)
        if v < 0:
            return None
        return 0.0 if v >= len(lw.col) else float(math.hypot(lw.x[v] - feet[0], lw.y[v] - feet[1]))

    @property
    def faces(self) -> Faces:
        if self._faces is None:
            self._faces = Faces(self.lv)
        return self._faces

    def snap(self, p, zone: str | None) -> tuple[float, float, float] | None:
        """An aim's target ``p`` on its floor: ``p`` when a floor face lies under it (at the face's height), else
        the nearest point within :data:`SNAP_M` (the :data:`GRID_M` grid) over a face :data:`SNAP_IN_M` inside it
        all round, in ``zone``; None for none."""
        fz = self.faces.floor_z
        if (z := fz(p[0], p[1], p[2])) is not None:
            return p[0], p[1], z
        for ox, oy in _rings(SNAP_M):
            x, y = p[0] + ox, p[1] + oy
            if (z := fz(x, y, p[2])) is None or self.zone_at((x, y, z), False, False) != zone:
                continue
            if all(fz(x + a, y + b, z) is not None for a, b in ((SNAP_IN_M, 0), (-SNAP_IN_M, 0), (0, SNAP_IN_M),
                                                                (0, -SNAP_IN_M))):
                return x, y, z
        return None

    def floor_near(self, p, zone: str | None) -> bool:
        """Whether a floor face of ``zone`` lies within :data:`SNAP_M` of ``p`` across (the :data:`GRID_M` grid), at
        its height (:data:`FACE_DZ`)."""
        fz = self.faces.floor_z
        return any((z := fz(p[0] + ox, p[1] + oy, p[2])) is not None
                   and self.zone_at((p[0] + ox, p[1] + oy, z), False, False) == zone for ox, oy in _rings(SNAP_M))

    def region_key(self, region: int) -> str:
        return self.keys["walk_game"][region]

    def region_at(self, feet) -> int | None:
        """The walkable region (its index) a standing body's feet are on, None for none."""
        v = self.locate(feet, False, self.walk, False)
        return int(self.walk.reg_soft[v]) if 0 <= v < len(self.walk.col) and self.walk.reg_soft[v] >= 0 else None

    # -- takeoffs --
    def _raw_normals(self, idx: np.ndarray) -> np.ndarray:
        """Per walk sample of ``idx``, the sum of the unit directions to the 8 neighbour columns holding no sample
        of its region within the step-up (the floor doesn't go on that way)."""
        w, NX = self.walk, self.lv.NX
        climb = w.p["climb"]
        ix = w.col[idx] % NX
        out = np.zeros((len(idx), 2))
        for dx, dy in _DIRS:
            valid = (ix + dx >= 0) & (ix + dx < NX)
            a, c = lookup(w.u, w.a, w.c, np.where(valid, w.col[idx] + dx + dy * NX, -1))
            has = np.zeros(len(idx), dtype=bool)
            for k in range(w.mx):
                v = valid & (k < c)
                j = np.where(v, a + k, 0)
                has |= v & (w.reg_soft[j] == w.reg_soft[idx]) & (np.abs(w.z[j] - w.z[idx]) <= climb)
            n = math.hypot(dx, dy)
            out[~has] += (dx / n, dy / n)
        return out

    def takeoffs(self, spacing: float = SPACING_M, min_area: float = MIN_AREA_M2,
                 regions: set[int] | None = None) -> list[Takeoff]:
        """The takeoffs (the module docstring), of ``regions`` only when given (walk_game region indices)."""
        w = self.walk
        area = w.reg_count * CELL * CELL
        ok = w.border & (w.reg >= 0)
        ok &= area[np.maximum(w.reg, 0)] >= min_area
        if regions is not None:
            ok &= np.isin(w.reg, sorted(regions))
        idx = np.nonzero(ok)[0]
        if not len(idx):
            return []
        raw = self._raw_normals(idx)
        bx, by = np.floor(w.x[idx] / spacing).astype(np.int64), np.floor(w.y[idx] / spacing).astype(np.int64)
        bz = np.floor(w.z[idx] / 2.0).astype(np.int64)
        o = np.lexsort((idx, bz, by, bx, w.reg[idx]))
        keys = np.stack([w.reg[idx], bx, by, bz], 1)[o]
        head = np.concatenate(([True], (keys[1:] != keys[:-1]).any(1)))
        starts = np.nonzero(head)[0].tolist() + [len(o)]
        picks = []
        for a, b in zip(starts[:-1], starts[1:]):
            m = o[a:b]
            n = raw[m].sum(0)
            if math.hypot(*n) < 1e-6:
                continue                    # a sliver open on both sides alike: no outward way
            mx, my = w.x[idx[m]].mean(), w.y[idx[m]].mean()
            j = m[int(np.argmin(np.hypot(w.x[idx[m]] - mx, w.y[idx[m]] - my)))]
            picks.append((int(idx[j]), math.atan2(-n[0], n[1])))
        cells = self.cells([(float(w.x[s]), float(w.y[s]), float(w.z[s])) for s, _ in picks])
        return [Takeoff(k, s, int(w.reg[s]), (float(w.x[s]), float(w.y[s]), float(w.z[s])), h, tuple(c))
                for k, ((s, h), c) in enumerate(zip(picks, cells))]

    def starts(self, t: Takeoff, heading: float, backs, zone: str | None = None) -> list[tuple[float, float, float]]:
        """The feet ``back`` metres behind takeoff ``t`` along ``heading``, for each of ``backs`` in order: R0's
        point (where the region's raster has its floor in that column) when a floor face lies under it, else the
        point over a floor face within the step-up of the takeoff's height, on its region or in ``zone`` (by
        default the takeoff's), or the nearest such point within :data:`SEARCH_M`; then the other of the two;
        else the takeoff's own feet.  So R0's start stays where it stands on a face, and one that would fall
        through or lose its run-up moves onto the face."""
        zone = self.zone_at(t.feet, False, False) if zone is None else zone
        dx, dy = -math.sin(heading), math.cos(heading)
        firsts, rest = [], []
        for b in backs:
            p = (t.feet[0] - b * dx, t.feet[1] - b * dy)
            r, f = self._raster_start(t, p), self._face_start(t, p, zone)
            on = r is not None and self.faces.floor_z(*r) is not None
            firsts.append(r if on or f is None else f)
            rest.append(f if on else r)
        out = []
        for f in firsts + rest:
            if f is not None and f not in out:
                out.append(f)
        return out or [t.feet]

    def _raster_start(self, t: Takeoff, p) -> tuple[float, float, float] | None:
        w = self.walk
        a, c = lookup(w.u, w.a, w.c, np.array([int(self.lv.col(*p))]))
        js = np.arange(int(a[0]), int(a[0]) + int(c[0]))
        js = js[(w.reg_soft[js] == t.region) & (np.abs(w.z[js] - t.feet[2]) <= w.p["climb"])] if len(js) else js
        return (float(p[0]), float(p[1]), float(w.z[js[np.argmin(np.abs(w.z[js] - t.feet[2]))]])) if len(js) else None

    def _face_start(self, t: Takeoff, p, zone) -> tuple[float, float, float] | None:
        fz, climb = self.faces.floor_z, self.walk.p["climb"]
        for ox, oy in _rings(SEARCH_M):
            x, y = p[0] + ox, p[1] + oy
            if (z := fz(x, y, t.feet[2], climb)) is None:
                continue
            f = (float(x), float(y), z)
            if self.region_at(f) == t.region or (zone is not None and self.zone_at(f, False, False) == zone):
                return f
        return None

    def cells(self, points) -> list[list[int]]:
        """For each point the level's cells (indices into its list, the world's cell array R6's place struct
        names) by the nearest location standing in each (the generated file's ``cells`` and locations, at their
        points on the level's mesh), then the cells no location stands in, in list order."""
        if self._locs is None:
            doc = json.loads(_generated(self.level))
            self._cells = doc.get("cells") or ["default cell"]
            at = []
            for x in doc.get("locations", ()):
                if x.get("cell") in self._cells:
                    try:
                        q = np.asarray(self.lv.rec_points(x["id"])[0], dtype=float).reshape(-1, 3)
                    except (KeyError, IndexError, ValueError, AttributeError):
                        continue
                    at += [(self._cells.index(x["cell"]), q)]
            self._locs = at
        out = []
        for p in points:
            near: dict[int, float] = {}
            for c, q in self._locs:
                near[c] = min(near.get(c, math.inf), float(np.min(np.linalg.norm(q - np.asarray(p), axis=1))))
            out.append(sorted(range(len(self._cells)), key=lambda c: (near.get(c, math.inf), c)))
        return out

    # -- what a body touches on the way (the workers' copy, private) --
    def targets(self) -> dict:
        """The volumes and pickups a body centre may touch, as plain arrays for the workers (private: they hold
        positions): each trigger, push and damage owner's mesh (``faces.Volumes``: its id the lowest face id, its
        category's name) and each location's point (its id)."""
        from devkit.sim.faces import Volumes
        lv = self.lv
        vols = Volumes.of_level(lv)
        cats = {int(np.min(t)): CAT_NAME[o["cat"]] for oi, o in enumerate(lv.owners)
                if o["cat"] in (CAT_DAMAGE, CAT_PUSH, CAT_TRIGGER) and len(t := lv.tris_of(oi))}
        picks = []
        for x in json.loads(_generated(self.level)).get("locations", ()):
            try:
                q = np.asarray(lv.rec_points(x["id"])[0], dtype=float).reshape(-1, 3)
            except (KeyError, IndexError, ValueError, AttributeError):
                continue
            if len(q):
                picks.append((x["id"], q[0].tolist()))
        return {"V": [v.tolist() for v in vols.V], "ids": vols.ids, "cats": [cats.get(i, "?") for i in vols.ids],
                "picks": picks}


def _slim(obj, keys):
    """A bare copy of ``obj`` (its class, no ``__init__``) holding only its attributes ``keys``."""
    out = object.__new__(type(obj))
    out.__dict__.update({k: getattr(obj, k) for k in keys if hasattr(obj, k)})
    return out


class Zones:
    """The logic's zones alone, for a pool's workers: what ``Router.zone_at`` reads (the logic walk's samples, the
    swim water, the column grid, each region's zone) and nothing else, so it pickles small (w1: about 0.3 GB
    against 4 GB for a built :class:`Nodes`) and names a body's zone as :meth:`Nodes.zone_at` does."""

    locate = rt.Router.locate
    zone_at = rt.Router.zone_at

    def __init__(self, nodes: Nodes) -> None:
        self.w = _slim(nodes.logic, ("u", "a", "c", "x", "y", "z", "reg_soft", "eroded", "col", "nreg"))
        self.wg = _slim(nodes.wg, ("col", "lab", "lo", "hi", "ucol", "ustart", "ucount", "n"))
        self.lv = _slim(nodes.lv, ("x0", "y0", "NX"))
        self.R = types.SimpleNamespace(zone_of=getattr(nodes.R, "zone_of", None), W={"logic": self.w},
                                       name=nodes.R.name)


def _generated(level: str) -> str:
    """The level's generated file's text; ``{}`` for a level that has none (a hand-built mesh: one cell)."""
    from azurkit.tools.randomizer.planner.loader import DATA_DIR
    p = DATA_DIR / "generated" / f"{level}.json"
    return p.read_text(encoding="utf-8") if p.is_file() else "{}"
