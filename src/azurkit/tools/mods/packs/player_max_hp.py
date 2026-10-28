"""player_max_hp: Starting HP and the health bar's full scale, two cells of
config.xbr's ``settings_foo`` (its columns are settings, its row
``Value``); no XBE byte.

- **Starting HP** (``initial hp``): a new game puts it, rounded, in the
  player's health slot as current and max HP, and every game start,
  continue or loaded save sets current HP to it again; the spawn copies the
  slot to the critter. The game rounds it to an int32 (an x87 FISTP, half
  to even), so a value no int32 holds once rounded is refused (D45). From
  -0.5 to 0.5 it gives 0 HP and the player dies at once, and again after
  each continue; below -0.5 the spawn falls back to the player critter's
  own 200 (both seen in xemu, Modkit's sitting p9). Neither is refused
  (D23).
- **Health bar full scale** (``max hp``): only the HUD reads it, the bar's
  length max HP over it and its fill current HP over it, so vanilla's
  200 HP shows a half-length bar, full. At 0 the HUD draws a full red
  tube, below 0 none, and the game runs on (xemu, p9).

Ported from Modkit's ``azurik_mod/patches/player_max_hp`` at the packs
oracle's tag, whose docstring holds the evidence.
"""

from __future__ import annotations

from azurkit.tools.mods.engine import Pack, XbrParametricEdit

STARTING_HP = XbrParametricEdit(
    name="starting_hp", label="Starting HP", table="settings_foo", entity="initial hp", prop="Value",
    default=200.0, slider_min=1.0, slider_max=1000.0, slider_step=1.0, unit="HP", int32="round",
    description="Current and max HP at a new game, continue or loaded save.")
HEALTH_BAR_SCALE = XbrParametricEdit(
    name="health_bar_full_scale", label="Health bar full scale", table="settings_foo", entity="max hp",
    prop="Value", default=400.0, slider_min=1.0, slider_max=1000.0, slider_step=1.0, unit="HP",
    description="HP that fills a full-length health bar (display only).")

PACK = Pack(name="player_max_hp", description="Starting HP and the health bar's full scale.",
            sites=(STARTING_HP, HEALTH_BAR_SCALE), category="player")
