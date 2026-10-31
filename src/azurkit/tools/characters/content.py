"""The content folder: the files a swap reads that Azurik-Custom-Content
carries, not this repository or the wheel (D869, D965: booblord's, optional
extras), and that repository's Install and Update (Step 4.3d, D913: the
Characters tab's community entries):

- ``clips/booblord/``, ``sounds/booblord/``: booblord's own clips and
  voice (the built-in variants', ``_player_variants.CLIPS`` and ``SOUNDS``).

The townsfolk's bare-hands kit (``clips/townsfolk/``, ``_player_kit.KIT``)
and the air elemental's funnel (``fx/air_elemental/``,
``_player_variants.FX_ASSETS``) are our own Blender work too, but ship in
this package beside the swap's modules (D965), so a townsfolk or an air
elemental needs no download.

The swap's modules read the content folder's below :data:`ROOT`: the
folder ``AZURKIT_CONTENT`` names, else ``content`` in the user data folder
(beside the images' links, where the app keeps what it installs). A build
that needs a file the folder lacks fails naming it. What an install copies
is held to Azurik-Custom-Content's own manifest (below), and the builds
that wear booblord to AzurKit's goldens (``tests/goldens/``, Step 4.12c).

**Azurik-Custom-Content** (D966; Azurik-Modding-Hub's at 4.4, D395): a file
has the same path in that repository and in the content folder, and its
``manifest.json`` (:func:`check`) lists each entry: ``{"format":
"azurik-custom-content", "schema_version": 1, "entries": [{"id", "kind"
("variant" or "pack"), "title", "author", "licence", "version" (a whole
number, bumped by any change to its files), "files": [{"path", "sha256",
"size"[, "licence"]}], "requires": [id]}]}``. :func:`install` copies an
entry and those it requires into a content folder from what a host fetched
(a ``fetch(path) -> bytes`` of the source it reads: a URL or a folder, the
app's and the CLI's; the site's worker checks what its page fetched with
:func:`verify`): every file's size and sha256 checked first, nothing written
on a mismatch (D35), then the files moved into place and ``installed.json``
written last. An installed copy stays at its version (pinned) until its
Update, the same install, which also removes the files the new version
dropped. Nothing here opens a network connection."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath

ENV = "AZURKIT_CONTENT"
FORMAT, SCHEMA_VERSION = "azurik-custom-content", 1
MANIFEST, INSTALLED = "manifest.json", "installed.json"
KINDS = ("variant", "pack")
FOLDERS = ("variants", "clips", "sounds", "fx", "packs")
"""The folders an entry's files lie in (a variant's recipe in ``variants/<id>/variant.json``)."""
MAX_MANIFEST, MAX_FILE = 1 << 20, 64 << 20
MAX_ENTRIES, MAX_FILES = 1000, 10000
"""A manifest's entries and its files in all, at most (D992's SEC-6: a small manifest is untrusted input)."""
MAX_ENTRY = 256 << 20
"""An entry's files, and an Install's (the entry and those it requires), at most, in bytes (D992's SEC-9)."""
XISO = b"MICROSOFT*XBOX*MEDIA"
"""An XISO image's media magic (at 0x10000 of an image, and of each of its parts): never content (D960)."""
_ID = re.compile(r"[a-z][a-z0-9_]*\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
ENTRY = ("id", "kind", "title", "author", "licence", "version", "files", "requires")


def root() -> Path:
    """The folder ``AZURKIT_CONTENT`` names, else ``content`` in the user
    data folder; the site's worker (the wheel without its dependencies, so
    no user data folder) reads ``content`` in its working folder."""
    if named := os.environ.get(ENV):
        return Path(named)
    try:
        from platformdirs import user_data_path
    except ImportError:
        return Path("content")
    return user_data_path("AzurKit", appauthor=False) / "content"


ROOT = root()
"""The content folder of this process (:func:`root`, read once)."""


def _path(where: str, value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/") or "//" in value:
        raise ValueError(f"{where}: path {value!r} is no relative POSIX path")
    parts = PurePosixPath(value).parts
    if ".." in parts or "." in parts or len(parts) < 2 or parts[0] not in FOLDERS:
        raise ValueError(f"{where}: path {value!r} isn't a file under {', '.join(f + '/' for f in FOLDERS)}")
    return value


def check(manifest: bytes | str | Mapping) -> dict:
    """``manifest`` (its text, at most :data:`MAX_MANIFEST` bytes, or the
    object) checked and normalized: its format and schema version (another
    is refused by name), each entry's fields (an id unique and an
    identifier, a kind of :data:`KINDS`, a version a whole number, the ids
    it requires known, with no cycle), each file's path (relative, POSIX,
    under :data:`FOLDERS`, no ``..``, claimed by one entry only), sha256 (64
    hex digits) and size (a whole number up to :data:`MAX_FILE`; an entry's
    files up to :data:`MAX_ENTRY` in all), and at most
    :data:`MAX_ENTRIES` entries and :data:`MAX_FILES` files in all.
    ``ValueError`` names the first fault, in time linear in the manifest
    (its requires walked once, :func:`needs`)."""
    if isinstance(manifest, (bytes, str)):
        raw = manifest.encode() if isinstance(manifest, str) else manifest
        if len(raw) > MAX_MANIFEST:
            raise ValueError(f"manifest: {len(raw):,} bytes, past the {MAX_MANIFEST:,} a manifest may hold")
        try:
            manifest = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"manifest: not JSON ({exc})") from None
        except RecursionError:
            raise ValueError("manifest: not JSON (nested too deep)") from None
    if not isinstance(manifest, Mapping):
        raise ValueError("manifest: not a JSON object")
    if manifest.get("format") != FORMAT:
        raise ValueError(f"manifest: format {manifest.get('format')!r} isn't {FORMAT!r}")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"manifest: schema_version {manifest.get('schema_version')!r} isn't one AzurKit reads "
                         f"({SCHEMA_VERSION}): update AzurKit")
    if not isinstance(entries := manifest.get("entries"), list):
        raise ValueError("manifest: entries is no list")
    if len(entries) > MAX_ENTRIES:
        raise ValueError(f"manifest: {len(entries):,} entries, past the {MAX_ENTRIES:,} a manifest may hold")
    out, claimed, seen, count = [], {}, set(), 0
    for k, given in enumerate(entries, 1):
        where = f"manifest: entry {k}"
        if not isinstance(given, Mapping) or set(given) != set(ENTRY):
            raise ValueError(f"{where}: an object of {', '.join(ENTRY)}, exactly")
        where = f"manifest: entry {given['id']!r}"
        if not isinstance(given["id"], str) or not _ID.match(given["id"]):
            raise ValueError(f"{where}: an id is a lower-case identifier")
        if given["id"] in seen:
            raise ValueError(f"{where}: two entries have that id")
        seen.add(given["id"])
        if given["kind"] not in KINDS:
            raise ValueError(f"{where}: kind {given['kind']!r} is none of {', '.join(KINDS)}")
        for field in ("title", "author", "licence"):
            if not isinstance(given[field], str) or not given[field].strip():
                raise ValueError(f"{where}: {field} is no text")
        if type(given["version"]) is not int or given["version"] < 1:
            raise ValueError(f"{where}: version {given['version']!r} is no whole number from 1")
        if not isinstance(given["files"], list) or not isinstance(given["requires"], list):
            raise ValueError(f"{where}: files and requires are lists")
        if not all(isinstance(r, str) for r in given["requires"]):
            raise ValueError(f"{where}: requires is a list of ids")
        if (count := count + len(given["files"])) > MAX_FILES:
            raise ValueError(f"{where}: past the {MAX_FILES:,} files a manifest may list in all")
        files = []
        for f in given["files"]:
            if not isinstance(f, Mapping) or not {"path", "sha256", "size"} <= set(f) <= {"path", "sha256", "size",
                                                                                         "licence"}:
                raise ValueError(f"{where}: a file is an object of path, sha256, size and maybe licence")
            path = _path(where, f["path"])
            if path in claimed:
                raise ValueError(f"{where}: {path} is entry {claimed[path]!r}'s too")
            claimed[path] = given["id"]
            if not isinstance(f["sha256"], str) or not _SHA.match(f["sha256"]):
                raise ValueError(f"{where}: {path}'s sha256 is no 64 lower-case hex digits")
            if type(f["size"]) is not int or not 0 <= f["size"] <= MAX_FILE:
                raise ValueError(f"{where}: {path}'s size {f['size']!r} is no whole number up to {MAX_FILE:,}")
            if "licence" in f and not (isinstance(f["licence"], str) and f["licence"].strip()):
                raise ValueError(f"{where}: {path}'s licence is no text")
            files.append({k: f[k] for k in ("path", "sha256", "size", "licence") if k in f})
        if (size := sum(f["size"] for f in files)) > MAX_ENTRY:
            raise ValueError(f"{where}: its files are {size:,} bytes, past the {MAX_ENTRY:,} an entry may hold")
        out.append({**{k: given[k] for k in ENTRY if k not in ("files", "requires")}, "files": files,
                    "requires": list(given["requires"])})
    ids = {e["id"]: e for e in out}
    for e in out:
        if lost := [r for r in e["requires"] if r not in ids]:
            raise ValueError(f"manifest: entry {e['id']!r} requires {', '.join(map(repr, lost))}, which it lists not")
    _walk(list(ids), ids)   # a cycle is named
    return {"format": FORMAT, "schema_version": SCHEMA_VERSION, "entries": out}


def filled(manifest: Mapping, read: Callable[[str], bytes]) -> dict:
    """``manifest`` (an object, unchecked) with each listed file's sha256
    and size those of ``read(path)``'s bytes (a contributor's ``azurkit
    content check --write``), then :func:`check` ed."""
    entries = [dict(e, files=[dict(f, **_measured(read(f["path"]))) for f in e.get("files", [])])
               if isinstance(e, Mapping) and isinstance(e.get("files"), list)
               and all(isinstance(f, Mapping) and isinstance(f.get("path"), str) for f in e["files"]) else e
               for e in manifest.get("entries", [])] if isinstance(manifest.get("entries"), list) else None
    return check(dict(manifest, entries=entries))


def _measured(data: bytes) -> dict:
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def needs(entry: str, entries: Mapping[str, Mapping]) -> list[str]:
    """``entry`` and each entry it requires, transitively, those required
    first (``entries``: id -> a checked entry); ``ValueError`` names a cycle
    or an unknown id."""
    return _walk([entry], entries)


def _walk(starts: list[str], entries: Mapping[str, Mapping]) -> list[str]:
    """Each of ``starts`` and what it requires, transitively, those required
    first, each once: one walk with a done set and a stack of its own (no
    recursion), so a lattice of requires costs its size and a chain of any
    depth is walked (D992's SEC-6)."""
    order: list[str] = []
    done: set[str] = set()
    for start in starts:
        if start in done:
            continue
        if start not in entries:
            raise ValueError(f"manifest: no entry {start!r}")
        path, on, stack = [start], {start}, [iter(entries[start]["requires"])]
        while stack:
            name = next(stack[-1], None)
            if name is None:
                stack.pop()
                done.add(last := path.pop())
                on.discard(last)
                order.append(last)
            elif name in on:
                loop = path[path.index(name):] + [name]
                shown = loop if len(loop) <= 8 else [*loop[:3], f"... {len(loop) - 6:,} more ...", *loop[-3:]]
                raise ValueError(f"manifest: entry {name!r} requires itself ({' -> '.join(shown)})")
            elif name not in done:
                if name not in entries:
                    raise ValueError(f"manifest: no entry {name!r}")
                path.append(name)
                on.add(name)
                stack.append(iter(entries[name]["requires"]))
    return order


def verify(manifest: Mapping, entry: str, files: Mapping[str, bytes]) -> list[dict]:
    """The entries an install of ``entry`` writes (it and those it requires,
    :func:`needs`, those already in ``files``' reach), each file of theirs
    in ``files`` checked: its size and sha256 as the manifest lists them,
    no XISO image or part of one (D960), and a built-in variant's recipe
    the engine's (:func:`builtin_refusal`), the whole install at most
    :data:`MAX_ENTRY`. ``ValueError`` names the entry, the path and, for a
    sha256, both values' first 12 digits."""
    manifest = check(manifest)
    entries = {e["id"]: e for e in manifest["entries"]}
    chosen = _chosen(entry, entries)
    for e in chosen:
        for f in e["files"]:
            _checked(e, f, files.get(f["path"]))
        if (why := builtin_refusal(e, files)) is not None:
            raise ValueError(f"{e['id']}: {why}")
    return chosen


def _chosen(entry: str, entries: Mapping[str, Mapping]) -> list[dict]:
    """The entries an install of ``entry`` reaches (:func:`needs`), at most :data:`MAX_ENTRY` in all."""
    chosen = [entries[name] for name in needs(entry, entries)]
    if (size := sum(f["size"] for e in chosen for f in e["files"])) > MAX_ENTRY:
        raise ValueError(f"{entry}: an install of it and the entries it requires is {size:,} bytes, past the "
                         f"{MAX_ENTRY:,} one may write")
    return chosen


def _checked(e: Mapping, f: Mapping, data) -> bytes:
    """``data``, a file ``f`` of entry ``e`` as fetched (``None``: not), checked against the manifest."""
    if data is None:
        raise ValueError(f"{e['id']}: {f['path']} wasn't fetched")
    data = bytes(data)
    if len(data) != f["size"]:
        raise ValueError(f"{e['id']}: {f['path']} is {len(data):,} bytes, not the manifest's {f['size']:,}")
    if (got := hashlib.sha256(data).hexdigest()) != f["sha256"]:
        raise ValueError(f"{e['id']}: {f['path']}'s sha256 {got[:12]} isn't the manifest's {f['sha256'][:12]}")
    if XISO in data:
        raise ValueError(f"{e['id']}: {f['path']} holds an Xbox disc image's magic: never content (D960)")
    return data


class _Landed(Mapping):
    """The files ``paths`` below ``folder``, each read when it is asked for
    (what :func:`builtin_refusal` reads of an entry install has checked)."""

    def __init__(self, folder: Path, paths: list[str]):
        self.folder, self.paths = folder, paths

    def __getitem__(self, path: str) -> bytes:
        if path not in self.paths:
            raise KeyError(path)
        return (self.folder / path).read_bytes()

    def __iter__(self):
        return iter(self.paths)

    def __len__(self) -> int:
        return len(self.paths)


def builtin_refusal(entry: Mapping, files: Mapping[str, bytes]) -> str | None:
    """Why a variant entry's recipe can't stand for the engine's built-in of
    a name it holds, or ``None``: the five variants build from the engine's
    own table (Step 4.12c kept them built-ins; ``_player_variants.load_variants`` refuses
    a recipe file naming one), so each recipe of the entry's ``variant.json``
    with a built-in's name must be that built-in's, its sha its sha."""
    if entry["kind"] != "variant":
        return None
    recipe = f"variants/{entry['id']}/variant.json"
    if recipe not in files:
        return None
    from azurkit.tools.characters import _player_variants as variants

    try:
        doc = json.loads(bytes(files[recipe]))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return f"{recipe} is no JSON ({exc})"
    if not isinstance(doc, dict):
        return f"{recipe} is no object of recipes"
    built = variants.builtins()
    for name in doc:
        if name in built:
            recipe_of, _ = variants.recipe_of(doc, name, "built-in")
            if (sha := variants.recipe_sha(recipe_of)) != built[name].sha:
                return (f"{recipe}'s {name} is recipe {sha}, not the built-in {name}'s {built[name].sha}: AzurKit "
                        "builds the built-in until the recipes move out of it")
    return None


def installed(root: Path | None = None) -> dict:
    """``{id: {"version", "source", "files": {path: sha256}}}`` of the
    entries installed in ``root`` (:data:`ROOT`), from its
    ``installed.json``; ``{}`` with none or one AzurKit can't read."""
    try:
        found = json.loads(((root or ROOT) / INSTALLED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def install(manifest: Mapping, entry: str, fetch: Callable[[str], bytes], root: Path | None = None,
            source: str = "") -> dict:
    """Install ``entry`` of ``manifest`` (and each entry it requires that
    isn't installed at its version) into ``root`` (:data:`ROOT`), reading
    each file through ``fetch``: each file checked as it lands
    (:func:`verify`'s checks) and written to ``root/.part-<id>/``, so one
    file at a time is held and a mismatch writes nothing (the parts
    removed, D35; D992's SEC-9); once every file is checked, each entry's
    moved into place, the files its last version held that this one doesn't
    removed, and ``installed.json`` written last, each entry's version,
    ``source`` and files' sha256. An installed entry is Updated the same
    way. Returns :func:`installed`'s record."""
    root = root or ROOT
    manifest = check(manifest)
    entries = {e["id"]: e for e in manifest["entries"]}
    had = installed(root)
    chosen = _chosen(entry, entries)
    todo = [e["id"] for e in chosen if e["id"] == entry or had.get(e["id"], {}).get("version") != e["version"]]
    made, parts = not root.exists(), []
    try:
        for e in chosen:
            paths = [f["path"] for f in e["files"]]
            if e["id"] not in todo:   # installed at its version: its files read back
                for f in e["files"]:
                    _checked(e, f, _held(root, f))
                landed = _Landed(root, paths)
            else:
                parts.append(part := root / f".part-{e['id']}")
                shutil.rmtree(part, ignore_errors=True)
                for f in e["files"]:
                    data = _checked(e, f, fetch(f["path"]))
                    (part / f["path"]).parent.mkdir(parents=True, exist_ok=True)
                    (part / f["path"]).write_bytes(data)
                    del data
                landed = _Landed(part, paths)
            if (why := builtin_refusal(e, landed)) is not None:
                raise ValueError(f"{e['id']}: {why}")
    except BaseException:
        for part in parts:
            shutil.rmtree(part, ignore_errors=True)
        if made:
            with contextlib.suppress(OSError):
                root.rmdir()
        raise
    root.mkdir(parents=True, exist_ok=True)
    record = dict(had)
    for name in todo:
        part = root / f".part-{name}"
        for f in entries[name]["files"]:
            (root / f["path"]).parent.mkdir(parents=True, exist_ok=True)
            os.replace(part / f["path"], root / f["path"])
        shutil.rmtree(part, ignore_errors=True)
        kept = {f["path"] for f in entries[name]["files"]}
        for path in sorted(set(had.get(name, {}).get("files", {})) - kept):
            if not any(path in other.get("files", {}) for key, other in record.items() if key != name):
                (root / path).unlink(missing_ok=True)
        record[name] = {"version": entries[name]["version"], "source": source,
                        "files": {f["path"]: f["sha256"] for f in entries[name]["files"]}}
    part = root / f"{INSTALLED}.part"
    part.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(part, root / INSTALLED)
    return record


def _held(root: Path, f: Mapping) -> bytes:
    """An installed required entry's file, read back for :func:`verify`."""
    try:
        return (root / f["path"]).read_bytes()
    except OSError:
        return b""


def states(manifest: Mapping | None, record: Mapping) -> list[dict]:
    """Each entry of ``manifest`` (checked; ``None``: none fetched) with what
    the content folder's ``record`` (:func:`installed`) makes of it:
    ``state`` ``"install"``, ``"installed"`` (at the manifest's version) or
    ``"update"`` (an older version installed, kept until its Update), and
    ``installed`` (the version held, or ``None``); an entry installed that the
    manifest no longer lists comes last, ``"installed"``."""
    out = []
    for e in (manifest or {}).get("entries", []):
        held = record.get(e["id"], {}).get("version")
        out.append({k: e[k] for k in ENTRY} | {
            "state": "install" if held is None else "installed" if held == e["version"] else "update",
            "installed": held})
    listed = {e["id"] for e in out}
    out += [{"id": name, "kind": "variant" if any(p.startswith("variants/") for p in held.get("files", {})) else "pack",
             "title": name, "author": "", "licence": "", "version": held.get("version"), "requires": [],
             "files": [{"path": path, "sha256": sha} for path, sha in held.get("files", {}).items()],
             "state": "installed", "installed": held.get("version")}
            for name, held in record.items() if name not in listed and isinstance(held, Mapping)]
    return out
