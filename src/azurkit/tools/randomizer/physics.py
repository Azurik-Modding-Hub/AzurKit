"""The movement physics calculator (Step R1.2b, D167): any movement settings
-> a reach envelope.

:class:`Movement` holds the settings that move the player, one field per
movement slider (:data:`SLIDERS`; :meth:`Movement.from_params` reads a
build's ``{pack: {slider: value}}``), vanilla by default.  :class:`Physics`
runs the game's movement laws under them (the per-tick model,
:meth:`Physics.tick_arc`, stores float32 as the game does; the search uses
the same laws in closed form), and :class:`Envelope` turns them into reach:
for a landing ``dh`` above the takeoff (negative: a drop) and, optionally,
a ceiling, the longest horizontal flight of each air rank (0 no air shield,
1-3 air shield N: :class:`Kit`) from a run or from standing, with the best
flap timing, and the highest rise.  The difficulty tiers are margins over
it (``draft/tiers.toml``).  Stdlib only, so the planner and a build can
call it with a build's sliders (Step R1.14b).

The laws (``docs/RE_MOVEMENT.md``; labels as in ``draft/envelope.py``:
[verified xemu sN / calib / p9] measured in game, [verified L2] the game's
own code under :mod:`azurik_mod.sim.l2`, [verified static] code read):

  tick         dt = 1 / fps (vanilla 30) [verified static 0x1980A0].
  jump tick    vz := k sqrt(2 g h) (k: jump_speed_scale, which injects
               g k^2 at the FLD 0x89160), no translation, the horizontal
               velocity kept; h = 1.1 and air control 9 c (no air power),
               h = 1.2 and air control 12 c with an air shield whose Flaps
               is not 0 (c: air_control_scale; 0x83F90).  The flap
               ceiling latch peak := takeoff + K h (K:
               wing_flap_ceiling_scale; the shim at 0x89154).
  air tick     v_xy := T + (v_xy - T) 0.6^dt, T = air control x stick;
               vz -= g dt; pos += v dt (semi-implicit Euler) [verified xemu
               s1, s6; L2].
  flap tick    a fresh press with counter < Flaps and a non-empty gauge:
               consume_fuel(e) (e: flap_entry_fuel_cost_scale) takes
               e / Flaps off the gauge and empties it (the shield drops)
               when under half a step is left; d = peak + h - z;
               v0f = f sqrt(2 g min(max(d, 0), h)) (f: flap_height_scale);
               d > 6 (the descent flap) also costs consume_fuel(100 q)
               (q: flap_descent_fuel_cost_scale) and multiplies v0f by
               0.5 b (b: flap_below_peak_scale); vz := min(v0f, vz + 1.5
               v0f).  No translation, no blend on that tick; presses 2
               ticks apart all register [verified xemu s6, calib, p9; L2].
               After the gauge empties no flap lifts this jump.
  roof         the tick the head would pass a roof the feet stop there
               (about 1.9 m under it) and the speed into it is gone;
               the arc falls on from there [verified L3, Step X.21].
  walk / run   run_speed x stick (garret4 runSpeed, walk_speed_scale x
               7.0) after about run_speed / 3.27 ramp ticks [verified xemu
               s3, s6].
  roll, swim   outside the logic (movement.MODELLED); measured in
               docs/RE_MOVEMENT.md.  Swim: toward 10 x swim_speed_scale m/s
               [verified xemu s6, p9].
  falls        damage needs |vz| > 10 m/s and a drop of 6 / 8 / 17 m for
               5 / 10 / 1000 HP [verified static].
"""

from __future__ import annotations

import functools
import itertools
import math
import struct
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import NamedTuple, Protocol

def f32(x: float) -> float:
    """``x`` rounded to float32, as the game stores it."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


# --------------------------------------------------------------------------- vanilla constants
FPS = 30.0                    # [verified static] dt 0x1980A0 = 1/30
GRAVITY = 9.8                 # [verified static] 0x1980A8
RUN_SPEED = 7.0               # [verified xemu s6] garret4 runSpeed x stick 1 (7.00009 measured)
H_PLAIN, H_AIR = 1.1, 1.2     # [verified L2 + xemu s6] entity+0x144
AC_PLAIN, AC_AIR = 9.0, 12.0  # [verified L2 + xemu s6] entity+0x140
FLAPS = (1, 2, 5)             # [verified config.xbr via L2 armor_slots] air shields 1-3
BLEND = 0.6                   # [verified static 0x894FB-0x8960E; xemu fit r = 0.983117]
FLAP_MULT = 1.5               # [verified xemu s6] vz + 1.5 v0f
DESCENT_D = 6.0               # [verified static 0x893C0] d > 6: the descent flap
DESCENT_FACTOR = 0.5          # [verified static 0x893DD]
FLAP_COST, DESCENT_COST = 1.0, 100.0   # [verified static 0x8934E, 0x893CE] consume_fuel's costs
FLAP_MIN_PERIOD = 2           # [verified xemu calib §5] presses every 2nd tick all register
RAMP_DV = 3.26667             # [verified xemu s6] ground speed gained per tick from rest (30 fps)
BODY_HEIGHT = 2.0             # the logic body (draft/floors.py's height) [inferred; L3: the head ~1.9 m over the feet]
FALL_MIN_V = 10.0             # [verified static 0x8AC66-0x8AD9B]
FALL_STEPS = ((6.0, 5), (8.0, 10), (17.0, 1000))
SWIM_MPS, SWIM_VERTICAL_MPS = 10.0, 5.0                  # [verified xemu s6 §3]


# --------------------------------------------------------------------------- the settings
@dataclass(frozen=True)
class Movement:
    """The movement settings, one field per slider (:data:`SLIDERS`);
    every default is vanilla."""
    run_speed: float = RUN_SPEED         # m/s at full stick (Azurik walks and runs at runSpeed x stick)
    jump_scale: float = 1.0              # the jump's launch speed (height x k^2)
    gravity: float = GRAVITY             # m/s^2, every entity
    air_control_scale: float = 1.0       # the air-control target, 9 / 12 m/s x c
    flap_scale: float = 1.0              # each flap's launch speed
    flaps: tuple[int, int, int] = FLAPS  # flaps per jump of air shields 1-3 (Flaps, truncated)
    flap_ceiling_scale: float = 1.0      # the flap ceiling latch, takeoff + K h
    descent_scale: float = 1.0           # a descent flap's lift, against vanilla's halving
    descent_fuel_scale: float = 1.0      # a descent flap's fuel, 100 x q
    flap_fuel_scale: float = 1.0         # each flap's fuel, 1 x e
    roll_scale: float = 1.0
    roll_time_scale: float = 1.0         # how fast the roll plays, the same distance (Step 2.185)
    climb_scale: float = 1.0             # how fast ladders and ledges are climbed, the same path (Step 2.185)
    swim_scale: float = 1.0
    fps: float = FPS                     # fps_unlock's target_fps when it is on

    @classmethod
    def from_params(cls, params: Mapping[str, Mapping[str, float]], enabled=None) -> Movement:
        """The settings of a build's sliders, ``{pack: {slider: value}}``
        (an unset slider keeps its vanilla value; ``enabled``, when
        given, names the packs that apply: a pack not in it is ignored).
        A movement pack's slider this table doesn't know, or a NaN or inf
        value (D23), fails by name (``ValueError``), so a new movement
        slider must be mapped here."""
        on = None if enabled is None else set(enabled)
        values = {f.name: getattr(cls(), f.name) for f in fields(cls)}
        flaps = list(values["flaps"])
        packs = {p for p, _ in SLIDERS}
        for pack, sliders in params.items():
            if pack not in packs or (on is not None and pack not in on):
                continue
            for name, value in sliders.items():
                if (pack, name) not in SLIDERS:
                    raise ValueError(f"{pack} {name}: not a movement slider the physics calculator maps "
                                     f"(azurik_mod/randomizer/physics.py SLIDERS)")
                field, how = SLIDERS[(pack, name)]
                value = float(value)
                if not math.isfinite(value):
                    raise ValueError(f"{pack} {name}: value {value} is not finite; a slider accepts any finite "
                                     f"number, never NaN or inf (D23)")
                if field == "flaps":
                    flaps[how] = math.trunc(value)      # the armor loader 0xF5A40 truncates
                else:
                    values[field] = value * how if how is not None else value
        if on is not None and "fps_unlock" in on and not params.get("fps_unlock", {}).get("target_fps"):
            values["fps"] = 60.0                        # fps_unlock's default rate
        values["flaps"] = tuple(flaps)
        return cls(**values)


# (pack, slider) -> (Movement field, the scale base (value x base) or, for flaps, the shield index)
SLIDERS = {
    ("player_physics", "walk_speed_scale"): ("run_speed", RUN_SPEED),
    ("player_physics", "gravity"): ("gravity", None),
    ("player_physics", "jump_speed_scale"): ("jump_scale", None),
    ("player_physics", "air_control_scale"): ("air_control_scale", None),
    ("player_physics", "flap_height_scale"): ("flap_scale", None),
    ("player_physics", "wing_flap_ceiling_scale"): ("flap_ceiling_scale", None),
    ("player_physics", "flap_below_peak_scale"): ("descent_scale", None),
    ("player_physics", "flap_descent_fuel_cost_scale"): ("descent_fuel_scale", None),
    ("player_physics", "flap_entry_fuel_cost_scale"): ("flap_fuel_scale", None),
    ("player_physics", "roll_speed_scale"): ("roll_scale", None),
    ("player_physics", "roll_time_scale"): ("roll_time_scale", None),
    ("player_physics", "climb_speed_scale"): ("climb_scale", None),
    ("player_physics", "swim_speed_scale"): ("swim_scale", None),
    ("air_shield_flaps", "air_shield_1_flaps"): ("flaps", 0),
    ("air_shield_flaps", "air_shield_2_flaps"): ("flaps", 1),
    ("air_shield_flaps", "air_shield_3_flaps"): ("flaps", 2),
    ("fps_unlock", "target_fps"): ("fps", None),
}
VANILLA = Movement()


def slider_values(params: Mapping[str, Mapping[str, float]], enabled=None) -> dict[str, dict[str, float]]:
    """The movement sliders (:data:`SLIDERS`) ``params`` sets otherwise than
    vanilla, as :meth:`Movement.from_params` reads them (``enabled`` too;
    fps_unlock on with no rate is its 60), ``{pack: {slider: value}}``:
    what a build's share string and placement file record (AZ-383).
    ``Movement.from_params`` of it is the same movement."""
    on = None if enabled is None else set(enabled)
    given = {(pack, name): float(v) for pack, sliders in params.items() if on is None or pack in on
             for name, v in sliders.items() if (pack, name) in SLIDERS}
    if on is not None and "fps_unlock" in on and not params.get("fps_unlock", {}).get("target_fps"):
        given[("fps_unlock", "target_fps")] = 60.0
    out: dict[str, dict[str, float]] = {}
    for (pack, name), v in sorted(given.items()):
        if Movement.from_params({pack: {name: v}}) != VANILLA:
            out.setdefault(pack, {})[name] = v
    return out


# --------------------------------------------------------------------------- the kits
@dataclass(frozen=True)
class Kit:
    """What one jump can do at an air rank: 0 no air power, N an air
    shield of level N (``air>=N``), freshly cast (a full gauge)."""
    rank: int
    h: float           # entity+0x144, f32
    air_control: float  # entity+0x140, f32
    flaps: int         # the per-jump cap (the slot's Flaps)
    v0: float          # the jump's launch speed, f32

    @property
    def name(self) -> str:
        return "none" if self.rank == 0 else f"air{self.rank}"


# --------------------------------------------------------------------------- the calculator
class Arc(NamedTuple):
    """A flight's outcome at a landing level."""
    cross: float | None   # air ticks to the last descending crossing of the level (None: never reached)
    apex: float           # the feet's highest point above the takeoff
    ticks: tuple          # the flaps that flapped (ticks after the jump tick)


RECOVER = 8.0     # a flap with the feet this far below the level (or below -30 m) is moot


class Physics:
    """The game's movement laws under :class:`Movement` ``m``."""

    def __init__(self, m: Movement = VANILLA):
        self.m = m
        self.dt = f32(1.0 / m.fps)
        self.g = f32(m.gravity)
        self.gdt = self.g * self.dt            # the x87 product of two f32s, exact in 53 bits
        self.blend = BLEND ** self.dt          # the per-tick blend factor (CRT pow)
        self.latch = m.flap_ceiling_scale      # peak = takeoff + K h
        self.descent = DESCENT_FACTOR * m.descent_scale
        c = m.air_control_scale
        self.kits = (self._kit(0, H_PLAIN, AC_PLAIN * c, 0),) + tuple(
            self._kit(n, H_AIR, AC_AIR * c, f) if f != 0 else self._kit(n, H_PLAIN, AC_PLAIN * c, 0)
            for n, f in enumerate(m.flaps, 1))

    def _kit(self, rank, h, ac, flaps) -> Kit:
        return Kit(rank, f32(h), f32(ac), max(int(flaps), 0), self.launch(h))

    def launch(self, h: float) -> float:
        """The launch speed of a jump (or a springboard) of height ``h``:
        the FLD of g k^2, x h, x 2, FSQRT, stored f32."""
        return f32(math.sqrt(2.0 * f32(self.g * self.m.jump_scale ** 2) * f32(h)))

    # ---- one flap
    def _consume(self, gauge: float, cost: float, flaps: int) -> tuple[float, bool]:
        """consume_fuel: the gauge after ``cost``, and whether it emptied."""
        step = cost / flaps
        left = f32(gauge - step)
        if left < step / 2:
            return 0.0, True
        return left, False

    def flap(self, kit: Kit, z: float, vz: float, gauge: float = 1.0, peak: float | None = None):
        """A flap at feet height ``z`` above the takeoff with ``vz``:
        (the new vz, the gauge left, whether the gauge emptied: no later
        flap this jump), or None when the press is refused.  ``peak`` is
        the latch above the takeoff (None: the jump's K h)."""
        if kit.flaps == 0 or gauge == 0.0:
            return None
        gauge, empty = self._consume(gauge, FLAP_COST * self.m.flap_fuel_scale, kit.flaps)
        d = (self.latch * kit.h if peak is None else peak) + kit.h - z
        v0f = self.m.flap_scale * math.sqrt(2.0 * self.g * min(max(d, 0.0), kit.h))
        if d > DESCENT_D:
            if not empty:
                gauge, empty = self._consume(gauge, DESCENT_COST * self.m.descent_fuel_scale, kit.flaps)
            v0f *= self.descent
        return min(v0f, vz + FLAP_MULT * v0f), gauge, empty

    # ---- the per-tick model (float32 storage, as the game)
    def tick_arc(self, kit: Kit, flap_ticks=(), v0_xy=(0.0, 0.0), target_dir=(1.0, 0.0), stick=1.0,
                 z_floor=-40.0, max_ticks=400, spring: float | None = None):
        """Tick by tick from the jump tick (k = 0): rows of (k, kind, x, y,
        z, vx, vy, vz) relative to the takeoff, until z < z_floor.  With
        ``spring`` the takeoff is a springboard launch of that height
        (air control 9 c whatever the shield; the first flap restores the
        kit's) [verified xemu calib §2]."""
        launch = kit.h if spring is None else spring
        vz = self.launch(launch)
        peak = self.latch * f32(launch)
        vx, vy = f32(v0_xy[0]), f32(v0_xy[1])
        ac = kit.air_control if spring is None else f32(AC_PLAIN * self.m.air_control_scale)
        tx, ty = ac * stick * target_dir[0], ac * stick * target_dir[1]
        x = y = z = 0.0
        rows = [(0, "jump", x, y, z, vx, vy, vz)]
        flaps = set(sorted(flap_ticks)[: kit.flaps])
        used, gauge, empty = 0, 1.0, False
        for k in range(1, max_ticks):
            if k in flaps and used < kit.flaps and not empty:
                f = self.flap(kit, z, vz, gauge, peak)
                if f is not None:
                    vz, gauge, empty = f32(f[0]), f[1], f[2]
                    used += 1
                    tx = kit.air_control * stick * target_dir[0]     # 0x83F90 runs with the flap
                    ty = kit.air_control * stick * target_dir[1]
                    rows.append((k, "flap", x, y, z, vx, vy, vz))
                    continue
            vx = f32(tx + (vx - tx) * self.blend)
            vy = f32(ty + (vy - ty) * self.blend)
            vz = f32(vz - self.gdt)
            x, y, z = f32(x + f32(vx * self.dt)), f32(y + f32(vy * self.dt)), f32(z + f32(vz * self.dt))
            rows.append((k, "air", x, y, z, vx, vy, vz))
            if z < z_floor:
                break
        return rows

    # ---- the closed form (double precision)
    def x_after(self, m: int, v0: float, ac: float) -> float:
        """Horizontal travel after m air ticks from speed v0, blending toward ac."""
        if m <= 0:
            return 0.0
        r = self.blend
        return self.dt * (m * ac + (v0 - ac) * r * (1 - r ** m) / (1 - r))

    def v_at(self, m: int, v0: float, ac: float) -> float:
        return ac + (v0 - ac) * self.blend ** m

    def travel(self, air: float, v0: float, ac: float) -> float:
        """Horizontal travel at ``air`` (fractional) air ticks."""
        a = math.floor(air)
        return self.x_after(a, v0, ac) + (air - a) * self.v_at(a + 1, v0, ac) * self.dt

    def z_after(self, z: float, vz: float, m: int) -> float:
        return z + self.dt * (m * vz - self.gdt * m * (m + 1) / 2)

    def _seg_max(self, z, vz, n):
        if n <= 0:
            return z
        ms = vz / self.gdt - 0.5 if self.gdt > 0 else n
        cands = {0, n, max(0, min(n, math.floor(ms))), max(0, min(n, math.ceil(ms)))}
        return max(self.z_after(z, vz, m) for m in cands)

    def _seg_cross(self, z: float, vz: float, level: float, n: int | None):
        """The first air tick m (1..n; n None = unbounded) with z(m-1) >=
        level > z(m) on the ballistic segment from (z, vz); None if none."""
        a = -self.dt * self.gdt / 2
        b = self.dt * (vz - self.gdt / 2)
        c = z - level
        if a == 0:                                  # no gravity: a straight line
            if b >= 0 or c < 0:
                return None
            m = math.floor(c / -b) + 1
            return None if n is not None and m > n else m
        disc = b * b - 4 * a * c
        if disc < 0:
            return None
        r2 = (-b - math.sqrt(disc)) / (2 * a)       # the larger root (a < 0)
        r1 = (-b + math.sqrt(disc)) / (2 * a)
        m = math.floor(r2) + 1
        # fix float edge cases by direct evaluation
        while m - 1 >= 0 and self.z_after(z, vz, m - 1) < level:
            m -= 1
        while self.z_after(z, vz, m) >= level:
            m += 1
        if m - 1 < 0 or m - 1 < math.ceil(r1 - 1e-12) and self.z_after(z, vz, m - 1) < level:
            return None
        if self.z_after(z, vz, m - 1) < level or (n is not None and m > n):
            return None
        return m

    def _frac(self, z: float, vz: float, m: int, level: float) -> float:
        za, zb = self.z_after(z, vz, m - 1), self.z_after(z, vz, m)
        return m - 1 + (za - level) / (za - zb)

    def _clipped(self, z: float, vz: float, n: int | None, cap: float | None):
        """The ballistic segment of ``n`` air ticks (None: unbounded) from
        (z, vz) under ``cap`` (the feet's highest point under a roof; None:
        open sky): on the tick the feet would pass the cap they stop there
        with no vertical speed, and the arc goes on from there (a roof stops
        the rise, docs/RE_MOVEMENT.md).  Returns the segment's free rest as
        (z, vz, the air ticks before it, its air ticks)."""
        if cap is None or vz <= 0.0 or self._seg_max(z, vz, 400 if n is None else n) <= cap:
            return z, vz, 0, n
        a, b = -self.dt * self.gdt / 2, self.dt * (vz - self.gdt / 2)
        if a == 0:                                  # no gravity: a straight line
            m = math.floor((cap - z) / b) + 1
        else:                                       # past the lower root of z(m) = cap
            m = math.floor((-b + math.sqrt(max(b * b - 4 * a * (z - cap), 0.0))) / (2 * a)) + 1
        m = max(m, 1)
        while m > 1 and self.z_after(z, vz, m - 1) > cap:
            m -= 1
        while self.z_after(z, vz, m) <= cap:
            m += 1
        return cap, 0.0, m, None if n is None else n - m

    def arc(self, kit: Kit, flap_ticks, level: float, cap: float | None = None) -> Arc:
        """A jump with flaps pressed on ``flap_ticks`` (ticks after the jump
        tick, >= 2 and >= 2 apart, assumed) crossing ``level`` (feet above
        the takeoff), under a roof that holds the feet at or under ``cap``
        (None: open sky; the rise stops there: :meth:`_clipped`).  A gap's
        far edge may be crossed at the last descending crossing: over the
        gap the body may dip below the level and flap back above it.  A flap
        with the feet far below the level (or below -30 m) is moot and ends
        the schedule."""
        z, vz, tick, mair, apex, gauge, cross, done = 0.0, kit.v0, 0, 0, 0.0, 1.0, None, []
        for t in flap_ticks:
            if len(done) >= kit.flaps:
                break
            zs, vs, k, n = self._clipped(z, vz, t - tick - 1, cap)
            zn = self.z_after(zs, vs, n)
            if zn < min(level - RECOVER, -30.0):
                break
            m = self._seg_cross(zs, vs, level, n)
            if m is not None:
                cross = mair + k + self._frac(zs, vs, m, level)
            apex = max(apex, self._seg_max(zs, vs, n), zn)
            f = self.flap(kit, zn, vs - n * self.gdt, gauge)
            if f is None:
                break
            vz, gauge, empty = f
            z, tick, mair = zn, t, mair + k + n
            done.append(t)
            if empty:
                break
        zs, vs, k, _ = self._clipped(z, vz, None, cap)
        m = self._seg_cross(zs, vs, level, None)
        if m is not None:
            cross = mair + k + self._frac(zs, vs, m, level)
        return Arc(cross, max(apex, self._seg_max(zs, vs, 400)), tuple(done))

    def feet(self, kit: Kit, flap_ticks, cap: float | None, n: int) -> list[float]:
        """The feet's height above the takeoff after each of the first ``n``
        air ticks of :meth:`arc`'s jump (a flap's tick, frozen, is no air
        tick), under a roof capping them at ``cap`` (the rise stops there)."""
        z, vz, gauge, out = 0.0, kit.v0, 1.0, []
        flaps, used, k = set(sorted(flap_ticks)[: kit.flaps]), 0, 0
        while len(out) < n and k < 8000:
            k += 1
            if k in flaps and used < kit.flaps and gauge > 0.0:
                f = self.flap(kit, z, vz, gauge)
                if f is not None:
                    vz, gauge, empty = f
                    used += 1
                    gauge = 0.0 if empty else gauge
                    continue
            vz -= self.gdt
            z += self.dt * vz
            if cap is not None and z > cap and vz > 0.0:
                z, vz = cap, 0.0
            out.append(z)
        return out

    def horizon(self, kit: Kit) -> int:
        """Ticks within which every useful flap falls: the jump's airtime
        plus each flap's, generously."""
        v0f = self.m.flap_scale * math.sqrt(2.0 * self.g * kit.h)
        up = (2 * kit.v0 + 2.5 * kit.flaps * v0f) / max(self.gdt, 1e-6)
        return int(min(up, 4000)) + 40

    def best(self, kit: Kit, level: float, cap: float | None = None, objective: str = "air",
             beam: int = 100) -> tuple[float | None, tuple, Arc]:
        """The frame-perfect flap ticks for ``kit`` landing at ``level``
        (feet above the takeoff): the most air ticks to the level's last
        descending crossing (``objective`` "air": the horizontal travel is
        monotone in them, from a run or standing alike) or the highest
        apex ("apex"), under a roof that holds the feet at or under ``cap``
        (:meth:`arc`).
        Exhaustive for up to 2 flaps; for more, a beam over flap prefixes,
        then moves of every flap within +/-2 ticks together (up to 6
        flaps) and of each flap alone, until none improves.  Returns
        (value, ticks, arc); the value is None when nothing reaches the
        level."""
        def val(a: Arc):
            return a.apex if objective == "apex" else a.cross

        def better(a, b):
            return a is not None and (b is None or a > b + 1e-12)

        a0 = self.arc(kit, (), level, cap)
        best = (val(a0), (), a0)
        if kit.flaps == 0:
            return best
        horizon = self.horizon(kit)
        if kit.flaps <= 2:
            for t1 in range(FLAP_MIN_PERIOD, horizon):
                a = self.arc(kit, (t1,), level, cap)
                if better(val(a), best[0]):
                    best = (val(a), (t1,), a)
                if kit.flaps == 2 and len(a.ticks) == 1:
                    for t2 in range(t1 + FLAP_MIN_PERIOD, horizon):
                        a = self.arc(kit, (t1, t2), level, cap)
                        if len(a.ticks) < 2:
                            break
                        if better(val(a), best[0]):
                            best = (val(a), (t1, t2), a)
            return best
        layer = [()]
        for _ in range(kit.flaps):
            cand = []
            for pre in layer:
                last = pre[-1] if pre else 0
                for t in range(last + FLAP_MIN_PERIOD, horizon):
                    a = self.arc(kit, pre + (t,), level, cap)
                    if len(a.ticks) <= len(pre):       # moot from here on
                        break
                    v = val(a)
                    if v is not None:
                        cand.append((v, a.ticks))
            if not cand:
                break
            cand.sort(key=lambda c: -c[0])
            layer = [c[1] for c in cand[:beam]]
            if better(cand[0][0], best[0]):
                best = (cand[0][0], cand[0][1], self.arc(kit, cand[0][1], level, cap))
        return self._refine(kit, level, val, best, cap)

    def _refine(self, kit, level, val, best, cap=None):
        """Local moves on a tick schedule until none improves it: every
        flap within +/-2 ticks at once (up to 6 flaps), then each alone
        within +/-6."""
        v, s, a = best
        if not s:
            return best

        def ok(t):
            return t[0] >= FLAP_MIN_PERIOD and all(t[j + 1] - t[j] >= FLAP_MIN_PERIOD for j in range(len(t) - 1))

        moves = []
        if len(s) <= 6:
            moves.append([d for d in itertools.product(range(-2, 3), repeat=len(s)) if any(d)])
        moves.append([tuple(dd if j == i else 0 for j in range(len(s)))
                      for i in range(len(s)) for dd in (-6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6)])
        improved = True
        while improved:
            improved = False
            for group in moves:
                for d in group:
                    t = tuple(x + y for x, y in zip(s, d))
                    if not ok(t):
                        continue
                    na = self.arc(kit, t, level, cap)
                    nv = val(na)
                    if nv is not None and (v is None or nv > v + 1e-12):
                        v, s, a, improved = nv, na.ticks, na, True
                if improved:
                    break
        return v, s, a

    def polish(self, kit: Kit, level: float, ticks, cap: float | None = None,
               objective: str = "air") -> tuple[float | None, tuple, Arc]:
        """A local optimum of the flap ticks from ``ticks`` (a near
        movement's best: a seeded :class:`Envelope`, Step R1.14b), as
        :meth:`best` returns it: each flap alone within +/-6 ticks, then
        every flap +/-1 together (up to 8 flaps), until none improves, in
        steps of the game's own tick (1/30 s) first, then of one tick.  A reach it gives is flyable (any schedule is), never
        above the optimum."""
        def val(a: Arc):
            return a.apex if objective == "apex" else a.cross

        def ok(t):
            return t[0] >= FLAP_MIN_PERIOD and all(t[j + 1] - t[j] >= FLAP_MIN_PERIOD for j in range(len(t) - 1))

        a0 = self.arc(kit, (), level, cap)
        best = (val(a0), (), a0)
        t = list(ticks)[: kit.flaps]
        while t and len(t) < kit.flaps:
            t.append(t[-1] + max(FLAP_MIN_PERIOD, t[-1] - t[-2] if len(t) > 1 else 20))
        if not t:
            return best
        for j in range(len(t)):
            t[j] = max(t[j], FLAP_MIN_PERIOD if j == 0 else t[j - 1] + FLAP_MIN_PERIOD)
        a = self.arc(kit, tuple(t), level, cap)
        v, s, n = val(a), tuple(t), len(t)
        unit = max(1, round(self.m.fps / FPS))       # a move of ticks at the game's own rate, then single ticks
        for k in sorted({unit, 1}, reverse=True):
            groups = [[tuple(dd * k if j == i else 0 for j in range(n)) for i in range(n)
                       for dd in (-6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6)],
                      [tuple(x * k for x in d) for d in itertools.product((-1, 0, 1), repeat=n) if any(d)]
                      if n <= 8 else []]
            improved = True
            while improved:
                improved = False
                for group in groups:
                    for d in group:
                        tt = tuple(x + y for x, y in zip(s, d))
                        if not ok(tt):
                            continue
                        na = self.arc(kit, tt, level, cap)
                        nv = val(na)
                        if nv is not None and (v is None or nv > v + 1e-12):
                            v, s, a, improved = nv, tt, na, True
                            break
                    if improved:
                        break
        if v is not None and (best[0] is None or v > best[0] + 1e-12):
            best = (v, a.ticks, a)
        return best

    # ---- ground moves and falls
    def run_up_m(self) -> float:
        """Straight ground before a takeoff at full run speed: the ramp
        from rest [verified xemu s6 at 7 m/s; the per-tick gain at other
        speeds and frame rates inferred]."""
        v, d, dv = 0.0, 0.0, RAMP_DV * FPS / self.m.fps
        while v < self.m.run_speed - 1e-9:
            v = min(v + dv, self.m.run_speed)
            d += v * self.dt
        return d

    def walk_off_carry(self, drop: float, slope: float = 0.0) -> float:
        """Horizontal carry falling ``drop`` m after running off an edge (no
        jump: air control 9 c, the entity's before its first jump [verified
        xemu s6 §2]; a walk-off flap uses a stale ceiling, calib §6), off a
        lip that falls ``slope`` m a metre along the run (AZ-365): the body
        leaves at the run speed along the slope, so with its downward part
        as its first fall speed and only the rest ahead [verified L3, Step
        X.16: 17 of 28 ledges leave at 0.7-2.9 m/s down]; a lip that rises
        counts as level."""
        k = 1.0 / math.hypot(1.0, max(slope, 0.0))
        vz = -self.m.run_speed * max(slope, 0.0) * k
        m = self._seg_cross(0.0, vz, -drop, None)
        if m is None:
            return math.inf
        return self.travel(self._frac(0.0, vz, m, -drop), self.m.run_speed * k,
                           f32(AC_PLAIN * self.m.air_control_scale))

    def fall_hp(self, drop: float) -> int:
        """HP a landing ``drop`` m below the last ground costs (from rest)."""
        if math.sqrt(2.0 * self.g * max(drop, 0.0)) <= FALL_MIN_V:
            return 0
        return max((hp for d, hp in FALL_STEPS if drop >= d), default=0)


# --------------------------------------------------------------------------- the envelope
class Envelope:
    """The reach of :class:`Movement` ``m``: per air rank (and, with
    ``flaps``, a cap on the flaps it uses: 0 the jump alone), the
    frame-perfect horizontal travel to a landing ``dh`` above the takeoff
    (body centre from the takeoff point to where the feet last descend
    through ``dh``), from a run or from standing, under an optional
    ceiling (the lowest roof over the flight, m above the takeoff: the
    body, :data:`BODY_HEIGHT` tall, stays under it), and the highest rise.

    Each kit's best flap timing is searched once per level of a grid
    (:meth:`levels`); at any other ``dh`` the travel is the best of the
    neighbouring levels' schedules flown to ``dh`` (each value is
    witnessed by a schedule).  Under a ceiling the arcs are clipped
    (:meth:`Physics.arc`: a roof stops the rise), and where it clips the
    best of them the flap timing is searched for that ceiling.  An
    ``exact`` envelope also searches it for each ``dh`` itself (slower; the
    neighbours' schedules can land a little short of that):
    :func:`~.movement.slider_ranges` confirms a seeded failure with one
    (AZ-367)."""

    DROP = 20.0          # the grid's lowest level, m below the takeoff

    def __init__(self, m: Movement = VANILLA, beam: int = 100, seed: Envelope | None = None, exact: bool = False):
        self.m = m
        self.exact = exact
        self.p = Physics(m)
        self.beam = beam     # the flap search's beam (a narrower one is faster and never overstates)
        # seed: another movement's envelope whose best flap ticks, rescaled, start a local search (Physics.polish)
        # instead of the beam: much faster, and never above the full search (Step R1.14b)
        self.seed = seed if seed is not None and seed.m != m else None
        self._sched: dict = {}
        self._cache: dict = {}
        self._levels: dict = {}

    def _from_seed(self, kit: Kit, level: float, ticks, cap: float | None = None, objective: str = "air"):
        """:meth:`Physics.polish` from the seed's ``ticks`` rescaled by the two kits' flap cycles in ticks."""
        sk = self.seed.kits[kit.rank]

        def cycle(p: Physics, k: Kit) -> float:
            return (k.v0 + p.m.flap_scale * math.sqrt(2.0 * p.g * k.h)) / max(p.gdt, 1e-6)
        r = cycle(self.p, kit) / cycle(self.seed.p, sk)
        ticks = list(ticks)
        starts = {tuple(max(FLAP_MIN_PERIOD, round(t * r)) for t in ticks), tuple(ticks)}
        if ticks:      # the first flap rescaled, the rest as far after it as in the seed
            starts.add(tuple(t - ticks[0] + max(FLAP_MIN_PERIOD, round(ticks[0] * r)) for t in ticks))
        best = None
        for s in sorted(starts):
            v, s, a = self.p.polish(kit, level, s, cap, objective)
            if best is None or (v is not None and (best[0] is None or v > best[0] + 1e-12)):
                best = (v, s, a)
        return best

    @property
    def kits(self) -> tuple[Kit, ...]:
        return self.p.kits

    def kit(self, rank: int, flaps: int | None = None) -> Kit:
        """Rank ``rank``'s kit, its flaps capped at ``flaps`` (None: all)."""
        k = self.kits[rank]
        return k if flaps is None or flaps >= k.flaps else replace(k, flaps=max(flaps, 0))

    @property
    def rises(self) -> tuple[float, ...]:
        """Per rank, the highest apex of the feet above the takeoff."""
        return tuple(self.rise(k.rank) for k in self.kits)

    def rise(self, rank: int, ceiling: float | None = None, flaps: int | None = None) -> float:
        """The highest apex of the feet above the takeoff (under a ceiling)."""
        key = ("rise", rank, flaps)
        if key not in self._cache:
            kit = self.kit(rank, flaps)
            if self.seed is not None:
                self.seed.rise(rank, flaps=flaps)
                v, s, _ = self._from_seed(kit, -60.0, self.seed._cache[("rise_ticks", rank, flaps)], objective="apex")
            else:
                v, s, _ = self.p.best(kit, -60.0, objective="apex", beam=self.beam)
            self._cache[key], self._cache[("rise_ticks", rank, flaps)] = v, s
        r = self._cache[key]
        return r if ceiling is None else min(r, ceiling - BODY_HEIGHT)

    def levels(self, rank: int, flaps: int | None = None) -> tuple[float, ...]:
        """The grid: just under the rise, every 0.25 m down to the
        takeoff, then 0.5, 1, 2 and every 2 m to -DROP."""
        key = (rank, flaps)
        if key not in self._levels:
            top = self.rise(rank, flaps=flaps)
            up = [round(q * 0.25, 2) for q in range(int(top * 4 - 1e-9), -1, -1)]
            down = [-0.5, -1.0] + [-float(d) for d in range(2, 7)] + [-float(d) for d in range(8, int(self.DROP) + 1, 2)]
            self._levels[key] = tuple([top - 0.02] + [u for u in up if u < top - 0.02] + down)
        return self._levels[key]

    def _schedule_at(self, rank: int, flaps: int | None, i: int) -> tuple[int, ...]:
        """The best flap ticks at grid level ``i`` (searched once)."""
        key = (rank, flaps, i)
        if key not in self._sched:
            kit, level = self.kit(rank, flaps), self.levels(rank, flaps)[i]
            s = None
            if self.seed is not None:
                s = self._from_seed(kit, level, self.seed.schedule(rank, level, flaps=flaps))[1]
                if kit.flaps and self.p.arc(kit, s, level).cross is None:
                    s = None    # above the seed's own rise it has no schedule to start from (Step X.11)
            self._sched[key] = s if s is not None else self.p.best(kit, level, beam=self.beam)[1]
        return self._sched[key]

    def airtime(self, rank: int, dh: float, ceiling: float | None = None, flaps: int | None = None):
        """(air ticks to the last descending crossing of ``dh``, the flap
        ticks, the apex); air ticks None when nothing reaches ``dh``."""
        key = (rank, flaps, round(dh, 4), None if ceiling is None else round(ceiling, 3))
        if key in self._cache:
            return self._cache[key]
        # the feet stop under the roof (the takeoff stood the body there, so it is no lower than the body)
        kit, cap = self.kit(rank, flaps), None if ceiling is None else max(ceiling - BODY_HEIGHT, 0.0)
        grid = self.levels(rank, flaps)
        i = next((i for i, lv in enumerate(grid) if lv <= dh + 1e-9), len(grid) - 1)
        best = (None, (), None)
        for k in range(max(i - 1, 0), min(i + 2, len(grid))):
            s = self._schedule_at(rank, flaps, k)
            st = self.p.arc(kit, s, dh, cap)
            if st.cross is not None and (best[0] is None or st.cross > best[0] + 1e-12):
                best = (st.cross, s, st.apex)
        # the roof clipped it, or an exact envelope: the flap timing searched for dh itself
        if kit.flaps and (self.exact or (cap is not None and (best[0] is None or best[2] >= cap - 1e-9))):
            v = None
            if self.seed is not None:
                v, s, st = self._from_seed(kit, dh, self.seed.schedule(rank, dh, ceiling, flaps), cap)
            if v is None:
                v, s, st = self.p.best(kit, dh, cap=cap, beam=self.beam)
            if v is not None and (best[0] is None or v > best[0] + 1e-12):
                best = (v, s, st.apex)
        self._cache[key] = best
        return best

    def travel(self, rank: int, dh: float, *, run: bool = True, ceiling: float | None = None,
               flaps: int | None = None) -> float | None:
        """The frame-perfect horizontal travel (m) to a landing ``dh`` m
        above the takeoff, or None when the kit can't reach it."""
        air = self.airtime(rank, dh, ceiling, flaps)[0]
        if air is None:
            return None
        return self.p.travel(air, self.m.run_speed if run else 0.0, self.kits[rank].air_control)

    def travel_plain(self, rank: int, dh: float, *, run: bool = True, ceiling: float | None = None) -> float | None:
        """The travel of the rank's jump alone (no flap), as :meth:`travel`."""
        return self.travel(rank, dh, run=run, ceiling=ceiling, flaps=0)

    def schedule(self, rank: int, dh: float, ceiling: float | None = None, flaps: int | None = None) -> tuple[int, ...]:
        """The flap ticks (after the jump tick) of :meth:`travel`'s flight."""
        return self.airtime(rank, dh, ceiling, flaps)[1]


@functools.lru_cache(maxsize=64)
def envelope(m: Movement = VANILLA, beam: int = 100, seeded: bool = False, exact: bool = False) -> Envelope:
    """The (cached) :class:`Envelope` of ``m``; ``seeded``: its flap ticks
    searched locally from vanilla's (:class:`Envelope`'s ``seed``);
    ``exact``: searched for each landing itself too."""
    return Envelope(m, beam, envelope(VANILLA, beam) if seeded else None, exact)


# --------------------------------------------------------------------------- tiers and certificates
class Margin(Protocol):
    """A difficulty tier's margins over the envelope (``draft/tiers.toml``)."""
    reach: float            # the share of the distance perfect flaps add to the jump that the tier counts
    takeoff_window: int     # ticks of jump-press window before the edge: a running takeoff loses that much run
    stick_deg: float        # off-axis stick error: the flight's cosine
    clearance: float        # feet above the far lip, m: the travel is taken at dh + clearance
    landing_margin: float   # body centre past the far edge, m
    max_drop: float         # the longest drop counted, m
    lift_allowance: float   # how far a plain ledge's lip may stand above the apex for the lip lift, m


def tier_gap(env: Envelope, margin: Margin, rank: int, dh: float, run: bool = True,
             ceiling: float | None = None, flaps: int | None = None) -> float | None:
    """The widest edge-to-edge gap ``margin``'s tier counts for air rank
    ``rank`` (its flaps capped at ``flaps``) to a landing ``dh`` (None:
    none).  At dh + clearance: the rank's jump alone, plus ``reach`` of
    what its perfect flaps add (none when the jump alone can't reach), less the run a press up to
    ``takeoff_window`` ticks early loses, times the stick error's cosine,
    less the landing margin.  Frame-perfect (reach 1, no window, stick,
    clearance or margin) is the envelope itself."""
    if dh < -margin.max_drop:
        return None
    lv = dh + margin.clearance
    t = env.travel(rank, lv, run=run, ceiling=ceiling, flaps=flaps)
    if t is None:
        return None
    t0 = env.travel_plain(rank, lv, run=run, ceiling=ceiling) or 0.0
    loss = margin.takeoff_window * env.m.run_speed * env.p.dt if run else 0.0
    return math.cos(math.radians(margin.stick_deg)) * (t0 + margin.reach * (t - t0) - loss) - margin.landing_margin


@dataclass(frozen=True)
class Certificate:
    """What one derived flight physically needs (D167, D168): the air rank
    it flies with, the edge-to-edge ``gap`` it covers (a walk-off: the run
    off the edge to the landing), the landing ``dh`` above the takeoff (a
    drop below zero: its fall), a running takeoff or a standing one, the
    takeoff floor's ``runup`` before its edge on the track, its
    ``headroom`` (the roof the flight passes under, m above the takeoff,
    such that the witness arc's apex plus the body fits under it; None:
    open sky), whether it is a walk-off (no jump) or uses the lip lift,
    a cap on its flaps (the jump alone, or fewer than the rank has), and
    the ``rim`` step-up it lands by (``dh`` is then under the far floor's
    top by that much: the body meets a sloped rim and is lifted on), and a
    walk-off's lip ``slope`` (m it falls a metre along the run at the
    takeoff floor's edge: the body leaves with that part of its run speed
    falling, AZ-365), and the least room over the head under the roof over
    the arc's first and last :data:`ROOF_END` (``room_start``,
    ``room_end``: the headroom's profile, AZ-387; None: open sky there).
    No coordinate: every number is relative to the takeoff."""
    rank: int
    gap: float
    dh: float
    run: bool = True
    runup: float = 0.0
    headroom: float | None = None
    walk_off: bool = False
    lip: bool = False
    flaps: int | None = None     # a cap on the flaps the flight uses (0: the jump alone; None: the rank's own)
    rim: float = 0.0             # the rim step-up it lands by: the far floor's top stands this far above ``dh``
    slope: float = 0.0           # a walk-off's lip: m it falls a metre along the run at the edge (AZ-365)
    room_start: float | None = None   # the least room over the head under the roof over the arc's first and last
    room_end: float | None = None     # ROOF_END, m (None: open sky there; AZ-387)

    def as_dict(self) -> dict:
        out = {"rank": self.rank, "gap": round(self.gap, 2), "dh": round(self.dh, 2), "run": self.run,
               "runup": round(self.runup, 2)}
        if self.headroom is not None:
            out["headroom"] = round(self.headroom, 2)
        if self.walk_off:
            out["walk_off"] = True
        if self.lip:
            out["lip"] = True
        if self.flaps is not None:
            out["flaps"] = self.flaps
        if self.rim:
            out["rim"] = round(self.rim, 2)
        if self.slope:
            out["slope"] = round(self.slope, 2)
        if self.room_start is not None:
            out["room_start"] = round(self.room_start, 2)
        if self.room_end is not None:
            out["room_end"] = round(self.room_end, 2)
        return out

    @classmethod
    def from_dict(cls, d: Mapping) -> Certificate:
        return cls(int(d["rank"]), float(d["gap"]), float(d["dh"]), bool(d.get("run", True)),
                   float(d.get("runup", 0.0)), None if d.get("headroom") is None else float(d["headroom"]),
                   bool(d.get("walk_off", False)), bool(d.get("lip", False)),
                   None if d.get("flaps") is None else int(d["flaps"]), float(d.get("rim", 0.0)),
                   float(d.get("slope", 0.0)), None if d.get("room_start") is None else float(d["room_start"]),
                   None if d.get("room_end") is None else float(d["room_end"]))


ROOF_END = 0.25          # a flight's ends, its arc's first and last quarter, where the roof's room is kept apart (AZ-387)
WALKOFF_SLACK = -0.95    # a walk-off reaches its carry + this past the takeoff floor's end (s0, draft/flights.py)
                         # [verified L3, Step X.16, AZ-357: on 11 clean ledges of 6 levels with a level lip (the body
                         # leaves at under 0.6 m/s down) the body centre is 0.28-0.94 m short of the carry at every
                         # drop to 10 m: it leaves 0.1-0.5 m before s0 and its arc is shorter. A sloped lip carries
                         # less again: AZ-365]


@dataclass(frozen=True)
class Margins:
    """A tier's margins over the envelope (a :class:`Margin`)."""
    reach: float
    takeoff_window: int
    stick_deg: float
    clearance: float
    landing_margin: float
    max_drop: float
    lift_allowance: float


TIERS_TOML = Path(__file__).resolve().parent / "draft" / "tiers.toml"   # draft/envelope.py checks it
PLAYER_TIERS = ("safe", "standard", "hard", "frame_perfect")


@functools.cache
def tier_margins() -> dict[str, Margins]:
    """The player tiers' margins, read from ``draft/tiers.toml`` as data
    (a build re-checks its flights with them; it imports no draft tool)."""
    doc = tomllib.loads(TIERS_TOML.read_text(encoding="utf-8"))
    return {t: Margins(**{f.name: doc[t][f.name] for f in fields(Margins)}) for t in PLAYER_TIERS}


# The zones' free movement (draft/reach.py: a zone is the regions free movement joins both ways), which every node
# of every level assumes: Step R1.2's safe margins, fixed, on their level grid and walk-off table (draft/envelope.py's
# ZONE reads these), a plain jump only (no item), and a plain ledge's lip lift up to the one measured lip (a higher
# lip is probe-needed: draft/flights.py).
FREE = Margins(reach=0.65, takeoff_window=6, stick_deg=10.0, clearance=0.15, landing_margin=0.5, max_drop=15.0,
               lift_allowance=0.4271)
FREE_LEVELS = (-16.0, -14.0, -12.0, -10.0, -8.0, -6.0, -5.0, -4.0, -3.0, -2.0, -1.0, -0.5, 0.0, 0.25, 0.5, 0.75,
               1.0, 1.25, 1.5, 1.75, 2.0, 2.2, 2.3)      # a flight reads the first level at or above its dh
FREE_CARRY_DROPS = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 16.0)   # the walk-off carry table's drops, m
LIP_M = 1.2578        # [verified xemu s6 §5] the one measured ledge's lip above its floor
PICK_STAND = 1.5      # [inferred] a pickup up to 1.5 m above the floor is touched standing (draft/gates.py)


@functools.cache
def free_certs() -> tuple[Certificate, ...]:
    """The zones' free movement at vanilla as certificates (Step R1.14b):
    the widest plain gap at each of :data:`FREE_LEVELS`, running and
    standing, each walk-off of the carry table and the highest lip, so a
    movement that keeps them all at a tier keeps every zone whole there."""
    env, out = envelope(VANILLA), []
    for run in (True, False):
        for lv in FREE_LEVELS:
            g = tier_gap(env, FREE, 0, lv, run)
            if g is not None and g > 0:
                out.append(Certificate(0, g, lv, run))
    out += [Certificate(0, env.p.walk_off_carry(d) + WALKOFF_SLACK, -d, walk_off=True)
            for d in FREE_CARRY_DROPS]
    out.append(Certificate(0, 0.0, LIP_M + 0.01, lip=True))
    return tuple(out)


def holds(cert: Certificate, env: Envelope, margin: Margin) -> bool:
    """Does the tier ``margin`` still count ``cert``'s flight under ``env``'s
    movement?  The same rule for weaker and stronger movement (D168): the
    flight's gap within the tier's share of the envelope under the flight's
    headroom (a taller arc meets the roof and falls from there: the roof
    stops the rise, AZ-364, so it counts with the airtime it keeps); a
    walk-off within the run-off carry; a drop within the tier's longest;
    the lip lift's lip within the tier's allowance above the new apex."""
    if cert.dh < -margin.max_drop:
        return False
    if cert.walk_off:
        return cert.gap <= env.p.walk_off_carry(max(-cert.dh, 0.0), cert.slope) + WALKOFF_SLACK
    if cert.lip:
        return cert.dh - env.rise(cert.rank, cert.headroom, cert.flaps) <= margin.lift_allowance + 1e-9
    g = tier_gap(env, margin, cert.rank, cert.dh, cert.run, cert.headroom, cert.flaps)
    if g is None or cert.gap > g + 1e-9:
        return False
    head = ends_headroom(cert, env, margin)
    if cert.headroom is None or head >= cert.headroom - 1e-9:
        return True
    g = tier_gap(env, margin, cert.rank, cert.dh, cert.run, head, cert.flaps)
    return g is not None and cert.gap <= g + 1e-9


def ends_headroom(cert: Certificate, env: Envelope, margin: Margin) -> float:
    """The headroom ``cert``'s flight keeps under ``env``'s movement at
    ``margin``'s tier once its roof's profile is read (AZ-387, D719): its
    one headroom is the least room over the whole flight, so a roof that
    dips toward an end (where vanilla's arc is low and the room over its
    head is all there is) is kept apart (``room_start``, ``room_end``).
    Tick for tick against vanilla's witness arc (the jump alone and with
    its flaps, to dh + the tier's clearance, as :func:`tier_gap` flies
    them): the arc rising more than ``room_start`` above vanilla's over
    vanilla's first :data:`ROOF_END` meets the roof there, which stops the
    rise, so the flight keeps that lower roof as its headroom; and one
    more than ``room_end`` above vanilla's over its last :data:`ROOF_END`
    meets the roof over the landing, which holds it under it, so the
    flight keeps that roof as its headroom too (clipped by the lowest roof
    near its ends, D719).  Else the certificate's headroom (vanilla
    movement keeps it; inf under open sky)."""
    head = cert.headroom
    if head is None:
        return math.inf
    if (cert.room_start is None and cert.room_end is None) or cert.walk_off or cert.lip:
        return head
    base = envelope(VANILLA, env.beam, exact=True) if env.exact else envelope(VANILLA, env.beam)
    lv = cert.dh + margin.clearance

    def arcs(ceiling: float):
        cap, out = max(ceiling - BODY_HEIGHT, 0.0), []
        for flaps in {0, cert.flaps}:
            air_v, sched_v, _ = base.airtime(cert.rank, lv, cert.headroom, flaps)
            if air_v is None:
                continue
            n = math.ceil(air_v)
            sched_m = env.schedule(cert.rank, lv, ceiling, flaps)
            zv = base.p.feet(base.kit(cert.rank, flaps), sched_v, max(cert.headroom - BODY_HEIGHT, 0.0), n)
            zm = env.p.feet(env.kit(cert.rank, flaps), sched_m, cap, n)
            out.append((air_v, zv, zm))
        return out
    for room, near in ((cert.room_start, lambda k, air: k <= ROOF_END * air),
                       (cert.room_end, lambda k, air: k >= (1.0 - ROOF_END) * air)):
        if room is None:
            continue
        for air_v, zv, zm in arcs(head):
            for k, (v, m) in enumerate(zip(zv, zm), 1):
                if near(k, air_v) and m > v + room + 1e-6:
                    head = min(head, v + room + BODY_HEIGHT)
    return head


TOLERANCE = 0.005    # m: two searches' gaps or rises this close count as equal (keeps' comparison with vanilla)


ROUNDING = 0.005     # m: a stored certificate's gap and dh are rounded to 0.01 m (Certificate.as_dict)


def read_as(cert: Certificate, base: Envelope, margin: Margin) -> Certificate | None:
    """``cert`` as the calculator reproduces the derive's verdict on it at
    vanilla (``base``): itself where it :func:`holds`, or within its
    :data:`ROUNDING`; as a lip lift where its landing is out of the plain
    arc's reach but within the tier's lift allowance (a probe-needed flight
    the derive rated by the lip lift, whose straight path met a solid: its
    certificate names no lip [inferred]); else None."""
    for c in (cert, replace(cert, gap=max(cert.gap - ROUNDING, 0.0), dh=cert.dh - ROUNDING)):
        if holds(c, base, margin):
            return c
        lip = replace(c, lip=True)
        if not (c.walk_off or c.lip) and c.dh >= -margin.max_drop and holds(lip, base, margin) and \
                tier_gap(base, margin, c.rank, c.dh, c.run, c.headroom, c.flaps) is None:
            return lip
    return None


def keeps(cert: Certificate, env: Envelope, margin: Margin) -> bool:
    """Does ``cert``'s flight stay in logic at ``margin``'s tier under
    ``env``'s movement (Step R1.14b)?  :func:`holds` of the certificate as
    vanilla reads it (:func:`read_as`); where vanilla doesn't reproduce the
    derive's verdict (its sweep, a probe class or a rounding knew more),
    only while ``env`` is no weaker than vanilla for that flight: its
    walk-off carry, rise and gap at least vanilla's within
    :data:`TOLERANCE` (the gap at the flight's dh, or under vanilla's rise
    when that is out of reach; both under the flight's headroom).  So
    vanilla movement keeps every certificate.  An ``exact`` ``env`` reads
    vanilla's exact envelope (like with like)."""
    base = envelope(VANILLA, env.beam, exact=True) if env.exact else envelope(VANILLA, env.beam)   # one cache key each
    read = read_as(cert, base, margin)
    if read is not None:
        return holds(read, env, margin)
    if cert.walk_off:
        drop = max(-cert.dh, 0.0)
        return env.p.walk_off_carry(drop, cert.slope) >= base.p.walk_off_carry(drop, cert.slope) - TOLERANCE
    r = cert.rank
    rise = base.rise(r, cert.headroom, cert.flaps)
    if env.rise(r, cert.headroom, cert.flaps) < rise - TOLERANCE:
        return False
    if cert.lip:
        return True
    lv = max(min(cert.dh, rise - margin.clearance - 0.05), -margin.max_drop)
    want = tier_gap(base, margin, r, lv, cert.run, cert.headroom, cert.flaps)
    got = tier_gap(env, margin, r, lv, cert.run, cert.headroom, cert.flaps)
    return want is None or (got is not None and got >= want - TOLERANCE)


def slack(cert: Certificate, env: Envelope, margin: Margin) -> float:
    """How much room ``cert``'s flight has at ``margin``'s tier under
    ``env`` (m; negative where :func:`holds` fails): the gap, walk-off,
    or lip it has to spare.  Orders certificates most fragile first."""
    if cert.walk_off:
        return env.p.walk_off_carry(max(-cert.dh, 0.0), cert.slope) + WALKOFF_SLACK - cert.gap
    if cert.lip:
        return margin.lift_allowance - cert.dh + env.rise(cert.rank, cert.headroom, cert.flaps)
    g = tier_gap(env, margin, cert.rank, cert.dh, cert.run, cert.headroom, cert.flaps)
    return -1.0 if g is None else g - cert.gap


def bisect_range(ok, v0: float, lo: float, hi: float, tol: float) -> tuple[tuple[float, float | None], ...]:
    """The interval around ``v0`` on which ``ok`` holds, assuming it is one
    (D168: each slider loses reach on one side, at most headroom on the
    other): each far end first (the corner: when it holds, the whole side
    does), else bisection to ``tol``.  Per side, (the last value that holds,
    the first that fails or None), as judged: unrounded, so ``ok`` asked
    again of either gives the same answer (a rounded end could fall back
    inside a measured range ending on a bisection point, AZ-368; only what
    is shown is rounded).  ``ok(v0)`` must hold (else ValueError)."""
    if not ok(v0):
        raise ValueError(f"{v0:g}: the base movement already breaks a certificate")
    out = []
    for far in (lo, hi):
        if ok(far):
            out.append((far, None))
            continue
        good, bad = v0, far
        while abs(bad - good) > tol:
            mid = (good + bad) / 2
            good, bad = (mid, bad) if ok(mid) else (good, mid)
        out.append((good, bad))
    return tuple(out)


__all__ = ["BODY_HEIGHT", "FREE", "Certificate", "Envelope", "Kit", "Margin", "Margins", "Movement", "Physics",
           "SLIDERS", "VANILLA", "bisect_range", "envelope", "f32", "free_certs", "holds", "keeps",
           "read_as", "slack", "tier_gap", "tier_margins"]
