"""Community packs (D988; D913's "community packs in Patches the same way"):
ready-made setups from Azurik-Custom-Content, data only.

A community pack is an entry of kind ``pack`` in that repository's manifest
(``tools.characters.content``) whose one file, ``packs/<id>/pack.json``
(:data:`PATH`), is a mods file (``edits.preset``) of at most two layers:
the ``mods`` tool's ``packs`` (AzurKit's own packs, with their slider
values) and the ``data`` tool's ``xbr`` (operations on ``gamedata/*.xbr``,
``edits.xbr``). No ``base`` or ``result`` (it is release-free), no
randomizer, character, XBE site, shim or script. :func:`check` holds a
pack.json to that, and :func:`refusal` is the content folder's Install
check of a pack entry (passed in by the sdk: ``tools.characters`` may not
import this tool).

A recipe names the community packs it builds with as ``community``, an
ordered list of ``{"id"[, "sha"]}`` (:func:`normalize`; ``sha`` the first
12 hex digits of its pack.json's sha256, a pin). :func:`resolve` reads each
from the content folder (its ``installed.json`` record and a ``read`` of
the folder's files, both given): installed, untouched since its install
and at the pin, else refused by name, naming what to Install or Update.
A build ticks and sets the built-in packs each names, :func:`merge` d with
the recipe's own (a built-in pack two sources set to other values is
refused by name; equal copies are one; it never unticks a pack), planned
as ordinary pack layers, and adds each pack's game-data edits as its own
layer (:func:`layer`, ``community <id>``) after the packs and the
character, before the player's own ``data xbr``, so a later layer's
overwrite wins and is reported (D28). Every refusal names the pack, the
file or the operation, never bytes."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping, Sequence

from azurkit.core.gate import Release
from azurkit.edits import preset, xbr
from azurkit.edits.layer import Layer
from azurkit.tools import mods

TOOL, KIND = "community", "packs"   # a build's layer of one pack, and a mods file's layer of them all
PATH = "packs/{}/pack.json"
LAYERS = {("mods", "packs"), (xbr.TOOL, xbr.KIND)}
OTHER = {("randomizer", "plan"): "a randomizer's settings travel by its share string",
         ("characters", "characters"): "a character travels as a community variant (the Characters tab)"}
_ID = re.compile(r"[a-z][a-z0-9_]*\Z")
_SHA12 = re.compile(r"[0-9a-f]{12}\Z")


def check(doc: bytes | str | Mapping, where: str = "pack.json") -> dict:
    """``doc`` (a pack.json's text, at most ``preset.MAX_FILE`` bytes, or
    the object) as a community pack: ``{"packs": {pack: {slider: value}},
    "xbr": [operation]}``, its packs normalized (``mods.normalize``: any
    finite value, nothing clamped, D23) and carrying every pack they
    require, its operations normalized (``edits.xbr``: gamedata/*.xbr
    only). ``ValueError`` names, after ``where``, every fault in one
    message (D35)."""
    try:
        if isinstance(doc, (str, bytes)):
            if (doc.encode() if isinstance(doc, str) else doc).lstrip()[:1] != b"{":
                raise ValueError("preset: no JSON object")
            doc = preset.read(doc)
        else:
            doc = preset.check(doc)
    except ValueError as exc:
        raise ValueError(f"{where}: {str(exc).removeprefix('preset: ')}") from None
    failed = [f"a community pack is release-free: no {key}" for key in ("base", "result") if key in doc]
    packs, ops = {}, []
    for la in doc["layers"]:
        at = (la["tool"], la["kind"])
        if at not in LAYERS:
            failed.append(f"no {la['tool']} {la['kind']} layer in a community pack (its: mods packs, data xbr)"
                          + (f": {OTHER[at]}" if at in OTHER else ""))
        elif at == ("mods", "packs"):
            try:
                packs = mods.normalize(la["recipe"])
            except ValueError as exc:
                failed.append(str(exc).removeprefix("recipe: "))
                continue
            failed += [f"{lost}: a community pack carries the packs it needs" for lost in mods.missing(packs)]
        elif set(la["recipe"]) != {"ops"}:
            failed.append("its data xbr layer's recipe is {ops}")
        else:
            try:
                ops = xbr.normalize(la["recipe"]["ops"])
            except ValueError as exc:
                failed.append(str(exc))
    if not failed and not packs and not ops:
        failed.append("a community pack sets a pack or a game-data value")
    if failed:
        raise ValueError(f"{where}: {'; '.join(failed)}")
    return {"packs": packs, "xbr": ops}


def refusal(entry: Mapping, files: Mapping[str, bytes]) -> str | None:
    """Why a content manifest's ``pack`` entry (checked) can't be installed,
    or ``None`` (any other kind is none of this): its one file is
    ``packs/<id>/pack.json``, a community pack (:func:`check`). ``files``
    are what a host fetched, by path (``content.verify``'s)."""
    if entry["kind"] != "pack":
        return None
    path = PATH.format(entry["id"])
    if [f["path"] for f in entry["files"]] != [path]:
        return f"a pack entry's one file is {path}"
    if path not in files:
        return f"{path} wasn't fetched"
    try:
        check(bytes(files[path]), path)
    except ValueError as exc:
        return str(exc)
    return None


def normalize(given: object) -> list[dict]:
    """A recipe's ``community``: a list of ``{"id"[, "sha"]}``, each id once
    (a manifest entry's: a lower-case identifier), ``sha`` the 12 hex
    digits of its pack.json's sha256; ``ValueError`` names each one that
    isn't, in one message."""
    if not isinstance(given, list):
        raise ValueError("recipe: community is a list of {id, sha}")
    out, failed = [], []
    for k, pin in enumerate(given, 1):
        if not (isinstance(pin, Mapping) and "id" in pin and set(pin) <= {"id", "sha"}):
            failed.append(f"community {k}: not {{id[, sha]}}")
        elif not (isinstance(pin["id"], str) and _ID.match(pin["id"])):
            failed.append(f"community {k}: id {pin['id']!r} is no lower-case identifier")
        elif "sha" in pin and not (isinstance(pin["sha"], str) and _SHA12.match(pin["sha"])):
            failed.append(f"community pack {pin['id']!r}: sha {pin['sha']!r} is no 12 hex digits of its pack.json's")
        elif any(p["id"] == pin["id"] for p in out):
            failed.append(f"community pack {pin['id']!r} is listed twice")
        else:
            out.append(dict(pin))
    if failed:
        raise ValueError("recipe: " + "; ".join(failed))
    return out


def resolve(pins: object, record: Mapping, read: Callable[[str], bytes]) -> list[dict]:
    """Each community pack ``pins`` names (:func:`normalize`), in its order,
    as a build takes it: ``{"id", "version", "sha256", "packs", "xbr"}``,
    read through ``read(path)`` (the content folder's files) where
    ``record`` (its ``installed.json``, ``content.installed``) lists it:
    installed, its pack.json's sha256 still the record's (untouched since
    its install) and at the pin, then :func:`check` ed. ``ValueError`` names
    each one that isn't and what to Install or Update, in one message."""
    out, failed = [], []
    for pin in normalize(pins):
        name, path = pin["id"], PATH.format(pin["id"])
        held = record.get(name) if isinstance(record.get(name), Mapping) else {}
        sha = held["files"].get(path) if isinstance(held.get("files"), Mapping) else None
        if not isinstance(sha, str):
            failed.append(f"community pack {name!r} isn't installed: Install it (the Patches tab's community "
                          f"group, or `azurkit content install {name}`)")
            continue
        if pin.get("sha") not in (None, sha[:12]):
            failed.append(f"community pack {name!r} is pack.json {pin['sha']} there and {sha[:12]} here: Install or "
                          "Update it to the one the recipe was made with")
            continue
        try:
            data = read(path)
        except OSError:
            failed.append(f"community pack {name!r}: {path} is gone from the content folder: Install it again")
            continue
        if (got := hashlib.sha256(data).hexdigest()) != sha:
            failed.append(f"community pack {name!r}: {path} is {got[:12]}, changed since its install ({sha[:12]}): "
                          "Install it again")
            continue
        try:
            found = check(data, f"community pack {name!r}'s {path}")
        except ValueError as exc:
            failed.append(str(exc))
            continue
        out.append({"id": name, "version": held.get("version"), "sha256": sha, **found})
    if failed:
        raise ValueError("; ".join(failed))
    return out


def said(op: Mapping) -> str:
    """A normalized operation in words: a cell by its names and value, a
    ``move`` by its entity and place, a ``replace_bytes`` by its file, size
    and offset, never its bytes."""
    if op["op"] == "set":
        return f"{op['file']}: {op['table']} / {op['entity']} / {op['prop']} = {op['value']}"
    if op["op"] == "move":
        return f"{op['file']}: {op['entity']} moved to {op['x']:g}, {op['y']:g}, {op['z']:g}"
    return f"{op['file']}: {len(op['value']) // 2} bytes at {op['offset']:#x}"


def held(record: Mapping, read: Callable[[str], bytes]) -> list[dict]:
    """Each community pack ``record`` (``installed.json``) lists, by id, as
    the page ticks it: ``{"id", "version", "sha", "packs", "ops"}`` (its
    sha12, its packs' values, :func:`said` of each edit), or ``{"id",
    "version", "refused"}`` where :func:`resolve` refuses it."""
    out = []
    for name in sorted(record):
        files = record[name].get("files") if isinstance(record[name], Mapping) else None
        if not isinstance(files, Mapping) or PATH.format(name) not in files:
            continue
        version = record[name].get("version")
        try:
            pick = resolve([{"id": name}], record, read)[0]
        except ValueError as exc:
            out.append({"id": name, "version": version, "refused": str(exc)})
        else:
            out.append({"id": name, "version": version, "sha": pick["sha256"][:12], "packs": pick["packs"],
                        "ops": [said(op) for op in pick["xbr"]]})
    return out


def _shown(pack: str, slider: str, params: Mapping) -> str:
    value = params.get(slider)
    default = value is None
    if default:
        value = next(s.default for s in mods.PACKS[pack].sliders() if s.name == slider)
    text = f"{value:g}"
    if float(text) != value:   # :g's 6 digits would show two values the same
        text = repr(value).removesuffix(".0")
    return f"{text} (its default)" if default else text


def merge(own: Mapping[str, Mapping], picked: Sequence[Mapping]) -> dict[str, dict]:
    """The packs a build applies: ``own`` (the recipe's, normalized) and
    each ``picked`` community pack's (:func:`resolve` d), in canonical order.
    A built-in pack two sources set (your packs and a community pack, or two
    community packs) must be set the same, else ``ValueError`` names the
    pack, the slider and both sources' values, every one in one message;
    equal copies are one. A community pack only ticks and sets: it never
    unticks one of ``own``."""
    merged = {name: dict(params) for name, params in own.items()}
    by = dict.fromkeys(own, "your packs")
    failed = []
    for pick in picked:
        label = f"community pack {pick['id']}"
        for name, params in pick["packs"].items():
            if name not in merged:
                merged[name], by[name] = dict(params), label
            elif dict(params) != merged[name]:
                failed += [f"{name}'s {s.name}: {label} sets {_shown(name, s.name, params)}, {by[name]} "
                           f"{_shown(name, s.name, merged[name])}: untick one"
                           for s in mods.PACKS[name].sliders() if params.get(s.name) != merged[name].get(s.name)]
    if failed:
        raise ValueError("; ".join(failed))
    return mods.normalize(merged)


def layer(pick: Mapping, release: Release, base: Mapping[str, bytes]) -> Layer:
    """The layer of a :func:`resolve` d community pack: its operations
    planned against ``release``'s vanilla files (``base``, each
    ``xbr.files`` names: ``edits.xbr.plan``) as ``community <id>``, its
    recipe the pack's id, version and pack.json's sha256 (a build's
    manifest carries it so, never its bytes); with no operation, no change
    (the manifest still records it), its plan's notes (a move past
    float32's range, Q110) each naming the pack. ``ValueError`` names the
    pack and each operation that can't apply (D35)."""
    changes, notes = (), ()
    if pick["xbr"]:
        try:
            planned = xbr.plan(pick["xbr"], release, base)
        except ValueError as exc:
            raise ValueError(f"community pack {pick['id']!r}: {exc}") from None
        changes, notes = planned.changes, tuple(f"community pack {pick['id']!r}: {n}" for n in planned.notes)
    return Layer(f"{TOOL} {pick['id']}", TOOL, KIND,
                 {"id": pick["id"], "version": pick["version"], "sha256": pick["sha256"]}, changes, notes=notes)
