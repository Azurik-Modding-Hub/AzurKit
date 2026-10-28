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
check (``sdk`` normalizes it).
"""

from __future__ import annotations

import base64
import json
import re
import zlib
from collections.abc import Mapping

from azurkit.core import gate

FORMAT = "azurkit-preset"
SCHEMA_VERSION = 1
PREFIX = "#p="
MAX_ENCODED = 8 * 1024
MAX_INFLATED = 64 * 1024
MAX_DEPTH = 8
KEYS = {"format", "schema_version", "azurkit", "base", "layers", "result"}
LAYER_KEYS = {"tool", "kind", "recipe"}
VERSION = re.compile(r"\d+\.\d+\.\d+[0-9A-Za-z.+-]{0,24}")
SHA256 = re.compile(r"[0-9a-f]{64}")
FILE = re.compile(r"[0-9A-Za-z_.\-/]{1,255}")
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


def _depth(value: object) -> int:
    if isinstance(value, Mapping):
        return 1 + max(map(_depth, value.values()), default=0)
    if isinstance(value, list):
        return 1 + max(map(_depth, value), default=0)
    return 0


def _object(pairs: list[tuple[str, object]]) -> dict:
    if len({k for k, _ in pairs}) != len(pairs):
        raise ValueError("preset: a key given twice")
    return dict(pairs)


def _constant(name: str) -> None:
    raise ValueError(f"preset: {name} is not a finite number")


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
    try:
        preset = json.loads(data.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
    except RecursionError:
        raise ValueError(f"preset: JSON nested deeper than {MAX_DEPTH}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"preset: not JSON ({exc.msg} at {exc.pos})") from None
    except UnicodeDecodeError:
        raise ValueError("preset: not UTF-8") from None
    if _depth(preset) > MAX_DEPTH:
        raise ValueError(f"preset: JSON nested deeper than {MAX_DEPTH}")
    return check(preset)
