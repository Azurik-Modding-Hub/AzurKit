"""The share preset (WEB §4.2, Q174 narrowing Q59): what replays a build,
and nothing taken from the game.

A preset is the base it was built from (optional), each layer's tool, kind
and recipe, and (optional) the sha256 of each file the build changed::

    {"format": "azurkit-preset", "schema_version": 1, "azurkit": "0.1.0",
     "base": {"kind": "vanilla", "release": "usa", "iso_sha256": "…"},
     "layers": [{"tool": "mods", "kind": "packs", "recipe": {"fps_unlock": {"target_fps": 120}}}],
     "result": {"default.xbe": "…"}}

No changes, claims, bytes or image paths: a rebuild from vanilla with the
same versions is deterministic (D34). :func:`encode` makes the link's
fragment, ``#p=`` and the base64url of its raw deflate; :func:`decode`
reverses it. A fragment is untrusted input, so :func:`decode` caps it (8 KB
encoded, 64 KB inflated, JSON nested at most 8 deep) and refuses, by name,
any key or value the format doesn't have. Each tool's recipe is its own to
check (``sdk`` normalizes it): the ``mods`` tool's ``packs``, the
``data`` tool's ``xbr`` (``{"ops": [...]}``, ``edits.xbr``), the
``randomizer`` tool's ``plan`` (its seed and share string) and the
``characters`` tool's ``characters`` (the body worn: its species or
variant by name, its options, and a variant's recipe sha, never a path)
and the ``community`` tool's ``packs`` (``{"packs": [{"id", "sha"}]}``: the
community packs built with, by id and their pack.json's sha12, never their
bytes, ``tools.mods.community``).

A mods file (Q268, :func:`read`) is a preset, or an AzurKit build's
manifest (its /azurkit.json), whose layers :func:`from_manifest` gathers
into one a tool, as JSON text, or a link.
"""

from __future__ import annotations

import base64
import json
import re
import zlib
from collections.abc import Callable, Mapping

from azurkit.core import gate, jsondepth

FORMAT = "azurkit-preset"
MANIFEST = "azurkit-manifest"
SCHEMA_VERSION = 1
PREFIX = "#p="
MAX_ENCODED = 8 * 1024
MAX_INFLATED = 64 * 1024
MAX_DEPTH = 8
MAX_MOD_DEPTH = 64   # a Modkit mod file's text (its sections nest groups freely): far under json's stack on any platform
MAX_FILE = 16 << 20                 # a mods file's JSON text
KEYS = {"format", "schema_version", "azurkit", "base", "layers", "result"}
LAYER_KEYS = {"tool", "kind", "recipe"}
VERSION = re.compile(r"\d+\.\d+\.\d+[0-9A-Za-z.+-]{0,24}")
SHA256 = re.compile(r"[0-9a-f]{64}")
FILE = re.compile(r"[0-9A-Za-z_.\- /]{1,255}")   # three of USA's files have a space in their names
BASE64URL = re.compile(r"[0-9A-Za-z_-]*")


def check(preset: object) -> dict:
    """``preset`` if it is one, else ``ValueError`` naming the first key or
    value that isn't the format's (its recipes are the tools' to check)."""
    if not isinstance(preset, Mapping):
        raise ValueError("preset: not a JSON object")
    if unknown := sorted(set(preset) - KEYS, key=str):
        raise ValueError(f"preset: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(sorted(KEYS))})")
    if preset.get("format") != FORMAT:
        raise ValueError(f"preset: format is not {FORMAT!r}")
    if type(preset.get("schema_version")) is not int or preset["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"preset: schema_version is not {SCHEMA_VERSION}")
    if "azurkit" in preset and not (isinstance(preset["azurkit"], str) and VERSION.fullmatch(preset["azurkit"])):
        raise ValueError("preset: azurkit is no version")
    if "base" in preset:
        base, releases = preset["base"], {r.name: r for r in gate.RELEASES}
        if not (isinstance(base, Mapping) and set(base) == {"kind", "release", "iso_sha256"}
                and base["kind"] == "vanilla" and isinstance(base["release"], str) and base["release"] in releases
                and base["iso_sha256"] == releases[base["release"]].iso_sha256):
            raise ValueError("preset: base is no release's vanilla image (kind, release, iso_sha256)")
    layers = preset.get("layers")
    if not isinstance(layers, list) or not all(isinstance(la, Mapping) and set(la) == LAYER_KEYS
                                               and isinstance(la["tool"], str) and isinstance(la["kind"], str)
                                               and isinstance(la["recipe"], Mapping) for la in layers):
        raise ValueError(f"preset: layers is a list of {{{', '.join(sorted(LAYER_KEYS))}}}")
    if len({la["tool"] for la in layers}) != len(layers):
        raise ValueError("preset: a tool has two layers")
    if "result" in preset and not (isinstance(preset["result"], Mapping) and all(
            isinstance(k, str) and FILE.fullmatch(k) and isinstance(v, str) and SHA256.fullmatch(v)
            for k, v in preset["result"].items())):
        raise ValueError("preset: result is {file: sha256}")
    return dict(preset)


def encode(preset: Mapping) -> str:
    """``preset`` (:func:`check` ed) as a link's fragment, ``#p=…``."""
    data = json.dumps(check(preset), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    squeeze = zlib.compressobj(9, zlib.DEFLATED, -15)
    text = PREFIX + base64.urlsafe_b64encode(squeeze.compress(data) + squeeze.flush()).rstrip(b"=").decode()
    if len(text) > MAX_ENCODED:
        raise ValueError(f"preset: {len(text)} B as a link, past its {MAX_ENCODED} B")
    return text


def _object(pairs: list[tuple[str, object]]) -> dict:
    if len({k for k, _ in pairs}) != len(pairs):
        raise ValueError("preset: a key given twice")
    return dict(pairs)


def _constant(name: str) -> None:
    raise ValueError(f"preset: {name} is not a finite number")


def _json(data: bytes, depth: int = MAX_DEPTH, pairs: Callable[[list], dict] = _object) -> object:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("preset: not UTF-8") from None
    if jsondepth.deeper(text, depth):   # before json parses it: its own limit differs by platform
        raise ValueError(f"preset: JSON nested deeper than {depth}")
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=_constant)
    except json.JSONDecodeError as exc:
        raise ValueError(f"preset: not JSON ({exc.msg}: line {exc.lineno}, column {exc.colno})") from None


def from_manifest(record: Mapping) -> dict:
    """The preset of an AzurKit build's manifest: its base, AzurKit's
    version, its result, and its layers' recipes, one layer a tool (each
    pack's ``{pack, params}`` into the ``mods`` tool's packs, each community
    pack's ``{id, version, sha256}`` into the ``community`` tool's packs as
    ``{id, sha}``, its sha12, in their order), :func:`check` ed;
    ``ValueError`` names a layer no mods file carries."""
    layers = record.get("layers", [])
    if not (isinstance(layers, list) and all(isinstance(layer, Mapping) for layer in layers)):
        raise ValueError("preset: a manifest's layers is a list of {tool, kind, recipe}")
    packs, ops, plan, character, community, put, failed = {}, None, None, None, [], None, []
    for layer in layers:
        recipe, where = layer.get("recipe"), (layer.get("tool"), layer.get("kind"))
        if where == ("mods", "packs") and isinstance(recipe, Mapping) and isinstance(recipe.get("pack"), str) \
                and isinstance(recipe.get("params"), Mapping) and recipe["pack"] not in packs:
            packs[recipe["pack"]] = dict(recipe["params"])
        elif where == ("data", "xbr") and isinstance(recipe, Mapping) and set(recipe) == {"ops"} and ops is None:
            ops = recipe["ops"]
        elif where == ("randomizer", "plan") and isinstance(recipe, Mapping) and plan is None:
            plan = dict(recipe)
        elif where == ("characters", "characters") and isinstance(recipe, Mapping) and character is None:
            character = dict(recipe)
        elif where == ("community", "packs") and isinstance(recipe, Mapping) and isinstance(recipe.get("id"), str) \
                and isinstance(recipe.get("sha256"), str) and SHA256.fullmatch(recipe["sha256"]) \
                and all(pin["id"] != recipe["id"] for pin in community):
            community.append({"id": recipe["id"], "sha": recipe["sha256"][:12]})
        elif where == ("files", "put") and isinstance(recipe, Mapping) and set(recipe) == {"files"} and put is None:
            put = recipe["files"]
        else:
            failed.append(f"a {layer.get('kind')!r} layer of tool {layer.get('tool')!r}")
    if failed:
        raise ValueError(f"preset: a mods file carries a plan, packs, a character, community packs, xbr and files only, not "
                         f"{', '.join(failed)}")
    base = record.get("base")
    made = {"format": FORMAT, "schema_version": SCHEMA_VERSION,
            "base": {k: base.get(k) for k in ("kind", "release", "iso_sha256")} if isinstance(base, Mapping) else base,
            "layers": ([{"tool": "randomizer", "kind": "plan", "recipe": plan}] if plan is not None else [])
                      + [{"tool": "mods", "kind": "packs", "recipe": packs}]
                      + ([{"tool": "characters", "kind": "characters", "recipe": character}] if character else [])
                      + ([{"tool": "community", "kind": "packs", "recipe": {"packs": community}}] if community else [])
                      + ([{"tool": "data", "kind": "xbr", "recipe": {"ops": ops}}] if ops is not None else [])
                      + ([{"tool": "files", "kind": "put", "recipe": {"files": put}}] if put is not None else []),
            "result": record.get("result")}
    if "azurkit" in record:
        made["azurkit"] = record["azurkit"]
    return check(made)


def parse(given: str | bytes | Mapping, modkit: Callable[[object], bool] | None = None) -> object:
    """A mods file's object: its JSON text parsed within the caps, a link's
    preset (:func:`decode`), or the object given. A text past the caps that
    ``modkit`` takes (one of Modkit's mod files, ``edits.modkit.is_mod``) is
    read as Modkit's ``json`` read it: nested to :data:`MAX_MOD_DEPTH`, a
    key given twice its last value."""
    if not isinstance(given, (str, bytes)):
        return given
    raw = given.encode() if isinstance(given, str) else given
    if len(raw) > MAX_FILE:
        raise ValueError(f"preset: a mods file of {len(raw):,} B, past its {MAX_FILE:,} B")
    if raw.lstrip()[:1] != b"{":
        return decode(raw.decode("utf-8", "replace"))
    try:
        return _json(raw)
    except ValueError as exc:
        if modkit is None:
            raise
        refused = exc
    try:
        found = _json(raw, MAX_MOD_DEPTH, dict)
    except ValueError:
        raise refused from None
    if not modkit(found):
        raise refused from None
    return found


def read(given: str | bytes | Mapping) -> dict:
    """A mods file (:func:`check` ed): a preset or a manifest (as JSON text
    or the object; :func:`from_manifest`), or a link (:func:`decode`)."""
    given = parse(given)
    if isinstance(given, Mapping) and given.get("format") == MANIFEST:
        return from_manifest(given)
    return check(given)


def decode(text: str) -> dict:
    """The preset in a link (or its fragment, ``#p=…``), :func:`check` ed;
    ``ValueError`` names why it is none, and reads no more than the caps."""
    if not isinstance(text, str) or len(text) > MAX_ENCODED + 4096:
        raise ValueError(f"preset: not a link of at most {MAX_ENCODED} B")
    _, found, fragment = text.strip().rpartition(PREFIX)
    if not found or len(PREFIX) + len(fragment) > MAX_ENCODED or not BASE64URL.fullmatch(fragment):
        raise ValueError(f"preset: no {PREFIX} and base64url of at most {MAX_ENCODED} B")
    try:
        raw = base64.urlsafe_b64decode(fragment + "=" * (-len(fragment) % 4))
        inflate = zlib.decompressobj(-15)
        data = inflate.decompress(raw, MAX_INFLATED + 1)
    except (ValueError, zlib.error):
        raise ValueError("preset: the link's data isn't raw deflate") from None
    if len(data) > MAX_INFLATED:
        raise ValueError(f"preset: inflates past {MAX_INFLATED} B")
    if not inflate.eof or inflate.unused_data:
        raise ValueError("preset: the link's data is cut short or runs on")
    return check(_json(data))
