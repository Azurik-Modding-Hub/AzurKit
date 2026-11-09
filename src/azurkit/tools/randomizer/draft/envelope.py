"""The movement difficulty tiers as margins over the physics envelope
(D108 Q256, D113, D144, D156, D167), and the contact laws the envelope
leaves to the reach model.

The laws of flight, the settings they take and the reach envelope they
give are :mod:`azurkit.tools.randomizer.physics` (Step R1.2b): any movement
settings, the frame-perfect travel of each air rank to a landing dh.  A
tier (``tiers.toml``) is a margin over it: at dh + ``clearance``,
the jump alone plus ``reach`` of what perfect flaps add, less the run a
press ``takeoff_window`` ticks early loses, times the cosine of the stick
error, less ``landing_margin``.  Frame-perfect counts all of it; safe
counts what vanilla's own route needs (D156).  Authoring only: the randomizer's planner and writer never
import this module.

Labels: [verified xemu s6] a capture holds it; [verified xemu calib] the
calibration sitting measured it (placed: after a RAM teleport or poke);
[verified L2] the game's own code under :mod:`azurik_mod.sim.l2`
computed it (:func:`l2_flight`); [verified static] code or config read;
[proposal] a policy number; [inferred].

Contact laws (``docs/RE_MOVEMENT.md`` § "Springboards, updrafts, flap
timing and the lip lift"):
  spring      a springboard S launches like a jump with h := S and air
              control 9 even with a shield (the physics' tick_arc).
  updraft     inside a pushZ volume, airborne: vz := vz + c (pushZ/0.9 -
              vz), c = 0.035404 per tick, and gravity does not act.
  lip lift    a plain ledge's lip a little above the apex mounts from a
              takeoff window that narrows as the deficit grows (s6 §5,
              calib §4: :func:`lip_lift_window`).
  falls       damage needs |vz| > 10 m/s and a drop (last ground z ->
              contact z) >= 6 / 8 / 17 m for 5 / 10 / 1000 HP.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
import struct
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from azurkit.tools.randomizer import physics
from azurkit.tools.randomizer.physics import FALL_MIN_V, FALL_STEPS, GRAVITY, f32

HERE = Path(__file__).resolve().parent
TIERS_TOML = HERE / "tiers.toml"
# This module as it was loaded (flights.py keys its kept envelope by the code a process runs)
SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# 1. Contact constants, with provenance
# --------------------------------------------------------------------------
V_RUN = physics.RUN_SPEED   # [verified xemu s6] runSpeed x stick 1 (7.00009 measured)
BODY_RADIUS = 0.5           # [verified config] collisionRadius
LAND_NORMAL_Z = 0.6         # [verified static 0x8C132] a landing contact needs nz > 0.6
STEP_NORMAL_Z = 0.8         # [verified static] walk calls the step-up 0x8B1D0 below 0.8
SWIM = {"target_mps": physics.SWIM_MPS, "blend_per_s": 0.1, "vertical_mps": physics.SWIM_VERTICAL_MPS,
        "m_in_3s_from_rest": 25.83}                     # [verified xemu s6 §3]
# Updrafts [verified xemu calib §3, placed; fit residual <= 1.9e-6 m/s for
# pushZ 10, 30 and 60]: terminal vz = pushZ / 0.9, time constant 1/c ticks.
PUSH_C = 0.035404
PUSH_TERM_DIV = 0.9
# The one ledge s6 measured (f6 S4): lip 1.2578 m above the floor, 0.2343 m
# above the plain apex; a running jump mounts it from 0.65 to 3.69 m before
# the blocked spot (13 ticks at 7 m/s), and fails from 4.39 m and from
# <= 0.42 m. Falling contacts mount at lip - feet <= 0.243 m and fail at
# >= 0.334 m (the movement-model investigator's reading of the 12 runs).
# The body rose to 1.7079 m during the lift. [verified xemu s6 §5; a plain
# jump only: the lift with an air shield's jump or a flap is [inferred]]
LEDGE_S6 = {"lip_m": physics.LIP_M, "above_plain_apex_m": 0.2343,
            "takeoff_window_m": (0.65, 3.69), "fails_from_m": 4.39, "fails_near_m": 0.42,
            "falling_contact_mount_max_m": 0.243, "falling_contact_fail_min_m": 0.334,
            "max_body_rise_with_lift_m": 1.7079}
# The lip-lift ceiling on the same ledge, the plain jump's height poked to
# vary lip - apex [verified xemu calib §4, placed]: (lip - apex m, first and
# last takeoff row that mounted). Rows were sampled 2 apart (every edge is
# +/-1 row); row r takes off 0.65 + (31 - r) x 7/30 m before the blocked spot
# (s6's table). It mounts at 0.4987 m and fails at 0.5232 m (odd rows; one
# ledge only). The window narrows as the deficit grows.
LIP_LIFT_ROWS = ((0.2343, 18, 31), (0.4271, 22, 28), (0.4745, 23, 27), (0.4987, 25, 27))
LIP_LIFT_FAILS_M = 0.5232


def lip_row_m(row: int) -> float:
    """How far before S4's blocked spot takeoff row ``row`` leaves the
    ground (s6 §5: row 31 at 0.65 m, one row per 7/30 m)."""
    return LEDGE_S6["takeoff_window_m"][0] + (31 - row) * V_RUN / 30


def push_tick(v: float, push: float) -> float:
    """One airborne tick's velocity along a push volume's axis: it tends
    to push / 0.9 with gravity off (an updraft's vz) [verified xemu calib
    §3, placed]."""
    return v + PUSH_C * (push / PUSH_TERM_DIV - v)


def fall_damage(drop: float, impact_vz: float | None = None) -> int:
    """HP a landing costs (impact_vz None: the free-fall speed from rest)."""
    if impact_vz is None:
        impact_vz = math.sqrt(2 * f32(GRAVITY) * max(drop, 0.0))
    if abs(impact_vz) <= FALL_MIN_V:
        return 0
    return max((hp for d, hp in FALL_STEPS if drop >= d), default=0)


# --------------------------------------------------------------------------
# 2. Tiers (tiers.toml): margins over the envelope
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Tier:
    name: str
    difficulty: int          # an edge's `difficulty` (1 safe .. 4 frame-perfect; 0 = R_phys only)
    reach: float             # the share of the distance perfect flaps add to the jump that the tier counts (0, 1]
    takeoff_window: int      # ticks of jump-press window before an edge: a running takeoff's lost run, the lip lift's rows
    stick_deg: float         # off-axis stick error: the flight's cosine, the landing room across the flight line
    clearance: float         # feet above the far lip and every hurdle, m
    landing_margin: float    # body centre past the far edge, m
    lift_allowance: float    # ledge lip above the rank's apex the lip lift may cover, m
    max_drop: float          # longest drop counted (fall damage <= 10 HP below 17 m)
    slippery: bool           # may a takeoff or landing be a slippery (0x8051) floor
    note: str


TIER_ORDER = ("safe", "standard", "hard", "frame_perfect", "phys")
DIFFICULTY = {"safe": 1, "standard": 2, "hard": 3, "frame_perfect": 4, "phys": 0}
_INT_FIELDS = ("difficulty", "takeoff_window")
_FLOAT_FIELDS = ("reach", "stick_deg", "clearance", "landing_margin", "lift_allowance", "max_drop")


def load_tiers(path: Path = TIERS_TOML) -> tuple[tuple[Tier, ...], Tier]:
    """The player tiers (safe .. frame_perfect) and R_phys's ``phys`` row.
    Fails on a missing, extra or misordered tier or field, a value of the
    wrong type, a number that is not finite, a reach outside (0, 1], a
    negative tick count or stick error, a difficulty other than the tier's
    (``DIFFICULTY``), or a player tier's lift allowance above the largest
    deficit measured to mount (no takeoff window is known above it)."""
    doc = tomllib.loads(path.read_text(encoding="utf-8"))
    if tuple(doc) != TIER_ORDER:
        raise ValueError(f"{path.name}: tiers {list(doc)}, expected {list(TIER_ORDER)}")
    fields = [f for f in Tier.__dataclass_fields__ if f != "name"]
    out = []
    for name, row in doc.items():
        if list(row) != fields:
            raise ValueError(f"{path.name} [{name}]: fields {list(row)}, expected {fields}")
        bad = [f for f in _INT_FIELDS if type(row[f]) is not int]
        bad += [f for f in _FLOAT_FIELDS if type(row[f]) not in (int, float)]
        if type(row["slippery"]) is not bool:
            bad.append("slippery")
        if type(row["note"]) is not str:
            bad.append("note")
        if bad:
            raise ValueError(f"{path.name} [{name}]: wrong type for {bad}")
        vals = {f: float(row[f]) if f in _FLOAT_FIELDS else row[f] for f in fields}
        bad = [f for f in _FLOAT_FIELDS if not math.isfinite(vals[f])]
        bad += [f for f in ("takeoff_window", "stick_deg") if vals[f] < 0]
        if not 0.0 < vals["reach"] <= 1.0:
            bad.append("reach")
        if vals["difficulty"] != DIFFICULTY[name]:
            bad.append("difficulty")
        if name != "phys" and vals["lift_allowance"] > LIP_LIFT_ROWS[-1][0]:
            bad.append("lift_allowance")
        if bad:
            raise ValueError(f"{path.name} [{name}]: value out of range for {bad}")
        out.append(Tier(name, **vals))
    return tuple(out[:-1]), out[-1]


def lip_lift_window(tier: Tier, deficit: float) -> tuple[float, float] | None:
    """The takeoff distances before a plain ledge's face (near, far; m)
    from which ``tier`` counts the collision lip lift over a lip
    ``deficit`` m above the rank's frame-perfect apex; None above the tier's
    ``lift_allowance``.  A player tier takes the window measured at the
    smallest deficit at or above this one (``LIP_LIFT_ROWS``; s6's own
    window up to 0.2343 m).  The window depends on the deficit alone and
    narrows as it grows, so a harder tier, whose allowance is no lower,
    counts every lip and takeoff an easier one counts.  R_phys counts
    from between s6's nearest failing takeoffs [proposal].  The caller
    still owes the takeoff room: the floor must allow a takeoff over at
    least max(takeoff_window, 1) rows (7/30 m each) of the window."""
    if deficit > tier.lift_allowance:
        return None
    if tier.difficulty == 0:
        return LEDGE_S6["fails_near_m"], LEDGE_S6["fails_from_m"]
    if deficit <= LIP_LIFT_ROWS[0][0]:
        return LEDGE_S6["takeoff_window_m"]
    _, first, last = next(r for r in LIP_LIFT_ROWS if deficit <= r[0])
    return round(lip_row_m(last), 2), round(lip_row_m(first), 2)


TIERS, PHYS = load_tiers()        # PHYS: the physical bound for the trap check, never a player tier
# The zones' free movement (reach.py's zones, gates.free_edge): fixed margins, Step R1.2's safe tier's on its level
# grid (a flight reads the first of ZONE_LEVELS at or above its dh) and walk-off table, so a zone, and its id that the hand authoring
# names, doesn't move when the tiers are recalibrated (Step R1.2b, D156). Every player tier is at least as
# permissive (its margins lie from these toward the envelope), so a zone is free at every tier. Only the jump alone
# matters (free movement takes no item): reach is never applied to it.
ZONE = Tier("zone", 1, slippery=False, note="the zones' free movement: Step R1.2's safe margins, fixed",
            **dataclasses.asdict(physics.FREE))
ZONE_CARRY_DROPS = physics.FREE_CARRY_DROPS     # its walk-off carry table's drops, m
ZONE_LEVELS = physics.FREE_LEVELS


def last_crossing(rows, level: float) -> float | None:
    """The travel where the feet last descend through ``level``."""
    for (xa, za), (xb, zb) in reversed(list(zip(rows, rows[1:]))):
        if za >= level > zb:
            return xa + (za - level) / (za - zb) * (xb - xa)
    return None
