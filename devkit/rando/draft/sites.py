"""The trick explorer's site miner and surface census (Step TD.4, D253; the trick-discovery plan §3.4 and §3.6).

One permissive rule for every level, on the game's own contact thresholds (``docs/RE_MOVEMENT.md`` "The contact
rules"); nothing here names a level or a site.

**Surface classes** (:func:`surface`: each solid face there at load; a face may be in several): ``wall`` (nz <= 0.6,
not climbable: no landing, the contact projects the velocity), ``slope`` (0.6 < nz <= 0.7071, not slippery: state
3/4, a jump along the normal), ``slide`` (slippery under :data:`~.floors.SLIP_FLAT_NZ`: the same, state 4 keeps its
speed), ``steep`` (0.7071 < nz < 0.8, not slippery: the game walks it, the logic doesn't), ``rim`` (0.8 <= nz <
0.87, not slippery: the logic walks it; bodies slid off such rims), ``floor`` (the other faces over 0.6), ``climb``
(climbable and not slippery, the catch's (word & 3) == 2, at |nz| < 0.2588), ``spring`` (autoSpring), ``rig`` (a
moving solid), ``thin`` (an upright wall with nothing solid :data:`THIN_M` behind it and a floor there within
:data:`STAND_M` under its lower part: a body there passes it from behind; the outer shell, with no floor behind it,
isn't) and ``open`` (a wall whose top edge no other solid face shares: an open wall top).

**Sites** (:func:`mine`): ``slope``, ``slide`` and ``steep`` patches (the class's faces joined by shared edges, at
least :data:`PATCH_M2`); ``climb`` columns (climbable patches at least :data:`CLIMB_M` tall, every rim edge kept,
no back-wall test); ``lip`` (a wall patch whose top edge a floor face above shares, from the step-up to the kit's
apex plus the rim step-up tall); ``thin`` and ``open`` patches (thin walls and open edges); ``trigger`` (an exit's
touch mesh with a point a straight path of :data:`FAR` m leaves crossing no solid face, with no floor
:data:`STAND_M` under it: it pokes out into open air and is reached only through it, the evidence's itrig scan's
``void_only``); ``speed`` (a spring patch, a push volume, a rig); ``oob`` (a phys floor region no logic floor lies
in: outside every zone, the out-of-bounds tops among them).  Each site's id is ``<level>.<class>.<n>``: patches,
lips and speed sources numbered in the order of their lowest faces, triggers in their exits' id order, off-zone
regions in phys-region order; never by value.

:func:`census` counts each class's faces, m² and share of the solid area, the faces an exploration touched (the
explorer's per-tick face record: ``l3_explore.Result.touched``), those touched in the class's state
(:data:`IN_STATE`) and those a find used; per site class the sites, their m² (a volume's mesh area too), the share
of the solid area their solid faces (an off-zone region's floor) make and the sites tried (a face touched, a volume
entered: ``Result.entered``; runs with no volume record leave a site with no solid face ``unmeasured``); and the
level's exits, those with no logic way in at the kit, and of each those reached (a touch mesh's face touched or
entered).  :func:`probes` lists the logic edges an exploration never reproduced out of a zone it saturated (a probe
list, never a refutation).  Public: ids, counts, m², heights and shares; faces and points stay in memory.
"""

from __future__ import annotations

import collections
import types
from dataclasses import dataclass

import numpy as np

from azurkit.tools.randomizer.draft import envelope
from devkit.rando.draft.flights import RIM_LIFT
from azurkit.tools.randomizer.draft.floors import SLIP_FLAT_NZ, WALK_GAME_NZ, lookup
from azurkit.tools.randomizer.draft.geometry import CAT_PUSH, CAT_RIG, CELL, SOLID_CATS, RadiusIndex, components, raster
from devkit.rando.draft.l3_goal import KIT_NAMES, OneSided, inside_mesh
from azurkit.tools.randomizer.art import collision

RIM_NZ = 0.87            # [sitting note] bodies slid off f6 and e2 rims to about this
CLIMB_NZ = 0.2588        # the catch's |nz| bound (0x87120)
CLIMB_M = 3.0            # [proposal] a climb column's least height
PATCH_M2 = 1.0           # [proposal] a slope, slide, steep or thin patch's least area
OOB_M2 = 4.0             # [proposal] an off-zone floor region's least area
THIN_M = 1.0             # [proposal] a wall with nothing solid this far behind it is thin (the body's width)
STEP_M = 0.65            # the s6 step-up: a lip is taller than it
APEX = (1.024, 2.24, 2.372, 2.395)   # [verified] flights.Env's phys apex per air level, without a reach model's
FAR, CAP, GRID = 60.0, 120, 0.5      # a trigger's paths (m), its most sampled points, their grid (m)
STAND_M = 3.4            # a body centre this far over a floor can stand or jump there (the itrig scan's)
POINTS = 8               # [proposal] each site's anchor points (face centroids; in memory)
ROUND = 100.0            # vertices are joined at 1 cm
SURFACE = ("wall", "slope", "slide", "steep", "rim", "floor", "climb", "spring", "rig", "thin", "open")
SITES = ("slope", "slide", "steep", "climb", "lip", "thin", "open", "trigger", "speed", "oob")
ANY = frozenset({"ground", "slope", "slide", "air", "catch", "climb", "swim", "0x100", "other"})
IN_STATE = {"wall": {"air"}, "slope": {"slope", "slide"}, "slide": {"slope", "slide"}, "steep": {"ground"},
            "rim": {"slope", "slide"}, "floor": {"ground"}, "climb": {"catch", "climb"}, "spring": ANY,
            "rig": ANY, "thin": ANY, "open": ANY}
"""The explorer's state classes (``l3_explore.CLASS``) that matter on each surface class."""


@dataclass
class Site:
    """A mined site: ``id``, ``cls``, its faces (indices into the level's triangles; private), m², height (m: its
    faces' z extent, an off-zone region's samples'), up to :data:`POINTS` anchor points (private) and, for a
    trigger, the share of its open-air points with no floor under them (``void``); an off-zone region's phys floor
    region (``region``: the explorer's ``R<n>`` key)."""
    id: str
    cls: str
    faces: np.ndarray
    m2: float
    height: float
    points: np.ndarray
    void: float | None = None
    region: int | None = None

    def public(self) -> dict:
        return {"id": self.id, "class": self.cls, "faces": int(len(self.faces)), "m2": round(self.m2, 1),
                "height_m": round(self.height, 2), **({"void_share": round(self.void, 3)} if self.void is not None
                                                      else {})}


def _solid(lv, present) -> np.ndarray:
    return np.isin(lv.tri_cat, SOLID_CATS) & np.asarray(present, dtype=bool)[lv.tri_owner]


def _normals(lv) -> np.ndarray:
    n = np.cross(lv.P[:, 1] - lv.P[:, 0], lv.P[:, 2] - lv.P[:, 0])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def _edges(lv, idx):
    """Each face of ``idx``'s three edges as sorted pairs of rounded vertex keys: (edge key (m, 3), face)."""
    v = np.round(lv.P[idx] * ROUND).astype(np.int64)
    _, vid = np.unique(v.reshape(-1, 3), axis=0, return_inverse=True)
    vid = vid.reshape(-1, 3)
    a = np.concatenate([vid[:, 0], vid[:, 1], vid[:, 2]])
    b = np.concatenate([vid[:, 1], vid[:, 2], vid[:, 0]])
    face = np.tile(np.arange(len(idx)), 3)
    return np.minimum(a, b) * (len(v) * 3 + 1) + np.maximum(a, b), face


def _groups(lab, idx) -> list[np.ndarray]:
    """``idx`` split by its labels ``lab`` (in label order)."""
    if not len(idx):
        return []
    o = np.argsort(lab, kind="stable")
    return np.split(idx[o], np.flatnonzero(np.diff(lab[o])) + 1)


def _patches(lv, idx):
    """Labels of the faces ``idx`` joined by shared edges (each face's patch, numbered by its lowest face)."""
    if not len(idx):
        return np.zeros(0, np.int64)
    key, face = _edges(lv, idx)
    o = np.argsort(key, kind="stable")
    key, face = key[o], face[o]
    same = key[1:] == key[:-1]
    return components(len(idx), face[1:][same], face[:-1][same]).astype(np.int64)


def surface(lv, present=None) -> dict[str, np.ndarray]:
    """Each surface class's faces (the module docstring), as boolean masks over the level's triangles."""
    present = np.array([o["present"] for o in lv.owners]) if present is None else present
    solid, n = _solid(lv, present), _normals(lv)
    nz, w = lv.tri_nz, lv.tri_word
    slip = (w & collision.W_SLIPPERY) != 0
    climb = solid & ((w & 3) == collision.W_CLIMBABLE) & (np.abs(nz) < CLIMB_NZ)
    wall = solid & (nz <= envelope.LAND_NORMAL_Z) & ~climb
    up = solid & (nz > envelope.LAND_NORMAL_Z)
    out = {"wall": wall, "slope": up & ~slip & (nz <= WALK_GAME_NZ), "slide": up & slip & (nz < SLIP_FLAT_NZ),
           "steep": up & ~slip & (nz > WALK_GAME_NZ) & (nz < envelope.STEP_NORMAL_Z),
           "rim": up & ~slip & (nz >= envelope.STEP_NORMAL_Z) & (nz < RIM_NZ), "climb": climb,
           "spring": solid & ((w & collision.W_AUTOSPRING) != 0), "rig": solid & (lv.tri_cat == CAT_RIG)}
    out["floor"] = up & ~(out["slope"] | out["slide"] | out["steep"] | out["rim"])
    upright = np.nonzero(wall & (np.abs(nz) < 0.5))[0]
    thin = np.zeros(len(nz), bool)
    if len(upright):
        c = lv.P[upright].mean(axis=1)
        c[:, 2] = np.minimum(c[:, 2], lv.P[upright][:, :, 2].min(axis=1) + 1.0)
        test = OneSided(types.SimpleNamespace(lv=lv, present=np.asarray(present, bool)), both=True)
        back = c - THIN_M * n[upright]
        thin[upright] = ~test.blocked(c - 0.05 * n[upright], back) & _floor_under(lv, present, back)
    out["thin"] = thin
    out["open"] = _open_tops(lv, solid, wall)
    return out


def _floor_under(lv, present, pts) -> np.ndarray:
    """Whether a solid floor face (nz > 0.6) tops out within :data:`STAND_M` under each point (or 0.1 m over it)."""
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 3)
    up = np.nonzero(_solid(lv, present) & (lv.tri_nz > envelope.LAND_NORMAL_Z))[0]
    out = np.zeros(len(pts), bool)
    if not len(up) or not len(pts):
        return out
    col, _, zhi = raster(lv, up)[:3]
    o = np.argsort(col, kind="stable")
    col, zhi = col[o], zhi[o]
    u, a, c = np.unique(col, return_index=True, return_counts=True)
    st, cnt = lookup(u, a, c, lv.col(pts[:, 0], pts[:, 1]))
    for k in range(int(cnt.max()) if len(cnt) else 0):
        v = k < cnt
        z = zhi[(st + k)[v]]
        out[np.nonzero(v)[0][(z <= pts[v, 2] + 0.1) & (z >= pts[v, 2] - STAND_M)]] = True
    return out


def _open_tops(lv, solid, wall) -> np.ndarray:
    """The walls whose top edge (both ends within 5 cm of the face's top) no other solid face shares."""
    idx = np.nonzero(solid)[0]
    key, face = _edges(lv, idx)
    _, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    alone = cnt[inv] == 1
    P = lv.P[idx]
    top = P[:, :, 2].max(axis=1)
    ends = np.stack([np.concatenate([P[:, 0, 2], P[:, 1, 2], P[:, 2, 2]]),
                     np.concatenate([P[:, 1, 2], P[:, 2, 2], P[:, 0, 2]])], 1)
    high = (ends >= top[face][:, None] - 0.05).all(axis=1)
    out = np.zeros(len(lv.tri_nz), bool)
    hit = face[alone & high]
    out[idx[hit]] = True
    return out & wall


def _site(lv, level, cls, k, faces) -> Site:
    faces = np.sort(faces)
    z = lv.P[faces][:, :, 2]
    step = max(1, len(faces) // POINTS)
    return Site(f"{level}.{cls}.{k:03d}", cls, faces, float(lv.tri_area[faces].sum()), float(z.max() - z.min()),
                lv.P[faces[::step][:POINTS]].mean(1))


def mine(lv, present=None, *, reach=None, exits=None, kit: int = 0, surf: dict | None = None) -> list[Site]:
    """The level's sites (the module docstring) for the kit's ``air`` level ``kit`` (the lips' band): ``reach`` a
    reach model (its presence at load, its exits' touch meshes, its phys and logic floors for ``oob``, its apex),
    else ``present`` (the owners' stored presence by default) and ``exits`` ({exit id: trigger mesh names});
    ``surf`` :func:`surface`'s masks when already made."""
    if reach is not None:
        present = reach.present
    present = np.array([o["present"] for o in lv.owners]) if present is None else np.asarray(present, bool)
    surf = surface(lv, present) if surf is None else surf
    level = lv.name
    by = collections.defaultdict(list)
    for cls in ("slope", "slide", "steep", "thin", "open", "climb", "spring"):
        idx = np.nonzero(surf[cls])[0]
        for f in _groups(_patches(lv, idx), idx):
            z = lv.P[f][:, :, 2]
            big = z.max() - z.min() >= CLIMB_M if cls == "climb" else lv.tri_area[f].sum() >= PATCH_M2
            if big:
                by["speed" if cls == "spring" else cls].append(f)
    air = min(max(kit, 0), 3)
    apex = reach.env.apex[("phys", KIT_NAMES[air])] if reach is not None else APEX[air]
    lips = [(f, h) for f, h in _lips(lv, present, surf) if STEP_M < h <= apex + RIM_LIFT]
    for oi, o in enumerate(lv.owners):
        if o["cat"] in (CAT_PUSH, CAT_RIG) and (o["present"] or o["driven"]) and len(f := lv.tris_of(oi)):
            by["speed"].append(f)
    out: list[Site] = []
    for cls in SITES:
        if cls == "lip":
            parts = sorted(lips, key=lambda x: int(x[0].min()))
            out += [_site(lv, level, cls, k, f) for k, (f, _) in enumerate(parts)]
        elif cls == "trigger":
            out += _triggers(lv, present, reach, exits)
        elif cls == "oob":
            out += _oob(reach) if reach is not None else []
        else:
            out += [_site(lv, level, cls, k, f) for k, f in enumerate(sorted(by[cls], key=lambda f: int(f.min())))]
    return out


def _lips(lv, present, surf):
    """(faces, height) of each wall patch whose top edge a floor face above shares."""
    idx = np.nonzero(surf["wall"])[0]
    lab = _patches(lv, idx)
    solid = np.nonzero(_solid(lv, present))[0]
    key, face = _edges(lv, solid)
    ledge = np.unique(key[(lv.tri_nz[solid] > envelope.LAND_NORMAL_Z)[face]])
    is_wall = surf["wall"][solid]
    P = lv.P[solid]
    top = P[:, :, 2].max(axis=1)
    ends = np.stack([np.concatenate([P[:, 0, 2], P[:, 1, 2], P[:, 2, 2]]),
                     np.concatenate([P[:, 1, 2], P[:, 2, 2], P[:, 0, 2]])], 1)
    high = (ends >= top[face][:, None] - 0.05).all(axis=1)
    lipped = set(solid[face[is_wall[face] & high & np.isin(key, ledge)]].tolist())
    out = []
    for f in _groups(lab, idx):
        if lipped.intersection(f.tolist()):
            z = lv.P[f][:, :, 2]
            out.append((f, float(z.max() - z.min())))
    return out


def exit_faces(lv, reach=None, exits=None) -> dict[str, np.ndarray]:
    """Each exit's touch-mesh faces (indices into the level's triangles; private): ``exits`` ({exit id: trigger mesh
    names}), else the reach model's exits' gate hints' ``touch`` names."""
    if exits is None:
        exits = {}
        for e in (reach.gen.get("exits", []) if reach is not None else []):
            exits[e["id"]] = sorted({nm for kind, nm in reach.HINT_NAMES.findall(e.get("gate_hint") or "")
                                     if kind == "touch"})
    return {eid: np.concatenate([lv.tris_of(oi) for nm in exits[eid] for oi in lv.by_name.get(nm, [])] or
                                [np.zeros(0, np.int64)]) for eid in sorted(exits)}


def _triggers(lv, present, reach, exits) -> list[Site]:
    """The exits' touch meshes that poke out into open air with no floor under it (a sampled inside point a straight
    path of :data:`FAR` m in one of 24 directions leaves crossing no solid face from either side, the itrig scan's
    ``free``, with no floor within :data:`STAND_M` under it: reached only through the air, its ``void_only``);
    ``void``: the share of the free points that are so."""
    test = OneSided(types.SimpleNamespace(lv=lv, present=present), both=True)
    ang = np.arange(12) * np.pi / 6
    dirs = np.r_[np.c_[np.cos(ang), np.sin(ang), np.zeros(12)],
                 np.c_[np.cos(ang[::2] + 0.26) * 0.7071, np.sin(ang[::2] + 0.26) * 0.7071, np.full(6, 0.7071)],
                 np.c_[np.cos(ang[::2] + 0.26) * 0.7071, np.sin(ang[::2] + 0.26) * 0.7071, np.full(6, -0.7071)]]
    out, k = [], 0
    for tris in exit_faces(lv, reach, exits).values():
        if not len(tris):
            continue
        V = lv.P[tris]
        lo, hi = V.reshape(-1, 3).min(0), V.reshape(-1, 3).max(0)
        step = max(GRID, float(np.prod(hi - lo)) ** (1 / 3) / 25)
        g = np.stack(np.meshgrid(*(np.arange(lo[i] + step / 2, hi[i], step) for i in range(3)), indexing="ij"),
                     -1).reshape(-1, 3)
        g = g[np.linspace(0, len(g) - 1, min(len(g), 4000)).astype(np.int64)] if len(g) else g
        pts = np.array([p for p in g if inside_mesh(V, p)]).reshape(-1, 3)
        pts = pts[np.linspace(0, len(pts) - 1, min(len(pts), CAP)).astype(np.int64)] if len(pts) else pts
        if not len(pts):
            continue
        A = np.repeat(pts, len(dirs), axis=0)
        free = ~test.blocked(A, A + np.tile(dirs, (len(pts), 1)) * FAR)
        reach_ = free.reshape(len(pts), len(dirs)).any(axis=1)
        if not reach_.any():
            continue
        stand = _floor_under(lv, present, pts)
        if not (reach_ & ~stand).any():
            continue
        site = _site(lv, lv.name, "trigger", k, tris)
        site.void = float((reach_ & ~stand).sum() / reach_.sum())
        site.points = pts[reach_][np.linspace(0, int(reach_.sum()) - 1, min(int(reach_.sum()), POINTS)).astype(int)]
        out.append(site)
        k += 1
    return out


def _oob(reach) -> list[Site]:
    """The phys floor regions (at least :data:`OOB_M2`) with no logic floor sample in their columns within 0.5 m
    of their own: outside every zone."""
    pw, lw = reach.W["phys"], reach.W["logic"]
    a, c = lookup(lw.u, lw.a, lw.c, pw.col)
    inside = np.zeros(len(pw.col), bool)
    for k in range(int(c.max()) if len(c) else 0):
        v = k < c
        j = (a + k)[v]
        inside[np.nonzero(v)[0][np.abs(lw.z[j] - pw.z[v]) <= 0.5]] = True
    js = np.nonzero(pw.reg_soft >= 0)[0]
    reg = pw.reg_soft[js]
    n, hit = np.bincount(reg), np.bincount(reg, weights=inside[js])
    keep = np.isin(reg, np.nonzero((hit == 0) & (n * CELL * CELL >= OOB_M2))[0])
    out = []
    for k, g in enumerate(_groups(reg[keep], js[keep])):
        z = pw.z[g]
        step = max(1, len(g) // POINTS)
        out.append(Site(f"{reach.name}.oob.{k:03d}", "oob", np.zeros(0, np.int64), float(len(g) * CELL * CELL),
                        float(z.max() - z.min()), np.c_[pw.x[g], pw.y[g], pw.z[g]][::step][:POINTS],
                        region=int(pw.reg_soft[g[0]])))
    return out


def census(lv, sites: list[Site], touched=None, used=(), present=None, surf: dict | None = None,
           regions=(), entered=None, exits: dict | None = None, no_way=()) -> dict:
    """The census (the module docstring): ``touched`` {(face, state class): ticks} of an exploration (summed over
    its runs), ``used`` the faces a confirmed find's rows touched, ``regions`` the explorer's region keys it visited
    (an off-zone site is tried when its ``R<n>`` is among them), ``entered`` {(volume id, state class): ticks} (None:
    the runs kept no volume record), ``exits`` :func:`exit_faces` and ``no_way`` the exits with no logic way in."""
    present = np.array([o["present"] for o in lv.owners]) if present is None else np.asarray(present, bool)
    surf = surface(lv, present) if surf is None else surf
    solid = _solid(lv, present)
    total = float(lv.tri_area[solid].sum()) or 1.0
    by_face = collections.defaultdict(set)
    for (f, cls), n in (touched or {}).items():
        if n:
            by_face[int(f)].add(cls)
    hit = np.zeros(len(lv.tri_nz), bool)
    hit[list(by_face)] = True
    reached = hit.copy()                # a face touched or a volume entered
    reached[[int(f) for (f, _), n in (entered or {}).items() if n]] = True
    unmeasured = lambda f: entered is None and len(f) > 0 and not solid[f].any()   # noqa: E731  a volume, unrecorded
    use = np.zeros(len(lv.tri_nz), bool)
    use[list(used)] = True
    out = {"solid_faces": int(solid.sum()), "solid_m2": round(total, 1), "surface": {}, "sites": {}}
    for cls in SURFACE:
        m = surf[cls]
        ins = [f for f in np.nonzero(m & hit)[0].tolist() if by_face[f] & IN_STATE[cls]]
        out["surface"][cls] = {"faces": int(m.sum()), "m2": round(float(lv.tri_area[m].sum()), 1),
                               "share": round(float(lv.tri_area[m].sum()) / total, 4),
                               "touched": int((m & hit).sum()), "in_state": len(ins), "used": int((m & use).sum())}
    for cls in SITES:
        ss = [s for s in sites if s.cls == cls]
        m2 = sum(s.m2 for s in ss)
        on = sum(float(lv.tri_area[s.faces][solid[s.faces]].sum()) if len(s.faces) else s.m2 for s in ss)
        out["sites"][cls] = {"sites": len(ss), "m2": round(m2, 1), "share": round(on / total, 4),
                             "tried": sum(bool(reached[s.faces].any()) if len(s.faces) else f"R{s.region}" in regions
                                          for s in ss),
                             **({"unmeasured": k} if (k := sum(unmeasured(s.faces) for s in ss)) else {}),
                             "ids": {s.id: round(s.m2, 1) for s in ss}}
    exits = exits or {}
    got = {e for e, f in exits.items() if len(f) and reached[f].any()}
    unknown = any(unmeasured(f) for f in exits.values())
    out["exits"] = {"exits": len(exits), "no_logic_way_in": len(set(no_way) & set(exits)),
                    "reached": None if unknown else len(got),
                    "no_logic_way_in_reached": None if unknown else len(got & set(no_way))}
    return out


def probes(derived: dict, saturated, transitions) -> list[dict]:
    """The logic edges (``derived``'s, in logic) out of a zone the exploration ``saturated`` that none of its
    ``transitions`` ({"from>to": ...}) reproduced: a probe list for confirmation, never a refutation."""
    seen, sat = set(transitions), set(saturated)
    out = {}
    for e in derived.get("edges", []):
        if e.get("logic") is False or e["from"] not in sat or e["from"] == e["to"]:
            continue
        key = f"{e['from']}>{e['to']}"
        if key not in seen:
            out.setdefault(key, {"from": e["from"], "to": e["to"], "kinds": set()})["kinds"].add(e["kind"])
    return [{**v, "kinds": sorted(v["kinds"])} for _, v in sorted(out.items())]


SITE_R, SITE_W, VISIT_M = 8.0, 1.0, 2.0   # [proposal] the site prior's reach (m), its most weight, a visit (m)


class Prior:
    """The trick explorer's site prior (a guide's ``site_prior``, ``l3_explore``'s novelty pick): 1 + ``SITE_W`` x
    (1 - d / ``SITE_R``) for the nearest anchor point (of a site not yet visited) within ``SITE_R`` of the body's feet
    (horizontally and in height), else 1; a site is visited once a row comes within ``VISIT_M`` of one of its points.
    The visited set is the caller's (``seen``: each exploration's own, so a guide a pool worker keeps for its next
    seed starts every exploration with none visited).  Mined sites only add weight: they never steer or filter (the
    plan §3.2)."""

    def __init__(self, sites: list[Site]):
        self.pts = np.concatenate([s.points for s in sites]) if sites else np.zeros((0, 3))
        self.owner = np.repeat(np.arange(len(sites)), [len(s.points) for s in sites])
        self.idx = RadiusIndex(self.pts[:, :2], SITE_R) if len(self.pts) else None

    def __call__(self, row, seen: set) -> float:
        if self.idx is None:
            return 1.0
        feet = np.array([row.pos[0], row.pos[1], row.pos[2] - 1.0])
        _, pj, _ = self.idx.pairs(feet[None, :2])
        best = 1.0
        for j in pj.tolist():
            s, d = int(self.owner[j]), float(np.linalg.norm(self.pts[j] - feet))
            if s in seen or d > SITE_R:
                continue
            if d <= VISIT_M:
                seen.add(s)
            best = max(best, 1.0 + SITE_W * (1.0 - d / SITE_R))
        return best
