"""Modkit's mod files, read as a mods file (Q268): a JSON object of value
edits that Modkit's ``patch --mod`` applied, made into the recipe's ``xbr``
operations (:mod:`.xbr`), in Modkit's order, so ``azurkit build --mods``
and both hosts' Load take one and the Data tab shows what it changes.

- ``patches`` (``[{section, entity, property, value}]``) and ``sections``
  (``{section: {groups...: {entity: {property: value}}}}``, keys starting
  with ``_`` comments, the key a leaf sits under its entity): config.xbr
  cells by the file's own names (D51's spellings), each a number. A name
  registry.json gave another cell until 2026-10-09 is refused, naming the
  cell it wrote (``modkit_retired.json``, Modkit's frozen table: AZ-123,
  AZ-167); ``_keyed_patches`` reaches those cells.
- ``_keyed_patches`` (``{table: {entity: {property: value}}}``, what
  ``mod-template`` writes): config.xbr cells, the same way, no groups.
- ``xbr_edits``: Modkit's edit dicts (``op``, ``xbr_file`` or ``file`` or
  ``filename``, ``section``, ``entity``, ``prop``, ``col``, ``offset``,
  ``value`` with ``value_kind`` ``hex`` for bytes, ``expected`` or Level
  Studio's ``original``, ``fill_empty``, ``label``): ``set_keyed_double``,
  ``set_keyed_string`` and ``point_keyed_string`` are ``set`` (text another
  cell of its table holds is pointed at, where Modkit's ``set_keyed_string``
  rewrote the cell's own slot and refused a shared one: other bytes, every
  cell reading the same; text no other cell holds is rewritten in place,
  which Modkit's ``point_keyed_string`` refused);
  ``replace_bytes`` and ``replace_string_at`` (a NUL-ended ASCII string, NUL
  padded to its old length) are ``replace_bytes``. As in Modkit, each is
  checked against what the mod's earlier edits left (its original may be an
  earlier edit's value; one already holding the new value is applied:
  dropped); its operation's ``expected`` is the vanilla bytes (config.xbr's
  as AzurKit ships it, a level's as the originals name them), and one a
  build would drop part of an earlier edit for (D28) covers both
  (:class:`_Chain`). A file name is
  looked for as Modkit did: in gamedata/, gamedata/index/, then the root.
- ``source_hashes`` (``{file: sha256}``, Level Studio's): each file must
  be a release's vanilla file (only gamedata/index/index.xbr differs
  between USA and Europe, and a mods file's operations replay on either).

``name``, ``author``, ``description``, ``source_dump`` and ``level`` are
metadata; ``level_patches`` (a level's entities moved or renamed by name) is
refused by name, as is any other key and a mod with no edit shape (AZ-215).
A null or empty ``_keyed_patches``, ``xbr_edits``, ``level_patches`` or
``source_hashes`` is none, as Modkit read it.
:func:`edits` gives each edit its label, operation and refusal (a host's
preview shows each); :func:`preset` refuses them all in one message (D35).
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from azurkit.core import gate
from azurkit.core.xbr import edits as cells
from azurkit.edits import preset as presets
from azurkit.edits import xbr

CONFIG = "gamedata/config.xbr"
SHAPES = ("patches", "sections", "_keyed_patches", "xbr_edits")
META = ("name", "author", "description", "source_dump", "source_hashes", "level")
KEYS = (*SHAPES, *META, "level_patches")
ENTRY = ("op", "label", "xbr_file", "file", "filename", "section", "entity", "prop", "col", "offset", "value",
         "value_kind", "expected", "original", "fill_empty")   # Modkit's xbr_edits keys
KEYED = ("set_keyed_double", "set_keyed_string", "point_keyed_string")
BYTES = ("replace_bytes", "replace_string_at")
PATCH = ("section", "entity", "property", "value")
WHERE = "Modkit mod"

Edit = tuple[str, dict | None, str | None]   # a label, its operation (None: nothing to do) and its refusal


def is_mod(doc: object) -> bool:
    """Whether ``doc``, a mods file's JSON object, is one of Modkit's: no
    ``format``, and a key of Modkit's mod files."""
    return isinstance(doc, Mapping) and "format" not in doc and bool(set(doc) & set(KEYS))


@functools.cache
def _retired() -> dict[tuple[str, str, str], list]:
    raw = json.loads(Path(__file__).with_name("modkit_retired.json").read_text(encoding="utf-8"))
    return {tuple(row[:3]): row[3:] for row in raw["names"]}


def retired(section: object, entity: object, prop: object) -> str | None:
    """Why ``section/entity/prop`` in ``patches`` or ``sections`` is refused:
    a retired registry.json name, with the cell it wrote; else ``None``."""
    old = _retired().get((section, entity, prop)) if all(isinstance(n, str) for n in (section, entity, prop)) else None
    if old is None:
        return None
    wrote = (f"{old[0]} column {old[1]} {old[2]!r}, row {old[3]!r} (cell 0x{old[4]:06X})" if len(old) == 5
             else f"the 8 bytes at 0x{old[0] + 8:06X}, no config.xbr cell's value")
    return (f"a retired registry.json name (AZ-123, AZ-167): it wrote {wrote}; sections and patches refuse every "
            "old name, even one config.xbr also uses, so name the cell you mean under _keyed_patches")


def _cell(label: str, section: object, entity: object, prop: object, value: object, legacy: bool) -> Edit:
    label = f"{label} {section}/{entity}/{prop}"
    if not all(isinstance(n, str) for n in (section, entity, prop)):
        return label, None, "section, entity and property are names"
    if legacy and (why := retired(section, entity, prop)):
        return label, None, why
    if why := _number(value):
        return label, None, why
    return label, {"op": "set", "file": CONFIG, "table": section, "entity": entity, "prop": prop, "value": value}, None


def _number(value: object) -> str | None:
    """Why ``value`` is no finite number (a bool, a text, NaN, inf, an integer past a double), else ``None``."""
    try:
        cells.finite(value, "value")
    except ValueError as exc:
        return str(exc)
    return None


def _sections(node: Mapping, path: tuple = ()) -> list[tuple[str, str, str, object]]:
    """Each leaf of ``sections``: (section, entity, property, value), as Modkit's ``flatten_mod`` walked them."""
    out = []
    for key, value in node.items():
        if key.startswith("_"):
            continue
        if isinstance(value, Mapping):
            out += _sections(value, (*path, key))
        else:
            out.append((path[0] if path else key, path[-1] if len(path) > 1 else "", key, value))
    return out


@functools.cache
def _paths() -> dict[str, str]:
    return {path.casefold(): path for release in gate.RELEASES for path in release.files}


def _file(name: object) -> str | None:
    """The image path a Modkit file name means: gamedata/NAME, gamedata/index/NAME, then NAME, case-blind."""
    if not isinstance(name, str) or not name:
        return None
    known = _paths()
    return next((known[p.casefold()] for p in (f"gamedata/{name}", f"gamedata/index/{name}", name)
                 if p.casefold() in known), None)


def _entry(k: int, raw: object, chains: dict[str, _Chain], gid: int) -> Edit:
    """``xbr_edits[k]`` as an operation, ``gid`` its place in the mod's edits."""
    label = f"xbr_edits[{k}]"
    if not isinstance(raw, Mapping):
        return label, None, "not an edit object"
    if unknown := [key for key in raw if key not in ENTRY]:
        return label, None, f"unknown key{'s' * (len(unknown) > 1)} {', '.join(map(repr, unknown))}"
    op, named = raw.get("op"), raw.get("xbr_file") or raw.get("file") or raw.get("filename")
    file = _file(named)
    label = f"{label} ({op} on {named})"
    if op not in (*KEYED, *BYTES):
        return label, None, f"unknown op {op!r} (Modkit's: {', '.join((*KEYED, *BYTES))})"
    if file is None or not file.endswith(".xbr"):
        return label, None, f"no release has an XBR file {named!r} (in gamedata/, gamedata/index/ or the root)"
    expected = raw["expected"] if raw.get("expected") is not None else raw.get("original")
    if expected is not None and op not in BYTES:
        return label, None, f"{op} doesn't check expected"
    fill = raw.get("fill_empty", False)
    if type(fill) is not bool:
        return label, None, f"fill_empty {fill!r} is not true or false"
    if fill and op not in ("set_keyed_double", "point_keyed_string"):
        return label, None, f"{op} doesn't take fill_empty"
    value = raw.get("value")
    hexed = raw.get("value_kind") == "hex"
    if op in KEYED:
        names = [raw.get(key) for key in ("section", "entity", "prop")]
        col = raw.get("col")
        if not all(isinstance(n, str) and n for n in names):
            return label, None, f"{op} needs section, entity and prop"
        if col is not None and not (type(col) is int and col >= 0):
            return label, None, f"col {col!r} is not a column's index"
        if op == "set_keyed_double" and (why := _number(value)):
            return label, None, why
        if op != "set_keyed_double" and (hexed or not isinstance(value, str) or not value.isascii() or "\0" in value):
            return label, None, f"{op} needs ASCII text without NULs"
        made = {"op": "set", "file": file, "table": names[0], "entity": names[1], "prop": names[2], "value": value}
        made |= ({"col": col} if col is not None else {}) | ({"fill": True} if fill else {})
        if file == CONFIG:
            chains[CONFIG].cell(gid, made)
        return label, made, None
    offset = raw.get("offset")
    if type(offset) is not int or offset < 0:
        return label, None, f"offset {offset!r} is not a non-negative integer"
    try:
        if op == "replace_bytes":
            if not (hexed and isinstance(value, str)):
                return label, None, "replace_bytes needs bytes (hex, with value_kind hex)"
            after = bytes.fromhex(value)
            if not after:
                return label, None, "replace_bytes needs at least one byte"
            was = bytes.fromhex(expected) if hexed and isinstance(expected, str) else expected
            if was is not None and not (isinstance(was, bytes) and len(was) == len(after)):
                return label, None, f"expected is not the {len(after)} B the value replaces (hex, with value_kind hex)"
        else:
            if hexed or not isinstance(value, str) or not value.isascii() or "\0" in value:
                return label, None, "replace_string_at needs ASCII text"
            if expected is not None and not (isinstance(expected, str) and expected.isascii() and "\0" not in expected):
                return label, None, "expected is not ASCII text"
    except ValueError:
        return label, None, "value or expected is not hex"
    chain = chains.setdefault(file, _Chain())
    if op == "replace_string_at" and file == CONFIG:   # its slot, as the earlier edits left it, ends at its NUL
        held = chain.now
        end = held.find(b"\0", offset)
        if offset >= len(held) or end < 0:
            return label, None, f"no NUL-ended string at 0x{offset:08X} of {CONFIG}"
        text = held[offset:end].decode("ascii", "replace")
        if text == value:
            return label, None, None
        if expected is not None and text != expected:
            return label, None, f"at 0x{offset:08X} the file holds neither the expected original nor the new value"
        if len(value) > end - offset:
            return label, None, f"{value!r} is longer than the {end - offset + 1} B slot at 0x{offset:08X}"
        after, was = value.encode("ascii").ljust(end + 1 - offset, b"\0"), None
    elif op == "replace_string_at":
        if expected is None:
            return label, None, _UNKNOWN.format(file=file)
        if len(value) > len(expected):
            return label, None, f"{value!r} is longer than the {len(expected) + 1} B slot of {expected!r}"
        was = expected.encode("ascii") + b"\0"
        after = value.encode("ascii").ljust(len(was), b"\0")
    elif file == CONFIG and offset + len(after) > len(chain.now):
        return label, None, f"0x{offset:X}+{len(after)} is past {CONFIG}'s {len(chain.now):,} B"
    return chain.replace(gid, label, file, offset, after, was)


_UNKNOWN = ("no expected or original: AzurKit replaces {file}'s bytes only where it knows what the vanilla file holds "
            "there (give the original bytes)")


class _Chain:
    """An XBR file as a Modkit mod's edits so far leave it in a build.
    Modkit wrote each edit in order over what the earlier ones left and
    checked a byte edit's expected against that; AzurKit's layer plans
    each operation against the vanilla file and drops an earlier one whole
    where a later one gives a byte of it another value (D28,
    ``edits.layer.compose``). So a byte edit is checked against what the
    mod's earlier edits left, and one that would drop bytes of an earlier
    edit it doesn't overwrite is made one ``replace_bytes`` over both, from
    the vanilla bytes to Modkit's. A config.xbr ``set`` counts with the
    writes a build plans for it (``cells``: when the mod has a byte edit).
    config.xbr's bytes are known (``vanilla``, the file AzurKit ships); a
    level's only where an edit's original named them (Q225)."""

    def __init__(self, vanilla: bytes | None = None, cells: bool = False) -> None:
        self.vanilla, self.cells, self.documents = vanilla, cells, {}
        self.van: dict[int, int] = {}   # a level's vanilla bytes an original named
        self.now: bytearray | dict[int, int] = {} if vanilla is None else bytearray(vanilla)   # what a build leaves
        self.holders: dict[int, list[int]] = {}   # a byte -> the edits (their places) whose operation writes it
        self.spans: dict[int, list[tuple[int, int]]] = {}

    def base(self, at: int) -> int | None:
        return self.van.get(at) if self.vanilla is None else self.vanilla[at]

    def held(self, at: int) -> int | None:
        return self.now.get(at, self.van.get(at)) if isinstance(self.now, dict) else self.now[at]

    def _hit(self, writes: list[tuple[int, bytes]]) -> set[int]:
        """The edits whose operation a build drops for ``writes``: each that wrote a byte of them another value."""
        return {g for at, data in writes for i, b in enumerate(data, at) for g in self.holders.get(i, ())
                if self.held(i) != b}

    def _put(self, gid: int, writes: list[tuple[int, bytes]]) -> None:
        for g in self._hit(writes):   # dropped whole: a byte no other edit holds is back to vanilla
            for lo, hi in self.spans.pop(g):
                for i in range(lo, hi):
                    self.holders[i].remove(g)
                    if not self.holders[i]:
                        del self.holders[i]
                        if isinstance(self.now, dict):
                            del self.now[i]
                        else:
                            self.now[i] = self.vanilla[i]
        for at, data in writes:
            for i, b in enumerate(data, at):
                self.now[i] = b
                self.holders.setdefault(i, []).append(gid)
        self.spans[gid] = [(at, at + len(data)) for at, data in writes]

    def cell(self, gid: int, op: Mapping) -> None:
        """A config.xbr ``set``, by the writes a build plans for it (one it refuses, ``tools.data.preview`` names)."""
        if self.cells:
            with contextlib.suppress(LookupError, ValueError):
                self._put(gid, xbr.writes(op, gate.USA, {CONFIG: self.vanilla}, self.documents)[1])

    def replace(self, gid: int, label: str, file: str, offset: int, after: bytes, was: bytes | None) -> Edit:
        """The bytes ``after`` at ``offset``, where Modkit's file held ``was``
        (``None``: anything) or ``after`` already (nothing to do)."""
        span = range(offset, offset + len(after))
        held = [self.held(i) for i in span]
        if was is None and None in held:
            return label, None, _UNKNOWN.format(file=file)
        now = bytes(w if h is None else h for h, w in zip(held, was or after))   # an unknown byte: as its original
        if now == after and None not in held:
            return label, None, None
        if was is not None and now not in (was, after):
            return label, None, f"at 0x{offset:08X} the file holds neither the expected original nor the new value"
        if self.vanilla is None:
            for i, b in zip(span, now):
                self.van.setdefault(i, b)
        writes, hit = [(offset, after)], self._hit([(offset, after)])
        if any(i not in span and not set(self.holders[i]) - hit and self.held(i) != self.base(i)
               for g in hit for lo, hi in self.spans[g] for i in range(lo, hi)):
            lo = min(offset, *(a for g in hit for a, _ in self.spans[g]))
            hi = max(offset + len(after), *(b for g in hit for _, b in self.spans[g]))
            made = bytearray(self.held(i) for i in range(lo, hi))
            made[offset - lo:offset - lo + len(after)] = after
            writes = [(lo, bytes(made))]
        at, data = writes[0]
        self._put(gid, writes)
        return label, _bytes(file, at, data, bytes(self.base(i) for i in range(at, at + len(data)))), None


def _bytes(file: str, offset: int, after: bytes, was: bytes) -> dict:
    expected = was.hex() if len(was) <= xbr.INLINE else {"sha256": hashlib.sha256(was).hexdigest(), "size": len(was)}
    return {"op": "replace_bytes", "file": file, "offset": offset, "expected": expected, "value": after.hex()}


def _hashes(given: object) -> list[str]:
    """Why ``source_hashes`` refuses the mod: a file no release has, or one no release's vanilla file is."""
    if not (isinstance(given, Mapping) and all(isinstance(h, str) for h in given.values())):
        return ["source_hashes must be {file: sha256}"]
    failed = []
    for name, want in given.items():
        if (file := _file(name)) is None:
            failed.append(f"source_hashes: no release has {name!r}")
            continue
        held = {r.files[file][1] for r in gate.RELEASES if file in r.files}
        if want.lower() not in held:
            failed.append(f"source_hashes: {name} is not the file the mod was made from (sha256 "
                          f"{', '.join(sorted(h[:12] for h in held))}, the mod's {want[:12]})")
    return failed


def edits(mod: Mapping, config: bytes) -> list[Edit]:
    """Each edit of Modkit's ``mod``, in the order Modkit applied them
    (``patches``, ``sections``, ``_keyed_patches``, ``xbr_edits``): its
    label, its operation and why it is refused (``config`` is the vanilla
    config.xbr). ``ValueError`` names what refuses the whole mod: a key
    Modkit's mod files don't have, ``level_patches``, no edit shape, a shape
    that isn't one, or ``source_hashes``."""
    failed = []
    if unknown := [str(key) for key in mod if key not in KEYS]:
        failed.append(f"no key {', '.join(map(repr, unknown))} (Modkit's: {', '.join(KEYS)})")
    if mod.get("level_patches"):
        failed.append("level_patches: AzurKit doesn't move or rename a level's entities by name; make each edit an "
                      "xbr_edits replace_bytes with its original")
    elif not any(shape in mod for shape in (*SHAPES, "level_patches")):
        failed.append(f"no edit shape ({', '.join(SHAPES)}); its keys: {', '.join(map(str, mod)) or 'none'}")
    # Modkit read a null or empty _keyed_patches, xbr_edits, level_patches or source_hashes as none
    patches, sections, keyed = mod.get("patches", []), mod.get("sections", {}), mod.get("_keyed_patches") or {}
    if not (isinstance(patches, list) and all(isinstance(p, Mapping) for p in patches)):
        failed.append("patches must be a list of {section, entity, property, value} objects")
    if not isinstance(sections, Mapping):
        failed.append("sections must be an object")
    if not (isinstance(keyed, Mapping) and all(isinstance(rows, Mapping) and all(
            isinstance(props, Mapping) for props in rows.values()) for rows in keyed.values())):
        failed.append("_keyed_patches must be {table: {entity: {property: value}}}")
    if not isinstance(xbr_edits := mod.get("xbr_edits") or [], list):
        failed.append("xbr_edits must be a list of edit objects")
    if mod.get("source_hashes") is not None:
        failed += _hashes(mod["source_hashes"])
    if failed:
        raise ValueError(f"{WHERE}: {'; '.join(failed)}")
    out: list[Edit] = []
    for k, p in enumerate(patches):
        if lost := [key for key in PATCH if key not in p]:
            out.append((f"patches[{k}]", None, f"no {', '.join(lost)}"))
        elif unknown := [str(key) for key in p if key not in PATCH]:
            out.append((f"patches[{k}]", None, f"no key {', '.join(map(repr, unknown))} (its keys: {', '.join(PATCH)})"))
        else:
            out.append(_cell(f"patches[{k}]", p["section"], p["entity"], p["property"], p["value"], True))
    out += [_cell("sections", *leaf, True) for leaf in _sections(sections)]
    out += [_cell("_keyed_patches", section, entity, prop, value, False)
            for section, rows in keyed.items() for entity, props in rows.items() for prop, value in props.items()]
    chain = _Chain(config, cells=any(isinstance(raw, Mapping) and raw.get("op") in BYTES for raw in xbr_edits))
    for gid, (_, op, why) in enumerate(out):
        if op and not why:
            chain.cell(gid, op)
    chains = {CONFIG: chain}
    for k, raw in enumerate(xbr_edits):
        out.append(_entry(k, raw, chains, len(out)))
    return out


def preset(made: list[Edit]) -> dict:
    """The preset of a Modkit mod's edits (:func:`edits`, with a host's own
    checks of their operations): one ``data`` layer of their operations (no
    packs layer: a build applies the packs on by default, as Modkit's
    ``patch`` did, and a host keeps its ticks); ``ValueError`` names every
    refused edit, in one message (D35)."""
    if failed := [f"{label}: {why}" for label, _, why in made if why]:
        raise ValueError(f"{WHERE}: {'; '.join(failed)}")
    return presets.check({"format": presets.FORMAT, "schema_version": presets.SCHEMA_VERSION,
                          "layers": [{"tool": xbr.TOOL, "kind": xbr.KIND,
                                      "recipe": {"ops": xbr.normalize([op for _, op, _ in made if op])}}]})
