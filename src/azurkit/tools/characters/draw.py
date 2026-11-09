"""A model drawn in software: its meshes with their own textures, lit, seen
from one side, on a transparent ground (Steps 2.52, 2.93).

:func:`draw` rasterizes :class:`Part` s (a mesh's triangles in one frame
with its first texture stage, read by :mod:`azurik_mod.xbr.render`) at
:data:`SS` times the size and box-filters them down, a 1 px rim round them.
``scripts/render_model_icons.py`` draws the GUI's committed icons with it.
Authoring only: numpy (a runtime dependency); nothing here prints a game byte.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import replace

import numpy as np

from azurkit.tools.characters import render

SS = 8                          # supersampling
PITCH = 25.0                    # degrees the camera looks down
AMBIENT, DIFFUSE = 0.55, 0.7
OUTLINE = (27, 31, 36)          # a 1 px dark rim, so a light model reads on a light table too
PREVIEW_VIEW = (210.0, 15.0)    # a body's yaw and pitch: from its front, a quarter round, a little above
BOOST = 1.6                     # a lit (MODULATE2X) material's texture drawn this much brighter
BATCH_BOX = 32                  # draw_batched: a triangle over this many samples across is drawn alone
BATCH_SAMPLES = 1 << 20         # draw_batched: samples tested at once


# --------------------------------------------------------------------------- models
class Part:
    """A mesh's triangles in one frame: positions (n, 3), UVs (n, 2),
    triangles (m, 3), its texture (h, w, 4, 0-1), its alpha-test reference
    (an opaque texel under it is cut out), whether it blends and each
    triangle's colour (m, 3).  Its first texture stage only; its vertex
    colours (a level's baked light), averaged, only with ``colours``.
    ``row`` is its material row and ``surf`` its texture's TOC index
    (``None``: none), ``boost`` whether its texture is drawn brightened
    (a lit material without ``colours``): the Variants page recolours a
    row's texture and draws it again (Step 2.164c)."""

    def __init__(self, data, toc, me, matrix=None, colours=False):
        p = me.positions
        if matrix is not None:
            m = np.array(matrix)
            p = np.stack([dot(p, m[r, :3]) + m[r, 3] for r in range(3)], 1)
        mt = render.material(data, toc, me.gshd, me.row)
        self.row, self.surf = me.row, mt["textures"][0] if mt.get("textures") else None
        tex = (render.surf_image(data, toc, self.surf).astype(np.float64) / 255 if self.surf is not None
               else np.ones((1, 1, 4)))
        self.tint = np.ones((len(me.triangles), 3))
        self.boost = bool(mt.get("flags", 0) & 0x10) and not colours
        if mt.get("flags", 0) & 0x10 and colours:     # MODULATE2X with its vertex colours' mean
            self.tint[:] = me.colors[me.triangles].mean((0, 1)) / 255 * 2
        elif self.boost:
            tex[:, :, :3] = np.clip(tex[:, :, :3] * BOOST, 0, 1)
        self.P, self.UV, self.T, self.tex = p, me.uvs, me.triangles, tex
        self.blend, self.ref = mt.get("blend") != 500, mt.get("alpha_ref", 0.0)
        self.lit = bool(mt.get("flags", 0) & 0x10)
        if self.blend and mt.get("flags", 0) & 0x20:   # a glow sprite, larger than the model: left out
            self.T = self.T[:0]


def dot(p: np.ndarray, v) -> np.ndarray:
    """Each row of ``p`` dotted with ``v``, without BLAS: the same bytes on every machine."""
    return p[..., 0] * v[..., 0] + p[..., 1] * v[..., 1] + p[..., 2] * v[..., 2]


# --------------------------------------------------------------------------- drawing
def draw(parts: list[Part], yaw: float, size: int, pitch: float = PITCH, roll: float = 0.0, gain: float = 1.0,
         rim: tuple = OUTLINE, ss: int = SS) -> np.ndarray:
    """The parts seen from the front ``yaw`` degrees round and ``pitch``
    above, turned ``roll`` degrees in the picture, lit from the upper left,
    their colour times ``gain``, drawn at ``ss`` times the size: (size,
    size, 4) RGBA uint8, a ``rim`` round them."""
    view = _View(parts, yaw, pitch, roll, size * ss, ss)
    for blend in (False, True):
        layer = []
        for q in parts:
            if q.blend == blend and len(q.T):
                layer += view.triangles(q)
        if blend:
            layer.sort(key=lambda e: -e[0])             # back to front
        for _, x, y, z, uv, tex, s, ref in layer:
            raster(x, y, z, uv, tex, s, ref, blend, view.rgb, view.alpha, view.depth)
    return down(view.rgb, view.alpha, size, gain, rim, ss)


class _View:
    """:func:`draw`'s camera on ``parts`` and its ``n`` x ``n`` buffers."""

    def __init__(self, parts: list[Part], yaw: float, pitch: float, roll: float, n: int, ss: int):
        a, p, r = np.radians(yaw), np.radians(pitch), np.radians(roll)
        right = np.array((np.cos(a), np.sin(a), 0.0))
        fwd = np.array((-np.sin(a), np.cos(a), 0.0))
        look = fwd * np.cos(p) - np.array((0, 0, 1.0)) * np.sin(p)
        up = np.cross(right, look)
        right, up = right * np.cos(r) + up * np.sin(r), up * np.cos(r) - right * np.sin(r)
        light = -look * 0.6 + up * 0.6 - right * 0.5
        light /= np.sqrt(dot(light, light))
        allp = np.concatenate([q.P for q in parts if len(q.T)])
        sx, sy = dot(allp, right), dot(allp, up)
        self.scale = (n - 2 * ss) / max(np.ptp(sx), np.ptp(sy), 1e-9)
        self.cx, self.cy = (sx.max() + sx.min()) / 2, (sy.max() + sy.min()) / 2
        self.right, self.up, self.look, self.light, self.n = right, up, look, light, n
        self.rgb, self.alpha, self.depth = np.zeros((n, n, 3)), np.zeros((n, n)), np.full((n, n), np.inf)

    def screen(self, q: Part) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """``q``'s points on the buffers (X, Y, depth) and each triangle's shade (m, 3)."""
        n = self.n
        X = (dot(q.P, self.right) - self.cx) * self.scale + n / 2
        Y = n / 2 - (dot(q.P, self.up) - self.cy) * self.scale
        Z = dot(q.P, self.look)
        tri = q.P[q.T]
        nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        nrm /= np.maximum(np.sqrt(dot(nrm, nrm)), 1e-12)[:, None]
        nrm *= np.where(dot(nrm, self.look) > 0, -1.0, 1.0)[:, None]          # two-sided: face the camera
        shade = AMBIENT + DIFFUSE * np.clip(dot(nrm, self.light), 0, 1)
        return X, Y, Z, shade[:, None] * q.tint

    def triangles(self, q: Part) -> list:
        """``q``'s triangles as :func:`raster` takes them, each after its mean depth."""
        X, Y, Z, shade = self.screen(q)
        return [(Z[t].mean(), X[t], Y[t], Z[t], q.UV[t], q.tex, s, q.ref) for t, s in zip(q.T, shade)]


def draw_batched(parts: list[Part], yaw: float, size: int, pitch: float = PITCH, ss: int = 2,
                 rim: tuple = OUTLINE) -> np.ndarray:
    """:func:`draw`'s picture (no roll, gain 1) with its opaque triangles
    rasterized together, a batch per box size up to :data:`BATCH_BOX`
    samples across (each sample of a triangle's box tested at once, the
    nearest kept per sample), the larger ones and the blended ones as
    :func:`draw` does: a fraction of a second for booblord's 84,694
    triangles at 160 px, where :func:`draw` takes 4 s or more a view (the
    Variants page's 3D view, Step 2.164c, D772).  The same picture but where two triangles meet at
    one depth."""
    view = _View(parts, yaw, pitch, 0.0, size * ss, ss)
    n, frags = view.n, []
    for q in parts:
        if q.blend or not len(q.T):
            continue
        X, Y, Z, shade = view.screen(q)
        x, y, z = X[q.T], Y[q.T], Z[q.T]
        x0, y0 = np.floor(x.min(1)).astype(np.int64), np.floor(y.min(1)).astype(np.int64)
        span = np.maximum(np.ceil(x.max(1)) - x0, np.ceil(y.max(1)) - y0).astype(np.int64) + 1
        big = span > BATCH_BOX
        for t in np.nonzero(big)[0]:
            raster(x[t], y[t], z[t], q.UV[q.T[t]], q.tex, shade[t], q.ref, False, view.rgb, view.alpha, view.depth)
        sides = np.maximum(2, 1 << np.ceil(np.log2(span)).astype(np.int64))
        for side in np.unique(sides[~big]):
            pick = np.nonzero(~big & (sides == side))[0]
            step = max(1, BATCH_SAMPLES // int(side) ** 2)
            frags += [_batch(q, pick[i:i + step], x, y, z, x0, y0, int(side), shade, n)
                      for i in range(0, len(pick), step)]
    if frags:
        pix, zz, col = (np.concatenate(c) for c in zip(*frags))
        order = np.lexsort((zz, pix))
        pix, zz, col = pix[order], zz[order], col[order]
        first = np.ones(len(pix), bool)
        first[1:] = pix[1:] != pix[:-1]
        pix, zz, col = pix[first], zz[first], col[first]
        flat_d, flat_rgb, flat_a = view.depth.reshape(-1), view.rgb.reshape(-1, 3), view.alpha.reshape(-1)
        near = zz < flat_d[pix]
        pix = pix[near]
        flat_d[pix], flat_rgb[pix], flat_a[pix] = zz[near], col[near], 1.0
    layer = []
    for q in parts:
        if q.blend and len(q.T):
            layer += view.triangles(q)
    layer.sort(key=lambda e: -e[0])
    for _, x, y, z, uv, tex, s, ref in layer:
        raster(x, y, z, uv, tex, s, ref, True, view.rgb, view.alpha, view.depth)
    return down(view.rgb, view.alpha, size, 1.0, rim, ss)


def _batch(q: Part, pick, x, y, z, x0, y0, side: int, shade, n: int):
    """The samples of ``q``'s triangles ``pick`` (each box within ``side``
    samples) that they cover, on the buffers and their alpha test passed:
    (buffer index, depth, colour)."""
    x, y, z = x[pick], y[pick], z[pick]
    gy, gx = np.mgrid[0:side, 0:side]
    px = (x0[pick, None, None] + gx).astype(np.float64) + 0.5
    py = (y0[pick, None, None] + gy).astype(np.float64) + 0.5
    e = (lambda a, i: a[:, i, None, None])
    den = (y[:, 1] - y[:, 2]) * (x[:, 0] - x[:, 2]) + (x[:, 2] - x[:, 1]) * (y[:, 0] - y[:, 2])
    ok = np.abs(den) >= 1e-12
    den = np.where(ok, den, 1.0)[:, None, None]
    l0 = ((e(y, 1) - e(y, 2)) * (px - e(x, 2)) + (e(x, 2) - e(x, 1)) * (py - e(y, 2))) / den
    l1 = ((e(y, 2) - e(y, 0)) * (px - e(x, 2)) + (e(x, 0) - e(x, 2)) * (py - e(y, 2))) / den
    l2 = 1 - l0 - l1
    inside = (l0 >= 0) & (l1 >= 0) & (l2 >= 0) & ok[:, None, None] & (px >= 0) & (px < n) & (py >= 0) & (py < n)
    t, iy, ix = np.nonzero(inside)
    l0, l1, l2 = l0[t, iy, ix], l1[t, iy, ix], l2[t, iy, ix]
    uv = q.UV[q.T[pick]][t]
    u = l0 * uv[:, 0, 0] + l1 * uv[:, 1, 0] + l2 * uv[:, 2, 0]
    v = l0 * uv[:, 0, 1] + l1 * uv[:, 1, 1] + l2 * uv[:, 2, 1]
    h, w = q.tex.shape[:2]
    texel = q.tex[np.floor(v * h).astype(np.int64) % h, np.floor(u * w).astype(np.int64) % w]
    keep = texel[:, 3] >= q.ref
    zz = l0 * z[t, 0] + l1 * z[t, 1] + l2 * z[t, 2]
    col = np.clip(texel[:, :3] * shade[pick][t], 0, 1)
    pix = (py[t, iy, ix].astype(np.int64)) * n + px[t, iy, ix].astype(np.int64)
    return pix[keep], zz[keep], col[keep]


def down(rgb: np.ndarray, alpha: np.ndarray, size: int, gain: float = 1.0, rim: tuple = OUTLINE,
         ss: int = SS) -> np.ndarray:
    """A picture supersampled ``ss`` times (``rgb`` 0-1, ``alpha`` its
    coverage) box-filtered down to ``size`` px, weighted by coverage, its
    colour times ``gain``, then the ``rim`` where a neighbour is covered and
    this pixel less so: (size, size, 4) RGBA uint8."""
    a = alpha.reshape(size, ss, size, ss).mean((1, 3))
    c = (rgb * alpha[:, :, None]).reshape(size, ss, size, ss, 3).sum((1, 3)) / ss ** 2 * gain
    pad = np.pad(a, 1)
    near = np.max([pad[1 + dy:size + 1 + dy, 1 + dx:size + 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)], 0)
    edge = np.clip(near - a, 0, 1) * 0.85
    c += np.array(rim) / 255 * edge[:, :, None]
    a = a + edge
    c /= np.maximum(a, 1e-9)[:, :, None]
    return np.round(np.clip(np.concatenate((c, a[:, :, None]), 2), 0, 1) * 255).astype(np.uint8)


def raster(x, y, z, uv, tex, shade, ref, blend, rgb, alpha, depth) -> None:
    """One triangle into the buffers: textured (nearest, wrapped), shaded
    (``shade`` an RGB); opaque ones alpha-tested at ``ref``, depth-tested
    and written, blended ones composited over."""
    n = rgb.shape[0]
    x0, x1 = max(int(np.floor(x.min())), 0), min(int(np.ceil(x.max())), n - 1)
    y0, y1 = max(int(np.floor(y.min())), 0), min(int(np.ceil(y.max())), n - 1)
    if x0 > x1 or y0 > y1:
        return
    den = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
    if abs(den) < 1e-12:
        return
    py, px = np.mgrid[y0:y1 + 1, x0:x1 + 1] + 0.5
    l0 = ((y[1] - y[2]) * (px - x[2]) + (x[2] - x[1]) * (py - y[2])) / den
    l1 = ((y[2] - y[0]) * (px - x[2]) + (x[0] - x[2]) * (py - y[2])) / den
    l2 = 1 - l0 - l1
    inside = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
    zz = l0 * z[0] + l1 * z[1] + l2 * z[2]
    win = depth[y0:y1 + 1, x0:x1 + 1]
    m = inside & (zz < win)
    if not m.any():
        return
    u = (l0 * uv[0, 0] + l1 * uv[1, 0] + l2 * uv[2, 0])[m]
    v = (l0 * uv[0, 1] + l1 * uv[1, 1] + l2 * uv[2, 1])[m]
    h, w = tex.shape[:2]
    texel = tex[(np.floor(v * h).astype(np.int64)) % h, (np.floor(u * w).astype(np.int64)) % w]
    col = np.clip(texel[:, :3] * shade, 0, 1)
    region_rgb, region_a = rgb[y0:y1 + 1, x0:x1 + 1], alpha[y0:y1 + 1, x0:x1 + 1]
    if not blend:
        keep = texel[:, 3] >= ref
        m[m] = keep
        region_rgb[m], region_a[m], win[m] = col[keep], 1.0, zz[m]
        return
    ta = texel[:, 3:4] * texel[:, :3].max(1, keepdims=True)     # additive: as bright as it is opaque
    region_rgb[m] = col * ta + region_rgb[m] * (1 - ta)
    region_a[m] = ta[:, 0] + region_a[m] * (1 - ta[:, 0])


def png_rgba(img: np.ndarray, level: int = 9) -> bytes:
    """An RGBA uint8 image as PNG bytes, deflated at zlib ``level`` (9:
    the committed pictures' bytes; 6 writes an evidence picture several
    times faster, a few percent bigger)."""
    h, w, _ = img.shape
    raw = b"".join(b"\x00" + img[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return ((b"\x89PNG" + "\r\n\x1a\n".encode("latin-1")) + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, level)) + chunk(b"IEND", b""))


def shrink(img: np.ndarray, k: int) -> np.ndarray:
    """An RGBA uint8 picture box-filtered to 1/``k`` of its size, weighted by coverage."""
    h, w = img.shape[0] // k, img.shape[1] // k
    f = img[:h * k, :w * k].astype(np.float64).reshape(h, k, w, k, 4)
    a = f[..., 3].mean((1, 3))
    c = (f[..., :3] * f[..., 3:4]).mean((1, 3)) / np.maximum(a, 1e-9)[..., None]
    return np.round(np.clip(np.concatenate((c, a[..., None]), 2), 0, 255)).astype(np.uint8)


# --------------------------------------------------------------------------- the picker's pictures
def _apart(part: Part, rest: list[Part]) -> bool:
    """Whether ``part``'s box lies clear of the rest's by more than half
    the rest's size (garret4's staff, 3 m off his side in the bind pose;
    no other body's part lies a tenth of its size off)."""
    if not rest:
        return False
    lo, hi = part.P[part.T.ravel()].min(0), part.P[part.T.ravel()].max(0)
    pts = np.concatenate([q.P[q.T.ravel()] for q in rest])
    rlo, rhi = pts.min(0), pts.max(0)
    gap = np.maximum(np.maximum(lo - rhi, rlo - hi), 0)
    return float(np.sqrt(dot(gap, gap))) > 0.5 * float((rhi - rlo).max())


def body_parts(data, toc, index: int, leave=(), posed=None) -> list[Part]:
    """characters.xbr's body ``index`` as :func:`body_preview` draws it:
    its parts, a lit material's not alpha-tested, one lying apart left out,
    and the groups ``leave`` names (LOD 0's, by index) too; ``posed``: each
    group's positions in a pose (:mod:`~azurkit.tools.characters.pose`), not its bind's."""
    meshes = render.body_meshes(data, toc, index)
    if posed is not None:
        meshes = [replace(me, positions=at) for me, at in zip(meshes, posed)]
    parts = [q for q in (Part(data, toc, me) for k, me in enumerate(meshes) if k not in leave) if len(q.T)]
    for q in parts:
        if q.lit:
            q.ref = 0.0
    return [q for i, q in enumerate(parts) if not _apart(q, parts[:i] + parts[i + 1:])]
