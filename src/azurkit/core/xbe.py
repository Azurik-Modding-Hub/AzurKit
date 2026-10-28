"""``default.xbe``, the game's executable: its section table, and where a
virtual address sits in the file.

The header starts ``XBEH``. At 0x104 is the base address it loads at, at
0x11C the number of sections and at 0x120 the address of their headers, 56
bytes each: flags, virtual address and size, raw (file) address and size,
then the address of the section's name. A section's file bytes start at its
raw address; a virtual address inside them is as far in. A section's tail
past its raw size has no file bytes (the loader zero-fills it).

Each release's table is in its facts (:mod:`azurkit.core.facts`), which a
build maps addresses through (AZ-316: no static USA map); a build reads only
its release's vanilla XBE, whose own table :func:`sections` reads that one.

A shim's bytes land where the carve allocator (:class:`Carver`) says, each
placement a claim on the file that the build's manifest keeps; the header
fields a claim changes (``.text``'s sizes, an appended section) are derived
from the claims when the image is made (:func:`grown`), never written by a
layer.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
from dataclasses import dataclass

MAGIC = b"XBEH"
_SECTION = struct.Struct("<6I")   # flags, va, vsize, raw, raw size, the name's address
_SECTION_SIZE = 56


@dataclass(frozen=True)
class Section:
    name: str
    va: int
    vsize: int
    raw: int
    raw_size: int
    flags: int


def sections(data: bytes) -> tuple[Section, ...]:
    """The section table the header of the XBE ``data`` holds;
    ``ValueError`` when ``data`` isn't an XBE or its table runs off it."""
    data = bytes(data)
    if data[:4] != MAGIC:
        raise ValueError("not an XBE: no XBEH at 0")
    try:
        (base,) = struct.unpack_from("<I", data, 0x104)
        count, at = struct.unpack_from("<II", data, 0x11C)
        table = []
        for i in range(count):
            flags, va, vsize, raw, raw_size, name = _SECTION.unpack_from(data, at - base + i * _SECTION_SIZE)
            end = data.index(b"\0", name - base)
            table.append(Section(data[name - base:end].decode("latin-1"), va, vsize, raw, raw_size, flags))
    except (struct.error, ValueError) as exc:
        raise ValueError(f"the XBE's section table runs off it ({exc})") from None
    return tuple(table)


def offset(table: Iterable[Section], va: int, size: int = 1) -> int:
    """The file offset of the ``size`` bytes at ``va`` in an XBE whose
    sections are ``table``; ``ValueError`` when no section's file bytes
    hold them all."""
    for s in table:
        if s.va <= va and va + size <= s.va + min(s.vsize, s.raw_size):
            return s.raw + va - s.va
    raise ValueError(f"0x{va:08X} ({size} B) is in no section's file bytes")


# Where shims land (the carve allocator) and the header state their claims derive.

FILE_ALIGN = VA_ALIGN = 0x1000
SHIMS = "SHIMS"            # the section a shim spills into, appended past the last
SHIMS_FLAGS = 0x00000006   # executable | preload (as .rdata); a writable claim adds 0x1
WRITABLE = 0x00000001
CODE_GAP = 64              # zero bytes around a writable landing: xemu retranslates a 64-byte line's code on each store
_HEADER = 56               # a section header's size
_TAIL_POINTERS = (0x14C, 0x150, 0x154, 0x164, 0x168, 0x16C, 0x170)   # image header fields that point past the table


def _align(n: int, to: int) -> int:
    return (n + to - 1) & ~(to - 1)


@dataclass(frozen=True)
class Room:
    """Where shims land in a vanilla XBE: ``.text`` grows into the zero bytes
    before the next section (``room`` of them: USA has 16 before BINK, Europe
    none), and past that a section appended after the last (:data:`SHIMS`),
    whose bytes start at ``shims`` in the file and at ``shims_va``."""
    text: Section
    room: int
    shims: int
    shims_va: int

    @property
    def gap(self) -> int:
        """The file offset of ``.text``'s end, where its growth starts."""
        return self.text.raw + self.text.raw_size


def room(data: bytes) -> Room:
    """The :class:`Room` of the vanilla XBE ``data``."""
    table = sections(data)
    text = next((s for s in table if s.name == ".text"), None)
    if text is None:
        raise ValueError("the XBE has no .text section")
    end = text.raw + text.raw_size
    later = [s for s in table if s is not text]
    va_gap = min((s.va for s in later if s.va > text.va), default=text.va + text.vsize) - (text.va + text.vsize)
    room = min(va_gap, min((s.raw for s in later if s.raw > text.raw), default=len(data)) - end)
    zeros = len(data[end:end + max(room, 0)]) - len(data[end:end + max(room, 0)].lstrip(b"\0"))
    return Room(text, zeros, _align(len(data), FILE_ALIGN), _align(max(s.va + s.vsize for s in table), VA_ALIGN))


class Carver:
    """The carve allocator over a vanilla XBE: :meth:`place` puts a shim's
    bytes past every claim in ``taken`` (``(offset, size)`` in the file:
    another layer's, then each it gave), in ``.text``'s gap while it holds
    them, else in :data:`SHIMS`; writable bytes never go in ``.text`` (it
    is read-only) and land :data:`CODE_GAP` from any code. Placement is
    canonical: the same claims taken in the same order land the same."""

    def __init__(self, data: bytes, taken=()):
        self.room = room(data)
        self.taken = [tuple(t) for t in taken]

    def place(self, size: int, align: int = 1, writable: bool = False) -> tuple[int, int, int, int]:
        """``(claim offset, claim size, offset, va)``: the claim covers the
        alignment's pad and any gap after it; the bytes go at ``offset``,
        which the loader maps at ``va``."""
        r = self.room
        at = max([r.gap] + [o + n for o, n in self.taken if r.gap <= o < r.gap + r.room])
        va = r.text.va + at - r.text.raw
        pad = -va % align
        if not writable and r.gap + r.room - at >= pad + size:
            self.taken.append((at, pad + size))
            return at, pad + size, at + pad, va + pad
        gap = CODE_GAP if writable else 0
        ends = [o + n for o, n in self.taken if o >= r.shims]
        if ends:
            at = max(ends)
            pad = gap + -(r.shims_va + at - r.shims + gap) % align
        elif align > VA_ALIGN:
            raise ValueError(f"an alignment of 0x{align:X} is past the appended section's 0x{VA_ALIGN:X}")
        else:
            at, pad = r.shims, gap + -gap % align
        self.taken.append((at, pad + size + gap))
        return at, pad + size + gap, at + pad, r.shims_va + at - r.shims + pad


def grown(data: bytes, claims) -> bytes:
    """The vanilla XBE ``data`` with the header state ``claims`` (``(offset,
    size, writable)``, each the :class:`Carver`'s) derive: ``.text`` grown
    over those in its gap, and :data:`SHIMS` appended over those past the
    file's end, zeros until a layer writes them. ``ValueError`` names a
    claim the allocator couldn't have given."""
    r = room(data)
    claims = sorted(tuple(c) for c in claims)
    text = [c for c in claims if r.gap <= c[0] and c[0] + c[1] <= r.gap + r.room]
    shims = [c for c in claims if c[0] >= r.shims]
    if stray := [c for c in claims if c not in text and c not in shims]:
        raise ValueError(f"a claim at 0x{stray[0][0]:X} ({stray[0][1]} B) is in neither .text's gap nor {SHIMS}")
    out = bytearray(data)
    base, table = struct.unpack_from("<I", out, 0x104)[0], struct.unpack_from("<I", out, 0x120)[0]
    if text:
        grow = max(o + n for o, n, _ in text) - r.gap
        at = table - base + next(i for i, s in enumerate(sections(data)) if s.name == ".text") * _HEADER
        struct.pack_into("<I", out, at + 8, r.text.vsize + grow)
        struct.pack_into("<I", out, at + 16, r.text.raw_size + grow)
    if shims:
        _append(out, max(o + n for o, n, _ in shims) - r.shims, r.shims, r.shims_va,
                SHIMS_FLAGS | (WRITABLE if any(w for *_, w in shims) else 0))
    return bytes(out)


def _append(out: bytearray, size: int, raw: int, va: int, flags: int) -> None:
    """Append :data:`SHIMS` (``size`` zeros at ``raw`` and ``va``): the
    section table grows by one header into the header's slack before the
    first section, the bytes after it move on by 56 with every pointer to
    them, the name goes at the header's new end, and the header's size,
    the image's size and the section count follow."""
    base, headers = struct.unpack_from("<II", out, 0x104)
    count, table = struct.unpack_from("<II", out, 0x11C)
    table -= base
    end = table + count * _HEADER
    old = sections(bytes(out))
    slack = min(min(s.va for s in old) - (base + headers), min(s.raw for s in old if s.raw) - headers)
    if slack < _HEADER:
        raise ValueError(f"the XBE header has {slack} B before its first section, not the {_HEADER} B a section takes")
    out[end + _HEADER:headers + _HEADER] = out[end:headers]
    out[end:end + _HEADER] = bytes(_HEADER)
    moved = lambda p: base <= p < base + headers and p - base >= end   # noqa: E731
    for field in _TAIL_POINTERS + tuple(table + i * _HEADER + k for i in range(count) for k in (20, 28, 32)):
        if moved(p := struct.unpack_from("<I", out, field)[0]):
            struct.pack_into("<I", out, field, p + _HEADER)
    headers += _HEADER
    name = SHIMS.encode("ascii") + b"\0"
    at = headers - len(name)
    if at < end + _HEADER:
        raise ValueError(f"the XBE header has no room for the name {SHIMS!r}")
    if any(out[at:headers]):
        if slack < _HEADER + len(name):
            raise ValueError(f"the XBE header has no room for the name {SHIMS!r}")
        at, headers = headers, headers + len(name)
    out[at:at + len(name)] = name
    out.extend(bytes(raw - len(out) + size))
    head = struct.unpack_from("<I", out, table + 28)[0]   # the first section's page counters, shared
    out[end:end + _HEADER] = struct.pack("<9I", flags, va, size, raw, size, base + at, 0, head, head) + bytes(20)
    struct.pack_into("<I", out, 0x108, headers)
    struct.pack_into("<I", out, 0x10C, _align(va + size, VA_ALIGN) - base)
    struct.pack_into("<I", out, 0x11C, count + 1)
