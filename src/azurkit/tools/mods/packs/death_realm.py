"""death_realm: the death realm unlock (D201, D1301). d1's death seal opens
without the five discs, and Spideyzar fights far harder and faster until
the player holds all five; his health stays vanilla's. Off by default; it
sits in the Randomizer category (D1302), whose logic counts it while ticked.

**The seal** (``docs/RE_DATA.md`` § "d1's death seal and Spideyzar's
floor"): d1.xbr's ``SealFragmentNumber_gameState`` sends each disc's
fragment count through a step curve (0 at 3 or fewer, 1 at 4) into the
seal's AND, beside the seal's touch, and into the help popup's NOR. The ten
curves' first key's y, 0.0, becomes 1.0 (:data:`SEAL`): each test is 1 at
any count, so a touch of the seal opens the chromatic field and no "you
need the discs" popup shows over it (R2.12a's ten writes; the field's own
look and sound stay vanilla's).

**Spideyzar** (``docs/RE_XBE.md`` § "Spideyzar's speed, his attacks and the
damage the player takes"): one shim (``shims/death_realm.c``), two landings,
each acting only while a disc lacks a fragment (the gameState's own test,
read live): his think's call of the base think (0x2BBF4) sets the rate his
clips play at to the speed slider times vanilla's 1.0, 1.25 or 1.5 by his
health, caps the wait before his next attack, and scales his species'
walk and run speeds; the player's hit, past its damage (0x8D657, Europe
0x8D607, beside enemy_scaling's 0x8D648), multiplies a hit he deals after
the armor. The pack hands the shim the scene pointer's address and
vanilla's five speed constants, each release's own. A damage k whose
product with the largest damage record no int32 holds fails by name (D45).
Seen in xemu (sitting 4.71c): a pad walk opens the seal at 0 discs, and one
disc short his rate, waits, moves and costs are exactly the sliders'; with
all five he is vanilla's. The defaults are the one step of the sitting's
three at which a player standing in his reach dies in about a tenth of
vanilla's time. Known flaws: his attack starts come about 2x as often as
vanilla's, not 3x, and his hits that no critter of his sources aren't scaled.
"""

from __future__ import annotations

import math
import struct

from azurkit.tools.mods.engine import (INT32, BytesParam, FloatParam, Pack, ParametricPatch, Place, TrampolinePatch,
                                       Xbe, XbrPatch, f32)

D1 = "gamedata/d1.xbr"
KEY = 0x20   # a curve link's two keys, 16 B each (x, y, slope, inf): the next link's first key's y
SEAL_KEYS, HELP_KEYS = 0x01AB2F8C, 0x01AB358C   # the seal AND's links 0-4, the help NOR's links 5-9: first key's y
SEAL = tuple(XbrPatch(label=f"d1's seal: {what} test {k + 1}", file=D1, offset=at + KEY * k, expected=f32(0.0),
                      value=f32(1.0)) for what, at in (("its disc", SEAL_KEYS), ("its help popup's disc", HELP_KEYS))
             for k in range(5))

UNTIL = "until you hold all five discs."
DAMAGE = ParametricPatch(name="spideyzar_damage_scale", label="Spideyzar's damage", default=6.0, slider_min=1.0,
                         slider_max=10.0, slider_step=0.5, unit="x", vanilla=1.0,
                         description=f"What his hits cost you, after your armor, {UNTIL}")
SPEED = ParametricPatch(name="spideyzar_speed_scale", label="Spideyzar's speed", default=2.5, slider_min=1.0,
                        slider_max=4.0, slider_step=0.25, unit="x", vanilla=1.0,
                        description=f"How fast all his moves play {UNTIL}")
WAIT = ParametricPatch(name="spideyzar_attack_wait", label="Spideyzar's longest wait", default=1.0, slider_min=0.0,
                       slider_max=15.0, slider_step=0.5, unit="s", vanilla=15.0,
                       description=f"The most seconds he waits between attacks {UNTIL}")
MOVE = ParametricPatch(name="spideyzar_move_scale", label="Spideyzar's movement", default=2.5, slider_min=1.0,
                       slider_max=4.0, slider_step=0.25, unit="x", vanilla=1.0,
                       description=f"How fast he walks and runs {UNTIL}")

FLOATS = (FloatParam(DAMAGE.name, "_death_realm_damage"), FloatParam(SPEED.name, "_death_realm_speed"),
          FloatParam(WAIT.name, "_death_realm_wait"), FloatParam(MOVE.name, "_death_realm_move"))
GAME = BytesParam("game", "_death_realm_game", 24)   # the scene pointer's VA, then SPEEDS' five floats
SCENE = 0x001BF63C   # the scene (game) object's pointer: [scene + 0x2C] the player data
SPEEDS = (0x001987B0, 0x001987B4, 0x001987B8, 0x001A2770, 0x001A276C)   # 1.0, 1.25, 1.5; under 1/3 and 2/3 health
MAX_RECORD_DAMAGE = 500   # the largest damage record's: the damage slider's k times it must fit an int32 (D45)

THINK = TrampolinePatch(label="Death realm: Spideyzar's think (its call of the base think)", va=0x0002BBF4,
                        shim="death_realm", symbol="_c_death_realm_think", floats=FLOATS, tables=(GAME,))
HIT = TrampolinePatch(label="Death realm: the player's hit, past its damage", va=0x0008D657, shim="death_realm",
                      symbol="_c_death_realm_hit", floats=FLOATS, tables=(GAME,))


def apply(xbe: Xbe, spideyzar_damage_scale: float, spideyzar_speed_scale: float, spideyzar_attack_wait: float,
          spideyzar_move_scale: float) -> None:
    """Both landings, the sliders' values and the release's own addresses and constants written into each."""
    if not (math.isfinite(hit := spideyzar_damage_scale * MAX_RECORD_DAMAGE) and INT32[0] <= math.trunc(hit) <= INT32[1]):
        raise ValueError(f"{DAMAGE.label}: x{spideyzar_damage_scale:g} of a {MAX_RECORD_DAMAGE} HP hit doesn't fit the "
                         f"game's 32-bit integer ({INT32[0]}..{INT32[1]})")
    params = {DAMAGE.name: spideyzar_damage_scale, SPEED.name: spideyzar_speed_scale, WAIT.name: spideyzar_attack_wait,
              MOVE.name: spideyzar_move_scale,
              GAME.name: struct.pack("<I", xbe.va(SCENE)) + b"".join(xbe.read(va, 4) for va in SPEEDS)}
    for hook in (THINK, HIT):
        xbe.patch(hook, params=params)


PACK = Pack(
    name="death_realm",
    description="Enter d1 without the five discs; Spideyzar is far harder until you hold them.",
    sites=(*SEAL, DAMAGE, SPEED, WAIT, MOVE),
    custom_apply=apply,
    footprint=(Place(va=THINK.va), Place(va=HIT.va)),
    category="randomizer",
)
