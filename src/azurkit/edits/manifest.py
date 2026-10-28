"""A build: its image (:func:`image`), written by :func:`build`, and its
:class:`Manifest`, the record of what made it.

``build() = iso.pack(image())``. :func:`image` reads the files the layers
change from the input (a release's vanilla image, which the caller's gate
stamp vouches for, D27), stacks the layers over them (:func:`layer.compose`,
D28) and returns the image unwritten, with its manifest: the base, each
layer and its changes, the sha256 of every file that differs from the base,
and every conflict. Nothing is written until :func:`build` writes the whole
image (D35), never over its input (D36).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from azurkit.core import gate, iso
from azurkit.edits.layer import Conflict, Layer, compose

FORMAT = "azurkit-manifest"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Manifest:
    release: gate.Release            # the base: that release's vanilla image
    layers: tuple[Layer, ...]
    result: Mapping[str, str]        # each file that differs from the base -> its sha256
    conflicts: tuple[Conflict, ...]
    verdicts: Mapping = field(default_factory=dict)

    def recipe(self) -> dict:
        """The base and each layer's recipe: what replays the build."""
        return {"base": {"kind": "vanilla", "release": self.release.name, "iso_sha256": self.release.iso_sha256},
                "layers": [{"id": la.id, "tool": la.tool, "kind": la.kind, "recipe": la.recipe} for la in self.layers]}

    def to_json(self) -> dict:
        recipe = self.recipe()
        return {
            "format": FORMAT,
            "schema_version": SCHEMA_VERSION,
            "base": recipe["base"] | {"files": _sha256(self.release.manifest.read_bytes())},
            "layers": [r | {"changes": [{"file": c.file, "offset": c.offset, "size": len(c.after), "before": c.before,
                                         "after": c.after.hex(), "group": c.group} for c in la.changes]}
                       for r, la in zip(recipe["layers"], self.layers)],
            "recipe_sha256": _sha256(json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode()),
            "result": dict(sorted(self.result.items())),
            "conflicts": [str(c) for c in self.conflicts],
            "verdicts": dict(self.verdicts),
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def image(stamp: gate.Stamp, layers: Sequence[Layer], base: Mapping[str, bytes] | None = None
          ) -> tuple[iso.Image, Manifest]:
    """The image ``layers`` make of the vanilla image ``stamp`` checked,
    unwritten, and its manifest. ``base`` holds files already read from it
    (the rest are read here). The image's ``filelist.txt`` is derived state
    (:func:`iso.read`), in the result when it differs."""
    names = sorted({c.file for la in layers for c in la.changes})
    base = dict(base or {})
    with iso.Reader(stamp.path) as r:
        base |= {name: r.read(name) for name in names if name not in base}
        files, conflicts = compose(base, layers)
        changed = {name: bytes(data) for name, data in files.items() if data != base[name]}
        made = iso.read(stamp.path, changed)
        listing = {}
        if changed:
            try:
                listing["filelist.txt"] = r.read("filelist.txt")
            except FileNotFoundError:
                pass
    result = {name: _sha256(data) for name, data in changed.items()}
    if listing:
        with iso.Reader(made) as r:
            if (new := r.read("filelist.txt")) != listing["filelist.txt"]:
                result["filelist.txt"] = _sha256(new)
    return made, Manifest(stamp.release, tuple(layers), result, tuple(conflicts))


def build(stamp: gate.Stamp, layers: Sequence[Layer], out, *, base: Mapping[str, bytes] | None = None,
          progress: Callable[[int, int], object] | None = None) -> tuple[str, Manifest]:
    """Write the image (:func:`image`) to ``out``; its sha256 and manifest.
    ``progress(done, total)`` follows the write, and an exception it raises
    cancels it with nothing written (:func:`iso.pack`)."""
    made, manifest = image(stamp, layers, base)
    return iso.pack(made, out, progress=progress), manifest
