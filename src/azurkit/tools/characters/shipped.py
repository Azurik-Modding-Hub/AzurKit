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
swap's bytes is red until it re-records."""

from __future__ import annotations

import functools
import hashlib
import json
import struct
from collections.abc import Mapping, Sequence
from pathlib import Path

from azurkit.edits.layer import Change, Claim, Layer

TABLE = Path(__file__).with_name("shipped.json")
"""The rows, ``{"size": [...], "plan": [...]}`` (the recorder's)."""
MAGIC = b"AZKP1\0"
LEVEL = 19
"""The recorder's zstd level (booblord's 117 MB of changes in about 6.6 MB a release)."""
MAX_HEAD = 16 << 20
"""An answer's JSON head, at most, in bytes (booblord's, a row a change, is about 1.4 MB)."""
OFF = False
"""``True``: no answer is taken from :data:`TABLE`, so every dress is
fresh (``scripts/record_goldens.py`` and ``scripts/record_shipped.py`` set
it, and the tests through the first)."""
SEEN: list | None = None
"""A list: each size and plan the swap works out fresh is appended to it,
``{"size": row}`` or ``{"plan": row, "found": (layer, lines, reasons)}``
(the row it would have; the recorder's and the pin's)."""


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
    answers (``/shipped/``), so an Install or Update that changes what it
    reads misses."""
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import content as kit

    held, names = kit.installed(), {recipe["species"]}
    if (found := variants.builtins().get(recipe["species"])) is not None and found.files:
        names.add(found.files)
    out = {}
    for name in sorted(names):
        files = held.get(name, {}).get("files") if isinstance(held.get(name), Mapping) else None
        if isinstance(files, Mapping):
            out[name] = {path: sha for path, sha in sorted(files.items()) if "/shipped/" not in path}
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


def encode(layer: Layer, lines: Sequence[str], reasons: Sequence[str], base: Mapping[str, bytes]) -> bytes:
    """A plan's answer as an ``AZKP1`` file: each whole file of :data:`base`
    zstd-compressed at :data:`LEVEL` against its vanilla bytes, the rest as
    they are."""
    from compression import zstd

    head, parts = {"layer": {"id": layer.id, "tool": layer.tool, "kind": layer.kind, "recipe": layer.recipe,
                             "notes": list(layer.notes),
                             "claims": [[c.file, c.offset, c.size, c.owner, c.writable] for c in layer.claims]},
                   "lines": list(lines), "reasons": list(reasons), "changes": []}, []
    for c in layer.changes:
        if c.whole and c.file in base:
            options = {zstd.CompressionParameter.compression_level: LEVEL,
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


KEYS = {"size": ("release", "recipe", "entries"), "plan": ("release", "recipe", "folded", "taken", "entries", "reads")}
"""What a row stands on, by kind (the rest is its answer)."""
ANSWERS = {"size": "value", "plan": "answer"}
SLIDERS = ("scale", "attack_reach", "attack_damage", "attack_speed", "jiggle_strength", "jiggle_stiffness")
"""The recipe's multipliers: at 1.0 one is as if not given (the page leaves it out; Modkit's flags, the goldens',
give it)."""


def _page(recipe: Mapping) -> dict:
    """``recipe`` as the page asks it: each of :data:`SLIDERS` at 1.0 left out."""
    return {k: v for k, v in recipe.items() if not (k in SLIDERS and v == 1.0)}


def name(kind: str, row: Mapping) -> str:
    """How a message names a row: ``plan of {"species": "booblord"} on usa``."""
    from azurkit.core import gate

    release = next((r.name for r in gate.RELEASES if r.iso_sha256 == row["release"]), row["release"][:12])
    return f"{kind} of {json.dumps(row['recipe'], sort_keys=True)} on {release}"


def held(seen: Mapping, rows_: Mapping | None = None) -> tuple[list[str], list[str]]:
    """What the table (``rows_``, else :func:`table`'s) makes of a fresh
    answer ``seen`` (one of :data:`SEEN`'s): the rows that stand on what it
    stood on and hold its answer (by :func:`name`), and a fault for each
    such row whose answer isn't it (stale: re-record), a recipe that gives
    a slider at 1.0 standing for the page's (:func:`_page`: the goldens'
    recipes give them, and dress the same)."""
    kind = next(k for k in KEYS if k in seen)
    fresh, good, stale = seen[kind] | {"recipe": _page(seen[kind]["recipe"])}, [], []
    for row in (rows_ if rows_ is not None else table()).get(kind, ()):
        if all(row[k] == fresh[k] for k in KEYS[kind]):
            if row[ANSWERS[kind]] == fresh[ANSWERS[kind]]:
                good.append(name(kind, row))
            else:
                stale.append(f"the shipped {name(kind, row)} isn't a fresh dress's (scripts/record_shipped.py)")
    return good, stale
