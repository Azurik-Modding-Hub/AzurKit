"""A player-only clone of a body's default fx graph, edited, with records
grafted from other graphs and new textures (Step 2.157, D446: "Clone +
author new"; ends D417).

A body's default fx, ``characters/<body>/fx/fx_default`` in
characters.xbr, is the graph 0x43700 instantiates on every critter that
wears the body, the player too.  A variant's (or a W23 overlay's) ``fx``
edits land on a copy of it under :func:`clone_key`,
``characters/<body>/v/fx/fx_default``, which X40 (Step 2.157) binds to
the player alone; every NPC of the body keeps the vanilla graph, so the
airship boss keeps his fx_default and all it reaches byte for byte in a
beamlord build.

:class:`Clone` copies the graph with what it reaches through relocated
fields (:class:`~azurik_mod.xbr.clone.Copier`: the textures and sounds
shared, every mesh, push buffer, collision, material, sprv and the ndbg
copied, as no two vanilla graphs share them) and applies, in order:

- **grafts** (``fx_grafts``): a set of another graph's records (a named
  graft of :data:`~azurik_mod.assets.fx_templates.GRAFTS`, or ``from``
  an archive, key and records)
  added at the end of the clone, in the donor's order (every parent
  before its child in all 8,358 DAG records of the 226 fx graphs), the
  set's roots under the recipe's ``parent`` (or, :data:`ROOT`, roots of
  the graph: a bound template's effectOrigin root, Step 2.167c).  The donor's whole node
  payload goes at the clone's tail as one block, so every self-relative
  reference of a grafted record (its type name, attributes, links and
  their curves, a platform's descriptors, LOD tables, sub-bounds and
  class strings, a transform's child list, a bind name, a particle
  system's lists) holds; then the record indices are remapped (a DAG
  parent, each link's destination, a pSystem's renderer and components
  and a pBurstEmitter's targets, :func:`index_fields`: one leaving the
  set is refused) and the relocated fields the grafted
  records own (:func:`owned_fields`) name copies of their targets (from
  fx.xbr every target copied; a streamed sound refused).  The record
  table moves to the clone's end, a grafted record its donor's +0x14
  list held joins the clone's, and the ndbg copy gains their names.
- per edit: ``parent`` (a DAG record's parent), ``inherit`` (a
  transform's mode, :data:`INHERIT_MODES`), ``anchor`` (a transform bound
  to a marker of the wearer by name, and renamed so: Step 2.167a, the
  holder an effect template hangs under), ``set`` (attributes by the
  type's names in the XBE's node schema, f32), ``links`` (a link's
  destination, plug, weight, factor), ``mesh`` (a platform of one
  descriptor and one LOD drawing a static glTF's mesh in its copies'
  place, its material and row kept, its bounds the mesh's:
  :mod:`azurik_mod.assets.fx_mesh`, Step 2.155e), ``material`` (a
  platform's rows, in the clone's copy of its material), ``texture`` (a renderer's
  texture or a platform material's stage: a new ``surf``, a recolour of
  the one it draws or a PNG, an animated list frame by frame (a PNG's
  every frame one new ``surf``); with
  ``shared``, a row other meshes of the clone draw too, for them all;
  :mod:`azurik_mod.assets.textures`) and ``graph`` (an ``effect``
  record's graph key, +0x1C, rewritten in its own string's bytes with its
  length: a key no longer than the old one, so nothing grows; Step
  2.159b points the thrown rock's break at its own clone).

Record indices of the source never change, so a recipe names each record
by index, name and type, both checked; a grafted record's index is the
source's count plus its place.  :meth:`Clone.build` returns the clone
(named) and its copies and new textures (unnamed) as
:class:`~azurik_mod.xbr.append.NewResource` values for
:func:`~azurik_mod.xbr.append.append_resources`; :meth:`Clone.plan`
says what they are.  Every refusal is a :class:`ValueError` naming the
edit (D35).  Nothing here prints a byte.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

from azurkit.tools.characters import fx_mesh, textures
from azurkit.tools.characters import render
from azurkit.core.xbr.append import NewResource
from azurkit.core.xbr.clone import Batch, Copier
from azurkit.core.xbr.graph import Graph, Schema, list_at
from azurkit.core.xbr.nodes import named_resources, parse_toc

INHERIT_MODES = (0, 1, 2, 3, 6, 7)
"""The inherit modes an edit may give a transform (0x681E0's jump table at
0x68BBC): 0 and 6 compose normally, 1 keeps only the parent's carriage of
the anchor, 2 the parent less its tilt, 3 the anchor where the parent
puts it with the top camera's axes (0x6880A, Step 2.157: the game's
shields face the camera so); 7 places the node in the player critter's
frame, its parent unread (0x68A43), where X37's anchor may move it onto
another critter (Step 2.197b: the beam's bolt targets, AZ-769)."""
GRAFTABLE = ("transform", "platform", "shader", "randomNumber", "timer", "combiner", "polyTrail", "effect",
             "pSystem", "pEmitter", "pBurstEmitter", "pSink", "pBoxSink", "pAccelerator", "pGravity", "pVortex",
             "pNull", "pRendererB")
"""The record types a graft takes: those whose record-index fields are
all read (a DAG parent at +0x18, the links' destinations and
:func:`index_fields`; each type's loader, Step 2.167a) and whose
relocated fields :func:`owned_fields` names; any other refused by name
(an ``effectControl``, which unloads the whole instance, among them)."""
CELL_LISTS = {"pSystem": 0x28, "polyTrail": 0x24}
"""The (count, self-relative ref) lists of u16 cell indices a pSystem
(0x6BD30) and a polyTrail (0x71580) hold, the instance's cell added: empty
in all 471 of the 226 fx graphs [data: Step 2.167a's census], and a graft
that holds one is refused (it names the donor's cells)."""
ARCHIVES = ("characters", "fx")
"""The archives a graft's donor graph may come from."""
ROOT = -1
"""A graft's ``parent`` that leaves its set's roots roots of the clone, as
the donor's DAG roots are (parent -1): the effectOrigin root of a bound
effects template's own graph, its holder under it (Step 2.167c, AZ-709)."""
MARKER_LIMIT = 255
"""The longest marker name an ``anchor`` edit writes (the readers stop at
300; the game's longest is 30)."""


def check_marker(where: str, marker) -> str:
    """``marker``, an ``anchor`` edit's marker name (printable ASCII, no
    space, 1 to :data:`MARKER_LIMIT` characters), or a :class:`ValueError`
    naming ``where``."""
    if (not isinstance(marker, str) or not 0 < len(marker) <= MARKER_LIMIT or not marker.isascii()
            or not marker.isprintable() or " " in marker):
        raise ValueError(f"{where}: {marker!r} is not a marker name (printable ASCII, no space, 1 to "
                         f"{MARKER_LIMIT} characters)")
    return marker


def default_key(body: str) -> str:
    """``body``'s default fx key, as 0x43700 formats it (lower case)."""
    return f"characters/{body}/fx/fx_default".casefold()


def clone_key(body: str) -> str:
    """The key of the player's clone of ``body``'s default fx (X40's
    format, ``characters/%s/v/fx/fx_default``)."""
    return f"characters/{body}/v/fx/fx_default".casefold()


def stand_key(body: str) -> str:
    """The key of the player's clone of a recipe's ``fx_ring.stand`` graph
    when its ``fx`` edits it (Step 2.155b, D501), ``characters/<body>/v/fx/
    fx_stand``: X38 spawns it by name, so no NPC plays it."""
    return f"characters/{body}/v/fx/fx_stand".casefold()


def _f32(out: bytearray, at: int, value: float, where: str) -> None:
    try:
        struct.pack_into("<f", out, at, value)
    except OverflowError:
        raise ValueError(f"{where}: {value!r} is past what an f32 holds") from None


def _rel(buf, at: int) -> int:
    return at + struct.unpack_from("<i", buf, at)[0]


def _pad(buf: bytearray, align: int) -> int:
    buf += bytes(-len(buf) % align)
    return len(buf)


def lod_fields(buf, rec: int) -> list[tuple[int, int]]:
    """The offsets in ``buf`` of a platform record's (at ``rec``) LOD pair
    fields, (rdms, push buffer), every descriptor's every LOD."""
    start, count = list_at(buf, rec + 0x1C)
    out = []
    for k in range(count):
        d = start + 72 * k
        pairs, lods = list_at(buf, d + 64)
        if struct.unpack_from("<I", buf, d + 28)[0] != 5:
            continue
        out += [(pairs + 16 * j, pairs + 16 * j + 4) for j in range(lods)]
    return out


def owned_fields(schema: Schema, buf, kind: str, rec: int) -> list[int]:
    """The offsets in ``buf`` of the fields a record of type ``kind`` at
    ``rec`` may hold a TOC index in: a platform's LOD pairs and collision
    (+0x24), a renderer's texture and a shader's material (+0x18), a sound
    node's wave (+0x18 stereoSound, +0x1C soundEffect) and a trail's
    material (+0x1C, a ``gshd``; its row at +0x20, 0x7C443).  Every
    relocated field of every vanilla fx graph but
    its header's ndbg (+0x1C) is one of these [data: Step 2.157, 34,693
    rows of 226 graphs]."""
    if kind == "platform":
        return [f for pair in lod_fields(buf, rec) for f in pair] + [rec + 0x24]
    if schema.is_a(kind, "pRendererB") or kind in ("shader", "stereoSound"):
        return [rec + 0x18]
    if kind in ("soundEffect", "polyTrail"):
        return [rec + 0x1C]
    return []


def index_fields(buf, kind: str, rec: int) -> list[tuple[int, str]]:
    """The offsets in ``buf`` of the record-index words a record of type
    ``kind`` at ``rec`` holds besides its DAG parent (+0x18) and its links'
    destinations, each with its role: a pSystem's ``renderer`` (+0x20, its
    pRendererB, -1 none) and ``component`` list (the (count, self-relative
    ref) list at +0x30 of u32 indices: its emitters, sinks and forces), a
    pBurstEmitter's ``target`` list (+0x1C: the pNulls, or pEmitters, its
    bolts reach).  The other graftable types' loaders read none: a timer's
    (the base node's 0x658E0), a combiner's (0x69BF0: +0x18 its input
    count, +0x1C its function), an effect's (0x707D0: its key string at
    +0x1C), a polyTrail's (0x71580) and the components' (their parent
    alone) [static: 0x6BD30, 0x6C210, 0x6D580, each type's vtable slots 1
    and 2; data: Step 2.167a's census, every value in range and of those
    types in the 226 fx graphs, no two lists sharing storage]."""
    if kind == "pSystem":
        start, n = list_at(buf, rec + 0x30)
        own = [(rec + 0x20, "renderer")] if struct.unpack_from("<i", buf, rec + 0x20)[0] != -1 else []
        return own + [(start + 4 * k, "component") for k in range(n)]
    if kind == "pBurstEmitter":
        start, n = list_at(buf, rec + 0x1C)
        return [(start + 4 * k, "target") for k in range(n)]
    return []


def material_row_at(gshd: bytes | bytearray, row: int) -> int | None:
    """The offset of material row ``row`` in a ``gshd`` payload, or None."""
    if not 0 <= row < struct.unpack_from("<I", gshd, 0)[0]:
        return None
    return _rel(gshd, _rel(gshd, 4) + 4 * row)


def donor_records(spec: dict) -> tuple[str, str, tuple[int, ...]]:
    """A graft's donor: (archive, key, records ascending)."""
    if "template" in spec:
        from azurkit.tools.characters.fx_templates import GRAFTS
        t = GRAFTS[spec["template"]]
        return t.archive, t.key, tuple(r for r, _, _ in t.records)
    f = spec["from"]
    return f["archive"], f["key"].casefold(), tuple(sorted(set(f["records"])))


class Clone:
    """``key``'s graph in ``characters`` (its own archive, ``archive``:
    ``characters`` for a body's default fx, or ``fx``) cloned for editing,
    its new entries numbered from ``base`` (the archive's count unless
    other entries are appended first), on ``xbe``'s node schema;
    ``fx_xbr`` (vanilla fx.xbr) for grafts from it into a characters.xbr
    clone, ``characters_xbr`` (vanilla characters.xbr) for grafts from it
    into an fx.xbr one (Step 2.196: the drain stream's sets on a copy of
    fx_norm_1); ``folder`` where a texture edit's PNG files and a mesh
    edit's glTF are."""

    def __init__(self, characters: bytes, key: str, xbe: bytes, *, base: int | None = None,
                 fx_xbr: bytes | None = None, folder: Path | None = None, archive: str = "characters",
                 characters_xbr: bytes | None = None):
        if archive not in ARCHIVES:
            raise ValueError(f"fx: archive {archive!r} is not one of {', '.join(ARCHIVES)}")
        self.characters, self.fx_xbr, self.folder, self.archive = characters, fx_xbr, folder, archive
        self.characters_xbr = characters_xbr
        self.key = key.casefold()
        self.schema = Schema(xbe)
        self.toc = parse_toc(characters)
        self.index = next((i for i, n in named_resources(characters).items() if n.casefold() == self.key), None)
        if self.index is None or self.toc[self.index].tag != "node":
            raise ValueError(f"fx: {archive}.xbr has no graph {self.key}")
        self.source = Graph(characters, self.toc, self.toc[self.index], self.schema)
        self.batch = Batch(characters, base)
        self.copier = Copier(characters, self.batch, same=True, label=f"{archive}.xbr")
        self.copiers = {archive: self.copier}
        self.node = self.batch.add("node", b"", source=(f"{archive}.xbr", self.index))
        self.payload = bytearray(self.source.s)
        self.refs = {off: self.copier.target(t) for off, t in self.copier.refs(self.index)}
        self.recs = list(self.source.recs)
        self.types = list(self.source.types)
        self.names = list(self.source.names)
        self.third = [struct.unpack_from("<I", self.payload, list_at(self.payload, 0x14)[0] + 4 * k)[0]
                      for k in range(list_at(self.payload, 0x14)[1])]
        self.ndbg = bytes(self.batch[self.refs[0x1C]].payload)   # the copy as copied; _finish grows it
        self.edited: set[int] = set()
        self.renamed: dict[int, str] = {}
        self.grafts: list[dict] = []
        self.textures: dict[tuple[int, str], int] = {}

    # -- reading the clone
    def record(self, where: str, edit: dict) -> int:
        """Edit ``where``'s record, its name and type checked."""
        r = edit["record"]
        got = (self.names[r], self.types[r]) if 0 <= r < len(self.recs) and self.recs[r] is not None else (None, None)
        if got != (edit["name"], edit["type"]):
            raise ValueError(f"{where}: record {r} of {self.key} is {got[0]!r} ({got[1]}), not {edit['name']!r} "
                             f"({edit['type']})")
        return r

    def attrs_of(self, r: int) -> list[str]:
        return self.schema.types[self.types[r]].attrs

    def is_dag(self, r: int) -> bool:
        return self.recs[r] is not None and self.schema.is_a(self.types[r], "dag")

    def parent(self, r: int) -> int | None:
        p = struct.unpack_from("<i", self.payload, self.recs[r] + 0x18)[0] if self.is_dag(r) else -1
        return None if p < 0 else p

    def entry_bytes(self, index: int) -> bytes:
        """TOC entry ``index``'s payload in the build: a new one's, or the archive's."""
        if index in self.batch:
            return bytes(self.batch[index].payload)
        e = self.toc[index]
        return bytes(self.characters[e.file_offset:e.file_offset + e.size])

    # -- edits
    def apply(self, edits, grafts=()) -> None:
        """Each graft (``template`` or ``from``, with ``parent``), then each
        edit (``record``, ``name``, ``type`` and one or more of ``parent``,
        ``inherit``, ``anchor``, ``set``, ``links``, ``mesh``,
        ``material``, ``texture``, ``graph``), in order; an edit names a
        record by its name before any ``anchor`` renames it."""
        for k, spec in enumerate(grafts):
            self.graft(f"fx_grafts[{k}]", spec)
        for k, edit in enumerate(edits):
            where = f"fx[{k}]"
            r = self.record(where, edit)
            self.edited.add(r)
            if "parent" in edit:
                self._parent(where, r, edit["parent"])
            if "inherit" in edit:
                self._inherit(where, r, edit["inherit"])
            if "anchor" in edit:
                self._anchor(where, r, edit["anchor"])
            if "set" in edit:
                self._set(where, r, edit["set"])
            if "links" in edit:
                self._links(where, r, edit["links"])
            if "mesh" in edit:
                self._mesh(where, r, edit["mesh"])
            if "material" in edit:
                self._material(where, r, edit)
            if "texture" in edit:
                self._texture(where, r, edit["texture"])
            if "graph" in edit:
                self._graph(where, r, edit["graph"])

    def _set(self, where: str, r: int, values: dict) -> None:
        attrs = self.attrs_of(r)
        start, n = list_at(self.payload, self.recs[r] + 8)
        for attr, value in values.items():
            if attr not in attrs or attrs.index(attr) >= n:
                raise ValueError(f"{where}: a {self.types[r]} has no attribute {attr!r}")
            _f32(self.payload, start + 4 * attrs.index(attr), value, f"{where}.set.{attr}")

    def _links(self, where: str, r: int, edits) -> None:
        links, count = list_at(self.payload, self.recs[r] + 0x10)
        for j, link in enumerate(edits):
            at = f"{where}.links[{j}]"
            if link["index"] >= count:
                raise ValueError(f"{at}: record {r} ({self.names[r]}) has {count} links")
            entry = links + 24 * link["index"]
            dst = link.get("dst", struct.unpack_from("<I", self.payload, entry + 20)[0])
            if not 0 <= dst < len(self.recs) or self.recs[dst] is None:
                raise ValueError(f"{at}.dst: {self.key} has no record {dst}")
            struct.pack_into("<I", self.payload, entry + 20, dst)
            if "dst_plug" in link:
                plugs = self.attrs_of(dst)
                if link["dst_plug"] not in plugs:
                    raise ValueError(f"{at}.dst_plug: a {self.types[dst]} has no attribute {link['dst_plug']!r}")
                struct.pack_into("<H", self.payload, entry + 16, plugs.index(link["dst_plug"]))
            for name, off in (("weight", 0), ("factor", 8)):
                if name in link:
                    _f32(self.payload, entry + off, link[name], f"{at}.{name}")

    def _graph(self, where: str, r: int, key: str) -> None:
        if not self.schema.is_a(self.types[r], "effect"):
            raise ValueError(f"{where}.graph: a {self.types[r]} isn't an effect, so it loads no graph")
        at = self.recs[r] + 0x1C
        n, ref = struct.unpack_from("<Ii", self.payload, at)
        raw = key.casefold().encode("ascii")
        if not raw or len(raw) > n:
            raise ValueError(f"{where}.graph: {key!r} is {len(raw)} characters, and {self.names[r]}'s key holds "
                             f"{n} (an edit in place: nothing grows)")
        start = at + 4 + ref
        self.payload[start:start + n] = raw + bytes(n - len(raw))
        struct.pack_into("<I", self.payload, at, len(raw))

    def _inherit(self, where: str, r: int, mode: int) -> None:
        if not self.schema.is_a(self.types[r], "transform"):
            raise ValueError(f"{where}.inherit: a {self.types[r]} isn't a transform, so it has no inherit mode")
        if mode not in INHERIT_MODES:
            raise ValueError(f"{where}.inherit: {mode!r} is not one of {', '.join(map(str, INHERIT_MODES))}")
        struct.pack_into("<I", self.payload, self.recs[r] + 0x28, mode)

    def _anchor(self, where: str, r: int, marker) -> None:
        """Bind transform ``r`` to ``marker``: +0x1C := 1 and the (length,
        ref) name at +0x20 a new NUL-terminated copy at the payload's end
        (0x67F80 copies it when +0x1C isn't 0), the record renamed so (as
        all 770 bound transforms of the fx graphs are named)."""
        if not self.schema.is_a(self.types[r], "transform"):
            raise ValueError(f"{where}.anchor: a {self.types[r]} isn't a transform, so it follows no marker")
        check_marker(f"{where}.anchor", marker)
        at = _pad(self.payload, 4)
        self.payload += marker.encode("ascii") + b"\0"
        struct.pack_into("<IIi", self.payload, self.recs[r] + 0x1C, 1, len(marker), at - (self.recs[r] + 0x24))
        self.renamed[r] = marker

    def _parent(self, where: str, r: int, p: int) -> None:
        if not self.is_dag(r):
            raise ValueError(f"{where}.parent: a {self.types[r]} isn't in the DAG, so it has no parent")
        if self.parent(r) is None:
            raise ValueError(f"{where}.parent: {self.names[r]} is a root of the graph (no parent to change)")
        if not (0 <= p < r and self.is_dag(p)):
            raise ValueError(f"{where}.parent: record {p} isn't a DAG record before {r} (a parent comes before its "
                             "child in every vanilla graph)")
        struct.pack_into("<i", self.payload, self.recs[r] + 0x18, p)

    def _file(self, at: str, ref: dict) -> Path:
        """A recipe's file ``ref`` ({``file``, ``sha256``}) in :attr:`folder`, its sha256 checked."""
        if self.folder is None:
            raise ValueError(f"{at}: no folder holds the recipe's files")
        path = self.folder / ref["file"]
        try:
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ValueError(f"{at}: {ref['file']}: {exc.strerror}") from None
        if sha != ref["sha256"]:
            raise ValueError(f"{at}: {ref['file']}'s sha256 isn't the recipe's")
        return path

    def _mesh(self, where: str, r: int, spec: dict) -> None:
        """Platform ``r`` draws ``spec``'s glTF (a ``.glb``): its one LOD
        pair's copies (the clone's ``rdms`` and push buffer) rewritten
        (:func:`~azurik_mod.assets.fx_mesh.from_gltf`), the ``rdms`` keeping
        its material and row, the push buffer retagged by its size with the
        pair's fourcc, the descriptor's bounds and its sub-bounds the
        mesh's.  Another platform of the clone naming the same copies
        draws it too."""
        at = f"{where}.mesh"
        if not self.schema.is_a(self.types[r], "platform"):
            raise ValueError(f"{at}: a {self.types[r]} isn't a platform, so it draws no mesh")
        d, count = list_at(self.payload, self.recs[r] + 0x1C)
        pairs = lod_fields(self.payload, self.recs[r])
        if count != 1 or len(pairs) != 1:
            raise ValueError(f"{at}: {self.names[r]} has {count} descriptors and {len(pairs)} meshes; a mesh edit "
                             "takes a platform of one")
        old, pb = self.batch[self.refs[pairs[0][0]]], self.batch[self.refs[pairs[0][1]]]
        path = self._file(f"{at}.gltf", spec["gltf"])
        try:
            mesh, strip = fx_mesh.from_gltf(path, old.refs[4], struct.unpack_from("<I", old.payload, 8)[0])
        except ValueError as exc:
            raise ValueError(f"{at}.gltf: {spec['gltf']['file']}: {exc}") from None
        old.payload, old.refs, old.source = bytearray(fx_mesh.write_rdms(mesh)), {}, f"{at} ({path.name})"
        old.point(4, mesh.gshd)
        blob, tag = fx_mesh.write_push(strip)
        pb.payload, pb.tag, pb.source = bytearray(blob), tag, f"{at} ({path.name})"
        self.payload[pairs[0][0] + 8:pairs[0][0] + 12] = tag.encode("ascii")
        box = fx_mesh.bounds(mesh)
        struct.pack_into("<6f", self.payload, d + 4, *box)
        sub, n = list_at(self.payload, d + 48)
        for k in range(n):
            struct.pack_into("<6f", self.payload, sub + 24 * k, *box)

    def meshes(self, r: int) -> list[int]:
        """Platform record ``r``'s meshes: the clone's ``rdms`` copies its
        LOD pairs name, each once."""
        out = []
        for rdms, _ in lod_fields(self.payload, self.recs[r]):
            if rdms in self.refs and self.refs[rdms] not in out:
                out.append(self.refs[rdms])
        return out

    def material_rows(self, where: str, r: int, shared: bool = False) -> list[tuple[int, int]]:
        """Platform record ``r``'s materials, (the clone's ``gshd`` copy, row);
        a row another mesh of the clone names too is refused unless ``shared``
        (the edit then changes those meshes with it: the boulder break's 7
        shards draw one row)."""
        if not self.schema.is_a(self.types[r], "platform"):
            raise ValueError(f"{where}: a {self.types[r]} isn't a platform, so it draws no material")
        meshes = self.meshes(r)
        rows = sorted({(self.batch[m].refs[4], struct.unpack_from("<I", self.batch[m].payload, 8)[0])
                       for m in meshes if 4 in self.batch[m].refs})
        if not rows:
            raise ValueError(f"{where}: {self.names[r]} draws no mesh")
        for gshd, row in rows if not shared else ():   # another mesh of the clone naming the row changes with it
            others = [i for i, e in enumerate(self.batch.entries, self.batch.base)
                      if e.tag == "rdms" and i not in meshes and e.refs.get(4) == gshd
                      and struct.unpack_from("<I", e.payload, 8)[0] == row]
            if others:
                raise ValueError(f"{where}: gshd row {row} is another mesh's material too, not "
                                 f"{self.names[r]}'s alone")
        return rows

    def _material(self, where: str, r: int, edit: dict) -> None:
        for gshd, row in self.material_rows(f"{where}.material", r):
            entry = self.batch[gshd]
            start = material_row_at(entry.payload, row)
            if start is None:
                raise ValueError(f"{where}.material: its material has no row {row}")
            for name, value in edit["material"].items():
                at, fmt = render.MATERIAL_FIELDS[name]
                if fmt == "<f":
                    _f32(entry.payload, start + at, value, f"{where}.material.{name}")
                else:
                    struct.pack_into(fmt, entry.payload, start + at, value)

    # -- textures
    def _texture(self, where: str, r: int, spec: dict) -> None:
        at = f"{where}.texture"
        if self.schema.is_a(self.types[r], "pRendererB"):
            field = self.recs[r] + 0x18
            if field not in self.refs:
                raise ValueError(f"{at}: {self.names[r]} draws no texture")
            self.refs[field] = self._new_texture(at, self.refs[field], spec)
            return
        if not self.schema.is_a(self.types[r], "platform"):
            raise ValueError(f"{at}: a {self.types[r]} draws no texture of its own (a pRendererB or a platform)")
        stage = spec.get("stage", 0)
        for gshd, row in self.material_rows(at, r, bool(spec.get("shared", False))):
            entry = self.batch[gshd]
            start = material_row_at(entry.payload, row)
            stages = struct.unpack_from("<I", entry.payload, start + 96)[0]
            if not 0 <= stage < stages:
                raise ValueError(f"{at}.stage: its material row has {stages} stages")
            off = start + 100 + 124 * stage
            if off not in entry.refs:
                raise ValueError(f"{at}.stage: stage {stage} names no texture")
            entry.point(off, self._new_texture(at, entry.refs[off], spec))

    def _image(self, at: str, spec: dict, base) -> object:
        if "png" in spec:
            return textures.read_png(self._file(f"{at}.png", spec["png"]).read_bytes())
        recolor = spec["recolor"]
        return textures.recolor(base, recolor["ramp"], recolor.get("gamma", 1.0), recolor.get("gain", 1.0))

    def _new_texture(self, at: str, src: int, spec: dict) -> int:
        """A new ``surf`` from ``src`` (a texture or an animated list, frame
        by frame) as ``spec`` makes it; each (source, spec) made once, a
        PNG's once whatever its source (a list's frames all name it, in
        the first frame's format unless ``spec`` gives one)."""
        payload = self.entry_bytes(src)
        info = textures.info(payload)
        memo = (None if "png" in spec and "list" not in info else src, json.dumps(spec, sort_keys=True))
        if memo in self.textures:
            return self.textures[memo]
        if "list" in info:
            frames = [self._new_texture(at, f, spec) for f in info["list"]]
            body, relocs = textures.list_surf(frames)
            new = self.batch.add("surf", body, dict(zip(relocs, frames)), source=f"{at} (list of {src})")
        else:
            fmt = textures.FORMATS[spec["format"]] if "format" in spec else info["format"]
            try:
                img = self._image(at, spec, textures.levels(payload)[0])
                new = self.batch.add("surf", textures.surf(img, fmt), source=f"{at} (from surf {src})")
            except ValueError as exc:
                raise ValueError(f"{at}: {exc}") from None
        self.textures[memo] = new
        return new

    # -- grafts
    def copier_for(self, archive: str) -> Copier:
        if archive not in self.copiers:
            src = {"fx": self.fx_xbr, "characters": self.characters_xbr}.get(archive)
            if src is None:
                raise ValueError(f"a graft from {archive}.xbr into {self.archive}.xbr: the build has no "
                                 f"{archive}.xbr to copy from")
            self.copiers[archive] = Copier(src, self.batch, same=False, label=f"{archive}.xbr")
        return self.copiers[archive]

    def graft(self, where: str, spec: dict) -> list[int]:
        """``spec``'s records appended to the clone (module docstring); their
        new indices."""
        archive, key, records = donor_records(spec)
        if archive not in ARCHIVES:
            raise ValueError(f"{where}: archive {archive!r} is not one of {', '.join(ARCHIVES)}")
        copier = self.copier_for(archive)
        data, toc = copier.src, copier.toc
        index = next((i for i, n in named_resources(data).items() if n.casefold() == key), None)
        if index is None or toc[index].tag != "node":
            raise ValueError(f"{where}: {archive}.xbr has no graph {key}")
        donor = Graph(data, toc, toc[index], self.schema)
        if "template" in spec:
            from azurkit.tools.characters.fx_templates import GRAFTS
            for r, name, kind in GRAFTS[spec["template"]].records:
                if r >= len(donor.recs) or (donor.names[r], donor.types[r]) != (name, kind):
                    raise ValueError(f"{where}: {key} [{r}] isn't {name!r} ({kind}): not a vanilla {archive}.xbr")
        new = {d: len(self.recs) + j for j, d in enumerate(records)}
        for d in records:
            if not 0 <= d < len(donor.recs) or donor.recs[d] is None:
                raise ValueError(f"{where}: {key} has no record {d}")
            if donor.types[d] not in GRAFTABLE:
                raise ValueError(f"{where}: {key} [{d}] is a {donor.types[d]}, and a graft takes only "
                                 f"{', '.join(GRAFTABLE)} records (their record-index fields are read)")
            for j, link in enumerate(donor.links(d)):
                if link.dst not in new:
                    raise ValueError(f"{where}: {key} [{d}] {donor.names[d]}'s link {j} goes to [{link.dst}] "
                                     f"{donor.names[link.dst]}, outside the graft")
            for f, role in index_fields(donor.s, donor.types[d], donor.recs[d]):
                v = struct.unpack_from("<I", donor.s, f)[0]
                if v not in new:
                    name = donor.names[v] if v < len(donor.names) else None
                    raise ValueError(f"{where}: {key} [{d}] {donor.names[d]}'s {role} [{v}] {name} is outside the "
                                     "graft")
            if (cells := CELL_LISTS.get(donor.types[d])) and list_at(donor.s, donor.recs[d] + cells)[1]:
                raise ValueError(f"{where}: {key} [{d}] {donor.names[d]} holds a cell list, which names the "
                                 "donor's cells")
        roots = [d for d in records if donor.is_dag(d) and donor.parent(d) not in new]
        parent = spec.get("parent")
        if roots and parent != ROOT and (isinstance(parent, bool) or not isinstance(parent, int)
                                         or not 0 <= parent < len(self.recs) or not self.is_dag(parent)):
            raise ValueError(f"{where}.parent: {parent!r} isn't a DAG record of {self.key} to hang "
                             f"{', '.join(donor.names[d] for d in roots)} under")
        for d in records:
            p = donor.parent(d)
            if p in new and new[p] > new[d]:
                raise ValueError(f"{where}: {key} [{d}]'s parent [{p}] comes after it")
        rows = dict(copier.refs(index))
        owned = {}
        for r, ro in enumerate(donor.recs):
            if ro is not None:
                for f in owned_fields(self.schema, donor.s, donor.types[r], ro):
                    if f in rows:
                        owned[f] = r
        stray = sorted(set(rows) - set(owned) - {0x1C})
        if stray:
            raise ValueError(f"{where}: {key} holds a relocated field at +0x{stray[0]:X} no record's known field "
                             "names, so a graft can't tell whose it is")
        block = _pad(self.payload, 16)
        self.payload += donor.s
        listed = {struct.unpack_from("<I", donor.s, list_at(donor.s, 0x14)[0] + 4 * k)[0]
                  for k in range(list_at(donor.s, 0x14)[1])}
        for d in records:
            ro = block + donor.recs[d]
            if donor.is_dag(d):
                p = donor.parent(d)
                struct.pack_into("<i", self.payload, ro + 0x18, new[p] if p in new else parent)
            links, count = list_at(donor.s, donor.recs[d] + 0x10)
            for j in range(count):
                dst = struct.unpack_from("<I", donor.s, links + 24 * j + 20)[0]
                struct.pack_into("<I", self.payload, block + links + 24 * j + 20, new[dst])
            for f, _ in index_fields(donor.s, donor.types[d], donor.recs[d]):
                struct.pack_into("<I", self.payload, block + f, new[struct.unpack_from("<I", donor.s, f)[0]])
            for f, owner in owned.items():
                if owner == d:
                    self.refs[block + f] = copier.target(rows[f])
            self.recs.append(ro)
            self.types.append(donor.types[d])
            self.names.append(donor.names[d])
            if d in listed:
                self.third.append(new[d])
        self.grafts.append({"from": f"{archive}.xbr {key}", "template": spec.get("template"),
                            "records": {new[d]: f"[{d}] {donor.names[d]} ({donor.types[d]})" for d in records}})
        return [new[d] for d in records]

    # -- the result
    def _finish(self) -> bytearray:
        """The clone's payload with its record table, +0x14 list and ndbg
        grown to the grafted records, and the ndbg naming each anchored
        record by its marker (unchanged without grafts or anchors)."""
        out = bytearray(self.payload)
        grown = len(self.recs) != len(self.source.recs)
        if not grown and not self.renamed:
            return out
        if grown:
            table = _pad(out, 4)
            for k, ro in enumerate(self.recs):
                out += struct.pack("<i", 0 if ro is None else ro - (table + 4 * k))
            struct.pack_into("<Ii", out, 0, len(self.recs), table - 4)
            if len(self.third) != list_at(self.payload, 0x14)[1]:
                third = len(out)
                out += struct.pack(f"<{len(self.third)}I", *self.third)
                struct.pack_into("<Ii", out, 0x14, len(self.third), third - 0x18)
        _pad(out, 16)
        nd = self.batch[self.refs[0x1C]].payload = bytearray(self.ndbg)
        count, start = struct.unpack_from("<I", nd, 8)[0], 12 + struct.unpack_from("<i", nd, 12)[0]
        targets = [None if not (v := struct.unpack_from("<i", nd, start + 4 * k)[0]) else start + 4 * k + v
                   for k in range(count)]
        for k in [k for k in sorted(self.renamed) if k < count] + list(range(count, len(self.names))):
            name = self.renamed.get(k, self.names[k])
            at = _pad(nd, 4)
            text = (name or "").encode("ascii")
            nd += struct.pack("<Ii", len(text), 4) + text + b"\0"
            if k < count:
                targets[k] = at
            else:
                targets.append(at if name else None)
        table = _pad(nd, 4)
        for k, t in enumerate(targets):
            nd += struct.pack("<i", 0 if t is None else t - (table + 4 * k))
        struct.pack_into("<Ii", nd, 8, len(targets), table - 12)
        _pad(nd, 16)
        return out

    def build(self, as_key: str) -> list[NewResource]:
        """The clone, named ``as_key``, and every copy and new texture,
        unnamed, in TOC order from the batch's base."""
        node = self.batch[self.node]
        node.payload = self._finish()
        node.name = as_key.casefold()
        node.refs = {}
        for off, target in self.refs.items():
            node.point(off, target)
        return self.batch.resources()

    def plan(self) -> dict:
        """What :meth:`build` appends: the clone's records, the edited ones,
        the grafts, each new entry (tag, source, bytes) and the shared
        vanilla entries it names (the ndbg as :meth:`_finish` grows it)."""
        node = self._finish()   # first: it grows the ndbg entry the list counts
        entries = [(e.tag, e.source, len(e.payload)) for e in self.batch.entries[1:]]
        shared = sorted({t for t in self.refs.values() if t < self.batch.count}
                        | {t for e in self.batch.entries for t in e.refs.values() if t < self.batch.count})
        return {"key": self.key, "records": len(self.recs), "edited": sorted(self.edited), "grafts": self.grafts,
                "entries": entries, "shared": shared,
                "bytes": len(node) + sum(size for _, _, size in entries)}


__all__ = ["ARCHIVES", "CELL_LISTS", "GRAFTABLE", "INHERIT_MODES", "MARKER_LIMIT", "ROOT", "Clone", "check_marker",
           "clone_key", "default_key", "donor_records", "index_fields", "lod_fields", "material_row_at",
           "owned_fields", "stand_key"]
