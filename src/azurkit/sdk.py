"""The one surface a UI calls: :func:`catalog`, :func:`verify`,
:func:`vanilla`, :func:`image`, :func:`build`, :func:`open_build`,
:func:`read_mods`, :func:`preset_encode` and :func:`preset_decode` (spoiler
and art come with their steps). JSON in and out: a recipe is a JSON object
and each call returns one; :func:`image` also returns the image, unwritten, which the web
page joins into a Blob (``iso.Image.segments``). A refusal is a
``ValueError`` or ``OSError`` whose message names what it refuses and why,
never game bytes; a build that fails writes nothing (D35).
``tests/sdk_api.txt`` is this surface's snapshot (``scripts/sdk_api.py``).

A recipe names its image, every pack it applies, each with its sliders'
values (a slider it doesn't name keeps its default), and the mods file's
``xbr`` operations (``edits.xbr``: a config.xbr cell ``set`` by its names,
or ``replace_bytes`` in an XBR file, applied in order after the packs)::

    {"iso": "<a vanilla image>", "packs": {"fps_unlock": {"target_fps": 120}, "qol_alloc_race": {}},
     "xbr": [{"op": "set", "file": "gamedata/config.xbr", "table": "critters_damage", "entity": "golem",
              "prop": "hitPoints", "value": 321}]}

A build with a layer carries its manifest in two root files the game never
opens, ``/azurkit.json`` and ``/azurkit.bin`` (Q66), and :func:`open_build`
reads an AzurKit build back into its recipe: its mods file (Q268), which
:func:`read_mods` turns into a recipe's ``packs`` and ``xbr`` again.

The packs apply in their canonical order, whatever order the recipe names
them in. A build applies the packs it names and no others: :func:`catalog`
says which are on by default (D528), for a UI to start ticked, each pack's
sliders, and the packs each requires in the same build, without which a
recipe is refused by name. A slider takes any finite number (D23; a whole
one its encoding holds where it takes only those, D45): its track's ends
are hints, never limits, and nothing is clamped (``mods.normalize``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from azurkit import __version__
from azurkit.core import gate, iso
from azurkit.edits import manifest as edits
from azurkit.edits import preset, xbr
from azurkit.edits.layer import Layer
from azurkit.tools import mods

__all__ = ["catalog", "verify", "vanilla", "image", "build", "open_build", "read_mods", "preset_encode",
           "preset_decode"]
RECIPE = ("iso", "packs", "xbr")
#: A UI's tabs, one an area, in the owner's order (D901), each with whether
#: its area works yet: a tab shows only once it does (D902).
TABS = (("patches", "Patches", True), ("randomizer", "Randomizer", False), ("characters", "Characters", False),
        ("data", "Data", False), ("tools", "Tools", False), ("about", "About", True))


def catalog() -> dict:
    """A UI's tabs (each id and title, those whose area works, D902), the
    packs' categories (each id, title and line, in the order a UI groups
    them) and every pack: its name, what it does, its category, whether a
    build starts with it (D528), the releases it supports, the packs it
    requires in the same build and its sliders, in the canonical order. A
    slider: its name, label, default, track (``min``, ``max`` and
    ``step``, display hints only), unit, description, vanilla value
    (``None`` where the image's XBE holds it) and ``whole`` (the range of
    whole numbers it takes, its encoding's, or ``None``)."""
    return {"tabs": [{"id": tab, "title": title} for tab, title, works in TABS if works],
            "categories": [{"id": category, "title": title, "description": line}
                           for category, (title, line) in mods.CATEGORIES.items()],
            "packs": [{"name": p.name, "description": p.description, "category": p.category,
                       "default_on": p.default_on, "releases": list(p.releases), "requires": list(p.requires),
                       "sliders": [s.catalog() for s in p.sliders()]} for p in mods.PACKS.values()]}


def verify(path: str) -> dict:
    """Check that the image at ``path`` is a release's vanilla image, every
    file of it (``gate.NotVanillaError`` names the first that isn't)."""
    stamp = gate.verify(path)
    return {"iso": str(stamp.path), "release": stamp.release.name, "label": stamp.release.label}


def vanilla(path: str) -> dict:
    """The vanilla values the image at ``path`` holds for every slider at a
    site of its XBE (``catalog`` gives those ``None``: the wheel holds no
    game constant, Q174), ``{"release", "label", "packs": {pack: {slider:
    value}}}``, so a UI's track can hold them (D42)."""
    stamp = gate.verify(path, whole=False)
    with iso.Reader(stamp.path) as r:
        xbe = r.read("default.xbe")
    return {"release": stamp.release.name, "label": stamp.release.label, "packs": mods.vanilla(stamp.release, xbe)}


def _packs(recipe: object) -> dict[str, dict]:
    """The recipe's packs, normalized (``mods.normalize``), each with every
    pack it requires (``mods.missing``); every refusal named."""
    if not isinstance(recipe, Mapping):
        raise ValueError(f"a recipe is a JSON object, not {type(recipe).__name__}")
    if unknown := sorted(set(recipe) - set(RECIPE), key=str):
        raise ValueError(f"recipe: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(RECIPE)})")
    packs = mods.normalize(recipe.get("packs", {}))
    if lost := mods.missing(packs):
        raise ValueError("; ".join(lost))
    return packs


def _plan(recipe: Mapping) -> tuple[gate.Stamp, dict[str, bytes], list[Layer]]:
    """The recipe's vanilla image (its build files checked, D27), the files
    read from it, each pack's layer, then its xbr operations' (the Data
    tool's, after the packs); every refusal named."""
    packs = _packs(recipe)
    ops = xbr.normalize(recipe.get("xbr", []))
    if not isinstance(recipe.get("iso"), str):
        raise ValueError("recipe: iso names no image")
    stamp = gate.verify(recipe["iso"], whole=False)
    chosen = {name: pack for name, pack in mods.PACKS.items() if name in packs}
    with iso.Reader(stamp.path) as r:
        names = [f for pack in chosen.values() for f in pack.files()] + xbr.files(ops)
        base = {file: r.read(file) for file in dict.fromkeys(names) if file in stamp.release.files}
    layers, failed = [], []
    for name, pack in chosen.items():
        try:
            layers.append(mods.plan(pack, stamp.release, base, packs[name], [c for la in layers for c in la.claims]))
        except mods.PackError as exc:
            failed.append(str(exc))
    if ops:
        try:
            layers.append(xbr.plan(ops, stamp.release, base))
        except ValueError as exc:
            failed.append(str(exc))
    if failed:
        raise ValueError("; ".join(failed))
    return stamp, base, layers


def _report(made: edits.Manifest) -> dict:
    return {"release": made.release.name, "label": made.release.label,
            "layers": [{"id": la.id, "sites": len({c.group for c in la.changes}),
                        "bytes": sum(len(c.after) for c in la.changes)} for la in made.layers],
            "result": dict(made.result), "conflicts": [str(c) for c in made.conflicts],
            "notes": [note for la in made.layers for note in la.notes]}


def image(recipe: Mapping) -> tuple[iso.Image, dict]:
    """The image ``recipe`` builds, unwritten, and its report: the release,
    each layer's sites and bytes, the sha256 of each file that differs from
    vanilla, every conflict (D28) and each layer's notes (a slider value
    past float32's range, written as the infinity it saturates to, Q110)."""
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


def open_build(path: str, *, whole: bool = True) -> dict:
    """The recipe of the AzurKit build at ``path``: its mods file (Q268), a
    preset of its base, AzurKit's version that built it, its layers'
    recipes (the packs; the xbr operations) and the sha256 of each file it
    changed, from its /azurkit.json, once every file of the image is
    checked against it (``edits.manifest.load``): a file no layer wrote
    that differs is drift, refused by name, as is an image that isn't an
    AzurKit build. With ``whole`` false only the files it changed are
    checked (the page's way: it offers the recipe, and builds from a
    vanilla image). Its recipe rebuilds the build from the vanilla image
    (:func:`read_mods`)."""
    return preset.from_manifest(edits.load(path, whole=whole)[1])


def read_mods(given: str | bytes | Mapping) -> dict:
    """A mods file (Q268: a preset or an AzurKit build's manifest, as JSON
    text or the object, or a share link) as a recipe's ``{"packs", "xbr"}``,
    normalized; ``packs`` only when it has a packs layer (a build's packs
    are then its packs, and no others). Every refusal named."""
    found = preset.read(given)
    out: dict = {}
    for layer in found["layers"]:
        if (layer["tool"], layer["kind"]) == ("mods", "packs"):
            out["packs"] = _packs({"packs": layer["recipe"]})
        elif (layer["tool"], layer["kind"]) == (xbr.TOOL, xbr.KIND) and set(layer["recipe"]) == {"ops"}:
            out["xbr"] = xbr.normalize(layer["recipe"]["ops"])
        else:
            raise ValueError(f"preset: no tool {layer['tool']!r} with {layer['kind']!r} "
                             "(AzurKit's: mods with packs, data with xbr)")
    return out


def _shared(ops: list[dict]) -> list[dict]:
    """``ops``, refused by name unless each is a ``set`` (Q174: a link
    carries names and numbers, never a file's bytes)."""
    if raw := [str(k) for k, op in enumerate(ops, 1) if op["op"] != "set"]:
        raise ValueError(f"preset: a share link carries packs and set only (Q174), not xbr op {', '.join(raw)} "
                         "(replace_bytes)")
    return ops


def preset_encode(recipe: Mapping, report: Mapping | None = None) -> str:
    """The share link's fragment (``#p=…``) for ``recipe``'s packs,
    normalized, and its ``set`` operations, never its image's path; given
    its build's report (:func:`image`), with the release it was built from
    and the sha256 of each file it changed. Names, numbers and hashes only
    (Q174): a recipe with a ``replace_bytes`` is refused by name."""
    made = {"format": preset.FORMAT, "schema_version": preset.SCHEMA_VERSION, "azurkit": __version__,
            "layers": [{"tool": "mods", "kind": "packs", "recipe": _packs(recipe)}]}
    if ops := _shared(xbr.normalize(recipe.get("xbr", []))):
        made["layers"].append({"tool": xbr.TOOL, "kind": xbr.KIND, "recipe": {"ops": ops}})
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
    normalized (``mods.normalize``) and its ``set`` operations checked: a
    tool or pack AzurKit doesn't have, a value a slider refuses or a
    ``replace_bytes`` (Q174) is refused by name."""
    found = preset.decode(text)
    for layer in found["layers"]:
        if (layer["tool"], layer["kind"]) == ("mods", "packs"):
            layer["recipe"] = _packs({"packs": layer["recipe"]})
        elif (layer["tool"], layer["kind"]) == (xbr.TOOL, xbr.KIND) and set(layer["recipe"]) == {"ops"}:
            layer["recipe"] = {"ops": _shared(xbr.normalize(layer["recipe"]["ops"]))}
        else:
            raise ValueError(f"preset: no tool {layer['tool']!r} with {layer['kind']!r} "
                             "(AzurKit's: mods with packs, data with xbr)")
    return found
