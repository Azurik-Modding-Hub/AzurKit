"""The one surface a UI calls: :func:`catalog`, :func:`verify`,
:func:`vanilla`, :func:`image`, :func:`build`, :func:`open_build`,
:func:`read_mods`, :func:`preset_encode`, :func:`preset_decode`, the
randomizer's :func:`plan`, :func:`spoiler`, :func:`randomizer_settings`
(its tab's), :func:`tracker` (the item tracker's) and :func:`art` and
:func:`art_world` (its maps and icons, drawn from the player's image),
:func:`restore`, and Azurik-Custom-Content's :func:`content`,
:func:`content_install` and :func:`content_check` (the Characters tab's
community entries). JSON in and
out: a recipe is a JSON object and each call returns one; :func:`image`
also returns the image, unwritten, which the web page joins into a Blob
(``iso.Image.segments``). A refusal is a
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
report's ``randomizer`` gives the verdict (``tools.randomizer.generator``)
and its ``spoiler`` the build's spoiler (Modkit's ``--spoiler`` file)::

    {"iso": "<a vanilla image>", "packs": {...}, "randomizer": {"seed": "2", "share": "AZR-AAEA"}}

A share link carries a recipe's randomizer too (its seed, settings and
obsidian cost), as an AzurKit build's mods file does.

A recipe's ``character`` dresses the player in a species' body (Modkit's
swap, ``tools.characters``: the body and its clips, its attacks, weapon,
sounds and fx, and the shims it hooks): the body's size folds into
player_physics' walk and roll before the packs (Modkit's ``size_params``;
the speed toggle flips those two to the body's own), and the character
layer stacks after the packs::

    {"iso": "<a vanilla image>", "packs": {...}, "character": {"species": "keylord", "mode": "garret4"}}

A character's ``species`` may name a variant (a recipe over a base species:
its sculpted mesh, painted textures, jiggle springs, clips and sounds), a
built-in or one of the recipe file ``variant_file`` names, its shapes sized
by ``shapes``::

    {"character": {"species": "mine", "variant_file": "<recipes.json>", "shapes": {"hips": 1.2}}}

A randomized build may wear a character (Modkit's ``randomize-full --seed``
with ``--player-character``): the plan stands on the walk and roll the
body's size folds, and what the body leaves unmodelled (its grade, its
attacks, its size) leaves the logic unverified, never refused. A character
isn't carried by a build's mods file (:func:`open_build`) or a share link
(:func:`preset_encode`) yet: each refuses it by name.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from collections.abc import Callable, Mapping
from pathlib import Path

from azurkit import __version__
from azurkit.core import gate, iso
from azurkit.edits import manifest as edits
from azurkit.edits import preset, xbr
from azurkit.edits.layer import Layer
from azurkit.tools import characters, mods, randomizer
from azurkit.tools.randomizer import generator, tracking
from azurkit.tools.randomizer import layer as rando_layer

__all__ = ["catalog", "verify", "vanilla", "image", "build", "open_build", "read_mods", "preset_encode",
           "preset_decode", "plan", "spoiler", "randomizer_settings", "tracker", "art", "art_world", "restore",
           "content", "content_install", "content_check"]
RECIPE = ("iso", "packs", "xbr", "randomizer", "character")
SETUP = ("ticked", "values", "xbr", "randomizer")   # a UI's remembered setup (D915, :func:`restore`)
SOURCE = "https://raw.githubusercontent.com/Azurik-Modding-Hub/Azurik-Custom-Content/main/"
"""Where Azurik-Custom-Content is read from by default (D966: the hub's, public at Step 4.4)."""
SOURCE_ENV = "AZURKIT_CONTENT_SOURCE"   # set, it wins over a host's setting (the tests', a private play's)
#: A UI's tabs, one an area, in the owner's order (D901), each with whether
#: its area works yet: a tab shows only once it does (D902).
TABS = (("patches", "Patches", True), ("randomizer", "Randomizer", True), ("characters", "Characters", False),
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
    which a randomized build's logic is unverified, D83(c); ``None``).
    ``randomizer``: what the Randomizer tab offers, with D144's defaults
    (``tools.randomizer.options``)."""
    return {"tabs": [{"id": tab, "title": title} for tab, title, works in TABS if works],
            "categories": [{"id": category, "title": title, "description": line}
                           for category, (title, line) in mods.CATEGORIES.items()],
            "packs": [{"name": p.name, "description": p.description, "category": p.category,
                       "default_on": p.default_on, "releases": list(p.releases), "requires": list(p.requires),
                       "sliders": [s.catalog() for s in p.sliders()]} for p in mods.PACKS.values()],
            "randomizer": randomizer.options()}


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


def _plan(recipe: Mapping) -> tuple[gate.Stamp, dict[str, bytes], list[Layer], Callable | None,
                                   generator.Prepared | None]:
    """The recipe's vanilla image (its build files checked, D27), the files
    read from it, its randomizer's layer (its plan written, the first), each
    pack's layer, then its xbr operations' (the Data tool's, after the
    packs), the randomizer's read-back of the built image and its plan
    (``None`` without one); every refusal named."""
    packs = _packs(recipe)
    ops = xbr.normalize(recipe.get("xbr", []))
    character = characters.normalize(recipe["character"]) if "character" in recipe else None
    if not isinstance(recipe.get("iso"), str):
        raise ValueError("recipe: iso names no image")
    prepared = None
    if "randomizer" in recipe and character is None:
        prepared = generator.prepare(recipe["randomizer"], packs)
    elif "randomizer" in recipe:   # checked now; planned below, on the walk and roll the body's size folds
        generator.check(recipe["randomizer"])
    stamp = gate.verify(recipe["iso"], whole=False)
    folded = vanilla = None
    inputs: dict[str, dict[str, float]] = {}
    if character is not None:   # the worn body's size folds into the walk and roll first (Modkit's size_params)
        from azurkit.tools.characters import ports

        vanilla = ports.Vanilla(stamp.release, stamp.path)
        folded = characters.size(character, vanilla)
        enabled, params = rando_layer.size_params(list(packs), packs, folded)
        if (fold := params.get(rando_layer.SIZE_PACK, {}).pop(rando_layer.SIZE_FOLD, None)) is not None:
            inputs[rando_layer.SIZE_PACK] = {rando_layer.SIZE_FOLD: fold}   # the speed toggle's walk and roll
        packs = mods.normalize({name: params.get(name, {}) for name in enabled})
        if "randomizer" in recipe:   # Modkit's randomize-full: the plan stands on the folded sliders (AZ-383)
            prepared = generator.prepare(recipe["randomizer"], packs)
    chosen = {name: pack for name, pack in mods.PACKS.items() if name in packs}
    with iso.Reader(stamp.path) as r:
        names = [f for pack in chosen.values() for f in pack.files()] + xbr.files(ops)
        names += generator.files(prepared) if prepared else []
        names += list(characters.READS) if character is not None else []
        base = {file: r.read(file) for file in dict.fromkeys(names) if file in stamp.release.files}
    layers, failed, judge = [], [], None
    if prepared is not None:
        layers.append(generator.plan_layer(prepared, base))   # a WriteError or LayerError: nothing planned on
        reasons = generator.movement_reasons(packs, catalog()["packs"])   # the worn body's join them below

        def judge(made: iso.Image, manifest: edits.Manifest) -> dict:
            return {generator.TOOL: generator.read_back(prepared, made, manifest.layers, manifest.conflicts,
                                                        reasons)}
    for name, pack in chosen.items():
        try:
            layers.append(mods.plan(pack, stamp.release, base, packs[name], [c for la in layers for c in la.claims],
                                    inputs.get(name)))
        except mods.PackError as exc:
            failed.append(str(exc))
    if character is not None and not failed:
        layer, lines, body = characters.plan(character, vanilla, layers,
                                             characters.packs_view(stamp.release, mods.PACKS), folded)
        if prepared is not None:   # Modkit's check_movement: its packs' reasons, then the body's
            reasons += body
        layers.append(Layer(layer.id, layer.tool, layer.kind, layer.recipe, layer.changes, layer.claims,
                            tuple(line.strip() for line in lines)))
    if ops:
        try:
            layers.append(xbr.plan(ops, stamp.release, base))
        except ValueError as exc:
            failed.append(str(exc))
    if failed:
        raise ValueError("; ".join(failed))
    return stamp, base, layers, judge, prepared


def _report(made: edits.Manifest, prepared: generator.Prepared | None) -> dict:
    out = {"release": made.release.name, "label": made.release.label,
           "layers": [{"id": la.id, "sites": len({c.group for c in la.changes}),
                       "bytes": sum(len(c.after) for c in la.changes)} for la in made.layers],
           "result": dict(made.result), "conflicts": [str(c) for c in made.conflicts],
           "notes": [note for la in made.layers for note in la.notes]}
    if prepared is not None:
        verdict = made.verdicts[generator.TOOL]
        tracking.prime(prepared.plan.doc, prepared.logic)
        out |= {"randomizer": verdict, "spoiler": generator.spoiler(prepared, verdict), "plan": prepared.plan.doc}
    return out


def image(recipe: Mapping) -> tuple[iso.Image, dict]:
    """The image ``recipe`` builds, unwritten, and its report: the release,
    each layer's sites and bytes, the sha256 of each file that differs from
    vanilla, every conflict (D28) and each layer's notes (a slider value
    past float32's range, written as the infinity it saturates to, Q110);
    with a randomizer, its verdict (``randomizer``: the seed, share string,
    settings, plan sha256, the movement sliders it stands on,
    ``logic_verified`` with each reason it is false, ``why_not``, and the
    placements a later layer changed, ``conflicts``) and its spoiler
    (``spoiler``: the text of Modkit's ``randomize-full --spoiler`` file) and
    its plan (``plan``: the plan file's object, which :func:`tracker` reads)."""
    stamp, base, layers, judge, prepared = _plan(recipe)
    made, manifest = edits.image(stamp, layers, base, judge=judge)
    return made, _report(manifest, prepared)


def build(recipe: Mapping, out: str, *, progress: Callable[[int, int], object] | None = None) -> dict:
    """Write the image ``recipe`` builds to ``out`` (never its input or a
    vanilla image, D36); :func:`image`'s report with the output's path,
    size and sha256. ``progress(done, total)`` follows the write; an
    exception it raises cancels it, and nothing is written."""
    stamp, base, layers, judge, prepared = _plan(recipe)
    target = Path(out)
    for release in gate.RELEASES:
        if (vanilla := gate.find(release)) and target.exists() and target.samefile(vanilla):
            raise ValueError(f"{target}: it is the vanilla {release.label} image, which a build never writes over")
    sha256, manifest = edits.build(stamp, layers, target, base=base, progress=progress, judge=judge)
    return _report(manifest, prepared) | {"out": str(target), "size": target.stat().st_size, "sha256": sha256}


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
    """The share link's fragment (``#p=…``) for ``recipe``'s randomizer
    (its seed, settings or share string and obsidian cost, checked as a
    build checks them), packs, normalized, and its ``set`` operations, never
    its image's path; given its build's report (:func:`image`), with the
    release it was built from and the sha256 of each file it changed. Names,
    numbers and hashes only (Q174): a recipe with a ``replace_bytes`` is
    refused by name, as is one with a ``character`` (no link carries one
    yet)."""
    packs = _packs(recipe)
    if "character" in recipe:
        raise ValueError("preset: a share link carries a randomizer, packs and set operations only, not a "
                         "character (yet)")
    made = {"format": preset.FORMAT, "schema_version": preset.SCHEMA_VERSION, "azurkit": __version__,
            "layers": [{"tool": generator.TOOL, "kind": generator.KIND,
                        "recipe": generator.check(recipe["randomizer"])}] if "randomizer" in recipe else []}
    made["layers"].append({"tool": "mods", "kind": "packs", "recipe": packs})
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
    normalized (``mods.normalize``), its ``set`` operations and its
    randomizer checked: a tool or pack AzurKit doesn't have, a value a
    slider refuses, a setting the randomizer refuses or a ``replace_bytes``
    (Q174) is refused by name."""
    found = preset.decode(text)
    for layer in found["layers"]:
        if (layer["tool"], layer["kind"]) == ("mods", "packs"):
            layer["recipe"] = _packs({"packs": layer["recipe"]})
        elif (layer["tool"], layer["kind"]) == (xbr.TOOL, xbr.KIND) and set(layer["recipe"]) == {"ops"}:
            layer["recipe"] = {"ops": _shared(xbr.normalize(layer["recipe"]["ops"]))}
        elif (layer["tool"], layer["kind"]) == (generator.TOOL, generator.KIND):
            layer["recipe"] = generator.check(layer["recipe"])
        else:
            raise ValueError(f"preset: no tool {layer['tool']!r} with {layer['kind']!r} "
                             "(AzurKit's: mods with packs, data with xbr, randomizer with plan)")
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


def randomizer_settings(given: Mapping) -> dict:
    """What the Randomizer tab shows for ``given``: its ``settings`` (a
    settings file's table), ``share`` (a share string) or ``file`` (a
    settings file's text, D144's Load settings), its
    ``obsidian_cost`` (vanilla's when not given) and the build's ``packs``
    (``{pack: {slider: value}}``, normalized): the settings as the tab
    holds them (format /2: its categories as they are), their share string
    with the packs' movement sliders, a ``note`` when a share string holds
    other sliders, each skip a setting can turn on (``skips``: its pick's
    id, name, rating, the ceiling's state and its toggle; D114, D275), the
    picks held and the forfeitable locations, what a build would leave
    unverified so far (``why_not``: the packs' movement past their logic
    floor, D83(c), a roll a skip on was proven at, an obsidian cost above
    vanilla's), the preflight's refusal (``preflight``, AZ-454; ``None``),
    the settings file of the settings (``file``, Save settings') and the
    skip groups (``groups``, D258: each group's picks with their variants'
    ratings, which a page compares with the Movement tier, ``tiers``).
    ``tools.randomizer.tab``; a refusal names the setting, the share string,
    the settings file or the pack."""
    if not isinstance(given, Mapping):
        raise ValueError(f"randomizer: a JSON object, not {type(given).__name__}")
    packs = _packs({"packs": given.get("packs", {})})
    view = randomizer.tab({k: v for k, v in given.items() if k != "packs"}, generator.sliders(packs))
    return view | {"why_not": generator.movement_reasons(packs, catalog()["packs"]) + view["why_not"]}


def tracker(given: Mapping) -> dict:
    """What the item tracker shows (D189, D249) for ``given``: ``plan`` (a
    plan file's object: :func:`plan`'s, or a randomized build's report's),
    ``marks`` (the spots collected: ``{"collected": [spot], "live": {spot:
    day clock or null}, "veto": [spot], "slot": a save slot or null}``, a
    live mark one the app's Live saw, a veto one a click took off), ``kit``
    (the element levels Live reads the game holding, which the reach holds
    past the marks, R1.41), ``held`` (Live's inventory, the Table's In game
    column), ``spoiler``, and ``toggle`` (a spot to mark or unmark) or
    ``reset``: the marks after it, the head line (the seed, share string,
    settings and skips on), the counter row (``status``: collected,
    reachable now, of how many, the sphere, victory in reach, the levels
    reached now and how many spots only a skip reaches), each spot's level,
    class, state (``got``, ``live``, ``near``, ``skip``: only with a skip,
    or ``far``) and item (once collected, or with ``spoiler``), and the
    Table's two trees (``table``: the items by kind and the spots by level,
    each row's collected, reachable now, left, total, where and the game's
    count). Modkit's tracker, the same verdicts on every host
    (``tools.randomizer.tracking``); a refusal names what it refuses."""
    return tracking.view(given)


def art(path: str, part: str) -> dict:
    """One part of the item tracker's pictures, drawn from the image at
    ``path`` (Step 4.2c3: the wheel, the app and the site hold none; a
    host keeps what this gives and draws each part once),
    each file it reads checked against its release's vanilla file
    (``gate.NotVanillaError`` names one that isn't): ``"icons"`` gives
    ``{"pictures": {"icons/<icon>": PNG bytes}}``, every item's and
    barrier's icon (the game's own model at 20 px, Modkit's), and a level
    of the world map (``tracker()``'s ``world.art.parts``) ``{"pictures":
    {floor: PNG bytes}, "entry": its maps.json entry, "thumb": PNG bytes}``:
    each floor seen from above, where its exits, items, spots, barriers,
    features and gems lie on it (in pixels, with their floor; ``frame``
    maps the world's metres to them), and its main floor's world-map
    thumbnail, which :func:`art_world` takes. Each picture is Modkit's
    pixel for pixel (``tests/test_art.py``). numpy draws them: a host
    without it can't."""
    from azurkit.tools.randomizer import art as drawn

    with drawn.Vanilla(path) as reader:
        out = drawn.part(reader, part)
    return {key: ({name: drawn.png(img) for name, img in value.items()} if key == "pictures"
                  else drawn.png(value) if key == "thumb" else value) for key, value in out.items()}


def art_world(parts: Mapping[str, Mapping]) -> dict:
    """The world map from each level's :func:`art` part (``{level:
    {"entry", "thumb"}}``, every level of the world map), and the maps'
    index, Modkit's ``maps.json``: ``{"pictures": {"world": PNG bytes},
    "index": {"world": {"title", "levels": {level: [x, y, w, h]}},
    "levels": {level: entry}}, "text": maps.json's text}``."""
    from azurkit.tools.randomizer import art as drawn
    from azurkit.tools.randomizer.tracking import GRID

    if not isinstance(parts, Mapping) or set(parts) != set(GRID):
        raise ValueError(f"art_world: a part for each level of the world map ({', '.join(GRID)})")
    picture, world = drawn.world({level: drawn.unpng(p["thumb"]) for level, p in parts.items()})
    entries = {level: p["entry"] for level, p in parts.items()}
    text = drawn.index(entries, world)
    return {"pictures": {"world": drawn.png(picture)}, "index": json.loads(text), "text": text}


def restore(setup: object) -> dict:
    """A UI's remembered setup (D915: the packs it had ticked, each setting
    it had changed, its pack ticked or not, and a loaded recipe's config.xbr
    ``set`` operations, ``{"ticked": [pack], "values": {pack: {slider:
    value}}, "xbr": [operation]}``; never an image, its path or anything
    read from one), as the UI applies it, with ``dropped``: what no longer
    normalizes (a pack renamed or retired, a setting gone, a value its
    slider refuses, a pack without one it requires, an operation a link
    couldn't carry), each left out and named, never applied. A setup's
    ``randomizer`` (the tab's: ``on``, ``seed``, ``settings`` and
    ``obsidian_cost``, ``tools.randomizer.remembered``) comes back
    checked, or is dropped whole, by name. It never refuses: a setup it
    can't read is dropped whole, by name."""
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
    rando = {}
    if "randomizer" in setup:
        try:
            rando = {"randomizer": randomizer.remembered(setup["randomizer"])}
        except ValueError as exc:
            why.append(f"the randomizer's settings ({exc})")
    return {"ticked": on, "values": {name: v for name, v in values.items() if v}, "xbr": kept,
            "dropped": list(dict.fromkeys(dropped + why))} | rando


def _source(given: object = None) -> str:
    """The content source: ``$AZURKIT_CONTENT_SOURCE``, else ``given`` (a
    host's setting), else :data:`SOURCE`; an http(s) URL or a folder's
    absolute path (``~`` expanded), refused by name otherwise."""
    source = os.environ.get(SOURCE_ENV) or given or SOURCE
    if not isinstance(source, str) or not source.strip():
        raise ValueError("content: the source is an http(s) URL or a folder's path")
    source = source.strip()
    if urllib.parse.urlsplit(source).scheme in ("http", "https"):
        return source if source.endswith("/") else source + "/"
    folder = Path(source).expanduser()
    if not folder.is_absolute():
        raise ValueError(f"content: {source} is neither an http(s) URL nor a folder's full path")
    return str(folder)


def _fetch(source: str) -> Callable[[str], bytes]:
    """``fetch(path)``: the bytes of the file at ``path`` of ``source``
    (:func:`_source`'s), at most the content folder's file limit;
    ``OSError`` names what failed. CPython hosts' (the app's, the CLI's):
    the site fetches in its page."""
    from azurkit.tools.characters import content

    def fetch(path: str) -> bytes:
        if not source.startswith(("http://", "https://")):
            return (Path(source) / path).read_bytes()
        import urllib.request

        url = urllib.parse.urljoin(source, urllib.parse.quote(path))
        try:
            with urllib.request.urlopen(url, timeout=60) as reply:
                data = reply.read(content.MAX_FILE + 1)
        except OSError as exc:   # urllib's HTTPError and URLError are OSErrors
            raise OSError(f"{url}: {getattr(exc, 'reason', exc)}") from None
        if len(data) > content.MAX_FILE:
            raise OSError(f"{url}: past the {content.MAX_FILE:,} bytes a content file may hold")
        return data
    return fetch


def content(given: Mapping | None = None) -> dict:
    """Azurik-Custom-Content as the Characters tab lists it (D913): the
    ``source`` read (:data:`SOURCE`, a host's setting ``given["source"]``, or
    ``$AZURKIT_CONTENT_SOURCE``), its manifest checked
    (``tools.characters.content.check``; the last one fetched, kept in the
    content folder, when the source can't be read, with ``why``), each
    entry's state against what the content folder holds (``entries``:
    install, installed at its version, or update, kept until its Update)
    and ``installed`` (the folder's ``installed.json``). CPython's: the
    site's page fetches, and its worker checks (:func:`content_check`)."""
    from azurkit.tools.characters import content as kit

    given = given or {}
    source, why, manifest = _source(given.get("source")), None, None
    try:
        raw = _fetch(source)(kit.MANIFEST)
        manifest = kit.check(raw)
        kit.ROOT.mkdir(parents=True, exist_ok=True)
        (kit.ROOT / kit.MANIFEST).write_bytes(raw)   # the last fetched, listed while the source can't be read
    except (OSError, ValueError) as exc:
        why = f"can't read {source}: {exc}"
        try:
            manifest = kit.check((kit.ROOT / kit.MANIFEST).read_bytes())
        except (OSError, ValueError):
            manifest = None
    record = kit.installed()
    return {"source": source, "manifest": manifest, "why": why, "entries": kit.states(manifest, record),
            "installed": record}


def content_install(given: Mapping) -> dict:
    """Install (or Update) the entry ``given["id"]`` of the content source
    (``given["source"]``, as :func:`content` reads it) into the content
    folder, with the entries it requires: every file's size and sha256
    checked before anything is written (D35), ``installed.json`` written
    last (``tools.characters.content.install``); :func:`content`'s view
    after it. A refusal names the entry and the file."""
    from azurkit.tools.characters import content as kit

    if not isinstance(given, Mapping) or not isinstance(given.get("id"), str):
        raise ValueError("content: name the entry to install")
    source = _source(given.get("source"))
    fetch = _fetch(source)
    kit.install(kit.check(fetch(kit.MANIFEST)), given["id"], fetch, source=source)
    return content({"source": given.get("source")})


def content_check(given: Mapping) -> dict:
    """The site's half of Install (its page fetches, this checks):
    ``given["manifest"]`` checked, and with ``id`` and ``files`` (``{path:
    bytes}``, what the page fetched of the entry and those it requires)
    every file verified as :func:`content_install` verifies it
    (``tools.characters.content.verify``): ``{"manifest", "install": [each
    entry's id it writes, those required first]}``, or the refusal named."""
    from azurkit.tools.characters import content as kit

    if not isinstance(given, Mapping):
        raise ValueError("content: a JSON object")
    manifest = kit.check(given.get("manifest"))
    if "id" not in given:
        return {"manifest": manifest, "install": []}
    chosen = kit.verify(manifest, given["id"], given.get("files") or {})
    return {"manifest": manifest, "install": [e["id"] for e in chosen]}
