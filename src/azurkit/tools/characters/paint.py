"""A variant's body textures painted anew (Step 2.154 round 3; D456, D482,
D483, D484, D488): W30, after W24's mesh and W29's jiggle.

- **The bake.**  A material row's new texture (``size`` texels square, a
  power of two) is drawn through the edited mesh: each texel the row's
  triangles cover in their final UVs (an ``island`` or ``atlas`` op's, an
  ``unwrap``'s, or their own) takes the vanilla texture at the same
  surface point's old UV (bilinear, wrapped), so the old look survives any
  UV layout, at any size; texels no triangle covers take their nearest
  covered neighbour's colour (:data:`PAD` rings), so filtering and the mip
  chain don't bleed the background in.  The vanilla texture is padded the
  same way first, from the texels the row's triangles' old UVs cover
  (round 9, D552): a bilinear sample at an old island's edge takes no
  colour from past it, which a stretched island drew as a dark line (the
  forehead and chin's midline seam, where her face's mirrored halves meet).
- **The ops**, in recipe order, each on the texels of the triangles its
  region selects (``bone``, ``offset``, ``radius``, ``mirror``, ``only``,
  ``groups``, as a mesh op's; with no ``bone``, every one of the row's;
  with ``feather``, round 7, the texels by their own rest place, the op
  eased in over that distance inside the region's edge):
  - ``skin``: texels whose source colour lies in the ``hue`` window
    (degrees) with a saturation of at least ``sat`` and a value of at
    least ``value`` take the skin colour (the median of the source texels
    the ``from`` region's triangles use whose hue lies in ``match``,
    default Azurik's blue 180-260, saturation at least 0.25), keeping
    ``detail`` of their own luminance's variation about the masked mean
    (0: smooth); ``lift`` scales the colour.
  - ``shade``: soft shading baked in (D484): each vertex's ambient
    occlusion in the rest pose (:func:`occlusion`: rays from the surface
    into a voxel grid of every triangle of the body, the vase left out) and
    a light from above and in front, through the texel's barycentric
    weights: the colour times ``1 - ao (1 - A)`` plus ``light`` times the
    light's cosine, and ``warm`` of a shift towards red and away from
    green where shadowed (the reverse where lit), so the blue isn't flat.
  - ``metal``: texels in the ``hue`` window with saturation at least
    ``sat`` and value at least ``value``: blended ``clean`` of the way to
    their 3 x 3 mean (the noise smoothed), then contrast ``contrast`` about
    their mean value, times ``gain``, saturation times ``chroma`` (a
    brighter, cleaner gold, D488).
  - ``strands`` (round 4, D485): hair that isn't a flat black: texels whose
    value is at most ``below`` gain faint streaks along the texture's v (a
    fixed sum of three waves across u, ``count`` of the first per texture
    width, ``seed`` their phases) of ``value`` at most, and a sheen band
    where the surface faces the light ``from`` (``sheen`` at most), both
    added in the ``tint`` colour (black can't be lit by scaling it);
    round 6 (D512, "make her hair darker (blacker)"): ``dark`` scales
    those texels first (1: as they were).
  - ``fill`` (round 8, D533): every texel the region selects takes
    ``colour`` (RGB, 0-1): new geometry's own colour where its UVs lie in
    a part of the texture no other triangle uses (a blue gem on a material
    with no blue); with ``mix`` (0-1, D552) only that share of it, the
    texel's own kept under it (a lip colour or an eyeshadow over her
    face's shading).
  - ``sharpen`` (Step 2.177d, D698: her face's detail from her paint
    source at the face's own scale): an unsharp mask, each texel plus
    ``amount`` of its difference from its Gaussian blur over the region's
    texels (no other island's), the blur's sigma ``texels`` (1 by default) texels of the
    source at the region's own scale (its triangles' new UV area over their
    old, in texels of each), so a source upsampled through the bake gets
    its edges back however far it was stretched.
- **The write.**  The texture is a new unnamed ``surf`` (DXT1 by default,
  its whole mip chain, :mod:`azurik_mod.assets.textures`) appended to
  ``characters.xbr``, and the row's stage-0 field (a relocated TOC index)
  names it: vanilla's own texture stays for no one.  A row whose UVs an
  ``island`` or ``atlas`` op laid anew must be repainted (the bake alone
  fixes them); the build refuses one the recipe leaves out (D35).

**Colours** (Step 2.170b, D539, D734: W38, the player's copy):
a recipe's ``colours`` recolour the textures the body's material rows
draw, texel by texel on every level the texture stores (no bake, no
mesh: :func:`recolour`), in a copy of the body as the build leaves it,
``characters/<body>/v/skin`` (:func:`write_colours`), which X47 binds for
the player alone; the body and its NPCs keep their own.  garret4's own
body, which only the player wears, is recoloured in place (Step 2.170c,
D748: its rows name the new textures; no copy, no X47).  The ops:

- ``hsv``: ``hue`` degrees added, ``sat`` and ``value`` times their own,
  on every texel, or with ``window`` [lo, hi] (hue degrees, wrapping)
  only those whose hue lies in it, eased out over ``soft`` degrees
  outside it (10), their hues' spread about the window's middle times
  ``spread`` first (1; 0.3 keeps a skin's shading in a narrow band of
  hues, so a blue's purple shadows don't turn yellow as its blue turns
  tan), and ``sat_min`` (0.15 with a window, else 0) and
  ``value_min`` (0) leaving the greys and blacks, which have no hue,
  eased in over :data:`GATE`.
- ``swap``: texels near the ``from`` colour (RGB, 0-1; their hue and
  saturation, the HSV disc's distance, within ``reach``, 0.15: shading
  doesn't move it) take the ``to`` colour's hue, and their saturation and
  value scale by ``to``'s over ``from``'s, so their shading stays.
- ``png`` (Step 2.203, D544: the round trip): the row's texture is the
  PNG ``file`` (its ``sha256`` checked; an 8-bit RGB or RGBA image of the
  texture's own size, which ``model export --variant`` writes it at), its
  alpha too, every level the texture stores the PNG's box-filtered level
  of that size (:func:`png_levels`), re-encoded in the texture's format;
  it replaces what the ops before it made (the every-row ops too), and the
  ops after it recolour it.  :func:`located` finds the file in the
  recipe's folder before a build or a preview reads it.

Each op weighs a texel 0-1 (the window's soft edge and the gates; a
swap's smoothstep of its distance over the reach) and moves its colour
that share of the way to the op's full change, in RGB.

Alpha is kept (but a ``png`` op's); a channel is clipped to 0-1 only where
the encoding holds no more (D23).

Arithmetic is numpy on the texture and the mesh in a fixed order; nothing
here prints a byte.
"""

from __future__ import annotations

import hashlib
import math
import struct
import zlib
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from azurkit.core import fdlibm, native
from azurkit.tools.characters import textures
from azurkit.tools.characters import render
from azurkit.core.xbr.append import NewResource, append_resources
from azurkit.core.xbr.nodes import parse_toc

PAD = 16
"""How many rings of uncovered texels take their nearest covered
neighbour's colour."""
CELL = 0.01
"""The occlusion grid's cell (model units)."""
RAYS = 48
"""Rays per vertex for the occlusion."""
OPS = ("skin", "shade", "metal", "strands", "fill", "sharpen")
COLOUR_OPS = ("hsv", "swap", "png")
"""A recipe's ``colours`` ops (the module docstring)."""
GATE = 0.05
"""The width an ``hsv`` op's ``sat_min`` and ``value_min`` ease in over,
centred on them."""
SKIN = "v/skin"
"""Where the player's copy of a body lives: ``characters/<body>/v/skin`` (W38, X47)."""


@dataclass(frozen=True)
class Region:
    """A paint op's region (a mesh op's selectors); ``bone`` ``None``: everywhere."""

    bone: str | None = None
    radius: tuple[float, float, float] = (1.0, 1.0, 1.0)
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    mirror: bool = False
    only: tuple[str, ...] = ()
    groups: tuple[int, ...] = ()
    z: tuple[float, float] | None = None
    """[from, to]: the rest centroid's height within it (a crisp band: a
    belt left out)."""
    feather: float = 0.0
    """Above 0 (Step 2.154 round 7, D512: "why does her neck have jagged
    edges"): each texel in or out by its own rest place, not its
    triangle's centroid, and the op's change eased in by a smoothstep of
    its depth inside the ellipsoid and the ``z`` band over this distance
    (model units), so the region's edge is a gradient: a crisp one follows
    its triangles' edges, a stair-step across her throat."""
    uv: tuple[float, float, float, float] | None = None
    """(u0, v0, u1, v1; round 8, D552): only the triangles whose new UVs'
    centroid lies in that rect of the texture (an island's: her eyes'
    whites apart from the lids round them, which lie in the same
    ellipsoid)."""


@dataclass(frozen=True)
class PaintOp:
    """One paint op (the module docstring): its kind, region and numbers."""

    op: str
    region: Region = Region()
    numbers: dict = field(default_factory=dict)
    source: Region | None = None


@dataclass(frozen=True)
class TextureSpec:
    """One of a recipe's ``textures``: the body's material ``row``, the new
    texture's ``size`` and format, and its paint ops."""

    row: int
    size: int
    format: str = "dxt1"
    ops: tuple[PaintOp, ...] = ()


@dataclass(frozen=True)
class ColourSpec:
    """One of a recipe's ``colours`` (W38): its material ``row`` (``None``:
    every row) and its ``hsv``, ``swap`` and ``png`` ops (each a
    :class:`PaintOp` with no region)."""

    row: int | None
    ops: tuple[PaintOp, ...]


@dataclass
class View:
    """The edited mesh as the bake reads it: per vertex its final position,
    unit normal, final and old UV, rest (stored) position, group and
    heaviest bone; the triangles; the bones' names and bind origins."""

    positions: np.ndarray
    normals: np.ndarray
    uvs: np.ndarray
    old_uvs: np.ndarray
    """Each triangle corner's source UV (m, 3, 2)."""
    rest: np.ndarray
    groups: np.ndarray
    heaviest: np.ndarray
    triangles: np.ndarray
    names: tuple[str, ...]
    origins: tuple
    parents: tuple

    @classmethod
    def of_plan(cls, plan) -> "View":
        """The view of a mesh plan that wrote the body whole (W24)."""
        mesh = plan.mesh
        n = len(mesh.ids)
        uvs = [plan.uvs.get(k, mesh.uvs[k]) if plan.uvs else mesh.uvs[k] for k in range(n)]
        corners = mesh.corners or tuple(tuple(mesh.uvs[v] for v in t) for t in mesh.triangles)
        return cls(np.array(plan.final, float), np.array(plan.every_normal, float), np.array(uvs, float),
                   np.array(corners, float), np.array(mesh.positions, float), np.array([g for g, _ in mesh.ids]),
                   np.array(mesh.heaviest), np.array(mesh.triangles, int), tuple(mesh.names), tuple(mesh.origins),
                   tuple(mesh.parents))


def _subtree(view: View, roots) -> set[int]:
    out = set()
    for k in range(len(view.names)):
        a = k
        while a >= 0:
            if view.names[a] in roots:
                out.add(k)
                break
            a = view.parents[a]
    return out


def _mirrored(name: str) -> str:
    from azurkit.tools.characters.mesh_edit import _mirrored as m
    return m(name)


def selected(view: View, tris: np.ndarray, region: Region) -> np.ndarray:
    """Which of ``tris`` (rows of vertex indices) ``region`` selects: its
    groups, its ``only`` bones (each corner's heaviest), its ellipsoid (the
    rest centroid; and its mirror)."""
    ok = np.ones(len(tris), bool)
    if region.groups:
        ok &= np.isin(view.groups[tris], region.groups).all(1)
    if region.uv is not None:
        c = view.uvs[tris].mean(1)
        u0, v0, u1, v1 = region.uv
        ok &= (c[:, 0] >= u0) & (c[:, 0] <= u1) & (c[:, 1] >= v0) & (c[:, 1] <= v1)
    if region.z is not None:
        z = view.rest[tris][:, :, 2].mean(1)
        ok &= (z >= region.z[0]) & (z <= region.z[1])
    if region.bone is None:
        return ok
    if region.bone not in view.names:
        raise ValueError(f"no bone {region.bone!r}")
    o = np.array(view.origins[view.names.index(region.bone)], float) + np.array(region.offset, float)
    centres = view.rest[tris].mean(1)
    sides = [(o, region.only)]
    if region.mirror:
        sides.append((o * np.array([-1.0, 1.0, 1.0]), tuple(_mirrored(n) for n in region.only)))
    hit = np.zeros(len(tris), bool)
    for c, only in sides:
        d = (fdlibm.sq((centres - c) / np.array(region.radius, float))).sum(1) < 1.0
        if only:
            bones = np.array(sorted(_subtree(view, set(only))))
            d &= np.isin(view.heaviest[tris], bones).all(1)
        hit |= d
    return ok & hit


def feathered(view: View, tris: np.ndarray, t: np.ndarray, w: np.ndarray, region: Region) -> np.ndarray:
    """Each texel's share of ``region`` (texel ``i`` on triangle ``tris[t[i]]``
    at barycentric ``w[i]``): :func:`selected`'s 0 or 1 by its triangle; with
    ``feather``, the groups and ``only`` by its triangle and the smoothstep
    of its rest place's depth inside the ellipsoid (the nearer side's; the
    depth ``(1 - s) min(radius)`` at scaled radius ``s``) and the ``z`` band,
    over ``feather``."""
    if not region.feather > 0.0:
        return selected(view, tris, region)[t].astype(float)
    loose = Region(None, groups=region.groups, uv=region.uv)
    ok = selected(view, tris, loose)[t]
    if region.bone is not None and region.only:
        bones = np.array(sorted(_subtree(view, set(region.only))))
        mine = np.isin(view.heaviest[tris], bones).all(1)
        if region.mirror:
            mine |= np.isin(view.heaviest[tris], np.array(sorted(_subtree(
                view, {_mirrored(n) for n in region.only})))).all(1)
        ok &= mine[t]
    rest = (view.rest[tris[t]] * w[..., None]).sum(1)
    depth = np.full(len(t), np.inf)
    if region.bone is not None:
        if region.bone not in view.names:
            raise ValueError(f"no bone {region.bone!r}")
        o = np.array(view.origins[view.names.index(region.bone)], float) + np.array(region.offset, float)
        r = np.array(region.radius, float)
        best = np.full(len(t), -np.inf)
        for c in ([o, o * np.array([-1.0, 1.0, 1.0])] if region.mirror else [o]):
            s = np.sqrt((fdlibm.sq((rest - c) / r)).sum(1))
            best = np.maximum(best, (1.0 - s) * r.min())
        depth = best
    if region.z is not None:
        depth = np.minimum(depth, np.minimum(rest[:, 2] - region.z[0], region.z[1] - rest[:, 2]))
    x = np.clip(depth / region.feather, 0.0, 1.0)
    return np.where(ok, x * x * (3.0 - 2.0 * x), 0.0)


def _raster_corners(corners: np.ndarray, size: int):
    """:func:`_raster` of triangles given by their corners' UVs (m, 3, 2)."""
    m = len(corners)
    return _raster(corners.reshape(-1, 2), np.arange(3 * m).reshape(m, 3), size)


def _raster(uv: np.ndarray, tris: np.ndarray, size: int):
    """Each texel's covering triangle (its index in ``tris``, -1 none) and
    barycentric weights, the triangles drawn in order (a later one over an
    earlier where their UVs overlap), a tiled triangle (UVs past 0..1)
    drawn where it lands with the texture wrapped. A UV that isn't finite
    (at ``size`` texels a side) is refused by name before any cast, which
    each CPU makes of a NaN its own way (D1009: the twin's answer is one)."""
    tid = np.full((size, size), -1, int)
    bary = np.zeros((size, size, 3))
    P = uv[tris] * size                     # (m, 3, 2): u right, v down
    if P.dtype == np.float64 and P.ndim == 3 and P.shape[1:] == (3, 2):   # the compiled kernel's (core.native)
        P, got = np.ascontiguousarray(P), np.full((size, size), -1, np.int64)
        if native.raster(P.ctypes.data, len(P), int(size), got.ctypes.data, bary.ctypes.data):
            return got.astype(tid.dtype, copy=False), bary
    if not (finite := np.isfinite(P).all((1, 2))).all():   # the kernel declines them: here they stop
        raise ValueError(f"paint: triangle {int(np.argmin(finite))} has a UV that isn't finite at {size} texels a side")
    for t in range(len(tris)):
        tri = P[t] - np.floor(P[t].min(0) / size) * size      # its lowest corner's tile at 0
        reach = np.floor(tri.max(0) / size).astype(int)
        for du in range(reach[0] + 1):
            for dv in range(reach[1] + 1):
                a, b, c = tri - np.array([du * size, dv * size])
                den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
                if abs(den) < 1e-12:
                    continue
                x0, x1 = int(math.floor(min(a[0], b[0], c[0]))), int(math.ceil(max(a[0], b[0], c[0])))
                y0, y1 = int(math.floor(min(a[1], b[1], c[1]))), int(math.ceil(max(a[1], b[1], c[1])))
                x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, size - 1), min(y1, size - 1)
                if x0 > x1 or y0 > y1:
                    continue
                gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
                l1 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / den
                l2 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / den
                l3 = 1.0 - l1 - l2
                inside = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
                if not inside.any():
                    continue
                jj, ii = (gy[inside] - 0.5).astype(int), (gx[inside] - 0.5).astype(int)
                tid[jj, ii] = t
                bary[jj, ii] = np.stack([l1[inside], l2[inside], l3[inside]], 1)
    return tid, bary


def _sample(src: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """``src`` (h, w, 4 float) at ``uv`` (n, 2), bilinear, wrapped."""
    h, w = src.shape[:2]
    x = uv[:, 0] * w - 0.5
    y = uv[:, 1] * h - 0.5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    def at(i, j):
        return src[np.mod(j, h), np.mod(i, w)]
    return (at(x0, y0) * (1 - fx) * (1 - fy) + at(x0 + 1, y0) * fx * (1 - fy) + at(x0, y0 + 1) * (1 - fx) * fy
            + at(x0 + 1, y0 + 1) * fx * fy)


def _hsv(rgb: np.ndarray):
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0.0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.degrees(_atan2(math.sqrt(3.0) * (g - b), 2.0 * r - g - b)) % 360.0
    return hue, sat, mx


def _atan2(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """``fdlibm.atan2`` of each point: the compiled kernel's (core.native), else its twin's, ``np.vectorize``'s."""
    y64, x64 = np.ascontiguousarray(y, dtype=np.float64), np.ascontiguousarray(x, dtype=np.float64)
    if y64.shape == x64.shape:
        out = np.empty(y64.shape)
        if native.atan2(y64.ctypes.data, x64.ctypes.data, y64.size, out.ctypes.data):
            return out
    return np.vectorize(fdlibm.atan2, otypes=[float])(y, x)


def _in_window(hue, lo, hi):
    return (hue >= lo) & (hue <= hi) if lo <= hi else (hue >= lo) | (hue <= hi)


def occlusion(view: View, which: np.ndarray, occluders: np.ndarray, reach: float) -> np.ndarray:
    """The ambient occlusion (0 open, 1 shut) of the vertices ``which`` in
    the rest pose: :data:`RAYS` cosine-weighted rays from just off the
    surface along each vertex's normal hemisphere, marched to ``reach``
    through a voxel grid (:data:`CELL`) of the ``occluders`` triangles'
    surface and the inside they close, each hit weighted by how near it
    is."""
    P = view.positions
    T = occluders
    lo = P[T].reshape(-1, 3).min(0) - 2 * CELL - reach
    hi = P[T].reshape(-1, 3).max(0) + 2 * CELL + reach
    dims = np.ceil((hi - lo) / CELL).astype(int) + 1
    occ = np.zeros(dims, bool)
    A, B, C = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    longest = np.maximum(np.maximum(np.linalg.norm(B - A, axis=1), np.linalg.norm(C - B, axis=1)),
                         np.linalg.norm(A - C, axis=1))
    steps = np.maximum(1, np.ceil(longest / (CELL * 0.5)).astype(int))
    for n in np.unique(steps):
        sel = steps == n
        g = np.arange(n + 1)
        ii, jj = np.meshgrid(g, g, indexing="ij")
        keep = ii + jj <= n
        u, v = (ii[keep] / n)[None, :, None], (jj[keep] / n)[None, :, None]
        pts = A[sel][:, None] + u * (B[sel] - A[sel])[:, None] + v * (C[sel] - A[sel])[:, None]
        idx = np.floor((pts.reshape(-1, 3) - lo) / CELL).astype(int)
        occ[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    outside = np.zeros(dims, bool)          # flood from the grid's edge through empty cells
    outside[0, :, :] = outside[-1, :, :] = outside[:, 0, :] = outside[:, -1, :] = True
    outside[:, :, 0] = outside[:, :, -1] = True
    outside &= ~occ
    while True:
        grown = outside.copy()
        grown[1:] |= outside[:-1]
        grown[:-1] |= outside[1:]
        grown[:, 1:] |= outside[:, :-1]
        grown[:, :-1] |= outside[:, 1:]
        grown[:, :, 1:] |= outside[:, :, :-1]
        grown[:, :, :-1] |= outside[:, :, 1:]
        grown &= ~occ
        if (grown == outside).all():
            break
        outside = grown
    solid = ~outside
    # a fixed hemisphere of directions (z up), cosine weighted (Fibonacci spiral)
    k = np.arange(RAYS) + 0.5
    r = np.sqrt(k / RAYS)
    phi = k * math.pi * (3.0 - math.sqrt(5.0))
    sine, cosine = np.vectorize(fdlibm.sin, otypes=[float]), np.vectorize(fdlibm.cos, otypes=[float])
    dirs = np.stack([r * cosine(phi), r * sine(phi), np.sqrt(1.0 - r * r)], 1)
    out = np.zeros(len(which))
    N = view.normals[which]
    N = N / np.maximum(np.linalg.norm(N, axis=1), 1e-12)[:, None]
    helper = np.where(np.abs(N[:, 2:3]) < 0.9, np.array([[0.0, 0.0, 1.0]]), np.array([[1.0, 0.0, 0.0]]))
    tx = np.cross(helper, N)
    tx /= np.maximum(np.linalg.norm(tx, axis=1), 1e-12)[:, None]
    ty = np.cross(N, tx)
    start = P[which] + N * (1.5 * CELL)
    marches = np.arange(1, int(reach / (0.75 * CELL)) + 1) * (0.75 * CELL)
    weight = 1.0 - marches / reach
    for s in range(0, len(which), 2048):
        e = slice(s, s + 2048)
        world = (dirs[None, :, 0:1] * tx[e, None] + dirs[None, :, 1:2] * ty[e, None]
                 + dirs[None, :, 2:3] * N[e, None])                          # (b, R, 3)
        hit = np.zeros(world.shape[:2])
        alive = np.ones(world.shape[:2], bool)
        for d, w in zip(marches, weight):
            q = start[e, None] + world * d
            idx = np.floor((q - lo) / CELL).astype(int)
            idx = np.clip(idx, 0, dims - 1)
            h = solid[idx[..., 0], idx[..., 1], idx[..., 2]] & alive
            hit += h * w
            alive &= ~h
        out[e] = hit.mean(1)
    return out


def bake(view: View, src: np.ndarray, groups: tuple[int, ...], spec: TextureSpec) -> np.ndarray:
    """The new texture (``spec.size`` square RGBA uint8) of the material
    the vertex ``groups`` use, from its vanilla texture ``src`` (h, w, 4
    uint8): the module docstring's bake and ops."""
    size = spec.size
    if size < 4 or size & (size - 1):
        raise ValueError(f"textures row {spec.row}: size {size} is not a power of two of at least 4")
    mine = np.isin(view.groups[view.triangles[:, 0]], groups)
    tris = view.triangles[mine]
    corners = view.old_uvs[mine]
    tid, bary = _raster(view.uvs, tris, size)
    covered = tid >= 0
    rid, _ = _raster_corners(corners, src.shape[0])
    s = _pad(src.astype(float) / 255.0, rid >= 0)        # the source padded past its own triangles' texels
    t = tid[covered]
    w = bary[covered]
    old = (corners[t] * w[..., None]).sum(1)
    colour = _sample(s, old)                             # (n, 4)
    out = np.zeros((size, size, 4))
    pos = (view.positions[tris[t]] * w[..., None]).sum(1)
    nrm = (view.normals[tris[t]] * w[..., None]).sum(1)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)[:, None]
    for i, op in enumerate(spec.ops):
        share = feathered(view, tris, t, w, op.region)
        picked = share > 0.0
        if not picked.any():
            continue
        before = colour.copy() if op.region.feather > 0.0 else None
        if op.op == "skin":
            lo, hi = op.numbers["hue"]
            hue, sat, val = _hsv(colour[:, :3])
            mask = picked & _in_window(hue, lo, hi) & (sat >= op.numbers.get("sat", 0.15)) \
                & (val >= op.numbers.get("value", 0.1))
            ref = selected(view, view.triangles, op.source)
            rid, rbary = _raster_corners(view.old_uvs[ref], src.shape[0])
            rc = s[rid >= 0][:, :3]
            rh, rs, rv = _hsv(rc)
            mlo, mhi = op.numbers.get("match", (180.0, 260.0))
            rc = rc[_in_window(rh, mlo, mhi) & (rs >= 0.25) & (rv >= 0.15)]
            if not len(rc):
                raise ValueError(f"textures row {spec.row}: ops[{i}].from selects no skin texel in its match window")
            skin = np.median(rc, 0) * op.numbers.get("lift", 1.0)
            lum = colour[:, :3].mean(1)
            mean = lum[mask].mean() if mask.any() else 1.0
            k = 1.0 + op.numbers.get("detail", 0.0) * (lum - mean) / max(mean, 1e-6)
            colour[mask, :3] = np.clip(skin[None, :] * k[mask, None], 0.0, 1.0)
        elif op.op == "shade":
            which = np.unique(tris[t[picked]])
            occluders = view.triangles[~np.isin(view.groups[view.triangles[:, 0]], op.numbers.get("skip", ()))]
            ao = np.zeros(len(view.positions))
            ao[which] = occlusion(view, which, occluders, op.numbers.get("reach", 0.12))
            a = (ao[tris[t[picked]]] * w[picked]).sum(1)
            light = np.array(op.numbers.get("from", (0.0, 0.5, 1.0)), float)
            light /= np.linalg.norm(light)
            lit = np.clip(nrm[picked] @ light, 0.0, 1.0)
            c = colour[picked, :3] * (1.0 - op.numbers.get("ao", 0.5) * a)[:, None]
            c += op.numbers.get("light", 0.0) * (fdlibm.sq(lit))[:, None] * c
            warm = op.numbers.get("warm", 0.0) * (a - 0.5 * lit)[:, None] * np.array([[1.0, -0.6, -0.2]])
            colour[picked, :3] = np.clip(c + warm * c.max(1, keepdims=True), 0.0, 1.0)
        elif op.op == "metal":
            lo, hi = op.numbers["hue"]
            hue, sat, val = _hsv(colour[:, :3])
            mask = picked & _in_window(hue, lo, hi) & (sat >= op.numbers.get("sat", 0.15)) \
                & (val >= op.numbers.get("value", 0.1))
            if not mask.any():
                continue
            img = np.zeros((size, size, 3))
            img[covered] = colour[:, :3]
            blur = img.copy()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy or dx:
                        blur += np.roll(np.roll(img, dy, 0), dx, 1)
            blur /= 9.0
            c = colour[mask, :3] + op.numbers.get("clean", 0.0) * (blur[covered][mask] - colour[mask, :3])
            v = c.max(1, keepdims=True)
            m = v.mean()
            v2 = np.clip(((v - m) * op.numbers.get("contrast", 1.0) + m) * op.numbers.get("gain", 1.0), 0.0, 1.0)
            grey = c.mean(1, keepdims=True)
            c = grey + (c - grey) * op.numbers.get("chroma", 1.0)
            c = c / np.maximum(c.max(1, keepdims=True), 1e-6) * v2
            colour[mask, :3] = np.clip(c, 0.0, 1.0)
        elif op.op == "strands":
            _, _, val = _hsv(colour[:, :3])
            mask = picked & (val <= op.numbers.get("below", 0.12))
            if not mask.any():
                continue
            colour[mask, :3] *= op.numbers.get("dark", 1.0)
            uv = (view.uvs[tris[t[mask]]] * w[mask][..., None]).sum(1)
            phase = np.random.default_rng(int(op.numbers.get("seed", 1))).uniform(0.0, 2.0 * math.pi, 3)
            k = op.numbers.get("count", 40.0) * np.array([1.0, 1.618, 2.718])
            sine = np.vectorize(fdlibm.sin, otypes=[float])
            wave = (sine(2.0 * math.pi * k[0] * uv[:, 0] + phase[0])
                    + 0.6 * sine(2.0 * math.pi * k[1] * uv[:, 0] + phase[1])
                    + 0.4 * sine(2.0 * math.pi * k[2] * uv[:, 0] + phase[2])) / 2.0
            light = np.array(op.numbers.get("from", (0.0, -0.5, 1.0)), float)
            light /= np.linalg.norm(light)
            band = fdlibm.sq(np.clip((nrm[mask] @ light - 0.55) / 0.45, 0.0, 1.0))
            add = (op.numbers.get("value", 0.12) * fdlibm.sq(np.clip(wave, 0.0, 1.0))
                   + op.numbers.get("sheen", 0.0) * band)
            tint = np.array(op.numbers.get("tint", (0.55, 0.62, 0.8)), float)
            colour[mask, :3] = np.clip(colour[mask, :3] + add[:, None] * tint[None, :], 0.0, 1.0)
        elif op.op == "sharpen":
            near = np.unique(t[picked])
            new, was = _uv_area(view.uvs[tris[near]]) * size * size, _uv_area(corners[near]) * fdlibm.sq(src.shape[0])
            sigma = op.numbers.get("texels", 1.0) * (math.sqrt(new / was) if was > 0.0 else 1.0)
            have = np.zeros((size, size))      # the blur over the region's own texels (no other island's)
            have[covered] = picked
            img = np.zeros((size, size, 3))
            img[covered] = colour[:, :3]
            blur = _blurred(img * have[..., None], sigma) / np.maximum(_blurred(have[..., None], sigma), 1e-9)
            c = colour[picked, :3]
            colour[picked, :3] = np.clip(c + op.numbers["amount"] * (c - blur[covered][picked]), 0.0, 1.0)
        elif op.op == "fill":
            mix = op.numbers.get("mix", 1.0)
            colour[picked, :3] = np.clip((1.0 - mix) * colour[picked, :3]
                                         + mix * np.array(op.numbers["colour"], float), 0.0, 1.0)
        else:
            raise ValueError(f"textures row {spec.row}: ops[{i}].op {op.op!r} is not one of {', '.join(OPS)}")
        if before is not None:      # a feathered region: its change eased in by each texel's share
            colour = before + (colour - before) * share[:, None]
    out[covered] = colour
    out = _pad(out, covered)
    return np.round(np.clip(out, 0.0, 1.0) * 255.0).astype(np.uint8)


def _uv_area(uv: np.ndarray) -> float:
    """The summed area of triangles' UVs (m, 3, 2)."""
    a, b, c = uv[:, 0], uv[:, 1], uv[:, 2]
    return float(np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])).sum() / 2)


def _blurred(img: np.ndarray, sigma: float) -> np.ndarray:
    """``img`` (h, w, c) blurred by a Gaussian of ``sigma`` texels, each axis
    in turn, wrapped as the texture is sampled."""
    r = max(1, int(math.ceil(3.0 * sigma)))
    k = np.vectorize(fdlibm.exp, otypes=[float])(-0.5 * fdlibm.sq(np.arange(-r, r + 1) / max(sigma, 1e-6)))
    k /= k.sum()
    for axis in (0, 1):
        img = sum(w * np.roll(img, d, axis) for d, w in zip(range(-r, r + 1), k))
    return img


def _pad(img: np.ndarray, have: np.ndarray) -> np.ndarray:
    """``img`` (h, w, c float) with each texel ``have`` lacks the mean of
    its covered neighbours, ring by ring (:data:`PAD` rings, wrapped), and
    any still uncovered the covered texels' mean."""
    out = img.copy()
    have = have.copy()
    for _ in range(PAD):
        if have.all():
            break
        acc = np.zeros(out.shape)
        cnt = np.zeros(have.shape)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            acc += np.roll(np.roll(np.where(have[..., None], out, 0.0), dy, 0), dx, 1)
            cnt += np.roll(np.roll(have, dy, 0), dx, 1)
        grow = ~have & (cnt > 0)
        out[grow] = acc[grow] / cnt[grow, None]
        have |= grow
    out[~have] = out[have].mean(0) if have.any() else 0.0
    return out


def materials(characters: bytes, body: str) -> dict[int, tuple[int, int]]:
    """The body's LOD-0 groups' materials: {group index: (gshd, row)}."""
    from azurkit.tools.characters.characters import body_at, mesh_groups
    toc = parse_toc(characters)
    vid = body_at(characters, body)[0]
    meshes = render.body_meshes(characters, toc, vid)
    groups = [g for g in mesh_groups(characters, body) if g.lod == 0]
    return {g.index: (me.gshd, me.row) for g, me in zip(groups, meshes)}


def _rows(vanilla_xbr: bytes, body: str) -> dict[int, tuple[int, list[int]]]:
    """The body's material rows: {row: (gshd, its LOD-0 groups)}."""
    rows: dict[int, tuple[int, list[int]]] = {}
    for g, (gshd, row) in materials(vanilla_xbr, body).items():
        rows.setdefault(row, (gshd, []))[1].append(g)
    return rows


def _baked(view: View, item: tuple):
    """One spec's texture baked and encoded (its ``surf`` payload), or the
    :class:`ValueError` the bake raised (:func:`bakes`' worker)."""
    src, groups, spec = item
    try:
        return textures.surf(bake(view, src, groups, spec), textures.FORMATS[spec.format])
    except ValueError as exc:
        return exc


def bakes(vanilla_xbr: bytes, body: str, plan, specs: tuple[TextureSpec, ...]) -> list[bytes]:
    """W30's textures (:func:`write`): each spec's baked from ``plan`` and
    the vanilla texture of its row and encoded, its ``surf`` payload, each
    in a worker process (:func:`azurik_mod.assets.pool.each`, Step 2.176:
    a build bakes them while W29 rigs).  :class:`ValueError` names the
    first of :func:`write`'s refusals, in its order."""
    from azurkit.tools.characters import pool

    rows = _rows(vanilla_xbr, body)
    asked = {s.row for s in specs}
    if plan is None or plan.mesh is None:
        raise ValueError("W30: a variant's textures are baked through its mesh: give it a mesh that writes the body "
                         "whole (a subdivide)")
    mats = materials(vanilla_xbr, body)
    for g in plan.repaint:
        if mats[g][1] not in asked:
            raise ValueError(f"W30: group {g}'s UVs were laid anew (an island or atlas op), so its material row "
                             f"{mats[g][1]} must be repainted: add it to the recipe's textures")
    view = View.of_plan(plan)
    vtoc = parse_toc(vanilla_xbr)
    items, stop = [], None
    for spec in specs:      # each spec's source, up to the first that fails (raised after the bakes before it)
        try:
            if spec.row not in rows:
                raise ValueError(f"W30: {body} has no material row {spec.row} (it has "
                                 f"{', '.join(map(str, sorted(rows)))})")
            gshd, groups = rows[spec.row]
            old = struct.unpack_from("<I", vanilla_xbr, render.material_row(vanilla_xbr, vtoc, gshd, spec.row) + 100)[0]
            items.append((render.surf_image(vanilla_xbr, vtoc, old), tuple(groups), spec))
        except ValueError as exc:
            stop = exc
            break
    out = pool.each(_baked, view, items, least=1)
    for got in out:
        if isinstance(got, ValueError):
            raise got
    if stop is not None:
        raise stop
    return out


def scaled(vanilla_xbr: bytes, body: str, specs: tuple[TextureSpec, ...], scale: int,
           dropped: tuple[int, ...] = ()) -> tuple[TextureSpec, ...]:
    """``specs`` with every material row of ``body`` at ``scale`` times its
    width and height (a recipe's ``texture_scale``, Step 2.177, D680): each
    spec's row at its size times it, then each other row from its vanilla
    texture at that texture's size times it in its format, with no ops (the
    game's look sampled anew through the mesh), but a row only ``dropped``
    groups drew (a mesh's drop, Step 4.3: no triangle left to sample it
    through).  :class:`ValueError` names a row whose vanilla texture isn't
    square or whose size passes 4,096."""
    out = [replace(s, size=s.size * scale) for s in specs]
    vtoc, painted = parse_toc(vanilla_xbr), {s.row for s in specs}
    names = {v: k for k, v in textures.FORMATS.items()}
    for row, (gshd, groups) in sorted(_rows(vanilla_xbr, body).items()):
        if row in painted or set(groups) <= set(dropped):
            continue
        old = struct.unpack_from("<I", vanilla_xbr, render.material_row(vanilla_xbr, vtoc, gshd, row) + 100)[0]
        t = vtoc[old]
        got = textures.info(vanilla_xbr[t.file_offset:t.file_offset + textures.HEADER])
        if got.get("width") != got.get("height") or got.get("format") not in names:
            raise ValueError(f"W30: texture_scale: {body}'s row {row} texture (surf {old}) is not a square DXT1, "
                             "DXT3 or BGRA8 one")
        out.append(TextureSpec(row, got["width"] * scale, names[got["format"]]))
    for s in out:
        if s.size > 4096:
            raise ValueError(f"W30: texture_scale: row {s.row} at {s.size}x{s.size} is past the 4096 texels a side "
                             "a texture's chain rule is known to")
    return tuple(out)


def write(characters: bytearray, vanilla_xbr: bytes, body: str, plan, specs: tuple[TextureSpec, ...],
          payloads: list[bytes] | None = None) -> list[str]:
    """W30: each spec's texture baked from ``plan`` (a mesh plan that wrote
    the body whole) and the vanilla texture of its row (``payloads``, as
    :func:`bakes` gives them, or baked here), appended as a new ``surf``
    and named by the row's stage 0 in ``characters`` (in place: the grown
    file); log lines.  :class:`ValueError` names a row the plan laid anew
    that no spec repaints, a row the body lacks, or a bad op."""
    if payloads is None:
        payloads = bakes(vanilla_xbr, body, plan, specs)
    rows = _rows(vanilla_xbr, body)
    vtoc = parse_toc(vanilla_xbr)
    log = []
    data = bytes(characters)
    for spec, payload in zip(specs, payloads):
        gshd, groups = rows[spec.row]
        old = struct.unpack_from("<I", vanilla_xbr, render.material_row(vanilla_xbr, vtoc, gshd, spec.row) + 100)[0]
        count = len(parse_toc(data))
        data = append_resources(data, [NewResource(None, "surf", payload)])
        toc = parse_toc(data)
        at = render.material_row(data, toc, gshd, spec.row) + 100
        grown = bytearray(data)
        struct.pack_into("<I", grown, at, count)
        data = bytes(grown)
        log.append(f"row {spec.row} ({len(groups)} groups): a {spec.size}x{spec.size} {spec.format} texture, "
                   f"{len(spec.ops)} paint ops, surf {count} (was {old})")
    characters[:] = data
    return log


# --- W38: a recipe's colours, on the player's copy of the body (Step 2.170b, D539, D734) ---
def _step(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def hsv_of(rgb: np.ndarray):
    """Hue (degrees), saturation and value (0-1) of ``rgb`` (..., 3; 0-1),
    the hexcone's (:func:`rgb_of` is its inverse)."""
    rgb = np.asarray(rgb, float)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    v = rgb.max(-1)
    c = v - rgb.min(-1)
    s = np.where(v > 0, c / np.where(v > 0, v, 1.0), 0.0)
    cc = np.where(c > 0, c, 1.0)
    h = np.where(v == r, ((g - b) / cc) % 6.0, np.where(v == g, (b - r) / cc + 2.0, (r - g) / cc + 4.0))
    return np.where(c > 0, h * 60.0, 0.0), s, v


def rgb_of(h, s, v) -> np.ndarray:
    """:func:`hsv_of`'s inverse: (..., 3) RGB, 0-1."""
    h6 = (np.asarray(h) % 360.0) / 60.0
    k = np.floor(h6)
    f = h6 - k
    k = k.astype(int) % 6
    p, q, t = v * (1.0 - s), v * (1.0 - s * f), v * (1.0 - s * (1.0 - f))
    return np.stack((np.choose(k, [v, q, p, p, t, v]), np.choose(k, [t, v, v, q, p, p]),
                     np.choose(k, [p, p, t, v, v, q])), -1)


def _gate(x, lo: float):
    return np.ones(np.shape(x)) if lo <= 0.0 else _step((x - lo) / GATE + 0.5)


def colour(rgb: np.ndarray, op: PaintOp) -> tuple[np.ndarray, np.ndarray]:
    """``rgb`` (n, 3; 0-1) after one ``hsv`` or ``swap`` op (the module
    docstring), and each texel's weight (0: untouched): its colour moved
    that share of the way to the op's full change in RGB, so a texel at a
    soft edge passes through no hue between (blue to tan by way of grey,
    never magenta)."""
    h, s, v = hsv_of(rgb)
    n = op.numbers
    if op.op == "hsv":
        w = np.ones(h.shape)
        window = n.get("window")
        if window is not None:
            lo, hi = window
            span = 360.0 if hi - lo >= 360.0 else (hi - lo) % 360.0
            x = (h - lo) % 360.0
            past = np.where(x <= span, 0.0, np.minimum(x - span, 360.0 - x))
            soft = n.get("soft", 10.0)
            w = 1.0 - _step(past / soft) if soft > 0.0 else (past <= 0.0).astype(float)
            mid = lo + span / 2.0      # the hues' spread about the window's middle, times spread
            h = mid + ((h - mid + 180.0) % 360.0 - 180.0) * n.get("spread", 1.0)
        w = w * _gate(s, n.get("sat_min", 0.15 if window is not None else 0.0)) * _gate(v, n.get("value_min", 0.0))
        dh, ks, kv = n.get("hue", 0.0), n.get("sat", 1.0), n.get("value", 1.0)
    elif op.op == "swap":
        hf, sf, vf = (float(c) for c in hsv_of(n["from"]))
        ht, st, vt = (float(c) for c in hsv_of(n["to"]))
        a, b = np.radians(h), math.radians(hf)
        sine, cosine = np.vectorize(fdlibm.sin, otypes=[float]), np.vectorize(fdlibm.cos, otypes=[float])
        hypot = np.vectorize(math.hypot, otypes=[float])
        d = hypot(s * cosine(a) - sf * fdlibm.cos(b), s * sine(a) - sf * fdlibm.sin(b))
        reach = n.get("reach", 0.15)
        w = _step(1.0 - d / reach) if reach > 0.0 else (d <= 0.0).astype(float)
        dh, ks, kv = (ht - hf + 180.0) % 360.0 - 180.0, st / sf, vt / vf
    else:
        raise ValueError(f"colours: op {op.op!r} is not one of {', '.join(COLOUR_OPS)}")
    full = rgb_of(h + dh, np.clip(s * ks, 0.0, 1.0), np.clip(v * kv, 0.0, 1.0))
    return np.where((w > 0.0)[..., None], rgb + w[..., None] * (full - rgb), rgb), w


_PNGS: dict[tuple, list[np.ndarray]] = {}   # png_levels' reads by file, sha256 and the file's stat
_PNGS_KEPT = 16


def png_levels(file: str, sha256: str) -> list[np.ndarray]:
    """A ``png`` op's image (``file`` an absolute path, :func:`located`;
    its sha256 ``sha256``) as (h, w, 4) RGBA uint8 and its box-filtered
    levels down to 1x1 (:func:`~azurik_mod.assets.textures.chain`), read
    again only when the file changes.  :class:`ValueError` names a file
    that is missing, isn't the recipe's (its sha256), isn't an 8-bit RGB
    or RGBA PNG or whose sides aren't powers of two (a texture's are)."""
    path = Path(file)
    if not path.is_absolute():
        raise ValueError(f"colours: png {file}: no folder holds the recipe's files")
    try:
        st = path.stat()
        key = (str(path), sha256, st.st_mtime_ns, st.st_size)
        if key in _PNGS:
            return _PNGS[key]
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"colours: png {path.name}: {exc.strerror or exc}") from None
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError(f"colours: png {path.name}: its sha256 is {hashlib.sha256(data).hexdigest()}, not the "
                         f"recipe's {sha256}")
    try:
        img = textures.read_png(data)
    except (ValueError, struct.error, zlib.error) as exc:
        raise ValueError(f"colours: png {path.name}: {exc}") from None
    h, w = img.shape[:2]
    if w & (w - 1) or h & (h - 1):
        raise ValueError(f"colours: png {path.name}: {w}x{h}: a texture's sides are powers of two")
    while len(_PNGS) >= _PNGS_KEPT:     # the oldest out (the preview's thread reads it too)
        _PNGS.pop(next(iter(_PNGS), None), None)
    _PNGS[key] = textures.chain(img)
    return _PNGS[key]


def _png_at(op: PaintOp, shape: tuple) -> np.ndarray:
    """A ``png`` op's texels at ``shape`` (h, w): its level of that size, else its image sampled at the nearest
    texel (a preview's tile or every k-th texel of a texture)."""
    levels = png_levels(op.numbers["file"], op.numbers["sha256"])
    for level in levels:
        if level.shape[:2] == tuple(shape):
            return level
    img, (h, w) = levels[0], shape
    return img[((np.arange(h) + 0.5) * img.shape[0] / h).astype(np.int64)][
        :, ((np.arange(w) + 0.5) * img.shape[1] / w).astype(np.int64)]


def located(specs: tuple[ColourSpec, ...], folder) -> tuple[ColourSpec, ...]:
    """``specs`` with each ``png`` op's ``file`` its path in ``folder``
    (the recipe's: beside its file), read and checked
    (:func:`png_levels`); specs with no ``png`` op come back equal.
    :class:`ValueError` names a ``png`` op with no ``folder`` and what
    :func:`png_levels` refuses."""
    out = []
    for s in specs:
        ops = []
        for op in s.ops:
            if op.op == "png":
                if folder is None:
                    raise ValueError(f"colours: png {op.numbers['file']}: no folder holds the recipe's files "
                                     "(a saved variant's are in its folder)")
                op = replace(op, numbers={**op.numbers, "file": str(Path(folder, op.numbers["file"]).absolute())})
                png_levels(op.numbers["file"], op.numbers["sha256"])
            ops.append(op)
        out.append(replace(s, ops=tuple(ops)))
    return tuple(out)


def recoloured(rgba: np.ndarray, ops: tuple[PaintOp, ...]) -> np.ndarray:
    """``rgba`` (..., 4 uint8) after ``ops`` in order; alpha and every
    texel no op weighs kept as they were (a ``png`` op: every texel and its
    alpha the PNG's at ``rgba``'s size, :func:`_png_at`)."""
    rgb, hit, alpha = rgba[..., :3] / 255.0, np.zeros(rgba.shape[:-1], bool), rgba[..., 3]
    for op in ops:
        if op.op == "png":
            img = _png_at(op, rgba.shape[:2])
            rgb, hit, alpha = img[..., :3] / 255.0, np.ones(rgba.shape[:-1], bool), img[..., 3]
            continue
        rgb, w = colour(rgb, op)
        hit |= w > 0.0
    out = rgba.copy()
    out[..., :3] = np.where(hit[..., None], np.round(np.clip(rgb, 0.0, 1.0) * 255.0), rgba[..., :3]).astype(np.uint8)
    out[..., 3] = alpha
    return out


def recolour(payload: bytes, ops: tuple[PaintOp, ...]) -> bytes:
    """A texture ``surf`` payload with ``ops`` run on every level it stores,
    each re-encoded in its format at its own offsets: a DXT block no texel
    of which changed keeps its bytes, so a no-op gives the payload back.
    A texture that isn't square is read as the square chain rule lays it
    out, each side halved down to 1 (Step 2.170c: garret4's 256x512 and
    firefly's 64x128 decode so, each level within 2.4-12.4 of a 2x2 box
    of the one before down to 2x4; the last two, 1x2 and 1x1, a block
    each, aren't (garret4's 86 and 61, firefly's 1x2 193): levels or the
    payload's padding, recoloured texel by texel either way).  A ``png``
    op's image is the base level's size (each level its own level of it).
    :class:`ValueError` for an animated list (its frames are recoloured
    one by one), a payload too short for its chain or a ``png`` of another
    size."""
    got = textures.info(payload)
    if "list" in got:
        raise ValueError("an animated list has no texels: its frames are recoloured one by one")
    fmt, w, h = got["format"], got["width"], got["height"]
    for op in ops:
        img = png_levels(op.numbers["file"], op.numbers["sha256"])[0] if op.op == "png" else None
        if img is not None and img.shape[:2] != (h, w):
            raise ValueError(f"colours: png {Path(op.numbers['file']).name} is {img.shape[1]}x{img.shape[0]}, its "
                             f"texture {w}x{h} (model export --variant writes each row's at its size)")
    out = bytearray(payload)
    at = 40 + struct.unpack_from("<i", payload, 40)[0]
    levels = textures.level_sizes(w, h) if got["mips"] else [(w, h)]
    if at + sum(textures.level_bytes(fmt, lw, lh) for lw, lh in levels) > len(payload):
        raise ValueError(f"a {w}x{h} texture: its {len(payload)} B hold no whole chain of its levels")
    for lw, lh in levels:
        old = render.texels(payload, at, fmt, lw, lh)
        new = recoloured(old, ops)
        if fmt in textures.BLOCK:
            size, bw = textures.BLOCK[fmt], max(1, (lw + 3) // 4)
            changed = (new != old).any(-1)
            for by, bx in zip(*np.nonzero(np.pad(changed, ((0, -lh % 4), (0, -lw % 4))).reshape(
                    -(-lh // 4), 4, -(-lw // 4), 4).any((1, 3)))):
                k = at + (int(by) * bw + int(bx)) * size
                out[k:k + size] = textures.encode(new[4 * by:4 * by + 4, 4 * bx:4 * bx + 4], fmt)
        else:
            out[at:at + textures.level_bytes(fmt, lw, lh)] = textures.encode(new, fmt)
        at += textures.level_bytes(fmt, lw, lh)
    return bytes(out)


def skin_key(body: str) -> str:
    """The key of the player's copy of ``body`` (X47's format, ``characters/%s/v/skin``)."""
    return f"characters/{body}/{SKIN}".casefold()


def drawn_rows(data, toc, body_index: int) -> dict[tuple[int, int], set[int]]:
    """The material rows the body at TOC ``body_index`` draws, {(gshd, row): its LODs}."""
    base = toc[body_index].file_offset
    lods = render._rel(data, base + 12)
    out: dict[tuple[int, int], set[int]] = {}
    for lod in range(struct.unpack_from("<I", data, base + 8)[0]):
        bmsh = toc[struct.unpack_from("<I", data, lods + 4 * lod)[0]].file_offset
        groups = render._rel(data, bmsh + 4)
        for k in range(struct.unpack_from("<I", data, bmsh)[0]):
            out.setdefault(struct.unpack_from("<II", data, groups + 40 * k + 32), set()).add(lod)
    return out


def write_colours(characters: bytes, index_xbr: bytes, body: str, specs: tuple[ColourSpec, ...], *,
                  in_place: bool = False) -> tuple[bytes, bytes, list[str]]:
    """W38: a copy of ``body`` as ``characters`` holds it (the module's
    ``clone.Copier``: everything it reaches but its textures and sounds,
    which it shares), named :func:`skin_key` in it and in ``index_xbr``,
    whose rows draw ``specs``' recolours (:func:`recolour`): an entry with
    no row every row's texture, a named row then its own; a row no entry
    names that draws a named row's texture follows that row, so a far LOD
    doesn't pop; one texture and ops, one new ``surf`` (an animated list
    frame by frame); a texture the ops leave as it was stays shared.  The
    grown characters.xbr and index.xbr, and log lines.  ``in_place``
    (Step 2.170c, D748: garret4's own body, which only the player wears)
    makes no copy: the body's own rows name the new surfs, and
    ``index_xbr`` comes back as it was.  A ``png`` op's file is its path
    (:func:`located`).  :class:`ValueError` names a row the body lacks, a
    named row with no texture, a payload too short for its chain, a
    ``png`` op on an animated list or of another size than its texture."""
    from azurkit.tools.characters.characters import body_at
    from azurkit.tools.characters.index_xbr import IndexRecord, add_index_records
    from azurkit.core.xbr.clone import Batch, Copier

    toc = parse_toc(characters)
    vid, _ = body_at(characters, body)
    rows = drawn_rows(characters, toc, vid)
    named = {s.row: s.ops for s in specs if s.row is not None}
    every = tuple(op for s in specs if s.row is None for op in s.ops)
    have = sorted({r for _, r in rows})
    for r in named:
        if r not in have:
            raise ValueError(f"W38: {body} has no material row {r} (it has {', '.join(map(str, have))})")

    def stage0(g: int, r: int) -> int | None:
        at = render.material_row(characters, toc, g, r)
        return struct.unpack_from("<I", characters, at + 100)[0] if struct.unpack_from(
            "<I", characters, at + 96)[0] else None
    surf = {gr: stage0(*gr) for gr in rows}
    for (g, r), s in sorted(surf.items()):
        if r in named and s is None:
            raise ValueError(f"W38: {body}'s material row {r} draws no texture")
    leads = {s: r for (g, r), s in sorted(surf.items()) if r in named and s is not None}
    batch = Batch(characters)
    copier = None if in_place else Copier(characters, batch, same=True, label="characters.xbr")
    if copier is not None:
        batch[copier.copy(vid)].name = skin_key(body)
    made: dict[tuple[int, str], int] = {}
    log, moved = [], []

    def entry(i: int) -> bytes:
        return bytes(characters[toc[i].file_offset:toc[i].file_offset + toc[i].size])

    def new_surf(i: int, ops: tuple) -> int:
        key = (i, repr(ops))
        if key not in made:
            payload = entry(i)
            kind = textures.info(payload)
            if "list" in kind:
                if any(op.op == "png" for op in ops):
                    raise ValueError(f"W38: {body}'s texture surf {i} is an animated list: a png op makes one "
                                     "texture")
                frames = [new_surf(f, ops) for f in kind["list"]]
                made[key] = i if frames == kind["list"] else batch.add(
                    "surf", textures.list_surf(frames)[0], dict(zip(textures.list_surf(frames)[1], frames)))
            else:
                try:
                    done = recolour(payload, ops)
                except ValueError as exc:
                    raise ValueError(f"W38: {body}'s texture surf {i}: {exc}") from None
                made[key] = i if done == payload else batch.add("surf", done, source=("characters.xbr", i))
        return made[key]
    for (g, r), s in sorted(surf.items()):
        ops = every + named.get(r, named.get(leads.get(s), ()))
        if s is None or not ops:
            continue
        new = new_surf(s, ops)
        if new != s and copier is None:
            moved.append((g, r, new))
        elif new != s:
            batch[copier.copies[g]].point(render.material_row(characters, toc, g, r) + 100 - toc[g].file_offset, new)
        log.append(f"row {r} (LOD {', '.join(map(str, sorted(rows[(g, r)])))}): {len(ops)} colour ops, "
                   + (f"surf {new} (was {s})" if new != s else f"surf {s} unchanged"))
    grown = append_resources(characters, batch.resources())
    if in_place:   # the row's stage 0 (a relocated TOC index) names the new surf, as W30's write does
        out, gtoc = bytearray(grown), parse_toc(grown)
        for g, r, new in moved:
            struct.pack_into("<I", out, render.material_row(grown, gtoc, g, r) + 100, new)
        return bytes(out), index_xbr, log
    index = add_index_records(index_xbr, [IndexRecord(skin_key(body), "characters.xbr", "body")])
    return grown, index, log


def npc_body(characters: bytes, vanilla: bytes, body: str) -> bytes:
    """P2 (Step 2.203, D543): ``characters`` (a build that has made W38's
    copy of ``body``, :func:`write_colours`) with the body's own entries
    back to ``vanilla``'s (the vanilla characters.xbr): its ``body``
    record's LODs, its LODs' ``bmsh`` and every other entry its vanilla
    record reaches but a texture or a sound (:data:`~azurik_mod.xbr.clone.SHARED`,
    which the copy shares: a build adds its own, W30's and W38's), so every
    NPC wearing the body draws vanilla's mesh while the player binds the
    copy (X47): a picked prop's (W31-W33) and a recipe's mesh (W24, W29,
    W30) are the player's alone.  The bones and markers the build appended
    after vanilla's stay, at their indices, in vanilla's place (W31's
    carriers, W29's new jiggle bones, B's markers): a clip the NPCs share
    may key one (W28's restyle, a cast's switch), and a track's index past
    the body's count writes past its scratch (``docs/RE_DATA.md``).
    :class:`ValueError` names a body whose vanilla bones or markers the
    build renamed or reordered (D35)."""
    from azurkit.tools.characters import body_codec
    from azurkit.core.xbr.append import relocations, rewrite_payloads
    from azurkit.core.xbr.clone import SHARED, closure, refs_in

    mine, built = body_codec.read_asset(vanilla, body), body_codec.read_asset(characters, body)
    for what, have, got in (("bones", mine.bones, built.bones), ("markers", mine.markers, built.markers)):
        if [x.name for x in got[:len(have)]] != [x.name for x in have]:
            raise ValueError(f"P2: the build renamed or reordered {body}'s vanilla {what}, so its NPCs can't keep "
                             "vanilla's body")
    mine.bones += built.bones[len(mine.bones):]
    mine.markers += built.markers[len(mine.markers):]
    out = body_codec.write_asset(characters, mine, regroup_groups=False)
    vtoc, toc = parse_toc(vanilla), parse_toc(out)
    vrows, rows = sorted(relocations(vanilla)), sorted(relocations(out))
    rewrite, relocated = {}, {}
    for i in closure(vanilla, [mine.index], vrows):
        if vtoc[i].tag in SHARED or i == mine.index:
            continue
        payload, refs = bytes(vanilla[vtoc[i].file_offset:vtoc[i].file_offset + vtoc[i].size]), refs_in(
            vanilla, vtoc, i, vrows)
        if payload != out[toc[i].file_offset:toc[i].file_offset + toc[i].size] or refs != refs_in(out, toc, i, rows):
            rewrite[i], relocated[i] = payload, [off for off, _ in refs]
    return rewrite_payloads(out, rewrite, relocated=relocated)


__all__ = ["CELL", "COLOUR_OPS", "ColourSpec", "GATE", "OPS", "PAD", "PaintOp", "RAYS", "Region", "SKIN",
           "TextureSpec", "View", "bake", "bakes", "colour", "drawn_rows", "hsv_of", "located", "materials", "npc_body",
           "occlusion", "png_levels", "recolour", "recoloured", "rgb_of", "scaled", "selected", "skin_key", "write",
           "write_colours"]
