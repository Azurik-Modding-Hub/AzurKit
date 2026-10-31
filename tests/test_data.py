"""The Data tab's engine (``azurkit.tools.data``, Step 4.7a): config.xbr's
tables and views by the file's own names (Modkit's Game Data editor's,
D262), read from the vanilla file AzurKit ships, which is both releases'
file byte for byte; and a cell's edit checked into the recipe's ``set``
operation, refused only where the cell's encoding can't hold it (D23,
D45). Pure: the shipped file and the manifests, no image."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

import pytest

from azurkit.core import gate
from azurkit.edits import xbr
from azurkit.tools import data
from azurkit.tools.data import views


def test_the_shipped_config_xbr_is_both_releases_vanilla_file():
    """``tools/data/config.xbr`` has the size and sha256 both releases'
    manifests give gamedata/config.xbr."""
    raw = data.vanilla()
    assert [len(raw), hashlib.sha256(raw).hexdigest()] == gate.USA.files[data.FILE] == gate.EUROPE.files[data.FILE]


def _cells(view: dict) -> list[dict]:
    return [c for s in view["sections"] for b in s["blocks"] for _, cells in b["rows"] for c in cells if c]


def test_the_data_tabs_views_show_modkits_cells_by_config_xbrs_own_names():
    """The index lists the 18 tables by Modkit's categories and labels and
    the pickers' entries with their groups and info rows; each view's
    sections are Modkit's (Settings first, a critter's Attack after its
    stats, an armor family's levels as columns), each cell a ref into its
    table with its schema note, int32 rule and editor; an operation shows
    in its cell with the vanilla value beside it, a ticked pack's span marks
    the cells it writes, and a grid lists its changed cells."""
    ix = data.index()
    assert [(t["category"], t["name"], t["label"]) for t in ix["tables"]] == [
        (category, name, label) for category, named in views.CATEGORIES.items() for name, label in named.items()]
    assert len(ix["tables"]) == 18 and ix["edits"] == 0
    assert {k: len(v) for k, v in ix["pickers"].items()} == {"critter": 110, "item": 73, "armor": 7, "weapon": 10}
    assert ix["pickers"]["armor"][0]["name"] == "no_armor" and {e["group"] for e in ix["pickers"]["item"]} == {
        "gems", "fragments", "keys", "fuels", "health", "powers"}
    assert dict(next(e for e in ix["pickers"]["weapon"] if e["name"] == "none")["info"])["Elements"] == "none"

    player = data.view("player")
    assert [s["title"] for s in player["sections"][:6]] == [
        "Settings", "Spells (magic)", "Attacks (attack animations)", "Damage the player deals", "Armor",
        "Hazards (no spell or critter)"]
    hp = next(c for c in _cells(player) if c.get("ref", [None])[0] == "settings_foo" and c.get("name") == "initial hp")
    assert hp["kind"] == "number" and hp["int32"] == "round" and hp["type"] == "int32" and "vanilla" not in hp
    critter = data.view("critter", "air_elemental")
    titles = [s["title"] for s in critter["sections"]]
    assert titles.index("Attack") == titles.index("Stats (speed, range, drops)") + 1
    attack = next(s for s in critter["sections"] if s["title"] == "Attack")["blocks"][0]
    assert attack["rows"][0][0] == "damageType" and attack["rows"][-1][0] == "Used by" and "read" in attack["rows"][-1][1][0]
    armor = data.view("armor", "earth_armor")["sections"][0]["blocks"][0]
    assert armor["columns"] == ["1", "2", "3"] and [label for label, _ in armor["rows"]][:2] == ["Type", "Level"]
    strong = next(cells for label, cells in armor["rows"] if label == "Strong vs")[0]
    assert strong["choices"]["kind"] == "words" and strong["max_words"] == 2
    with pytest.raises(ValueError, match="^the Data tab has no critter 'nobody'$"):
        data.view("critter", "nobody")

    op = {"op": "set", "file": data.FILE, "table": "settings_foo", "entity": "initial hp", "prop": "Value",
          "value": 500}
    at = hp["ref"]
    cell = data._vanilla_tables()["settings_foo"].cell(at[1], at[2])
    edited = next(c for c in _cells(data.view("player", ops=[op], written=[(cell.at + 8, 8)]))
                  if c.get("ref") == at)
    assert edited["value"] == 500 and edited["vanilla"] == hp["text"] and edited["written"] is True
    grid = data.table("settings_foo", ops=[op])
    assert grid["changed"] == [[at[1], at[2], hp["text"]]] and grid["cols_meta"][at[1]]["int32"] == "round"
    assert next(t for t in data.index(ops=[op])["tables"] if t["name"] == "settings_foo")["changed"] is True
    damage = data.table("critters_damage")
    assert (len(damage["rows"]), len(damage["cols"])) == (62, 107) and len(damage["cells"][0]) == 62


def _at(table: str, entity: str, prop: str, col: int | None = None) -> tuple[int, int]:
    t = data._vanilla_tables()[table]
    return t.column(entity, col), t.row(prop)


def _check(table: str, entity: str, prop: str, value, ops=(), col: int | None = None) -> dict:
    c, r = _at(table, entity, prop, col)
    return data.check({"table": table, "col": c, "row": r, "value": value}, ops)


def test_an_edit_is_refused_only_where_the_cells_encoding_cant_hold_it():
    """A number cell takes any finite value, far past its range hint (D23),
    but NaN and inf, and an int32 cell (schema.json's int32 rows, the
    sliders' rounding where they write one) what int32 can't hold once the
    game rounds or truncates it (D45), in the Data tab and in a mods file's
    operation alike. A text cell takes a text another cell of its table
    holds (pointed at; a list's words in any order), else one that fits its
    unshared string; a number into a text cell, a text past its slot, a
    shared string, a list past the game's word cap and an empty cell of a
    text row given a text none holds are refused, saying why. An empty
    cell takes a number (filled), empty text or the vanilla value puts a
    cell back, and an edit whose string another edit points at is refused."""
    tables = data._vanilla_tables()
    drops = tables["critters_critter_data"]
    dropped = next(v for c in range(len(drops.cols)) if isinstance(v := drops.cell(c, drops.row("drop1")).value, str))
    assert {(t, name) for t, s in data.schema()["tables"].items() for name, e in s["cells"].items()
            if e["type"] == "int32"} == set(xbr.INT32)
    ok = [
        (("settings_foo", "max hp", "Value", "1e300"), 1e300),
        (("settings_foo", "max hp", "Value", -1e300), -1e300),
        (("critters_damage", "barnacle", "hitPoints", "2147483647.9"), 2147483647.9),
        (("critters_damage", "barnacle", "hitPoints", "-2147483648.9"), -2147483648.9),
        (("settings_foo", "initial hp", "Value", "2147483647.4"), 2147483647.4),
        (("attacks_anims", "sweep1", "Damage multiplier", "2"), 2.0),
        (("critters_critter_data", "air_elemental", "drop5", dropped), dropped),
    ]
    for (table, entity, prop, value), want in ok:
        made = _check(table, entity, prop, value)
        assert made["op"]["value"] == want and made["ops"] == [made["op"]], (entity, prop, value)
        assert made["op"].get("fill", False) is (tables[table].find(entity, prop).kind == 0)
        assert xbr.plan(made["ops"], gate.USA, {data.FILE: data.vanilla()}).changes
    armor = tables["armor_properties"]
    strong = armor.find("earth_armor_1", "Strong vs").value
    two = next(v for c in range(len(armor.cols)) if len(str(v := armor.find(armor.cols[c], "Strong vs").value).split()) == 2)
    assert _check("armor_properties", "earth_armor_1", "Strong vs", " ".join(reversed(two.split())))["op"]["value"] == two
    flock = tables["critters_flocking"]
    first_col = flock.cols.index("good_noreht")
    row = next(r for r in range(1, len(flock.rows)) if flock.cell(first_col, r).kind == 1)
    twice = data.check({"table": "critters_flocking", "col": first_col, "row": row, "value": "3"})
    assert (twice["op"]["entity"], twice["op"]["col"]) == ("good_noreht", first_col) != (
        "good_noreht", flock.column("good_noreht"))
    first = _check("settings_foo", "max hp", "Value", "7")
    assert _check("settings_foo", "max hp", "Value", "", first["ops"]) == {"op": None, "ops": []}
    vanilla_max = views.format_value(tables["settings_foo"].find("max hp", "Value").value)
    assert _check("settings_foo", "max hp", "Value", vanilla_max, first["ops"]) == {"op": None, "ops": []}

    engine = tables["critters_engine"]
    refs = Counter(at for _field, at in engine.refs())
    own = next(n for c, n in enumerate(engine.cols) if refs[engine.cell(c, engine.row("body")).text_at] == 1)
    ai, body = engine.find(own, "ai").value, engine.find(own, "body").value
    refused = [
        (("settings_foo", "max hp", "Value", "nan"), "max hp / Value: a number (64-bit float)"),
        (("settings_foo", "max hp", "Value", math.inf), "max hp / Value: a number (64-bit float)"),
        (("settings_foo", "max hp", "Value", "abc"), "max hp / Value: a number (64-bit float)"),
        (("critters_damage", "barnacle", "hitPoints", "2147483648"),
         "barnacle / hitPoints: a number the game reads as a 32-bit integer (-2147483648 to 2147483647; it truncates"),
        (("settings_foo", "initial hp", "Value", "2147483647.5"),
         "initial hp / Value: a number the game reads as a 32-bit integer (-2147483648 to 2147483647; it rounds"),
        (("critters_engine", own, "body", 5), f"{own} / body holds text, not a number"),
        (("critters_engine", own, "body", body + "x" * 200), f"{own} / body: text, at most"),
        (("critters_engine", own, "ai", ai + "x"), f"{own} / ai: this text is shared with"),
        (("critters_engine", own, "body", "é"), f"{own} / body: text, e.g."),
        (("armor_properties", "earth_armor_1", "Strong vs", f"{strong} {strong} {strong}"),
         "earth_armor_1 / Strong vs: at most 2 words"),
        (("critters_critter_data", "air_elemental", "drop5", "12"),
         "air_elemental / drop5 is empty: it takes a text another cell of this table holds, and none holds '12'"),
    ]
    for (table, entity, prop, value), why in refused:
        with pytest.raises(ValueError, match=f"^{re.escape(why)}"):
            _check(table, entity, prop, value)
    other = next(n for n in engine.cols if n and n != own)
    pointed = _check("critters_engine", other, "body", body)
    assert pointed["op"]["value"] == body and _check("critters_engine", own, "body", body[:-1])["op"]
    with pytest.raises(ValueError, match=f"^{re.escape(own)} / body: its string is one another edit points at"):
        _check("critters_engine", own, "body", body[:-1], pointed["ops"])
    with pytest.raises(ValueError, match=re.escape("xbr op 1 (set): config table settings_foo initial hp/Value: "
                                                   "2.14748e+09 doesn't fit the game's 32-bit integer once rounded")):
        xbr.plan([{"op": "set", "file": data.FILE, "table": "settings_foo", "entity": "initial hp", "prop": "Value",
                   "value": 2147483647.5}], gate.USA, {data.FILE: data.vanilla()})
