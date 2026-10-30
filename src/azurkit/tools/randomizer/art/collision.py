"""A level's collision in world space: every ``tern`` with its owner,
its collision word and its world placement (``docs/XBR_FORMAT.md``
§ "`tern` (collision)", ``docs/RE_XBE.md`` § "Collision (`tern`): the
engine side").

:mod:`azurik_mod.xbr.tern` reads the sections; this module, built on
the node graph (:mod:`azurik_mod.xbr.nodes`), finds who owns each one:

* the ``levl`` payload's +0x00 (a u32 TOC index) names the level's
  static collision, already in world coordinates; its chunks carry
  their own collision class (0x8050 / 0x8051 / 0x8052 / 0x8013);
* a ``platform`` record's +0x24 (an i32 TOC index, -1 = none) names a
  platform's collision, in the platform's frame: its world matrix
  (:meth:`~azurik_mod.xbr.nodes.Graph.world`) places it, and its
  attributes give the collision word the platform builder 0x6AD20
  makes (:func:`platform_word`).

Every ``tern`` on the disc has exactly one owner, so a second reference,
or a reference to an entry that is not a ``tern``, fails the load.
Ported on 2026-10-12 (Step R1.3a; default taken under D115, Q300) from
the randomizer evidence's ``geometry/tern.py`` (``load_xbr``,
``platform_word``, ``triangles``).  Positions stay in memory: nothing
here prints or stores a coordinate or a game byte (RANDOMIZER_PLAN §4.4,
D87).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from azurkit.tools.randomizer.art import nodes, tern
from azurkit.core.xbr.nodes import parse_toc

PLATFORM_TERN_FIELD = 0x24
"""The i32 TOC index of a ``platform`` record's ``tern`` (-1 = none);
the platform loader reads it at 0x6A943."""

# The collision word's bits, as the platform builder 0x6AD20 sets them
# (attribute indices in parentheses) [verified static, RE_XBE.md].
W_SLIPPERY = 0x01    # slippery (12)
W_CLIMBABLE = 0x02   # climbable (13)
W_AUTOSPRING = 0x04  # autoSpring (16)
W_PUSH = 0x08        # pushEnable (18)
W_SOLID = 0x10       # gameSolid (11)
W_FIELD = 0x20       # a non-solid word with water, a push, damage or fog
W_BLOCK = 0x40       # a solid word unless slippery and climbable are both set
W_WATER = 0x100      # water (14)

TRS_PLUGS = frozenset(f"{a}{x}" for a in ("translate", "rotate", "scale") for x in "XYZ")
"""A transform's plugs that move what it carries when a link drives them."""


def platform_word(attrs: dict) -> int:
    """The low 16 bits 0x6AD20 builds from a platform's attributes (name ->
    value): 0xC000 plus the bits above; ``damage`` counts as an int
    (truncated).  The builder's runtime term ``[obj+0x30] & 4``, which only
    adds 0x20 to a non-solid word, is not in the record and is left out."""
    w = tern.PLATFORM_CHUNK
    for name, bit in (("gameSolid", W_SOLID), ("slippery", W_SLIPPERY), ("climbable", W_CLIMBABLE),
                      ("water", W_WATER), ("autoSpring", W_AUTOSPRING), ("pushEnable", W_PUSH)):
        if attrs.get(name, 0.0) != 0.0:
            w |= bit
    damage = int(attrs.get("damage", 0.0))
    if not w & W_SOLID and ((w & (W_WATER | W_PUSH)) or damage & 0xFF
                            or attrs.get("fieldFogStartDistance", 0.0) != 0.0
                            or attrs.get("fieldFogEndDistance", 0.0) != 0.0):
        w |= W_FIELD
    if w & W_SOLID and (w & 0x13) != 0x13:
        w |= W_BLOCK
    return w


@dataclass
class Owner:
    """Who owns one ``tern``: the level (``kind`` ``levl``) or a platform."""
    kind: str                       # "levl" or "platform"
    tern: int                       # the tern's TOC index
    mesh: tern.Tern
    graph: int | None = None        # the platform's node graph (its index in nodes.graphs())
    record: int | None = None
    name: str | None = None
    attrs: dict | None = None       # the platform's attributes by name
    word: int | None = None         # its collision word (platform_word); a static chunk has its own flags
    world: tuple = nodes.IDENTITY   # the platform's world matrix
    approx: bool = False            # it or an ancestor uses an inherit mode nodes.py doesn't decode
    moved: bool = False             # a link drives an ancestor transform's translate, rotate or scale
    driven: tuple = ()              # the platform's own plugs that links drive (names, sorted)

    def triangles(self):
        """Yield (word, p0, p1, p2) for each face, in world space: a static
        chunk's own flags, or the platform's word and world placement."""
        for ch in self.mesh.chunks:
            if self.kind == "levl":
                w, v = ch.flags, ch.verts
            else:
                w, v = self.word, [nodes.apply(self.world, p) for p in ch.verts]
            for a, b, c, _group in ch.faces:
                yield w, v[a], v[b], v[c]


def owners(data, schema: nodes.Schema, graphs: list[nodes.Graph] | None = None) -> list[Owner]:
    """Every ``tern`` of one XBR file with its owner, sorted by the tern's
    TOC index.  ``graphs`` (from :func:`nodes.graphs`) saves reading the
    node sections again."""
    toc = parse_toc(data)
    out: dict[int, Owner] = {}

    def claim(ti: int, where: str) -> tern.Tern:
        if not 0 <= ti < len(toc) or toc[ti].tag != tern.TAG:
            raise ValueError(f"{where} names TOC entry {ti}, which is not a tern")
        if ti in out:
            raise ValueError(f"{where} names tern {ti}, which already has an owner")
        t = toc[ti]
        return tern.parse(bytes(data[t.file_offset:t.file_offset + t.size]), ti)

    for t in toc:
        if t.tag == "levl" and t.size >= 4:
            ti = struct.unpack_from("<I", data, t.file_offset + tern.LEVL_TERN_FIELD)[0]
            if ti != 0xFFFFFFFF:
                out[ti] = Owner("levl", ti, claim(ti, f"levl {t.index}"), name="levl")
    if graphs is None:
        graphs = nodes.graphs(data, schema)
    attr_names = schema.types["platform"].attrs
    for gi, g in enumerate(graphs):
        inc = g.incoming()
        for i, ty in enumerate(g.types):
            if ty != "platform":
                continue
            (ti,) = struct.unpack_from("<i", g.s, g.recs[i] + PLATFORM_TERN_FIELD)
            if ti < 0:
                continue
            mesh = claim(ti, f"graph {gi} record {i}")
            attrs = dict(zip(attr_names, g.attrs(i)))
            world, approx = g.world(i)
            moved = any(g.types[a] and schema.is_a(g.types[a], "transform")
                        and any(g.plug_name(a, lk.dst_plug) in TRS_PLUGS for lk, _ in inc.get(a, ()))
                        for a in g.ancestors(i))
            driven = tuple(sorted({g.plug_name(i, lk.dst_plug) for lk, _ in inc.get(i, ())}))
            out[ti] = Owner("platform", ti, mesh, gi, i, g.names[i], attrs, platform_word(attrs),
                            world, approx, moved, driven)
    return [out[ti] for ti in sorted(out)]
