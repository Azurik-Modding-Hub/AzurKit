"""devkit's build checks, ``python -m devkit builds`` (``devkit/builds/``, Step
4.6l; Modkit's ``verify-patches`` and ``inspect-physics`` and their
test_verify_patches_strict and test_inspect_physics, leanly): on either
release, each pack's site of a build is read at that release's own address
as applied, vanilla or a mismatch (by digests, never bytes), the frame-rate
guard holds fps_unlock's places, a byte outside every site fails only
--strict, and each player_physics slider site shows the value it holds.
The builds are AzurKit's packs' layers over each vanilla image."""

from __future__ import annotations

import json
import re

import pytest

from azurkit import sdk
from azurkit.core import facts, gate, iso
from azurkit.edits.layer import compose
from azurkit.tools import mods
from azurkit.tools.mods import engine
from azurkit.tools.mods.packs import qol_popups
from devkit.builds import inspect_physics, verify_patches
from tests import _xiso

RELEASES = [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
            pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe], id="europe")]
PHYSICS = {"gravity": 12.0, "jump_speed_scale": 1.5, "roll_speed_scale": 2.0, "roll_time_scale": 1.25,
           "climb_speed_scale": 1.5, "wing_flap_ceiling_scale": 3.0, "swim_speed_scale": 2.0, "air_control_scale": 1.5,
           "flap_descent_fuel_cost_scale": 0.5, "flap_entry_fuel_cost_scale": 0.25, "walk_speed_scale": 2.0,
           "flap_height_scale": 1.2, "flap_below_peak_scale": 2.0, "toggle_gravity": 1}


def built(path, release, recipe: dict, tmp_path) -> tuple[bytes, bytes, bytes]:
    """The image's vanilla XBE, and the XBE and config.xbr the packs of
    ``recipe`` build over it, their layers in order as a build lays them."""
    with iso.Reader(path) as r:
        base = {engine.XBE: r.read(engine.XBE), engine.CONFIG: r.read(engine.CONFIG)}
    layers = []
    for name, params in mods.normalize(recipe).items():
        layers.append(mods.plan(mods.PACKS[name], release, base, params, [c for l in layers for c in l.claims]))
    made = compose(base, layers)[0]
    return base[engine.XBE], made.get(engine.XBE, base[engine.XBE]), made.get(engine.CONFIG, base[engine.CONFIG])


def run(capsys, verb, *argv) -> tuple[int, str, str]:
    code = verb.main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


@pytest.mark.parametrize("release", RELEASES)
def test_verify_patches_reads_each_packs_sites_of_a_build_and_fails_a_mismatch_a_broken_guard_or_a_stray(
        release, request, tmp_path, capsys):
    """A build of popups, the skip-logo trampoline, 60 fps, every physics
    slider and the upper-64 packs passes --strict: its fixed patches applied
    (the rest vanilla's), the gravity slider custom, the trampolines applied
    where built, fps_unlock's places its bytes at 60 fps and no byte outside
    every site and the shim room (Modkit's strict whitelist; on Europe each
    site at its own address, RG.4b); the vanilla image passes too, and so
    does a character's build, its swap sites written. A fixed
    patch's byte changed is a mismatch shown by digests, a step-cap byte a
    failed guard, exit 1; a header, a .text and two tail bytes are named
    runs that fail only --strict. A build of neither release, or a vanilla
    image that isn't, is one line, exit 2."""
    image = request.getfixturevalue(f"{release.name}_iso")
    known = facts.of(release)
    recipe = {"player_physics": PHYSICS, "qol_gem_popups": {}, "qol_skip_logo": {}, "fps_unlock": {},
              "qol_memory_upper64": {}, "qol_memory_upper64_gpu": {}}
    vanilla, xbe, _ = built(image, release, recipe, tmp_path)
    (tmp_path / "b.xbe").write_bytes(xbe)
    code, out, _ = run(capsys, verify_patches, "--xbe", tmp_path / "b.xbe", "--original", image, "--strict")
    specs = [s for name in recipe for s in mods.PACKS[name].sites
             if isinstance(s, engine.PatchSpec) and s.on(release.name)]
    assert code == 0 and f"  applied:      {len(specs)}\n" in out and "  mismatch:     0" in out
    assert f"the {release.label} release" in out
    assert "[custom  ]  player_physics.gravity  = 12 m/s^2  (default 9.8)" in out
    assert "[applied ]  qol_skip_logo: the logo movie's call" in out and "[original]  qol_save_warp: " in out
    assert "[OK ] fps_unlock at 60 fps" in out and out.endswith(":\n  none\n")
    code, out, _ = run(capsys, verify_patches, "--iso", image, "--original", image, "--strict")
    assert code == 0 and "  applied:      0\n" in out and "runs at 30 fps, vanilla's" in out
    made, _ = sdk.image({"iso": str(image), "character": {"species": "keylord", "mode": "garret4"}})
    with iso.Reader(made) as r:
        (tmp_path / "c.xbe").write_bytes(r.read(engine.XBE))
    code, out, _ = run(capsys, verify_patches, "--xbe", tmp_path / "c.xbe", "--original", image, "--strict")
    assert code == 0 and re.search(r"Player-model swap sites: [1-9]\d* of \d+ written", out) and out.endswith(
        ":\n  none\n")

    gem = known.offset(qol_popups.GEM_POPUPS.sites[0].own(known), 1)
    step = known.offset(known.va(0x59AFD), 1)   # fps_unlock's step clamp: Modkit's safety-critical site
    for at, why in ((gem, "*** MISMATCHES"), (step, "[FAIL] fps_unlock at 60 fps: 1 of its")):
        broken = bytearray(xbe)
        broken[at] ^= 0xFF
        (tmp_path / "x.xbe").write_bytes(broken)
        code, out, _ = run(capsys, verify_patches, "--xbe", tmp_path / "x.xbe", "--original", image)
        assert code == 1 and why in out, why
        assert at != gem or ("             got:      <" in out and "first differing offset 0x0" in out)
    text = next(s for s in known.sections if s.name == ".text")
    stray = bytearray(xbe)
    stray[0x114] ^= 1                # the header's time stamp
    stray[text.raw] ^= 0xFF          # .text's first byte, no pack's
    (tmp_path / "s.xbe").write_bytes(bytes(stray) + b"\1\2")
    code, out, _ = run(capsys, verify_patches, "--xbe", tmp_path / "s.xbe", "--original", image)
    assert code == 0 and "file 0x000114  (the header): 1 B" in out and f"VA 0x{text.va:08X}  .text: 1 B" in out
    assert f"file 0x{len(xbe):06X}  (no section): 2 B" in out and "3 run(s), 4 B (--strict fails on them)" in out
    assert run(capsys, verify_patches, "--xbe", tmp_path / "s.xbe", "--original", image, "--strict")[0] == 1
    (tmp_path / "neither.xbe").write_bytes(vanilla[:0x158] + bytes(4) + vanilla[0x15C:])
    for argv in (("--xbe", tmp_path / "neither.xbe"), ("--xbe", tmp_path / "b.xbe", "--original", tmp_path / "b.xbe")):
        code, _, err = run(capsys, verify_patches, *argv)
        assert code == 2 and len(err.splitlines()) == 1 and err.startswith("verify-patches: "), err


@pytest.mark.parametrize("release", RELEASES)
def test_inspect_physics_shows_the_value_each_slider_site_of_a_build_holds(release, request, tmp_path, capsys):
    """Every player_physics slider of a build at its release's own address
    (Modkit's AZ-101 and RG.4b): the in-place floats (gravity, the fuel
    costs, air control) against vanilla, the loads pointed at a carved
    float (jump and flap g k^2), the hand shims' k, the speed toggle's hook
    and walk's runSpeed in the image's config.xbr (not read from a raw XBE,
    D53); the vanilla image is VANILLA throughout, and a load whose opcode
    changed is DRIFTED, by its digest."""
    image = request.getfixturevalue(f"{release.name}_iso")
    _, xbe, config = built(image, release, {"player_physics": PHYSICS}, tmp_path)
    (tmp_path / "b.iso").write_bytes(_xiso.image({"default.xbe": xbe, "gamedata/config.xbr": config}))
    code, out, _ = run(capsys, inspect_physics, "--iso", tmp_path / "b.iso", "--original", image, "--json")
    report = json.loads(out)
    values = {name: (row["state"], round(row.get("value", 0.0), 4)) for name, row in report["sliders"].items()}
    assert code == 0 and values == {
        "walk": ("PATCHED", 14.0), "gravity": ("PATCHED", 12.0), "swim": ("PATCHED", 20.0), "jump": ("PATCHED", 27.0),
        "flap": ("PATCHED", 17.28), "flap_below_peak": ("PATCHED", 1.0), "roll": ("PATCHED", 2.0),
        "roll_time": ("PATCHED", 1.25), "climb": ("PATCHED", 1.5), "ceiling": ("PATCHED", 3.0),
        "descent_fuel": ("PATCHED", 50.0), "entry_fuel": ("PATCHED", 0.25), "speed_toggle": ("PATCHED", 0.0)}
    assert {(row["state"], round(row["value"] / row["vanilla"], 4)) for row in report["air_control"]} == {
        ("PATCHED", 1.5)}
    code, out, _ = run(capsys, inspect_physics, "--iso", tmp_path / "b.iso", "--original", image)
    lines = [line for line in out.splitlines() if "entry fuel" in line or "walk" in line]
    assert "[PATCHED]" in lines[0] and "14.0000  (2.000x vanilla)" in lines[0]
    assert "[PATCHED]" in lines[1] and "0.2500  (0.250x vanilla)" in lines[1]
    report = json.loads(run(capsys, inspect_physics, "--iso", image, "--original", image, "--json")[1])
    assert {row["state"] for row in [*report["sliders"].values(), *report["air_control"]]} == {"VANILLA"}
    known = facts.of(release)
    drifted = bytearray(xbe)
    drifted[known.offset(known.va(0x8B7BF), 1)] ^= 0xFF   # swim's opcode
    (tmp_path / "d.xbe").write_bytes(drifted)
    report = json.loads(run(capsys, inspect_physics, "--xbe", tmp_path / "d.xbe", "--original", image, "--json")[1])
    assert report["sliders"]["walk"]["state"] == "NOT READ"
    swim = report["sliders"]["swim"]
    assert swim["state"] == "DRIFTED" and swim["got"].startswith("<6 B, sha256")
