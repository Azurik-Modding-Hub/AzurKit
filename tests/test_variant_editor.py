"""The Variants editor's engine (Step 4.6b; Modkit's Variants page's
engine half, ``authoring/colour_preview.py`` and ``variant_library.py``'s
calls past the library's rules): the colour views
(``tools/characters/colour_preview.py``) and the sdk's ``variant_*`` calls
(``tools/characters/editor.py``): what a base species' tabs read, an
edit's refusals by name, Check with game data, the quick shape preview and
the rows' PNG round trip; and the Moves and Attacks tabs' logic
(``web/variants/moves.mjs`` and ``attacks.mjs``, Step 4.6f) under Node
on the engine's answers, each recipe it writes one the loader takes."""

from __future__ import annotations

import array
import concurrent.futures
import dataclasses
import hashlib
import io
import json
import math
import os
import pickle
import re
import struct
import subprocess
import sys
import time
import wave
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from azurkit import sdk
from azurkit.app import engine
from azurkit.core import iso
from azurkit.tools import characters
from azurkit.tools.characters import _player_variants, colour_preview, library, parts, retarget
from azurkit.tools.randomizer import art
from tests import _hosts

#: booblord_human's colours (W38: her skin's reds warmed, her purples turned green), which the views draw on her base
#: species' own body here.
HUMAN = json.loads(_player_variants.BUILTIN.read_text(encoding="utf-8"))["booblord_human"]["colours"]


def _sha12(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def _game(usa_iso) -> tuple[bytes, bytes]:
    with iso.Reader(usa_iso) as r:
        return r.read(characters.CONFIG), r.read(characters.FILES[0])


def test_the_colour_views_draw_a_bodys_rows_recoloured_as_its_build_recolours_them(usa_iso):
    """``colour_preview`` (Modkit's, in the package since Step 4.6b) draws town_female_2's own body, booblord's
    base, in booblord_human's colours from the front and from behind, 160 px, by sha256 on the recording host (off
    it, D1016, close enough: each view's size, its drawn pixels' count within 1 % and their mean colour within 2 of
    each channel's), the colours changing both; and her rows' textures whole as the Export's PNGs, each recoloured
    row's pixels by sha256 on every host (the recolour's maths is fdlibm's and numpy's correctly rounded operations,
    AZ-830; a PNG's own bytes are each zlib's, so its pixels are held)."""
    config, bodies = _game(usa_iso)
    base = colour_preview.vanilla(config, bodies, "town_female_2")
    colours = colour_preview.specs(HUMAN)
    drawn, plain = colour_preview.pictures(colour_preview.recoloured(base, colours)), colour_preview.pictures(base.parts)
    assert (base.body, sorted(base.sizes.items())) == ("townspeople/female_2", [(r, (128, 128)) for r in range(3)])
    assert all(drawn[view] != plain[view] for view in ("front", "back"))
    seen = {}
    for view, png in drawn.items():
        px = art.unpng(png)
        drawn_at = px[..., 3] > 0
        seen[view] = (px.shape, int(drawn_at.sum()), px[drawn_at][:, :3].mean(0))
    if _hosts.recording():
        assert {view: _sha12(png) for view, png in drawn.items()} == {"front": "f8afb06f3a7b", "back": "70c65104331e"}
    want = {"front": ((160, 160, 4), 5364, (114.22, 78.1, 54.16)),
            "back": ((160, 160, 4), 5435, (113.85, 81.2, 57.31))}
    for view, (shape, count, mean) in seen.items():
        assert shape == want[view][0] and abs(count - want[view][1]) <= want[view][1] // 100, view
        assert np.abs(mean - np.array(want[view][2])).max() <= 2, view
    rows = colour_preview.rows(bodies, base.body, colours)
    files = colour_preview.pngs("mine", rows)
    assert {name: _sha12(art.unpng(png).tobytes()) for name, png in files.items()} == {
        "mine_row0.png": "546ff8107223", "mine_row1.png": "de321e106c9a", "mine_row2.png": "11a3e26a824f",
        "mine_row3.png": "819befadd5c2"}


def _given(usa_iso, tmp_path, recipe=None, name="mine", **more) -> dict:
    """An edit as the editor sends it: a built-in's by name, else its recipe and the folder its files are in."""
    given = {"iso": str(usa_iso), "name": name, **more}
    return given if recipe is None else given | {"recipe": recipe, "folder": str(tmp_path / name)}


#: A recipe on town_female_2 whose mesh widens her pelvis (booblord's own op) and one shape that sizes it.
HIPS = {"base": "town_female_2", "mesh": {"ops": [
    {"op": "scale", "name": "pelvis", "profile": "smooth", "bone": "root_joint", "offset": [0.0, -0.033, -0.175],
     "radius": [0.4, 0.16, 0.22], "factors": [1.4, 1.0, 1.0]}]},
    "shapes": {"hips": {"title": "Hips", "ops": ["pelvis"], "value": 1.0}}}


#: A recipe on town_female_2 with each part a Check keeps (Step 4.6n): its mesh (her hips split, booblord's right
#: glute), a jiggle bone in it, a texture, its arms, its LODs and (Step 4.6q) a sound of its own.
PARTED = {"base": "town_female_2", "mode": "own", "arms": {"out_deg": 10.0}, "lods": {"ratio": [0.5], "at": [9.0]},
          "sfx": {"spin": {"generator": "whoosh", "length": 0.2, "swells": 2, "seed": 1, "columns": ["basic1"]}},
          "mesh": {"ops": [{"op": "subdivide", "name": "hips", "bone": "root_joint", "offset": [0.0, -0.03, -0.1],
                            "radius": [0.32, 0.24, 0.22], "edge": 0.05, "groups": [1]},
                           {"op": "round", "name": "glute right", "bone": "root_joint", "offset": [0.08, -0.07, -0.085],
                            "dir": [0.05, -1.0, 0.0], "origin": 0.07, "groups": [1],
                            "radius": {"across": 0.105, "along": 0.17, "up": 0.145, "down": 0.167, "taper": 0.3},
                            "blend": {"up": 0.05, "down": 0.06, "inner": [0.1, 0.11, 0.15]}}]},
          "jiggle": {"frees": [], "bones": [
              {"role": "glute_right", "bone": "glute_right", "parent": "root_joint", "shape": ["glute right"],
               "groups": [1], "takes": ["root_joint", "right_hip"], "weight": 0.75,
               "spring": {"freq": 3.1, "damping": 0.15, "travel": [0.03, 0.08, 0.12], "gain": 4.3}}]},
          "textures": [{"row": 0, "size": 64, "ops": [{"op": "fill", "bone": "head", "offset": [0.0, -0.06, 0.06],
                                                       "radius": [0.2, 0.2, 0.2], "groups": [0],
                                                       "colour": [0.5, 0.2, 0.2], "mix": 0.5}]}]}


def test_each_base_species_answers_the_editors_tabs_from_the_image(usa_iso):
    """What the editor's tabs read of a base species (Modkit's ``base_bones``, ``own_sounds``, ``kit_throw`` and
    ``move_sources``), for the bases the built-ins stand on, garret4 and a townsman: the body and its bones (the
    springs rows'), the roles its own sounds take (a base with any takes no voice of a recipe's), what its default
    weapon throws and from which columns, and the clips the Moves tab offers (the columns but the roll, its own,
    each lender's and each built-in's Blender clips)."""
    got = {}
    for species in ("town_female_2", "balthazar", "garret4", "town_male_1"):
        asked = {"iso": str(usa_iso), "species": species}
        bones, moves = sdk.base_bones(asked), sdk.move_sources(asked)
        got[species] = (bones["body"], len(bones["bones"]), bones["bones"][0], sdk.own_sounds(asked)["roles"],
                        sdk.kit_throw(asked), len(moves["columns"]), len(moves["own"]), len(moves["lenders"]),
                        sum(map(len, moves["lenders"].values())),
                        {k: [on, len(clips)] for k, (on, clips) in moves["variants"].items()})
    root, kit, none = ["root_joint", ""], {"throw": "", "columns": []}, []
    lent = {"booblord": ["townspeople/female_2", 12]}
    assert got == {
        "town_female_2": ("townspeople/female_2", 93, root, none, {"throw": "vase", "columns": ["right1"]}, 23, 5, 33,
                          268, lent),
        "balthazar": ("balthazar_airship", 135, root, ["attack", "hurt", "death", "taunt", "roll", "hit"], kit, 23, 11,
                      33, 262, lent),
        "garret4": ("garret4", 122, root, none, kit, 23, 95, 33, 178, lent),
        "town_male_1": ("townspeople/male_1", 89, root, none, {"throw": "rock", "columns": ["right1"]}, 23, 8, 33, 265,
                        lent)}


def test_the_moves_tabs_clips_check_every_lender_on_rigs_each_read_and_mapped_once(usa_iso, monkeypatch):
    """The Moves tab's first open reads the bodies' clips (``sdk.move_sources``): its check of each lender a body
    takes shares one ``retarget.Rigs``, so each body's rig is read once and each role map made once (the check read
    garret4's and the body's rigs and mapped the body again for each of its 33 lenders: the tab's open took 1 to 3 s
    in the app), and it offers the lenders a check of each on its own takes (the golem's and keylord's refused)."""
    reads, maps = Counter(), Counter()
    read, mapped = retarget.Rig.read.__func__, retarget.role_map
    monkeypatch.setattr(retarget.Rig, "read", classmethod(lambda cls, xbr, body: reads.update([body])
                                                          or read(cls, xbr, body)))
    monkeypatch.setattr(retarget, "role_map", lambda target, g4, over=None: maps.update([target.name])
                        or mapped(target, g4, over))
    got = sdk.move_sources({"iso": str(usa_iso), "species": "town_female_3"})
    assert (len(got["lenders"]), max(reads.values()), max(maps.values())) == (33, 1, 1)
    _, bodies = _game(usa_iso)
    lenders = ("garret4", "townspeople/female_2", "golem", "keylord")
    alone = [lender for lender in lenders if not _refused(
        lambda lender=lender: retarget.Retarget(bodies, "townspeople/female_3", grow=False, lender=lender))]
    assert [lender for lender in lenders if lender in got["lenders"]] == alone == ["garret4", "townspeople/female_2"]


def _refused(make) -> bool:
    try:
        make()
    except ValueError:
        return True
    return False


def test_an_edit_the_loader_refuses_is_refused_by_name_and_writes_nothing(usa_iso, tmp_path):
    """Each call refuses an edit by the field or file it can't take (D35): an unknown field, a built-in's name, a
    number that isn't finite (D23), a colour op of another kind, no folder, no such built-in; a PNG not the row's
    size and a file that isn't a WAV (nothing copied); and an Export into a folder holding one of its names
    (nothing written)."""
    out = tmp_path / "out"
    out.mkdir()
    (out / "mine_row1.png").write_bytes(b"kept")
    (tmp_path / "noise.wav").write_bytes(b"not a wav")
    (tmp_path / "small.png").write_bytes(colour_preview.pngs("x", {0: np.zeros((4, 4, 4), np.uint8)})["x_row0.png"])
    folder = tmp_path / "mine"
    refused = [
        (sdk.variant_colours, _given(usa_iso, tmp_path, {"base": "town_female_2", "colour": []}), "colour"),
        (sdk.variant_colours, _given(usa_iso, tmp_path, {"base": "town_female_2"}, name="booblord"),
         "a built-in variant has that name"),
        (sdk.variant_check, _given(usa_iso, tmp_path, {"base": "town_female_2", "scale": math.nan}), "scale"),
        (sdk.variant_colours, _given(usa_iso, tmp_path, {"base": "town_female_2", "colours": [
            {"ops": [{"op": "skin"}]}]}), "a textures op"),
        (sdk.variant_rows, {"iso": str(usa_iso), "name": "mine", "recipe": {"base": "town_female_2"}}, "folder"),
        (sdk.variant_check, _given(usa_iso, tmp_path, name="nobody"), "no built-in has that name"),
        (sdk.add_png, {"folder": str(folder), "file": str(tmp_path / "small.png"), "size": [256, 256]}, "4x4"),
        (sdk.add_wav, {"folder": str(folder), "file": str(tmp_path / "noise.wav")}, "noise.wav"),
        (sdk.export_pngs, _given(usa_iso, tmp_path, {"base": "town_female_2", "colours": HUMAN}, out=str(out)),
         "mine_row1.png already")]
    for call, given, words in refused:
        with pytest.raises(ValueError, match=re.escape(words)):
            call(given)
    assert not folder.exists() and sorted(p.name for p in out.iterdir()) == ["mine_row1.png"]


def test_a_check_dresses_a_built_in_answers_then_draws_it_and_one_it_cant_dress_lists_its_bases_bones(usa_iso,
                                                                                                         tmp_path):
    """Check with game data (Modkit's ``check``) dresses beamlord as a build of him does: no refusal, its sha, the
    dressed body and its bones, its own load runs under its build's lines and each effects row's bytes (he has none);
    his picture comes after the answer (Step 4.6q), drawn from the dress the Check kept, and an edit no Check kept asks
    for one; a recipe whose glTF isn't in its folder can't dress, and says so by its file in that folder with its
    base's own bones (where its springs rows go)."""
    given = _given(usa_iso, tmp_path, name="beamlord")
    found = sdk.variant_check(given)
    assert (found["refusal"], found["sha"], found["body"], len(found["bones"])) == (None, "628f6d09ad7b",
                                                                                     "balthazar_airship", 135)
    assert 0 < found["load"]["own"] < found["load"]["error"] and found["log"] and "front" not in found
    assert len(found["effects"]) == len(_player_variants.builtins()["beamlord"].effects)
    drawn = sdk.variant_pictures(given)
    assert art.unpng(drawn["front"]).shape == art.unpng(drawn["back"]).shape == (160, 160, 4)
    with pytest.raises(ValueError, match="no Check of it is kept"):
        sdk.variant_pictures(_given(usa_iso, tmp_path, name="booblord"))
    glb = {"base": "town_female_2", "mesh": {"gltf": {"file": "body.glb", "sha256": "0" * 64}}}
    cant = sdk.variant_check(_given(usa_iso, tmp_path, glb))
    assert str(tmp_path / "mine" / "body.glb") in cant["refusal"]
    assert cant["bones"] == sdk.base_bones({"iso": str(usa_iso), "species": "town_female_2"})["bones"]


def test_a_check_of_a_dress_that_leaves_characters_xbr_vanilla_reads_the_images_own(usa_iso, tmp_path):
    """A New on flicken (his own moves) dresses with characters.xbr left as the image holds it: Check answers from the
    image's own file, as Modkit's (its dress holds the whole game) does, not a KeyError: his body and its bones, and
    the own load Modkit's Check gives the same recipe."""
    found = sdk.variant_check(_given(usa_iso, tmp_path, library.new("flicken")))
    assert (found["refusal"], found["body"], found["load"]["own"]) == (None, "flicken", 253952)
    assert found["bones"] == sdk.base_bones({"iso": str(usa_iso), "species": "flicken"})["bones"]


def test_a_check_of_a_look_on_garret4_hands_the_colours_views_his_body_before_its_colours(usa_iso, tmp_path):
    """A recipe on garret4's own body whose build changes his body (a mesh op) and recolours his own rows in place
    (hue +120): Check with game data hands the Colours views his body before its colours, each part's texture his
    vanilla one (``colour_preview.uncoloured``), as for any other body, so they recolour it once (Modkit's Step
    2.206, its rebase review's D2; the Export half is ``test_model_authoring``'s)."""
    op = {"op": "scale", "bone": "spine_2", "radius": [0.2, 0.2, 0.2], "factors": [1.2, 1.2, 1.2]}
    found = sdk.variant_check(_given(usa_iso, tmp_path, {"base": "garret4", "mesh": {"ops": [op]},
                                                         "colours": [{"ops": [{"op": "hsv", "hue": 120}]}]}))
    assert found["refusal"] is None, found["refusal"]
    kept, plain = sdk._kept_base(sdk._CHECKED["last"]), colour_preview.vanilla(*_game(usa_iso), "garret4")
    assert kept.dressed and [(q.row, q.raw.tobytes()) for q in kept.parts] == [
        (q.row, q.raw.tobytes()) for q in plain.parts] != []


def test_a_check_of_content_checked_before_answers_from_what_it_kept(usa_iso, tmp_path, monkeypatch):
    """Check with game data keeps by content (D1015): the same edit checked again answers at once, and in a process
    that kept its dress (another thread's call: another hidden recipe file) takes it by what the file dresses, its
    log naming recipe.json, a title typed since too (no dress reads it); yours as saved, or but for its notes,
    dresses by name, so its Build takes the Check's dress. Only new content (a scale moved) dresses again."""
    kept, dressed = {}, []
    store = type("Store", (), {"get": lambda _, key: kept.get(key),
                               "put": lambda _, key, made: kept.__setitem__(key, made if isinstance(made, bytes)
                                                                            else made())})
    monkeypatch.setattr(characters, "CACHE", store())
    monkeypatch.setattr(library, "ROOT", tmp_path / "library")
    for name in ("_size", "_plan"):
        work = getattr(characters, name)
        monkeypatch.setattr(characters, name, lambda recipe, *a, _work=work, _name=name, **k: (
            dressed.append((_name, recipe["species"])), _work(recipe, *a, **k))[1])
    recipe = library.new("keylord")
    given = _given(usa_iso, tmp_path, recipe)
    first = sdk.variant_check(given)
    assert sdk.variant_check(given) == first and dressed == [("_size", "mine"), ("_plan", "mine")]
    sdk._CHECKED.clear()
    with concurrent.futures.ThreadPoolExecutor(1) as other:
        again = other.submit(sdk.variant_check, given).result()
    assert again == first and len(dressed) == 2 and not any(".edit-" in line for line in again["log"])
    assert sdk.variant_check(given | {"recipe": recipe | {"title": "Mine"}}) == first and len(dressed) == 2
    library.save_as("yours", recipe)
    yours = given | {"name": "yours", "folder": str(tmp_path / "library" / "yours")}
    sdk.variant_check(yours)
    sdk._plan({"iso": str(usa_iso), "packs": {}, "character": {"species": "yours"}})
    sdk.variant_check(yours | {"recipe": recipe | {"notes": "kept"}})
    sdk.variant_check(given | {"recipe": recipe | {"scale": 1.5}})
    assert dressed[2:] == [("_size", "yours"), ("_plan", "yours"), ("_size", "mine"), ("_plan", "mine")]


def test_a_copy_under_another_name_checks_from_the_parts_a_check_kept_as_a_fresh_check_answers(usa_iso, tmp_path,
                                                                                                monkeypatch):
    """Step 4.6n (the Check design's R1): a dress's parts are kept by what they read, never the variant's name or
    folder, so PARTED checked again under another name in another folder takes each part the first Check kept (its
    size, its body's mesh, rig and paint, its kit's clips, its bakes, both restyles, its LODs and, Step 4.6q, its
    sounds' encodings, each later file named from the one before it), and a copy with its spring edited keeps the mesh
    and works out the rest, each answering and dressing as a fresh Check of it (no part kept or taken) does, byte for
    byte; at a later visit (Step 4.6o: this process's parts gone, its host's store holding what the first Check's
    parts were handed it as, ``part_codec``'s bytes) the copy takes each of them from the store, answering the same
    (a built-in's own copy shares its body's parts: ``test_variant_library``'s New from this test)."""
    stored = {}
    store = type("Store", (), {"get": lambda _, key: stored.get(key),
                               "put": lambda _, key, made: stored.__setitem__(key, made()),
                               "used": lambda *_: None})
    monkeypatch.setattr(parts, "HEARD", {})
    monkeypatch.setattr(parts, "STORE", store())
    parts.clear()
    sdk.variant_check(_given(usa_iso, tmp_path, PARTED, name="first"))
    springier = json.loads(json.dumps(PARTED))
    springier["jiggle"]["bones"][0]["spring"]["freq"] = 2.5
    copies, answers, missed, heard = {"second": PARTED, "third": springier}, {}, {}, {}
    for visit, name in ((1, "second"), (1, "third"), (2, "second")):
        if visit == 2:   # a later visit's process: only the store's parts
            parts.clear()
        parts.HEARD.clear()
        sdk._CHECKED.clear()
        answers[visit, name] = sdk.variant_check(_given(usa_iso, tmp_path, copies[name], name=name)), _sha12(
            sdk._CHECKED["last"]["characters"])
        missed[visit, name] = {stage: counts["miss"] for stage, counts in parts.HEARD.items()}
        heard[visit, name] = {stage: counts.get("stored", 0) for stage, counts in parts.HEARD.items()}
    taken = dict.fromkeys(("size", "W24", "W29", "W30", "kit clips", "bake", "W28 arms", "W28 springs", "W39",
                           "wave"), 0)
    assert missed[1, "second"] == missed[2, "second"] == taken and heard[2, "second"] == dict.fromkeys(
        taken, 1) | {"bake": 2}   # its two bakes (Step 4.6q): its own clips, then its style's
    assert answers[2, "second"] == answers[1, "second"]
    assert missed[1, "third"]["W24"] == 0 < missed[1, "third"]["W29"] and answers[1, "third"][0]["refusal"] is None
    answers = {name: answers[1, name] for name in copies}
    monkeypatch.setattr(parts, "OFF", True)
    for name, recipe in copies.items():
        sdk._CHECKED.clear()
        assert (sdk.variant_check(_given(usa_iso, tmp_path, recipe, name=name)),
                _sha12(sdk._CHECKED["last"]["characters"])) == answers[name]


def _exact(a, b) -> bool:
    """Whether ``a`` and ``b`` hold the same values of the same types: floats by their bits, objects by their fields."""
    if type(a) is not type(b):
        return False
    if isinstance(a, parts.Pickled):
        return _exact(pickle.loads(a), pickle.loads(b))
    if type(a) is float:
        return struct.pack("<d", a) == struct.pack("<d", b)
    if type(a) in (tuple, list):
        return len(a) == len(b) and all(map(_exact, a, b))
    if type(a) is dict:
        return list(a) == list(b) and all(map(_exact, a.values(), b.values()))
    if type(a) is array.array:
        return a.typecode == b.typecode and a.tobytes() == b.tobytes()
    if type(a) is np.ndarray:
        return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()
    if dataclasses.is_dataclass(a):
        return all(_exact(getattr(a, f.name), getattr(b, f.name)) for f in dataclasses.fields(a))
    return a == b


def test_a_part_kept_across_visits_reads_back_as_it_was_and_a_spoiled_stale_or_foreign_one_is_refused_by_name(
        tmp_path):
    """Step 4.6o (the Check design's L2 and R4): a dress's part as a later visit's host keeps it (``part_codec``'s
    bytes, no pickle) reads back as the values it held, each of its type, a float's bits (a zero's sign, a NaN) and
    the lists and dicts it held in two places one again, the objects it pickled (LODs, a mesh plan's runs of rows and
    dicts) too; bytes that aren't one, cut short, inflating past what they list or past the most a part may hold, or
    a class whose fields changed since (a stale part) or no part holds are refused by name, and a value no part holds
    isn't kept. A WAV's part (Step 4.6q) is one it keeps."""
    from compression import zstd

    from azurkit.tools.characters import body_codec, part_codec, xbox_adpcm

    shared, skin = [0, 3], {7: 0.5, 2: 0.25}
    vertices = [body_codec.Vertex((1.0, -0.0, k), (0.75, 0.25, 0.0, 0.0), (0.0, 0.0, 1.0), (0.5, 0.25), slots=(1, 2, 0,
                                                                                                             0))
                for k in range(5)]
    lods = [body_codec.Lod(None, [body_codec.Group(shared, vertices, [(0, 1, 2)] * 4, (1, 2)),
                                  body_codec.Group(shared, vertices[:1], [], (0, 0))])]
    held = {"lods": lods, "skins": (skin, {1: 1.0}, {}, skin, {}), "same": [skin], "corners": (((0.5, -0.0),) * 3,) * 4,
            "keys": (b"abc", b"", b"de", b"f"), "grid": np.arange(6, dtype="<f4").reshape(2, 3),
            "odd": (math.nan, -math.inf, 1 << 70, None, True, "\u00e9", frozenset({1}), {2}, bytearray(b"z"),
                    np.float64(2.5), array.array("q", [-1, 2]))}
    part = ((8192, array.array("q", [0, 4096]), b"\x01" * 4096), parts.dump(held), ("painted",), False)
    blob = part_codec.encode(part)
    back = part_codec.decode(blob)
    again = pickle.loads(back[1])
    assert _exact(back, part) and again["lods"][0].groups[0].palette is again["lods"][0].groups[1].palette
    assert again["skins"][0] is again["skins"][3] is again["same"][0]
    head = len(part_codec.MAGIC) + 8
    body = zstd.decompress(blob[head:])

    def packed(data: bytes) -> bytes:   # bytes as a part's, inflating to ``data``
        return part_codec.MAGIC + struct.pack("<Q", len(data)) + zstd.compress(data)

    n = struct.unpack_from("<I", body)[0]
    stale, foreign = (packed(struct.pack("<I", n + delta) + body[4:4 + n].replace(old, new) + body[4 + n:])
                      for old, new, delta in ((b'"palette"', b'"colours"', 0), (b"body_codec", b"body_codex", 0)))
    for spoiled, words in ((b"PK\x03\x04" + blob[4:], "not one AzurKit keeps"), (blob[:-9], "inflate"),
                           (blob[:head - 8] + struct.pack("<Q", len(body) - 1) + blob[head:], "inflate"),
                           (blob[:head - 8] + struct.pack("<Q", 1 << 40) + blob[head:], "past the"),
                           (stale, "Group's fields changed since it was kept (a stale part)"),
                           (foreign, "no codec for a azurkit.tools.characters.body_codex.Lod"),
                           (packed(body + b"x"), "1 bytes past its last value")):
        with pytest.raises(ValueError, match=re.escape(words)):
            part_codec.decode(spoiled)
    with pytest.raises(ValueError, match="no codec for a builtins.object"):
        part_codec.encode((1, object()))
    sound = tmp_path / "a.wav"
    with wave.open(str(sound), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(xbox_adpcm.RATE), w.writeframes(b"\x01\x00" * 64)
    parts.clear()
    read = xbox_adpcm.read_wav(sound)
    kept = parts.get(parts.key("wav", hashlib.sha256(sound.read_bytes()).hexdigest()))
    assert part_codec.decode(part_codec.encode(kept)) == kept and xbox_adpcm.read_wav(sound) == read


def test_a_built_ins_shipped_part_is_fetched_only_when_a_check_asks_for_it_held_to_its_row_and_kept_by_the_host(
        tmp_path, monkeypatch):
    """Step 4.6p (the Check design's L3): a part a ``part`` row of ``shipped.json`` ships (``record_shipped.py``'s: a
    file in its entry's ``shipped/parts/`` in Azurik-Custom-Content, at zstd 19) is listed with its entry, but Install
    leaves it (``content.later``: the rest written, the record listing it; the site's check passes without it), and a
    Check that asks for it fetches it from the source its entry came from (the sdk's fetch: a folder here), reads it
    back as it was, hears it fetched and hands it to the host's store as a part made there, so a later visit fetches
    none; one a content folder holds (a clone's) is taken there and never handed to the store. One whose fetched bytes
    aren't its row's (a byte spoiled, another part's, gone), one no installed entry lists at its sha256, and any with
    ``shipped.OFF`` are worked out, and a source that failed isn't asked again for ``shipped.DOWN``. A fresh part is
    heard (``shipped.SEEN``) by its digest, the row's answer, which a set of names doesn't move from one process to
    another (a str's hash does), so the re-record pin holds it to its row."""
    from azurkit.tools.characters import content, part_codec, shipped

    held = ((8192, array.array("q", [0, 4096]), b"\x01" * 4096), parts.dump({"bones": {"hip", "tail", "ear"}}), False)
    blob, other = part_codec.encode((held, 64), 19), part_codec.encode(("another", 1))
    at, note, source, root = "variants/x/shipped/parts/0.azkp", "variants/x/README.md", tmp_path / "source", tmp_path / "c"
    files = []
    for path, data in ((at, blob), (note, b"x")):
        (source / path).parent.mkdir(parents=True, exist_ok=True)
        (source / path).write_bytes(data)
        files.append({"path": path, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
    listed = json.dumps({"format": content.FORMAT, "schema_version": 1, "entries": [{
        "id": "x", "kind": "variant", "title": "x", "author": "a", "licence": "l", "version": 1, "files": files,
        "requires": []}]})
    (source / content.MANIFEST).write_text(listed, encoding="utf-8")
    monkeypatch.delenv(sdk.SOURCE_ENV, raising=False)
    monkeypatch.setattr(content, "ROOT", root)
    sdk.content_install({"id": "x", "source": str(source)})
    assert sorted(f.relative_to(root).as_posix() for f in root.rglob("*") if f.is_file()) == [
        content.INSTALLED, content.MANIFEST, note]
    assert content.installed()["x"]["files"] == {f["path"]: f["sha256"] for f in files}
    assert sdk.content_check({"manifest": listed, "id": "x", "files": {note: b"x"}})["install"] == ["x"]
    row = {"part": "W24:k", "answer": part_codec.digest((held, 64)), "blob": files[0]}
    table, put, used, fetches = {"part": [row], "host": shipped.host()}, [], [], []
    store = type("Store", (), {"get": lambda *_: None, "put": lambda _, key, data: put.append((key, data)),
                               "used": lambda _, key, make: used.append(key)})
    monkeypatch.setattr(shipped, "table", lambda: table)
    monkeypatch.setattr(shipped, "OFF", False)
    monkeypatch.setattr(shipped, "_DOWN", {})
    monkeypatch.setattr(shipped, "FETCH", lambda *args: fetches.append(args[1]) or sdk._later(*args))
    monkeypatch.setattr(parts, "STORE", store())
    monkeypatch.setattr(parts, "HEARD", {})
    parts.clear()
    assert _exact(parts.get("W24:k", "W24"), held) and parts.HEARD["W24"] == {"hit": 1, "miss": 0, "fetched": 1}
    assert put == [(parts._stored("W24:k"), blob)] and fetches == [at]
    (root / at).parent.mkdir(parents=True)
    (root / at).write_bytes(blob)   # a clone's content folder: taken there, never handed to the store
    parts.clear()
    parts.HEARD = {}
    assert _exact(parts.get("W24:k", "W24"), held) and parts.HEARD["W24"] == {"hit": 1, "miss": 0, "shipped": 1}
    assert _exact(parts.get("W24:k"), held) and used == [] and len(put) == 1 and fetches == [at]
    (root / at).unlink()
    record = (root / content.INSTALLED).read_text(encoding="utf-8")
    for why, spoil in {"a byte spoiled": lambda: (source / at).write_bytes(blob[:-1] + bytes([blob[-1] ^ 1])),
                       "another part's": lambda: (source / at).write_bytes(other),
                       "listed by no entry at its sha256": lambda: (root / content.INSTALLED).write_text(
                           record.replace(files[0]["sha256"], "0" * 64), encoding="utf-8"),
                       "gone": (source / at).unlink, "shipped.OFF": lambda: setattr(shipped, "OFF", True)}.items():
        spoil()
        parts.clear()
        assert parts.get("W24:k") is None, why
        (source / at).write_bytes(blob)
        (root / content.INSTALLED).write_text(record, encoding="utf-8")
        shipped.OFF = False
    assert fetches == [at] * 4 and parts.get("W24:k") is None and fetches == [at] * 4   # gone a moment ago: not asked
    shipped._DOWN.clear()
    assert _exact(parts.get("W24:k"), held) and fetches == [at] * 5
    monkeypatch.setattr(shipped, "SEEN", [])
    parts.put("W24:k", held, 64)
    assert shipped.SEEN == [{"part": {"part": "W24:k", "answer": row["answer"]}}]
    assert shipped.held(shipped.SEEN[0], table) == (["part W24:k"], [])
    digests = {subprocess.run([sys.executable, "-c", "from azurkit.tools.characters import part_codec, parts; print("
                               "part_codec.digest((parts.dump({'bones': {'hip', 'tail', 'ear'}}), frozenset('abcd'))))"],
                              env=os.environ | {"PYTHONHASHSEED": seed}, capture_output=True, text=True,
                              check=True).stdout for seed in ("1", "2")}
    assert len(digests) == 1


def test_two_dresses_on_two_threads_take_and_keep_parts_at_once_and_hold_only_the_parts_kept(monkeypatch):
    """Step 4.6n: the app's engine dresses on a thread a call, so a Check and a build take and keep parts at once,
    under the lock it sets (``parts.LOCK``): a part let go while the other takes it is a miss, never a KeyError, and
    the bytes held stay those of the parts kept, within ROOM."""
    monkeypatch.setattr(parts, "ROOM", 3)
    parts.clear()
    names, switch = "abcd", sys.getswitchinterval()

    def run(work) -> None:
        stop = time.monotonic() + 0.2
        while time.monotonic() < stop:
            for name in names:
                work(name)

    sys.setswitchinterval(1e-6)
    try:
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            for done in [pool.submit(run, parts.get), pool.submit(run, lambda name: parts.put(name, name, 1))]:
                done.result()
    finally:
        sys.setswitchinterval(switch)
    assert parts._HELD[0] == sum(size for _, size in parts._SLOTS.values()) == len(parts._SLOTS) <= 3
    parts.clear()


def test_the_quick_preview_puts_each_drawn_vertex_where_a_dress_at_those_values_does(usa_iso, tmp_path):
    """The Shape tab's preview (Modkit's ``preview``) moves the last Check's drawn vertices to a shape's new value
    with no dress: HIPS' pelvis at 1.5 drawn as a Check of it at 1.5 draws it (its scale op makes no new vertex, so
    every one is found), in a fraction of a second, its edit under another name and folder than the Check's (a
    built-in checked by its name, then dragged, is an edit of it); one whose mesh changed beyond its shapes asks for
    the Check."""
    given = _given(usa_iso, tmp_path, HIPS)
    sdk.variant_check(given)
    first = sdk.variant_pictures(given)
    wider = json.loads(json.dumps(HIPS))
    wider["shapes"]["hips"]["value"] = 1.5
    quick = sdk.variant_preview(_given(usa_iso, tmp_path, wider, name=sdk.UNSAVED))
    assert quick["front"] != first["front"] and quick["seconds"] < 3
    sdk.variant_check(given | {"recipe": wider})
    assert {k: quick[k] for k in ("front", "back")} == sdk.variant_pictures(given | {"recipe": wider})
    other = json.loads(json.dumps(HIPS))
    other["mesh"]["ops"][0]["bone"] = "spine_1"
    with pytest.raises(ValueError, match="Check with game data dresses it"):
        sdk.variant_preview(given | {"recipe": other})


def test_a_rows_png_exports_and_an_edited_one_comes_back_as_the_rows_texture(usa_iso, tmp_path):
    """The Colours tab's round trip (Step 2.203): Export writes each row's texture whole as its build recolours it
    (the site's: the same files in a zip); an edited one comes back (``add_png``: its name and sha256) as the row's
    ``png`` op, which the rows, the views and its palette (the wheel's, Step 4.6e: its main colours as the PNG
    leaves them, then after the row's other ops, one for one, as Modkit's page reads them) then draw; a WAV comes in
    under a name a recipe's ``wavs`` take, the same bytes once. The app's engine runs the views, its pictures base64."""
    out, folder = tmp_path / "out", tmp_path / "mine"
    given = _given(usa_iso, tmp_path, {"base": "town_female_2", "colours": HUMAN})
    written = sdk.export_pngs(given | {"out": str(out)})["files"]
    assert written == [f"mine_row{r}.png" for r in range(4)]
    zipped = sdk.export_pngs(given)
    with zipfile.ZipFile(io.BytesIO(zipped["zip"])) as z:
        assert (zipped["name"], {n: z.read(n) for n in z.namelist()}) == (
            "mine_pngs.zip", {f"mine_pngs/{n}": (out / n).read_bytes() for n in written})
    turned = sdk.variant_colours(given | {"row": 1})["palette"]   # HUMAN's row 1: its blues turned, its browns kept
    assert len(turned["found"]) == 6 and turned["found"][1] != turned["shown"][1] and turned["found"][5] == turned[
        "shown"][5]
    row = 255 - art.unpng((out / written[0]).read_bytes())
    row[..., 3] = 255
    (tmp_path / "edited.png").write_bytes(colour_preview.pngs("e", {0: row})["e_row0.png"])
    op = sdk.add_png({"folder": str(folder), "file": str(tmp_path / "edited.png"),
                      "size": sdk.variant_rows(given)["sizes"]["0"]})
    assert op["name"] == "edited.png" and (folder / "edited.png").is_file()
    edited = _given(usa_iso, tmp_path, {"base": "town_female_2", "colours": [
        {"row": 0, "ops": [{"op": "png", "file": op["name"], "sha256": op["sha256"]}]}]})
    assert np.array_equal(art.unpng(sdk.variant_rows(edited)["files"]["mine_row0.png"]), row)
    png = sdk.variant_colours(edited | {"row": 0})["palette"]
    assert png["found"] == png["shown"] == colour_preview.palette(row).tolist()
    assert sdk.variant_colours(edited)["front"] != sdk.variant_colours(given)["front"]
    assert engine.JOBS["variant_colours"](given) == engine._shown(sdk.variant_colours(given))
    with wave.open(str(tmp_path / "my take.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x01\x00" * 2205)
    assert [sdk.add_wav({"folder": str(folder), "file": str(tmp_path / "my take.wav")})["name"] for _ in "ab"] == [
        "my_take.wav", "my_take.wav"]


def test_the_sounds_and_effects_tabs_read_what_the_loader_lays_and_a_picked_wav_comes_in_by_its_bytes(
        tmp_path, monkeypatch):
    """What the Sounds and Effects tabs read with no image (Step 4.6g; Modkit's tabs, Step 2.164b): the list's
    ``editor`` names the WAV roles (the loader's), each role's most takes and the effects templates with each param's
    default and display range; a recipe from booblord reads her sounds as the loader lays them (her voice, WAVs,
    sounds and shouts) and her rows as its ``from_effects``, and one with rows of its own reads them with their
    defaults left out, beamlord's his fx edits and grafts; a WAV picked on the site comes in by its bytes under the
    name a recipe's ``wavs`` take (the same bytes once, other bytes beside them), and bytes that are no WAV are
    refused by the name it was picked as, nothing copied."""
    monkeypatch.setattr(library, "ROOT", tmp_path / "library")
    lists = sdk.variants()["editor"]
    assert (lists["roles"], lists["takes"], lists["bound_rows"]) == (list(_player_variants.DROP_ROLES),
                                                                     _player_variants.TAKES, 3)
    fireball = next(t for t in lists["templates"] if t["name"] == "fireball")
    assert ([t["name"] for t in lists["templates"]][:3], fireball["engine"], fireball["params"]["speed"]) == (
        ["fireball", "ice_shard", "arrow"], "throw", {"default": 18, "range": [4, 40]})
    hers = sdk.variant_open({"name": "booblord"})["read"]
    boob = _player_variants.builtins()["booblord"]
    assert (hers["voice"], hers["wavs"], list(hers["sfx"]), hers["shouts"], hers["effects"], hers["from_effects"]) == (
        "silent", {k: list(v) for k, v in boob.wavs.items()}, list(boob.sfx), list(boob.shouts), [], [])
    own = sdk.variant_read({"name": sdk.UNSAVED, "recipe": {"from": "booblord", "effects": [
        {"template": "bubble", "columns": ["basic1"], "size": 1.1, "opacity": 0.5}]}})
    assert (own["effects"], own["from_effects"]) == ([{"template": "bubble", "columns": ["basic1"], "opacity": 0.5}], [])
    beam = sdk.variant_open({"name": "beamlord"})["read"]
    assert (len(beam["fx"]), beam["fx_grafts"][0], beam["fx_ring"]) == (11, {"template": "electric_shield",
                                                                             "parent": 32}, {})
    folder, take = tmp_path / "library" / "mine", tmp_path / "take.wav"
    with wave.open(str(take), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x01\x00" * 2205)
    picked = [sdk.add_wav({"folder": str(folder), "file": "C:\\picked\\my take.wav", "data": data})["name"]
              for data in (take.read_bytes(), take.read_bytes(), take.read_bytes()[:-2] + b"\x02\x00")]
    assert picked == ["my_take.wav", "my_take.wav", "my_take_2.wav"]
    with pytest.raises(ValueError, match=r"^noise\.wav: "):
        sdk.add_wav({"folder": str(folder), "file": "noise.wav", "data": b"not a wav"})
    assert sorted(p.name for p in folder.iterdir()) == ["my_take.wav", "my_take_2.wav"]


# The Moves and Attacks tabs' own logic (Step 4.6f, web/variants/moves.mjs and attacks.mjs) under Node, as the page runs
# it: the given engine answers in, each step's recipe and what the tab shows out (the drivers below).
TABS = """
import * as moves from %s;
import * as attacks from %s;
let input = "";
for await (const chunk of process.stdin) input += chunk;
const given = JSON.parse(input), out = {};
const copy = (x) => JSON.parse(JSON.stringify(x));
const find = (entries, ...path) => path.reduce((at, label) => (Array.isArray(at) ? at : at.entries)
  .find((e) => e.label === label), entries);
const leaves = (entries) => entries.filter((e) => !e.separator && !e.entries).map((e) => e.label);
%s
process.stdout.write(JSON.stringify(out));
"""


def _tabs(steps: str, given: dict) -> dict:
    """``steps`` (JS over ``given``, writing ``out``) run under Node on the tabs' modules."""
    web = Path(__file__).resolve().parent.parent / "web" / "variants"
    script = TABS % (json.dumps((web / "moves.mjs").as_uri()), json.dumps((web / "attacks.mjs").as_uri()), steps)
    run = subprocess.run(["node", "--input-type=module", "--eval", script], input=json.dumps(given), capture_output=True,
                         text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    return json.loads(run.stdout)


def _loaded(recipe: dict, tmp_path):
    """``recipe`` as the loader reads it from your variant's folder (``sdk.variant_read`` taking it too)."""
    assert sdk.variant_read({"name": "mine", "recipe": recipe})["refusal"] is None, recipe
    return _player_variants.load_variants(json.dumps({"mine": recipe}), str(tmp_path / "mine" / library.RECIPE),
                                          tuple(_player_variants.builtins()))["mine"]


MOVES = """
const { sources, barnacle } = given;
const recipe = { base: "town_female_3", mode: "own" };
const jump = moves.menuOf(sources, recipe, null);
const lent = jump.filter((e) => e.entries).map((e) => e.label), g4 = find(jump, "garret4").entries;
out.menu = [lent[0], lent.at(-1), find(jump, "Townspeople").entries.map((e) => e.label).includes("town_male_1"),
            leaves(jump), g4.length < 20, leaves(find(g4, "jump (2)").entries)];
moves.pick(recipe, "slots", "jump", find(jump, "garret4", "jump (2)", "jump").value, sources);
moves.pick(recipe, "idles", "idle", find(moves.menuOf(sources, recipe, null), "booblord (Blender clips)", "hip_idle").value,
           sources);
out.lent = [copy(recipe), moves.shownText("g4_jump", recipe.clips, sources.names)];
moves.pick(recipe, "slots", "jump", null, sources);
out.dropped = copy(recipe);
const fidgets = () => [1, 2].map((k) => moves.gated("idles", `idle_${k}`, moves.named(recipe, null)));
out.gated = [fidgets()];
moves.pick(recipe, "idles", "idle_1", "sit", sources);
moves.pick(recipe, "idles", "idle_2", "listen", sources);
out.gated.push(fidgets());
out.waits = [moves.setWait(recipe, ["2", ""]), moves.setWait(recipe, ["2.5", "8"]), moves.setCancel(recipe, "fast"),
             moves.setCancel(recipe, "0.75")];
out.fidgets = copy(recipe);
moves.pick(recipe, "idles", "idle", null, sources);
delete recipe.victory_cancel;
out.cleared = [copy(recipe), fidgets(), moves.setWait(recipe, ["1", "2"])];
const armed = { base: "town_female_3", mode: "own", weapon: "farmers_hoe" };
const hoe = moves.menuOf(sources, armed, null);
moves.pick(armed, "idles", "idle", "listen", sources);
out.armed = [hoe.some((e) => e.entries), leaves(hoe).includes("listen"), copy(armed)];
const lone = moves.menuOf(barnacle, { base: "barnacle", mode: "own" }, null);
out.barnacle = [lone.some((e) => e.entries), leaves(lone).length > 1];
out.fixed = [moves.whyFixed({ from: "beamlord" }, null), moves.whyFixed({ base: "keylord", mode: "garret4" }, null),
             moves.whyFixed({ base: "garret4" }, { mode: "own" })];
"""


@pytest.mark.web
def test_a_moves_pick_writes_the_recipes_slot_and_offers_only_what_the_loader_takes(usa_iso, tmp_path, monkeypatch):
    """The Moves tab (Step 4.6f; Modkit's, D768, D785 "Any humanoid body's"): a slot's menu offers the build's pick,
    the body's own clips and, a submenu each, garret4's clips (first, grouped by their first word), every humanoid
    body's the bake can put on it (the townsfolk in one submenu, each by its species) and booblord's Blender clips; a
    pick of another's writes a ``bake`` clip under a short name (W3 holds a column's in a vanilla string, Modkit's
    names) that the slot plays, shown as its clip and body, and "—" takes the slot out and drops the clip no slot
    plays. A fidget waits for the slot before it ("—" on the base clears those after it); the idles' wait takes both
    ends or neither, after a base, and Cancel after a number, each named otherwise. A recipe whose weapon plays every
    column, and a body the bake doesn't serve, are offered their own clips alone; a recipe from another is read-only
    and Skin only plays Garret's. Every recipe written is one the loader takes."""
    monkeypatch.setenv(library.ENV, str(tmp_path / "variants"))
    asked = lambda species: sdk.move_sources({"iso": str(usa_iso), "species": species})   # noqa: E731
    got = _tabs(MOVES, {"sources": asked("town_female_3"), "barnacle": asked("barnacle")})
    hip = {"generator": "bake", "body": "townspeople/female_2", "variant": "booblord", "clip": "hip_idle"}
    lent = {"base": "town_female_3", "mode": "own", "slots": {"jump": "g4_jump"}, "idles": {"idle": "b_hip_idle"},
            "clips": {"g4_jump": {"generator": "bake", "body": "garret4", "clip": "jump"}, "b_hip_idle": hip}}
    assert got["menu"] == ["garret4", "booblord (Blender clips)", True,
                           ["— the build's pick", "idle", "listen", "sit", "talk", "walk"], True, ["jump", "jump_standing"]]
    assert got["lent"] == [lent, "jump · garret4"]
    assert got["dropped"] == {"base": "town_female_3", "mode": "own", "idles": {"idle": "b_hip_idle"},
                              "clips": {"b_hip_idle": hip}}
    assert got["gated"] == [[False, True], [False, False]]
    assert got["waits"] == ["Wait: give both ends as numbers, or neither", "", "Cancel after: 'fast' is not a number", ""]
    assert (got["fidgets"]["idles"], got["fidgets"]["victory_cancel"]) == (
        {"idle": "b_hip_idle", "idle_1": "sit", "idle_2": "listen", "wait": [2.5, 8]}, 0.75)
    assert got["cleared"] == [{"base": "town_female_3", "mode": "own"}, [True, True], "Wait: pick an idle base first"]
    assert got["armed"] == [False, True, {"base": "town_female_3", "mode": "own", "weapon": "farmers_hoe",
                                          "idles": {"idle": "listen"}}]
    assert got["barnacle"] == [False, True]
    assert got["fixed"] == [["beamlord's moves (read-only): New from this… makes one to edit.", True],
                            ["Skin only plays Garret's moves.", False], ["", True]]
    worn = [_loaded(recipe, tmp_path) for recipe in (lent, got["dropped"], got["fidgets"], got["armed"][2])]
    assert (worn[0].clips["g4_jump"], worn[2].idle_wait, worn[2].victory_cancel, worn[3].idles) == (
        lent["clips"]["g4_jump"], (2.5, 8.0), 0.75, {"idle": "listen"})


ATTACKS = """
const { sources, offers, built, booblord, beamlord } = given, names = sources.columns, tip = attacks.FLAG_LISTS[0][2];
const recipe = { base: "town_female_2", mode: "own" };
attacks.setDrain(recipe, "all");
out.drain = [copy(recipe.drain)];
attacks.setDrain(recipe, "nearest");
out.drain.push("drain" in recipe);
for (const [key, column] of [["carry", "basic3"], ["carry", "basic1"], ["held", "finish"]]) {
  attacks.setFlag(recipe, null, key, column, true, names);
}
out.flags = [copy(recipe), attacks.flagText(attacks.listed(recipe, null, "carry"), tip),
             attacks.flagText(attacks.listed(recipe, null, "held"), tip)[0]];
for (const column of ["basic1", "basic3"]) attacks.setFlag(recipe, null, "carry", column, false, names);
out.flags.push("carry" in recipe, attacks.flagText(attacks.listed(recipe, null, "carry"), tip)[0]);
delete recipe.held;
const kick = find(moves.menuOf(sources, recipe, null), "garret4", "attack (19)", "attack_back_kick").value;
moves.pick(recipe, "columns", "basic1", kick, sources);
attacks.setSeek(recipe, "g4_1", true);
out.seek = [copy(recipe), attacks.playedOf(recipe, null, names)[0]];
moves.pick(recipe, "columns", "basic1", null, sources);
out.kit = [attacks.kitOf(recipe, built, offers).weapons.map((w) => w.label)];
attacks.setWeapon(recipe, "axion_staff");
out.kit.push(recipe.weapon, attacks.offOf(recipe));
attacks.setWeapon(recipe, null);
const shown = attacks.kitOf(recipe, built, offers).switches;
attacks.setAttack(recipe, "reach", 1.25);
attacks.setAttack(recipe, "damage", 2);
attacks.setSwitch(recipe, "balance", false, built.attack_defaults);
attacks.setSwitch(recipe, "through_walls", true, built.attack_defaults);
out.numbers = [shown, copy(recipe), moves.number("fast"), moves.repr("fast")];
attacks.setSwitch(recipe, "balance", true, built.attack_defaults);
attacks.setSwitch(recipe, "through_walls", false, built.attack_defaults);
attacks.setAttack(recipe, "reach", 1);
attacks.setAttack(recipe, "damage", 1);
moves.pick(recipe, "columns", "basic1", "talk", sources);
const kit = attacks.kitOf(recipe, built, offers);
out.refused = ["attacks" in recipe, kit.refused, kit.open];
out.parents = [beamlord, booblord].map(([open, read]) => {
  const k = attacks.kitOf(open, read, offers);
  return [k.values, k.switches, k.parent, k.open, attacks.attacksWhyFixed(open, read)[0],
          attacks.flagText(attacks.listed(open, read, "carry"), tip)[0]];
});
out.garret4 = [attacks.kitOf({ base: "garret4" }, { base: "garret4", mode: "own" }, offers).hidden,
               moves.whyFixed({ base: "garret4" }, { base: "garret4", mode: "own" })];
const spins = given.spins;
out.made = [attacks.playedOf(spins, null, names)[1].map(([, title]) => title)];
attacks.setNumber(spins, "spin", "turns", 3);
attacks.setNumber(spins, "hspin", "tilt_deg", 60.5);
out.made.push(copy(spins));
"""


@pytest.mark.web
def test_the_attacks_tab_writes_the_columns_lists_weapon_and_numbers_the_build_reads(usa_iso, tmp_path, monkeypatch):
    """The Attacks tab (Step 4.6f; Modkit's, D480, D495, D804, X33): life drain writes ``drain`` (its default,
    nearest, no key); the Moves with stick and Chains held menus tick a column into ``carry`` or ``held`` in the
    columns' order (none left: the key out), shown in words or counted; a column picks a clip as the Moves tab does,
    and a recipe clip a column plays takes its ``seek``. The Weapon box offers what the Models view offers its base
    less its weapon (Default, the key out) and, while the recipe plays clips of its own, is refused, saying why; a
    weapon over the columns leaves them out. Reach, Damage and Speed write ``attacks`` multipliers (1: the key out),
    Balance and Reaches the ground show the mode's default while unset (back at it: the key out), Hits through walls
    is off. A recipe from beamlord shows his numbers, from booblord those her Axion staff plays (her moves her
    Booblord spin pick's), read-only, her carry counted; garret4's own body has no weapon row and its columns are
    his to pick. The Clip line edits the numbers of a recipe clip a column plays (booblord's spins). Every recipe
    written is one the loader takes, as the build reads it."""
    monkeypatch.setenv(library.ENV, str(tmp_path / "variants"))
    sources = sdk.move_sources({"iso": str(usa_iso), "species": "town_female_2"})
    built = sdk.variant_read({"name": "mine", "recipe": {"base": "town_female_2", "mode": "own"}})
    offers = sdk.variant_weapons({"iso": str(usa_iso), "name": "mine", "recipe": {"base": "town_female_2"},
                                  "folder": str(tmp_path / "mine")})["weapons"]
    opened = {name: [sdk.variant_open({"name": name})[k] for k in ("recipe", "read")] for name in ("beamlord", "booblord")}
    spins = {k: v for k, v in json.loads(_player_variants.BUILTIN.read_text(encoding="utf-8"))["booblord"].items()
             if k != "weapon"}
    got = _tabs(ATTACKS, {"sources": sources, "offers": offers, "built": built, "spins": spins, **opened})
    columns, tip = sources["columns"], "These columns' swings follow the stick; a held A or B chains them."
    assert got["drain"] == [{"targets": "all"}, False]
    flags = got["flags"][0]
    assert (flags["carry"], flags["held"], got["flags"][1:]) == (["basic1", "basic3"], ["finish"], [
        ["2 columns", f"{tip}\nBasic 1, Basic 3."], "Finish", False, "none"])
    worn = _loaded(flags, tmp_path)
    bit = lambda *names: sum(1 << columns.index(c) for c in names)   # noqa: E731
    assert (_player_variants.carried(worn, columns), _player_variants.held(worn, columns)) == (
        bit("basic1", "basic3"), bit("finish"))
    kick = {"generator": "bake", "body": "garret4", "clip": "attack_back_kick", "seek": True}
    assert (got["seek"][0]["columns"], got["seek"][0]["clips"], got["seek"][1]) == ({"basic1": "g4_1"}, {"g4_1": kick},
                                                                                    ["g4_1"])
    assert _loaded(got["seek"][0], tmp_path).clips["g4_1"]["seek"] is True
    assert got["kit"] == [["Default (Bare hands)", "Axion staff", "Farmer's hoe", "Balthazar's magic", "Booblord spin"],
                          "axion_staff", "Its weapon axion_staff plays every attack: Weapon Default picks clips."]
    assert got["numbers"][0] == {"balance": True, "ground": True, "through_walls": False}
    assert (got["numbers"][1]["attacks"], got["numbers"][2:]) == (
        {"reach": 1.25, "damage": 2, "balance": False, "through_walls": True}, [None, "'fast'"])
    v = _loaded(got["numbers"][1], tmp_path)
    assert (v.reach, v.damage, v.speed, v.balance, v.ground, v.through_walls) == (1.25, 2.0, 1.0, False, None, True)
    assert got["refused"] == [False, "A weapon plays every attack column: clear its columns first.", False]
    him, her = _player_variants.builtins()["beamlord"], _player_variants.builtins()["booblord"]
    theirs = "'s moves (read-only): New from this… makes one to edit."
    assert got["parents"] == [
        [{"reach": him.reach, "damage": him.damage, "speed": him.speed}, {"balance": False, "ground": True,
                                                                          "through_walls": True},
         True, False, "beamlord" + theirs, "none"],
        [{"reach": 1, "damage": 1, "speed": 1}, {"balance": True, "ground": True, "through_walls": False}, True, False,
         "booblord" + theirs + " Its Axion staff plays every attack; these moves are its Booblord spin pick's.",
         f"{len(her.carry)} columns"]]
    assert got["garret4"] == [True, ["", True]]
    assert got["made"][0] == ["hspin (hand_spin)", "pony_whip (gltf)", "spin (t_spin)", "stomp (t_spin)",
                              "twirl (t_spin)"]
    v = _loaded(got["made"][1], tmp_path)
    assert (v.clips["spin"]["turns"], v.clips["hspin"]["tilt_deg"], v.clips["spin"]["length"]) == (3, 60.5, 0.4)
