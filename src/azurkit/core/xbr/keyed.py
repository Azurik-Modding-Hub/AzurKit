"""config.xbr's keyed tables (the ``tabl`` entries), read and written
back.

A table's payload starts with five little-endian words: its row count;
where its row headers start, from that word (0x10, so at +0x14); its
column count; its cell count (rows x columns); and where its cell grid
starts, from that word (right after the row headers). A row header is
8 bytes: the row name's length, then where the name is, from that field.
The grid holds a 16-byte cell for each row of each column, column by
column: its kind (0 empty, 1 a number, 2 a string), a zero word, then a
double, or a string's length and where it is, from that field. Every
string (the row names and the string cells') ends in a NUL, past the
grid and inside the payload. A column's name is the string its first
row's cell holds; a few tables repeat a column name, and a name then
finds its last column unless an index picks another.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass

EMPTY, NUMBER, STRING = 0, 1, 2
KINDS = {EMPTY: "an empty", NUMBER: "a number", STRING: "a string"}
WORDS = struct.Struct("<5I")    # rows, row headers (from +0x4), columns, cells, grid (from +0x10)
ROW = struct.Struct("<II")      # name length, name (from +4)
CELL = struct.Struct("<II")     # kind, zero; then the double, or the string's length and where it is (from +12)
SIZE = 16
_U32 = 0xFFFFFFFF


@dataclass(frozen=True)
class Cell:
    at: int                          # its 16 bytes' file offset
    kind: int                        # EMPTY, NUMBER or STRING
    value: float | str | None
    text_at: int = 0                 # a string cell's string's file offset


@dataclass(frozen=True)
class Table:
    name: str
    start: int                       # its payload's file offset
    size: int
    words: tuple[int, ...]           # the five header words
    rows: tuple[str, ...]
    row_text: tuple[int, ...]        # each row name's file offset
    cells: tuple[Cell, ...]          # column by column
    cols: tuple[str, ...]            # each column's name: its first row's string

    @classmethod
    def parse(cls, data: bytes, name: str, start: int, size: int) -> Table:
        """The table whose payload is ``data[start:start + size]``;
        ``ValueError`` names what doesn't fit the format."""
        end = start + size

        def within(at: int, n: int, what: str) -> None:
            if not (start <= at and at + n <= end):
                raise ValueError(f"config table {name}: {what} (0x{at:X}, {n} B) is outside its payload")

        def text(field: int, length: int, what: str) -> int:
            at = (field + struct.unpack_from("<I", data, field)[0]) & _U32
            within(at, length + 1, what)
            if data[at + length] != 0:
                raise ValueError(f"config table {name}: {what} at 0x{at:X} has no NUL after its {length} B")
            return at

        within(start, WORDS.size, "its header")
        words = WORDS.unpack_from(data, start)
        n_rows, rows_from, n_cols, n_cells, grid_from = words
        if n_cells != n_rows * n_cols:
            raise ValueError(f"config table {name}: {n_cells} cells, not {n_rows} rows x {n_cols} columns")
        rows_at, grid_at = start + 4 + rows_from, start + 0x10 + grid_from
        within(rows_at, ROW.size * n_rows, "its row headers")
        within(grid_at, SIZE * n_cells, "its cells")
        rows, row_text = [], []
        for r in range(n_rows):
            length = ROW.unpack_from(data, rows_at + ROW.size * r)[0]
            at = text(rows_at + ROW.size * r + 4, length, f"row {r}'s name")
            rows.append(data[at:at + length].decode("latin-1"))
            row_text.append(at)
        cells = []
        for k in range(n_cells):
            at = grid_at + SIZE * k
            kind = CELL.unpack_from(data, at)[0]
            if kind == NUMBER:
                cells.append(Cell(at, kind, struct.unpack_from("<d", data, at + 8)[0]))
            elif kind == STRING:
                length = struct.unpack_from("<I", data, at + 8)[0]
                where = text(at + 12, length, f"cell {k}'s string")
                cells.append(Cell(at, kind, data[where:where + length].decode("latin-1"), where))
            elif kind == EMPTY:
                cells.append(Cell(at, kind, None))
            else:
                raise ValueError(f"config table {name}: cell {k} at 0x{at:X} is of kind {kind}, not 0, 1 or 2")
        cols = tuple(c.value if c.kind == STRING else "" for c in cells[::n_rows]) if n_rows else ("",) * n_cols
        return cls(name, start, size, words, tuple(rows), tuple(row_text), tuple(cells), cols)

    def cell(self, col: int, row: int) -> Cell:
        return self.cells[col * len(self.rows) + row]

    def column(self, entity: str, col: int | None = None) -> int:
        """The column named ``entity``: its last, or ``col`` when that
        column has the name; ``LookupError`` says why there is none."""
        found = [i for i, name in enumerate(self.cols) if name == entity]
        if col is not None:
            if col not in found:
                raise LookupError(f"config table {self.name}: column {col} isn't named {entity!r}")
            return col
        if not found:
            raise LookupError(f"config table {self.name} has no column {entity!r}")
        return found[-1]

    def row(self, prop: str) -> int:
        try:
            return self.rows.index(prop)
        except ValueError:
            raise LookupError(f"config table {self.name} has no row {prop!r}") from None

    def find(self, entity: str, prop: str, col: int | None = None) -> Cell:
        """The cell of column ``entity`` (:meth:`column`) and row ``prop``."""
        return self.cell(self.column(entity, col), self.row(prop))

    def number(self, entity: str, prop: str) -> float | None:
        """The number in ``entity``/``prop``, ``None`` when it is empty;
        ``ValueError`` when it holds a string."""
        cell = self.find(entity, prop)
        if cell.kind == STRING:
            raise ValueError(f"config table {self.name} {entity}/{prop} holds a string, not a number")
        return cell.value

    def refs(self) -> Iterator[tuple[int, int]]:
        """Each reference to a string: ``(its field's file offset, the string's)``."""
        rows_at = self.start + 4 + self.words[1]
        for r, at in enumerate(self.row_text):
            yield rows_at + ROW.size * r + 4, at
        for c in self.cells:
            if c.kind == STRING:
                yield c.at + 12, c.text_at

    def write(self, out: bytearray) -> None:
        """Write the table's header, row headers, cells and strings into
        ``out`` (its archive's bytes), as parsed."""
        WORDS.pack_into(out, self.start, *self.words)
        rows_at = self.start + 4 + self.words[1]
        for r, (name, at) in enumerate(zip(self.rows, self.row_text)):
            raw = name.encode("latin-1")
            field = rows_at + ROW.size * r
            ROW.pack_into(out, field, len(raw), (at - (field + 4)) & _U32)
            out[at:at + len(raw) + 1] = raw + b"\0"
        for c in self.cells:
            if c.kind == NUMBER:
                struct.pack_into("<IId", out, c.at, NUMBER, 0, c.value)
            elif c.kind == STRING:
                raw = c.value.encode("latin-1")
                struct.pack_into("<IIII", out, c.at, STRING, 0, len(raw), (c.text_at - (c.at + 12)) & _U32)
                out[c.text_at:c.text_at + len(raw) + 1] = raw + b"\0"
            else:
                out[c.at:c.at + SIZE] = bytes(SIZE)

