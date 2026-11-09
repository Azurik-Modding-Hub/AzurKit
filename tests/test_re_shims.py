"""devkit's shim authoring (``python -m devkit re``: ``plan-trampoline``,
``shim-inspect``, ``new-shim``, ``test-for-va`` and ``region-map``, Step
4.11e; Modkit's test_xbe_tools planner and inspector cases, test_scaffolder,
test_test_for_va and test_region, leanly): a hook site is sized to an
instruction boundary with what it can't size flagged; a scaffolded pack's
entry compiles to the symbol its trampoline calls, its ABI from Ghidra or
the facts; an object's sections, symbols and calls are listed at a
release's addresses; a VA or a pack picks the tests that spell it and those
the facts, the goldens and the import graph tie to it; and Europe's address
map holds on both images, as every address a Europe pack names or writes
and the live kit's Europe buffers do. No test prints a game byte."""

from __future__ import annotations

import ast
import dataclasses
import json
import runpy
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

import shimkit
from azurkit.core import coff, facts, gate
from azurkit.tools import mods
from azurkit.tools.mods import engine
from azurkit.tools.randomizer.live import recipes
from devkit.re import new_shim, plan_trampoline, region_map, shim_inspect, test_for_va, xbe
from tests.test_re_xbe import TEXT, synthetic

ROOT = Path(__file__).resolve().parent.parent
MODRM = bytes.fromhex(
    "8b442408"              # mov eax, [esp+8]            SIB, disp8
    "83ec0c"                # sub esp, 0xc               imm8
    "8d4c2410"              # lea ecx, [esp+0x10]
    "d94508"                # fld dword [ebp+8]          x87
    "c7057856341201000000"  # mov dword [0x12345678], 1  disp32, imm32
    "f7c100010000"          # test ecx, 0x100            F7 /0 imm32
    "f7d8"                  # neg eax                    F7 /3
    "8b048500100100"        # mov eax, [eax*4+0x11000]   SIB base 5
    "0fb64104"              # movzx eax, byte [ecx+4]
    "ff1500200100"          # call [0x12000]
    "817e10ff000000"        # cmp dword [esi+0x10], 0xff disp8, imm32
    "8b8034120000")         # mov eax, [eax+0x1234]      disp32


def test_plan_trampoline_sizes_a_hook_to_an_instruction_boundary_and_flags_what_it_cant(tmp_path, capsys):
    """Each instruction decodes at its full length (AZ-225: the ModR/M forms
    with their SIB byte, displacement and immediate, as capstone sizes
    them); the suggested length is the first boundary at or past the
    budget, an overshoot (a 6-byte JCC for a 5-byte CALL) or an opcode the
    decoder can't size (a prefix) is a warning, never a guess. The verb
    prints no byte of the code unless ``--bytes`` (a human's), exits 1 on a
    warning and 2, one line, on a VA with no file bytes (M25)."""
    cases = [  # code, budget, window -> suggested, clean, the warning's word, the lengths decoded
        (bytes.fromhex("e800000000"), 5, 5, (5, True, None, [5])),
        (bytes.fromhex("68acc11900"), 5, 5, (5, True, None, [5])),
        (bytes.fromhex("b803400100"), 5, 5, (5, True, None, [5])),
        (bytes.fromhex("668bec"), 5, 16, (0, False, "Unknown opcode", [0])),
        (bytes.fromhex("0f8400000000"), 5, 6, (6, False, "overshoots", [6])),
        (MODRM, 7, len(MODRM), (7, True, None, [4, 3, 4, 3, 10, 6, 2, 7, 4, 6, 7, 6])),
    ]
    for code, budget, window, (suggested, clean, warning, lengths) in cases:
        plan = plan_trampoline.plan_trampoline(bytes(synthetic(text=code)), TEXT, budget=budget, window=window)
        assert (plan.suggested_length, plan.clean_boundary, [i.length for i in plan.instructions]) == (
            suggested, clean, lengths), code.hex()
        assert any(warning in w for w in plan.warnings) if warning else plan.warnings == [], code.hex()
    (path := tmp_path / "synthetic.xbe").write_bytes(synthetic(text=bytes.fromhex("e800000000")))
    assert plan_trampoline.main([f"{TEXT:#x}", "--xbe", str(path)]) == 0
    out = capsys.readouterr().out
    assert "CALL rel32" in out and "e800000000" not in out and "[OK] Clean instruction boundary" in out
    assert plan_trampoline.main([f"{TEXT:#x}", "--xbe", str(path), "--bytes", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["instructions"][0]["bytes"] == "e800000000"
    path.write_bytes(synthetic(text=bytes.fromhex("668bec")))
    assert plan_trampoline.main([f"{TEXT:#x}", "--xbe", str(path)]) == 1
    assert "668bec" not in capsys.readouterr().out
    assert plan_trampoline.main(["0x100", "--xbe", str(path)]) == 2
    err = capsys.readouterr().err.splitlines()
    assert err[-1].startswith("plan-trampoline: VA 0x100 has no file bytes") and "Traceback" not in "".join(err)


def test_new_shim_scaffolds_a_pack_whose_entry_compiles_to_the_symbol_its_trampoline_calls(usa_iso, tmp_path,
                                                                                           capsys):
    """The skip-logo hook (0x5F6E5, a CALL of the facts' ``play_movie_fn``,
    stdcall with 8 argument bytes) plans clean at 5 bytes, and a pack
    scaffolded there takes the callee's ABI from the facts: its module's
    ``PACK`` hooks the USA address with a ``TrampolinePatch`` calling
    ``_c_<name>@8``, which its C entry compiles to with shimkit's flags and
    headers, and neither file holds the site's bytes (the facts' sha256
    stands for them). With no hook the entry is a ``stdcall`` ``void(void)``
    guess, ``_c_<name>@0``. A bad or taken name, an existing file and a
    second write refuse; ``--dry-run`` writes nothing; an ``--xbe`` that
    can't be read or isn't USA's exits 2, one line, never a guessed site."""
    data, _ = xbe.load(str(usa_iso))
    plan = plan_trampoline.plan_trampoline(data, 0x5F6E5)
    assert (plan.suggested_length, plan.clean_boundary, plan.preserved_mnemonics) == (5, True, ["CALL rel32"])
    hooked = new_shim.plan_scaffold("my_skip", root=tmp_path, hook_va=0x5F6E5, xbe_bytes=data)
    bare = new_shim.plan_scaffold("my_bare", root=tmp_path)
    assert (hooked.abi.attribute, hooked.abi.stdcall_n, hooked.abi.confidence, hooked.site_size) == (
        "stdcall", 8, "facts", 5)
    assert (bare.abi.attribute, bare.abi.parameters, bare.abi.confidence) == ("stdcall", (), "low")
    vanilla = data[plan.file_offset:plan.file_offset + 5].hex()
    for scaffold, symbol in ((hooked, "_c_my_skip@8"), (bare, "_c_my_bare@0")):
        new_shim.write_scaffold(scaffold)
        (site,) = runpy.run_path(str(scaffold.pack_path))["PACK"].sites
        assert (type(site), site.shim, site.symbol) == (engine.TrampolinePatch, scaffold.name, symbol)
        assert coff.parse(shimkit.compile(scaffold.shim_c_path)).symbol(symbol).section > 0
        assert vanilla not in scaffold.pack_body + scaffold.shim_c_body
    assert site.va == 0 and runpy.run_path(str(hooked.pack_path))["PACK"].sites[0].va == 0x5F6E5
    for name, match in (("my_skip", "already exists"), ("qol_skip_logo", "a pack named"), ("My-Skip", "invalid name")):
        with pytest.raises(ValueError, match=match):
            new_shim.plan_scaffold(name, root=tmp_path)
    with pytest.raises(ValueError, match="already exists"):
        new_shim.write_scaffold(hooked)
    assert new_shim.main(["my_dry_run", "--dry-run"]) == 0
    assert "files that WOULD be written" in capsys.readouterr().out
    (other := tmp_path / "other.xbe").write_bytes(synthetic(text=bytes.fromhex("e800000000")))
    for image in (tmp_path / "missing.xbe", other):
        assert new_shim.main(["my_dry_run", "--hook", "0x5F6E5", "--xbe", str(image), "--dry-run"]) == 2
        out, err = capsys.readouterr()
        assert out == "" and err.startswith("new-shim: ") and err.count("\n") == 1, image.name
    assert not any((ROOT / folder / f"my_dry_run{ext}").exists()
                   for folder, ext in ((new_shim.PACKS, ".py"), (new_shim.SHIMS, ".c")))


def test_new_shim_takes_the_convention_from_ghidras_parameter_storage():
    """Ghidra's parameters' storage gives the convention: all on the stack
    is ``stdcall``, ``ECX`` alone ``thiscall``, ``ECX`` and ``EDX``
    ``fastcall``, its ``@N`` clang's: every parameter, a byte or a short
    rounded up to 4, the registers' too; ``undefined`` returns ``void`` and
    ``undefined4`` ``unsigned int``; no parameters is the low-confidence
    default. A live client's answer is the scaffold's ABI and symbol; a
    failing one is a warning, the default kept."""
    stack, ecx, edx = "Stack[0x4]:4", "ECX:4", "EDX:4"
    cases = [  # signature, parameters' (type, storage) -> attribute, @N, return type, confidence
        ("int f(undefined1 a, short b)", [("undefined1", stack), ("short", stack)], ("stdcall", 8, "int", "high")),
        ("void m(void * this, int x)", [("void *", ecx), ("int", stack)], ("thiscall", 0, "void", "high")),
        ("undefined4 g(int a, int b, int c)", [("int", ecx), ("int", edx), ("int", stack)],
         ("fastcall", 12, "unsigned int", "high")),
        ("undefined h(void)", [], ("stdcall", 0, "void", "low")),
    ]
    for signature, params, want in cases:
        parameters = [{"name": f"p{i}", "dataType": t, "storage": s} for i, (t, s) in enumerate(params)]
        abi = new_shim.guess_abi_from_signature(signature, parameters)
        assert (abi.attribute, abi.stdcall_n, abi.return_type, abi.confidence) == want, signature
    live = SimpleNamespace(get_function=lambda va: SimpleNamespace(signature=cases[2][0], parameters=[
        {"name": "a", "dataType": "int", "storage": ecx}, {"name": "b", "dataType": "int", "storage": edx},
        {"name": "c", "dataType": "int", "storage": stack}]))
    scaffold = new_shim.plan_scaffold("my_fast", root=Path("/nonexistent"), hook_va=0x85700, ghidra_client=live)
    assert "__attribute__((fastcall))" in scaffold.shim_c_body and 'symbol="@c_my_fast@12"' in scaffold.pack_body
    dead = SimpleNamespace(get_function=lambda va: (_ for _ in ()).throw(OSError("connection refused")))
    scaffold = new_shim.plan_scaffold("my_dead", root=Path("/nonexistent"), hook_va=0x85700, ghidra_client=dead)
    assert scaffold.abi.confidence == "low" and any("Ghidra ABI lookup failed" in w for w in scaffold.planner_warnings)


def test_shim_inspect_lists_an_objects_sections_symbols_and_its_calls_at_the_releases_addresses(tmp_path, capsys):
    """A shim by name: qol_skip_logo's ``.text`` is its 5 bytes (``xor al,
    al; ret 8``), its entry ``_c_skip_logo`` defined there (not an
    undefined external). Each game
    function a shim calls is listed at the release's address (Step RG.5),
    or as having none there (a function Europe's facts don't list); a file
    that isn't COFF and a missing one are one line and exit 1."""
    r = shim_inspect.inspect_object("qol_skip_logo")
    text = next(s for s in r.sections if s.name == ".text")
    assert (text.raw_size, text.first_bytes) == (5, "30c0c20800")
    entry = next(s for s in r.symbols if s.name == "_c_skip_logo")
    assert (entry.storage_class_name, entry.section_number, entry.is_external) == ("EXTERNAL", 1, False)
    assert shim_inspect.resolve(shimkit.SHIMS / "qol_save_warp.c") == shimkit.SHIMS / "qol_save_warp.o"
    usa, europe = facts.of(gate.USA), facts.of(gate.EUROPE)
    for release, known in ((gate.USA, usa), (gate.EUROPE, europe)):
        r = shim_inspect.inspect_object("qol_save_warp", release)
        assert r.vanilla_vas and r.vanilla_vas == {
            s.name: known.mangled().get(s.name) for s in r.externals if s.name in usa.mangled()}
    gone = next(f.mangled for f in usa.functions.values() if f.name not in europe.functions)
    assert shim_inspect.vanilla_vas([gone, "_not_a_game_function"], gate.EUROPE) == {gone: None}
    assert shim_inspect.main(["qol_skip_logo", "--json", "--region", "europe"]) == 0
    assert json.loads(capsys.readouterr().out)["region"] == "europe"
    (not_coff := tmp_path / "default.xbe").write_bytes(b"XBEH" + bytes(256))
    for target, words in ((not_coff, "not a parseable PE-COFF"), (tmp_path / "missing.o", "no file or shim")):
        assert shim_inspect.main([str(target)]) == 1
        err = capsys.readouterr().err
        assert err.startswith("shim-inspect: ") and words in err and err.count("\n") == 1


def test_test_for_va_picks_each_spelling_test_and_what_the_facts_goldens_and_imports_tie_to_a_target(tmp_path):
    """A hit selects the test it sits in (with its test class), else its
    test class, else its module: never a helper class nested in a test or a
    class pytest doesn't collect. A VA is spelled at any width and case,
    and by the name of the facts function at it (0x18980,
    ``play_movie_fn``). No test need spell a VA the facts tie: a section's
    byte is the facts' test's; a site (0x893CE's starts 2 bytes in) is the
    sites test's, and its packs' (G1 builds them on each release they list,
    the sites test checks their sites there, G2 their shims); a pack's
    importers, by fullsuite's graph, never through the registry. The nodes
    named exist in the real tests."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_mod.py").write_text(
        "import unittest\n"
        "class Checks(unittest.TestCase):\n"
        "    def test_nested_helper(self):\n"
        "        class Helper:\n"
        "            pack = 'my_pack'\n"
        "def test_plain_function():\n"
        "    assert 'my_pack', 0x00018980\n"
        "class Setup(unittest.TestCase):\n"
        "    pack = 'my_pack'\n"
        "    def test_x(self): pass\n", encoding="utf-8")
    (tests / "test_constant.py").write_text(
        "PACK = 'my_pack'\n"
        "def test_uses_it(): assert PACK\n"
        "class TestBase:\n"
        "    def test_a(self): pass\n"
        "class Child(TestBase):\n"
        "    def test_b(self): assert 'my_pack', 'play_movie_fn'\n"
        "class TestHelper:\n"
        "    def __init__(self): self.pack = 'my_pack'\n", encoding="utf-8")

    def picked(target, deps=None) -> list[tuple[str, str]]:
        return [(m.pytest_selector(), m.why) for m in test_for_va.find_matches(target, tests, deps or {})]

    assert [s for s, _ in picked("my_pack")] == ["tests/test_constant.py", "tests/test_mod.py::Checks::test_nested_helper",
                                                 "tests/test_mod.py::Setup", "tests/test_mod.py::test_plain_function"]
    facts_test = ("tests/test_packs.py::" + test_for_va.FACTS_TEST.partition("::")[2], "the facts' sections")
    assert picked(0x18980) == [("tests/test_constant.py", "spelled"), ("tests/test_mod.py::test_plain_function", "spelled"),
                               facts_test]
    assert picked(0x1A25B8) == [facts_test]   # a constant no pack writes
    sites, g1, g2 = (f"tests/{n.rpartition('/')[2]}" for n in (test_for_va.SITES_TEST, test_for_va.G1_TEST,
                                                                 test_for_va.G2_TEST))
    graph = {"tests.test_y": {"azurkit.tools.mods.packs.player_physics"}, "tests.test_z": {"azurkit.tools.mods"},
             "azurkit.tools.mods": {"azurkit.tools.mods.packs"}, "azurkit.tools.mods.packs": {
                 "azurkit.tools.mods.packs.player_physics"}}
    assert picked(0x893CE, graph) == [
        (f"{g1}[europe]", "G1 builds player_physics"), (f"{g1}[usa]", "G1 builds player_physics"),
        (f"{sites}[europe]", "player_physics's sites"), (f"{sites}[usa]", "the facts' site"), facts_test,
        (g2, "player_physics's shim"), ("tests/test_y.py", "imports player_physics")]
    for node in test_for_va.NODES:
        path, _, name = node.partition("::")
        assert name in {n.name for n in ast.parse((ROOT / path).read_text(encoding="utf-8")).body
                        if isinstance(n, ast.FunctionDef)}, node


def _targets(va: int, data: bytes, abs32, rel32) -> list[int]:
    return ([struct.unpack_from("<I", data, k)[0] for k in abs32]
            + [(va + k + 4 + struct.unpack_from("<i", data, k)[0]) & 0xFFFFFFFF for k in rel32])


def test_europes_address_map_holds_on_both_images_and_a_moved_entry_of_each_role_fails(usa_iso, europe_iso):
    """``region-map check``: each entry of the facts' map holds on the two
    vanilla images by the role its USA address gives it (a facts site, its
    operands moved through the map; code outside its address fields; data;
    an instruction's unique twin, for BSS and what was rebuilt), and an
    entry of each role moved by 4 bytes fails, by its addresses. ``find``
    gives a site's Europe address alone."""
    usa, eu = region_map.Image(xbe.load(str(usa_iso))[0]), region_map.Image(xbe.load(str(europe_iso))[0])
    known = facts.of(gate.EUROPE)
    assert region_map.check(usa, eu) == []
    roles = {}
    for u, e in sorted(known.addresses.items()):
        role = ("site" if u in facts.of(gate.USA).sites else "zero-filled" if not min(usa.held(u), eu.held(e))
                else "code" if usa.code(u) else "data")
        roles.setdefault(role, (u, e))
    assert roles.keys() == {"site", "code", "data", "zero-filled"}
    for role, (u, e) in roles.items():
        moved = region_map.check(usa, eu, dataclasses.replace(known, addresses={u: e + 4}, absent={}))
        assert [line.partition(":")[0] for line in moved] == [f"0x{u:08X} -> 0x{e + 4:08X}"], role
    assert region_map.find(usa, eu, 0x5F6E5) == [known.va(0x5F6E5)]


def test_every_address_a_europe_pack_names_or_writes_is_mapped_declared_and_never_fixed_in_its_shim(usa_iso):
    """AZ-325, AZ-324, R2.1b: each place a pack that lists Europe writes at
    a USA address, and each address its patch bytes hold, has a Europe
    entry or a named absence; each code patch's in-image absolute operands
    and rel32 branches are exactly the ``abs32``/``rel32`` it declares (one
    it didn't would write USA's address on Europe); and its prebuilt C
    shims' ``.text`` holds no address of the image outside a relocation
    (a fixed ``0x...`` reads USA's on Europe)."""
    usa = region_map.Image(xbe.load(str(usa_iso))[0])
    known, problems = facts.of(gate.EUROPE), []
    for pack in (p for p in mods.PACKS.values() if gate.EUROPE.name in p.releases):
        for place in (s for s in (*pack.sites, *pack.footprint) if getattr(s, "va", 0) and s.on("usa")):
            spec = place if isinstance(place, engine.PatchSpec) else None
            for va in [place.va, *(_targets(place.va, spec.patch, spec.abs32, spec.rel32) if spec else ())]:
                if va not in known.addresses and va not in known.absent:
                    problems.append(f"{pack.name} 0x{place.va:X}: 0x{va:X} has no Europe entry")
            if spec and usa.code(spec.va):
                s = usa.section(spec.va)
                at = s.raw + spec.va - s.va
                patched = region_map.Image(usa.xbe[:at] + spec.patch + usa.xbe[at + len(spec.patch):])
                found = {(k, kind) for k, kind, _ in patched.fields(spec.va, len(spec.patch))}
                if found != {(k, "abs32") for k in spec.abs32} | {(k, "rel32") for k in spec.rel32}:
                    problems.append(f"{pack.name} 0x{spec.va:X}: declares {spec.abs32}, {spec.rel32}; holds {found}")
            if isinstance(place, engine.TrampolinePatch):
                for text in (s for s in engine.shim(place.shim).sections if s.name == ".text"):
                    relocated = {r.offset for r in text.relocations}
                    if fixed := [f"0x{t:X}" for k, _, t in usa.code_fields(0x7F000000, text.data) if k not in relocated]:
                        problems.append(f"{pack.name}: {place.shim}.o holds {fixed}")
    assert problems == []


def test_the_live_kits_place_and_level_hop_write_europes_own_buffers_through_the_map():
    """AZ-420: the sitting kit's R6 place (Continue's place struct) and R7
    level hop (the levelSwitch fire's request) write Europe's own buffers,
    0x392100 and 0x38F2C8, through the facts' map, and point the request
    block at them; the move-state setter the ladder rows break on and the
    ladder latch's three offset globals are the map's too (Step X.45)."""
    eu = facts.of(gate.EUROPE).va
    assert [eu(va) for va in (0x8BDB0, 0x38B678, 0x38ABB8, 0x38B67C)] == [0x8BD60, 0x38D618, 0x38CB58, 0x38D61C]
    writes = (recipes.place(lambda va: 0, (0.0, 0.0, 0.0), 0.0, cell=0, va=eu)
              + recipes.hop(lambda va: 0, "levels/fire/f6", "startspot", va=eu))
    assert [(va, len(data)) for va, data in writes] == [
        (0x392100, 30), (recipes.R_PLACE, 4), (0x38F2C8, 1), (0x38F3CC, 15), (0x38F4D0, 10), (recipes.R_LEVEL, 4)]
    assert (writes[1][1], writes[-1][1]) == (struct.pack("<I", 0x392100), struct.pack("<I", 0x38F2C8))


# --- Step 4.27e: Modkit's kernel-ordinal and shim-header tests no test above pinned (test_kernel_imports,
# test_d1_extend's catalogue and test_shim_authoring), ported leanly.


def test_the_kernel_catalogue_names_each_retail_export_once_and_each_releases_thunk_table_by_it(usa_iso, europe_iso):
    """Modkit's test_kernel_imports' ordinal and thunk-table checks and
    test_d1_extend's catalogue (AZ-114): devkit's kernel catalogue
    (``devkit/sim/data/kernel.toml``) names every retail export, ordinals
    1-366, each name once, at the retail kernel's ordinals; each release's
    thunk table, read from its image (``parse_kernel_thunks``), is contiguous
    dwords from the facts' address, every slot an ordinal the catalogue
    names (USA's first four NtClose, NtQueryDirectoryFile, NtOpenFile and
    RtlInitAnsiString), and each facts kernel export sits at its slot."""
    import tomllib

    from azurkit.core import iso
    from devkit.sim import ports as sim

    names = {int(k): v for k, v in tomllib.loads(sim.KERNEL.read_text(encoding="utf-8"))["names"].items()}
    assert sorted(names) == list(range(1, 367)) and len(set(names.values())) == 366
    retail = {"DbgBreakPoint": 5, "DbgPrint": 8, "DbgPrompt": 10, "IoStartNextPacketByKey": 82,
              "IoSynchronousDeviceIoControlRequest": 84, "KdDebuggerEnabled": 88, "KeBugCheck": 95,
              "KeGetCurrentThread": 104, "KeTickCount": 156, "MmFreeContiguousMemory": 171, "MmIsAddressValid": 174,
              "NtClose": 187, "ObReferenceObjectByName": 247, "ObfReferenceObject": 251, "PsCreateSystemThread": 254,
              "RtlZeroMemory": 320, "XboxKrnlVersion": 324, "HalEnableSecureTrayEject": 365}
    assert {n: o for o, n in names.items() if n in retail} == retail
    for release, path in ((gate.USA, usa_iso), (gate.EUROPE, europe_iso)):
        with iso.Reader(path) as r:
            table = sim.parse_kernel_thunks(r.read("default.xbe"))
        known = facts.of(release)
        assert [t.thunk_va for t in table] == [known.thunks + 4 * i for i in range(len(table))], release.name
        assert [t.name for t in table] == [names[t.ordinal] for t in table], release.name
        assert {k.name: k.slot for k in known.kernel.values()} == {
            k.name: next(t.thunk_va for t in table if t.ordinal == k.ordinal) for k in known.kernel.values()}
    assert known.thunks != facts.of(gate.USA).thunks and facts.of(gate.USA).thunks == 0x18F3A0
    with iso.Reader(usa_iso) as r:
        assert [t.name for t in sim.parse_kernel_thunks(r.read("default.xbe"))[:4]] == [
            "NtClose", "NtQueryDirectoryFile", "NtOpenFile", "RtlInitAnsiString"]


CONTROLLER = {"left_stick_x": 0x00, "left_stick_y": 0x04, "right_stick_x": 0x08, "right_stick_y": 0x0C, "dpad_y": 0x10,
              "dpad_x": 0x14, "button_a": 0x18, "button_y": 0x24, "trigger_left": 0x30, "trigger_right": 0x34,
              "stick_left_click": 0x38, "stick_right_click": 0x3C, "start_button": 0x40, "back_button": 0x44,
              "edge_state": 0x48}
"""ControllerState's fields at the offsets the game's XInput poll (0xA2880) writes (``dpad_y`` holds the X axis:
AZ-234)."""
STRUCTS = {
    "PlayerInputState": {"stick_magnitude": 0x1C, "flags": 0x20, "dead": 0x21, "ref_x": 0x24, "critter_data": 0x34,
                         "direction_angle": 0x120, "magnitude": 0x124, "direction_x": 0x128, "direction_y": 0x12C,
                         "direction_z": 0x130},
    "CritterData": {"collision_radius": 0x18, "scale": 0x24, "walk_speed": 0x38, "run_speed": 0x40,
                    "ouch2_threshold": 0x48, "ouch3_threshold": 0x4C, "ouch1_knockback": 0x50, "ouch2_knockback": 0x54,
                    "ouch3_knockback": 0x58, "hits_through_walls": 0x7C, "drown_time": 0x80, "shadow_size": 0x94,
                    "range": 0xB8, "range_up": 0xBC, "range_down": 0xC0, "attack_range": 0xC4, "drop_1": 0xD4,
                    "drop_5": 0xE4, "drop_count_1": 0xE8, "drop_count_5": 0xF8, "drop_chance_1": 0xFC,
                    "drop_chance_5": 0x10C},
    "ControllerState": CONTROLLER}
"""The fields Ghidra placed (Modkit's test_shim_authoring; CritterData's ouch rows misnamed once)."""


def test_the_structures_a_shim_or_the_re_data_declares_hold_each_field_at_ghidras_offset(tmp_path):
    """Modkit's test_shim_authoring (AZ-258): a probe of one
    ``_Static_assert`` a field (``__builtin_offsetof``) or a constant,
    apart from the headers' own asserts, compiles against devkit's RE
    structures (``structs.h``: PlayerInputState, CritterData,
    ControllerState, and PLAYER_FLAG_RUNNING 0x40 and _FALLING 0x01, the
    bits 0x84940 tests) and against the ControllerState shimkit's
    ``azurik_vanilla.h`` gives every shim; a field moved fails by name."""
    def asserts(offsets: dict[str, dict[str, int]]) -> str:
        return "\n".join(f"_Static_assert(__builtin_offsetof({struct}, {field}) == 0x{at:X}, "
                         f'"{struct}.{field} is not at 0x{at:X}");'
                         for struct, fields in offsets.items() for field, at in fields.items())
    flags = ('_Static_assert(PLAYER_FLAG_RUNNING == 0x40u, "RUNNING");\n'
             '_Static_assert(PLAYER_FLAG_FALLING == 0x01u, "FALLING");\n')
    for name, header, offsets, extra in (("re", (xbe.DATA / "structs.h").as_posix(), STRUCTS, flags),
                                         ("shim", "azurik_vanilla.h", {"ControllerState": CONTROLLER}, "")):
        (probe := tmp_path / f"{name}.c").write_text(f'#include "{header}"\n{asserts(offsets)}\n{extra}',
                                                     encoding="utf-8")
        assert coff.parse(shimkit.compile(probe)).machine == coff.MACHINE_I386, name
    probe.write_text('#include "azurik_vanilla.h"\n' + asserts({"ControllerState": {"back_button": 0x40}}),
                     encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"ControllerState\.back_button is not at 0x40"):
        shimkit.compile(probe)


def test_new_shim_lists_its_flags_and_refuses_a_bad_name_or_category_by_name_exit_1(capsys):
    """Modkit's test_scaffolder CLI cases (Step 2.84): ``new-shim --help``
    lists each flag; a name that isn't a lowercase identifier and a
    category the packs don't have (Modkit's retired Experimental tab) are
    each one ``new-shim:`` line naming why, exit 1, nothing printed or
    written."""
    with pytest.raises(SystemExit) as done:
        new_shim.main(["--help"])
    out = capsys.readouterr().out
    assert done.value.code == 0 and all(f in out for f in ("--hook", "--iso", "--xbe", "--category", "--ghidra",
                                                           "--port", "--dry-run"))
    for argv, why in ((["BadName"], "invalid name 'BadName'"), (["my_x", "--category", "experimental"],
                                                                 "no category 'experimental'")):
        assert new_shim.main([*argv, "--dry-run"]) == 1
        out, err = capsys.readouterr()
        assert (out, err.startswith(f"new-shim: {why}"), err.count("\n")) == ("", True, 1), argv
    assert not (ROOT / new_shim.PACKS / "my_x.py").exists()
