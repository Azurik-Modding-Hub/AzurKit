"""qol_save_warp: the save-point warp (D202). On a save platform, hold LT
and press A, B, X and Y (each at least once while LT stays held): the
platform becomes the one return point and the game loads town, arriving on
town's save platform; the same on town's platform returns to the stored one.
The return point is a global-map entry, so a save keeps it. Off by default;
a randomized build that applies it plans with the warp counted (the
randomizer's ``save_warp``, D1154).

Two hooks into one shim (``shims/qol_save_warp.c``), each landing its own
copy: the player tick's call of the armor-state tick (0x8C2EC) watches for
the ritual and posts the level request, and the scene tick's level load
(0x55F80) points the arrival at the stored platform. The shim names no
address of the image, so both releases take it. Ported from Modkit's
``azurik_mod/patches/qol_save_warp`` at the packs oracle's tag, whose
README holds the evidence.
"""

from __future__ import annotations

from azurkit.tools.mods.engine import Pack, TrampolinePatch

PACK = Pack(
    name="qol_save_warp",
    description="Save-point warp: on a save platform, LT + A, B, X, Y goes to town and back.",
    sites=(TrampolinePatch(label="Save-point warp: the ritual (player tick)", va=0x0008C2EC, shim="qol_save_warp",
                           symbol="_c_save_warp_tick@4"),
           TrampolinePatch(label="Save-point warp: the arrival (the scene tick's level load)", va=0x00055F80,
                           shim="qol_save_warp", symbol="_c_save_warp_load@16")),
)
