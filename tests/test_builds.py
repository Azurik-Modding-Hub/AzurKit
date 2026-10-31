"""A build's recipe and its record (Step 4.1g): the mods file (Q268: packs
and the ``xbr`` operations, ``edits.xbr``), the manifest a build carries in
its root (``/azurkit.json`` and ``/azurkit.bin``, Q66), opening a build back
into its recipe (``sdk.open_build``), and Modkit's G3 packs-family cases and
G4 build cases, file by file, with G3's whole image.

G3's and G4's recipes are Modkit's flags and mod shapes (the goldens'
``cases.json``), translated once into AzurKit's by
``scripts/record_goldens.py``'s ``recipe`` (REORG §12.2: Modkit's shapes
are read only there): its ``patches``, ``_keyed_patches`` and
``xbr_edits`` become ``set`` and ``replace_bytes`` operations, whose
``expected`` is read from the image. ``level_patches`` isn't ported
(AZ-009), so the three cases that move an entity in ``training_room.xbr``
leave that file, ``filelist.txt``, which lists it, and the image out by
name."""

from __future__ import annotations

import hashlib
import re
import struct

import pytest

from azurkit import sdk
from azurkit.core import iso
from azurkit.core.xbr import Document
from azurkit.edits import manifest
from azurkit.tools import mods
from scripts import record_goldens

CONFIG = "gamedata/config.xbr"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cases(path) -> dict[str, tuple[dict, dict, tuple[str, ...]]]:
    """``{case: (its recipe, its golden, the files it leaves out)}`` for G3's
    packs-family cases and G4's build cases (``tests/goldens/``)."""
    out = {}
    for golden in ("pipelines.json", "gui.json"):
        recipes = record_goldens.cases(golden)
        for name, files in record_goldens.recorded(golden).items():
            if golden == "pipelines.json" and record_goldens.wears(recipes[name]):   # tests/test_characters.py's
                continue
            left = record_goldens.LEVEL_PATCHED if golden == "pipelines.json" and record_goldens.level_patched(
                recipes[name]) else ()
            out[name] = (record_goldens.recipe(golden, recipes[name], path), files, left)
    return out


def test_g3_and_g4_cases_build_their_goldens_and_open_back_into_their_recipes(usa_iso):
    """Each of G3's 5 packs-family cases and G4's 3 build cases, as a mods
    file's recipe, changes each file its golden names to its sha256 and no
    other (the level-patched cases less ``training_room.xbr`` and
    ``filelist.txt``). Its image carries /azurkit.json and /azurkit.bin,
    and ``sdk.open_build`` reads it back into its mods file: the release,
    the result, and the recipe it was built from, normalized, which
    ``sdk.read_mods`` takes again. A build with no pack carries no root
    file."""
    cases = _cases(usa_iso)
    assert len(cases) == 8 and sum(bool(left) for _, _, left in cases.values()) == 3
    for name, (recipe, golden, left) in cases.items():
        made, report = sdk.image(recipe | {"iso": str(usa_iso)})
        want = {file: sha for file, sha in golden.items() if file != "ISO"}
        assert {file: report["result"].get(file) for file in want} == want, name
        assert report["result"].keys() - set(left) == want.keys() and report["conflicts"] == [], name
        found = sdk.open_build(made)
        assert (found["base"]["release"], found["result"]) == ("usa", report["result"]), name
        assert sdk.read_mods(found) == {"packs": mods.normalize(recipe["packs"])} | (
            {"xbr": recipe["xbr"]} if recipe.get("xbr") else {}), name
    with iso.Reader(sdk.image({"iso": str(usa_iso), "packs": {}})[0]) as r:
        with pytest.raises(FileNotFoundError):
            r.find(manifest.JSON)


def test_the_whole_image_less_its_root_entries_is_modkits(usa_iso):
    """G3's ``randomize-full:zero-scales`` (the packs on by default and
    player_physics at zero), its changed files packed into the vanilla image
    without the root entries, is Modkit's image byte for byte: the XISO
    layout (PLAN §3.3)."""
    recipe, golden, _ = _cases(usa_iso)["randomize-full:zero-scales"]
    made, report = sdk.image(recipe | {"iso": str(usa_iso)})
    with iso.Reader(made) as r:
        files = {file: r.read(file) for file in report["result"] if file != "filelist.txt"}
    assert iso.read(usa_iso, files).sha256() == golden["ISO"]


def test_a_mods_file_names_each_operation_it_refuses_and_a_drifted_build(usa_iso):
    """The ``xbr`` operations (``edits.xbr``) find a cell by D51's
    spellings (case-blind, ``_`` as a space) and apply in order: a later one
    that rewrites an earlier one's cell wins, and the conflict names both
    (D28). Every operation that isn't one, or can't apply, is named in one
    message, by its number, never by the file's bytes. A share link
    carries ``set`` alone (Q174). ``sdk.open_build`` refuses an image that
    isn't an AzurKit build, one whose file drifted from its manifest, and a
    manifest whose blob isn't its bytes, by name; with ``whole`` false (the
    page's) it checks only the files the build changed."""
    with iso.Reader(usa_iso) as r:
        a1 = r.read("gamedata/a1.xbr")
    golem = {"op": "set", "file": CONFIG, "table": "critters_damage", "entity": "golem", "prop": "hitPoints"}
    ops = [golem | {"value": 321}, golem | {"entity": "GOLEM", "prop": "HITPOINTS", "value": 654.5}]
    made, report = sdk.image({"iso": str(usa_iso), "packs": {}, "xbr": ops})
    with iso.Reader(made) as r:
        assert Document(r.read(CONFIG)).tables["critters_damage"].number("golem", "hitPoints") == 654.5
        a3, flip = r.find("gamedata/a3.xbr"), bytes([r.read("gamedata/a3.xbr")[9] ^ 0xFF])
        config = r.find(CONFIG)
        bend = bytes([r.read(config)[9] ^ 0xFF])
    assert len(report["conflicts"]) == 1 and re.fullmatch(
        rf"{CONFIG} 0x[0-9A-F]+ \(\d B\): data xbr \(#2 set critters_damage/golem/hitPoints\) overwrote data xbr, "
        r"whose group #1 set critters_damage/golem/hitPoints is dropped whole", report["conflicts"][0])
    held = a1[0x800:0x804]
    refused = [{"op": "set", "file": CONFIG, "table": "critters_damage", "entity": "golem", "prop": "x", "value": 1},
               golem | {"value": "text"},
               {"op": "set", "file": CONFIG, "table": "nope", "entity": "golem", "prop": "hitPoints", "value": 1},
               {"op": "replace_bytes", "file": "gamedata/a1.xbr", "offset": 0x800, "value": "00" * 4,
                "expected": {"sha256": _sha256(b"other bytes"), "size": 4}},
               {"op": "replace_bytes", "file": "gamedata/nope.xbr", "offset": 0, "value": "00",
                "expected": "00"}]
    with pytest.raises(ValueError) as caught:
        sdk.image({"iso": str(usa_iso), "packs": {}, "xbr": refused})
    assert str(caught.value) == (
        "xbr op 1 (set): gamedata/config.xbr table critters_damage has no prop 'x'; "
        "xbr op 2 (set): config table critters_damage golem/hitPoints is a number cell, not a string; "
        "xbr op 3 (set): gamedata/config.xbr has no keyed table 'nope'; "
        f"xbr op 4 (replace_bytes): gamedata/a1.xbr holds <4 B, sha256 {_sha256(held)[:12]}> at 0x800, "
        "not the bytes it expects; "
        "xbr op 5 (replace_bytes): the USA image has no gamedata/nope.xbr")
    shapes = [{"op": "rename"}, {"op": "set", "file": CONFIG}, golem | {"value": float("nan"), "x": 1},
              {"op": "replace_bytes", "file": "default.xbe", "offset": -1, "value": "abc", "expected": "ab"},
              {"op": "replace_bytes", "file": "gamedata/a1.xbr", "offset": 0, "value": "00" * 33,
               "expected": "00" * 33}, {"op": ["set"]}]
    with pytest.raises(ValueError) as caught:
        sdk.image({"iso": str(usa_iso), "xbr": shapes})
    assert str(caught.value) == (
        "xbr op 1: not an operation (op: set | replace_bytes); xbr op 2 (set): no table, entity, prop, value; "
        "xbr op 3 (set): no key 'x' (its keys: op, file, table, entity, prop, value); "
        "xbr op 4 (replace_bytes): file 'default.xbe' is no gamedata/<name>.xbr; xbr op 4 (replace_bytes): "
        "offset -1 is not a file offset (a whole number from 0); xbr op 4 (replace_bytes): value is not hex bytes; "
        "xbr op 5 (replace_bytes): expected is not the hex of the 33 B the value replaces (up to 32 B; past that "
        "{sha256, size}); xbr op 6: not an operation (op: set | replace_bytes)")
    assert held.hex() not in str(caught.value)
    with pytest.raises(ValueError, match=r"preset: a manifest's layers is a list of \{tool, kind, recipe\}"):
        sdk.read_mods({"format": manifest.FORMAT, "layers": ["x"]})
    replace = {"op": "replace_bytes", "file": "gamedata/a1.xbr", "offset": 0x800, "value": "deadbeef",
               "expected": {"sha256": _sha256(held), "size": 4}}
    with pytest.raises(ValueError, match=re.escape("a share link carries packs and set only (Q174), not xbr op 2")):
        sdk.preset_encode({"packs": {}, "xbr": [ops[0], replace]})
    assert sdk.preset_decode(sdk.preset_encode({"packs": {}, "xbr": ops}))["layers"][1]["recipe"] == {"ops": ops}
    with pytest.raises(ValueError, match=r"no /azurkit\.json, so it isn't an AzurKit build"):
        sdk.open_build(str(usa_iso))
    drifted = iso.Image(made.source, (*made.writes, (a3.sector * iso.SECTOR + 9, flip)), made.size)
    with pytest.raises(ValueError, match=r"isn't the build its /azurkit\.json records: gamedata/a3\.xbr: its contents "
                                         r"differ$"):
        sdk.open_build(drifted)
    assert sdk.open_build(drifted, whole=False) == sdk.open_build(made)
    changed = iso.Image(made.source, (*made.writes, (config.sector * iso.SECTOR + 9, bend)), made.size)
    with pytest.raises(ValueError, match=r"gamedata/config\.xbr: its contents differ$"):
        sdk.open_build(changed, whole=False)
    built, _ = sdk.image({"iso": str(usa_iso), "packs": {"qol_photo_mode": {}}})
    with iso.Reader(built) as r:
        blob = r.find(manifest.BIN)
        flip = bytes([r.read(blob)[0] ^ 0xFF])
    bent = iso.Image(built.source, (*built.writes, (blob.sector * iso.SECTOR, flip)), built.size)
    with pytest.raises(ValueError, match=r"/azurkit\.bin's blob [0-9a-f]{12} isn't the bytes its sha256 names"):
        sdk.open_build(bent)


def test_a_conflict_on_a_config_cell_names_the_cell_on_both_sides(usa_iso):
    """AZ-130: a pack's config.xbr cell (player_max_hp's Starting HP) that
    a mods file's ``set`` rewrites (named in D51's spellings) is a D28
    conflict naming the cell on both sides, by table, entity and prop, at
    the bytes the two values differ in; the later layer's value lands."""
    initial = {"op": "set", "file": CONFIG, "table": "settings_foo", "entity": "Initial_HP", "prop": "value",
               "value": 321}
    made, report = sdk.image({"iso": str(usa_iso), "packs": {"player_max_hp": {"starting_hp": 500}},
                              "xbr": [initial]})
    with iso.Reader(made) as r:
        table = Document(r.read(CONFIG)).tables["settings_foo"]
    differ = [k for k, (a, b) in enumerate(zip(struct.pack("<d", 500.0), struct.pack("<d", 321.0))) if a != b]
    assert table.number("initial hp", "Value") == 321.0 and differ == list(range(differ[0], differ[-1] + 1))
    assert report["conflicts"] == [
        f"{CONFIG} 0x{table.find('initial hp', 'Value').at + 8 + differ[0]:X} ({len(differ)} B): data xbr "
        "(#1 set settings_foo/initial hp/Value) overwrote pack player_max_hp, whose group "
        "player_max_hp settings_foo/initial hp/Value is dropped whole"]
