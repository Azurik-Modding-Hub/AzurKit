"""A build: its image (:func:`image`), written by :func:`build`, and its
:class:`Manifest`, the record of what made it.

``build() = iso.pack(image())``. :func:`image` reads the files the layers
change from the input (a release's vanilla image, which the caller's gate
stamp vouches for, D27), stacks the layers over them (:func:`layer.compose`,
D28) and returns the image unwritten, with its manifest: the base, each
layer and its changes and claims (the carve allocator's room, which a
re-planned layer keeps clear of), the sha256 of every file that differs from
the base, and every conflict. Nothing is written until :func:`build` writes the whole
image (D35), never over its input (D36).

A build with any layer carries its manifest (Q66, V10) as two files in the
image's root, which the game never opens: ``/azurkit.json``
(:meth:`Manifest.to_json`), where a change's bytes past :data:`INLINE` are
named by their sha256, and ``/azurkit.bin``, those bytes, each once, at the
offset and size the JSON's ``bin`` gives (:func:`root_files`); a file Replace
files put (``edits.files``, the last layer) is named only, as the image holds
it at its path, so a build of large files stays under :data:`MAX_BIN`. :func:`load`
reads them back from an image, re-verifies each blob, and checks the image
against them: every file the manifest says the build changed has its
sha256, and every other is the release's vanilla file (a file no layer
wrote that differs is drift, refused by name: AzurKit can only discard it,
REORG §12.2). A build with no layer is the vanilla image, byte for byte.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from azurkit import __version__
from azurkit.core import filelist, gate, iso
from azurkit.edits.layer import Conflict, Layer, compose

FORMAT = "azurkit-manifest"
SCHEMA_VERSION = 1
JSON, BIN = "azurkit.json", "azurkit.bin"   # the image's root files that hold a build's manifest (Q66)
INLINE = 32                                  # a change's bytes up to this many sit in the JSON as hex
MAX_JSON = 16 << 20                          # an image's /azurkit.json is untrusted: read no more
MAX_BIN = 256 << 20


@dataclass(frozen=True)
class Manifest:
    release: gate.Release            # the base: that release's vanilla image
    layers: tuple[Layer, ...]
    result: Mapping[str, str]        # each file that differs from the base -> its sha256
    conflicts: tuple[Conflict, ...]
    verdicts: Mapping = field(default_factory=dict)   # a tool's verdict on the built image, by tool (judge)

    def recipe(self) -> dict:
        """The base and each layer's recipe: what replays the build."""
        return {"base": {"kind": "vanilla", "release": self.release.name, "iso_sha256": self.release.iso_sha256},
                "layers": [{"id": la.id, "tool": la.tool, "kind": la.kind, "recipe": la.recipe} for la in self.layers]}

    def to_json(self, blobs: dict[str, bytes] | None = None) -> dict:
        """The manifest as JSON. With ``blobs``, a change's bytes past
        :data:`INLINE` are ``{"sha256"}`` there, each kept in ``blobs``
        once; else every change's are hex. A file Replace files put is
        ``{"sha256"}`` either way, in no blob (the module's docstring)."""
        recipe = self.recipe()

        def after(c, tool: str) -> str | dict:
            if c.whole and tool == "files":   # edits.files.TOOL (that module imports this one)
                return {"sha256": _sha256(c.after)}
            if blobs is None or len(c.after) <= INLINE:
                return c.after.hex()
            blobs.setdefault(sha := _sha256(c.after), bytes(c.after))
            return {"sha256": sha}
        return {
            "format": FORMAT,
            "schema_version": SCHEMA_VERSION,
            "azurkit": __version__,
            "base": recipe["base"] | {"files": _sha256(self.release.manifest.read_bytes())},
            "layers": [r | {"changes": [{"file": c.file, "offset": c.offset, "size": len(c.after), "before": c.before,
                                         "after": after(c, la.tool), "group": c.group}
                                        | ({"whole": True} if c.whole else {}) for c in la.changes],
                             "claims": [{"file": c.file, "offset": c.offset, "size": c.size, "owner": c.owner,
                                         "writable": c.writable} for c in la.claims],
                             "notes": list(la.notes)}
                       for r, la in zip(recipe["layers"], self.layers)],
            "recipe_sha256": _sha256(json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode()),
            "result": dict(sorted(self.result.items())),
            "conflicts": [str(c) for c in self.conflicts],
            "verdicts": dict(self.verdicts),
        }


def root_files(made: Manifest) -> dict[str, bytes]:
    """``{"azurkit.json": …, "azurkit.bin": …}``: the manifest's two root
    files (the module's docstring)."""
    blobs: dict[str, bytes] = {}
    record = made.to_json(blobs)
    at, index = 0, {}
    for sha, data in blobs.items():
        index[sha] = [at, len(data)]
        at += len(data)
    record["bin"] = index
    text = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {JSON: text.encode() + b"\n", BIN: b"".join(blobs.values())}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hashes(data: bytes) -> tuple[str, str]:
    """A changed file's sha256 (the manifest's result) and md5 (its
    ``filelist.txt`` line's)."""
    return _sha256(data), filelist.md5(data)


def image(stamp: gate.Stamp, layers: Sequence[Layer], base: Mapping[str, bytes] | None = None, *,
          root: bool = True, judge: Callable[[iso.Image, Manifest], Mapping] | None = None,
          map: Callable = map) -> tuple[iso.Image, Manifest]:
    """The image ``layers`` make of the vanilla image ``stamp`` checked,
    unwritten, and its manifest, which the image carries in its root
    (:func:`root_files`) when it has a layer and ``root`` (without them, it
    is Modkit's image of the same recipe, byte for byte). ``base`` holds
    files already read from it (the rest are read here). The image's
    ``filelist.txt`` is derived state (:func:`iso.read`), in the result when
    it differs. ``judge`` reads the image without the root files back and
    gives the manifest's verdicts (``{tool: verdict}``), or raises
    ``ValueError`` naming why the build fails (D35: the randomizer's
    read-back against its plan). The stamp vouches for its build files'
    sha256 (none is hashed again); ``map(fn, items)`` (a host's threads'; the
    built-in by default) hashes each changed file, once a build, and the
    image keeps each one's md5 for the read-back (:meth:`iso.Image.md5`)."""
    names = sorted({c.file for la in layers for c in (*la.changes, *la.claims)})
    base = dict(base or {})
    with iso.Reader(stamp.path) as r:
        base |= {name: r.read(name) for name in names if name not in base}
        known = {name: stamp.release.files[name][1] for name in base
                 if name in stamp.release.files and name.startswith(gate.BUILD_FILES)}
        files, conflicts = compose(base, layers, known)
        changed = {}
        for name in list(files):   # each file's copy freed as it is kept: a randomized build changes 700 MB of levels
            if (data := files.pop(name)) != base[name]:
                changed[name] = bytes(data)
            del data
        hashes = dict(zip(changed, map(_hashes, changed.values())))
        md5s = {name: md5 for name, (_, md5) in hashes.items()}
        made = iso.read(stamp.path, changed, md5s=md5s)
        listing = {}
        if changed:
            try:
                listing["filelist.txt"] = r.read("filelist.txt")
            except FileNotFoundError:
                pass
    result = {name: sha for name, (sha, _) in hashes.items()}
    if listing:
        with iso.Reader(made) as r:
            if (new := r.read("filelist.txt")) != listing["filelist.txt"]:
                result["filelist.txt"] = _sha256(new)
    manifest = Manifest(stamp.release, tuple(layers), result, tuple(conflicts))
    if judge is not None:
        manifest = replace(manifest, verdicts=dict(judge(made, manifest)))
    if root and layers:
        made = iso.read(stamp.path, changed, add=root_files(manifest), md5s=md5s)
    held = (stamp.size, stamp.mtime_ns, stamp.ctime_ns)[:3 if stamp.ctime_ns else 2]
    if made.origin[:len(held)] != held:   # the stamp vouches for the image as it was checked
        raise ValueError(f"{stamp.path}: it changed after it was checked (D27); choose it again")
    return made, manifest


def _object(pairs: list[tuple[str, object]]) -> dict:
    if len({k for k, _ in pairs}) != len(pairs):
        raise ValueError("a key given twice")
    return dict(pairs)


def _constant(name: str) -> None:
    raise ValueError(f"{name} is not a finite number")


def _checked(record: object, blob: bytes) -> dict:
    """``record`` (an image's /azurkit.json) if it is a manifest whose every
    blob ``blob`` (its /azurkit.bin) holds; ``ValueError`` names what isn't."""
    if not (isinstance(record, dict) and record.get("format") == FORMAT
            and record.get("schema_version") == SCHEMA_VERSION):
        raise ValueError(f"not an {FORMAT} of schema_version {SCHEMA_VERSION}")
    base, releases = record.get("base"), {r.name: r for r in gate.RELEASES}
    if not (isinstance(base, dict) and base.get("kind") == "vanilla" and base.get("release") in releases
            and base.get("iso_sha256") == releases[base["release"]].iso_sha256):
        raise ValueError("its base is no release's vanilla image")
    release = releases[base["release"]]
    layers, result, index = record.get("layers"), record.get("result"), record.get("bin", {})
    if not (isinstance(layers, list) and all(isinstance(la, dict) and isinstance(la.get("tool"), str)
                                             and isinstance(la.get("kind"), str) and isinstance(la.get("recipe"), dict)
                                             for la in layers) and layers):
        raise ValueError("its layers are no list of {tool, kind, recipe, ...}")
    if not (isinstance(result, dict) and all(path in release.files and isinstance(sha, str) for path, sha in
                                             result.items())):
        raise ValueError(f"its result names a file the {release.label} image doesn't have")
    if not isinstance(index, dict):
        raise ValueError("its bin is no {sha256: [offset, size]}")
    for sha, where in index.items():
        if not (isinstance(where, list) and len(where) == 2 and all(type(n) is int and n >= 0 for n in where)
                and where[0] + where[1] <= len(blob)):
            raise ValueError(f"its bin's blob {str(sha)[:12]} is outside /{BIN}")
        if _sha256(blob[where[0]:where[0] + where[1]]) != sha:
            raise ValueError(f"/{BIN}'s blob {str(sha)[:12]} isn't the bytes its sha256 names")
    return record


def load(path: str | os.PathLike, *, whole: bool = True) -> tuple[gate.Release, dict]:
    """The manifest of the AzurKit build at ``path`` (its /azurkit.json,
    checked, its /azurkit.bin's blobs re-verified) and its release, once the
    image is checked against it (the module's docstring; with ``whole``
    false, only the files it says the build changed): ``ValueError`` names
    why it is no AzurKit build or what drifted, never game bytes."""
    try:
        with iso.Reader(path) as r:
            entries = {e.path: e for e in r.entries()}
            found = [entries.get(name) for name in (JSON, BIN)]
            if found[0] is None:
                raise ValueError(f"{path}: no /{JSON}, so it isn't an AzurKit build")
            if found[0].size > MAX_JSON or (found[1] is not None and found[1].size > MAX_BIN):
                raise ValueError(f"{path}: its /{JSON} or /{BIN} is larger than any build writes")
            text, blob = r.read(found[0]), r.read(found[1]) if found[1] else b""
    except ValueError as exc:
        raise ValueError(str(exc) if str(exc).startswith(str(path)) else f"{path}: {exc}") from None
    try:
        record = _checked(json.loads(text.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant),
                          blob)
    except (ValueError, RecursionError) as exc:   # JSONDecodeError and UnicodeDecodeError are ValueErrors
        raise ValueError(f"{path}: its /{JSON} isn't a manifest AzurKit reads: {exc}") from None
    release = {r.name: r for r in gate.RELEASES}[record["base"]["release"]]
    try:
        gate.check(path, release, record["result"], (JSON, BIN), whole=whole)
    except gate.NotVanillaError as exc:
        raise ValueError(f"{path} isn't the build its /{JSON} records: {exc}") from None
    return release, record


def build(stamp: gate.Stamp, layers: Sequence[Layer], out, *, base: Mapping[str, bytes] | None = None,
          progress: Callable[[int, int], object] | None = None,
          judge: Callable[[iso.Image, Manifest], Mapping] | None = None, map: Callable = map) -> tuple[str, Manifest]:
    """Write the image (:func:`image`, with ``judge`` and ``map``) to
    ``out``; its sha256 and manifest. ``progress(done, total)`` follows the
    write, and an exception it raises cancels it with nothing written
    (:func:`iso.pack`)."""
    made, manifest = image(stamp, layers, base, judge=judge, map=map)
    return iso.pack(made, out, progress=progress), manifest
