"""The archive writers a character swap builds on (Step 4.3a1; the models
family's source, ported by the sync): ``core.xbr.append`` (new resources,
their relocations and named rows, grown payloads), ``index.xbr``'s records,
the body codec; the character layer's whole-file group; and the swap's XBE
hooks in the facts. Checked on the player's images and against the oracle
at its models tag: ``resources.json`` (one sha256 per XBR resource of each
G3 build that wears a model, Modkit's own builds) and G3's per-file hashes."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

import shimkit
from azurkit import sdk
from azurkit.core import coff, facts, gate, iso
from azurkit.core.xbr.append import PAGE, NewResource, append_resources, appended
from azurkit.core.xbr.nodes import named_resources, parse_toc, runs
from azurkit.edits import manifest as edits_manifest
from azurkit.edits.layer import Layer, compose
from azurkit.edits.manifest import image
from azurkit.tools import characters, mods
from azurkit.tools.characters import _player_kit, _player_variants, content, ports
from azurkit.tools.characters import body_codec as bc
from azurkit.tools.characters.index_xbr import IndexRecord, add_index_records, parse_index_xbr
from scripts import gen_facts
from tests import _pyodide

MODELS = gen_facts.ORACLE / "models"
CHARACTERS, FX, INDEX = characters.FILES
G3 = {"usa": "tests/goldens/pipelines.json", "europe": "tests/goldens/europe/pipelines.json"}
RELEASES = [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
            pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe], id="europe")]


def _sha256(data) -> str:
    return hashlib.sha256(data).hexdigest()


def _oracle(rel: str) -> dict:
    return json.loads((MODELS / rel).read_text(encoding="utf-8"))


def _payload(data: bytes, e) -> bytes:
    return data[e.file_offset:e.file_offset + e.size]


def test_every_body_reads_and_encodes_back_and_appended_resources_resolve_by_name(usa_iso):
    """Each of characters.xbr's 158 bodies decodes and encodes back byte for
    byte (its ``body`` and each LOD's ``bmsh``; both releases hold the same
    file), and a body written back unchanged leaves the file as it was.
    Appending nothing changes nothing; 186 clips appended (one past what
    the TOC's page holds, so the data area moves a page) with a body grown
    in place resolve by their names to their payloads, each on a page and
    in a load run of its own, while every old payload, offset, per-tag
    row, relocation and named row stays as it was."""
    with iso.Reader(usa_iso) as r:
        data = r.read(CHARACTERS)
    toc, names = parse_toc(data), named_resources(data)
    bodies = [n.removeprefix("characters/") for i, n in names.items() if toc[i].tag == "body"]
    assert len(bodies) == 158
    for name in bodies:
        asset = bc.read_asset(data, name)
        assert bc.encode_body(asset)[0] == _payload(data, toc[asset.index]), name
        for lod in asset.lods:
            assert bc.encode_bmsh(lod)[0] == _payload(data, toc[lod.bmsh]), name
    assert bc.write_asset(data, bc.read_asset(data, "townspeople/female_2")) == data
    assert append_resources(data) is data and appended(len(toc), data) == []

    index_of = {name: i for i, name in names.items()}
    clips = sorted(n for i, n in names.items() if toc[i].tag == "banm" and n.startswith("characters/garret4/"))
    new = [NewResource(f"characters/balthazar_airship/g4/{j}/{n.rsplit('/', 1)[1]}", "banm",
                       _payload(data, toc[index_of[n]])) for j in (0, 1) for n in clips][:186]
    body = index_of["characters/balthazar_airship"]
    grown_body = _payload(data, toc[body]) + bytes(1024)
    grown = append_resources(data, new, rewrite={body: grown_body})
    toc2, names2 = parse_toc(grown), named_resources(grown)
    h, h2 = (struct.unpack_from("<15I", d) for d in (data, grown))
    assert (len(new), h2[4] - h[4], h2[6] % PAGE, h2[13] + h2[14] - len(grown)) == (186, PAGE, 0, 0)
    assert {names2[i]: (toc2[i].tag, toc2[i].rel_offset % PAGE, _payload(grown, toc2[i]))
            for i in range(len(toc), len(toc2))} == {r.name: ("banm", 0, r.payload) for r in new}
    assert all(runs(grown).of[i] == i for i in range(len(toc), len(toc2)))
    assert [e.index for e, e2 in zip(toc, toc2) if (e.rel_offset, e.tag, e.flags) != (e2.rel_offset, e2.tag, e2.flags)
            or (e.index != body and _payload(data, e) != _payload(grown, e2))] == []
    assert _payload(grown, toc2[body]) == grown_body
    assert (data[h[6]:h[12] + 8 * h[11]], data[h[13]:h[13] + h[14]]) == (
        grown[h2[6]:h2[12] + 8 * h[11]], grown[h2[13]:h2[13] + h[14]])
    assert [(r.name, r.payload) for r in appended(len(toc), grown)] == [(r.name, r.payload) for r in new]


@pytest.mark.parametrize("release", RELEASES)
def test_each_model_cases_index_xbr_is_modkits_file_for_file(release, request):
    """index.xbr reads back (USA's 3,072 records, Europe's 3,730) and adding
    no record leaves it as it was. Each G3 case of the
    oracle's models family on the release that changes index.xbr adds its
    records (``resources.json``: those its build added, in the order it
    added them, each naming a resource the case appended to its archive
    with that fourcc), and the file is Modkit's, byte for byte: the sha256
    of G3's golden and of ``resources.json``'s file."""
    with iso.Reader(request.getfixturevalue(f"{release.name}_iso")) as r:
        vanilla = r.read(INDEX)
    records = parse_index_xbr(vanilla).records
    assert len(records) == {"usa": 3072, "europe": 3730}[release.name]
    assert add_index_records(vanilla, []) == vanilla
    golden, built = _oracle(G3[release.name]), _oracle("resources.json")[G3[release.name]]
    cases = {case: files[INDEX] for case, files in built.items() if INDEX in files}
    assert sorted(cases) == sorted(case for case, files in golden.items() if INDEX in files) and cases
    for case, view in cases.items():
        added = [IndexRecord(*row) for row in view["records"]]
        appended_names = {(r.archive, r.fourcc): set() for r in added}
        for archive, file in (("characters.xbr", CHARACTERS), ("fx.xbr", FX)):
            for name, tag, *_ in built[case].get(file, {}).get("new", ()):
                appended_names.setdefault((archive, tag), set()).add(name)
        assert [r.key for r in added if r.key not in appended_names[r.archive, r.fourcc]] == [], case
        assert _sha256(add_index_records(vanilla, added)) == view["sha256"] == golden[case][INDEX], case


@pytest.mark.parametrize("release", RELEASES)
def test_each_releases_xbe_holds_the_swap_sites_vanilla_bytes_and_its_refs_name_its_functions(release, request):
    """The facts carry the player-model swap's hooks (the oracle's models
    family, ``swap.json``): each of the 117 vanilla spans it writes holds,
    at the release's own address in the player's default.xbe, the bytes
    whose sha256 and size the facts give, and each of the 65 addresses its
    shims call or are handed lies in a section (its memory: a global may lie
    past the file's bytes), a called one the address
    of the facts' function of its name."""
    with iso.Reader(request.getfixturevalue(f"{release.name}_iso")) as r:
        xbe = r.read("default.xbe")
    known = facts.of(release)
    assert (len(known.swap), len(known.swap_refs)) == (117, 65)
    assert [f"0x{va:08X}" for va, site in known.swap.items()
            if _sha256(xbe[(at := known.offset(va, site.size)):at + site.size]) != site.sha256] == []
    for va, name in known.swap_refs.items():
        assert any(s.va <= va < s.va + s.vsize for s in known.sections), f"0x{va:08X}"   # a global may be past raw
        assert name is None or known.functions[name].va == va, f"0x{va:08X}"
    assert sum(name is None for name in known.swap_refs.values()) == 9


def test_the_character_layer_writes_its_grown_files_whole_into_an_image_that_reads_back(usa_iso, tmp_path):
    """The character layer's group (:func:`characters.whole_files`): each
    of characters.xbr, fx.xbr and index.xbr a swap changed, written whole,
    one group, the others left out; a file outside the group is refused by
    name. Its image holds the grown files (moved past the image's end),
    filelist.txt follows their sizes, and the manifest's result names them."""
    stamp = gate.verify(usa_iso, whole=False)
    with iso.Reader(usa_iso) as r:
        base = {name: r.read(name) for name in characters.FILES}
    toc = parse_toc(base[CHARACTERS])
    clip = next(i for i, n in named_resources(base[CHARACTERS]).items() if n == "characters/garret4/idle")
    new = [NewResource("characters/keylord/g4/idle", "banm", _payload(base[CHARACTERS], toc[clip]))]
    built = {CHARACTERS: append_resources(base[CHARACTERS], new),
             INDEX: add_index_records(base[INDEX], [IndexRecord(new[0].name, "characters.xbr", "banm")]),
             FX: base[FX]}
    changes = characters.whole_files(base, built, "player model keylord (its archives)")
    assert [(c.file, c.whole, len(c.after)) for c in changes] == [(f, True, len(built[f])) for f in (CHARACTERS, INDEX)]
    with pytest.raises(ValueError, match=r"^swap: gamedata/config\.xbr isn't a file the character layer writes whole"):
        characters.whole_files(base, {"gamedata/config.xbr": b""}, "swap")
    layer = Layer("player model keylord", characters.TOOL, characters.KIND, {"species": "keylord"}, changes)
    made, manifest = image(stamp, [layer], base)
    with iso.Reader(made) as r:
        assert all(_sha256(r.read(f)) == _sha256(built[f]) for f in (CHARACTERS, INDEX))
        listing = r.read("filelist.txt").decode("latin-1")
    assert all(f"{len(built[f])}" in listing for f in (CHARACTERS, INDEX))
    assert set(manifest.result) == {CHARACTERS, INDEX, "filelist.txt"} and manifest.conflicts == ()


# --- the swap (Step 4.3a2): Modkit's, ported by the sync, its shims prebuilt ----------------------------------

FIELDS = {"player_character_mode": "mode", "player_character_size": "size", "player_character_scale": "scale",
          "player_attack_reach": "attack_reach", "player_attack_damage": "attack_damage",
          "player_attack_speed": "attack_speed", "player_character_anims": "anims",
          "player_character_sounds": "sounds", "player_weapon": "weapon", "player_jiggle_strength": "jiggle_strength",
          "player_jiggle_stiffness": "jiggle_stiffness"}
VARIANTS = ("beamlord", "booblord", "booblord_high", "booblord_human", "booblord_high_human")   # Step 4.3c's
KIT = {   # a case whose build reads the townsfolk's bare-hands kit or the air elemental's funnel (the package's, D965)
    "randomize-full:player-character=air_elemental": "its gust's funnel mesh (fx/air_elemental/air_funnel.glb)",
    **{f"randomize-full:{case}": "the townsfolk's bare-hands kit (clips/townsfolk/)" for case in (
        "player-character=balthazar,weapon=bare_hands", "player-character=town_female_4",
        "player-character=town_girlchild_1", "player-character=town_male_6",
        "player-character=town_male_6,weapon=booblord_spin", "weapon=bare_hands")}}


def _character(args: dict) -> dict:
    """A G3 case's Modkit flags as a recipe's ``character`` (``tools.characters.normalize``): its
    ``--player-character``, else garret4's own body (Modkit's ``player_species``: a player slider or weapon set)."""
    out = {"species": args["player_character"] or "garret4"} | {
        FIELDS[k]: v for k, v in args.items() if k in FIELDS and v is not None}
    return out | {k.removeprefix("player_"): args[k] == "on" for k in ("player_attack_ground", "player_attack_balance")
                  if args[k] is not None}


def _bodies(kit: bool = False) -> dict[str, dict]:
    """``{case: its recipe}`` of G3's USA cases that wear a species' body and
    build from the player's image and the package alone, but those of
    :data:`KIT` (with ``kit``, those alone): every models-family case that names a player
    character, but Modkit's built-in variants (Step 4.3c), a variant file's
    and the seed case (level_patches, AZ-009)."""
    out = {}
    for case, spec in _oracle("cases.json")[G3["usa"]].items():
        args = spec["args"]
        if args["player_character"] in VARIANTS or args["player_variant_file"] or args["config_mod"] or (
                case in KIT) != kit:
            continue
        assert args["no_randomize"] and args["ram"] == 128 and not args["disable_pack"], case
        out[case] = {"packs": {name: {} for name, pack in mods.PACKS.items() if pack.default_on},
                     "character": _character(args)}
    return out


def _view(vanilla: bytes, built: bytes) -> dict:
    """``resources.json``'s record of a built archive (Modkit's ``scripts/modkit_resources.py``'s ``_view``)."""
    old, new = parse_toc(vanilla), parse_toc(built)
    return {"sha256": _sha256(built), "size": len(built), "count": len(new), "vanilla_count": len(old),
            "changed": [[e.index, e.tag, e.size, _sha256(_payload(built, e))] for e, v in zip(new, old)
                        if _payload(built, e) != _payload(vanilla, v)],
            "new": [[r.name, r.tag, len(r.payload), _sha256(r.payload), list(r.relocs)]
                    for r in appended(len(old), built)]}


def _missed(cases: dict[str, dict], usa_iso) -> dict[str, tuple]:
    """``{case: (the files whose sha256 isn't G3's, default.xbe's writes outside the character layer's claims and
    the facts' swap sites, the conflicts)}`` of each of ``cases`` built through ``sdk.image`` that isn't Modkit's
    file for file (every file G3 records) and resource for resource (characters.xbr's and fx.xbr's, as
    ``resources.json`` holds them); ``keylord``'s whole image less its root entries is Modkit's."""
    golden, views = _oracle(G3["usa"]), _oracle("resources.json")[G3["usa"]]
    assert set(cases) <= set(golden)
    known = facts.of(gate.USA)
    sites = sorted((known.offset(va, s.size), known.offset(va, s.size) + s.size) for va, s in known.swap.items())
    with iso.Reader(usa_iso) as r:
        vanilla = {f: r.read(f) for f in characters.FILES}
    missed = {}
    for case, recipe in cases.items():
        stamp, base, layers, _, _ = sdk._plan(recipe | {"iso": str(usa_iso)})
        made, manifest = edits_manifest.image(stamp, layers, base)
        layer = next(la for la in layers if la.tool == characters.TOOL)
        held = []   # its claims and the swap sites, those that meet merged
        for lo, hi in sorted([(c.offset, c.offset + c.size) for c in layer.claims] + sites):
            held[-1:] = [(held[-1][0], max(hi, held[-1][1]))] if held and lo <= held[-1][1] else [*held[-1:], (lo, hi)]
        loose = [f"0x{c.offset:X}" for c in layer.changes if c.file == "default.xbe"
                 and not any(lo <= c.offset and c.offset + len(c.after) <= hi for lo, hi in held)]
        with iso.Reader(made) as r:
            files = {f: r.read(f) for f in golden[case] if f != "ISO"}
        shas = {f: _sha256(data) for f, data in files.items()}
        want = {f: sha for f, sha in golden[case].items() if f != "ISO"}
        resources = {f: _view(vanilla[f], files[f]) for f in (CHARACTERS, FX) if f in files}
        if shas != want or loose or manifest.conflicts or any(
                {k: views[case][f][k] for k in resources[f]} != resources[f] for f in resources):
            missed[case] = (sorted(f for f in want if shas.get(f) != want[f]), loose, manifest.conflicts)
        if case.endswith("=keylord"):
            changed = {f: data for f, data in files.items() if f != "filelist.txt" and data != base.get(f)}
            assert iso.read(usa_iso, changed).sha256() == golden[case]["ISO"]
    return missed


@pytest.fixture
def no_content(tmp_path, monkeypatch):
    """An empty content folder, as a player who downloaded nothing has it:
    each name a characters module binds to a folder of ``content.ROOT``
    (``_player_variants``' ``CLIPS`` and ``SOUNDS``) rebound to that folder
    of an empty one."""
    empty, root = tmp_path / "content", content.ROOT
    empty.mkdir()
    for name, module in list(sys.modules.items()):
        if name == characters.__name__ or name.startswith(f"{characters.__name__}."):
            for attr, value in list(vars(module).items()):
                if isinstance(value, Path) and value.is_relative_to(root):
                    monkeypatch.setattr(module, attr, empty / value.relative_to(root))
    assert (_player_variants.CLIPS, _player_variants.SOUNDS) == (empty / "clips", empty / "sounds")
    return empty


def test_each_body_case_is_modkits_file_for_file_and_resource_for_resource_its_hooks_at_the_facts_sites(
        usa_iso, no_content):
    """Each of G3's body cases (:func:`_bodies`: 20 of its 35 USA model
    cases, weapons and sounds and garret4's own body among them) built through ``sdk.image`` (the
    packs on by default, the body's size folded into the walk and roll, the
    character layer after them) gives every file G3 records Modkit's
    sha256, characters.xbr's and fx.xbr's resources each as
    ``resources.json`` holds them (each vanilla entry it changed, each it
    appended, by name, size and sha256), and ``keylord``'s whole image less
    its root entries is Modkit's (the grown files' layout). The character
    layer writes default.xbe only inside its claims (its shims) and the
    facts' swap sites (:func:`_missed`), with an empty content folder.
    garret4's roll table the roll shim's object holds as zeros, read from
    the image, gives G2's object back."""
    bodies = _bodies()
    assert len(bodies) == 20 and _missed(bodies, usa_iso) == {}
    roll = coff.parse((shimkit.PLAYER_MODEL / "roll.o").read_bytes())
    assert coff.normalized_sha256(ports.restored("roll", roll, ports.Vanilla(gate.USA, usa_iso))) == _oracle(
        "tests/goldens/shims.json")["player_model_roll.o"]["normalized sha256"]


def _probe(probe: dict, release, image_path, vanilla: dict, tmp_path) -> tuple[dict, dict, Layer]:
    """``(Modkit's record, AzurKit's, the character layer)`` of a
    ``probes.json`` probe built through ``sdk.image`` from ``image_path``,
    the packs on by default (its variant file, if it has one, written in
    ``tmp_path``): each record the sha256 of every file Modkit's build
    changed, the files the manifest changed but filelist.txt, characters.xbr's
    and fx.xbr's resources and the conflicts."""
    character = probe["character"]
    if "variants" in probe:
        recipes = tmp_path / f"{len(list(tmp_path.iterdir()))}.json"
        recipes.write_text(json.dumps(probe["variants"]), encoding="utf-8")
        character = character | {"variant_file": str(recipes)}
    stamp, base, layers, _, _ = sdk._plan({"iso": str(image_path), "character": character, "packs": {
        name: {} for name, pack in mods.PACKS.items() if pack.default_on}})
    made, manifest = edits_manifest.image(stamp, layers, base)
    want = probe[release.name]
    with iso.Reader(made) as r:
        files = {f: r.read(f) for f in want["files"]}
    keep = (CHARACTERS, FX)
    return ({"files": want["files"], "changed": sorted(set(want["files"]) - {"filelist.txt"}),
             "resources": {f: view for f, view in want["resources"].items() if f in keep}, "conflicts": ()},
            {"files": {f: _sha256(data) for f, data in files.items()},
             "changed": sorted(set(manifest.result) - {"filelist.txt"}),
             "resources": {f: _view(vanilla[f], files[f]) for f in want["resources"] if f in keep},
             "conflicts": manifest.conflicts},
            next(la for la in layers if la.tool == characters.TOOL))


@pytest.mark.parametrize("release", RELEASES)
def test_a_townsfolk_and_an_air_elemental_swap_need_no_download_and_are_modkits_file_for_file(
        release, request, no_content, tmp_path):
    """The townsfolk's bare-hands kit (the weaponless townsfolk's weapon,
    and ``bare_hands`` and the spin attack on any body) and the air
    elemental's funnel ship in the package (D965: each file Modkit's at the
    models tag, ORACLE.toml's ``models.source``), so with an empty content
    folder a townsman's and the air elemental's own bodies (``probes.json``'s
    species probes) are Modkit's file for file and resource for resource on
    both releases, and on USA so is each G3 case that reads the kit or the
    funnel (:data:`KIT`, :func:`_missed`). A build that needs a file the
    content folder lacks (booblord's clips) fails naming it."""
    package = Path(characters.__file__).parent
    assert (_player_kit.KIT, _player_variants.FX_ASSETS) == (package / "clips" / "townsfolk", package / "fx")
    image_path = request.getfixturevalue(f"{release.name}_iso")
    with iso.Reader(image_path) as r:
        vanilla = {f: r.read(f) for f in characters.FILES}
    species = {case: probe for case, probe in _oracle("probes.json").items() if "variants" not in probe}
    assert sorted(probe["character"]["species"] for probe in species.values()) == ["air_elemental", "town_male_6"]
    built = {case: _probe(probe, release, image_path, vanilla, tmp_path)[:2] for case, probe in species.items()}
    assert {case: got for case, (_, got) in built.items()} == {case: want for case, (want, _) in built.items()}
    if release is gate.USA:
        cases = _bodies(kit=True)
        assert sorted(cases) == sorted(KIT) and _missed(cases, image_path) == {}
    with pytest.raises((OSError, ValueError), match=r"clips[/\\]booblord[/\\]"):
        sdk._plan({"iso": str(image_path), "packs": {}, "character": {"species": "booblord"}})


def test_a_character_is_refused_by_name_where_a_build_cant_carry_it_yet():
    """A randomized build doesn't wear a character yet (its logic would need
    the body's reasons, Modkit's model reasons) and a share link doesn't
    carry one (``sdk.preset_encode``, as a build's mods file doesn't): each
    is refused by name, before any image is read."""
    recipe = {"iso": "/nowhere/usa.iso", "packs": {}, "character": {"species": "flicken"}}
    with pytest.raises(ValueError, match=r"^recipe: a randomized build doesn't wear a character yet"):
        sdk.image(recipe | {"randomizer": {"seed": "2"}})
    with pytest.raises(ValueError, match=r"^preset: a share link carries .* not a character"):
        sdk.preset_encode(recipe)


def test_the_speed_toggle_flips_a_worn_bodys_walk_and_roll_to_the_bodys_own(usa_iso):
    """With a character, the speed toggle's vanilla walk and roll distance
    are the body's own, 7 sqrt(s) and sqrt(s) (the ``size_fold`` the sdk
    hands player_physics, Modkit's Step 2.186), not garret4's: picked
    alone they have nothing to flip, and a doubled walk flips between
    14 sqrt(s) and 7 sqrt(s)."""
    def physics(params: dict) -> tuple[Layer, bytes]:
        _, base, layers, _, _ = sdk._plan({"iso": str(usa_iso), "packs": {"player_physics": params},
                                           "character": {"species": "keylord"}})
        return next(la for la in layers if la.id == "pack player_physics"), bytes(compose(base, layers)[0][characters.XBE])
    alone, _ = physics({"toggle_walk_speed_scale": 1, "toggle_roll_speed_scale": 1})
    assert any(note.endswith("nothing to flip; not installed") for note in alone.notes)
    walk, xbe = physics({"walk_speed_scale": 2.0, "toggle_walk_speed_scale": 1})
    r = walk.recipe["params"]["walk_speed_scale"] / 2   # sqrt(s), keylord's s 1.0988
    assert abs(r * r - 1.0988) < 1e-4 and struct.pack("<I2f", 1, 14 * r, 7 * r) in xbe


# --- variants (Step 4.3c1): a recipe's mesh, paint and jiggle -----------------------------------------------------


@pytest.mark.parametrize("release", RELEASES)
def test_each_variant_probe_is_modkits_file_for_file_and_resource_for_resource(release, request, no_content, tmp_path):
    """Each of ``probes.json``'s variants (Modkit's own build of it at the
    models tag: a recipe file's variant whose mesh is subdivided, deformed and
    grown a tube, its textures painted and coloured, its bones on jiggle
    springs, a shape sized, worn with a weapon), built through ``sdk.image``
    from its recipe file with an empty content folder, gives every file Modkit's build changed Modkit's
    sha256 and characters.xbr's and fx.xbr's resources as Modkit's, with no
    conflict. The layer's recipe holds the variant's sha, and neither it nor
    a note holds the recipe file's folder."""
    probes = {case: probe for case, probe in _oracle("probes.json").items() if "variants" in probe}
    assert probes
    with iso.Reader(image_path := request.getfixturevalue(f"{release.name}_iso")) as r:
        vanilla = {f: r.read(f) for f in characters.FILES}
    for case, probe in probes.items():
        want, got, layer = _probe(probe, release, image_path, vanilla, tmp_path)
        assert got == want and len(layer.recipe["variant"]) == 12, case
        assert str(tmp_path) not in json.dumps([layer.recipe, layer.notes]), case


def test_a_variants_shapes_and_options_are_refused_by_name_where_it_cant_take_them():
    """``shapes`` size a variant's shapes: on a species they are refused by
    name (an empty ``shapes`` sizes none, as Modkit's ``player_variant``),
    as a shape's value that isn't a finite number is (D23); an option a
    recipe gives that isn't the variant's own (beamlord's mode) is refused
    by name, before any image is read."""
    with pytest.raises(ValueError, match=r"^character: shapes\.hips nan is not a finite number"):
        characters.normalize({"species": "keylord", "shapes": {"hips": float("nan")}})
    with pytest.raises(ValueError, match=r"^character: shapes size a variant's shapes, and 'keylord' names no variant"):
        characters.variant(characters.normalize({"species": "keylord", "shapes": {"hips": 1.2}}), None)
    assert characters.variant(characters.normalize({"species": "keylord", "shapes": {}}), None) == (None, None)
    own = characters.variant({"species": "beamlord"}, None)[1]["mode"]
    with pytest.raises(ValueError, match=r"^--player-character-mode \w+: the variant 'beamlord' is mode " + own):
        characters.variant({"species": "beamlord", "mode": {"own": "garret4", "garret4": "own"}[own]}, None)


def test_a_body_case_under_pyodide_is_modkits_file_for_file(usa_iso, pyodide):
    """keylord's case built by ``sdk.image`` under Pyodide on Node (the
    site's runtime, D882: swaps on the site too), from the wheel alone with
    Pyodide's numpy wheel loaded, changes each file G3 records to Modkit's
    sha256."""
    case = "randomize-full:player-character=keylord"
    got = pyodide(image=_bodies()[case] | {"iso": str(usa_iso)}, packages=(_pyodide.numpy(),))
    assert (got["code"], got["platform"]) == (0, "emscripten"), got["stderr"][-2000:]
    assert got["report"]["result"] == {f: sha for f, sha in _oracle(G3["usa"])[case].items() if f != "ISO"}
