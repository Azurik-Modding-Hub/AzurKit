"""The shim engine (Step 4.1f1): the prebuilt objects (AZ-045) are their
sources' builds and hold the oracle's G2 hashes; the one header a shim
includes is written from the facts (AZ-099, Q85: no vendored header), and a
shim built against it lands with each call at the facts' address
(``core.coff``); the carve allocator places a shim past every claim the
layers before it hold, in ``.text``'s gap or an appended section, and the
claims, kept in the manifest, derive the header's state
(``core.xbe.Carver``, ``grown``). qol_skip_logo's G1 cases are
``tests/test_packs.py``'s, ``tests/test_site.py``'s and
``tests/test_hosts.py``'s."""

from __future__ import annotations

import dataclasses
import json
import re
import struct
import subprocess

import pytest

import shimkit
from azurkit.core import coff, facts, gate, iso, xbe
from azurkit.edits import manifest
from azurkit.edits.layer import Claim, Layer, compose
from azurkit.tools import mods
from azurkit.tools.mods import engine
from scripts import gen_facts

G2 = json.loads((gen_facts.ORACLE / "packs/tests/goldens/shims.json").read_text(encoding="utf-8"))


def test_each_prebuilt_shim_is_its_sources_build_and_holds_its_g2_hash():
    """Every ``shims/<name>.c`` has its object beside it, which zig builds
    from it byte for byte (``shimkit --check``), and whose normalized
    sha256 is the oracle's G2 record of Modkit's build: qol_skip_logo's and
    the shared kernel-export resolver's."""
    sources = {p.stem for p in shimkit.SHIMS.glob("*.c")}
    assert sources == {p.stem for p in shimkit.SHIMS.glob("*.o")} == {"qol_skip_logo", "xboxkrnl_resolver"}
    assert shimkit.build(check=True) == []
    for name in sorted(sources):
        held = coff.normalized_sha256((shimkit.SHIMS / f"{name}.o").read_bytes())
        assert held == G2[f"{name}.o"]["normalized sha256"], name


def test_a_shim_built_against_the_facts_header_lands_with_each_call_at_its_facts_address(tmp_path):
    """A shim that takes the address of every game function the header
    declares, and calls one, builds against shimkit's header: its externals
    are exactly the facts' functions as C mangles them, and laid out
    (``coff.layout``) each word of its table holds that function's address
    and the call's rel32 reaches it; its table, in .data, lands writable,
    its code not. The repo tracks no header: the facts are the only source
    (no GPL vendor header, Q85), and they carry AZ-116's corrected names."""
    functions = sorted(facts.of(gate.USA).functions.values(), key=lambda f: f.name)
    called = next(f for f in functions if f.convention == "stdcall" and f.arg_bytes == 8)
    source = tmp_path / "every.c"
    source.write_text('#include "azurik_vanilla.h"\nvoid *every[] = {'
                      + ", ".join(f"(void *){f.name}" for f in functions)
                      + f"}};\nunsigned int c_entry(void) {{ return {called.name}(1, 2); }}\n", encoding="utf-8")
    shim = coff.parse(shimkit.compile(source))
    assert {s.name for s in shim.symbols if s.storage == coff.EXTERNAL and s.section == 0} == {
        f.mangled for f in functions}
    given = []

    def allocate(size: int, align: int, writable: bool) -> tuple[int, int]:
        given.append(writable)
        return 0x100 * len(given), 0x10000 * len(given)
    placed, entry = coff.layout(shim, "_c_entry", allocate, facts.of(gate.USA).mangled())
    table, text = (next(p for p in placed if p.section == name) for name in (".data", ".text"))
    assert list(struct.unpack(f"<{len(functions)}I", table.data)) == [f.va for f in functions]
    calls = [text.va + at + 5 + struct.unpack_from("<i", text.data, at + 1)[0]
             for at in range(len(text.data) - 4) if text.data[at] in (0xE8, 0xE9)]
    assert called.va in calls and entry == text.va + shim.symbol("_c_entry").value
    assert sorted(given) == [False, True] and len(placed) == 2
    tracked = subprocess.run(["git", "-C", str(shimkit.ROOT), "ls-files", "*.h"], capture_output=True, text=True,
                             check=True).stdout
    included = {h for p in shimkit.SHIMS.glob("*.c") for h in re.findall(r'#include\s*[<"]([^>"]+)', p.read_text())}
    assert tracked == "" and included <= {"azurik_vanilla.h"}
    names = {f.name for f in functions}
    assert {"player_ground_attack_start", "settings_get_double", "game_start_setup"} <= names
    assert not {"player_ground_land_tick", "cvar_get_double", "dev_menu_flag_check"} & names


def test_a_shim_lands_past_every_claim_before_it_and_its_claims_derive_the_header(usa_iso):
    """qol_skip_logo on USA lands its 5 bytes at .text's end (16 bytes of
    gap before BINK), its hook a CALL to them; past another layer's claim
    of 8 there, 8 bytes on; past one of 12, in SHIMS, appended past the
    last section (executable, not writable), the hook following it; a
    shim's .data lands there too, 64 bytes from any code, and makes the
    section writable. The claims derive .text's growth and the section, are
    kept in the manifest under the shim's name, and two layers' claims that
    meet are refused by name; so is a shim the object lacks."""
    with iso.Reader(usa_iso) as r:
        vanilla = r.read("default.xbe")
    room, pack = xbe.room(vanilla), mods.PACKS["qol_skip_logo"]
    hook = facts.of(gate.USA).offset(0x5F6E5, 5)

    def landed(held: int) -> tuple[Layer, Layer, bytes]:
        other = Layer("other", "t", "k", {}, (), (Claim("default.xbe", room.gap, held, "shim:other"),))
        layer = engine.plan(pack, gate.USA, {"default.xbe": vanilla}, {}, other.claims if held else ())
        files, _ = compose({"default.xbe": vanilla}, [other, layer] if held else [layer])
        return other, layer, bytes(files["default.xbe"])
    for held, at, va in ((0, room.gap, 0x1001D0), (8, room.gap + 8, 0x1001D8), (12, room.shims, room.shims_va)):
        other, layer, built = landed(held)
        assert [(c.offset, c.size, c.owner, c.writable) for c in layer.claims] == [(at, 5, "shim:qol_skip_logo",
                                                                                     False)]
        assert built[hook] == 0xE8 and 0x5F6E5 + 5 + struct.unpack_from("<i", built, hook + 1)[0] == va
        assert built[at:at + 5] == engine.shim("qol_skip_logo").sections[0].data
        text, *rest = (s for s in xbe.sections(built) if s.name in (".text", xbe.SHIMS))
        assert text.raw_size - room.text.raw_size == (held + 5 if held < 12 else held)
        appended = [(va, at, 5, xbe.SHIMS_FLAGS)] if held == 12 else []
        assert [(s.va, s.raw, s.raw_size, s.flags) for s in rest] == appended
    carver = xbe.Carver(vanilla, [(room.gap, 16)])   # .text's gap full: a shim's .data, writable, goes to SHIMS
    writable = carver.place(4, 4, True)
    assert writable == (room.shims, xbe.CODE_GAP + 4 + xbe.CODE_GAP, room.shims + xbe.CODE_GAP,
                        room.shims_va + xbe.CODE_GAP)
    (appended,) = (s for s in xbe.sections(xbe.grown(vanilla, [(room.gap, 16, False), (*writable[:2], True)]))
                   if s.name == xbe.SHIMS)
    assert (appended.raw_size, appended.flags) == (writable[1], xbe.SHIMS_FLAGS | xbe.WRITABLE)
    assert manifest.Manifest(gate.USA, (layer,), {}, ()).to_json()["layers"][0]["claims"] == [
        {"file": "default.xbe", "offset": room.shims, "size": 5, "owner": "shim:qol_skip_logo", "writable": False}]
    with pytest.raises(ValueError, match=re.escape(
            f"default.xbe: shim:qol_skip_logo's claim at 0x{room.gap:X} meets shim:other's at 0x{room.gap:X}")):
        compose({"default.xbe": vanilla}, [landed(8)[0], landed(0)[1]])
    lacking = dataclasses.replace(pack, sites=(dataclasses.replace(pack.sites[0], symbol="_c_nope"),))
    with pytest.raises(mods.PackError, match=re.escape(
            "the logo movie's call at 0x0005F6E5: its shim 'qol_skip_logo': the shim has no symbol '_c_nope'")):
        engine.plan(lacking, gate.USA, {"default.xbe": vanilla})
