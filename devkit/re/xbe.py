"""``python -m devkit re xbe VERB [ARGS ...]``: offline reads of a
``default.xbe``, with no Ghidra (Modkit's ``azurik-mod xbe``, ported in Step
4.11c): where an address is, the values, strings and floats it holds, the
instructions and data dwords that hold it, and listings of its code (capstone).

A verb reads the XBE of ``--iso`` or ``--xbe`` (either takes an Xbox image or
a raw XBE), else the image of ``--region``'s release (USA's when found, else
the only one found: :func:`azurkit.core.gate.find`), whose ``default.xbe``
must be that release's vanilla one. It names what it read, the release and
the XBE's ``sha256[:12]`` on stderr; stdout is the verb's (``--json`` for a
machine). Addresses in and out are that XBE's own, mapped through its own
section table, so an appended section (``SHIMS``) and a section's zero-filled
tail map right (AZ-140). A listing names each address its release's facts
know: their functions and the kernel imports' thunk slots (:func:`names_for`).

Code is every section but the data ones (:data:`DATA_SECTIONS`), told by
name, never by flags (``.rdata`` is flagged executable), decoded by a linear
sweep that steps over a byte capstone can't decode, so data inside code (a
jump table) can show as instructions. No verb prints the game's bytes but
``hexdump``, a human's: an agent reads values with ``read`` and code with
``dis`` and ``fn``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import sys
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

from capstone import CS_ARCH_X86, CS_MODE_32, Cs
from capstone import x86 as X

from azurkit.core import facts, gate, iso, xbe
from azurkit.core.gate import RELEASES, Release
from azurkit.core.xbe import Section

DATA_SECTIONS = frozenset({".rdata", ".data", "BINKDATA", "DOLBY", "$$XTIMAGE"})
STRING_SECTIONS = (".rdata", ".data")   # where the game keeps its string literals
_NOT_ON_PENTIUM3 = frozenset({
    X.X86_GRP_SSE2, X.X86_GRP_SSE3, X.X86_GRP_SSSE3, X.X86_GRP_SSE41, X.X86_GRP_SSE42, X.X86_GRP_SSE4A,
    X.X86_GRP_AVX, X.X86_GRP_AVX2, X.X86_GRP_AVX512, X.X86_GRP_FMA, X.X86_GRP_FMA4, X.X86_GRP_F16C, X.X86_GRP_XOP,
    X.X86_GRP_3DNOW, X.X86_GRP_BMI, X.X86_GRP_BMI2, X.X86_GRP_TBM, X.X86_GRP_ADX, X.X86_GRP_AES, X.X86_GRP_PCLMUL,
    X.X86_GRP_SHA})
_NOT_ON_PENTIUM3_MNEMONICS = frozenset({"fisttp", "popcnt", "lzcnt", "movbe", "rdrand", "rdseed"})   # ungrouped
_PATH_ENDS = frozenset({"ret", "retf", "iret", "iretd", "jmp", "ljmp", "hlt", "int3", "ud2"})
_READS = {"f32": "<f", "f64": "<d", "i32": "<i", "u32": "<I", "u16": "<H", "u8": "<B", "ptr": "<I"}
_TEXT = frozenset(range(0x20, 0x7F)) | {0x09, 0x0A, 0x0D}
_PRINTABLE = re.compile(rb"[\x20-\x7E]+")
_HEX = re.compile(r"0x[0-9a-fA-F]+")
_C_STRING_MAX = _VTABLE_MAX = 1024
_LITE = Cs(CS_ARCH_X86, CS_MODE_32)
_DETAIL = Cs(CS_ARCH_X86, CS_MODE_32)
_DETAIL.detail = True


# The XBE: where it comes from, its release and its names

def load(path: str | None = None, region: str | None = None) -> tuple[bytes, str]:
    """The XBE to read and the line naming it, its release and its
    ``sha256[:12]``. ``path`` is an Xbox image (its ``default.xbe`` is read)
    or a raw XBE; with none, the image of ``region``'s release (``"usa"`` or
    ``"europe"``; ``None``: USA's when found, else the only one found), whose
    ``default.xbe`` must be that release's vanilla one. ``ValueError`` (an
    ``OSError`` for a file that can't be read) says why not, as it does for a
    ``region`` the XBE isn't."""
    want = next((r for r in RELEASES if r.name == region), None)
    if region and want is None:
        raise ValueError(f"no release {region!r}: {' or '.join(r.name for r in RELEASES)}")
    found = None
    if path:
        name, data = Path(path).name, _read(Path(path))
    else:
        releases = (want,) if want else RELEASES
        if (found := next(((r, p) for r in releases if (p := gate.find(r))), None)) is None:
            raise ValueError(f"no image: {gate.missing(releases[0])}, or pass --iso PATH or --xbe PATH")
        name, data = found[1].name, _read(found[1])
    sha = hashlib.sha256(data).hexdigest()
    if found and sha != facts.of(found[0]).sha256:
        raise ValueError(f"{found[1]} holds no vanilla {found[0].label} default.xbe")
    xbe.sections(data)   # refuses what isn't an XBE, or a table that runs off it
    release = release_of(data)
    what = ("neither release" if release is None else f"the {release.label} release"
            if sha == facts.of(release).sha256 else f"a build of the {release.label} release")
    if want and release != want:
        raise ValueError(f"--region {region}, but {name} is {what}")
    return data, f"{name}: {what} (default.xbe sha256 {sha[:12]})"


def _read(path: Path) -> bytes:
    with path.open("rb") as f:
        if f.read(4) == xbe.MAGIC:
            return path.read_bytes()
    with iso.Reader(path) as r:
        try:
            return r.read("default.xbe")
        except FileNotFoundError:
            raise ValueError(f"{path} holds no default.xbe") from None


def release_of(data: bytes) -> Release | None:
    """The release whose addresses the XBE ``data`` has, by the kernel thunk
    table's address its header holds (a build keeps it); ``None``: neither's."""
    if bytes(data[:4]) != xbe.MAGIC or len(data) < 0x15C:
        return None
    thunks = int.from_bytes(bytes(data[0x158:0x15C]), "little") ^ facts.THUNK_KEY
    return next((r for r in RELEASES if facts.of(r).thunks == thunks), None)


def names_for(data: bytes) -> dict[int, str]:
    """The names at the XBE's own addresses: its release's facts' functions
    and its kernel imports (by their slots in the thunk table); none for an
    XBE of neither release. Until the Ghidra side comes (Step 4.11d) these
    are all the names there are."""
    if (release := release_of(data)) is None:
        return {}
    known = facts.of(release)
    names = {k.slot: k.name for k in known.kernel.values() if k.slot is not None}
    return names | {f.va: f.name for f in known.functions.values()}


def operand_names(operands: str, names: dict[int, str]) -> str | None:
    """The names of the addresses an instruction's operand text holds
    (``call 0xcb2a0``, ``fld dword ptr [0x1980a8]``), ``", "``-joined, or
    ``None`` when it holds no named one."""
    found = (names.get(int(h, 16)) for h in _HEX.findall(operands))
    return ", ".join(dict.fromkeys(n for n in found if n)) or None


# Sections and addresses

def _mapped(s: Section) -> int:
    """How many of the section's bytes the file holds and the loader maps."""
    return min(s.raw_size, s.vsize)


def section_at(table: Iterable[Section], value: int, is_va: bool = True) -> tuple[Section | None, int]:
    """The section that maps ``value`` and how far into it ``value`` is: a VA
    up to the section's virtual size, a file offset only within the bytes the
    loader maps; ``(None, 0)`` when none does."""
    for s in table:
        delta = value - (s.va if is_va else s.raw)
        if 0 <= delta < (s.vsize if is_va else _mapped(s)):
            return s, delta
    return None, 0


def _seen(data: bytes, s: Section, delta: int, n: int) -> bytes:
    """The ``n`` bytes the game sees ``delta`` into ``s``, cut at its end;
    zeros past its file bytes (the loader's zero-fill)."""
    n = min(n, s.vsize - delta)
    raw = data[s.raw + delta:s.raw + min(s.raw_size, delta + n)]
    return raw + bytes(n - len(raw))


@dataclass(frozen=True)
class Address:
    value: int
    kind: str                  # what value was read as: "va" or "file"
    va: int | None             # None: no section maps it
    file_offset: int | None    # None: past its section's file bytes (zero-filled at load), or past the file
    section: str | None

    def __str__(self) -> str:
        va = f"VA 0x{self.va:08X}" if self.va is not None else "no VA"
        at = f"file 0x{self.file_offset:06X}" if self.file_offset is not None else "no file bytes"
        return f"{va}  {at}  {self.section or 'no section'}  (read as a {'VA' if self.kind == 'va' else 'file offset'})"


def address(data: bytes, value: int, kind: str | None = None) -> Address:
    """``value`` as a VA and a file offset, through the XBE's own sections:
    a VA when it is at least the image's base address (0x10000), else a file
    offset, unless ``kind`` (``"va"`` or ``"file"``) says."""
    table = xbe.sections(data)
    kind = kind or ("va" if value >= struct.unpack_from("<I", data, 0x104)[0] else "file")
    s, delta = section_at(table, value, kind == "va")
    if kind == "va":
        va, at = (value if s else None), (s.raw + delta if s and delta < s.raw_size else None)
    else:
        va, at = (s.va + delta if s else None), (value if 0 <= value < len(data) else None)
    return Address(value, kind, va, at, s.name if s else None)


@dataclass(frozen=True)
class Row:
    """Up to 16 bytes at ``va``; ``file_offset`` is ``None`` past the
    section's file bytes, which read as the loader's zeros."""
    va: int
    file_offset: int | None
    raw: bytes

    def __str__(self) -> str:
        hexed = [" ".join(f"{b:02x}" for b in part) for part in (self.raw[:8], self.raw[8:])]
        text = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in self.raw)
        where = "(zero-filled)" if self.file_offset is None else f"(file 0x{self.file_offset:06X})"
        return f"0x{self.va:08X}  {where}  {hexed[0]:<23}  {hexed[1]:<23}  |{text}|"


def hexdump(data: bytes, at: int, length: int = 64, is_va: bool = True) -> list[Row]:
    """``length`` bytes from ``at`` (a VA, else a file offset) in 16-byte
    rows, stopping at the end of the section that maps it; ``[]`` when none does."""
    s, delta = section_at(xbe.sections(data), at, is_va)
    if s is None:
        return []
    end = min(delta + length, s.vsize if is_va else _mapped(s))
    return [Row(s.va + d, s.raw + d if d < s.raw_size else None, _seen(data, s, d, min(16, end - d)))
            for d in range(delta, end, 16)]


# Scans of the data: floats, strings, typed values, vtables and the dwords that hold an address

@dataclass(frozen=True)
class Float:
    va: int
    file_offset: int
    width: int      # 4: a float32, 8: a double
    value: float


def find_floats(data: bytes, lo: float, hi: float, widths: tuple[int, ...] = (4, 8)) -> list[Float]:
    """Each float32 and double in ``.rdata`` whose value lies in [lo, hi],
    at every byte offset (the compiler packs them unaligned), but zero
    (``.rdata``'s zero runs would give thousands), NaNs and infinities."""
    s = next((s for s in xbe.sections(data) if s.name == ".rdata"), None)
    if s is None:
        return []
    end = min(s.raw + _mapped(s), len(data))
    hits = []
    for width in widths:
        fmt = "<f" if width == 4 else "<d"
        for off in range(s.raw, end - width + 1):
            (value,) = struct.unpack_from(fmt, data, off)
            if value and math.isfinite(value) and lo <= value <= hi:
                hits.append(Float(s.va + off - s.raw, off, width, value))
    return hits


@dataclass(frozen=True)
class String:
    va: int
    file_offset: int
    text: str


def find_strings(data: bytes, pattern: str, *, regex: bool = False, ignore_case: bool = False, min_len: int = 4,
                 limit: int = 200) -> list[String]:
    """At most ``limit`` runs of printable ASCII in ``.rdata`` and ``.data``,
    each ``min_len`` or more characters long, that hold ``pattern`` (a
    substring, or with ``regex`` a Python regex searched for; one that
    doesn't compile is a ValueError: re.compile raises OverflowError for a
    repeat count past its limit and RecursionError for nesting too deep for
    its parser, besides re.error)."""
    try:
        rx = re.compile(pattern if regex else re.escape(pattern), re.IGNORECASE if ignore_case else 0)
    except (re.error, OverflowError, RecursionError) as exc:
        raise ValueError(f"--regex {pattern!r}: {exc}") from None
    hits: list[String] = []
    for s in xbe.sections(data):
        if s.name not in STRING_SECTIONS:
            continue
        for m in _PRINTABLE.finditer(data, s.raw, s.raw + _mapped(s)):
            text = m.group().decode("ascii")
            if len(text) >= min_len and rx.search(text):
                if len(hits) >= limit:
                    return hits
                hits.append(String(s.va + m.start() - s.raw, m.start(), text))
    return hits


@dataclass(frozen=True)
class Read:
    """One value at ``va``: a number, a C string (``cstr``; ``None`` where no
    printable NUL-terminated one starts), or ``None`` where the loader
    zero-fills (``bss``: set only at run time). A pointer (``ptr``) also says
    what it points at: the ``name`` :func:`names_for` gives it, else the C
    ``string`` there (in ``.rdata`` or ``.data``, of 4 or more characters),
    and the ``section`` holding it (``None``: none maps it, as for a null)."""
    va: int
    value: int | float | str | None
    name: str | None = None
    string: str | None = None
    section: str | None = None
    bss: bool = False


def read_values(data: bytes, va: int, kind: str, count: int = 1, names: dict[int, str] | None = None) -> list[Read]:
    """``count`` values of ``kind`` (``f32 f64 i32 u32 u16 u8 ptr cstr``) one
    after another from ``va``, as the game sees them, stopping at the end of
    ``va``'s section. ``cstr`` reads ``count`` strings in a row, each from the
    first non-NUL byte after the last, and stops at one that isn't printable.
    ``ValueError`` when no section maps ``va``, its section ends before one
    whole value, or a ``cstr`` is asked for outside ``.rdata`` and ``.data``
    (code bytes are no string)."""
    table = xbe.sections(data)
    s, delta = section_at(table, va)
    if s is None:
        raise ValueError(f"0x{va:X} is in no section")
    if kind == "cstr":
        if s.name not in STRING_SECTIONS:
            raise ValueError(f"0x{va:X} is in {s.name}: C strings are read only in {' and '.join(STRING_SECTIONS)}")
        return _strings(data, s, delta, count)
    fmt = _READS[kind]
    width = struct.calcsize(fmt)
    raw = _seen(data, s, delta, width * count)
    if len(raw) < width:
        raise ValueError(f"no whole {kind} at 0x{va:X}: {s.name} ends first")
    out = []
    for k in range(len(raw) // width):
        if delta + k * width >= s.raw_size:
            out.append(Read(va + k * width, None, bss=True))
            continue
        (value,) = struct.unpack_from(fmt, raw, k * width)
        out.append(Read(va + k * width, value, **(_pointee(data, table, value, names or {}) if kind == "ptr" else {})))
    return out


def _c_string(data: bytes, s: Section, delta: int) -> str | None:
    """The printable NUL-terminated string ``delta`` into ``s``'s file bytes, or ``None``."""
    start = s.raw + delta
    nul = data.find(b"\0", start, s.raw + min(_mapped(s), delta + _C_STRING_MAX + 1))
    if nul < 0 or not _TEXT.issuperset(data[start:nul]):
        return None
    return data[start:nul].decode("ascii")


def _pointee(data: bytes, table: tuple[Section, ...], target: int, names: dict[int, str]) -> dict:
    s, delta = section_at(table, target)
    name = names.get(target)
    string = (_c_string(data, s, delta) if name is None and s is not None and s.name in STRING_SECTIONS
              and delta < s.raw_size else None)
    return {"name": name, "string": string if string and len(string) >= 4 else None,
            "section": s.name if s is not None else None}


def _strings(data: bytes, s: Section, delta: int, count: int) -> list[Read]:
    out: list[Read] = []
    while len(out) < count and delta < s.vsize:
        if delta >= s.raw_size:
            out.append(Read(s.va + delta, None, bss=True))
            break
        text = _c_string(data, s, delta)
        out.append(Read(s.va + delta, text))
        if text is None:
            break
        delta += len(text) + 1
        while delta < _mapped(s) and data[s.raw + delta] == 0:
            delta += 1
    return out


def vtable(data: bytes, va: int, slots: int | None = None, names: dict[int, str] | None = None) -> list[Read]:
    """A vtable's slots from ``va``, each a ``ptr`` :class:`Read`: ``slots``
    of them (fewer where the section ends), else each up to the first that
    holds no address in a code section or whose own VA an instruction holds
    (:func:`va_refs`: the next vtable, which its constructor stores; the
    level camera's 0x19C3D8 has 55 slots, then the camera base's +0xD8 one),
    at most 1024."""
    reads = read_values(data, va, "ptr", slots or _VTABLE_MAX, names)
    if slots is None:
        reads = reads[:next((k for k, r in enumerate(reads) if r.section is None or r.section in DATA_SECTIONS
                             or k and va_refs(data, r.va, None)), len(reads))]
    return reads


def data_refs(data: bytes, target: int) -> list[tuple[int, str]]:
    """``(va, section)`` of each 4-aligned dword in a data section whose file
    bytes hold ``target``: a vtable's or a pointer table's slot, a struct's
    pointer field. A zero-filled tail holds none."""
    needle = struct.pack("<I", target & 0xFFFFFFFF)
    out = []
    for s in xbe.sections(data):
        if s.name in DATA_SECTIONS:
            at = data.find(needle, s.raw, s.raw + _mapped(s))
            while at >= 0:
                if (s.va + at - s.raw) % 4 == 0:
                    out.append((s.va + at - s.raw, s.name))
                at = data.find(needle, at + 1, s.raw + _mapped(s))
    return out


# The code (capstone)

@dataclass(frozen=True)
class Insn:
    va: int
    mnemonic: str
    operands: str

    def __str__(self) -> str:
        return f"0x{self.va:08X}  {self.mnemonic} {self.operands}".rstrip()


@dataclass(frozen=True)
class VaRef:
    """An instruction that holds a VA as an absolute operand."""
    va: int
    file_offset: int
    mnemonic: str
    operands: str


def _code_sections(data: bytes, section: str | None) -> list[Section]:
    """The code sections, or only the one named ``section``."""
    found = [s for s in xbe.sections(data) if s.name not in DATA_SECTIONS and section in (None, s.name)]
    if section is not None and not found:
        raise ValueError(f"no code section named {section!r}")
    return found


def _sweep(data: bytes, section: str | None, detail: bool = False) -> Iterator:
    """A linear sweep of the code sections (or the one named ``section``),
    stepping over a byte capstone can't decode; with ``detail`` it yields
    ``(Insn, groups)``."""
    for s in _code_sections(data, section):
        code, off = data[s.raw:s.raw + _mapped(s)], 0
        while off < len(code):
            if detail:
                for ins in _DETAIL.disasm(code[off:], s.va + off):
                    yield Insn(ins.address, ins.mnemonic, ins.op_str), ins.groups
                    off += ins.size
            else:
                for va, size, mnemonic, ops in _LITE.disasm_lite(code[off:], s.va + off):
                    yield Insn(va, mnemonic, ops)
                    off += size
            off += 1


def _scoped(data: bytes, section: str | None, span: tuple[int, int] | None, fn: int | None) -> Iterator[Insn]:
    """The sweep's instructions, or with ``fn`` those of the function at
    ``fn`` (:func:`function`); with ``span`` only those at ``lo <= VA < hi``."""
    lo, hi = span or (0, 1 << 32)
    return (i for i in (function(data, fn) if fn is not None else _sweep(data, section)) if lo <= i.va < hi)


def search(data: bytes, mnemonic: str | None = None, operand: str | None = None, section: str | None = None, *,
           span: tuple[int, int] | None = None, fn: int | None = None) -> list[Insn]:
    """The instructions whose mnemonic is ``mnemonic`` and whose operand text
    holds ``operand`` (both case-blind; one or both), in :func:`_scoped`'s scope."""
    if not mnemonic and not operand:
        raise ValueError("give a mnemonic, an operand substring or both")
    m, o = (mnemonic or "").lower(), (operand or "").lower()
    return [i for i in _scoped(data, section, span, fn) if (not m or i.mnemonic == m) and o in i.operands]


def calls(data: bytes, target: int | None = None, section: str | None = None, *,
          span: tuple[int, int] | None = None, fn: int | None = None) -> list[tuple[int, int]]:
    """``(site, callee)`` of each direct ``call`` into code, or only those to
    ``target``, in :func:`_scoped`'s scope."""
    code = [(s.va, s.va + _mapped(s)) for s in _code_sections(data, None)]
    out = []
    for i in _scoped(data, section, span, fn):
        if i.mnemonic == "call" and i.operands.startswith("0x"):
            callee = int(i.operands, 16)
            if callee == target if target is not None else any(lo <= callee < hi for lo, hi in code):
                out.append((i.va, callee))
    return out


def va_refs(data: bytes, target: int, section: str | None = ".text") -> list[VaRef]:
    """Each instruction in ``section`` (``None``: every code section) that
    holds ``target`` as an absolute 32-bit operand: an immediate (``push``,
    ``mov r32``, ``mov dword ptr [esi]``, ``cmp`` ...) or a memory
    displacement (``[0x...]``, ``[eax*4 + 0x...]``, ``jmp dword ptr [0x...]``).
    Capstone's imm or disp must equal ``target`` where the instruction encodes
    it, so a relative call or jump (an offset) never counts (AZ-219): direct
    calls are :func:`calls`'. Only the instructions whose bytes hold the VA are
    decoded in detail."""
    target &= 0xFFFFFFFF
    needle = struct.pack("<I", target)
    out = []
    for s in _code_sections(data, section):
        code = data[s.raw:s.raw + _mapped(s)]
        if needle not in code:
            continue
        off = 0
        while off < len(code):
            for va, size, _, _ in _LITE.disasm_lite(code[off:], s.va + off):
                raw = code[off:off + size]
                if needle in raw:
                    ins = next(_DETAIL.disasm(raw, va, count=1))
                    if _holds(ins, target, raw, needle):
                        out.append(VaRef(va, s.raw + off, ins.mnemonic, ins.op_str))
                off += size
            off += 1
    return out


def _holds(ins, target: int, raw: bytes, needle: bytes) -> bool:
    """Whether a detailed instruction encodes ``target`` as its immediate or its displacement."""
    for op in ins.operands:
        if (op.type == X.X86_OP_IMM and op.imm & 0xFFFFFFFF == target
                and raw[ins.imm_offset:ins.imm_offset + 4] == needle):
            return True
        if (op.type == X.X86_OP_MEM and op.mem.disp & 0xFFFFFFFF == target
                and raw[ins.disp_offset:ins.disp_offset + 4] == needle):
            return True
    return False


def _holding(data: bytes, va: int) -> tuple[bytes, int]:
    """The file bytes of the section whose file bytes hold ``va``, and its VA."""
    for s in xbe.sections(data):
        if s.va <= va < s.va + _mapped(s):
            return data[s.raw:s.raw + _mapped(s)], s.va
    raise ValueError(f"0x{va:X} is in no section's file bytes (outside the image, or a zero-filled tail)")


def _one(code: bytes, base: int, off: int) -> tuple[Insn, int] | None:
    """The instruction ``off`` into ``code`` and its size, or ``None``."""
    for _, size, mnemonic, ops in _LITE.disasm_lite(code[off:off + 15], base + off, 1):
        return Insn(base + off, mnemonic, ops), size
    return None


def listing(data: bytes, va: int, count: int) -> list[Insn]:
    """``count`` instructions from ``va`` on, in the section holding it,
    stopping early at its end; a byte capstone can't decode (a cut-off
    instruction too) is one ``(bad)``."""
    code, base = _holding(data, va)
    out, off = [], va - base
    while len(out) < count and off < len(code):
        ins, size = _one(code, base, off) or (Insn(base + off, "(bad)", ""), 1)
        out.append(ins)
        off += size
    return out


def function(data: bytes, va: int) -> list[Insn]:
    """The instructions ``va`` reaches without a call, in address order: each
    direct branch's target in the section is followed, and a path ends at a
    ``ret``, a ``jmp`` (its direct target queued), ``int3``, ``hlt``, ``ud2``
    or a ``(bad)`` byte. A heuristic: a tail ``jmp`` into another function is
    followed too, and an indirect ``jmp`` (a switch's table) is not; Ghidra's
    function body is the authority."""
    code, base = _holding(data, va)
    seen: dict[int, Insn] = {}
    todo = [va]
    while todo:
        at = todo.pop()
        while at not in seen and base <= at < base + len(code):
            ins, size = _one(code, base, at - base) or (Insn(at, "(bad)", ""), 0)
            seen[at] = ins
            if ins.mnemonic.startswith(("j", "loop")) and ins.operands.startswith("0x"):
                todo.append(int(ins.operands, 16))
            if size == 0 or ins.mnemonic in _PATH_ENDS:
                break
            at += size
    return [seen[at] for at in sorted(seen)]


def lacks_on_pentium3(mnemonic: str, groups: Iterable[int]) -> bool:
    """Whether the Xbox's Pentium III lacks an instruction of this mnemonic
    and these capstone groups: SSE2 and later, 3DNow! and the ungrouped later
    ones (AZ-021); ``pause`` runs there as a NOP. Unicorn runs them all."""
    return mnemonic != "pause" and (mnemonic in _NOT_ON_PENTIUM3_MNEMONICS
                                    or bool(_NOT_ON_PENTIUM3.intersection(groups)))


def not_on_pentium3(data: bytes, section: str | None = None) -> list[Insn]:
    """The instructions in the code sections (or ``section``) a Pentium III can't run."""
    return [i for i, groups in _sweep(data, section, detail=True) if lacks_on_pentium3(i.mnemonic, groups)]


# The verb

DESCRIPTION = """\
Offline reads of a default.xbe. A verb reads the XBE of --iso or --xbe (either takes an Xbox image or a raw XBE),
else the image of --region's release (USA's when found, else the only one found), and names it, its release and its
sha256[:12] on stderr. Addresses in and out are that XBE's own; a listing names what the release's facts know."""
RECIPES = """\
recipes (VAs are the XBE's own; --iso, --xbe, --region and --json go before the verb or after it):
  addr 0x85700                     a VA's file offset and section (addr 0x75700 --from file: back)
  sections                         the section table
  read 0x1980A8 --as f32           a value at a VA, never its bytes (ptr names its target; cstr a string)
  vtable 0x19C3D8                  a vtable's slots and their names
  dis 0x85700:30                   30 instructions from a VA
  fn 0x85700                       what the function at a VA reaches without a call
  calls 0x85700                    the direct calls to a VA
  find-refs --va 0x19C1AC          the .text instructions that hold a VA (--data: the data dwords)
  find-refs --string fx_magic_timer   the same, for the string
  insns --mnemonic fmul --operand 0x1a   instructions by mnemonic and operand text
  sse2 --section SHIMS             what a Pentium III can't run
  find-floats 9.7 9.9              the floats in .rdata in a range
  strings levels/water             the strings in .rdata and .data
  hexdump 0x19C1AC --length 64     the bytes (a human's: it prints the game's bytes)
"""


def _int(text: str) -> int:
    try:
        return int(text, 0)
    except ValueError:
        raise ValueError(f"{text!r} is no number (hex 0x... or decimal)") from None


def _number(text: str) -> int:
    try:
        return _int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def _positive(text: str) -> int:
    if (n := _number(text)) < 1:
        raise argparse.ArgumentTypeError(f"{text} is not 1 or more")
    return n


def _where(text: str, given: int | None, default: int) -> tuple[int, int]:
    """``VA[:N]`` and ``--count N`` as ``(va, n)``."""
    start, _, n = text.partition(":")
    va, count = _int(start), _int(n) if n else None
    if None not in (count, given) and count != given:
        raise ValueError(f"two counts: :{n} and --count {given}")
    count = given if given is not None else count if count is not None else default
    if count < 1:
        raise ValueError(f"N is {count}; give 1 or more")
    return va, count


def _named(line: str, name: str | None) -> str:
    return f"{line}  ; {name}" if name else line


def _f32_text(value: float) -> str:
    """The shortest decimal that reads back as this float32."""
    if not math.isfinite(value):
        return repr(value)
    for digits in range(1, 10):
        text = f"{value:.{digits}g}"
        try:   # FLT_MAX's short texts round past float32 (AZ-659)
            if struct.unpack("<f", struct.pack("<f", float(text)))[0] == value:
                return text
        except OverflowError:
            continue
    return repr(value)


def _value_text(r: Read, kind: str) -> str:
    """A :class:`Read` as text: its value, never its bytes."""
    if r.bss:
        return "bss"
    if kind == "cstr":
        return repr(r.value) if r.value is not None else "(no printable C string)"
    if kind == "f32":
        return _f32_text(r.value)
    if kind in ("f64", "i32"):
        return repr(r.value)
    if kind != "ptr":
        return f"{r.value} (0x{r.value:X})"
    if r.value == 0:
        return "0x00000000  null"
    what = r.name or (repr(r.string) if r.string else "")
    return f"0x{r.value:08X}  {r.section or '(no section)'}  {what}".rstrip()


def _scope(args) -> dict:
    if args.in_fn is not None and args.section is not None:
        raise ValueError("--in-fn VA lists one function's instructions; drop --section")
    span = None
    if args.range is not None:
        lo, sep, hi = args.range.partition(":")
        if not sep:
            raise ValueError(f"--range {args.range!r}: give LO:HI")
        span = (_int(lo), _int(hi))
    return {"span": span, "fn": args.in_fn}


def _addr(args, data: bytes) -> tuple[object, list[str]]:
    found = address(data, args.value, None if args.from_ == "auto" else args.from_)
    return asdict(found), [str(found)]


def _hexdump(args, data: bytes) -> tuple[object, list[str]]:
    rows = hexdump(data, args.address, args.length, not args.file)
    if not rows:
        raise ValueError(f"0x{args.address:X} is in no section")
    return [{"va": r.va, "file_offset": r.file_offset, "bytes": r.raw.hex()} for r in rows], [str(r) for r in rows]


def _find_refs(args, data: bytes) -> tuple[object, list[str]]:
    lines = []
    target = args.va
    if target is None:
        hits = find_strings(data, args.string, min_len=len(args.string), limit=sys.maxsize)
        found = [h for h in hits if h.text == args.string] or hits
        if not found:
            raise ValueError(f"no string holds {args.string!r}")
        if len(found) > 1:
            what = "copies of" if found[0].text == args.string else "strings hold"
            raise ValueError("\n  ".join([f"{len(found)} {what} {args.string!r}; pass --va with one of:",
                                          *(f"VA 0x{h.va:08X}  len={len(h.text):4d}  {h.text[:77]!r}" for h in found)]))
        target = found[0].va
        lines.append(f"# the string {found[0].text!r} at VA 0x{target:X}")
    if args.data:
        refs, names = data_refs(data, target), names_for(data)
        return ([{"va": va, "section": s} for va, s in refs],
                lines + ([f"{len(refs)} data dword(s) hold VA 0x{target:X}:"]
                         + [_named(f"  VA 0x{va:08X}  {s}", names.get(va)) for va, s in refs] if refs
                         else [f"(no 4-aligned data dword holds VA 0x{target:X})"]))
    refs = va_refs(data, target)
    return ([asdict(r) for r in refs],
            lines + ([f"{len(refs)} .text instruction(s) hold VA 0x{target:X}:"]
                     + [f"  VA 0x{r.va:08X}  file 0x{r.file_offset:06X}  {r.mnemonic} {r.operands}".rstrip()
                        for r in refs] if refs
                     else [f"(no .text instruction holds VA 0x{target:X} as an immediate or a displacement; "
                           f"direct calls: xbe calls 0x{target:X})"]))


def _find_floats(args, data: bytes) -> tuple[object, list[str]]:
    hits = find_floats(data, args.min, args.max, {"float": (4,), "double": (8,), "both": (4, 8)}[args.width])
    rows = [(h, _f32_text(h.value) if h.width == 4 else repr(h.value)) for h in hits]
    return ([{"va": h.va, "file_offset": h.file_offset, "width": h.width, "value": float(t)} for h, t in rows],
            [f"{len(hits)} float(s) in [{args.min}, {args.max}]:"]
            + [f"  VA 0x{h.va:08X}  file 0x{h.file_offset:06X}  width={h.width}  value={t}" for h, t in rows])


def _strings_verb(args, data: bytes) -> tuple[object, list[str]]:
    hits = find_strings(data, args.pattern, regex=args.regex, ignore_case=args.ignore_case, min_len=args.min_len,
                        limit=args.limit)
    return ([asdict(h) for h in hits],
            [f"{len(hits)} string(s) matching {args.pattern!r}:"]
            + [f"  VA 0x{h.va:08X}  file 0x{h.file_offset:06X}  len={len(h.text):4d}  "
               f"{h.text if len(h.text) < 80 else h.text[:77] + '...'!r}" for h in hits])


def _sections(args, data: bytes) -> tuple[object, list[str]]:
    table = xbe.sections(data)
    return ([asdict(s) for s in table],
            [f"base 0x{struct.unpack_from('<I', data, 0x104)[0]:08X}",
             f"{'name':<10}  {'va':<10}  {'vsize':<10}  {'raw':<10}  {'raw_size':<10}  flags"]
            + [f"{s.name:<10}  0x{s.va:08X}  0x{s.vsize:08X}  0x{s.raw:08X}  0x{s.raw_size:08X}  0x{s.flags:08X}"
               for s in table])


def _code(args, data: bytes) -> tuple[object, list[str]]:
    names = names_for(data)
    if args.verb == "calls":
        if None not in (args.callee, args.to) and args.callee != args.to:
            raise ValueError(f"two callees: 0x{args.callee:X} and --to 0x{args.to:X}")
        to = args.callee if args.to is None else args.to
        hits = [{"site": s, "callee": c} | ({"name": names[c]} if c in names else {})
                for s, c in calls(data, to, args.section, **_scope(args))]
        lines = [_named(f"0x{h['site']:08X}  call 0x{h['callee']:08X}", h.get("name")) for h in hits]
    else:
        found = (search(data, args.mnemonic, args.operand, args.section, **_scope(args)) if args.verb == "insns"
                 else not_on_pentium3(data, args.section))
        rows = [(i, operand_names(i.operands, names)) for i in found]
        hits = [asdict(i) | ({"name": n} if n else {}) for i, n in rows]
        lines = [_named(str(i), n) for i, n in rows]
    return hits, lines + [f"({len(hits)} found)"]


def _listing(args, data: bytes) -> tuple[object, list[str]]:
    if args.verb == "fn":
        found = function(data, args.where)
    else:
        found = listing(data, *_where(args.where, args.count, 20))
    names = names_for(data)
    rows = [(i, operand_names(i.operands, names)) for i in found]
    return [asdict(i) | ({"name": n} if n else {}) for i, n in rows], [_named(str(i), n) for i, n in rows]


def _read_verb(args, data: bytes) -> tuple[object, list[str]]:
    names = names_for(data)
    vt = args.verb == "vtable"
    if vt:
        va, count, kind = args.va, args.slots, "ptr"
        reads = vtable(data, va, count, names)
        if not reads:
            raise ValueError(f"0x{va:X} holds no code address; --slots N reads it anyway")
    else:
        (va, count), kind = _where(args.where, None, 1), args.as_
        reads = read_values(data, va, kind, count, names)
    out = [{"va": r.va} | ({"offset": r.va - va} if vt else {})
           | {"value": float(_f32_text(r.value)) if kind == "f32" and not r.bss else r.value}
           | ({"bss": True} if r.bss else {})
           | ({"name": r.name, "string": r.string, "section": r.section} if kind == "ptr" else {}) for r in reads]
    lines = [f"{f'+0x{r.va - va:03X}' if vt else f'0x{r.va:08X}  {kind:<4}'}  {_value_text(r, kind)}" for r in reads]
    short = count is not None and len(reads) < count
    if vt:
        lines.append(f"({len(reads)} of {count} slots: the section ends)" if short else f"({len(reads)} slots)")
    elif short:
        lines.append(f"({len(reads)} of {count}: the section ends, or a string isn't printable)")
    return out, lines


def _source(p: argparse.ArgumentParser, after: bool = False) -> None:
    # A verb's flags default to those typed before it: SUPPRESS leaves them alone unless typed after the verb.
    d = {"default": argparse.SUPPRESS} if after else {}
    p.add_argument("--iso", metavar="PATH", help="an Xbox image (or a raw XBE) to read default.xbe from", **d)
    p.add_argument("--xbe", metavar="PATH", help="a raw default.xbe (or an Xbox image)", **d)
    p.add_argument("--region", choices=[r.name for r in RELEASES],
                   help="with neither: which release's image (default USA's when found, else the only one)", **d)
    p.add_argument("--json", action="store_true", help="JSON on stdout", **d)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m devkit re xbe", description=DESCRIPTION,
                                epilog=RECIPES, formatter_class=argparse.RawDescriptionHelpFormatter)
    _source(p)
    sub = p.add_subparsers(dest="verb", required=True, metavar="VERB")

    def verb(name: str, run, line: str) -> argparse.ArgumentParser:
        v = sub.add_parser(name, help=line, description=line)
        _source(v, after=True)
        v.set_defaults(run=run)
        return v

    v = verb("addr", _addr, "a number as a VA, a file offset and a section")
    v.add_argument("value", type=_number, help="hex (0x...) or decimal")
    v.add_argument("--from", dest="from_", choices=("auto", "va", "file"), default="auto",
                   help="read it as a VA or a file offset (default: a VA from the base address 0x10000 up)")
    v = verb("sections", _sections, "the section table")
    v = verb("read", _read_verb, "typed values at a VA, never their bytes: a float, an int, a pointer and what it "
             "points at, a C string")
    v.add_argument("where", metavar="VA[:N]", help="the start, then :N values in a row (default 1)")
    v.add_argument("--as", dest="as_", default="u32", choices=(*_READS, "cstr"),
                   help="the type (default u32); ptr names its target or shows its C string; cstr reads N strings")
    v = verb("vtable", _read_verb, "a vtable's slots: offset, target and the target's name")
    v.add_argument("va", type=_number, metavar="VA")
    v.add_argument("--slots", type=_positive, metavar="N",
                   help="read N slots (default: up to the first that holds no code address, or the next vtable)")
    v = verb("dis", _listing, "N instructions from a VA (mnemonics and operands, no bytes)")
    v.add_argument("where", metavar="VA[:N]", help="the start, then :N instructions (default 20)")
    v.add_argument("--count", type=_positive, metavar="N", help="N instructions, as VA:N")
    v = verb("fn", _listing, "the function at a VA: what it reaches without a call")
    v.add_argument("where", type=_number, metavar="VA")
    for name, line in (("insns", "instructions by mnemonic and operand text"),
                       ("calls", "direct call sites and their callees"),
                       ("sse2", "the instructions a Pentium III lacks: SSE2 and later, 3DNow! (AZ-021)")):
        v = verb(name, _code, line)
        v.add_argument("--section", help="only this code section, e.g. SHIMS (default: every code section)")
        if name == "insns":
            v.add_argument("--mnemonic", help="an exact mnemonic, e.g. fmul")
            v.add_argument("--operand", help="a substring of the operand text, e.g. 'dword ptr [esi + 0x'")
        if name == "calls":
            v.add_argument("callee", nargs="?", type=_number, metavar="VA", help="only the calls to VA, as --to")
            v.add_argument("--to", type=_number, metavar="VA", help="only the calls to VA")
        if name != "sse2":
            v.add_argument("--range", metavar="LO:HI", help="only the instructions at LO <= VA < HI")
            v.add_argument("--in-fn", type=_number, metavar="VA", help="only the instructions of the function at VA")
    v = verb("find-refs", _find_refs, "the .text instructions that hold a VA as an immediate or a displacement "
             "(direct calls: calls)")
    which = v.add_mutually_exclusive_group(required=True)
    which.add_argument("--va", type=_number, help="the VA")
    which.add_argument("--string", metavar="TEXT", help="the string equal to TEXT, else the one string holding it")
    v.add_argument("--data", action="store_true",
                   help="the 4-aligned data dwords that hold it instead: vtable and pointer-table slots")
    v = verb("find-floats", _find_floats, "the float32s and doubles in .rdata in a range")
    v.add_argument("min", type=float)
    v.add_argument("max", type=float)
    v.add_argument("--width", choices=("float", "double", "both"), default="both")
    v = verb("strings", _strings_verb, "the printable ASCII strings in .rdata and .data")
    v.add_argument("pattern", help="a substring (or with --regex a Python regex)")
    v.add_argument("--regex", action="store_true")
    v.add_argument("-i", "--ignore-case", action="store_true")
    v.add_argument("--min-len", type=int, default=4, help="skip shorter strings (default 4)")
    v.add_argument("--limit", type=int, default=200, help="at most N (default 200)")
    v = verb("hexdump", _hexdump, "the bytes from a VA or a file offset (a human's: it prints the game's bytes)")
    v.add_argument("address", type=_number, help="a VA (or with --file a file offset)")
    v.add_argument("--length", type=_positive, default=64, help="how many bytes (default 64)")
    v.add_argument("--file", action="store_true", help="the address is a file offset")
    return p


def main(argv: list[str]) -> int:
    """Run one verb. A refusal (no image, not an XBE, an address no section
    maps ...) is one ``xbe: ...`` paragraph on stderr and exit 2, as a usage
    error is."""
    args = parser().parse_args(argv)
    try:
        data, line = load(args.iso or args.xbe, args.region)
        print(line, file=sys.stderr)
        out, lines = args.run(args, data)
    except (OSError, ValueError) as exc:
        print(f"xbe: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2) if args.json else "\n".join(lines))
    return 0
