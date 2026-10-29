"""enemy_scaling: every enemy's health, the damage it deals, its attack and
movement speed and its size, and the same five for the bosses (D812, D817).
Ten multipliers, each 1.0 by default and writing nothing there: five over
every enemy but the bosses, five over the bosses. Off by default.

**Who.** The enemies are the critters whose ``critters_engine`` ``ai``
isn't ``player``, ``town`` or ``item``, less ``debug`` (no level places
it). The bosses, by the game's own reading: a critter whose ``ai`` has a
factory of its own in the species load (:data:`BOSS_AIS`), whose body is in
``characters/bosses/``, or whose name a boss's AI spawns by
(:data:`BOSS_SPAWNS`). The cell sliders read them from the vanilla tables;
the shim gets them as name lists (:data:`BOSSES`, :data:`ENEMIES`, those
tables' answer).

**What.** Health (``critters_damage`` ``hitPoints``, each ceil(k x HP), so
none with HP is left with none), movement (``critters_critter_data``
``walkSpeed`` and ``runSpeed``, and ``critters_flocking``'s accelerations
and start speed), size (``critters_engine`` ``scale`` and
``boundRadius``) and the enemies' attack speed (``critters_walking``
``attack anim rate``) are config.xbr cells: k x the vanilla cell, an empty
one taking the loader's default first, a 0 left as it is. The damage dealt
(both), the bosses' attack speed and the reach at a size off 1.0 are the
shim's (``shims/enemy_scaling.c``), landed only for a slider off 1.0, once
per hook, its floats and name tables written into each landing: the
player's hit (0x8D648) costs k x its base before the armor, a boss's attack
clips play k times as fast (anim_change at 0x429F7, the layer-rate setter
0x30940, spideyzar's own rate at 0x2C7E2), and the attack range (0x256B0)
is max(scale, k) x attackRange (AZ-788). Two bosses' AIs set their own scale
each tick, so boss size also points their seven reads of four constants at
copies k times as large (:data:`SIZE_SITES`). A value no int32 holds fails
by name (D45). Ported from Modkit's ``azurik_mod/patches/enemy_scaling`` at
the packs oracle's tag, whose docstring and README hold the evidence.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Mapping

from azurkit.core.xbr.keyed import EMPTY, NUMBER, Table
from azurkit.tools.mods.engine import (BytesParam, FloatParam, Pack, ParametricPatch, Place, TrampolinePatch,
                                       XbrParametricEdit, Xbe)

NOT_ENEMIES = ("player", "town", "item")   # the critters_engine ai values that aren't enemies
UNPLACED = ("debug",)                      # an enemy AI's critter no level places
BOSS_AIS = ("airboss", "airbossclone", "earthboss", "fireboss1", "fireboss2", "fireboss3", "waterboss",
            "watertentacle1", "watertentacle2", "watertentacle3", "balthazar", "spideyzar")
BOSS_FOLDER = "bosses/"
BOSS_SPAWNS = ("rock_shard_boss", "air_elemental_boss")
BOSSES = ("guard_air", "guard_air_clone", "guard_earth", "guard_fire1", "guard_fire2", "guard_fire3",
          "guard_water", "water_tentacle1", "water_tentacle2", "water_tentacle3", "balthazar", "spideyzar",
          "rock_shard_boss", "air_elemental_boss", "boulder")
ENEMIES = ("air_elemental", "air_octopus", "barnacle", "bird", "blaze_sentinel", "blaze_move", "bot", "fire_bot",
           "catalisk", "catalisk_baby", "cat_dead", "channeler", "evil_noreht", "firedrake", "fire_elemental",
           "firefly", "gargoylestone", "golem", "good_noreht", "harvester", "harvester_train", "ice_shard",
           "lava_shard", "magmar", "keylord", "overlord", "overlord and gargoyle", "overlord and golem", "rock_shard",
           "shadow_demon", "skrit_water", "skrit_fire", "skrit_earth", "skrit_air", "shard", "fire_shard", "sleeth",
           "sleeth_momma", "sleeth_x", "splinter", "water_elemental", "24hr", "fish_big", "fish_little1",
           "fish_little2", "jellyfish", "flicken", "flicken of peril", "kingkong", "tesla_tree", "tesla_tree_x", "test",
           "movies", "catalisk_grp", "catalisk_baby_grp", "rock_shard_grp")
# A damage platform's hit (no critter) by its record: B the bosses' fields and fires, E the tesla tree's.
PLATFORM_RECORDS = {"B": ("norm_1", "norm_2", "norm_3", "fire_1", "water_2", "rock_shard"), "E": ("tesla",)}
MAX_RECORD_DAMAGE = 500   # the largest damage record's: a damage slider's k times it must fit an int32 (D45)


def bosses_in(tables: Mapping[str, Table]) -> tuple[str, ...]:
    """The bosses by the game's reading of ``critters_engine``, in column order."""
    engine = tables["critters_engine"]
    ai, body = engine.row("ai"), engine.row("body")
    return tuple(c for col, c in enumerate(engine.cols) if engine.cell(col, ai).value in BOSS_AIS
                 or str(engine.cell(col, body).value or "").startswith(BOSS_FOLDER) or c in BOSS_SPAWNS)


def enemies_in(tables: Mapping[str, Table]) -> tuple[str, ...]:
    """Every critter whose ai isn't :data:`NOT_ENEMIES`, less :data:`UNPLACED` and the bosses."""
    engine, boss = tables["critters_engine"], set(bosses_in(tables))
    ai = engine.row("ai")
    return tuple(c for col, c in enumerate(engine.cols)
                 if c not in UNPLACED and c not in boss and engine.cell(col, ai).value not in NOT_ENEMIES)


HEALTH_ROWS = (("critters_damage", "hitPoints", 0.0),)
ATTACK_ROWS = (("critters_walking", "attack anim rate", 1.0),)
MOVE_ROWS = (("critters_critter_data", "walkSpeed", 1.0), ("critters_critter_data", "runSpeed", 0.0),
             *(("critters_flocking", row, 0.0) for row in (
                 "max xy accel", "max accel up", "max accel down", "max brake down", "initial velocity")))
SIZE_ROWS = (("critters_engine", "scale", 1.0), ("critters_engine", "boundRadius", 0.0))
# Each cell slider's (table, row, the loader's value for an empty cell) rows, and whether it is the bosses'.
ROWS = {"enemy_health_scale": (HEALTH_ROWS, False), "boss_health_scale": (HEALTH_ROWS, True),
        "enemy_attack_speed_scale": (ATTACK_ROWS, False),
        "enemy_move_speed_scale": (MOVE_ROWS, False), "boss_move_speed_scale": (MOVE_ROWS, True),
        "enemy_size_scale": (SIZE_ROWS, False), "boss_size_scale": (SIZE_ROWS, True)}


def cells(slider: str, tables: Mapping[str, Table]) -> list[tuple[str, int, str, float, str]]:
    """A cell slider's cells, ``(critter, column, row, base, table)``: each
    of its critters' cells in its rows that isn't 0 (an empty one the
    loader's default; health truncated, as the loader keeps it)."""
    rows, bosses = ROWS[slider]
    critters, out = set(bosses_in(tables) if bosses else enemies_in(tables)), []
    for name, row, default in rows:
        table = tables[name]
        r = table.row(row)
        for col, critter in enumerate(table.cols):
            if critter not in critters:
                continue
            cell = table.cell(col, r)
            if cell.kind not in (EMPTY, NUMBER):
                raise ValueError(f"config table {name} {critter}/{row} is not a number")
            base = default if cell.kind == EMPTY else math.trunc(cell.value) if row == "hitPoints" else cell.value
            if base:
                out.append((critter, col, row, float(base), name))
    return out


def _cell_slider(name: str, label: str, description: str, table: str, prop: str, lo: float, hi: float,
                 step: float, int32=None) -> XbrParametricEdit:
    return XbrParametricEdit(name=name, label=label, table=table, entity="bosses" if ROWS[name][1] else "enemies",
                             prop=prop, default=1.0, slider_min=lo, slider_max=hi, slider_step=step, unit="x",
                             description=description, int32=int32, cells=lambda tables: cells(name, tables),
                             logic_floor="max")   # stronger enemies than the logic assumes (D83(c))


def _shim_slider(name: str, label: str, description: str, lo: float, hi: float, step: float) -> ParametricPatch:
    return ParametricPatch(name=name, label=label, default=1.0, slider_min=lo, slider_max=hi, slider_step=step,
                           unit="x", vanilla=1.0, description=description, logic_floor="max")


HEALTH = _cell_slider("enemy_health_scale", "Enemy health", "Every enemy's HP but the bosses', rounded up.",
                      "critters_damage", "hitPoints", 0.1, 10.0, 0.1, int32="ceil")
DAMAGE_DEALT = _shim_slider("enemy_damage_dealt_scale", "Enemy damage dealt",
                            "Damage enemies' hits deal you before your armor; below 0 they heal you.", 0.0, 5.0, 0.05)
ATTACK_SPEED = _cell_slider("enemy_attack_speed_scale", "Enemy attack speed",
                            "How fast enemies swing and recover (the walking AI's attacks).",
                            "critters_walking", "attack anim rate", 0.25, 4.0, 0.05)
MOVE_SPEED = _cell_slider("enemy_move_speed_scale", "Enemy movement speed", "How fast enemies walk, run, fly and swim.",
                          "critters_critter_data", "walkSpeed, runSpeed", 0.25, 4.0, 0.05)
SIZE = _cell_slider("enemy_size_scale", "Enemy size", "Every enemy's size, with its collision, hit boxes and reach.",
                    "critters_engine", "scale", 0.25, 4.0, 0.05)
BOSS_HEALTH = _cell_slider("boss_health_scale", "Boss health", "Every boss's HP, rounded up.",
                           "critters_damage", "hitPoints", 0.1, 10.0, 0.1, int32="ceil")
BOSS_DAMAGE_DEALT = _shim_slider("boss_damage_dealt_scale", "Boss damage dealt",
                                 "Damage bosses' hits deal you before your armor; below 0 they heal you.",
                                 0.0, 5.0, 0.05)
BOSS_ATTACK_SPEED = _shim_slider("boss_attack_speed_scale", "Boss attack speed",
                                 "How fast bosses swing (their attack clips).", 0.25, 4.0, 0.05)
BOSS_MOVE_SPEED = _cell_slider("boss_move_speed_scale", "Boss movement speed", "How fast bosses walk, run and fly.",
                               "critters_critter_data", "walkSpeed, runSpeed", 0.25, 4.0, 0.05)
BOSS_SIZE = _cell_slider("boss_size_scale", "Boss size", "Every boss's size, with its collision, hit boxes and reach.",
                         "critters_engine", "scale", 0.25, 4.0, 0.05)

FLOATS = (FloatParam(DAMAGE_DEALT.name, "_enemy_scaling_enemy_damage"),
          FloatParam(BOSS_DAMAGE_DEALT.name, "_enemy_scaling_boss_damage"),
          FloatParam(BOSS_ATTACK_SPEED.name, "_enemy_scaling_boss_attack"),
          FloatParam(SIZE.name, "_enemy_scaling_enemy_size"), FloatParam(BOSS_SIZE.name, "_enemy_scaling_boss_size"))
TABLES = (BytesParam("bosses", "_enemy_scaling_bosses", 256), BytesParam("enemies", "_enemy_scaling_enemies", 640),
          BytesParam("records", "_enemy_scaling_records", 128), BytesParam("calls", "_enemy_scaling_calls", 8))
DAMAGE_VA, RECORDS_VA = 0x00083FE0, 0x0038C364   # the player's damage (armor_mgr, record); the damage records


def _hook(what: str, why: str, va: int, mode: str = "call") -> TrampolinePatch:
    return TrampolinePatch(label=f"Enemy scaling: {why}", va=va, shim="enemy_scaling",
                           symbol=f"_c_enemy_scaling_{what}", mode=mode, floats=FLOATS, tables=TABLES)


# (the hook, its span's size): a boss's or enemy's hit (the hit handler's call of 0x83FE0), a boss's played
# attack clip (anim_change's two loads past its play), the layer-rate setter (all of it, by a JMP), spideyzar's
# own rate (his FLD of it) and the attack range (all of it, by a JMP).
DAMAGE_HOOK = (_hook("damage", "a hit's cost by who deals it", 0x0008D648), 5)
CLIP_HOOK = (_hook("clip", "a boss's attack clip's rate", 0x000429F7), 8)
RATE_HOOK = (_hook("rate", "a boss's attack rate", 0x00030940, "jmp"), 9)
SPEED_HOOK = (_hook("speed", "spideyzar's slot 0x59 attack's rate", 0x0002C7E2), 6)
REACH_HOOK = (_hook("reach", "an enemy's attack range by its size", 0x000256B0, "jmp"), 9)
HOOKS = (DAMAGE_HOOK, CLIP_HOOK, RATE_HOOK, SPEED_HOOK, REACH_HOOK)

# The two AIs that set a boss's scale each tick (the fire guardians' 0x29F40, the water tentacles' 0x2F440)
# read four float constants (1.0, 0.1, 2.0 and the tentacles' 1/3, in this order) with seven 6-byte x87
# instructions; boss size points each at a copy of its constant x k.
SIZE_CONSTANTS = (0x001A250C, 0x001A2674, 0x001A2588, 0x00198770)
SIZE_SITES = ((0x0002A020, 0x001A2674), (0x0002A046, 0x001A250C), (0x0002A04C, 0x001A2588),
              (0x0002F4B0, 0x001A250C), (0x0002F4BD, 0x00198770), (0x0002F4C9, 0x001A250C),
              (0x0002F4D8, 0x001A250C))


def _size(xbe: Xbe, k: float) -> None:
    """Each size site's constant x ``k`` in a carved block, and each site pointing at its copy."""
    for va, const in SIZE_SITES:
        if struct.unpack("<I", xbe.read(va, 6)[2:])[0] != xbe.va(const):
            raise ValueError(f"boss size: the instruction at 0x{va:08X} doesn't read 0x{const:08X}")
    block = xbe.carve(b"".join(xbe.f32(k * struct.unpack("<f", xbe.read(c, 4))[0], "boss size")
                               for c in SIZE_CONSTANTS), "boss size's constants")
    at = {c: block + 4 * i for i, c in enumerate(SIZE_CONSTANTS)}
    for va, const in SIZE_SITES:
        xbe.write(va, f"boss size at 0x{va:X}", xbe.read(va, 2) + struct.pack("<I", at[const]))


def _tables(xbe: Xbe) -> dict[str, bytes]:
    return {"bosses": b"".join(n.encode() + b"\0" for n in BOSSES) + b"\0",
            "enemies": b"".join(n.encode() + b"\0" for n in ENEMIES) + b"\0",
            "records": b"".join(c.encode() + n.encode() + b"\0" for c, names in PLATFORM_RECORDS.items()
                                for n in names) + b"\0",
            "calls": struct.pack("<II", xbe.va(DAMAGE_VA), xbe.va(RECORDS_VA))}


def apply(xbe: Xbe, enemy_health_scale: float, enemy_damage_dealt_scale: float, enemy_attack_speed_scale: float,
          enemy_move_speed_scale: float, enemy_size_scale: float, boss_health_scale: float,
          boss_damage_dealt_scale: float, boss_attack_speed_scale: float, boss_move_speed_scale: float,
          boss_size_scale: float) -> None:
    """The shim's landings for the sliders off 1.0 (the cell sliders'
    cells are the engine's): the damage hook for either damage slider, the
    clip, rate and speed hooks for the bosses' attack speed, the reach hook
    for either size; and boss size's constants. A damage k whose product
    with the largest record no int32 holds is refused (D45)."""
    for name, k in ((DAMAGE_DEALT.label, enemy_damage_dealt_scale), (BOSS_DAMAGE_DEALT.label, boss_damage_dealt_scale)):
        if not -2**31 <= math.trunc(k * MAX_RECORD_DAMAGE) <= 2**31 - 1:
            raise ValueError(f"{name}: x{k:g} of a {MAX_RECORD_DAMAGE} HP hit doesn't fit the game's 32-bit integer "
                             f"({-2**31}..{2**31 - 1})")
    if boss_size_scale != 1.0:
        _size(xbe, boss_size_scale)
    hooks = ([DAMAGE_HOOK] if enemy_damage_dealt_scale != 1.0 or boss_damage_dealt_scale != 1.0 else []) \
        + ([CLIP_HOOK, RATE_HOOK, SPEED_HOOK] if boss_attack_speed_scale != 1.0 else []) \
        + ([REACH_HOOK] if enemy_size_scale != 1.0 or boss_size_scale != 1.0 else [])
    params = {DAMAGE_DEALT.name: enemy_damage_dealt_scale, BOSS_DAMAGE_DEALT.name: boss_damage_dealt_scale,
              BOSS_ATTACK_SPEED.name: boss_attack_speed_scale, SIZE.name: enemy_size_scale,
              BOSS_SIZE.name: boss_size_scale} | (_tables(xbe) if hooks else {})
    for hook, _ in hooks:
        xbe.patch(hook, params=params)


PACK = Pack(
    name="enemy_scaling",
    description="Enemies' and bosses' health, damage dealt, attack and movement speed, and size.",
    sites=(HEALTH, DAMAGE_DEALT, ATTACK_SPEED, MOVE_SPEED, SIZE,
           BOSS_HEALTH, BOSS_DAMAGE_DEALT, BOSS_ATTACK_SPEED, BOSS_MOVE_SPEED, BOSS_SIZE),
    custom_apply=apply,
    footprint=(*(Place(va=hook.va, size=size) for hook, size in HOOKS),
               *(Place(va=va, size=6) for va, _ in SIZE_SITES)),
    category="enemies",
)
