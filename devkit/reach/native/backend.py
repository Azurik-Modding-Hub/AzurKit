"""Step R2.19d: the native kernel (:mod:`devkit.reach.native`) as the reach engine's launch backend
(``devkit/reach/reach_engine.py --backend kernel``; the R2.19 plan's §1, D845, D846).

What runs where (a pool worker with FastL3 once :func:`install` has run; each job on a :class:`KernelSim` over it):

- a job's placements (R6's tick and the 20-tick settle), its kit (as state: the armor's Flaps, the cast's gauge), its
  camera align and each launch: the kernel, under the engine's own controllers (``runner.find_start``,
  ``macros.launches``, ``aim.Aim``, ``aim.Sched``: unchanged, so its pads are the controllers' answer to the kernel's
  rows); the witness keeps every pad, the align's too.  Since Step R2.19p a launch family runs in C (:func:`c_launches`:
  ``controllers.c``'s copy of ``macros.launches`` and the three controllers, one call a family, its outcome the same
  record :func:`outcome` makes of the Python run's rows; :data:`SHADOWS` pins the Python sources it copies and
  :func:`install` refuses while one has moved), unless ``AZURIK_REACH_CONTROLLERS=py`` (:data:`CONTROLLERS`: the
  Python controllers, the reference) or the family is one it has no copy of (it then runs in Python);
- an aim's floor scans and other starts (:func:`floor`, :func:`other_starts`): the kernel's scan picks the point (it
  orders the work), FastL3 answers whether a floor is there (that point, else its own scan), so the floors a record
  names (``floor``, ``from_floor``: the verdicts' "no L3 floor") are L3's;
- a placement, kit or align the kernel flags: run whole on FastL3 (the placement and the steps logged since), the
  start and every launch from it L3's (``by`` "l3");
- a launch the kernel flags: run on FastL3, with the others of its family that flag (``macros.launches``' shared
  ticks), from its start's FastL3 twin (:meth:`KernelSim.on_l3`: the placement and its logged steps run on FastL3;
  none when L3 doesn't stand the start where the kernel did), its outcome L3's own (``by`` "l3").  A flag is a stop
  (a state the kernel doesn't port, a water or push volume that moves or switches, a step-up, a lip lift, a catch, a
  climb, a roll: ``kernel.c``'s header) or a law it notes and doesn't port (ice), raised as :class:`Flagged` on
  that tick, so ``macros.launches`` ends the launches sharing the tick with ``fault:kernel:<why>`` (:data:`FLAG`);
- a kernel outcome (``by`` "kernel"; :func:`outcome`: no labels, volumes or picks) is a candidate and counts in no
  link until FastL3 confirms it (D845): :func:`confirm` runs its string again from the snapshot (R6 at its start,
  its kit, its pads) and ``hold.HOLD`` idle ticks on, and re-derives the outcome from L3's rows (``runner.outcome``:
  its end, where it settled and first touched down, HP, flaps, trick labels, volumes, picks, taint and witness
  hash; none where L3 doesn't stand its start, ``runner.find_start``'s rule).  An aim's hit is confirmed as it is
  found (``aim.run_job``'s hold): its outcome is L3's after (``by`` "confirmed"); every other zone witness when the
  graph holds it (``graph.Graph.hold``), its answer the hold's, cached, carrying the re-derived fields (``outcome``)
  the graph's witness takes.  ``same`` in a confirm's answer: L3's string ends settled at the kernel's air rank or
  under.  Every hold answer on this route names the movers its body path touches (:class:`Movers`, the mover-contact
  router: ``route``).  A confirm runs on the worker's timed FastL3 (``reach_engine.worker.timed``): a step stopped
  for time raises, never an answer (AZ-813).

The drift audit (PLAN-v2 §1.6): about 1 job in :data:`DRIFT_EVERY` (by key) has each kernel launch that settled run
again on FastL3 (:func:`confirm` without the hold, nothing replaced); one whose L3 string ends over :data:`END_M`
from the kernel's landing is silent drift, kept in the record's ``drift``.  ``devkit/reach/reach_engine.py run`` sums it
by level stage and names a stage over :data:`DRIFT_MAX`.

A record's ``kernel`` holds its launches' counts: run on the kernel, flagged (by why) and their ticks on each side.
A kernel record's key (:func:`key`) is its job's L3 key and the kernel's (:func:`kernel_sha12`: ``kernel.c``,
``controllers.c``, this package, the geometry decode, the compiler and its flags, the host's machine; not which
controllers ran: the records are the same) and the snapshot's census
(:func:`census`: the platforms the game's world doesn't hold there, left out of the kernel's).  Positions stay in
memory and the private cache.
"""

from __future__ import annotations

import ctypes
import functools
import hashlib
import inspect
import json
import math
import os
import platform
import struct
from pathlib import Path
from typing import NamedTuple

from devkit.reach import native as N
from devkit.reach.engine import cache, hold, runner, worker
from devkit.reach.engine.macros import AIRBORNE, DEAD, KITS, SWIMMING, launches, min_rank
from devkit.sim import l3
from devkit.sim.l3 import L3Error, Pad, Row
from devkit.sim.obs import Obs, settled

FLAG = "fault:kernel"      # a launch end the kernel flagged (``macros._stepped``'s fault end, :class:`Flagged`'s site)
END_M = 0.5                # [proposal, R2.17's] a kernel landing this near L3's is the same find
DRIFT_EVERY = 100          # [PLAN-v2 §1.6] about 1 job in this many is drift-audited (by key)
DRIFT_MAX = 0.02           # [PLAN-v2 §1.6] a level stage's silent drift over this share goes to FastL3
FILES = ("devkit/reach/native/kernel.c", "devkit/reach/native/controllers.c", "devkit/reach/native/__init__.py",
         "devkit/reach/native/backend.py", "src/azurkit/tools/randomizer/draft/geometry.py",
         "src/azurkit/tools/randomizer/art/collision.py")   # the kernel's code and the geometry it decodes
CONTROLLERS = os.environ.get("AZURIK_REACH_CONTROLLERS", "c")   # "c": launch families in C (:func:`c_launches`);
                                                                 # "py": the Python controllers, the reference
_SPEC: dict = {}           # this worker's level, census and targets file (:func:`install`)
_WORLD: dict = {}          # the worker's kernel world and movers (:func:`world`, :func:`movers`)
_COST: dict = {}           # this job's kernel counts (:func:`run_macros`), moved into its record


class Flagged(L3Error):
    """The kernel reached what it doesn't port (the module docstring): its launch goes to FastL3."""


@functools.cache
def kernel_sha12() -> str:
    """sha256[:12] of the kernel's code (:data:`FILES`, each ``cache.code_bytes``: no comment or docstring moves
    it), the compiler's version and flags and the host's machine; once per process (every kernel job's key asks
    for it, and tokenising the code costs about 50 ms)."""
    root = Path(__file__).resolve().parents[3]
    h = hashlib.sha256(f"{N.zig_version()} {' '.join(N.FLAGS)} {platform.machine()}\n".encode())
    for rel in FILES:
        h.update(f"{rel}\n".encode() + cache.code_bytes(root / rel))
    return h.hexdigest()[:12]


def key(job_key: str, census12: str) -> str:
    """A kernel record's key: its job's L3 key (``cache.job_key``), :func:`kernel_sha12` and the census's sha12."""
    doc = {"job": job_key, "kernel": kernel_sha12(), "census": census12}
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:12]


# -- the census -----------------------------------------------------------------------------------------------------

CENSUS_SWEEP = 0x60870     # collision_sweep(world, critter, dt, from, to, rh, rv, flags, out)


def census_of(sim, level) -> dict:
    """Which of ``level``'s (``geometry.Level``) present solid platforms the game's collision world holds at ``sim``'s
    snapshot (L3's own ``collision_sweep`` on the player's world, a body swept into up to 3 of each one's largest
    faces from 1.6 m in front to 0.2 m behind): ``absent`` the owners no sweep met where one reached the face's
    plane, with counts (``present``, ``unclear``: kept)."""
    import numpy as np

    from azurkit.tools.randomizer.draft.geometry import CAT_PSTATIC, CAT_RIG, CAT_TOGGLE
    from azurkit.tools.randomizer.art import collision
    buf = l3._STACK + 0x8000
    critter = sim.u32(sim.entity + 0x20)
    world = sim.u32(sim.u32(critter + 0x154) + 0xAC)

    def f32(x):
        return struct.unpack("<I", struct.pack("<f", x))[0]

    def sweep(a, b):
        sim.write(buf, struct.pack("<3f", *a))
        sim.write(buf + 0x10, struct.pack("<3f", *b))
        sim.write(buf + 0x20, bytes(0x60))
        sim._run(CENSUS_SWEEP, (world, critter, f32(1.0 / 30), buf, buf + 0x10, f32(0.5), f32(1.0), 0x10, buf + 0x20),
                 {}, 2_000_000)
        rec = sim.read(buf + 0x20, 0x48)
        return (sim.uc.reg_read(l3.X.UC_X86_REG_EAX) & 0xFF, struct.unpack_from("<f", rec, 0x18)[0],
                struct.unpack_from("<I", rec, 0x38)[0])

    cats = (CAT_PSTATIC, CAT_RIG, CAT_TOGGLE)
    owners = [o["oi"] for o in level.owners if o["kind"] != "levl" and o["cat"] in cats and o["present"]
              and (o["word"] or 0) & collision.W_SOLID]
    sim.reset()
    c = struct.unpack("<3f", sim.read(critter + 0x15C, 12))
    static = sweep(c, (c[0], c[1], c[2] - 3.0))[2]          # the static level's object: the one under the snapshot
    absent, seen, unclear = [], 0, 0
    for oi in owners:
        P = level.P[level.tris_of(oi)]
        n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
        area = np.linalg.norm(n, axis=1)
        met = miss = False
        for j in np.argsort(-area)[:3]:
            if area[j] <= 1e-9:
                continue
            nn, cen = n[j] / area[j], P[j].mean(axis=0)
            a, b = cen + nn * 1.6, cen - nn * 0.2
            sim.reset()
            try:
                hit, t, obj = sweep(tuple(a), tuple(b))
            except L3Error:
                continue
            d = float(np.dot((a + (b - a) * t) - cen, nn)) if hit else -1.0
            if hit and obj and obj != static and d <= 1.35:
                met = True
                break
            if not hit or d < 0.45:
                miss = True
        seen += met
        if not met and miss:
            absent.append(int(oi))
        unclear += not met and not miss
    sim.reset()
    return {"absent": absent, "platforms": len(owners), "present": seen, "unclear": unclear}


def census(level: str, snap: dict, sim_of) -> tuple[dict, str]:
    """The snapshot ``snap``'s census (:func:`census_of`), made once per snapshot and census code into the level's
    cache folder (``sim_of()`` an L3 on it, asked only then); it and its sha12."""
    from devkit.sim.ports import vanilla_iso
    from azurkit.tools.randomizer.draft.geometry import Level
    code = cache.code_sha12(Path(__file__))
    p = cache.folder(level) / f"census-{snap['meta_sha12']}-{code}.json"
    if not p.exists():
        cache.write(p, census_of(sim_of(), Level.read(vanilla_iso(), level)) | {"level": level})
    doc = json.loads(p.read_text(encoding="utf-8"))
    return doc, cache.sha12(sorted(doc["absent"]))


# -- the mover-contact router (PLAN-v2 §1.5b) ----------------------------------------------------------------------

NEAR_M = 2.0               # [proposal, PLAN-v2 §1.5b] a pass this near an unrecorded mover's load pose: near_parked_rig
PROBE_M = 0.05             # each tick's body also swept this far up and down through where it is: a face it rests on
                           # (the kernel's sweep meets only faces it moves into)


class Movers:
    """The owners the derive or the census calls moved or toggled (``geometry.Level``: a rig, a toggled solid, or a
    platform the census finds the game's world doesn't hold at the snapshot), their load-pose triangles both ways
    round as two kernel worlds: the body's (0.5 / 1.0 m) and one grown by :data:`NEAR_M`.  :meth:`route` names the
    ones a witness's body path touches and passes near.  No mover's pose over time is recorded yet (R2.19h1's
    recorder): contact at the load pose routes a link (a known flaw, D610, bounded by D847's parking)."""

    def __init__(self, P, owner, kind) -> None:
        import numpy as np
        P = np.asarray(P, np.float64).reshape(-1, 3, 3)
        self.owner = np.concatenate([np.asarray(owner, np.int64)] * 2)
        self.kind = dict(kind)                 # owner -> "rig" | "gate"
        both = np.concatenate([P, P[:, ::-1]]) if len(P) else np.zeros((0, 3, 3))
        words = np.full(len(both), 0x8050, np.int32)
        self.body = N.World(both, words) if len(both) else None
        self.grown = N.World(both, words, (N.RH + NEAR_M) / (N.RV + NEAR_M)) if len(both) else None

    @classmethod
    def of(cls, level, absent) -> Movers:
        """``level``'s movers (the class docstring), ``absent`` the census's owners."""
        import numpy as np

        from azurkit.tools.randomizer.draft.geometry import CAT_RIG, CAT_TOGGLE
        gone = set(absent)
        kind = {o["oi"]: "gate" if o["cat"] == CAT_TOGGLE else "rig" for o in level.owners
                if o["kind"] != "levl" and (o["cat"] in (CAT_RIG, CAT_TOGGLE) or o["oi"] in gone)}
        tris = np.nonzero(np.isin(level.tri_owner, list(kind)))[0] if kind else np.zeros(0, np.int64)
        return cls(level.P[tris], level.tri_owner[tris], kind)

    def route(self, path) -> dict:
        """The movers the body swept along ``path`` (body centres a tick apart) touches, by kind (``rigs``: a rig
        or a platform the snapshot doesn't hold, the link routed to R2.19h1 or parked; ``gates``: a toggled solid,
        the link owing its open condition), and the rigs it passes within :data:`NEAR_M` of untouched (``near``);
        owner ids, empty lists when none."""
        out = {"rigs": set(), "gates": set(), "near": set()}
        if self.body is None or not path:
            return {k: [] for k in out}
        for a, b in zip(path, list(path[1:]) + [path[-1]]):
            down = ((b[0], b[1], b[2] + PROBE_M), (b[0], b[1], b[2] - PROBE_M))   # a body at rest on a deck
            for c in (self.body.sweep(a, b), self.body.sweep(*down)):
                if c is not None:
                    oi = int(self.owner[c.tri])
                    out["rigs" if self.kind[oi] == "rig" else "gates"].add(oi)
            for c in (self.grown.sweep(a, b, N.RH + NEAR_M, N.RV + NEAR_M),
                      self.grown.sweep(*down, N.RH + NEAR_M, N.RV + NEAR_M)):
                if c is not None and self.kind[oi := int(self.owner[c.tri])] == "rig":
                    out["near"].add(oi)
        out["near"] -= out["rigs"]
        return {k: sorted(v) for k, v in out.items()}


def movers() -> Movers:
    """This worker's level's :class:`Movers` (once a process)."""
    k = (_SPEC["level"], tuple(sorted(_SPEC.get("absent", ()))))
    if _WORLD.get("movers", (None,))[0] != k:
        from devkit.sim.ports import vanilla_iso
        from azurkit.tools.randomizer.draft.geometry import Level
        _WORLD["movers"] = (k, Movers.of(Level.read(vanilla_iso(), k[0]), k[1]))
    return _WORLD["movers"][1]


# -- the kernel's simulator ----------------------------------------------------------------------------------------

def world(level: str, absent) -> tuple[N.World, N.Fields]:
    """``level``'s kernel world less the ``absent`` platforms (its faces' springboard heights beside) and its push and
    water volumes (each process: once)."""
    k = (level, tuple(sorted(absent)))
    if _WORLD.get("world", (None,))[0] != k:
        from devkit.sim.ports import vanilla_iso
        from azurkit.tools.randomizer.draft.geometry import Level
        lv = Level.read(vanilla_iso(), level)
        solid = N.World(*N.solid(lv, absent), spring=N.springs(lv, absent))
        _WORLD["world"] = (k, (solid, N.Fields(N.fields(lv))))
        solid.fields(_WORLD["world"][1][1])
    return _WORLD["world"][1]


KIT = "kit"                # a kernel step's write that sets the kit (:meth:`KernelSim.kit_writes`)


class Base:
    """What the snapshot's player is once R6 has placed it (read once a worker from FastL3, :func:`base`): the
    velocity the placement's tick leaves (R6 moves the body, not its velocity: the snapshot's), HP and its most, the
    flap ceiling's latch (the snapshot's: R6 keeps it) and the camera the input builder reads."""

    def __init__(self, row0, row) -> None:
        self.vel, self.hp, self.hp_max, self.cam = row0.obs.vel, row.hp, row.obs.hp_max, row.cam
        self.peak_z = row.obs.peak_z if row.obs.peak_z is not None and math.isfinite(row.obs.peak_z) else -3.4e38


def base(sim) -> Base:
    """:class:`Base` of FastL3 ``sim``'s snapshot, once a process (a placement where the snapshot's player stands)."""
    if "base" not in _SPEC:
        sim.reset()
        c = struct.unpack("<3f", sim.read(sim.u32(sim.entity + 0x20) + 0x15C, 12))
        row0 = row = sim.teleport((c[0], c[1], c[2] - 1.0), 0.0)
        for _ in range(runner.SETTLE_START):
            row = sim.step(Pad())
        _SPEC["base"] = Base(row0, row)
        sim.reset()
    return _SPEC["base"]


class KernelSim:
    """The kernel route's simulator for one job: the kernel's player under L3's interface (:meth:`teleport`,
    :meth:`step` with a :class:`~devkit.sim.l3.Row` of the light observation's fields the controllers and
    ``settled`` read, :meth:`save`, :meth:`reset`, :meth:`kit_writes`), with ``l3`` the worker's FastL3.

    A placement (R6: the body centre 1 m over the feet, airborne, at rest, the snapshot's HP, flap latch and camera)
    and the steps after it (the settle, the kit as state: the armor's Flaps with an element's shield, the gauge
    its cast fills; the align) run on the kernel and are logged; one the kernel flags there runs the placement and
    its log again on ``l3`` and goes on there (``mode`` "l3": every later step of that start, its launches too, is
    L3's).  In a launch (``launching``) a flag raises :class:`Flagged` instead (``run_macros`` runs that launch on L3).
    HP stays the snapshot's: the kernel models no damage."""

    def __init__(self, l3sim, w: N.World, b: Base) -> None:
        self.l3, self.w, self.b, self.lib = l3sim, w, b, w.lib
        self.p, self._pad, self._out = N.Player(), N.Pad(), (ctypes.c_double * 10)()
        self.mode, self.launching, self.log, self.at, self.cam, self.k = "kernel", False, [], None, b.cam, 0
        self.ticks = 0

    @property
    def taint(self):
        return self.l3.taint if self.mode == "l3" else frozenset()

    def save(self) -> tuple:
        s = self.l3.save() if self.mode == "l3" else N.Player.from_buffer_copy(self.p)
        return self.mode, s, self.at, tuple(self.log), self.cam, self.k

    def reset(self, state: tuple | None = None) -> None:
        if state is None:
            self.mode, self.at, self.log, self.cam, self.k = "kernel", None, [], self.b.cam, 0
            return
        self.mode, s, self.at, log, self.cam, self.k = state
        self.log = list(log)
        if self.mode == "l3":
            self.l3.reset(s)
        else:
            ctypes.memmove(ctypes.byref(self.p), ctypes.byref(s), ctypes.sizeof(N.Player))

    def kit_writes(self, kit: dict) -> tuple:
        return self.l3.kit_writes(kit) if self.mode == "l3" else ((KIT, kit),)

    def teleport(self, feet, yaw: float, *, cell: int | None = None) -> Row:
        """R6's tick: the body centre put 1 m over ``feet`` at the tick's end, airborne, the velocity the snapshot's
        (:class:`Base`), no move."""
        self.mode, self.at, self.log, self.cam = "kernel", (tuple(feet), yaw, cell), [(Pad(), None)], self.b.cam
        p = N.player((feet[0], feet[1], feet[2] + 1.0), self.b.vel, 2, (0.0, 0.0, 1.0), peak_z=self.b.peak_z,
                     gauge=0.0)
        ctypes.memmove(ctypes.byref(self.p), ctypes.byref(p), ctypes.sizeof(N.Player))
        self.k += 1
        return self._row()

    def step(self, pad: Pad = Pad(), *, writes=()) -> Row:
        if self.mode == "l3":
            return self.l3.step(pad, writes=writes)
        kit = next((v for k, v in writes if k is KIT), None)
        if not self.launching:
            self.log.append((pad, kit))
        if kit is not None:
            flaps = 5 if kit.get("air") else 0       # [the armor's Flaps at air 3, L3's]; no element, no flap
            self.p.flaps_max, self.p.shield, self.p.gauge = flaps, int(flaps > 0), 0.0
        try:
            return self._step(pad)
        except Flagged:
            if self.launching:
                raise
            return self.to_l3()

    def to_l3(self) -> Row:
        """The placement and its logged steps run again on ``l3`` (``mode`` "l3" on): the last one's row."""
        feet, yaw, cell = self.at
        self.mode = "l3"
        self.l3.reset()
        row = self.l3.teleport(feet, yaw, cell=cell)
        for pad, kit in self.log[1:]:
            row = self.l3.step(pad, writes=self.l3.kit_writes(kit) if kit is not None else ())
        return row

    def _step(self, pad: Pad) -> Row:
        if pad.cam is not None:
            self.cam = struct.pack("<2f", *pad.cam)
        elif pad.yaw is not None:
            self.cam = l3.camera_dir(pad.yaw)
        cx, cy = struct.unpack("<2f", self.cam)
        b, q, p = pad.buttons, self._pad, self.p
        q.sx, q.sy, q.cx, q.cy = pad.stick[0], pad.stick[1], cx, cy
        q.buttons = (N.Y if "y" in b else 0) | (N.LT if "lt" in b else 0) | (N.BLACK if "black" in b else 0)
        self.lib.p_run(self.w.ptr, ctypes.byref(p), 1, ctypes.addressof(q), ctypes.addressof(self._out))
        self.ticks += 1
        self.k += 1
        code = int(self._out[9])
        if code % 16 or (code >> 4) & sum(N.TRIES):
            why = _why(code)
            raise Flagged(f"the kernel stops: {why}", f"kernel:{why}")
        return self._row()

    def _row(self) -> Row:
        p = self.p
        pos, vel = (p.pos[0], p.pos[1], p.pos[2]), (p.vel[0], p.vel[1], p.vel[2])
        obs = Obs(pos, vel, p.state, self.b.hp, self.b.hp_max, p.flaps_used, struct.unpack("<2f", self.cam),
                  flaps=p.flaps_max, normal=(p.normal[0], p.normal[1], p.normal[2]), fall_ref=p.fall_ref,
                  state_t=p.state_t, gauge=p.gauge, peak_z=p.peak_z)
        return Row(self.k, pos, p.state, self.b.hp, None, (), self.cam, frozenset(), obs, None)

    def on_l3(self, state: tuple):
        """FastL3's state at kernel state ``state`` (its placement and logged steps run on ``l3``), None when L3 doesn't
        stand the start where the kernel did (``runner.find_start``'s rule, at the settle's end)."""
        if state[0] == "l3":
            return state[1]
        feet, yaw, cell = state[2]
        self.l3.reset()
        row = self.l3.teleport(feet, yaw, cell=cell)
        for n, (pad, kit) in enumerate(state[3][1:], 1):
            row = self.l3.step(pad, writes=self.l3.kit_writes(kit) if kit is not None else ())
            if n == runner.SETTLE_START and not stood(row, feet):
                return None
        return self.l3.save()


def _why(code: int) -> str:
    """A flagged tick's why (``p_run``'s code: its stop, else the noted laws it doesn't port)."""
    return N.STOP.get(code % 16) or "+".join(N.TRIES[t] for t in N.TRIES if (code >> 4) & t)


def stood(row, feet) -> bool:
    """Whether a placement onto ``feet`` whose settle ended at ``row`` stands there (``runner.find_start``'s rule)."""
    g = runner._feet(row)
    return (row.state == 0 and math.hypot(g[0] - feet[0], g[1] - feet[1]) <= runner.START_XY
            and abs(g[2] - feet[2]) <= runner.START_Z)


# -- the route -----------------------------------------------------------------------------------------------------

def _cost(**add) -> None:
    for k, v in add.items():
        if isinstance(v, dict):
            d = _COST.setdefault(k, {})
            for a, b in v.items():
                d[a] = d.get(a, 0) + b
        else:
            _COST[k] = _COST.get(k, 0) + v


def outcome(m, pads, rows, end: str, first, hp0: int, place: bytes, taint) -> dict:
    """``runner.outcome`` of a kernel launch: its fields but the ones FastL3's confirm re-derives from the game's
    own code and the graph reads from confirmed outcomes only (trick labels, volumes, picks: empty)."""
    last = rows[-1] if rows else None
    took = runner._took(rows)
    return {"macro": m.name, "kit": m.kit, "flaps_planned": m.flaps, "end": end, "ticks": len(rows),
            "land": list(runner._feet(last)) if last else None, "land_state": last.state if last else None,
            "first": list(runner._feet(rows[first])) if first is not None else None,
            "first_state": rows[first].state if first is not None else None,
            "took": list(runner._feet(rows[took])) if took is not None else None,
            "hp0": hp0, "hp_min": min((r.hp for r in rows), default=hp0),
            "flaps": max(((r.obs.flaps_used or 0) for r in rows if r.obs is not None), default=0),
            "labels": [], "volumes": [], "picks": [], "taint": sorted(taint),
            "segments": runner.segments(pads, rows), "string_sha12": runner.string_sha12(pads, place, rows=rows)}


def run_macros(sim, rec: dict, ms, heading: float, takeoff, starts: dict, cells, touch=None, *,
               find=runner.find_start, memo: dict | None = None, name: str = "", target=None, ctl=None,
               done=None) -> bool:
    """``runner.run_macros`` on the kernel route (the module docstring; ``sim`` a :class:`KernelSim`): each family's
    launches on the kernel from its start's saved state, the flagged ones on FastL3 from that state's L3 twin
    (:meth:`KernelSim.on_l3`); each outcome's ``by`` says which ran it."""
    memo = {} if memo is None else memo
    ran = set()
    for n, m in enumerate(ms):
        if n in ran:
            continue
        family = [k for k in range(n, len(ms)) if k not in ran and ms[k]._replace(flaps=0) == m._replace(flaps=0)]
        ran.update(family)
        kind = "stand" if m.stands else "run"
        variant = kind + name
        if variant not in rec["starts"]:
            st = rec["starts"][variant] = find(sim, starts[kind], heading, cells)
            memo[variant] = sim.save() if "cell" in st else None
        if memo[variant] is None:
            continue
        st = rec["starts"][variant]
        if (variant, m.kit) not in memo:
            sim.reset(memo[variant])
            try:
                rows = runner.set_kit(sim, m.kit)
                turn, turned, cam = runner.align(sim, runner._cam(rows[-1]), heading)
            except L3Error:
                memo[(variant, m.kit)] = None
            else:
                memo[(variant, m.kit)] = (sim.save(), turn, turned, cam, rows[-1].hp,
                                          runner.witness_prefix(st["feet"], heading, st["cell"], m.kit))
        if (got := memo[(variant, m.kit)]) is None:
            continue
        state, turn, turned, cam, hp0, prefix = got
        back = ((takeoff[0] - st["feet"][0]) * -math.sin(heading)
                + (takeoff[1] - st["feet"][1]) * math.cos(heading))
        fam, at, feet = [ms[k] for k in family], None if target is None else target(m), tuple(st["feet"])
        sim.reset(state)
        on = "l3" if sim.mode == "l3" else "kernel"
        ticks, sim.launching = sim.ticks, True
        try:
            gos = (c_launches(sim, fam, heading, cam, feet, back, at, ctl, state)
                   or launches(sim, fam, heading, cam, feet, back, target=at, ctl=ctl))
        finally:
            sim.launching = False
        by = [on] * len(gos)
        flagged = [i for i, g in enumerate(gos) if g.end.startswith(FLAG)]
        _cost(launches=len(gos) if on == "kernel" else 0, kernel_ticks=sim.ticks - ticks, flagged=len(flagged),
              l3_starts=len(gos) if on == "l3" else 0)
        for i in flagged:
            _cost(why={gos[i].end[len(FLAG) + 1:]: 1})
        if flagged:
            if ("l3", variant, m.kit) not in memo:
                memo["l3", variant, m.kit] = sim.on_l3(state)
            if (twin := memo["l3", variant, m.kit]) is None:
                _cost(l3_refused=len(flagged))
            else:
                sim.l3.reset(twin)
                redo = launches(sim.l3, [fam[i] for i in flagged], heading, cam, feet, back, target=at, ctl=ctl)
                for i, g in zip(flagged, redo):
                    gos[i], by[i] = g, "l3"
                _cost(flagged_ticks=sum(len(g.rows) for g in redo))
        k, stop = len(turn), False
        for f, go, b in zip(family, gos, by):
            if b == "kernel" and go.end.startswith(FLAG):
                continue                                # L3 refused its start: no outcome
            first = None if go.first is None else go.first + k
            o = (c_outcome(ms[f], turn, turned, go, hp0, prefix) if isinstance(go, CLaunch) else
                 outcome(ms[f], turn + go.pads, turned + go.rows, go.end, first, hp0, prefix, go.taint) if b == "kernel"
                 else runner.outcome(ms[f], turn + go.pads, turned + go.rows, go.end, first, hp0, prefix, touch,
                                     go.taint))
            o |= {"start": variant, "by": b}
            rec["outcomes"].append(o)
            stop |= done is not None and done(o, st)
        if stop:
            return True
    return False


# -- the controllers in C (Step R2.19p) -----------------------------------------------------------------------------

# The Python sources ``controllers.c`` copies (or that the record it gives leans on) and the sha256[:12] of each when
# they last matched it (:func:`stale`; ``reach_engine.fast``'s rule): edit controllers.c beside one, then pin its new
# hash.  Their named constants aren't copied: :func:`_consts` passes them in.
SHADOWS = {"macros.launches": "532616e695d1", "macros._Run": "0c03454d6eb9", "macros.flap_due": "b8f9d092a822",
           "macros._roll_buttons": "5abd85de7fce", "macros.settled": "cb9b714ff149", "aim.Aim": "b44bb58d40d0",
           "aim.Sched": "3e601468d0b4", "aim._steer": "7ebbc7919311", "aim.landing": "545420eb2158",
           "physics.Physics.x_after": "a3f0acb37a15", "inputs.wrap": "becf340ea616",
           "inputs.heading_to": "7804f56b9190", "inputs.camera": "909a513953b7", "inputs.gate_max": "1a6ee38cde87",
           "inputs.stick": "f3be5f14c4cd", "l3.camera_dir": "c0feeebaaa49", "l3_search.segments": "3d478d5a4d25",
           "l3_search.string_sha12": "c0c473417dac", "runner._took": "68603020731d",
           "KernelSim._step": "74d5bd9d172b", "outcome": "9fa6b7051f73"}
_KINDS = {"walkoff": 0, "runjump": 1, "standjump": 2, "rolljump": 3}   # controllers.c's macro kinds
_ENDS = ("ticks", "settled", "unsettled", "walked off", "dead", "air cap", "stuck", "stayed")   # its ends (8: a flag)
_BUTTONS = ((1, "y"), (2, "lt"), (4, "black"))
MAXL = 32                  # controllers.c's CT_MAXL: the most launches a family runs in C


def _shadowed() -> dict:
    from devkit.rando import physics
    from devkit.reach.engine import aim, macros
    from devkit.sim import inputs, l3_search
    return {"macros.launches": macros.launches, "macros._Run": macros._Run, "macros.flap_due": macros.flap_due,
            "macros._roll_buttons": macros._roll_buttons, "macros.settled": macros.settled, "aim.Aim": aim.Aim,
            "aim.Sched": aim.Sched, "aim._steer": aim._steer, "aim.landing": aim.landing,
            "physics.Physics.x_after": physics.Physics.x_after, "inputs.wrap": inputs.wrap,
            "inputs.heading_to": inputs.heading_to, "inputs.camera": inputs.camera, "inputs.gate_max": inputs.gate_max,
            "inputs.stick": inputs.stick, "l3.camera_dir": l3.camera_dir, "l3_search.segments": l3_search.segments,
            "l3_search.string_sha12": l3_search.string_sha12, "runner._took": runner._took,
            "KernelSim._step": KernelSim._step, "outcome": outcome}


def stale() -> list[str]:
    """The :data:`SHADOWS` whose source has moved since ``controllers.c`` was last checked against it."""
    got = _shadowed()
    return [k for k in SHADOWS if hashlib.sha256(inspect.getsource(got[k]).encode()).hexdigest()[:12] != SHADOWS[k]]


@functools.cache
def _consts() -> N.Consts:
    """``controllers.c``'s constants from the modules whose code it copies (each set of two states as a pair)."""
    from devkit.reach.engine import aim, macros
    from devkit.sim import inputs, l3_search, obs, tricks_detect

    def pair(states) -> ctypes.Array:
        if len(states) != 2:
            raise RuntimeError(f"controllers.c takes a pair of states, not {sorted(states)}")
        return (ctypes.c_int * 2)(*sorted(states))
    law = aim._LAW
    return N.Consts(ticks=macros.TICKS, air_cap=macros.AIR_CAP, run_cap=macros.RUN_CAP, stuck=macros.STUCK,
                    still=macros.STILL, settle=macros.SETTLE, swim_hold=macros.SWIM_HOLD, jump_hold=macros.JUMP_HOLD,
                    chain0=macros.CHAIN[0], chain1=macros.CHAIN[1], roll_y=macros.ROLL_Y, roll_tap=macros.ROLL_TAP,
                    roll_period=macros.ROLL_PERIOD, roll_ticks=macros.ROLL_TICKS, cast_wait=macros.CAST_WAIT,
                    turn=aim.TURN, home_ticks=aim.HOME_TICKS, brake_ticks=aim.BRAKE_TICKS, tries=sum(N.TRIES),
                    airborne=pair(macros.AIRBORNE), dead=pair(macros.DEAD), settled=pair(obs.SETTLED),
                    swimming=macros.SWIMMING, slide=obs.SLIDE, flap_margin=macros.FLAP_MARGIN, h_air=macros.H_AIR,
                    descent_d=macros.DESCENT_D, gravity=macros.GRAVITY, fps=macros.FPS, flap_mult=macros.FLAP_MULT,
                    short_m=aim.SHORT_M, home_m=aim.HOME_M, brake_v=aim.BRAKE_V, cam_rate=inputs.CAM_RATE,
                    snap_deg=inputs.SNAP_DEG, dead_raw=inputs.DEAD_RAW, raw_scale=inputs.RAW_SCALE,
                    gate_raw=inputs.GATE_RAW, flat_nz=obs.FLAT_NZ, rest_mps=obs.REST_MPS, dt=law.dt, gdt=law.gdt,
                    blend=law.blend)


class CLaunch(NamedTuple):
    """A launch :func:`c_launches` ran: its end (``macros.launches``'), ``first`` its first row back on something
    after the takeoff and that row's centre and state, ``n`` its rows, ``air`` its first airborne row, ``took`` its last
    standing row before that one with its centre, its last row's centre and state, ``hp`` its rows' HP (the
    snapshot's), its most flaps used and its pads' run-length segments ((n, sx, sy, buttons, cx, cy) each)."""
    end: str
    first: int | None
    first_row: tuple
    n: int
    air: int | None
    took: int | None
    took_pos: tuple
    last: tuple
    last_state: int | None
    hp: int
    flaps: int
    segs: list


def c_launches(sim, fam, heading: float, cam: float, start: tuple, back: float, target, ctl, state):
    """``macros.launches(sim, fam, heading, cam, start, back, target=target, ctl=ctl)`` on ``controllers.c``
    (``sim`` a :class:`KernelSim` in its kernel mode at saved state ``state``; ``ctl`` None, R0's, or ``aim``'s
    ``Aim`` or ``Sched`` with its ``home`` and ``sched``): its :class:`CLaunch` es, the kernel's ticks added to
    ``sim.ticks``.  None where it doesn't run them: :data:`CONTROLLERS` "py", L3's mode, another simulator, controller,
    macro kind or kit, a family over :data:`MAXL`, or one Python's controllers would raise in (``sim`` back at
    ``state``: the caller runs it in Python)."""
    from devkit.reach.engine import aim
    if CONTROLLERS != "c" or type(sim) is not KernelSim or sim.mode != "kernel" or not 0 < len(fam) <= MAXL:
        return None
    if ctl is None:
        kind, kw = 0, {}
    elif (isinstance(ctl, functools.partial) and not ctl.args and ctl.func in (aim.Aim, aim.Sched)
          and set(ctl.keywords) <= ({"home"} if ctl.func is aim.Aim else {"home", "sched"})):
        kind, kw = 1 if ctl.func is aim.Aim else 2, ctl.keywords
    else:
        return None
    if any(m.kind not in _KINDS or m.kit not in aim.AIR_CONTROL for m in fam):
        return None
    home, sched = kw.get("home"), list(kw.get("sched") or ())
    sch = (ctypes.c_double * max(len(sched), 1))(*sched)
    f = N.Fam(ctl=kind, n=len(fam), hp=int(sim.b.hp), has_target=target is not None, has_home=home is not None,
              nsched=len(sched), heading=heading, cam=cam, back=back, start=tuple(start),
              target=tuple(target) if target is not None else (0.0, 0.0, 0.0),
              home=tuple(home) if home is not None else (0.0, 0.0, 0.0), sched=sch)
    macs = (N.Mac * len(fam))(*[N.Mac(_KINDS[m.kind], m.flaps, m.rolls, int(m.recast), int(m.hold), m.curve, m.lead,
                                      aim.AIR_CONTROL[m.kit]) for m in fam])
    outs, segs = (N.LOut * len(fam))(), (N.Seg * (len(fam) * _consts().ticks))()
    ticks = ctypes.c_int64()
    if sim.lib.p_launches(sim.w.ptr, ctypes.byref(sim.p), ctypes.byref(_consts()), ctypes.byref(f), macs, outs,
                          segs, ctypes.byref(ticks)):
        sim.reset(state)
        return None
    sim.ticks += ticks.value
    sim.k += ticks.value
    hp = int(sim.b.hp)
    return [CLaunch(f"{FLAG}:{_why(o.code)}" if o.end == 8 else _ENDS[o.end],
                    None if o.first < 0 else o.first, (tuple(o.firstp), o.first_state), o.n,
                    None if o.air < 0 else o.air, None if o.took < 0 else o.took, tuple(o.tookp), tuple(o.last),
                    o.last_state if o.n else None, hp, o.flaps,
                    [(s.n, s.sx, s.sy, s.buttons, s.cx, s.cy) for s in segs[o.seg0:o.seg0 + o.nseg]])
            for o in outs]


def _feet3(p) -> list:
    return [p[0], p[1], p[2] - 1.0]


def c_outcome(m, turn, turned, go: CLaunch, hp0: int, place: bytes) -> dict:
    """:func:`outcome` of C launch ``go`` after the align's ``turn`` pads and ``turned`` rows: the record
    ``outcome(m, turn + pads, turned + rows, ...)`` gives of the same launch run in Python."""
    k = len(turned)
    if go.n:
        land, land_state = _feet3(go.last), go.last_state
    elif turned:
        land, land_state = list(runner._feet(turned[-1])), turned[-1].state
    else:
        land = land_state = None
    j = next((i for i, r in enumerate(turned) if r.state in AIRBORNE), None)
    if j is None and go.air is not None and go.took is not None:
        took = _feet3(go.took_pos)
    else:                                              # runner._took: the align's rows hold it, or none does
        t = None if j is None and go.air is None else next(
            (i for i in range((k if j is None else j) - 1, -1, -1) if turned[i].state == 0), None)
        took = None if t is None else list(runner._feet(turned[t]))
    segs = runner.segments(turn, turned)
    for n, sx, sy, b, cx, cy in go.segs:
        d = {"stick": [sx, sy], **({"buttons": sorted(name for bit, name in _BUTTONS if b & bit)} if b else {}),
             "cam": [cx, cy]}
        if segs and {k_: v for k_, v in segs[-1].items() if k_ != "n"} == d:
            segs[-1]["n"] += n
        else:
            segs.append({"n": n, **d})
    return {"macro": m.name, "kit": m.kit, "flaps_planned": m.flaps, "end": go.end, "ticks": k + go.n,
            "land": land, "land_state": land_state,
            "first": _feet3(go.first_row[0]) if go.first is not None else None,
            "first_state": go.first_row[1] if go.first is not None else None, "took": took,
            "hp0": hp0, "hp_min": min([r.hp for r in turned] + [go.hp] * bool(go.n), default=hp0),
            "flaps": max([(r.obs.flaps_used or 0) for r in turned if r.obs is not None] + [go.flaps] * bool(go.n),
                         default=0),
            "labels": [], "volumes": [], "picks": [], "taint": [], "segments": segs,
            "string_sha12": hashlib.sha256(place + json.dumps(segs, sort_keys=True).encode()).hexdigest()[:12]}


class _Macro:
    """The fields ``runner.outcome`` reads of an outcome's macro."""

    def __init__(self, o: dict) -> None:
        self.name, self.kit, self.flaps = o["macro"], o["kit"], o["flaps_planned"]


def _touch():
    p = _SPEC.get("touch")
    if p is None:
        return None
    if _SPEC.get("_touch", (None,))[0] != p:
        _SPEC["_touch"] = (p, runner.Touch(json.loads(Path(p).read_text(encoding="utf-8"))))
    return _SPEC["_touch"][1]


def confirm(sim, st: dict, heading: float, o: dict, touch=None, held: bool = True) -> dict:
    """Kernel outcome ``o`` of start ``st`` run on ``sim`` (FastL3) from the snapshot, then ``hold.HOLD`` idle ticks
    (the module docstring; none without ``held``): ``hold.replay``'s answer (where the body is then, ``same``, the
    ticks) with ``outcome`` the outcome re-derived from L3's rows (``runner.outcome``'s fields but its pads); a start
    L3 doesn't stand (:func:`stood`) is ``fault`` "start" (no stay)."""
    pads, ticks = l3.pads(o["segments"]), runner.SETTLE_START
    yaw = st.get("yaw", heading)
    try:
        if not stood(runner.place(sim, st["feet"], yaw, st["cell"]), st["feet"]):
            return {"fault": "start", "ticks": ticks}
        kit = runner.set_kit(sim, o["kit"])
        ticks += len(kit)
        rows = []
        for p in pads:
            rows.append(sim.step(p))
            ticks += 1
        path = [r.pos for r in rows]
        last = rows[-1] if rows else kit[-1]
        alive = all(r.state not in DEAD and r.hp > 0 for r in rows)
        took = next((i for i, r in enumerate(rows) if r.state in AIRBORNE), None)
        first = None if took is None else next((i for i in range(took, len(rows)) if rows[i].state not in AIRBORNE),
                                               None)
        exited = any(r.exit is not None for r in rows)
        end = ("dead" if not alive else "exit" if exited else
               "settled" if first is not None and settled(last) else "unsettled")
        got = runner.outcome(_Macro(o), pads, rows, end, first, kit[-1].hp,
                             runner.witness_prefix(st["feet"], yaw, st["cell"], o["kit"]),
                             touch if touch is not None else _touch(), sim.taint)
        row = last
        for _ in range(hold.HOLD if held else 0):
            row, ticks = sim.step(Pad()), ticks + 1
            path.append(row.pos)
    except L3Error as exc:
        return {"fault": str(getattr(exc, "site", "other")), "ticks": ticks}
    got.pop("segments")
    same = got["end"] == "settled" and min_rank(got) <= min_rank(o)
    return {"land": list(runner._feet(row)), "state": row.state, "settled": settled(row), "same": same,
            "ticks": ticks, "outcome": got, **({"route": movers().route(path)} if held and "level" in _SPEC else {})}


_held, _floor, _others = hold.replay, None, None


def _l3_stands(sim, q, heading: float, cells, ok) -> bool:
    """Whether FastL3 (``sim.l3``) stands a body placed at ``q`` (``aim.stands``) where ``ok`` takes it."""
    from devkit.reach.engine import aim
    g = aim.stands(sim.l3, q, heading, cells)
    return g is not None and ok(g)


def floor(sim, p, zone: str, heading: float, cells, zone_at) -> dict:
    """``aim.floor`` on the kernel route (:func:`install`): the kernel's scan picks the point the aims fly to and
    FastL3 says whether ``zone`` has a floor there: where FastL3 too stands a body placed at that point (``l3``
    "point"), else FastL3's own scan (``l3`` "scan"), so ``to`` is L3's answer."""
    got = _floor(sim, p, zone, heading, cells, zone_at)
    if not isinstance(sim, KernelSim):
        return got
    if got["to"] and _l3_stands(sim, got.get("snap", p), heading, cells,
                                lambda g: zone_at(g[0], g[1] == SWIMMING, False) == zone):
        return got | {"l3": "point"}
    return _floor(sim.l3, p, zone, heading, cells, zone_at) | {"l3": "scan"}


def other_starts(sim, takeoff, heading: float, target, zone: str, cells, zone_at) -> tuple[list, int]:
    """``aim.other_starts`` on the kernel route (:func:`install`): the kernel's takeoffs where FastL3 too stands a
    body (standing, in ``zone``) on one of them, else FastL3's own (so a count of 0 is L3's)."""
    picks, n = _others(sim, takeoff, heading, target, zone, cells, zone_at)
    if not isinstance(sim, KernelSim) or any(
            _l3_stands(sim, q, heading, cells, lambda g: g[1] == 0 and zone_at(g[0], False, False) == zone)
            for q in picks):
        return picks, n
    return _others(sim.l3, takeoff, heading, target, zone, cells, zone_at)


def replay(sim, st: dict, heading: float, o: dict) -> dict:
    """``hold.replay`` on the kernel route: a kernel outcome's is its :func:`confirm`, whose re-derived fields then
    replace the kernel's in ``o`` (:func:`confirmed`: an aim's hit, so its record holds L3's outcome; a graph hold's
    copy goes); any other's is ``hold.replay``'s.  Either way on the worker's FastL3, timed (a step stopped for time
    raises ``worker.StepTimeout``: no answer), the answer carrying the witness's ``route`` (:class:`Movers`: its
    string and hold's body path from the placement's settle on)."""
    sim = worker.timed(getattr(sim, "l3", sim))   # an aim's hit: the job's KernelSim; a graph hold: FastL3
    if o.get("by") != "kernel":
        path, step = [], sim.step

        def traced(*a, **k):
            row = step(*a, **k)
            path.append(row.pos)
            return row
        sim.step = traced
        try:
            got = _held(sim, st, heading, o)
        finally:
            sim.step = step
        return got | ({"route": movers().route(path[runner.SETTLE_START + 1:])} if "land" in got else {})
    got = confirm(sim, st, heading, o)
    _cost(confirms=1, confirm_ticks=got["ticks"])
    confirmed(o, got)
    return got


def confirmed(o: dict, got: dict) -> None:
    """Kernel outcome ``o`` made its confirm's (``got``): L3's fields, ``by`` "confirmed"."""
    if "outcome" in got:
        o.update(got["outcome"])
        o["by"] = "confirmed"


def _drift(sim, rec: dict) -> dict:
    """The drift audit of a kernel record (the module docstring): its kernel launches that settled; ``silent`` those
    whose FastL3 string ends over :data:`END_M` from the kernel's landing (R2.17's SILENT; a death where the kernel
    landed is no drift: the kernel models no damage, and the confirm drops it; a start L3 doesn't stand is silent
    too), ``moving`` those it ends within it but not at rest (a slope, a slide: L3 goes on), ``dead`` those it ends
    dead there."""
    out = {"settled": 0, "silent": 0, "moving": 0, "dead": 0}
    for o in rec["outcomes"]:
        if o.get("by") != "kernel" or o["end"] != "settled":
            continue
        got = confirm(sim, rec["starts"][o["start"]], rec["heading"], o, held=False)
        out["settled"] += 1
        g = got.get("outcome")
        if g is None or g["land"] is None or math.dist(g["land"], o["land"]) > END_M:
            out["silent"] += 1
        elif g["end"] == "dead":
            out["dead"] += 1
        elif g["end"] != "settled":
            out["moving"] += 1
    return out


def drifted(key: str) -> bool:
    """Whether the job ``key`` is drift-audited (about 1 in :data:`DRIFT_EVERY`, by key)."""
    return int(key, 16) % DRIFT_EVERY == 0


def install(spec: dict) -> None:
    """Route a worker's jobs and holds through the kernel (``spec``: its ``level``, the census's ``absent`` owners
    and the plan's ``touch`` targets file): ``runner.run_job`` runs each job on a :class:`KernelSim` over the worker's
    FastL3 (its record's ``kernel`` counts and, for an audited job, ``drift``; ``runner.summary`` passes them on),
    ``runner`` and ``aim``'s ``run_macros`` are :func:`run_macros`, ``hold.replay`` is :func:`replay` (a kernel
    outcome's confirm; an aim's hit made its confirm's) and ``aim``'s ``floor`` and ``other_starts`` are
    :func:`floor` and :func:`other_starts` (FastL3's answers)."""
    global _held, _floor, _others
    from devkit.reach.engine import aim
    if CONTROLLERS == "c" and (moved := stale()):
        raise RuntimeError(f"reach_native/controllers.c copies {', '.join(moved)}, edited since: edit controllers.c "
                           "beside them and pin their new hashes in backend.SHADOWS, or run with "
                           "AZURIK_REACH_CONTROLLERS=py")
    _SPEC.clear()
    _SPEC.update(spec)
    _held, _floor, _others = hold.replay, aim.floor, aim.other_starts
    runner.run_macros = aim.run_macros = run_macros
    hold.replay, aim.floor, aim.other_starts = replay, floor, other_starts
    run_job, summary = runner.run_job, runner.summary

    def job(sim, j, *a, **k):
        _COST.clear()
        ks = KernelSim(worker.timed(sim), world(_SPEC["level"], _SPEC.get("absent", ()))[0], base(sim))
        rec = run_job(ks, j, *a, **k)
        rec["kernel"] = dict(_COST)
        if drifted(j["key"]):
            rec["drift"] = _drift(ks.l3, rec)
        return rec

    def summed(rec: dict) -> dict:
        return summary(rec) | {k: rec[k] for k in ("kernel", "drift") if k in rec}
    runner.run_job, runner.summary = job, summed


def setup(spec: dict, x87: str | None = None, fast: bool = True) -> None:
    """A kernel pool worker's start (``fast``: on a FastL3 pool): ``reach_engine.worker.setup`` without FastL3's tick
    cuts (the kernel runs the launches they cut), its records stamped with the L3 that ran and the kernel, then
    :func:`install`."""
    from devkit.reach.engine import worker
    worker.setup(False, x87)
    worker.IMPL.clear()
    worker.IMPL.update(worker.impl(fast) | {"kernel": kernel_sha12()})
    install(spec)
