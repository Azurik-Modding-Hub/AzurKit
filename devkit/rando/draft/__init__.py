"""Randomizer authoring drafts: tools that derive logic data from the game (dev only).

Modkit's ``randomizer/draft`` at its freeze (Step 4.13c), each module its code with its imports pointed at
AzurKit's: :mod:`.reach` is the reach model (on the shipped draft's geometry, floors and wiring, with
:mod:`.flights`, :mod:`.moves`, :mod:`.gates`, :mod:`.coverage` and :mod:`.sites`), :mod:`.export` writes its derived
data and :mod:`.author` the level and movement files (``authoring/<level>.toml``: the realm steps' hand
decisions); :mod:`.route` is the route graph and :mod:`.l3_goal` the L3 goals over it; :mod:`.svg` draws a level's
tiers and :mod:`.value` ranks the probe sites. The shipped half (``azurkit.tools.randomizer.draft``: the envelope,
floors, geometry, wiring and ``tiers.toml``) never imports this package.

``blocker_families.toml`` lives here, beside the authoring: the shipped wiring's :func:`families` reads it from this
folder (its ``FAMILIES_TOML``, pointed here on import), and only the derive calls it.
"""

from pathlib import Path

import azurkit.tools.randomizer.art  # noqa: F401  (first: the randomizer's levels and art import each other, art first)
from azurkit.tools.randomizer.draft import wiring

wiring.FAMILIES_TOML = Path(__file__).with_name("blocker_families.toml")
