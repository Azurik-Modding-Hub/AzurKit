"""Copies of an archive's resources under new TOC entries (Step 2.157,
D446: "Clone + author new").

Every cross-resource reference in an XBR is a u32 TOC index that the
trailer's relocation table lists; the run loader 0xA55F0 turns each into
a handle (the archive's slot base plus the index) when the run holding it
loads, and every other reference inside a payload is self-relative
(``docs/XBR_FORMAT.md`` § "Relocations").  So a copy of a resource is its
bytes plus its relocation rows at the same inner offsets, each naming the
copy of its target or the target itself.

- :func:`refs_in` lists an entry's relocated fields (inner offset,
  target), :func:`closure` what a set of entries reaches through them.
- :class:`Batch` collects new entries for one destination archive,
  numbered from its TOC count (or a later base, when other entries go
  first), and hands them to
  :func:`~azurik_mod.xbr.append.append_resources` as
  :class:`~azurik_mod.xbr.append.NewResource` values with their rows.
- :class:`Copier` copies a source archive's entries into a batch, each
  once.  Into its own archive it shares what vanilla shares between
  graphs, the textures and sounds (:data:`SHARED`: no ``rdms``,
  ``pbrc``, ``pbrw``, ``tern``, ``ndbg``, ``gshd`` or ``sprv`` is reached
  by two named graphs in either fx archive, the Step 2.157 critique's
  census), and copies the rest; across archives it copies everything it
  reaches, refusing a tag the destination has no per-tag row for
  (characters.xbr has no ``sdsr``: a streamed sound).

Every refusal is an :class:`~azurik_mod.xbr.edits.XbrStructuralError`
naming the entry (D35).  Nothing here prints a byte.
"""

from __future__ import annotations

import bisect
import struct
from dataclasses import dataclass, field

from azurkit.core.xbr.append import NewResource, relocations
from azurkit.core.xbr.nodes import XbrStructuralError
from azurkit.core.xbr.nodes import TocEntry, parse_toc

SHARED = ("surf", "wave")
"""The tags a copy into the same archive shares rather than copies: the
only resources vanilla's graphs share (a texture, a sound)."""


def tags(data) -> set[str]:
    """The tags ``data``'s per-tag rows name (0xA54F0 checks each)."""
    h = struct.unpack_from("<15I", data, 0)
    return {bytes(data[h[6] + 8 * k:h[6] + 8 * k + 4]).decode("ascii") for k in range(h[5])}


def refs_in(data, toc: list[TocEntry], index: int, rows: list[int] | None = None) -> list[tuple[int, int]]:
    """Entry ``index``'s relocated fields: (offset in its payload, the TOC
    index it holds), in offset order (``rows``: :func:`relocations`)."""
    rows = sorted(relocations(data)) if rows is None else rows
    e = toc[index]
    lo, hi = bisect.bisect_left(rows, e.rel_offset), bisect.bisect_left(rows, e.rel_offset + e.size)
    return [(r - e.rel_offset, struct.unpack_from("<I", data, e.file_offset + r - e.rel_offset)[0])
            for r in rows[lo:hi]]


def closure(data, roots, rows: list[int] | None = None) -> list[int]:
    """The TOC indices ``roots`` reach through relocated fields, the roots
    included, ascending."""
    toc = parse_toc(data)
    rows = sorted(relocations(data)) if rows is None else rows
    seen, todo = set(), list(roots)
    while todo:
        i = todo.pop()
        if i in seen:
            continue
        if not 0 <= i < len(toc):
            raise XbrStructuralError(f"TOC index {i} is outside the {len(toc)} entries")
        seen.add(i)
        todo += [t for _, t in refs_in(data, toc, i, rows)]
    return sorted(seen)


@dataclass
class Entry:
    """A new TOC entry under construction: its tag, payload, relocated
    fields (offset -> the destination TOC index it names), name (``None``:
    no named row) and where it came from ((archive, TOC index), or a
    description), for a plan."""
    tag: str
    payload: bytearray
    refs: dict[int, int] = field(default_factory=dict)
    name: str | None = None
    source: object = None

    def point(self, off: int, target: int) -> None:
        """Make the u32 at ``off`` a relocated field naming ``target``."""
        if off % 4 or not 0 <= off <= len(self.payload) - 4:
            raise XbrStructuralError(f"+0x{off:X} isn't a 4-aligned field inside the {len(self.payload)} B "
                                     f"{self.tag}")
        self.refs[off] = target
        struct.pack_into("<I", self.payload, off, target)


class Batch:
    """New entries for one destination archive ``dst``, numbered from
    ``base`` (its TOC count unless other entries are appended first)."""

    def __init__(self, dst, base: int | None = None):
        self.count = len(parse_toc(dst))
        self.base = self.count if base is None else base
        self.tags = tags(dst)
        self.entries: list[Entry] = []

    def add(self, tag: str, payload, refs: dict[int, int] | None = None, name: str | None = None,
            source=None) -> int:
        """A new entry's TOC index; refused for a tag ``dst`` has no row for."""
        if tag not in self.tags:
            raise XbrStructuralError(f"{source or tag}: the destination holds no {tag!r} resource, so it has "
                                     f"no per-tag row for it (0xA54F0)")
        e = Entry(tag, bytearray(payload), {}, name, source)
        for off, target in (refs or {}).items():
            e.point(off, target)
        self.entries.append(e)
        return self.base + len(self.entries) - 1

    def __getitem__(self, index: int) -> Entry:
        if not self.base <= index < self.base + len(self.entries):
            raise KeyError(index)
        return self.entries[index - self.base]

    def __contains__(self, index: int) -> bool:
        return self.base <= index < self.base + len(self.entries)

    def resources(self) -> list[NewResource]:
        """The entries as :func:`~azurik_mod.xbr.append.append_resources`
        takes them; refused when a field names an index past them."""
        top = self.base + len(self.entries)
        for k, e in enumerate(self.entries):
            for off, t in e.refs.items():
                if not 0 <= t < top:
                    raise XbrStructuralError(f"new TOC entry {self.base + k} ({e.tag}): +0x{off:X} names TOC "
                                             f"index {t}, past the {top} entries")
        return [NewResource(e.name, e.tag, bytes(e.payload), tuple(sorted(e.refs))) for e in self.entries]


class Copier:
    """Copies entries of the archive ``src`` into ``batch``, each at most
    once (:meth:`copy`).  ``same``: the batch's archive is ``src``, so the
    :data:`SHARED` tags are shared, not copied; ``label`` names ``src`` in
    refusals and plans."""

    def __init__(self, src, batch: Batch, *, same: bool, label: str = ""):
        self.src, self.batch, self.same, self.label = src, batch, same, label
        self.toc = parse_toc(src)
        self.rows = sorted(relocations(src))
        self.copies: dict[int, int] = {}

    def refs(self, index: int) -> list[tuple[int, int]]:
        return refs_in(self.src, self.toc, index, self.rows)

    def payload(self, index: int) -> bytes:
        e = self.toc[index]
        return bytes(self.src[e.file_offset:e.file_offset + e.size])

    def target(self, index: int) -> int:
        """Where a field naming source entry ``index`` points in the
        destination: the entry itself when shared, else its copy."""
        if not 0 <= index < len(self.toc):
            raise XbrStructuralError(f"{self.label} TOC index {index} is outside its {len(self.toc)} entries")
        return index if self.same and self.toc[index].tag in SHARED else self.copy(index)

    def copy(self, index: int) -> int:
        """The destination index of source entry ``index``'s copy, its
        relocated fields naming their targets' (:meth:`target`)."""
        if index in self.copies:
            return self.copies[index]
        e = self.toc[index]
        new = self.batch.add(e.tag, self.payload(index), source=(self.label, index))
        self.copies[index] = new
        for off, t in self.refs(index):
            self.batch[new].point(off, self.target(t))
        return new


__all__ = ["Batch", "Copier", "Entry", "SHARED", "closure", "refs_in", "tags"]
