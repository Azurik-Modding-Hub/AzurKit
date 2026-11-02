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
it (``draft/tiers.toml``).  Stdlib only; ``scripts/slider_tiers.py``
makes the movement sliders' tier table from it (D1066), so a plan runs
none of it.

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
  roll, swim   outside the tier table (movement.MODELLED); measured in
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
    best of them the flap timing is searched for that ceiling."""

    DROP = 20.0          # the grid's lowest level, m below the takeoff

    def __init__(self, m: Movement = VANILLA, beam: int = 100):
        self.m = m
        self.p = Physics(m)
        self.beam = beam     # the flap search's beam (a narrower one is faster and never overstates)
        self._sched: dict = {}
        self._cache: dict = {}
        self._levels: dict = {}

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
            self._cache[key] = self.p.best(self.kit(rank, flaps), -60.0, objective="apex", beam=self.beam)[0]
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
            self._sched[key] = self.p.best(self.kit(rank, flaps), self.levels(rank, flaps)[i], beam=self.beam)[1]
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
        # the roof clipped it: the flap timing searched for dh itself
        if kit.flaps and cap is not None and (best[0] is None or best[2] >= cap - 1e-9):
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


@functools.lru_cache(maxsize=64)
def envelope(m: Movement = VANILLA, beam: int = 100) -> Envelope:
    """The (cached) :class:`Envelope` of ``m``."""
    return Envelope(m, beam)


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


__all__ = ["BODY_HEIGHT", "FREE", "Envelope", "Kit", "Margin", "Margins", "Movement", "Physics", "SLIDERS", "VANILLA",
           "envelope", "f32", "tier_gap", "tier_margins"]
