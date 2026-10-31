"""The randomizer: its planner (Step 4.2a) and its generator layer, the
plan written as a build's first layer and read back (Step 4.2b,
:mod:`.generator`); the tracker comes with Step 4.2c.

:func:`plan` fills the database's authored levels for a seed and returns
the plan file's object, the same as Modkit's (``planner.plan.dumps`` writes
its file byte for byte), on the logic re-checked under a share string's
movement sliders (AZ-383); :func:`spoiler` reads a plan back into its
spoiler on the logic it was planned on. The planner (``planner/``), its
database (``data/``, our own logic data, no game bytes), the writer,
physics, movement and layer are Modkit's, which ``scripts/oracle_sync.py``
installs as they are (the modules through its rewrites): never edit them by
hand. ``generator.py``, ``ports.py`` (what they import of Modkit's engine,
on ours) and ``dbcache.py`` (no cache on disk) are AzurKit's. The fill runs
in the calling thread: Modkit's seed roll in a process pool isn't ported.

A recipe names the seed (any string) and at most one of ``settings`` (a
settings file's table, ``data/settings/defaults.toml``'s format) and
``share`` (a share string, ``AZR-...``); without either the plan takes the
database's defaults (D144)::

    {"seed": "2"}
    {"seed": "2", "share": "AZR-AAEA"}
    {"seed": "2", "settings": {"format": "azurik-rando-settings/1", "skip_ceiling": 0,
                               "movement_tier": "standard", "dark_fire": 1, "skip_override": {}}}

The Randomizer tab (Step 4.2c1, RANDOMIZER_PLAN §5.5) reads :func:`options`
(what it offers, with D144's defaults, no database) and :func:`tab` (what
its settings give: the share string, each skip a setting can turn on, and
what a build would leave unverified); a page holds its settings as
:func:`literal` gives them, and :func:`remembered` checks the setup it
keeps (D915).
"""

from __future__ import annotations

import collections
import functools
import json
import math
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import replace

from azurkit.core.progress import Steps
from azurkit.tools.randomizer import dbcache, layer
from azurkit.tools.randomizer.movement import logic_of, run_floor
from azurkit.tools.randomizer.planner import loader
from azurkit.tools.randomizer.planner.fill import fill, starved
from azurkit.tools.randomizer.planner.loader import DATA_DIR, kept_logic
from azurkit.tools.randomizer.planner.plan import load_plan, plan_doc, spoiler_lines
from azurkit.tools.randomizer.planner.settings import (
    CATEGORIES, MOVEMENT_TIERS, SETTINGS_FORMAT_ELEMENTAL, Settings, picks, settings_from_table,
    share_decode, share_encode, turnable)
from azurkit.tools.randomizer.planner.solver import Logic

# The wheel's and the frozen app's checked database comes with its Logic's tables (Step 4.3g, P4): kept_logic takes
# that Logic, a fresh one each call, and builds none (Step 2.221's hook; elsewhere it is None and kept_logic builds)
loader.SHIPPED = functools.partial(dbcache.shipped_logic, logic_type=Logic)

RECIPE = ("seed", "settings", "share")
#: The tab's offers (§5.5): Movement's three tiers (D261; a loaded safe shows as its own), the skip ceiling's none and
#: D259's three skip tiers (a loaded 1 shows as its own), and the fire levels dark areas need (D144).
MOVEMENT = (("standard", "Standard"), ("hard", "Hard"), ("frame_perfect", "Frame-perfect"), ("safe", "Safe (loaded)"))
CEILINGS = ((0, "None"), (2, "Standard"), (3, "Hard"), (4, "Frame-perfect"), (1, "Safe (loaded)"))
LOADED = {"movement_tier": "safe", "skip_ceiling": 1}   # offered only when a loaded setting holds it
MOVEMENT_TIP = ("How tight the jumps and flaps the logic may ask for are. Standard: a little care; room for an early "
                "press, a crooked stick, imperfect flaps. Hard: press within a frame of the edge, stick nearly "
                "straight, flaps nearly perfect. Frame-perfect: the physics limit: the perfect frame, a straight "
                "stick, ideal flaps.")
CEILING_TIP = "Turns on every skip rated at or below it; a skip's own toggle wins over it."
RATINGS = ("Unrated", "Safe", "Standard", "Hard", "Frame-perfect")   # a skip's difficulty 1-4 (the ceiling's names)
BARRIERS = "Stay vanilla in v1 (R2.2)."
#: The item rows (Modkit's Randomize page): each its category, ticked to shuffle it, or None, greyed: it stays vanilla;
#: its label and note, the kind its base-game count counts (:func:`base_counts`) and its icons (the page's own drawings,
#: Modkit's icon names).
ITEMS = (("fragments", "Disc fragments", "Guardians keep their 4th.", "disc_fragment",
          ("frag_air", "frag_water", "frag_fire", "frag_earth", "frag_life")),
         ("powers", "Elemental powers", "Air, water, fire and earth.", "power",
          ("power_air", "power_water", "power_fire", "power_earth")),
         ("upgrades", "Upgrades", "Swap among the 8 town vaults.", "upgrade",
          ("power_life", "power_staff1", "power_staff2", "power_ammo")),
         (None, "Keys", "Stay vanilla (I-9).", "key", ("key",)),
         ("gems", "Gems", "Clusters keep their yield.", "gem", ("gem_diamond", "gem_emerald", "gem_ruby", "gem_sapphire")),
         ("obsidians", "Obsidians", "Each lock stays reachable.", "obsidian", ("obsidian",)),
         ("consumables", "Fuel pickups", "Town's health and fuel dispensers stay.", "consumable", ("fuel",)),
         (None, "Fire barriers", BARRIERS, "firewall", ("fire_barrier",)),
         (None, "Ice blocks", BARRIERS, "iceblock", ("ice_block",)),
         (None, "Acid blocks", BARRIERS, "acidblock", ("acid_block",)),
         (None, "Smash walls", BARRIERS, "smashwall", ("smash_wall",)),
         (None, "Earth crystals", "Tree-song switches, vanilla in v1.", "crystal", ("crystal",)))
#: A barrier group the vanilla data names for no kind that has a requirement takes the kind its damage gives
#: (Modkit's ``render_level_maps.DAMAGE_KINDS``, M17, AZ-463).
DAMAGE_KINDS = {"watr": "firewall", "stem": "iceblock", "acid": "acidblock", "smsh": "smashwall"}
UPGRADES = ("power_life", "power_staff1", "power_staff2", "power_ammo")
#: D258: the skip groups (Modkit's ``gui/rando_view.SKIP_GROUPS``, our own data): a ticked group turns on each of its
#: picks rated at or below the Movement tier (a batch, D275, once every in-logic variant is), unticked by default.
SKIP_GROUPS = {"storage": "Power storage", "movement": "Roll jumps and flap tricks", "barriers": "Barrier skips",
               "dark": "Dark rooms without light", "bounds": "Out of bounds and super jumps"}
#: Each skip's group (Modkit's ``SKIP_GROUP``): every [[skip]] of tricks.toml, held ones too, by its tricks.
SKIP_GROUP = {
    **dict.fromkeys(("w1.pstorage_electric_arch", "w1.pstorage_steam_iceblock01", "w1.pstorage_water_firewall01",
                     "w2.pstorage_steam_iceblock02", "w3.pstorage_smash_shield", "f2.pstorage_air_flap",
                     "f3.pstorage_acid_acidblock01", "w4.pstorage_air_flap"), "storage"),
    **dict.fromkeys(("w4.rjump_leaves", "w4.rjump_frag_earth1", "a5.one_island_air2", "a6.rjump_platforms",
                     "f2.rjump_interior", "f6.rjump_terraces", "f6.rjump_terraces_air1", "f6.mound_climb_air1",
                     "life.rjump_second_switch", "w3.iceclimb_frag_fire1", "e6.slide_flight",
                     "e6.upper_ring_flutter_air1", "e6.upper_ring_flutter_air2"), "movement"),
    **dict.fromkeys(("w1.firewall01_air1_beach_town", "w1.firewall01_air1_town_beach", "w1.firewall01_air2_beach_town",
                     "w2.firewall02_air3", "town.firewall02_air1", "f1.flamespout6_air1", "f2.acidblock04_fly_around",
                     "e2.steam_group_air1", "e2.steam_group_air2", "e5.frag_fire3_earth1", "e6.acidblock02_air1",
                     "e6.acidblock02_air2", "w3.ice_island_steam_block"), "barriers"),
    **dict.fromkeys(("w1.dark_cave_nolight", "e7.dark_room_nolight"), "dark"),
    **dict.fromkeys(("w1.torpedo_skip", "w1.hidden_airship", "w1.hidden_airship_saveanywhere",
                     "w1.shoreline_rollthrough", "f4.ledgepop", "e6.tree_song_skip", "w3.water_guardian_no_seal",
                     "d1.elevator_bounce", "d1.elevator_bounce_f10"), "bounds"),
}
TAB = ("settings", "share", "file", "obsidian_cost")
SEED_MAX = 256   # a remembered seed's length (D915; any string builds)


def _settings(recipe: Mapping, db) -> Settings:
    """The settings ``recipe`` asks for on the database ``db``, checked as
    Modkit checks a settings file or a share string; ``ValueError`` names
    every refusal."""
    if "share" in recipe:
        return share_decode(recipe["share"], {sid: s for sid, (_, s) in db.skips.items()})
    if "settings" in recipe:
        if not isinstance(recipe["settings"], Mapping):
            raise ValueError("recipe: settings is a settings file's table")
        return settings_from_table(recipe["settings"], {sid: s for sid, (_, s) in db.skips.items()}, "settings")
    return db.defaults


def plan(recipe: Mapping, progress: Callable[[dict], object] | None = None) -> dict:
    """The plan file's object for ``recipe``: the first of the fill's
    attempts that passes the verify, on the logic re-checked under the share
    string's movement sliders. ``progress(record)`` hears its three stages
    (``core.progress``'s ``plan``, done of 3): the logic read, the fill and
    the placements written. ``ValueError`` names a recipe or a setting it
    refuses, or (a ``FillError``) the progression items with no safe proven
    spot when no attempt passes."""
    if not isinstance(recipe, Mapping):
        raise ValueError(f"a randomizer recipe is a JSON object, not {type(recipe).__name__}")
    if unknown := sorted(set(recipe) - set(RECIPE), key=str):
        raise ValueError(f"recipe: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(RECIPE)})")
    if not isinstance(recipe.get("seed"), str):
        raise ValueError("recipe: seed is a string (any string; the same seed and settings give the same plan)")
    if "settings" in recipe and "share" in recipe:
        raise ValueError("recipe: settings and share both give the settings: give one")
    steps = Steps(progress)
    steps("plan", "Reading the randomizer's logic", 0, 3)
    logic = kept_logic()
    settings = _settings(recipe, logic.db)
    steps("plan", "Filling the seed", 1, 3)
    filled = fill(logic_of(logic, settings), recipe["seed"], settings)
    steps("plan", "Writing the placements", 2, 3)
    return plan_doc(filled, logic.db)


def spoiler(doc: Mapping) -> list[str]:
    """The spoiler of the plan file's object ``doc``: its settings, the
    spheres with each progression item's obtain and return paths, the traps
    and the rest (Modkit's ``rando spoiler``). ``ValueError`` names a plan
    this database can't read (another format, generator or database, an
    edited one)."""
    if not isinstance(doc, Mapping):
        raise ValueError(f"a plan file is a JSON object, not {type(doc).__name__}")
    logic = kept_logic()
    planned = load_plan(doc, logic.db)
    return spoiler_lines(planned, logic_of(logic, planned.settings))


def literal(settings: Settings) -> dict:
    """``settings`` as the tab holds them: a settings file's table in format
    /2, whose ``exclude_categories`` are exactly the categories kept vanilla
    (format /1's ``powers`` keeps the upgrades too), so a page reads and
    sets each row's box as it is."""
    return {"format": SETTINGS_FORMAT_ELEMENTAL, "skip_ceiling": settings.skip_ceiling,
            "movement_tier": settings.movement_tier, "dark_fire": settings.dark_fire,
            "exclude_categories": sorted(settings.exclude_categories, key=CATEGORIES.index),
            "skip_override": dict(sorted(settings.skip_override.items()))}


def _kind(item: str) -> str:
    """An item's row kind (Modkit's ``rando_view._kind``)."""
    if item.startswith("frag_"):
        return "disc_fragment"
    if item in UPGRADES:
        return "upgrade"
    if item.startswith("power_"):
        return "power"
    if item.startswith("key_"):
        return "key"
    if item in ("all_fuel", "all_health"):
        return "consumable"
    return "gem" if item in ("diamond", "emerald", "ruby", "sapphire") else item


@functools.cache
def base_counts() -> dict[str, int]:
    """How many of each item row's kind the base game places (Modkit's
    ``base_counts``): the pool locations of the vanilla data but town's two
    endless dispensers, which never move, and the barrier groups of each
    kind its maps show (a group named for no kind that gates the logic takes
    its damage's kind; training_room, never part of a seed, D194, has no
    map)."""
    n: collections.Counter = collections.Counter()
    for path in sorted((DATA_DIR / "generated").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        n.update(_kind(loc["item"]) for loc in data["locations"]
                 if loc["pool"] and not loc["dead"] and not loc["unbounded"])
        if path.stem != "training_room":
            n.update(b["kind"] if b["kind"] != "other" or b["requires"] is None
                     else DAMAGE_KINDS.get(b["damage"], "other") for b in data["barriers"])
    return {kind: n[kind] for *_, kind, _ in ITEMS}


def options() -> dict:
    """What the Randomizer tab offers, read without the database: D144's
    defaults (``data/settings/defaults.toml``, :func:`literal`), Movement's
    tiers, the skip ceilings and the fire levels, each ``[value, label]``
    (``loaded``: those offered only when a loaded setting holds them), the
    item rows (each ``[category or None, label, note]``) and the categories
    in the order a settings table lists them, the vanilla
    obsidian cost (D910) and the tips. An item row is ``[category or None,
    label, note, its base-game count, its icons]`` (:func:`base_counts`)."""
    table = tomllib.loads((DATA_DIR / "settings" / "defaults.toml").read_text(encoding="utf-8"))
    counts = base_counts()
    return {"defaults": literal(settings_from_table(table, {}, "settings/defaults.toml")),
            "movement": [list(m) for m in MOVEMENT], "ceilings": [list(c) for c in CEILINGS], "loaded": LOADED,
            "dark_fire": [1, 2, 3], "categories": list(CATEGORIES),
            "items": [[category, label, note, counts[kind], list(icons)] for category, label, note, kind, icons in ITEMS],
            "obsidian_cost": layer.OBSIDIAN_COST_VANILLA, "tips": {"movement": MOVEMENT_TIP, "ceiling": CEILING_TIP}}


def _rating(rows: list[Mapping]) -> str:
    """A pick's rating: its skip's, or a batch's variants' lowest to highest (Modkit's)."""
    def named(skip: Mapping) -> str:
        return RATINGS[d] if (d := skip.get("difficulty", 0)) in (1, 2, 3, 4) else RATINGS[0]

    low, high = (named(f(rows, key=lambda s: s.get("difficulty", 5))) for f in (min, max))
    return low if low == high else f"{low}-{high}"


def _cost(given: Mapping) -> float | None:
    """The tab's obsidian cost: ``None`` at vanilla's, else any finite
    number (D23); ``ValueError`` otherwise."""
    cost = given.get("obsidian_cost", layer.OBSIDIAN_COST_VANILLA)
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost):
        raise ValueError(f"obsidian cost {cost!r}: type a number (vanilla's is {layer.OBSIDIAN_COST_VANILLA:g})")
    return None if cost == layer.OBSIDIAN_COST_VANILLA else float(cost)


def tab(given: Mapping, sliders: Mapping[str, Mapping[str, float]]) -> dict:
    """What the tab shows for ``given`` (``settings``, a settings file's
    table, ``share``, a share string, or ``file``, a settings file's text,
    D144's Load settings; and ``obsidian_cost``) on a build's
    movement ``sliders`` (``physics.slider_values``): the settings
    (:func:`literal`), their share string with those sliders (AZ-383), a
    ``note`` when a given share string holds other sliders, each skip a
    setting can turn on (D114; D275: a batch is one pick) with its name,
    rating, the ceiling's state of it (``true``, ``false``, or ``null``:
    some of a batch's variants) and its toggle (``null``: none), the picks
    held (no toggle turns one on, D144), the forfeitable locations, what a
    build of them leaves unverified (``why_not``: a roll a skip on was
    proven at, an obsidian cost above vanilla's) and the preflight's
    refusal (``preflight``: too few proven spots, AZ-454), the settings
    file of them (``file``: Save settings' text, Modkit's ``--save-settings``
    file) and the skip groups (``groups``, D258: each group's picks a
    setting can turn on, each with its in-logic variants' ratings, which
    the page compares with the Movement tier). ``ValueError`` names a key,
    setting, share string or settings file refused."""
    if not isinstance(given, Mapping):
        raise ValueError(f"randomizer: a JSON object, not {type(given).__name__}")
    if unknown := sorted(set(given) - set(TAB), key=str):
        raise ValueError(f"randomizer: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(TAB)})")
    if sum(key in given for key in ("settings", "share", "file")) != 1:
        raise ValueError("randomizer: give settings, share or file")
    logic = kept_logic()
    skips = {sid: s for sid, (_, s) in logic.db.skips.items()}
    note = None
    if "share" in given:
        st = share_decode(given["share"], skips)
        if st.sliders and st.sliders != sliders and st.sliders != run_floor(sliders):
            note = (f"the share string was made with the movement sliders {layer.sliders_text(st.sliders)}: set "
                    "them on the Patches tab for the same plan")
    elif "file" in given:
        if not isinstance(given["file"], str):
            raise ValueError("randomizer: file is a settings file's text")
        try:
            table = tomllib.loads(given["file"])
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"settings file: not TOML ({exc})") from None
        st = settings_from_table(table, skips, "settings file")
    elif isinstance(given["settings"], Mapping):
        st = settings_from_table(given["settings"], skips, "settings")
    else:
        raise ValueError("randomizer: settings is a settings file's table")
    cost = _cost(given)
    st = replace(st, sliders={pack: dict(values) for pack, values in sliders.items()})
    every, rows, groups = picks(skips), [], {key: [] for key in SKIP_GROUPS}
    for pid, ids in every.items():
        if live := [skips[v] for v in ids if turnable(skips[v])]:
            n = sum(s.get("difficulty", len(RATINGS)) <= st.skip_ceiling for s in live)
            rows.append({"id": pid, "name": live[0].get("batch_name") or live[0].get("name", pid),
                         "rating": _rating(live), "ceiling": None if 0 < n < len(live) else n == len(live),
                         "toggle": st.skip_override.get(pid)})
            if (group := SKIP_GROUP.get(live[0]["id"])) in groups:
                groups[group].append({"id": pid, "name": rows[-1]["name"], "rating": rows[-1]["rating"],
                                      "levels": [s.get("difficulty", len(RATINGS)) for s in live]})
    refused = starved(logic, st)
    why = layer.roll_reasons(st, logic.db, sliders) + [r for r in [layer.obsidian_reason(cost)] if r]
    return {"settings": literal(st), "share": share_encode(st, skips), "note": note, "skips": rows,
            "held": len(every) - len(rows), "forfeitable": len(logic.forfeitable), "why_not": why,
            "preflight": refused.reason if refused else None, "file": layer.settings_text(st),
            "groups": [{"id": key, "label": label, "picks": groups[key]} for key, label in SKIP_GROUPS.items()],
            "tiers": list(MOVEMENT_TIERS)}


def settings_file(table: object) -> str:
    """The settings file of a settings table (D144's Save settings:
    Modkit's ``--save-settings`` file, which loads back to the same
    settings); ``ValueError`` names a setting refused."""
    if not isinstance(table, Mapping):
        raise ValueError("settings is a settings file's table")
    return layer.settings_text(settings_from_table(table, {sid: s for sid, (_, s) in kept_logic().db.skips.items()},
                                                   "settings"))


def remembered(given: object) -> dict:
    """A page's remembered randomizer (D915): ``on``, ``seed`` (a string of
    at most :data:`SEED_MAX` characters), ``settings`` (a settings file's
    table) and, when not vanilla's, ``obsidian_cost``, checked as a build
    checks them; ``ValueError`` names the first refusal."""
    keys = ("on", "seed", "settings", "obsidian_cost")
    if not isinstance(given, Mapping) or not {"on", "seed", "settings"} <= set(given) <= set(keys):
        raise ValueError(f"not an object of {', '.join(keys)}")
    if not isinstance(given["on"], bool):
        raise ValueError("on is true or false")
    if not (isinstance(given["seed"], str) and len(given["seed"]) <= SEED_MAX):
        raise ValueError(f"seed is a string of at most {SEED_MAX} characters")
    if not isinstance(given["settings"], Mapping):
        raise ValueError("settings is a settings file's table")
    skips = {sid: s for sid, (_, s) in kept_logic().db.skips.items()}
    out = {"on": given["on"], "seed": given["seed"],
           "settings": literal(settings_from_table(given["settings"], skips, "settings"))}
    return out | ({"obsidian_cost": cost} if (cost := _cost(given)) is not None else {})
