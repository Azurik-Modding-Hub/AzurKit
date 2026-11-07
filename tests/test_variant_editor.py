"""The Variants editor's engine (Step 4.6b; Modkit's Variants page's
engine half, ``authoring/colour_preview.py`` and ``variant_library.py``'s
calls past the library's rules): the colour views
(``tools/characters/colour_preview.py``) and the sdk's ``variant_*`` calls
(``tools/characters/editor.py``): what a base species' tabs read, an
edit's refusals by name, Check with game data, the quick shape preview and
the rows' PNG round trip."""

from __future__ import annotations

import hashlib
import json
import math
import re
import wave

import numpy as np
import pytest

from azurkit import sdk
from azurkit.app import engine
from azurkit.core import iso
from azurkit.tools import characters
from azurkit.tools.characters import _player_variants, colour_preview
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


def test_a_check_dresses_a_built_in_and_one_it_cant_dress_still_lists_its_bases_bones(usa_iso, tmp_path):
    """Check with game data (Modkit's ``check``) dresses beamlord as a build of him does: no refusal, its sha, the
    dressed body and its bones, its own load runs under its build's lines, each effects row's bytes (he has none) and
    his picture; a recipe whose glTF isn't in its folder can't dress, and says so by its file in that folder with its
    base's own bones (where its springs rows go)."""
    found = sdk.variant_check(_given(usa_iso, tmp_path, name="beamlord"))
    assert (found["refusal"], found["sha"], found["body"], len(found["bones"])) == (None, "628f6d09ad7b",
                                                                                     "balthazar_airship", 135)
    assert 0 < found["load"]["own"] < found["load"]["error"] and found["log"]
    assert len(found["effects"]) == len(_player_variants.builtins()["beamlord"].effects)
    assert art.unpng(found["front"]).shape == art.unpng(found["back"]).shape == (160, 160, 4)
    glb = {"base": "town_female_2", "mesh": {"gltf": {"file": "body.glb", "sha256": "0" * 64}}}
    cant = sdk.variant_check(_given(usa_iso, tmp_path, glb))
    assert str(tmp_path / "mine" / "body.glb") in cant["refusal"]
    assert cant["bones"] == sdk.base_bones({"iso": str(usa_iso), "species": "town_female_2"})["bones"]


def test_the_quick_preview_puts_each_drawn_vertex_where_a_dress_at_those_values_does(usa_iso, tmp_path):
    """The Shape tab's preview (Modkit's ``preview``) moves the last Check's drawn vertices to a shape's new value
    with no dress: HIPS' pelvis at 1.5 drawn as a Check of it at 1.5 draws it (its scale op makes no new vertex, so
    every one is found), in a fraction of a second; one whose mesh changed beyond its shapes asks for the Check."""
    given = _given(usa_iso, tmp_path, HIPS)
    first = sdk.variant_check(given)
    wider = json.loads(json.dumps(HIPS))
    wider["shapes"]["hips"]["value"] = 1.5
    quick = sdk.variant_preview(given | {"recipe": wider})
    assert quick["front"] != first["front"] and quick["seconds"] < 3
    assert {k: quick[k] for k in ("front", "back")} == {k: sdk.variant_check(given | {"recipe": wider})[k]
                                                        for k in ("front", "back")}
    other = json.loads(json.dumps(HIPS))
    other["mesh"]["ops"][0]["bone"] = "spine_1"
    with pytest.raises(ValueError, match="Check with game data dresses it"):
        sdk.variant_preview(given | {"recipe": other})


def test_a_rows_png_exports_and_an_edited_one_comes_back_as_the_rows_texture(usa_iso, tmp_path):
    """The Colours tab's round trip (Step 2.203): Export writes each row's texture whole as its build recolours it;
    an edited one comes back (``add_png``: its name and sha256) as the row's ``png`` op, which the rows and the views
    then draw; a WAV comes in under a name a recipe's ``wavs`` take, the same bytes once. The app's engine runs the
    views, its pictures base64."""
    out, folder = tmp_path / "out", tmp_path / "mine"
    given = _given(usa_iso, tmp_path, {"base": "town_female_2", "colours": HUMAN})
    written = sdk.export_pngs(given | {"out": str(out)})["files"]
    assert written == [f"mine_row{r}.png" for r in range(4)]
    row = 255 - art.unpng((out / written[0]).read_bytes())
    row[..., 3] = 255
    (tmp_path / "edited.png").write_bytes(colour_preview.pngs("e", {0: row})["e_row0.png"])
    op = sdk.add_png({"folder": str(folder), "file": str(tmp_path / "edited.png"),
                      "size": sdk.variant_rows(given)["sizes"]["0"]})
    assert op["name"] == "edited.png" and (folder / "edited.png").is_file()
    edited = _given(usa_iso, tmp_path, {"base": "town_female_2", "colours": [
        {"row": 0, "ops": [{"op": "png", "file": op["name"], "sha256": op["sha256"]}]}]})
    assert np.array_equal(art.unpng(sdk.variant_rows(edited)["files"]["mine_row0.png"]), row)
    assert sdk.variant_colours(edited)["front"] != sdk.variant_colours(given)["front"]
    assert engine.JOBS["variant_colours"](given) == engine._shown(sdk.variant_colours(given))
    with wave.open(str(tmp_path / "my take.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x01\x00" * 2205)
    assert [sdk.add_wav({"folder": str(folder), "file": str(tmp_path / "my take.wav")})["name"] for _ in "ab"] == [
        "my_take.wav", "my_take.wav"]
