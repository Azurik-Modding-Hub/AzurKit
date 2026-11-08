"""Simulator Level 1: is the code a build patched in well-formed?

Modkit's Step 2.7 (behavior test 4; ported in Step 4.13a).  :func:`check`
compares a patched XBE with vanilla and disassembles, with Capstone, every byte the
build changed or added:

- patched code decodes, and each in-place edit falls back onto a vanilla
  instruction boundary (or ends in an unconditional ``jmp``/``ret``);
- every direct branch lands on an instruction start in mapped code
  (N6: a trampoline's target is checked, not just its opcode byte), and
  no vanilla branch the build kept now lands inside a patched instruction
  (one whose own bytes it rewrote is gone);
- ``ret N`` parity (the ``ret 0xA408`` class, AZ-001): a shim reached by
  a ``call`` that replaced a ``call`` returns with the original callee's
  ``ret N`` (a tail ``jmp`` returns with its target's), one that replaced
  inline code with a plain ``ret``; a ``ret`` written into a vanilla
  function keeps that function's ``ret N``;
- the floats the build wrote are finite: those patched code reads through
  FPU memory operands, rewritten float immediates and the caller's
  ``float_vas`` (bytes the build left alone, BSS included, are not judged);
- what Unicorn can't see: no instruction the Pentium III lacks (SSE2 and
  later, AZ-021), and absolute 16-byte operands are 16-byte aligned
  (AZ-019).

Code and data are told apart by section name, never by section flags
(``.rdata`` is flagged executable).  Bytes a build added (the grown
``.text`` tail, appended sections) are code where patched code branches
to them and data where it reads them.

The API takes bytes, e.g. from the ISO reader
(:func:`azurik_mod.iso.read_xbe`, which uses :mod:`devkit.sim.ports`).
"""

from __future__ import annotations

import math
import struct
from bisect import bisect_left, bisect_right
from functools import lru_cache

from capstone import CS_ARCH_X86, CS_MODE_32, Cs
from capstone import x86 as X

from devkit.sim.ports import parse_kernel_thunks
from devkit.sim.ports import parse_xbe_sections
from devkit.sim import require_usa
from devkit.re.xbe import DATA_SECTIONS, lacks_on_pentium3

_FPU_READS = frozenset({"fld", "fadd", "fsub", "fsubr", "fmul", "fdiv",
                        "fdivr", "fcom", "fcomp"})
_UNALIGNED_OK = frozenset({"movups", "movupd", "movdqu", "lddqu"})
_ENDS_FLOW = frozenset({"jmp", "ret"})

_MD = Cs(CS_ARCH_X86, CS_MODE_32)
_MD.detail = True


class _Image:
    def __init__(self, data: bytes):
        self.data = data
        _, self.sections = parse_xbe_sections(data)

    def section(self, va: int) -> dict | None:
        """The section whose file-backed bytes hold ``va``."""
        return next((s for s in self.sections
                     if s["vaddr"] <= va < s["vaddr"] + s["raw_size"]), None)

    def read(self, va: int, n: int) -> bytes:
        s = self.section(va)
        if s is None:
            return b""
        off = s["raw_addr"] + va - s["vaddr"]
        return self.data[off:min(off + n, s["raw_addr"] + s["raw_size"])]

    def insn(self, va: int):
        return next(_MD.disasm(self.read(va, 15), va, count=1), None)


@lru_cache(maxsize=1)
def _sweep(vanilla: bytes) -> tuple[list[int], dict[int, list[tuple[int, int]]]]:
    """Instruction starts, and each direct branch target with the
    ``(address, size)`` of the branches to it, from a linear sweep of
    vanilla's code (~0.3 s)."""
    md, starts, targets = Cs(CS_ARCH_X86, CS_MODE_32), [], {}
    for s in _Image(vanilla).sections:
        if s["name"] in DATA_SECTIONS:
            continue
        code, off = vanilla[s["raw_addr"]:s["raw_addr"] + s["raw_size"]], 0
        while off < len(code):
            for addr, size, m, op in md.disasm_lite(code[off:], s["vaddr"] + off):
                starts.append(addr)
                if m.startswith(("j", "call", "loop")) and op.startswith("0x"):
                    targets.setdefault(int(op, 16), []).append((addr, size))
                off += size
            off += 1  # step over an undecodable byte
    return sorted(starts), targets


def _is_boundary(bounds: list[int], va: int) -> bool:
    i = bisect_right(bounds, va) - 1
    return i >= 0 and bounds[i] == va


def _as_f32(u32: int) -> float:
    return struct.unpack("<f", struct.pack("<I", u32 & 0xFFFFFFFF))[0]


def _ret_n(image: _Image, va: int) -> int | None:
    """``N`` of the first ``ret`` in a linear decode of 4 KiB from ``va``,
    through a leading ``jmp`` thunk; a leading ``jmp [slot]`` pops what
    the kernel import in that thunk slot pops (``azurik_kernel.h``; the
    run free's XPhysicalFree 0xF4F09, Step 2.162h), else is unknown."""
    for ins in _MD.disasm(image.read(va, 4096), va):
        if ins.group(X.X86_GRP_RET):
            return ins.operands[0].imm if ins.operands else 0
        if ins.address == va and ins.mnemonic == "jmp":
            op = ins.operands[0]
            if op.type == X.X86_OP_IMM:
                t = op.imm & 0xFFFFFFFF
                return _ret_n(image, t) if t != va else None
            if op.type == X.X86_OP_MEM and not op.mem.base and not op.mem.index:
                return _kernel_pops(image, op.mem.disp & 0xFFFFFFFF)
    return None


def _kernel_pops(image: _Image, slot: int) -> int | None:
    """The stack bytes the kernel import in thunk ``slot`` pops, or None."""
    from devkit.sim.l2 import kernel_arg_bytes   # deferred: L2 loads the packs
    name = next((t.name for t in parse_kernel_thunks(image.data) if t.thunk_va == slot), None)
    return kernel_arg_bytes().get(name) if name else None


def _changes(v: _Image, p: _Image):
    """In-place edits to vanilla code, and added bytes, as VA ranges."""
    edits, added = [], []
    for s in p.sections:
        old = next((o for o in v.sections
                    if (o["name"], o["vaddr"]) == (s["name"], s["vaddr"])), None)
        same = min(s["raw_size"], old["raw_size"]) if old else 0
        if s["raw_size"] > same:
            added.append((s["vaddr"] + same, s["vaddr"] + s["raw_size"]))
        if old is None or s["name"] in DATA_SECTIONS:
            continue
        a = v.data[old["raw_addr"]:old["raw_addr"] + same]
        b = p.data[s["raw_addr"]:s["raw_addr"] + same]
        for c in range(0, same, 256):
            if a[c:c + 256] == b[c:c + 256]:
                continue
            for i in range(c, min(c + 256, same)):
                if a[i] != b[i]:
                    va = s["vaddr"] + i
                    if edits and edits[-1][1] >= va - 16:  # decode neighbours together
                        edits[-1][1] = va + 1
                    else:
                        edits.append([va, va + 1])
    return edits, added


def check(vanilla: bytes, patched: bytes, float_vas=()) -> list[str]:
    """Return every Level 1 violation in ``patched`` (empty = well-formed);
    ``ValueError`` for a Europe build (:func:`devkit.sim.require_usa`)."""
    require_usa(vanilla)
    require_usa(patched)
    v, p = _Image(vanilla), _Image(patched)
    bounds, sources = _sweep(vanilla)
    targets = sorted(sources)
    edits, added = _changes(v, p)
    bad, insns, shim, seen, rets, calls = [], {}, {}, set(), {}, []

    def bad_float(va, size=4):  # the build wrote a non-finite float here
        raw = p.read(va, size)
        return raw != v.read(va, size) and not (len(raw) == size and math.isfinite(
            struct.unpack("<f" if size == 4 else "<d", raw)[0]))

    def landing_end(va):
        return next((hi for lo, hi in added if lo <= va < hi), None)

    def old_insn(va):  # the vanilla instruction starting at va, if any
        return v.insn(va) if _is_boundary(bounds, va) else None

    for lo, hi in edits:  # in-place edits decode and resync
        va = bounds[bisect_right(bounds, lo) - 1]
        while (ins := p.insn(va)) is not None:
            if va + ins.size > lo:
                insns[va] = ins
            va += ins.size
            if va >= hi:
                if not (_is_boundary(bounds, va) or ins.mnemonic in _ENDS_FLOW):
                    bad.append(f"0x{lo:X}: edit ends mid-instruction at 0x{va:X}")
                break
        else:
            bad.append(f"0x{va:X}: patched code does not decode")
    for va, ins in insns.items():  # vanilla branches the build kept still land on instruction starts
        for t in targets[bisect_right(targets, va):bisect_left(targets, va + ins.size)]:
            if _is_boundary(bounds, t) and any(p.read(a, n) == v.read(a, n) for a, n in sources[t]):
                bad.append(f"0x{t:X}: a vanilla branch lands inside patched {ins.mnemonic}")

    def decode_shim(va, owner):  # owner: the shim entry whose ret N this shares
        out, hi = [], landing_end(va)
        while (va, owner) not in seen:
            seen.add((va, owner))
            ins = p.insn(va)
            if ins is None or va + ins.size > hi:
                bad.append(f"0x{va:X}: shim code runs off its landing area")
                break
            shim[va] = ins.size
            out.append((ins, owner))
            if ins.mnemonic in _ENDS_FLOW:
                break
            va += ins.size
        return out

    work = [(ins, None) for ins in insns.values()]
    while work:
        ins, owner = work.pop()
        a, ops, m = ins.address, ins.operands, ins.mnemonic
        if lacks_on_pentium3(m, ins.groups):
            bad.append(f"0x{a:X}: {m} is not a Pentium III instruction")
        if ins.group(X.X86_GRP_RET):
            n = ops[0].imm if ops else 0
            if owner is not None:
                rets.setdefault(owner, set()).add(n)
            elif landing_end(a) is None:  # a ret written into a vanilla function
                want = _ret_n(v, bounds[bisect_right(bounds, a) - 1])
                if n != want:
                    bad.append(f"0x{a:X}: ret {n} in a function that returns with ret {want}")
        for op in ops:
            if op.type != X.X86_OP_MEM or op.mem.base or op.mem.index:
                continue
            t = op.mem.disp & 0xFFFFFFFF
            if op.size == 16 and t % 16 and m not in _UNALIGNED_OK:
                bad.append(f"0x{a:X}: {m} reads misaligned m128 0x{t:X}")
            if m in _FPU_READS and op.size in (4, 8) and bad_float(t, op.size):
                bad.append(f"0x{a:X}: {m} reads a non-finite float at 0x{t:X}")
        branch = ((ins.group(X.X86_GRP_JUMP) or ins.group(X.X86_GRP_CALL))
                  and ops and ops[0].type == X.X86_OP_IMM)
        old = old_insn(a) if owner is None and not branch else None
        if old is not None and old.mnemonic == m:  # rewritten float immediates
            for o, n in zip(old.operands, ops):
                if (o.type == n.type == X.X86_OP_IMM and o.size == n.size == 4
                        and 1e-6 < abs(_as_f32(o.imm)) < 1e9
                        and not math.isfinite(_as_f32(n.imm))):
                    bad.append(f"0x{a:X}: {m} immediate float is {_as_f32(n.imm)}")
        if not branch:
            continue
        t = ops[0].imm & 0xFFFFFFFF
        s = p.section(t)
        if s is None or s["name"] in DATA_SECTIONS:
            bad.append(f"0x{a:X}: {m} 0x{t:X} lands outside mapped code")
        elif landing_end(t):
            if m == "call" and owner is None:
                calls.append((a, t))
            work += decode_shim(t, t if m == "call" else owner)
        elif not (t in insns if any(lo <= t < hi for lo, hi in edits)
                  else _is_boundary(bounds, t)):
            bad.append(f"0x{a:X}: {m} 0x{t:X} lands mid-instruction")
        elif m == "jmp" and owner is not None:  # a tail call returns with its target's ret N
            rets.setdefault(owner, set()).add(_ret_n(p, t))

    starts = sorted(shim)
    for va, nxt in zip(starts, starts[1:]):
        if va + shim[va] > nxt:
            bad.append(f"0x{nxt:X}: a branch lands mid-instruction in shim code")
    for site, entry in calls:  # ret N parity (the ret 0xA408 class)
        old = old_insn(site)
        if old is None or old.mnemonic != "call":
            want = 0  # it replaced inline code
        elif old.operands[0].type == X.X86_OP_IMM:
            want = _ret_n(v, old.operands[0].imm & 0xFFFFFFFF)
        else:
            want = None  # an indirect call: its callee is unknown
        got = rets.get(entry, set())
        if want is None:
            bad.append(f"0x{site:X}: shim 0x{entry:X} replaced a call whose ret N is unknown")
        elif got != {want}:
            bad.append(f"0x{site:X}: shim 0x{entry:X} returns with ret "
                       f"{sorted(got, key=str)}, the code it replaced needs ret {want}")
    bad += [f"0x{va:X}: float site is not finite" for va in float_vas if bad_float(va)]
    return bad
