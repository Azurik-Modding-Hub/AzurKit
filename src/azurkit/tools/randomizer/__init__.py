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
"""

from __future__ import annotations

from collections.abc import Mapping

from azurkit.tools.randomizer.movement import logic_of
from azurkit.tools.randomizer.planner.fill import fill
from azurkit.tools.randomizer.planner.loader import kept_logic
from azurkit.tools.randomizer.planner.plan import load_plan, plan_doc, spoiler_lines
from azurkit.tools.randomizer.planner.settings import Settings, settings_from_table, share_decode

RECIPE = ("seed", "settings", "share")


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


def plan(recipe: Mapping) -> dict:
    """The plan file's object for ``recipe``: the first of the fill's
    attempts that passes the verify, on the logic re-checked under the share
    string's movement sliders. ``ValueError`` names a recipe or a
    setting it refuses, or (a ``FillError``) the progression items with no
    safe proven spot when no attempt passes."""
    if not isinstance(recipe, Mapping):
        raise ValueError(f"a randomizer recipe is a JSON object, not {type(recipe).__name__}")
    if unknown := sorted(set(recipe) - set(RECIPE), key=str):
        raise ValueError(f"recipe: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(RECIPE)})")
    if not isinstance(recipe.get("seed"), str):
        raise ValueError("recipe: seed is a string (any string; the same seed and settings give the same plan)")
    if "settings" in recipe and "share" in recipe:
        raise ValueError("recipe: settings and share both give the settings: give one")
    logic = kept_logic()
    settings = _settings(recipe, logic.db)
    return plan_doc(fill(logic_of(logic, settings), recipe["seed"], settings), logic.db)


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
