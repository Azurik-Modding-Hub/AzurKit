"""player_physics: gravity and the player's walk, jump, swim, roll, climb,
air control and wing flaps, each slider scaling its own vanilla baseline
and writing nothing at 1.0 (gravity at its 9.8). Off by default.

- **Gravity** is the world's float at 0x1980A8, every entity's: jump and
  flap heights stay the same (their launch speed is sqrt(2gh) with the same
  g, below).
- **Walk** is garret4's ``runSpeed`` in config.xbr (the player's species,
  whatever body it wears), k x its vanilla 7.0; no XBE byte (D53).
- **Swim**, **jump**, **flap height** and the **far-descent flap**
  (``flap_below_peak_scale``) each rewrite one 6-byte x87 load or multiply
  of a shared constant (the swim stroke's 10.0 at 0x8B7BF; gravity in the
  jump at 0x89160 and the flap at 0x893AE, g x k^2 so the launch speed is k
  x vanilla's at any gravity, D16; the 0.5 that halves a flap more than 6 m
  below the flap ceiling at 0x893DD) to read a float of its own the build
  carves.
- **Air control** rewrites the seven imm32s that set the airborne steering
  speed (9.0, and 12.0 with air power), and the two **fuel** sliders the
  pushed costs of a flap's consume_fuel (100.0 far below the ceiling at
  0x893CE, 1.0 every flap at 0x8934E).
- **Roll distance** (the roll's root-motion velocity, a 36-byte shim at its
  call of gravity_integrate_raw, 0x8C745), **roll speed** (its clip rate, 22
  bytes at the load of the move's rate, 0x889BB), **climb speed** (the rung
  step and the climb moves' rates: 67 bytes whose four entries the seven
  readers of the two climb constants call) and the **wing-flap ceiling**
  (the peak the jump latches, 15 bytes at 0x89154) are hand-written shims,
  each with its k in a data block it reads (with a 4-byte 0xFF sentinel,
  kept so the bytes are Modkit's).
- **The speed toggle** (D713): ``toggle_<slider>`` 1 picks a slider a left
  stick click (L3) flips between the build's value and vanilla's while the
  game runs, a note in the HUD's corner for 2 s; a game start puts the
  build's back. Its C shim (``shims/player_physics.c``) lands at the
  PlayerControl tick's call of the physics state machine (0x8C37D), the
  HUD draw (0x5545A) and game_start_setup (0x52F50), with a table of each
  value's address, the build's dword and vanilla's; the tick's landing keeps
  the state, the other two its address. None picked installs nothing. A
  worn body's ``size_fold`` (sqrt(s), the input the sdk hands it with a
  character, Modkit's Step 2.186) is the walk's and the roll distance's
  vanilla there: 7 sqrt(s) and sqrt(s), the body's own, not garret4's.

Ported from Modkit's ``azurik_mod/patches/player_physics`` at the packs
oracle's tag, whose docstring holds each site's evidence.
"""

from __future__ import annotations

import inspect
import struct

from azurkit.tools.mods.engine import (BytesParam, Hook, Pack, ParametricPatch, Place, TrampolinePatch,
                                       XbrParametricEdit, Xbe)

GRAVITY = ParametricPatch(name="gravity", label="World gravity", va=0x001980A8, default=9.8, slider_min=0.0,
                          slider_max=100.0, slider_step=0.1, unit="m/s^2", logic_floor="max",
                          description="World gravity for every entity (Earth 9.8); jump and flap heights stay "
                                      "the same.")


def _scale(name: str, label: str, lo: float, hi: float, step: float, description: str,
           floor: str | None = "min") -> ParametricPatch:
    return ParametricPatch(name=name, label=label, default=1.0, slider_min=lo, slider_max=hi, slider_step=step,
                           unit="x", vanilla=1.0, description=description, logic_floor=floor)


SCALES = (
    _scale("roll_speed_scale", "Roll distance", 0.0, 3.0, 0.05,
           "How far the roll goes; 0 rolls in place, negative rolls backwards."),
    _scale("roll_time_scale", "Roll speed", 0.25, 4.0, 0.05,
           "How fast the roll plays: 2x takes half the time, the same distance from a run.", None),
    _scale("climb_speed_scale", "Climb speed", 0.25, 4.0, 0.05,
           "How fast the player climbs ladders and ledges, animation and movement together.", None),
    _scale("swim_speed_scale", "Player swim speed", 0.1, 10.0, 0.05,
           "Horizontal swim speed; diving and rising keep their 5 m/s."),
    _scale("jump_speed_scale", "Player jump height", 0.1, 5.0, 0.05,
           "The jump's launch speed (2x = 4x height); past 1.41x raise the flap ceiling too."),
    _scale("air_control_scale", "Player air-control speed", 0.1, 10.0, 0.05,
           "How fast the stick moves the player sideways in the air."),
    _scale("flap_height_scale", "Wing-flap: flap height", 0.1, 10.0, 0.05,
           "Each wing flap's launch speed (2x = 4x height)."),
    _scale("flap_below_peak_scale", "Wing-flap: far-descent recovery", 0.1, 10.0, 0.05,
           "Lift of a flap far below the flap ceiling, against a normal flap."),
    _scale("wing_flap_ceiling_scale", "Wing-flap: altitude ceiling", 0.1, 20.0, 0.05,
           "Flaps lift to (K + 1) x 1.2 m above take-off; a k x jump needs K >= k^2 - 1."),
    _scale("flap_descent_fuel_cost_scale", "Wing-flap: descent penalty fuel", -0.05, 1.0, 0.001,
           "Fuel of a flap far below the flap ceiling; vanilla's 100 empties the gauge.", None),
    _scale("flap_entry_fuel_cost_scale", "Wing-flap: fuel cost per flap", -5.0, 5.0, 0.1,
           "Fuel each flap costs; 0 never drains the gauge, negative refunds.", "max"),
)
WALK = XbrParametricEdit(name="walk_speed_scale", label="Player walk speed", table="critters_critter_data",
                         entity="garret4", prop="runSpeed", default=1.0, slider_min=0.1, slider_max=10.0,
                         slider_step=0.05, unit="x", logic_floor="min",
                         description="Walk speed at full stick (garret4's runSpeed in config.xbr).",
                         cells=lambda tables: [("garret4", tables["critters_critter_data"].column("garret4"),
                                                "runSpeed", tables["critters_critter_data"].number("garret4",
                                                                                                    "runSpeed"))])
FLIPPED = (GRAVITY, *SCALES, WALK)   # every slider the left stick click can flip
TOGGLES = tuple(ParametricPatch(name=f"toggle_{s.name}", label=f"L3 flips: {s.label}", default=0, slider_min=0,
                                slider_max=1, slider_step=1, vanilla=0, whole=(0, 1), why="1 picks it, 0 doesn't",
                                description=f"1: a left stick click flips {s.label.lower()} to vanilla and back.")
                for s in FLIPPED)
SLIDERS = (*FLIPPED, *TOGGLES)


def _held(xbe: Xbe, va: int, size: int = 4) -> float:
    """The vanilla float at this release's own ``va``."""
    return struct.unpack("<f", xbe.read(va, size, own=True)[:4])[0]


def _operand(xbe: Xbe, site: int) -> int:
    """The release's own address a vanilla 6-byte ``op [abs32]`` at the USA ``site`` reads."""
    return struct.unpack("<I", xbe.read(site, 6)[2:])[0]


# The hand-written shims: each body is built at its own address (``at``) with its data block's (``k``); the
# USA addresses of the game's it names sit at its ``abs32`` offsets, the targets of its branches at ``rel32``.
ROLL_HOOK, ROLL_SIZE = 0x0008C745, 36
GRAVITY_INTEGRATE_RAW = 0x00085700


def _roll(at: int, k: int) -> bytes:
    """If entity+0x134 (ESI's) is 20, the roll: the velocity at EDX, x and y,
    times k (x87, two slots); then a tail jump to gravity_integrate_raw."""
    return (bytes.fromhex("83be3401000014 7516 d905") + struct.pack("<I", k) + bytes.fromhex("d902d8c9d91a")
            + bytes.fromhex("d94204") + bytes.fromhex("d8c9d95a04 ddd8 e9")
            + struct.pack("<i", GRAVITY_INTEGRATE_RAW - (at + ROLL_SIZE)))


ROLL_TIME_HOOK, ROLL_TIME_SIZE = 0x000889BB, 22


def _roll_time(at: int, k: int) -> bytes:
    """The move's rate (EDI+0x104) loaded as the hook's load did, times k
    when entity+0x134 is 20, the roll; then a return."""
    return (bytes.fromhex("d98704010000 83bf3401000014 7506 d80d") + struct.pack("<I", k) + b"\xC3")


CLIMB_RUNG, CLIMB_MOVE, CLIMB_SIZE = 0x001980E4, 0x001980E0, 67
CLIMB_ENTRY = {"fld": 0, "eax": 13, "ecx": 31, "edx": 49}
# Each reader of the two climb constants (its 6- or 5-byte load) and the entry of the climb shim it calls.
CLIMB_HOOKS = ((0x00087FA7, 6, "fld"), (0x00088357, 6, "fld"), (0x00086D96, 5, "eax"), (0x000870EE, 6, "ecx"),
               (0x0008743B, 6, "ecx"), (0x00087920, 6, "ecx"), (0x00087F4C, 6, "edx"))


def _climb(at: int, k: int) -> bytes:
    """Four entries: ST0 = the rung step's 2.0 x k, and EAX, ECX or EDX = the
    float bits of the climb moves' 1.5 x k, each through the stack, its
    register's push and pop around it."""
    def load(va: int) -> bytes:   # the constant at va times k, in ST0
        return bytes.fromhex("d905") + struct.pack("<I", va) + bytes.fromhex("d80d") + struct.pack("<I", k)
    return load(CLIMB_RUNG) + b"\xC3" + b"".join(bytes([push]) + load(CLIMB_MOVE) + bytes.fromhex("d91c24")
                                                 + bytes([push + 8, 0xC3]) for push in (0x50, 0x51, 0x52))


CEILING_HOOK, CEILING_SIZE = 0x00089154, 15


def _ceiling(at: int, k: int) -> bytes:
    """The flap height (ESI+0x144) times k, added into the take-off z the
    jump left in ST0, popped; then a return."""
    return bytes.fromhex("d98644010000 d80d") + struct.pack("<I", k) + bytes.fromhex("dec1 c3")


SWIM, JUMP, FLAP, BELOW_PEAK = 0x0008B7BF, 0x00089160, 0x000893AE, 0x000893DD   # 6-byte loads and multiplies
AIR_CONTROL = (0x00084ED3, 0x000856D4, 0x000890EA, 0x00089126, 0x0008D322, 0x00083FAC, 0x00083FCE)   # imm32s
DESCENT_FUEL, ENTRY_FUEL = 0x000893CE, 0x0008934E   # the pushed costs, imm32s
HUD_MATERIAL = 0x00097420   # the game's 2D material (its first instruction keeps it out of the facts' functions)
TOGGLE_SLOTS = 24
TABLES = (BytesParam("speed_toggle_table", "_speed_toggle_table", 4 + 12 * TOGGLE_SLOTS),
          BytesParam("speed_toggle_walk", "_speed_toggle_walk", 12),
          BytesParam("speed_toggle_state_at", "_speed_toggle_state_at", 4),
          BytesParam("speed_toggle_material", "_speed_toggle_material", 4))


def _toggle(what: str, why: str, va: int) -> TrampolinePatch:
    return TrampolinePatch(label=f"Speed toggle: {why}", va=va, shim="player_physics",
                           symbol=f"_c_speed_toggle_{what}", tables=TABLES)


TOGGLE_HOOKS = ((_toggle("tick", "the left stick click (L3) each player tick", 0x0008C37D), 5),
                (_toggle("hud", "its note after the HUD draw", 0x0005545A), 5),
                (_toggle("start", "the build's values at a game start", 0x00052F50), 6))


def _hand(xbe: Xbe, label: str, hook: tuple[int, int], body, size: int, k: float, *, writable: bool = False,
          abs32=(), rel32=()) -> tuple[int, int]:
    """A hand-written shim: its data block (k and the sentinel), its body,
    and the hook's CALL to it; ``(the body's address, the data's)``."""
    data = xbe.carve(xbe.f32(k, label) + b"\xFF" * 4, f"{label}: k", writable=writable)
    at = xbe.carve(lambda at: xbe.moved(body(at, data), at, abs32, rel32), label, size=size)
    xbe.patch(Hook(label=label, va=hook[0], target=at))
    return at, data


def _load(xbe: Xbe, site: int, label: str, value: float) -> tuple[int, bytes]:
    """The 6-byte load or multiply at ``site`` pointed at a carved float of
    ``value``: the float's address and bytes."""
    data = xbe.f32(value, label)
    float_va = xbe.carve(data, label)
    xbe.write(site, label, xbe.read(site, 2) + struct.pack("<I", float_va))
    return float_va, data


def apply(xbe: Xbe, size_fold: float | None = None, **values: float) -> None:
    """Each slider off its default at its sites, in Modkit's order (the
    carves land in it), then the speed toggle for the picked sliders
    (``size_fold``: a worn body's sqrt(s), its walk and roll's vanilla)."""
    fold = 1.0 if size_fold is None else size_fold
    g = values[GRAVITY.name]
    if g != GRAVITY.default:
        xbe.patch(GRAVITY, g)
    held: dict[str, list[tuple[int, bytes, bytes]]] = {}   # a slider -> (address, the build's dword, vanilla's)
    one = xbe.f32(1.0, "vanilla")
    at = values.get
    if (k := at("roll_speed_scale")) != 1.0:
        held["roll_speed_scale"] = [(_hand(xbe, "the roll's distance", (ROLL_HOOK, 5), _roll, ROLL_SIZE, k,
                                           rel32=(32,))[1], xbe.f32(k, "roll"), xbe.f32(fold, "roll"))]
    if (k := at("roll_time_scale")) != 1.0:
        held["roll_time_scale"] = [(_hand(xbe, "the roll's speed", (ROLL_TIME_HOOK, 6), _roll_time, ROLL_TIME_SIZE, k,
                                          writable=True)[1], xbe.f32(k, "roll"), one)]
    if (k := at("climb_speed_scale")) != 1.0:
        (va, width, _), *others = CLIMB_HOOKS
        shim, data = _hand(xbe, "the climb's speed", (va, width), _climb, CLIMB_SIZE, k, writable=True,
                           abs32=(2, 16, 34, 52))
        for va, width, entry in others:
            xbe.patch(Hook(label=f"the climb's speed at 0x{va:X}", va=va, target=shim + CLIMB_ENTRY[entry]))
        held["climb_speed_scale"] = [(data, xbe.f32(k, "climb"), one)]
    if (k := at("swim_speed_scale")) != 1.0:
        base = _held(xbe, _operand(xbe, SWIM))
        held["swim_speed_scale"] = [(*_load(xbe, SWIM, "the swim stroke", base * k), xbe.f32(base, "swim"))]
    jumps = {}
    if (k := at("jump_speed_scale")) != 1.0:
        jumps["jump_speed_scale"] = _load(xbe, JUMP, "the jump's gravity", g * k * k)
    if (k := at("air_control_scale")) != 1.0:
        held["air_control_scale"] = []
        for va in AIR_CONTROL:
            base = struct.unpack("<f", xbe.read(va, 4))[0]
            xbe.write(va, f"air control at 0x{va:X}", xbe.f32(base * k, "air control"))
            held["air_control_scale"].append((xbe.va(va), xbe.f32(base * k, "air control"), xbe.read(va, 4)))
    if (k := at("flap_height_scale")) != 1.0:
        jumps["flap_height_scale"] = _load(xbe, FLAP, "the flap's gravity", g * k * k)
    if (k := at("flap_below_peak_scale")) != 1.0:
        base = _held(xbe, _operand(xbe, BELOW_PEAK))
        held["flap_below_peak_scale"] = [(*_load(xbe, BELOW_PEAK, "a far-descent flap's halving", base * k),
                                          xbe.f32(base, "flap"))]
    if (k := at("wing_flap_ceiling_scale")) != 1.0:
        held["wing_flap_ceiling_scale"] = [(_hand(xbe, "the wing-flap ceiling", (CEILING_HOOK, 6), _ceiling,
                                                  CEILING_SIZE, k)[1], xbe.f32(k, "ceiling"), one)]
    for name, va in (("flap_descent_fuel_cost_scale", DESCENT_FUEL), ("flap_entry_fuel_cost_scale", ENTRY_FUEL)):
        if (k := at(name)) != 1.0:
            base = struct.unpack("<f", xbe.read(va, 4))[0]
            xbe.write(va, f"{name} at 0x{va:X}", xbe.f32(base * k, name))
            held[name] = [(xbe.va(va), xbe.f32(base * k, name), xbe.read(va, 4))]
    picked = {s.name for s in FLIPPED if values[f"toggle_{s.name}"]}
    if picked:
        _toggle_install(xbe, picked, values, held, jumps, fold)


def _toggle_install(xbe: Xbe, picked: set[str], values: dict, held: dict, jumps: dict, fold: float) -> None:
    """The speed toggle for the ``picked`` sliders: the table of what a click
    flips (each slot whose build and vanilla dwords differ, in Modkit's
    order), the walk's two runSpeeds (vanilla's x ``fold``), then the three
    landings."""
    vanilla_g = values[GRAVITY.name] if GRAVITY.name not in picked else GRAVITY.default
    slots = []
    if GRAVITY.name in picked:
        slots.append((xbe.va(GRAVITY.va), xbe.f32(values[GRAVITY.name], "gravity"), xbe.read(GRAVITY.va, 4)))
    for s in SCALES:
        if s.name in picked:
            slots += held.get(s.name, [])
    for name in ("jump_speed_scale", "flap_height_scale"):
        if (name in picked or GRAVITY.name in picked) and name in jumps:
            k = 1.0 if name in picked else values[name]
            slots.append((*jumps[name], xbe.f32(vanilla_g * k * k, name)))
    slots = [(va, on, off) for va, on, off in slots if on != off]
    base = xbe.tables["critters_critter_data"].number("garret4", "runSpeed")
    walk = (xbe.f32(base * values[WALK.name], "walk"), xbe.f32(base * fold, "walk"))
    walk = walk if WALK.name in picked and walk[0] != walk[1] else None
    if not slots and walk is None:
        xbe.notes.append(f"player_physics: the speed toggle's {', '.join(sorted(picked))} build vanilla's values, "
                         "so the left stick click has nothing to flip; not installed")
        return
    params = {"speed_toggle_table": struct.pack("<I", len(slots)) + b"".join(struct.pack("<I", va) + on + off
                                                                             for va, on, off in slots),
              "speed_toggle_walk": b"" if walk is None else struct.pack("<I", 1) + walk[0] + walk[1],
              "speed_toggle_material": struct.pack("<I", xbe.va(HUD_MATERIAL))}
    (tick, _), *others = TOGGLE_HOOKS
    xbe.patch(tick, params=params)
    if (state := xbe.landed.get(tick.label, {}).get("_speed_toggle_state")) is None:
        return   # the tick didn't land: its failure is recorded
    for hook, _ in others:
        xbe.patch(hook, params=params | {"speed_toggle_state_at": struct.pack("<I", state)})


apply.__signature__ = inspect.Signature(   # it takes every slider, then its input, as a custom_apply does
    [inspect.Parameter("xbe", inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    + [inspect.Parameter(s.name, inspect.Parameter.KEYWORD_ONLY) for s in SLIDERS]
    + [inspect.Parameter("size_fold", inspect.Parameter.KEYWORD_ONLY, default=None)])

PACK = Pack(
    name="player_physics",
    description="Gravity and the player's walk, jump, swim, roll, climb, air control and flaps.",
    sites=SLIDERS,
    custom_apply=apply,
    inputs=("size_fold",),
    footprint=(Place(va=GRAVITY.va), Place(va=ROLL_HOOK, size=5), Place(va=ROLL_TIME_HOOK, size=6),
               *(Place(va=va, size=width) for va, width, _ in CLIMB_HOOKS),
               *(Place(va=va, size=6) for va in (SWIM, JUMP, FLAP, BELOW_PEAK)),
               *(Place(va=va, size=4) for va in (*AIR_CONTROL, DESCENT_FUEL, ENTRY_FUEL)),
               Place(va=CEILING_HOOK, size=6), *(Place(va=hook.va, size=width) for hook, width in TOGGLE_HOOKS)),
    category="player",
)
