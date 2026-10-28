"""The one surface a UI calls: :func:`catalog`, :func:`verify`, :func:`image`
and :func:`build` (preset, spoiler and art come with their steps). JSON in
and out: a recipe is a JSON object and each call returns one; :func:`image`
also returns the image, unwritten, which the web page joins into a Blob
(``iso.Image.segments``). A refusal is a ``ValueError`` or ``OSError`` whose
message names what it refuses and why, never game bytes; a build that fails
writes nothing (D35).

A recipe names its image and every pack it applies, each with its
parameters::

    {"iso": "<a vanilla image>", "packs": {"fps_unlock": {}, "qol_alloc_race": {}}}

The packs apply in their canonical order, whatever order the recipe names
them in. A build applies the packs it names and no others: :func:`catalog`
says which are on by default (D528), for a UI to start ticked.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from azurkit.core import gate, iso
from azurkit.edits import manifest as edits
from azurkit.edits.layer import Layer
from azurkit.tools import mods

RECIPE = ("iso", "packs")


def catalog() -> dict:
    """Every pack: its name, what it does, its category, whether a build
    starts with it (D528), the releases it supports and its parameters
    with their defaults, in the canonical order."""
    return {"packs": [{"name": p.name, "description": p.description, "category": p.category,
                       "default_on": p.default_on, "releases": list(p.releases), "parameters": p.parameters()}
                      for p in mods.PACKS.values()]}


def verify(path: str) -> dict:
    """Check that the image at ``path`` is a release's vanilla image, every
    file of it (``gate.NotVanillaError`` names the first that isn't)."""
    stamp = gate.verify(path)
    return {"iso": str(stamp.path), "release": stamp.release.name, "label": stamp.release.label}


def _plan(recipe: Mapping) -> tuple[gate.Stamp, dict[str, bytes], list[Layer]]:
    """The recipe's vanilla image (its build files checked, D27), the files
    read from it and each pack's layer; every refusal named."""
    if not isinstance(recipe, Mapping):
        raise ValueError(f"a recipe is a JSON object, not {type(recipe).__name__}")
    if unknown := sorted(set(recipe) - set(RECIPE)):
        raise ValueError(f"recipe: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(RECIPE)})")
    if not isinstance(recipe.get("iso"), str):
        raise ValueError("recipe: iso names no image")
    packs = recipe.get("packs", {})
    if not isinstance(packs, Mapping) or not all(isinstance(v, Mapping) for v in packs.values()):
        raise ValueError("recipe: packs is {pack: {parameter: value}}")
    if unknown := sorted(set(packs) - set(mods.PACKS)):
        raise ValueError(f"recipe: no pack {', '.join(map(repr, unknown))} (the packs: {', '.join(mods.PACKS)})")
    stamp = gate.verify(recipe["iso"], whole=False)
    with iso.Reader(stamp.path) as r:
        base = {mods.engine.XBE: r.read(mods.engine.XBE)}
    layers, failed = [], []
    for name, pack in mods.PACKS.items():
        if name in packs:
            try:
                layers.append(mods.plan(pack, stamp.release, base[mods.engine.XBE], packs[name]))
            except mods.PackError as exc:
                failed.append(str(exc))
    if failed:
        raise ValueError("; ".join(failed))
    return stamp, base, layers


def _report(made: edits.Manifest) -> dict:
    return {"release": made.release.name, "label": made.release.label,
            "layers": [{"id": la.id, "sites": len({c.group for c in la.changes}),
                        "bytes": sum(len(c.after) for c in la.changes)} for la in made.layers],
            "result": dict(made.result), "conflicts": [str(c) for c in made.conflicts]}


def image(recipe: Mapping) -> tuple[iso.Image, dict]:
    """The image ``recipe`` builds, unwritten, and its report: the release,
    each layer's sites and bytes, the sha256 of each file that differs from
    vanilla, and every conflict (D28)."""
    stamp, base, layers = _plan(recipe)
    made, manifest = edits.image(stamp, layers, base)
    return made, _report(manifest)


def build(recipe: Mapping, out: str, *, progress: Callable[[int, int], object] | None = None) -> dict:
    """Write the image ``recipe`` builds to ``out`` (never its input or a
    vanilla image, D36); :func:`image`'s report with the output's path,
    size and sha256. ``progress(done, total)`` follows the write; an
    exception it raises cancels it, and nothing is written."""
    stamp, base, layers = _plan(recipe)
    target = Path(out)
    for release in gate.RELEASES:
        if (vanilla := gate.find(release)) and target.exists() and target.samefile(vanilla):
            raise ValueError(f"{target}: it is the vanilla {release.label} image, which a build never writes over")
    sha256, manifest = edits.build(stamp, layers, target, base=base, progress=progress)
    return _report(manifest) | {"out": str(target), "size": target.stat().st_size, "sha256": sha256}
