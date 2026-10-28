"""Edits of a keyed table's cells (:mod:`.keyed`), each the writes
``[(file offset, bytes)]`` that make it, planned against the table as it
was parsed and never applied here: a layer carries them
(:mod:`azurkit.edits.layer`). Every cell is 16 bytes, so nothing grows,
and each write stays inside its table's payload. A refusal is a
``ValueError`` (``LookupError`` for a cell the table hasn't) naming the
cell and why, never the file's bytes.

- :func:`set_number`: a number cell's double, any finite value (D23).
- :func:`set_text`: a string cell takes the text by pointing at the first
  string of its table (column by column) that holds it; else, when no
  other reference shares its string, the string is rewritten in place if
  the text fits its slot (its length and the NULs after it, inside its
  table's payload), NUL-padded.

With ``fill``, an empty cell becomes a number or a string cell, unless
its row holds only the other kind (no vanilla row mixes them).
"""

from __future__ import annotations

import math
import struct

from azurkit.core.xbr.keyed import EMPTY, KINDS, NUMBER, STRING, Table

Writes = list[tuple[int, bytes]]


def finite(value: object, what: str) -> float:
    """``value`` as a double; ``ValueError`` naming ``what`` unless it is a finite number."""
    try:
        ok = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:   # an int past a double's range
        ok = False
    if not ok:
        shown = repr(value)
        raise ValueError(f"{what}: {shown if len(shown) <= 40 else shown[:37] + '...'} is not a finite number")
    return float(value)


def _where(table: Table, entity: str, prop: str) -> str:
    return f"config table {table.name} {entity}/{prop}"


def _fill(table: Table, entity: str, prop: str, kind: int) -> None:
    held = {table.cell(c, table.row(prop)).kind for c in range(len(table.cols))}
    if (other := NUMBER + STRING - kind) in held and kind not in held:
        raise ValueError(f"{_where(table, entity, prop)} is empty and its row holds only "
                         f"{KINDS[other].split()[1]}s, so it can't take {KINDS[kind]}")


def set_number(table: Table, entity: str, prop: str, value: float, *, col: int | None = None,
               fill: bool = False) -> Writes:
    """Write ``value`` into the number cell ``entity``/``prop`` (an empty
    one too, with ``fill``)."""
    value = finite(value, _where(table, entity, prop))
    cell = table.find(entity, prop, col)
    if cell.kind == NUMBER:
        return [(cell.at + 8, struct.pack("<d", value))]
    if cell.kind == EMPTY and fill:
        _fill(table, entity, prop, NUMBER)
        return [(cell.at, struct.pack("<IId", NUMBER, 0, value))]
    raise ValueError(f"{_where(table, entity, prop)} is {KINDS[cell.kind]} cell, not a number")


def _slot(data: bytes, at: int, length: int, limit: int) -> int:
    """The bytes a string at ``at`` may fill: its length and the NULs after
    it (an earlier rewrite's padding) up to ``limit``, its table's payload
    end, at least its length and one NUL."""
    end = at + length
    while end < limit and data[end] == 0:
        end += 1
    return max(length + 1, end - at)


def set_text(table: Table, data: bytes, entity: str, prop: str, text: str, *, col: int | None = None,
             fill: bool = False) -> Writes:
    """Give the string cell ``entity``/``prop`` (an empty one too, with
    ``fill``) the text ``text``; ``data`` is the archive's bytes, as
    parsed. Nothing when it holds ``text`` already."""
    where = _where(table, entity, prop)
    if not text.isascii() or "\0" in text:
        raise ValueError(f"{where}: {text!r} is not ASCII text without NULs")
    cell = table.find(entity, prop, col)
    if not (cell.kind == STRING or (cell.kind == EMPTY and fill)):
        raise ValueError(f"{where} is {KINDS[cell.kind]} cell, not a string")
    if cell.kind == STRING and cell.value == text:
        return []
    raw = text.encode("ascii")
    source = next((c for c in table.cells if c.kind == STRING and c.value == text), None)
    if source is not None:
        writes = [(cell.at + 8, struct.pack("<II", len(raw), (source.text_at - (cell.at + 12)) & 0xFFFFFFFF))]
        if cell.kind == EMPTY:
            _fill(table, entity, prop, STRING)
            writes.insert(0, (cell.at, struct.pack("<I", STRING)))
        return writes
    if cell.kind == EMPTY:
        raise ValueError(f"{where}: no cell of the table holds {text!r}, and a new string needs the table to grow")
    slot = _slot(data, cell.text_at, len(cell.value), table.start + table.size)
    if len(raw) + 1 > slot:
        raise ValueError(f"{where}: {text!r} needs {len(raw) + 1} B, and its string's slot holds {slot} B "
                         "(a longer string needs the table to grow)")
    if shared := sum(1 for field, at in table.refs()
                     if field != cell.at + 12 and cell.text_at <= at < cell.text_at + slot):
        raise ValueError(f"{where}: its string is shared with {shared} other reference(s), which a rewrite in "
                         "place would change too")
    return [(cell.text_at, raw + bytes(slot - len(raw))), (cell.at + 8, struct.pack("<I", len(raw)))]
