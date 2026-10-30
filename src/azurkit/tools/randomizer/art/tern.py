"""The ``tern`` sections: Azurik's collision meshes.

The layout is ``docs/XBR_FORMAT.md`` § "`tern` (collision)", and the
engine side ``docs/RE_XBE.md`` § "Collision (`tern`): the engine side".
In short (little-endian):

    section   +0 u32 n chunks (>= 1); +4 i32 self-relative from +4 to the
              spatial structure; +8 u32 off[n] from the section start
              (off[0] = 8 + 4n, ascending, 4-aligned); after the last
              chunk 0-2 B of padding, one u32 and the spatial structure
              (neither decoded), up to the section's end.
    chunk     +0 i16 min[3] and +8 i16 max[3] (whole metres: the floor and
              ceiling of the vertices), +6 u8 vertex count, +7 u8 face
              count, +14 i16 centre[3], +20 u16 flags; then the vertices
              (i16[3], centre + v / 256 m), the faces (three vertex indices
              and a group byte, non-decreasing and <= the face's index) and
              0 or 2 B of padding to the next 4-aligned chunk.
    flags     0xC000 on every platform-owned chunk (the platform's
              attributes give its collision word); 0x8050 / 0x8051 /
              0x8052 / 0x8013 on static chunks: solid / slippery /
              climbable / all three without 0x40 [inferred, strong].

A level's static collision is the ``tern`` its ``levl`` payload names at
+0x00 (a u32 TOC index), in world coordinates.  Every other ``tern`` is
a platform's (a ``platform`` node record's +0x24); reading those owners
needs the node graph, so :mod:`azurik_mod.xbr.collision` reads them, with
the world placement and collision words, on top of ``xbr/nodes.py``
(Step R1.3a, Q300).

Ported from the R0 evidence (``randomizer-plan-2026-10-10``,
``geometry/tern.py`` at ``4b8f3f3``; D110 O-5).  Nothing here prints or
stores game bytes or world positions: :func:`census` returns counts.
"""

from __future__ import annotations

import collections
import math
import struct
from collections.abc import Iterable
from dataclasses import dataclass, field

from azurkit.core.xbr.nodes import parse_toc

TAG = "tern"
CHUNK_HEADER = 22
LEVL_TERN_FIELD = 0x00        # u32 TOC index in the `levl` payload

PLATFORM_CHUNK = 0xC000
STATIC_CLASSES = {0x8050: "solid", 0x8051: "slippery", 0x8052: "climbable", 0x8013: "exception"}
KNOWN_FLAGS = frozenset(STATIC_CLASSES) | {PLATFORM_CHUNK}


@dataclass
class Chunk:
    flags: int
    bmin: tuple
    bmax: tuple
    centre: tuple
    verts: list          # [(x, y, z)] metres in the tern's own frame
    faces: list          # [(a, b, c, group)]


@dataclass
class Tern:
    toc_index: int
    size: int
    chunks: list
    tree: int            # section offset of the spatial structure (4 + rel)
    violations: list = field(default_factory=list)

    @property
    def n_vertices(self):
        return sum(len(c.verts) for c in self.chunks)

    @property
    def n_triangles(self):
        return sum(len(c.faces) for c in self.chunks)


def parse(buf: bytes, toc_index: int = -1) -> Tern:
    """Parse one ``tern`` payload.  Never raises on bad data: each
    problem goes to ``.violations`` as a short code (no bytes)."""
    v = []
    size = len(buf)
    if size < 12:
        return Tern(toc_index, size, [], 0, ["short"])
    n, rel = struct.unpack_from("<Ii", buf, 0)
    tree = 4 + rel
    if n == 0:
        v.append("n0")
    if 8 + 4 * n > size:
        return Tern(toc_index, size, [], tree, v + ["table_past_end"])
    offs = struct.unpack_from(f"<{n}I", buf, 8)
    if offs and offs[0] != 8 + 4 * n:
        v.append("off0")
    if any(b <= a for a, b in zip(offs, offs[1:])):
        v.append("offsets_not_ascending")
    if any(o % 4 for o in offs):
        v.append("chunk_not_4_aligned")
    if not (offs and offs[-1] < tree <= size):
        v.append("tree_out_of_range")
    chunks = []
    for k, o in enumerate(offs):
        nxt = offs[k + 1] if k + 1 < n else tree - 4
        if o + CHUNK_HEADER > size:
            v.append("chunk_header_past_end")
            break
        bmin = struct.unpack_from("<3h", buf, o)
        nv, nf = buf[o + 6], buf[o + 7]
        bmax = struct.unpack_from("<3h", buf, o + 8)
        cen = struct.unpack_from("<3h", buf, o + 14)
        flags = struct.unpack_from("<H", buf, o + 20)[0]
        end = o + CHUNK_HEADER + 6 * nv + 4 * nf
        pad = nxt - end
        if nv == 0 or nf == 0:
            v.append("empty_chunk")
        if end > nxt or end > size:
            v.append("chunk_past_next")
            continue
        if pad != (-end) % 4:
            v.append("padding_not_4_alignment")
        if flags not in KNOWN_FLAGS:
            v.append("unknown_flags")
        if any(not (bmin[i] <= cen[i] <= bmax[i]) for i in range(3)):
            v.append("centre_outside_bbox")
        raw = struct.unpack_from(f"<{3 * nv}h", buf, o + CHUNK_HEADER)
        for i in range(3 if nv else 0):
            col = raw[i::3]
            lo, hi = cen[i] + min(col) / 256.0, cen[i] + max(col) / 256.0
            if bmin[i] != math.floor(lo) or bmax[i] != math.ceil(hi):
                v.append("bbox_not_floor_ceil")
                break
        fo = o + CHUNK_HEADER + 6 * nv
        fb = buf[fo:fo + 4 * nf]
        faces = [(fb[4 * j], fb[4 * j + 1], fb[4 * j + 2], fb[4 * j + 3]) for j in range(nf)]
        if any(max(f[0], f[1], f[2]) >= nv for f in faces):
            v.append("face_index_out_of_range")
        if any(f[3] > j for j, f in enumerate(faces)) or \
                any(faces[j][3] > faces[j + 1][3] for j in range(nf - 1)):
            v.append("group_byte_order")
        cx, cy, cz = cen
        verts = [(cx + raw[3 * i] / 256.0, cy + raw[3 * i + 1] / 256.0, cz + raw[3 * i + 2] / 256.0)
                 for i in range(nv)]
        chunks.append(Chunk(flags, bmin, bmax, cen, verts, faces))
    return Tern(toc_index, size, chunks, tree, sorted(set(v)))


def census(xbrs: Iterable[tuple[str, bytes]]) -> dict:
    """Counts over every ``tern`` of the given XBR files (name, bytes);
    a file with none is not counted.  ``levl_refs`` counts the ``tern``
    TOC indices the ``levl`` payloads name (their static collision);
    ``levl_problems`` names a file whose ``levl`` names a TOC entry that
    is not a ``tern`` (other than -1) or names one ``tern`` twice."""
    tot = collections.Counter()
    viol = collections.Counter()
    flags = collections.Counter()
    static_tris = collections.Counter()
    problems = []
    for name, data in xbrs:
        toc = parse_toc(data)
        terns = {t.index: parse(bytes(data[t.file_offset:t.file_offset + t.size]), t.index)
                 for t in toc if t.tag == TAG}
        if not terns:
            continue
        refs = collections.Counter()
        for t in toc:
            if t.tag == "levl" and t.size >= 4:
                ti = struct.unpack_from("<I", data, t.file_offset + LEVL_TERN_FIELD)[0]
                if ti < len(toc) and toc[ti].tag == TAG:
                    refs[ti] += 1
                elif ti != 0xFFFFFFFF:
                    problems.append({"file": name, "levl_ref_to_non_tern": ti})
        problems += [{"file": name, "tern": ti, "levl_refs": c} for ti, c in refs.items() if c != 1]
        tot["files"] += 1
        tot["levl_refs"] += len(refs)
        for ti, tn in terns.items():
            tot["sections"] += 1
            tot["chunks"] += len(tn.chunks)
            tot["vertices"] += tn.n_vertices
            tot["triangles"] += tn.n_triangles
            viol.update(tn.violations)
            for ch in tn.chunks:
                flags[hex(ch.flags)] += 1
                if ti in refs:
                    static_tris[hex(ch.flags)] += len(ch.faces)
    return {**dict(tot), "violations": dict(viol), "chunk_flags": dict(flags),
            "static_triangles_by_flags": dict(static_tris), "levl_problems": problems}
