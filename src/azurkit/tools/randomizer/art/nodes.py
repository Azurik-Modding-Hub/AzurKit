"""Level node graphs: the ``node`` section's records, links, save list and
transforms, the ``ndbg`` names that go with them, the ``levl`` cell
names, and the node types ``default.xbe`` registers
(``docs/XBR_FORMAT.md`` § "Level node graph").

These are the generic readers: the randomizer's level semantics
(:mod:`azurkit.tools.randomizer.levels`) and the player-model swap's
``fx.xbr`` staff reader (:func:`azurik_mod.patches._player_character.staff_scales`)
both read records through :func:`record_offsets`, :func:`list_at` and
:func:`lstr`, and the TOC through
:func:`~azurik_mod.xbr.toc_scan.parse_toc`, the one TOC reader (AZ-124).
Ported on 2026-10-12 (Step R1.1) from the randomizer evidence's
``r0/tools/nodegraph.py``.  What each rule rests on:

* ``node`` / ``ndbg`` pairing: the u32 at node payload +0x1C is the TOC
  index of the graph's ``ndbg`` (263 of 263 on the disc, HM-07).
* Attribute names per node type, read from ``default.xbe``: each type is
  registered by a static initialiser in 0xFD000-0xFF000,
  ``push <chunk>; mov edx,<attr count>; mov ecx,<type name>;
  mov eax,<parent descriptor>; mov esi,<descriptor>; call 0xCE0B0``.  A
  chunk is a run of 16-byte records ``{u32 index, char *name, u32 kind,
  f32 default}`` ending at a NULL name; a type's attributes are its
  ancestors' chunks plus its own (critterGenerator: node, dag, locator,
  critterGenerator).  Builds read them from the names table
  ``node_types.json`` beside this module (:class:`Schema`; Step X.102):
  each type's base type and attribute names, which both releases
  register alike; capstone reads the registrations only to make or
  check the table (``python -m devkit re node-types``).
* Links (the link loader 0x658F0): record +0x10 is (count, ref) of
  24-byte links ``{f32 weight +0x00, u32 curve +0x04, f32 factor +0x08,
  u16 source plug +0x0C, u16 target plug +0x10, u32 target record
  +0x14}``; the loader reads each plug as 16 bits (0x65950, 0x65956), so
  the halves at +0x0E and +0x12 are skipped (0 on every vanilla link).
  The plugs index the source and target types' attribute lists.
* The save list (the node-graph initialiser 0x65E50): node header +0x0C
  is the count and +0x10 a ref to u32 record indexes, the nodes a level
  ``.sav`` restores (``docs/SAVE_FORMAT.md``).
* Transforms (HM-08): from the loader 0x67F80, the local-matrix builder
  0x68BE0 and the Euler routine 0xBC630, the column-vector local matrix
  is ``T(t + rpt + rp) . R(order) . T(spt + sp - rp) . S(s) . T(-sp)``
  with t/r/s the attribute words 1-3/4-6/7-9, sp = +0x2C, spt = +0x38,
  rp = +0x44, rpt = +0x50, the order at +0x6C and the inherit mode at
  +0x28.  The Euler axis (0x1979D0) and parity (0x197A18) tables are read
  from the XBE.  Inherit modes 0 and 6 compose normally, mode 1 replaces
  the parent by the translation that carries the anchor ``t + rp`` along
  (0x681E0's jump table at 0x68BBC), and mode 2 (0x68359, Step X.16,
  HM-87) by the parent's rotation less its tilt, with that anchor kept
  where the parent puts it (:func:`upright`): an upright carrier, which
  stays level while its parent turns it round.  Mode 3 (0x6880A, Step
  2.157) keeps the anchor where the parent puts it and takes its axes
  from the top camera's rotation, which no offline reader knows; modes
  4, 5 and 8 are not decoded, and mode 7 (case 0x68A43) places the node
  at the critter at world +0xC0, the player (Balthazar's ``onPlayer``,
  Step 2.75e); so a world matrix under any of these is composed like
  mode 0 and marked approximate.

These are USA VAs; the node-types scan and :class:`Euler` read them at
the XBE's own release's addresses (its address map, Step RG.4c), so the
Europe ``default.xbe`` gives the same 44 types and tables.

Positions computed here stay in memory: nothing in the repository stores
a coordinate or a game byte (RANDOMIZER_PLAN §4.4, D87).
"""

from __future__ import annotations

import collections
import functools
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path

from azurkit.tools.randomizer.ports import xbe_layout
from azurkit.tools.randomizer.ports import resolve_va_to_file
from azurkit.core.xbr.nodes import TocEntry, parse_toc

REGISTER_FN = 0xCE0B0
"""The node-type registration call every type's static initialiser makes."""
INIT_RANGE = (0xFD000, 0xFF000)
"""The VAs of the static initialisers that call :data:`REGISTER_FN` (in
either release)."""
EULER_AXES_VA = 0x1979D0
"""Six ``{u32 i, j, k}`` axis triples, one per rotation order."""
EULER_PARITY_VA = 0x197A18
"""Six i8 parities (+1 / -1), one per rotation order."""
NODE_TYPES = 44
"""How many node types ``default.xbe`` registers (either release)."""
NODE_TYPES_FILE = Path(__file__).with_name("node_types.json")
"""The node-type names table (:func:`node_types`), made by
``python -m devkit re node-types`` from both releases' registrations."""

IDENTITY = ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0))
DECODED_MODES = (0, 1, 2, 6)
"""The inherit modes :meth:`Graph.world` composes as the game does."""


def lstr(buf, at: int, limit: int | None = 300) -> str | None:
    """The (u32 length, i32 self-relative ref) string at ``at`` in ``buf``,
    as ASCII (an undecodable byte reads as U+FFFD), or ``None`` when its
    length is 0 (or ``limit`` or more) or it lies outside ``buf``."""
    n, ref = struct.unpack_from("<Ii", buf, at)
    st = at + 4 + ref
    if not 0 < n or (limit is not None and n >= limit) or st <= 0 or st + n > len(buf):
        return None
    return bytes(buf[st:st + n]).decode("ascii", "replace")


def list_at(buf, at: int) -> tuple[int, int]:
    """(start, count) of the (u32 count, i32 self-relative ref) list at
    ``at`` in ``buf``: the layout of a record's attribute block (+0x08),
    its links (+0x10), a graph's record table (+0) and its save list
    (+0x0C)."""
    n, ref = struct.unpack_from("<Ii", buf, at)
    return at + 4 + ref, n


def record_offsets(buf, base: int = 0) -> list[int | None]:
    """The offset in ``buf`` of each record of the ``node`` payload at
    ``base`` (``None`` for an empty slot): a u32 count at +0, then at +4
    a self-relative ref to ``count`` self-relative pointers."""
    table, n = list_at(buf, base)
    out: list[int | None] = []
    for k in range(n):
        (ptr,) = struct.unpack_from("<i", buf, table + 4 * k)
        out.append(table + 4 * k + ptr if ptr else None)
    return out


def bind_name(buf, rec: int) -> str | None:
    """A ``transform`` record's bind name (the marker it follows, such as
    ``m_stafftop``): the (length, ref) string at +0x20 when the u32 at
    +0x1C isn't 0, else ``None``."""
    if not struct.unpack_from("<I", buf, rec + 0x1C)[0]:
        return None
    return lstr(buf, rec + 0x20)


def xbe_cstr(xbe: bytes, va: int) -> str | None:
    """The printable NUL-terminated ASCII string at ``va`` in ``default.xbe``."""
    o = resolve_va_to_file(xbe, va)
    if o is None:
        return None
    e = xbe.index(b"\0", o)
    try:
        s = bytes(xbe[o:e]).decode("ascii")
    except UnicodeDecodeError:
        return None
    return s if s and s.isprintable() else None


# --------------------------------------------------------------------------- the XBE side
@dataclass
class TypeInfo:
    """One registered node type."""
    name: str
    attrs: list    # index -> name, its ancestors' chunks included
    chain: list    # the type names from `node` down to this one


@functools.cache
def node_types() -> dict:
    """:data:`NODE_TYPES_FILE`: ``{"releases": the releases whose
    ``default.xbe`` registers these types, "types": name -> {"parent",
    "attrs"} as the node-types scan reads them}``.  Names only, no game
    bytes; ``tests/test_re_xbe.py`` checks it against capstone on each
    release."""
    return json.loads(NODE_TYPES_FILE.read_text(encoding="utf-8"))


class Euler:
    """The Euler tables the transform composition uses, read from
    ``default.xbe`` at its release's addresses, and the rotation they
    give: no capstone, so a build can compose a transform as the game
    does (X16's armor table, Step 2.118)."""

    def __init__(self, xbe: bytes):
        va = xbe_layout(xbe).va  # USA VA -> the XBE's release's
        axes_va, parity_va = va(EULER_AXES_VA), va(EULER_PARITY_VA)
        o = resolve_va_to_file(xbe, axes_va)
        self.euler_axes = [struct.unpack_from("<3I", xbe, o + 12 * k) for k in range(6)]
        o = resolve_va_to_file(xbe, parity_va)
        self.euler_parity = list(struct.unpack_from("<6b", xbe, o))
        if any(sorted(a) != [0, 1, 2] for a in self.euler_axes) or \
                any(p not in (1, -1) for p in self.euler_parity):
            raise ValueError(f"the Euler tables at {axes_va:#x} and {parity_va:#x} hold no "
                             f"6 axis orders with parities of +/-1: is this a vanilla default.xbe?")

    def rotation(self, rx: float, ry: float, rz: float, order: int):
        """0xBC630 (Shoemake's Eul_ToHMatrix, static frame), as a column-vector
        matrix: the rotation about axis i by angle[i] comes first, then j, then k."""
        a = (rx, ry, rz)
        if not 0 <= order < 6:
            raise ValueError(f"rotation order {order} is outside the engine's 0-5 table")
        i, j, k = self.euler_axes[order]
        p = self.euler_parity[order]
        ci, cj, ck = math.cos(a[i]), math.cos(a[j]), math.cos(a[k])
        si, sj, sk = p * math.sin(a[i]), p * math.sin(a[j]), p * math.sin(a[k])
        m = [[0.0] * 4 for _ in range(4)]
        m[i][i] = cj * ck
        m[j][i] = cj * sk
        m[k][i] = -sj
        m[i][j] = si * sj * ck - ci * sk
        m[j][j] = si * sj * sk + ci * ck
        m[k][j] = si * cj
        m[i][k] = ci * sj * ck + si * sk
        m[j][k] = ci * sj * sk - si * ck
        m[k][k] = ci * cj
        m[3][3] = 1.0
        return tuple(tuple(r) for r in m)


class Schema(Euler):
    """The node types ``default.xbe`` registers, with their attribute names,
    from the names table (:func:`node_types`: no capstone, so a build
    needs none; Step X.102), and the Euler tables the transform
    composition uses, read from ``xbe`` (:class:`Euler`)."""

    def __init__(self, xbe: bytes):
        super().__init__(xbe)
        table = node_types()["types"]
        self.types: dict[str, TypeInfo] = {}
        for name, t in table.items():
            chain, d = [], name
            while d is not None:
                chain.append(d)
                d = table[d]["parent"]
            self.types[name] = TypeInfo(name, list(t["attrs"]), chain[::-1])

    def attr(self, typ: str, idx: int) -> str:
        """Attribute ``idx``'s name for type ``typ`` (``?<idx>`` when unknown)."""
        t = self.types.get(typ)
        if t is None or idx >= len(t.attrs):
            return f"?{idx}"
        return t.attrs[idx]

    def is_a(self, typ: str, base: str) -> bool:
        t = self.types.get(typ)
        return bool(t) and base in t.chain


# --------------------------------------------------------------------------- matrices (column vectors, 4x4 tuples)
def mat_mul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)) for i in range(4))


def translate(x, y, z):
    return ((1.0, 0.0, 0.0, x), (0.0, 1.0, 0.0, y), (0.0, 0.0, 1.0, z), (0.0, 0.0, 0.0, 1.0))


def scale(x, y, z):
    return ((x, 0.0, 0.0, 0.0), (0.0, y, 0.0, 0.0), (0.0, 0.0, z, 0.0), (0.0, 0.0, 0.0, 1.0))


def apply(m, p):
    """The point ``p`` (x, y, z) moved by the matrix ``m``."""
    return tuple(sum(m[i][k] * (p[k] if k < 3 else 1.0) for k in range(4)) for i in range(3))


def _quat(m) -> tuple[float, float, float, float]:
    """0xA0520: the quaternion (x, y, z, w) of ``m``'s 3x3 (Shoemake's,
    on the matrix as it is: a scaled parent gives a scaled quaternion)."""
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0.0:
        s = math.sqrt(tr + 1.0)
        k = 0.5 / s
        return ((m[2][1] - m[1][2]) * k, (m[0][2] - m[2][0]) * k, (m[1][0] - m[0][1]) * k, s * 0.5)
    i = 1 if m[1][1] > m[0][0] else 0
    if m[2][2] > m[i][i]:
        i = 2
    j, k = (i + 1) % 3, (i + 2) % 3
    s = math.sqrt(m[i][i] - m[j][j] - m[k][k] + 1.0)
    q = [0.0, 0.0, 0.0, 0.0]
    q[i], r = s * 0.5, 0.5 / s
    q[j] = (m[j][i] + m[i][j]) * r
    q[k] = (m[k][i] + m[i][k]) * r
    q[3] = (m[k][j] - m[j][k]) * r
    return tuple(q)


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v) if n else tuple(v)


def upright(pm, anchor):
    """Inherit mode 2 (0x68359): the parent matrix ``pm`` with its tilt
    removed.  Its quaternion q (:func:`_quat`) is composed with r, the
    shortest arc from world up to world up seen in q's frame, so the
    result turns about world Z only; its translation keeps ``anchor``
    (``t + rp``) where ``pm`` puts it.  Checked against the game's 0x681E0
    under Unicorn (:func:`azurik_mod.sim.l2.transform_world`)."""
    qx, qy, qz, qw = _quat(pm)
    v = _unit((2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)))
    hx, hy, hz = _unit((v[0], v[1], v[2] + 1.0))
    rx, ry, rz, rw = -hy, hx, 0.0, hz
    x = qw * rx + qx * rw + qy * rz - qz * ry       # q * r (Hamilton)
    y = qw * ry - qx * rz + qy * rw + qz * rx
    z = qw * rz + qx * ry - qy * rx + qz * rw
    w = qw * rw - qx * rx - qy * ry - qz * rz
    rot = ((1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
           (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
           (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)))
    wa = apply(pm, anchor)
    t = [wa[i] - sum(rot[i][k] * anchor[k] for k in range(3)) for i in range(3)]
    return tuple(rot[i] + (t[i],) for i in range(3)) + ((0.0, 0.0, 0.0, 1.0),)


def local_matrix(schema: Euler, x: dict):
    """A transform's local matrix from its :meth:`Graph.xform_fields`."""
    t, sp, spt, rp, rpt = x["t"], x["sp"], x["spt"], x["rp"], x["rpt"]
    m = translate(t[0] + rpt[0] + rp[0], t[1] + rpt[1] + rp[1], t[2] + rpt[2] + rp[2])
    m = mat_mul(m, schema.rotation(*x["r"], x["order"]))
    m = mat_mul(m, translate(spt[0] + sp[0] - rp[0], spt[1] + sp[1] - rp[1], spt[2] + sp[2] - rp[2]))
    m = mat_mul(m, scale(*x["s"]))
    return mat_mul(m, translate(-sp[0], -sp[1], -sp[2]))


def inherit(pm, x: dict):
    """The parent matrix ``pm`` as a child with fields ``x`` inherits it
    (0x681E0): mode 1 keeps only the translation that carries the anchor
    ``t + rp`` along, mode 2 the parent less its tilt (:func:`upright`);
    every other mode ``pm`` itself."""
    a = tuple(x["t"][k] + x["rp"][k] for k in range(3))
    if x["mode"] == 1:
        q = apply(pm, a)
        return translate(q[0] - a[0], q[1] - a[1], q[2] - a[2])
    return upright(pm, a) if x["mode"] == 2 else pm


# --------------------------------------------------------------------------- the level side
@dataclass
class Link:
    src: int
    src_plug: int
    dst: int
    dst_plug: int
    weight: float
    curve: int
    factor: float


class Graph:
    """One ``node`` section and the ``ndbg`` its +0x1C word names.  Offsets
    are section offsets; :attr:`file_offset` is where the section starts."""

    def __init__(self, data, toc: list[TocEntry], entry: TocEntry, schema: Schema):
        o, sz = entry.file_offset, entry.size
        self.schema = schema
        self.file_offset = o
        self.s = s = bytes(data[o:o + sz])
        self.recs = record_offsets(s)
        n = len(self.recs)
        nd = toc[struct.unpack_from("<I", s, 0x1C)[0]]
        if nd.tag != "ndbg":
            raise ValueError(f"node section {entry.index}: +0x1C names a {nd.tag!r} entry")
        b = bytes(data[nd.file_offset:nd.file_offset + nd.size])
        self.ndbg_index = nd.index
        m = struct.unpack_from("<I", b, 8)[0]
        if m != n:
            raise ValueError(f"node section {entry.index}: {n} records but its ndbg names {m}")
        tb = 12 + struct.unpack_from("<i", b, 12)[0]
        self.names: list[str | None] = []
        for k in range(m):
            v = struct.unpack_from("<i", b, tb + 4 * k)[0]
            self.names.append(None if v == 0 else (lstr(b, tb + 4 * k + v, limit=None) or ""))
        self.types = [self.pstr(ro, 0) if ro is not None else None for ro in self.recs]
        self._world: dict = {}
        self._incoming: dict | None = None

    # -- raw access
    def pstr(self, ro: int, lo: int) -> str | None:
        """The (length, ref) string at record offset ``ro + lo``."""
        return lstr(self.s, ro + lo)

    def str_target(self, i: int, lo: int) -> tuple[int, int]:
        """(section offset of the string, length) the (length, ref) field at
        record ``i`` + ``lo`` points at."""
        ro = self.recs[i]
        ln, ref = struct.unpack_from("<Ii", self.s, ro + lo)
        return ro + lo + 4 + ref, ln

    def list_at(self, i: int, lo: int) -> tuple[int, int]:
        """(start, count) of the (count, self-relative ref) list at record ``i`` + ``lo``."""
        return list_at(self.s, self.recs[i] + lo)

    def attrs(self, i: int) -> tuple[float, ...]:
        """Record ``i``'s attribute block (record +0x08), as f32 values."""
        st, n = self.list_at(i, 0x08)
        return struct.unpack_from(f"<{n}f", self.s, st) if n else ()

    def attr_named(self, i: int, name: str) -> float:
        return self.attrs(i)[self.schema.types[self.types[i]].attrs.index(name)]

    def links(self, i: int) -> list[Link]:
        """Record ``i``'s outgoing links (record +0x10)."""
        if self.recs[i] is None:
            return []
        st, n = self.list_at(i, 0x10)
        out = []
        for k in range(n):
            w, curve, f, sp, dp, dn = struct.unpack_from("<fIfHxxHxxI", self.s, st + 24 * k)
            out.append(Link(i, sp, dn, dp, w, curve, f))
        return out

    def all_links(self):
        for i, ro in enumerate(self.recs):
            if ro is not None:
                yield from self.links(i)

    def incoming(self) -> dict[int, list[tuple[Link, int]]]:
        """Each record's incoming links: target record -> [(link, its index
        among its source's links)], in record and link order (a defaultdict,
        built once)."""
        if self._incoming is None:
            self._incoming = collections.defaultdict(list)
            for i, ro in enumerate(self.recs):
                if ro is not None:
                    for k, lk in enumerate(self.links(i)):
                        self._incoming[lk.dst].append((lk, k))
        return self._incoming

    def plug_name(self, i: int, plug: int) -> str:
        return self.schema.attr(self.types[i], plug)

    def saved(self) -> list[int]:
        """The save list: the records a level ``.sav`` restores (0x65E50)."""
        st, n = list_at(self.s, 0x0C)
        return [struct.unpack_from("<I", self.s, st + 4 * k)[0] for k in range(n)]

    def record_sizes(self) -> dict[int, int]:
        """Bytes from each record to the next record's start (64 for the last)."""
        order = sorted(ro for ro in self.recs if ro)
        nxt = dict(zip(order, order[1:]))
        return {i: (nxt.get(ro, ro + 64) - ro) for i, ro in enumerate(self.recs) if ro}

    # -- the DAG
    def is_dag(self, i: int) -> bool:
        return self.recs[i] is not None and self.schema.is_a(self.types[i], "dag")

    def parent(self, i: int) -> int | None:
        if not self.is_dag(i):
            return None
        p = struct.unpack_from("<i", self.s, self.recs[i] + 0x18)[0]
        return None if p < 0 or p >= len(self.recs) else p

    def ancestors(self, i: int, depth: int = 64) -> list[int]:
        out, p = [], self.parent(i)
        while p is not None and len(out) < depth:
            out.append(p)
            p = self.parent(p)
        return out

    # -- transforms
    def xform_fields(self, i: int) -> dict:
        """A transform record's decoded fields (in memory only)."""
        ro = self.recs[i]
        a = self.attrs(i)

        def f(off):
            return struct.unpack_from("<3f", self.s, ro + off)
        return {"t": a[1:4], "r": a[4:7], "s": a[7:10],
                "mode": struct.unpack_from("<I", self.s, ro + 0x28)[0],
                "sp": f(0x2C), "spt": f(0x38), "rp": f(0x44), "rpt": f(0x50),
                "order": struct.unpack_from("<I", self.s, ro + 0x6C)[0]}

    def local(self, i: int):
        """(local matrix, inherit mode) per 0x67F80 / 0x68BE0; the identity
        for a type that isn't a transform."""
        if not self.schema.is_a(self.types[i], "transform"):
            return IDENTITY, 0
        x = self.xform_fields(i)
        return local_matrix(self.schema, x), x["mode"]

    def world(self, i: int):
        """(world matrix, approximate) of record ``i``; approximate is True when
        it or an ancestor uses an inherit mode this module doesn't decode."""
        if i in self._world:
            return self._world[i]
        self._world[i] = (IDENTITY, True)  # cycle guard
        loc, mode = self.local(i)
        p = self.parent(i)
        if p is None:
            res = (loc, mode not in DECODED_MODES)
        else:
            pm, papprox = self.world(p)
            if mode in (1, 2):
                pm = inherit(pm, self.xform_fields(i))
            res = (mat_mul(pm, loc), papprox or mode not in DECODED_MODES)
        self._world[i] = res
        return res

    def world_posed(self, i: int, rec: int, plug: str, delta: float):
        """Record ``i``'s world matrix with transform ``rec``'s plug
        (``translateX`` .. ``scaleZ``) moved by ``delta`` (not cached)."""
        m = IDENTITY
        for k, c in enumerate(list(reversed(self.ancestors(i))) + [i]):
            if not self.schema.is_a(self.types[c], "transform"):
                continue        # a dag that isn't a transform has the identity (local)
            x = self.xform_fields(c)
            if c == rec:
                f = {"translate": "t", "rotate": "r", "scale": "s"}[plug[:-1]]
                v = list(x[f])
                v["XYZ".index(plug[-1])] += delta
                x = dict(x, **{f: tuple(v)})
            m = mat_mul(inherit(m, x) if k else m, local_matrix(self.schema, x))
        return m


def graphs(data, schema: Schema) -> list[Graph]:
    """Every ``node`` section of an XBR, each paired with its own ``ndbg``."""
    toc = parse_toc(data)
    return [Graph(data, toc, t, schema) for t in toc if t.tag == "node"]


def cells(data) -> list[str]:
    """The ``levl`` cell names, by index (header +0x1C count, +0x20 ref;
    72-byte cells whose +0 is the (length, ref) name)."""
    levl = [t for t in parse_toc(data) if t.tag == "levl"]
    if not levl:
        return []
    s = bytes(data[levl[0].file_offset:levl[0].file_offset + levl[0].size])
    n, ref = struct.unpack_from("<Ii", s, 0x1C)
    return [lstr(s, 0x20 + ref + 72 * k, limit=None) or "" for k in range(n)]
