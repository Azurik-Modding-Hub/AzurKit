"""The randomizer's generator layer (Step 4.2b): a plan written as a
build's first layer, before the packs (Modkit's ``mod_apply`` order), the
read-back of the built image against it (D28, D35), and the movement check
through the packs' catalog (D83(c)).

- :func:`prepare`: the recipe checked, the build's movement sliders
  (``physics.slider_values`` of its packs), and the plan Modkit's
  ``layer.plan_for`` makes on the logic re-checked under them (a run under
  garret4's falls back to his, AZ-606), with each reason that leaves its
  logic unverified.
- :func:`plan_layer`: the writer's writes (``writer.layout`` and its
  per-file writes, each computed from the vanilla bytes), one group a node
  graph (its new strings, its TOC size and each location it repoints land
  whole, ``edits.layer.compose``), the obsidian cost's lock thresholds
  as one more group, and :func:`contained`'s touches in config.xbr, one
  group a species.
- :func:`read_back`: ``writer.read_back`` of the built image; a difference
  a later layer explains (it wrote the location's type field, its name
  field or the string that names, or a conflict dropped its graph's group)
  is a D28 conflict and the logic unverified, and any other fails the
  build, by name (D35); a contained touch's cells likewise.
- :func:`movement_reasons`: the packs' sliders the logic doesn't model, past
  their ``logic_floor`` (the catalog's), and the speed sliders at 0 or less
  whose move never ends: each leaves the logic unverified, never refused.
  A worn body's are the characters' (``tools.characters.reasons``), which
  the sdk joins to these (Step 4.3c2).
- :func:`spoiler`: the build's spoiler, Modkit's ``--spoiler`` file (Step
  4.2c1), and :func:`check`: a link's recipe checked before a page loads it.

``layer``, ``writer``, ``movement`` and ``physics`` are Modkit's, installed
by the oracle sync; this module is AzurKit's. It never imports the packs
(the tools don't import each other): the sdk hands it their values and
catalog.
"""

from __future__ import annotations

import collections
import hashlib
import math
import struct
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import SimpleNamespace

from azurkit.core import iso
from azurkit.core.progress import note
from azurkit.core.xbr import Document, edits
from azurkit.edits.layer import Change, Conflict, Layer
from azurkit.tools.randomizer import layer, physics, writer
from azurkit.tools.randomizer.planner.loader import kept_logic
from azurkit.tools.randomizer.planner.settings import settings_from_table, share_decode, share_encode

TOOL, KIND = "randomizer", "plan"
LAYER = layer.LAYER      # the layer's id, as Modkit names it in a conflict
RECIPE = ("seed", "settings", "share", "obsidian_cost")
OBSIDIAN_GROUP = f"{LAYER} obsidian lock thresholds"
CONFIG, ENGINE = "gamedata/config.xbr", "critters_engine"
CONTAINED_GROUP = f"{LAYER} contained touch"   # + its species: one group a species (contained)
TOUCH = ("collisionRadius", "scale", "collisionAspectRatio", "playerCollisionRadius")


@dataclass
class Prepared:
    """A build's plan: the layer's recipe (the seed, the plan's share string,
    the obsidian cost when given), the plan and the logic it stands on, and
    the reasons its logic is unverified so far."""
    recipe: dict
    plan: object
    logic: object
    why_not: list[str] = field(default_factory=list)
    edits: dict = field(default_factory=dict)    # writer.layout's, by graph key


def _skips(db) -> dict:
    return {sid: s for sid, (_, s) in db.skips.items()}


def normalize(recipe: object) -> dict:
    """``recipe`` checked: its keys, the seed a string, at most one of
    ``settings`` (a settings file's table) and ``share`` (a share string),
    and ``obsidian_cost`` any number whose thresholds (x1 to x10) a float32
    holds (D23: never clamped). ``ValueError`` names the first refusal."""
    if not isinstance(recipe, Mapping):
        raise ValueError(f"randomizer: a JSON object, not {type(recipe).__name__}")
    if unknown := sorted(set(recipe) - set(RECIPE), key=str):
        raise ValueError(f"randomizer: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(RECIPE)})")
    if not isinstance(recipe.get("seed"), str):
        raise ValueError("randomizer: seed is a string (any string; the same seed and settings give the same plan)")
    if "settings" in recipe and "share" in recipe:
        raise ValueError("randomizer: settings and share both give the settings: give one")
    if "settings" in recipe and not isinstance(recipe["settings"], Mapping):
        raise ValueError("randomizer: settings is a settings file's table")
    if "share" in recipe and not isinstance(recipe["share"], str):
        raise ValueError("randomizer: share is a share string (AZR-...)")
    if "obsidian_cost" in recipe:
        cost = recipe["obsidian_cost"]
        try:
            ok = not isinstance(cost, bool) and isinstance(cost, (int, float)) and math.isfinite(cost) \
                and bool(struct.pack("<f", cost * layer.OBSIDIAN_LOCK_COUNT))
        except OverflowError:
            ok = False
        if not ok:
            raise ValueError(f"randomizer: obsidian_cost {cost!r}: the lock thresholds (the cost x 1 to "
                             f"{layer.OBSIDIAN_LOCK_COUNT}) are finite float32s (at most 3.4e38)")
    return dict(recipe)


def check(recipe: object) -> dict:
    """:func:`normalize`'s ``recipe`` with its settings table or share
    string checked as a build checks them (a link's, before its page loads
    it); ``ValueError`` names the first refusal."""
    recipe = normalize(recipe)
    skips = _skips(kept_logic().db)
    if "settings" in recipe:
        settings_from_table(recipe["settings"], skips, "settings")
    if "share" in recipe:
        share_decode(recipe["share"], skips)
    return recipe


def prepare(recipe: Mapping, packs: Mapping[str, Mapping[str, float]]) -> Prepared:
    """The plan :func:`normalize`'s ``recipe`` makes under the build's
    ``packs`` (``{pack: {slider: value}}``, normalized), on the logic
    re-checked under their movement sliders; a share string made for other
    sliders is refused (AZ-383). ``ValueError`` names a setting refused or
    the items no attempt found a safe spot for (D35)."""
    recipe = normalize(recipe)
    db = kept_logic().db
    share = recipe.get("share")
    if "settings" in recipe:
        share = share_encode(settings_from_table(recipe["settings"], _skips(db), "settings"), _skips(db))
    args = SimpleNamespace(plan=None, seed=recipe["seed"], settings=None, share=share, skip_ceiling=None,
                           movement_tier=None, dark_fire=None, skip=None, no_skip=None, exclude_category=None)
    note("placing the items")   # the seed's fill starts (core.progress: the call's stage folds it)
    plan, logic, _, why = layer.plan_for(args, db, sliders(packs))
    made = {"seed": plan.doc["seed"], "share": plan.doc["share"]}
    if "obsidian_cost" in recipe:
        made["obsidian_cost"] = recipe["obsidian_cost"]
    why = [r for r in [layer.obsidian_reason(recipe.get("obsidian_cost"))] if r] + list(why)
    return Prepared(made, plan, logic, why, writer.layout(plan.placement, db))


def files(prepared: Prepared) -> list[str]:
    """The image's files the layer writes: each level a graph edit names,
    ``town.xbr`` for an obsidian cost, and ``config.xbr``, where
    :func:`contained` reads the items' touches (and may write some)."""
    names = {f"gamedata/{edit.file}.xbr" for edit in prepared.edits.values()} | {CONFIG}
    return sorted(names | ({"gamedata/town.xbr"} if "obsidian_cost" in prepared.recipe else set()))


def _change(base: bytes, file: str, offset: int, data: bytes, group: str) -> Change:
    return Change(file, offset, hashlib.sha256(base[offset:offset + len(data)]).hexdigest(), bytes(data), group)


def _cells(engine, species: str) -> tuple[float, float, float, float | None]:
    """``species``' :data:`TOUCH` cells in critters_engine, empty ones as
    the game reads them (0x49480: 1.0, 1.0, 1.0; playerCollisionRadius
    ``None``, which the game reads as collisionRadius)."""
    cr, scale, aspect, pcr = (engine.number(species, row) for row in TOUCH)
    return (1.0 if cr is None else cr), (1.0 if scale is None else scale), (1.0 if aspect is None else aspect), pcr


def touch(engine, species: str) -> tuple[float, float]:
    """Where the game takes ``species``' pickup (Modkit's RE_DATA "Pickups
    and exit triggers"): when the player's centre lies in the ellipsoid of
    horizontal radius R = scale x playerCollisionRadius (else
    collisionRadius) + 1 and half-height Z = scale x collisionRadius x
    collisionAspectRatio + 1 round the item's centre, which rests Z - 1
    over its floor, through any wall. ``(R, Z)`` in metres."""
    cr, scale, aspect, pcr = _cells(engine, species)
    return scale * (cr if pcr is None else pcr) + 1, scale * cr * aspect + 1


def inside(placed: tuple[float, float], vanilla: tuple[float, float]) -> bool:
    """Whether the :func:`touch` ``placed`` lies inside ``vanilla``, both
    resting on one floor (so both ellipsoids' bottoms meet, 1 m under it):
    Z <= Zv and R^2 / Z <= Rv^2 / Zv."""
    (r, z), (rv, zv) = placed, vanilla
    return z <= zv and r * r * zv <= rv * rv * z


def contained(placement: Mapping[str, str], db, config: bytes) -> list[tuple[str, list[tuple[int, bytes]]]]:
    """The touches a plan's ``placement`` writes into the vanilla
    ``config`` (config.xbr's bytes), each species' ``(its name, its
    writes)`` (AZ-834, D1041). A container (derived ``enclosed_by``: an ice
    or acid block, a force field, a gem rock, a gate's region) holds in
    only what the game can't touch through it, and the writer keeps each
    location's vanilla point, so a species the image holds once (its one
    copy, sitting there) whose :func:`touch` isn't :func:`inside` the
    vanilla item's there gets that item's collision (collisionRadius and
    collisionAspectRatio, and playerCollisionRadius where either sets one,
    at the placed species' own scale; its model unchanged): it touches,
    collides and rests as that item did, so it is taken only once the
    container opens, for any body. A species held more than once keeps its
    own, so it looks and plays the same everywhere."""
    names = writer.Names(db)
    held = {lid: (names.target(lid, placement[lid]) if lid in placement else None) or loc["template"]
            for lid, loc in names.locations.items()}
    copies = collections.Counter(held.values())
    engine, out = Document(config).tables[ENGINE], []
    for lid in sorted(loc["id"] for doc in db.derived.values() for loc in doc["locations"]
                      if loc.get("enclosed_by") and loc["id"] in held):
        species, was = held[lid], names.locations[lid]["template"]
        if copies[species] != 1 or species == was or inside(touch(engine, species), touch(engine, was)):
            continue
        (cr, scale, aspect, pcr), own = _cells(engine, was), _cells(engine, species)
        cells = {"collisionRadius": cr * scale / own[1], "collisionAspectRatio": aspect}
        if pcr is not None or own[3] is not None:
            cells["playerCollisionRadius"] = (cr if pcr is None else pcr) * scale / own[1]
        out.append((species, [w for row, value in cells.items()
                              for w in edits.set_number(engine, species, row, value, fill=True)]))
    return out


def plan_layer(prepared: Prepared, base: Mapping[str, bytes]) -> Layer:
    """The layer :func:`prepare`'s plan writes over the vanilla files
    ``base`` (:func:`files`); ``writer.WriteError`` names every location
    it can't write, ``layer.LayerError`` a town.xbr too short for the
    thresholds, before anything is written (D35)."""
    db, changes, problems = prepared.logic.db, [], []
    for key, edit in sorted(prepared.edits.items()):
        file = f"gamedata/{edit.file}.xbr"
        writes, found = writer._level_writes(base[file], edit.file, [edit], db)
        problems += found
        changes += [_change(base[file], file, at, data, f"{LAYER} {key}") for at, data in writes]
    if problems:
        raise writer.WriteError(problems)
    if (cost := prepared.recipe.get("obsidian_cost")) is not None:
        town = base["gamedata/town.xbr"]
        changes += [_change(town, "gamedata/town.xbr", at, struct.pack("<f", value), OBSIDIAN_GROUP)
                    for at, value in layer._thresholds(town, cost)]
    for species, writes in contained(prepared.plan.placement, db, base[CONFIG]):
        changes += [_change(base[CONFIG], CONFIG, at, data, f"{CONTAINED_GROUP} {species}") for at, data in writes]
    return Layer(LAYER, TOOL, KIND, dict(prepared.recipe), tuple(changes))


def read_back(prepared: Prepared, image: iso.Image, layers: Sequence[Layer], conflicts: Sequence[Conflict],
              reasons: Sequence[str] = (), progress: Callable[[int, int], object] | None = None) -> dict:
    """The randomizer's verdict on the built ``image`` (its ``layers``,
    after ``compose``'s ``conflicts``) after ``reasons`` (the movement's,
    :func:`movement_reasons`): its seed, share string, settings, plan
    sha256, the conflicts a later layer made (D28) and whether the logic
    still holds, with each reason it doesn't. A contained touch's cells
    (:func:`contained`) are read back too: one a later layer changed
    leaves its item takeable through its container. ``ValueError`` names
    every difference no later layer explains (D35). ``progress(done, total)``
    hears each level file read back (``writer.read_back``)."""
    db, plan = prepared.logic.db, prepared.plan
    locs, later, failures = writer._locations(db), [], []
    dropped = {c.dropped: c.layer for c in conflicts if c.overwrote == LAYER}
    problems = writer.read_back(image, plan.placement, db, progress)
    held: dict[str, bytes] = {}
    for problem in problems:
        lid = problem.split(":", 1)[0]
        if (loc := locs.get(lid)) is None:
            failures.append(problem)
            continue
        file = f"gamedata/{lid.split('/', 1)[0]}.xbr"
        if file not in held:
            with iso.Reader(image) as r:
                held[file] = r.read(file)
        spans = layer._location_ranges(held[file], loc)
        who = {la.id for la in layers if la.id != LAYER for c in la.changes if c.file == file
               and any(c.offset < s.stop and s.start < c.offset + len(c.after) for s in spans)}
        if (by := dropped.get(f"{LAYER} {writer.graph_of(lid)}")) is not None:
            who.add(by)
        if who:
            later.append(f"{problem}: {', '.join(sorted(who))} wrote it after the randomizer (D28)")
        else:
            failures.append(problem)
    touches = [c for la in layers if la.id == LAYER for c in la.changes if c.group.startswith(CONTAINED_GROUP)]
    opened = []   # the touches a later layer explains (D28)
    if touches:
        with iso.Reader(image) as r:
            config = r.read(CONFIG)
    for group in dict.fromkeys(c.group for c in touches):
        mine = [c for c in touches if c.group == group]
        if all(config[c.offset:c.offset + len(c.after)] == c.after for c in mine):
            continue
        problem = f"{group.removeprefix(f'{LAYER} ')}: config.xbr's critters_engine doesn't hold the plan's cells"
        who = {la.id for la in layers if la.id != LAYER for d in la.changes if d.file == CONFIG
               and any(d.offset < c.offset + len(c.after) and c.offset < d.offset + len(d.after) for c in mine)}
        if (by := dropped.get(group)) is not None:
            who.add(by)
        if who:
            opened.append(f"{problem}: {', '.join(sorted(who))} wrote it after the randomizer (D28)")
        else:
            failures.append(problem)
    if failures:
        shown = "; ".join(failures[:20]) + (f"; ... and {len(failures) - 20} more" if len(failures) > 20 else "")
        raise ValueError(f"the image doesn't read back to the plan ({len(failures)}): {shown}")
    why = list(prepared.why_not) + list(reasons)
    if later:
        why.append(f"{len(later)} placement(s) changed by a later layer")
    if opened:
        why.append(f"{len(opened)} contained item(s) given another touch by a later layer, so they may be taken "
                   "through their container")
    return {"seed": plan.doc["seed"], "share": plan.doc["share"], "settings": layer.settings_doc(plan.settings),
            "plan": plan.doc["sha256"], "attempt": plan.doc["attempt"],
            "sliders": {pack: dict(values) for pack, values in sorted(plan.settings.sliders.items())},
            "obsidian_cost": prepared.recipe.get("obsidian_cost"), "logic_verified": not why,
            "why_not": why, "conflicts": later + opened}


def movement_reasons(packs: Mapping[str, Mapping[str, float]], catalog: Sequence[Mapping]) -> list[str]:
    """Why the build's ``packs`` (``{pack: {slider: value}}``; a slider not
    given holds its default) leave a plan's logic unverified, by the packs'
    ``catalog`` (each pack's name and sliders, each with its ``default`` and
    ``logic_floor``): a slider no certificate reads (``movement.MODELLED``:
    the roll, the swim; the enemies) past its floor, below vanilla's
    (``"min"``) or above (``"max"``), and a speed slider at 0 or less whose
    move never ends (``layer.LOCKS``) or that leaves enemies unkillable
    (``layer.UNKILLABLE``). Modkit's ``layer.movement_reasons`` for packs."""
    from azurkit.tools.randomizer.movement import MODELLED

    why = []
    for pack in catalog:
        if pack["name"] not in packs or not any(s.get("logic_floor") for s in pack["sliders"]):
            continue
        values = packs[pack["name"]]
        for s in pack["sliders"]:
            key = (pack["name"], s["name"])
            if physics.SLIDERS.get(key, (None,))[0] in MODELLED:
                continue    # the logic re-checks it (plan_for)
            value = values.get(s["name"], s["default"])
            below = s.get("logic_floor") == "min" and value < s["default"]
            above = s.get("logic_floor") == "max" and value > s["default"]
            if below or above:
                what = "movement" if key in physics.SLIDERS else "enemy strength"
                why.append(f"{key[0]} {key[1]} {value:g} is {'below' if below else 'above'} vanilla's "
                           f"{s['default']:g}, {what} the logic doesn't model (D83(c))")
            if key in layer.LOCKS and value <= 0:
                why.append(f"{key[0]} {key[1]} {value:g} is a lock, not a speed: {layer.LOCKS[key]}")
            if key in layer.UNKILLABLE and value <= 0:
                why.append(f"{key[0]} {key[1]} {value:g} leaves enemies unkillable: {layer.UNKILLABLE[key]}")
    return why


def sliders(packs: Mapping[str, Mapping[str, float]]) -> dict[str, dict[str, float]]:
    """The movement sliders a build of ``packs`` (normalized) plans on, and
    its share string records (``physics.slider_values``, AZ-383)."""
    return physics.slider_values(packs, list(packs))


def spoiler(prepared: Prepared, verdict: Mapping) -> str:
    """The build's spoiler, as Modkit's ``randomize-full --spoiler`` writes
    it: the plan's spheres and paths on the logic it stands on, with the
    build's ``logic_verified`` and each reason it is false on its second
    line (``layer.spoiler_text``)."""
    return layer.spoiler_text(prepared.plan, prepared.logic, verdict["logic_verified"], verdict["why_not"])
