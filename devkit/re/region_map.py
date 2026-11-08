"""``python -m devkit re region-map check | find VA [N]``: Europe's address
map, the ``addresses`` and ``absent`` of ``src/azurkit/core/facts.europe.json``,
checked against both vanilla images and extended (Modkit's
``scripts/region_map.py``, ported in Step 4.11e).

USA addresses are the canonical ones: the map takes each USA address the
packs, the facts' functions and the player-model swap name to its Europe
address, or ``absent`` says why Europe has none. Modkit's map gave each
entry its roles and sizes by hand; the facts give only the two addresses,
so :func:`check` reads each entry's role from where its USA address is:

- a facts **site** (a USA site's start): its USA bytes, with the rest of
  the instructions it starts, the address fields in them (absolute
  operands, rel32 branches) moved through the map, equal Europe's, and
  Europe's facts have a site of its size there;
- **code** (a code section's file bytes): :data:`CODE` bytes from it equal
  outside their address fields, cut at either section's file bytes;
- **data** (a data section's file bytes, :data:`devkit.re.xbe.DATA_SECTIONS`):
  :data:`DATA` bytes equal;
- else, or when code or data differ (rebuilt code, a table of addresses,
  BSS, a section's zero-filled tail), a **witness**: an instruction of
  USA's code sections that references the USA address (a direct rel32
  branch, or an absolute operand) whose :data:`WITNESS` bytes from
  :data:`CONTEXT` before it match one place in Europe's image alone,
  address fields as wildcards, and the instruction there references the
  Europe address.

Each entry's address is in a section of the same name in both, and no
address is both mapped and absent. Run on the shipped map it finds
nothing; an entry moved by a few bytes fails it (each role's), but data
that repeats (zeros, a table of one value) can't tell. ``find`` matches N
bytes (24 by default) with code address fields as wildcards; a unique match
is the entry to add to the facts by hand, which ``check`` then verifies.
Both print addresses and counts only, never the game's bytes.
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from bisect import bisect_right

from capstone import CS_ARCH_X86, CS_GRP_BRANCH_RELATIVE, CS_MODE_32, Cs

from azurkit.core import facts, xbe
from azurkit.core.gate import EUROPE, USA
from azurkit.tools.mods.engine import moved
from devkit.re.xbe import DATA_SECTIONS, load

CODE = 16   # bytes a code entry compares (most of Modkit's code entries were 16)
DATA = 8    # bytes a data entry compares (fewer at its section's end)
CONTEXT = 8   # bytes before a witness's instruction that must agree too
WITNESS = 24  # bytes a witness matches, from CONTEXT before it


class Image:
    """One XBE: its bytes, image range and code instruction starts."""

    def __init__(self, data: bytes):
        self.xbe = bytes(data)
        self.sections = xbe.sections(self.xbe)
        self.base = struct.unpack_from("<I", self.xbe, 0x104)[0]
        self.end = self.base + struct.unpack_from("<I", self.xbe, 0x10C)[0]
        self._md = Cs(CS_ARCH_X86, CS_MODE_32)
        self._md.detail = True
        self._starts_of: dict[str, list[int]] = {}
        self._branches: dict[int, list[int]] = {}   # a direct rel32 branch's target -> where each is

    def section(self, va: int) -> xbe.Section | None:
        return next((s for s in self.sections if s.va <= va < s.va + s.vsize), None)

    def read(self, va: int, n: int) -> bytes | None:
        """``n`` file bytes at ``va``, or ``None`` past its section's file data."""
        s = self.section(va)
        if s is None or va + n > s.va + min(s.raw_size, s.vsize):
            return None
        return self.xbe[s.raw + va - s.va:][:n]

    def held(self, va: int) -> int:
        """How many file bytes its section holds from ``va`` on (0: none)."""
        s = self.section(va)
        return max(0, s.va + min(s.raw_size, s.vsize) - va) if s else 0

    def code(self, va: int) -> bool:
        s = self.section(va)
        return s is not None and s.name not in DATA_SECTIONS

    def _starts(self, s: xbe.Section) -> list[int]:
        """Instruction starts in code section ``s``: a linear sweep that
        steps over a byte capstone can't decode (``devkit.re.xbe``'s); it
        notes each direct branch of 5 bytes or more by its target."""
        if s.name in self._starts_of:
            return self._starts_of[s.name]
        code, lite = self.xbe[s.raw:s.raw + min(s.raw_size, s.vsize)], Cs(CS_ARCH_X86, CS_MODE_32)
        out, off = [], 0
        while off < len(code):
            for va, size, mnemonic, ops in lite.disasm_lite(code[off:], s.va + off):
                out.append(va)
                if size >= 5 and mnemonic.startswith(("j", "call")) and ops.startswith("0x"):
                    self._branches.setdefault(int(ops, 16), []).append(va)
                off += size
            off += 1
        self._starts_of[s.name] = out
        return out

    def fields(self, va: int, n: int, partial: bool = False) -> list[tuple[int, str, int]]:
        """``(offset, "abs32" | "rel32", target VA)`` of each address field
        wholly inside ``[va, va + n)`` (or, with ``partial``, overlapping
        it; the offset may then be negative): decoded from the instruction
        that holds ``va``; none in a data section."""
        s = self.section(va)
        if s is None or s.name in DATA_SECTIONS:
            return []
        starts = self._starts(s)
        at = starts[max(bisect_right(starts, va) - 1, 0)]
        out = []
        while at < va + n:
            code = self.read(at, 15) or self.read(at, s.va + min(s.raw_size, s.vsize) - at)
            ins = next(self._md.disasm(code, at, 1), None) if code else None
            if ins is None:
                at += 1
                continue
            for k, kind, target in self._ins_fields(ins):
                if (va - 4 < at + k < va + n) if partial else (va <= at + k and at + k + 4 <= va + n):
                    out.append((at + k - va, kind, target))
            at += ins.size
        return out

    def _ins_fields(self, ins) -> list[tuple[int, str, int]]:
        if CS_GRP_BRANCH_RELATIVE in ins.groups and ins.imm_size == 4:
            return [(ins.imm_offset, "rel32", ins.operands[0].imm & 0xFFFFFFFF)]
        out = []
        for k, size, value in ((ins.disp_offset, ins.disp_size, ins.disp),
                               (ins.imm_offset, ins.imm_size, None)):
            if size != 4 or not k:
                continue
            value = struct.unpack_from("<I", ins.bytes, k)[0] if value is None else value & 0xFFFFFFFF
            if self.base <= value < self.end:
                out.append((k, "abs32", value))
        return out

    def code_fields(self, va: int, code: bytes) -> list[tuple[int, str, int]]:
        """``(offset, kind, target VA)`` of each address field into this
        image that ``code``, decoded at ``va`` (outside it: a carved shim
        body), holds."""
        return [(ins.address - va + k, kind, target)
                for ins in self._md.disasm(code, va)
                for k, kind, target in self._ins_fields(ins)
                if self.base <= target < self.end]

    def insn(self, va: int):
        """The instruction at ``va``, or ``None``."""
        code = self.read(va, 15) or self.read(va, self.held(va))
        return next(self._md.disasm(code, va, 1), None) if code else None

    def refs(self, va: int) -> set[int]:
        """The VAs the instruction at ``va`` references."""
        ins = self.insn(va)
        return {t for _, _, t in self._ins_fields(ins)} if ins else set()

    def referrers(self, target: int) -> list[int]:
        """The instructions of the code sections (the sweep's) that reference
        ``target``: a direct rel32 branch to it, or an absolute operand (only
        the instructions whose bytes hold it are decoded)."""
        needle, out = struct.pack("<I", target), set()
        for s in self.sections:
            if s.name in DATA_SECTIONS:
                continue
            code, starts = self.xbe[s.raw:s.raw + min(s.raw_size, s.vsize)], self._starts(s)
            at = code.find(needle)
            while at >= 0:
                start = starts[max(bisect_right(starts, s.va + at) - 1, 0)]   # the instruction holding it
                if target in self.refs(start):
                    out.add(start)
                at = code.find(needle, at + 1)
        return sorted(out | set(self._branches.get(target, ())))

    def cover(self, va: int, n: int) -> int:
        """``n``, or in code the bytes from ``va`` to the end of the last
        instruction that starts inside ``[va, va + n)`` (a facts site holds
        only the bytes a pack changes, which can stop inside an operand)."""
        s = self.section(va)
        if s is None or s.name in DATA_SECTIONS:
            return n
        starts = self._starts(s)
        last = starts[max(bisect_right(starts, va + n - 1) - 1, 0)]
        ins = self.insn(last)
        return max(n, last + ins.size - va) if ins and last >= va else n

    def masked(self, va: int, n: int, usa: Image | None = None, usa_va: int = 0) -> bytes | None:
        """``n`` bytes at ``va`` with the address fields zeroed: this
        image's own, or (``usa``) those of ``usa``'s bytes at ``usa_va``."""
        data = self.read(va, n)
        if data is None:
            return None
        out = bytearray(data)
        for k, _, _ in (usa or self).fields(usa_va if usa else va, n, partial=True):
            out[max(k, 0):k + 4] = bytes(min(k + 4, 4))
        return bytes(out[:n])


def _site(usa: Image, eu: Image, known: facts.Facts, usa_va: int, eu_va: int, size: int) -> str | None:
    """Why a facts site's USA bytes (and the rest of the instructions it
    starts), moved through the map, aren't Europe's (``None``: they are)."""
    if (site := known.sites.get(eu_va)) is None or site.size != size:
        return f"site: Europe's facts have no {size}-byte site there"
    n = usa.cover(usa_va, size)
    have, want = usa.read(usa_va, n), eu.read(eu_va, n)
    if have is None or want is None:
        return f"site: no {n} file bytes"
    fields = usa.fields(usa_va, n)
    try:
        have = moved(known, have, usa_va, eu_va, [k for k, kind, _ in fields if kind == "abs32"],
                     [k for k, kind, _ in fields if kind == "rel32"])
    except LookupError as exc:
        return f"site: {exc}"
    return None if have == want else f"site: the {n} bytes differ"


def _witnessed(usa: Image, eu: Image, usa_va: int, eu_va: int) -> bool:
    """Whether an instruction referencing ``usa_va`` has a Europe twin that
    references ``eu_va``: the one place in Europe's image whose
    :data:`WITNESS` bytes match those from :data:`CONTEXT` bytes before it,
    address fields as wildcards (alike instructions referencing a
    neighbouring address match too, so the match must be unique)."""
    for ru in usa.referrers(usa_va):
        if usa.read(ru - CONTEXT, WITNESS) is None:
            continue
        hits = find(usa, eu, ru - CONTEXT, WITNESS, partial=True)
        if len(hits) == 1 and eu_va in eu.refs(hits[0] + CONTEXT):
            return True
    return False


def check(usa: Image, eu: Image, known: facts.Facts | None = None) -> list[str]:
    """Every entry of Europe's map (``known``'s, Europe's facts by default)
    that doesn't hold on the two images, one line each, by the role its
    USA address gives it (the module's list)."""
    known = known or facts.of(EUROPE)
    sites = facts.of(USA).sites
    problems = [f"0x{va:08X}: both mapped and absent" for va in sorted(known.addresses.keys() & known.absent.keys())]
    for usa_va, eu_va in sorted(known.addresses.items()):
        where = f"0x{usa_va:08X} -> 0x{eu_va:08X}"
        a, b = usa.section(usa_va), eu.section(eu_va)
        if a is None or b is None or a.name != b.name:
            problems.append(f"{where}: in {a.name if a else 'no section'}, Europe's in {b.name if b else 'none'}")
            continue
        if usa_va in sites:
            why = _site(usa, eu, known, usa_va, eu_va, sites[usa_va].size)
        else:
            n = min(usa.held(usa_va), eu.held(eu_va), CODE if usa.code(usa_va) else DATA)
            if n == 0:
                why = "zero-filled"
            elif usa.code(usa_va):
                why = None if usa.masked(usa_va, n) == eu.masked(eu_va, n, usa, usa_va) else f"code: {n} bytes differ"
            else:
                why = None if usa.read(usa_va, n) == eu.read(eu_va, n) else f"data: {n} bytes differ"
            if why and _witnessed(usa, eu, usa_va, eu_va):
                why = None   # rebuilt code, a table that differs or BSS: an instruction witnesses it
            elif why:
                why += " and no instruction witnesses it"
        if why:
            problems.append(f"{where}: {why}")
    return problems


def find(usa: Image, eu: Image, va: int, n: int = 24, partial: bool = False) -> list[int]:
    """Europe VAs whose ``n`` bytes match the USA ones at ``va``, code
    address fields as wildcards (with ``partial``, those the window's ends
    cut too)."""
    data = usa.read(va, n)
    if data is None:
        raise ValueError(f"0x{va:08X} has no {n} USA file bytes")
    wild = {k + i for k, _, _ in usa.fields(va, n, partial) for i in range(4)}
    pattern = re.compile(b"".join(b"." if i in wild else re.escape(data[i:i + 1])
                                  for i in range(n)), re.DOTALL)
    out = []
    for s in eu.sections:
        raw = eu.xbe[s.raw:s.raw + min(s.raw_size, s.vsize)]
        out += [s.va + m.start() for m in pattern.finditer(raw)]
    return out


def images() -> tuple[Image, Image]:
    """Both releases' vanilla XBEs (their images: ``devkit.re.xbe.load``'s)."""
    return Image(load(region=USA.name)[0]), Image(load(region=EUROPE.name)[0])


def main(argv: list[str]) -> int:
    """``check``: exit 1 naming each entry that doesn't hold; ``find``: exit
    0 on one match, 1 on none or several; no image: one line and exit 2."""
    ap = argparse.ArgumentParser(prog="python -m devkit re region-map", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="check every entry of the map against both vanilla images")
    f = sub.add_parser("find", help="the Europe VAs holding a USA VA's bytes")
    f.add_argument("va", type=lambda v: int(v, 0))
    f.add_argument("n", type=int, nargs="?", default=24)
    args = ap.parse_args(argv)
    try:
        usa, eu = images()
        if args.cmd == "check":
            problems = check(usa, eu)
            print("\n".join(problems) or f"{len(facts.of(EUROPE).addresses)} entries hold")
            return 1 if problems else 0
        hits = find(usa, eu, args.va, args.n)
    except (OSError, ValueError) as exc:
        print(f"region-map: {exc}", file=sys.stderr)
        return 2
    print("\n".join(f"0x{h:08X}" for h in hits) or "no match")
    print(f"{len(hits)} match(es)", file=sys.stderr)
    return 0 if len(hits) == 1 else 1
