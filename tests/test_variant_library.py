"""Your own variants (Step 4.6a; Modkit's variant library, D372, D480:
``tools.characters.library``): a folder each in ``AZURKIT_VARIANTS``, its
``recipe.json`` Modkit's format, listed as its recipe or its refusal,
written whole or not at all, worn by name as a built-in is (the share link,
the kept answers and the Characters tab's Custom group with it), and built
as Modkit built it (the probe golden, by sha256)."""

from __future__ import annotations

import json
import re

import pytest

from azurkit import sdk
from azurkit.app import ahead
from azurkit.core import gate, iso
from azurkit.tools import characters
from azurkit.tools.characters import _player_variants as variants
from azurkit.tools.characters import library
from tests.test_characters import _golden, _probe, no_content  # noqa: F401 (a fixture)

GLTF = {"file": "nowhere.glb", "sha256": "0" * 64}
LADY = {"base": "town_female_2", "mesh": {"gltf": GLTF}, "wavs": {"hurt": ["ow.wav"]}}


@pytest.fixture
def lib(tmp_path, monkeypatch):
    """An empty library in ``tmp_path`` (``AZURKIT_VARIANTS``), its built-ins' sounds and clips folders empty too
    (a content folder with nothing installed)."""
    folder = tmp_path / "variants"
    monkeypatch.setenv(library.ENV, str(folder))
    monkeypatch.setattr(variants, "SOUNDS", tmp_path / "content" / "sounds")
    monkeypatch.setattr(variants, "CLIPS", tmp_path / "content" / "clips")
    return folder


def _write(folder, name: str, text: str) -> None:
    (folder / name).mkdir(parents=True)
    (folder / name / library.RECIPE).write_text(text, encoding="utf-8")


def test_the_library_lists_each_folder_as_its_recipe_or_its_refusal_and_a_build_finds_it_by_name(lib):
    """Each folder of the library is listed by name: one whose recipe.json
    holds one recipe named as the folder loads as a recipe file's recipe
    does, the same Variant until the file changes, and a build's
    ``resolve`` finds it by name after the built-ins; one that holds two
    recipes, a built-in's or a species' name, nesting past 64, no
    recipe.json or what the loader refuses (a file outside its folder
    among them) is refused by name, and so is a build naming it. Of the files a recipe names only
    its WAVs are yours to share (D393)."""
    _write(lib, "my_lady", json.dumps({"my_lady": LADY}))
    for name, doc in (("two", {"two": {"base": "keylord"}, "other": {"base": "keylord"}}),
                      ("booblord", {"booblord": {"base": "keylord"}}), ("keylord", {"keylord": {"base": "golem"}}),
                      ("escape", {"escape": {"base": "keylord", "mesh": {"gltf": {**GLTF, "file": "../edit.glb"}}}}),
                      ("odd", {"odd": {"base": "keylord", "mode": []}}),
                      ("unknown", {"unknown": {"base": "keylord", "wings": 2}})):
        _write(lib, name, json.dumps(doc))
    _write(lib, "deep", "[" * 100 + "]" * 100)
    _write(lib, "torn", '{"torn": {"base": ')
    (lib / "empty").mkdir()
    (lib / ".writer.part-1").mkdir()
    refusals = {e.name: e.refusal for e in library.listing()}
    assert refusals.pop("my_lady") is None
    for name, why in (("booblord", r"variant 'booblord' \(.*\): a built-in variant has that name"),
                      ("deep", r"deep.recipe\.json: not a recipe \(it nests deeper than 64\)"),
                      ("empty", r"empty: no recipe\.json"),
                      ("escape", r"variant 'escape' \(.*\): mesh\.gltf\.file: '\.\./edit\.glb' is not a file in "
                                 r"the recipe's folder"),
                      ("keylord", r"variant 'keylord': a species has that name"),
                      ("odd", r"odd.recipe\.json: not a recipe \(TypeError"),
                      ("torn", r"variants \(.*torn.recipe\.json\): not JSON"),
                      ("two", r"two.recipe\.json: it holds 'two', 'other'; .* named as the folder \('two'\)"),
                      ("unknown", r"variant 'unknown' \(.*\).*wings")):
        assert re.search(why, refusals.pop(name)), (name, refusals.get(name))
    assert refusals == {}
    mine = next(e.variant for e in library.listing() if e.name == "my_lady")
    assert mine.source == str(lib / "my_lady" / library.RECIPE)
    assert [variants.resolve(n) for n in ("my_lady", "keylord", "booblord", "nobody")] == [
        mine, None, variants.builtins()["booblord"], None] and variants.resolve("my_lady") is mine
    with pytest.raises(ValueError, match=r"two.recipe\.json: it holds 'two', 'other'"):
        characters.variant({"species": "two"}, None)
    assert library.unshareable(lib / "my_lady") == ["nowhere.glb"]
    stamp = library.stamp("my_lady")
    (lib / "my_lady" / "ow.wav").write_bytes(b"RIFF")
    assert library.stamp("my_lady") != stamp and library.stamp("keylord") is library.stamp("booblord") is None
    (lib / "my_lady" / library.RECIPE).write_text(json.dumps({"my_lady": {**LADY, "scale": 1.2}}), encoding="utf-8")
    assert variants.resolve("my_lady").sha != mine.sha


def test_new_new_from_this_save_save_as_and_delete_write_whole_or_nothing(lib):
    """New is a recipe on a species' own body; Save as makes a folder of
    it with the files it names, Save writes it again and Delete removes the
    folder. New from this and Save as on a built-in make one own copy: its
    recipe laid whole with no ``from`` (beamlord's sha), and one whose
    files no folder holds (booblord's, nothing installed) is refused naming
    the file. A bad recipe, a taken, malformed, built-in's or species' name
    and a missing file are each refused by name with nothing written, the
    saved file as it was and no writer's folder left."""
    file = library.save_as("mine", library.new("keylord"))
    assert file == lib / "mine" / library.RECIPE and json.loads(file.read_text(encoding="utf-8")) == {
        "mine": {"base": "keylord", "mode": "own"}} and library.new("garret4") == {"base": "garret4"}
    assert library.save("mine", {"base": "keylord", "scale": 1.5}) == file and variants.resolve("mine").scale == 1.5
    before = file.read_bytes()
    beam = library.copy_as("beam", library.opened("beamlord"))
    assert "from" not in json.loads(beam.read_text(encoding="utf-8"))["beam"]
    assert variants.resolve("beam").sha == variants.builtins()["beamlord"].sha
    assert library.opened("beam") == json.loads(beam.read_text(encoding="utf-8"))["beam"]
    for write, why in (
            (lambda: library.save("mine", {"base": "keylord", "wings": 2}), r"variant 'mine' \(.*\).*wings"),
            (lambda: library.save_as("mine", library.new("golem")), r"variant 'mine': .* exists"),
            (lambda: library.save_as("Mine", library.new("golem")), r"'Mine': a variant's name is a lower-case"),
            (lambda: library.save_as("booblord", library.new("golem")), r"a built-in variant has that name"),
            (lambda: library.save_as("golem", library.new("golem")), r"variant 'golem': a species has that name"),
            (lambda: library.save_as("lady", LADY, lib), r"variant 'lady': it names 'nowhere\.glb', 'ow\.wav'"),
            (lambda: library.copy_as("boob", library.opened("booblord")), r"variant 'boob': it names '.*', which "
                                                                          r"none of .* holds"),
            (lambda: library.own_copy("other", library.new("golem")), r"an own copy is of a recipe from a built-in"),
            (lambda: library.delete("nobody"), r"variant 'nobody': the library \(.*\) has no such folder")):
        with pytest.raises(ValueError, match=why):
            write()
    assert sorted(p.name for p in lib.iterdir()) == ["beam", "mine"] and file.read_bytes() == before
    assert sorted(p.name for p in (lib / "mine").iterdir()) == [library.RECIPE]
    library.delete("mine")
    assert [e.name for e in library.listing()] == ["beam"] and variants.resolve("mine") is None


def test_a_link_and_the_kept_answers_carry_your_variant_by_its_recipe(lib, monkeypatch):
    """A share link carries a variant of yours by name and its recipe's
    sha, as a built-in's (Q174), and reads back where it is; once it is
    edited the link names the recipe it was, and once it is gone what to
    import. The keys an answer is kept under (the app's store, its work
    ahead) change with what its build reads."""
    library.save_as("mine", library.new("keylord"))
    link = sdk.preset_encode({"iso": "/nowhere/usa.iso", "packs": {}, "character": {"species": "mine"}})
    sha = variants.resolve("mine").sha
    assert [la["recipe"] for la in sdk.preset_decode(link)["layers"] if la["tool"] == characters.TOOL] == [
        {"species": "mine", "variant": sha}]
    monkeypatch.setattr(characters, "CACHE", object())
    keys = (characters.cache_key("plan", {"species": "mine"}, gate.USA),
            ahead.key({"character": {"species": "mine"}}))
    library.save("mine", {"base": "keylord", "scale": 2.0})
    assert all(a != b for a, b in zip(keys, (characters.cache_key("plan", {"species": "mine"}, gate.USA),
                                             ahead.key({"character": {"species": "mine"}}))))
    with pytest.raises(ValueError, match=rf"'mine' is recipe {sha} there and recipe \w+ in your variants: import"):
        sdk.preset_decode(link)
    library.delete("mine")
    with pytest.raises(ValueError, match=rf"'mine' is a variant \(recipe {sha}\) this AzurKit has no recipe of: "
                                         r"install it .* or import its recipe file as one of yours"):
        sdk.preset_decode(link)


def test_a_saved_variant_builds_as_modkit_built_it(usa_iso, lib, no_content, tmp_path):  # noqa: F811
    """The probe variant (a subdivided, deformed mesh grown a tube, painted
    and coloured, on jiggle springs, a shape sized, worn with a weapon:
    ``probes.json``, first recorded from Modkit's build), saved as yours
    and worn by name with no recipe file, gives every file its golden's
    sha256 and characters.xbr's and fx.xbr's resources as the golden's; the
    layer holds its recipe's sha at that shape and no folder of the library."""
    probe = _golden("probes.json")["variant:probe,shape=hips=1.2,weapon=farmers_hoe"]
    library.save_as("probe", probe["variants"]["probe"])
    assert [e.name for e in library.listing()] == ["probe"] and variants.resolve("probe").source.startswith(str(lib))
    with iso.Reader(usa_iso) as r:
        vanilla = {f: r.read(f) for f in characters.FILES}
    want, got, layer = _probe({k: v for k, v in probe.items() if k != "variants"}, gate.USA, usa_iso, vanilla,
                              tmp_path)
    assert got == want and layer.recipe["variant"] == variants.reshaped(variants.resolve("probe"), {"hips": 1.2}).sha
    assert str(lib) not in json.dumps([layer.recipe, layer.notes])


def test_the_characters_tab_lists_your_variants_in_the_custom_group(lib):
    """The Characters tab's view lists your variants after the community
    group, under Custom: each its title, base and grade colour (unseen: no
    sitting graded it), a folder that isn't one with its refusal. One
    picked shows its recipe as yours, never a community entry's (its name
    begins booblord's); a refused one picked says why."""
    library.save_as("booblord_mine", library.new("keylord") | {"title": "Mine"})
    _write(lib, "broken", "{}")
    view = sdk.pickers({"iso": None, "character": {"species": "booblord_mine"}})
    unseen = view["colours"]["unseen"]
    assert view["custom"] == {"title": "Custom", "variants": [
        {"name": "booblord_mine", "title": "Mine", "base": "keylord", "colour": unseen},
        {"name": "broken", "refusal": view["custom"]["variants"][1]["refusal"]}]}
    assert "it holds no recipe" in view["custom"]["variants"][1]["refusal"]
    chosen = view["chosen"]
    assert (chosen["variant"], chosen["community"], chosen["refused"]) == (True, None, None)
    assert ["Source", f"yours, recipe {variants.resolve('booblord_mine').sha}", None] in chosen["info"]
    assert "it holds no recipe" in sdk.pickers({"iso": None, "character": {"species": "broken"}})["chosen"]["refused"]


def _zip(files: dict[str, bytes]) -> bytes:
    import io
    import zipfile

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for path, data in files.items():
            z.writestr(path, data)
    return out.getvalue()


def test_the_variants_views_calls_open_read_save_import_and_export_whole_or_refused_by_name(lib):
    """The Variants view's engine calls (Step 4.6c): the list holds the
    built-ins, your folders (a refused one with its refusal) and the species
    New starts on; a built-in opens as a recipe ``from`` it, read with its
    sha and grade, and an edit of it reads unseen; a recipe the loader
    refuses reads as its refusal, never raised. Save as on a built-in makes
    its own copy and hands back its files (the site keeps them); Save writes
    it again, a refused one writes nothing. Export packs a folder with the
    files its recipe names, naming those not yours to share (a mesh: D393);
    Import makes a folder of an Export's zip or a recipe.json alone, its
    other files left out, and refuses by name a taken name, two recipes, a
    path outside its folder and what is no zip or recipe; Delete removes it."""
    import hashlib
    import io
    import zipfile

    _write(lib, "broken", "{}")
    listed = sdk.variants()
    assert (listed["root"], [b["name"] for b in listed["builtins"]], listed["unsaved"]) == (
        str(lib), list(variants.builtins()), sdk.UNSAVED)
    assert listed["yours"][0]["name"] == "broken" and "it holds no recipe" in listed["yours"][0]["refusal"]
    assert "keylord" in listed["species"] and "beamlord" not in listed["species"]
    opened = sdk.variant_open({"name": "beamlord"})
    beam = variants.builtins()["beamlord"]
    assert (opened["kind"], opened["recipe"]["from"], opened["read"]["sha"], opened["read"]["grade"]) == (
        "built-in", "beamlord", beam.sha, sdk._grade(beam))
    edited = {**opened["recipe"], "title": "Mine"}
    assert sdk.variant_read({"name": "unsaved", "recipe": edited, "built_in": "beamlord"})["grade"] == "unseen"
    assert "'flying'" in sdk.variant_read({"name": "unsaved", "recipe": {"base": "keylord", "mode": "flying"}})["refusal"]
    copy = sdk.variant_save({"name": "unsaved", "recipe": opened["recipe"], "as": "beam", "files": True})
    assert copy["folder"] == str(lib / "beam") and "from" not in json.loads(copy["files"][library.RECIPE])["beam"]
    sdk.variant_save({"name": "beam", "recipe": {"base": "keylord", "scale": 1.5}})
    before = (lib / "beam" / library.RECIPE).read_bytes()
    with pytest.raises(ValueError, match="wings"):
        sdk.variant_save({"name": "beam", "recipe": {"base": "keylord", "wings": 2}})
    assert (lib / "beam" / library.RECIPE).read_bytes() == before
    glb = b"glTF fake body"
    lady = {"base": "town_female_2", "mesh": {"gltf": {"file": "body.glb", "sha256": hashlib.sha256(glb).hexdigest()}},
            "wavs": {"hurt": ["ow.wav"]}}
    made = sdk.variant_import({"data": _zip({"lady/recipe.json": json.dumps({"lady": lady}).encode(), "lady/body.glb": glb,
                                             "lady/ow.wav": b"RIFF", "lady/junk.txt": b"x"})})
    assert made["name"] == "lady" and sorted(p.name for p in (lib / "lady").iterdir()) == ["body.glb", "ow.wav",
                                                                                           library.RECIPE]
    out = sdk.variant_export({"name": "lady"})
    assert (out["name"], out["unshareable"]) == ("lady.zip", ["body.glb"])
    assert sorted(zipfile.ZipFile(io.BytesIO(out["zip"])).namelist()) == ["lady/body.glb", "lady/ow.wav",
                                                                           "lady/recipe.json"]
    assert sdk.variant_import({"data": json.dumps({"solo": {"base": "keylord"}}).encode()})["name"] == "solo"
    for data, why in ((out["zip"], r"variant 'lady': .* exists"),
                      (_zip({"a/recipe.json": b"{}", "b/recipe.json": b"{}"}), "holds 2 recipe.json files"),
                      (_zip({"x/recipe.json": b'{"x": {"base": "keylord"}}', "y/z.wav": b""}), "outside the variant's"),
                      (b"PK not a zip", "not a zip"), (b"[1]", "holds one recipe")):
        with pytest.raises(ValueError, match=why):
            sdk.variant_import({"data": data})
    sdk.variant_delete({"name": "lady"})
    assert [e["name"] for e in sdk.variants()["yours"]] == ["beam", "broken", "solo"]
