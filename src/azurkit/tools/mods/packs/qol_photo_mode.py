"""qol_photo_mode: photo mode (D489). Click both sticks (L3 + R3): the game
freezes, the HUD hides and the camera flies free (the game's own free
camera, cheat code 3's, in which the world doesn't step). L3 + R3 again,
START or BACK resumes as it was; nothing held across the exit fires. Hold B
for a quarter of the camera's speed, Y for four times it; the Fly speed
slider scales it all. Off by default; camera only, so the randomizer's logic
ignores it.

Two hooks into one shim (``shims/qol_photo_mode.c``), each landing its own
copy: the scene tick's call of the cheat-owner tick (0x55BB9) opens and
closes the camera, and the frame's call of the active camera's update
(0x548E3, its 9 bytes: the push of dt, the camera into ECX and the indirect
call) scales the free camera's dt by the slider, a float the build writes
into the shim. Both releases (the same addresses; the shim names no address
of the image). Design from Azurik Debug Menu 1.1.0 by Azurik Perathia (MIT),
reimplemented in Modkit; ported from Modkit's
``azurik_mod/patches/qol_photo_mode`` at the packs oracle's tag.
"""

from __future__ import annotations

from azurkit.tools.mods.engine import FloatParam, Pack, ParametricPatch, TrampolinePatch

FLY_SPEED = ParametricPatch(name="fly_speed", label="Fly speed", default=1.0, slider_min=0.1, slider_max=4.0,
                            slider_step=0.05, unit="x", vanilla=1.0,
                            description="Photo mode's camera speed; hold B for a quarter, Y for four times.")

PACK = Pack(
    name="qol_photo_mode",
    description="Photo mode: L3 + R3 freezes the game and frees the camera; again to resume.",
    sites=(TrampolinePatch(label="Photo mode: L3 + R3 (the cheat-owner tick)", va=0x00055BB9, shim="qol_photo_mode",
                           symbol="_c_photo_mode_tick"),
           TrampolinePatch(label="Photo mode: the free camera's speed (the camera update)", va=0x000548E3,
                           shim="qol_photo_mode", symbol="_c_photo_mode_camera",
                           floats=(FloatParam(FLY_SPEED.name, "_photo_mode_fly_speed"),)),
           FLY_SPEED),
)
