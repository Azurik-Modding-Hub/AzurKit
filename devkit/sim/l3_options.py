"""The trick explorer's options (Step TD.3, D253; the trick-discovery plan §3.2): closed-loop moves the bandit draws
per state class wherever their runtime precondition holds (``l3_explore.Option``), each reacting to every tick's
row (its state, speed, the stored contact normal, the time in the state, flaps left), never to a site constant.
They come by spec in ``l3_explore.Limits.options`` (all of them by default; ``Limits(options=())`` is the
explorer without them).  From the dev sources only (the plan §4's blind protocol: nothing from the pilot's sites):

- :class:`Hoist` (``hoist``): from the ground, a run-up along a drawn heading, cut short when the body stops against
  a face (a full stick and under :data:`BLOCKED` m/s), then a jump with the stick held on, turned into the face the
  air contact reports (in the air against a face, that push alone), through the ledge hoist (state 0x100 from the
  air, 0x86920) to its end [X.35: 35 hoist starts, each from the air with the stick forward, ledges 0.4-2.15 m up;
  f6's section 81 has one from a standing jump and one from a run-up (this option's two kinds), and one from a slide
  off a slope with no jump, which it doesn't make];
- :class:`SlopeHop` (``slope_hop``): on the slope or slide state (3, 4), a jump (it goes along the face's normal and
  keeps the slide speed, 0x89060) steered uphill or across, a flap at a drawn tick while flaps are left and an LT+Y
  recast (the gauge refilled) at another, to the landing [``tricks.toml`` bskip method 2's slope-recast hops];
- :class:`SteepWalk` (``steep_walk``): on a face of 0.6 < nz < 0.8 (to 0.7071 the slope state 3/4, with no
  friction; then walkable with step-ups 0x8B1D0; all of it off the logic's floor rule, nz >= 0.8), the stick at a
  drawn magnitude at a drawn angle off the uphill direction the stored normal gives, re-aimed each tick [the plan
  §1's surface classes; no dev trace shows one yet: X.35's predates the stored normal];
- :class:`RollChain` (``roll_chain``): BLACK, then a press on a drawn roll tick 12-20 for each further roll (one
  every 19 ticks), and on a drawn share of firings Y held from the last roll's drawn tick into its end tick, the
  end-tick jump (in mid-air too: the fall speed replaced by v0, the flaps reset) [``tricks.toml`` rjump's mechanism
  and buffering, skips-a A1-A5 on the vanilla-flat spot: a roll is 21 rows of 0x100].

Not built: ``CatchCharge`` and ``Release`` wait for Step TD.4's climb-column miner (a climbable outside e6: the only
charge site measured is the pilot's), and ``AimedDescent`` for a landing target to aim at (TD.4b's exit goal); its
air-steering decay was measured at a pilot site (skips-e).  An option's plan is drawn from the explorer's ``rng``
only, so a seed gives the same strings.
"""

from __future__ import annotations

import math
import random

from devkit.sim.l3_explore import AIRBORNE, SECTORS, Option, flaps_left, speed

Y, BLACK, CAST, NONE = frozenset({"y"}), frozenset({"black"}), frozenset({"lt", "y"}), frozenset()
GROUND, SLOPE, SLIDE, ATTACK = 0, 3, 4, 0x100
BLOCKED = 1.5            # m/s: a full stick this slow on the ground is against a face
WALL_NZ = 0.6            # a stored normal this steep or steeper is a face, not a floor (no landing: 0x8C12F)
STEEP_NZ = (0.6, 0.8)
RUNS = (0, 0, 2, 4, 6, 8, 12, 16, 20, 24)   # [proposal] a hoist's run-up, ticks (0: a standing jump, X.35's)
ROLL_PERIOD, CHAIN_TICKS = 19, (12, 20)    # a chained roll starts every 19 ticks, from a press on roll ticks 12-20
ROLLS = (1, 1, 2, 2, 3, 4, 5)              # [proposal] rolls a firing chains (rjc5 A6's skip: 4)
JUMP_SHARE = 0.6                           # [proposal] firings that end in the end-tick jump
__all__ = ["Hoist", "SlopeHop", "SteepWalk", "RollChain", "uphill"]


def _sector(rng: random.Random) -> float:
    return (rng.randrange(SECTORS) + rng.uniform(-0.5, 0.5)) * 2 * math.pi / SECTORS - math.pi


def _normal(row):
    o = getattr(row, "obs", None)
    return None if o is None else getattr(o, "normal", None)


def _face(row) -> bool:
    """The stored normal is a face's (steeper than a floor), not a floor's."""
    n = _normal(row)
    return n is not None and abs(n[2]) < WALL_NZ and math.hypot(n[0], n[1]) > 0.5


def uphill(row) -> float | None:
    """The world heading against the stored normal's horizontal part (uphill on a slope; into a face the air
    contact reports), None with no normal or a flat one."""
    n = _normal(row)
    if n is None or math.hypot(n[0], n[1]) < 1e-3:
        return None
    return math.atan2(n[0], -n[1])        # heading a faces (-sin a, cos a) = -(nx, ny) / |n_xy|


class Hoist(Option):
    name, air, weight, most = "hoist", 90, 1.0, 200

    def applies(self, row) -> bool:
        return row.state == GROUND or (row.state in AIRBORNE and _face(row))

    def begin(self, row, rng: random.Random) -> dict:
        if row.state in AIRBORNE:            # already in the air against a face: push into it, no jump
            return {"h": uphill(row), "run": 0, "hold": 0, "jump": 0, "up": False}
        return {"h": _sector(rng), "run": rng.choice(RUNS), "hold": rng.randint(2, 6), "jump": None, "up": False}

    def act(self, p: dict, row, t: int):
        if p["jump"] is None:
            if t < p["run"] and not (t >= 4 and speed(row) < BLOCKED):
                return p["h"], 1.0, NONE
            p["jump"] = t
        k = t - p["jump"]
        if row.state == ATTACK:
            p["up"] = True
        elif p["up"] or (k > 2 and row.state not in AIRBORNE):
            return None                      # the hoist is over, or the jump landed without one
        if row.state in AIRBORNE and _face(row) and (h := uphill(row)) is not None:
            p["h"] = h                       # a face met in the air: push into it, toward its lip
        return p["h"], 1.0, Y if k < p["hold"] else NONE


class SlopeHop(Option):
    name, air, weight, most = "slope_hop", 150, 1.0, 150

    def applies(self, row) -> bool:
        return row.state in (SLOPE, SLIDE)

    def begin(self, row, rng: random.Random) -> dict:
        up = uphill(row)
        h = up + rng.gauss(0.0, 0.6) if up is not None and rng.random() < 0.7 else _sector(rng)
        o = getattr(row, "obs", None)
        armor = o is not None and (getattr(o, "flaps", None) or 0) > 0
        hold = rng.randint(1, 6)
        flap = hold + rng.randint(2, 28) if flaps_left(row) > 0 and rng.random() < 0.7 else None
        cast = hold + rng.randint(2, 36) if armor and rng.random() < 0.5 else None
        return {"h": h, "mag": rng.choice((0.7, 1.0)), "hold": hold, "flap": flap, "cast": cast}

    def act(self, p: dict, row, t: int):
        if t >= p["hold"] + 3 and row.state not in AIRBORNE:
            return None                      # landed (or never left the face)
        b = Y if t < p["hold"] else NONE
        if row.state in AIRBORNE:
            if p["flap"] is not None and p["flap"] <= t < p["flap"] + 2 and flaps_left(row) > 0:
                b = Y
            if p["cast"] is not None and t == p["cast"]:
                b = CAST
        return p["h"], p["mag"], b


class SteepWalk(Option):
    name, air, weight, most = "steep_walk", 60, 0.5, 64

    def applies(self, row) -> bool:
        n = _normal(row)
        return row.state in (GROUND, SLOPE) and n is not None and STEEP_NZ[0] < n[2] < STEEP_NZ[1]

    def begin(self, row, rng: random.Random) -> dict:
        return {"off": rng.uniform(-1.05, 1.05), "mag": rng.choice((0.35, 0.5, 0.7, 1.0)),
                "n": rng.randint(8, self.most), "h": uphill(row), "away": 0}

    def act(self, p: dict, row, t: int):
        if t >= p["n"] or row.state in AIRBORNE:
            return None
        n = _normal(row)
        if n is not None and STEEP_NZ[0] < n[2] < STEEP_NZ[1] and (h := uphill(row)) is not None:
            p["h"], p["away"] = h, 0
        elif row.state != ATTACK:            # a step-up (0x100) keeps the walk's heading
            p["away"] += 1
            if p["away"] > 6:
                return None
        return (None if p["h"] is None else p["h"] + p["off"]), p["mag"], NONE


class RollChain(Option):
    name, air, weight, most = "roll_chain", 300, 0.5, 5 * ROLL_PERIOD + 40

    def applies(self, row) -> bool:
        return row.state in (GROUND, SLOPE)

    def begin(self, row, rng: random.Random) -> dict:
        rolls = rng.choice(ROLLS)
        return {"h": _sector(rng), "rolls": rolls, "chain": rng.randint(*CHAIN_TICKS),
                "y": rng.randint(4, 20) if rng.random() < JUMP_SHARE else None, "end": None}

    def act(self, p: dict, row, t: int):
        if t == 0:
            return p["h"], 1.0, BLACK
        if p["end"] is None and row.state != ATTACK:
            p["end"] = t                     # the roll never started (t 1), or it is over: a tick more, then done
        if p["end"] is not None:
            return None if t == 1 or t > p["end"] else (p["h"], 1.0, NONE)
        i, r = divmod(t + 1 - p["chain"], ROLL_PERIOD)   # roll i's tick ``chain`` is tick i * 19 + chain - 1
        b = BLACK if r == 0 and 0 <= i < p["rolls"] - 1 else NONE   # a press on roll tick 12-20 chains the next
        last = (p["rolls"] - 1) * ROLL_PERIOD
        if p["y"] is not None and t >= last + p["y"] - 1:
            b = b | Y                        # held into the last roll's end tick: the end-tick jump
        return p["h"], 1.0, b
