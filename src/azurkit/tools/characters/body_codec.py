"""A character body decoded whole, edited and written back with any
topology (Step 2.154, D438, D443: the model toolkit's writer).

:func:`read_asset` decodes a ``body`` payload of ``characters.xbr`` and
the ``bmsh`` payload of each of its LODs into a :class:`BodyAsset`: its
bones (their 160-byte records), markers (0x38-byte records), and per LOD
its groups, each with its palette, its 60-byte vertices
(:class:`Vertex`, as stored: palette space), its drawn triangles (the
strip's, winding kept) and its material.  :func:`encode` lays the asset
out as vanilla does, so an asset read and encoded unchanged gives the
payloads byte for byte (every body of the disc: ``tests/test_model_write.py``),
and :func:`write_asset` puts the payloads into a ``characters.xbr``.

**The layouts** (``docs/XBR_FORMAT.md`` § "Graphics resources", every
body of the USA disc):

- ``body``: a 0x20-byte header (+0 the bone count, +4 a self-relative
  pointer to the bone records, +8 the LOD count, +12 a pointer to the LOD
  list, +16 the LOD count again, +20 a pointer to the per-LOD (group
  count, pointer to its records) pairs, +0x18 the marker count, +0x1C a
  pointer to the marker records, the pairs' place when there are none);
  then the bone records, the marker records, the pairs, the bone names
  and the marker names (NUL-terminated, in order), zeros to 4, the LOD
  list (``bmsh`` TOC indices, relocated), and per LOD its 28-byte group
  records (+0 a pointer to the group's push buffer, +4 the strip's
  indices less 2, +8 a D3DPushBuffer {Common 0x10001, Data 0, Lock 0,
  Size, AllocationSize = Size}) and its push buffers, each Size bytes.
- A push buffer: BEGIN 0x17FC = 6 (a strip), its indices as
  0x40001800 commands of at most 256 dwords (two 16-bit indices each)
  and one 0x1808 dword for an odd last index, END 0x17FC = 0 and a zero
  dword (Size counts it; RunPushBuffer copies Size - 4 bytes, 0x1253AE).
- ``bmsh``: +0 the group count, +4 a pointer to the 40-byte groups at +8
  (+0 FVF 0x1021C, +4 the palette count, +8 a pointer to it, +0xC a
  D3DVertexBuffer {Common 1, Data 0, Lock 0}, +24 the vertex count, +28
  a pointer to the vertices, +32 the ``gshd`` TOC index, relocated, +36
  its row); then per group its palette (i32 bone indices) and, from the
  next 16-byte boundary, its vertices.

**Writing** (:func:`write_asset`, D35: every refusal a
:class:`ValueError` naming the body, LOD, group or vertex, nothing
written): a group whose triangles are its stored ones keeps its stored
push buffer; any other is stripped again (:func:`stripify`: greedy
strips joined by degenerate triangles, each triangle's winding kept,
decoded back and compared).  :func:`regroup` first splits a group past
what the format or the game holds into groups of the same material:
past :data:`PALETTE_MAX` bones (the slot bytes name 31 entries), past
:data:`INDEX_MAX` + 1 vertices (16-bit indices) or past
:data:`PUSH_MAX` bytes of push buffer (vanilla's largest, magmar's: the
game copies each into its main push buffer, whose reserve is unread);
the first part keeps the group's place and the rest follow the LOD's
last group.  Every payload grows in place by whole pages
(:func:`~azurik_mod.xbr.append.rewrite_payloads`), the ``bmsh``'s
relocated ``gshd`` fields follow its groups, and the file is read back:
each payload decodes to the asset, every strip to its triangles.

**LODs** (Step 2.166a, D537): a :class:`Lod` whose ``bmsh`` is ``None``
(a LOD :func:`~azurik_mod.assets.decimate.decimate` cut) is written as a
new unnamed ``bmsh`` appended to the file
(:func:`~azurik_mod.xbr.append.append_resources`, its groups' ``gshd``
fields its relocations), reached only through the body's relocated LOD
list, a load run of its own as vanilla's LOD 1+ are; the counts at +8 and
+16 follow the list.  A LOD given an existing ``bmsh`` of the body is
written over it; LODs left out of the asset are dropped: the count falls
and their entries stay in the file, unreferenced.

A group's palette entry ``e`` is slot byte ``e + 1`` for 0-11 and ``e +
2`` for 12-30 (never 13, the palette upload at 0x9B320).  Nothing here
prints a byte or a coordinate.
"""

from __future__ import annotations

import functools
import heapq
import struct
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from azurkit.core.xbr.append import NewResource, append_resources, rewrite_payloads
from azurkit.core.xbr.nodes import named_resources, parse_toc

Vec = tuple[float, float, float]

VERTEX_SIZE = 60
FVF = 0x1021C
PALETTE_MAX = 31
"""The entries a group's slot bytes can name (1-12 and 14-32)."""
INDEX_MAX = 0xFFFF
"""The largest index a 0x1800 pair holds."""
PUSH_MAX = 22392
"""The largest push buffer (bytes, its Size) of any vanilla group: the
game runs it (magmar's group 0, 11,142 indices)."""
BONE_RECORD = 160
MARKER_RECORD = 0x38
LOD_RECORD = 28
GROUP_RECORD = 40
_BEGIN, _END_VALUE, _STRIP = 0x000417FC, 0, 6
_PAIRS, _ONE = 0x40001800, 0x00041808
_CHUNK = 256
_PB_COMMON, _VB_COMMON = 0x10001, 1


def slot_byte(entry: int) -> int:
    """A palette entry's slot byte."""
    if not 0 <= entry < PALETTE_MAX:
        raise ValueError(f"palette entry {entry} is past the {PALETTE_MAX} a slot byte names")
    return entry + 1 if entry <= 11 else entry + 2


def slot_entry(byte: int) -> int | None:
    """The palette entry a slot byte names, or ``None`` (0, 13, past 32)."""
    if byte == 0 or byte == 13 or byte > 32:
        return None
    return byte - 1 if byte <= 12 else byte - 2


def slot_code(entry: int) -> int:
    """A vertex's code for palette entry ``entry``: its slot byte, or
    0x100 + ``entry`` past the slot range (a palette grown past
    :data:`PALETTE_MAX`, which :func:`regroup` splits before a write;
    no stored vertex holds one)."""
    return slot_byte(entry) if 0 <= entry < PALETTE_MAX else 0x100 + entry


def code_entry(code: int) -> int | None:
    """The palette entry a vertex's slot code names (:func:`slot_code`)."""
    return code - 0x100 if code >= 0x100 else slot_entry(code)


def _f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


@dataclass(frozen=True)
class Vertex:
    """One 60-byte vertex as stored: its position, four blend weights,
    normal, UV, the +48 pair and four slot bytes (palette space)."""

    position: Vec
    weights: tuple[float, float, float, float]
    normal: Vec
    uv: tuple[float, float]
    extra: tuple[float, float] = (0.0, 0.0)
    slots: tuple[int, int, int, int] = (0, 0, 0, 0)

    @classmethod
    def unpack(cls, cell, at: int = 0) -> Vertex:
        f = struct.unpack_from("<14f", cell, at)
        return cls(f[0:3], f[3:7], f[7:10], f[10:12], f[12:14], tuple(cell[at + 56:at + 60]))

    def pack(self) -> bytes:
        return struct.pack("<14f4B", *self.position, *self.weights, *self.normal, *self.uv, *self.extra, *self.slots)

    def skin(self, palette: Sequence[int]) -> dict[int, float]:
        """The vertex's weights by bone (``palette`` its group's), summed
        where two slots name one bone; :class:`ValueError` for a live
        weight on a slot byte outside the palette."""
        out: dict[int, float] = {}
        for w, b in zip(self.weights, self.slots):
            if w > 0:
                e = code_entry(b)
                if e is None or e >= len(palette):
                    raise ValueError(f"a weight's slot byte {b} is outside the {len(palette)}-entry palette")
                out[palette[e]] = out.get(palette[e], 0.0) + w
        return out


def make_vertex(position, normal, uv, skin: Mapping[int, float], palette: list[int],
                extra=(0.0, 0.0)) -> Vertex:
    """A vertex of a group whose palette is ``palette`` (bones it lacks
    are added to its end, in place): ``skin`` ({bone: weight}) cut to its
    four heaviest, renormalised in float32 to sum to 1 (the heaviest
    takes the rounding), heaviest first (ties by bone), unused slots 0
    with byte 0 (vanilla's rule).  :class:`ValueError` for no positive
    weight."""
    live = sorted(((w, b) for b, w in skin.items() if w > 0), key=lambda wb: (-wb[0], wb[1]))[:4]
    if not live:
        raise ValueError("a vertex needs a positive weight")
    total = sum(w for w, _ in live)
    ws = [_f32(w / total) for w, _ in live]
    ws[0] = _f32(1.0 - sum(ws[1:]))
    order = sorted(zip(ws, (b for _, b in live)), key=lambda wb: (-wb[0], wb[1]))
    codes = []
    for _, b in order:
        if b not in palette:
            palette.append(b)
        codes.append(slot_code(palette.index(b)))
    return Vertex(tuple(_f32(c) for c in position), tuple(w for w, _ in order) + (0.0,) * (4 - len(order)),
                  tuple(_f32(c) for c in normal), tuple(_f32(c) for c in uv), tuple(_f32(c) for c in extra),
                  tuple(codes) + (0,) * (4 - len(codes)))


@dataclass
class Group:
    """One ``bmsh`` group: its palette (bone indices), vertices,
    drawn triangles (vertex indices, the strip's winding), material
    (``gshd`` TOC index, row), FVF, the two D3D headers' fields as stored,
    and what the stored push buffer drew (kept while ``triangles`` equals
    it)."""

    palette: list[int]
    vertices: list[Vertex]
    triangles: list[tuple[int, int, int]]
    material: tuple[int, int]
    fvf: int = FVF
    vb: tuple[int, int, int] = (_VB_COMMON, 0, 0)
    pb: tuple[int, int, int] = (_PB_COMMON, 0, 0)
    stored: tuple[tuple[tuple[int, int, int], ...], bytes, int] | None = field(default=None, repr=False)

    def skin(self, k: int) -> dict[int, float]:
        """Vertex ``k``'s weights by bone."""
        return self.vertices[k].skin(self.palette)

    def add(self, position, normal, uv, skin: Mapping[int, float], extra=(0.0, 0.0)) -> int:
        """A new vertex at the end of the group (:func:`make_vertex`, the
        palette grown as it needs); its index."""
        self.vertices.append(make_vertex(position, normal, uv, skin, self.palette, extra))
        return len(self.vertices) - 1

    def remove(self, drop: Iterable[int]) -> list[int]:
        """The vertices ``drop`` taken out with every triangle that uses
        one, the rest kept in order; each old index's new one (-1 for a
        dropped vertex)."""
        gone = set(drop)
        new, n = [], 0
        for k in range(len(self.vertices)):
            new.append(-1 if k in gone else n)
            n += k not in gone
        self.vertices = [v for k, v in enumerate(self.vertices) if k not in gone]
        self.triangles = [tuple(new[v] for v in t) for t in self.triangles if not gone.intersection(t)]
        return new


@dataclass
class Lod:
    """One LOD: its ``bmsh`` TOC index (``None`` for a new one the write
    appends) and groups."""

    bmsh: int | None
    groups: list[Group]


@dataclass
class Bone:
    """One bone record: its name and the 160 bytes as stored (the name's
    length and pointer rewritten on encode)."""

    name: str
    record: bytes

    @property
    def parent(self) -> int:
        return struct.unpack_from("<h", self.record, 8)[0]


@dataclass
class Marker:
    """One marker record: its name and the 0x38 bytes as stored."""

    name: str
    record: bytes


@dataclass
class BodyAsset:
    """A body as :func:`read_asset` decodes it: its name under
    ``characters/``, TOC index, header (0x20 bytes as stored), bones,
    markers and LODs."""

    name: str
    index: int
    header: bytes
    bones: list[Bone]
    markers: list[Marker]
    lods: list[Lod]

    @property
    def bone_names(self) -> list[str]:
        return [b.name for b in self.bones]

    def bone(self, name: str) -> int:
        """The index of the bone ``name``; :class:`ValueError` if none."""
        names = self.bone_names
        if name not in names:
            raise ValueError(f"{self.name} has no bone {name!r}")
        return names.index(name)


# --------------------------------------------------------------------------- reading
def _i32(data, at: int) -> int:
    return struct.unpack_from("<i", data, at)[0]


def _u32(data, at: int) -> int:
    return struct.unpack_from("<I", data, at)[0]


def _rel(data, at: int) -> int:
    return at + _i32(data, at)


def _cstr(data, at: int) -> str:
    return bytes(data[at:data.index(b"\0", at)]).decode("ascii")


def strip_indices(data, at: int, size: int) -> list[int] | None:
    """A push buffer of :func:`encode_strip`'s form at ``at`` (``size``
    bytes): its strip's indices, or ``None`` when it holds anything else."""
    end = at + size
    if size < 20 or _u32(data, at) != _BEGIN or _u32(data, at + 4) != _STRIP:
        return None
    out, p = [], at + 8
    while p + 4 <= end:
        cmd = _u32(data, p)
        n = (cmd >> 18) & 0x7FF
        method = cmd & 0x1FFF
        if cmd == _BEGIN:
            if _u32(data, p + 4) != _END_VALUE or p + 12 != end or _u32(data, p + 8) != 0:
                return None
            return out
        if method == 0x1800 and cmd & 0x40000000 and 0 < n <= _CHUNK:
            for v in struct.unpack_from(f"<{n}I", data, p + 4):
                out.extend((v & 0xFFFF, v >> 16))
        elif cmd == _ONE:
            out.append(_u32(data, p + 4))
        else:
            return None
        p += 4 + 4 * n
    return None


def strip_triangles(strip: Sequence[int]) -> list[tuple[int, int, int]]:
    """The triangles a strip draws (``render._pushbuffer``'s rule): odd
    ones turned so every winding is the strip's; degenerate ones dropped."""
    out = []
    for i in range(2, len(strip)):
        a, b, c = strip[i - 2], strip[i - 1], strip[i]
        t = (a, b, c) if i % 2 == 0 else (b, a, c)
        if a != b and b != c and a != c:
            out.append(t)
    return out


def _body_entry(data: bytes, body: str) -> tuple[int, str]:
    toc, names = parse_toc(data), named_resources(data)
    index = {n.casefold(): i for i, n in names.items()}.get(f"characters/{body}".casefold())
    if index is None or toc[index].tag != "body":
        raise ValueError(f"characters.xbr: no body {body!r}")
    return index, names[index][len("characters/"):]


def read_asset(characters_xbr: bytes, body: str) -> BodyAsset:
    """The body ``characters/<body>`` (case-blind) and its LODs' meshes
    (module docstring); :class:`ValueError` names what doesn't parse."""
    index, name = _body_entry(characters_xbr, body)
    toc = parse_toc(characters_xbr)
    at, size = toc[index].file_offset, toc[index].size
    data = characters_xbr
    try:
        nb, lodn, nm = _i32(data, at), _i32(data, at + 8), _i32(data, at + 0x18)
        if _i32(data, at + 16) != lodn:
            raise ValueError("its two LOD counts differ")
        table = _rel(data, at + 4)
        bones = []
        for k in range(nb):
            rec = table + BONE_RECORD * k
            bones.append(Bone(_cstr(data, _rel(data, rec + 4)), bytes(data[rec:rec + BONE_RECORD])))
        markers = []
        mt = _rel(data, at + 0x1C)
        for k in range(nm):
            rec = mt + MARKER_RECORD * k
            markers.append(Marker(_cstr(data, _rel(data, rec + 4)), bytes(data[rec:rec + MARKER_RECORD])))
        lods_at, pairs = _rel(data, at + 12), _rel(data, at + 20)
        lods = []
        for lod in range(lodn):
            bmsh = _u32(data, lods_at + 4 * lod)
            if not 0 <= bmsh < len(toc) or toc[bmsh].tag != "bmsh":
                raise ValueError(f"LOD {lod} names TOC entry {bmsh}, no bmsh")
            m0 = toc[bmsh].file_offset
            ng = _i32(data, m0)
            groups_at = _rel(data, m0 + 4)
            count = _u32(data, pairs + 8 * lod)
            records = _rel(data, pairs + 8 * lod + 4)
            if count != ng:
                raise ValueError(f"LOD {lod}: {count} records for {ng} groups")
            groups = []
            for g in range(ng):
                ga = groups_at + GROUP_RECORD * g
                fvf, npal = _u32(data, ga), _i32(data, ga + 4)
                palette = list(struct.unpack_from(f"<{npal}i", data, _rel(data, ga + 8))) if npal > 0 else []
                vb = struct.unpack_from("<3I", data, ga + 0xC)
                nv = _i32(data, ga + 24)
                va = _rel(data, ga + 28)
                verts = [Vertex.unpack(data, va + VERTEX_SIZE * j) for j in range(nv)]
                material = struct.unpack_from("<II", data, ga + 32)
                rec = records + LOD_RECORD * g
                pb_at, tri_count = _rel(data, rec), _u32(data, rec + 4)
                common, pdata, lock, psize, alloc = struct.unpack_from("<5I", data, rec + 8)
                push = bytes(data[pb_at:pb_at + psize])
                strip = strip_indices(data, pb_at, psize)
                if strip is None or alloc != psize or len(strip) - 2 != tri_count:
                    raise ValueError(f"LOD {lod} group {g}'s push buffer isn't one strip as vanilla stores them")
                tris = strip_triangles(strip)
                if any(v >= nv for t in tris for v in t):
                    raise ValueError(f"LOD {lod} group {g}: a strip index past its {nv} vertices")
                groups.append(Group(palette, verts, list(tris), material, fvf, vb, (common, pdata, lock),
                                    (tuple(tris), push, tri_count)))
            lods.append(Lod(bmsh, groups))
    except (struct.error, IndexError, UnicodeDecodeError) as exc:
        raise ValueError(f"characters.xbr: body {name!r} doesn't parse: {exc}") from None
    except ValueError as exc:
        raise ValueError(f"characters.xbr: body {name!r}: {exc}") from None
    return BodyAsset(name, index, bytes(data[at:at + 0x20]), bones, markers, lods)


# --------------------------------------------------------------------------- strips
def encode_strip(strip: Sequence[int]) -> bytes:
    """A strip's push buffer (module docstring's form)."""
    out = bytearray(struct.pack("<II", _BEGIN, _STRIP))
    pairs = len(strip) // 2
    for c in range(0, pairs, _CHUNK):
        n = min(_CHUNK, pairs - c)
        out += struct.pack("<I", _PAIRS | (n << 18))
        out += struct.pack(f"<{n}I", *(strip[2 * (c + j)] | (strip[2 * (c + j) + 1] << 16) for j in range(n)))
    if len(strip) % 2:
        out += struct.pack("<II", _ONE, strip[-1])
    out += struct.pack("<III", _BEGIN, _END_VALUE, 0)
    return bytes(out)


def _canonical(t: tuple[int, int, int]) -> tuple[int, int, int]:
    i = t.index(min(t))
    return t[i:] + t[:i]


def stripify(triangles: Sequence[tuple[int, int, int]]) -> list[int]:
    """One strip (degenerate triangles join its runs) that draws exactly
    ``triangles`` with their windings.  Greedy runs: each starts at the
    unused triangle with the fewest unused neighbours, grows forward
    along the edge its parity asks for (to the neighbour with the fewest
    unused neighbours of its own; a swap, one repeated index, turns it
    onto its last triangle's other edge) and backward from its first edge by an
    even count (so the forward part's parity holds), the best of its
    three rotations kept.  Deterministic, so the last few are kept by
    their triangles (Step 2.176: a write strips each group it splits to
    fit, then checks and encodes the same groups)."""
    return list(_stripped(tuple(tuple(t) for t in triangles)))


@functools.lru_cache(maxsize=256)
def _stripped(tris: tuple[tuple[int, int, int], ...]) -> tuple[int, ...]:
    for t in tris:
        if len(set(t)) != 3:
            raise ValueError(f"triangle {t} repeats a vertex")
    by_edge: dict[tuple[int, int], list[int]] = {}
    for k, (a, b, c) in enumerate(tris):
        for e in ((a, b), (b, c), (c, a)):
            by_edge.setdefault(e, []).append(k)
    used = [False] * len(tris)

    def third(k: int, p: int, q: int) -> int:
        a, b, c = tris[k]
        if p == a and q == b:
            return c
        if p == b and q == c:
            return a
        if p == c and q == a:
            return b
        raise KeyError((p, q))

    def neighbours(k: int, mark=()) -> int:
        a, b, c = tris[k]
        n = 0
        for e in ((b, a), (c, b), (a, c)):
            for j in by_edge.get(e, ()):
                if not used[j] and j not in mark:
                    n += 1
        return n

    def grow(seq: list[int], mark: set[int]) -> tuple[list[int], list[int]]:
        """``seq`` grown while a triangle off its last edge (its parity's)
        is free: the vertices and the triangles taken, in order."""
        seq, taken = list(seq), []
        while True:
            i = len(seq)
            p, q = (seq[-2], seq[-1]) if i % 2 == 0 else (seq[-1], seq[-2])
            free = [j for j in by_edge.get((p, q), ()) if not used[j] and j not in mark]
            if not free and taken:      # a swap: u p q -> u p u q (one index) turns the run onto edge u-q
                u, last = seq[-3], seq[-1]
                p, q = (u, last) if (i + 1) % 2 == 0 else (last, u)
                free = [j for j in by_edge.get((p, q), ()) if not used[j] and j not in mark]
                if free:
                    seq.insert(len(seq) - 1, u)
            if not free:
                return seq, taken
            best = min(free, key=lambda j: (neighbours(j, mark), j))
            seq.append(third(best, p, q))
            taken.append(best)
            mark.add(best)

    heap = [(neighbours(k), k) for k in range(len(tris))]
    heapq.heapify(heap)
    out: list[int] = []
    while heap:
        deg, k = heapq.heappop(heap)
        if used[k]:
            continue
        now = neighbours(k)
        if now != deg:
            heapq.heappush(heap, (now, k))
            continue
        a, b, c = tris[k]
        best = None
        for r in ((a, b, c), (b, c, a), (c, a, b)):
            mark = {k}
            fwd, ftaken = grow(list(r), mark)
            back, btaken = grow([r[1], r[0]], mark)
            back, btaken = back[2:], btaken
            if len(back) % 2:
                back, btaken = back[:-1], btaken[:-1]
            run = (back[::-1] + fwd, [k] + ftaken + btaken)
            if best is None or len(run[1]) > len(best[1]):
                best = run
        strip, taken = best
        for j in taken:
            used[j] = True
        if out:
            out += [out[-1], strip[0]]
            if len(out) % 2:
                out.append(strip[0])
        out += strip
    got = sorted(_canonical(t) for t in strip_triangles(out))
    if got != sorted(_canonical(t) for t in tris):
        raise ValueError("the strip doesn't draw its triangles (a stripper fault)")
    return tuple(out)


# --------------------------------------------------------------------------- regrouping
def _push_size(group: Group) -> int:
    if group.stored is not None and tuple(group.triangles) == group.stored[0]:
        return len(group.stored[1])
    return len(encode_strip(stripify(group.triangles)))


def _least_push(triangles: int) -> int:
    """The fewest bytes :func:`encode_strip` writes for any strip that
    draws ``triangles`` triangles: one of at least ``triangles + 2``
    indices, of that many or one more (an odd count's lone index costs
    more than a pair)."""
    def size(n: int) -> int:
        pairs = n // 2
        return 20 + 4 * pairs + 4 * -(-pairs // _CHUNK) + 8 * (n % 2)
    return min(size(triangles + 2), size(triangles + 3))


def _fits(group: Group) -> bool:
    """Whether ``group`` is one group as it stands; past :func:`_least_push`
    no strip of it fits, so it isn't stripped (Step 2.176: a split's
    halves too big to fit were each stripped once, the bulk of a big
    group's regroup)."""
    return (len(group.palette) <= PALETTE_MAX and len(group.vertices) <= INDEX_MAX + 1
            and _least_push(len(group.triangles)) <= PUSH_MAX and _push_size(group) <= PUSH_MAX)


def _bone_skin(group: Group) -> list[dict[int, float]]:
    out = []
    for v in group.vertices:
        skin: dict[int, float] = {}
        for w, b in zip(v.weights, v.slots):
            if w > 0:
                e = code_entry(b)
                if e is None or e >= len(group.palette):
                    raise ValueError(f"a weight's slot byte {b} is outside the {len(group.palette)}-entry palette")
                skin[group.palette[e]] = skin.get(group.palette[e], 0.0) + w
        out.append(skin)
    return out


def _subgroup(group: Group, skins: list[dict[int, float]], tris: list[tuple[int, int, int]], keep_order: list[int]
              ) -> Group:
    """``tris`` of ``group`` as a group of their own: their vertices in
    the group's order, the palette the old one's bones they use in its
    order, then the rest by index."""
    used = sorted({v for t in tris for v in t})
    local = {v: n for n, v in enumerate(used)}
    bones = {b for v in used for b, w in skins[v].items() if w > 0}
    palette = [b for b in keep_order if b in bones] + sorted(bones - set(keep_order))
    entry: dict[int, int] = {}
    for n, b in enumerate(palette):
        entry.setdefault(b, n)
    codes: dict[int, int] = {}      # each weighted slot byte's code in the new palette, worked out once (Step 2.179)
    verts = []
    for v in used:
        old = group.vertices[v]
        slots = []
        for w, b in zip(old.weights, old.slots):
            if w > 0:
                code = codes.get(b)
                if code is None:
                    code = codes[b] = slot_code(entry[group.palette[code_entry(b)]])
                slots.append(code)
            else:
                slots.append(0)
        verts.append(Vertex(old.position, old.weights, old.normal, old.uv, old.extra, tuple(slots)))
    return Group(palette, verts, [tuple(local[v] for v in t) for t in tris], group.material, group.fvf, group.vb,
                 group.pb)


def regroup(group: Group) -> list[Group]:
    """``group`` as one group if it fits (module docstring), else split:
    clusters of its triangles, each grown from the first left (in order)
    by the triangles whose bones it holds already, then the one adding
    the fewest new bones, to :data:`PALETTE_MAX` bones; a cluster whose
    strip passes :data:`PUSH_MAX` or :data:`INDEX_MAX` is halved across
    its widest extent at its triangles' median (each half one patch, so
    its strip stays tight and few vertices are copied).  A vertex two
    clusters share is copied into each; each keeps its triangles' order."""
    if _fits(group) and all(b < 0x100 for v in group.vertices for b in v.slots):
        return [group]
    skins = _bone_skin(group)
    tri_bones = [frozenset(b for v in t for b in skins[v]) for t in group.triangles]
    for k, bones in enumerate(tri_bones):
        if len(bones) > PALETTE_MAX:
            raise ValueError(f"triangle {k} is skinned to {len(bones)} bones, past the {PALETTE_MAX} a group holds")
    left: dict[frozenset, list[int]] = {}   # the triangles left, by their bones (Step 2.179: one set's go together)
    for k, bones in enumerate(tri_bones):
        left.setdefault(bones, []).append(k)
    clusters = []
    while left:
        bones = set(min(left, key=lambda b: left[b][0]))
        mine = []
        while True:
            for b in [b for b in left if b <= bones]:
                mine += left.pop(b)
            best = min(left, key=lambda b: (len(b - bones), left[b][0]), default=None)
            if best is None or len(bones | best) > PALETTE_MAX:
                break
            bones |= best
        clusters.append(sorted(mine))
    centres = [tuple(sum(group.vertices[v].position[c] for v in t) / 3.0 for c in range(3)) for t in group.triangles]
    parts: list[Group] = []
    todo = [c for c in clusters]
    while todo:
        c = todo.pop(0)
        sub = _subgroup(group, skins, [group.triangles[k] for k in c], group.palette)
        if _fits(sub):
            parts.append(sub)
        elif len(c) > 1:      # halved across its widest extent at the median, so each half stays one patch
            axis = max(range(3), key=lambda a: (max(centres[k][a] for k in c) - min(centres[k][a] for k in c), -a))
            order = sorted(c, key=lambda k: (centres[k][axis], k))
            half = set(order[:len(order) // 2])
            todo[:0] = [[k for k in c if k in half], [k for k in c if k not in half]]
        else:
            raise ValueError("a single triangle doesn't fit a group")
    return parts


def regroup_lod(lod: Lod) -> list[int]:
    """Every group of ``lod`` through :func:`regroup`, in place: a split
    group's first part keeps its index, the others go at the end.
    Returns, for each final group, the index of the group it came from."""
    groups, origin, extra, extra_origin = [], [], [], []
    for k, g in enumerate(lod.groups):
        parts = regroup(g)
        groups.append(parts[0])
        origin.append(k)
        extra += parts[1:]
        extra_origin += [k] * (len(parts) - 1)
    lod.groups = groups + extra
    return origin + extra_origin


# --------------------------------------------------------------------------- encoding
def _align(n: int, a: int) -> int:
    return -(-n // a) * a


def encode_bmsh(lod: Lod) -> tuple[bytes, list[int]]:
    """``lod``'s ``bmsh`` payload and the offsets of its relocated
    fields (each group's ``gshd`` index)."""
    ng = len(lod.groups)
    out = bytearray(struct.pack("<Ii", ng, 4))
    out += bytes(GROUP_RECORD * ng)
    for g, grp in enumerate(lod.groups):
        ga = 8 + GROUP_RECORD * g
        pal_at = len(out)
        out += struct.pack(f"<{len(grp.palette)}i", *grp.palette)
        out += bytes(_align(len(out), 16) - len(out))
        va = len(out)
        out += b"".join(v.pack() for v in grp.vertices)
        struct.pack_into("<IiiIIIiiII", out, ga, grp.fvf, len(grp.palette), pal_at - (ga + 8), *grp.vb,
                         len(grp.vertices), va - (ga + 28), *grp.material)
    return bytes(out), [8 + GROUP_RECORD * g + 32 for g in range(ng)]


def _push(grp: Group) -> tuple[bytes, int]:
    """A group's push buffer and its record's +4: the stored ones while
    its triangles are the stored strip's, else a new strip's."""
    if grp.stored is not None and tuple(grp.triangles) == grp.stored[0]:
        return grp.stored[1], grp.stored[2]
    strip = stripify(grp.triangles)
    return encode_strip(strip), len(strip) - 2


def encode_body(asset: BodyAsset) -> tuple[bytes, list[int]]:
    """``asset``'s ``body`` payload and the offsets of its relocated
    fields (the LOD list), laid out as vanilla's (module docstring)."""
    nb, nm, nl = len(asset.bones), len(asset.markers), len(asset.lods)
    bones_at = 0x20
    markers_at = bones_at + BONE_RECORD * nb
    pairs_at = markers_at + MARKER_RECORD * nm
    names_at = pairs_at + 8 * nl
    out = bytearray(names_at)
    out[:0x20] = asset.header
    struct.pack_into("<iiiiiiii", out, 0, nb, bones_at - 4, nl, 0, nl, pairs_at - 20, nm,
                     (markers_at if nm else pairs_at) - 0x1C)
    for k, b in enumerate(asset.bones):
        name = b.name.encode("ascii")
        rec = bytearray(b.record)
        at = bones_at + BONE_RECORD * k
        struct.pack_into("<Ii", rec, 0, len(name), len(out) - (at + 4))
        out[at:at + BONE_RECORD] = rec
        out += name + b"\0"
    for k, m in enumerate(asset.markers):
        name = m.name.encode("ascii")
        rec = bytearray(m.record)
        at = markers_at + MARKER_RECORD * k
        struct.pack_into("<Ii", rec, 0, len(name), len(out) - (at + 4))
        out[at:at + MARKER_RECORD] = rec
        out += name + b"\0"
    out += bytes(_align(len(out), 4) - len(out))
    lods_at = len(out)
    struct.pack_into("<i", out, 12, lods_at - 12)
    out += struct.pack(f"<{nl}I", *(lod.bmsh for lod in asset.lods))
    for n, lod in enumerate(asset.lods):
        records = len(out)
        struct.pack_into("<Ii", out, pairs_at + 8 * n, len(lod.groups), records - (pairs_at + 8 * n + 4))
        out += bytes(LOD_RECORD * len(lod.groups))
        for g, grp in enumerate(lod.groups):
            push, tri_count = _push(grp)
            rec = records + LOD_RECORD * g
            struct.pack_into("<iI5I", out, rec, len(out) - rec, tri_count, *grp.pb, len(push), len(push))
            out += push
    return bytes(out), [lods_at + 4 * n for n in range(nl)]


# --------------------------------------------------------------------------- checks and the write
def problems(asset: BodyAsset, characters_xbr: bytes | None = None, *, fixable: bool = True) -> list[str]:
    """What the format or the game can't hold in ``asset`` (each named:
    the body, LOD, group, vertex or bone), ``[]`` when nothing; with
    ``characters_xbr`` its materials and LOD ``bmsh`` entries too; with
    ``fixable`` false, not what :func:`regroup` fixes (a palette, vertex
    count or push buffer past its limit, a slot code past a byte)."""
    out, nb = [], len(asset.bones)
    where = asset.name
    names = asset.bone_names
    for k, b in enumerate(asset.bones):
        if not b.name or not b.name.isascii() or "\0" in b.name:
            out.append(f"{where}: bone {k}'s name {b.name!r} isn't ASCII without a NUL")
        if not -1 <= b.parent < k:
            out.append(f"{where}: bone {b.name!r}'s parent {b.parent} isn't an earlier bone (the pose runs parents first)")
        if len(b.record) != BONE_RECORD:
            out.append(f"{where}: bone {b.name!r}'s record isn't {BONE_RECORD} bytes")
    if len(set(names)) != len(names):
        out.append(f"{where}: two bones share the name {next(n for n in names if names.count(n) > 1)!r}")
    if not asset.lods:
        out.append(f"{where}: no LOD")
    toc = parse_toc(characters_xbr) if characters_xbr is not None else None
    for n, lod in enumerate(asset.lods):
        if toc is not None and lod.bmsh is not None and \
                not (0 <= lod.bmsh < len(toc) and toc[lod.bmsh].tag == "bmsh"):
            out.append(f"{where} LOD {n}: TOC entry {lod.bmsh} isn't a bmsh")
        for g, grp in enumerate(lod.groups):
            at = f"{where} LOD {n} group {g}"
            if grp.fvf != FVF:
                out.append(f"{at}: FVF 0x{grp.fvf:X} isn't 0x{FVF:X}")
            if len(grp.palette) > PALETTE_MAX and fixable:
                out.append(f"{at}: {len(grp.palette)} palette bones, past the {PALETTE_MAX} slot bytes name")
            if any(not 0 <= b < nb for b in grp.palette):
                out.append(f"{at}: its palette names a bone the body hasn't")
            if len(grp.vertices) > INDEX_MAX + 1 and fixable:
                out.append(f"{at}: {len(grp.vertices)} vertices, past the {INDEX_MAX + 1} 16-bit indices reach")
            if toc is not None:
                gshd, row = grp.material
                if not (0 <= gshd < len(toc) and toc[gshd].tag == "gshd") or \
                        row >= struct.unpack_from("<I", characters_xbr, toc[gshd].file_offset)[0]:
                    out.append(f"{at}: material ({gshd}, {row}) is no gshd row of the file")
            for j, v in enumerate(grp.vertices):
                floats = (*v.position, *v.weights, *v.normal, *v.uv, *v.extra)
                if not all(x == x and abs(x) != float("inf") for x in floats):
                    out.append(f"{at} vertex {j}: a float isn't finite")
                    break
                if any(w < 0 for w in v.weights):
                    out.append(f"{at} vertex {j}: a negative weight")
                    break
                live = [(w, b) for w, b in zip(v.weights, v.slots) if w > 0]
                if any((b > 0xFF and fixable) or code_entry(b) is None or code_entry(b) >= len(grp.palette)
                       for _, b in live):
                    out.append(f"{at} vertex {j}: a weight's slot byte is outside the {len(grp.palette)}-entry palette")
                    break
                if live and abs(sum(w for w, _ in live) - 1.0) > 1e-5:
                    out.append(f"{at} vertex {j}: its weights sum to {sum(w for w, _ in live):.6f}, not 1")
                    break
            bad = [t for t in grp.triangles if len(set(t)) != 3 or any(not 0 <= v < len(grp.vertices) for v in t)]
            if bad:
                out.append(f"{at}: {len(bad)} triangles repeat a vertex or name one past its {len(grp.vertices)}")
            elif len(grp.palette) <= PALETTE_MAX and fixable:
                size = _push_size(grp)
                if size > PUSH_MAX:
                    out.append(f"{at}: a {size} B push buffer, past the {PUSH_MAX} B vanilla's largest holds")
    return out


def _users(characters_xbr: bytes, bmsh: int) -> list[str]:
    """The bodies whose LOD lists name ``bmsh``."""
    toc, names = parse_toc(characters_xbr), named_resources(characters_xbr)
    out = []
    for e in toc:
        if e.tag != "body":
            continue
        at = e.file_offset
        lods = _rel(characters_xbr, at + 12)
        if bmsh in struct.unpack_from(f"<{_i32(characters_xbr, at + 8)}I", characters_xbr, lods):
            out.append(names.get(e.index, f"body {e.index}"))
    return out


def subset(asset: BodyAsset, groups: Mapping[int, Sequence[int]], markers: Iterable[str] = ()) -> BodyAsset:
    """``asset`` cut to ``groups`` ({LOD: its group indices}, in LOD
    order; every other LOD and group dropped), the bones their palettes
    name and those bones' ancestors (so each kept bone keeps its parent
    and its rest, which its parent's frame holds), renumbered in order
    with each palette and parent following, and the markers named in
    ``markers`` (Step 2.159b's G-a: the townswomen's thrown vase, one
    group on one bone; a cut LOD1).  :func:`write_asset` writes it over
    the body; a dropped LOD's ``bmsh`` stays in the file, unnamed by it.
    :class:`ValueError` for a LOD, group or marker the body hasn't, or
    no group kept."""
    where = asset.name
    if not any(groups.values()):
        raise ValueError(f"{where}: a subset keeps no group")
    lods = []
    for n in sorted(groups):
        if not 0 <= n < len(asset.lods):
            raise ValueError(f"{where}: no LOD {n} (it has {len(asset.lods)})")
        have = asset.lods[n].groups
        bad = [g for g in groups[n] if not 0 <= g < len(have)]
        if bad:
            raise ValueError(f"{where} LOD {n}: no group {bad[0]} (it has {len(have)})")
        lods.append((asset.lods[n].bmsh, [have[g] for g in groups[n]]))
    named = {m.name for m in asset.markers}
    missing = [m for m in markers if m not in named]
    if missing:
        raise ValueError(f"{where}: no marker {missing[0]!r}")
    keep: set[int] = set()
    for _, grps in lods:
        for grp in grps:
            for b in grp.palette:
                while b >= 0 and b not in keep:
                    keep.add(b)
                    b = asset.bones[b].parent
    new = {old: k for k, old in enumerate(sorted(keep))}
    bones = []
    for old in sorted(keep):
        rec = bytearray(asset.bones[old].record)
        struct.pack_into("<h", rec, 8, new.get(asset.bones[old].parent, -1))
        bones.append(Bone(asset.bones[old].name, bytes(rec)))
    out_lods = [Lod(bmsh, [replace(g, palette=[new[b] for b in g.palette], vertices=list(g.vertices),
                                   triangles=list(g.triangles)) for g in grps]) for bmsh, grps in lods]
    wanted = set(markers)
    return BodyAsset(asset.name, asset.index, asset.header, bones,
                     [Marker(m.name, m.record) for m in asset.markers if m.name in wanted], out_lods)


def write_asset(characters_xbr: bytes, asset: BodyAsset, *, regroup_groups: bool = True) -> bytes:
    """``characters_xbr`` with ``asset`` written over its body and LOD
    meshes (module docstring): each LOD regrouped first (unless
    ``regroup_groups`` is false), each new LOD (``bmsh`` ``None``) appended
    as a ``bmsh`` of its own, every payload grown in place by whole pages,
    the relocated fields rewritten, then the file read back and compared
    with the asset; a new LOD's ``bmsh`` is then its new TOC index.
    :class:`ValueError` names the first thing that blocks it; nothing is
    returned then (D35)."""
    issues = problems(asset, characters_xbr, fixable=not regroup_groups)
    if not issues and regroup_groups:
        for lod in asset.lods:
            regroup_lod(lod)
        issues = problems(asset, characters_xbr)
    if issues:
        raise ValueError(f"model write: {issues[0]}" + (f" (and {len(issues) - 1} more)" if len(issues) > 1 else ""))
    index, name = _body_entry(characters_xbr, asset.name)
    if index != asset.index:
        raise ValueError(f"model write: {asset.name} is TOC entry {index} here, not {asset.index}")
    count = len(parse_toc(characters_xbr))
    added = [n for n, lod in enumerate(asset.lods) if lod.bmsh is None]
    staged = replace(asset, lods=[replace(lod, bmsh=count + added.index(n)) if lod.bmsh is None else lod
                                  for n, lod in enumerate(asset.lods)])
    rewrite, relocated, new = {}, {}, []
    payload, lods = encode_body(staged)
    rewrite[index], relocated[index] = payload, lods
    for lod in asset.lods:
        if lod.bmsh is None:
            mesh, relocs = encode_bmsh(lod)
            new.append(NewResource(None, "bmsh", mesh, tuple(relocs)))
            continue
        others = [u for u in _users(characters_xbr, lod.bmsh) if u.casefold() != f"characters/{name}".casefold()]
        if others:
            raise ValueError(f"model write: {name}'s bmsh {lod.bmsh} is also {others[0]}'s mesh")
        if lod.bmsh in rewrite:
            raise ValueError(f"model write: two LODs of {name} name bmsh {lod.bmsh}")
        rewrite[lod.bmsh], relocated[lod.bmsh] = encode_bmsh(lod)
    out = rewrite_payloads(append_resources(characters_xbr, new), rewrite, relocated=relocated)
    back = read_asset(out, asset.name)
    if [lod.bmsh for lod in back.lods] != [lod.bmsh for lod in staged.lods]:
        raise ValueError(f"model write: {name}'s LOD list doesn't read back as written")
    for n, (a, b) in enumerate(zip(asset.lods, back.lods)):
        for g, (ga, gb) in enumerate(zip(a.groups, b.groups)):
            if ga.vertices != gb.vertices or ga.palette != gb.palette or ga.material != gb.material or \
                    sorted(map(_canonical, ga.triangles)) != sorted(map(_canonical, gb.triangles)):
                raise ValueError(f"model write: {name} LOD {n} group {g} doesn't read back as written")
    if [len(lod.groups) for lod in back.lods] != [len(lod.groups) for lod in asset.lods] or \
            [(b.name, b.record[8:]) for b in back.bones] != [(b.name, b.record[8:]) for b in asset.bones] or \
            [(m.name, m.record[8:]) for m in back.markers] != [(m.name, m.record[8:]) for m in asset.markers]:
        raise ValueError(f"model write: {name}'s bones, markers or groups don't read back as written")
    for lod, done in zip(asset.lods, staged.lods):
        lod.bmsh = done.bmsh
    return out


__all__ = ["BONE_RECORD", "BodyAsset", "Bone", "FVF", "Group", "INDEX_MAX", "Lod", "Marker", "PALETTE_MAX",
           "PUSH_MAX", "VERTEX_SIZE", "Vertex", "encode_body", "encode_bmsh", "encode_strip",
           "code_entry", "make_vertex", "problems", "read_asset", "regroup", "regroup_lod", "slot_byte", "slot_code",
           "slot_entry",
           "strip_indices", "strip_triangles", "stripify", "subset", "write_asset"]
