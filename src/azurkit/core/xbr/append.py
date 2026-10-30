"""Add named resources to an XBR archive (Step 2.86).

:func:`append_resources` returns an archive with new resources added
the way the engine finds them (docs/XBR_FORMAT.md § "Appending
resources"; docs/RE_DATA.md § "How a name resolves"):

- each new payload starts on a page (0x1000) after the last payload, so
  the run builder 0xA4C00 can load it, and gets a TOC entry after the
  last one, with the flags (alignment) the archive's entries of that
  tag carry;
- each named one gets a named row after the last one and its name at
  the end of the pool; with its ``index.xbr`` record
  (:func:`azurik_mod.assets.index_xbr.add_index_records`) the key then
  resolves (0xA6A70, 0xA5570, 0xA5CA0); an unnamed one (``name=None``,
  Step 2.157) gets a TOC entry alone, reached only through a relocated
  field that names it, as vanilla's ``rdms``, ``gshd``, ``sprv`` and
  most ``surf`` entries are;
- each new payload's ``relocs`` (the offsets of its fields that hold a
  TOC index, Step 2.157) become relocation rows after the old ones, so
  the run loader 0xA55F0 turns each into a handle when the run loads;
- ``data_start`` grows by whole pages once the TOC, plus vanilla's zero
  entry, needs them (characters.xbr has room for 185 more entries);
- the trailer moves to the page after the last payload, and only the
  header's offsets change: every old payload, its relative offset, the
  per-tag rows, the old relocations and the old named rows and names stay
  byte-identical.

:func:`appended` reads the entries an archive gained past a count back as
:class:`NewResource` values (their names, or ``None``, and their
relocated fields), so a later pass can add them again to the archive
they were appended to (W28's :func:`~azurik_mod.patches._player_variants.restyled`).

``rewrite`` replaces existing payloads in place (:func:`rewrite_payloads`,
Step 2.154): a payload that outgrows the slack before the next one moves
every later payload by whole pages (since Step 2.158, where the next
payload isn't page-aligned, sharing the grown one's load run, that one
and the rest of its page move to the next page start as a new run), and
every relocated field inside it must keep its value.  Bytes of the old
payload past the new one become zeros.

:func:`rewrite_payloads` is that rewrite alone, and can also give a
rewritten payload a new set of relocated fields (a mesh with more or
fewer groups, each naming its material by TOC index): growth moves each
later payload's TOC offset and every relocation entry in or after it by
the same whole pages, so its alignment (8, 16 or 128) and its offset in
its page hold; no TOC index, relocation value, named row or name
changes.

Every refusal raises :class:`~azurik_mod.xbr.edits.XbrStructuralError`
(a :exc:`ValueError`) naming what blocks it (D35).
"""

from __future__ import annotations

import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from azurkit.core.xbr.nodes import XbrStructuralError
from azurkit.core.xbr.nodes import (
    TOC_ROW_SIZE,
    TOC_START,
    named_resources,
    parse_toc,
    runs,
)

PAGE = 0x1000

# Header words (byte offsets) that hold a trailer offset.
_TRAILER_FIELDS = (0x18, 0x20, 0x28, 0x30, 0x34)


@dataclass(frozen=True)
class NewResource:
    """A resource to add: the archive's own ``name`` for it (lower
    case, as the engine looks names up: 0xA5B10 lowercases a key; ``None``
    for an entry with no named row), its ``tag`` (one the archive already
    holds, so its per-tag row exists), its ``payload`` and ``relocs``, the
    offsets in it of the u32 fields that hold a TOC index (each already the
    final index: a new entry's is the archive's count plus its place among
    the new ones)."""

    name: str | None
    tag: str
    payload: bytes
    relocs: tuple[int, ...] = ()


def _up(n: int) -> int:
    return -(-n // PAGE) * PAGE


def check_key(key: str) -> None:
    """Refuse a key the engine can't look up: not lower-case ASCII, or
    holding a NUL."""
    if not key or not key.isascii() or "\0" in key or key != key.lower():
        raise XbrStructuralError(
            f"{key!r}: a resource key must be non-empty lower-case ASCII "
            f"with no NUL (0xA5B10 lowercases every lookup)")


def _trailer(data) -> list[int]:
    """The header's 15 words, once the trailer is checked to be laid out
    as vanilla's."""
    h = list(struct.unpack_from("<15I", data, 0))
    named_end = h[12] + 8 * h[11]
    if not (h[6] <= h[8] <= h[10] <= h[12] and named_end <= h[13]
            and h[13] + h[14] <= len(data) and h[8] == h[6] + 8 * h[5]
            and h[10] == h[8] + 4 * h[7]):
        raise XbrStructuralError(
            "the trailer isn't laid out as vanilla's: per-tag rows, "
            "relocations, 12-byte records, named rows, then the name pool")
    return h


def rewrite_payloads(data: bytes, rewrite: Mapping[int, bytes], *,
                     relocated: Mapping[int, Sequence[int]] | None = None) -> bytes:
    """``data`` with each payload of ``rewrite`` ({TOC index: payload})
    in its entry's place (Step 2.154).  One that outgrows the slack
    before the next payload (in file order) moves that payload and every
    later one by the fewest whole pages that make room; the trailer
    follows the last.  Where the next payload isn't page-aligned it
    shares the grown one's load run (the run builder 0xA4C00 loads it
    with the page-aligned entry its page starts, :func:`~azurik_mod.xbr.toc_scan.runs`),
    and moved a page on it would load in no run; so (Step 2.158) it moves
    to the first page start after the grown payload, a new run's head,
    and the rest of its old page follows it (:func:`_repage`: at their old
    distances where their alignment holds, else each at its own), every
    later payload moving by whole pages; the result's runs are checked
    (every entry in one, each re-paged entry a head).  Each moved entry's
    TOC offset and every relocation entry inside a moved payload move by
    its delta.  A payload
    of ``relocated`` ({TOC index: offsets in the new payload}) takes
    those relocated fields in place of its old ones (each 4-aligned,
    inside it, holding a TOC index below the count); every other
    rewritten payload must keep each relocated field at its offset with
    its value.  Bytes of an old payload past its new end become zeros;
    the slack between payloads is kept.  Returns ``data`` unchanged when
    ``rewrite`` is empty."""
    if not rewrite:
        return data
    relocated = dict(relocated or {})
    toc = parse_toc(data)
    h = _trailer(data)
    count, ds, trailer = h[3], h[4], h[6]
    for index in (*rewrite, *relocated):
        if not 0 <= index < count:
            raise XbrStructuralError(
                f"rewrite: TOC index {index} is outside the {count} entries")
    for index in relocated:
        if index not in rewrite:
            raise XbrStructuralError(
                f"rewrite: TOC entry {index}'s relocations change but its payload isn't rewritten")
    order = sorted(range(count), key=lambda i: (toc[i].rel_offset, toc[i].size > 0, i))
    for a, b in zip(order, order[1:]):
        if toc[a].rel_offset + toc[a].size > toc[b].rel_offset and toc[a].size:
            raise XbrStructuralError(f"TOC entries {a} and {b} overlap: no layout to grow")
    relocs = struct.unpack_from(f"<{h[7]}I", data, h[8])
    owner = {}
    for r in relocs:
        k = _owner(toc, order, r)
        if k is None:
            raise XbrStructuralError(f"relocation entry 0x{r:X} lies in no payload")
        owner.setdefault(k, []).append(r)
    for index, payload in rewrite.items():
        e = toc[index]
        if index in relocated:
            for off in relocated[index]:
                if off % 4 or not 0 <= off <= len(payload) - 4:
                    raise XbrStructuralError(
                        f"rewrite of TOC entry {index}: relocated field +0x{off:X} isn't a 4-aligned field "
                        f"inside its {len(payload)} B")
                if not struct.unpack_from("<I", payload, off)[0] < count:
                    raise XbrStructuralError(
                        f"rewrite of TOC entry {index}: relocated field +0x{off:X} holds no TOC index")
            continue
        for r in owner.get(index, ()):
            if (payload[r - e.rel_offset:r - e.rel_offset + 4]
                    != data[ds + r:ds + r + 4]):
                raise XbrStructuralError(
                    f"rewrite of TOC entry {index}: the relocated field at "
                    f"payload+0x{r - e.rel_offset:X} changes or is cut off")

    # the new layout: each payload's segment (it and the slack after it) grows by whole pages where it must;
    # one that outgrows a page it shares re-pages the entries after it in that page (Step 2.158)
    toc_rows = bytearray(data[TOC_START:TOC_START + TOC_ROW_SIZE * count])
    pieces = [(0, bytes(data[ds:ds + toc[order[0]].rel_offset]))] if order else []
    shift, moved, repaged = 0, {}, []
    n = 0
    while n < len(order):
        i = order[n]
        e = toc[i]
        last = n + 1 == len(order)
        stop = trailer - ds if last else toc[order[n + 1]].rel_offset
        segment = _segment(data, ds, e, stop, rewrite.get(i))
        size = len(rewrite[i]) if i in rewrite else e.size
        at = e.rel_offset + shift
        grow = max(0, size - (stop - e.rel_offset))
        if grow and not last and toc[order[n + 1]].rel_offset % PAGE:
            mates = _page_mates(toc, order, n + 1)
            place, end = _repage(toc, mates, rewrite, at + size)
            pieces.append((at, bytes(segment[:size])))
            moved[i] = at - e.rel_offset
            for k, m in enumerate(mates):
                mstop = trailer - ds if n + 2 + k >= len(order) else toc[order[n + 2 + k]].rel_offset
                pieces.append((place[m], bytes(_segment(data, ds, toc[m], mstop, rewrite.get(m)))))
                moved[m] = place[m] - toc[m].rel_offset
            repaged.append((i, mates[0]))
            after = n + 1 + len(mates)
            old_after = trailer - ds if after >= len(order) else toc[order[after]].rel_offset
            shift += _up(max(0, end - (old_after + shift)))
            n = after
            continue
        if grow:
            grow = grow if last else _up(grow)
            segment += bytes(stop - e.rel_offset + grow - len(segment))
        moved[i] = shift
        pieces.append((at, bytes(segment)))
        shift += grow
        n += 1
    for i, at in moved.items():
        struct.pack_into("<I", toc_rows, TOC_ROW_SIZE * i, toc[i].rel_offset + at)
        if i in rewrite:
            struct.pack_into("<I", toc_rows, TOC_ROW_SIZE * i + 4, len(rewrite[i]))
    body = bytearray(max((at + len(b) for at, b in pieces), default=0))
    for at, b in pieces:
        body[at:at + len(b)] = b
    body += bytes(_up(len(body)) - len(body))
    new_relocs = []
    for i in order:
        if i in relocated:
            new_relocs += [toc[i].rel_offset + moved[i] + off for off in relocated[i]]
        else:
            new_relocs += [r + moved[i] for r in owner.get(i, ())]
    new_relocs.sort()
    new_trailer = ds + len(body)
    delta = new_trailer - trailer
    hdr = h[:]
    hdr[6] = new_trailer
    hdr[7], hdr[8] = len(new_relocs), h[8] + delta
    grown = 4 * (len(new_relocs) - len(relocs))
    hdr[10], hdr[12], hdr[13] = h[10] + delta + grown, h[12] + delta + grown, h[13] + delta + grown
    out = bytearray(data[:ds])
    out[:0x3C] = struct.pack("<15I", *hdr)
    out[TOC_START:TOC_START + len(toc_rows)] = toc_rows
    out = bytes(out + body + data[trailer:h[8]] + struct.pack(f"<{len(new_relocs)}I", *new_relocs) + data[h[10]:])
    if repaged:   # the run partition the game builds: every entry in one, each re-paged entry a head
        try:
            part = runs(out)
        except ValueError as exc:
            raise XbrStructuralError(f"rewrite: {exc}") from None
        for grown, q in repaged:
            if part.orphans or part.of.get(q) != q:
                raise XbrStructuralError(
                    f"rewrite of TOC entry {grown}: re-paged, TOC entry {q} isn't a load run's head or entry "
                    f"{(part.orphans or (q,))[0]} is in no run")
    return out


def _segment(data, ds: int, e, stop: int, payload: bytes | None) -> bytearray:
    """Entry ``e``'s segment (its payload and the slack up to ``stop``),
    ``payload`` laid over it (the old bytes past it zeros)."""
    segment = bytearray(data[ds + e.rel_offset:ds + stop])
    if payload is not None:
        keep = max(len(payload), e.size)
        segment += bytes(max(0, keep - len(segment)))
        segment[:keep] = payload + bytes(keep - len(payload))
    return segment


def _page_mates(toc, order: list[int], first: int) -> list[int]:
    """``order[first]`` and the entries after it that start in its page
    and aren't page-aligned: the rest of its load run."""
    page = toc[order[first]].rel_offset // PAGE
    mates = [order[first]]
    for i in order[first + 1:]:
        if toc[i].rel_offset % PAGE == 0 or toc[i].rel_offset // PAGE != page:
            break
        mates.append(i)
    return mates


def _repage(toc, mates: list[int], rewrite: Mapping[int, bytes], end: int) -> tuple[dict[int, int], int]:
    """New offsets for ``mates`` (a load run's tail, :func:`_page_mates`)
    after a payload ending at ``end`` that outgrew their page: the first
    at the next page start, a new run's head, each other one at its old
    distance from it where that keeps its alignment (its TOC flags) and
    its place, else at its own alignment after the one before; and where
    the last one ends."""
    head = _up(end)
    place: dict[int, int] = {}
    for m in mates:
        align = max(toc[m].flags, 1)
        at = head + toc[m].rel_offset - toc[mates[0]].rel_offset
        if at % align or at < end:
            at = -(-end // align) * align
        place[m] = at
        end = at + (len(rewrite[m]) if m in rewrite else toc[m].size)
    return place, end


def _owner(toc, order: list[int], rel: int) -> int | None:
    """The TOC entry whose payload holds the data-relative offset ``rel``."""
    lo, hi = 0, len(order)
    while lo < hi:
        mid = (lo + hi) // 2
        if toc[order[mid]].rel_offset <= rel:
            lo = mid + 1
        else:
            hi = mid
    for n in range(lo - 1, -1, -1):
        e = toc[order[n]]
        if e.rel_offset + e.size > rel:
            return e.index
        if e.size:
            return None
    return None


def append_resources(data: bytes, new: Sequence[NewResource] = (), *,
                     rewrite: Mapping[int, bytes] | None = None) -> bytes:
    """``data`` with ``rewrite`` ({TOC index: payload}) laid over
    existing payloads (:func:`rewrite_payloads`) and ``new`` appended
    (module docstring).  With neither it returns ``data`` unchanged."""
    data = rewrite_payloads(data, rewrite or {})
    if not new:
        return data
    toc = parse_toc(data)
    h = _trailer(data)
    count, ds, tag_rows, trailer = h[3], h[4], h[5], h[6]
    named_end = h[12] + 8 * h[11]
    pool_end = h[13] + h[14]
    reloc_end = h[8] + 4 * h[7]
    tag_set = {bytes(data[trailer + 8 * k:trailer + 8 * k + 4])
               for k in range(tag_rows)}
    toc_rows = bytearray(data[TOC_START:TOC_START + TOC_ROW_SIZE * count])
    body = bytearray(data[ds:trailer])

    names = set(named_resources(data).values())
    flags = {}
    for e in toc:
        flags[e.tag] = max(flags.get(e.tag, 0), e.flags)
    sizes = [struct.unpack_from("<I", toc_rows, TOC_ROW_SIZE * k + 4)[0]
             for k in range(count)]
    end = max((e.rel_offset + sizes[e.index] for e in toc), default=0)
    if new:
        body = body[:_up(end)] + bytes(max(0, _up(end) - len(body)))
    rows, pool, new_relocs = bytearray(), bytearray(), []
    new_count = count + len(new)
    for j, res in enumerate(new):
        what = repr(res.name) if res.name is not None else f"new TOC entry {count + j} ({res.tag})"
        if res.name is not None:
            check_key(res.name)
            if res.name in names:
                raise XbrStructuralError(f"{res.name!r}: the archive already "
                                         f"names a resource so")
            names.add(res.name)
        tag = res.tag.encode("ascii")
        if tag not in tag_set:
            raise XbrStructuralError(
                f"{what}: the archive holds no {res.tag!r} resource, "
                f"so it has no per-tag row for it (0xA54F0)")
        at = len(body)
        for off in sorted(set(res.relocs)):
            if off % 4 or not 0 <= off <= len(res.payload) - 4:
                raise XbrStructuralError(
                    f"{what}: relocated field +0x{off:X} isn't a 4-aligned "
                    f"field inside its {len(res.payload)} B")
            if not struct.unpack_from("<I", res.payload, off)[0] < new_count:
                raise XbrStructuralError(
                    f"{what}: relocated field +0x{off:X} holds no TOC index "
                    f"below the {new_count} entries")
            new_relocs.append(at + off)
        body += res.payload + bytes(_up(len(res.payload)) - len(res.payload))
        toc_rows += struct.pack("<II4sI", at, len(res.payload), tag,
                                flags[res.tag])
        if res.name is not None:
            rows += struct.pack("<II", count + j, h[14] + len(pool))
            pool += res.name.encode("ascii") + b"\0"
    body += bytes(_up(len(body)) - len(body))

    new_ds = max(ds, _up(0x40 + TOC_ROW_SIZE * (new_count + 1)))
    delta = new_ds + len(body) - trailer
    out = bytearray(data[:ds]) + bytes(new_ds - ds)
    end_of_toc = TOC_START + len(toc_rows)
    out[TOC_START:end_of_toc] = toc_rows
    if new:                                   # vanilla's zero entry after the last
        out[end_of_toc:end_of_toc + TOC_ROW_SIZE] = bytes(TOC_ROW_SIZE)
    hdr = h[:]
    hdr[3], hdr[4] = new_count, new_ds
    hdr[7] = h[7] + len(new_relocs)
    hdr[11], hdr[14] = h[11] + len(rows) // 8, h[14] + len(pool)
    for field in _TRAILER_FIELDS:
        hdr[field // 4] = h[field // 4] + delta
    for k in (10, 12, 13):                    # past the relocation rows
        hdr[k] += 4 * len(new_relocs)
    hdr[13] += len(rows)                      # the pool follows the new rows
    out[:0x3C] = struct.pack("<15I", *hdr)
    return bytes(out + body + data[trailer:reloc_end]
                 + struct.pack(f"<{len(new_relocs)}I", *new_relocs)
                 + data[reloc_end:named_end] + rows
                 + data[named_end:pool_end] + pool + data[pool_end:])


def relocations(data) -> list[int]:
    """The archive's relocation rows: the data-relative offsets of its u32
    fields that hold a TOC index, as stored (ascending in every vanilla
    archive)."""
    h = struct.unpack_from("<15I", data, 0)
    return list(struct.unpack_from(f"<{h[7]}I", data, h[8]))


def appended(before_count: int, data) -> list[NewResource]:
    """The entries of ``data`` from TOC index ``before_count`` on, each as
    the :class:`NewResource` that appends it again: its name (``None``
    where it has no named row), tag, payload and the offsets of its
    relocated fields."""
    toc, names = parse_toc(data), named_resources(data)
    rows = relocations(data)
    out = []
    for e in toc[before_count:]:
        inside = [r - e.rel_offset for r in rows if e.rel_offset <= r < e.rel_offset + e.size]
        out.append(NewResource(names.get(e.index), e.tag, bytes(data[e.file_offset:e.file_offset + e.size]),
                               tuple(inside)))
    return out


__all__ = ["NewResource", "PAGE", "append_resources", "appended", "check_key", "relocations",
           "rewrite_payloads"]
