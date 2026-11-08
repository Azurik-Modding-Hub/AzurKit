"""Dev-only route pilot for the xemu oracle (Steps X.2, X.4): walk the
player to a target with pad input, in closed loop.

A sitting script (``uv run --locked python`` from the checkout's root)
asks::

    from devkit.xemu import oracle as xo, route as xr
    router = xr.router(iso, "w2")                  # the level's reach model and route graph: minutes, keep it
    res = xr.walk_to(sb, router, "w2/g0/r1357", tier="hard", air=0, ticks=2400, label="r1357-0",
                     log="legs.jsonl")              # one line per leg, planned against actual
    res["reached"], res["left_m"], res["legs"]     # no coordinates

A target is a point (x, y, z at the feet), a zone (``w2.Z013``), a node of
the level file (``w2_z013``) or a generated id (``w2/g0/r1357``: a pickup's
point).  ``plan(sb, router, target)`` only plans from the player's spot.

The pilot plans with ``devkit/rando/draft/route.py`` from the
player's spot (the body centre critter+0x15C less 1 m), then on every player
tick (``Sandbox.capture``'s ``on_tick``, halted at 0x8CCC0) it steers.

The pad (Step X.4).  By default the left stick is analog: the stick the
pilot picks for the next tick is written into the active ControllerState's
left-stick floats when the game builds that tick's input (a capture hook
on ``xo.INPUT_BUILD`` calling ``Sandbox.write_pad``, the harness's one RAM
pad writer, with ``stick_only``), within what a real pad's round gate gives
(``route.stick``).  That write is the pilot's only RAM write: the pad's own
state as the game reads it.  The right stick turns the camera 3 degrees a
tick so the heading lies along a stick axis (where the gate gives full
speed); it and the buttons (Y jump, A) go through the FIFO.  With
``analog=False`` the pad is X.2's FIFO alone (four cardinal directions,
which a skip confirmation's input rule needs, D114).  With
``analog="pipe"`` (Step X.14, the fork build) the same analog stick goes
through the input pipe's ``axis lx|ly`` lines instead of a RAM write: the
pad's own path, no RAM write at all, landing a tick or two later
(``xo.pipe_axis`` maps the ControllerState value to the raw axis).

Walking is pure pursuit on the way-points (a look-ahead point), slower on
steep border floors.  A flight it runs along its track at the takeoff
speed it needs (a lip lift and a gap at full speed, the camera turned to
the track in the run-up; backing up first when it starts slow near the
takeoff) and presses Y at ``at`` (none at a drop); in the air the stick
holds the air-control target that lands the body on the aim
(``route.air_target``; a lip lift pushes into its face until it is over
the ledge), and a flap leg flaps while the landing is out of reach.  It
swims, goes to a ride's trigger pad and then stands on the ride, hops
into a climb's face (a climb starts in the air), and walks back up a
slope it slid onto.  While the game ignores the stick (input+0x30: an
exit's camera field walking the player out) it waits, then replans.
With no progress for
``STUCK_TICKS`` ticks it sidesteps, then hops, then replans around the
spot; off its route (a fall, a slide, a missed landing) it replans too.  A
ride that doesn't move, a swim's shore, a flight that misses twice (or
whose landing it slides off twice) is banned.  When HP drops fast and is
under 60 % of max it retreats along its way, holds still, then replans
around where the hits came (twice at most, then it presses on).  A dialog stops the player tick:
A clears it and the pilot goes on.

``log``: a JSONL file, one line per leg: the leg as planned (its edge's
kind, rise, gap, lip window) against what happened (takeoff offset and
speed, apex, landing error, ticks, HP lost) and, for a flight, its arc
relative to the takeoff: the research report's P7 calibration data.

Dev only (devkit, Step 4.13d2), a library, never in pytest (D11); the
sandbox rules are the
``azurik-xemu-oracle`` skill's.  Nothing it returns, prints or logs holds
a coordinate: distances, zones, actions and counts only, and arcs relative
to their takeoff.
"""

from __future__ import annotations

import json
import math
import struct
import sys
import time

from devkit.rando.derive import router  # noqa: F401  (the reach model and its route graph: Step 4.13c's home)
from devkit.rando.draft import route as rt_mod
from devkit.sim import inputs, l3
from devkit.xemu import oracle as xo

STICK = {"lstick_up": 0.0, "lstick_left": 90.0, "lstick_right": -90.0, "lstick_down": 180.0}   # [verified xemu skips-b]
BODY_CENTRE = 0x15C      # critter+0x15C: the body centre, feet + 1.0 m (it follows the body in the air and in water)
CAM_YAW = 0x10           # input+0x10 (EAX at 0x8CCC0): the camera yaw, radians; game angle a faces (-sin a, cos a)
FORCED = 0x30            # input+0x30: set, the builder ignored the stick this tick (0x8503C: something else moves the
                         # player, e.g. 0x84FEE's list at gameplay+0xC4); sitting x4 saw 7 m/s at a fixed heading
FORCED_MAX = 450         # [proposal] carried this many ticks in a row (15 s): the walk ends
FLAPS_USED = 0xD8        # entity+0xD8
GROUND = (0, 1, 3, 0x100)        # ground, climb, slope, the ground attack move (the step-up sets it)
HIT = 0x102                      # the hit handler's air attack move (13 ticks), then 2
AIR, SWIM, DEAD, SLOPE, CLIMB = (2, HIT), 6, 7, (3, 4), 1
G = 9.8                  # [verified static] 0x1980A8
LOOK_M = {"walk": 1.2, "swim": 2.5, "climb": 0.8}
STUCK_TICKS, HOP_TICKS, SIDE_TICKS = 45, 3, 12   # [proposal] no 0.3 m of progress in 1.5 s: sidestep, hop, replan
OFF_ROUTE_M, OFF_TICKS = 2.5, 8  # [proposal] this far off a walk leg's way-point line (or 2 m off its height) on the
                                 # ground for this many ticks: replan
LEAD_M = {"jump": 0.15, "step": 0.55, "flap": 0.15}   # [proposal] Y goes down this far and half a tick's run (0.12 m
                                                      # at 7 m/s) before `at`: it acts a tick later (skill section 3);
                                                      # x4: a whole tick's run took e2.Z028's jump off the rim's slope
RIM_LEAD_M = 0.35        # [proposal] a lip lift's takeoff at a pit's rim: press earlier, the body mustn't walk off
WAIT_TICKS = 300
RUN_M = (1.5, 1.0, 0.5)  # a flight's run-up, where the floor behind its takeoff allows
SLIDE_TICKS = 24         # [proposal] after a landing on a slope, walk back up for this long before calling it off-route
STEEP_NZ, STEEP_MAG = 0.9, 0.45   # [proposal] on a border floor steeper than this, walk at this stick (x4: f6.Z806's
                                  # 35-degree hump threw a 5.3 m/s walk off its crest, state 3 then 2)
CAM_DEAD = 3.5           # [proposal] the camera turns 3.3 deg a tick: a narrower deadband flips it left and right
CLIMB_HOP = 20           # [proposal] on a climb leg's ground, a hop into the face every this many ticks
DANGER_TICKS, DANGER_HP = 60, (30, 0.10)   # [proposal] HP falling max(30, 10 % of max) within 2 s is danger,
DANGER_LOW = 0.6                           # with HP under 60 % of max (x4: retreats at f6's step, HP 385 of 400,
                                           # cost a run X.2's press-on pilot made)
RETREAT_M, RETREAT_TICKS, HOLD_TICKS, RETREATS = 4.0, 75, 60, 2   # [proposal] back 4 m, hold 2 s, at most twice
PAD_BUTTON = {"touch": None, "action": "x", "whack": "a"}   # a ride's pad: stand there, then this button (X opens the
                                                            # level-1 door; A is the staff); magic hits and joysticks: none
last_pilot = None        # walk_to's last Pilot (its routes and trace: positions, keep them private)


def wrap(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def ang_of(dx: float, dy: float) -> float:
    """The game angle a of a world direction (dx, dy): (-sin a, cos a)."""
    return math.degrees(math.atan2(-dx, dy))


def feet(sb, row: dict) -> tuple:
    """The player's feet (the body centre less 1 m), in memory only."""
    c = row.get("critter")
    c = c if isinstance(c, int) else sb.g.u32(row["ent"] + 0x20)
    x, y, z = struct.unpack("<3f", sb.g.read(c + BODY_CENTRE, 12))
    return x, y, z - 1.0


def cam_yaw(sb) -> float:
    return read_input(sb)[0]


def read_input(sb) -> tuple:
    """(camera yaw in degrees, forced) from the input struct (EAX, halted at 0x8CCC0)."""
    g = sb.g
    b = g.read(g.regs()["eax"] + CAM_YAW, FORCED - CAM_YAW + 1)
    return math.degrees(struct.unpack_from("<f", b, 0)[0]), b[FORCED - CAM_YAW] != 0


class Pilot:
    """The closed-loop route follower (the module docstring): a ``capture``
    ``on_tick`` callable, with :meth:`pad_hook` its analog stick's writer.
    ``result()`` summarises the walk."""

    def __init__(self, router, target, *, tier="hard", air=0, tol=0.6, allow_probe=None, gates_open=False,
                 max_replans=10, plan_kw=None, analog=True, log=None, label=None):
        self.R, self.target, self.tol = router, target, tol
        allow_probe = router.probe_classes() if allow_probe is None else allow_probe
        self.kw = dict(tier=tier, air=air, allow_probe=tuple(allow_probe), gates_open=gates_open, **(plan_kw or {}))
        self.max_replans = max_replans
        if analog not in (True, False, "pipe"):
            raise ValueError(f"analog {analog!r}: True (RAM at the input builder), 'pipe' (the pipe's axis) or False")
        self.analog, self.log, self.label = analog, log, label
        self.gmask, self.gp, self.band = router.goal(target)
        self.held: set = set()
        self.stick = (0.0, 0.0)
        self.piped = (0.0, 0.0)        # the stick the pipe was last sent (analog="pipe")
        self.cam = self.cam_prev = None
        self.ban: set = set()
        self.fails: dict = {}
        self.avoid: list = []
        self.plans: list = []
        self.legs_done: list = []
        self.route = None
        self.done = False
        self.why = None
        self.replans = self.hops = self.sides = self.retreats = 0
        self.k = 0
        self.last = None
        self.states: set = set()
        self.hp: list = []
        self.dmg: list = []            # (tick, HP) lost away from a landing
        self.last_st, self.land_k = None, -99
        self.mode = None               # None, "retreat" or "hold" (fast HP loss)
        self.forced = 0                # ticks in a row the stick was ignored (FORCED)
        self.logged: set = set()       # (plan, leg) pairs the log has
        self.touched: set = set()      # the ride pads touched (atoms)
        self.detours: list = []        # (target, goal) stacked while the pilot goes to a ride's pad
        self.press_left, self.press_btn = 0, None
        self.trace: list = []          # (tick, feet, state, leg, held, stick, camera, its prediction, velocity xy) in
                                       # memory only: keep it private
        self.routes: list = []         # every plan's Route (positions: keep them private)

    # -- plans and legs
    def _plan(self, p, why):
        rt = self.R.plan(p, self.target, ban=self.ban, avoid=self.avoid, **self.kw)
        self.plans.append({"why": why, "reached": None if rt is None else rt.reached,
                           "cost_s": None if rt is None else round(rt.cost_s, 1),
                           "legs": None if rt is None else [leg.summary() for leg in rt.legs]})
        self.route = rt
        self.routes.append(rt)
        self.li = 0
        self._leg_start(p)
        return rt

    def _leg_start(self, p):
        self.seg, self.phase, self.t, self.air_t = 0, "go", 0, None
        self.best, self.best_k, self.hop_left, self.side_left, self.unstick = math.inf, self.k, 0, 0, 0
        self.anchor = p
        self.y_down = 0
        self.final = False
        self.aim = None
        self.off_n = 0
        self.on_route = None
        self.back = None
        self.slid = 0
        self.leg_k0, self.leg_hp0, self.leg_states, self.leg_forced = self.k, self.hp[-1] if self.hp else None, set(), 0
        self.fl = {}                   # a flight's measurements (positions in memory only)
        self.air_T = (0.0, 0.0)        # the air-control target the last stick asked for (world, m/s)

    @property
    def leg(self):
        rt = self.route
        return rt.legs[self.li] if rt is not None and self.li < len(rt.legs) else None

    def _end_leg(self, how):
        leg = self.leg
        self.legs_done.append({**leg.summary(), "how": how, "ticks": self.t})
        self._log_leg(leg, how)

    def _next_leg(self, p, how="done"):
        self._end_leg(how)
        self.li += 1
        self._leg_start(p)

    def _replan(self, p, why, ban_leg=False):
        leg = self.leg
        if leg is not None:
            self._end_leg(why)
            prev = self.route.legs[self.li - 1] if self.li else None
            if leg.action == "walk" and prev is not None and prev.eid >= 0 and prev.action in ("jump", "flap", "drop"):
                self.fails[prev.eid] = self.fails.get(prev.eid, 0) + 1
                if self.fails[prev.eid] >= 2:      # the walk on from a flight's landing failed twice: land elsewhere
                    self.ban.add(prev.eid)
            if ban_leg and leg.eid >= 0:
                self.fails[leg.eid] = self.fails.get(leg.eid, 0) + 1
                if self.fails[leg.eid] >= 2 or leg.action in ("walk", "swim", "wait"):
                    self.ban.add(leg.eid)       # a flight gets a second try
        self.replans += 1
        if self.replans > self.max_replans:
            return self.finish(f"{why}; replans used up")
        if self._plan(p, why) is None:
            return self.finish(f"{why}; no route from here")

    def finish(self, why):
        if not self.done and self.leg is not None:
            self._log_leg(self.leg, why if why == "reached" else f"end: {why}")
        self.done, self.why = True, why

    # -- the goal
    def at_goal(self, p, st) -> bool:
        if st in AIR:
            return False
        if self.gp is not None:
            return (math.hypot(p[0] - self.gp[0], p[1] - self.gp[1]) <= self.tol
                    and self.band[0] - 0.1 <= self.gp[2] - p[2] <= self.band[1] + 0.1)
        v = self.R.locate(p, prefer_water=st == SWIM)
        return v >= 0 and bool(self.gmask[v])

    def left_m(self, p) -> float:
        """The distance still to go: to the target point, or the rest of the route."""
        return math.dist(p, self.gp) if self.gp is not None else self.rest_m(p)

    def rest_m(self, p) -> float:
        """The rest of the route from p: to the next way-point, then along the way-points."""
        if self.route is None or self.leg is None:
            return math.nan
        rest = [self.leg.pts[min(self.seg, len(self.leg.pts) - 1)]] + self.leg.pts[self.seg + 1:]
        for leg in self.route.legs[self.li + 1:]:
            rest += ([leg.at] if leg.at else []) + leg.pts
        return math.dist(p, rest[0]) + sum(math.dist(a, b) for a, b in zip(rest, rest[1:]))

    # -- steering
    def _steer(self, cam, heading, tol, want, move=True, mag=1.0, cam_to=None):
        """The right stick turns the camera until a stick axis points along
        ``heading`` (``cam_to``: along that, as a flight's track before its
        run); analog: the left stick along ``heading`` at ``mag`` (the
        gate's most that way), under the camera predicted for the next tick;
        cardinal: the nearest axis, held only within ``tol`` degrees."""
        if cam_to is not None and self.analog:
            err = wrap(cam_to - cam)
            s = min(STICK, key=lambda k: abs(wrap(err - STICK[k])))
            res = wrap(err - STICK[s])
            want.add("rstick_right") if res > CAM_DEAD else want.add("rstick_left") if res < -CAM_DEAD else None
            if move and mag > 0:
                self.stick = inputs.stick(math.radians(heading), math.radians(self.cam), mag)
            return res
        err = wrap(heading - cam)
        s = min(STICK, key=lambda k: abs(wrap(err - STICK[k])))
        res = wrap(err - STICK[s])
        if res > CAM_DEAD:
            want.add("rstick_right")
        elif res < -CAM_DEAD:
            want.add("rstick_left")
        if self.analog:
            if move and mag > 0:
                self.stick = inputs.stick(math.radians(heading), math.radians(self.cam), mag)
        elif move and abs(res) <= tol:
            want.add(s)
        return res

    def _lookahead(self, pts, p, L):
        """The point L m ahead along the way-points from p's projection on
        the current segment (``self.seg`` advances past way-points reached;
        a first way-point the body already stands past, as after a landing
        beyond the landing sample, is skipped, not walked back to)."""
        if self.seg == 0 and len(pts) > 1:
            a, b = pts[0], pts[1]
            ab = (b[0] - a[0], b[1] - a[1])
            n2 = ab[0] ** 2 + ab[1] ** 2
            if n2 > 1e-9 and ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) > 0 and math.dist(p[:2], a[:2]) < 3.0:
                self.seg = 1
        while self.seg < len(pts) - 1:
            a = self.anchor if self.seg == 0 else pts[self.seg - 1]
            b = pts[self.seg]
            ab = (b[0] - a[0], b[1] - a[1])
            n2 = ab[0] ** 2 + ab[1] ** 2
            t = ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / n2 if n2 > 1e-9 else 1.0
            if t >= 1.0 or math.hypot(p[0] - b[0], p[1] - b[1]) < 0.5:
                self.seg += 1
                continue
            break
        a = self.anchor if self.seg == 0 else pts[self.seg - 1]
        b = pts[self.seg]
        ab = (b[0] - a[0], b[1] - a[1])
        n = math.hypot(*ab)
        t = max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / (n * n))) if n > 1e-6 else 1.0
        q = (a[0] + ab[0] * t, a[1] + ab[1] * t)
        off = math.hypot(p[0] - q[0], p[1] - q[1])
        rem, i, cur = L, self.seg, q
        while i < len(pts):
            nxt = pts[i]
            d = math.hypot(nxt[0] - cur[0], nxt[1] - cur[1])
            if d >= rem:
                return (cur[0] + (nxt[0] - cur[0]) * rem / d, cur[1] + (nxt[1] - cur[1]) * rem / d), off
            rem -= d
            cur = nxt
            i += 1
        return (pts[-1][0], pts[-1][1]), off

    # -- the tick
    def __call__(self, sb, row, rows):
        self.stick = (0.0, 0.0)
        if self.done:
            return self._set(set()) + ["stop"]
        self.k += 1
        p = feet(sb, row)
        st = row["state"]
        self.last = (p, st)
        self.states.add(st)
        if self.last_st in AIR and st not in AIR:
            self.land_k = self.k
        self.last_st = st
        if isinstance(row.get("hp"), int):
            if self.hp and row["hp"] < self.hp[-1] and self.k - self.land_k > 5:
                self.dmg.append((self.k, self.hp[-1] - row["hp"]))    # a hit or a hazard; a landing's fall damage isn't
            self.hp.append(row["hp"])
        if st == DEAD:
            self.finish("died")
            return self._set(set()) + ["stop"]
        if self.route is None:
            if self._plan(p, "start") is None:
                self.finish("no route from the start")
                return self._set(set()) + ["stop"]
        if self.press_left > 0:               # a pad's button, standing still
            self.press_left -= 1
            return self._set({self.press_btn})
        if self.at_goal(p, st):
            if not self.detours:
                self.finish("reached")
                return self._set(set()) + ["stop"]
            self._pad_done(p)                 # on a ride's pad: its button, then back to the target
            return self._set(set())
        cam, forced = read_input(sb)
        if forced:                            # carried: no input acts; wait, then replan from where it ends
            self.forced += 1
            self.leg_forced += 1
            self.best_k = self.k
            if self.forced > FORCED_MAX:
                self.finish(f"carried {self.forced} ticks by something the stick can't override")
                return self._set(set()) + ["stop"]
            return self._set(set())
        if self.forced:
            self.forced = 0
            self._replan(p, "carried off the route")
            if self.done:
                return self._set(set()) + ["stop"]
        self.cam = cam + (max(-6.0, min(6.0, wrap(cam - self.cam_prev))) if self.cam_prev is not None else 0.0)
        self.cam_prev = cam
        want: set = set()
        leg = self.leg
        if leg is None:                       # the route's end, short of the target (a partial route)
            self.finish("the route ends short of the target")
            return self._set(set()) + ["stop"]
        self.t += 1
        self.leg_states.add(st)
        if self._danger(p, st, row) or self.mode is not None:
            self._evade(sb, row, p, st, cam, want)
        else:
            act = leg.action
            if act in ("walk", "swim", "climb"):
                self._go(sb, row, p, st, cam, leg, want)
            elif act in ("jump", "flap", "drop"):
                self._fly(sb, row, p, st, cam, leg, want)
            elif act == "wait":
                self._ride(p, st, leg, want)
        if self.done:
            self.stick = (0.0, 0.0)
            return self._set(set()) + ["stop"]
        self.trace.append((self.k, p, st, self.li, tuple(sorted(want)), self.stick, cam, self.cam,
                           (row["vx"], row["vy"])))
        return self._set(want)

    def pad_hook(self, sb, regs) -> None:
        """At INPUT_BUILD: the stick for this tick into the active
        ControllerState, through the harness's one RAM pad writer."""
        sb.write_pad(l3.Pad(stick=self.stick), stick_only=True)

    def _set(self, want):
        acts = [f"up {b}" for b in sorted(self.held - want)] + [f"down {b}" for b in sorted(want - self.held)]
        self.held = set(want)
        if self.analog == "pipe" and self.stick != self.piped:   # the stick through the pipe, when it changes
            acts += [f"axis {n} {xo.pipe_axis(v):.6f}" for n, v, was in zip(("lx", "ly"), self.stick, self.piped)
                     if v != was]
            self.piped = self.stick
        return acts

    # -- rides
    def _ride(self, p, st, leg, want):
        """A ride (Step X.4): its pads first: off them, a detour to the
        nearest (a touch is standing there, an action pad X, a whack A; a
        magic hit or a joystick it can't give: the ride is banned); then
        stand on the deck; one that doesn't move in WAIT_TICKS is banned."""
        if self.t == 1:
            self.wait_from = p
            here = self.R.node_at(p, prefer_water=st == SWIM)
            for t in leg.trigger or ():
                if here in t["nodes"] and t["kind"] in PAD_BUTTON:
                    self.touched.add(t["atom"])
            todo = [t for t in leg.trigger or () if t["atom"] not in self.touched]
            if any(t["kind"] not in PAD_BUTTON for t in todo):
                return self._replan(p, f"the ride's pad needs {todo[0]['kind']}", ban_leg=True)
            if todo:
                t = todo[0]
                self.detours.append((self.target, (self.gmask, self.gp, self.band), t))
                self.target = t["nodes"]
                self.gmask, self.gp, self.band = self.R.goal(self.target)
                self._end_leg(f"to its pad {t['pad']}")
                if self._plan(p, f"to the ride's pad {t['pad']}") is None:
                    self._pad_back(p, "no route to the ride's pad")
                return
        self.best_k = self.k
        if math.dist(p, self.wait_from) > 1.0:
            self._replan(p, "ride over")
        elif self.t > WAIT_TICKS:
            self._replan(p, "the ride didn't move", ban_leg=True)

    def _pad_done(self, p):
        tgt, goal, t = self.detours[-1]
        self.touched.add(t["atom"])
        if PAD_BUTTON[t["kind"]]:
            self.press_btn, self.press_left = PAD_BUTTON[t["kind"]], 6
        self._end_leg(f"on its pad {t['pad']}")
        self._pad_back(p, f"touched {t['pad']}")

    def _pad_back(self, p, why):
        tgt, goal, t = self.detours.pop()
        self.target, (self.gmask, self.gp, self.band) = tgt, goal
        self.replans += 1
        if self.replans > self.max_replans:
            return self.finish(f"{why}; replans used up")
        if self._plan(p, why) is None:
            self.finish(f"{why}; no route from here")

    # -- fast HP loss: retreat, hold, replan around it
    def _danger(self, p, st, row) -> bool:
        """HP lost away from landings, at least max(30, 10 % of max) within
        DANGER_TICKS, with HP under DANGER_LOW of max: a healthy player presses on."""
        if self.mode is not None or self.retreats >= RETREATS or not self.dmg:
            return False
        cap = row.get("hp_max") if isinstance(row.get("hp_max"), int) else 400
        if sum(n for k, n in self.dmg if k > self.k - DANGER_TICKS) < max(DANGER_HP[0], DANGER_HP[1] * cap) \
                or self.hp[-1] > DANGER_LOW * cap:
            return False
        back = None
        for k, q, s_, *_ in reversed(self.trace):          # the last spot RETREAT_M back along the way it came
            if s_ in GROUND and math.dist(q, p) >= RETREAT_M:
                back = q
                break
        self.retreats += 1
        self.mode, self.mode_t, self.hit_at, self.back_to = "retreat", 0, p, back or p
        return True

    def _evade(self, sb, row, p, st, cam, want):
        self.mode_t += 1
        self.best_k = self.k
        if self.mode == "retreat":
            q = self.back_to
            d = math.hypot(q[0] - p[0], q[1] - p[1])
            if d < 0.6 or self.mode_t > RETREAT_TICKS:
                self.mode, self.mode_t = "hold", 0
            else:
                self._steer(cam, ang_of(q[0] - p[0], q[1] - p[1]), 25.0, want)
            return
        if self.mode_t >= HOLD_TICKS and st not in AIR:   # held: replan around where the hits came
            self.mode = None
            self.avoid.append((self.hit_at, 2.5))
            self._replan(p, "retreated from hits")

    # -- walking, swimming, climbing
    def _progress(self, p, st, want, ahead=None):
        """Stuck: no 0.3 m of progress in STUCK_TICKS ticks; sidestep
        (SIDE_TICKS, alternating sides), then hop once (Y held HOP_TICKS
        ticks, pushing on), then replan around a 1 m disc 1 m ahead (toward
        ``ahead``), the leg's region edge banned.  A hit's knock-back counts
        as no time."""
        rem = self.rest_m(p)
        if rem < self.best - 0.3 or st == HIT:
            self.best, self.best_k = min(rem, self.best), self.k
        if self.hop_left > 0:
            self.hop_left -= 1
            want.add("y")
            return
        if self.k - self.best_k > STUCK_TICKS:
            self.best_k = self.k
            if self.unstick == 0 and self.analog and st in GROUND:
                self.unstick, self.side_left = 1, SIDE_TICKS
                self.sides += 1
            elif self.unstick <= 1 and st in GROUND + (SWIM,):
                self.unstick, self.hop_left = 2, HOP_TICKS
                self.hops += 1
                want.add("y")
            else:
                if ahead is not None:
                    d = math.hypot(ahead[0] - p[0], ahead[1] - p[1])
                    if d > 1e-6:
                        self.avoid.append(((p[0] + (ahead[0] - p[0]) / d, p[1] + (ahead[1] - p[1]) / d, p[2]), 1.0))
                self._replan(p, "stuck", ban_leg=True)

    def _go(self, sb, row, p, st, cam, leg, want):
        pts = leg.pts
        if st in AIR:                          # walked off: steer on toward the way-point
            look, off = self._lookahead(pts, p, LOOK_M.get(leg.action, 1.2))
            self._steer(cam, ang_of(look[0] - p[0], look[1] - p[1]), 25.0, want)
            return
        last = self.li == len(self.route.legs) - 1
        end = pts[-1]
        dend = math.hypot(end[0] - p[0], end[1] - p[1])
        if last and self.gp is not None and self.route.reached and (self.final or dend < self.tol + 0.1):
            self.final = True                 # the route's end: straight on to the target point itself
            d = math.hypot(self.gp[0] - p[0], self.gp[1] - p[1])
            v = math.hypot(row["vx"], row["vy"])
            brake = d < self.tol * 0.5 + (0.6 if v > 5 else 0.25 if v > 2 else 0.0)
            self._steer(cam, ang_of(self.gp[0] - p[0], self.gp[1] - p[1]), 25.0, want, move=not brake,
                        mag=max(0.2, min(1.0, d / 1.5)))
            self._progress(p, st, want, self.gp)
            return
        nxt_act = None if last else self.route.legs[self.li + 1].action
        reach_m = self.tol if last else 1.5 if nxt_act in ("climb", "wait") else 0.6   # a climb's foot is at a face
        if dend < reach_m and abs(end[2] - p[2]) < 1.5:
            nxt = self.route.legs[self.li + 1] if not last else None
            if nxt is None:
                if not self.route.reached:
                    self.finish("the route ends short of the target")
                return              # at the end: at_goal decides (a stop by the target)
            self._next_leg(p)
            if nxt.action in ("jump", "flap", "drop"):
                self._fly(sb, row, p, st, cam, nxt, want)
            else:
                self._go(sb, row, p, st, cam, nxt, want)
            return
        look, off = self._lookahead(pts, p, LOOK_M.get(leg.action, 1.2))
        a, b = (self.anchor if self.seg == 0 else pts[self.seg - 1]), pts[self.seg]
        n2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
        t = max(0.0, min(1.0, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / n2)) if n2 > 1e-9 else 1.0
        away = (st in GROUND + (4,) and leg.action == "walk"
                and (off > OFF_ROUTE_M or abs(p[2] - (a[2] + (b[2] - a[2]) * t)) > 2.0))
        if st in SLOPE and self.t <= SLIDE_TICKS and self.li and self.route.legs[self.li - 1].action in (
                "jump", "flap", "drop"):
            away = False                          # slid after a landing: walk back up first (below, toward `look`)
            self.slid += 1
        self.off_n = self.off_n + 1 if away else 0
        if not away and st in (0, 0x100):
            self.on_route = (p, look)
        if self.off_n >= OFF_TICKS:               # beside it, or fallen (slid) off it, for OFF_TICKS ticks: replan
            if self.on_route is not None:         # around where it left the route
                q, lk = self.on_route
                d = math.hypot(lk[0] - q[0], lk[1] - q[1])
                if d > 1e-6:
                    self.avoid.append(((q[0] + (lk[0] - q[0]) / d, q[1] + (lk[1] - q[1]) / d, q[2]), 1.0))
            self._replan(p, "off the route")
            return
        heading = ang_of(look[0] - p[0], look[1] - p[1])
        if self.side_left > 0:                    # unsticking: a sidestep, alternate sides
            self.side_left -= 1
            heading = wrap(heading + (90.0 if self.sides % 2 else -90.0))
        v = math.hypot(row["vx"], row["vy"])
        tol = 12.0 if leg.clear == 0 else 25.0
        brake = last and dend < self.tol + (0.6 if v > 5 else 0.25 if v > 2 else 0.05)
        mag = 1.0 if not last else max(0.25, min(1.0, dend / 1.5))
        if leg.action == "climb" and st in (0, 0x100) and self.t % CLIMB_HOP == CLIMB_HOP // 4:
            self.hop_left = HOP_TICKS             # a climb starts in the air (its checks run in the air and swim
                                                  # ticks, 0x897A0, 0x8D346): hop into the face, pushing on
        if nxt_act == "drop" and dend < 2.0:      # a walk-off at a walk (x4: e2.Z415's met its edge at 6.7 m/s)
            mag = min(mag, max(0.4, dend / 2.0))
        runup = nxt_act in ("jump", "flap") and dend < 3.0          # a flight's run-up: at speed (x4: e2.Z028's
        if leg.action == "walk" and not runup and min(self._floor_nz(p), self._floor_nz((look[0], look[1], p[2]))) \
                < STEEP_NZ:                                          # crept up at 2.7 m/s and slid off its edge)
            mag = min(mag, STEEP_MAG)
        cam_to = None
        if runup:                                 # the camera along the flight's track by its takeoff (full stick)
            f = self.route.legs[self.li + 1]
            q = f.pts[-1]
            cam_to = ang_of(q[0] - f.at[0], q[1] - f.at[1])
        self._steer(cam, heading, tol, want, move=not brake, mag=mag, cam_to=cam_to)
        if st == CLIMB and self.analog:           # on the wall: stick up (x4: a camera-relative push into the face
            self.stick = (0.0, 1.0)               # turned sideways on w2's climb and it stalled)
        self._progress(p, st, want, look)

    def _floor_nz(self, p) -> float:
        """The floor's normal z under p when it is a border sample (1.0 inside a floor, in water, or off it)."""
        v = self.R.locate(p)
        return float(self.R.nz[v]) if 0 <= v < self.R.ns and self.R.clear[v] == 0 else 1.0

    # -- flights
    def _fly(self, sb, row, p, st, cam, leg, want):
        """A jump, flap or drop leg: align, run along the track, press Y at
        ``at`` (no Y for a drop), steer in the air to the landing; landed on
        the leg's node (or within 1.5 m of the landing): next leg, else replan."""
        at, q = leg.at, leg.pts[-1]
        d = math.hypot(q[0] - at[0], q[1] - at[1])
        u = ((q[0] - at[0]) / d, (q[1] - at[1]) / d) if d > 1e-6 else (0.0, 1.0)
        track = ang_of(*u)
        if self.aim is None:
            # land up to 1 m past the landing sample (half the floor beyond it).  The takeoff speed: a lip lift
            # and a gap at full speed (the window and the envelope's gap tables assume it); onto a ledge with no
            # gap, or a walk-off, no faster than reaches the landing with the kit's jump (h 1.1, 1.2 with air
            # power) or the fall: the air control can't stop a 7 m/s run
            depth = self.R.run_on(q, u, leg.node)[0] if 0 <= leg.node < self.R.w.nreg else 0.0
            self.aim = (q[0] + u[0] * min(depth / 2, 1.0), q[1] + u[1] * min(depth / 2, 1.0), q[2])
            ac = row.get("air_ctl") if isinstance(row.get("air_ctl"), float) else 9.0
            vz0 = 0.0 if leg.action == "drop" else math.sqrt(2 * G * (1.2 if ac > 10.5 else 1.1))
            t = (vz0 + math.sqrt(max(vz0 * vz0 - 2 * G * (q[2] - at[2]), 0.0))) / G
            want_m = math.hypot(self.aim[0] - at[0], self.aim[1] - at[1])
            gap = leg.edge.get("gap_edge", 0.0) if leg.edge else 0.0
            if leg.lip or (leg.action != "drop" and gap > 1.0) or leg.action == "flap":
                self.v_take = 7.0
            else:
                self.v_take = min(7.0, max(2.5, want_m / max(t, 1e-3)))
            self.fl = {"v_take": round(self.v_take, 2), "want_m": round(want_m, 2), "track_m": round(d, 2),
                       "dh": round(q[2] - at[2], 2)}
        q = self.aim
        if self.phase == "go":
            proj = (p[0] - at[0]) * u[0] + (p[1] - at[1]) * u[1]
            if st in AIR and proj < -1.0 and row["vz"] > -2.0:
                self._steer(cam, track, 40.0, want, move=False)   # still falling into place: wait for the ground
                return
            if st in AIR:
                self._takeoff(p, row, at, u)
                self.phase, self.air_t = "air", 0         # walked off at the takeoff
            else:
                side = abs((p[0] - at[0]) * -u[1] + (p[1] - at[1]) * u[0])
                if self.back is None:                     # the run-up: up to 1.5 m of floor behind the takeoff
                    self.back = next((b_ for b_ in RUN_M if self.R.line_ok(
                        (at[0] - u[0] * b_, at[1] - u[1] * b_, at[2]), at, swim=False)), 0.0)
                    v0 = math.hypot(row["vx"], row["vy"])
                    if self.v_take >= 6.0 and v0 < self.v_take - 2.0 and proj > -self.back + 0.5 and self.back >= 1.0:
                        self.phase = "back"               # slow and near the takeoff: back up for a run first
                if self.phase == "back":
                    if proj <= -self.back + 0.25 or self.t > 60:
                        self.phase = "go"
                    else:
                        tgt = (at[0] - u[0] * self.back, at[1] - u[1] * self.back)
                        self._steer(cam, ang_of(tgt[0] - p[0], tgt[1] - p[1]), 20.0, want, mag=0.5)
                        return
                if proj < -2.5 or side > 1.0:      # off its track: a walk on the floor to its run-up, not a beeline
                    if self.analog:                # (x4: e2's drops walked off a side edge on the way, then died)
                        return self._replan(p, "off the flight's track", ban_leg=True)
                    tgt = (at[0] - u[0] * max(self.back, 1.0), at[1] - u[1] * max(self.back, 1.0))
                    self._steer(cam, ang_of(tgt[0] - p[0], tgt[1] - p[1]), 20.0, want)
                    self._progress(p, st, want)
                    return
                # on its track: run along it (aiming 2 m ahead on it, so drift is corrected) at the takeoff speed;
                # Y down `lead` m before the takeoff (a drop walks off along it)
                lead = LEAD_M.get(leg.kind if leg.kind == "step" else leg.action, 0.15)
                if leg.lip:
                    lead = RIM_LEAD_M if leg.lip.get("floor_m", 1.0) < 0.3 else LEAD_M["jump"]
                aim = (at[0] + u[0] * (proj + 2.0), at[1] + u[1] * (proj + 2.0))
                v = math.hypot(row["vx"], row["vy"])
                fast = v > self.v_take + 0.5
                res = self._steer(cam, ang_of(aim[0] - p[0], aim[1] - p[1]), 8.0, want,
                                  move=not fast or self.analog, mag=self.v_take / 7.0)
                lined = (abs(res) <= 8.0) if not self.analog else (
                    v < 1.0 or abs(wrap(ang_of(row["vx"], row["vy"]) - track)) <= (6.0 if leg.lip else 20.0))
                late = max(0.1, leg.lip["before_m"] - leg.lip["window_m"][0] - 0.25) if leg.lip else 0.1
                if leg.action != "drop" and proj >= -lead - v / 60 and (lined or proj >= late):   # Y acts a tick later
                    want.add("y")
                    self.y_down = 1
                    self.phase = "press"
                self._progress(p, st, want)
                return
        if self.phase == "press":
            self.y_down += 1
            want.add("y")
            self._steer(cam, track, 30.0, want, mag=self.v_take / 7.0)
            if st in AIR:
                self._takeoff(p, row, at, u)
                self.phase, self.air_t = "air", 0
            elif self.y_down > 8:                # never left the ground: try again
                self.phase = "go"
                self._progress(p, st, want)
            return
        # in the air
        self.air_t = (self.air_t or 0) + 1
        self._arc(p, row)
        dx, dy = q[0] - p[0], q[1] - p[1]
        dist = math.hypot(dx, dy)
        if st not in AIR and self.air_t > 2:
            here = self.R.node_at(p, prefer_water=st == SWIM)
            self.fl["land"] = p
            if here == leg.node or dist < 1.5 and abs(q[2] - p[2]) < 1.0:
                self._next_leg(p, "landed")
            else:
                self._replan(p, "missed the landing", ban_leg=True)
            return
        if self.air_t < 3 and leg.action != "drop":
            want.add("y")                         # the press, held over the takeoff
        heading = ang_of(dx, dy) if dist > 0.3 else track
        n = rt_mod.fall_ticks(row["vz"], p[2] - q[2])
        ac = row.get("air_ctl") if isinstance(row.get("air_ctl"), float) and row["air_ctl"] > 0 else 9.0
        if self.analog:
            # the air-control target that lands the body on the aim in the n ticks left to come down (the tick
            # under way still holds the last target: one tick of input latency); a lip lift pushes on into its
            # face at full stick until the lift has the body over the ledge (x4: f6.Z609's then overshot it), and
            # a body that can't come down there any more pushes on toward it
            mag, need = 1.0, math.inf
            if n > 1 and (not leg.lip or p[2] > q[2] + 0.05):
                T0 = self.air_T
                v1 = (T0[0] + (row["vx"] - T0[0]) * rt_mod.AIR_F, T0[1] + (row["vy"] - T0[1]) * rt_mod.AIR_F)
                tx, ty = rt_mod.air_target(dx - v1[0] / 30, dy - v1[1] / 30, v1[0], v1[1], n - 1)
                need = math.hypot(tx, ty) / ac
                heading, mag = (ang_of(tx, ty), min(need, 1.0)) if need > 1e-3 else (heading, 0.0)
            self._steer(cam, heading, 40.0, want, move=mag > 0, mag=mag)
            sx, sy = self.stick                   # the target this stick gives, in the world (for the next tick)
            h = math.radians(self.cam + math.degrees(math.atan2(-sx, sy)))
            self.air_T = (-math.sin(h) * math.hypot(sx, sy) * ac, math.cos(h) * math.hypot(sx, sy) * ac)
        else:
            # X.2's cardinal stick: push on, coast or brake by which lands nearest the aim
            toward = (row["vx"] * dx + row["vy"] * dy) / max(dist, 1e-6)
            n = float(n)
            geo = rt_mod.AIR_F * (1 - rt_mod.AIR_F ** n) / (1 - rt_mod.AIR_F) / 30.0
            go = {T: T * n / 30.0 + (toward - T) * geo for T in (ac, 0.0, -ac)}
            need = 0.0 if go[ac] >= dist - 0.3 else math.inf
            move = dist > 0.25
            if n and p[2] >= q[2] + 0.2:
                T = min(go, key=lambda T_: abs(go[T_] - dist))
                if T < 0:
                    heading = wrap(heading + 180.0)
                move = move and T != 0.0
            self._steer(cam, heading, 40.0, want, move=move)
        if leg.action == "flap" and self.air_t >= 4 and row["vz"] < 0.5 and "y" not in self.held:
            past = (p[0] - q[0]) * u[0] + (p[1] - q[1]) * u[1] > 0.0      # over the aim already: come down
            short = not past and (not n or (p[2] < q[2] + 0.2 and row["vz"] < 0) or need > 1.0)
            budget = row.get("flaps") if isinstance(row.get("flaps"), int) else 0
            if short and sb.read_i32(row["ent"] + FLAPS_USED) < budget:
                want.add("y")                     # a fresh Y edge; released the next tick

    def _takeoff(self, p, row, at, u):
        self.fl.update(take=p, take_k=self.k, u=u, top=p[2], arc=[],
                       take_off_m=round((p[0] - at[0]) * u[0] + (p[1] - at[1]) * u[1], 2),
                       take_side_m=round((p[0] - at[0]) * -u[1] + (p[1] - at[1]) * u[0], 2),
                       take_v=round(math.hypot(row["vx"], row["vy"]), 2), take_vz=round(row["vz"], 3))

    def _arc(self, p, row):
        f = self.fl
        if "take" not in f:
            return
        o, u = f["take"], f["u"]
        f["top"] = max(f["top"], p[2])
        f["arc"].append([self.k - f["take_k"], round((p[0] - o[0]) * u[0] + (p[1] - o[1]) * u[1], 3),
                         round((p[0] - o[0]) * -u[1] + (p[1] - o[1]) * u[0], 3), round(p[2] - o[2], 3),
                         round(row["vz"], 3), row["state"]])

    # -- the trace log (P7)
    def _log_leg(self, leg, how):
        """One JSONL line for ``leg``: planned against actual, no coordinates."""
        if not self.log or (len(self.plans), self.li) in self.logged:
            return
        self.logged.add((len(self.plans), self.li))
        e = leg.edge or {}
        rec = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "label": self.label, "level": self.R.R.name,
               "prof": self.R.prof, "target": self.target if isinstance(self.target, str) else "point",
               "tier": self.kw["tier"], "air": self.kw["air"], "analog": self.analog, "plan": len(self.plans) - 1,
               "leg": self.li, **leg.summary(), "how": how, "ticks": self.t,
               "hp_lost": (self.leg_hp0 - self.hp[-1]) if self.hp and self.leg_hp0 is not None else None,
               "states": sorted(hex(s) for s in self.leg_states), "forced_ticks": self.leg_forced}
        if e:
            rec["edge"] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in e.items()
                           if k in ("kind", "conf", "ranks", "kit", "dh", "gap", "gap_edge", "profile", "fall", "lip",
                                    "face_m", "why", "via")}
        f = self.fl
        if leg.action in ("jump", "flap", "drop"):
            rec["planned"] = {k: f[k] for k in ("v_take", "want_m", "track_m", "dh") if k in f}
            if "take" in f:
                land = f.get("land") or (self.last[0] if how == "reached" else None)
                aim = self.aim
                rec["actual"] = {"take_off_m": f["take_off_m"], "take_side_m": f["take_side_m"], "take_v": f["take_v"],
                                 "take_vz": f["take_vz"], "apex_m": round(f["top"] - f["take"][2], 3),
                                 "air_ticks": len(f["arc"]),
                                 "land_err_m": None if land is None or aim is None else
                                 round(math.hypot(land[0] - aim[0], land[1] - aim[1]), 2),
                                 "land_dz": None if land is None or aim is None else round(land[2] - aim[2], 2)}
                rec["arc"] = f["arc"]
        elif self.leg_k0 is not None and self.trace:
            walked = [q for k, q, *_ in self.trace if k >= self.leg_k0]
            m = sum(math.dist(a, b) for a, b in zip(walked, walked[1:]))
            rec["actual"] = {"m": round(m, 1), "mps": round(m / max(self.t, 1) * 30, 2), "slid": self.slid}
        with open(self.log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")

    # -- the summary
    def result(self, rows, dialogs: int) -> dict:
        p, st = self.last if self.last else (None, None)
        left = None if p is None else self.left_m(p)
        return {"reached": self.why == "reached", "why": self.why or "ticks used up",
                "left_m": None if left is None or math.isnan(left) else round(left, 1),
                "end_zone": None if p is None else self.R.zone_at(p, prefer_water=st == SWIM),
                "end_state": st, "ticks": len(rows), "replans": self.replans, "hops": self.hops,
                "sidesteps": self.sides, "retreats": self.retreats, "dialogs": dialogs, "analog": self.analog,
                "legs": self.legs_done + ([{**self.leg.summary(), "how": "last", "ticks": self.t}]
                                          if self.leg is not None else []),
                "plans": self.plans, "states": sorted(hex(s) for s in self.states),
                "hp": [self.hp[0], self.hp[-1], min(self.hp)] if self.hp else None}


def clear_dialog(sb, tries: int = 4) -> bool:
    """A dialog or cutscene stops the player tick: press A (real input)
    until the tick runs; halted at it."""
    for _ in range(tries):
        sb.press("a", seconds=0.3)
        time.sleep(0.8)
        if sb.wait_bp([xo.PLAYER_TICK], 3.0) == xo.PLAYER_TICK:
            return True
    return False


def plan(sb, router, target, **kw):
    """The route from the player's spot (halted at a player tick) to ``target``, without moving."""
    if sb.wait_bp([xo.PLAYER_TICK], 5.0) != xo.PLAYER_TICK:
        raise SystemExit("no player tick to plan from")
    g = sb.g
    ent = g.u32(g.regs()["esp"] + 4)
    return router.plan(feet(sb, {"ent": ent}), target, **kw)


def walk_to(sb, router, target, *, ticks: int = 1800, label: str | None = None, max_dialogs: int = 4,
            **kw) -> dict:
    """Walk to ``target`` (the module docstring); ``kw`` goes to
    :class:`Pilot` (tier, air, tol, allow_probe: by default the level's
    admitted probe classes, gates_open, analog: True, "pipe" or False,
    log). The captures (positions: keep them private) go to the sandbox's
    out folder under ``label``. Returns :meth:`Pilot.result`."""
    global last_pilot
    pil = last_pilot = Pilot(router, target, label=label, **kw)
    hooks = {xo.INPUT_BUILD: pil.pad_hook} if pil.analog is True else None   # "pipe": the pipe's axis lines
    rows, dialogs = [], 0
    while len(rows) < ticks and not pil.done:
        cap = sb.capture(ticks - len(rows), on_tick=pil, hooks=hooks, label=label and f"{label}-{dialogs}")
        rows += cap["rows"]
        if pil.done or cap["meta"]["complete"]:
            break
        dialogs += 1
        if dialogs > max_dialogs or not clear_dialog(sb):
            pil.finish(f"the player tick stopped: {cap['meta']['stop']}")
            break
        pil.held, pil.piped = set(), (0.0, 0.0)   # the capture's end let go of the buttons and the piped stick
    if not pil.done:
        pil.finish("ticks used up")
    return pil.result(rows, dialogs)


if __name__ == "__main__":
    sys.exit("devkit/xemu/route.py is a library for sitting scripts: see its docstring")
