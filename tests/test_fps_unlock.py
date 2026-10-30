"""fps_unlock's frame rate against the vanilla USA XBE (Modkit's
``test_fps_coverage.py`` and ``test_fps_safety.py``, ported in Step
4.12a): the 60 FPS audit's coverage of every 1/30 s, 30.0 and 60.0
constant in ``.rdata``, what each audited reader reads in a build, that no
vanilla instruction reads a slot the pack fills, and each class of site at
any rate F.

No disassembler: each instruction these read is an x87 one with an
absolute operand (an opcode D8-DF, a ModRM of mod 00 and r/m 101, then the
address), which :func:`_operand` decodes, and refuses any other. The
catch-up's run at a hitch is Modkit's Unicorn check (``test_fps_safety``)
until the simulator is ported (Step 4.13); its step count and timestep are
checked here."""

from __future__ import annotations

import hashlib
import math
import struct

from azurkit.core import facts, gate, iso, xbe
from azurkit.edits.layer import compose
from azurkit.tools import mods
from azurkit.tools.mods import engine
from azurkit.tools.mods.packs import fps_unlock
from scripts import record_goldens

# .rdata's 30.0 and 60.0 floats that aren't frame rates (the 60 FPS audits, Ghidra xrefs), by USA address.
NOT_A_RATE_30 = {
    0x0019FD98: "threshold in FUN_0003EA00 (not a rate)",
    0x001A2524: "high half of the double 2^32 at 0x1A2520 (KEEP_30: fps_unlock's keep-30 redirects read it)",
    0x00198B7C: "HUD list age, 30 x dt against a 25.0 life (AZ-331)",
    0x00198A74: "HUD flipbook frame from seconds (AZ-332)",
}
NOT_A_RATE_60 = {
    0x0019D816: "pRenderer UI scale", 0x0019D82A: "pRenderer UI scale",
    0x0019E628: "UI y-position math (FUN_0005AC80)", 0x0019FBCE: "rendering scale",
    0x001A1ADE: "rendering scale", 0x001A2608: "FOV default (FUN_00054800)",
}
# What each reader reads under fps_unlock, as a rule on what it reads in vanilla (the 60 FPS audit, 2026-10-12):
# a reader counting seconds keeps vanilla's value, a factor applied once a tick its square root, the ground
# probe's offset halves.
KEEP, SQRT, HALF = (lambda v: v), math.sqrt, (lambda v: v / 2)
READERS = {
    0x1A635: KEEP,  # HUD list age, 30 x dt against a 25.0 life (AZ-331)
    0x242B5: KEEP,  # HUD flipbook frame, 30 x seconds (AZ-332)
    0x3EADD: KEEP,  # hit-flash fade window, 1/6 s (AZ-333)
    0x3EB7F: KEEP,
    0x3EBD3: KEEP,  # hit-flash flicker index, 30 x seconds (AZ-334)
    0xBDA6D: KEEP,  # the double FLT_EPSILON (AZ-330)
    0x2A0BA: SQRT,  # the fire bosses' vx *= 0.85 per think (AZ-335)
    0x2A0CB: SQRT,  # vy
    0x2BB53: SQRT,  # Spideyzar's meter *= 0.9885 per think (AZ-336)
    0x86160: HALF,  # the ground probe's 0.1
}
# The bytes an x87 instruction with an absolute operand reads: by its opcode, and for D9, DB, DD and DF by
# ModRM's reg field too (the forms these readers and the slots' neighbours use).
X87 = {0xD8: 4, 0xDA: 4, 0xDC: 8, 0xDE: 2, (0xD9, 0): 4, (0xD9, 2): 4, (0xD9, 3): 4, (0xDB, 0): 4, (0xDB, 2): 4,
       (0xDB, 3): 4, (0xDB, 5): 10, (0xDD, 0): 8, (0xDD, 2): 8, (0xDD, 3): 8, (0xDF, 5): 8, (0xDF, 7): 8}
DT = 0x1983E8                           # the main loop's timestep
CATCHUP = 0x59B37                       # the catch-up after a hitch
SOLVER_DOUBLINGS = (0x47BC6, 0x47CF3)   # FADD ST0,ST0, 2 bytes each
# The code changes, the same at any F: the D3D VSync and spin-wait, the keep-30 and decay redirects, the ground
# probe's redirect.
FIXED = {0x12635D: 2, 0x1263E2: 1, 0x4E9D9: 4, 0x89AAC: 4, 0xFB518: 4, 0xFB608: 4,
         0x3EBD5: 4, 0x2A0BC: 4, 0x2A0CD: 4, 0x2BB55: 4, 0x86162: 4}


def _vanilla(path) -> bytes:
    with iso.Reader(path) as r:
        return r.read(engine.XBE)


def _built(vanilla: bytes, fps: int) -> bytes:
    layer = mods.plan(mods.PACKS["fps_unlock"], gate.USA, {engine.XBE: vanilla}, {"target_fps": fps})
    return bytes(compose({engine.XBE: vanilla}, [layer])[0].get(engine.XBE, vanilla))


def _at(va: int, size: int = 1) -> int:
    return facts.of(gate.USA).offset(va, size)


def _span(data: bytes, va: int, size: int) -> bytes:
    return data[_at(va, size):_at(va, size) + size]


def _operand(data: bytes, va: int) -> tuple[int, int]:
    """The address and size an x87 instruction at ``va`` reads; AssertionError for any other instruction."""
    op, modrm = data[_at(va)], data[_at(va) + 1]
    size = X87.get(op) or X87.get((op, modrm >> 3 & 7))
    assert size and modrm & 0xC7 == 0x05, f"0x{va:X} is no x87 instruction with an absolute operand"
    return struct.unpack_from("<I", data, _at(va) + 2)[0], size


def _floats(data: bytes, lo: float, hi: float, width: int) -> list[int]:
    """The address of every ``width``-byte float in ``.rdata`` (at any byte) in [lo, hi], zero aside."""
    rdata = next(s for s in xbe.sections(data) if s.name == ".rdata")
    fmt = "<f" if width == 4 else "<d"
    return [rdata.va + i for i in range(rdata.raw_size - width + 1)
            if (v := struct.unpack_from(fmt, data, rdata.raw + i)[0]) and math.isfinite(v) and lo <= v <= hi]


def test_every_frame_rate_constant_in_rdata_is_patched_or_classified(usa_iso):
    """The vanilla ``.rdata`` holds 29 float and 1 double 1/30 s, all
    halved by fps_unlock; 5 float and 1 double 30.0, each a rate it sets or
    one :data:`NOT_A_RATE_30` classifies; 6 float 60.0, none a rate; and no
    1/60. A new one fails, to be patched or classified."""
    data = _vanilla(usa_iso)
    patched = {s.va for s in fps_unlock.sites(60, lambda va, size: bytes(size))}
    third = (_floats(data, 0.03333, 0.03334, 4), _floats(data, 0.033333, 0.033334, 8))
    thirty = (_floats(data, 29.99, 30.01, 4), _floats(data, 29.999, 30.001, 8))
    sixty = _floats(data, 59.99, 60.01, 4)
    assert [len(hits) for hits in (*third, *thirty, sixty)] == [29, 1, 5, 1, 6]
    assert [va for hits in third for va in hits if va not in patched] == []
    assert [va for hits in thirty for va in hits if va not in patched and va not in NOT_A_RATE_30] == []
    assert set(sixty) == set(NOT_A_RATE_60)
    assert _floats(data, 0.01666, 0.01667, 4) + _floats(data, 0.01666, 0.01667, 8) == []


def test_each_reader_sees_its_60_fps_value_and_no_instruction_reads_a_filled_slot(usa_iso):
    """Each reader in :data:`READERS` reads, in a build with fps_unlock, its
    rule applied to what it reads in vanilla (where the build points it
    elsewhere, at its new operand). Each slot the pack fills (a data site
    whose vanilla bytes are zero) is read by no vanilla instruction: every
    word of the XBE that names an address from 16 bytes below a slot to 4
    past its start is an x87 instruction's operand that ends below it
    (AZ-330: the 0.05 went into the low half of a double)."""
    vanilla = _vanilla(usa_iso)
    built = _built(vanilla, 60)
    for va, rule in READERS.items():
        (at, size), (moved, _) = _operand(vanilla, va), _operand(built, va)
        fmt = "<f" if size == 4 else "<d"
        before = struct.unpack_from(fmt, vanilla, _at(at, size))[0]
        after = struct.unpack_from(fmt, built, _at(moved, size))[0]
        assert struct.pack(fmt, after) == struct.pack(fmt, rule(before)), (hex(va), before, after)
    table = xbe.sections(vanilla)
    rdata = next(s for s in table if s.name == ".rdata")
    slots = [s.va for s in fps_unlock.sites(60, lambda va, size: _span(vanilla, va, size))
             if rdata.va <= s.va < rdata.va + rdata.vsize and not any(_span(vanilla, s.va, len(s.patch)))]
    assert sorted(slots) == [0x1A268C, 0x1A2704, 0x1A2724]
    named = 0
    for s in table:   # every word of the file's sections, code or data
        for i in range(s.raw_size - 3):
            r = struct.unpack_from("<I", vanilla, s.raw + i)[0]
            for slot in (slot for slot in slots if slot - 16 < r < slot + 4):
                at, size = _operand(vanilla, s.va + i - 2)
                assert (at, at + size <= slot) == (r, True), f"0x{s.va + i - 2:X} reads the slot 0x{slot:X}"
                named += 1
    assert named == 36


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def test_target_fps_sets_every_site_class_from_the_rate(usa_iso):
    """30 builds vanilla, 60 the golden's XBE, and at 60 and 144 each site
    class holds its value at that rate, the code changes are 60's, and the
    catch-up runs cap steps of the timestep it loads; the solver keeps its
    x2 at 42."""
    vanilla = _vanilla(usa_iso)
    sha = lambda data: hashlib.sha256(data).hexdigest()  # noqa: E731
    assert sha(_built(vanilla, 30)) == sha(vanilla)
    sixty = _built(vanilla, 60)
    assert sha(sixty) == record_goldens.recorded("packs.json")["fps_unlock"]["default.xbe"]
    for fps in (60, 144):
        built, cap = _built(vanilla, fps), math.ceil(fps / 15)
        expected = {
            "VBlanks per present": (0x8FD1B, "<b", math.ceil(60 / fps)),
            "rate, double": (0x1A28C8, "<d", fps),
            "rate, shared float": (0x1A2650, "<f", fps),
            "timestep, float": (DT, "<f", _f32(1 / fps)),
            "timestep, double": (0x1A2750, "<d", 1 / fps),
            "decay 0.85": (0x1A2704, "<f", _f32(_f32(0.85) ** (30 / fps))),
            "decay 0.9885": (0x1A2724, "<f", _f32(_f32(0.9885) ** (30 / fps))),
            "step cap, truncation": (0x59B2F, "<b", cap),
            "bounce limit": (0x47EEF, "<b", cap),
            "ground probe": (0x1A268C, "<f", _f32(_f32(0.1) * 30 / fps)),
            "solver correction cap": (0x1AA230, "<f", _f32(_f32(0.001) * 30 / fps)),
        }
        for name, (va, fmt, want) in expected.items():
            assert struct.unpack_from(fmt, built, _at(va))[0] == want, (fps, name)
        for va, size in (*FIXED.items(), *((va, 2) for va in SOLVER_DOUBLINGS)):
            assert _span(built, va, size) == _span(sixty, va, size), (fps, hex(va))
        catchup = _span(built, CATCHUP, 9)   # FLD [DT]; PUSH cap; POP ESI: the steps it allows
        assert (catchup[:2], struct.unpack_from("<I", catchup, 2)[0], catchup[6:]) == (
            b"\xd9\x05", DT, bytes([0x6A, cap, 0x5E])), fps
    for va in SOLVER_DOUBLINGS:
        assert _span(_built(vanilla, 42), va, 2) == _span(vanilla, va, 2)
