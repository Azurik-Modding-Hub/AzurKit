"""Parse Azurik's ``index.xbr``: the global asset directory.

``index.xbr`` is listed under ``tag=always`` in ``prefetch-lists.txt``,
so the streaming loader keeps it resident.  Its one TOC entry, ``indx``,
maps every named asset key to the archive (XBR file) that holds it.

## Layout (AZ-218; HUB_MINING_PLAN HM-03)

The ``indx`` payload (:class:`azurik_mod.xbr.IndexRecordsSection`):

    +0   u32  count           3072 in vanilla
    +4   i32  table pointer   relative to its own field: payload+8
    +8   count x 20-byte records, sorted and unique by key,
         then the NUL-terminated strings

Each record:

    +0   u32      key length              (no NUL)
    +4   i32      key pointer             relative to its own field
    +8   u32      archive-name length
    +12  i32      archive-name pointer    relative to its own field
    +16  char[4]  fourcc                  body, banm, node, surf, wave,
                                          levl, tabl, font

Every record repeats one row of its archive's own named-resource table
(:func:`azurik_mod.xbr.toc_scan.named_resources`), and no record holds a
TOC index.  Vanilla, pinned by ``tests/test_index_xbr.py``: 3072
records, surf 1099, wave 816, banm 712, node 230, body 160, levl 33,
tabl 18, font 4; all 3072 equal a named row of their archive, and the
only named row without a record is index.xbr's own ``index``.

Until AZ-218 (2026-10-11) this parser read a 16-byte header, so each
field it named was another one: "version 4" was the table pointer,
"header_hint 24" record 0's key length, "pool_hint 0xEFFC" record 0's
key pointer, and "pool_magic 0x1812D" / "pool_tag levl" the last
record's archive pointer and fourcc; it found 3071 records.

See docs/RE_DATA.md § index.xbr.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from azurkit.core.xbr.append import append_resources, check_key
from azurkit.core.xbr.nodes import IndexRecordsSection
from azurkit.core.xbr.nodes import TocEntry, parse_toc


@dataclass(frozen=True)
class IndexRecord:
    """One ``indx`` record: an asset ``key`` (``characters/garret4/body``),
    the ``archive`` that holds it (``characters.xbr``) and its
    ``fourcc``."""

    key: str
    archive: str
    fourcc: str


@dataclass(frozen=True)
class IndexXbr:
    """Parsed ``index.xbr``.  Construct with :func:`load_index_xbr`."""

    records: tuple[IndexRecord, ...]

    def tag_counts(self) -> dict[str, int]:
        """Number of records per fourcc."""
        out: dict[str, int] = {}
        for r in self.records:
            out[r.fourcc] = out.get(r.fourcc, 0) + 1
        return out


def load_index_xbr(path: str | Path) -> IndexXbr:
    """Parse an ``index.xbr`` file.

    Raises :exc:`FileNotFoundError` for a missing path and
    :exc:`ValueError` for a file that isn't an XBR, has no ``indx``
    entry, or whose record table or strings run outside the ``indx``
    payload.
    """
    p = Path(path)
    return parse_index_xbr(p.read_bytes(), p.name)


def parse_index_xbr(raw: bytes, name: str = "index.xbr") -> IndexXbr:
    """:func:`load_index_xbr` of the bytes ``raw`` (``name`` labels its
    errors)."""
    return IndexXbr(tuple(r for r, _, _ in _records(raw, name)[1]))


def _records(raw: bytes, name: str
             ) -> tuple[TocEntry, list[tuple[IndexRecord, int, int]]]:
    """The ``indx`` entry and each record with the file offsets of its
    key and archive-name strings."""
    try:
        toc = parse_toc(raw)
    except ValueError as exc:
        raise ValueError(f"{name}: {exc}") from None
    indx = next((e for e in toc if e.tag == "indx"), None)
    if indx is None:
        raise ValueError(f"{name}: no indx TOC entry")
    start, end = indx.file_offset, min(indx.file_offset + indx.size, len(raw))
    count, table = IndexRecordsSection.frame(raw, start)

    def string(field: int, length: int, k: int) -> tuple[str, int]:
        at = field + struct.unpack_from("<i", raw, field)[0]
        if not (start <= at and at + length < end and raw[at + length] == 0):
            raise ValueError(
                f"{name}: record {k}'s string at 0x{at:X} ({length} B) "
                f"is not a NUL-terminated string inside the indx payload")
        return raw[at:at + length].decode("ascii"), at

    records = []
    for k in range(count):
        at = table + k * IndexRecordsSection.RECORD_SIZE
        if not start <= at <= end - IndexRecordsSection.RECORD_SIZE:
            raise ValueError(
                f"{name}: record {k} of {count} at 0x{at:X} runs past "
                f"the indx payload (0x{start:X}..0x{end:X})")
        key_len, arc_len = struct.unpack_from("<I4xI", raw, at)
        (key, key_at), (archive, arc_at) = (string(at + 4, key_len, k),
                                            string(at + 12, arc_len, k))
        records.append((IndexRecord(
            key=key, archive=archive,
            fourcc=raw[at + 16:at + 20].decode("ascii", "replace")),
            key_at, arc_at))
    return indx, records


def add_index_records(raw: bytes, records: Iterable[IndexRecord]) -> bytes:
    """``index.xbr`` with ``records`` added (Step 2.86): the table stays
    sorted and unique by key, the old strings are kept as they are and
    the new ones follow them, and the grown ``indx`` payload moves the
    trailer (:func:`azurik_mod.xbr.append.append_resources`).  A new key
    also needs its archive's named row to resolve (docs/RE_DATA.md §
    "How a name resolves").  Raises :exc:`ValueError` for a duplicate
    key or one the engine can't look up (not lower-case ASCII)."""
    indx, old = _records(raw, "index.xbr")
    count, table = IndexRecordsSection.frame(raw, indx.file_offset)
    strings_at = table + IndexRecordsSection.RECORD_SIZE * count
    if any(min(k, a) < strings_at for _, k, a in old):
        raise ValueError("index.xbr: a record's string precedes the strings "
                         "after the record table")
    strings = bytearray(raw[strings_at:indx.file_offset + indx.size])
    rows = [(r, k - strings_at, a - strings_at) for r, k, a in old]
    archives = {r.archive: a for r, _, a in rows}
    for r in records:
        check_key(r.key)
        if len(r.fourcc.encode("ascii")) != 4:
            raise ValueError(f"{r.key}: fourcc {r.fourcc!r} isn't 4 ASCII bytes")
        if r.archive not in archives:
            archives[r.archive] = len(strings)
            strings += r.archive.encode("ascii") + b"\0"
        rows.append((r, len(strings), archives[r.archive]))
        strings += r.key.encode("ascii") + b"\0"
    rows.sort(key=lambda row: row[0].key)
    keys = [r.key for r, _, _ in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("index.xbr: a key is listed twice")
    size = IndexRecordsSection.RECORD_SIZE
    base = 8 + size * len(rows)              # the strings, from payload+0
    payload = bytearray(struct.pack("<Ii", len(rows), 4))
    for j, (r, k, a) in enumerate(rows):
        at = 8 + size * j
        payload += struct.pack("<IiIi4s", len(r.key), base + k - (at + 4),
                               len(r.archive), base + a - (at + 12),
                               r.fourcc.encode("ascii"))
    return append_resources(raw, rewrite={indx.index: bytes(payload + strings)})


__all__ = [
    "IndexRecord",
    "IndexXbr",
    "add_index_records",
    "load_index_xbr",
    "parse_index_xbr",
]
