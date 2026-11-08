"""``python -m devkit re plan-trampoline VA``: size a hook site before
writing any shim (Modkit's ``azurik-mod plan-trampoline``, ported in Step
4.11e).

Authoring a trampoline patch needs three numbers:

1. **How many bytes does the hook CALL/JMP replace?** (usually 5)
2. **What lives there today?** (the instructions a call-through shim
   must redo)
3. **Are any of those multi-byte instructions that the trampoline must
   preserve intact?** (Splitting a CALL rel32 in half produces a
   silently-broken shim.)

This module answers 1-3 from a VA and the XBE alone, no Ghidra. It uses a
minimal x86 instruction-length decoder of its own (the opcode tables below,
with the ModR/M forms that mid-function code is made of: ``MOV``/``LEA``/ALU
``r/m``, the group opcodes, x87, ``MOVZX``); an opcode outside them, or any
prefix byte, is flagged as unknown so the author checks it in Ghidra or with
``python -m devkit re xbe dis`` rather than ship a guess. The suggested
length is the pack's facts site's size (AzurKit's packs name no bytes: the
facts' sha256 of the site's vanilla bytes stands for Modkit's
``replaced_bytes``).

Public API:

- :func:`plan_trampoline` (``xbe``, ``va``, ``budget=5``) returns a
  :class:`TrampolinePlan` with classified instructions, the suggested
  trampoline length and warnings;
- :func:`format_plan`, the human-readable summary, prints the game's bytes
  only when asked (``--bytes``, a human's, as ``xbe hexdump`` is).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field

from azurkit.core.xbe import resolve_va_to_file
from devkit.re import xbe as xbe_verbs

# ---------------------------------------------------------------------------
# Minimal x86 instruction classifier
# ---------------------------------------------------------------------------
#
# Goal: for each byte offset, return (length, mnemonic).  We don't
# disassemble operands in full, just identify enough to answer
# "can I split my trampoline here?".
#
# Opcode table coverage includes:
#
#   1-byte:  NOP, RET, LEAVE, INT3, HLT, CLD/STD, CLC/STC,
#            PUSH/POP r32, INC/DEC r32
#   Relative branches: JCC short/long, CALL/JMP rel32
#   Immediate forms: MOV r32, imm32; PUSH imm8/imm32; RET imm16;
#            ALU AL, imm8; TEST EAX, imm32
#   ModR/M forms (_MODRM, _MODRM_0F): the opcode, a ModR/M byte, its
#            SIB byte and displacement (32-bit addressing), then any
#            immediate; a group opcode's reg field picks its member
#
# Anything not in the tables, a prefix byte (66, F3, 64 ...) and an
# undefined group member return ``length=0``, which the caller
# treats as "unknown: please inspect by hand".


@dataclass(frozen=True)
class DecodedInstr:
    """One decoded instruction at a specific byte offset."""

    offset: int          # byte offset within the decode window
    length: int          # bytes consumed; 0 = unknown
    mnemonic: str        # short name ("CALL rel32", "MOV r32", etc.)
    raw: bytes

    @property
    def is_unknown(self) -> bool:
        return self.length == 0


_SIMPLE_ONE_BYTE = {
    # Single-byte opcodes we know emit exactly 1 byte.
    0x90: "NOP",                        # NOP
    0xC3: "RET",                        # RET
    0xC9: "LEAVE",                      # LEAVE
    0xCC: "INT3",                       # INT3
    0xF4: "HLT",                        # HLT
    0xFC: "CLD", 0xFD: "STD",           # CLD / STD
    0xF8: "CLC", 0xF9: "STC",           # CLC / STC
}
# PUSH reg: 0x50..0x57 (1 byte). POP reg: 0x58..0x5F.
for _op in range(0x50, 0x58):
    _SIMPLE_ONE_BYTE[_op] = "PUSH r32"
for _op in range(0x58, 0x60):
    _SIMPLE_ONE_BYTE[_op] = "POP r32"
# INC/DEC r32: 0x40..0x4F (1 byte)
for _op in range(0x40, 0x50):
    _SIMPLE_ONE_BYTE[_op] = "INC/DEC r32"

# Opcodes followed by a ModR/M byte (32-bit operands, no prefix): the
# mnemonic, or a group's members by the ModR/M reg field (a missing
# member is undefined), and the immediate's size in bytes.
_ALU = ("ADD", "OR", "ADC", "SBB", "AND", "SUB", "XOR", "CMP")
_SHIFT = ("ROL", "ROR", "RCL", "RCR", "SHL", "SHR", "SAL", "SAR")
_GRP3 = ("TEST", "TEST", "NOT", "NEG", "MUL", "IMUL", "DIV", "IDIV")  # imm: TEST only
_MODRM: dict[int, tuple[str | tuple[str, ...], int]] = {
    **{8 * i + d: (f"{name} r/m", 0) for i, name in enumerate(_ALU) for d in range(4)},
    0x69: ("IMUL r32, r/m32, imm32", 4), 0x6B: ("IMUL r32, r/m32, imm8", 1),
    0x80: (_ALU, 1), 0x81: (_ALU, 4), 0x83: (_ALU, 1),
    0x84: ("TEST r/m, r", 0), 0x85: ("TEST r/m, r", 0),
    0x86: ("XCHG r/m, r", 0), 0x87: ("XCHG r/m, r", 0),
    0x88: ("MOV r/m, r", 0), 0x89: ("MOV r/m, r", 0),
    0x8A: ("MOV r, r/m", 0), 0x8B: ("MOV r, r/m", 0),
    0x8D: ("LEA r32, m", 0), 0x8F: (("POP",), 0),
    0xC0: (_SHIFT, 1), 0xC1: (_SHIFT, 1), 0xC6: (("MOV",), 1), 0xC7: (("MOV",), 4),
    **{op: (_SHIFT, 0) for op in range(0xD0, 0xD4)},
    **{op: (f"x87 {op:02X}", 0) for op in range(0xD8, 0xE0)},
    0xF6: (_GRP3, 1), 0xF7: (_GRP3, 4), 0xFE: (("INC", "DEC"), 0),
    0xFF: (("INC", "DEC", "CALL", "CALL far", "JMP", "JMP far", "PUSH"), 0),
}
_MODRM_0F = {0xAF: "IMUL r32, r/m32", 0xB6: "MOVZX", 0xB7: "MOVZX",
             0xBE: "MOVSX", 0xBF: "MOVSX", **{op: "SETcc" for op in range(0x90, 0xA0)}}


def _modrm_length(data: bytes, at: int) -> int:
    """Bytes the ModR/M byte at ``data[at]`` takes with its SIB byte and
    displacement (32-bit addressing); 0 when they run past ``data``."""
    if at >= len(data):
        return 0
    mod, rm = data[at] >> 6, data[at] & 7
    size = 1 + (0, 1, 4, 0)[mod]
    if mod != 3 and rm == 4:                    # a SIB byte follows
        if at + 1 >= len(data):
            return 0
        size += 1 + (4 if mod == 0 and data[at + 1] & 7 == 5 else 0)
    elif mod == 0 and rm == 5:                  # [disp32]
        size += 4
    return size


def _decode_one(data: bytes, offset: int) -> DecodedInstr:
    """Decode a single x86 instruction starting at ``data[offset]``.

    Returns length=0 for opcodes we haven't classified: the caller uses
    this signal to bail out rather than guess.
    """
    if offset >= len(data):
        return DecodedInstr(offset, 0, "(out of window)", b"")
    b = data[offset]

    # 1-byte opcodes we recognise.
    if b in _SIMPLE_ONE_BYTE:
        return DecodedInstr(offset, 1, _SIMPLE_ONE_BYTE[b],
                            bytes([b]))

    # PUSH imm8 (6A ib)
    if b == 0x6A:
        if offset + 1 < len(data):
            return DecodedInstr(offset, 2, "PUSH imm8",
                                data[offset:offset + 2])
    # PUSH imm32 (68 id)
    if b == 0x68:
        if offset + 4 < len(data):
            return DecodedInstr(offset, 5, "PUSH imm32",
                                data[offset:offset + 5])

    # JMP rel8 / JMP rel32 / JCC rel32
    if b == 0xEB:
        return DecodedInstr(offset, 2, "JMP rel8",
                            data[offset:offset + 2])
    if b == 0xE9:
        return DecodedInstr(offset, 5, "JMP rel32",
                            data[offset:offset + 5])
    if b == 0xE8:
        return DecodedInstr(offset, 5, "CALL rel32",
                            data[offset:offset + 5])
    # JCC rel8 (0x70..0x7F)
    if 0x70 <= b <= 0x7F:
        return DecodedInstr(offset, 2, "JCC rel8",
                            data[offset:offset + 2])
    # JCC rel32 (0F 8X)
    if b == 0x0F and offset + 1 < len(data):
        nxt = data[offset + 1]
        if 0x80 <= nxt <= 0x8F:
            return DecodedInstr(offset, 6, "JCC rel32",
                                data[offset:offset + 6])

    # MOV r32, imm32: 0xB8..0xBF (5 bytes)
    if 0xB8 <= b <= 0xBF:
        if offset + 4 < len(data):
            return DecodedInstr(offset, 5, "MOV r32, imm32",
                                data[offset:offset + 5])

    # RET imm16 (0xC2 iw)
    if b == 0xC2 and offset + 2 < len(data):
        return DecodedInstr(offset, 3, "RET imm16",
                            data[offset:offset + 3])

    # TEST AL, imm8 / AND/OR/XOR AL, imm8 (common 2-byte forms)
    if b in (0xA8, 0x0C, 0x24, 0x34, 0x2C, 0x04):
        return DecodedInstr(offset, 2, "ALU AL, imm8",
                            data[offset:offset + 2])
    # TEST EAX, imm32
    if b == 0xA9 and offset + 4 < len(data):
        return DecodedInstr(offset, 5, "TEST EAX, imm32",
                            data[offset:offset + 5])

    # ModR/M forms (FF 25 / FF 15 [imm32], D9 05 FLD [imm32], ...).
    if b == 0x0F and offset + 1 < len(data) and data[offset + 1] in _MODRM_0F:
        op_len, (name, imm) = 2, (_MODRM_0F[data[offset + 1]], 0)
    elif b in _MODRM:
        op_len, (name, imm) = 1, _MODRM[b]
    else:  # Unknown.  Length=0 signals the caller to stop.
        return DecodedInstr(offset, 0, f"?? ({b:#04x})", bytes([b]))
    at = offset + op_len
    if at < len(data) and not isinstance(name, str):   # a group member
        reg = (data[at] >> 3) & 7
        if reg >= len(name):
            return DecodedInstr(offset, 0, f"?? ({b:#04x} /{reg})",
                                data[offset:at + 1])
        imm = 0 if b in (0xF6, 0xF7) and reg > 1 else imm
        name = f"{name[reg]} r/m" + (f", imm{8 * imm}" if imm else "")
    modrm = _modrm_length(data, at)
    length = op_len + modrm + imm
    if not modrm or offset + length > len(data):
        return DecodedInstr(offset, 0, "(out of window)", data[offset:])
    return DecodedInstr(offset, length, name, data[offset:offset + length])


# ---------------------------------------------------------------------------
# Plan + formatter
# ---------------------------------------------------------------------------


@dataclass
class TrampolinePlan:
    """Authoring report for hooking a specific VA.

    Attributes
    ----------
    va: int
        Hook-site VA.
    file_offset: int
        File offset the VA resolves to.
    budget: int
        The trampoline-length target requested by the caller (5 by
        default = ``CALL rel32``).
    instructions: list[DecodedInstr]
        Decoded instructions starting at ``va``.  The caller walks
        this until the total bytes covers the budget.
    suggested_length: int
        The SMALLEST byte count that fits the budget + ends on an
        instruction boundary.  When the window contains unknowns,
        this falls back to the budget itself with a warning.
    warnings: list[str]
        Human-readable concerns the author should resolve before
        shipping the shim; they name addresses, never bytes.
    preserved_mnemonics: list[str]
        Mnemonics of the instructions the trampoline overwrites:
        shim authors often re-implement them after calling into
        the hook body.
    """

    va: int
    file_offset: int
    budget: int
    instructions: list[DecodedInstr] = field(default_factory=list)
    suggested_length: int = 0
    warnings: list[str] = field(default_factory=list)
    preserved_mnemonics: list[str] = field(default_factory=list)

    @property
    def clean_boundary(self) -> bool:
        return self.suggested_length >= self.budget and not self.warnings


def plan_trampoline(xbe: bytes, va: int, *,
                    budget: int = 5,
                    window: int = 16) -> TrampolinePlan:
    """Produce a :class:`TrampolinePlan` for hooking ``va``.

    Parameters
    ----------
    xbe: bytes
        Vanilla XBE image, of either release.
    va: int
        Virtual address of the hook site: ``xbe``'s own (its section
        headers).
    budget: int
        Target trampoline length.  5 for ``CALL rel32`` (default);
        6 for ``JMP DWORD PTR [imm32]`` thunks.
    window: int
        How many bytes to decode forward from ``va``.  16 is plenty
        for any realistic trampoline + a few instructions of
        context.
    """
    file_off = resolve_va_to_file(xbe, va)
    if file_off is None:
        raise ValueError(f"VA 0x{va:X} has no file bytes in this XBE")
    raw = xbe[file_off:file_off + window]

    instrs: list[DecodedInstr] = []
    off = 0
    while off < len(raw):
        ins = _decode_one(raw, off)
        instrs.append(ins)
        if ins.length == 0:
            break
        off += ins.length

    warnings: list[str] = []
    suggested = 0
    for ins in instrs:
        if ins.length == 0:
            warnings.append(
                f"Unknown opcode at VA 0x{va + ins.offset:X}: the "
                f"decoder can't classify it; inspect it in Ghidra or "
                f"with `xbe dis 0x{va + ins.offset:X}:1` before "
                f"writing the shim.")
            break
        suggested += ins.length
        if suggested >= budget:
            break

    if suggested < budget:
        warnings.append(
            f"Decoded {suggested} bytes before running out of "
            f"known opcodes; consider widening ``window=`` or "
            f"re-confirming the hook site in Ghidra.")

    # Does the boundary align with the budget exactly?  If it
    # overshoots (e.g. budget=5 but we can only carve 6-byte
    # chunks), warn: shims need to NOP-pad unused bytes.
    if suggested > budget:
        warnings.append(
            f"Boundary overshoots budget: carved {suggested} bytes "
            f"to reach {budget}.  Shim must NOP-pad the extra "
            f"{suggested - budget} byte(s) OR use a larger "
            f"trampoline and restore the overshoot in the callback.")

    covered = 0
    preserved = []
    for ins in instrs:
        if ins.length == 0:
            break
        if covered >= budget:
            break
        preserved.append(ins.mnemonic)
        covered += ins.length

    return TrampolinePlan(
        va=va, file_offset=file_off, budget=budget,
        instructions=instrs,
        suggested_length=suggested,
        warnings=warnings,
        preserved_mnemonics=preserved,
    )


def format_plan(plan: TrampolinePlan, show_bytes: bool = False) -> str:
    """Human-readable summary for the CLI; each instruction's bytes (the
    game's) only with ``show_bytes``."""
    lines = [
        f"Trampoline plan for VA 0x{plan.va:08X} "
        f"(file 0x{plan.file_offset:06X}, budget={plan.budget})",
        "",
        "Decoded instructions:",
    ]
    for ins in plan.instructions:
        raw = f"  {ins.raw.hex()}" if show_bytes else ""
        if ins.length == 0:
            lines.append(
                f"  + 0x{plan.va + ins.offset:08X}  ??  UNKNOWN{raw}")
            break
        lines.append(
            f"  + 0x{plan.va + ins.offset:08X}  "
            f"{ins.length} B  {ins.mnemonic:<24}{raw}".rstrip())

    lines.append("")
    lines.append(f"Suggested trampoline length: {plan.suggested_length} B")
    if plan.preserved_mnemonics:
        lines.append(
            "Instructions the trampoline will overwrite "
            "(call-through shims must restore these): "
            + ", ".join(plan.preserved_mnemonics))

    if plan.warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in plan.warnings:
            lines.append(f"  ! {w}")
    elif plan.clean_boundary:
        lines.append("")
        lines.append("[OK] Clean instruction boundary; ready to hook.")

    return "\n".join(lines)


def to_json_dict(plan: TrampolinePlan, show_bytes: bool = False) -> dict:
    """The plan as JSON; an instruction's ``bytes`` only with ``show_bytes``,
    an unknown one's mnemonic ``??`` without them (it names its byte)."""
    return {
        "va": plan.va, "file_offset": plan.file_offset,
        "budget": plan.budget,
        "suggested_length": plan.suggested_length,
        "clean_boundary": plan.clean_boundary,
        "warnings": plan.warnings,
        "preserved_mnemonics": plan.preserved_mnemonics,
        "instructions": [{
            "offset": i.offset, "length": i.length,
            "mnemonic": i.mnemonic if show_bytes or i.length else "??",
            **({"bytes": i.raw.hex()} if show_bytes else {}),
        } for i in plan.instructions],
    }


def main(argv: list[str]) -> int:
    """Exit 0 on a clean boundary, 1 when the plan has warnings (review
    before shipping), 2 on a refusal (no image, a VA with no file bytes)."""
    p = argparse.ArgumentParser(
        prog="python -m devkit re plan-trampoline",
        description="Decode the instructions at a hook site, suggest the smallest byte count that fits the "
                    "trampoline budget and ends on an instruction boundary (the pack's facts site's size), and "
                    "flag the multi-byte instructions the shim must preserve. Exit 0: a clean boundary; 1: "
                    "warnings to review; 2: a refusal.")
    xbe_verbs._source(p)
    p.add_argument("va", type=xbe_verbs._number, help="the hook site's VA, the XBE's own (e.g. 0x5F6E5)")
    p.add_argument("--budget", type=int, default=5,
                   help="the trampoline's size in bytes (5 for CALL rel32, 6 for an FF25 thunk; default 5)")
    p.add_argument("--window", type=int, default=16, help="bytes to decode forward from the VA (default 16)")
    p.add_argument("--bytes", action="store_true",
                   help="print each instruction's bytes too (a human's: they are the game's)")
    args = p.parse_args(argv)
    try:
        data, line = xbe_verbs.load(args.iso or args.xbe, args.region)
        print(line, file=sys.stderr)
        plan = plan_trampoline(data, args.va, budget=args.budget, window=args.window)
    except (OSError, ValueError) as exc:
        print(f"plan-trampoline: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(to_json_dict(plan, args.bytes), indent=2) if args.json else format_plan(plan, args.bytes))
    return 0 if plan.clean_boundary else 1


__all__ = [
    "DecodedInstr",
    "TrampolinePlan",
    "format_plan",
    "plan_trampoline",
]
