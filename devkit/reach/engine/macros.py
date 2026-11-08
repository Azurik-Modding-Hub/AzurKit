"""The reach engine's launches (Step R2.16a; the R2.16 design §1's M0 and its targeted pass; Step R2.16b's aims,
roll jumps and recasts): closed-loop controllers that read each tick's row and give the next tick's pad, so a launch
adapts to where the game puts the body, and the pads it gave are its witness string (``l3.pads`` run-length
segments, the camera as the exact f32 pair the input builder read: what ``xemu_oracle.py replay`` replays).

A launch from a settled start, along a game heading (it faces (-sin h, cos h)), the stick held at full tilt:

- ``walkoff``: run along the heading until the body leaves the floor;
- ``runjump``: run along it and press Y (held :data:`JUMP_HOLD` ticks) once the feet have come ``back`` metres,
  the run-up the start was placed behind the takeoff, less the macro's ``lead`` (:data:`JUMP_LEAD` by default: the
  takeoff sample's floor may end a quarter metre past it, and the press acts a tick later; an aim's 0 presses at
  the takeoff itself);
- ``standjump``: press Y on the first tick;
- ``rolljump``: run as for a run jump and press BLACK there instead (a roll, BLACK's ``roll forward``: 21 rows of
  state 0x100 that move the body by root motion and take no stick, off the edge into the air too), each further
  roll of its ``rolls`` chained by BLACK held on the roll's ticks :data:`CHAIN` (a press on ticks 12-20 chains
  the next, one every :data:`ROLL_PERIOD` ticks), and Y held from the last roll's tick :data:`ROLL_Y` into its
  end tick: the end-tick jump, which in mid-air replaces the fall speed by the jump's and resets the flaps (D114:
  both buttons buffer, held);

a run or roll jump whose body leaves the floor before its press is no launch of its own (``walked off``: the
walk-off's, which the set holds); then, in the air, ``flaps`` flaps chained down each fall (:func:`flap_due`: a one-tick press, Y released the tick
before, the game's per-jump counter below the macro's count; the air shield's Flaps 1/2/5 cap it), with ``recast``
an LT+Y cast whenever the gauge has emptied with flaps left (a descent flap empties it; a recast refills the gauge,
not the jump's flap count), the stick still held; then at rest until the body has been settled :data:`STILL` ticks
(``l3_search.settled``: standing, swimming or at rest on near-flat ice, AZ-737; a slide or a hoist runs on: at
most :data:`SETTLE` ticks after the first touch-down; a swimmer is then held at rest :data:`SWIM_HOLD` ticks more,
so a landing that drifts on out of its zone is seen), it dies (state 7 or 8, HP 0), it
has been airborne :data:`AIR_CAP` ticks (or at rest in the air :data:`STUCK`), the launch reaches :data:`TICKS`, or
the step raises (a fault, a level exit).

An aim (the targeted pass, :mod:`.aim`) is any of them toward a target, its own controller steering the stick
(:meth:`_Run.steer`, which R0's holds along the heading until the body is back on something).

The R0 set (:data:`R0`): ``k0`` (no element levels: rank 0) walkoff, runjump and standjump; ``air3`` (air level 3,
the shield cast by LT+Y: Flaps 5) walkoff with 1, 2 or 5 flaps and runjump and standjump with 0, 1, 2 or 5.
:func:`launches` runs macros that differ only in their flaps together: their pads agree until the fewest's flaps are
spent, so those ticks are stepped once (Step R2.16c: a fifth of R0's fan's ticks), each branch going on from its
saved state with the pads and rows it would have alone.  Pure but for the simulator it drives (``step``, ``save``,
``reset``: L3, or a test's stand-in); positions stay in memory.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from devkit.rando.physics import DESCENT_D, FLAP_MULT, FPS, GRAVITY, H_AIR
from devkit.sim.inputs import camera, stick
from devkit.sim.l3 import L3Error, LevelExit, Pad
from devkit.sim.l3_search import CAST_WAIT, ROLL_TAP, SETTLED, settled  # noqa: F401 (SETTLED: importers')
from devkit.sim.tricks_detect import ROLL_PERIOD, ROLL_TICKS

AIRBORNE = frozenset({2, 0x102})     # entity+0x94: in the air, the air attack move
SWIMMING = 6
DEAD = frozenset({7, 8})
JUMP_HOLD = 6                        # Y held this many ticks for a jump (the harness's capture, l3_search's)
JUMP_LEAD = 0.45                     # [proposal] a run jump's press this far short of the takeoff (the smoke slice's
                                     # 0.2 walked off the derive's takeoffs before the press: a tick is 0.23 m)
STILL = 5                            # [proposal] ticks settled that end a launch once it has landed
SETTLE = 120                         # [proposal] ticks after the first touch-down for a slide or a hoist to end (the
                                     # tall hoist alone is 88 ticks; the smoke slice's 30 cut 26% of launches mid-slide)
SWIM_HOLD = 60                       # [proposal] ticks a settled swimmer is held at rest more (R2.16a's skeptic: 2 of 3
                                     # swimming landings left their zone within 60 idle ticks; R2.16c's, S6: 24 of 40
                                     # new-reach swims, 0 of 40 standing ones)
AIR_CAP = 300                        # ticks airborne at most (l3_search's LAND_CAP: 10 s; 5 flaps take 133-185 ticks
                                     # and a fall into the sea after them more: 210 capped 4% of the smoke slice)
RUN_CAP = 40                         # [proposal] ticks a run may take to leave the floor (a wall stops it)
TICKS = 400                          # a launch's longest string
STUCK = 30                           # [proposal] ticks airborne at rest (under 0.05 m/s) that end a launch: a body
                                     # resting on an edge in state 2 (the smoke slice's air caps sat so 220 ticks)
CHAIN = (14, 18)                     # [proposal] BLACK held on these ticks of a roll chains the next (12-20 do,
                                     # l3_options.RollChain; skips-a A4/A5)
ROLL_Y = 16                          # [proposal] Y held from this tick of the last roll into its end tick (4-20 do)
KITS = {"k0": {}, "air3": {"air": 3}}   # the two kit branches: rank 0 and the air shield (cast by input)
FLAP_MARGIN = 0.3                    # [proposal] a flap keeps this far inside the law's bounds (l3_goal's)
Y, BLACK, CAST = frozenset({"y"}), frozenset({"black"}), frozenset({"lt", "y"})


class Macro(NamedTuple):
    """One launch: ``kind`` walkoff, runjump, standjump or rolljump; its kit branch (:data:`KITS`); the flaps it
    chains; an aim's ``curve`` (radians off its target for its first airborne ticks, ``aim.TURN``); a run or roll
    jump's press ``lead`` (m short of the takeoff); a roll jump's ``rolls``; ``recast`` (an LT+Y cast whenever the
    gauge empties with flaps left); an aim's ``hold`` (the stick held at its unsnapped point, R0's steering)."""
    kind: str
    kit: str
    flaps: int = 0
    curve: float = 0.0
    lead: float = JUMP_LEAD
    rolls: int = 1
    recast: bool = False
    hold: bool = False

    @property
    def name(self) -> str:
        extra = f"-c{round(math.degrees(self.curve)):+d}" if self.curve else ""
        extra += f"-l{self.lead:g}" if self.lead != JUMP_LEAD and self.kind in ("runjump", "rolljump") else ""
        extra += f"-r{self.rolls}" if self.kind == "rolljump" else ""
        extra += "-recast" if self.recast else ""
        extra += "-hold" if self.hold else ""
        return f"{self.kind}{extra}-{self.kit}-f{self.flaps}"

    @property
    def stands(self) -> bool:
        """Whether it starts from the standing start (0.3 m back) rather than the run-up."""
        return self.kind == "standjump"


R0 = tuple([Macro(k, "k0") for k in ("walkoff", "runjump", "standjump")]
           + [Macro("walkoff", "air3", n) for n in (1, 2, 5)]
           + [Macro(k, "air3", n) for k in ("runjump", "standjump") for n in (0, 1, 2, 5)])
BACK_RUN, BACK_STAND = (1.0, 0.5, 0.0), (0.3, 0.0)   # the design's run-up and stand (m), then what the floor allows


def min_rank(o: dict) -> int:
    """The least air rank an outcome's witness needs (``graph``'s rule): none in rank 0's branch; in the shield's,
    1 for at most one flap in the jump, 2 for two, 3 for more (Flaps 1/2/5)."""
    if o["kit"] == "k0":
        return 0
    return 1 if o["flaps"] <= 1 else 2 if o["flaps"] == 2 else 3


def _feet(row) -> tuple[float, float, float]:
    return row.pos[0], row.pos[1], row.pos[2] - 1.0


def _flaps(row) -> int:
    o = getattr(row, "obs", None)
    return (o.flaps_used or 0) if o is not None else 0


def flap_due(row) -> bool:
    """Whether a falling body (``row``) flaps now (the flap law, physics.py: d = peak_z + h - z, the lift
    sqrt(2 g min(max(d, 0), h)) and vz := min(v0f, vz + 1.5 v0f), a descent flap past d = 6): never above the
    ceiling (d under :data:`FLAP_MARGIN`: it lifts nothing), at once short of the descent flap, else on the last
    tick its full lift still holds (vz no lower than -v0f / 2 a tick on), so each of a chain lifts the most it can;
    with no latch (a walk-off's may be stale or unset) on the fall's first tick."""
    o = getattr(row, "obs", None)
    if o is None or o.vel[2] > 0.0:
        return False
    peak = o.peak_z
    if peak is None or not math.isfinite(peak) or peak < -1e30:
        return True
    d = peak + H_AIR - row.pos[2]
    if d <= FLAP_MARGIN:
        return False
    if d >= DESCENT_D - FLAP_MARGIN:
        return True
    v0f = math.sqrt(2 * GRAVITY * min(d, H_AIR))
    return o.vel[2] - GRAVITY / FPS < v0f - FLAP_MULT * v0f


class Launch(NamedTuple):
    """A launch's pads and the rows they made, why it ended (:func:`launch`), the index of the first row back on
    something after the takeoff (None if none) and the simulator's taint when it ended."""
    pads: list
    rows: list
    end: str
    first: int | None
    taint: frozenset = frozenset()


def align(sim, cam: float, heading: float) -> tuple[list, list, float]:
    """Turn the camera to ``heading`` at the pad's rate (``inputs.CAM_RATE``), the stick at rest, from the
    simulator's state now: (the pads, their rows, the camera after).  A player turns the camera before a run, so
    the run's stick sits on the camera's axis (full speed, not the round gate's diagonal 0.76)."""
    pads, rows = [], []
    while abs(math.remainder(heading - cam, 2 * math.pi)) > 1e-9:
        cam = camera(cam, heading)
        pads.append(Pad(stick(None, cam), frozenset(), cam))
        rows.append(sim.step(pads[-1]))
    return pads, rows, cam


def _roll_buttons(m: Macro, k: int, took) -> frozenset:
    """A roll jump's buttons on tick ``k`` after its BLACK press (the module docstring): BLACK tapped, held on the
    chaining ticks of every roll but the last, Y from the last roll's :data:`ROLL_Y` until the jump is in the air."""
    i, r = divmod(k, ROLL_PERIOD)
    if k < ROLL_TAP or (i < m.rolls - 1 and CHAIN[0] - 1 <= r <= CHAIN[1] - 1):
        return BLACK
    last = (m.rolls - 1) * ROLL_PERIOD
    if took is None and last + ROLL_Y - 1 <= k < last + ROLL_TICKS + JUMP_HOLD:
        return Y
    return frozenset()


class _Run:
    """One launch's controller (:func:`launch`): :meth:`pad` the next tick's pad from the rows so far, :meth:`seen`
    the row that pad made (why the launch ended, or None) and :meth:`steer` the stick, R0's (an aim's controller,
    ``reach_engine.aim.Aim``, steers its own at ``target``)."""

    def __init__(self, m: Macro, heading: float, cam: float, start: tuple, back: float, target=None) -> None:
        self.m, self.heading, self.cam, self.start, self.back, self.target = m, heading, cam, start, back, target
        self.pads, self.rows = [], []
        self.dx, self.dy = -math.sin(heading), math.cos(heading)
        self.jump_at = 0 if m.kind == "standjump" else None
        self.took = self.first = self.settle = None   # the first airborne row; the first row back on something
                                                      # after it; the row its settle completed on
        self.still = self.air = self.presses = self.rest = self.recasts = 0
        self.cast_at = -99

    def steer(self, t: int, prev) -> tuple[float | None, bool, bool]:
        """Tick ``t``'s stick heading (None: at rest; ``prev`` the row before), whether the camera follows it and
        whether a flap may go (an aim's control flaps only while it would land short): R0's stick held along the
        heading until the body is back on something, then at rest."""
        return (None if self.first is not None else self.heading), True, True

    def pad(self) -> Pad:
        m, rows, took = self.m, self.rows, self.took
        t, prev = len(rows), (rows[-1] if rows else None)
        buttons = frozenset()
        h, follow, short = self.steer(t, prev)
        if self.jump_at is None and took is None and prev is not None and m.kind in ("runjump", "rolljump"):
            f = _feet(prev)
            if (f[0] - self.start[0]) * self.dx + (f[1] - self.start[1]) * self.dy >= self.back - m.lead:
                self.jump_at = t
        if m.kind == "rolljump":
            if self.jump_at is not None:
                buttons = _roll_buttons(m, t - self.jump_at, took)
        elif self.jump_at is not None and t - self.jump_at < JUMP_HOLD:
            buttons = Y
        if took is not None and self.first is None and not buttons and t - self.cast_at > CAST_WAIT:
            o = prev.obs
            if (m.recast and o is not None and o.gauge is not None and o.gauge <= 1e-6 and _flaps(prev) < m.flaps
                    and self.recasts < m.flaps and "y" not in self.pads[-1].buttons):
                buttons, self.cast_at, self.recasts = CAST, t, self.recasts + 1
            elif (self.presses < m.flaps + 2 + self.recasts and _flaps(prev) < m.flaps and short
                  and "y" not in self.pads[-1].buttons and flap_due(prev)):
                buttons, self.presses = Y, self.presses + 1
        self.cam = camera(self.cam, h if follow else None)
        return Pad(stick(h, self.cam), buttons, self.cam)

    def seen(self, pad: Pad, row) -> str | None:
        m, t = self.m, len(self.rows)
        self.pads.append(pad)
        self.rows.append(row)
        if row.state in DEAD or row.hp <= 0:
            return "dead"
        if getattr(row, "exit", None) is not None:
            return "exit"
        if row.state in AIRBORNE:
            if self.took is None and self.jump_at is None and m.kind in ("runjump", "rolljump"):
                return "walked off"
            self.air += 1
            self.took = t if self.took is None else self.took
            self.rest = self.rest + 1 if row.obs is not None and math.hypot(*row.obs.vel) < 0.05 else 0
            if self.air > AIR_CAP or self.rest >= STUCK:
                return "air cap" if self.air > AIR_CAP else "stuck"
        elif self.took is not None and self.first is None:
            self.first = t
        rolling = ROLL_PERIOD * m.rolls + ROLL_TICKS if m.kind == "rolljump" and self.jump_at is not None else 0
        if self.took is None and t >= RUN_CAP + (JUMP_HOLD if self.jump_at is not None else 0) + rolling:
            return "stayed"
        if self.first is not None:
            self.still = self.still + 1 if settled(row) else 0
            if self.settle is None and self.still >= STILL:
                self.settle = t
            if self.settle is not None and (self.rows[self.settle].state != SWIMMING or t - self.settle >= SWIM_HOLD):
                return "settled" if settled(row) else "unsettled"     # a swimmer the hold left on a slope
            if self.settle is None and t - self.first >= SETTLE:
                return "unsettled"
        return None


def _stepped(sim, pad: Pad):
    """``sim.step(pad)``'s row, or why the launch ended there (a level exit, a fault) as a string."""
    try:
        return sim.step(pad)
    except LevelExit:
        return "exit"
    except L3Error as exc:
        return f"fault:{getattr(exc, 'site', 'other')}"


def launch(sim, m: Macro, heading: float, cam: float, start: tuple, back: float, *, target=None,
           ctl=None) -> Launch:
    """Run macro ``m`` from the simulator's state now (feet ``start``, ``back`` m behind the takeoff, camera yaw
    ``cam``) along ``heading`` under controller ``ctl`` (:class:`_Run`, R0's, by default; an aim's steers at
    ``target``, ``reach_engine.aim.Aim``).  Returns its :class:`Launch`: the
    pads and rows, why it ended (``settled``; ``unsettled``: back on something but not settled :data:`STILL`
    ticks within :data:`SETTLE`, or a swimmer not settled when its hold ends;
    ``walked off``: a run or roll jump off the floor before its press;
    ``dead``, ``air cap``, ``stuck``: airborne at rest :data:`STUCK` ticks, ``ticks``, ``stayed``: it never left
    the floor, ``exit``: a level exit, ``fault:<site>``) and the first row back on something after the takeoff."""
    return launches(sim, [m], heading, cam, start, back, target=target, ctl=ctl)[0]


def launches(sim, ms, heading: float, cam: float, start: tuple, back: float, *, target=None,
             ctl=None) -> list[Launch]:
    """Each macro of ``ms`` as :func:`launch` runs it alone from the simulator's state now, the ticks they share
    stepped once: they run together while their next pads agree, and those whose pad parts from the first's go on
    from that tick's saved state (``sim.save``, ``sim.reset``) after it ends, so macros that differ only in their
    flaps share their run-up, their jump and every flap up to the fewest's.  Their :class:`Launch` es, in order."""
    runs, ends = [(ctl or _Run)(m, heading, cam, start, back, target) for m in ms], ["ticks"] * len(ms)
    taints = [frozenset()] * len(ms)
    todo = [(None, list(range(len(ms))), None)]      # (the state to go back to, the runs together, their next pad)
    while todo:
        state, group, pad = todo.pop()
        if state is not None:
            sim.reset(state)
        while group and len(runs[group[0]].rows) < TICKS:
            if pad is None:
                pads = [runs[i].pad() for i in group]
                pad = pads[0]
                apart = {}
                for i, p in zip(group, pads):
                    if p != pad:
                        apart.setdefault(p, []).append(i)
                if apart:
                    here = sim.save()
                    todo += [(here, g, p) for p, g in apart.items()]
                    group = [i for i, p in zip(group, pads) if p == pad]
            row = _stepped(sim, pad)
            if isinstance(row, str):
                for i in group:
                    ends[i] = row
                break
            for i in list(group):
                if (end := runs[i].seen(pad, row)) is not None:
                    ends[i], taints[i] = end, frozenset(getattr(sim, "taint", ()))
                    group.remove(i)
            pad = None
        for i in group:                                # those the cap or a raise ended
            taints[i] = frozenset(getattr(sim, "taint", ()))
            if ends[i] == "ticks" and runs[i].settle is not None:     # the cap in a swimmer's hold
                ends[i] = "settled" if settled(runs[i].rows[-1]) else "unsettled"
    return [Launch(r.pads, r.rows, e, r.first, t) for r, e, t in zip(runs, ends, taints)]
