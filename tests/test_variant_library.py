"""Your own variants (Step 4.6a; Modkit's variant library, D372, D480:
``tools.characters.library``): a folder each in ``AZURKIT_VARIANTS``, its
``recipe.json`` Modkit's format, listed as its recipe or its refusal,
written whole or not at all, worn by name as a built-in is (the share link
and the kept answers with it), and built
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

