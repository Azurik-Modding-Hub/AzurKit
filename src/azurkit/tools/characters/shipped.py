"""The swap's shipped answers (D995, the owner: "why dont we just precompute
all of her?"): a body's size and a character's whole plan at the page's
defaults, per release, made once by ``scripts/record_shipped.py`` from
fresh dresses and read here in place of dressing it again.

:data:`TABLE` (``shipped.json`` beside this module, the recorder's) holds
each answer with what it stands on: the release, the recipe and the
content it reads (:func:`entries`), and for a plan the size the walk and
roll were folded with, the ``default.xbe`` claims of the layers before it
(:func:`taken`) and the sha256 of every staged file the swap read, as
those layers left it (:func:`reads`). One is taken only when all of them
are the build's (the swap is a function of what it reads), so a pack, a
seed, an option or a content update that changes what it would read
misses, and the swap runs.

A size's answer is its number in the row. A plan's is a file in the
content folder beside the entry's recipe (``variants/<id>/shipped/
<release>-<sha12>.azkp``: Azurik-Custom-Content's, installed and checked
with the entry's files, D960), read only when its size and sha256 are its
row's, before a byte of it is decompressed: ``AZKP1``, a JSON head and
each change's bytes, a whole file zstd-compressed against its vanilla file
(a prefix) and inflated to at most the size its head lists (D992's SEC-5
rule); no pickle. Its whole answer's digest (:func:`answer`) is the row's
too, so the answer taken is the one the re-record pin held to a fresh
dress: ``tests/test_characters.py``'s goldens build with :data:`OFF` and
hold each answer they make to its row (:func:`held`), so a change to the
swap's bytes is red until it re-records.

A third kind stands for a part of a dress: a reshape of a body (one slider
moved, D999, or a variant ``from`` her) places its jiggle bones where her
own build at her defaults puts them (``_player_character._parent_places``,
a child's minute of work), and those places are the same for each of her
reshapes, so they ship as a ``places`` row (:func:`places`, a few hundred
bytes), taken where it stands on what they'd read: the release, her recipe,
her content and the staged ``characters.xbr``, so a pack or a Data-tab edit
to it misses (its release, the first that holds the image's file: USA's and
Europe's are one, so one row serves both).

A fourth kind is a Check's part (``part`` rows, Step 4.6p, the Check
design's L3): each part (:mod:`.parts`) a Check of a built-in variant and
of its own copy (New from this) works out at the page's defaults, on each
release, so a first Check of either takes it in place of its dress's
minutes. A part's key is already what it stands on (the bytes and fields
its stage reads, never a name or a folder), so a row is that key, the
part's :func:`~.part_codec.digest` (its ``answer``) and its file
(:func:`part`): ``part_codec``'s bytes (no pickle) in the entry's
``shipped/parts/`` folder, named for their sha256 (a part a re-record
leaves alone keeps its file), read no further than its size and taken
only when its sha256 is the row's.

Each row's floats are its recording host's (:data:`TABLE`'s ``host``,
:func:`host`). Another host's maths may round otherwise and that's close
enough (D1016), so there the pin holds a size and places within
:data:`ULPS` and a plan to what it stands on (:func:`agrees`), and a build
takes them as they are, a body's fresh size close to a shipped one
(:func:`same_size`)."""

from __future__ import annotations

import functools
import hashlib
import json
import platform
import struct
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from azurkit.edits.layer import Change, Claim, Layer

TABLE = Path(__file__).with_name("shipped.json")
"""The rows, ``{"host": ..., "size": [...], "plan": [...], "places": [...], "part": [...]}`` (the recorder's)."""
MAGIC = b"AZKP1\0"
CHARACTERS = "gamedata/characters.xbr"
LEVEL = 19
"""The recorder's zstd level (booblord's 117 MB of changes in about 6.6 MB a release)."""
MAX_HEAD = 16 << 20
"""An answer's JSON head, at most, in bytes (booblord's, a row a change, is about 1.4 MB)."""
OFF = False
"""``True``: no answer is taken from :data:`TABLE`, so every dress is
fresh (``scripts/record_goldens.py`` and ``scripts/record_shipped.py`` set
it, and the tests through the first)."""
SEEN: list | None = None
"""A list: each size, plan, parent's places and dress's part the swap works
out fresh is appended to it, ``{"size": row}``, ``{"plan": row, "found":
(layer, lines, reasons)}``, ``{"places": row}`` or ``{"part": row}`` (the
row it would have, but a part's ``blob``; the recorder's and the pin's)."""
ULPS = 8
"""How many float32 steps apart another host's float may be (D1016: what a dress writes is float32; AZ-833 saw 8)."""
NEAR = 2e-12
"""How far apart two floats near zero may be, in place of :data:`ULPS` (another host's noise on a zero)."""


@functools.cache
def table() -> dict:
    """:data:`TABLE`'s rows, read once a process (none without the file)."""
    return json.loads(TABLE.read_text(encoding="utf-8")) if TABLE.is_file() else {}


def _json(value: object) -> object:
    return json.loads(json.dumps(value))


def entries(recipe: Mapping) -> dict:
    """The installed content ``recipe``'s body reads (``installed.json``'s
    ``{id: {path: sha256}}``): the entry named for its species and for the
    built-in variant whose files it wears (its ``from``), less the shipped
    answers (``/shipped/``) and the entry's recipe (a built-in's own stands,
    ``variants.json``: Install holds this one to its sha, and its title and
    notes are read by no dress), so an Install or Update that changes what it
    reads misses and a new note doesn't."""
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import content as kit

    held, names = kit.installed(), {recipe["species"]}
    if (found := variants.builtins().get(recipe["species"])) is not None and found.files:
        names.add(found.files)
    out = {}
    for name in sorted(names):
        files = held.get(name, {}).get("files") if isinstance(held.get(name), Mapping) else None
        if isinstance(files, Mapping):
            out[name] = {path: sha for path, sha in sorted(files.items())
                         if "/shipped/" not in path and not path.endswith("/variant.json")}
    return out


def taken(before: Sequence[Layer]) -> list:
    """The ``default.xbe`` claims of the layers ``before`` a plan, ``[offset, size, writable]`` in order."""
    from azurkit.tools.characters import XBE

    return sorted([c.offset, c.size, c.writable] for la in before for c in la.claims if c.file == XBE)


def _stood(left: Mapping, release, path: str) -> str | None:
    """The sha256 of ``path`` as the layers before a plan leave it (``left``), else of the release's vanilla file."""
    if path in left:
        return hashlib.sha256(left[path]).hexdigest()
    return release.files.get(path, (None, None))[1]


def reads(staging, release) -> dict[str, str]:
    """Each file a swap's ``staging`` (``ports.IsoStaging``) loaded, by the
    sha256 it had as the layers before it left it (:func:`_stood`)."""
    return {path: _stood(staging._current, release, path) for path in sorted(staging.loaded())}


def size(recipe: Mapping, release) -> float | None:
    """The shipped size of :func:`~azurkit.tools.characters.normalize`'s ``recipe`` on ``release``, or ``None``."""
    if OFF:
        return None
    want = _json(recipe)
    found = [row for row in table().get("size", ()) if row["release"] == release.iso_sha256 and row["recipe"] == want]
    held = entries(recipe) if found else None
    return next((float.fromhex(row["value"]) for row in found if row["entries"] == held), None)


def rows(recipe: Mapping, release, folded: float | None, before: Sequence[Layer]) -> list[dict]:
    """The plan rows of ``recipe`` on ``release`` that stand on this build's
    fold, claims and content (each one's reads still to check, :func:`plan`)."""
    if OFF:
        return []
    want = _json(recipe)
    found = [row for row in table().get("plan", ()) if row["release"] == release.iso_sha256 and row["recipe"] == want]
    if not found:
        return []
    key = {"folded": None if folded is None else float(folded).hex(), "taken": taken(before), "entries": entries(recipe)}
    return [row for row in found if all(row[k] == v for k, v in key.items())]


def plan(found: Sequence[Mapping], release, base: Mapping[str, bytes], staging, root: Path | None = None
         ) -> tuple[Layer, list[str], list[str]] | None:
    """The answer of the first of ``found`` (:func:`rows`) whose every read
    is what the layers before leave (``staging``'s, ``ports.IsoStaging``)
    and whose answer file in ``root`` (the content folder) is its row's and
    decodes to its row's answer (``base``: the vanilla files it was
    compressed against); else ``None`` (the swap runs)."""
    from azurkit.tools.characters import content as kit

    for row in found:
        if any(_stood(staging._current, release, path) != sha for path, sha in row["reads"].items()):
            continue
        if (blob := _blob(row["blob"], root or kit.ROOT)) is None:
            continue
        try:
            answered, digest = _decode(blob, base, row["recipe"])
        except ValueError:   # not an answer this AzurKit reads: the swap runs
            continue
        if digest == row["answer"]:
            return answered
    return None


def _blob(want: Mapping, root: Path) -> bytes | None:
    """The answer file ``want`` (a row's ``blob``) in ``root``, read no
    further than its size: its bytes when they are its size and sha256,
    else ``None``. Nothing is decompressed before this holds."""
    try:
        with open(root / want["path"], "rb") as f:
            data = f.read(want["size"] + 1)
    except OSError:
        return None
    if len(data) != want["size"] or hashlib.sha256(data).hexdigest() != want["sha256"]:
        return None
    return data


_INDEX: list = [None, {}]


def _part_rows(name: str) -> Sequence[Mapping]:
    """:data:`TABLE`'s ``part`` rows of the part ``name``, by name (indexed once a table)."""
    held = table()
    if _INDEX[0] is not held:
        index: dict[str, list] = {}
        for row in held.get("part", ()):
            index.setdefault(row["part"], []).append(row)
        _INDEX[:] = [held, index]
    return _INDEX[1].get(name, ())


def part(name: str, root: Path | None = None) -> bytes | None:
    """The bytes (``part_codec``'s) of the part :mod:`.parts` keeps under
    ``name`` as a row ships them in the content folder ``root`` (its
    :data:`~.content.ROOT`), read no further than the row's size and held
    to its sha256 (:func:`_blob`); ``None`` where no row lists it, none's
    file is there as listed, or :data:`OFF`."""
    from azurkit.tools.characters import content as kit

    if OFF:
        return None
    for row in _part_rows(name):
        if (data := _blob(row["blob"], root or kit.ROOT)) is not None:
            return data
    return None


def heard_part(name: str, part: object, size: int) -> None:
    """Hear a dress's part worked out fresh (:data:`SEEN`): its row but its
    ``blob`` (none for a part the codec doesn't keep: it ships nowhere)."""
    from azurkit.tools.characters import part_codec

    if SEEN is not None:
        try:
            SEEN.append({"part": {"part": name, "answer": part_codec.digest((part, size))}})
        except ValueError:
            pass


def answer(layer: Layer, lines: Sequence[str], reasons: Sequence[str], asked: Mapping,
           digests: Sequence[str] | None = None) -> str:
    """The sha256 of a plan's whole answer to the recipe ``asked``: its layer
    (its recipe's fields but those ``asked`` gives, which the swap only
    copies: the variant's sha; each change's bytes by their sha256,
    ``digests`` when known), its lines and its reasons."""
    digests = digests if digests is not None else [hashlib.sha256(c.after).hexdigest() for c in layer.changes]
    added = {k: v for k, v in layer.recipe.items() if k not in asked}
    return hashlib.sha256(json.dumps(
        [layer.id, layer.tool, layer.kind, added, list(layer.notes),
         [[c.file, c.offset, c.size, c.owner, c.writable] for c in layer.claims],
         [[c.file, c.offset, c.before, c.group, c.whole, len(c.after), d] for c, d in zip(layer.changes, digests)],
         list(lines), list(reasons)], sort_keys=True).encode()).hexdigest()


def _window(prefix: bytes, size: int) -> int:
    return max(20, (len(prefix) + size).bit_length())


def encode(layer: Layer, lines: Sequence[str], reasons: Sequence[str], base: Mapping[str, bytes],
           level: int = LEVEL) -> bytes:
    """A plan's answer as an ``AZKP1`` file: each whole file of ``base``
    zstd-compressed at ``level`` against its vanilla bytes, the rest as
    they are."""
    from compression import zstd

    head, parts = {"layer": {"id": layer.id, "tool": layer.tool, "kind": layer.kind, "recipe": layer.recipe,
                             "notes": list(layer.notes),
                             "claims": [[c.file, c.offset, c.size, c.owner, c.writable] for c in layer.claims]},
                   "lines": list(lines), "reasons": list(reasons), "changes": []}, []
    for c in layer.changes:
        if c.whole and c.file in base:
            options = {zstd.CompressionParameter.compression_level: level,
                       zstd.CompressionParameter.window_log: _window(base[c.file], len(c.after)),
                       zstd.CompressionParameter.enable_long_distance_matching: 1}
            data, enc = zstd.compress(c.after, options=options,
                                      zstd_dict=zstd.ZstdDict(base[c.file], is_raw=True).as_prefix), "zstd-prefix"
        else:
            data, enc = c.after, "raw"
        head["changes"].append({"file": c.file, "offset": c.offset, "before": c.before, "group": c.group,
                                "whole": c.whole, "size": len(c.after), "sha256": hashlib.sha256(c.after).hexdigest(),
                                "enc": enc, "length": len(data)})
        parts.append(data)
    text = json.dumps(head, sort_keys=True).encode()
    return MAGIC + struct.pack("<I", len(text)) + text + b"".join(parts)


def decode(blob: bytes, base: Mapping[str, bytes]) -> tuple[Layer, list[str], list[str]]:
    """An ``AZKP1`` file's answer (``(layer, lines, reasons)``), each change
    inflated to at most the size its head lists and held to its sha256;
    ``ValueError`` names what isn't so."""
    return _decode(blob, base, {})[0]


def _decode(blob: bytes, base: Mapping[str, bytes], asked: Mapping
            ) -> tuple[tuple[Layer, list[str], list[str]], str]:
    """:func:`decode`'s answer and its :func:`answer` to ``asked``."""
    from compression import zstd

    if blob[:len(MAGIC)] != MAGIC or len(blob) < len(MAGIC) + 4:
        raise ValueError("shipped: not an AZKP1 answer")
    n, at = struct.unpack_from("<I", blob, len(MAGIC))[0], len(MAGIC) + 4
    if n > min(MAX_HEAD, len(blob) - at):
        raise ValueError(f"shipped: a head of {n:,} bytes, past the {min(MAX_HEAD, len(blob) - at):,} it may hold")
    try:
        head = json.loads(blob[at:at + n])
        at += n
        changes, digests = [], []
        for c in head["changes"]:
            data = blob[at:at + c["length"]]
            if len(data) != c["length"]:
                raise ValueError(f"shipped: {c['file']}'s bytes end early")
            at += c["length"]
            if c["enc"] == "zstd-prefix":
                prefix = base[c["file"]]
                inflate = zstd.ZstdDecompressor(zstd_dict=zstd.ZstdDict(prefix, is_raw=True).as_prefix, options={
                    zstd.DecompressionParameter.window_log_max: _window(prefix, c["size"])})
                data = inflate.decompress(data, max_length=c["size"])   # never past its listed size (SEC-5)
                if not inflate.eof:
                    raise ValueError(f"shipped: {c['file']} inflates past the {c['size']:,} bytes its head lists")
            elif c["enc"] != "raw":
                raise ValueError(f"shipped: {c['file']}'s encoding {c['enc']!r} is none AzurKit reads")
            if len(data) != c["size"] or (sha := hashlib.sha256(data).hexdigest()) != c["sha256"]:
                raise ValueError(f"shipped: {c['file']}'s bytes aren't the answer's")
            changes.append(Change(c["file"], c["offset"], c["before"], bytes(data), c["group"], c["whole"]))
            digests.append(sha)
        if at != len(blob):
            raise ValueError(f"shipped: {len(blob) - at:,} bytes past its last change")
        la = head["layer"]
        found = (Layer(la["id"], la["tool"], la["kind"], la["recipe"], tuple(changes),
                       tuple(Claim(*c) for c in la["claims"]), tuple(la["notes"])),
                 list(head["lines"]), list(head["reasons"]))
    except (KeyError, TypeError, AttributeError, RecursionError, UnicodeDecodeError, zstd.ZstdError) as exc:
        raise ValueError(f"shipped: not an answer AzurKit reads ({type(exc).__name__})") from None
    return found, answer(*found, asked, digests)


def _places_recipe(body: str, parent) -> dict:
    """What a parent's places are of: ``body``, whose content they read
    (``species``, :func:`entries`') and the sha256 of its mesh and jiggle
    specs by ``repr`` (a zero's sign counts, as ``_body_keys``')."""
    return {"body": body, "species": parent.files or parent.name,
            "spec": hashlib.sha256(repr((parent.mesh, parent.jiggle)).encode()).hexdigest()}


def _places_stood(current: bytes, stored: bytes) -> dict | None:
    """The first release whose ``characters.xbr`` is ``stored`` and the sha256
    of ``current`` (the file a dress was handed, as the layers left it), or
    ``None``: a file of no release."""
    from azurkit.core import gate

    sha = hashlib.sha256(stored).hexdigest()
    release = next((r for r in gate.RELEASES if r.files.get(CHARACTERS, (None, None))[1] == sha), None)
    if release is None:
        return None
    return {"release": release.iso_sha256,
            "reads": {CHARACTERS: sha if current == stored else hashlib.sha256(current).hexdigest()}}


def places(current: bytes, stored: bytes, body: str, parent) -> dict | None:
    """``{role: (origin, sides)}`` of ``parent``'s jiggle bones on ``body``
    from the row that stands on the staged ``current`` over the image's
    ``stored``, ``parent``'s specs and the content they read, or ``None``
    (they're worked out)."""
    if OFF:
        return None
    want = _places_recipe(body, parent)
    if not (found := [row for row in table().get("places", ()) if row["recipe"] == want]):
        return None
    if (stood := _places_stood(current, stored)) is None:
        return None
    held = entries(want)
    for row in found:
        if row["entries"] == held and all(row[k] == v for k, v in stood.items()):
            return {role: (tuple(float.fromhex(x) for x in origin), float.fromhex(sides))
                    for role, (origin, sides) in row["places"].items()}
    return None


def heard_places(current: bytes, stored: bytes, body: str, parent, at: Mapping) -> None:
    """Hear a parent's places worked out fresh (:data:`SEEN`), on a release's file."""
    if SEEN is not None and (stood := _places_stood(current, stored)) is not None:
        want = _places_recipe(body, parent)
        SEEN.append({"places": stood | {"recipe": want, "entries": entries(want), "places": {
            role: [[float(x).hex() for x in origin], float(sides).hex()] for role, (origin, sides) in at.items()}}})


def size_row(recipe: Mapping, release, value: float) -> dict:
    """The row a size of ``recipe`` on ``release`` is shipped under."""
    return {"release": release.iso_sha256, "recipe": _json(recipe), "entries": entries(recipe),
            "value": float(value).hex()}


def plan_row(recipe: Mapping, release, folded: float | None, before: Sequence[Layer], found, staging) -> dict:
    """The row (but its ``blob``) a plan's answer ``found`` of ``recipe`` on
    ``release`` is shipped under, what it stood on read from ``staging``."""
    return {"release": release.iso_sha256, "recipe": _json(recipe),
            "folded": None if folded is None else float(folded).hex(), "taken": taken(before),
            "entries": entries(recipe), "reads": reads(staging, release), "answer": answer(*found, recipe)}


def heard_size(recipe: Mapping, release, value: float) -> None:
    if SEEN is not None:
        SEEN.append({"size": size_row(recipe, release, value)})


def heard_plan(recipe: Mapping, release, folded: float | None, before: Sequence[Layer], found, staging) -> None:
    if SEEN is not None:
        SEEN.append({"plan": plan_row(recipe, release, folded, before, found, staging), "found": found})


KEYS = {"size": ("release", "recipe", "entries"), "plan": ("release", "recipe", "folded", "taken", "entries", "reads"),
        "places": ("release", "recipe", "entries", "reads"), "part": ("part",)}
"""What a row stands on, by kind (the rest is its answer; a part's key is what its stage reads)."""
ANSWERS = {"size": "value", "plan": "answer", "places": "places", "part": "answer"}
SLIDERS = ("scale", "attack_reach", "attack_damage", "attack_speed", "jiggle_strength", "jiggle_stiffness")
"""The recipe's multipliers: at 1.0 one is as if not given (the page leaves it out; Modkit's flags, the goldens',
give it)."""


def _page(recipe: Mapping) -> dict:
    """``recipe`` as the page asks it: each of :data:`SLIDERS` at 1.0 left out."""
    return {k: v for k, v in recipe.items() if not (k in SLIDERS and v == 1.0)}


def name(kind: str, row: Mapping) -> str:
    """How a message names a row: ``plan of {"species": "booblord"} on usa``, ``part W24:0123456789ab``."""
    from azurkit.core import gate

    if kind == "part":
        stage, _, key = row["part"].rpartition(":")
        return f"part {stage}:{key[:12]}"
    release = next((r.name for r in gate.RELEASES if r.iso_sha256 == row["release"]), row["release"][:12])
    return f"{kind} of {json.dumps(row['recipe'], sort_keys=True)} on {release}"


@functools.cache
def host() -> str:
    """Whose float maths this process does: its OS, its CPU and numpy's BLAS."""
    import numpy as np

    blas = np.show_config(mode="dicts").get("Build Dependencies", {}).get("blas", {}).get("name", "")
    return f"{sys.platform}-{platform.machine()}-{blas}"


def near(a: float, b: float) -> bool:
    """Whether two floats are as close as another host's float maths leaves
    them (D1016): at most :data:`ULPS` float32 steps apart, or :data:`NEAR` where they're about zero."""
    if abs(a - b) <= NEAR:
        return True
    x, y = struct.unpack("<2i", struct.pack("<2f", a, b))
    return abs(x - y) <= ULPS


def same_size(fresh: float, folded: float) -> bool:
    """Whether a dressed body's ``fresh`` size is the ``folded`` one its build
    needs (D35): equal; off the table's recording host, whose number a shipped one is, close enough."""
    return fresh == folded or (table().get("host") != host() and near(fresh, folded))


def _floats(answer: object) -> list[float]:
    """The floats of a row's size or places, in order."""
    if isinstance(answer, str):
        return [float.fromhex(answer)]
    if isinstance(answer, Mapping):
        return [x for role in sorted(answer) for x in _floats(answer[role])]
    return [x for part in answer for x in _floats(part)]


def agrees(kind: str, row: object, fresh: object, exact: bool) -> bool:
    """Whether a row's answer ``row`` holds the ``fresh`` one: equal on the
    recording host (``exact``); off it (D1016) a plan's or a part's digest,
    the recording host's bytes, says nothing and a size's or places' roles are
    equal and its floats :func:`near` (:data:`ULPS`)."""
    if exact or row == fresh:
        return row == fresh
    if kind in ("plan", "part"):
        return True
    if kind == "places" and sorted(row) != sorted(fresh):
        return False
    return all(near(a, b) for a, b in zip(_floats(row), _floats(fresh), strict=True))


def held(seen: Mapping, rows_: Mapping | None = None) -> tuple[list[str], list[str]]:
    """What the table (``rows_``, else :func:`table`'s) makes of a fresh
    answer ``seen`` (one of :data:`SEEN`'s): the rows that stand on what it
    stood on and hold its answer (by :func:`name`, :func:`agrees`), and a
    fault for each such row whose answer isn't it (stale: re-record), a
    recipe that gives a slider at 1.0 standing for the page's (:func:`_page`:
    the goldens' recipes give them, and dress the same)."""
    kind = next(k for k in KEYS if k in seen)
    fresh, good, stale = seen[kind] | ({"recipe": _page(seen[kind]["recipe"])} if "recipe" in seen[kind] else {}), [], []
    rows_ = rows_ if rows_ is not None else table()
    for row in rows_.get(kind, ()):
        if all(row[k] == fresh[k] for k in KEYS[kind]):
            if agrees(kind, row[ANSWERS[kind]], fresh[ANSWERS[kind]], rows_.get("host") == host()):
                good.append(name(kind, row))
            else:
                stale.append(f"the shipped {name(kind, row)} isn't a fresh dress's (scripts/record_shipped.py)")
    return good, stale
