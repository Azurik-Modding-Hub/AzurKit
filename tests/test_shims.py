"""The shim engine (Steps 4.1f1, 4.1f2, 4.3a2): the prebuilt objects (AZ-045,
D895) are their sources' builds and hold their G2 hashes, all fifty-one: the
packs' eleven and the player-model swap's forty; the headers a shim includes are written from the facts
(AZ-099, Q85: no vendored header), and a shim built against them lands with
each call at the facts' address (``core.coff``), each of whose functions
starts a function in its release's code (the prologue drift guard); the
carve allocator places
a shim past every claim the layers before it hold, in ``.text``'s gap or an
appended section, and the claims, kept in the manifest, derive the header's
state (``core.xbe.Carver``, ``grown``). The shim packs' G1 cases (their
kernel stubs, parameters and carves) are ``tests/test_packs.py``'s,
``tests/test_site.py``'s and ``tests/test_hosts.py``'s."""

from __future__ import annotations

import dataclasses
import re
import struct
import subprocess
from pathlib import Path

import pytest

import shimkit
from azurkit.core import coff, facts, gate, iso, xbe
from azurkit.edits import manifest
from azurkit.edits.layer import Claim, Layer, compose
from azurkit.tools import mods
from azurkit.tools.characters import ports
from azurkit.tools.mods import engine
from scripts import record_goldens

G2 = record_goldens.recorded("shims.json")


def test_each_prebuilt_shim_is_its_sources_build_and_holds_its_g2_hash(usa_iso):
    """Every shim source has its object beside it, which zig builds from it
    byte for byte (``shimkit --check``, D895: roll.c's table filled from the
    USA image, so the test is ``vanilla``), and whose normalized sha256
    is G2's record (``tests/goldens/shims.json``, first recorded as Modkit's
    build at its last cut): the packs' eleven (``tools/mods/shims/<name>.c``,
    the shared kernel-export resolver's among them) and the swap's forty
    (``tools/characters/player_model/<stem>.c``, G2's
    ``player_model_<stem>.o``). Three
    hold zeros where a build writes back what Modkit's holds
    (``ports.HELD``: garret4's roll motion, read from the image, and
    constants whose bytes meet a vanilla file's by chance), which give
    G2's object back."""
    for folder, prefix in {shimkit.SHIMS: "", shimkit.PLAYER_MODEL: "player_model_"}.items():
        sources = {p.stem for p in folder.glob("*.c")}
        assert sources == {p.stem for p in folder.glob("*.o")} == {
            name.removeprefix(prefix).removesuffix(".o") for name in G2
            if name.startswith("player_model") == bool(prefix)}
        for name in sorted(sources - (set(ports.HELD) if prefix else set())):
            held = coff.normalized_sha256((folder / f"{name}.o").read_bytes())
            assert held == G2[f"{prefix}{name}.o"]["normalized sha256"], name
    assert len(list(shimkit.PLAYER_MODEL.glob("*.o"))) == 40
    for stem, held in ports.HELD.items():   # zeros where a build writes back; its constants give G2's object back
        obj = coff.parse((shimkit.PLAYER_MODEL / f"{stem}.o").read_bytes())
        assert all(not any(obj.sections[(s := obj.symbol(name)).section - 1].data[s.value:s.value + 4])
                   for name in held), stem
        if not any(callable(value) for value in held.values()):   # garret4's roll table: tests/test_characters.py
            assert coff.normalized_sha256(ports.restored(stem, obj)) == G2[f"player_model_{stem}.o"][
                "normalized sha256"], stem
    assert shimkit.build(check=True) == []


def test_a_shim_built_against_the_facts_header_lands_with_each_call_at_its_facts_address(tmp_path):
    """A shim that takes the address of every game function the header
    declares, and calls one, builds against shimkit's header: its externals
    are exactly the facts' functions as C mangles them, and laid out
    (``coff.layout``) each word of its table holds that function's address
    and the call's rel32 reaches it; its table, in .data, lands writable,
    its code not. The repo tracks no header but a shim's own beside it, and a
    shim includes only those and the two shimkit writes from the facts (no
    GPL vendor header, Q85: ``azurik_kernel.h`` names the facts' kernel
    exports, a variable as an import); the facts carry AZ-116's corrected
    names."""
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
                             check=True).stdout.split()
    own = {Path(h).name for h in tracked}
    included = {h for folder in shimkit.FOLDERS for p in folder.glob("*.[ch]")
                for h in re.findall(r'#include\s*[<"]([^>"]+)', p.read_text())}
    assert all(Path(h).parent == shimkit.SHIMS.relative_to(shimkit.ROOT) for h in tracked)
    assert included <= {*shimkit.HEADERS, *own} and not own & set(shimkit.HEADERS)
    kernel = facts.of(gate.USA).kernel
    assert [line.split("/*")[0].strip() for line in shimkit.kernel_header().splitlines() if "/* ordinal" in line] == [
        "__declspec(dllimport) extern unsigned int KeTickCount;",
        "__attribute__((stdcall)) unsigned int MmFreeContiguousMemory(unsigned int);"]
    assert {k.mangled for k in kernel.values()} == {"__imp__KeTickCount", "_MmFreeContiguousMemory@4"}
    names = {f.name for f in functions}
    assert {"player_ground_attack_start", "settings_get_double", "game_start_setup"} <= names
    assert not {"player_ground_land_tick", "cvar_get_double", "dev_menu_flag_check"} & names


# The bytes an i386 function opens with in MSVC-compiled code (Modkit's test_va_audit): PUSH EBP/EBX/ESI/EDI/ECX,
# SUB ESP, MOV r32 or r8 from memory, LEA, MOV AL/EAX from an address, XOR r32, FLD, PUSH imm, a 16-bit operand,
# CMP r8, TEST r/m8, a tail-call JMP, an import thunk's JMP [abs] or PUSH [ESP+4], and a TIB read (FS:). A
# function whose first byte is none of these is mid-function: fix its address (Ghidra), never extend this set.
PROLOGUE_FIRST_BYTES = frozenset({0x55, 0x53, 0x56, 0x57, 0x51, 0x83, 0x81, 0x8B, 0x8A, 0x8D, 0xA0, 0xA1, 0x33,
                                  0xD9, 0x6A, 0x68, 0x66, 0x80, 0xF6, 0xE9, 0xFF, 0x64})


@pytest.mark.parametrize("release", [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
                                     pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe],
                                                  id="europe")])
def test_each_facts_function_starts_a_function_in_its_releases_code(release, request):
    """The prologue drift guard (Modkit's test_va_audit, ported in Step
    4.12a, when the facts' functions became AzurKit's to edit): each
    function the facts give a shim lies, at its release's address, in the
    file bytes of an executable section of that release's vanilla XBE, and
    its first byte is one a prologue opens with (``PROLOGUE_FIRST_BYTES``)."""
    with iso.Reader(request.getfixturevalue(f"{release.name}_iso")) as r:
        data = r.read("default.xbe")
    known = facts.of(release)
    code = [s for s in xbe.sections(data) if s.flags & 4]   # an XBE section's executable bit
    outside, opens = [], []
    for f in known.functions.values():
        if not any(s.va <= f.va < s.va + min(s.vsize, s.raw_size) for s in code):
            outside.append(f.name)
        elif data[known.offset(f.va)] not in PROLOGUE_FIRST_BYTES:
            opens.append(f"{f.name} at 0x{f.va:08X}")
    assert (outside, opens, len(known.functions)) == ([], [], {"usa": 354, "europe": 254}[release.name])


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
