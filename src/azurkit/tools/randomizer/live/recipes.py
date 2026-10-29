"""The RAM recipes: the game's own requests, posted from outside (RAM_RECIPES R2, R6, R7; Step X.9).

The write side of guest memory, shared by the xemu sitting kit (``scripts/xemu_sitting.py``) and simulator Level 3
(:meth:`azurik_mod.sim.l3.L3.teleport`), so there is one implementation instead of a copy per sitting.  Each recipe
reads through ``u32(va) -> int`` (an xemu sandbox's ``read_u32``, L3's ``u32``, a test's dict) and returns the
writes, ``[(va, bytes)]``, that make the request; the caller applies them, the guest halted at a player tick, and
the game acts on them at its next one.

- R6, a teleport (:func:`place`): the place struct Continue uses, at its idle buffer, and the request block's
  pointer to it; 0x855D0 consumes it from the player tick, putting the body centre 1 m over the feet, airborne.
  0x855D0 keeps the player's velocity, so given the player entity the place also stops it (AZ-437).
- R7, a level hop (:func:`hop`): the request a levelSwitch fires (movie, level, arrival spot), at its buffer.
- R2, the element levels, fragments and keys of the inventory (:func:`element_levels`, :func:`fragments`,
  :func:`keys`).

Every VA and offset was read from the USA vanilla ``default.xbe`` (the R0 RAM-recipe notes, 2026-10-11, and
sittings since).  VAs are USA's: pass ``va`` (a release's ``Region.va``) to take each to the booted release's,
which names any it lacks (D146).  Positions stay in memory: nothing here prints.
"""

from __future__ import annotations

import math
import struct
from typing import Callable

SCENE_PTR = 0x1BF63C          # the scene (game) object; [scene+0x2C] = pd, the player data
SCENE_PD = 0x2C
PD_LEVEL, PD_PLAYER, PD_ARMOR, PD_WORLD, PD_REQ, PD_INV = 0x00, 0xC0, 0xCC, 0xD4, 0xD8, 0xE0
WORLD_CELLS, CELL_SIZE = 0x28, 0xB4   # [world+0x28] = the cell array
R_PLACE, R_LEVEL = 0x08, 0x10         # the request block [pd+0xD8]: a place struct (0x855D0), a level request (0x55D4F)
PLACE_BUF = 0x39014C          # Continue's place struct (0x53428), idle after a load
LEVEL_BUF = 0x38D320          # the levelSwitch fire's request (0x6F050): movie, level, spot, 0x104 B each
STR_SLOT = 0x104
CR_CELL, CR_BODY, CR_HP, CR_QUAT = 0x158, 0x15C, 0x210, 0x18C   # the player critter ([entity+0x20])
ENT_VEL = 0x24                # the player entity's (PlayerControl's) velocity, 3 floats; 0x855D0 never writes it
LIFT = 1.0                    # 0x855D0 puts the body centre this far over the place struct's point
INV_SAVED = 0x1D4             # the inventory's saved bytes (inv.sav after its version word)
INV_CLOCK = 4                 # its first word is the day clock, which player-tick L3 doesn't advance (AZ-389)
ELEMENTS = ("earth", "air", "fire", "water")
INV_LEVEL = {"earth": 0x04, "air": 0x08, "fire": 0x0C, "water": 0x10}   # i32 0..3
SLOTS = ("ef", "af", "ff", "wf", "emer", "diam", "ruby", "sapp", "obsi", "hlth", "spow", "mpow")
SLOT0, FRAG0, KEY0 = 0x18, 0xA8, 0x198   # 12 slots, 20 fragments, 5 keys: {tag, value, cap} of 12 B each
FRAG_ELEMS = "eafwl"          # fragment k (1-4) of earth, air, fire, water, life


def _same(va: int) -> int:
    return va


Writes = list[tuple[int, bytes]]


def chain(u32: Callable[[int], int], va: Callable[[int], int] = _same) -> dict[str, int]:
    """The pointers from the scene global: pd, the request block, the inventory, the armor manager, the world
    and its cell array, the player critter (0 where one isn't set yet)."""
    pd = u32(u32(va(SCENE_PTR)) + SCENE_PD)
    c = {"pd": pd, "req": u32(pd + PD_REQ), "inv": u32(pd + PD_INV), "armor_mgr": u32(pd + PD_ARMOR),
         "world": u32(pd + PD_WORLD), "player": u32(pd + PD_PLAYER)}
    c["cells"] = u32(c["world"] + WORLD_CELLS) if c["world"] else 0
    return c


def cell_of(u32: Callable[[int], int], critter: int, c: dict[str, int]) -> int:
    """The index of the cell (room) the engine tracks ``critter`` in."""
    return (u32(critter + CR_CELL) - c["cells"]) // CELL_SIZE


def yaw_quat(yaw: float) -> tuple[float, float, float, float]:
    """The facing quaternion of game angle ``yaw`` (radians; forward is (-sin yaw, cos yaw))."""
    return 0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2)


def place_struct(feet, yaw: float | None = None, *, quat=None, cell: int = 0) -> bytes:
    """R6's 30-byte place struct: the feet, the facing (``yaw`` radians, or ``quat``) and the cell (u16)."""
    return struct.pack("<3f4fH", *feet, *(quat if quat is not None else yaw_quat(yaw or 0.0)), cell)


def place(u32: Callable[[int], int], feet, yaw: float | None = None, *, quat=None, cell: int | None = None,
          critter: int | None = None, entity: int | None = None, va: Callable[[int], int] = _same) -> Writes:
    """R6: the place request that puts the player's feet at ``feet`` (the body centre ``LIFT`` over it), airborne,
    facing ``yaw`` (radians) or ``quat``, in ``cell`` (default: the cell ``critter``, else the player, is in).
    Given the player ``entity`` (the player tick's PlayerControl, [esp+4]) it also zeroes its velocity, which the
    consumer keeps: after a warp onto a1's rising tree lift a place flew 6.8 m up (AZ-437)."""
    c = chain(u32, va)
    if cell is None:
        cell = cell_of(u32, critter or c["player"], c)
    out = [(va(PLACE_BUF), place_struct(feet, yaw, quat=quat, cell=cell)),
           (c["req"] + R_PLACE, struct.pack("<I", va(PLACE_BUF)))]
    return out + ([(entity + ENT_VEL, bytes(12))] if entity else [])


def hop(u32: Callable[[int], int], level: str, spot: str, movie: str = "",
        va: Callable[[int], int] = _same) -> Writes:
    """R7: the level request a levelSwitch fires: to ``level`` (``levels/fire/f6``), arriving at ``spot`` (a
    playerLocation's name), after ``movie`` (none by default)."""
    out = []
    for k, s in enumerate((movie, level, spot)):
        b = s.encode("ascii")
        if len(b) >= STR_SLOT:
            raise ValueError(f"{s!r} is longer than a request slot ({STR_SLOT - 1} characters)")
        out.append((va(LEVEL_BUF) + k * STR_SLOT, b + b"\0"))
    return out + [(chain(u32, va)["req"] + R_LEVEL, struct.pack("<I", va(LEVEL_BUF)))]


def element_levels(u32: Callable[[int], int], levels: dict[str, int], va: Callable[[int], int] = _same) -> Writes:
    """R2: the element (staff) levels in the inventory, 0-3 each: only the ones ``levels`` names."""
    inv = chain(u32, va)["inv"]
    if bad := sorted(set(levels) - set(INV_LEVEL)):
        raise ValueError(f"no element {bad[0]!r}: one of {', '.join(ELEMENTS)}")
    return [(inv + INV_LEVEL[e], struct.pack("<i", v)) for e, v in levels.items()]


def frag_off(elem: str, k: int) -> int:
    """Fragment ``k`` (1-4) of ``elem`` (e, a, f, w or l): its tag's offset; its count is at +4."""
    return FRAG0 + 12 * (4 * FRAG_ELEMS.index(elem) + k - 1)


def fragments(u32: Callable[[int], int], elem: str, n: int, va: Callable[[int], int] = _same) -> Writes:
    """R2: fragments 1..``n`` of ``elem`` held (count 1) and the rest not."""
    inv = chain(u32, va)["inv"]
    return [(inv + frag_off(elem, k) + 4, struct.pack("<i", int(k <= n))) for k in range(1, 5)]


def keys(u32: Callable[[int], int], held: dict[str, int], va: Callable[[int], int] = _same) -> Writes:
    """R2: the key slots hold exactly ``held`` ({key fourcc: count}, the fourcc a key's ``critters_item_data``
    ``invType``: ``d2k1`` the lens, ``d1k1`` the diamond battery), one slot a type in order, the rest empty as the
    new-game reset leaves them (tag 0, count 0; the cap, -1 there, untouched).  The game finds a key by its tag
    (0x58090) and stores the fourcc as its four characters in memory order (0xB62F0)."""
    inv = chain(u32, va)["inv"]
    if len(held) > 5:
        raise ValueError(f"{len(held)} key types: the inventory has 5 key slots")
    out: Writes = []
    for i in range(5):
        tag, n = list(held.items())[i] if i < len(held) else ("", 0)
        if tag and len(tag.encode("ascii")) != 4:
            raise ValueError(f"key tag {tag!r} is not a fourcc")
        out.append((inv + KEY0 + 12 * i, tag.encode("ascii").ljust(4, b"\0") + struct.pack("<i", n)))
    return out


def inventory(b: bytes) -> dict[str, int]:
    """The inventory's saved bytes (``INV_SAVED`` from inv) decoded: each element level, slot value and
    fragment and key count, by name (the day clock and the popup bits left out)."""
    out = {f"level.{e}": struct.unpack_from("<i", b, o)[0] for e, o in INV_LEVEL.items()}
    out |= {f"{name}": struct.unpack_from("<i", b, SLOT0 + 12 * i + 4)[0] for i, name in enumerate(SLOTS)}
    out |= {f"fg{e}{k}": struct.unpack_from("<i", b, frag_off(e, k) + 4)[0] for e in FRAG_ELEMS for k in range(1, 5)}
    return out | {f"key{i}": struct.unpack_from("<i", b, KEY0 + 12 * i + 4)[0] for i in range(5)}


def item_fields(item: str) -> set[str] | None:
    """The :func:`inventory` fields a pickup of ``item`` (a randomizer item: ``frag_fire_3``, ``power_air``, a key,
    a gem) changes, None when any but a gem count tells (a gem on the way is no proof of the item)."""
    parts = item.split("_")
    if parts[0] == "power" and len(parts) > 1 and parts[1] in ELEMENTS:
        return {f"level.{parts[1]}"}
    if parts[0] == "frag" and len(parts) >= 3 and parts[2].isdigit():
        return {f"fg{parts[1][0]}{parts[2]}"}
    if parts[0] == "key":
        return {f"key{i}" for i in range(5)}
    gems = {"obsidian": "obsi", "emerald": "emer", "diamond": "diam", "ruby": "ruby", "sapphire": "sapp"}
    return {gems[item]} if item in gems else None


def level_path(read: Callable[[int, int], bytes], u32: Callable[[int], int],
               va: Callable[[int], int] = _same) -> str:
    """The level the game is in (pd's path, ``levels/water/w1``)."""
    return read(chain(u32, va)["pd"] + PD_LEVEL, 0x50).split(b"\0")[0].decode("latin-1")
