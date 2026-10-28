"""enemy_damage: how much damage enemies take, by what a hit is to them
(D712): three multipliers over config.xbr's ``critters_damage``; no XBE
byte.

A cell there is the HP a critter loses to one damage record: empty means
the record's own ``Damage`` (the ``damage`` table), 0 immune, below 0 a
heal. The critter loader truncates each to an int32 (AZ-513), and the hit
deals it times the move's multiplier, rounded up.

**The cells.** Every enemy's (each column but those whose
``critters_engine`` ``ai`` is ``player`` or ``town``: the player and the
townspeople, immune to everything) for the 33 records the player deals
(:data:`RECORDS`: the plain staff, the nine spells at levels 1 to 3 and
the electro shield). A cell's class is the game's own reading where it has
one (the hit's rumble: above the record's ``Damage`` a weakness):

- **weakness**, above the record's ``Damage``: the cell x k;
- **neutral**, empty, or from 1 to the record's ``Damage`` (a resistance
  is scaled as neutral, D115): the cell x k, an empty one the record's
  ``Damage`` x k;
- **immune**, 0: the record's ``Damage`` x k;
- a vanilla heal (below 0) stays as it is.

Each value is truncated as the loader truncates it, and one no int32 holds
fails the build, naming its cell (D45). A negative k heals. The classes are
read from the vanilla tables (``Pack.files`` are checked against the
release's manifest, D27). The defaults (neutral and weakness 1.0, immune
0.0, the multiplier that keeps vanilla's 0) write nothing.

Ported from Modkit's ``azurik_mod/patches/enemy_damage`` at the packs
oracle's tag, whose docstring holds the evidence.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from azurkit.core.xbr.keyed import EMPTY, NUMBER, Table
from azurkit.tools.mods.engine import Pack, XbrParametricEdit

RECORDS = tuple(f"{kind}_{level}"
                for kind in ("norm", "water", "fire", "wind", "acid", "steam", "lightning", "smash", "ice",
                             "elemental", "shield_lightning")
                for level in (1, 2, 3))
NOT_ENEMIES = ("player", "town")   # the critters_engine ai values whose columns stay vanilla


def classes(tables: Mapping[str, Table]) -> dict[str, list[tuple[str, int, str, float]]]:
    """Every enemy cell of ``critters_damage`` for :data:`RECORDS`, by
    class, each ``(critter, column, record, base)``: the HP the slider
    multiplies."""
    hurt, engine, damage = tables["critters_damage"], tables["critters_engine"], tables["damage"]
    dealt = {}
    for record in RECORDS:
        if (cell := damage.find(record, "Damage")).kind != NUMBER:
            raise ValueError(f"config table damage {record}/Damage is not a number")
        dealt[record] = math.trunc(cell.value)
    rows = {record: hurt.row(record) for record in RECORDS}
    out: dict[str, list[tuple[str, int, str, float]]] = {"weakness": [], "neutral": [], "immune": []}
    for col, critter in enumerate(hurt.cols):
        if critter in engine.cols and engine.find(critter, "ai").value in NOT_ENEMIES:
            continue
        for record, row in rows.items():
            cell = hurt.cell(col, row)
            if cell.kind == EMPTY:
                out["neutral"].append((critter, col, record, float(dealt[record])))
                continue
            if cell.kind != NUMBER:
                raise ValueError(f"config table critters_damage {critter}/{record} is not a number")
            held = math.trunc(cell.value)   # what the loader keeps
            if held > dealt[record]:
                out["weakness"].append((critter, col, record, float(held)))
            elif held > 0:
                out["neutral"].append((critter, col, record, float(held)))
            elif held == 0:
                out["immune"].append((critter, col, record, float(dealt[record])))
    return out


def _slider(name: str, label: str, default: float, unit: str, description: str) -> XbrParametricEdit:
    return XbrParametricEdit(
        name=f"enemy_damage_{name}", label=label, table="critters_damage", entity="enemies", prop=name,
        default=default, slider_min=-2.0, slider_max=4.0, slider_step=0.05, unit=unit, int32="trunc",
        description=description, cells=lambda tables: classes(tables)[name])


PACK = Pack(
    name="enemy_damage",
    description="Damage enemies take: neutral hits, their weakness and what they're immune to.",
    sites=(_slider("neutral", "Neutral hits", 1.0, "x",
                   "Damage enemies take from hits they're neither weak nor immune to; below 0 heals."),
           _slider("weakness", "Their weakness", 1.0, "x",
                   "Damage enemies take from their weakness; below 0 heals."),
           _slider("immune", "What they're immune to", 0.0, "x normal hit",
                   "Damage enemies take from what they're immune to, x a normal hit; below 0 heals.")),
    category="enemies")
