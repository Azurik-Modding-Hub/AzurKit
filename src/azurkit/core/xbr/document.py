"""An XBR archive (``xobx``): its header, table of contents and trailer,
parsed, and written back (:meth:`Document.dumps`).

The header is 15 little-endian words: ``xobx``, the version (4), a zero,
the TOC's entry count, where the data area starts, then the trailer's
index: the count of per-tag rows and where the trailer starts (on a page,
after the last payload), the count and offset of the relocations, of the
12-byte records, and of the named rows, then the offset and size of the
name pool, which ends the file. Every offset in it is from the file's
start.

The TOC follows at 0x3C, 16 bytes an entry: the payload's offset from the
data area's start, its size, its four-character tag and its alignment.

The trailer's tables follow each other from its start: a ``(tag, u32)``
row for each tag the archive holds, then the relocations (each a u32, the
data-area offset of a field that holds a TOC index), the 12-byte records,
the named rows (``u32`` TOC index, ``u32`` offset into the pool), and the
pool of NUL-terminated names.

A file of the header alone (no TOC entry and no trailer) is a stub.
:meth:`Document.dumps` writes every structure parsed here, and a keyed
table's (:mod:`.keyed`), from its fields over the file's bytes, so a
round trip of every vanilla archive giving its own bytes back checks the
parse.
"""

from __future__ import annotations

import functools
import struct
from dataclasses import dataclass

from azurkit.core.xbr import keyed

MAGIC = b"xobx"
HEADER = struct.Struct("<4s14I")
ENTRY = struct.Struct("<II4sI")    # offset (from the data area), size, tag, alignment
TOC_AT = HEADER.size               # 0x3C
TAG_ROW = struct.Struct("<4sI")
NAMED_ROW = struct.Struct("<II")   # TOC index, offset into the pool
RECORD12 = 12


@dataclass(frozen=True)
class Header:
    version: int
    zero: int
    toc_count: int
    data_start: int
    tag_rows: int
    trailer: int
    reloc_count: int
    reloc_at: int
    record_count: int
    record_at: int
    named_count: int
    named_at: int
    pool_at: int
    pool_size: int


@dataclass(frozen=True)
class Entry:
    index: int
    offset: int      # from the data area's start
    size: int
    tag: str
    align: int
    start: int       # the payload's file offset


@dataclass(frozen=True)
class Named:
    index: int       # its TOC entry
    at: int          # its name's offset in the pool
    name: str


class Document:
    """An archive's bytes and what they hold. ``ValueError`` names the
    first structure that runs off the file or breaks the layout."""

    def __init__(self, data: bytes):
        self.data = bytes(data)
        if len(self.data) < HEADER.size or self.data[:4] != MAGIC:
            raise ValueError("not an XBR: no xobx header")
        self.header = Header(*HEADER.unpack_from(self.data, 0)[1:])
        h = self.header
        entries = []
        for k in range(h.toc_count):
            at = TOC_AT + ENTRY.size * k
            self._within(at, ENTRY.size, f"TOC entry {k}")
            offset, size, tag, align = ENTRY.unpack_from(self.data, at)
            self._within(h.data_start + offset, size, f"TOC entry {k}'s payload")
            entries.append(Entry(k, offset, size, tag.decode("latin-1"), align, h.data_start + offset))
        self.entries = tuple(entries)
        if h.toc_count == 0 and len(self.data) == HEADER.size:   # a stub: nothing past the header
            self.tag_rows, self.relocations, self.named = (), (), ()
            return
        chain = ((h.trailer, h.tag_rows, TAG_ROW.size, h.reloc_at, "the per-tag table"),
                 (h.reloc_at, h.reloc_count, 4, h.record_at, "the relocation table"),
                 (h.record_at, h.record_count, RECORD12, h.named_at, "the 12-byte record table"),
                 (h.named_at, h.named_count, NAMED_ROW.size, h.pool_at, "the named-row table"),
                 (h.pool_at, 1, h.pool_size, len(self.data), "the name pool"))
        for at, count, size, after, what in chain:
            if at + count * size != after:
                raise ValueError(f"{what} (0x{at:X}, {count} x {size} B) ends at 0x{at + count * size:X}, "
                                 f"not at 0x{after:X}")
        self.tag_rows = tuple((tag.decode("latin-1"), version)
                              for tag, version in TAG_ROW.iter_unpack(self.data[h.trailer:h.reloc_at]))
        self.relocations = tuple(v for (v,) in struct.iter_unpack("<I", self.data[h.reloc_at:h.record_at]))
        self.named = tuple(Named(index, at, self._name(at)) for index, at in
                           NAMED_ROW.iter_unpack(self.data[h.named_at:h.pool_at]))

    def _within(self, at: int, size: int, what: str) -> None:
        if at < 0 or at + size > len(self.data):
            raise ValueError(f"{what} (0x{at:X}, {size} B) runs off the {len(self.data)} B file")

    def _name(self, at: int) -> str:
        start = self.header.pool_at + at
        end = self.data.find(b"\0", start)
        if not self.header.pool_at <= start < end:
            raise ValueError(f"a named row's name at pool offset 0x{at:X} isn't in the pool")
        return self.data[start:end].decode("latin-1")

    def payload(self, entry: Entry) -> bytes:
        return self.data[entry.start:entry.start + entry.size]

    def names(self) -> dict[int, str]:
        """Each named TOC entry's name, by its index."""
        return {n.index: n.name for n in self.named}

    @functools.cached_property
    def tables(self) -> dict[str, keyed.Table]:
        """Each keyed table (a ``tabl`` entry: config.xbr's), by the last
        part of its name (``config/armor_properties``: ``armor_properties``)."""
        names = self.names()
        out = {}
        for e in self.entries:
            if e.tag == "tabl":
                name = names.get(e.index, f"tabl_{e.index}").rpartition("/")[2]
                out[name] = keyed.Table.parse(self.data, name, e.start, e.size)
        return out

    def dumps(self) -> bytes:
        """The archive written from what was parsed (the header, the TOC,
        the trailer's tables, the names and every keyed table) over its
        bytes: its own bytes, when the parse is whole."""
        out = bytearray(self.data)
        h = self.header
        HEADER.pack_into(out, 0, MAGIC, *(getattr(h, f) for f in Header.__dataclass_fields__))
        for e in self.entries:
            ENTRY.pack_into(out, TOC_AT + ENTRY.size * e.index, e.offset, e.size, e.tag.encode("latin-1"), e.align)
        for k, (tag, version) in enumerate(self.tag_rows):
            TAG_ROW.pack_into(out, h.trailer + TAG_ROW.size * k, tag.encode("latin-1"), version)
        for k, value in enumerate(self.relocations):
            struct.pack_into("<I", out, h.reloc_at + 4 * k, value)
        for k, n in enumerate(self.named):
            NAMED_ROW.pack_into(out, h.named_at + NAMED_ROW.size * k, n.index, n.at)
            name = n.name.encode("latin-1") + b"\0"
            out[h.pool_at + n.at:h.pool_at + n.at + len(name)] = name
        for table in self.tables.values():
            table.write(out)
        return bytes(out)
