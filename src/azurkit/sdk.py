"""The one surface a UI calls: :func:`catalog`, :func:`verify`,
:func:`vanilla`, :func:`image`, :func:`build`, :func:`open_build`,
:func:`read_mods`, :func:`preset_encode`, :func:`preset_decode`, the
randomizer's :func:`plan` and :func:`spoiler`, and :func:`restore` (art
comes with its step). JSON in and out: a recipe is a JSON object
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

A randomizer plan needs no image: :func:`plan` takes a seed and its
settings (``tools.randomizer``'s recipe) and returns Modkit's plan file. A
build recipe's ``randomizer`` (that recipe, and an ``obsidian_cost``) plans
it on the logic re-checked under the build's movement sliders and writes it
as the build's first layer, before the packs (Modkit's ``mod_apply``
order); the built image is read back against the plan before anything is
written: a placement a later layer changed is a conflict that leaves the
logic unverified (D28), any other difference fails the build (D35), and the
report's ``randomizer`` gives the verdict (``tools.randomizer.generator``)::

    {"iso": "<a vanilla image>", "packs": {...}, "randomizer": {"seed": "2", "share": "AZR-AAEA"}}
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from azurkit import __version__
from azurkit.core import gate, iso
from azurkit.edits import manifest as edits
from azurkit.edits import preset, xbr
from azurkit.edits.layer import Layer
from azurkit.tools import mods, randomizer
from azurkit.tools.randomizer import generator

__all__ = ["catalog", "verify", "vanilla", "image", "build", "open_build", "read_mods", "preset_encode",
           "preset_decode", "plan", "spoiler", "restore"]
RECIPE = ("iso", "packs", "xbr", "randomizer")
SETUP = ("ticked", "values", "xbr")   # a UI's remembered setup (D915, :func:`restore`)
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
    (``None`` where the image's XBE holds it), ``whole`` (the range of
    whole numbers it takes, its encoding's, or ``None``) and
    ``logic_floor`` (``"min"`` or ``"max"``: the side of its default past
    which a randomized build's logic is unverified, D83(c); ``None``)."""
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


def _plan(recipe: Mapping) -> tuple[gate.Stamp, dict[str, bytes], list[Layer], Callable | None]:
    """The recipe's vanilla image (its build files checked, D27), the files
    read from it, its randomizer's layer (its plan written, the first), each
    pack's layer, then its xbr operations' (the Data tool's, after the
    packs), and the randomizer's read-back of the built image (``None``
    without one); every refusal named."""
    packs = _packs(recipe)
    ops = xbr.normalize(recipe.get("xbr", []))
    if not isinstance(recipe.get("iso"), str):
        raise ValueError("recipe: iso names no image")
    prepared = generator.prepare(recipe["randomizer"], packs) if "randomizer" in recipe else None
    stamp = gate.verify(recipe["iso"], whole=False)
    chosen = {name: pack for name, pack in mods.PACKS.items() if name in packs}
    with iso.Reader(stamp.path) as r:
        names = [f for pack in chosen.values() for f in pack.files()] + xbr.files(ops)
        names += generator.files(prepared) if prepared else []
        base = {file: r.read(file) for file in dict.fromkeys(names) if file in stamp.release.files}
    layers, failed, judge = [], [], None
    if prepared is not None:
        layers.append(generator.plan_layer(prepared, base))   # a WriteError or LayerError: nothing planned on
        reasons = generator.movement_reasons(packs, catalog()["packs"])

        def judge(made: iso.Image, manifest: edits.Manifest) -> dict:
            return {generator.TOOL: generator.read_back(prepared, made, manifest.layers, manifest.conflicts,
                                                        reasons)}
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
    return stamp, base, layers, judge


def _report(made: edits.Manifest) -> dict:
    return {"release": made.release.name, "label": made.release.label,
            "layers": [{"id": la.id, "sites": len({c.group for c in la.changes}),
                        "bytes": sum(len(c.after) for c in la.changes)} for la in made.layers],
            "result": dict(made.result), "conflicts": [str(c) for c in made.conflicts],
            "notes": [note for la in made.layers for note in la.notes]} | (
        {"randomizer": made.verdicts[generator.TOOL]} if generator.TOOL in made.verdicts else {})


def image(recipe: Mapping) -> tuple[iso.Image, dict]:
    """The image ``recipe`` builds, unwritten, and its report: the release,
    each layer's sites and bytes, the sha256 of each file that differs from
    vanilla, every conflict (D28) and each layer's notes (a slider value
    past float32's range, written as the infinity it saturates to, Q110);
    with a randomizer, its verdict (``randomizer``: the seed, share string,
    settings, plan sha256, the movement sliders it stands on,
    ``logic_verified`` with each reason it is false, ``why_not``, and the
    placements a later layer changed, ``conflicts``)."""
    stamp, base, layers, judge = _plan(recipe)
    made, manifest = edits.image(stamp, layers, base, judge=judge)
    return made, _report(manifest)


def build(recipe: Mapping, out: str, *, progress: Callable[[int, int], object] | None = None) -> dict:
    """Write the image ``recipe`` builds to ``out`` (never its input or a
    vanilla image, D36); :func:`image`'s report with the output's path,
    size and sha256. ``progress(done, total)`` follows the write; an
    exception it raises cancels it, and nothing is written."""
    stamp, base, layers, judge = _plan(recipe)
    target = Path(out)
    for release in gate.RELEASES:
        if (vanilla := gate.find(release)) and target.exists() and target.samefile(vanilla):
            raise ValueError(f"{target}: it is the vanilla {release.label} image, which a build never writes over")
    sha256, manifest = edits.build(stamp, layers, target, base=base, progress=progress, judge=judge)
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
    normalized, and ``randomizer`` (the seed and share string a randomized
    build's plan replays from); ``packs`` only when it has a packs layer (a
    build's packs are then its packs, and no others). Every refusal named."""
    found = preset.read(given)
    out: dict = {}
    for layer in found["layers"]:
        if (layer["tool"], layer["kind"]) == ("mods", "packs"):
            out["packs"] = _packs({"packs": layer["recipe"]})
        elif (layer["tool"], layer["kind"]) == (xbr.TOOL, xbr.KIND) and set(layer["recipe"]) == {"ops"}:
            out["xbr"] = xbr.normalize(layer["recipe"]["ops"])
        elif (layer["tool"], layer["kind"]) == (generator.TOOL, generator.KIND):
            out["randomizer"] = generator.normalize(layer["recipe"])
        else:
            raise ValueError(f"preset: no tool {layer['tool']!r} with {layer['kind']!r} "
                             "(AzurKit's: mods with packs, data with xbr, randomizer with plan)")
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
    (Q174): a recipe with a ``replace_bytes`` is refused by name, as is
    one with a ``randomizer`` (its link comes with the page's tab, which
    reads it: Step 4.2c)."""
    if isinstance(recipe, Mapping) and "randomizer" in recipe:
        raise ValueError("preset: a share link doesn't carry a randomizer yet (its tab comes with Step 4.2c): "
                         "share the seed and share string")
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


def plan(recipe: Mapping) -> dict:
    """A randomizer plan: the fill of ``recipe``'s seed (any string) under
    the database's default settings (D144), a settings file's table
    (``settings``) or a share string (``share``), as Modkit's plan file's
    object (its format and generator, the seed, the attempt that passed,
    the settings, their share string and digest, the database's digest,
    every authored pool location's item, and the sha256 of the rest). The
    same recipe gives the same plan on every host. A refusal names the
    setting, or the progression items no attempt found a safe spot for."""
    return randomizer.plan(recipe)


def spoiler(plan: Mapping) -> dict:
    """``{"lines": [...]}``, the spoiler of a plan file's object: its
    settings, the spheres with each progression item's obtain and return
    paths, the traps and the rest. A plan from another database, format or
    generator, or an edited one, is refused by name."""
    return {"lines": randomizer.spoiler(plan)}


def restore(setup: object) -> dict:
    """A UI's remembered setup (D915: the packs it had ticked, each setting
    it had changed, its pack ticked or not, and a loaded recipe's config.xbr
    ``set`` operations, ``{"ticked": [pack], "values": {pack: {slider:
    value}}, "xbr": [operation]}``; never an image, its path or anything
    read from one), as the UI applies it, with ``dropped``: what no longer
    normalizes (a pack renamed or retired, a setting gone, a value its
    slider refuses, a pack without one it requires, an operation a link
    couldn't carry), each left out and named, never applied. It never
    refuses: a setup it can't read is dropped whole, by name."""
    if not isinstance(setup, Mapping) or not set(setup) <= set(SETUP):
        return {"ticked": [], "values": {}, "xbr": [], "dropped": ["your last setup (not one AzurKit reads)"]}
    ticked, dropped = setup.get("ticked", []), []
    if not isinstance(ticked, list):
        ticked, dropped = [], ["the ticked packs (not a list of names)"]
    dropped += [f"{name} (no such pack)" for name in ticked if not (isinstance(name, str) and name in mods.PACKS)]
    on = [name for name in mods.PACKS if name in ticked]
    while lost := [name for name in on if not set(mods.PACKS[name].requires) <= set(on)]:
        dropped += [f"{name} (needs {', '.join(r for r in mods.PACKS[name].requires if r not in on)})" for name in lost]
        on = [name for name in on if name not in lost]
    values, why = mods.salvage(setup.get("values", {}))
    ops, kept = setup.get("xbr", []), []
    if not isinstance(ops, list):
        ops, why = [], [*why, "the config.xbr values (not a list)"]
    for k, op in enumerate(ops, 1):
        try:
            if not (isinstance(op, Mapping) and op.get("op") == "set"):
                raise ValueError("a setup holds set operations only, Q174")
            kept += xbr.normalize([op])
        except ValueError as exc:
            why.append(f"config.xbr value {k} ({str(exc).replace('xbr op 1 (set): ', '')})")
    return {"ticked": on, "values": {name: v for name, v in values.items() if v}, "xbr": kept,
            "dropped": list(dict.fromkeys(dropped + why))}
