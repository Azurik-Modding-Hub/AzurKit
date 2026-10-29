"""A level's node graphs as the randomizer's writer reads them (Step 4.2b):
the table of contents (:func:`parse_toc`), a graph's records
(:func:`record_offsets`) and a record's strings (:func:`lstr`).

A ``node`` payload starts with a list: a ``u32`` count, then an ``i32``
reference to a table of that many ``i32`` pointers, each relative to its
own slot (0: an empty slot), one a record. A record's string field is a
``u32`` length and an ``i32`` reference relative to the reference's own
offset; the string has no NUL counted in its length. Every number is
little-endian. Unlike :class:`~azurkit.core.xbr.document.Document`, the
table of contents is read alone (16 bytes an entry at :data:`TOC_START`),
so a level of tens of megabytes isn't parsed whole to find one graph.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

TOC_START = 0x3C      # the first TOC entry, past the 15-word header
TOC_ROW_SIZE = 16     # u32 offset (from the data area), u32 size, char[4] tag, u32 alignment


@dataclass(frozen=True)
class TocEntry:
    index: int
    size: int
    tag: str            # its four characters, or their hex when they aren't ASCII
    flags: int
    file_offset: int    # the data area's start (header +0x10) plus rel_offset
    rel_offset: int


def parse_toc(data: bytes | bytearray | memoryview) -> list[TocEntry]:
    """The TOC entries of the archive ``data`` (header +0x0C counts them);
    ``ValueError`` when it isn't an archive or its TOC runs past its end."""
    if bytes(data[:4]) != b"xobx" or len(data) < TOC_START:
        raise ValueError(f"not an XBR archive ({len(data)} B, no xobx header)")
    count, data_start = struct.unpack_from("<II", data, 0x0C)
    if TOC_START + count * TOC_ROW_SIZE > len(data):
        raise ValueError(f"an XBR archive whose {count} TOC entries run past its {len(data)} B")
    out = []
    for k in range(count):
        rel, size, raw, flags = struct.unpack_from("<II4sI", data, TOC_START + k * TOC_ROW_SIZE)
        tag = raw.decode("ascii") if raw.isascii() else raw.hex()
        out.append(TocEntry(k, size, tag, flags, data_start + rel, rel))
    return out


def lstr(buf, at: int, limit: int | None = 300) -> str | None:
    """The string field at ``at`` in ``buf`` as text (a byte past ASCII as
    U+FFFD); ``None`` for a length of 0, of ``limit`` or more, or a string
    outside ``buf``."""
    n, ref = struct.unpack_from("<Ii", buf, at)
    start = at + 4 + ref
    if n == 0 or (limit is not None and n >= limit) or start <= 0 or start + n > len(buf):
        return None
    return bytes(buf[start:start + n]).decode("ascii", "replace")


def list_at(buf, at: int) -> tuple[int, int]:
    """The list at ``at`` in ``buf``: where its items start, and how many."""
    n, ref = struct.unpack_from("<Ii", buf, at)
    return at + 4 + ref, n


def record_offsets(buf, base: int = 0) -> list[int | None]:
    """Each record's offset in ``buf`` of the ``node`` payload at ``base``,
    ``None`` for an empty slot, in slot order."""
    table, n = list_at(buf, base)
    out: list[int | None] = []
    for k in range(n):
        (ptr,) = struct.unpack_from("<i", buf, table + 4 * k)
        out.append(table + 4 * k + ptr if ptr else None)
    return out
