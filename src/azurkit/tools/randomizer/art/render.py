"""A level's graphics: textures, meshes and materials (``docs/XBR_FORMAT.md``
§ "Graphics resources").

* ``surf`` (a texture): +0 the type, low 16 bits the format (0x10 BGRA8,
  0x20 DXT1, 0x40 DXT3; 1 is an animated list whose +4 count and +12 TOC
  indices name the frames); +28/+32 float width and height; +40 an i32
  self-relative pointer to the base level's texels.
* ``gshd`` (materials): +0 the row count, +4 an i32 relative to +4 to a
  table of i32 self-relative row pointers; a row is 100 + 124 x stages
  bytes, +96 the stage count, each stage's +0 the TOC index of its
  ``surf``.
* ``rdms`` (a mesh): +0 5; +4 its ``gshd`` and +8 the row; +24 the vertex
  count; +32 a float origin; +44 the vertex declaration (stride 16, 18
  or 22: an i16 position / 256, a packed normal, BGRA at +10, from
  stride 18 the UV at +14 as i16 / 1024; 0x252, stride 44: a float
  position, BGRA at +24, the UV at +28), the position relative to the
  origin; +48 the part count and +52 an
  i32 relative to +52 to 8-byte parts (u32 index count, i32 relative to
  the part's +4 to u16 triangle lists).  A mesh with no parts is a vertex
  pool whose triangles a push buffer draws.
* ``pbrc``/``pbrw`` (a push buffer): +4 an i32 relative to +4 to NV2A
  commands: 0x17FC begins a primitive (5 triangles, 6 a strip), 0x1800
  sends u16 index pairs and 0x1808 u32 indices.
* The ``levl`` payload's +44 count and +48 self-relative pointer give its
  72-byte static descriptors (the level's world geometry, in world
  coordinates); a ``platform`` record's +0x1C and +0x20 give its own (in
  the platform's frame).  A descriptor's +64 count and +68 pointer list
  16-byte LOD pairs (``rdms``, push buffer, fourcc, distance); the first
  is the most detailed.
* ``body`` (a character model, characters.xbr): +8 the LOD count and +12
  an i32 relative to +12 to that many ``bmsh`` TOC indices (the first
  the most detailed), then LOD 0's 28-byte records, one per group (LOD
  1+'s sit elsewhere: +20), its +0 an i32 self-relative pointer to its
  push buffer (one primitive, ended by 0x17FC 0).  ``bmsh``: +0 the
  group count and +4 an i32 relative to +4 to 40-byte groups: +0 the FVF
  0x1021C, +24 the vertex count, +28 an i32 self-relative pointer to the
  60-byte vertices (float position, four blend weights at +12, normal at
  +28, UV at +40, an unused pair at +48, four bone-slot bytes at +56),
  +32 the ``gshd`` and +36 the row.

Knowledge from Azurik Level Studio's readers (MIT, read for HM-11; no
code copied), checked on the USA disc for Step 2.33.  Authoring only:
numpy (a runtime dependency); nothing here prints or stores a game byte or a
coordinate.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

from azurkit.core.xbr.nodes import TocEntry

STRIDES = {0x80001111: 16, 0x80002111: 18, 0x80004111: 22, 0x80040111: 30, 0x252: 44}


def _rel(data, field: int) -> int:
    return field + struct.unpack_from("<i", data, field)[0]


# --------------------------------------------------------------------------- textures
def _rgb565(c: np.ndarray) -> np.ndarray:
    c = c.astype(np.uint32)
    return np.stack((((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31), -1)


def _dxt_colors(blocks: np.ndarray, four: bool) -> np.ndarray:
    """(n, 16, 4) RGBA texels of n 8-byte DXT colour blocks."""
    c0 = blocks[:, 0].astype(np.uint16) | (blocks[:, 1].astype(np.uint16) << 8)
    c1 = blocks[:, 2].astype(np.uint16) | (blocks[:, 3].astype(np.uint16) << 8)
    p0, p1 = _rgb565(c0).astype(np.int32), _rgb565(c1).astype(np.int32)
    opaque = np.full((len(c0), 1), 255, dtype=np.int32)
    p0, p1 = np.concatenate((p0, opaque), 1), np.concatenate((p1, opaque), 1)
    gt = (c0 > c1)[:, None] | four
    p2 = np.where(gt, (2 * p0 + p1) // 3, (p0 + p1) // 2)
    p3 = np.where(gt, (p0 + 2 * p1) // 3, 0)
    pal = np.stack((p0, p1, p2, p3), 1)                              # (n, 4, 4)
    bits = blocks[:, 4:8].astype(np.uint32)
    word = bits[:, 0] | (bits[:, 1] << 8) | (bits[:, 2] << 16) | (bits[:, 3] << 24)
    idx = (word[:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3
    return np.take_along_axis(pal, idx[:, :, None].astype(np.int64), 1)


def surf_image(data, toc: list[TocEntry], index: int) -> np.ndarray:
    """The base level of ``surf`` ``index`` as (h, w, 4) RGBA uint8 (an
    animated list gives its first frame).  BGRA8 texels are stored linear."""
    t = toc[index]
    base = t.file_offset
    kind = struct.unpack_from("<I", data, base)[0]
    if kind == 1:
        return surf_image(data, toc, struct.unpack_from("<I", data, base + 12)[0])
    fmt = kind & 0xFFFF
    w, h = (int(v) for v in struct.unpack_from("<2f", data, base + 28))
    try:
        return texels(data, _rel(data, base + 40), fmt, w, h)
    except ValueError as exc:
        raise ValueError(f"surf {index}: {exc}") from None


def texels(data, px: int, fmt: int, w: int, h: int) -> np.ndarray:
    """The ``w`` x ``h`` level of format ``fmt`` at ``px`` in ``data`` as
    (h, w, 4) RGBA uint8 (BGRA8 stored linear)."""
    if fmt == 0x10:
        a = np.frombuffer(data, np.uint8, w * h * 4, px).reshape(h, w, 4)
        return a[:, :, [2, 1, 0, 3]].copy()
    if fmt not in (0x20, 0x40):
        raise ValueError(f"format 0x{fmt:X} isn't decoded")
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    size = 8 if fmt == 0x20 else 16
    raw = np.frombuffer(data, np.uint8, bw * bh * size, px).reshape(-1, size)
    if fmt == 0x20:
        cells = _dxt_colors(raw, False)
    else:
        cells = _dxt_colors(raw[:, 8:], True)
        a = raw[:, :8].astype(np.int32)
        nib = np.stack((a & 15, a >> 4), -1).reshape(-1, 16)
        cells[:, :, 3] = nib * 17
    img = cells.reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return img[:h, :w].astype(np.uint8)


def surf_mean(data, toc: list[TocEntry], index: int) -> tuple[np.ndarray, float]:
    """(mean RGB weighted by alpha, mean alpha) of a texture."""
    img = surf_image(data, toc, index).reshape(-1, 4).astype(np.float64)
    a = img[:, 3] / 255.0
    if a.sum() <= 0:
        return img[:, :3].mean(0), 0.0
    return (img[:, :3] * a[:, None]).sum(0) / a.sum(), float(a.mean())


# --------------------------------------------------------------------------- materials
MATERIAL_FIELDS = {"opacity": (76, "<f"), "alpha_ref": (84, "<f"), "blend": (92, "<I")}
"""A material row's written fields: (offset, struct format) of its opacity,
alpha-test reference (+84 [inferred]: a key's keyhole plate is cut out at
it) and blend type."""


def material_row(data, toc: list[TocEntry], gshd: int, row: int) -> int | None:
    """The file offset of ``gshd`` ``gshd``'s row ``row``; None when absent."""
    if not 0 <= gshd < len(toc) or toc[gshd].tag != "gshd":
        return None
    base = toc[gshd].file_offset
    if row >= struct.unpack_from("<I", data, base)[0]:
        return None
    return _rel(data, _rel(data, base + 4) + 4 * row)


def material(data, toc: list[TocEntry], gshd: int, row: int) -> dict:
    """``gshd`` ``gshd``'s row ``row``: its stage textures (TOC indices),
    flags (+72) and :data:`MATERIAL_FIELDS`; {} when absent."""
    start = material_row(data, toc, gshd, row)
    if start is None:
        return {}
    n = struct.unpack_from("<I", data, start + 96)[0]
    stages = [struct.unpack_from("<I", data, start + 100 + 124 * k)[0] for k in range(n)]
    return {"textures": [s for s in stages if s < len(toc) and toc[s].tag == "surf"],
            "flags": struct.unpack_from("<I", data, start + 72)[0],
            **{k: struct.unpack_from(f, data, start + at)[0] for k, (at, f) in MATERIAL_FIELDS.items()}}


# --------------------------------------------------------------------------- meshes
@dataclass
class Mesh:
    """One ``rdms`` (or ``bmsh`` group) with the triangles its binding
    draws: positions (n, 3) in its own frame, vertex colours (n, 3) RGB
    uint8, triangles (m, 3), its material (``gshd`` TOC index, row) and
    texture coordinates (n, 2; zero where the layout has none)."""
    positions: np.ndarray
    colors: np.ndarray
    triangles: np.ndarray
    gshd: int
    row: int
    uvs: np.ndarray


def _pushbuffer(data, at: int, stop: int, once: bool = False) -> list[int]:
    """The triangles (flat index list) of the NV2A commands from ``at``;
    ``once``: only the first primitive (a ``body`` group's)."""
    out, strip, mode = [], [], None

    def flush():
        if mode == 6:
            for i in range(2, len(strip)):
                t = (strip[i - 2], strip[i - 1], strip[i]) if i % 2 == 0 else (strip[i - 1], strip[i - 2], strip[i])
                if len(set(t)) == 3:
                    out.extend(t)
        elif mode == 5:
            for i in range(0, len(strip) - 2, 3):
                if len(set(strip[i:i + 3])) == 3:
                    out.extend(strip[i:i + 3])
        strip.clear()

    while at + 4 <= stop:
        cmd = struct.unpack_from("<I", data, at)[0]
        if cmd == 0:
            break
        n, method = (cmd >> 18) & 0x7FF, cmd & 0x1FFF
        vals = struct.unpack_from(f"<{n}I", data, at + 4)
        if method == 0x17FC:
            for v in vals:
                flush()
                mode = v or None
            if once and mode is None and out:
                break
        elif method == 0x1800:
            for v in vals:
                strip.extend((v & 0xFFFF, v >> 16))
        elif method == 0x1808:
            strip.extend(vals)
        else:
            raise ValueError(f"push buffer at 0x{at:X}: method 0x{method:X} isn't decoded")
        at += 4 + 4 * n
    flush()
    return out


def mesh(data, toc: list[TocEntry], rdms: int, prim: int | None = None) -> Mesh:
    """``rdms`` ``rdms`` with its own triangle lists, or the push buffer
    ``prim``'s when it is a vertex pool."""
    base = toc[rdms].file_offset
    h = struct.unpack_from("<8I3f5I", data, base)
    if h[0] != 5 or h[11] not in STRIDES:
        raise ValueError(f"rdms {rdms}: magic {h[0]} or declaration 0x{h[11]:X} isn't decoded")
    n, stride, parts = h[6], STRIDES[h[11]], h[12]
    raw = np.frombuffer(data, np.uint8, n * stride, base + 64).reshape(n, stride)
    uv = np.zeros((n, 2))
    if stride == 44:
        pos = raw[:, :12].copy().view("<f4").astype(np.float64)
        bgra = raw[:, 24:28]
        uv = raw[:, 28:36].copy().view("<f4").astype(np.float64)
    else:
        pos = raw[:, :6].copy().view("<i2").astype(np.float64) / 256.0
        bgra = raw[:, 10:14]
        if stride >= 18:
            uv = raw[:, 14:18].copy().view("<i2").astype(np.float64) / 1024.0
    pos = pos + np.array(h[8:11])
    tris = []
    if parts:
        table = base + 52 + h[13]
        for k in range(parts):
            cnt, _ = struct.unpack_from("<Ii", data, table + 8 * k)
            tris.append(np.frombuffer(data, "<u2", cnt, _rel(data, table + 8 * k + 4)).astype(np.int64))
    elif prim is not None:
        pb = toc[prim]
        tris.append(np.array(_pushbuffer(data, _rel(data, pb.file_offset + 4), pb.file_offset + pb.size),
                             dtype=np.int64))
    t = np.concatenate(tris).reshape(-1, 3) if tris else np.zeros((0, 3), np.int64)
    t = t[(t < n).all(1)]
    return Mesh(pos, bgra[:, [2, 1, 0]].copy(), t, h[1], h[2], uv)


def body_meshes(data, toc: list[TocEntry], body: int) -> list[Mesh]:
    """``body`` ``body``'s most detailed LOD: a Mesh per ``bmsh`` group,
    in the model's frame (z up), white."""
    base, stop = toc[body].file_offset, toc[body].file_offset + toc[body].size
    lods = _rel(data, base + 12)
    records = lods + 4 * struct.unpack_from("<I", data, base + 8)[0]
    bmsh = toc[struct.unpack_from("<I", data, lods)[0]].file_offset
    groups = _rel(data, bmsh + 4)
    out = []
    for k in range(struct.unpack_from("<I", data, bmsh)[0]):
        g = groups + 40 * k
        n, _, gshd, row = struct.unpack_from("<4I", data, g + 24)
        v = np.frombuffer(data, "<f4", 15 * n, _rel(data, g + 28)).reshape(n, 15).astype(np.float64)
        t = np.array(_pushbuffer(data, _rel(data, records + 28 * k), stop, once=True), dtype=np.int64).reshape(-1, 3)
        out.append(Mesh(v[:, :3], np.full((n, 3), 255, np.uint8), t[(t < n).all(1)], gshd, row, v[:, 10:12]))
    return out


def _descriptors(data, start: int, count: int, every: bool = False) -> list[tuple[int, int]]:
    """The first LOD pair (rdms, push buffer) of ``count`` 72-byte
    descriptors; ``every``: each of their LOD pairs."""
    out = []
    for k in range(count):
        d = start + 72 * k
        lods = struct.unpack_from("<I", data, d + 64)[0]
        if struct.unpack_from("<I", data, d + 28)[0] != 5 or not lods:
            continue
        pairs = _rel(data, d + 68)
        out += [struct.unpack_from("<II", data, pairs + 16 * j) for j in range(lods if every else 1)]
    return out


def static_bindings(data, toc: list[TocEntry]) -> list[tuple[int, int]]:
    """The level's world geometry: (rdms, push buffer) of each static
    descriptor of its ``levl``, most detailed LOD."""
    levl = next((t for t in toc if t.tag == "levl"), None)
    if levl is None:
        return []
    count = struct.unpack_from("<I", data, levl.file_offset + 44)[0]
    return _descriptors(data, _rel(data, levl.file_offset + 48), count) if count else []


def platform_bindings(graph, i: int, every: bool = False) -> list[tuple[int, int]]:
    """A ``platform`` record's (rdms, push buffer) pairs, most detailed LOD
    (``every``: each LOD's); its vertices sit in the platform's frame
    (``graph.world(i)``)."""
    ro = graph.recs[i]
    count = struct.unpack_from("<I", graph.s, ro + 0x1C)[0]
    if not count:
        return []
    start = _rel(graph.s, ro + 0x20)
    return _descriptors(graph.s, start, count, every)
