"""Your own variants (Step 4.6a; Modkit's variant library, D372, D480:
``tools.characters.library``): a folder each in ``AZURKIT_VARIANTS``, its
``recipe.json`` Modkit's format, listed as its recipe or its refusal,
written whole or not at all, worn by name as a built-in is (the share link,
the kept answers and the Characters tab's Yours group with it), and built
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
from azurkit.tools.characters import content, library
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


#: A community repository's own character (Step 4.38b): a recipe no built-in has the name of, and its entry's note.
MINE = {"variants/mine_lord/variant.json": json.dumps({"mine_lord": {"base": "keylord", "mode": "own", "scale": 1.2,
                                                                    "title": "Mine"}}).encode(),
        "variants/mine_lord/README.md": b"A key lord of a player's own."}


@pytest.fixture
def installs(lib, tmp_path, monkeypatch):
    """``install(entry, files)``: ``files`` (path -> bytes) installed as community entry ``entry`` into a content
    folder in ``tmp_path`` (``content.install``, from a repository of them), which the engine reads (``content.ROOT``),
    beside the empty library ``lib``."""
    root = tmp_path / "content"
    monkeypatch.setattr(content, "ROOT", root)

    def install(entry: str, files: dict[str, bytes], version: int = 1) -> dict:
        repo = tmp_path / f"repo-{entry}"
        for path, data in files.items():
            (repo / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / path).write_bytes(data)
        manifest = content.filled({"format": content.FORMAT, "schema_version": 1, "entries": [
            {"id": entry, "kind": "variant", "title": entry.title(), "author": "a player", "licence": "MIT",
             "version": version, "requires": [], "files": [{"path": path} for path in files]}]},
            lambda path: (repo / path).read_bytes())
        return content.install(manifest, entry, lambda path: (repo / path).read_bytes(), root)
    install.root = root
    return install


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


def test_a_kept_answer_stands_on_the_buffer_a_gltf_reads_beside_it(lib):
    """What a kept Build or Check answer stands on (``library.stamp``, ``library.file_stamp``) holds a named glTF
    as its recipe's pin does, with the ``.bin`` it reads: a weights-only re-export under an unchanged ``.gltf`` is
    new content, as a fresh dress refusing the old pin finds."""
    _write(lib, "glad", json.dumps({"glad": {**LADY, "mesh": {"gltf": {**GLTF, "file": "m.gltf"}}}}))
    (lib / "glad" / "m.gltf").write_text(json.dumps({"asset": {"version": "2.0"},
                                                    "buffers": [{"uri": "m.bin", "byteLength": 4}]}))
    (lib / "glad" / "m.bin").write_bytes(bytes(4))
    stamps = library.stamp("glad"), library.file_stamp(lib / "glad" / library.RECIPE)
    (lib / "glad" / "m.bin").write_bytes(b"\1" * 4)
    assert None not in stamps and all(
        a != b for a, b in zip(stamps, (library.stamp("glad"), library.file_stamp(lib / "glad" / library.RECIPE))))


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


def test_new_from_this_on_each_built_in_dresses_the_built_ins_body_its_springs_where_its_build_places_them(lib):
    """Step 4.6r: New from this on booblord_high (from booblord, her mesh
    finer) keeps booblord's mesh and jiggle as its ``places``, so its
    springs sit where the built-in's build puts them (it refused, her idles'
    bust_bounce 4.2e-03 off the file's pose) and its dress takes the
    built-in's three body parts and shipped places under one key; every
    other built-in's copy holds none (its own mesh places them, or it is
    a copy ``from`` them). A ``places`` with no jiggle is refused by name."""
    from azurkit.tools.characters import shipped
    from azurkit.tools.characters._player_character import _body_keys

    for name, built in variants.builtins().items():
        opened = library.opened(name)
        for f in library.named_files(variants.recipe_of({"probe": opened}, "probe", "probe")[0]):
            (variants.sound_folder(built) / f).parent.mkdir(parents=True, exist_ok=True)
            (variants.sound_folder(built) / f).touch()   # her files as installed (only their names are read)
        recipe = json.loads(library.copy_as(f"{name}_own", opened).read_text(encoding="utf-8"))[f"{name}_own"]
        copy, home = variants.resolve(f"{name}_own"), json.loads(variants.BUILTIN.read_text(encoding="utf-8"))
        assert recipe.get("places") == ({"of": "booblord", "mesh": home["booblord"]["mesh"],
                                          "jiggle": home["booblord"]["jiggle"]} if name == "booblord_high" else None)
        mine, its = variants.placing(copy), variants.placing(built)
        assert (mine is None) == (its is None) == (name not in ("booblord_high", "booblord_high_human")), name
        if built.mesh is not None:
            assert _body_keys(b"", b"", built.base, copy, lib / f"{name}_own", mine) == \
                _body_keys(b"", b"", built.base, built, None, its), name
        if mine is not None:
            assert shipped._places_recipe(built.base, mine) == shipped._places_recipe(built.base, its), name
    with pytest.raises(ValueError, match=r"variant 'bare' \(.*\): places: they place the recipe's jiggle bones, "
                                         "and it has no jiggle"):
        library.save_as("bare", library.new("golem") | {"places": {"of": "booblord", "mesh": home["booblord"]["mesh"],
                                                                     "jiggle": home["booblord"]["jiggle"]}})


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


def test_the_characters_tab_lists_your_variants_in_the_yours_group(lib):
    """The Characters tab's view lists your variants after the community
    group, under Yours (the Variants view's name): each its title, base and grade colour (unseen: no
    sitting graded it), a folder that isn't one with its refusal. One
    picked shows its recipe as yours, never a community entry's (its name
    begins booblord's); a refused one picked says why."""
    library.save_as("booblord_mine", library.new("keylord") | {"title": "Mine"})
    _write(lib, "broken", "{}")
    view = sdk.pickers({"iso": None, "character": {"species": "booblord_mine"}})
    unseen = view["colours"]["unseen"]
    assert view["custom"] == {"title": "Yours", "variants": [
        {"name": "booblord_mine", "title": "Mine", "base": "keylord", "colour": unseen},
        {"name": "broken", "refusal": view["custom"]["variants"][1]["refusal"]}]}
    assert "it holds no recipe" in view["custom"]["variants"][1]["refusal"]
    chosen = view["chosen"]
    assert (chosen["variant"], chosen["community"], chosen["refused"]) == (True, None, None)
    assert ["Source", f"yours, recipe {variants.resolve('booblord_mine').sha}", None] in chosen["info"]
    assert "it holds no recipe" in sdk.pickers({"iso": None, "character": {"species": "broken"}})["chosen"]["refused"]


def test_save_as_copies_files_only_from_the_variant_its_from_names_and_refuses_any_other_from_by_name(lib):
    """Save as and New from this copy the files a recipe names from ``from``'s folder, the variant open: ``from``
    is checked as a new name is, so a path (out of the library), what is no name and a name none of your variants
    has are each refused by name, nothing written."""
    recipe = {"base": "keylord", "mode": "own", "wavs": {"hurt": ["ow.wav"]}}
    _write(lib, "mine", json.dumps({"mine": recipe}))
    (lib / "mine" / "ow.wav").write_bytes(b"RIFF")
    (outside := lib.parent / "outside").mkdir()
    (outside / "ow.wav").write_bytes(b"RIFF")
    for source, why in (("../outside", r"from '\.\./outside': a variant's name is a lower-case letter"),
                        (str(outside), r"from '.*outside': a variant's name is"), (7, r"from 7: a variant's name"),
                        ("nobody", r"from 'nobody': none of your variants has that name")):
        with pytest.raises(ValueError, match=why):
            sdk.variant_save({"name": "unsaved", "recipe": recipe, "as": "copy", "from": source})
        assert sorted(p.name for p in lib.iterdir()) == ["mine"]
    assert sdk.variant_save({"name": "mine", "recipe": recipe, "as": "copy", "from": "mine"})["name"] == "copy"
    assert (lib / "copy" / "ow.wav").read_bytes() == b"RIFF"


def test_an_installed_community_only_character_is_worn_by_name_as_its_entry_after_the_built_ins_and_yours(installs):
    """A community repository's own character (Step 4.38b, D988), a recipe of an installed entry's ``variant.json``
    no built-in has the name of, resolves third, after the built-ins and yours, read as a recipe file is from its
    entry's folder: a build and its options wear it by name, its Source and every line its dress logs name the
    entry and version (``community mine_lord v1``), never the folder; the Models view lists it under its entry,
    the Variants view lists and opens it (its folder the entry's) and its Check takes it by name, a share link
    carries it by name and sha, and New from this copies it as yours. One ``from`` another of its entry (booblord
    and booblord_high's layout) opens laid whole, as it builds, its springs where that one's build puts them, so
    an edit of it Checks and New from this copies it."""
    installs("mine_lord", MINE)
    worn = variants.resolve("mine_lord")
    assert (worn.base, worn.scale, worn.source) == ("keylord", 1.2, str(installs.root / "variants/mine_lord/variant.json"))
    assert content.entry_of(worn.source) == ("mine_lord", 1) and characters.variant({"species": "mine_lord"}, None)[0] is worn
    assert variants.status(worn) == ("unseen", "a community recipe (community mine_lord v1); no sitting graded it")
    view = sdk.pickers({"iso": None, "character": {"species": "mine_lord"}})
    assert [(e["id"], e["variants"]) for e in view["community"]] == [("mine_lord", [
        {"name": "mine_lord", "title": "Mine", "base": "keylord", "colour": view["colours"]["unseen"]}])]
    assert (view["chosen"]["community"], view["chosen"]["refused"]) == ("mine_lord", None)
    assert ["Source", f"community mine_lord v1, recipe {worn.sha}", None] in view["chosen"]["info"]
    assert sdk.variants()["community"] == [{"name": "mine_lord", "title": "Mine", "base": "keylord", "grade": "unseen",
                                            "community": "mine_lord"}]
    opened = sdk.variant_open({"name": "mine_lord"})
    assert (opened["kind"], opened["recipe"], opened["folder"], opened["read"]["sha"]) == (
        "community", json.loads(MINE["variants/mine_lord/variant.json"])["mine_lord"],
        str(installs.root / "variants/mine_lord"), worn.sha)
    assert sdk._editing({"name": "mine_lord"}, "variant_check", image=False)[1] is worn
    link = sdk.preset_encode({"iso": "/nowhere/usa.iso", "packs": {}, "character": {"species": "mine_lord"}})
    assert [la["recipe"] for la in sdk.preset_decode(link)["layers"] if la["tool"] == characters.TOOL] == [
        {"species": "mine_lord", "variant": worn.sha}]
    sdk.variant_save({"name": "unsaved", "recipe": opened["recipe"], "as": "my_lord", "from": "mine_lord"})
    assert variants.resolve("my_lord").sha == worn.sha and variants.resolve("my_lord").source.startswith(
        str(library.root()))
    boob = json.loads(variants.BUILTIN.read_text(encoding="utf-8"))
    pair = {"pair": {k: v for k, v in boob["booblord"].items() if k not in ("wavs", "shouts")},   # no WAV in an entry
            "pair_high": {**boob["booblord_high"], "from": "pair"}}
    installs("pair", {"variants/pair/variant.json": json.dumps(pair).encode(),
                      **{f"variants/pair/{f}": b"x" for f in library.named_files(pair)}})
    opened = sdk.variant_open({"name": "pair_high"})
    assert ("from" in opened["recipe"], opened["recipe"]["places"]["of"], opened["read"].get("refusal")) == (
        False, "pair", None)
    edited = sdk._editing({"name": "unsaved", "recipe": {**opened["recipe"], "title": "Mine"}, "folder": opened["folder"]},
                          "variant_check", image=False)[1]
    sdk.variant_save({"name": "unsaved", "recipe": opened["recipe"], "as": "my_high", "from": "pair_high"})
    assert len({repr((p.name, p.mesh, p.jiggle)) for p in map(variants.placing, (
        variants.resolve("pair_high"), edited, variants.resolve("my_high")))}) == 1


def test_a_community_character_is_refused_by_name_where_its_files_arent_as_installed_or_its_name_is_taken(installs):
    """A community-only character is read only once its entry's files are those ``installed.json`` records (an
    altered or moved file refused by name, its sha256s' first 12 digits beside it; an altered recipes file never
    read, so none of its names reaches a view: one row under its entry's id refuses it), names only files its entry
    lists, and never stands in for a built-in or yours (what a link or a saved setup already names): an entry whose
    recipe has a built-in's name with another recipe is refused at Install, one holding the built-in's own recipe
    lists that built-in and the name is the built-in's (one from a built-in reads that one's files); one named as yours lists refused and yours is worn; one
    named as a species, or held by two entries, is refused by name. A link of a community character whose recipe
    changed names the Install or Update to make."""
    installs("mine_lord", MINE)
    sha = variants.resolve("mine_lord").sha
    link = sdk.preset_encode({"iso": "/nowhere/usa.iso", "packs": {}, "character": {"species": "mine_lord"}})
    recipe = installs.root / "variants/mine_lord/variant.json"
    recipe.write_bytes(json.dumps({"mine_lord": {"base": "keylord", "mode": "own", "scale": 3.0},
                                   "<b>Odd</b> ../name": {}, "y" * 300: {}}).encode())
    assert [(r["name"], "isn't the file installed" in r["refusal"]) for r in sdk.variants()["community"]] == [
        ("mine_lord", True)]
    for why in (r"variant 'mine_lord': community entry 'mine_lord': variants/mine_lord/variant\.json isn't the file "
                r"installed \(its sha256 [0-9a-f]{12}, installed [0-9a-f]{12}\): Install it again",):
        with pytest.raises(ValueError, match=why):
            variants.resolve("mine_lord")
    recipe.unlink()
    with pytest.raises(ValueError, match=r"variants/mine_lord/variant\.json isn't in the content folder \(moved"):
        variants.resolve("mine_lord")
    installs("mine_lord", {**MINE, "variants/mine_lord/variant.json": json.dumps(
        {"mine_lord": {"base": "keylord", "mode": "own", "scale": 3.0}}).encode()}, version=2)
    with pytest.raises(ValueError, match=rf"'mine_lord' is recipe {sha} there and recipe \w+ here: Install or Update"):
        sdk.preset_decode(link)
    beam = json.loads(variants.BUILTIN.read_text(encoding="utf-8"))["beamlord"]
    with pytest.raises(ValueError, match=r"beam_fake: variants/beam_fake/variant\.json's beamlord is recipe \w+, not "
                                         r"the built-in beamlord's"):
        installs("beam_fake", {"variants/beam_fake/variant.json": json.dumps({"beamlord": {**beam, "scale": 9.0}}).encode()})
    installs("beam_copy", {"variants/beam_copy/variant.json": json.dumps({"beamlord": beam}).encode()})
    installs("keylord_pack", {"variants/keylord_pack/variant.json": json.dumps({"keylord": {"base": "golem"}}).encode()})
    for entry in ("twin_a", "twin_b"):
        installs(entry, {f"variants/{entry}/variant.json": json.dumps({"twin": {"base": "keylord"}}).encode()})
    installs("lister", {"variants/lister/variant.json": json.dumps({"lister": {"base": "town_female_2", "mesh": {
        "gltf": {"file": "body.glb", "sha256": "0" * 64}}}}).encode()})
    (installs.root / "variants/lister/body.glb").write_bytes(b"glTF not listed")
    installs("from_boob", {"variants/from_boob/variant.json": json.dumps({"from_boob": {"from": "booblord"}}).encode()})
    library.save_as("yours_too", library.new("keylord"))
    installs("yours_too", {"variants/yours_too/variant.json": json.dumps({"yours_too": {"base": "golem"}}).encode()})
    assert variants.resolve("beamlord") is variants.builtins()["beamlord"] and variants.resolve("keylord") is None
    assert variants.resolve("yours_too").base == "keylord"
    refused = {r.name: r.refusal for r in content.community()}
    for name, why in (("keylord", "a species has that name"), ("twin", "community entries twin_a, twin_b each hold it"),
                      ("lister", r"\(variants/lister/variant\.json\): it names 'body\.glb', which community entry "
                                 r"'lister' doesn't list"),
                      ("yours_too", "one of yours has that name, which a build wears in its place")):
        assert re.search(why, refused.pop(name)), name
    assert refused == {"mine_lord": None, "from_boob": None}   # from a built-in: its files the built-in's
    for name in ("twin", "lister"):
        with pytest.raises(ValueError, match=f"variant '{name}'"):
            characters.variant({"species": name}, None)
    rows = {e["id"]: e["variants"] for e in sdk.pickers({"iso": None, "character": {"species": "garret4"}})["community"]}
    assert ([(v["name"], "refusal" in v) for v in rows["beam_copy"]], [(v["name"], "refusal" in v)
                                                                       for v in rows["twin_a"]]) == (
        [("beamlord", False)], [("twin", True)])


def test_a_community_only_characters_check_dresses_it_on_the_image_as_a_build_and_its_log_names_its_entry(
        usa_iso, no_content, installs):  # noqa: F811
    """The Variants view's Check of an installed community-only character by name (Step 4.38b) dresses it on the
    image as a build of it does (the build's plan): no refusal, its recipe's sha, and its log names its entry and
    version, never the content folder's path."""
    installs("mine_lord", MINE)
    found = sdk.variant_check({"iso": str(usa_iso), "name": "mine_lord"})
    assert (found["refusal"], found["sha"]) == (None, variants.resolve("mine_lord").sha)
    assert any("(recipe " in line and "community mine_lord v1" in line for line in found["log"])
    assert str(installs.root) not in json.dumps(found["log"])


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
    path outside its folder, a member it can't read and what is no zip or
    recipe; Delete removes it."""
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
                      (b"PK not a zip", "not a zip"), (b"[1]", "holds one recipe"),
                      (_zip({"c/recipe.json": b'{"c": {"base": "keylord"}}', "c/ow.wav": b"RIFFWAVE"}).replace(
                          b"RIFFWAVE", b"RIFFWAVF"), "'c/ow.wav' can't be read")):   # a stored member's bad CRC
        with pytest.raises(ValueError, match=why):
            sdk.variant_import({"data": data})
    sdk.variant_delete({"name": "lady"})
    assert [e["name"] for e in sdk.variants()["yours"]] == ["beam", "broken", "solo"]


def test_the_shape_and_jiggle_tabs_read_each_shape_its_mesh_ops_and_springs_as_the_recipe_builds(lib):
    """The Variants view's Shape and Jiggle tabs (Step 4.6d; Modkit's
    ``ShapeTab.load`` and ``JiggleTab._jiggle``), from ``variant_read``: a
    recipe from booblord reads her shapes, each its value as built (its own
    over hers), the value its key drops back at (hers) and what it sizes
    in words, her mesh's ops with the sized first, and her springs as it
    builds them until it has a jiggle of its own; one of its own reads its
    shape's value with no value to drop at; a body with no mesh reads none
    of either. Modkit's tabs read the same rows of these recipes."""
    her = json.loads(variants.BUILTIN.read_text(encoding="utf-8"))["booblord"]
    own = json.loads(json.dumps(her["jiggle"]))
    own["bones"][0]["spring"]["damping"] = 0.3
    hips = {"base": "town_female_2", "mesh": {"ops": [
        {"op": "scale", "name": "pelvis", "profile": "smooth", "bone": "root_joint", "offset": [0.0, -0.033, -0.175],
         "radius": [0.4, 0.16, 0.22], "factors": [1.4, 1.0, 1.0]}]},
        "shapes": {"hips": {"title": "Hips", "ops": ["pelvis"], "value": 1.3}}}
    read = {name: sdk.variant_read({"name": name, "recipe": recipe}) for name, recipe in (
        ("hers", {"from": "booblord"}), ("mine", {"from": "booblord", "shapes": {"bust": {"value": 1.2}}, "jiggle": own}),
        ("hips", hips), ("plain", {"base": "keylord", "mode": "own"}))}
    got = {name: ([(s["name"], s["value"], s["at"]) for s in r["shapes"]], r["ops"][:1] + r["ops"][-1:],
                  r["jiggle"] == her["jiggle"], r["jiggle"] == own) for name, r in read.items()}
    ends = [["pelvis", "scale", "Hip width < 1"], ["strap's neck edge out", "push", ""]]   # sized first, then the rest
    assert got == {"hers": ([("bust", 1.0, 1.0), ("hips", 1.0, 1.0), ("butt", 1.0, 1.0)], ends, True, False),
                   "mine": ([("bust", 1.2, 1.0), ("hips", 1.0, 1.0), ("butt", 1.0, 1.0)], ends, False, True),
                   "hips": ([("hips", 1.3, None)], [["pelvis", "scale", "Hips"]] * 2, False, False),
                   "plain": ([], [], False, False)}
    assert {(tuple(r["track"]), r["rows_max"]) for r in read.values()} == {((0.5, 1.4, 0.05), 32)}
    assert [s["sizes"] for s in read["hers"]["shapes"]] == [
        "Bust size sizes breast (both sides), 2 layers.",
        "Hip width sizes hip (both sides); hip bone (both sides), and below 1 pelvis too.",
        "Butt size sizes glute (both sides), and turns out loincloth back 1 70° a unit over 1."]
    assert read["plain"]["jiggle"] is None and read["mine"]["sha"] != read["hers"]["sha"]
