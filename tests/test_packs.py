"""The packs (Step 4.1c: fps_unlock, qol_alloc_race, qol_gem_popups,
qol_other_popups, qol_pickup_anims; Step 4.1e2: player_max_hp,
air_shield_flaps and enemy_damage, config.xbr's; Step 4.1f1: qol_skip_logo,
a shim's) against their goldens (``tests/goldens/``, Step 4.12a).

The facts' XBE half is each release's image's (``scripts/gen_facts.py``),
and each release's vanilla XBE has their section table (AZ-316). Every case
of the sites golden (its sliders' values normalized, Step 4.1e1) writes its
bytes site by site and nothing else; then each G1 case of a ported pack, with its
sliders' values, builds its golden, file by file, on both releases, through
the sdk, and its preset carries its recipe back and nothing from the game;
``azurkit build`` applies the packs on by default (D528) and sets sliders.
A pack that can't apply names each site and why, never its bytes (D35); a
slider at a site writes any finite value there (D23)."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
import struct

import pytest

from azurkit import __version__, cli, sdk
from azurkit.core import facts, gate, iso, xbe
from azurkit.edits import preset
from azurkit.edits.layer import claimed, compose
from azurkit.edits.manifest import image
from azurkit.tools import characters, mods
from azurkit.tools.characters import model_inspect, ports
from azurkit.tools.mods import engine
from scripts import gen_facts, record_goldens
from tests import _g1

SITES = {"usa": "sites.json", "europe": "europe/sites.json"}
RELEASES = [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
            pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe], id="europe")]


def _sha256(data) -> str:
    return hashlib.sha256(data).hexdigest()


def _vanilla_file(path, name: str) -> bytes:
    with iso.Reader(path) as r:
        return r.read(name)


def test_the_shipped_facts_xbe_half_is_the_one_gen_facts_reads_from_each_image(usa_iso, europe_iso):
    """Each release's facts file is what ``scripts/gen_facts.py`` writes
    from its image: the XBE's sha256, size, header, sections, each site's
    vanilla sha256 and each kernel slot, the rest as the file holds it."""
    for release, path in ((gate.USA, usa_iso), (gate.EUROPE, europe_iso)):
        assert facts.path(release).read_text(encoding="utf-8") == gen_facts.text(
            release, _vanilla_file(path, engine.XBE)), release.name


def test_the_recorder_writes_a_golden_from_its_cases_and_check_names_each_case_that_differs(usa_iso, tmp_path,
                                                                                            monkeypatch, capsys):
    """``scripts/record_goldens.py`` builds a golden's cases on the player's
    image and writes the committed file byte for byte, naming each case it
    changed (the editor's two cases here, into an empty folder; its first
    run on every golden left them all unchanged, Step 4.12a); ``--check``
    writes nothing and exits 1 naming each case that differs. Each built
    golden holds exactly its recipes' cases (``resources.json`` each G3 case
    that dresses the player), so a deleted row fails here."""
    for golden in record_goldens.CASED:
        assert record_goldens.recorded(golden).keys() == record_goldens.cases(golden).keys(), golden
    assert {g: rows.keys() for g, rows in record_goldens.recorded(record_goldens.RESOURCES).items()} == {
        f"tests/goldens/{g}": {c for c, spec in record_goldens.cases(g).items() if record_goldens.wears(spec)}
        for g in record_goldens.G3}
    name = "xbr_editor.json"
    committed = (record_goldens.GOLDENS / name).read_text(encoding="utf-8")
    rows = json.loads(committed)
    monkeypatch.setattr(record_goldens, "GOLDENS", tmp_path)
    images = record_goldens.Images({gate.USA: usa_iso})
    assert record_goldens.main([name], images) == 0
    assert capsys.readouterr().out.splitlines() == [f"wrote: {name}", *(f"changed: {name}: {c}" for c in sorted(rows))]
    assert (tmp_path / name).read_text(encoding="utf-8") == committed
    case = sorted(rows)[0]
    rows[case] = {"config.xbr": "0" * 64}
    (tmp_path / name).write_text(record_goldens.text(rows), encoding="utf-8")
    assert record_goldens.main(["--check", name], images) == 1
    assert capsys.readouterr().out == f"differs: {name}: {case}\n"
    assert json.loads((tmp_path / name).read_text(encoding="utf-8"))[case] == {"config.xbr": "0" * 64}


@pytest.mark.parametrize("release", RELEASES)
def test_each_ported_case_writes_the_facts_bytes_site_by_site_and_nothing_else(release, request):
    """The release's XBE has the facts' sections and sha256. For each case
    of the sites golden (``tests/goldens/sites.json``, every XBE pack's,
    ``fps_unlock:target_fps=120`` too), each facts site holds the case's
    recorded bytes (by sha256), or vanilla's when the case leaves it (USA's
    ``.text`` slack among them, where a shim lands), and no byte changed
    outside the case's sites, its shims' claims and the header state they
    derive; every facts site is some case's (none is dead)."""
    with iso.Reader(request.getfixturevalue(f"{release.name}_iso")) as r:
        vanilla, config = r.read(engine.XBE), r.read(engine.CONFIG)
    known = facts.of(release)
    assert (xbe.sections(vanilla), _sha256(vanilla)) == (known.sections, known.sha256)
    golden, recipes = record_goldens.recorded(SITES[release.name]), record_goldens.cases(SITES[release.name])
    xbe_packs = {name for name, pack in mods.PACKS.items() if engine.XBE in pack.files()}
    assert {recipes[case]["pack"] for case in golden} == xbe_packs and len(golden) == 32
    assert {int(va, 16) for spans in golden.values() for va in spans} == set(known.sites)
    for case, spans in golden.items():
        recipe = recipes[case]
        params = mods.normalize({recipe["pack"]: recipe["params"]})[recipe["pack"]]
        layer = mods.plan(mods.PACKS[recipe["pack"]], release, {engine.XBE: vanilla, engine.CONFIG: config}, params)
        built = compose({"default.xbe": vanilla, engine.CONFIG: config}, [layer])[0].get("default.xbe", vanilla)
        derived = bytearray(claimed({"default.xbe": vanilla}, [layer]).get("default.xbe", vanilla))
        drift, masked = [], bytearray(built)
        for va, site in known.sites.items():
            s = max((s for s in known.sections if s.va <= va), key=lambda s: s.va)   # the slack is its section's
            at, want = s.raw + va - s.va, spans.get(f"0x{va:08X}", site.sha256)
            if _sha256(built[at:at + site.size]) != want:
                drift.append(f"0x{va:08X}")
            masked[at:at + site.size] = derived[at:at + site.size]
        for claim in layer.claims:
            masked[claim.offset:claim.offset + claim.size] = derived[claim.offset:claim.offset + claim.size]
        assert drift == [], case
        assert masked == derived, f"{case}: bytes outside its sites, claims and derived state changed"


def _names_numbers_and_hashes(value: object, names: set[str]) -> bool:
    """Every key and string in ``value`` is one of ``names`` or a sha256, and every other leaf a number."""
    if isinstance(value, dict):
        return all(k in names and _names_numbers_and_hashes(v, names) for k, v in value.items())
    if isinstance(value, list):
        return all(_names_numbers_and_hashes(v, names) for v in value)
    if isinstance(value, str):
        return value in names or re.fullmatch(r"[0-9a-f]{64}", value) is not None
    return type(value) in (int, float) and math.isfinite(value)


@pytest.mark.parametrize("release", RELEASES)
def test_each_g1_case_of_a_ported_pack_builds_its_golden_and_its_preset_carries_it_back(release, request):
    """``sdk.image`` with each G1 case of a ported pack (``tests/_g1.py``:
    Europe's config.xbr packs take their USA cases), its sliders at the
    case's values: each file the case changes reads back from the image
    with its sha256, and no other file differs from vanilla but
    ``filelist.txt`` (derived state). A config.xbr slider's vanilla value
    is its default: its pack's default case changes no XBR. The case's
    preset (with the build's report) decodes to its normalized recipe, the
    release and the result, and holds only names, numbers and hashes: no
    image path, no game byte. A pack that requires others (the memory packs
    past upper64, ``Pack.requires``) is refused alone, by name, so its case
    (G1 builds each pack alone) is its layer's image (``edits.manifest.image``)."""
    path = request.getfixturevalue(f"{release.name}_iso")
    cases = _g1.cases(release)
    assert {case.pack for case in cases.values()} == set(mods.PACKS)
    assert {name: pack.requires for name, pack in mods.PACKS.items() if pack.requires} == {
        "qol_memory_upper64_gpu": ("qol_memory_upper64",),
        "qol_memory_upper256": ("qol_memory_upper64", "qol_memory_upper64_gpu")}
    names = {*preset.KEYS, *preset.LAYER_KEYS, "kind", "release", "iso_sha256", preset.FORMAT, __version__, "mods",
             "packs", "vanilla", release.name, *mods.PACKS, *(s.name for p in mods.PACKS.values() for s in p.sliders())}
    stamp = gate.verify(str(path), whole=False)
    for name, case in cases.items():
        packs, pack = {case.pack: case.params}, mods.PACKS[case.pack]
        if pack.requires:
            with pytest.raises(ValueError, match=re.escape(f"pack {case.pack!r} needs 'qol_memory_upper64'")):
                sdk.image({"iso": str(path), "packs": packs})
            base = {file: _vanilla_file(path, file) for file in pack.files()}
            made, manifest = image(stamp, [mods.plan(pack, release, base, case.params)], base)
            result = dict(manifest.result)
        else:
            made, report = sdk.image({"iso": str(path), "packs": packs})
            result = report["result"]
        with iso.Reader(made) as r:
            assert {file: _sha256(r.read(file)) for file in case.files} == case.files, name
        _g1.check(result, case, name)
        if pack.requires:
            continue
        assert [layer["id"] for layer in report["layers"]] == [f"pack {case.pack}"] and report["conflicts"] == []
        shared = sdk.preset_decode(sdk.preset_encode({"iso": str(path), "packs": packs}, report))
        assert (shared["base"]["release"], shared["layers"][0]["recipe"], shared["result"]) == (
            release.name, mods.normalize(packs), report["result"]), name
        assert _names_numbers_and_hashes(shared, names | report["result"].keys()), name
    for name, pack in mods.PACKS.items():
        assert not cases[name].files.keys() & {s.file for s in pack.sliders() if isinstance(s, mods.XbrParametricEdit)}


def test_azurkit_build_applies_the_packs_on_by_default_and_a_mods_file_which_open_reads_back(europe_iso, tmp_path,
                                                                                               capsys):
    """``azurkit packs`` lists the packs in the order a build applies them,
    with their sliders; ``azurkit build`` with none named applies those on
    by default (D528, D571, D588): the load budget, the two upper-64 MiB
    packs and qol_alloc_race (``--no-pack qol_memory_upper64`` leaves out
    the GPU pack that requires it too, test_a_choice_moves_what_it_needs_and_what_needs_it); less the three memory packs (``--no-pack``),
    the written image's XBE holds qol_alloc_race's golden.
    ``--pack-param PACK.SLIDER=VALUE`` sets a slider of a pack the build
    applies, and is refused by name otherwise. ``--mods FILE`` (Q268) adds
    its xbr operations, and a mods file with a packs layer replaces the
    packs on by default; ``azurkit open`` prints the written build's mods
    file, which holds its packs and operations."""
    assert cli.main(["packs"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[:2] for line in lines] == [[name, "on" if p.default_on else "off"] for name, p in mods.PACKS.items()]
    assert lines[0].startswith("fps_unlock") and lines[0].endswith(" [target_fps=60]")
    assert cli.recipe("x.iso", ["fps_unlock"], [], True, ["fps_unlock.target_fps=120"])["packs"] == {
        "fps_unlock": {"target_fps": 120.0}, "qol_memory_budget": {}, "qol_memory_upper64": {},
        "qol_memory_upper64_gpu": {}, "qol_alloc_race": {}}
    for given, refused in (("fps_unlock.target_fps=fast", "not PACK.SLIDER=NUMBER"),
                           ("fps_unlock=120", "not PACK.SLIDER=NUMBER"),
                           ("qol_gem_popups.x=1", "the build doesn't apply 'qol_gem_popups'")):
        with pytest.raises(ValueError, match=re.escape(f"--pack-param {given}: {refused}")):
            cli.recipe("x.iso", ["fps_unlock"], [], True, [given])
    assert cli.recipe("x.iso", [], [], True, [], {"packs": {"fps_unlock": {"target_fps": 120}}})["packs"] == {
        "fps_unlock": {"target_fps": 120}}
    golem = {"op": "set", "file": "gamedata/config.xbr", "table": "critters_damage", "entity": "golem",
             "prop": "hitPoints", "value": 321}
    given = tmp_path / "mods.json"
    given.write_text(json.dumps({"format": "azurkit-preset", "schema_version": 1, "layers": [
        {"tool": "data", "kind": "xbr", "recipe": {"ops": [golem]}}]}), encoding="utf-8")
    out = tmp_path / "europe.iso"
    try:
        memory = ("qol_memory_budget", "qol_memory_upper64", "qol_memory_upper64_gpu")
        assert cli.main(["build", "--iso", str(europe_iso), "--out", str(out), "--mods", str(given),
                         *(arg for name in memory for arg in ("--no-pack", name))]) == 0
        with iso.Reader(out) as r:
            assert _sha256(r.read("default.xbe")) == _g1.cases(gate.EUROPE)["qol_alloc_race"].files["default.xbe"]
        assert capsys.readouterr().out.splitlines()[:2] == ["pack qol_alloc_race: 8 sites, 2360 B",
                                                            "data xbr: 1 sites, 8 B"]
        assert cli.main(["open", str(out)]) == 0
        opened = json.loads(capsys.readouterr().out)
    finally:
        out.unlink(missing_ok=True)
    assert opened["base"]["release"] == "europe"
    assert sdk.read_mods(opened) == {"packs": {"qol_alloc_race": {}}, "xbr": [golem]}


VANILLA = bytes(range(256))   # the synthetic XBE: one .text section at 0x1000


def test_a_choice_moves_what_it_needs_and_what_needs_it_with_a_line(capsys):
    """One rule (``mods.settle``, D1061), the CLI's flags and a mods file's and
    a link's packs: ``--pack`` completes its needs, ``--no-pack`` takes off
    what depends on it, each move with a line before the layers and none for
    a pack named or already there; a pack that needs one taken away stays
    refused by name, and a build's complete manifest moves nothing."""
    budget, up64, gpu, up256 = "qol_memory_budget", "qol_memory_upper64", "qol_memory_upper64_gpu", "qol_memory_upper256"
    race = "qol_alloc_race"
    tick = {up64: f"Also ticked {up64}: {gpu} places its textures and meshes in the memory {up64} opens.",
            gpu: f"Also ticked {gpu}: {up256} extends the memory {up64} and {gpu} use."}
    gone = {gpu: f"Also unticked {gpu}: it places its textures and meshes in the memory {up64} opens.",
            up256: f"Also unticked {up256}: it extends the memory {up64} and {gpu} use."}
    layer = lambda *names: {"format": "azurkit-preset", "schema_version": 1, "layers": [
        {"tool": "mods", "kind": "packs", "recipe": {name: {} for name in names}}]}
    file = sdk.read_mods(layer(up64, gpu))
    assert file == {"packs": {up64: {}, gpu: {}}}
    for packs, no_packs, defaults, given, chosen, lines in (
            ([up256], [], False, None, [up64, gpu, up256], [f"Also ticked {up64}: {up256} extends the memory {up64} and {gpu} use.",
                                                             tick[gpu]]),
            ([gpu], [], False, None, [up64, gpu], [tick[up64]]),
            ([up256], [], True, None, [budget, up64, gpu, up256, race], []),
            ([], [up64], True, None, [budget, race], [gone[gpu]]),
            ([], [gpu], True, None, [budget, up64, race], []),
            ([], [up64], True, {"packs": {up64: {}, gpu: {}, up256: {}}}, [], [gone[gpu], gone[up256]]),
            ([], [up64], True, file, [], [gone[gpu]])):
        made = cli.recipe("x.iso", packs, no_packs, defaults, (), given)
        assert (list(made["packs"]), capsys.readouterr().out.splitlines()) == (chosen, lines), (packs, no_packs, given)
    with pytest.raises(ValueError, match=re.escape(f"pack {gpu!r} needs {up64!r} in the same build")):
        cli.recipe("x.iso", [gpu], [up64], True)
    assert capsys.readouterr().out == ""
    for given, added in ((layer(gpu), {gpu: {}, up64: {}}), (layer(up256), {up64: {}, gpu: {}, up256: {}})):
        read = sdk.read_mods(given)
        loaded = sdk.mods_file({"text": json.dumps(given)})["preset"]
        assert (read["packs"], loaded["layers"][0]["recipe"], loaded["settled"]) == (added, added, read["settled"])
        assert read["settled"] and all(line.startswith("Also ticked ") for line in read["settled"])
    linked = sdk.preset_decode(preset.encode(layer(gpu)))
    assert (linked["layers"][0]["recipe"], linked["settled"]) == ({up64: {}, gpu: {}}, [tick[up64]])
    assert "settled" not in sdk.mods_file({"text": json.dumps(layer(up64, gpu))})["preset"]


def test_ticking_upper256_raises_a_bodys_limit_with_the_ticks_that_would_take_it_named(usa_iso, monkeypatch):
    """A build that asks no ``ram`` takes the lines of what its own XBE carries:
    49.5 MiB at the default packs, 127 with qol_memory_upper256 ticked, which
    the page and CLI never asked for by the machine's size; a recipe's ``ram``
    128 keeps its lines, and a refusal names ticks, not flags AzurKit lacks."""
    swap = characters._swap()
    monkeypatch.setattr(model_inspect, "own_runs", lambda *_, **__: {
        "bytes": 60 * model_inspect.MiB, "largest": 30 * model_inspect.MiB, "by_tag": {"mesh": 30 * model_inspect.MiB}})
    defaults = {name: {} for name, pack in mods.PACKS.items() if pack.default_on}
    stamp = gate.verify(str(usa_iso), whole=False)
    build = ports.Build(ports.Vanilla(stamp.release, stamp.path, stamped=stamp), taken=[],
                        packs=characters.packs_view(stamp.release, mods.PACKS))

    def weighed(packs: dict, ram: int | None) -> list[str]:
        made = sdk.image({"iso": str(usa_iso), "packs": packs})[0]
        with iso.Reader(made) as r:
            game = {"default.xbe": r.read("default.xbe"), "characters.xbr": b""}
        with ports.building(build):
            return swap._load_budget(game, "body", "big", False, ram)

    up256 = defaults | {"qol_memory_upper256": {}}
    for packs, ram, limit in ((defaults, None, 49.5), (up256, 128, 49.5)):
        with pytest.raises(ValueError, match=rf"pass the {limit:g} MiB .*or tick qol_memory_upper256 for a 256 MiB") as why:
            weighed(packs, ram)
        assert "--ram" not in str(why.value)
    assert "--ram" not in "".join(said := weighed(up256, None)) and "without qol_memory_upper256" in said[-1]


def _synthetic(monkeypatch) -> None:
    """Synthetic facts over :data:`VANILLA` (no game bytes): sites at 0x1010
    (4 B) and 0x1030 (2 B) holding its bytes, 0x1020 (4 B) holding others;
    Europe moves only 0x1010, and has no 0x1040."""
    usa = facts.Facts(gate.USA, _sha256(VANILLA), 256, (xbe.Section(".text", 0x1000, 0x100, 0, 0x100, 0),),
                      {va: facts.Site(va, size, _sha256(VANILLA[va - 0x1000:va - 0x1000 + size]))
                       for va, size in ((0x1010, 4), (0x1030, 2))} | {0x1020: facts.Site(0x1020, 4, _sha256(b"ours"))},
                      None, {})
    europe = dataclasses.replace(usa, release=gate.EUROPE, addresses={0x1010: 0x1010}, absent={0x1040: "rebuilt"})
    monkeypatch.setattr(engine.facts_, "of", {gate.USA: usa, gate.EUROPE: europe}.get)


def _slider(name: str, va: int = 0, **kw) -> engine.ParametricPatch:
    return engine.ParametricPatch(va=va, name=name, label=name, default=kw.pop("default", 1.0), slider_min=0,
                                  slider_max=2, slider_step=0.1, **kw)


def test_a_pack_that_cant_apply_names_each_site_and_why_never_its_bytes(monkeypatch):
    """Synthetic facts over a synthetic XBE (no game bytes): every failing
    site of a pack is named in one error, by label and address, with why:
    other bytes there (named by size and sha256), a patch of another size,
    no facts site, no address in the release, a write outside a
    custom_apply's footprint; and a pack is refused by name for another
    release, an XBE that isn't vanilla, or a parameter it doesn't take."""
    vanilla = VANILLA
    held = vanilla[0x20:0x24]
    _synthetic(monkeypatch)

    def refused(pack, release=gate.USA, xbe_bytes=vanilla, **params) -> str:
        with pytest.raises(mods.PackError) as caught:
            engine.plan(pack, release, {engine.XBE: xbe_bytes}, params)
        assert held.hex() not in str(caught.value) and repr(held) not in str(caught.value)
        return str(caught.value)

    site = lambda va, patch, label: engine.PatchSpec(label=label, va=va, patch=patch)   # noqa: E731
    sites = engine.Pack("p", "", sites=(site(0x1010, b"ok!!", "fine"), site(0x1020, b"1234", "held"),
                                         site(0x1030, b"123", "long"), site(0x1050, b"1", "none")))
    assert refused(sites) == (
        "pack 'p': 3 site(s) failed: held at 0x00001020: default.xbe holds "
        f"<4 B, sha256 {_sha256(held)[:12]}> there, not the facts' <4 B, sha256 {_sha256(b'ours')[:12]}>; "
        "long at 0x00001030: the patch is 3 B, the facts' site 2 B; "
        "none at 0x00001050: the USA facts have no patch site at 0x00001050")
    assert refused(engine.Pack("p", "", sites=(site(0x1040, b"1", "gone"),)), gate.EUROPE) == (
        "pack 'p': 1 site(s) failed: gone at 0x00001040: 0x00001040 has no Europe address: rebuilt")

    def writes(xbe_view, value: float):
        xbe_view.patch(site(0x1010, b"ok!!", "inside"))
        xbe_view.patch(site(0x1030, b"12", "outside"))
    custom = engine.Pack("c", "", sites=(_slider("value"),), custom_apply=writes, footprint=(engine.Place(va=0x1010),))
    assert refused(custom) == ("pack 'c': 1 site(s) failed: outside at 0x00001030: "
                               "it is outside the pack's declared footprint")
    assert refused(custom, speed=2) == "pack 'c': no parameter 'speed' (its parameters: value)"
    assert refused(dataclasses.replace(custom, releases=("usa",)), gate.EUROPE) == (
        "pack 'c' is not available on the Europe release (it supports usa)")
    assert refused(custom, xbe_bytes=vanilla[::-1]) == (
        f"pack 'c': default.xbe <256 B, sha256 {_sha256(vanilla[::-1])[:12]}> is not the vanilla USA one")
    layer = engine.plan(engine.Pack("q", "", sites=(site(0x1010, b"ok!!", "fine"),)), gate.USA, {engine.XBE: vanilla})
    assert [(c.offset, c.after, c.group) for c in layer.changes] == [(0x10, b"ok!!", "q 0x00001010 (fine)")]


def test_a_slider_writes_any_finite_value_at_its_site_and_a_virtual_one_reaches_custom_apply(monkeypatch):
    """Synthetic facts (no game bytes): a slider at a site writes its value
    there as its float32, its default when the recipe gives none, any
    finite value far past its track (D23: never clamped), past float32's
    range the infinity a C cast gives (Q110), and nothing but a finite
    number (refused by name). A virtual slider's value reaches the pack's
    custom_apply, a whole one's as an int; a custom_apply that doesn't take
    exactly its pack's sliders is refused when the pack is made, as is a
    category that isn't one of ``CATEGORIES`` (the page groups packs by
    them)."""
    _synthetic(monkeypatch)
    pack = engine.Pack("s", "", sites=(_slider("speed", 0x1010),))
    written = {value: engine.plan(pack, gate.USA, {engine.XBE: VANILLA}, {} if value is None else {"speed": value})
               .changes[0].after
               for value in (None, 1e30, -7.5, 1e39, -1e39)}
    assert written == {None: struct.pack("<f", 1.0), 1e30: struct.pack("<f", 1e30), -7.5: struct.pack("<f", -7.5),
                       1e39: struct.pack("<f", math.inf), -1e39: struct.pack("<f", -math.inf)}
    for bad in (math.nan, math.inf, "2", True, None):
        with pytest.raises(mods.PackError, match=re.escape(f"pack 's': speed: {bad!r} is not a finite number")):
            engine.plan(pack, gate.USA, {engine.XBE: VANILLA}, {"speed": bad})
    got = []
    whole = engine.Pack("w", "", sites=(_slider("count", whole=(0, 9), why="a digit"),),
                        custom_apply=lambda xbe_view, count: got.append(count))
    assert engine.plan(whole, gate.USA, {engine.XBE: VANILLA}, {"count": 7.0}).changes == () and got == [7]
    assert type(got[0]) is int
    with pytest.raises(TypeError, match="custom_apply takes"):
        engine.Pack("x", "", sites=(_slider("speed", 0x1010),), custom_apply=lambda xbe_view, sped: None)
    with pytest.raises(TypeError, match=re.escape("pack 'x': no category 'memory' (the categories: player, enemies, qol)")):
        engine.Pack("x", "", category="memory")


def test_normalize_names_every_unknown_pack_parameter_and_refused_value_and_never_clamps():
    """``mods.normalize``, the one check of a recipe's packs for every host:
    the packs in their canonical order, a value equal to its slider's
    default dropped (fps_unlock's 60, not its vanilla 30), any value its
    encoding holds kept, far past the track's hints (D23), and in one
    message every pack no pack has, every parameter a pack doesn't take and
    every value that is no finite number, or for a whole slider no whole
    number its encoding holds (D45), each by name; a config.xbr cell the
    game reads as an int32 takes a fraction, but no value that int32 can't
    hold once rounded or truncated as the game does (D45). Every slider's
    track holds its default and its vanilla value (D42)."""
    assert list(mods.normalize({"qol_alloc_race": {}, "fps_unlock": {"target_fps": 60.0}})) == [
        "fps_unlock", "qol_alloc_race"]
    assert mods.normalize({"fps_unlock": {"target_fps": 60.0}}) == {"fps_unlock": {}}
    for kept in (30, 1, 1905.0):
        assert mods.normalize({"fps_unlock": {"target_fps": kept}}) == {"fps_unlock": {"target_fps": int(kept)}}
    whole = "is not a whole number from 1 to 1905 (the step cap ceil(F/15) is a signed byte)"
    for bad, why in ((math.nan, "nan is not a finite number"), (-math.inf, "-inf is not a finite number"),
                     ("60", "'60' is not a finite number"), (None, "None is not a finite number"),
                     (10 ** 400, "1" + "0" * 36 + "... is not a finite number"),
                     (60.5, f"60.5 {whole}"), (1906, f"1906 {whole}"), (0, f"0 {whole}")):
        with pytest.raises(ValueError, match=re.escape(f"pack 'fps_unlock': target_fps: {why} (its parameters")):
            mods.normalize({"fps_unlock": {"target_fps": bad}})
    with pytest.raises(ValueError) as caught:
        mods.normalize({"nope": {}, "fps_unlock": {"speed": 2, "target_fps": math.inf}, "qol_gem_popups": {"x": 1}})
    assert str(caught.value) == (
        f"recipe: no pack 'nope' (the packs: {', '.join(mods.PACKS)}); pack 'fps_unlock': no parameter 'speed'; "
        "target_fps: inf is not a finite number (its parameters: target_fps); "
        "pack 'qol_gem_popups': no parameter 'x' (its parameters: none)")
    hp = "starting_hp: {} doesn't fit the game's 32-bit integer once rounded (-2147483648..2147483647)"
    for given, why in ((2147483647.5, hp.format("2.14748e+09")), (-1e30, hp.format("-1e+30"))):
        with pytest.raises(ValueError, match=re.escape(f"pack 'player_max_hp': {why} (its parameters")):
            mods.normalize({"player_max_hp": {"starting_hp": given}})
    assert mods.normalize({"player_max_hp": {"starting_hp": -2147483648.4, "health_bar_full_scale": 1e300},
                           "air_shield_flaps": {"air_shield_1_flaps": 2.7}}) == {
        "player_max_hp": {"starting_hp": -2147483648.4, "health_bar_full_scale": 1e300},
        "air_shield_flaps": {"air_shield_1_flaps": 2.7}}
    for pack in mods.PACKS.values():
        for s in pack.sliders():
            vanilla = s.catalog()["vanilla"]
            held = [s.default] + ([vanilla] if vanilla is not None else [])
            assert all(s.slider_min <= v <= s.slider_max for v in held), (pack.name, s.name)
            assert (vanilla is None) == (isinstance(s, engine.ParametricPatch) and not s.virtual), (
                pack.name, s.name)   # an XBE site's vanilla is the image's


def test_a_remembered_setup_keeps_what_still_normalizes_and_names_each_part_it_drops():
    """``sdk.restore``, a UI's remembered setup back (D915): its ticked
    packs in their canonical order, each setting normalized (a value equal
    to its default left out) and its config.xbr ``set`` cells; a pack
    renamed or retired, a setting gone, a value its slider refuses, a pack
    without one it requires and a cell a link couldn't carry are left out
    and named, never applied, and a setup it can't read is dropped whole,
    by name, never refused."""
    cell = {"op": "set", "file": "gamedata/config.xbr", "table": "critters_damage", "entity": "golem",
            "prop": "hitPoints", "value": 321}
    hp = next(s for s in mods.PACKS["player_max_hp"].sliders() if s.name == "starting_hp")
    assert sdk.restore({"ticked": ["qol_retired", "player_physics", "fps_unlock", "qol_memory_upper64_gpu"],
                        "values": {"qol_retired": {"x": 1}, "fps_unlock": {"target_fps": 120, "speed": 2},
                                   "player_physics": {"jump_speed_scale": 1.5, "toggle_gravity": 2, "gravity": "4"},
                                   "player_max_hp": {"starting_hp": hp.default}},
                        "xbr": [cell, {"op": "replace_bytes"}, {"op": "set", "file": "gamedata/config.xbr"}]}) == {
        "ticked": ["fps_unlock", "player_physics"],
        "values": {"fps_unlock": {"target_fps": 120}, "player_physics": {"jump_speed_scale": 1.5}},
        "xbr": [cell],
        "dropped": ["qol_retired (no such pack)", "qol_memory_upper64_gpu (needs qol_memory_upper64)",
                    "fps_unlock.speed (no such setting)",
                    "player_physics.toggle_gravity: 2 is not a whole number from 0 to 1 (1 picks it, 0 doesn't)",
                    "player_physics.gravity: '4' is not a finite number",
                    "config.xbr value 2 (a setup holds set operations only, Q174)",
                    "config.xbr value 3 (no table, entity, prop, value)"]}
    unread = {"ticked": [], "values": {}, "xbr": [], "dropped": ["your last setup (not one AzurKit reads)"]}
    assert [sdk.restore(given) for given in ("{", None, {"ticked": [], "iso": "a.iso"})] == [unread] * 3


# --- Step 4.28a: Modkit's pack and CLI tests no test above pinned (test_categories and test_gui_pages' Patches
# page, test_legacy_pack_migration, test_cli_dispatch, test_goldens' golden write), ported leanly.


def test_a_slider_whose_product_passes_a_doubles_range_is_refused_by_name():
    """Step 4.42b (D45): a finite value ``mods.normalize`` keeps (D23)
    whose product the encoding takes passes a double's range (the load
    budget's 1e303 MiB, a damage x1e306) is refused by its slider as one
    the encoding can't hold, as a smaller one past it is, not an
    OverflowError no host takes as a refusal."""
    from azurkit.tools.mods.packs import enemy_scaling, qol_memory

    for mib in (5000.0, 1e303):
        with pytest.raises(ValueError, match="MiB is outside the limit's u32 of bytes"):
            qol_memory._budget(mib)
    ones = {spec.name: 1.0 for spec in enemy_scaling.PACK.sites}
    for spec in (enemy_scaling.DAMAGE_DEALT, enemy_scaling.BOSS_DAMAGE_DEALT):
        for k in (1e10, 1e306, -1e306):
            with pytest.raises(ValueError, match=f"^{re.escape(spec.label)}: x.* doesn't fit the game's 32-bit"):
                enemy_scaling.apply(None, **ones | {spec.name: k})


def test_a_flag_typed_short_is_refused_and_nothing_starts(monkeypatch, capsys):
    """Modkit's Q100 (test_cli_dispatch): argparse took any unique prefix of
    a flag, so ``--no-def`` meant ``--no-defaults``. ``azurkit`` and each of
    its verbs, an action's too, take a flag only as spelled: exit 2 naming
    it, and the build never starts."""
    ran = []
    monkeypatch.setattr(sdk, "build", lambda *args, **kwargs: ran.append(args))
    for argv in (["--vers"], ["build", "--iso", "in.iso", "--out", "o.iso", "--no-def"],
                 ["entity", "diff", "golem", "octo", "--al"]):
        with pytest.raises(SystemExit) as exc:
            cli.main(argv)
        assert exc.value.code == 2 and f"unrecognized arguments: {argv[-1]}\n" in capsys.readouterr().err, argv
    assert ran == []


def test_a_retired_pack_name_is_refused_saying_what_replaced_it(tmp_path, capsys):
    """Modkit's D43 (test_legacy_pack_migration): a retired pack name
    (qol_skip_save_signature, the randomizer's old rand_* packs) is refused
    by name, saying what replaced it, by ``mods.normalize`` (every host's
    check of a recipe, a mods file's or a link's packs) and by ``azurkit
    build --pack``, before the image is read; an unknown name is refused as
    before."""
    with pytest.raises(ValueError, match=re.escape(
            "recipe: no pack 'qol_skip_save_signature' (retired: azurkit save edit signs an edited save again "
            f"with your own BIOS files), 'zz' (the packs: {', '.join(mods.PACKS)})")):
        mods.normalize({"zz": {}, "qol_skip_save_signature": {}})
    out = tmp_path / "out.iso"
    assert cli.main(["build", "--iso", str(tmp_path / "none.iso"), "--out", str(out), "--pack", "rand_keys"]) == 1
    assert capsys.readouterr().err == (
        "azurkit: no pack 'rand_keys' (retired: the randomizer's settings choose what is shuffled (keys stay "
        f"vanilla)) (the packs: {', '.join(mods.PACKS)})\n")
    assert not out.exists()


def test_a_golden_whose_re_record_stops_midway_is_still_the_old_one(tmp_path, monkeypatch):
    """Modkit's Step X.81e (test_goldens): ``scripts/record_goldens.py``
    writes a golden whole, then renames it into place, so a re-record that
    stops partway (a full disk) leaves the old golden and no part file."""
    from pathlib import Path

    golden = tmp_path / "packs.json"
    record_goldens.write(golden, record_goldens.text({"a": {"default.xbe": "1" * 64}}))
    write_text = Path.write_text

    def half_then_fail(self, data, *args, **kwargs):
        write_text(self, data[:len(data) // 2], *args, **kwargs)
        raise OSError("disk full")
    monkeypatch.setattr(Path, "write_text", half_then_fail)
    with pytest.raises(OSError, match="disk full"):
        record_goldens.write(golden, record_goldens.text({"b": {"default.xbe": "2" * 64}}))
    monkeypatch.undo()
    assert json.loads(golden.read_text(encoding="utf-8")) == {"a": {"default.xbe": "1" * 64}}
    assert [p.name for p in tmp_path.iterdir()] == ["packs.json"]


def test_every_text_the_patches_tab_shows_is_one_short_line_with_no_tag_range_or_note():
    """Modkit's Step 2.28, the owner's standing rule (test_categories, and
    test_gui_pages' Patches page): every text the page shows from the
    catalog (a tab's title, a category's title and line, a pack's
    description, a slider's label and description) is one line of at most
    80 characters, with no tag ("[fps]"), range ("any", "from 1"),
    "experimental" label or note. Modkit's logic-safe hint beside a slider
    is AzurKit's Randomizer tab's ⚠ line: movement's slider ranges weren't
    ported (AGENTS.md's Porting from Modkit)."""
    catalog = sdk.catalog()
    texts = [tab["title"] for tab in catalog["tabs"]] + [t for c in catalog["categories"]
                                                         for t in (c["title"], c["description"])]
    texts += [t for p in catalog["packs"]
              for t in (p["description"], *(t for s in p["sliders"] for t in (s["label"], s["description"])))]
    assert len(texts) > 100 and [t for t in texts if len(t) > 80 or "\n" in t] == []
    assert [t for t in texts if re.search(r"\bany\b|from \d", t) or any(
        word in t for word in ("[", "range", "unrestricted", "xperimental", "commonly", "logic-safe"))] == []


# --- Step 4.28f: Modkit's unpinned pack behaviours, ported ------------------------------------------------------


def test_player_physics_past_float32s_range_writes_infinity_with_a_note_and_never_raises(usa_iso):
    """AZ-171 (Modkit's L14): the jump and flap height square their scale
    (g x k x k), so jump 1e20 overflows float32, 1e200 the double too, and
    swim 1e39 is past float32: each builds its float32's +inf, a C cast's,
    never an OverflowError, with Q110's note naming the slider's site, a
    product already infinite too."""
    pack = mods.PACKS["player_physics"]
    with iso.Reader(usa_iso) as r:
        base = {name: r.read(name) for name in pack.files()}
    for params, what in (({"jump_speed_scale": 1e20}, "the jump's gravity: 9.8e+40"),
                         ({"swim_speed_scale": 1e39}, "the swim stroke: 1e+40"),
                         ({"jump_speed_scale": 1e200}, "the jump's gravity: inf"),
                         ({"flap_height_scale": 1e200}, "the flap's gravity: inf")):
        made = engine.plan(pack, gate.USA, base, params)
        assert struct.pack("<f", math.inf) in [c.after for c in made.changes], params
        assert made.notes == (f"player_physics {what} is past float32's range: written as inf (Q110)",), params
