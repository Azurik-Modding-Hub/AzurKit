"""The one surface a UI calls: :func:`catalog`, :func:`verify`, :func:`image`,
:func:`build`, :func:`preset_encode` and :func:`preset_decode` (spoiler and
art come with their steps). JSON in and out: a recipe is a JSON object and each call returns one; :func:`image`
also returns the image, unwritten, which the web page joins into a Blob
(``iso.Image.segments``). A refusal is a ``ValueError`` or ``OSError`` whose
message names what it refuses and why, never game bytes; a build that fails
writes nothing (D35).

A recipe names its image and every pack it applies, each with its sliders'
values (a slider it doesn't name keeps its default)::

    {"iso": "<a vanilla image>", "packs": {"fps_unlock": {"target_fps": 120}, "qol_alloc_race": {}}}

The packs apply in their canonical order, whatever order the recipe names
them in. A build applies the packs it names and no others: :func:`catalog`
says which are on by default (D528), for a UI to start ticked, and each
pack's sliders. A slider takes any finite number (D23; a whole one its
encoding holds where it takes only those, D45): its track's ends are hints,
never limits, and nothing is clamped (``mods.normalize``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from azurkit import __version__
from azurkit.core import gate, iso
from azurkit.edits import manifest as edits
from azurkit.edits import preset
from azurkit.edits.layer import Layer
from azurkit.tools import mods

RECIPE = ("iso", "packs")


def catalog() -> dict:
    """Every pack: its name, what it does, its category, whether a build
    starts with it (D528), the releases it supports and its sliders, in the
    canonical order. A slider: its name, label, default, track (``min``,
    ``max`` and ``step``, display hints only), unit, description, vanilla
    value (``None`` where the image holds it) and ``whole`` (the range of
    whole numbers it takes, its encoding's, or ``None``)."""
    return {"packs": [{"name": p.name, "description": p.description, "category": p.category,
                       "default_on": p.default_on, "releases": list(p.releases),
                       "sliders": [s.catalog() for s in p.sliders()]} for p in mods.PACKS.values()]}


def verify(path: str) -> dict:
    """Check that the image at ``path`` is a release's vanilla image, every
    file of it (``gate.NotVanillaError`` names the first that isn't)."""
    stamp = gate.verify(path)
    return {"iso": str(stamp.path), "release": stamp.release.name, "label": stamp.release.label}


def _packs(recipe: object) -> dict[str, dict]:
    """The recipe's packs, normalized (``mods.normalize``); every refusal named."""
    if not isinstance(recipe, Mapping):
        raise ValueError(f"a recipe is a JSON object, not {type(recipe).__name__}")
    if unknown := sorted(set(recipe) - set(RECIPE), key=str):
        raise ValueError(f"recipe: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(RECIPE)})")
    return mods.normalize(recipe.get("packs", {}))


def _plan(recipe: Mapping) -> tuple[gate.Stamp, dict[str, bytes], list[Layer]]:
    """The recipe's vanilla image (its build files checked, D27), the files
    read from it and each pack's layer; every refusal named."""
    packs = _packs(recipe)
    if not isinstance(recipe.get("iso"), str):
        raise ValueError("recipe: iso names no image")
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


def preset_encode(recipe: Mapping, report: Mapping | None = None) -> str:
    """The share link's fragment (``#p=…``) for ``recipe``'s packs,
    normalized, never its image's path; given its build's report
    (:func:`image`), with the release it was built from and the sha256 of
    each file it changed. Names, numbers and hashes only (Q174)."""
    made = {"format": preset.FORMAT, "schema_version": preset.SCHEMA_VERSION, "azurkit": __version__,
            "layers": [{"tool": "mods", "kind": "packs", "recipe": _packs(recipe)}]}
    if report is not None:
        name = report.get("release") if isinstance(report, Mapping) else None
        release = next((r for r in gate.RELEASES if r.name == name), None)
        if release is None:
            raise ValueError("preset: the report names no release")
        made["base"] = {"kind": "vanilla", "release": release.name, "iso_sha256": release.iso_sha256}
        made["result"] = dict(report.get("result", {}))
    return preset.encode(made)


def preset_decode(text: str) -> dict:
    """The preset in a link or its fragment (``preset.decode``), its packs
    normalized (``mods.normalize``): a tool or pack AzurKit doesn't have, or
    a value a slider refuses, is refused by name."""
    found = preset.decode(text)
    for layer in found["layers"]:
        if (layer["tool"], layer["kind"]) != ("mods", "packs"):
            raise ValueError(f"preset: no tool {layer['tool']!r} with {layer['kind']!r} (AzurKit's: mods, packs)")
        layer["recipe"] = mods.normalize(layer["recipe"])
    return found
