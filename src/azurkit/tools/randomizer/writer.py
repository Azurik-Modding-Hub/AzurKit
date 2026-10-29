"""The writer's string rules, which the fill reads (Step 4.2a): Modkit's
``azurik_mod/randomizer/writer.py`` up to :func:`layout`, as it is. The
writes into the level files and the read-back of a build come with the
generator layer (Step 4.2b).

A placement maps pool location ids (``<file>/g<G>/r<R>``, the generated
data's) to ``items.toml`` names. The writer never renames a string: it
repoints each changed location's critter-name field at a string in the
same node graph, an existing one (another location's template string in
that graph) or a new one, NUL-terminated and 4-byte aligned, in the zero
gap after the graph's ``node`` payload. Each graph's new strings must fit
its gap: :func:`layout` refuses a placement whose distinct new names cost
more (:func:`string_cost` each) than the gap holds, and the fill reads the
same numbers (:class:`Names`). Pure: it reads the database only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


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
