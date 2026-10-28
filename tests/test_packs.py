"""The packs (Step 4.1c: fps_unlock, qol_alloc_race, qol_gem_popups,
qol_other_popups, qol_pickup_anims) against the oracle at its packs tag.

The facts AzurKit ships are the oracle's, and each release's vanilla XBE has
their section table (AZ-316). Every case the oracle's facts record for a
ported pack writes their bytes site by site and nothing else; then each
pack's G1 case builds its golden, file by file, on both releases, through
the sdk; ``azurkit build`` applies the packs on by default (D528). A pack
that can't apply names each site and why, never its bytes (D35)."""

from __future__ import annotations

import dataclasses
import hashlib
import json

import pytest

from azurkit import cli, sdk
from azurkit.core import facts, gate, iso, xbe
from azurkit.edits.layer import compose
from azurkit.tools import mods
from azurkit.tools.mods import engine
from scripts import gen_facts

ORACLE = gen_facts.ORACLE / "packs"
FACTS = {"usa": "tests/facts/xbe.json", "europe": "tests/facts/xbe.europe.json"}
GOLDENS = {"usa": "tests/goldens/packs.json", "europe": "tests/goldens/europe/packs.json"}
RELEASES = [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
            pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe], id="europe")]


def _sha256(data) -> str:
    return hashlib.sha256(data).hexdigest()


def _oracle(rel: str) -> dict:
    return json.loads((ORACLE / rel).read_text(encoding="utf-8"))


def _vanilla_xbe(path) -> bytes:
    with iso.Reader(path) as r:
        return r.read("default.xbe")


def test_the_shipped_facts_are_the_ones_gen_facts_derives_from_the_oracle():
    for release in gate.RELEASES:
        assert facts.path(release).read_text(encoding="utf-8") == gen_facts.text(release.name), release.name


@pytest.mark.parametrize("release", RELEASES)
def test_each_ported_case_writes_the_facts_bytes_site_by_site_and_nothing_else(release, request):
    """The release's XBE has the facts' sections and sha256. For each case
    of a ported pack in the oracle's facts (``fps_unlock:target_fps=120``
    too), each site holds the case's recorded bytes (by sha256), or vanilla's
    when the case leaves it, and no byte outside the case's sites changed."""
    vanilla = _vanilla_xbe(request.getfixturevalue(f"{release.name}_iso"))
    known = facts.of(release)
    assert (xbe.sections(vanilla), _sha256(vanilla)) == (known.sections, known.sha256)
    oracle, recipes = _oracle(FACTS[release.name]), _oracle("cases.json")[FACTS[release.name]]
    cases = [case for case in oracle["cases"] if recipes[case]["pack"] in mods.PACKS]
    assert {recipes[case]["pack"] for case in cases} == set(mods.PACKS) and len(cases) == 6
    for case in cases:
        recipe = recipes[case]
        layer = mods.plan(mods.PACKS[recipe["pack"]], release, vanilla, recipe["params"])
        built = compose({"default.xbe": vanilla}, [layer])[0]["default.xbe"]
        drift, masked = [], bytearray(built)
        for va, site in ((int(va, 16), site) for va, site in oracle["patch_sites"].items()):
            new = site.get("new", {})
            try:
                at = known.offset(va, site["size"])
            except ValueError:   # USA's .text slack: no file bytes until a shim pack grows .text
                assert case not in new
                continue
            want = new.get(case, {"sha256": site["original_sha256"]})["sha256"]
            if _sha256(built[at:at + site["size"]]) != want:
                drift.append(f"0x{va:08X}")
            masked[at:at + site["size"]] = vanilla[at:at + site["size"]]
        assert drift == [], case
        assert _sha256(masked) == known.sha256, f"{case}: bytes outside its sites changed"


@pytest.mark.parametrize("release", RELEASES)
def test_each_ported_pack_builds_its_g1_golden_file_by_file(release, request):
    """``sdk.image`` with one pack at its defaults: each file the golden
    records reads back from the image with its sha256, and no other file
    differs from vanilla but ``filelist.txt`` (derived state)."""
    path = request.getfixturevalue(f"{release.name}_iso")
    golden = _oracle(GOLDENS[release.name])
    for name in mods.PACKS:
        made, report = sdk.image({"iso": str(path), "packs": {name: {}}})
        with iso.Reader(made) as r:
            assert {file: _sha256(r.read(file)) for file in golden[name]} == golden[name], name
        assert report["result"].keys() - {"filelist.txt"} == golden[name].keys(), name
        assert [layer["id"] for layer in report["layers"]] == [f"pack {name}"] and report["conflicts"] == []


def test_azurkit_build_applies_the_packs_on_by_default_and_names_each_pack(europe_iso, tmp_path, capsys):
    """``azurkit packs`` lists the packs in the order a build applies them;
    ``azurkit build`` with none named applies those on by default (D528):
    qol_alloc_race, whose golden the written image's XBE holds."""
    assert cli.main(["packs"]) == 0
    listed = [line.split()[:2] for line in capsys.readouterr().out.splitlines()]
    assert listed == [[name, "on" if pack.default_on else "off"] for name, pack in mods.PACKS.items()]
    out = tmp_path / "europe.iso"
    try:
        assert cli.main(["build", "--iso", str(europe_iso), "--out", str(out)]) == 0
        with iso.Reader(out) as r:
            assert _sha256(r.read("default.xbe")) == _oracle(GOLDENS["europe"])["qol_alloc_race"]["default.xbe"]
    finally:
        out.unlink(missing_ok=True)
    assert capsys.readouterr().out.splitlines()[0] == "pack qol_alloc_race: 3 sites, 71 B"


def test_a_pack_that_cant_apply_names_each_site_and_why_never_its_bytes(monkeypatch):
    """Synthetic facts over a synthetic XBE (no game bytes): every failing
    site of a pack is named in one error, by label and address, with why:
    other bytes there (named by size and sha256), a patch of another size,
    no facts site, no address in the release, a write outside a
    custom_apply's footprint; and a pack is refused by name for another
    release, an XBE that isn't vanilla, or a parameter it doesn't take."""
    vanilla = bytes(range(256))
    held = vanilla[0x20:0x24]
    usa = facts.Facts(gate.USA, _sha256(vanilla), 256, (xbe.Section(".text", 0x1000, 0x100, 0, 0x100, 0),),
                      {va: facts.Site(va, size, _sha256(vanilla[va - 0x1000:va - 0x1000 + size]))
                       for va, size in ((0x1010, 4), (0x1030, 2))} | {0x1020: facts.Site(0x1020, 4, _sha256(b"ours"))},
                      None, {})
    europe = dataclasses.replace(usa, release=gate.EUROPE, addresses={0x1010: 0x1010}, absent={0x1040: "rebuilt"})
    monkeypatch.setattr(engine.facts_, "of", {gate.USA: usa, gate.EUROPE: europe}.get)

    def refused(pack, release=gate.USA, xbe_bytes=vanilla, **params) -> str:
        with pytest.raises(mods.PackError) as caught:
            engine.plan(pack, release, xbe_bytes, params)
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

    def writes(xbe_view, value: int = 1):
        xbe_view.patch(site(0x1010, b"ok!!", "inside"))
        xbe_view.patch(site(0x1030, b"12", "outside"))
    custom = engine.Pack("c", "", custom_apply=writes, footprint=(engine.Place(va=0x1010),))
    assert refused(custom) == ("pack 'c': 1 site(s) failed: outside at 0x00001030: "
                               "it is outside the pack's declared footprint")
    assert "unexpected keyword argument 'speed' (its parameters: value)" in refused(custom, speed=2)
    assert refused(dataclasses.replace(custom, releases=("usa",)), gate.EUROPE) == (
        "pack 'c' is not available on the Europe release (it supports usa)")
    assert refused(custom, xbe_bytes=vanilla[::-1]) == (
        f"pack 'c': default.xbe <256 B, sha256 {_sha256(vanilla[::-1])[:12]}> is not the vanilla USA one")
    layer = engine.plan(engine.Pack("q", "", sites=(site(0x1010, b"ok!!", "fine"),)), gate.USA, vanilla)
    assert [(c.offset, c.after, c.group) for c in layer.changes] == [(0x10, b"ok!!", "q 0x00001010 (fine)")]
