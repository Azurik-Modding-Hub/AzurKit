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

import pytest

from azurkit.core import facts, gate, iso
from azurkit.core.xbr.append import PAGE, NewResource, append_resources, appended
from azurkit.core.xbr.nodes import named_resources, parse_toc, runs
from azurkit.edits.layer import Layer
from azurkit.edits.manifest import image
from azurkit.tools import characters
from azurkit.tools.characters import body_codec as bc
from azurkit.tools.characters.index_xbr import IndexRecord, add_index_records, parse_index_xbr
from scripts import gen_facts

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
