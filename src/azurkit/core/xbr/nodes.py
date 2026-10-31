"""A level's node graphs as the randomizer's writer reads them (Step 4.2b):
the table of contents (:func:`parse_toc`), a graph's records
(:func:`record_offsets`) and a record's strings (:func:`lstr`); and what the
character tool's archive writers read of any archive (Step 4.3a1): the
names an archive gives its resources (:func:`named_resources`), the load
runs its TOC makes (:func:`runs`) and ``index.xbr``'s record list
(:class:`IndexRecordsSection`).

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

import functools
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
    ``ValueError`` when it isn't an archive or its TOC runs past its end.
    The entries are kept by the TOC's bytes (a character swap reads
    characters.xbr's a few hundred times)."""
    count, data_start = _toc_header(data)
    return list(_entries(bytes(data[TOC_START:TOC_START + count * TOC_ROW_SIZE]), data_start))


def _toc_header(data: bytes | bytearray | memoryview) -> tuple[int, int]:
    if bytes(data[:4]) != b"xobx" or len(data) < TOC_START:
        raise ValueError(f"not an XBR archive ({len(data)} B, no xobx header)")
    count, data_start = struct.unpack_from("<II", data, 0x0C)
    if TOC_START + count * TOC_ROW_SIZE > len(data):
        raise ValueError(f"an XBR archive whose {count} TOC entries run past its {len(data)} B")
    return count, data_start


@functools.lru_cache(maxsize=64)   # every level file's, vanilla and built (23 each): a build parses each once
def _entries(rows: bytes, data_start: int) -> tuple[TocEntry, ...]:
    out = []
    for k, (rel, size, raw, flags) in enumerate(struct.iter_unpack("<II4sI", rows)):
        tag = raw.decode("ascii") if raw.isascii() else raw.hex()
        out.append(TocEntry(k, size, tag, flags, data_start + rel, rel))
    return tuple(out)


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


class XbrStructuralError(ValueError):
    """An archive edit that can't be made without breaking the archive's
    layout or a pointer in it; the message names what blocks it (D35)."""


def named_resources(data: bytes | bytearray | memoryview) -> dict[int, str]:
    """TOC index -> the name the archive gives that resource: the header's
    ``+0x2C`` rows of 8 bytes at ``+0x30`` (a ``u32`` TOC index and a ``u32``
    offset into the pool of NUL-terminated names at ``+0x34``, ``+0x38``
    bytes long); ``{}`` with no rows. ``ValueError`` names a row, or the
    table or pool, outside the file or the TOC."""
    toc_count, _ = _toc_header(data)
    count, table, pool, pool_size = struct.unpack_from("<IIII", data, 0x2C)
    if not count:
        return {}
    if table + 8 * count > len(data) or pool + pool_size > len(data):
        raise ValueError(f"an XBR archive whose named rows ({count} at 0x{table:X}, names at 0x{pool:X}) run past "
                         f"its {len(data)} B")
    return dict(_names(toc_count, bytes(data[table:table + 8 * count]), bytes(data[pool:pool + pool_size])))


@functools.lru_cache(maxsize=16)
def _names(toc_count: int, rows: bytes, chars: bytes) -> tuple[tuple[int, str], ...]:
    names = {}
    for k, (index, at) in enumerate(struct.iter_unpack("<II", rows)):
        end = chars.find(b"\0", at)
        if index >= toc_count or at >= len(chars) or end < 0:
            raise ValueError(f"an XBR archive whose named row {k} (TOC entry {index}, its name at +0x{at:X}) is "
                             "outside its TOC or its names")
        names[index] = chars[at:end].decode("ascii")
    return tuple(names.items())


PAGE = 0x1000   # a load run starts at an entry whose offset is a multiple of it


@dataclass(frozen=True)
class Run:
    """A load run: the page-aligned TOC entry ``head`` and the entries after
    it that start in its page (``members``, the head first), read as one
    block of ``size`` bytes (whole pages)."""

    head: int
    members: tuple[int, ...]
    size: int


@dataclass(frozen=True)
class Runs:
    """:func:`runs`' partition: the runs in TOC order, each entry's run head
    (``of``) and the entries in none (``orphans``)."""

    runs: tuple[Run, ...]
    of: dict[int, int]
    orphans: tuple[int, ...]


def runs(data: bytes | bytearray | memoryview) -> Runs:
    """The load runs the game makes of ``data``'s TOC: walking it in index
    order, a page-aligned entry starts a run, and each entry after it that
    starts in the head's page joins it; any other entry is in no run (an
    orphan, which the game can't load). ``ValueError`` when the index order
    of the entries with a payload isn't their offset order (the walk
    follows the index; every vanilla archive's is)."""
    toc = parse_toc(data)
    sized = [e for e in toc if e.size]
    for a, b in zip(sized, sized[1:]):
        if b.rel_offset < a.rel_offset:
            raise ValueError(f"TOC entry {b.index} starts before entry {a.index}: the load runs follow the TOC's "
                             "index order, and this archive's isn't its offset order")
    out: list[Run] = []
    of: dict[int, int] = {}
    orphans: list[int] = []
    members: list[TocEntry] = []
    open_run = False
    for e in toc:
        if e.rel_offset % PAGE == 0:
            if members:
                out.append(_run(members))
            members, open_run = [e], True
        elif open_run and e.rel_offset & ~(PAGE - 1) == members[0].rel_offset:
            members.append(e)
        else:
            orphans.append(e.index)
            open_run = False
            continue
        of[e.index] = members[0].index
    if members:
        out.append(_run(members))
    return Runs(tuple(out), of, tuple(orphans))


def _run(members: list[TocEntry]) -> Run:
    head, last = members[0], members[-1]
    return Run(head.index, tuple(e.index for e in members),
               -(-(last.rel_offset - head.rel_offset + last.size) // PAGE) * PAGE)


class IndexRecordsSection:
    """``index.xbr``'s ``indx`` payload: a list (:func:`list_at`) of
    :data:`RECORD_SIZE`-byte records, then their strings."""

    RECORD_SIZE = 20   # key length, key (from +4), archive length, archive (from +12), fourcc

    @staticmethod
    def frame(data: bytes | bytearray | memoryview, start: int) -> tuple[int, int]:
        """The payload at ``start``'s record count and where its records
        start."""
        table, count = list_at(data, start)
        return count, table
