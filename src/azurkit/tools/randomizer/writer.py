"""The randomizer's writer: a plan's placement into the level files, and
the read-back that gates every build (RANDOMIZER_PLAN §5.2, path (b2);
Step R1.10a).

A placement maps pool location ids (``<file>/g<G>/r<R>``, the generated
data's) to ``items.toml`` names.  The writer never renames a string
(the M3 lesson, §5.1): it repoints each changed location's critter-name
field (record +0x1C length, +0x20 self-relative ref; the string sits at
record + 0x20 + ref) at a string in the **same node graph**:

* an existing one: another location's template string in that graph,
  so gem and obsidian moves cost nothing where the graph holds them;
* else a new one, NUL-terminated and 4-byte aligned, in the zero gap
  after the graph's ``node`` payload, with that TOC entry's size (+4)
  grown over it.  Nothing moves: every section starts on a 4 KiB
  boundary.  A ``_move`` location keeps its suffix when the graph holds
  the new item's ``_move`` string (§5.2 item 4).

Every target is computed from vanilla: the generated data's
``name_ref`` offsets and ``graphs[].padding_after``, each checked
against the bytes before anything is written.  Each graph's new strings
must fit its gap: :func:`layout` refuses a placement whose distinct new
names cost more (:func:`string_cost` each) than the gap holds, and the
fill (R1.9) reads the same numbers (:class:`Names`).  Only critter-name fields, the gap
and the grown TOC sizes are written: never an exit's or a spot's string,
since exits stay vanilla in v1 (§5.2 item 9).

:func:`write_plan` makes one pass per level file, in place, on a
``{filename: bytearray}`` view such as
:class:`~azurik_mod.patching.xbr_staging.IsoStaging` (the build's first
layer, before packs and mods).  :func:`read_back` decodes every location
of every level file of a final image with the generic node readers
(:mod:`azurik_mod.xbr.nodes`, :func:`~azurik_mod.xbr.toc_scan.parse_toc`),
each section cut at its TOC size, and checks each level's
``filelist.txt`` line; any difference from the plan is listed.
``randomize-full`` (:mod:`azurkit.tools.randomizer.layer`, Step R1.10b) runs
both: the writes as the build's first layer, the read-back on the final
image (Europe's stale ``filelist.txt`` lines repaired by the packer)
before it is written (D35).

Pure stdlib at import (the planner's contract,
``tests/test_import_isolation.py``).  Nothing here prints a game byte.
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field

from azurkit.core import iso

from azurkit.tools.randomizer.ports import listed
from azurkit.core.xbr.nodes import lstr, record_offsets
from azurkit.core.xbr.nodes import TOC_ROW_SIZE, TOC_START, parse_toc

NAME_FIELD = 0x1C
"""A critterGenerator record's (length, ref) critter-name field."""
GENERATOR = "critterGenerator"


class WriteError(ValueError):
    """A placement the writer can't write, or a build whose read-back
    differs from its plan; :attr:`problems` names each one (D35)."""

    def __init__(self, problems: list[str]) -> None:
        shown = "; ".join(problems[:20]) + (f"; ... and {len(problems) - 20} more" if len(problems) > 20 else "")
        super().__init__(shown)
        self.problems = problems


def string_cost(name: str) -> int:
    """The gap bytes a new string takes: its NUL, rounded up to 4."""
    return (len(name) + 4) & ~3


@dataclass
class GraphEdit:
    """What one node graph gets: ``repoint`` (location id -> the template
    it will name), the ``new`` strings (sorted) and their ``used`` bytes,
    against ``budget``, the graph's gap rounded down to 4."""
    file: str
    g: int
    toc_index: int
    budget: int
    repoint: dict[str, str] = field(default_factory=dict)
    new: list[str] = field(default_factory=list)
    used: int = 0

    @property
    def key(self) -> str:
        return f"{self.file}/g{self.g}"


def _locations(db) -> dict[str, dict]:
    return {loc["id"]: loc for doc in db.generated.values() for loc in doc["locations"]}


def graph_of(lid: str) -> str:
    """A location id's node graph key: ``w1/g0/r1717`` -> ``w1/g0``."""
    return lid.rsplit("/", 1)[0]


class Names:
    """The writer's string rules on one database (plan §5.2): each node
    graph's vanilla strings (``have``) and new-string budget, and the name
    a location is repointed to for an item.  :func:`layout` and the fill
    (Step R1.9) both read them."""

    def __init__(self, db) -> None:
        items = {it["name"]: it for it in db.items["item"]}
        self.items = items
        self.base = {name: it.get("base", name) for name, it in items.items()}
        self.move_of = {it["base"]: name for name, it in items.items() if "base" in it}
        self.locations = _locations(db)
        self.graphs = {f"{stem}/g{g['g']}": (stem, g) for stem, doc in db.generated.items() for g in doc["graphs"]}
        self.have: dict[str, set[str]] = {}
        for lid, loc in self.locations.items():
            self.have.setdefault(graph_of(lid), set()).add(loc["template"])

    def budget(self, gkey: str) -> int:
        """A graph's new-string budget: its gap rounded down to 4."""
        return self.graphs[gkey][1]["padding_after"] & ~3

    def target(self, lid: str, item: str) -> str | None:
        """The string location ``lid`` names when it holds ``item``: None
        for its vanilla item (nothing is written); a ``_move`` location
        keeps its suffix when its graph holds that string (§5.2 item 4)."""
        loc = self.locations[lid]
        if self.base[item] == loc["item"]:
            return None
        if loc["template"] != loc["item"] and (mv := self.move_of.get(self.base[item])) in self.have[graph_of(lid)]:
            return mv
        return item


def layout(placement: Mapping[str, str], db) -> dict[str, GraphEdit]:
    """The edit of each node graph ``placement`` changes, by graph key
    (``w1/g0``); :class:`WriteError` names every location id that is no
    pool location (an exit, a spot or any other id), every item
    ``items.toml`` doesn't define, every guardian slot given another item
    (D81) and every graph whose new strings overrun its gap.  Pure: it
    reads the database only."""
    names = Names(db)
    edits: dict[str, GraphEdit] = {}
    problems = []
    for lid, item in sorted(placement.items()):
        loc = names.locations.get(lid)
        if loc is None or not loc["pool"]:
            problems.append(f"{lid}: no pool location (only pool locations are written; never an exit or a spot)")
            continue
        if item not in names.items:
            problems.append(f"{lid}: items.toml defines no {item!r}")
            continue
        name = names.target(lid, item)
        if name is None:
            continue                                   # its vanilla item: nothing to write
        if loc.get("guardian_slot"):
            problems.append(f"{lid}: a guardian slot keeps its vanilla {loc['item']} (D81)")
            continue
        gkey = graph_of(lid)
        if gkey not in names.graphs:
            problems.append(f"{lid}: its graph {gkey} is in no level's generated data")
            continue
        stem, g = names.graphs[gkey]
        edit = edits.setdefault(gkey, GraphEdit(stem, g["g"], g["toc_index"], names.budget(gkey)))
        edit.repoint[lid] = name
    for edit in edits.values():
        edit.new = sorted(set(edit.repoint.values()) - names.have[edit.key])
        edit.used = sum(map(string_cost, edit.new))
        if edit.used > edit.budget:
            problems.append(f"{edit.key}: {len(edit.new)} new strings take {edit.used} B, over its "
                            f"{edit.budget} B gap (the new-string budget, plan §5.2)")
    if problems:
        raise WriteError(problems)
    return edits


@dataclass
class WriteReport:
    """What a write did: per graph its edit (``graphs``) and each written
    file's sha256[:12] (``files``)."""
    graphs: list[GraphEdit]
    files: dict[str, str]


def _level_writes(buf, stem: str, edits: list[GraphEdit], db) -> tuple[list[tuple[int, bytes]], list[str]]:
    """The writes (file offset, bytes) one level file's graph edits make
    on its vanilla bytes ``buf``, and the problems that stop them."""
    locs = _locations(db)
    toc = parse_toc(buf)
    node_entries = [e for e in toc if e.tag == "node"]
    starts = sorted({e.file_offset for e in toc} | {len(buf)})
    problems, writes = [], []
    for edit in edits:
        where = f"{stem}.xbr {edit.key}"
        if edit.g >= len(node_entries) or node_entries[edit.g].index != edit.toc_index:
            problems.append(f"{where}: TOC entry {edit.toc_index} is not node section {edit.g}")
            continue
        entry = node_entries[edit.g]
        lo, end = entry.file_offset, entry.file_offset + entry.size
        gap_end = next(s for s in starts if s > lo)
        at = end + (-end) % 4                          # the first aligned byte of the gap
        if edit.new and (gap_end - at < edit.budget or any(buf[end:gap_end])):
            problems.append(f"{where}: the gap after the section is not vanilla's zero bytes")
        strings = {}
        for lid, loc in sorted(locs.items()):
            if lid.rsplit("/", 1)[0] == edit.key and loc["template"] not in strings:
                s, n = loc["name_ref"]["string"], loc["name_ref"]["length"]
                if bytes(buf[s:s + n + 1]) == loc["template"].encode("ascii") + b"\0":
                    strings[loc["template"]] = s
        for name in edit.new:
            blob = name.encode("ascii").ljust(string_cost(name), b"\0")
            writes.append((at, blob))
            strings[name] = at
            at += len(blob)
        for lid, name in sorted(edit.repoint.items()):
            loc = locs[lid]
            fld = loc["name_ref"]["field"]
            if not lo <= fld - NAME_FIELD < end or lstr(buf, fld - NAME_FIELD) != GENERATOR \
                    or lstr(buf, fld) != loc["template"]:
                problems.append(f"{where}: {lid} is not a vanilla {loc['template']} critterGenerator")
            elif name not in strings:
                problems.append(f"{where}: no vanilla {name!r} string to point {lid} at")
            else:
                writes.append((fld, struct.pack("<Ii", len(name), strings[name] - (fld + 4))))
        if edit.new:
            writes.append((TOC_START + TOC_ROW_SIZE * entry.index + 4, struct.pack("<I", at - lo)))
    return writes, problems


def write_plan(files: MutableMapping[str, bytearray], placement: Mapping[str, str], db) -> WriteReport:
    """Write ``placement`` into ``files`` (``{"<level>.xbr": bytearray}``,
    e.g. an :class:`~azurik_mod.patching.xbr_staging.IsoStaging` of a
    vanilla ISO): one pass per level file records its writes, each
    computed from its vanilla bytes, and they are applied only once every
    file has passed.  :class:`WriteError` names every problem; then no
    file is changed."""
    edits = layout(placement, db)
    by_file: dict[str, list[GraphEdit]] = {}
    for key in sorted(edits):
        by_file.setdefault(edits[key].file, []).append(edits[key])
    planned, problems = {}, []
    for stem, file_edits in sorted(by_file.items()):
        planned[stem], found = _level_writes(files[f"{stem}.xbr"], stem, file_edits, db)
        problems += found
    if problems:
        raise WriteError(problems)
    shas = {}
    for stem, writes in planned.items():
        buf = files[f"{stem}.xbr"]
        for off, data in writes:
            buf[off:off + len(data)] = data
        shas[stem] = hashlib.sha256(buf).hexdigest()[:12]
    return WriteReport([edits[k] for k in sorted(edits)], shas)


def read_back(image, placement: Mapping[str, str], db) -> list[str]:
    """Every difference between ``image`` (an ISO path or an
    :class:`~azurkit.core.iso.Image`) and ``placement``: each location
    of the database decoded from its file in the image (its node section
    cut at the TOC size, the record a critterGenerator, its item that of
    the name it holds) against its planned item, else its vanilla one;
    and each level file's ``filelist.txt`` line against the file's md5
    and size (an image's :meth:`~azurkit.core.iso.Image.md5`: a file it
    wrote with its md5 given isn't hashed again).  Empty when the image
    holds the plan.  One file at a time."""
    from azurkit.tools.randomizer.ports import XisoReader

    base = {it["name"]: it.get("base", it["name"]) for it in db.items["item"]}
    want: dict[str, dict[str, str]] = {}
    for lid, loc in sorted(_locations(db).items()):
        item = placement.get(lid, loc["item"])
        want.setdefault(lid.split("/", 1)[0], {})[lid] = base.get(item, item)
    out = []
    md5 = image.md5 if isinstance(image, iso.Image) else lambda _, data: hashlib.md5(data).hexdigest()
    with XisoReader(image) as r:
        lines = {e.path.lower(): e for e in listed(r.read_file("filelist.txt"))}
        for stem, locs in sorted(want.items()):
            data = r.read_file(path := f"gamedata/{stem}.xbr")
            line = lines.get(f"{stem}.xbr")
            if line is None or (line.md5, line.size) != (md5(path, data), len(data)):
                out.append(f"{stem}.xbr: its filelist.txt line doesn't name its md5 and size")
            node_entries = [e for e in parse_toc(data) if e.tag == "node"]
            sections: dict[int, tuple[memoryview, list]] = {}
            for lid, item in locs.items():
                g, rec = (int(part[1:]) for part in lid.split("/")[1:])
                if g not in sections:
                    e = node_entries[g]
                    s = memoryview(data)[e.file_offset:e.file_offset + e.size]
                    sections[g] = (s, record_offsets(s))
                s, recs = sections[g]
                ro = recs[rec] if rec < len(recs) else None
                name = lstr(s, ro + NAME_FIELD) if ro is not None and lstr(s, ro) == GENERATOR else None
                if base.get(name, name) != item:
                    out.append(f"{lid}: the plan has {item}, the image {name or 'no critter name'}")
    return out
