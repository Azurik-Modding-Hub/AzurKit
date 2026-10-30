"""An effect platform's mesh: an ``rdms`` and its push buffer read and
written (Step 2.155e, D525: the worn air elemental's spinning funnel).

The layout, as all 1,155 meshes the fx graphs' platforms draw hold it
(both fx archives; ``docs/XBR_FORMAT.md`` § "Graphics resources"):

- ``rdms``: +0 5; +4 the ``gshd`` (a relocated field) and +8 its row;
  +12..+20 1, 0, 0 (a D3DVertexBuffer); +24 the vertex count; +28 36 (a
  self-relative pointer to the vertices at +64); +32 the origin, f32 x3;
  +44 the vertex declaration (:data:`~azurik_mod.xbr.render.STRIDES`);
  +48 the part count, 1, and +52 a pointer relative to +52 to the part
  table at ``align4(64 + count x stride)``: per part a u32 index count
  and an i32 relative to its own field to a u16 triangle list (the
  triangles the push buffer's strip draws), the payload ending with the
  last (unpadded); +56/+60 0.  A vertex of
  declaration 0x80002111 (:data:`DECL`, 18 bytes) is an i16 x3 position
  / 256 from the origin, an 11:11:10 signed normal (x in the low bits),
  BGRA (0, 0, 0, 255 in every vanilla fx mesh) and an i16 x2 UV / 1024.
- a push buffer: +0 the strip's index count less 2; +4 28 (a
  self-relative pointer to the commands at +32); +8..+16 0; +20 and +24
  the commands' size (the end marker and its zero dword in it); +28 its
  own tag; then :func:`~azurik_mod.assets.body_codec.encode_strip`'s
  commands.  A ``pbrc`` up to :data:`PBRC_MAX` bytes in all, a ``pbrw``
  past it (1,043 and 112 of the 1,155).

:func:`read_rdms` and :func:`read_push` decode every one of them and
:func:`write_rdms`, :func:`write_push` give their bytes back
(``tests/test_fx_mesh.py``).  :func:`from_gltf` makes a mesh of a static
glTF (Blender's y up turned to the game's z up).  Every refusal is a
:class:`ValueError` naming what can't be held (D35).  Nothing here prints
a byte.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from azurkit.tools.characters.body_codec import encode_strip, strip_indices, stripify

MAGIC = 5
DECL = 0x80002111
"""The declaration :func:`from_gltf` writes (stride 18: position, normal, BGRA, UV)."""
STRIDES = {0x80001111: 16, 0x80002111: 18, 0x80004111: 22, 0x80040111: 30, 0x252: 44}
HEADER = 64
PB_HEADER = 32
PBRC_MAX = 1028
"""The largest push buffer (bytes, header included) tagged ``pbrc``: every larger one is a ``pbrw``."""
VERTEX_MAX = 0xFFFF
"""The most vertices a mesh's u16 triangle lists name."""
PUSH_MAX = 61748
"""The largest fx push buffer (bytes, its Size): characters.xbr 280, spideyzar's IceballShape, which the game
draws (a body group's cap, :data:`~azurik_mod.assets.body_codec.PUSH_MAX`, is magmar's 22,392)."""
POSITION_UNIT, UV_UNIT = 256.0, 1024.0
BLACK = struct.pack("<4B", 0, 0, 0, 255)


def _align4(n: int) -> int:
    return (n + 3) & ~3


@dataclass(frozen=True)
class Rdms:
    """An ``rdms`` as stored: its material (``gshd`` TOC index, row),
    origin, declaration, vertices (count x stride bytes) and parts (each
    a triangle list of vertex indices; the payload ends with the last)."""
    gshd: int
    row: int
    origin: tuple[float, float, float]
    decl: int
    vertices: bytes
    parts: tuple[tuple[int, ...], ...]

    @property
    def count(self) -> int:
        return len(self.vertices) // STRIDES[self.decl]

    def positions(self) -> np.ndarray:
        """(count, 3) float positions in the mesh's frame (an i16 layout's)."""
        raw = np.frombuffer(self.vertices, np.uint8).reshape(self.count, STRIDES[self.decl])
        return raw[:, :6].copy().view("<i2").astype(np.float64) / POSITION_UNIT + np.array(self.origin)


def read_rdms(payload) -> Rdms:
    """An ``rdms`` payload decoded (module docstring)."""
    h = struct.unpack_from("<8I3f5I", payload, 0)
    if h[0] != MAGIC or h[11] not in STRIDES or h[3:6] != (1, 0, 0) or h[7] != 36 or h[14:16] != (0, 0):
        raise ValueError("not an rdms this reads (its magic, declaration or constant words)")
    count, stride, parts = h[6], STRIDES[h[11]], h[12]
    end = HEADER + count * stride
    table = 52 + struct.unpack_from("<i", payload, 52)[0]
    if table != _align4(end) or any(payload[end:table]):
        raise ValueError("an rdms whose part table isn't right after its vertices")
    lists, at = [], table + 8 * parts
    for k in range(parts):
        n, rel = struct.unpack_from("<Ii", payload, table + 8 * k)
        if table + 8 * k + 4 + rel != at:
            raise ValueError("an rdms whose triangle lists aren't in order after its table")
        lists.append(struct.unpack_from(f"<{n}H", payload, at))
        at += 2 * n
    if at != len(payload):
        raise ValueError("an rdms with bytes after its last triangle list")
    return Rdms(h[1], h[2], tuple(h[8:11]), h[11], bytes(payload[HEADER:end]), tuple(lists))


def write_rdms(m: Rdms) -> bytes:
    """``m``'s payload; +4 holds its ``gshd`` (the caller's relocated field)."""
    end = HEADER + len(m.vertices)
    table = _align4(end)
    out = bytearray(struct.pack("<8I3f5I", MAGIC, m.gshd, m.row, 1, 0, 0, m.count, 36, *m.origin, m.decl,
                                len(m.parts), table - 52, 0, 0))
    out += m.vertices + bytes(table - end)
    at = table + 8 * len(m.parts)
    for k, tris in enumerate(m.parts):
        out += struct.pack("<Ii", len(tris), at - (table + 8 * k + 4))
        at += 2 * len(tris)
    for tris in m.parts:
        out += struct.pack(f"<{len(tris)}H", *tris)
    return bytes(out)


def push_tag(size: int) -> str:
    """A push buffer's tag by its size in bytes (module docstring)."""
    return "pbrc" if size <= PBRC_MAX else "pbrw"


def read_push(payload) -> list[int]:
    """A push buffer's strip (its indices), or a :class:`ValueError`."""
    h = struct.unpack_from("<5I2I4s", payload, 0)
    size = h[5]
    strip = strip_indices(payload, PB_HEADER, size) if len(payload) == PB_HEADER + size else None
    if (strip is None or h[1:5] != (28, 0, 0, 0) or h[6] != size or h[0] != len(strip) - 2
            or h[7] != push_tag(len(payload)).encode("ascii")):
        raise ValueError("not a push buffer this reads (one strip, its header and tag)")
    return strip


def write_push(strip) -> tuple[bytes, str]:
    """``strip``'s push buffer and its tag."""
    cmds = encode_strip(strip)
    tag = push_tag(PB_HEADER + len(cmds))
    return struct.pack("<5I2I4s", len(strip) - 2, 28, 0, 0, 0, len(cmds), len(cmds), tag.encode("ascii")) + cmds, tag


def _normal(n) -> int:
    x, y, z = (float(c) for c in n)
    length = math.sqrt(x * x + y * y + z * z)
    x, y, z = (x / length, y / length, z / length) if length > 1e-12 else (0.0, 0.0, 1.0)
    return (round(x * 1023) & 0x7FF) | ((round(y * 1023) & 0x7FF) << 11) | ((round(z * 511) & 0x3FF) << 22)


def build(positions, normals, uvs, triangles, gshd: int, row: int) -> tuple[Rdms, list[int]]:
    """A :data:`DECL` mesh of ``positions`` (n, 3; metres), ``normals``,
    ``uvs`` and ``triangles`` (vertex indices, their winding kept) on
    material ``gshd`` row ``row``, and the strip that draws it.  Refused:
    past :data:`VERTEX_MAX` vertices, a position past the i16 range from
    the bounds' centre, a UV past the i16 range, a push buffer past
    :data:`PUSH_MAX`."""
    p = np.asarray(positions, np.float64)
    n = len(p)
    if not 0 < n <= VERTEX_MAX:
        raise ValueError(f"{n} vertices: a mesh holds 1 to {VERTEX_MAX} (u16 triangle lists)")
    lo, hi = p.min(0), p.max(0)
    origin = tuple(float(np.float32(c)) for c in (lo + hi) / 2)
    q = np.round((p - origin) * POSITION_UNIT)
    if np.abs(q).max() > 32767:
        raise ValueError(f"a vertex lies {np.abs(p - origin).max():.1f} m from the mesh's centre, past the "
                         f"{32767 / POSITION_UNIT:.0f} m an i16 position holds")
    uv = np.round(np.asarray(uvs, np.float64) * UV_UNIT)
    if np.abs(uv).max() > 32767:
        raise ValueError(f"a UV of {np.abs(np.asarray(uvs)).max():.1f}: past the {32767 / UV_UNIT:.0f} an i16 UV holds")
    tris = [tuple(int(v) for v in t) for t in triangles]
    strip = stripify(tris)
    cmds = len(encode_strip(strip))
    if cmds > PUSH_MAX:
        raise ValueError(f"its push buffer is {cmds} B, past the {PUSH_MAX} B of the largest vanilla fx one "
                         "(characters.xbr 280)")
    verts = b"".join(struct.pack("<3hI", *map(int, q[k]), _normal(normals[k])) + BLACK
                     + struct.pack("<2h", *map(int, uv[k])) for k in range(n))
    return Rdms(gshd, row, origin, DECL, verts, (tuple(v for t in tris for v in t),)), strip


def from_gltf(path: Path, gshd: int, row: int) -> tuple[Rdms, list[int]]:
    """:func:`build` of a static glTF's one mesh (one triangle primitive
    with POSITION, NORMAL, TEXCOORD_0 and indices; its node unmoved; no
    buffer outside the file, so its sha256 pins every byte read), glTF's
    y up turned to the game's z up (x, -z, y)."""
    try:
        return _from_gltf(Path(path), gshd, row)
    except (KeyError, TypeError, IndexError, struct.error, UnicodeDecodeError) as exc:
        raise ValueError(f"not a glTF this import reads ({exc!r})") from None


def _from_gltf(path: Path, gshd: int, row: int) -> tuple[Rdms, list[int]]:
    from azurkit.tools.characters.mesh_edit import _load, _values

    doc, buffers, _ = _load(path)
    if any(not str(b.get("uri", "data:")).startswith("data:") for b in doc.get("buffers", [])):
        raise ValueError("a buffer outside the file (export a .glb)")
    meshes = doc.get("meshes", [])
    if len(meshes) != 1 or len(meshes[0].get("primitives", [])) != 1:
        raise ValueError("a static mesh's glTF holds one mesh of one primitive")
    prim = meshes[0]["primitives"][0]
    if prim.get("mode", 4) != 4 or "indices" not in prim or any(
            a not in prim.get("attributes", {}) for a in ("POSITION", "NORMAL", "TEXCOORD_0")):
        raise ValueError("its primitive isn't indexed triangles with POSITION, NORMAL and TEXCOORD_0")
    for node in doc.get("nodes", []):
        if "mesh" in node and any(k in node for k in ("matrix", "translation", "rotation", "scale")):
            raise ValueError("its mesh's node is moved (apply the transform before the export)")
    a = prim["attributes"]
    pos = np.array(_values(doc, buffers, a["POSITION"]), np.float64)
    nrm = np.array(_values(doc, buffers, a["NORMAL"]), np.float64)
    turn = lambda v: np.stack((v[:, 0], -v[:, 2], v[:, 1]), 1)   # noqa: E731
    idx = [int(i[0]) for i in _values(doc, buffers, prim["indices"])]
    if len(idx) % 3 or any(not 0 <= i < len(pos) for i in idx):
        raise ValueError("its indices aren't whole triangles of its vertices")
    return build(turn(pos), turn(nrm), _values(doc, buffers, a["TEXCOORD_0"]),
                 [idx[k:k + 3] for k in range(0, len(idx), 3)], gshd, row)


def bounds(m: Rdms) -> tuple[float, ...]:
    """``m``'s bounds as a descriptor holds them (min x, y, z, max x, y, z)."""
    p = m.positions()
    return (*map(float, p.min(0)), *map(float, p.max(0)))


__all__ = ["DECL", "PBRC_MAX", "PUSH_MAX", "Rdms", "STRIDES", "VERTEX_MAX", "bounds", "build", "from_gltf", "push_tag",
           "read_push", "read_rdms", "write_push", "write_rdms"]
