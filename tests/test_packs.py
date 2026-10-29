"""The packs (Step 4.1c: fps_unlock, qol_alloc_race, qol_gem_popups,
qol_other_popups, qol_pickup_anims; Step 4.1e2: player_max_hp,
air_shield_flaps and enemy_damage, config.xbr's; Step 4.1f1: qol_skip_logo,
a shim's) against the oracle at its packs tag.

The facts AzurKit ships are the oracle's, and each release's vanilla XBE has
their section table (AZ-316). Every case the oracle's facts record for a
ported pack (its sliders' values normalized, Step 4.1e1) writes their bytes
site by site and nothing else; then each G1 case of a ported pack, with its
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
from azurkit.tools import mods
from azurkit.tools.mods import engine
from scripts import gen_facts
from tests import _g1

ORACLE = gen_facts.ORACLE / "packs"
FACTS = {"usa": "tests/facts/xbe.json", "europe": "tests/facts/xbe.europe.json"}
RELEASES = [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
            pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe], id="europe")]


def _sha256(data) -> str:
    return hashlib.sha256(data).hexdigest()


def _oracle(rel: str) -> dict:
    return json.loads((ORACLE / rel).read_text(encoding="utf-8"))


def _vanilla_file(path, name: str) -> bytes:
    with iso.Reader(path) as r:
        return r.read(name)


def test_the_shipped_facts_are_the_ones_gen_facts_derives_from_the_oracle():
    for release in gate.RELEASES:
        assert facts.path(release).read_text(encoding="utf-8") == gen_facts.text(release.name), release.name


@pytest.mark.parametrize("release", RELEASES)
def test_each_ported_case_writes_the_facts_bytes_site_by_site_and_nothing_else(release, request):
    """The release's XBE has the facts' sections and sha256. For each case
    in the oracle's facts, every pack's (``fps_unlock:target_fps=120``
    too), each site holds the case's recorded bytes (by sha256), or vanilla's
    when the case leaves it (USA's ``.text`` slack among them, where a shim
    lands; a legacy site, which no build writes, isn't read), and no byte
    changed outside the case's sites, its shims' claims and the header state
    they derive."""
    with iso.Reader(request.getfixturevalue(f"{release.name}_iso")) as r:
        vanilla, config = r.read(engine.XBE), r.read(engine.CONFIG)
    known = facts.of(release)
    assert (xbe.sections(vanilla), _sha256(vanilla)) == (known.sections, known.sha256)
    oracle, recipes = _oracle(FACTS[release.name]), _oracle("cases.json")[FACTS[release.name]]
    cases = oracle["cases"]
    xbe_packs = {name for name, pack in mods.PACKS.items() if engine.XBE in pack.files()}
    assert {recipes[case]["pack"] for case in cases} == xbe_packs and len(cases) == 32
    for case in cases:
        recipe = recipes[case]
        params = mods.normalize({recipe["pack"]: recipe["params"]})[recipe["pack"]]
        layer = mods.plan(mods.PACKS[recipe["pack"]], release, {engine.XBE: vanilla, engine.CONFIG: config}, params)
        built = compose({"default.xbe": vanilla, engine.CONFIG: config}, [layer])[0].get("default.xbe", vanilla)
        derived = bytearray(claimed({"default.xbe": vanilla}, [layer]).get("default.xbe", vanilla))
        drift, masked = [], bytearray(built)
        for va, site in ((int(va, 16), site) for va, site in oracle["patch_sites"].items() if site.get("new")):
            s = max((s for s in known.sections if s.va <= va), key=lambda s: s.va)   # the slack is its section's
            at, want = s.raw + va - s.va, site.get("new", {}).get(case, {"sha256": site["original_sha256"]})["sha256"]
            if _sha256(built[at:at + site["size"]]) != want:
                drift.append(f"0x{va:08X}")
            masked[at:at + site["size"]] = derived[at:at + site["size"]]
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
    the GPU pack that requires it too, and a build that names that pack
    without it is refused by name); less the three memory packs (``--no-pack``),
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
    assert list(cli.recipe("x.iso", [], ["qol_memory_upper64"], True)["packs"]) == [   # D588: gpu goes with it
        "qol_memory_budget", "qol_alloc_race"]
    with pytest.raises(ValueError, match=re.escape("pack 'qol_memory_upper64_gpu' needs 'qol_memory_upper64' in")):
        sdk.image(cli.recipe("x.iso", ["qol_memory_upper64_gpu"], ["qol_memory_upper64"], True))
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
        assert capsys.readouterr().out.splitlines()[:2] == ["pack qol_alloc_race: 4 sites, 204 B",
                                                            "data xbr: 1 sites, 8 B"]
        assert cli.main(["open", str(out)]) == 0
        opened = json.loads(capsys.readouterr().out)
    finally:
        out.unlink(missing_ok=True)
    assert opened["base"]["release"] == "europe"
    assert sdk.read_mods(opened) == {"packs": {"qol_alloc_race": {}}, "xbr": [golem]}


VANILLA = bytes(range(256))   # the synthetic XBE: one .text section at 0x1000


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
    exactly its pack's sliders is refused when the pack is made."""
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
