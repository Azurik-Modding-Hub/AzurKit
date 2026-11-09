"""The Data tab's engine (``azurkit.tools.data``, Step 4.7a): config.xbr's
tables and views by the file's own names (Modkit's Game Data editor's,
D262), read from the vanilla file AzurKit ships, which is both releases'
file byte for byte; and a cell's edit checked into the recipe's ``set``
operation, refused only where the cell's encoding can't hold it (D23,
D45); All files (Step 4.6h): every .xbr of the image and any file's keyed
tables. Pure (the shipped file and the manifests), but a build of a data
edit over a pack's slider and All files' reads (vanilla: the USA image)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter

import pytest

from azurkit import cli, sdk
from azurkit.core import gate
from azurkit.core.xbr import Document
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
    the pickers' entries with their groups and info rows (a critter's and a
    pickup's with its body, which its picture shows); each view's
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
    bodies = {e["name"]: e.get("body") for kind in ("critter", "item") for e in ix["pickers"][kind]}   # their pictures'
    assert (bodies["boulder"], bodies["small_health"], bodies["jellyfish"]) == ("bosses/boulder", "large_health", None)
    assert sum(b is not None for b in bodies.values()) == 106 + 73

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
    a whole number up to a double's range too, but NaN and inf, and an int32 cell (schema.json's int32 rows, among
    them critters_damage's cell for each damage record, by its row even in
    a column named as a record; the sliders' rounding where they write one)
    what int32 can't hold once the game rounds or truncates it (D45), in the
    Data tab and in a mods file's
    operation alike. A text cell takes a text another cell of its table
    holds (pointed at; a list's words in any order), else one that fits its
    unshared string; a number into a text cell, a text past its slot, a
    shared string, a list past the game's word cap and an empty cell of a
    text row given a text none holds are refused, saying why. An empty
    cell takes a number (filled), empty text or the vanilla value puts a
    cell back, and an edit whose string another edit points at is refused.
    A table or ops of the wrong type is refused by name, as the hosts
    answer a refusal (never a TypeError)."""
    tables = data._vanilla_tables()
    drops = tables["critters_critter_data"]
    dropped = next(v for c in range(len(drops.cols)) if isinstance(v := drops.cell(c, drops.row("drop1")).value, str))
    assert {(t, name) for t, s in data.schema()["tables"].items() for name, e in s["cells"].items()
            if e["type"] == "int32"} == set(xbr.INT32)
    assert xbr.int32("critters_damage", "golem", "damageType") is None   # golem is a record and a column's name
    assert data.table("critters_damage")["cols_meta"] is None
    ok = [
        (("settings_foo", "max hp", "Value", "1e300"), 1e300),
        (("settings_foo", "max hp", "Value", -1e300), -1e300),
        (("settings_foo", "max hp", "Value", 10**308), 1e308),
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
        (("settings_foo", "max hp", "Value", 10**309), "max hp / Value: a number (64-bit float)"),
        (("settings_foo", "max hp", "Value", "abc"), "max hp / Value: a number (64-bit float)"),
        (("critters_damage", "barnacle", "hitPoints", "2147483648"),
         "barnacle / hitPoints: a number the game reads as a 32-bit integer (-2147483648 to 2147483647; it truncates"),
        (("critters_damage", "barnacle", "norm_1", "2147483648"),
         "barnacle / norm_1: a number the game reads as a 32-bit integer (-2147483648 to 2147483647; it truncates"),
        (("critters_damage", "golem", "fire_shard", -3e9), "golem / fire_shard: a number the game reads as a 32-bit"),
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
    hp = {"table": "settings_foo", "col": 0, "row": 0, "value": "1"}
    for ask, given, why in [(sdk.data, {"what": "table", "table": []}, "config.xbr has no table []"),
                            (sdk.data, {"what": "index", "ops": 5}, "data: ops is a list of xbr operations"),
                            (sdk.data_edit, {"edit": hp | {"table": []}}, "config.xbr has no table []"),
                            (sdk.data_edit, {"edit": hp, "ops": 5}, "data_edit: ops is a list of xbr operations")]:
        with pytest.raises(ValueError, match=f"^{re.escape(why)}$"):
            ask(given)
    other = next(n for n in engine.cols if n and n != own)
    pointed = _check("critters_engine", other, "body", body)
    assert pointed["op"]["value"] == body and _check("critters_engine", own, "body", body[:-1])["op"]
    with pytest.raises(ValueError, match=f"^{re.escape(own)} / body: its string is one another edit points at"):
        _check("critters_engine", own, "body", body[:-1], pointed["ops"])
    with pytest.raises(ValueError, match=re.escape("xbr op 1 (set): config table settings_foo initial hp/Value: "
                                                   "2.14748e+09 doesn't fit the game's 32-bit integer once rounded")):
        xbr.plan([{"op": "set", "file": data.FILE, "table": "settings_foo", "entity": "initial hp", "prop": "Value",
                   "value": 2147483647.5}], gate.USA, {data.FILE: data.vanilla()})


def test_the_texts_a_cell_cant_take_yet_are_named_with_what_they_need_as_its_editor_greys_them():
    """D1171's census row G38 (Modkit's greyed values, Step 2.100): asked
    with texts, the Data tab's edit names each the cell can't take yet. The
    magic A spell's empty Damage takes a code another magic cell holds
    (fire) and not one none holds (kill: a new string); earth_armor_2's
    Strong vs takes fire and stem, the ice armors' "stem fire" in another
    order, but not fire alone; the word the game reads an empty cell as
    (attacks_transitions' button "any") needs a clear edit where the game
    data fills the cell; a cell that isn't there is refused by name, as
    its edit is, and so are texts that aren't a list of texts."""
    def needs(table, entity, prop, texts):
        c, r = _at(table, entity, prop)
        return sdk.data_edit({"edit": {"table": table, "col": c, "row": r}, "texts": texts})["needs"]
    assert needs("magic", "A", "Damage", ["fire", "kill"]) == {"kill": data.NEEDS_STRING}
    assert needs("armor_properties", "earth_armor_2", "Strong vs", ["fire stem", "fire"]) == {"fire": data.NEEDS_STRING}
    assert needs("attacks_transitions", "a", "button", ["any", ""]) == {"any": data.NEEDS_CLEAR}
    for edit, texts, why in [({"table": "magic", "col": 999, "row": 0}, ["fire"],
                              "config table magic has no cell at column 999, row 0"),
                             ({"table": "magic", "col": 0, "row": 0}, "fire", "texts is a list of a cell's texts")]:
        with pytest.raises(ValueError, match=f"^{re.escape(why)}$"):
            sdk.data_edit({"edit": edit, "texts": texts})


def test_a_cell_a_ticked_packs_slider_writes_is_marked_and_the_data_edit_wins(usa_iso, capsys):
    """sdk.data marks ⚠ (``written``) each cell a ticked pack's slider also
    writes, as a build plans it (Starting HP's settings_foo initial hp, in
    the Player view and in the grid), and nothing a pack left unticked or
    its slider at its default leaves alone; the cell's data edit
    (sdk.data_edit) builds last: the build names the D28 conflict and its
    config.xbr holds the edit's value, the file the data layer alone makes.
    ``azurkit data`` prints the grid's cells by name."""
    packs = {"player_max_hp": {"starting_hp": 300}}

    def initial_hp(given: dict) -> dict:
        return next(c for c in _cells(sdk.data({"what": "view", "kind": "player"} | given))
                    if c.get("ref", [None])[0] == "settings_foo" and c.get("name") == "initial hp")
    hp = initial_hp({"packs": packs})
    assert hp["written"] is True and "written" not in initial_hp({}) and "written" not in initial_hp(
        {"packs": {"player_physics": {}}})
    _, col, row = hp["ref"]
    grid = sdk.data({"what": "table", "table": "settings_foo", "packs": packs})
    assert [col, row] in grid["written"] and sdk.data({"what": "table", "table": "settings_foo"})["written"] == []
    walk = sdk.data({"what": "table", "table": "critters_critter_data", "packs": {"player_physics": {}}})
    assert walk["written"] == []   # a multiplier at its default writes nothing
    edit = sdk.data_edit({"edit": {"table": "settings_foo", "col": col, "row": row, "value": "500"}, "ops": []})
    assert edit["ops"] == [edit["op"]] and initial_hp({"packs": packs, "ops": edit["ops"]})["vanilla"] == "200"
    made, report = sdk.image({"iso": str(usa_iso), "packs": packs, "xbr": edit["ops"]})
    [conflict] = [c for c in report["conflicts"] if c.startswith(data.FILE)]
    assert "data" in conflict and "pack player_max_hp" in conflict, conflict
    alone = data._state(edit["ops"]).data
    assert report["result"][data.FILE] == hashlib.sha256(alone).hexdigest()
    assert Document(alone).tables["settings_foo"].cell(col, row).value == 500
    assert cli.main(["data", "settings_foo", "initial hp"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"{prop or '(no name)'}: {'(empty)' if grid['cells'][col][r] is None else json.dumps(grid['cells'][col][r])}"
        for r, prop in enumerate(grid["rows"][1:], 1)]


def test_a_mods_files_edits_preview_against_vanilla_on_the_command_line_and_in_the_data_tabs_changes(tmp_path, capsys):
    """Step 4.6i (P23, Modkit's ``diff``): before a build, ``sdk.mods_diff``
    gives each edit of a mods file (Modkit's or AzurKit's) as a build makes
    it of the vanilla config.xbr: a cell by the file's names with its
    vanilla and new values, an edit that changes nothing, a byte edit of a
    level left to the build, and one a build refuses, by name, beside the
    rest. ``azurkit diff`` prints them numbered and exits 1 for a refused
    one. The Data tab's Changes view lists each changed cell table by table,
    its vanilla value beside it, then the byte edits; nothing without
    edits."""
    tables = Document(data.vanilla()).tables
    damage, delay = (views.format_value(tables["damage"].find("catalisk", p).value) for p in ("Damage", "Delay"))
    mod = {"name": "My Mod", "description": "what it does",
           "patches": [{"section": "damage", "entity": "norm_1", "property": "Name", "value": 0.5}],
           "sections": {"damage": {"enemies": {"catalisk": {"Damage": 20.0, "Delay": float(delay)}}}},
           "xbr_edits": [{"op": "replace_bytes", "xbr_file": "a1.xbr", "offset": 2048, "value": "aabb",
                          "value_kind": "hex", "original": "0000"}]}
    found = sdk.mods_diff({"text": json.dumps(mod)})
    assert found == {"name": "My Mod", "description": "what it does", "edits": [
        {"edit": "patches[0] damage/norm_1/Name",
         "refused": "config table damage norm_1/Name is a string cell, not a number"},
        {"edit": "sections damage/catalisk/Damage", "what": "damage/catalisk/Damage", "vanilla": damage, "value": "20",
         "changed": True},
        {"edit": "sections damage/catalisk/Delay", "what": "damage/catalisk/Delay", "vanilla": delay, "value": delay,
         "changed": False},
        {"edit": "xbr_edits[0] (replace_bytes on a1.xbr)", "what": "replace_bytes gamedata/a1.xbr 0x800",
         "checked": False, "changed": True}]}
    path = tmp_path / "mod.json"
    path.write_text(json.dumps(mod), encoding="utf-8")
    assert cli.main(["diff", str(path)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        f"{path}: My Mod", "  what it does",
        "  [1] ERROR patches[0] damage/norm_1/Name: config table damage norm_1/Name is a string cell, not a number",
        f"  [2] ~ damage/catalisk/Damage: {damage} -> 20", f"  [3] = damage/catalisk/Delay: {delay} -> {delay}",
        "  [4] ? replace_bytes gamedata/a1.xbr 0x800: a build checks it, on your image",
        "2 changed, 1 errors, 1 unchanged"]
    ops = sdk.read_mods(json.dumps({k: v for k, v in mod.items() if k != "patches"}))["xbr"]
    assert [e["edit"] for e in sdk.mods_diff({"text": sdk.mods_file({"recipe": {"xbr": ops}})["text"]})["edits"]] == [
        "xbr op 1", "xbr op 2", "xbr op 3"]
    shown = sdk.data({"what": "view", "kind": "changes", "ops": ops})
    assert shown["kind"] == "changes" and shown["name"] is None
    cells, raw = shown["sections"]
    assert cells["title"] == "Damage types (all sources) (damage)" and raw["title"].startswith("Byte edits from a mods file")
    [(label, (vanilla, cell))] = cells["blocks"][0]["rows"]
    assert (label, vanilla, cell["text"], cell["vanilla"], cell["ref"][0]) == (
        "catalisk / Damage", {"read": damage}, "20", damage, "damage")
    assert raw["blocks"][0]["rows"] == [["gamedata/a1.xbr 0x800", [{"read": "2 B"}]]]
    assert sdk.data({"what": "view", "kind": "changes"})["sections"] == []


def test_a_mod_template_holds_each_number_cells_vanilla_value_and_reads_back_changing_nothing(tmp_path, capsys):
    """Step 4.6i (P22, Modkit's ``mod-template``): ``sdk.mod_template``
    and ``azurkit mod-template`` make Modkit's mod file of the vanilla value
    of every number cell of the named tables (a repeated entity's last
    column, the one its name edits), by config.xbr's own names, which reads
    back (``azurkit diff``, a build's ``--mods``) as edits that change
    nothing. With ``--entity`` a table without it is left out, saying so; an
    entity none has, or a table config.xbr hasn't, is refused by name and
    nothing written."""
    tables = Document(data.vanilla()).tables
    made = sdk.mod_template({"tables": ["critters_flocking", "settings_foo"], "name": "mine"})
    mod = json.loads(made["text"])
    assert (mod["name"], list(mod["_keyed_patches"])) == ("mine", ["critters_flocking", "settings_foo"])
    held = [(t, e, p, v) for t, rows in mod["_keyed_patches"].items() for e, props in rows.items()
            for p, v in props.items()]
    assert len(held) == made["cells"] and all(tables[t].find(e, p).value == v for t, e, p, v in held)
    assert len(held) == sum(1 for t in ("critters_flocking", "settings_foo") for c, e in enumerate(tables[t].cols)
                            if tables[t].column(e) == c for r in range(len(tables[t].rows))
                            if tables[t].cell(c, r).kind == 1)
    path = tmp_path / "template.json"
    path.write_text(made["text"], encoding="utf-8")
    assert cli.main(["diff", str(path)]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == f"0 changed, 0 errors, {len(held)} unchanged"
    one, none = tmp_path / "catalisk.json", tmp_path / "none.json"
    assert cli.main(["mod-template", "damage", "settings_foo", "--entity", "catalisk", "--out", str(one)]) == 0
    assert "settings_foo has no number cell of 'catalisk': left out" in capsys.readouterr().err
    assert list(json.loads(one.read_text(encoding="utf-8"))["_keyed_patches"]) == ["damage"]
    assert cli.main(["mod-template", "damage", "--entity", "nope", "--out", str(none)]) == 1 and not none.exists()
    assert capsys.readouterr().err == "azurkit: no number cell of entity 'nope' in damage\n"
    with pytest.raises(ValueError, match="^config.xbr has no table 'nope'"):
        sdk.mod_template({"tables": ["nope"]})


def test_entity_diff_sets_two_entities_cells_side_by_side_table_by_table_and_names_one_no_table_holds(capsys):
    """Step 4.6i (P59, Modkit's ``entity diff``): ``sdk.entity_diff`` joins
    two entities' cells by property in each table that holds either:
    garret4 and air_elemental differ in dozens, their hit points among them,
    and only air_elemental is in critters_damage_fx and critters_flocking;
    ``all`` adds what they hold alike. ``azurkit entity diff`` prints them
    by table or as JSON; an entity no table holds is refused by name, either
    side (AZ-145)."""
    found = sdk.entity_diff({"a": "garret4", "b": "air_elemental"})
    assert len(found["rows"]) > 50 and {"critters_damage_fx", "critters_flocking"} <= set(found["only_in_b"])
    [hp] = [r for r in found["rows"] if (r["table"], r["property"]) == ("critters_damage", "hitPoints")]
    assert hp["kind"] == "different" and hp["a_type"] == hp["b_type"] == "number" and hp["a_value"] != hp["b_value"]
    same = sdk.entity_diff({"a": "garret4", "b": "garret4", "all": True})
    assert same["rows"] and {r["kind"] for r in same["rows"]} == {"equal"}
    assert cli.main(["entity", "diff", "garret4", "air_elemental", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == found
    assert cli.main(["entity", "diff", "garret4", "air_elemental"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("'garret4' vs 'air_elemental': ") and "[critters_damage]" in out
    for a, b in (("garret4", "no_such_entity"), ("no_such_entity", "garret4")):
        assert cli.main(["entity", "diff", a, b]) == 1
        assert capsys.readouterr().err == "azurkit: no config.xbr table has 'no_such_entity' (azurkit data TABLE lists " \
                                          "a table's entities)\n"
def test_all_files_lists_every_xbr_of_the_image_and_only_config_xbr_holds_keyed_tables(usa_iso, capsys):
    """Step 4.6h (Modkit's All files…): sdk.data lists every .xbr of the
    image, config.xbr first, then by path (index/index.xbr among them), and
    each file's keyed tables, read from the image no further than its TOC:
    config.xbr's 18 by its own names (its shipped file's, so no image), none
    in any other vanilla file (Modkit's AZ-124). A file's ask without the
    image, a table a file hasn't and a file the image hasn't are refused by
    name; ``azurkit data --files`` and ``--file`` print the same."""
    image = {"iso": str(usa_iso)}
    listed = sdk.data({"what": "files"} | image)
    paths = [f["file"] for f in listed["files"]]
    xbrs = [p for p in gate.USA.files if p.endswith(".xbr")]
    assert listed["release"] == "usa" and paths == [data.FILE, *sorted(set(xbrs) - {data.FILE}, key=str.lower)]
    assert len(paths) == 42 and "gamedata/index/index.xbr" in paths
    held = {p: [t["name"] for t in sdk.data({"what": "tables", "file": p} | image)["tables"]] for p in paths}
    assert held[data.FILE] == [t["name"] for t in sdk.data({"what": "tables"})["tables"]] == list(
        Document(data.vanilla()).tables) and [p for p in paths if held[p]] == [data.FILE]
    for given, why in [({"what": "files"}, "data: All files needs your image: pick it first (iso, its path)"),
                       ({"what": "tables", "file": "gamedata/a1.xbr"},
                        "data: gamedata/a1.xbr needs your image: pick it first (iso, its path)"),
                       ({"what": "table", "file": "gamedata/a1.xbr", "table": "x"} | image,
                        "gamedata/a1.xbr has no keyed table 'x'"),
                       ({"what": "tables", "file": "gamedata/nope.xbr"} | image,
                        "data: the USA image has no gamedata/nope.xbr")]:
        with pytest.raises(ValueError, match=f"^{re.escape(why)}$"):
            sdk.data(given)
    assert cli.main(["data", "--files", "--iso", str(usa_iso)]) == 0
    assert capsys.readouterr().out.splitlines() == [f"{len(held[p]):>3} keyed tables  {p}" for p in paths]
    assert cli.main(["data", "--file", "gamedata/index/index.xbr", "--iso", str(usa_iso)]) == 0
    assert capsys.readouterr().out == "(no keyed tables)\n"


def test_data_diff_and_entity_diff_read_any_images_config_xbr_or_a_loose_file_read_only(tmp_path, capsys):
    """Step 4.24a (Modkit's ``list`` and ``dump --input`` or ``--iso`` on a built image, ``diff --input`` and
    ``entity diff --config``): ``azurkit data`` reads a cell as a built image's config.xbr (``--iso``, never gated)
    or a loose file (``--input``) holds it, ``--files`` lists that image's .xbr files; ``diff`` previews a mods
    file against it (an edit it already holds changes nothing) and ``entity diff`` compares its entities; none of
    them writes the image. A file that isn't an XBR and flags that don't go together are refused by name."""
    from azurkit.core.xbr import document as xbrdoc
    from tests._xiso import image

    op = {"op": "set", "file": data.FILE, "table": "damage", "entity": "octo", "prop": "Damage", "value": 12}
    built, loose, odd = data._state([op]).data, tmp_path / "config.xbr", tmp_path / "odd.xbr"
    made = tmp_path / "built.iso"
    made.write_bytes(image({data.FILE: built, "gamedata/index/index.xbr": xbrdoc.HEADER.pack(b"xobx", *[0] * 14),
                            "default.xbe": b"x"}))
    loose.write_bytes(built)
    odd.write_bytes(b"not an archive")
    held = hashlib.sha256(made.read_bytes()).hexdigest()
    assert cli.main(["data", "damage", "octo"]) == 0
    vanilla = capsys.readouterr().out.splitlines()
    for source in (["--iso", str(made)], ["--input", str(loose)]):
        assert cli.main(["data", "damage", "octo", *source]) == 0
        assert capsys.readouterr().out.splitlines() == ["Damage: 12.0" if line.startswith("Damage: ") else line
                                                        for line in vanilla] != vanilla
    assert cli.main(["data", "--files", "--iso", str(made)]) == 0
    assert capsys.readouterr().out.splitlines() == [f" 18 keyed tables  {data.FILE}",
                                                    "  0 keyed tables  gamedata/index/index.xbr"]
    mod = tmp_path / "mod.json"
    mod.write_text(json.dumps({"_keyed_patches": {"damage": {"octo": {"Damage": 12}}}}), encoding="utf-8")
    for source, tally in (([], "1 changed"), (["--iso", str(made)], "0 changed"), (["--input", str(loose)], "0 changed")):
        assert cli.main(["diff", str(mod), *source]) == 0
        assert capsys.readouterr().out.splitlines()[-1].startswith(f"{tally}, 0 errors")
    for source in (["--config", str(loose)], ["--iso", str(made)]):
        assert cli.main(["entity", "diff", "octo", "catalisk", "--json", *source]) == 0
        [damage] = [r for r in json.loads(capsys.readouterr().out)["rows"] if (r["table"], r["property"]) == (
            "damage", "Damage")]
        assert damage["a_value"] == 12
    assert hashlib.sha256(made.read_bytes()).hexdigest() == held
    for argv, why in ((["data", "--input", str(odd)], f"--input {odd}: not an XBR file (no xobx header)"),
                      (["entity", "diff", "octo", "catalisk", "--config", str(odd)],
                       f"--config {odd}: not an XBR file (no xobx header)"),
                      (["data", "--input", str(loose), "--file", "gamedata/a1.xbr"],
                       "data: --input reads one .xbr file: give no --iso, --files or --file"),
                      (["data", "--file", "gamedata/a1.xbr"], "data: --file gamedata/a1.xbr is an image's: give --iso"),
                      (["data", "--iso", str(made), "--file", "gamedata/a1.xbr"], f"{made} has no gamedata/a1.xbr")):
        assert cli.main(argv) == 1
        assert capsys.readouterr().err == f"azurkit: {why}\n"


def test_another_files_keyed_table_reads_and_edits_as_config_xbrs_without_its_notes_rules_or_marks():
    """A keyed table of any file (Step 4.6h; config.xbr's bytes stand in
    for another file's, as no other vanilla file holds one) shows as a grid
    and edits into a ``set`` operation naming that file, which plans on it
    and marks its table changed; config.xbr's schema notes, int32 rules
    (its armor Level takes 3e9 there) and pack spans don't reach it, and
    config.xbr's own tables stay unedited."""
    other, base = "gamedata/index/index.xbr", data.vanilla()
    c, r = _at("armor_properties", "earth_armor_1", "Level")
    span = [(data._vanilla_tables()["armor_properties"].cell(c, r).at, 16)]
    grid = data.table("armor_properties", written=span, file=other, base=base)
    config = data.table("armor_properties")
    assert (grid["file"], grid["label"], grid["category"], grid["written"], grid["cols_meta"]) == (
        other, "armor_properties", "", [], None) and set(map(type, grid["rows_meta"])) == {type(None)}
    assert (grid["rows"], grid["cols"], grid["cells"]) == (config["rows"], config["cols"], config["cells"])
    made = data.check({"file": other, "table": "armor_properties", "col": c, "row": r, "value": "3e9"}, base=base)
    assert made["op"] == {"op": "set", "file": other, "table": "armor_properties", "entity": "earth_armor_1",
                          "prop": "Level", "value": 3e9} and made["ops"] == [made["op"]]
    with pytest.raises(ValueError, match="^earth_armor_1 / Level: a number the game reads as a 32-bit integer"):
        _check("armor_properties", "earth_armor_1", "Level", "3e9")
    assert xbr.plan(made["ops"], gate.USA, {other: base}).changes
    assert data.table("armor_properties", made["ops"], file=other, base=base)["changed"] == [[c, r, "1"]]
    assert {t["name"]: t["changed"] for t in data.tables(made["ops"], other, base)["tables"]}["armor_properties"]
    assert data.index(made["ops"])["edits"] == 0 and data.table("armor_properties", made["ops"])["changed"] == []
