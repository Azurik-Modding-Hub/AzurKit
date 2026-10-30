"""A shim's object file: i386 PE-COFF, as ``zig cc -target x86-windows-msvc
-c`` writes it (``shimkit``), read and laid out into ``default.xbe``.

The file starts with a 20-byte header: the machine (0x14C, i386), the
number of sections, a timestamp, the symbol table's offset and its number
of records, and the optional header's size (0 in an object). Each 40-byte
section header that follows holds an 8-byte name (or ``/N``, an offset into
the string table), the raw data's size and offset, the relocation table's
offset and count, and the flags (bits 20-23 its alignment: n gives
2**(n-1) bytes; 0x80, uninitialized data, has no file bytes). A relocation
is 10 bytes: the offset in its section, the symbol's index and the type.
A symbol record is 18 bytes: a name (inline, or 4 zero bytes and an offset
into the string table), its value (its offset in its section), its section
number (1-based; 0 is an external it doesn't define), type, storage class
(2: external) and how many auxiliary records follow it, which keep their
places in the indices. The string table follows the symbols, its size
first.

:func:`layout` places a shim's sections where an allocator says and
resolves its relocations: an absolute address (DIR32) or a rel32
displacement (REL32), each to a symbol of its own or a vanilla function the
facts name. :func:`normalized_sha256` is an object's identity as the
oracle's G2 records it.
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Callable, Mapping
from dataclasses import dataclass

MACHINE_I386 = 0x014C
UNINITIALIZED = 0x00000080
EXTERNAL = 2
ABSOLUTE, DIR32, REL32 = 0x0000, 0x0006, 0x0014
METADATA = (".drectve", ".debug", ".llvm_", ".xdata", ".pdata")   # never landed
WRITABLE = (".data", ".bss")


@dataclass(frozen=True)
class Relocation:
    offset: int    # in its section
    symbol: int    # its index in the symbol table
    type: int


@dataclass(frozen=True)
class Section:
    name: str
    flags: int
    data: bytes    # an uninitialized section's: its size in zeros
    relocations: tuple[Relocation, ...]

    @property
    def align(self) -> int:
        n = (self.flags >> 20) & 0xF
        return 1 << (n - 1) if n else 1

    @property
    def landed(self) -> bool:
        """Whether a build places it (it has bytes and isn't metadata)."""
        return bool(self.data) and not self.name.startswith(METADATA)

    @property
    def writable(self) -> bool:
        return self.name.split("$")[0] in WRITABLE


@dataclass(frozen=True)
class Symbol:
    name: str      # "" for an auxiliary record
    value: int
    section: int   # 1-based; 0: an external it doesn't define
    storage: int


@dataclass(frozen=True)
class Coff:
    machine: int
    sections: tuple[Section, ...]
    symbols: tuple[Symbol, ...]

    def symbol(self, name: str) -> Symbol:
        for s in self.symbols:
            if s.name == name:
                return s
        raise LookupError(f"the shim has no symbol {name!r}")


def _name(raw: bytes, strings: bytes) -> str:
    if raw[:4] == bytes(4):
        at = struct.unpack_from("<I", raw, 4)[0]
    elif raw[:1] == b"/" and (digits := raw[1:].split(b"\0")[0].strip()).isdigit():
        at = int(digits)
    else:
        return raw.split(b"\0")[0].decode("ascii", "replace")
    end = strings.find(b"\0", at)
    return strings[at:end if end >= 0 else len(strings)].decode("ascii", "replace")


def parse(data: bytes) -> Coff:
    """The object ``data``; ``ValueError`` says why it isn't one AzurKit lands."""
    try:
        machine, count, _, symbols_at, symbol_count, optional, _ = struct.unpack_from("<HHIIIHH", data, 0)
        if machine != MACHINE_I386:
            raise ValueError(f"its machine is 0x{machine:04X}, not i386 (0x014C)")
        strings_at = symbols_at + symbol_count * 18
        size = struct.unpack_from("<I", data, strings_at)[0] if strings_at + 4 <= len(data) else 0
        strings = data[strings_at:strings_at + size] if size >= 4 else b""
        sections = []
        for i in range(count):
            at = 20 + optional + i * 40
            size, raw, relocs_at, _, relocs, _, flags = struct.unpack_from("<4xIIIIHHI", data, at + 12)
            if not flags & UNINITIALIZED and raw + size > len(data):
                raise ValueError(f"section {i}'s bytes run off the file")
            body = bytes(size) if flags & UNINITIALIZED else data[raw:raw + size]
            sections.append(Section(_name(data[at:at + 8], strings), flags, body, tuple(
                Relocation(*struct.unpack_from("<IIH", data, relocs_at + j * 10)) for j in range(relocs))))
        symbols, i = [], 0
        while i < symbol_count:
            at = symbols_at + i * 18
            value, section, _, storage, aux = struct.unpack_from("<IhHBB", data, at + 8)
            symbols += [Symbol(_name(data[at:at + 8], strings), value, section, storage)] + [Symbol("", 0, 0, 0)] * aux
            i += 1 + aux
    except struct.error as exc:
        raise ValueError(f"it is cut short ({exc})") from None
    return Coff(machine, tuple(sections), tuple(symbols))


def normalized_sha256(data: bytes | Coff) -> str:
    """The sha256 of what decides the object's landed code (an object's
    bytes, or one parsed), as the oracle's G2 records it: the machine, each
    landed section and ``.bss`` (name, flags, size, the sha256 of its bytes,
    and its relocations with each symbol by name), and the external symbols
    with their values; not the timestamp or the debug records, which change
    between builds."""
    coff = data if isinstance(data, Coff) else parse(data)
    name = lambda i: coff.symbols[i].name if i < len(coff.symbols) else i   # noqa: E731
    sections = [(s.name, s.flags, len(s.data), hashlib.sha256(s.data).hexdigest(),
                 [(r.offset, name(r.symbol), r.type) for r in s.relocations])
                for s in coff.sections if s.landed or s.name.startswith(".bss")]
    externals = sorted((s.name, s.value) for s in coff.symbols if s.storage == EXTERNAL)
    return hashlib.sha256(repr((coff.machine, sections, externals)).encode()).hexdigest()


@dataclass(frozen=True)
class Placed:
    section: str
    offset: int    # in default.xbe
    va: int
    data: bytes    # relocated
    index: int = 0   # the section's, in the object (several share a name)


Allocate = Callable[[int, int, bool], tuple[int, int]]   # (size, align, writable) -> (file offset, address)
Extern = Callable[[str], int | None]   # an external's mangled name -> its address, or None: not one it knows


def layout(coff: Coff, entry: str, allocate: Allocate, vanilla: Mapping[str, int], extern: Extern | None = None
           ) -> tuple[list[Placed], int]:
    """Each section of ``coff`` placed where ``allocate`` says, relocated,
    and the address of its symbol ``entry``. A shim whose ``.text`` has no
    relocations lands its ``.text`` alone, unaligned; any other lands each
    section it has bytes in, at its alignment, writable for ``.data`` and
    ``.bss``. A relocation's symbol is one of its own, or an external
    ``vanilla`` maps (a function's name as C mangles it -> its address), or
    one ``extern`` resolves (a kernel import, which may allocate its stub
    then, at the first relocation that names it); ``LookupError`` or
    ``ValueError`` names what it can't place or resolve."""
    text = next((s for s in coff.sections if s.name == ".text"), None)
    symbol = coff.symbol(entry)
    if text is not None and not text.relocations:
        if symbol.section < 1 or coff.sections[symbol.section - 1] is not text:
            raise LookupError(f"the shim's {entry!r} is not in its .text")
        offset, va = allocate(len(text.data), 1, False)
        return [Placed(".text", offset, va, text.data, coff.sections.index(text))], va + symbol.value
    places = {i: allocate(len(s.data), s.align, s.writable) for i, s in enumerate(coff.sections) if s.landed}
    if not places:
        raise ValueError("the shim has no section to land")

    def address(s: Symbol) -> int:
        if s.section > 0:
            if s.section - 1 not in places:
                raise ValueError(f"the shim's {s.name!r} is in a section it doesn't land")
            return places[s.section - 1][1] + s.value
        if s.name in vanilla:
            return vanilla[s.name]
        if extern is not None and (va := extern(s.name)) is not None:
            return va
        raise LookupError(f"the shim's external {s.name!r} is no vanilla function or kernel export the facts name")

    placed = []
    for i, (offset, va) in places.items():
        section = coff.sections[i]
        data = bytearray(section.data)
        for r in section.relocations:
            if r.type == ABSOLUTE:
                continue
            if r.offset + 4 > len(data):
                raise ValueError(f"a relocation at {section.name}+0x{r.offset:X} runs off its section")
            addend, target = struct.unpack_from("<i", data, r.offset)[0], address(coff.symbols[r.symbol])
            if r.type == DIR32:
                struct.pack_into("<I", data, r.offset, (addend + target) & 0xFFFFFFFF)
            elif r.type == REL32:
                struct.pack_into("<I", data, r.offset, (addend + target - (va + r.offset + 4)) & 0xFFFFFFFF)
            else:
                raise ValueError(f"relocation type 0x{r.type:04X} at {section.name}+0x{r.offset:X} "
                                 "(AzurKit lands DIR32 and REL32)")
        placed.append(Placed(section.name, offset, va, bytes(data), i))
    return placed, address(symbol)
