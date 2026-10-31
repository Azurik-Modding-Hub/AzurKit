"""The Data tool (Modkit's Game Data editor, D151/D262; D986): config.xbr's
18 keyed tables, read from the vanilla file AzurKit ships beside this
module (``config.xbr``: both releases hold it byte for byte), so the Data
tab opens, searches and edits before an image is picked. Each cell carries
its note, unit, range hint, value set and editor from ``schema.json``
beside it (Modkit's notes, by config.xbr's own names).

- :func:`index`: the tables by category and the pickers' lists (critters
  by realm, pickups by kind, armor families, the staff spells), each entry
  with its info rows.
- :func:`view`: one entity's cells of every table that holds it, as
  sections of blocks (:mod:`.views`); :func:`table`: a table as a grid.
- :func:`check`: a cell's edit as the recipe's ``xbr`` ``set`` operation
  (``edits.xbr``), or a ``ValueError`` saying why the cell can't hold it,
  with its type and an example, never game bytes: a number cell takes any
  finite value (D23) but what int32 can't hold where the game reads an
  int32 (D45); a text cell a text another cell of its table holds (it
  points at it) or one that fits its own unshared string; an empty cell a
  number unless its row holds only text, or a text its table holds.

Every call takes the recipe's ``xbr`` operations (``ops``) and shows the
tables as they make them, each changed cell with its vanilla value; the
operations are vanilla-relative (each planned against the vanilla file, as
a mods file replays anywhere), and an edit that would change any other cell
than its own (a string another operation points at or rewrote) is refused.
``written``, a host's spans ``(offset, size)`` of config.xbr that its
ticked packs write, marks the cells they touch (the data edit wins: its
layer is last, D28).
"""

from __future__ import annotations

import functools
import json
import math
import struct
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from azurkit.core import gate
from azurkit.core.xbr import Document
from azurkit.core.xbr.keyed import EMPTY, NUMBER, STRING, Table
from azurkit.edits import xbr
from azurkit.tools.data import views
from azurkit.tools.data.views import CATEGORIES, Block, Noted, Section, Views, format_value

FILE = "gamedata/config.xbr"
HERE = Path(__file__).parent
KIND = {EMPTY: "empty", NUMBER: "number", STRING: "text"}
VIEWS = ("player", "critter", "item", "armor", "weapon")
LABELS = {table: (category, label) for category, tables in CATEGORIES.items() for table, label in tables.items()}
_RESETS = "empty resets it"


@functools.cache
def vanilla() -> bytes:
    """The vanilla config.xbr AzurKit ships."""
    return (HERE / "config.xbr").read_bytes()


@functools.cache
def schema() -> dict:
    return json.loads((HERE / "schema.json").read_text(encoding="utf-8"))


@dataclass(frozen=True)
class _State:
    ops: tuple[dict, ...]          # the operations on config.xbr, normalized
    data: bytes                    # config.xbr as they make it
    now: Mapping[str, Table]
    was: Mapping[str, Table]       # vanilla's
    views: Views


def _entry(table: str, entity: str, prop: str) -> tuple[str, dict]:
    """schema.json's cell of ``table``: by its row's name, else its column's (settings_foo's setting)."""
    cells = schema()["tables"].get(table, {}).get("cells", {})
    name = prop if prop in cells else entity if entity in cells else ""
    return name, cells.get(name, {})


def _default(tables: Mapping[str, Table], ref: views.Ref) -> str | None:
    t = tables[ref[0]]
    entry = _entry(ref[0], t.cols[ref[1]], t.rows[ref[2]])[1]
    return format_value(entry["empty_default"]) if "empty_default" in entry else None


_LAST: dict[str, _State] = {}


def _state(ops: object = ()) -> _State:
    """The tables as ``ops`` (the recipe's ``xbr`` list) make them: their
    operations on config.xbr planned against vanilla and applied; the last
    two asked are kept."""
    mine = tuple(op for op in xbr.normalize(list(ops)) if op["file"] == FILE)
    key = json.dumps(mine, sort_keys=True)
    if (kept := _LAST.get(key)) is not None:
        return kept
    base, was = vanilla(), _vanilla_tables()
    if mine:
        out = bytearray(base)
        for change in xbr.plan(list(mine), gate.USA, {FILE: base}).changes:
            out[change.offset:change.offset + len(change.after)] = change.after
        data = bytes(out)
        now = Document(data).tables
    else:
        data, now = base, was
    state = _State(mine, data, now, was, Views(now, functools.partial(_default, now)))
    if len(_LAST) >= 2:
        _LAST.pop(next(iter(_LAST)))
    _LAST[key] = state
    return state


@functools.cache
def _vanilla_tables() -> Mapping[str, Table]:
    return Document(vanilla()).tables


def _differs(now: Table, was: Table, data: bytes, skip: int = -1) -> bool:
    """Whether a cell of ``now`` (but the one at ``skip``) holds another value than in ``was``."""
    if data[was.start:was.start + was.size] == vanilla()[was.start:was.start + was.size] and skip < 0:
        return False
    return any((a.kind, a.value) != (b.kind, b.value) for a, b in zip(now.cells, was.cells) if a.at != skip)


def _spans(written: Iterable[Sequence[int]]) -> list[tuple[int, int]]:
    return [(int(at), int(at) + int(size)) for at, size in written]


def _touched(cell_at: int, spans: list[tuple[int, int]]) -> bool:
    return any(lo < cell_at + 16 and cell_at < hi for lo, hi in spans)


# -- what a cell shows

def _value_set(state: _State, table: str, row: int, entry: Mapping) -> tuple[str, ...]:
    """Every value schema.json says the cell takes, in order: its
    ``values`` (or the value set they name), each ``values_from`` source's
    (a table's entity names, or the values a row of it holds), then those
    its own row holds; a list cell's split into words."""
    values = entry.get("values", [])
    out = [format_value(float(v)) if isinstance(v, (int, float)) else v
           for v in (schema()["value_sets"].get(values, []) if isinstance(values, str) else values)]
    for source in entry.get("values_from", ()):
        name, _, prop = source.partition("/")
        if (grid := state.views.grid(name)) is not None:
            out += list(grid.cols) if not prop else [
                format_value(c[grid.rows.index(prop)]) for c in grid.cells
                if prop in grid.rows and c[grid.rows.index(prop)] is not None]
    out += [format_value(c[row]) for c in state.views.grid(table).cells if c[row] is not None]
    if entry.get("type") == "list":
        out = [word for v in out for word in v.split()]
    return tuple(dict.fromkeys(v for v in out if v))


def _meta(state: _State, table: str, col: int, row: int) -> dict:
    """The cell's note, type, unit, range hint, default, editor and int32 rule."""
    t = state.was[table]
    entity, prop = t.cols[col], t.rows[row]
    name, entry = _entry(table, entity, prop)
    out: dict = {}
    if how := xbr.int32(table, entity, prop):
        out["int32"] = how
    if not entry:
        return out
    out |= {"name": name, "label": entry["label"], "type": entry["type"], "note": entry["note"]}
    if entry["unit"]:
        out["unit"] = entry["unit"]
    if "range" in entry:
        out["range"] = entry["range"]
    if "empty_default" in entry:
        out["default"] = format_value(entry["empty_default"])
    if entry.get("max_words"):
        out["max_words"] = entry["max_words"]
    if entry.get("yes_no"):
        out["choices"] = {"kind": "yes_no", "values": ["0", "1"]}
    elif kind := {"list": "words", "text": "one"}.get(entry["type"], "one" if "values" in entry else None):
        values = _value_set(state, table, row, entry)
        word = entry.get("empty_default")
        if values and kind == "one" and isinstance(word, str):
            values = (word, *values)
        if values:
            out["choices"] = {"kind": kind, "values": list(values)}
    return out


def _cell(state: _State, ref: views.Ref, spans: list[tuple[int, int]], meta: dict) -> dict:
    table, col, row = ref
    now, was = state.now[table].cell(col, row), state.was[table].cell(col, row)
    out = {"ref": [table, col, row], "kind": KIND[now.kind], "value": now.value, "text": format_value(now.value)}
    if (now.kind, now.value) != (was.kind, was.value):
        out["vanilla"] = format_value(was.value)
    if _touched(now.at, spans):
        out["written"] = True
    key = (table, col, row)
    if key not in meta:
        meta[key] = _meta(state, table, col, row)
    return out | meta[key]


def _shown(item: object, state: _State, spans: list[tuple[int, int]], meta: dict) -> dict | None:
    if item is None:
        return None
    if isinstance(item, Noted):
        return {"read": item.cell, "note": item.note}
    if isinstance(item, str):
        return {"read": item}
    return _cell(state, item, spans, meta)


def _sections(sections: list[Section], state: _State, spans: list[tuple[int, int]]) -> list[dict]:
    meta: dict = {}

    def block(b: Block) -> dict:
        return {"title": b.title, "columns": list(b.columns), "open": b.open,
                "rows": [[label, [_shown(item, state, spans, meta) for item in cells]] for label, cells in b.rows]}
    return [{"title": s.title, "blocks": [block(b) for b in s.blocks]} for s in sections]


# -- the tab's calls

def index(ops: object = ()) -> dict:
    """The tables by category (each its label, size and whether ``ops``
    change it) and the pickers' lists: each critter with its group (realm,
    else body folder), each pickup with its kind, each armor family and
    each staff spell, with the info rows the picker shows."""
    state = _state(ops)
    v = state.views
    changed = {t for t in state.now if _differs(state.now[t], state.was[t], state.data)}
    tables = [{"name": name, "label": label, "category": category, "rows": len(state.was[name].rows),
               "cols": len(state.was[name].cols), "changed": name in changed}
              for category, named in CATEGORIES.items() for name, label in named.items() if name in state.was]
    pickers = {
        "critter": [{"name": n, "group": g, "info": v.critter_info(n)} for n, g in v.critter_groups().items()],
        "item": [{"name": n, "group": g, "info": v.item_info(n)} for n, g in v.items().items()],
        "armor": [{"name": f, "info": v.armor_info(f)} for f in v.armor_families()],
        "weapon": [{"name": s, "label": label, "info": v.weapon_info(s)} for s, label in v.weapons().items()]}
    return {"file": FILE, "tables": tables, "pickers": pickers, "edits": len(state.ops)}


def view(kind: str, name: str | None = None, ops: object = (), written: Iterable[Sequence[int]] = ()) -> dict:
    """One entity's cells (``kind`` one of :data:`VIEWS`; ``name`` its
    critter, pickup, armor family or staff spell; the player has none) as
    ``{kind, name, sections: [{title, blocks: [{title, columns, open, rows:
    [[label, [cell]]]}]}]}``, a cell ``{ref, kind, value, text}`` with
    ``vanilla`` when changed, ``written`` where a ticked pack writes it,
    and its schema's note, type, unit, range, default and choices; a
    read-only one ``{read, note}``."""
    state = _state(ops)
    v = state.views
    if kind == "player":
        sections = v.player_view()
    elif kind in ("critter", "item", "armor", "weapon"):
        known = {"critter": v.critters, "item": lambda: list(v.items()), "armor": lambda: list(v.armor_families()),
                 "weapon": lambda: list(v.weapons())}[kind]()
        if name not in known:
            raise ValueError(f"the Data tab has no {kind} {name!r}")
        sections = {"critter": v.critter_view, "item": v.item_view, "armor": v.armor_view,
                    "weapon": v.weapon_view}[kind](name)
    else:
        raise ValueError(f"the Data tab has no view {kind!r} (its views: {', '.join(VIEWS)})")
    return {"kind": kind, "name": name if kind != "player" else None,
            "sections": _sections(sections, state, _spans(written))}


def table(name: str, ops: object = (), written: Iterable[Sequence[int]] = ()) -> dict:
    """Table ``name`` as a grid: its rows and columns (entities) by name,
    ``cells[col][row]`` (``None`` empty, a number or a text), the cells
    ``ops`` change ``[col, row, vanilla text]``, those a ticked pack writes
    ``[col, row]``, and each row's meta (``rows_meta``; settings_foo's by
    column, ``cols_meta``)."""
    state = _state(ops)
    if name not in state.was:
        raise ValueError(f"config.xbr has no table {name!r}")
    now, was, spans = state.now[name], state.was[name], _spans(written)
    n = len(was.rows)
    category, label = LABELS.get(name, ("", name))
    cells, changed, touched = [], [], []
    for col in range(len(was.cols)):
        cells.append([c.value for c in now.cells[col * n:(col + 1) * n]])
        for row in range(n):
            a, b = now.cell(col, row), was.cell(col, row)
            if (a.kind, a.value) != (b.kind, b.value):
                changed.append([col, row, format_value(b.value)])
            if spans and _touched(a.at, spans):
                touched.append([col, row])
    entries = schema()["tables"].get(name, {}).get("cells", {})
    rows_meta = [_meta(state, name, 0, r) if was.rows[r] in entries else None for r in range(n)]
    cols_meta = ([_meta(state, name, c, min(1, n - 1)) if was.cols[c] in entries else None
                  for c in range(len(was.cols))] if any(c in entries for c in was.cols) else None)
    return {"name": name, "label": label, "category": category, "rows": list(was.rows), "cols": list(was.cols),
            "cells": cells, "changed": changed, "written": touched, "rows_meta": rows_meta, "cols_meta": cols_meta}


def _ref(op: Mapping, tables: Mapping[str, Table]) -> tuple[str, int, int] | None:
    """The cell a ``set`` operation writes, by position, else ``None``."""
    if op["op"] != "set" or op["file"] != FILE or op["table"] not in tables:
        return None
    t = tables[op["table"]]
    try:
        entity = xbr._spelled([c for c in t.cols if c], op["entity"], "entity", "")
        prop = xbr._spelled(t.rows, op["prop"], "prop", "", xbr._COLOR)
        return op["table"], t.column(entity, op.get("col")), t.row(prop)
    except LookupError:
        return None


def _number(text: object) -> float | None:
    if isinstance(text, str):
        try:
            value = float(text.strip())
        except ValueError:
            return None
    elif isinstance(text, (int, float)) and not isinstance(text, bool):
        value = float(text) if not isinstance(text, int) or abs(text) < 2**1023 else math.inf
    else:
        return None
    return value if math.isfinite(value) else None


def check(edit: Mapping, ops: object = ()) -> dict:
    """The edit ``{table, col, row, value}`` (a cell by position, as the
    views and grids give it; ``value`` the typed text or a number) checked
    against the tables ``ops`` make: ``{op, ops}``, its ``set`` operation
    (``None`` when the edit puts the cell back as vanilla: empty text, the
    vanilla value or the word the game reads an empty cell as) and ``ops``
    with the cell's earlier operations dropped and it last.
    ``ValueError`` says why the cell can't hold it."""
    if not (isinstance(edit, Mapping) and set(edit) == {"table", "col", "row", "value"}):
        raise ValueError("an edit is {table, col, row, value}")
    name, col, row, given = edit["table"], edit["col"], edit["row"], edit["value"]
    tables = _vanilla_tables()
    if name not in tables:
        raise ValueError(f"config.xbr has no table {name!r}")
    t = tables[name]
    if not (type(col) is int and type(row) is int and 0 <= col < len(t.cols) and 0 <= row < len(t.rows)):
        raise ValueError(f"config table {name} has no cell at column {col!r}, row {row!r}")
    kept = [op for op in xbr.normalize(list(ops)) if _ref(op, tables) != (name, col, row)]
    op = _op(t, col, row, given)
    if op is None:
        return {"op": None, "ops": kept}
    before, after = _state(kept), _state([*kept, op])
    made = after.now[name].cell(col, row)
    if made.value != op["value"] or _differs(after.now[name], before.now[name], after.data, skip=made.at):
        raise ValueError(f"{t.cols[col]} / {t.rows[row]}: its string is one another edit points at or rewrote, so "
                         "it takes only a text another cell of this table holds")
    return {"op": op, "ops": [*kept, op]}


def _op(t: Table, col: int, row: int, given: object) -> dict | None:
    """The ``set`` operation that puts ``given`` in vanilla's cell (``None``: the cell as vanilla), or why not."""
    entity, prop, was = t.cols[col], t.rows[row], t.cell(col, row)
    entry = _entry(t.name, entity, prop)[1]
    word = entry.get("empty_default") if isinstance(entry.get("empty_default"), str) else None
    if isinstance(given, str) and (not given.strip() or given.strip() == word):
        if given.strip() and was.kind != EMPTY:
            raise ValueError(f"{given.strip()!r} is an empty cell, and AzurKit can't empty a cell the game data "
                             "fills; empty text resets it to the game data's value")
        return None
    held = {t.cell(c, row).kind for c in range(len(t.cols))}
    number = _number(given)
    typed = {"text": STRING, "list": STRING, "number": NUMBER, "int32": NUMBER}.get(entry.get("type"))
    as_text = was.kind == STRING or was.kind == EMPTY and (   # an empty cell: its schema's type, else its row's
        typed == STRING if typed else STRING in held and NUMBER not in held or NUMBER not in held and number is None)
    base = {"op": "set", "file": FILE, "table": t.name, "entity": entity, "prop": prop}
    if t.cols.count(entity) > 1:
        base["col"] = col
    if was.kind == EMPTY:
        base["fill"] = True
    if not as_text:
        return _number_op(t, col, row, given, number, base)
    if not isinstance(given, str):
        raise ValueError(f"{entity} / {prop} holds text, not a number: {_text_hint(t, col, row)}")
    return _text_op(t, col, row, given, entry, base)


def _number_op(t: Table, col: int, row: int, given: object, number: float | None, base: dict) -> dict | None:
    entity, prop, was = t.cols[col], t.rows[row], t.cell(col, row)
    how = xbr.int32(t.name, entity, prop)
    example = format_value(was.value) if was.kind == NUMBER else "1"
    if how:
        whole, made = xbr.WHOLE[how]
        if number is None or not xbr.RANGE[0] <= whole(number) <= xbr.RANGE[1]:
            raise ValueError(f"{entity} / {prop}: a number the game reads as a 32-bit integer ({xbr.RANGE[0]} to "
                             f"{xbr.RANGE[1]}; it {'rounds' if how == 'round' else 'truncates'} a fraction), e.g. "
                             f"{example}. NaN and inf are refused; {_RESETS}.")
    elif number is None:
        raise ValueError(f"{entity} / {prop}: a number (64-bit float), e.g. {example} or -10. NaN and inf are "
                         f"refused; {_RESETS}.")
    if was.kind == NUMBER and struct.pack("<d", number) == struct.pack("<d", was.value):
        return None
    return base | {"value": number}


def _text_hint(t: Table, col: int, row: int) -> str:
    was = t.cell(col, row)
    example = was.value if was.kind == STRING else next(
        (t.cell(c, row).value for c in range(len(t.cols)) if t.cell(c, row).kind == STRING), "")
    return f"text, e.g. {example!r}, or a value another cell of this table holds; {_RESETS}."


def _text_op(t: Table, col: int, row: int, text: str, entry: Mapping, base: dict) -> dict | None:
    entity, prop, was = t.cols[col], t.rows[row], t.cell(col, row)
    where = f"{entity} / {prop}"
    if not text.isascii() or "\0" in text:
        raise ValueError(f"{where}: {_text_hint(t, col, row)} (ASCII, no NULs)")
    if (cap := entry.get("max_words")) and len(text.split()) > cap:
        raise ValueError(f"{where}: at most {cap} words: the game holds {cap} (one more fails its assert)")
    strings = [c.value for c in t.cells if c.kind == STRING]
    if text not in strings and entry.get("type") == "list":   # the same words in another order: the game ORs them
        text = next((s for s in strings if sorted(s.split()) == sorted(text.split())), text)
    if was.kind == STRING and text == was.value:
        return None
    if text in strings:
        return base | {"value": text}
    if was.kind == EMPTY:
        raise ValueError(f"{where} is empty: it takes a text another cell of this table holds, and none holds "
                         f"{text!r} (a new string needs the table to grow)")
    room = _room(t, was)
    if shared := sum(1 for field, at in t.refs() if field != was.at + 12 and was.text_at <= at <= was.text_at + room):
        raise ValueError(f"{where}: this text is shared with {shared} other cell{'s' * (shared > 1)}, so it takes "
                         f"only a value another cell of this table holds, and none holds {text!r}")
    if len(text) > room:
        raise ValueError(f"{where}: text, at most {room} ASCII characters, e.g. {was.value!r}, or a value another "
                         f"cell of this table holds; {_RESETS}.")
    return base | {"value": text}


def _room(t: Table, cell) -> int:
    """How many characters a text cell's string's slot holds (its length and the NULs after it)."""
    data, end = vanilla(), cell.text_at + len(cell.value)
    limit = t.start + t.size
    while end < limit and data[end] == 0:
        end += 1
    return max(len(cell.value) + 1, end - cell.text_at) - 1
