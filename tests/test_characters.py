"""The archive writers a character swap builds on (Step 4.3a1; the models
family's source, ported by the sync): ``core.xbr.append`` (new resources,
their relocations and named rows, grown payloads), ``index.xbr``'s records,
the body codec; the character layer's whole-file group; and the swap's XBE
hooks in the facts. Checked on the player's images against AzurKit's
goldens (``scripts/record_goldens.py``'s, Step 4.12c; their first recording
Modkit's at oracle-models-3): ``resources.json`` (one sha256 per XBR
resource of each G3 build that wears a model) and G3's per-file hashes."""

from __future__ import annotations

import hashlib
import json
import math
import multiprocessing
import os
import re
import struct
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

import shimkit
from azurkit import cli, sdk
from azurkit.core import coff, facts, gate, iso
from azurkit.core.xbr.append import PAGE, NewResource, append_resources, appended
from azurkit.core.xbr.nodes import named_resources, parse_toc, runs
from azurkit.edits import manifest as edits_manifest
from azurkit.edits import preset
from azurkit.edits.layer import Layer, compose
from azurkit.edits.manifest import image
from azurkit.tools import characters, mods
from azurkit.tools.characters import _player_kit, _player_variants, content, ports, shipped
from azurkit.tools.characters import body_codec as bc
from azurkit.tools.characters.index_xbr import IndexRecord, add_index_records, parse_index_xbr
from scripts import record_goldens, record_shipped
from tests import _pyodide

CHARACTERS, FX, INDEX = characters.FILES
G3 = {"usa": "pipelines.json", "europe": "europe/pipelines.json"}
RELEASES = [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
            pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe], id="europe")]


def _sha256(data) -> str:
    return hashlib.sha256(data).hexdigest()


def _golden(rel: str) -> dict:
    return record_goldens.recorded(rel)


def _resources(release: str) -> dict:
    """``resources.json``'s rows of the release's G3 cases."""
    return _golden("resources.json")[f"tests/goldens/{G3[release]}"]


def _models(release: str) -> dict[str, dict]:
    """``{case: its recipe}`` of the release's G3 cases that dress the player."""
    return {case: spec for case, spec in record_goldens.cases(G3[release]).items() if record_goldens.wears(spec)}


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
def test_each_model_cases_index_xbr_is_its_goldens_file_for_file(release, request):
    """index.xbr reads back (USA's 3,072 records, Europe's 3,730) and adding
    no record leaves it as it was. Each G3 case that dresses the player on
    the release and changes index.xbr adds its records
    (``resources.json``: those its build added, in the order it
    added them, each naming a resource the case appended to its archive
    with that fourcc), and the file is the golden's, byte for byte: the
    sha256 of G3's golden and of ``resources.json``'s file."""
    with iso.Reader(request.getfixturevalue(f"{release.name}_iso")) as r:
        vanilla = r.read(INDEX)
    records = parse_index_xbr(vanilla).records
    assert len(records) == {"usa": 3072, "europe": 3730}[release.name]
    assert add_index_records(vanilla, []) == vanilla
    golden, built = _golden(G3[release.name]), _resources(release.name)
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
    """The facts carry the player-model swap's hooks (their addresses edited
    by hand, each span's sha256 gen_facts's): each of the 117 vanilla spans it writes holds,
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


# --- the swap (Step 4.3a2): Modkit's, ported, AzurKit's own since Step 4.12c, its shims prebuilt ----------------

VARIANTS = ("beamlord", "booblord", "booblord_high", "booblord_human", "booblord_high_human")   # Step 4.3c's
KIT = {   # a case whose build reads the townsfolk's bare-hands kit or the air elemental's funnel (the package's, D965)
    "randomize-full:player-character=air_elemental": "its gust's funnel mesh (fx/air_elemental/air_funnel.glb)",
    **{f"randomize-full:{case}": "the townsfolk's bare-hands kit (clips/townsfolk/)" for case in (
        "player-character=balthazar,weapon=bare_hands", "player-character=town_female_4",
        "player-character=town_girlchild_1", "player-character=town_male_6",
        "player-character=town_male_6,weapon=booblord_spin", "weapon=bare_hands")}}


def _bodies(kit: bool = False) -> dict[str, dict]:
    """``{case: its recipe}`` of G3's USA cases that wear a species' body and
    build from the player's image and the package alone, but those of
    :data:`KIT` (with ``kit``, those alone): every case that dresses the player,
    but the built-in variants (Step 4.3c), a variant file's
    and the seed case (level_patches, AZ-009)."""
    out = {}
    for case, spec in _models("usa").items():
        args = spec["args"]
        if args["player_character"] in VARIANTS or args["player_variant_file"] or args["config_mod"] or (
                case in KIT) != kit:
            continue
        assert args["no_randomize"] and args["ram"] == 128 and not args["disable_pack"], case
        out[case] = {"packs": {name: {} for name, pack in mods.PACKS.items() if pack.default_on},
                     "character": record_goldens.character(spec)}
    return out


PINNED = "shipped: "
"""A :func:`_missed` case named so is no golden's: a shipped plan no case builds, built for its answer alone."""


def _missed(cases: dict[str, dict], image_path, release=gate.USA, workers: int = 1,
            held: set | None = None) -> dict[str, tuple]:
    """``{case: (the files whose sha256 isn't G3's, default.xbe's writes outside the character layer's claims and
    the facts' swap sites, the conflicts, the shipped answers that aren't its dress's)}`` of each of ``cases``
    built through ``sdk.image`` from the ``release``
    image that isn't its golden's file for file (every file G3 records; a Europe build's XBRs but index.xbr, the
    USA case's, as G3 records them) and resource for resource (characters.xbr's and fx.xbr's, as ``resources.json``
    holds them); ``keylord``'s whole image less its root entries is the golden's. Each dress is fresh
    (``shipped.OFF``, which importing ``record_goldens`` sets), and each shipped answer that stands on what it read
    must be its answer (D995's re-record pin, ``shipped.held``; ``held`` gathers those rows' names); a
    :data:`PINNED` case is built for that alone. With ``workers``, that many spawned
    processes build the cases (a case's build is the same in any process; the content folder is the process's)."""
    assert {c for c in cases if not c.startswith(PINNED)} <= set(_golden(G3[release.name]))
    jobs = [(case, recipe, str(image_path), release.name) for case, recipe in cases.items()]
    if workers > 1:
        with ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("spawn")) as pool:
            done = list(pool.map(_miss, jobs))
    else:
        done = [_miss(job) for job in jobs]
    if held is not None:
        held.update(name for _, _, names in done for name in names)
    return {case: why for case, why, _ in done if why is not None}


def _miss(job: tuple) -> tuple[str, tuple | None, list[str]]:
    """One case of :func:`_missed`: ``(case, why or None, the shipped rows its fresh dress held)``."""
    case, recipe, image_path, name = job
    release = next(r for r in gate.RELEASES if r.name == name)
    assert shipped.OFF
    shipped.SEEN = []
    try:
        stamp, base, layers, _, _ = sdk._plan(recipe | {"iso": image_path})
    finally:
        seen, shipped.SEEN = shipped.SEEN, None
    held = [shipped.held(s) for s in seen]
    good, stale = [n for g, _ in held for n in g], [w for _, s in held for w in s]
    if case.startswith(PINNED):
        return case, tuple(stale) or None, good
    golden, view, usa = _golden(G3[name])[case], _resources(name)[case], _golden(G3["usa"])[case]
    known = facts.of(release)
    sites = sorted((known.offset(va, s.size), known.offset(va, s.size) + s.size) for va, s in known.swap.items())
    with iso.Reader(image_path) as r:
        vanilla = {f: r.read(f) for f in characters.FILES}
    made, manifest = edits_manifest.image(stamp, layers, base)
    layer = next(la for la in layers if la.tool == characters.TOOL)
    held = []   # its claims and the swap sites, those that meet merged
    for lo, hi in sorted([(c.offset, c.offset + c.size) for c in layer.claims] + sites):
        held[-1:] = [(held[-1][0], max(hi, held[-1][1]))] if held and lo <= held[-1][1] else [*held[-1:], (lo, hi)]
    loose = [f"0x{c.offset:X}" for c in layer.changes if c.file == "default.xbe"
             and not any(lo <= c.offset and c.offset + len(c.after) <= hi for lo, hi in held)]
    want = {f: sha for f, sha in ({f: sha for f, sha in usa.items() if f.endswith(".xbr") and f != INDEX}
                                  | golden).items() if f != "ISO"}
    with iso.Reader(made) as r:
        files = {f: r.read(f) for f in want}
    shas = {f: _sha256(data) for f, data in files.items()}
    resources = {f: record_goldens.view(vanilla[f], files[f], f) for f in (CHARACTERS, FX) if f in files}
    if case.endswith("=keylord"):
        changed = {f: data for f, data in files.items() if f != "filelist.txt" and data != base.get(f)}
        assert iso.read(image_path, changed).sha256() == golden["ISO"]
    if shas != want or loose or manifest.conflicts or stale or any(
            {k: view[f][k] for k in resources[f]} != resources[f] for f in resources):
        return case, (sorted(f for f in want if shas.get(f) != want[f]), loose, manifest.conflicts, stale), good
    return case, None, good


@pytest.fixture
def no_content(tmp_path, monkeypatch):
    """An empty content folder, as a player who downloaded nothing has it:
    each name a characters module binds to a folder of ``content.ROOT``
    (``_player_variants``' ``CLIPS`` and ``SOUNDS``) rebound to that folder
    of an empty one, and ``AZURKIT_CONTENT`` naming it, so the processes
    :func:`_missed` spawns read it too."""
    empty, root = tmp_path / "content", content.ROOT
    empty.mkdir()
    monkeypatch.setenv(content.ENV, str(empty))
    for name, module in list(sys.modules.items()):
        if name == characters.__name__ or name.startswith(f"{characters.__name__}."):
            for attr, value in list(vars(module).items()):
                if isinstance(value, Path) and value.is_relative_to(root):
                    monkeypatch.setattr(module, attr, empty / value.relative_to(root))
    assert (_player_variants.CLIPS, _player_variants.SOUNDS) == (empty / "clips", empty / "sounds")
    return empty


def test_each_body_case_is_its_goldens_file_for_file_and_resource_for_resource_its_hooks_at_the_facts_sites(
        usa_iso, no_content):
    """Each of G3's body cases (:func:`_bodies`: 20 of its 35 USA model
    cases, weapons and sounds and garret4's own body among them) built through ``sdk.image`` (the
    packs on by default, the body's size folded into the walk and roll, the
    character layer after them) gives every file G3 records its
    sha256, characters.xbr's and fx.xbr's resources each as
    ``resources.json`` holds them (each vanilla entry it changed, each it
    appended, by name, size and sha256), and ``keylord``'s whole image less
    its root entries is G3's (the grown files' layout). The character
    layer writes default.xbe only inside its claims (its shims) and the
    facts' swap sites (:func:`_missed`), with an empty content folder.
    garret4's roll table the roll shim's object holds as zeros, read from
    the image, gives G2's object back. The cases build in 4 processes."""
    bodies = _bodies()
    assert len(bodies) == 20 and _missed(bodies, usa_iso, workers=4) == {}
    roll = coff.parse((shimkit.PLAYER_MODEL / "roll.o").read_bytes())
    assert coff.normalized_sha256(ports.restored("roll", roll, ports.Vanilla(gate.USA, usa_iso))) == _golden(
        "shims.json")["player_model_roll.o"]["normalized sha256"]


def _probe(probe: dict, release, image_path, vanilla: dict, tmp_path) -> tuple[dict, dict, Layer]:
    """``(the golden's record, the build's, the character layer)`` of a
    ``probes.json`` probe built through ``sdk.image`` from ``image_path``,
    the packs on by default (its variant file, if it has one, written in
    ``tmp_path``): each record the sha256 of every file the golden's build
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
             "resources": {f: record_goldens.view(vanilla[f], files[f], f) for f in want["resources"] if f in keep},
             "conflicts": manifest.conflicts},
            next(la for la in layers if la.tool == characters.TOOL))


@pytest.mark.parametrize("release", RELEASES)
def test_a_townsfolk_and_an_air_elemental_swap_need_no_download_and_are_their_goldens_file_for_file(
        release, request, no_content, tmp_path):
    """The townsfolk's bare-hands kit (the weaponless townsfolk's weapon,
    ``bare_hands`` and the spin attack) and the air
    elemental's funnel ship in the package (D965), so with an empty content
    folder a townsman's and the air elemental's own bodies (``probes.json``'s
    species probes) are their goldens' file for file and resource for resource on
    both releases, and on USA so is each G3 case that reads the kit or the
    funnel (:data:`KIT`, :func:`_missed`). A build that needs a file the
    content folder lacks (booblord's clips) fails naming it."""
    package = Path(characters.__file__).parent
    assert (_player_kit.KIT, _player_variants.FX_ASSETS) == (package / "clips" / "townsfolk", package / "fx")
    image_path = request.getfixturevalue(f"{release.name}_iso")
    with iso.Reader(image_path) as r:
        vanilla = {f: r.read(f) for f in characters.FILES}
    species = {case: probe for case, probe in _golden("probes.json").items() if "variants" not in probe}
    assert sorted(probe["character"]["species"] for probe in species.values()) == ["air_elemental", "town_male_6"]
    built = {case: _probe(probe, release, image_path, vanilla, tmp_path)[:2] for case, probe in species.items()}
    assert {case: got for case, (_, got) in built.items()} == {case: want for case, (want, _) in built.items()}
    if release is gate.USA:
        cases = _bodies(kit=True)
        assert sorted(cases) == sorted(KIT) and _missed(cases, image_path, workers=4) == {}   # in 4 processes
    with pytest.raises((OSError, ValueError), match=r"clips[/\\]booblord[/\\]"):
        sdk._plan({"iso": str(image_path), "packs": {}, "character": {"species": "booblord"}})


def test_a_share_link_and_a_mods_file_carry_a_character():
    """A share link (``sdk.preset_encode`` and ``preset_decode``) and a mods file (``sdk.read_mods``: a link, or a
    build's manifest through ``preset.from_manifest``) carry a character by name and numbers, a variant with its
    recipe's sha, both ways, and ``azurkit build --mods`` wears it (``cli.recipe``); a recipe file's path (``variant_file``) is refused by name (Q174), and so is a variant
    whose recipe isn't this AzurKit's, naming what to Install or Update; a remembered setup (``sdk.restore``) keeps
    one and drops a path by name; a randomized recipe's settings are checked before any image is read."""
    recipe = {"iso": "/nowhere/usa.iso", "packs": {}, "character": {"species": "beamlord", "attack_reach": 1.5}}
    fragment = sdk.preset_encode(recipe)
    worn = {"species": "beamlord", "attack_reach": 1.5}
    assert [la for la in sdk.preset_decode(fragment)["layers"] if la["tool"] == characters.TOOL] == [
        {"tool": "characters", "kind": "characters", "recipe": worn | {"variant": "628f6d09ad7b"}}]
    assert sdk.read_mods(fragment) == {"packs": {}, "character": worn}
    built = {"format": preset.MANIFEST, "base": {"kind": "vanilla", "release": "usa", "iso_sha256": gate.USA.iso_sha256},
             "layers": [{"tool": "mods", "kind": "packs", "recipe": {"pack": "fps_unlock", "params": {}}},
                        {"tool": "characters", "kind": "characters", "recipe": {"species": "keylord", "mode": "garret4"}}],
             "result": {}}
    assert sdk.read_mods(json.dumps(built)) == {"packs": {"fps_unlock": {}}, "character": {"species": "keylord",
                                                                                           "mode": "garret4"}}
    assert cli.recipe("x.iso", [], [], True, [], sdk.read_mods(json.dumps(built)))["character"] == {
        "species": "keylord", "mode": "garret4"}
    with pytest.raises(ValueError, match=r"^preset: a character travels by name and numbers \(Q174\), never its "
                                         r"recipe file's path \(variant_file\)"):
        sdk.preset_encode(recipe | {"character": {"species": "mine", "variant_file": "/x/mine.json"}})
    other = preset.encode({"format": preset.FORMAT, "schema_version": preset.SCHEMA_VERSION, "layers": [
        {"tool": "characters", "kind": "characters", "recipe": {"species": "beamlord", "variant": "0123456789ab"}}]})
    with pytest.raises(ValueError, match=r"^preset: 'beamlord' is recipe 0123456789ab there and recipe 628f6d09ad7b "
                                         r"here: Install or Update it"):
        sdk.preset_decode(other)
    kept = sdk.restore({"character": worn})
    assert kept["character"] == worn and not kept["dropped"]
    lost = sdk.restore({"character": {"species": "mine", "variant_file": "/x/mine.json"}})
    assert "character" not in lost and lost["dropped"][0].startswith("the character (a character travels by name")
    with pytest.raises(ValueError, match=r"^randomizer: seed is a string"):
        sdk.image(recipe | {"randomizer": {"seed": 2}})


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
    r = math.sqrt(characters.size({"species": "keylord"}, ports.Vanilla(gate.USA, usa_iso)))   # keylord's s 1.0988
    assert abs(r * r - 1.0988) < 1e-4 and struct.pack("<I2f", 1, 14 * r, 7 * r) in xbe


@pytest.mark.parametrize("release", RELEASES)
def test_a_character_builds_recipe_rebuilds_its_image(release, request):
    """keylord over the packs on by default: the build's recipe (``sdk.open_build``, then ``sdk.read_mods``: Load
    its recipe, ``azurkit build --mods``) holds the walk and roll as asked, not as the body's size folded them, so
    it rebuilds the same image on each release (AZ-829: they were folded again)."""
    path = str(request.getfixturevalue(f"{release.name}_iso"))
    made, _ = sdk.image({"iso": path, "packs": {name: {} for name, pack in mods.PACKS.items() if pack.default_on},
                         "character": {"species": "keylord"}})
    recipe = sdk.read_mods(sdk.open_build(made))
    assert recipe["packs"]["player_physics"] == {}
    assert sdk.image({"iso": path} | recipe)[0].sha256() == made.sha256()


def test_a_worn_combo_chains_only_on_a_stun_unless_chain_is_any_and_every_sets_first_three_attacks_stun(
        usa_iso, no_content, monkeypatch):
    """D1045: by default (``chain`` "hit", as a link or mods file without the field reads) the combo's rows 28-31
    keep the game's stunned-target gate, so its next attack follows only a hit, as garret4's; ``chain`` "any" lifts
    it, on a boss, a creature, a townsman and a variant (and garret4's own body); any other chain is refused by name.
    Each set's first three attacks stun a target (their multiplier under 1.0, or X18: a light column, or a set's
    swing read from X36's state), so every set's combo can chain on a hit (Step 4.3: air_elemental's gust,
    beamlord's second set and the townsman's second set never stunned), and so does a drain among them (X37 names
    its hit's target in X18's slot: its level 2 cleared the swing's stun, beamlord's set 2 at its drain, Balthazar's
    basic2)."""
    from azurkit.tools.characters import _player_character as swap

    with pytest.raises(ValueError, match=r"^character: chain 'press' is not one of 'hit', 'any'"):
        characters.normalize({"species": "keylord", "chain": "press"})
    seen, attack_sets, light_hit, drain = {}, swap.attack_sets, swap.install_light_hit_shim, swap.install_drain_shim

    def sets(columns, picks):   # the sets the build plays and X18 as it lands, recorded
        seen["sets"] = attack_sets(columns, picks)
        return seen["sets"]

    def x18(xbe, columns, sets_state=0):
        seen["x18"] = columns, sets_state
        light_hit(xbe, columns, sets_state)

    def x37(xbe, columns, *args):   # its drain's columns and X18's slot as it lands
        seen["x37"] = columns, args[5] if len(args) > 5 else 0
        drain(xbe, columns, *args)
    monkeypatch.setattr(swap, "attack_sets", sets)
    monkeypatch.setattr(swap, "install_light_hit_shim", x18)
    monkeypatch.setattr(swap, "install_drain_shim", x37)
    for species in ("balthazar", "air_elemental", "town_male_1", "beamlord", "garret4"):
        for chain in ("hit", "any"):
            seen.clear()
            _, base, layers, _, _ = sdk._plan({"iso": str(usa_iso), "character": {"species": species} | (
                {"chain": chain} if chain == "any" else {})})
            doc = ports.XbrDocument(bytearray(compose(base, layers)[0].get(characters.CONFIG, base[characters.CONFIG])))
            gates = doc.keyed_section("attacks_transitions")
            at = gates.row_names().index("target features")
            assert [c.string_value if (c := gates.read_cell(col, at)).type_code else None
                    for col in swap.CHAIN_GATES] == (["stunned frozen"] * 4 if chain == "hit" else [None] * 4), (
                species, chain)
            if chain == "any":
                continue
            anims = doc.keyed_section("attacks_anims")
            columns, (mask, state), (drains, slot) = anims.col_names(), seen.get("x18", (0, 0)), seen.get("x37", (0, 0))
            for k, cols in enumerate(seen.get("sets") or [[0, 1, 2]]):
                for c in cols[:3]:
                    m = anims.find_cell(columns[c], swap.MULTIPLIER, c)
                    assert (m is not None and m.type_code == 1 and m.double_value < swap.LIGHT) or "x18" in seen and (
                        mask >> c & 1 or k and state), (species, k, columns[c])
                    assert not drains >> c & 1 or "x18" in seen and slot and (mask >> c & 1 or k and state), (
                        species, k, columns[c], "drain")
            assert species not in ("balthazar", "beamlord") or drains & sum(  # each has a drain the combo chains from
                1 << c for cols in seen["sets"] for c in cols[:3]), species


# --- variants (Step 4.3c1): a recipe's mesh, paint and jiggle -----------------------------------------------------


@pytest.mark.parametrize("release", RELEASES)
def test_each_variant_probe_is_its_goldens_file_for_file_and_resource_for_resource(release, request, no_content,
                                                                                   tmp_path):
    """Each of ``probes.json``'s variants (a recipe file's variant whose mesh is subdivided, deformed and
    grown a tube, its textures painted and coloured, its bones on jiggle
    springs, a shape sized, worn with a weapon), built through ``sdk.image``
    from its recipe file with an empty content folder, gives every file the golden's build changed its
    sha256 and characters.xbr's and fx.xbr's resources as the golden's, with no
    conflict. The layer's recipe holds the variant's sha, and neither it nor
    a note holds the recipe file's folder."""
    probes = {case: probe for case, probe in _golden("probes.json").items() if "variants" in probe}
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


def test_a_mesh_drop_takes_its_bones_last_groups_off_lod_0_and_refuses_any_other_by_name(usa_iso):
    """``mesh.drop`` (Step 4.3: booblord's vase) takes the LOD-0 vertices of
    its bones' subtrees off a body with every triangle that uses one:
    town_female_2's vase, her last group (5) on ``vase_joint``, 202 vertices
    and 231 triangles, while every other group's vertices and triangles and
    every bone stay as they were. A bone the body lacks, one whose vertices
    share a group with others (her head and hair) and one no vertex weighs most on
    are refused by name, nothing written."""
    from azurkit.tools.characters import mesh_edit

    with iso.Reader(usa_iso) as r:
        data = r.read(CHARACTERS)
    body = "townspeople/female_2"
    before = bc.read_asset(data, body)
    plan = mesh_edit.plan(data, body, mesh_edit.MeshSpec(drop=("vase_joint",)))
    written = bytearray(data)
    mesh_edit.write(written, plan, data)
    after = bc.read_asset(bytes(written), body)
    assert plan.dropped == (5,) and (len(before.lods[0].groups[5].vertices), len(before.lods[0].groups[5].triangles)) \
        == (202, 231)
    assert [(g.vertices, g.triangles) for g in after.lods[0].groups] == [
        (g.vertices, g.triangles) for g in before.lods[0].groups[:5]]
    assert after.bone_names == before.bone_names
    for drop, why in (("nope", "townspeople/female_2 has no bone 'nope'"),
                      ("head", "townspeople/female_2 group 0 holds vertices off head too: a drop takes whole groups"),
                      ("joint77", "no vertex of townspeople/female_2 weighs most on joint77")):
        with pytest.raises(ValueError, match=f"^mesh\\.drop: {re.escape(why)}"):
            mesh_edit.plan(data, body, mesh_edit.MeshSpec(drop=(drop,)))


# --- Azurik-Custom-Content's Install and Update (Step 4.3d) ----------------------------------------------------


def _source(folder: Path, files: dict[str, bytes], entries: list[dict]) -> dict:
    """A content source in ``folder``: ``files`` at their paths and a manifest of ``entries`` (each's files
    listed by path, their sha256 and size measured)."""
    for path, data in files.items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_bytes(data)
    manifest = content.filled({"format": content.FORMAT, "schema_version": content.SCHEMA_VERSION, "entries": [
        {"kind": "pack", "title": e["id"], "author": "Azurik-Modding-Hub", "licence": "MIT", "version": 1,
         "requires": []} | e | {"files": [{"path": path} for path in e["files"]]} for e in entries]},
        lambda path: (folder / path).read_bytes())
    (folder / content.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def test_a_content_manifest_is_checked_and_each_fault_refused_by_name(tmp_path):
    """Azurik-Custom-Content's manifest (``content.check``): one fault each, every one refused by name, and a
    file whose bytes aren't its size or sha256, or hold an Xbox disc image's magic, refused by
    ``content.verify`` before an install writes anything."""
    good = _source(tmp_path, {"packs/a/pack.json": b"{}", "packs/b/pack.json": b"[]"},
                   [{"id": "a", "files": ["packs/a/pack.json"], "requires": ["b"]}, {"id": "b", "files": ["packs/b/pack.json"]}])
    assert content.check(json.dumps(good)) == good

    def entry(k: int = 0, **fields):
        bad = json.loads(json.dumps(good))
        bad["entries"][k] |= fields
        return bad
    file = good["entries"][0]["files"][0]
    faults = {
        "manifest: schema_version 2 isn't one AzurKit reads": good | {"schema_version": 2},
        "manifest: format 'other' isn't": good | {"format": "other"},
        "entry 'a': two entries have that id": entry(1, id="a"),
        "kind 'mod' is none of variant, pack": entry(kind="mod"),
        "version 1.5 is no whole number from 1": entry(version=1.5),
        "requires 'c', which it lists not": entry(requires=["c"]),
        "requires itself": entry(1, requires=["a"]),
        "path '../a/x' isn't a file under": entry(files=[file | {"path": "../a/x"}]),
        "is no relative POSIX path": entry(files=[file | {"path": "packs\\a"}]),
        "path 'iso/usa.iso' isn't a file under": entry(files=[file | {"path": "iso/usa.iso"}]),
        "entry 'b': packs/b/pack.json is entry 'a''s too": entry(files=[file | {"path": "packs/b/pack.json"}]),
        "sha256 is no 64 lower-case hex digits": entry(files=[file | {"sha256": "ab"}]),
        f"size {content.MAX_FILE + 1} is no whole number": entry(files=[file | {"size": content.MAX_FILE + 1}]),
        "an object of id, kind, title": entry(extra=1)}
    for why, bad in faults.items():
        with pytest.raises(ValueError, match=re.escape(why)):
            content.check(bad)
    with pytest.raises(ValueError, match=r"past the 1,048,576 a manifest may hold"):
        content.check(b" " * (content.MAX_MANIFEST + 1))
    files = {"packs/a/pack.json": b"{}", "packs/b/pack.json": b"[]"}
    assert [e["id"] for e in content.verify(good, "a", files)] == ["b", "a"]   # what it requires first
    for broken, why in ((b"{ }", r"a: packs/a/pack.json is 3 bytes, not the manifest's 2"),
                        (b"{]", r"a: packs/a/pack.json's sha256 [0-9a-f]{12} isn't the manifest's [0-9a-f]{12}")):
        with pytest.raises(ValueError, match=why):
            content.verify(good, "a", files | {"packs/a/pack.json": broken})
    magic = b"x" + content.XISO
    disc = entry(files=[file | {"sha256": _sha256(magic), "size": len(magic)}])
    with pytest.raises(ValueError, match=r"holds an Xbox disc image's magic: never content \(D960\)"):
        content.verify(disc, "a", files | {"packs/a/pack.json": magic})


def test_an_entry_installs_whole_or_not_at_all_pinned_to_its_version(tmp_path, monkeypatch):
    """``sdk.content_install`` from a folder source into the content folder: a file changed by a byte is
    refused naming it and nothing is written (D35); an install writes the entry and the one it requires and
    ``installed.json`` last (each version and file's sha256); a newer version upstream leaves the installed copy
    as it was until its Update, which drops the files that version no longer lists; and a built-in variant's
    entry whose recipe isn't the engine's (its sha) is refused by name."""
    source, folder = tmp_path / "source", tmp_path / "content"
    monkeypatch.setattr(content, "ROOT", folder)
    monkeypatch.delenv(sdk.SOURCE_ENV, raising=False)
    files = {"packs/a/pack.json": b"{}", "packs/a/old.md": b"old", "packs/b/pack.json": b"[]"}
    manifest = _source(source, files, [{"id": "a", "files": ["packs/a/pack.json", "packs/a/old.md"], "requires": ["b"]},
                                       {"id": "b", "files": ["packs/b/pack.json"]}])
    (source / "packs/a/old.md").write_bytes(b"olD")
    with pytest.raises(ValueError, match=r"^a: packs/a/old\.md's sha256 [0-9a-f]{12} isn't the manifest's"):
        sdk.content_install({"id": "a", "source": str(source)})
    assert not folder.exists()
    (source / "packs/a/old.md").write_bytes(b"old")
    view = sdk.content_install({"id": "a", "source": str(source)})
    shas = {e["id"]: {f["path"]: f["sha256"] for f in e["files"]} for e in manifest["entries"]}
    assert json.loads((folder / content.INSTALLED).read_text()) == view["installed"] == {
        name: {"version": 1, "source": str(source), "files": shas[name]} for name in ("a", "b")}
    assert {e["id"]: e["state"] for e in view["entries"]} == {"a": "installed", "b": "installed"}
    assert sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()) == sorted(
        [*files, content.INSTALLED, content.MANIFEST])
    _source(source, {"packs/a/pack.json": b'{"v": 2}'},
            [{"id": "a", "version": 2, "files": ["packs/a/pack.json"], "requires": ["b"]},
             {"id": "b", "files": ["packs/b/pack.json"]}])
    view = sdk.content({"source": str(source)})
    assert [(e["id"], e["state"], e["installed"]) for e in view["entries"]] == [("a", "update", 1), ("b", "installed", 1)]
    assert (folder / "packs/a/pack.json").read_bytes() == b"{}" and (folder / "packs/a/old.md").is_file()
    view = sdk.content_install({"id": "a", "source": str(source)})
    assert view["installed"]["a"]["version"] == 2 and not (folder / "packs/a/old.md").exists()
    assert (folder / "packs/a/pack.json").read_bytes() == b'{"v": 2}'
    recipe = json.loads(_player_variants.BUILTIN.read_text(encoding="utf-8"))["beamlord"] | {"scale": 1.5}
    _source(source, {"variants/beamlord/variant.json": json.dumps({"beamlord": recipe}).encode()},
            [{"id": "beamlord", "kind": "variant", "files": ["variants/beamlord/variant.json"]}])
    with pytest.raises(ValueError, match=r"^beamlord: variants/beamlord/variant\.json's beamlord is recipe "
                                         r"[0-9a-f]{12}, not the built-in beamlord's 628f6d09ad7b"):
        sdk.content_install({"id": "beamlord", "source": str(source)})
    assert "beamlord" not in content.installed()


# --- untrusted content (D992's SEC-5, 6, 9, 14, 15 and the allow-list; Step S1) -----------------------------


def _png(width: int, height: int, rows: bytes, channels: int = 4) -> bytes:
    """A PNG file whose header says ``width`` x ``height``, 8-bit RGBA (or RGB), and whose image data is
    ``rows`` deflated (whatever their length: a bomb's)."""
    import zlib

    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    deflate = zlib.compressobj(9)
    data = b"".join(deflate.compress(rows[at:at + (1 << 20)]) for at in range(0, len(rows), 1 << 20)) + deflate.flush()
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6 if channels == 4 else 2,
                                                               0, 0, 0)) + chunk(b"IDAT", data) + chunk(b"IEND", b""))


def test_untrusted_content_is_refused_quickly_by_name(tmp_path):
    """What a community entry, a recipe or a picture a player is handed can hold (D992's threat model) is
    refused by name, as a ``ValueError``, in under 0.1 s and with under 16 MiB held, or, for a valid one,
    read as quickly: a PNG bomb (64 MiB of rows behind a 64x64 header, in the textures' reader, in a glTF
    folder's read-back and in the tracker's pictures' read-back) and a picture past 4096x4096 (refused before it inflates; SEC-5); a manifest whose
    requires make an 80-entry lattice (checked, each entry walked once), a 5,000-deep chain back to itself
    (named, not a ``RecursionError``), 200,000 brackets, past 1,000 entries or 10,000 files, or a requires
    that holds no id (SEC-6); an Install whose last file is off (each file checked as it lands, into the
    entry's part folder, so one is held at a time, and nothing written), an entry or an Install past
    256 MiB (SEC-9); a path with a ``:`` or a name Windows keeps for a device, two paths one but for letter
    case, and an Update whose ``installed.json`` lists a path outside the content folder, which it leaves
    (SEC-15); a file whose suffix its folder doesn't take (``content.SUFFIXES``: a listed ``.html``, a
    picture in ``packs/``, a suffix-less file, a shipped answer outside ``variants/``; SEC-3's allow-list); a
    recipe whose clip or mesh file leaves the recipe's folder (``..``, an absolute path; SEC-14); and a shipped
    answer (``shipped.py``, D995) whose file isn't its row's size and sha256, never inflated, or that inflates
    past the size its head lists, stopped there (SEC-5's rule)."""
    import time
    import tracemalloc

    from compression import zstd

    from azurkit.tools.characters import gltf, textures
    from azurkit.tools.randomizer import art

    bomb, wide = _png(64, 64, bytes(64 << 20)), _png(8192, 4096, bytes(4096 * (8192 * 4 + 1)))
    flood = zstd.compress(bytes(64 << 20), options={zstd.CompressionParameter.window_log: 20})

    def answer(size: int) -> bytes:
        """An ``AZKP1`` file of one whole characters.xbr that inflates to 64 MiB, its head listing ``size``."""
        head = json.dumps({"layer": {"id": "x", "tool": "characters", "kind": "characters", "recipe": {},
                                     "notes": [], "claims": []}, "lines": [], "reasons": [], "changes": [
            {"file": CHARACTERS, "offset": 0, "before": "0" * 64, "group": "x", "whole": True, "size": size,
             "sha256": "0" * 64, "enc": "zstd-prefix", "length": len(flood)}]}).encode()
        return shipped.MAGIC + struct.pack("<I", len(head)) + head + flood
    (tmp_path / "shipped").mkdir()
    (tmp_path / "shipped/x.azkp").write_bytes(planted := answer(64 << 20))
    unlisted = {"reads": {}, "recipe": {}, "answer": "0" * 64,
                "blob": {"path": "x.azkp", "sha256": "0" * 64, "size": len(planted)}}   # not its sha256

    def manifest(entries: list[dict]) -> dict:
        return {"format": content.FORMAT, "schema_version": 1, "entries": [
            {"id": "", "kind": "pack", "title": "t", "author": "a", "licence": "MIT", "version": 1, "files": [],
             "requires": []} | e for e in entries]}
    lattice = json.dumps(manifest([{"id": f"e{level}{side}", "requires": [f"e{level + 1}a", f"e{level + 1}b"][:2 * (
        level < 39)]} for level in range(40) for side in "ab"]))
    chain = {f"e{k}": {"requires": [f"e{(k + 1) % 5000}"]} for k in range(5000)}
    many = manifest([{"id": f"e{k}"} for k in range(content.MAX_ENTRIES + 1)])
    files = manifest([{"id": "a", "files": [{"path": f"packs/a/{k}.json", "sha256": "0" * 64, "size": 0}
                                            for k in range(content.MAX_FILES + 1)]}])
    five = {"sha256": _sha256(bytes(5 << 20)), "size": 5 << 20}
    big = manifest([{"id": "a", "files": [{"path": f"packs/a/{k}.json"} | five for k in range(4)]}])
    big["entries"][0]["files"][3]["size"] += 1   # the last one fetched isn't the manifest's
    huge = manifest([{"id": "a", "requires": ["b"], "files": [
        {"path": f"packs/a/{k}.json", "sha256": "0" * 64, "size": content.MAX_FILE} for k in range(3)]},
        {"id": "b", "files": [{"path": f"packs/b/{k}.json", "sha256": "0" * 64, "size": content.MAX_FILE}
                              for k in range(2)]}])
    folder, seen = tmp_path / "new" / "content", []   # its parent folder made by the Install too
    booblord = json.loads(_player_variants.BUILTIN.read_text(encoding="utf-8"))["booblord"]

    def recipe(field: str, value: dict) -> str:
        """booblord's recipe as a user's, ``mine``, with its ``field`` updated by ``value``."""
        return json.dumps({"mine": booblord | {field: {**booblord[field], **value}}})

    def fetch(path: str) -> bytes:
        seen.append((path, sorted(p.name for p in folder.rglob("*.json"))))
        return bytes(5 << 20)
    rows = {
        "a PNG bomb": (lambda: textures.read_png(bomb), r"^the PNG's image data isn't its size"),
        "a PNG bomb in a glTF folder": (lambda: gltf._read_png(bomb), r"^the PNG's image data isn't its size"),
        "a PNG bomb as a tracker's picture": (lambda: art.unpng(bomb), r"^the PNG's image data isn't its size"),
        "a PNG past 4096x4096": (lambda: textures.read_png(wide),
                                 r"^a PNG of 8192x4096: past the 4096x4096 pixels a picture may hold"),
        "an 80-entry lattice of requires": (lambda: content.check(lattice), None),
        "a 5,000-deep chain back to itself": (lambda: content.needs("e0", chain), r"^manifest: entry 'e0' requires "
                                              r"itself \(e0 -> e1 -> e2 -> \.\.\. 4,995 more \.\.\. -> e4998 -> e4999 -> e0\)"),
        "200,000 brackets": (lambda: content.check("[" * 200_000), r"^manifest: not JSON \(nested too deep\)"),
        "1,001 entries": (lambda: content.check(many), r"^manifest: 1,001 entries, past the 1,000 a manifest may hold"),
        "10,001 files": (lambda: content.check(files), r"^manifest: entry 'a': past the 10,000 files a manifest may "),
        "a requires of no id": (lambda: content.check(manifest([{"id": "a", "requires": [["b"]]}])),
                                r"^manifest: entry 'a': requires is a list of ids"),
        "an Install of 4 x 5 MiB, the last file off": (lambda: content.install(big, "a", fetch, folder),
                                                       r"^a: packs/a/3\.json is 5,242,880 bytes, not the manifest's "),
        "an entry past 256 MiB": (lambda: content.check(manifest([{"id": "a", "files": [
            {"path": f"packs/a/{k}.json", "sha256": "0" * 64, "size": content.MAX_FILE} for k in range(5)]}])),
            r"^manifest: entry 'a': its files are 335,544,320 bytes, past the 268,435,456 an entry may hold"),
        "an Install past 256 MiB": (lambda: content.install(huge, "a", fetch, folder), r"^a: an install of it and "
                                    r"the entries it requires is 335,544,320 bytes, past the 268,435,456"),
        **{f"a path {what}": (lambda path=path: content.check(manifest([{"id": "a", "files": [
            {"path": path, "sha256": "0" * 64, "size": 0}]}])), why) for what, path, why in (
            ("with a ':'", "packs/a/x.json:stream", r"^manifest: entry 'a': path 'packs/a/x\.json:stream' holds a ':'"),
            ("Windows keeps for a device", "packs/Nul/x.json",
             r"^manifest: entry 'a': path 'packs/Nul/x\.json': 'Nul' is a name Windows keeps for a device"),
            ("Windows keeps, with a suffix", "packs/a/com1.json", r"'com1\.json' is a name Windows keeps"),
            ("to a listed .html", "variants/a/index.HTML", r"^manifest: entry 'a': path 'variants/a/index\.HTML' is a "
             r"\.html file: variants/ holds only \.json, \.glb, \.gltf, \.bin, \.png, \.md, \.azkp files"),
            ("to a shipped answer outside variants/", "clips/a/usa-0.azkp",
             r"'clips/a/usa-0\.azkp' is a \.azkp file: clips/ holds only \.glb, "),
            ("to a picture in packs/", "packs/a/x.png", r"'packs/a/x\.png' is a \.png file: packs/ holds only \.json, "),
            ("to a suffix-less file", "sounds/a/x", r"'sounds/a/x' is a suffix-less file: sounds/ holds only \.wav, "))},
        **{f"a recipe's {what} outside its folder": (lambda text=text: _player_variants.load_variants(
            text, str(tmp_path / "variant.json")), rf"^variant 'mine' \([^)]*\): {field}: '{re.escape(name)}' is not "
            r"a file in the recipe's folder") for what, text, field, name in (
            ("clip", recipe("clips", {"hip_idle": booblord["clips"]["hip_idle"] | {"file": "../../x.glb"}}),
             "clips.hip_idle.file", "../../x.glb"),
            ("mesh", recipe("mesh", {"gltf": {"file": "/etc/x.glb", "sha256": "0" * 64}}), "mesh.gltf.file", "/etc/x.glb"))},
        "a shipped answer that isn't its row's": (lambda: shipped.plan(
            [unlisted], gate.USA, {CHARACTERS: b"x" * 16}, SimpleNamespace(_current={}), tmp_path / "shipped"), None),
        "a shipped answer past the size its head lists": (lambda: shipped.decode(answer(1024), {CHARACTERS: b"x" * 16}),
                                                          r"^shipped: gamedata/characters\.xbr inflates past the "
                                                          r"1,024 bytes its head lists"),
        "two paths one but for letter case": (lambda: content.check(manifest([
            {"id": "a", "files": [{"path": "packs/a/X.json", "sha256": "0" * 64, "size": 0}]},
            {"id": "b", "files": [{"path": "packs/a/x.json", "sha256": "0" * 64, "size": 0}]}])),
            r"^manifest: entry 'b': packs/a/x\.json is entry 'a''s too"),
    }
    assert list(_player_variants.load_variants(json.dumps({"mine": booblord}), str(tmp_path / "variant.json"))) == [
        "mine"]   # her own recipe as a user's reads (and the reader is warm)
    slow = {}
    for row, (call, why) in rows.items():
        tracemalloc.start()
        try:
            start = time.perf_counter()
            if why is None:
                call()
            else:
                with pytest.raises(ValueError, match=why):
                    call()
            took, held = time.perf_counter() - start, tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        if took >= 0.1 or held >= 16 << 20:
            slow[row] = f"{took:.3f} s, {held:,} bytes held"
    assert not slow, slow
    assert seen == [(f"packs/a/{k}.json", [f"{j}.json" for j in range(k)]) for k in range(4)]   # each held alone
    assert not (tmp_path / "new").exists()   # a refused Install writes nothing, not even the folders above it
    updated, victim = tmp_path / "updated", tmp_path / "victim.json"
    (updated / "packs/a").mkdir(parents=True)
    victim.write_bytes(b"{}")
    olds = ("packs/a/old.json", "packs/a/old.txt", "packs/a/Note.md")   # an older version's .txt goes too, though
    for old in olds:                                                     # packs/ now refuses one; Note.md is renamed
        (updated / old).write_bytes(b"{}")
    (updated / content.INSTALLED).write_text(json.dumps({"a": {"version": 1, "source": "", "files": {
        "../victim.json": "0" * 64, str(victim): "0" * 64} | dict.fromkeys(olds, "0" * 64)}}))
    news = {"packs/a/new.json": b"[]", "packs/a/note.md": b"# v2\n"}
    content.install(manifest([{"id": "a", "version": 2, "files": [
        {"path": path, "sha256": _sha256(data), "size": len(data)} for path, data in news.items()]}]), "a",
        news.__getitem__, updated)
    assert victim.is_file() and sorted(p.name for p in (updated / "packs/a").iterdir()) == ["new.json", "note.md"]
    assert (updated / "packs/a/note.md").read_bytes() == news["packs/a/note.md"]   # a rename by letter case kept
    assert set(content.installed(updated)["a"]["files"]) == set(news)   # an Update removes only its own (SEC-15)
    assert textures.read_png(_png(2, 2, b"\x00" + bytes(8) + b"\x00" + bytes(8))).shape == (2, 2, 4)


def test_an_install_takes_its_hosts_refusal_and_an_entry_keeps_its_description(tmp_path):
    """An entry's optional ``description`` (one line of plain text, at most 200 characters) is kept by
    ``content.check`` and in the entry's state; another is refused by name. A host's ``refusal`` (Step 4.3k:
    the sdk's reading of a community pack) reads each entry from its checked files, at ``content.verify``
    and at ``content.install``, which then writes nothing; with none, a built-in variant's recipe is read
    (``builtin_refusal``)."""
    good = _source(tmp_path / "source", {"packs/a/pack.json": b"{}", "packs/b/pack.json": b"[]"},
                   [{"id": "a", "files": ["packs/a/pack.json"], "requires": ["b"], "description": "Harder fights"},
                    {"id": "b", "files": ["packs/b/pack.json"]}])
    checked = content.check(json.dumps(good))
    assert checked == good and checked["entries"][0]["description"] == "Harder fights"
    assert [e.get("description") for e in content.states(checked, {})] == ["Harder fights", None]
    for bad in ("", " ", "x" * 201, "two\nlines", 7):
        with pytest.raises(ValueError, match=r"^manifest: entry 'a': description is no line of plain text of at "
                                             r"most 200 characters"):
            content.check(good | {"entries": [good["entries"][0] | {"description": bad}, good["entries"][1]]})
    files = {"packs/a/pack.json": b"{}", "packs/b/pack.json": b"[]"}
    read = []

    def refusal(entry, landed) -> str | None:
        read.append((entry["id"], {path: landed[path] for path in landed}))
        return "packs/a/pack.json isn't a community pack" if entry["id"] == "a" else None
    with pytest.raises(ValueError, match=r"^a: packs/a/pack\.json isn't a community pack"):
        content.verify(good, "a", files, refusal=refusal)
    assert read == [("b", {"packs/b/pack.json": b"[]"}), ("a", {"packs/a/pack.json": b"{}"})]
    folder, read[:] = tmp_path / "content", []
    with pytest.raises(ValueError, match=r"^a: packs/a/pack\.json isn't a community pack"):
        content.install(good, "a", lambda path: (tmp_path / "source" / path).read_bytes(), folder, refusal=refusal)
    assert read == [("b", {"packs/b/pack.json": b"[]"}), ("a", {"packs/a/pack.json": b"{}"})] and not folder.exists()
    assert set(content.install(good, "a", files.__getitem__, folder, refusal=lambda *_: None)) == {"a", "b"}


def test_the_hosts_content_reads_stop_at_a_files_listed_size_and_a_too_deep_or_big_manifest_is_refused_by_name(
        tmp_path, monkeypatch):
    """The sdk's half of Install (Step 4.3m, SEC-9, SEC-6): a source's file is read to at most one past the size its
    manifest lists, and one past it is refused by name with nothing written; a manifest past what a manifest may
    hold is refused as that (it lists no size for itself); a manifest nested too deep to read or past 1,000 entries
    is refused by name as any other fault, never a RecursionError: ``content.check``'s own refusal (S1's SEC-6, the
    hosts adding no catch of their own; ``sdk.content`` lists it as the source's fault, ``sdk.content_check``, the
    site's, refuses it)."""
    source, folder = tmp_path / "source", tmp_path / "content"
    monkeypatch.setattr(content, "ROOT", folder)
    _source(source, {"packs/a/pack.json": b"{}"}, [{"id": "a", "files": ["packs/a/pack.json"]}])
    (source / "packs/a/pack.json").write_bytes(b"{}" + b" " * 64)
    with pytest.raises(OSError, match=r"packs/a/pack\.json: past the 2 bytes its manifest lists$"):
        sdk.content_install({"id": "a", "source": str(source)})
    listed = (source / content.MANIFEST).read_bytes()
    (source / content.MANIFEST).write_bytes(listed + b" " * content.MAX_MANIFEST)
    with pytest.raises(OSError, match=r"manifest\.json: past the 1,048,576 bytes a manifest may hold$"):
        sdk.content_install({"id": "a", "source": str(source)})
    assert not folder.exists()
    entry = {"kind": "pack", "title": "x", "author": "a", "licence": "MIT", "version": 1, "files": []}
    chain = json.dumps({"format": content.FORMAT, "schema_version": content.SCHEMA_VERSION, "entries": [
        entry | {"id": f"e{k}", "requires": [f"e{k + 1}"] if k < 1499 else []} for k in range(1500)]})
    for deep, why in (("[" * 200_000, "not JSON (nested too deep)"), (chain, "1,500 entries, past the 1,000")):
        (source / content.MANIFEST).write_text(deep, encoding="utf-8")
        view = sdk.content({"source": str(source)})
        assert view["why"].startswith(f"can't read {source}: manifest: {why}") and view["manifest"] is None
        with pytest.raises(ValueError, match=rf"^manifest: {re.escape(why)}"):
            sdk.content_check({"manifest": deep})


def test_the_characters_view_lists_178_species_in_their_grades(usa_iso, tmp_path, monkeypatch):
    """``sdk.pickers`` (the Characters tab, D877): the species the player can wear in ``critters_engine``'s order
    (``player_models``' usable ones), each in its grade's colour as Modkit's picker shows it (60 green, 44 yellow,
    73 untested and marked, 1 unseen: Modkit's map-scope record, 2026-10-28), the untested greyed; 76 of them objects
    (D1034: ``characters.object_bodies``, the untested and the three clipless statues; species.json's the same with no
    image); a weapon on an
    untested model reads grey, never better than the model (AZ-807); a community entry before Install is one row,
    marked, and a variant's options its recipe decides are locked and left out of the build's character."""
    from azurkit.tools.characters import _player_character as swap
    from azurkit.tools.characters import picker

    monkeypatch.setattr(content, "ROOT", tmp_path / "content")
    with iso.Reader(usa_iso) as r:
        config, bodies = r.read(characters.CONFIG), r.read(CHARACTERS)
    usable = [m.species for m in swap.player_models(config, bodies) if m.status != swap.REFUSED]
    view = sdk.pickers({"iso": str(usa_iso), "character": {"species": "keylord"}})
    assert [s["name"] for s in view["species"]] == usable and len(usable) == 178
    colours = {v: k for k, v in picker.STATUS_COLOURS.items()}
    tally = {k: sum(colours[s["colour"]] == k and not s["untested"] for s in view["species"])
             for k in picker.STATUS_COLOURS}
    assert tally | {"untested": sum(s["untested"] for s in view["species"])} == {
        "green": 60, "yellow": 44, "red": 0, "unseen": 1, "untested": 73}
    assert all(s["colour"] == picker.STATUS_COLOURS["unseen"] and s["label"].endswith("(not yet tested)")
               for s in view["species"] if s["untested"])
    objects = {s["name"] for s in view["species"] if s["object"]}   # D1034: the 73 pickups and the clipless statues
    assert objects == {s["name"] for s in view["species"] if s["untested"]} | {"gargoylestone", "tesla_tree",
                                                                                 "tesla_tree_x"} and len(objects) == 76
    assert objects == {s["name"] for s in sdk.pickers({"iso": None})["species"] if s["object"]}   # species.json's
    untested = next(s["name"] for s in view["species"] if s["untested"])
    picks = sdk.pickers({"iso": str(usa_iso), "character": {"species": untested}})["chosen"]["weapons"]
    assert len(picks) > 1 and {p["colour"] for p in picks[1:] if p.get("fit") not in ("default", "same")} == {
        picker.STATUS_COLOURS["unseen"]}
    manifest = {"format": content.FORMAT, "schema_version": 1, "entries": [{
        "id": "beamlord", "kind": "variant", "title": "Beamlord", "author": "Azurik-Modding-Hub", "licence": "MIT",
        "version": 1, "files": [{"path": "variants/beamlord/variant.json", "sha256": "0" * 64, "size": 2}],
        "requires": []}]}
    view = sdk.pickers({"iso": str(usa_iso), "character": {"species": "beamlord", "mode": "garret4", "scale": 1.0},
                        "content": {"manifest": manifest}})
    assert [(e["id"], e["state"], e["variants"]) for e in view["community"]] == [("beamlord", "install", [])]
    assert view["chosen"]["locked"]["mode"] == "own" and view["character"] == {"species": "beamlord"}


def test_the_characters_view_on_an_image_tells_its_models_read_then_the_view_so_the_sites_bar_moves(usa_iso,
                                                                                                    monkeypatch):
    """Step 4.3 round 3 (S10, S11 in Chromium, D980): ``sdk.pickers`` on an
    image tells its two steps (``read``), the image's model files read and
    then the models' view, the first only while the image isn't read yet:
    the site's worker posts them, so a model picked while the tab's own
    first answer (a new worker's) is worked shows its bar moving (1.4 s
    with none in Chromium), and never back from one answer to the next."""
    monkeypatch.setattr(sdk, "_GAME", {})   # the image's model files not kept from another test
    told: list[dict] = []
    for species in ("garret4", "keylord"):
        sdk.pickers({"iso": str(usa_iso), "character": {"species": species}}, progress=told.append)
    assert [(s["stage"], s["percent"], s["label"]) for s in told] == [
        ("read", 0, "Reading your image's models"), ("read", 50, "Reading the models"),
        ("read", 50, "Reading the models")]


def test_the_shipped_species_and_pictures_are_what_each_image_gives(usa_iso, europe_iso):
    """The Characters tab's shipped files (Step 4.3f, D961; the page shows them before an image) are what
    ``scripts/record_goldens.py``'s characters family makes from the images, byte for byte: ``species.json``, the
    species ``player_models`` reads from USA's image and from Europe's (the same), which the view lists with no image
    (in their grades), the no-image view itself, and each body's two pictures, ``picker.preview``'s (the app's
    draw) from USA's image, and from Europe's the same bytes. A built-in variant's are drawn again only when its
    recipe changes (its dress takes minutes), so here they are the recorded ones."""
    from azurkit.tools.characters import picker

    made = record_goldens.characters(record_goldens.Images({gate.USA: usa_iso, gate.EUROPE: europe_iso}), 1)
    shipped = record_goldens.kept_files((record_goldens.PICTURES, record_goldens.SPECIES))
    assert {rel: _sha256(data) for rel, data in made.items()} == {rel: _sha256(data) for rel, data in shipped.items()}
    assert picker.species_list() == json.loads(made[record_goldens.SPECIES]) and len(picker.species_list()) == 178
    with iso.Reader(europe_iso) as r:
        bodies = r.read(CHARACTERS)
    drawn = {f"{record_goldens.PICTURES}/{body.replace('/', '--')}.{view}.png": png
             for body in dict.fromkeys(b for _, b, _ in picker.species_list())
             for view, png in picker.preview(bodies, body).items()}
    assert len(drawn) == 272 and {rel: _sha256(png) for rel, png in drawn.items()} == {
        rel: _sha256(made[rel]) for rel in drawn}


def test_the_shipped_sizes_are_each_listed_species_and_built_in_variant_on_both_releases():
    """``scripts/record_shipped.py`` sizes each species ``species.json`` lists (its ``[species, body, object]``
    rows) and each built-in variant, at its defaults, and ``shipped.json`` holds a size of each on both releases
    (D995): the recorder reads the list as its rows are, so it can re-record them."""
    want = {(release.iso_sha256, json.dumps(shipped._json(recipe), sort_keys=True))
            for release in gate.RELEASES for recipe in record_shipped.recipes()}
    assert len(want) == 2 * 183 and {record_shipped._key(row) for row in shipped.table()["size"]} == want


def test_a_variants_shipped_pictures_are_drawn_again_when_the_recipe_it_is_from_changes():
    """``scripts/record_goldens.py`` draws a built-in variant's shipped pictures again when its key in
    ``web/characters/index.json`` changes: the sha256 of its recipe as it builds, so booblord's three looks
    ``from`` her are drawn again with her (Step 4.3: her vase dropped, which none of their own entries names),
    and beamlord's, from none, is his entry's."""
    doc = json.loads(_player_variants.BUILTIN.read_text(encoding="utf-8"))
    keys = record_goldens.recipe_keys(doc)
    assert keys["beamlord"] == _sha256(json.dumps(doc["beamlord"], sort_keys=True).encode())
    doc["booblord"]["mesh"]["drop"] = []
    assert sorted(n for n, key in record_goldens.recipe_keys(doc).items() if key != keys[n]) == [
        "booblord", "booblord_high", "booblord_high_human", "booblord_human"]


def test_the_g4_buttons_values_are_their_goldens_garret_match(usa_iso):
    """``sdk.match`` (P52, D358; Modkit's ``_player_match``, ported): keylord's and beamlord's Model size,
    Attack reach, speed and damage over the packs on by default are the golden's exactly (``matches.json``,
    first recorded as Modkit's ``garret_match``), each box's text 4 figures rounded up; garret4's own body
    matches at 1."""
    packs = {name: {} for name, pack in mods.PACKS.items() if pack.default_on}
    keys = dict(zip(characters.MATCHED, ("size", "reach", "speed", "damage")))
    for name, want in _golden("matches.json")["usa"].items():
        got = sdk.match({"iso": str(usa_iso), "packs": packs, "character": {"species": name}})
        assert got["values"] == {k: want[v] for k, v in keys.items()} and got["why"] == want["why"], name
        assert all(float(got["text"][k]) >= v and len(got["text"][k].replace(".", "").lstrip("0")) <= 4
                   for k, v in got["values"].items()), name
    garret = sdk.match({"iso": str(usa_iso), "packs": packs, "character": {"species": "garret4"}})
    assert garret["values"] == dict.fromkeys(characters.MATCHED, 1.0) and garret["text"]["scale"] == "1"


def test_the_recorder_writes_the_characters_goldens_from_azurkits_own_builds(usa_iso, tmp_path, monkeypatch, capsys):
    """The characters' goldens are AzurKit's own (Step 4.12c; before it Modkit's oracle bundle):
    ``scripts/record_goldens.py`` writes ``matches.json`` from ``sdk.match`` on the player's image byte for byte
    as committed, naming the case it wrote, and ``--check`` names a case that differs."""
    committed = (record_goldens.GOLDENS / record_goldens.MATCHES).read_text(encoding="utf-8")
    monkeypatch.setattr(record_goldens, "GOLDENS", tmp_path)
    images = record_goldens.Images({gate.USA: usa_iso})
    assert record_goldens.main([record_goldens.MATCHES], images) == 0
    assert capsys.readouterr().out.splitlines() == ["wrote: matches.json", "changed: matches.json: usa"]
    assert (tmp_path / record_goldens.MATCHES).read_text(encoding="utf-8") == committed
    (tmp_path / record_goldens.MATCHES).write_text(record_goldens.text({"usa": {}}), encoding="utf-8")
    assert record_goldens.main(["--check", record_goldens.MATCHES], images) == 1
    assert capsys.readouterr().out == "differs: matches.json: usa\n"


# --- the built-in variants, the effects templates and a seed with a character (Step 4.3c2) ----------------------

SEEDED = "randomize-full:seed=0,all"


def _content_source() -> str:
    """Azurik-Custom-Content's source: ``$AZURKIT_CONTENT_SOURCE``, else its
    clone beside the main checkout."""
    if env := os.environ.get(sdk.SOURCE_ENV):
        return env
    common = subprocess.run(["git", "-C", str(record_goldens.ROOT), "rev-parse", "--path-format=absolute",
                             "--git-common-dir"], capture_output=True, text=True, check=True).stdout.strip()
    return str(Path(common).parent.parent / "Azurik-Custom-Content")


@pytest.fixture
def booblords(tmp_path_factory, monkeypatch):
    """Booblord installed from Azurik-Custom-Content (:func:`_content_source`:
    Install's own path, ``sdk.content_install``, every file checked against
    that repository's own manifest) into a new content folder, which the
    build processes read (``AZURKIT_CONTENT``). A source it can't read stops
    the test with one message."""
    source, folder = _content_source(), tmp_path_factory.mktemp("content")
    monkeypatch.setattr(content, "ROOT", folder)
    monkeypatch.setenv(content.ENV, str(folder))
    try:
        sdk.content_install({"id": "booblord", "source": source})
    except (OSError, ValueError) as exc:
        pytest.fail(f"Azurik-Custom-Content's booblord can't be installed from {source} (set "
                    f"{sdk.SOURCE_ENV}, or clone it beside the main checkout): {exc}", pytrace=False)


def _variants(release, folder: Path) -> dict[str, dict]:
    """``{case: its recipe}`` of G3's cases on ``release`` that wear a
    variant: each built-in's (:data:`VARIANTS`, booblord with a weapon
    among them) and the effects case's, a recipe file's (written in
    ``folder``) whose fireball row is made of the effects templates."""
    return {case: {"packs": {name: {} for name, pack in mods.PACKS.items() if pack.default_on},
                   "character": record_goldens.character(spec, folder)}
            for case, spec in _models(release.name).items()
            if spec["args"]["player_character"] in VARIANTS or spec["args"]["player_variant_file"]}


@pytest.mark.parametrize("release", RELEASES)
def test_each_variant_case_is_its_goldens_file_for_file_and_resource_for_resource(release, request, booblords,
                                                                                  tmp_path):
    """Each of G3's variant cases (:func:`_variants`: on USA the five
    built-in variants' recipes applied to the player's image, booblord's
    clips and voice installed from Azurik-Custom-Content (:func:`booblords`),
    booblord with a weapon,
    and the effects case; on Europe the effects case) built through
    ``sdk.image`` is its golden's file for file and resource for resource, its
    default.xbe written inside its claims and the facts' swap sites
    (:func:`_missed`, in 4 processes: booblord's builds take minutes). Each of
    the release's shipped plans (``shipped.json``, D995: booblord's at the
    page's defaults) is the answer of a fresh dress that reads what it stood on:
    on USA booblord's case's, on Europe one built for it (:data:`PINNED`), so a
    change to her bytes is red until ``scripts/record_shipped.py`` re-records."""
    cases = _variants(release, tmp_path)
    assert len(cases) == {"usa": 7, "europe": 1}[release.name]
    plans = [row for row in shipped.table().get("plan", ()) if row["release"] == release.iso_sha256]
    built = [shipped._page(characters.normalize(recipe["character"])) for recipe in cases.values()]
    cases |= {f"{PINNED}{json.dumps(row['recipe'])}": {"packs": {name: {} for name, pack in mods.PACKS.items()
                                                                 if pack.default_on}, "character": row["recipe"]}
              for row in plans if row["recipe"] not in built}
    first = dict(sorted(cases.items(), key=lambda kv: "booblord" not in kv[0]))   # the longest builds start first
    held: set[str] = set()
    assert _missed(first, request.getfixturevalue(f"{release.name}_iso"), release, workers=4, held=held) == {}
    assert plans and {shipped.name("plan", row) for row in plans} <= held


def test_a_swap_under_the_apps_process_pool_is_its_goldens_file_for_file(usa_iso, no_content, tmp_path, monkeypatch):
    """Step 4.3i: the app's process pool (``azurkit.app.procpool``, the
    swap's ``pool.MAP`` and ``LATER``: Modkit's split over spawned
    children, the dearest items first, and a thread) writes the bytes the
    swap writes in order: keylord's body case and beamlord's reshaped variant
    built under it are their goldens' file for file and resource for
    resource (:func:`_missed`), and its children were used."""
    from azurkit.app import procpool
    from azurkit.tools.characters import pool

    monkeypatch.delenv(procpool.CORES, raising=False)
    monkeypatch.setattr(pool, "MAP", None)
    monkeypatch.setattr(pool, "LATER", None)
    assert procpool.install() >= 2 and (pool.MAP, pool.LATER) == (procpool.map_, procpool.later)
    cases = {case: recipe for case, recipe in (_bodies() | _variants(gate.USA, tmp_path)).items()
             if case.endswith(("=keylord", "=beamlord"))}
    try:
        assert len(cases) == 2 and _missed(cases, usa_iso) == {}
        assert procpool._IDLE
    finally:
        procpool.stop()


def test_a_bodys_answers_kept_in_the_apps_store_build_the_same_image_and_miss_when_a_layer_or_the_content_changes(
        usa_iso, no_content, tmp_path, monkeypatch):
    """Step 4.3i: the swap's answers kept in the app's store
    (``app.swapcache.Folder`` as ``characters.CACHE``, a launch's on the
    same folder) build keylord's image as a fresh dress builds it, without
    working its size and plan out again; an earlier layer changed (a pack
    ticked) works out its plan again, and a changed content folder both."""
    from azurkit.app import swapcache

    kept = []

    class Counted(swapcache.Folder):
        def put(self, key: str, data: bytes) -> None:
            kept.append(key)
            super().put(key, data)

    def keylord(packs: dict) -> list:
        monkeypatch.setattr(characters, "CACHE", Counted(tmp_path / "swap", key=tmp_path / "cache.key"))   # a launch's
        made, _ = sdk.image({"iso": str(usa_iso), "packs": packs, "character": {"species": "keylord"}})
        return [(at, _sha256(data)) for at, data in made.writes]
    first = keylord({})
    assert len(kept) == 2 and keylord({}) == first and len(kept) == 2   # its size and plan, then from the store
    keylord({"fps_unlock": {}})
    assert len(kept) == 3   # the plan over another layer; the size kept
    (content.ROOT / "installed.json").write_text(json.dumps({"booblord": {"version": 1, "source": "", "files": {}}}))
    assert keylord({}) == first and len(kept) == 5


def test_a_shipped_answer_is_taken_only_where_it_stands_on_what_the_build_reads(tmp_path, monkeypatch):
    """D995's shipped answers (``tools/characters/shipped.py``), on made-up
    files: a plan's ``AZKP1`` file (a whole file zstd-compressed against its
    vanilla bytes, a range as it is) decodes to the answer it was made from;
    ``characters.plan`` and ``characters.size`` take a row's answer in place
    of a dress, never keeping it in the app's store, where the row stands on
    the build's release, recipe, fold, claims, content and reads; and a pack
    that changed a file the dress read, another fold or recipe, an installed
    entry the body reads, the file changed by a byte, an answer other than
    its row's and ``shipped.OFF`` each miss (``None``: the swap runs). The
    re-record pin (``shipped.held``) holds a fresh answer to the row it
    stands on, a slider at 1.0 as the page's recipe, and names a stale one."""
    from azurkit.edits.layer import Change, Claim

    made = {f: bytes([k + 1]) * (4096 + k) for k, f in enumerate(characters.READS)}
    vanilla, xbe = ports.Vanilla(gate.USA, made), characters.XBE
    grown = made[CHARACTERS][:100] + b"grown" * 1000 + made[CHARACTERS][100:]
    found = (Layer("player model x", characters.TOOL, characters.KIND, {"species": "x", "variant": "0" * 12},
                   (Change(CHARACTERS, 0, _sha256(made[CHARACTERS]), grown, "x (its archives)", True),
                    Change(xbe, 16, _sha256(made[xbe][16:24]), b"\x90" * 8, "x (default.xbe)")),
                   (Claim(xbe, 16, 8, "shim:x"),)), ["dressed x"], ["a reason"])
    blob = shipped.encode(*found, made)
    assert shipped.decode(blob, made) == found and len(blob) < len(grown) // 4
    monkeypatch.setattr(content, "ROOT", tmp_path)
    staging = characters._over(vanilla, [])[3]
    staging["default.xbe"], staging["config.xbr"]   # what a dress of x reads
    row = shipped.plan_row({"species": "x"}, gate.USA, 1.0, [], found, staging) | {
        "blob": {"path": "variants/x/shipped/usa-0.azkp", "sha256": _sha256(blob), "size": len(blob)}}
    (answer := tmp_path / row["blob"]["path"]).parent.mkdir(parents=True)
    answer.write_bytes(blob)
    table = {"plan": [row], "size": [shipped.size_row({"species": "x"}, gate.USA, 1.25)]}
    monkeypatch.setattr(shipped, "table", lambda: table)
    monkeypatch.setattr(shipped, "OFF", False)

    class Store(dict):
        put = dict.__setitem__
    monkeypatch.setattr(characters, "CACHE", kept := Store())
    assert characters.plan({"species": "x"}, vanilla, [], folded=1.0) == found
    assert characters.size({"species": "x"}, vanilla) == 1.25 and not kept

    def ask(recipe: dict = {"species": "x"}, folded: float = 1.0, before: tuple = ()):
        over = characters._over(vanilla, list(before))
        return shipped.plan(shipped.rows(recipe, gate.USA, folded, list(before)), gate.USA, over[0], over[3])
    pack = Layer("pack p", "mods", "packs", {}, (Change(xbe, 0, _sha256(made[xbe][:4]), b"abcd", "p"),))
    entry = {"x": {"version": 1, "source": "", "files": {"clips/x/a.glb": "0" * 64}}}
    for why, given in {"a pack that changed a file it read": {"before": (pack,)}, "another fold": {"folded": 1.5},
                       "another recipe": {"recipe": {"species": "x", "scale": 2.0}}}.items():
        assert ask(**given) is None, why
    for why, change in {
            "an installed entry it reads": lambda: (tmp_path / content.INSTALLED).write_text(json.dumps(entry)),
            "its file changed by a byte": lambda: answer.write_bytes(blob[:-1] + bytes([blob[-1] ^ 1])),
            "another answer than its row's": lambda: table["plan"].__setitem__(0, row | {"answer": "0" * 64}),
            "shipped.OFF": lambda: monkeypatch.setattr(shipped, "OFF", True)}.items():
        change()
        assert ask() is None, why
        (tmp_path / content.INSTALLED).unlink(missing_ok=True)
        answer.write_bytes(blob)
        table["plan"][0] = row
        monkeypatch.setattr(shipped, "OFF", False)
        assert ask() == found, why
    (tmp_path / content.INSTALLED).write_text(json.dumps(entry))   # an installed entry the body reads: a size miss
    assert shipped.size({"species": "x"}, gate.USA) is None
    (tmp_path / content.INSTALLED).unlink()
    monkeypatch.setattr(shipped, "OFF", True)
    assert shipped.size({"species": "x"}, gate.USA) is None
    seen = {k: v for k, v in row.items() if k != "blob"} | {"recipe": {"species": "x", "scale": 1.0}}   # a golden's
    assert shipped.held({"plan": seen}, table) == ([shipped.name("plan", row)], [])   # the re-record pin's reading
    assert shipped.held({"plan": seen | {"answer": "0" * 64}}, table)[1] == [
        f"the shipped {shipped.name('plan', row)} isn't a fresh dress's (scripts/record_shipped.py)"]


def test_a_changed_dress_in_the_sdk_changes_the_key_the_app_keeps_a_characters_match_under(no_content, monkeypatch):
    """The app keeps a character's G4 match and pictures (``sdk._dress``,
    through ``sdk.match`` and ``sdk.preview``) under the swap's key, whose
    code digest holds ``sdk.py``: an AzurKit whose dress changed, with no
    new version, never answers from what an older one kept."""
    read, dress = Path.read_bytes, Path(sdk.__file__).resolve()
    monkeypatch.setattr(characters, "CACHE", {})

    def key() -> str:
        characters._code.cache_clear()
        return characters.cache_key("match", characters.normalize({"species": "keylord"}), gate.USA, extra={})
    try:
        before = key()
        monkeypatch.setattr(Path, "read_bytes", lambda p: read(p).replace(b"def _dress(", b"def _dress( ")
                            if p == dress else read(p))
        assert key() != before
        monkeypatch.setattr(Path, "read_bytes", read)
        assert key() == before
    finally:
        characters._code.cache_clear()


@pytest.mark.parametrize("release", RELEASES)
def test_a_randomized_build_wears_a_character_as_its_goldens_seed_0_all(release, request):
    """G3's ``seed=0,all`` (Modkit's ``randomize-full --seed 0`` with
    flicken's body, the movement sliders, packs and a config mod, its
    settings flags and obsidian cost; ``record_goldens.recipe``'s
    translation) built through ``sdk.image``: the plan stands on the walk
    and roll the body's size folds, and every file G3 records (Modkit's
    build changed them all but ``training_room.xbr``, its level_patches,
    AZ-009, and filelist.txt, which lists it) is the golden's; the image reads back to the plan, and the
    logic is unverified with the packs' reasons and the body's
    (``characters.reasons``: flicken's x0.351 height, in the words of
    Modkit's verdict of this build). A body no
    sitting graded, with no melee idle swing, a weak attack or one that
    never ends gives Modkit's reasons for each."""
    path = request.getfixturevalue(f"{release.name}_iso")
    spec = record_goldens.cases(G3[release.name])[SEEDED]
    made, report = sdk.image(record_goldens.recipe(G3[release.name], spec, path) | {"iso": str(path)})
    usa, golden = _golden(G3["usa"])[SEEDED], _golden(G3[release.name])[SEEDED]
    want = {f: sha for f, sha in ({f: sha for f, sha in usa.items() if f.endswith(".xbr")} | golden).items()
            if f not in record_goldens.LEVEL_PATCHED}
    assert {f: report["result"].get(f) for f in want} == want and report["conflicts"] == []
    assert set(report["result"]) - set(want) == {"filelist.txt"}
    verdict = report["randomizer"]
    assert (verdict["seed"], verdict["logic_verified"], verdict["conflicts"]) == ("0", False, [])
    assert verdict["why_not"][-1].startswith("the worn body is x0.351 garret4's height, so it touches pickups")
    assert not any(why.startswith("--player-character") for why in verdict["why_not"])
    weak = characters.reasons("nobody", SimpleNamespace(reach=None, damage=0.25, speed=0.0, size=1.0))
    assert [why.split(": ", 2)[1][:20] for why in weak] == [
        "not yet tested as a ", "none of its idle swi", "an attack deals x0.2", "--player-attack-spee"]


def test_a_body_case_under_pyodide_is_its_goldens_file_for_file(usa_iso, pyodide):
    """keylord's case built by ``sdk.image`` under Pyodide on Node (the
    site's runtime, D882: swaps on the site too), from the wheel alone with
    Pyodide's numpy wheel loaded, changes each file G3 records to its
    sha256."""
    case = "randomize-full:player-character=keylord"
    got = pyodide(image=_bodies()[case] | {"iso": str(usa_iso)}, packages=(_pyodide.numpy(),))
    assert (got["code"], got["platform"]) == (0, "emscripten"), got["stderr"][-2000:]
    assert got["report"]["result"] == {f: sha for f, sha in _golden(G3["usa"])[case].items() if f != "ISO"}
