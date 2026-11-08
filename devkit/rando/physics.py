"""The physics the derive reads: AzurKit's calculator (:mod:`azurkit.tools.randomizer.physics`) with the parts of
Modkit's ``randomizer/physics.py`` that AzurKit dropped and the derive still needs (Step 4.13c).

AzurKit's randomizer keeps the calculator and the tiers' margins; it dropped what only the derive and Modkit's
slider re-check read. The derive's flights need three of those, restored here as Modkit had them at its freeze:

- :meth:`Physics.walk_off_carry`, the carry off a ledge with no jump (the derive's walk-off table);
- :class:`Certificate`, what a derived flight physically needs (each derived edge keeps its witness's);
- :data:`ROOF_END` and :data:`WALKOFF_SLACK`, which the flights read, and :data:`PICK_STAND`, the gates' and the
  authoring's standing touch.

:class:`Envelope` is AzurKit's on :class:`Physics`. Every other name is AzurKit's own (this module's
:func:`__getattr__` hands it over), so the derive's numbers are the shipped calculator's. :data:`SOURCE_SHA256` is
the code a process runs, AzurKit's physics.py and this file as they loaded: the flights key their kept envelope by
it (Modkit keyed it by its own physics.py's). Dev only, like all of devkit.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from azurkit.tools.randomizer import physics as _physics
from azurkit.tools.randomizer.physics import AC_PLAIN, f32

SOURCE_SHA256 = hashlib.sha256(Path(_physics.__file__).read_bytes() + Path(__file__).read_bytes()).hexdigest()


def __getattr__(name: str):
    """AzurKit's physics' own names (the calculator, the movement, the margins and constants)."""
    return getattr(_physics, name)


class Physics(_physics.Physics):
    """AzurKit's calculator with the walk-off carry (Modkit's ``Physics.walk_off_carry``)."""

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


class Envelope(_physics.Envelope):
    """AzurKit's envelope on :class:`Physics` (so its ``p`` has the walk-off carry)."""

    def __init__(self, m: _physics.Movement = _physics.VANILLA, beam: int = 100):
        super().__init__(m, beam)
        self.p = Physics(m)


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
PICK_STAND = 1.5      # [inferred] a pickup up to 1.5 m above the floor is touched standing (draft/gates.py)
