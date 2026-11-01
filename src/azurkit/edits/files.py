"""The mods file's ``files`` recipe (Replace files): files the player picked
on their computer, each standing in whole for one of the image's own, at any
size, planned into one layer (tool ``files``, kind ``put``) that goes after
every other. A group of an earlier layer it shadows (a pack's site, an
``xbr`` operation, a randomizer placement) is dropped whole and named (D28,
``layer.compose``); a file another layer writes whole (the character
layer's) is refused by name, as ``compose`` refuses a second whole writer.

An entry is ``{"path", "sha256", "size"}``: the file's path in the image and
the picked file's sha256 and size, never its bytes, so a recipe, a manifest
and a mods file name it and nothing more. :func:`entry` makes one of the
picked bytes. Refused by name: ``default.xbe`` (the packs' file, planned in
sites and shims against its own layout), ``filelist.txt`` (the build writes
it), ``/azurkit.json`` and ``/azurkit.bin`` (a build's manifest, the build's
too), a path the image hasn't (Replace files adds no file) and a size past
:data:`LARGEST`, the most an image's file holds.

A computer path is never part of a recipe (SEC-11): a recipe read from a
file says which file to pick, and nothing is read until the player picks it
in this session; :func:`plan` takes the picked bytes from its host and opens
nothing. A recipe whose file isn't picked again stops there, by name, as
does a picked file that isn't the one it names (their sizes, never either
sha256). A host checks a computer path with :func:`source` before it reads
one: a network share (``\\\\host\\share``, ``//host``), a device path
(``\\\\?\\``, ``\\\\.\\``) and macOS's automounter (``/net/``) are refused, so
no path makes the computer contact another.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
from collections.abc import Mapping, Sequence

from azurkit.core.gate import Release
from azurkit.edits import manifest
from azurkit.edits.layer import Change, Layer

TOOL, KIND, LAYER = "files", "put", "files put"
KEYS = ("path", "sha256", "size")
SHA256 = re.compile(r"[0-9a-f]{64}")
LARGEST = 0xFFFF_FFFF   # an image's file's size field is 32 bits (iso.read packs it "<I")
OWNED = {"default.xbe": "the packs' file, planned against its own layout, is never replaced whole",
         "filelist.txt": "the build writes it",
         manifest.JSON: "a build's manifest, which the build writes",
         manifest.BIN: "a build's manifest, which the build writes"}


def entry(path: str, data: bytes) -> dict:
    """The recipe's entry for ``data``, picked to stand in for ``path``."""
    return {"path": path, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def normalize(entries: object) -> list[dict]:
    """``entries`` checked: a list of entries, each with exactly its keys,
    each path once and none the build owns; ``ValueError`` names every one
    that isn't, in one message (D35), never echoing a sha256."""
    if not isinstance(entries, list):
        raise ValueError("recipe: files is a list of {path, sha256, size}")
    failed, seen = [], {}
    for k, item in enumerate(entries, 1):
        where = f"files {k}"
        if not isinstance(item, Mapping):
            failed.append(f"{where}: not an entry ({{path, sha256, size}})")
            continue
        if lost := [key for key in KEYS if key not in item]:
            failed.append(f"{where}: no {', '.join(lost)}")
        if unknown := sorted(set(item) - set(KEYS), key=str):
            failed.append(f"{where}: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(KEYS)})")
        if lost or unknown:
            continue
        path = item["path"]
        if not (isinstance(path, str) and path):
            failed.append(f"{where}: path names no file of the image")
            continue
        where = f"{where} ({path})"
        if why := OWNED.get(path.removeprefix("/").casefold()):
            failed.append(f"{where}: {why}")
        if path in seen:
            failed.append(f"{where}: replaced twice (files {seen[path]} and {k})")
        seen.setdefault(path, k)
        if not (isinstance(item["sha256"], str) and SHA256.fullmatch(item["sha256"])):
            failed.append(f"{where}: sha256 is not 64 lowercase hex digits")
        if type(item["size"]) is not int or item["size"] < 0:
            failed.append(f"{where}: size is not a whole number of bytes from 0")
        elif item["size"] > LARGEST:
            failed.append(f"{where}: {item['size']:,} B is more than an image's file holds ({LARGEST:,} B)")
    if failed:
        raise ValueError("; ".join(failed))
    return [{key: item[key] for key in KEYS} for item in entries]


def plan(entries: Sequence[Mapping], picked: Mapping[str, bytes], release: Release) -> Layer:
    """The layer ``entries`` (:func:`normalize` d) make of ``release``'s
    vanilla files, each the bytes the player picked for its path this
    session (``picked``, by path), whole, planned against the vanilla
    file's sha256 its manifest gives (nothing of the image is read here);
    ``ValueError`` names every entry the image has no file for, whose file
    isn't picked, or whose picked file isn't the one it names, and a file
    picked for a path no entry names (D35)."""
    changes, failed = [], []
    for k, item in enumerate(entries, 1):
        path, where = item["path"], f"files {k} ({item['path']})"
        if path not in release.files:
            failed.append(f"{where}: the {release.label} image has no {path} (Replace files adds no file)")
            continue
        data = picked.get(path)
        if data is None:
            failed.append(f"{where}: its file isn't picked in this session; pick it again ({item['size']:,} B)")
            continue
        if len(data) != item["size"]:
            failed.append(f"{where}: the picked file is {len(data):,} B, not the {item['size']:,} B it names")
            continue
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            failed.append(f"{where}: the picked file isn't the one it names (another sha256)")
            continue
        changes.append(Change(path, 0, release.files[path][1], bytes(data), f"put {path}", whole=True))
    if strays := sorted(set(picked) - {item["path"] for item in entries}):
        failed.append(f"files: a file picked for {', '.join(strays)}, which no entry replaces")
    if failed:
        raise ValueError("; ".join(failed))
    return Layer(LAYER, TOOL, KIND, {"files": [dict(item) for item in entries]}, tuple(changes))


def source(path: str | os.PathLike) -> str:
    """``path``, a computer path a host is about to read a replacement from,
    when it may: ``ValueError`` names a network share, a device path or a
    path under ``/net/`` (SEC-11; the module's docstring). Nothing is
    opened or looked up."""
    text = os.fspath(path)
    flat = text.replace("\\", "/")
    if flat.startswith(("//?/", "//./")):
        raise ValueError(f"{text!r}: a device path (\\\\?\\ or \\\\.\\) is never read; pick a file on this computer")
    if flat.startswith("//"):
        raise ValueError(f"{text!r}: a network share is never read; pick a file on this computer")
    # /net from the root, whichever drive that is on Windows, where abspath would hide it behind this folder's drive
    full = posixpath.normpath(flat if flat.startswith("/") else os.path.abspath(flat).replace("\\", "/")).casefold()
    if full == "/net" or full.startswith("/net/"):
        raise ValueError(f"{text!r}: a path under /net/ (the automounter's other computers) is never read; "
                         f"pick a file on this computer")
    return text
