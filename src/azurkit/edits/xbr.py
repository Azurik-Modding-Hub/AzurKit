"""The mods file's ``xbr`` recipe (Q268): an ordered list of operations on
the image's XBR files, planned against the vanilla files into one layer
(tool ``data``, kind ``xbr``; the Data tool's, one layer per tool):

- ``{"op": "set", "file", "table", "entity", "prop", "value"}``, with
  ``"col"`` and ``"fill"`` optional: a keyed cell (config.xbr's), by the
  file's own names with D51's spelling aliases (case-blind, ``_`` read as a
  space, ``color_r``/``g``/``b`` for the rows ``R``/``G``/``B``; an exact
  name wins, and a spelling of several names is refused), type-checked per
  cell: a number into a number cell (any finite value, D23, but where the
  game reads the cell as an int32, :data:`INT32`, what it can't hold once
  rounded or truncated, D45), text into a string cell
  (``core.xbr.edits``). ``col`` picks the column by its index where the
  entity names several (else its last); with ``fill`` an empty cell takes
  the value, unless its row holds only the other kind.
- ``{"op": "replace_bytes", "file", "offset", "expected", "value"}``: the
  bytes ``value`` (hex) at ``offset`` of an XBR file, where the vanilla
  file holds ``expected``: their hex, up to 32 B, or ``{"sha256", "size"}``
  (Q225); a file that holds other bytes there is refused.

The operations apply in list order: one that gives a byte an earlier one
wrote another value wins, and the earlier one is dropped whole and reported
(D28, ``layer.compose``). Every refusal names the operation (by its number,
from 1) and why, never game bytes; an unknown key or operation is refused by
name (Q46, Q223). A share link carries ``set`` alone (Q174).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence

from azurkit.core.gate import Release
from azurkit.core.xbr import Document, edits
from azurkit.core.xbr.keyed import Table
from azurkit.edits.layer import Change, Layer

TOOL, KIND, LAYER = "data", "xbr", "data xbr"
KEYS = {"set": ("op", "file", "table", "entity", "prop", "value"),
        "replace_bytes": ("op", "file", "offset", "expected", "value")}
OPTIONAL = {"set": ("col", "fill"), "replace_bytes": ()}
INLINE = 32                                  # the most bytes ``expected`` gives as hex (Q225)
HEX = re.compile(r"(?:[0-9a-fA-F]{2})+")
SHA256 = re.compile(r"[0-9a-f]{64}")
_COLOR = {"color r": "r", "color g": "g", "color b": "b"}
#: config.xbr's cells the game reads as an int32, by table and row name (settings_foo's by setting, its column), and
#: how it makes one: 0xF5A40 truncates; Starting HP's x87 FISTP rounds half to even (D45, D73).
INT32 = {("armor_properties", name): "trunc" for name in ("Level", "Strong protection hp", "Normal protection hp",
                                                          "Cost", "Hits", "Flaps")} | {
    ("critters_damage", "hitPoints"): "trunc", ("damage", "Level"): "trunc", ("damage", "Damage"): "trunc",
    ("damage", "Cost"): "trunc", ("settings_foo", "initial hp"): "round", ("settings_foo", "fall damage 1"): "trunc",
    ("settings_foo", "fall damage 2"): "trunc", ("settings_foo", "fall damage 3"): "trunc"}
WHOLE = {"round": (round, "rounded"), "trunc": (math.trunc, "truncated")}
RANGE = (-2**31, 2**31 - 1)


def _digest(data: bytes) -> str:
    return f"<{len(data)} B, sha256 {hashlib.sha256(data).hexdigest()[:12]}>"


def normalize(ops: object) -> list[dict]:
    """``ops`` checked: a list of operations, each with exactly its keys;
    ``ValueError`` names every one that isn't, in one message (D35)."""
    if not isinstance(ops, list):
        raise ValueError("recipe: xbr is a list of operations ({op: set | replace_bytes, ...})")
    failed = []
    for k, op in enumerate(ops, 1):
        where = f"xbr op {k}"
        if not isinstance(op, Mapping) or not isinstance(op.get("op"), str) or op["op"] not in KEYS:
            failed.append(f"{where}: not an operation (op: set | replace_bytes)")
            continue
        where, keys, optional = f"{where} ({op['op']})", KEYS[op["op"]], OPTIONAL[op["op"]]
        if lost := [key for key in keys if key not in op]:
            failed.append(f"{where}: no {', '.join(lost)}")
        if unknown := sorted(set(op) - set(keys) - set(optional), key=str):
            failed.append(f"{where}: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(keys)})")
        if lost or unknown:
            continue
        if not (isinstance(op["file"], str) and op["file"].startswith("gamedata/") and op["file"].endswith(".xbr")):
            failed.append(f"{where}: file {op['file']!r} is no gamedata/<name>.xbr")
        if op["op"] == "set":
            if not all(isinstance(op[key], str) for key in ("table", "entity", "prop")):
                failed.append(f"{where}: table, entity and prop are names")
            if "col" in op and not (type(op["col"]) is int and op["col"] >= 0):
                failed.append(f"{where}: col {op['col']!r} is not a column's index (a whole number from 0)")
            if "fill" in op and type(op["fill"]) is not bool:
                failed.append(f"{where}: fill {op['fill']!r} is not true or false")
            value = op["value"]
            if isinstance(value, str):
                if not value.isascii() or "\0" in value:
                    failed.append(f"{where}: value {value!r} is not ASCII text without NULs")
            else:
                try:
                    edits.finite(value, f"{where}: value")
                except ValueError as exc:
                    failed.append(str(exc))
            continue
        if type(op["offset"]) is not int or op["offset"] < 0:
            failed.append(f"{where}: offset {op['offset']!r} is not a file offset (a whole number from 0)")
        if not (isinstance(op["value"], str) and HEX.fullmatch(op["value"])):
            failed.append(f"{where}: value is not hex bytes")
            continue
        size, expected = len(op["value"]) // 2, op["expected"]
        if isinstance(expected, str):
            if not (HEX.fullmatch(expected) and len(expected) // 2 == size <= INLINE):
                failed.append(f"{where}: expected is not the hex of the {size} B the value replaces (up to "
                              f"{INLINE} B; past that {{sha256, size}})")
        elif not (isinstance(expected, Mapping) and set(expected) == {"sha256", "size"}
                  and isinstance(expected["sha256"], str) and SHA256.fullmatch(expected["sha256"])
                  and type(expected["size"]) is int and expected["size"] == size):
            failed.append(f"{where}: expected is not {{sha256, size}} of the {size} B the value replaces")
    if failed:
        raise ValueError("; ".join(failed))
    return [dict(op) for op in ops]


def files(ops: Sequence[Mapping]) -> list[str]:
    """The files the operations write, each once, in their order."""
    return list(dict.fromkeys(op["file"] for op in ops))


def _fold(name: str) -> str:
    return name.casefold().replace("_", " ")


def _spelled(names: Sequence[str], given: str, what: str, where: str, aliases: Mapping[str, str] | None = None
             ) -> str:
    """The one of ``names`` that ``given`` spells (D51): itself, else the one
    equal to it case-blind with ``_`` as a space, else its alias's."""
    if given in names:
        return given
    for wanted in (_fold(given), (aliases or {}).get(_fold(given))):
        hits = sorted({n for n in names if _fold(n) == wanted})
        if len(hits) > 1:
            raise LookupError(f"{where}: {what} {given!r} spells several: {', '.join(map(repr, hits))}")
        if hits:
            return hits[0]
    raise LookupError(f"{where} has no {what} {given!r}")


def int32(table: str, entity: str, prop: str) -> str | None:
    """How the game makes an int32 of config.xbr's cell ``table``/``entity``/``prop``
    (:data:`INT32`: ``round`` or ``trunc``), ``None`` where it reads a double."""
    return INT32.get((table, prop)) or INT32.get((table, entity))


def _set(table: Table, data: bytes, op: Mapping) -> tuple[str, list[tuple[int, bytes]]]:
    where = f"{op['file']} table {table.name}"
    entity = _spelled([c for c in table.cols if c], op["entity"], "entity", where)
    prop = _spelled(table.rows, op["prop"], "prop", where, _COLOR)
    value, col, fill = op["value"], op.get("col"), op.get("fill", False)
    if isinstance(value, str):
        writes = edits.set_text(table, data, entity, prop, value, col=col, fill=fill)
    else:
        if how := int32(table.name, entity, prop):
            whole, made = WHOLE[how]
            if not RANGE[0] <= whole(value) <= RANGE[1]:
                raise ValueError(f"config table {table.name} {entity}/{prop}: {value:g} doesn't fit the game's "
                                 f"32-bit integer once {made} ({RANGE[0]}..{RANGE[1]})")
        writes = edits.set_number(table, entity, prop, value, col=col, fill=fill)
    column = f" (column {table.column(entity, col)})" if table.cols.count(entity) > 1 else ""
    return f"set {table.name}/{entity}/{prop}{column}", writes


def plan(ops: Sequence[Mapping], release: Release, base: Mapping[str, bytes]) -> Layer:
    """The layer ``ops`` (:func:`normalize` d) make of ``release``'s vanilla
    files (``base``: each of :func:`files`); ``ValueError`` names every
    operation that can't apply, and why (D35)."""
    changes, failed, documents = [], [], {}
    for k, op in enumerate(ops, 1):
        where, file = f"xbr op {k} ({op['op']})", op["file"]
        if file not in release.files:
            failed.append(f"{where}: the {release.label} image has no {file}")
            continue
        data = base[file]
        try:
            if op["op"] == "set":
                if file not in documents:
                    documents[file] = Document(data)
                tables = documents[file].tables
                if op["table"] not in tables:
                    raise LookupError(f"{file} has no keyed table {op['table']!r}")
                what, writes = _set(tables[op["table"]], data, op)
            else:
                at, after = op["offset"], bytes.fromhex(op["value"])
                if at + len(after) > len(data):
                    raise ValueError(f"0x{at:X}+{len(after)} is past {file}'s {len(data):,} B")
                held, expected = data[at:at + len(after)], op["expected"]
                if (held.hex() != expected.lower() if isinstance(expected, str)
                        else hashlib.sha256(held).hexdigest() != expected["sha256"]):
                    raise ValueError(f"{file} holds {_digest(held)} at 0x{at:X}, not the bytes it expects")
                what, writes = f"replace_bytes {file} 0x{at:X}", [(at, after)]
        except (LookupError, ValueError) as exc:
            failed.append(f"{where}: {str(exc).removeprefix(f'{where}: ')}")
            continue
        changes += [Change(file, at, hashlib.sha256(data[at:at + len(after)]).hexdigest(), after, f"#{k} {what}")
                    for at, after in writes]
    if failed:
        raise ValueError("; ".join(failed))
    return Layer(LAYER, TOOL, KIND, {"ops": [dict(op) for op in ops]}, tuple(changes))
