#!/usr/bin/env python3
"""Render the Randomize tab's level maps into ``gui/assets/maps/`` (Steps 2.29, 2.33).

A level's map is its floors seen from above (the tops of the reach model's
solid spans, ``azurik_mod/randomizer/draft``; above 2 px/m each 0.5 m
column fills its own pixels), coloured the way the level looks in the
game: a floor pixel takes the colour of the render-mesh face that lies on
it (``azurik_mod/xbr/render.py``: the face's texture, averaged, times its
vertex colours; a black vertex, which the level's lights light instead,
the texture's own), a blended face where no opaque one does, else an
opaque face up to ``FAR`` m off, lit by its slope and lighter where it is
higher.  Lava (the damage volumes that are seen and wave like water) and
water (the water volumes, where a face lies at their top) cover the floor,
the water see-through by its depth.  A level whose walkable regions (the
reach model's ``floors.Walk``) stack is split into at most ``FLOORS``
floors (``FLOORS_OF`` where its storeys stack deeper), none of which overlaps itself from above, the drawn surfaces no
one walks on going on the floor they lie beside (:func:`floors`); a base
plane far under the level is on none (:func:`base`), and a surface no one
walks on that the game shows nothing on isn't drawn (:func:`unseen`).
Each floor is a picture, with the level's other floors faint under it.

``maps.json`` holds each level's size, floors and frame (``[x0, y1, s]``:
world (x, y) is pixel ``(floor((x - x0) * s), floor((y1 - y) * s))``, the
live tracker's you-are-here dot) and, as pixels with their floor, the live exits (at the shapes that fire them, the vanilla data's
``gate_hint``), the major items, the other spots the tracker marks
(obsidians, fuel and health) and the barriers at their vanilla
positions (a group the data names for no kind that gates the logic takes
its damage's: :data:`DAMAGE_KINDS`), the features a player steers by
(:func:`features`) and the gem spots (:func:`gems`, the tracker's gem
dots); ``world.png`` is every level's main
floor on a grid.  The GUI draws the names, icons and connections over the
pictures, and draws a level's pictures finer in its user cache when one is
zoomed past its own pixels (:func:`draw_detail`, Step 2.97).

Usage (needs the vanilla ISO)::

    uv run --locked python scripts/render_level_maps.py [--iso PATH] [--out DIR]

About five minutes; prints sizes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from azurkit.tools.randomizer.draft.geometry import CELL as COLUMN
from azurkit.tools.randomizer.levels import GENERATED, LEVELS, SLOT_BOSS, _pivot

REPO = Path(__file__).resolve().parent.parent

SIZE = 480                      # a level map's long side, px
CELL, THUMB = (170, 140), (160, 124)
WORLD_TOP = 34                  # room for the title
# The world map's grid (column, row): neighbours where the game links them.
# A level with no cell gets no map: training_room, never part of a seed (D194).
GRID = {"airship": (0, 0), "a3": (1, 0), "a5": (2, 0), "a6": (3, 0), "a1": (4, 0), "e6": (5, 0),
        "w3": (0, 1), "w1": (1, 1), "town": (2, 1), "life": (3, 1), "e2": (4, 1), "e7": (5, 1),
        "w4": (0, 2), "w2": (1, 2), "d1": (2, 2), "f1": (3, 2), "e5": (4, 2), "f2": (5, 2),
        "f3": (1, 3), "d2": (2, 3), "f6": (3, 3), "f4": (4, 3)}
# The ground where no render face lies on a floor: a low and a high colour per realm.
PALETTE = {"a": ((70, 58, 40), (240, 226, 176)), "w": ((22, 54, 78), (150, 205, 196)),
           "f": ((58, 24, 16), (226, 140, 64)), "e": ((30, 56, 30), (186, 196, 122)),
           "d": ((40, 32, 48), (172, 160, 180)), "town": ((60, 48, 32), (216, 196, 154)),
           "life": ((36, 74, 42), (216, 240, 200)), "other": ((40, 44, 50), (190, 196, 204))}
SHAPES = re.compile(r"(?:touch|actionButton|teleported)\((?:spot )?([^()]+)\)")
BACKGROUND = np.array((27, 31, 36), dtype=np.float64)
TOL = 1.5                       # m: a render face this close to a floor colours it
FAR = 10.0                      # m: else the nearest within this (a collision floor laid over its render, town's)
WATER, LAVA = np.array((36, 92, 140.0)), np.array((235, 96, 24.0))
FLOORS = 5                      # the most floors a level's map has (M7), but where its storeys stack deeper:
# the levels whose walkable ground five floors left on none (AZ-485, measured with 5 to 8: in m^2, a1 28 to 0
# with 7, a5 126 to 0, f6 226 to 8, a3 2,060 to 389 with 8, d1 5,302 to 677, d2 2,195 to 44, f3 2,010 to 770, life
# 917 to 30, town 1,817 to 225; a cap of 6 for every level drew less of w3, e2, e5 and f4, whose small floors fit
# nowhere)
FLOORS_OF = {"a1": 7, "a5": 7, "f6": 7, "a3": 8, "d1": 8, "d2": 8, "f3": 8, "life": 8, "town": 8}
FLOOR_MIN, FLOOR_SHARE = 2000.0, 0.04   # a floor smaller than this (m^2, share) joins another where it fits
FLOOR_TINY = 250.0              # m^2: one this small that fits nowhere is no floor (a ledge over the ground)
BASE_GAP, BASE_FLAT = 30.0, 1.0   # m: the lowest walkable ground this far under the rest, this flat, is a base
LINK = 1.0                      # m: neighbouring drawn tops no one walks on this close in height are one surface
NEAR = 2.5                      # m: a surface beside a floored top this close in height takes to that floor
FAINT = 0.25                    # the other floors' share of a floor's picture
BARRIERS = ("firewall", "iceblock", "acidblock", "crystal", "smashwall")
# A barrier group the vanilla data names for no kind ("other": one under a node named "all", or a shape named
# polySurfaceShape2) that has a requirement takes the kind its damage gives every named group: water douses
# a fire barrier (all 32 meshless, as a5's and w2's Damage_FieldShape), steam melts an ice block (a5's, w2's
# and e2's "all", the ice block's own rock), acid an acid block (f3's "all", AcidBlock_01's other half); a
# smash wall (f1's and w3's faint glow planes) is a kind of its own (M17, AZ-463). The rest gate nothing
# (e6's detectors, w2's hose machine) and the traps went with D191.
DAMAGE_KINDS = {"watr": "firewall", "stem": "iceblock", "acid": "acidblock", "smsh": "smashwall"}


def realm(level: str) -> str:
    return level[0] if level[1:].isdigit() else level if level in PALETTE else "other"


class Frame:
    """World (x, y) to pixels: ``SIZE`` px on the long side of the level's
    up-facing static collision, ``detail`` times that for the GUI's detail
    pictures (:func:`draw_detail`; the same corner, so a map pixel u is
    detail pixel u * detail)."""

    def __init__(self, lv, detail: float = 1.0):
        st = [o["oi"] for o in lv.owners if o["kind"] == "levl"]
        t = np.isin(lv.tri_owner, st) & (lv.tri_nz > 0)
        P = lv.P[t] if t.any() else lv.P
        self.x0, self.x1 = P[:, :, 0].min(), P[:, :, 0].max()
        self.y0, self.y1 = P[:, :, 1].min(), P[:, :, 1].max()
        self.s = (SIZE - 1) / max(self.x1 - self.x0, self.y1 - self.y0, 1e-6) * detail
        self.w, self.h = int((self.x1 - self.x0) * self.s) + 1, int((self.y1 - self.y0) * self.s) + 1

    def pixel(self, x, y):
        """(px, py, inside) of world points."""
        px = np.floor((np.asarray(x) - self.x0) * self.s).astype(np.int64)
        py = np.floor((self.y1 - np.asarray(y)) * self.s).astype(np.int64)
        return px, py, (px >= 0) & (px < self.w) & (py >= 0) & (py < self.h)


def load(rd, schema, level: str):
    """(XBR bytes, its TOC, its node graphs, the reach model's floors)."""
    from azurkit.tools.randomizer.draft.geometry import Level
    from azurkit.tools.randomizer.art.reach import Reach
    from azurkit.tools.randomizer.art import collision, nodes
    from azurkit.core.xbr.nodes import parse_toc

    data = bytes(rd.read_file(f"gamedata/{level}.xbr"))
    graphs = nodes.graphs(data, schema)
    return data, parse_toc(data), graphs, Reach(Level(level, collision.owners(data, schema, graphs), graphs),
                                                flights=False)


# --------------------------------------------------------------------------- floors
def links(A, tops: np.ndarray, dz: float) -> tuple[np.ndarray, np.ndarray]:
    """The pairs (i, j) of ``tops`` (span tops in column order) that stand
    in neighbouring columns (8 ways) within ``dz`` m of each other in
    height, each pair once."""
    from azurkit.tools.randomizer.draft.floors import csr, lookup

    spans, NX = A.spans, A.lv.NX
    col, z = spans.col[tops], spans.top[tops]
    u, a, c, mx = csr(col)
    ix, ei, ej = col % NX, [], []
    for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
        valid = ix + dx < NX
        aa, cc = lookup(u, a, c, np.where(valid, col + dx + dy * NX, -1))
        for k in range(mx):
            v = valid & (k < cc)
            j = np.where(v, aa + k, 0)
            i = np.nonzero(v & (np.abs(z[j] - z) <= dz))[0]
            ei.append(i)
            ej.append(j[i])
    return tuple(np.concatenate(x) if x else np.zeros(0, dtype=np.int64) for x in (ei, ej))


def base(A, items) -> np.ndarray:
    """The level's base plane, the walkable tops of it: its lowest walkable
    ground when it is flat (within ``BASE_FLAT`` m), lies at least
    ``BASE_GAP`` m under all the rest, is ``FLOOR_MIN`` m^2 or more (a
    smaller one joins another floor anyway: e6's, f2's and w2's patches of
    a few m^2 stay on theirs) and holds none of the span tops ``items``
    (the items' and spots' own): town's at -88 m (its pit's floor,
    160,000 m^2, which took one of its five floors), f3's, w4's, f4's
    (AZ-461).  It shows only faint under the floors; an exit on it (town's
    Town_D1, 60 m over it) goes on the main floor.  Empty when there is
    none."""
    w = A.W["logic"]
    sidx, z = w.sidx[w.reg_soft >= 0], w.z[w.reg_soft >= 0]
    if not len(z):
        return sidx
    low = z <= z.min() + BASE_FLAT
    if ((~low).any() and z[~low].min() - z[low].max() >= BASE_GAP and low.sum() * 0.25 >= FLOOR_MIN
            and not np.isin(sidx[low], items).any()):
        return sidx[low]
    return sidx[:0]


def unseen(A, fr: Frame, F, tops) -> np.ndarray:
    """Which of the span ``tops`` have no render face (``faces``) within
    ``FAR`` m of them in their pixel: collision the game shows nothing on
    (d1's bowl under its islands, AZ-461)."""
    pix, z = F[0], F[1]
    key = np.sort(pix * 1e5 + (z + 5e4))
    px, py, _ = fr.pixel(*A.lv.cxy(A.spans.col[tops]))
    q = (np.clip(py, 0, fr.h - 1) * fr.w + np.clip(px, 0, fr.w - 1)) * 1e5 + (A.spans.top[tops] + 5e4)
    if not len(key):
        return np.ones(len(tops), dtype=bool)
    i = np.minimum(np.searchsorted(key, q - FAR), len(key) - 1)
    return np.abs(key[i] - q) > FAR


def floors(A, sp: np.ndarray, marks=(), under=(), n_floors: int = FLOORS) -> tuple[np.ndarray, list[int]]:
    """(the floor of each span top, -1 for none; the floors' order by
    height), for the span tops ``sp`` a picture draws and ``marks``, the
    tops the icons stand on (:func:`own_tops`); the walkable tops ``under``
    (:func:`base`) are on none.  No floor overlaps itself from above (M7):
    a floor holds at most one top of a column.

    The logic profile's walkable regions, then the drawn surfaces no one
    walks on (tops in neighbouring columns within ``LINK`` m, AZ-460: a
    seabed, a pedestal, a roof), each cut where it passes over itself, are
    put on floors: a walkable piece largest first on the first of
    ``n_floors`` floors where nothing of it lies above or under what that
    floor holds, else on the one it overlaps least; a surface, those an
    icon stands on first, then largest first, on the floor it lies beside
    most (a top within ``NEAR`` m of its height in a neighbouring column),
    else as a walkable piece.  Then where a floor holds two tops of a
    column, one of a piece holding a mark stays, else the highest; the
    others move to a floor with nothing in the column, the one nearest them
    in height, or to none where every floor has (a tower's storeys, stacked
    deeper than ``n_floors``), so an icon sits on the floor of the ground it
    stands on: first among the walkable tops and the icons' own, then the
    surfaces' in the floors left in their columns.  Last, a floor whose walkable
    ground is smaller than ``FLOOR_MIN`` m^2 (or ``FLOOR_SHARE`` of the
    level's) joins the floor nearest it in height that has nothing in its
    columns, if one has none, and one under ``FLOOR_TINY`` that fits
    nowhere and holds no mark is no floor."""
    from azurkit.tools.randomizer.draft.geometry import components

    w, spans = A.W["logic"], A.spans
    ok = w.reg_soft >= 0
    walk = np.zeros(spans.n, dtype=bool)
    walk[w.sidx[ok]] = True
    ok &= ~np.isin(w.sidx, np.asarray(under, dtype=np.int64))    # the base plane: on no floor
    col, z, reg, sidx = w.col[ok], w.z[ok], w.reg_soft[ok], w.sidx[ok]
    marks = np.asarray(marks, dtype=np.int64)
    nwalk = len(sidx)
    # the drawn tops no one walks on, labelled by their connected surfaces: regions after the walkable ones
    dec = np.asarray(sp, dtype=np.int64)[~walk[sp]]
    if len(dec):
        lab = components(len(dec), *links(A, dec, LINK))
        base = int(reg.max()) + 1 if len(reg) else 0
        col, z, reg, sidx = (np.r_[a, b.astype(a.dtype)] for a, b in
                             zip((col, z, reg, sidx), (spans.col[dec], spans.top[dec], base + lab, dec)))
    isdec = np.arange(len(sidx)) >= nwalk
    # a region's pieces: its samples by how many of its own lie above them in their column
    o = np.lexsort((-z, reg, col))
    first = np.r_[True, (col[o][1:] != col[o][:-1]) | (reg[o][1:] != reg[o][:-1])]
    rank = np.empty(len(o), dtype=np.int64)
    rank[o] = np.arange(len(o)) - np.flatnonzero(first)[np.cumsum(first) - 1]
    _, piece = np.unique(reg.astype(np.int64) * (int(rank.max()) + 1) + rank, return_inverse=True)
    n = int(piece.max()) + 1
    area = np.bincount(piece, minlength=n) * 0.25
    # two pieces clash when they hold samples of one column
    o = np.argsort(col, kind="stable")
    cs, ps, keys, d = col[o], piece[o], [], 1
    while d < len(cs) and (same := cs[d:] == cs[:-d]).any():
        a, b = ps[d:][same], ps[:-d][same]
        keys += [a * n + b, b * n + a]
        d += 1
    keys = np.unique(np.concatenate(keys)) if keys else np.zeros(0, dtype=np.int64)
    keys = keys[keys // n != keys % n]
    start = np.searchsorted(keys // n, np.arange(n + 1))
    marked = np.zeros(n, dtype=bool)
    marked[piece[np.isin(sidx, marks)]] = True
    pdec = np.zeros(n, dtype=bool)
    pdec[piece[isdec]] = True
    # a surface's contacts: how many links it has to each other piece beside it at about its height
    by_col = np.argsort(col, kind="stable")
    i, j = links(A, sidx[by_col], NEAR)
    pa, pb = piece[by_col[i]], piece[by_col[j]]
    m = (pa != pb) & (pdec[pa] | pdec[pb])
    touch, count = np.unique(np.r_[pa[m] * n + pb[m], pb[m] * n + pa[m]], return_counts=True)
    tstart = np.searchsorted(touch // n, np.arange(n + 1))
    layer = np.full(n, -1)
    walkable = [p for p in np.lexsort((np.arange(n), -area)).tolist() if not pdec[p]]
    surfaces = [p for p in np.lexsort((np.arange(n), -area, ~marked)).tolist() if pdec[p]]
    for p in walkable + surfaces:
        nb = keys[start[p]:start[p + 1]] % n
        nb = nb[layer[nb] >= 0]
        over = np.bincount(layer[nb], weights=area[nb], minlength=n_floors)
        if pdec[p]:
            tb, tc = touch[tstart[p]:tstart[p + 1]] % n, count[tstart[p]:tstart[p + 1]]
            on = layer[tb] >= 0
            beside = np.bincount(layer[tb[on]], weights=tc[on], minlength=n_floors)
            if beside.any():
                layer[p] = int(np.lexsort((np.arange(n_floors), over, -beside))[0])
                continue
        layer[p] = int(np.argmin(over))
    of_span = np.full(spans.n, -1)
    of_span[sidx] = layer[piece]

    def height(j):
        on = sp[of_span[sp] == j]
        return float(np.median(spans.top[on])) if len(on) else 0.0

    # two tops of a column on one floor: one of a marked piece stays, else the highest; the others go to a floor
    # with nothing in their column, else none. The walkable tops and the icons' own settle first, the surfaces
    # after them in what is left
    h = [height(j) for j in range(n_floors)]
    f, mk, W = layer[piece], marked[piece], n_floors + 1
    held = np.zeros(0, dtype=np.int64)          # the settled (column, floor + 1)
    for group in (np.flatnonzero(~isdec | np.isin(sidx, marks)), np.flatnonzero(isdec & ~np.isin(sidx, marks))):
        o = group[np.lexsort((-z[group], ~mk[group], col[group], f[group]))]
        key = col[o].astype(np.int64) * W + f[o] + 1
        lost = np.r_[False, key[1:] == key[:-1]] | np.isin(key, held)
        dup, stay = o[lost], o[~lost]
        taken = {}
        for c, g in zip(*divmod(held[np.isin(held // W, col[dup])], W)):
            taken.setdefault(int(c), set()).add(int(g) - 1)
        for t in stay[np.isin(col[stay], col[dup])].tolist():
            taken.setdefault(int(col[t]), set()).add(int(f[t]))
        for t in dup[np.lexsort((-z[dup], ~mk[dup]))].tolist():
            have = taken.setdefault(int(col[t]), set())
            free = [j for j in range(n_floors) if j not in have]
            f[t] = min(free, key=lambda j: abs(h[j] - z[t])) if free else -1
            have.add(int(f[t]))
        on = group[f[group] >= 0]
        held = np.unique(np.r_[held, col[on].astype(np.int64) * W + f[on] + 1])
    of_span[sidx] = f
    # small floors
    k, held = n_floors, set(of_span[marks].tolist())
    on = of_span[sidx[:nwalk]]
    size = np.bincount(on[on >= 0], minlength=k) * 0.25
    cols = [np.unique(spans.col[np.r_[sp[of_span[sp] == j], sidx[of_span[sidx] == j]]]) for j in range(k)]
    h = [height(j) for j in range(k)]
    into = list(range(k))
    for j in sorted(range(k), key=lambda j: size[j]):
        if size[j] >= max(FLOOR_MIN, FLOOR_SHARE * size.sum()):
            break
        fits = [g for g in set(into) - {j, None}
                if size[g] and not len(np.intersect1d(cols[j], cols[g], assume_unique=True))]
        if fits or size[j] < FLOOR_TINY and j not in held:
            g = min(fits, key=lambda g: (abs(h[g] - h[j]), g)) if fits else None
            into = [g if t == j else t for t in into]
            if g is not None:
                cols[g] = np.union1d(cols[g], cols[j])
                size[g] += size[j]
    keep = sorted({t for t in into if t is not None})
    remap = np.array([keep.index(t) if t is not None else -1 for t in into] + [-1])
    of_span = remap[of_span]
    return of_span, sorted(range(len(keep)), key=height)


def footprint(fr: Frame, x, y):
    """(k, px, py) of the pixels the reach model's columns centred at (x, y)
    cover, ``k`` each pixel's column: the pixel of its centre, or above 2
    px/m (the airship's 4.7) every pixel whose centre lies in its 0.5 m
    square, so a floor is whole rather than a grid of dots."""
    x, y = np.asarray(x), np.asarray(y)
    if COLUMN * fr.s <= 1:
        px, py, ins = fr.pixel(x, y)
        k = np.arange(len(px))
    else:
        h = COLUMN / 2
        ax, bx = (np.ceil((x + d - fr.x0) * fr.s - 0.5).astype(np.int64) for d in (-h, h))
        ay, by = (np.ceil((fr.y1 - y + d) * fr.s - 0.5).astype(np.int64) for d in (-h, h))
        nx, ny = np.maximum(bx - ax, 1), np.maximum(by - ay, 1)
        n = nx * ny
        k = np.repeat(np.arange(len(n)), n)
        j = np.arange(len(k)) - np.repeat(np.cumsum(n) - n, n)
        px, py = ax[k] + j % nx[k], ay[k] + j // nx[k]
        ins = (px >= 0) & (px < fr.w) & (py >= 0) & (py < fr.h)
    return k[ins], px[ins], py[ins]


def tops(px, py, z, fr: Frame) -> np.ndarray:
    """The highest ``z`` in each pixel (-inf where none)."""
    H = np.full(fr.w * fr.h, -np.inf)
    np.maximum.at(H, py * fr.w + px, z)
    return H


# --------------------------------------------------------------------------- colours
def faces(data, toc, graphs, fr: Frame):
    """Points on every non-vertical render face: (pixel, z, colour, opaque)."""
    from azurkit.tools.randomizer.art import render

    binds = [(b, None) for b in render.static_bindings(data, toc)]
    for g in graphs:
        for i, ty in enumerate(g.types):
            if ty == "platform":
                binds += [(b, np.array(g.world(i)[0])) for b in render.platform_bindings(g, i)]
    mats, tris, cols, opq = {}, [], [], []
    for (rdms, prim), m in binds:
        me = render.mesh(data, toc, rdms, prim)
        key = (me.gshd, me.row)
        if key not in mats:
            mt = render.material(data, toc, *key)
            tex = render.surf_mean(data, toc, mt["textures"][0])[0] if mt.get("textures") else np.full(3, 160.0)
            mats[key] = (tex / 255.0, 2.0 if mt.get("flags", 0) & 0x10 else 1.0, mt.get("blend") == 500)
        tex, gain, opaque = mats[key]
        rgb = me.colors.astype(np.float64) * gain
        rgb[me.colors.max(1) < 8] = 255.0       # a black vertex is lit by the level's lights, not prelit: its texture
        p = me.positions
        if m is not None:      # no BLAS: the same bytes on every machine
            p = np.stack([p[:, 0] * m[r, 0] + p[:, 1] * m[r, 1] + p[:, 2] * m[r, 2] + m[r, 3] for r in range(3)], 1)
        tris.append(p[me.triangles])
        cols.append(np.clip(rgb[me.triangles].mean(1) * tex, 0, 255))
        opq.append(np.full(len(me.triangles), opaque))
    P, C, O = np.concatenate(tris), np.concatenate(cols), np.concatenate(opq)
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    flat = np.abs(n[:, 2]) > 0.2 * np.maximum(np.linalg.norm(n, axis=1), 1e-12)
    P, C, O = P[flat], C[flat], O[flat]
    # every pixel centre a face covers, and each face's middle (a face may be smaller than a pixel)
    X, Y, Z = (P[:, :, 0] - fr.x0) * fr.s, (fr.y1 - P[:, :, 1]) * fr.s, P[:, :, 2]
    out = [(np.floor(X.mean(1)).astype(np.int64), np.floor(Y.mean(1)).astype(np.int64), Z.mean(1),
            np.arange(len(P)))]
    ix0 = np.maximum(np.ceil(X.min(1) - 0.5).astype(np.int64), 0)
    iy0 = np.maximum(np.ceil(Y.min(1) - 0.5).astype(np.int64), 0)
    nx = np.maximum(np.minimum(np.floor(X.max(1) - 0.5).astype(np.int64), fr.w - 1) - ix0 + 1, 0)
    ny = np.maximum(np.minimum(np.floor(Y.max(1) - 0.5).astype(np.int64), fr.h - 1) - iy0 + 1, 0)
    n = nx * ny
    den = (Y[:, 1] - Y[:, 2]) * (X[:, 0] - X[:, 2]) + (X[:, 2] - X[:, 1]) * (Y[:, 0] - Y[:, 2])
    den = np.where(np.abs(den) > 1e-12, den, 1e-12)
    cum, start = np.cumsum(n), 0
    while start < len(n):
        end = max(int(np.searchsorted(cum, (cum[start - 1] if start else 0) + 4_000_000, "right")), start + 1)
        t = np.repeat(np.arange(start, end), n[start:end])
        k = np.arange(len(t)) - np.repeat(np.cumsum(n[start:end]) - n[start:end], n[start:end])
        cx, cy = ix0[t] + k % np.maximum(nx[t], 1), iy0[t] + k // np.maximum(nx[t], 1)
        fx, fy = cx + 0.5 - X[t, 2], cy + 0.5 - Y[t, 2]
        l0 = ((Y[t, 1] - Y[t, 2]) * fx + (X[t, 2] - X[t, 1]) * fy) / den[t]
        l1 = ((Y[t, 2] - Y[t, 0]) * fx + (X[t, 0] - X[t, 2]) * fy) / den[t]
        ok = (l0 >= -1e-9) & (l1 >= -1e-9) & (l0 + l1 <= 1 + 1e-9)
        out.append((cx[ok], cy[ok], (l0 * Z[t, 0] + l1 * Z[t, 1] + (1 - l0 - l1) * Z[t, 2])[ok], t[ok]))
        start = end
    px, py, z, t = (np.concatenate(x) for x in zip(*out))
    inside = (px >= 0) & (px < fr.w) & (py >= 0) & (py < fr.h)
    return (py * fr.w + px)[inside], z[inside], C[t[inside]], O[t[inside]]


def nearest(H, F, opaque_only=True, tol=TOL) -> np.ndarray:
    """Per pixel, the colour of the face point closest to height ``H``
    (within ``tol``); NaN where none."""
    pix, z, col, opq = F
    dz = np.abs(z - H[pix])
    m = dz < tol
    if opaque_only:
        m &= opq
    pix, dz, col = pix[m], dz[m], col[m]
    o = np.lexsort((dz, pix))
    first = o[np.r_[True, pix[o][1:] != pix[o][:-1]]] if len(o) else o
    out = np.full((len(H), 3), np.nan)
    out[pix[first]] = col[first]
    return out


def ground(H, F) -> np.ndarray:
    """Per pixel, the colour of the render face on the floor at ``H``: the
    nearest opaque face within ``TOL``, else a blended one (life's
    walkways are only those), else the nearest opaque face within ``FAR``
    (town's and f4's collision lies up to a few metres over its render);
    NaN where none (d1's bowl under its islands has no render face within
    500 m: the realm palette)."""
    c = nearest(H, F)
    for opaque_only, tol in ((False, TOL), (True, FAR)):
        miss = np.isnan(c[:, 0])
        if miss.any():
            c[miss] = nearest(H, F, opaque_only, tol)[miss]
    return c


def paint(level: str, H, F, water, lava, fr: Frame, z0: float, z1: float, gamma: float):
    """A floor's picture (rows of RGB, float): the floor under ``H``, with
    the lava and water over it; NaN where it has no floor."""
    lo, hi = (np.array(c, dtype=np.float64) for c in PALETTE[realm(level)])
    has = np.isfinite(H)
    t = np.clip((np.where(has, H, z0) - z0) / max(z1 - z0, 1e-6), 0, 1)
    c = ground(H, F)
    miss = has & np.isnan(c[:, 0])
    c[miss] = lo + (hi - lo) * t[miss, None]
    Z = np.where(has, H, np.nan).reshape(fr.h, fr.w)
    up = np.full_like(Z, np.nan)
    up[1:, 1:] = Z[:-1, :-1]
    with np.errstate(invalid="ignore"):
        light = np.where(np.isfinite(up) & np.isfinite(Z), 1 + np.clip(np.round((Z - up) * 2), -2, 2) * 0.08, 1.0)
    c = 255 * (c / 255) ** gamma * (0.9 + 0.2 * t[:, None]) * light.reshape(-1, 1)
    with np.errstate(invalid="ignore"):
        hot = np.isfinite(lava) & (~has | (lava > H - 0.05))
        if hot.any():          # lava: its own colour where that is bright, else LAVA
            lc = nearest(lava, F, opaque_only=False)
            c[hot] = np.where((lc @ (0.3, 0.59, 0.11) > 90)[:, None], lc, LAVA)[hot]
        depth = np.where(has, water - H, 30.0)      # water is drawn where a face lies at its top: it is seen
        wet = np.isfinite(water) & (depth > 0.05) & ~np.isnan(nearest(water, F, opaque_only=False)[:, 0])
    a = np.clip(0.3 + depth / 30, 0.3, 0.6)[wet, None]
    c[wet] = WATER * a + np.where(np.isnan(c), BACKGROUND, c)[wet] * (1 - a)
    return c


def volume_tops(vol, fr: Frame, lv, owners=None) -> np.ndarray:
    """The highest top of ``vol``'s volumes (those of ``owners``) in each pixel (-inf: none)."""
    m = np.ones(len(vol.col), dtype=bool) if owners is None else np.isin(vol.own, list(owners))
    x, y = lv.cxy(vol.col[m])
    px, py, ins = fr.pixel(x, y)
    return tops(px[ins], py[ins], vol.hi[m][ins], fr)


# --------------------------------------------------------------------------- places
def place(A, fr: Frame, of_span, floor_no, x, y, z) -> list:
    """[px, py, floor] of a world point: where it is on the map, in pixels
    to 0.01 (pixel u covers [u, u + 1); not a whole pixel, so a zoomed map
    shows it where it is, Step 2.97), and the floor of the span top under
    it (-1: none)."""
    spans = A.spans
    a, cnt = spans.range_of(A.lv.col([x], [y]))
    f, best = None, None
    for j in range(int(cnt[0])):
        s = int(a[0]) + j
        if of_span[s] >= 0 and spans.top[s] <= z + 1.5 and (best is None or spans.top[s] > best):
            f, best = of_span[s], spans.top[s]
    px, py = (x - fr.x0) * fr.s, (fr.y1 - y) * fr.s
    return [round(float(np.clip(px, 0, fr.w - 0.01)), 2), round(float(np.clip(py, 0, fr.h - 0.01)), 2),
            floor_no.get(f, -1)]


def own_tops(A, found: dict, drawn: np.ndarray) -> np.ndarray:
    """The span top each point of the icons ``found`` (:func:`icons`)
    stands on: the highest walkable or ``drawn`` top at most 1.5 m over it
    in its column (none over a point: none), as :func:`place` reads it."""
    spans, w = A.spans, A.W["logic"]
    ok = np.zeros(spans.n, dtype=bool)
    ok[drawn] = ok[w.sidx[w.reg_soft >= 0]] = True
    out = []
    for x, y, z in (p for icons_ in found.values() for i in icons_ for p in i["at"]):
        a, cnt = spans.range_of(A.lv.col([x], [y]))
        under = [s for s in range(int(a[0]), int(a[0]) + int(cnt[0])) if ok[s] and spans.top[s] <= z + 1.5]
        if under:
            out.append(max(under, key=lambda s: spans.top[s]))
    return np.array(sorted(set(out)), dtype=np.int64)


def barrier_kind(b: dict) -> str:
    """A barrier group's kind: the vanilla data's, else (``other``) when it
    has a requirement its damage's (:data:`DAMAGE_KINDS`)."""
    if b["kind"] != "other" or b["requires"] is None:
        return b["kind"]
    return DAMAGE_KINDS.get(b["damage"], "other")


def where(A, gid: str):
    """A record's world point: the middle of its collision, else its pivot."""
    _, g, r = gid.split("/")
    oi = A.lv.by_rec.get((int(g[1:]), int(r[1:])))
    if oi is not None:
        P = A.lv.P[A.lv.tris_of(oi)].reshape(-1, 3)
        return tuple((P.min(0) + P.max(0)) / 2)
    return _pivot(A.lv.graphs[int(g[1:])], int(r[1:]))


def icons(A, level: str) -> dict:
    """``level``'s icons for ``maps.json`` with ``at`` their world points:
    the live exits (at the shapes that fire them), the major items, the
    other spots the tracker marks (obsidians, fuel and health) and the
    barriers with a kind, at their vanilla positions."""
    gen = json.loads((GENERATED / f"{level}.json").read_text(encoding="utf-8"))
    found = {"exits": [], "items": [], "spots": [], "barriers": []}
    for e in gen["exits"]:
        if e["kind"] != "exit" or not e["live"]:      # a dead switch never fires
            continue
        gs = e["id"].split("/")[1]
        shapes = set(SHAPES.findall(e["gate_hint"] or ""))
        found["exits"].append({"spot": e["spot"] or "", "to": e["dest_level"], "disc": e["disc_teleport"],
                               "at": [where(A, f"{level}/{gs}/r{i}")
                                      for i, n in enumerate(A.lv.graphs[int(gs[1:])].names) if n in shapes]})
    for loc in gen["locations"]:
        if loc["class"] in ("major", "obsidian", "consumable") and loc["pool"] and not loc["dead"]:
            gid = loc["id"]
            if not gid.startswith(f"{level}/"):     # a guardian's drop (characters.xbr): where it appears
                gid = next(b["id"] for b in gen["bosses"] if b["critter"] == SLOT_BOSS[level])
            found["items" if loc["class"] == "major" else "spots"].append(
                {"id": loc["id"], "item": loc["item"], "at": [A.lv.rec_points(gid)[0][0]]})
    for b in gen["barriers"]:
        kind = barrier_kind(b)
        if kind in BARRIERS:
            found["barriers"].append({"id": b["id"], "kind": kind, "at": [where(A, gid) for gid in b["shapes"]]})
    return found


def gems(A, level: str) -> list[dict]:
    """``level``'s gem spots (a gem's, a cluster's) for ``maps.json`` with
    ``at`` the middle of their generator's points, its vanilla position
    (Step R1.43: the tracker's gem dots). They take no part in the floors
    (:func:`layout`) or in which is the main one."""
    gen = json.loads((GENERATED / f"{level}.json").read_text(encoding="utf-8"))
    return [{"id": loc["id"], "item": loc["item"], "at": tuple(np.mean(A.lv.rec_points(loc["id"])[0], axis=0))}
            for loc in gen["locations"] if loc["class"] in ("gem", "cluster") and loc["pool"] and not loc["dead"]]


def features(A, level: str) -> list[dict]:
    """``level``'s features a player steers by, for ``maps.json`` with
    ``at`` their world points (Step 2.97, D278): its save points, key locks
    (at their triggers; e5's four uncoded earth locks have none and aren't
    drawn), seals (at the shapes a touch opens them by) and teleporter pads
    (at each route's touch), in the vanilla data's order. They take no part
    in the floors (:func:`layout`)."""
    gen = json.loads((GENERATED / f"{level}.json").read_text(encoding="utf-8"))
    out = [{"id": s["id"], "kind": "save", "at": where(A, s["id"])} for s in gen["save_points"]]
    out += [{"id": k["id"], "kind": "keylock", "at": where(A, k["trigger"])} for k in gen["keylocks"]
            if k["trigger"]]
    out += [{"id": s["id"], "kind": "seal", "at": where(A, t.split()[0])} for s in gen["seals"] for t in s["touch"]]
    out += [{"id": t["id"], "kind": "teleport", "at": where(A, r["touch"])} for t in gen["teleporters"]
            for r in t["routes"]]
    return out


# --------------------------------------------------------------------------- one level
def layout(A, fr: Frame, F, found: dict, n_floors: int = FLOORS):
    """What a level's pictures draw and on which floor: (the span tops
    drawn, sorted; their :func:`footprint`; the floor of each span top;
    the floors' order).  Every up-facing top is drawn but one no one walks
    on that the game shows nothing on (:func:`unseen`; an icon's own top
    stays), on the at most ``n_floors`` floors :func:`floors` gives, the
    base plane (:func:`base`) on none."""
    spans, w = A.spans, A.W["logic"]
    sp = np.nonzero(A.lv.tri_nz[spans.toptri] > 0.05)[0]
    k, _, _ = footprint(fr, *A.lv.cxy(spans.col[sp]))
    marks = own_tops(A, found, sp[np.unique(k)])
    sp = sp[np.isin(sp, w.sidx[w.reg_soft >= 0]) | np.isin(sp, marks) | ~unseen(A, fr, F, sp)]
    feet = footprint(fr, *A.lv.cxy(spans.col[sp]))
    drawn = sp[np.unique(feet[0])]
    under = base(A, own_tops(A, {"items": found["items"] + found["spots"]}, drawn))
    return (sp, feet) + floors(A, drawn, own_tops(A, found, drawn), under, n_floors)


def render(rd, schema, level: str, detail: float = 1.0):
    """({picture name: (h, w, 3) uint8}, maps.json's entry for ``level``);
    with ``detail`` the pictures are ``detail`` times finer (the GUI's
    detail layer, :func:`draw_detail`), on the same floors in the same
    colours, the entry the same."""
    data, toc, graphs, A = load(rd, schema, level)
    fr = Frame(A.lv)
    spans = A.spans
    F = faces(data, toc, graphs, fr)
    found = icons(A, level)
    shown, (k, px, py), of_span, order = layout(A, fr, F, found, FLOORS_OF.get(level, FLOORS))
    sp = shown[k]
    z = spans.top[sp]
    floor_no = {f: k for k, f in enumerate(order)}
    z0, z1 = float(z.min()), float(z.max())
    area = [int((of_span[sp] == f).sum()) for f in order]      # each floor's pixels on the map
    probe = ground(tops(px, py, z, fr), F)
    lum = probe[~np.isnan(probe[:, 0])] @ np.array([0.3, 0.59, 0.11])
    med = float(np.median(lum)) if len(lum) else 115.0
    gamma = float(np.clip(np.log(0.45) / np.log(min(max(med, 1.0), 254.0) / 255), 0.6, 1.0))
    pic, Fp = (fr, F) if detail == 1 else (fd := Frame(A.lv, detail), faces(data, toc, graphs, fd))
    if detail != 1:
        k, px, py = footprint(pic, *A.lv.cxy(spans.col[shown]))
        sp = shown[k]
        z = spans.top[sp]
    lava_oids = [o["oi"] for o in A.lv.owners if o["oi"] in A.dmg_present and o["attrs"].get("gameVisible")
                 and (o["attrs"].get("WaterSpeed") or "lava" in (o["name"] or "").lower())]
    water = volume_tops(A.water_vol, pic, A.lv)
    lava = volume_tops(A.damage_vol, pic, A.lv, lava_oids)
    whole = paint(level, tops(px, py, z, pic), Fp, water, lava, pic, z0, z1, gamma)
    images = []
    for f in order:
        if len(order) == 1:
            c = whole
        else:
            m = of_span[sp] == f
            c = paint(level, tops(px[m], py[m], z[m], pic), Fp, water, lava, pic, z0, z1, gamma)
            faint = np.where(np.isnan(whole), BACKGROUND, whole) * FAINT + BACKGROUND * (1 - FAINT)
            c = np.where(np.isnan(c), faint, c)
        img = np.where(np.isnan(c), BACKGROUND, c).reshape(pic.h, pic.w, 3)
        images.append(np.clip(np.round(img), 0, 255).astype(np.uint8))
    exits = [{**e, "at": [place(A, fr, of_span, floor_no, *p) for p in e["at"]]} for e in found["exits"]]
    items, spots = ([{**i, "at": place(A, fr, of_span, floor_no, *i["at"][0])} for i in found[key]]
                    for key in ("items", "spots"))
    barriers = []
    for b in found["barriers"]:
        at = []
        for p in (place(A, fr, of_span, floor_no, *p) for p in b["at"]):
            if not any(abs(p[0] - q[0]) + abs(p[1] - q[1]) < 10 and p[2] == q[2] for q in at):
                at.append(p)
        barriers.append({**b, "at": at})
    # the main floor holds the most of them (town's and f3's widest floor is a plane under the level), else
    # the most ground; one on no floor shows on it
    at = [p for e in exits for p in e["at"]] + [i["at"] for i in items + spots] + [p for b in barriers for p in b["at"]]
    held = np.bincount([p[2] for p in at if p[2] >= 0], minlength=len(order))
    main = max(range(len(order)), key=lambda j: (held[j], area[j]))
    feats = []
    for f in features(A, level):      # one marker of a feature to a place
        p = place(A, fr, of_span, floor_no, *f["at"])
        if not any(g["id"] == f["id"] and abs(p[0] - g["at"][0]) + abs(p[1] - g["at"][1]) < 10 for g in feats):
            feats.append({**f, "at": p})
    gem_at = [{**g, "at": place(A, fr, of_span, floor_no, *g["at"])} for g in gems(A, level)]
    for p in at + [f["at"] for f in feats] + [g["at"] for g in gem_at]:
        p[2] = main if p[2] < 0 else p[2]
    names = [level if j == main else f"{level}-{j + 1}" for j in range(len(order))]
    return dict(zip(names, images)), {"size": [fr.w, fr.h], "floors": names, "main": main,
                                      "exits": exits, "items": items, "spots": spots, "barriers": barriers,
                                      "features": feats, "gems": gem_at,
                                      "frame": [round(float(fr.x0), 4), round(float(fr.y1), 4), round(float(fr.s), 6)]}


def thumb(img: np.ndarray, box) -> np.ndarray:
    """``img`` shrunk (nearest) to fit ``box``."""
    h, w = img.shape[:2]
    s = max(w / box[0], h / box[1])
    return img[(np.arange(int(h / s)) * s).astype(int)][:, (np.arange(int(w / s)) * s).astype(int)]
