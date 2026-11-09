"""The shim engine (Steps 4.1f1, 4.1f2, 4.3a2): the prebuilt objects (AZ-045,
D895) are their sources' builds and hold their G2 hashes, all fifty-one: the
packs' eleven and the player-model swap's forty; the headers a shim includes are written from the facts
(AZ-099, Q85: no vendored header), and a shim built against them lands with
each call at the facts' address (``core.coff``), each of whose functions
starts a function in its release's code (the prologue drift guard) and pops
what its declared ABI makes its caller push (AZ-108's guard); the carve
allocator places
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
import tomllib
from pathlib import Path

import pytest
from capstone import CS_ARCH_X86, CS_GRP_JUMP, CS_MODE_32, Cs
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG

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
    its code not. The repo tracks no header but a shim's own beside it and the
    RE data's ``structs.h`` (the developer side's, D990), and a shim includes
    only its own and those shimkit writes from the facts, never that one (no
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
    shims = shimkit.SHIMS.relative_to(shimkit.ROOT)
    own = {Path(h).name for h in tracked if Path(h).parent == shims}
    included = {h for folder in shimkit.FOLDERS for p in folder.glob("*.[ch]")
                for h in re.findall(r'#include\s*[<"]([^>"]+)', p.read_text())}
    assert [h for h in tracked if Path(h).parent != shims] == ["devkit/re/data/structs.h"]
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


BOTH = [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
        pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe], id="europe")]


@pytest.mark.parametrize("release", BOTH)
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


_CAPSTONE = Cs(CS_ARCH_X86, CS_MODE_32)
_CAPSTONE.detail = True


def _ret_pops(data: bytes, table: tuple[xbe.Section, ...], entry: int) -> set[int]:
    """The ``RET imm16`` pop counts (0 for a plain RET) of every return
    reachable from ``entry``: both arms of each conditional branch, direct
    JMPs (tail calls too) and switch tables bounded by the ``CMP index, imm``
    before them; a CALL falls through, and a path ends at a RET, an INT3 (but
    the one after ``INT 2Dh``, which the debug service skips) or any other
    indirect JMP."""
    def code(va: int, n: int = 16) -> bytes:
        for s in table:
            if s.va <= va < s.va + min(s.vsize, s.raw_size):
                return data[s.raw + va - s.va:s.raw + min(va - s.va + n, s.vsize, s.raw_size)]
        return b""

    pops, seen, todo = set(), set(), [entry]
    while todo:
        va, prev, bound = todo.pop(), None, None
        while va not in seen:
            seen.add(va)
            ins = next(_CAPSTONE.disasm(code(va), va), None)
            if ins is None:
                break
            m, ops = ins.mnemonic, ins.operands
            if m == "ret":
                pops.add(ops[0].imm if ops else 0)
                break
            if m == "int3" and not (prev and prev.mnemonic == "int" and prev.op_str == "0x2d"):
                break
            if m == "cmp" and ops[0].type == X86_OP_REG and ops[1].type == X86_OP_IMM:
                bound = (ops[0].reg, ops[1].imm + 1)
            if ins.group(CS_GRP_JUMP):
                op = ops[0]
                if op.type == X86_OP_IMM:
                    if m == "jmp":
                        va = op.imm
                    else:
                        todo.append(op.imm)
                        va += ins.size
                    prev = ins
                    continue
                if (op.type == X86_OP_MEM and op.mem.base == 0 and op.mem.scale == 4 and bound
                        and bound[0] == op.mem.index):
                    cases = op.mem.disp & 0xFFFFFFFF   # a switch's table, bound[1] entries
                    todo += [struct.unpack("<I", code(cases + 4 * i, 4))[0] for i in range(bound[1])]
                break
            va, prev = va + ins.size, ins
    return pops


@pytest.mark.parametrize("release", BOTH)
def test_each_facts_function_pops_what_its_declared_abi_makes_its_caller_push(release, request):
    """AZ-108's guard (Modkit's test_va_audit, ported in Step 4.11c): a shim
    calling a game function through the ABI its release's facts declare
    leaves the stack balanced, so every RET reachable from the function's
    address (:func:`_ret_pops`) pops exactly what the declaration makes the
    caller push: cdecl 0, stdcall and thiscall ``arg_bytes``, fastcall
    ``arg_bytes`` less the 8 passed in ECX and EDX. A function that pops
    otherwise has a wrong convention, size or address in the facts: fix that."""
    with iso.Reader(request.getfixturevalue(f"{release.name}_iso")) as r:
        data = r.read("default.xbe")
    known, table = facts.of(release), xbe.sections(data)
    wrong = []
    for f in known.functions.values():
        want = {"cdecl": 0, "stdcall": f.arg_bytes, "thiscall": f.arg_bytes,
                "fastcall": max(0, f.arg_bytes - 8)}[f.convention]
        if (pops := _ret_pops(data, table, f.va)) != {want}:
            wrong.append(f"{f.name} ({f.convention}, {f.arg_bytes}) pops {sorted(pops)}, not {want}")
    assert (wrong, len(known.functions)) == ([], {"usa": 354, "europe": 254}[release.name])


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


KERNEL_BASE = 0x80010000   # where the retail loader maps xboxkrnl.exe, whose exports the resolver walks


def test_a_shims_call_of_a_kernel_function_the_game_doesnt_import_resolves_it_once_and_keeps_ecx_and_edx(
        usa_iso, tmp_path, monkeypatch):
    """Modkit's D1-extend (Step 4.24c): a shim may call a kernel function
    the USA XBE doesn't import (no thunk slot; the facts name its ordinal).
    Each such import lands a 37-byte stub of its own, writable for the
    cache it keeps (AZ-281), and the shared resolver lands once a pack. Run
    on the build, a shim calling two (fastcall IofCallDriver and
    ObfReferenceObject) reaches each kernel function through the resolver's
    walk of xboxkrnl's export table on its first call and through the cache
    on its second, ECX and EDX its arguments both times (AZ-041). A kernel
    variable with no slot is refused by name: it has no code to stub. Each
    facts kernel export is named as the kernel's catalogue
    (``devkit/sim/data/kernel.toml``) names its ordinal (AZ-114)."""
    from unicorn import UC_ARCH_X86, UC_MODE_32, Uc
    from unicorn.x86_const import UC_X86_REG_ESP

    with iso.Reader(usa_iso) as r:
        vanilla = r.read("default.xbe")
    known, real_of, real_shim = facts.of(gate.USA), facts.of, engine.shim
    extra = {"IofCallDriver": facts.Kernel("IofCallDriver", 86, "fastcall", 8, None),
             "ObfReferenceObject": facts.Kernel("ObfReferenceObject", 251, "fastcall", 4, None),
             "KeSystemTime": facts.Kernel("KeSystemTime", 154, "data", 0, None)}
    names = tomllib.loads((shimkit.ROOT / "devkit" / "sim" / "data" / "kernel.toml").read_text(encoding="utf-8"))["names"]
    assert [k.name for k in (*known.kernel.values(), *extra.values())] == [   # AZ-114: each its ordinal's
        names[str(k.ordinal)] for k in (*known.kernel.values(), *extra.values())]
    monkeypatch.setattr(facts, "of", lambda release: dataclasses.replace(known, kernel={**known.kernel, **extra})
                        if release is gate.USA else real_of(release))
    probes = {}
    for name, body in (("calls", "IofCallDriver(a, b); return ObfReferenceObject(a ^ b);"),
                       ("reads", "return KeSystemTime + a + b;")):
        source = tmp_path / f"{name}.c"
        source.write_text("__attribute__((fastcall)) unsigned int IofCallDriver(unsigned int, unsigned int);\n"
                          "__attribute__((fastcall)) unsigned int ObfReferenceObject(unsigned int);\n"
                          "__declspec(dllimport) extern unsigned int KeSystemTime;\n"
                          f"unsigned int c_entry(unsigned int a, unsigned int b) {{ {body} }}\n", encoding="utf-8")
        probes[name] = coff.parse(shimkit.compile(source))
    monkeypatch.setattr(engine, "shim", lambda name: probes.get(name) or real_shim(name))
    pack = mods.PACKS["qol_skip_logo"]

    def probe(name: str) -> mods.Pack:
        return dataclasses.replace(pack, sites=(dataclasses.replace(pack.sites[0], shim=name, symbol="_c_entry"),))
    layer = engine.plan(probe("calls"), gate.USA, {"default.xbe": vanilla})
    assert sorted(c.writable for c in layer.claims) == [False, False, True, True]   # the shim, the resolver, 2 stubs
    built = bytes(compose({"default.xbe": vanilla}, [layer])[0]["default.xbe"])
    hook = known.offset(0x5F6E5, 5)
    entry = 0x5F6E5 + 5 + struct.unpack_from("<i", built, hook + 1)[0]

    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    table, base = xbe.sections(built), struct.unpack_from("<I", built, 0x104)[0]
    uc.mem_map(base, -(-(max(s.va + s.vsize for s in table) - base) // 0x1000) * 0x1000)
    for s in table:
        uc.mem_write(s.va, built[s.raw:s.raw + min(s.raw_size, s.vsize)])
    kernel = bytearray(0x2000)   # a PE whose exports 86 and 251 each keep their ECX and EDX
    struct.pack_into("<I", kernel, 0x3C, 0x80)
    struct.pack_into("<I", kernel, 0x80 + 24 + 0x60, 0x200)              # the export directory
    struct.pack_into("<3I", kernel, 0x200 + 0x10, 1, 400, 0)            # first ordinal, functions, (names)
    struct.pack_into("<I", kernel, 0x200 + 0x1C, 0x300)                 # the functions' table
    for ordinal, at in ((86, 0x1000), (251, 0x1100)):
        struct.pack_into("<I", kernel, 0x300 + 4 * (ordinal - 1), at)
        kernel[at:at + 13] = (b"\x89\x0D" + struct.pack("<I", KERNEL_BASE + at + 0x80)
                              + b"\x89\x15" + struct.pack("<I", KERNEL_BASE + at + 0x84) + b"\xC3")
    uc.mem_map(KERNEL_BASE, 0x2000)
    uc.mem_write(KERNEL_BASE, bytes(kernel))
    stack, back = 0x00F00000, 0x0DEAD000
    uc.mem_map(stack, 0x10000)
    uc.mem_map(back, 0x1000)
    seen = []
    for a, b in ((0xAABBCCDD, 0x13572468), (0x55667788, 0x24681357)):   # the first resolves, the second is cached
        sp = stack + 0xF000
        uc.mem_write(sp, struct.pack("<3I", back, a, b))
        uc.reg_write(UC_X86_REG_ESP, sp)
        uc.emu_start(entry, back, count=10_000)
        seen.append([struct.unpack("<2I", uc.mem_read(KERNEL_BASE + at + 0x80, 8)) for at in (0x1000, 0x1100)])
    assert [(calls[0], calls[1][0]) for calls in seen] == [((0xAABBCCDD, 0x13572468), 0xAABBCCDD ^ 0x13572468),
                                                           ((0x55667788, 0x24681357), 0x55667788 ^ 0x24681357)]
    with pytest.raises(mods.PackError, match="kernel variable 'KeSystemTime' has no slot in the USA XBE's thunk"):
        engine.plan(probe("reads"), gate.USA, {"default.xbe": vanilla})


# --- Step 4.27e: Modkit's shim, COFF and kernel-import tests no test above pinned (test_coff_relocations,
# test_coff_section_alignment, test_append_xbe_section, test_kernel_imports, test_vanilla_thunks and
# test_shim_toolchain), ported leanly.


def _object(sections, symbols) -> bytes:
    """An i386 object as clang writes one: ``sections`` (name, flags, bytes or an uninitialized size, [(offset,
    symbol index, type)]) and ``symbols`` (name, value, section, storage, auxiliary records); a section name past
    8 bytes in the string table (``/N``)."""
    body, headers, strings, at = b"", [], b"", 20 + 40 * len(sections)
    for name, flags, data, relocs in sections:
        raw, size = (0, data) if isinstance(data, int) else (at + len(body), len(data))
        body += b"" if isinstance(data, int) else data
        relocs_at = at + len(body)
        body += b"".join(struct.pack("<IIH", *r) for r in relocs)
        if len(name) > 8:
            name, strings = f"/{4 + len(strings)}", strings + name.encode() + b"\0"
        headers.append(name.encode().ljust(8, b"\0") + struct.pack("<IIIIIIHHI", 0, 0, size, raw, relocs_at if relocs
                                                                  else 0, 0, len(relocs), 0, flags))
    table = b"".join(name.encode().ljust(8, b"\0") + struct.pack("<IhHBB", value, section, 0, storage, aux)
                     + bytes(18 * aux) for name, value, section, storage, aux in symbols)
    count = sum(1 + s[4] for s in symbols)
    return (struct.pack("<HHIIIHH", coff.MACHINE_I386, len(sections), 0, at + len(body), count, 0, 0)
            + b"".join(headers) + body + table + struct.pack("<I", 4 + len(strings)) + strings)


def test_a_shims_sections_land_each_its_own_writable_by_its_kind_at_its_alignment_relocated_to_its_own_symbols():
    """Modkit's test_coff_relocations and test_coff_section_alignment, on
    ``coff.layout``: an object's ``.text`` (a REL32 to its own helper, a
    DIR32 to its static in ``.bss`` and one to its second ``.rdata``), its
    ``.bss`` (zeros of its declared size, larger than the file: AZ-018;
    writable: AZ-220) and its two ``.rdata`` sections (each its own bytes and
    symbols, H8 and AZ-022; the ALIGN_16 one asked for at 16: AZ-019) each
    land where the allocator says, and its metadata (``.debug$S``,
    ``.llvm_addrsig``) doesn't; a symbol index past a section symbol's
    auxiliary record names its own symbol; a relocation type it doesn't
    land is refused by name, never skipped."""
    text = (b"\xE8" + bytes(4)             # 0: call _helper           (REL32)
            + b"\xFF\x05" + bytes(4)       # 5: inc dword [_g]         (DIR32)
            + b"\xA1" + bytes(4) + b"\xC3"   # 11: mov eax, [_k2]; ret (DIR32)
            + b"\x31\xC0\xC3")             # 17: _helper: xor eax, eax; ret
    sections = [(".text", 0x60500020, text, [(1, 3, coff.REL32), (7, 4, coff.DIR32), (12, 6, coff.DIR32)]),
                (".bss", 0xC0300080, 4096, []), (".rdata", 0x40300040, struct.pack("<f", 2.5), []),
                (".rdata", 0x40500040, bytes(range(16)), []), (".debug$S", 0x42100040, b"\x04\0\0\0", []),
                (".llvm_addrsig", 0x00100800, b"\x02", [])]
    symbols = [(".text", 0, 1, 3, 1), ("_c_entry", 0, 1, coff.EXTERNAL, 0), ("_helper", 17, 1, 3, 0),
               ("_g", 0, 2, 3, 0), ("_k1", 0, 3, 3, 0), ("_k2", 0, 4, 3, 0)]
    obj, asked = coff.parse(_object(sections, symbols)), []

    def allocate(size: int, align: int, writable: bool) -> tuple[int, int]:
        asked.append((size, align, writable))
        return 0x1000 * len(asked), 0x100000 * len(asked)
    placed, entry = coff.layout(obj, "_c_entry", allocate, {})
    assert [(p.section, p.index) for p in placed] == [(".text", 0), (".bss", 1), (".rdata", 2), (".rdata", 3)]
    assert asked == [(len(text), 16, False), (4096, 4, True), (4, 4, False), (16, 16, False)]
    code, bss, k1, k2 = placed
    assert (bss.data, k1.data, k2.data, entry) == (bytes(4096), struct.pack("<f", 2.5), bytes(range(16)), code.va)
    assert (code.va + 5 + struct.unpack_from("<i", code.data, 1)[0], struct.unpack_from("<I", code.data, 7)[0],
            struct.unpack_from("<I", code.data, 12)[0]) == (code.va + 17, bss.va, k2.va)
    odd = [(*sections[0][:3], [(7, 4, 0x1234)]), *sections[1:]]
    with pytest.raises(ValueError, match=re.escape("relocation type 0x1234 at .text+0x7 (AzurKit lands DIR32 and "
                                                   "REL32)")):
        coff.layout(coff.parse(_object(odd, symbols)), "_c_entry", allocate, {})


def test_the_carver_lays_shims_end_to_end_one_shims_section_at_their_alignment_whatever_their_bytes(usa_iso):
    """Modkit's test_append_xbe_section's carve cases (H7, AZ-019): the carve
    allocator places by claims, never by the bytes a claim holds, so three
    4-byte landings in ``.text``'s gap lie 4 apart; landings past it fill
    one appended SHIMS end to end, and one aligned 16 after an odd-sized one
    lands on 16 in both; their claims grow ``.text`` by what its gap took
    and append one SHIMS whose bytes cover the rest."""
    with iso.Reader(usa_iso) as r:
        vanilla = r.read("default.xbe")
    room, carver = xbe.room(vanilla), xbe.Carver(vanilla)
    small = [carver.place(4) for _ in range(3)]
    assert [(p[2], p[3]) for p in small] == [(room.gap + 4 * i, room.text.va + room.text.raw_size + 4 * i)
                                             for i in range(3)]
    big = [carver.place(301), carver.place(100), carver.place(16, 16)]
    assert [p[2] - room.shims for p in big] == [p[3] - room.shims_va for p in big] == [0, 301, 416]
    claims = [(at, size, False) for at, size, *_ in small + big]
    text, shims = (next(s for s in xbe.sections(xbe.grown(vanilla, claims)) if s.name == name)
                   for name in (".text", xbe.SHIMS))
    assert (text.raw_size - room.text.raw_size, shims.raw, shims.raw_size) == (12, room.shims, 432)
    assert [s.name for s in xbe.sections(xbe.grown(vanilla, claims))].count(xbe.SHIMS) == 1


def test_a_shims_kernel_imports_take_one_stub_a_function_and_a_variable_its_slot_and_an_unknown_one_is_refused(
        usa_iso, tmp_path, monkeypatch):
    """Modkit's test_kernel_imports (D1, AZ-020) on the engine: a shim's
    calls of a kernel function the game imports go through one 6-byte
    ``jmp [slot]`` stub a pack, however many calls (two functions, two
    stubs, each its own facts slot); a kernel variable is read through its
    slot itself, never a stub; another pack gets its own stubs past the
    first's claims. An external that is no vanilla function or kernel
    export the facts name is refused by name (Modkit's test_vanilla_thunks)."""
    with iso.Reader(usa_iso) as r:
        vanilla = r.read("default.xbe")
    known, real_of, real_shim = facts.of(gate.USA), facts.of, engine.shim
    extra = {"NtClose": facts.Kernel("NtClose", 187, "stdcall", 4, known.thunks)}   # the table's first slot
    monkeypatch.setattr(facts, "of", lambda release: dataclasses.replace(known, kernel={**known.kernel, **extra})
                        if release is gate.USA else real_of(release))
    probes = {}
    for name, body in (("calls", "MmFreeContiguousMemory(a); NtClose(MmFreeContiguousMemory(a + KeTickCount));"
                                 " return KeTickCount;"), ("strays", "return Frotz(a);")):
        (source := tmp_path / f"{name}.c").write_text(
            "__attribute__((stdcall)) unsigned int MmFreeContiguousMemory(unsigned int);\n"
            "__attribute__((stdcall)) unsigned int NtClose(unsigned int);\n"
            "__attribute__((stdcall)) unsigned int Frotz(unsigned int);\n"
            "__declspec(dllimport) extern unsigned int KeTickCount;\n"
            f"unsigned int c_entry(unsigned int a) {{ {body} }}\n", encoding="utf-8")
        probes[name] = coff.parse(shimkit.compile(source))
    monkeypatch.setattr(engine, "shim", lambda name: probes.get(name) or real_shim(name))
    pack = mods.PACKS["qol_skip_logo"]

    def probe(name: str) -> mods.Pack:
        return dataclasses.replace(pack, sites=(dataclasses.replace(pack.sites[0], shim=name, symbol="_c_entry"),))

    def targets(layer) -> tuple[dict[str, set[int]], dict[int, bytes]]:
        """Each external the shim names -> where its relocations reach, and the 6 bytes at each place it calls."""
        built = bytes(compose({"default.xbe": vanilla}, [layer])[0]["default.xbe"])
        hook = known.offset(0x5F6E5, 5)
        text_va = 0x5F6E5 + 5 + struct.unpack_from("<i", built, hook + 1)[0] - probes["calls"].symbol("_c_entry").value
        (text,) = (s for s in probes["calls"].sections if s.name == ".text")
        at = xbe.resolve_va_to_file(built, text_va)
        reach = {}
        for rel in text.relocations:
            word = struct.unpack_from("<I", built, at + rel.offset)[0]
            va = word if rel.type == coff.DIR32 else (text_va + rel.offset + 4 + word) & 0xFFFFFFFF
            reach.setdefault(probes["calls"].symbols[rel.symbol].name, set()).add(va)
        stubs = {va: built[(o := xbe.resolve_va_to_file(built, va)):o + 6] for name, vas in reach.items()
                 if not name.startswith("__imp__") for va in vas}
        return reach, stubs
    first = engine.plan(probe("calls"), gate.USA, {"default.xbe": vanilla})
    reach, stubs = targets(first)
    slot = {f"_{k}@4": known.kernel[k].slot if k in known.kernel else known.thunks for k in ("MmFreeContiguousMemory",
                                                                                              "NtClose")}
    assert {name: len(vas) for name, vas in reach.items()} == {"_MmFreeContiguousMemory@4": 1, "_NtClose@4": 1,
                                                               "__imp__KeTickCount": 1}
    assert reach["__imp__KeTickCount"] == {known.kernel["KeTickCount"].slot}
    assert stubs == {next(iter(reach[name])): b"\xFF\x25" + struct.pack("<I", s) for name, s in slot.items()}
    assert sorted(c.size for c in first.claims if c.size == 6) == [6, 6]
    second = engine.plan(probe("calls"), gate.USA, {"default.xbe": vanilla}, occupied=first.claims)
    assert not {(c.offset, c.size) for c in second.claims} & {(c.offset, c.size) for c in first.claims}
    with pytest.raises(mods.PackError, match=re.escape("the shim's external '_Frotz@4' is no vanilla function or "
                                                       "kernel export the facts name")):
        engine.plan(probe("strays"), gate.USA, {"default.xbe": vanilla})


def test_shimkit_compiles_with_no_warning_and_no_shell_puts_double_math_on_x87_and_names_a_compile_error(
        tmp_path, monkeypatch):
    """Modkit's test_shim_toolchain and test_autocompile's AZ-046/AZ-055:
    the Xbox's CPU is a Pentium III (SSE, no SSE2: its opcodes raise #UD on
    the hardware, though xemu runs them, AZ-021), so a shim's double math
    and its float-double conversions compile to x87, never SSE2's movsd,
    mulsd, cvttsd2si or cvtss2sd; a compile prints no warning (Q153, D86),
    with zig run by its path, no shell or PATH (a stock Windows host); and a
    source that doesn't compile raises with the compiler's own words
    (AZ-060), never a skip or a stale object."""
    runs, real_run = [], subprocess.run

    def kept(*args, **kwargs):
        runs.append(real_run(*args, **kwargs))
        return runs[-1]
    monkeypatch.setattr(shimkit.subprocess, "run", kept)
    monkeypatch.setenv("PATH", "")
    (src := tmp_path / "probe.c").write_text(
        "double c_dmul(double a, double b) { return a * b; }\n"
        "double c_widen(float f) { return f; }\n"
        "int c_trunc(double d) { return (int)d; }\n", encoding="utf-8")
    (text,) = (s.data for s in coff.parse(shimkit.compile(src)).sections if s.name == ".text")
    assert b"\xf2\x0f" not in text and b"\xf3\x0f\x5a" not in text
    shimkit.compile(shimkit.SHIMS / "qol_skip_logo.c")
    assert [done.stderr for done in runs] == ["", ""]
    src.write_text("#error simulated breakage\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="simulated breakage"):
        shimkit.compile(src)
