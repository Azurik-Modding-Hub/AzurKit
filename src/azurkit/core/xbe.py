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
