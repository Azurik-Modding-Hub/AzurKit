"""Reach's flights: the drops, steps, jumps and flap jumps between regions.

The third stage of the reach model (Step R1.3a; reach v6's
``jump_edges``).  Candidate flights join a takeoff sample of one region
to a landing sample of another within 20 m (no-flap kits) or 62 m (flap
kits, regions of at least 4 m^2 at both ends), in a fixed order: by
takeoff, then landing (reach v6 took scipy's cKDTree order, which decides
which of two equal flights it keeps; default taken under D115).  Per difficulty tier the
physics envelope (:mod:`devkit.rando.physics`) under the tier's
margins (``tiers.toml``, :class:`Env`) gives the cheapest air rank whose
gap table allows each one, or the collision lip lift onto a plain ledge
(a vertical face and a flat top) whose face lies in the tier's takeoff
window for that lip (:func:`lip_windows`).  Each edge keeps, per tier,
its witness flight's certificate (:class:`physics.Certificate`: the gap,
dh, run-up, headroom, walk-off or lip lift it needs), so another
movement can re-check it (D167, D168).

With the sweep (the ``logic`` profile) every flight is checked whole
against the solid spans, as a 2.0 m body: the walk-off (walk at the
takeoff height while a logic floor carries the body, then fall from
rest) or the rank's modelled arc (the physics' per-tick model with the
grid level's frame-perfect flap ticks, cut at the landing height).  The sweep's
points are a 0.25 m grid plus every column-boundary crossing of the
ground track and every turning point of the arc, so each step lies in
one column with a monotone feet height and is swept exactly in it.
Mid-flight the body's middle band must be free 0.4 m to one side of the
track (a gap narrower than the body is a wall).  Two shapes per kit:
``edge`` walks to the takeoff floor's edge, flies the edge-to-edge gap
(what the envelope's gap means) and walks on; ``full`` flies sample to
sample.  The tiers are monotone: a harder tier keeps every flight an
easier one flies.  A flight no kit clears is a probe-needed edge (a
curved path may pass) or, when it could only pass a solid (the same
column, into or out of a region roofed everywhere below the other end,
or between two air components), no edge.  Without the sweep (``phys``)
the envelope alone decides.

A flight over a shut barrier (:class:`OverTest`) is keyed apart, so the
gates can make it that barrier's crossing.  Authoring only (numpy, a
runtime dependency); coordinates stay in memory.

The envelope (:class:`Env`, 20-50 s to build) is built once and kept in
the user cache (:meth:`Env.kept`, Step R1.33) under a key of everything it
is made from.
"""

from __future__ import annotations

import collections
import contextlib
import dataclasses
import hashlib
import json
import math
import os
import pickle
import platform
import sys
import tempfile
from pathlib import Path

import numpy as np
from platformdirs import user_cache_dir

from devkit.rando import physics
from azurkit.tools.randomizer.draft import envelope
from azurkit.tools.randomizer.draft.floors import Walk, lookup
from azurkit.tools.randomizer.draft.geometry import BODY_R, CELL, SLOPE_LAND, Level, RadiusIndex, Spans, components

TIERS = envelope.TIER_ORDER[:-1]                     # safe, standard, hard, frame_perfect
# (name, air rank): each air rank's jump alone (air power: h 1.2, air control 12) and with its flaps, and air 3
# with 3 of its flaps (a lower, steadier arc than 5), so a flight under a roof or over a short gap is swept with
# the lowest arc that covers it; FLAP_CAP caps each kit's flaps (None: the rank's own)
KITS = (("none", 0), ("air_power", 1), ("air1", 1), ("air2", 2), ("air3_3flaps", 3), ("air3", 3))
FLAP_CAP = {"none": 0, "air_power": 0, "air1": None, "air2": None, "air3_3flaps": 3, "air3": None}
FLAP_KITS = frozenset(k for k, _ in KITS if FLAP_CAP[k] != 0)
_TIER = {t.name: t for t in envelope.TIERS + (envelope.PHYS, envelope.ZONE)}

LIP_FACE_FAR = envelope.LEDGE_S6["takeoff_window_m"][1]   # 3.69 m: the farthest takeoff a player tier's window holds
LIP_GAP_MAX = LIP_FACE_FAR + BODY_R + 2.0                 # a lip candidate's bound; the face test decides
LIP_MEASURED = envelope.LEDGE_S6["lip_m"]                  # 1.2578 m: the one measured ledge
LIP_ROW_M = envelope.V_RUN / 30                            # a takeoff row of the lip-lift window, m
SHORT_R, LONG_R = 20.0, 62.0       # pair search radii: no-flap kits, flap kits
SMALL_REGION_M2 = 4.0              # a takeoff region (walk group) smaller than this gets the standing table
RIM_LIFT = 0.8        # the rim step-up (AZ-352): a flight may land this far under a far floor's top when the body meets
                      # a sloped rim there, the step-up (state 0x100) lifting it on [verified xemu r18d: w1's stepping
                      # stone, the rim nz 0.58, hit 0.8 m under the top, 8 of 8; town's hill nz 0.72, 4 of 4]
RIM_NZ = (0.4, envelope.STEP_NORMAL_Z)   # [proposal] the rim's slope band: steeper than a walkable floor (the walk's own
                                         # step covers those), not a wall (the lip lift's case, measured apart)
RIM_STEP_LIFT = envelope.LIP_LIFT_ROWS[-1][0]   # a riser the floors meet at within a cell (its slope unresolved by the
                      # columns: town's hill): the body hits it rising and is lifted, as the measured lip lift is, so
                      # up to the largest lift measured over a face, 0.4987 m (calib §4)
SIDE_M, SIDE_BAND = 0.4, (0.6, 1.4)   # the thin-body test: a solid in the body's middle band (feet + 0.6 .. 1.4 m)
                                      # 0.4 m to BOTH sides of the track is a gap narrower than the body
ROOM_FREE_M = 4.0     # [proposal] the first 4 m of a flight are lined up; sideways drift (the tier's stick error)
                      # accrues beyond it, so the landing floor across the flight line must be (gap - 4) sin(stick) wide
SWEEP_STEP = 0.25     # m of ground travel between a flight's uniform body samples (half a column)
END_M = 0.75          # [inferred] within this of the takeoff or the landing the feet may graze a floor by the step
HEAD_TOL = 0.1        # [inferred] a ceiling may graze the top of the body by this much
ROOF_END = physics.ROOF_END   # [proposal] a flight's ends, its arc's first and last quarter, where the roof's room is
                              # kept apart (AZ-387: a taller arc rises sooner and comes down later, under the roof there)
CARRY_SLOPES = np.round(np.arange(0.0, 1.4 + 1e-9, 0.05), 2)   # the walk-off carry tables' lip slopes, m a metre (AZ-365;
                                                               # a logic floor's nz 0.8 slopes 0.75, a phys one's 1.33)
WALKOFF_SLACK = physics.WALKOFF_SLACK   # L3's walk-off reach past the takeoff floor's end, less the carry (AZ-357)
KEEP_BEST, KEEP_SPREAD, SPREAD_BIN = 2, 6, 8   # flights kept per region pair before the sweep: the 2 best by rank
                                               # and gap, and the best per (4 m takeoff cell, 4 m landing cell) up
                                               # to 6 more, so a pair whose shortest flights are roofed keeps others
FLIGHT_CHUNK = 1_000_000                       # uniform body samples per vectorised block (memory)
OVER_SIDE_M = 0.25    # [proposal] a flight over a barrier crosses it when its ends are this far off its plane
OVER_MARGIN_M = 5.0   # [proposal] a flight crossing a barrier's plane this far past its extent goes round it


def lip_room(tier: str) -> float:
    """The takeoff room a tier's lip lift needs (m): it presses within
    max(takeoff_window, 1) rows of 7/30 m, so max(takeoff_window, 1) - 1
    rows lie between the first and the last press."""
    return (max(_TIER[tier].takeoff_window, 1) - 1) * LIP_ROW_M


def lip_windows(tier: str, deficit: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The takeoff distances before a plain ledge's face (near, far; m) from
    which ``tier`` counts the lip lift over a lip ``deficit`` m above the
    kit's robust apex (:func:`envelope.lip_lift_window`), with the takeoff
    room (:func:`lip_room`) taken off the near end, so a takeoff sample has
    the tier's rows of the window between it and the face.  The presses
    stand on floor too: :func:`_resolve_flights` also needs the takeoff
    floor to run on for the room from the sample (the floor behind the
    sample is not counted; default taken under D115).  NaN where the tier counts no lip lift."""
    room = lip_room(tier)
    t = _TIER[tier]
    near = np.full(len(deficit), np.nan)
    far = np.full(len(deficit), np.nan)
    for k, d in enumerate(np.asarray(deficit, dtype=np.float64).tolist()):
        w = envelope.lip_lift_window(t, d)
        if w is not None and w[0] + room <= w[1]:
            near[k], far[k] = w[0] + room, w[1]
    return near, far


# --------------------------------------------------------------------------- the envelope
KEEP = 4                                # kept envelopes (Env.kept): the newest stay
KEPT_DIR_VAR = "AZURIK_DERIVE_ENV_DIR"  # their folder; unset: user_cache_dir("AzurKit")/derive-env
_KEPT_FORMAT = b"azurik-derive-env/1\0"
# This module as it was loaded: with physics' and envelope's SOURCE_SHA256 (each hashed as it loaded), the code an
# envelope is built from (Env, Arcs, KITS, the physics), so a file edited after a process loaded it never keys
# that process's old code; tiers.toml is keyed by value (each field it gives the tiers: Env.sha256)
SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _env_tiers(tiers):
    return tuple(envelope.TIERS) + (envelope.PHYS, envelope.ZONE) if tiers is None else tuple(tiers)


# Step 2.185's roll time and climb speed shape no envelope (only movement.recheck and the locks read them), so they
# stay out of its hash: vanilla's keeps the envelope_sha256 every committed derived file records.
_NOT_ENVELOPE = ("roll_time_scale", "climb_scale")


def _env_sha256(movement: physics.Movement, tiers) -> str:
    m = {k: v for k, v in dataclasses.asdict(movement).items() if k not in _NOT_ENVELOPE}
    return hashlib.sha256(json.dumps(
        {"movement": m, "tiers": [dataclasses.asdict(t) for t in tiers]}, sort_keys=True).encode()).hexdigest()


def _kept_read(path: Path, sha256: str) -> Env | None:
    try:
        with open(path, "rb") as f:
            env = pickle.load(f)
    except Exception:  # noqa: BLE001  (none yet, or unreadable: a cache, so the envelope is built)
        return None
    if not isinstance(env, Env) or env.sha256 != sha256:
        return None
    with contextlib.suppress(OSError):
        os.utime(path)          # the newest KEEP stay
    return env


def _kept_write(path: Path, env: Env) -> None:
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as f:
            tmp = f.name
            pickle.dump(env, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)   # whole or not at all: a reader never sees a part
        tmp = None
        for old in sorted(path.parent.glob("*.pickle"), key=lambda p: p.stat().st_mtime, reverse=True)[KEEP:]:
            old.unlink()
    except Exception:  # noqa: BLE001  (unwritable: built, not kept)
        if tmp is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp)


class Env:
    """The physics envelope (:mod:`devkit.rando.physics`) of a
    movement (vanilla's by default) under the tiers' margins
    (``tiers.toml``), as vectorised lookups: per tier, kit and level
    of a fine grid (every :data:`STEP` m) the widest gap (running and
    standing), the rank's rise, and the walk-off carry.  A flight at dh
    reads the grid's first level at or above it (the gap shrinks as the
    landing rises).  :meth:`kept` reads a built one back."""

    STEP = 0.025

    def __init__(self, movement: physics.Movement = physics.VANILLA, tiers=None):
        tiers = _env_tiers(tiers)
        self.movement = movement
        # its own envelope, not physics.envelope's shared one: another caller's searches would ride along in a kept copy
        self.env = env = physics.Envelope(movement)
        self.sha256 = _env_sha256(movement, tiers)
        self.clearance = {t.name: t.clearance for t in tiers}
        self.max_drop = {t.name: t.max_drop for t in tiers}
        self.side = {t.name: math.sin(math.radians(t.stick_deg)) for t in tiers}
        drops = np.arange(0.0, 40.0 + 1e-9, 0.5)
        self.carry_drop = drops
        # per lip slope (AZ-365: m the takeoff floor falls a metre along the run at its edge; a row per CARRY_SLOPES)
        self.carry_m = np.array([[0.0] + [env.p.walk_off_carry(float(d), float(sl)) for d in drops[1:]]
                                 for sl in CARRY_SLOPES])
        # the zones' walk-offs read Step R1.2's coarser carry table (envelope.ZONE: its drops fixed), off the lip's slope
        self.zone_carry_drop = np.array([0.0] + list(envelope.ZONE_CARRY_DROPS))
        self.zone_carry_m = np.array([[0.0] + [env.p.walk_off_carry(d, float(sl)) for d in envelope.ZONE_CARRY_DROPS]
                                      for sl in CARRY_SLOPES])
        top = max(env.rises) + max(self.clearance.values()) + self.STEP
        self.levels = np.round(np.arange(-env.DROP, top + 1e-9, self.STEP), 3)
        self.tab, self.rise, self.apex, self.sched = {}, {}, {}, {}
        dt = env.p.dt
        for kname, rk in KITS:
            kit, cap = env.kits[rk], FLAP_CAP[kname]
            air = [env.airtime(rk, float(lv), flaps=cap) for lv in self.levels]
            plain = [env.p.arc(kit, (), float(lv)).cross for lv in self.levels]
            self.sched[kname] = [a[1] for a in air]
            for tag, v0 in (("gap_run", movement.run_speed), ("gap_stand", 0.0)):
                fp = np.array([np.nan if a[0] is None else env.p.travel(a[0], v0, kit.air_control) for a in air])
                jump = np.array([0.0 if a is None else env.p.travel(a, v0, kit.air_control) for a in plain])
                coarse = np.array(envelope.ZONE_LEVELS)
                for t in tiers:      # a tier's gap (tiers.toml) on the grid, the travel taken at level + clearance
                    at = self.levels + t.clearance
                    if t.name == "zone":     # the first ZONE_LEVELS level at or above each grid level
                        k = np.searchsorted(coarse, self.levels - 1e-9, "left")
                        at = np.where(k < len(coarse), coarse[np.minimum(k, len(coarse) - 1)], np.inf) + t.clearance
                    t_fp = np.interp(at, self.levels, fp, right=np.nan)
                    t_jump = np.interp(at, self.levels, jump, right=0.0)
                    loss = t.takeoff_window * v0 * dt
                    g = math.cos(math.radians(t.stick_deg)) * (t_jump + t.reach * (t_fp - t_jump) - loss) - t.landing_margin
                    g[self.levels < -t.max_drop] = np.nan
                    self.tab[(t.name, kname, tag)] = g
            top = env.rise(rk, flaps=cap)
            for t in tiers:
                self.rise[(t.name, kname)] = (top - t.clearance, top + t.lift_allowance)
                self.apex[(t.name, kname)] = top
        self._arcs = None

    def arcs(self) -> Arcs:
        if self._arcs is None:
            self._arcs = Arcs(self)
        return self._arcs

    @classmethod
    def kept_path(cls, movement: physics.Movement = physics.VANILLA, tiers=None) -> Path:
        """The file :meth:`kept` keeps this envelope in: its folder
        (``$AZURIK_DERIVE_ENV_DIR``, else ``derive-env/`` in the user
        cache), named by the key of everything it is made from: the
        movement and the tiers (what :attr:`sha256` hashes), the bytes of
        ``physics.py``, ``envelope.py`` and this module as this process
        loaded them (each one's ``SOURCE_SHA256``), and the Python, numpy
        and platform it is computed under."""
        h = hashlib.sha256(_KEPT_FORMAT)
        h.update(f"{sys.version}\0{np.__version__}\0{platform.platform()}\0"
                 f"{physics.SOURCE_SHA256}\0{envelope.SOURCE_SHA256}\0{SOURCE_SHA256}\0"
                 f"{_env_sha256(movement, _env_tiers(tiers))}".encode())
        root = os.environ.get(KEPT_DIR_VAR) or Path(user_cache_dir("AzurKit"), "derive-env")
        return Path(root) / f"{h.hexdigest()[:32]}.pickle"

    @classmethod
    def kept(cls, movement: physics.Movement = physics.VANILLA, tiers=None) -> Env:
        """``Env(movement, tiers)`` with its :meth:`arcs`, read back from
        :meth:`kept_path` while every input of its key is unchanged (a
        changed one is a new key, so it is built again).  On a miss one
        process builds it, under the folder's lock (POSIX), and writes it
        whole; another waiting for the lock then reads it.  The newest
        :data:`KEEP` are kept; an entry that can't be read is built again,
        and a folder that can't be written builds it here, unkept."""
        path, sha = cls.kept_path(movement, tiers), _env_sha256(movement, _env_tiers(tiers))
        if (env := _kept_read(path, sha)) is not None:
            return env
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            lock = os.open(path.parent / ".lock", os.O_RDWR | os.O_CREAT, 0o600)
        except OSError:
            lock = None
        try:
            if lock is not None:
                with contextlib.suppress(ImportError, OSError):   # no lock: the write is still whole
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX)     # released when the descriptor closes, or the process ends
                if (env := _kept_read(path, sha)) is not None:   # built while this one waited
                    return env
            env = cls(movement, tiers)
            env.arcs()
            if lock is not None:
                _kept_write(path, env)
            return env
        finally:
            if lock is not None:
                os.close(lock)

    def carry(self, drop, zone: bool = False, slope=0.0):
        """Walk-off carry (m) for a drop (m, positive) off a lip that falls ``slope`` m a metre (AZ-365: read at
        the table's next slope up, so never more than the lip's own); past the table, its last slope (``zone``: the
        zones' table)."""
        xs, table = (self.zone_carry_drop, self.zone_carry_m) if zone else (self.carry_drop, self.carry_m)
        drop = np.asarray(drop, dtype=np.float64)
        row = np.minimum(np.searchsorted(CARRY_SLOPES, np.broadcast_to(np.asarray(slope, dtype=np.float64), drop.shape)
                                         - 1e-9, "left"), len(CARRY_SLOPES) - 1)
        out = np.empty(drop.shape)
        for r in np.unique(row):
            ys, at = table[r], row == r
            k = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
            out[at] = np.where(drop[at] > xs[-1], ys[-1] + (drop[at] - xs[-1]) * k, np.interp(drop[at], xs, ys))
        return out

    def kits_ok(self, tier, dh, gap, stand):
        """Per kit (n, len(KITS)): the gap table allows it; the lip lift could
        (a candidate: the plain-ledge and window tests are geometry); and
        each flight's envelope level."""
        idx = np.searchsorted(self.levels, dh - 1e-9, "left")
        valid = idx < len(self.levels)
        idxc = np.minimum(idx, len(self.levels) - 1)
        ok = np.zeros((len(dh), len(KITS)), dtype=bool)
        lipc = np.zeros((len(dh), len(KITS)), dtype=bool)
        bad = dh < -self.max_drop[tier]
        for ki, (kname, _) in enumerate(KITS):
            g = np.where(stand, self.tab[(tier, kname, "gap_stand")][idxc], self.tab[(tier, kname, "gap_run")][idxc])
            ok[:, ki] = valid & (gap <= np.nan_to_num(g, nan=-1.0)) & ~bad
            lift = self.rise[(tier, kname)][1]
            lipc[:, ki] = (~stand) & (dh > 0) & (dh <= lift) & (gap <= LIP_GAP_MAX) & ~ok[:, ki]
        return ok, lipc, idxc

    def rank(self, tier, dh, gap, stand):
        """(rank, kit index, lip used) arrays from the envelope alone (no
        geometry: R_phys counts a lip whose face lies within the tier's far
        takeoff, half a cell added)."""
        idx = np.searchsorted(self.levels, dh - 1e-9, "left")
        valid = idx < len(self.levels)
        idxc = np.minimum(idx, len(self.levels) - 1)
        best = np.full(len(dh), 4, dtype=np.int8)
        kit = np.full(len(dh), -1, dtype=np.int8)
        lip = np.zeros(len(dh), dtype=bool)
        for ki, (kname, rk) in enumerate(KITS):
            g = np.where(stand, self.tab[(tier, kname, "gap_stand")][idxc], self.tab[(tier, kname, "gap_run")][idxc])
            ok = valid & (gap <= np.nan_to_num(g, nan=-1.0))
            lift = self.rise[(tier, kname)][1]
            cand = (~stand) & (dh > 0) & (dh <= lift)
            far = np.full(len(dh), np.nan)
            if cand.any():
                far[cand] = lip_windows(tier, dh[cand] - self.apex[(tier, kname)])[1]
            lp = cand & (gap <= far + CELL / 2)
            take = (ok | lp) & (rk < best)
            best = np.where(take, rk, best)
            kit = np.where(take, ki, kit)
            lip = np.where(take, ~ok, lip)
        best = np.where(dh < -self.max_drop[tier], 4, best)
        return best, kit, lip

    def rise_rank(self, tier, dz):
        """The rank that touches something dz above standing reach (a vertical jump to the clean apex)."""
        best = np.full(len(dz), 4, dtype=np.int8)
        for kname, rk in KITS:
            best = np.where((dz <= self.rise[(tier, kname)][0]) & (rk < best), rk, best)
        return best


class Arcs:
    """The flights the envelope models, as feet height over ground travel:
    per (kit, grid level) the kit's jump with that level's frame-perfect
    flap ticks (the physics' per-tick model; every tier flies the same arc,
    its margins are distances) [computed].  A flight to a landing dh above
    the takeoff, gap d away, is that path cut at its last descending
    crossing of dh and scaled along the ground to d [inferred: air control
    spreads a slower run evenly over the flight]."""

    def __init__(self, env: Env):
        self.paths = []                  # (x, z, suffix max of z) per tick, relative to the takeoff (contiguous,
                                         # as a kept copy reads back: Env.kept)
        self.turns = []                  # per path: the ground travel of its turning points
        p, cache = env.env.p, {}
        floor = -(env.max_drop.get("phys", 17.0) + 4.0)
        ids = {}
        for ki, (kname, rk) in enumerate(KITS):
            col = []
            for ticks in env.sched[kname]:
                key = (rk, tuple(ticks))
                if key not in cache:
                    rows = [r for r in p.tick_arc(env.env.kit(rk, FLAP_CAP[kname]), ticks, v0_xy=(env.movement.run_speed, 0.0),
                                                  z_floor=floor, max_ticks=4000) if r[1] != "flap"]
                    x = np.array([r[2] for r in rows], dtype=np.float64)
                    z = np.array([r[4] for r in rows], dtype=np.float64)
                    cache[key] = len(self.paths)
                    self.paths.append((x, z, np.ascontiguousarray(np.maximum.accumulate(z[::-1])[::-1])))
                    # the turning points (apexes, and the lows between flaps): with them among the sweep's
                    # points the feet height is monotone between consecutive points
                    dz = np.diff(z)
                    self.turns.append(x[np.nonzero((dz[:-1] > 0) != (dz[1:] > 0))[0] + 1])
                col.append(cache[key])
            ids[ki] = np.array(col)
        self.lookup = {(tname, ki): ids[ki] for tname in TIERS + ("phys", "zone") for ki in range(len(KITS))}
        # per flap kit, its steepest arc too: the flaps that rise highest, from standing (a short hop up a high
        # ledge climbs at once; the travel-maximizing flaps come late and dip first)
        self.climb = {}
        for ki, (kname, rk) in enumerate(KITS):
            if FLAP_CAP[kname] == 0:
                continue
            kit = env.env.kit(rk, FLAP_CAP[kname])
            ticks = p.best(kit, -60.0, objective="apex", beam=env.env.beam)[1]
            rows = [r for r in p.tick_arc(kit, ticks, v0_xy=(0.0, 0.0), z_floor=floor, max_ticks=4000) if r[1] != "flap"]
            x = np.array([r[2] for r in rows], dtype=np.float64)
            z = np.array([r[4] for r in rows], dtype=np.float64)
            self.climb[ki] = len(self.paths)
            self.paths.append((x, z, np.ascontiguousarray(np.maximum.accumulate(z[::-1])[::-1])))
            dz = np.diff(z)
            self.turns.append(x[np.nonzero((dz[:-1] > 0) != (dz[1:] > 0))[0] + 1])

    def apex(self, path) -> float:
        """The path's highest feet height above the takeoff."""
        return float(self.paths[path][2][0])

    def cut(self, path, dh):
        """Per flight: (the level the path is cut at: dh, or just under the
        path's top when dh is above it, the lip lift's case; the ground
        travel to that crossing)."""
        x, z, sm = self.paths[path]
        lvl = np.minimum(dh, sm[0] - 0.02)
        last = np.clip(np.searchsorted(-sm, -lvl, "right") - 1, 0, len(z) - 2)     # last tick with z >= lvl
        f = np.clip((z[last] - lvl) / np.maximum(z[last] - z[last + 1], 1e-9), 0.0, 1.0)
        return lvl, x[last] + f * (x[last + 1] - x[last])


# --------------------------------------------------------------------------- the sweep
def _bins(w: Walk, mask, binc, keep_max):
    """One sample per (region, bin of binc cells): the highest (takeoff) or lowest (landing)."""
    idx = np.nonzero(mask & (w.reg >= 0))[0]
    if not len(idx):
        return idx
    ix = (w.col[idx] % w.lv.NX) // binc
    iy = (w.col[idx] // w.lv.NX) // binc
    key = (w.reg[idx].astype(np.int64) * 1_000_003 + iy) * 1_000_003 + ix
    zz = -w.z[idx] if keep_max else w.z[idx]
    o = np.lexsort((zz, key))
    first = np.concatenate(([True], key[o][1:] != key[o][:-1]))
    return idx[o][first]


def _flight_points(lv, xa, ya, xb, yb, d):
    """Body sample points along each straight ground track: (flight, ground distance, column, index, count)."""
    ns = np.clip(np.ceil(d / SWEEP_STEP).astype(np.int64) + 1, 2, 2000)
    pid = np.repeat(np.arange(len(d)), ns)
    k = np.arange(len(pid)) - np.repeat(np.cumsum(ns) - ns, ns)
    t = k / (ns[pid] - 1)
    s = t * d[pid]
    cols = lv.col(xa[pid] + t * (xb - xa)[pid], ya[pid] + t * (yb - ya)[pid])
    return pid, s, cols, k, ns


def _body(spans: Spans, cols, L, U, H):
    """For a body with feet at L and head top at U in each column: (poke,
    roof).  A span starting below the body's middle (L + H/2) is under the
    feet: ``poke`` is how far its top rises above the feet (a floor, a
    hurdle, or a wall through the body).  A span starting between the middle
    and U - HEAD_TOL is a ceiling or a roof the body would pass through."""
    a, c = spans.range_of(cols)
    poke = np.full(len(cols), -np.inf)
    roof = np.zeros(len(cols), dtype=bool)
    mid = L + H / 2
    top_ok = U - HEAD_TOL
    idx = np.nonzero(c > 0)[0]
    j = 0
    while len(idx):
        s_ = a[idx] + j
        b, t = spans.bot[s_], spans.top[s_]
        fl = b < mid[idx]
        poke[idx] = np.where(fl, np.maximum(poke[idx], t - L[idx]), poke[idx])
        roof[idx] |= ~fl & (b < top_ok[idx])
        j += 1
        idx = idx[(c[idx] > j) & (b < top_ok[idx])]
    return poke, roof


def _heights(kind, path, arcs, pid, s, za, zb, sA, sB, zcut=None):
    """Feet heights along a flight: the takeoff height up to sA (walking),
    the flight over [sA, sB] (``walk``: a fall from rest at a constant ground
    speed; else the Arcs path scaled onto it, cut at ``zcut``: the landing
    height, or under it by the rim step-up), the landing height from sB."""
    za_p, zb_p, a_, b_ = za[pid], zb[pid], sA[pid], sB[pid]
    u = np.clip((s - a_) / np.maximum(b_ - a_, 1e-6), 0.0, 1.0)
    if kind == "walk":
        h = za_p + (zb_p - za_p) * u * u
    else:
        x, z, _ = arcs.paths[path]
        _, xT = arcs.cut(path, (zb if zcut is None else zcut) - za)
        h = za_p + np.interp(u * xT[pid], x, z)
        h = np.where(s >= b_, zb_p, h)
    h = np.where(s <= a_, za_p, h)
    first = np.concatenate(([True], pid[1:] != pid[:-1]))
    last = np.concatenate((pid[1:] != pid[:-1], [True]))
    return np.where(first, za_p, np.where(last, zb_p, h))


def _flight_track(lv, arcs, kind, path, xa, ya, za, xb, yb, zb, d, sA, sB, zcut=None):
    """The sweep's points of each flight, sorted by flight then ground
    distance s: the uniform grid, every crossing of a column boundary by
    the ground track, sA and sB, and (an arc) the path's turning points.
    Returns (pid, s, x, y, h)."""
    n = len(d)
    ns = np.clip(np.ceil(d / SWEEP_STEP).astype(np.int64) + 1, 2, 4000)
    p0 = np.repeat(np.arange(n), ns)
    k = np.arange(len(p0)) - np.repeat(np.cumsum(ns) - ns, ns)
    pid, s = [p0], [k / (ns[p0] - 1) * d[p0]]
    for a_, b_, o_ in ((xa, xb, lv.x0), (ya, yb, lv.y0)):
        ga, gb = (a_ - o_) / CELL, (b_ - o_) / CELL
        lo = np.floor(np.minimum(ga, gb)).astype(np.int64) + 1
        hi = np.ceil(np.maximum(ga, gb)).astype(np.int64) - 1
        cnt = np.clip(hi - lo + 1, 0, 8000)
        p_ = np.repeat(np.arange(n), cnt)
        kk = lo[p_] + (np.arange(len(p_)) - np.repeat(np.cumsum(cnt) - cnt, cnt))
        den = (gb - ga)[p_]
        okd = np.abs(den) > 1e-12
        t = np.where(okd, (kk - ga[p_]) / np.where(okd, den, 1.0), 0.0)
        pid.append(p_)
        s.append(np.clip(t, 0.0, 1.0) * d[p_])
    pid += [np.arange(n), np.arange(n)]
    s += [np.clip(sA, 0.0, d), np.clip(sB, 0.0, d)]
    if kind != "walk" and len(arcs.turns[path]):
        _, xT = arcs.cut(path, (zb if zcut is None else zcut) - za)
        u = arcs.turns[path][None, :] / np.maximum(xT[:, None], 1e-9)
        fi, ki = np.nonzero((u > 0) & (u < 1))
        pid.append(fi)
        s.append(sA[fi] + u[fi, ki] * (sB - sA)[fi])
    pid, s = np.concatenate(pid), np.concatenate(s)
    o = np.lexsort((s, pid))
    pid, s = pid[o], s[o]
    head = np.concatenate(([True], pid[1:] != pid[:-1]))
    tail = np.concatenate((pid[1:] != pid[:-1], [True]))
    keep = head | tail | np.concatenate(([True], s[1:] - s[:-1] > 1e-7))
    pid, s = pid[keep], s[keep]
    t = s / np.maximum(d[pid], 1e-9)
    x = xa[pid] + t * (xb - xa)[pid]
    y = ya[pid] + t * (yb - ya)[pid]
    return pid, s, x, y, _heights(kind, path, arcs, pid, s, za, zb, sA, sB, zcut)


def _roof_low(spans: Spans, cols, lo):
    """The bottom of the lowest solid span starting at or above lo[i] in
    column cols[i] (inf: open sky)."""
    a, c = spans.range_of(cols)
    out = np.full(len(cols), np.inf)
    idx = np.nonzero(c > 0)[0]
    j = 0
    while len(idx):
        s_ = a[idx] + j
        b = spans.bot[s_]
        hit = b >= lo[idx]
        out[idx[hit]] = np.minimum(out[idx[hit]], b[hit])
        j += 1
        idx = idx[(c[idx] > j) & ~hit]
    return out


def _hits(spans: Spans, cols, lo, hi):
    """Does any solid span of column cols[i] overlap the open interval (lo[i], hi[i])?"""
    a, c = spans.range_of(cols)
    res = np.zeros(len(cols), dtype=bool)
    idx = np.nonzero(c > 0)[0]
    j = 0
    while len(idx):
        s_ = a[idx] + j
        b, t = spans.bot[s_], spans.top[s_]
        res[idx] |= (b < hi[idx]) & (t > lo[idx])
        j += 1
        idx = idx[(c[idx] > j) & ~res[idx] & (b < hi[idx])]
    return res


def _flight_check(lv, spans, pid, s, x, y, h, H, end_lo, end_hi, n, perp, sA=None, sB=None):
    """The whole flight (_flight_track's points) against the solid spans:
    each step k -> k+1 is swept, [min h, max h + H], in the one column it
    lies in.  Mid-flight the body's middle band must also be free on at
    least one side 0.4 m off the track.  Returns per flight: roof (a
    ceiling, a roof, a floor slab or a slit is passed through), the largest
    poke within the end windows (s <= end_lo or s >= end_hi) and elsewhere,
    the highest top under the body away from the ends (absolute), and the
    least room over the head (HEAD_TOL in) under the roofs over the whole
    flight, over its arc's first :data:`ROOF_END` and over its last ([n, 3];
    the arc between ``sA`` and ``sB``; inf: open sky there; AZ-387)."""
    endf = (s <= end_lo[pid]) | (s >= end_hi[pid])
    same = np.concatenate((pid[1:] == pid[:-1], [False]))
    k0 = np.nonzero(same)[0]
    k1 = k0 + 1
    cm = lv.col((x[k0] + x[k1]) / 2, (y[k0] + y[k1]) / 2)
    LL = np.minimum(h[k0], h[k1])
    UU = np.maximum(h[k0], h[k1]) + H
    ff = pid[k0]
    ee = endf[k0] | endf[k1]
    poke, roof = _body(spans, cm, LL, UU, H)
    r = np.zeros(n, dtype=bool)
    np.logical_or.at(r, ff, roof)
    free = np.full((n, 3), np.inf)   # the least room between the head (with HEAD_TOL) and the roof above it
    room = _roof_low(spans, cm, LL + H / 2) - (UU - HEAD_TOL)
    np.minimum.at(free[:, 0], ff, room)
    if sA is not None:               # the arc's ends apart (AZ-387): a step by its midpoint's share of the arc
        u = ((s[k0] + s[k1]) / 2 - sA[ff]) / np.maximum(sB[ff] - sA[ff], 1e-6)
        for col, at in ((1, u <= ROOF_END), (2, u >= 1.0 - ROOF_END)):
            np.minimum.at(free[:, col], ff[at], room[at])
    pe = np.full(n, -np.inf)
    pm = np.full(n, -np.inf)
    top = np.full(n, -np.inf)
    np.maximum.at(pe, ff[ee], poke[ee])
    np.maximum.at(pm, ff[~ee], poke[~ee])
    np.maximum.at(top, ff[~ee], (poke + LL)[~ee])
    # the thin-body probes: at every point and every step's midpoint (spacing <= 0.125 m), mid-flight
    lx = np.concatenate((x, (x[k0] + x[k1]) / 2))
    ly = np.concatenate((y, (y[k0] + y[k1]) / 2))
    lh = np.concatenate((h, (h[k0] + h[k1]) / 2))
    lp = np.concatenate((pid, ff))
    q = np.nonzero(~np.concatenate((endf, ee)) & ~r[lp])[0]
    if len(q):
        px_, py_ = perp[0][lp[q]], perp[1][lp[q]]
        both = _hits(spans, lv.col(lx[q] + SIDE_M * px_, ly[q] + SIDE_M * py_), lh[q] + SIDE_BAND[0],
                     lh[q] + SIDE_BAND[1])
        qq = q[both]
        both2 = _hits(spans, lv.col(lx[qq] - SIDE_M * perp[0][lp[qq]], ly[qq] - SIDE_M * perp[1][lp[qq]]),
                      lh[qq] + SIDE_BAND[0], lh[qq] + SIDE_BAND[1])
        r[lp[qq[both2]]] = True
    return r, pe, pm, top, free


def _walk_supported(w: Walk, cols, z, climb):
    """Is there a logic walk sample within the walking step of z in each
    column (the body still walks there on a floor the logic walk uses)?"""
    a, c = lookup(w.u, w.a, w.c, cols)
    sup = np.zeros(len(cols), dtype=bool)
    idx = np.nonzero(c > 0)[0]
    j = 0
    while len(idx):
        s_ = a[idx] + j
        sup[idx] |= np.abs(w.z[s_] - z[idx]) <= climb
        j += 1
        idx = idx[(c[idx] > j) & ~sup[idx]]
    return sup


def _chunks(d, limit=FLIGHT_CHUNK):
    """Index blocks of flights whose body samples total at most ``limit`` (at least one flight each)."""
    ns = np.clip(np.ceil(d / SWEEP_STEP).astype(np.int64) + 1, 2, 2000)
    cum = np.cumsum(ns)
    start = 0
    while start < len(d):
        base = cum[start - 1] if start else 0
        end = max(int(np.searchsorted(cum, base + limit, "right")), start + 1)
        yield np.arange(start, end)
        start = end


def _track_edges(lv, w, xa, ya, za, xb, yb, zb, d, climb):
    """Per flight along its straight ground track: s0, where the takeoff
    floor (logic walk samples within the walking step of the takeoff
    height, contiguous from the takeoff) ends, and s1, where the landing
    floor (contiguous to the landing) begins; s1 - s0 is the edge-to-edge
    gap the envelope's gap means."""
    n = len(d)
    s0 = np.zeros(n)
    s1 = d.copy()
    for q in _chunks(d):
        pid, s, cols, k, ns = _flight_points(lv, xa[q], ya[q], xb[q], yb[q], d[q])
        supa = _walk_supported(w, cols, za[q][pid], climb)
        supb = _walk_supported(w, cols, zb[q][pid], climb)
        fu = ns.copy()
        np.minimum.at(fu, pid[~supa], k[~supa])
        lu = np.full(len(q), -1, dtype=np.int64)
        np.maximum.at(lu, pid[~supb], k[~supb])
        stp = d[q] / (ns - 1)
        s0[q] = np.clip((fu - 0.5) * stp, 0.0, d[q])
        s1[q] = np.clip((lu + 0.5) * stp, 0.0, d[q])
    return s0, s1


def _lip_slope(lv, spans, w, xa, ya, za, xb, yb, d, s0, climb):
    """Per flight, how far the takeoff floor falls a metre along its ground track at its edge (AZ-365; 0 where it
    rises, is level or holds no sample): the plane of the top triangle under the logic walk sample within the
    walking step of the takeoff height in the column half a cell before s0, where the takeoff floor ends.  A
    walk-off leaves along it at the run speed, so the steeper the lip, the faster it falls and the less it carries
    (L3, Step X.16: 17 of 28 lips slope down, the body leaving at 0.7-2.9 m/s down)."""
    dd = np.maximum(d, 1e-9)
    ux, uy = (xb - xa) / dd, (yb - ya) / dd
    t = np.clip(s0 - CELL / 2, 0.0, d)
    a, c = lookup(w.u, w.a, w.c, lv.col(xa + ux * t, ya + uy * t))
    tri = np.full(len(d), -1, dtype=np.int64)
    best = np.full(len(d), np.inf)
    idx = np.nonzero(c > 0)[0]
    j = 0
    while len(idx):
        s_ = a[idx] + j
        dz = np.abs(w.z[s_] - za[idx])
        take = (dz <= climb) & (dz < best[idx])
        best[idx[take]] = dz[take]
        tri[idx[take]] = spans.toptri[w.sidx[s_[take]]]
        j += 1
        idx = idx[c[idx] > j]
    P = lv.P[np.maximum(tri, 0)]
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    n = n * np.where(n[:, 2] < 0, -1.0, 1.0)[:, None]
    fall = (n[:, 0] * ux + n[:, 1] * uy) / np.maximum(n[:, 2], 1e-9)
    return np.where(tri >= 0, np.clip(fall, 0.0, None), 0.0)


def _rim(lv, spans, xa, ya, za, xb, yb, zb, d, s0, s1, climb):
    """Per flight, the rim step-up's lift (m; 0: none): RIM_LIFT where a
    sloped rim (a solid top in the slope band RIM_NZ, within RIM_LIFT under
    the landing floor's top) stands in one of the two columns before the
    landing floor's edge s1 on the ground track, else RIM_STEP_LIFT where
    the two floors meet within a cell across a riser higher than the
    walking step (the riser's slope is below the columns' resolution).  The
    body that meets the rim or the riser is lifted onto the floor by the
    step-up (AZ-352)."""
    out = np.zeros(len(d), dtype=bool)
    for back in (CELL / 2, 1.5 * CELL):
        t = np.clip(s1 - back, 0.0, d) / np.maximum(d, 1e-9)
        cols = lv.col(xa + t * (xb - xa), ya + t * (yb - ya))
        a, c = spans.range_of(cols)
        hit = np.zeros(len(d), dtype=bool)
        best = np.full(len(d), -np.inf)
        idx = np.nonzero(c > 0)[0]
        j = 0
        while len(idx):
            s_ = a[idx] + j
            tp = spans.top[s_]
            nz = lv.tri_nz[spans.toptri[s_]]
            take = (tp <= zb[idx] + 0.1) & (tp > best[idx])
            best[idx[take]] = tp[take]
            hit[idx[take]] = (nz[take] >= RIM_NZ[0]) & (nz[take] < RIM_NZ[1]) \
                & (zb[idx[take]] - tp[take] <= RIM_LIFT + 0.1)
            j += 1
            idx = idx[c[idx] > j]
        out |= hit
    step = ~out & (s1 - s0 <= CELL) & (zb - za > climb)
    return np.where(out, RIM_LIFT, np.where(step, RIM_STEP_LIFT, 0.0))


def _fly(lv, spans, arcs, kind, path, xa, ya, za, xb, yb, zb, d, H, sA, sB, end_tol_extra=None, zcut=None,
         end_back=0.0):
    """Sweep one flight shape for every flight.  The end windows (walking
    tolerance) are the walk before sA and after sB and END_M at both ends
    (the landing's ``end_back`` m longer).  Returns roof, poke_end (less
    end_tol_extra, the lip lift or the rim step-up a flight may use at the
    landing), poke_mid, top_mid and free (the least room above the head,
    HEAD_TOL included, under the roofs over the flight, over its arc's first
    and over its last :data:`ROOF_END`: [n, 3], AZ-387).  ``zcut`` (an
    arc): the height the arc is cut at, under the landing by the rim
    step-up."""
    n = len(d)
    roof = np.ones(n, dtype=bool)
    pe = np.full(n, np.inf)
    pm = np.full(n, np.inf)
    top = np.full(n, -np.inf)
    free = np.full((n, 3), np.inf)
    dd = np.maximum(d, 1e-9)
    px, py = -(yb - ya) / dd, (xb - xa) / dd
    for q in _chunks(d):
        pid, s, x, y, h = _flight_track(lv, arcs, kind, path, xa[q], ya[q], za[q], xb[q], yb[q], zb[q], d[q],
                                        sA[q], sB[q], None if zcut is None else zcut[q])
        r, a_, b_, t_, f_ = _flight_check(lv, spans, pid, s, x, y, h, H, np.maximum(END_M, sA[q] + SWEEP_STEP),
                                          np.minimum(d[q] - END_M, sB[q] - SWEEP_STEP) - end_back, len(q),
                                          (px[q], py[q]), sA[q], sB[q])
        roof[q], pe[q], pm[q], top[q] = r, a_ - (0.0 if end_tol_extra is None else end_tol_extra[q]), b_, t_
        free[q] = f_
    return roof, pe, pm, top, free


def _plain_ledge(lv, spans, xa, ya, za, xb, yb, zb, d, climb):
    """The lip lift's ledge from the collision: along the ground track the
    floor under the body steps from the takeoff level (within the walking
    step) to the ledge top (within 0.15 m) between two adjacent samples (a
    vertical face) and stays at the ledge top for the next two samples (a
    flat top).  Returns (ok, face_m): face_m is how far before the face the
    takeoff sample stands, measured to where the face stops the body (face
    - body radius)."""
    n = len(d)
    ok = np.zeros(n, dtype=bool)
    face = np.full(n, np.nan)
    if not n:
        return ok, face
    pid, s, cols, k, ns = _flight_points(lv, xa, ya, xb, yb, d)
    lim = np.maximum(za, zb)[pid] + 0.5
    a, c = spans.range_of(cols)
    ft = np.full(len(cols), -np.inf)
    idx = np.nonzero(c > 0)[0]
    j = 0
    while len(idx):
        s_ = a[idx] + j
        t = spans.top[s_]
        ft[idx] = np.where(t <= lim[idx], np.maximum(ft[idx], t), ft[idx])
        j += 1
        idx = idx[(c[idx] > j) & (spans.bot[s_] <= lim[idx])]
    on_top = np.abs(ft - zb[pid]) <= 0.15
    low = ft <= za[pid] + climb
    first = np.full(n, 10 ** 9, dtype=np.int64)
    idx_on = np.nonzero(on_top)[0]
    np.minimum.at(first, pid[idx_on], idx_on)
    has = first < 10 ** 9
    g = np.where(has, first, 0)
    prev_low = has & (g > 0) & (pid[np.maximum(g - 1, 0)] == np.arange(n)) & low[np.maximum(g - 1, 0)]
    flat = has.copy()
    for off in (1, 2):
        gg = np.minimum(g + off, len(pid) - 1)
        flat &= (pid[gg] != np.arange(n)) | on_top[gg]
    fm = np.where(has, (s[g] + s[np.maximum(g - 1, 0)]) / 2 - BODY_R, np.nan)
    return prev_low & flat, fm


def _room_ok(lv, spans, w, i, j, width):
    """Is the landable surface (solid tops with nz >= 0.6 within 1 m of the
    landing height) across the flight line i -> j at landing sample j at
    least ``width`` wide?  It is probed in steps of width/4 out to
    ``width`` on each side; the contiguous landable run through j must span
    ``width`` [proposal: the tier's landing room]."""
    ok = np.ones(len(j), dtype=bool)
    need = width > CELL
    if not need.any():
        return ok
    dx, dy = w.x[j] - w.x[i], w.y[j] - w.y[i]
    d = np.maximum(np.hypot(dx, dy), 1e-6)
    px, py = -dy / d, dx / d
    zj = w.z[j]
    runs = []
    for sgn in (1.0, -1.0):
        run = np.zeros(len(j), dtype=np.int8)
        alive = np.ones(len(j), dtype=bool)
        for q in (1, 2, 3, 4):
            off = sgn * width * q / 4.0
            cols = lv.col(w.x[j] + off * px, w.y[j] + off * py)
            a, c = spans.range_of(cols)
            hit = np.zeros(len(j), dtype=bool)
            for k in range(spans.maxper):
                v = k < c
                s = np.where(v, a + k, 0)
                hit |= v & (np.abs(spans.top[s] - zj) <= 1.0) & (lv.tri_nz[spans.toptri[s]] >= SLOPE_LAND)
            alive &= hit
            run += alive
        runs.append(run)
    return (runs[0] + runs[1] >= 4) | ~need


def _resolve_flights(lv, spans, w, env, tiers, i, j, gap, dh, stand, haz):
    """Per flight and tier: the least kit rank whose whole flight is clear,
    with the envelope's gap table (or the lip lift onto a plain ledge in the
    tier's window), the landing room rule and the tier's clearance over
    every hurdle away from the ends; the walk-off (no jump: rank 0) likewise
    lands just past the landing floor's edge or at the landing sample.
    Returns (R, K, L, wall, hurdle, haz owners, profile, reject, face,
    gap_edge): wall = no clear flight at any tier (R then holds the
    envelope's ranks for the probe-needed edge), reject = a wall flight
    that can only pass a solid."""
    p = w.p
    H, climb = p["height"], p["climb"]
    arcs = env.arcs()
    n, T = len(i), len(tiers)
    za, zb = w.z[i], w.z[j]
    xa, ya, xb, yb = w.x[i], w.y[i], w.x[j], w.y[j]
    s0, s1 = _track_edges(lv, w, xa, ya, za, xb, yb, zb, gap, climb)
    gap_e = np.maximum(s1 - s0, 0.0)
    shapes = {   # name -> (envelope gap, flight start, flight end)
        "edge": (gap_e, np.maximum(s0 - SWEEP_STEP, 0.0),
                 np.minimum(np.maximum(s1 + SWEEP_STEP, np.maximum(s0 - SWEEP_STEP, 0.0) + 2 * SWEEP_STEP), gap)),
        "full": (gap, np.zeros(n), gap)}
    OK = {nm: np.zeros((n, T, len(KITS)), dtype=bool) for nm in shapes}
    LIPC = np.zeros((n, T, len(KITS)), dtype=bool)
    ROOM = np.ones((n, T), dtype=bool)
    CELL_I = np.zeros(n, dtype=np.int64)
    for ti, tn in enumerate(tiers):
        side = env.side.get(tn, 0.0)
        if side > 0:
            ROOM[:, ti] = _room_ok(lv, spans, w, i, j, np.maximum(gap - ROOM_FREE_M, 0.0) * side)
        for nm, (g_, _, _) in shapes.items():
            ok, lipc, CELL_I = env.kits_ok(tn, dh, g_, stand)
            OK[nm][:, ti] = ok & ROOM[:, ti, None]
            if nm == "full":
                LIPC[:, ti] = lipc & ROOM[:, ti, None]
    anyok = OK["edge"] | OK["full"] | LIPC          # the envelope alone (what a probe-needed edge keeps)
    envR = np.full((n, T), 4, dtype=np.int8)
    for ki in range(len(KITS) - 1, -1, -1):
        envR = np.where(anyok[:, :, ki], KITS[ki][1], envR)
    # the plain-ledge test once per flight with a lip candidate, then each tier's window for each kit's deficit
    lipq = np.nonzero(LIPC.any((1, 2)))[0]
    plain = np.zeros(n, dtype=bool)
    face = np.full(n, np.nan)
    if len(lipq):
        plain[lipq], face[lipq] = _plain_ledge(lv, spans, xa[lipq], ya[lipq], za[lipq], xb[lipq], yb[lipq], zb[lipq],
                                               gap[lipq], climb)
    LIPC &= plain[:, None, None]
    for ti, tn in enumerate(tiers):
        room = lip_room(tn)
        for ki, (kname, _) in enumerate(KITS):
            m = np.nonzero(LIPC[:, ti, ki])[0]
            if len(m):
                # the window holds the tier's rows, and the takeoff floor (s0: where it ends ahead of the sample)
                # carries the run over them: across a pit there is no floor to press from
                near, far = lip_windows(tn, dh[m] - env.apex[(tn, kname)])
                LIPC[m, ti, ki] = (face[m] >= near) & (face[m] <= far) & (s0[m] >= room)
    R = np.full((n, T), 4, dtype=np.int8)
    K = np.full((n, T), -1, dtype=np.int8)
    L = np.zeros((n, T), dtype=bool)
    P = np.full((n, T), -1, dtype=np.int64)          # -2 the walk-off, else an Arcs path id
    V = np.zeros((n, T), dtype=np.int8)              # 0 the edge shape, 1 the full shape
    HT = np.full((n, T), -np.inf)                    # the highest top under the chosen flight (absolute)
    HR = np.full((n, T), np.nan)                     # its headroom over the takeoff (an arc: apex + body + free room)
    RS = np.full((n, T), np.inf)                     # the least room over the head over its arc's first and last
    RE = np.full((n, T), np.inf)                     # ROOF_END (AZ-387; inf: open sky there)
    WO = np.full((n, T), np.nan)                     # a walk-off's run off the edge to the landing, m
    DH = np.tile(dh[:, None], (1, T))                # the landing level the flight needs (under dh by the rim step-up)
    clr = np.array([env.clearance[tn] for tn in tiers])
    maxd = np.array([env.max_drop[tn] for tn in tiers])
    SL = np.zeros(n)                                 # a walk-off's lip slope (AZ-365)
    wo = np.nonzero(dh < -climb)[0]
    if len(wo):
        SL[wo] = _lip_slope(lv, spans, w, xa[wo], ya[wo], za[wo], xb[wo], yb[wo], gap[wo], s0[wo], climb)
    carry = env.carry(np.maximum(-dh, 0.0), slope=SL) + WALKOFF_SLACK
    zone_carry = env.carry(np.maximum(-dh, 0.0), zone=True, slope=SL) + WALKOFF_SLACK
    # 1. the walk-off: rank 0 wherever the tier counts the drop and the landing room holds
    for vi, nm in enumerate(("edge", "full")):
        if not len(wo):
            break
        sA = s0[wo]
        sB = np.minimum(np.maximum(s1[wo] + SWEEP_STEP, sA + SWEEP_STEP), gap[wo]) if nm == "edge" else gap[wo]
        valid = (sB - sA) <= carry[wo]
        if not valid.any():
            continue
        q = wo[valid]
        roof, pe, pm, top, _ = _fly(lv, spans, arcs, "walk", -2, xa[q], ya[q], za[q], xb[q], yb[q], zb[q], gap[q], H,
                                    s0[q], sB[valid])
        base = ~roof & (pe <= climb)
        run_off = (sB - sA)[valid]
        for ti in range(T):
            take = base & (pm <= -clr[ti]) & (-dh[q] <= maxd[ti]) & ROOM[q, ti] & (R[q, ti] > 0)
            if tiers[ti] == "zone":
                take &= run_off <= zone_carry[q]
            R[q[take], ti], K[q[take], ti], P[q[take], ti], V[q[take], ti], HT[q[take], ti] = 0, 0, -2, vi, top[take]
            WO[q[take], ti] = run_off[take]
    # 2. the modelled arcs, kit by kit (cheapest first), the edge shape then the full one
    for ki, (kname, rk) in enumerate(KITS):
        PT = np.stack([arcs.lookup[(tn, ki)][CELL_I] for tn in tiers], axis=1)     # (n, T) path ids
        for vi, nm in enumerate(("edge", "full")):
            okv = OK[nm][:, :, ki]
            need = (okv | LIPC[:, :, ki]) & (R > rk)
            if not need.any():
                continue
            _, sA_all, sB_all = shapes[nm]
            for path in np.unique(PT[need]).tolist():
                sub = np.nonzero((need & (PT == path)).any(1))[0]
                lvl, _ = arcs.cut(path, dh[sub])
                extra = np.maximum(dh[sub] - lvl, 0.0)
                roof, pe, pm, top, free = _fly(lv, spans, arcs, "arc", path, xa[sub], ya[sub], za[sub], xb[sub],
                                               yb[sub], zb[sub], gap[sub], H, sA_all[sub], sB_all[sub], extra)
                room_up = arcs.apex(path) + H + free[:, 0]
                for ti in range(T):
                    m = need[sub, ti] & (PT[sub, ti] == path) & (R[sub, ti] > rk)
                    good = m & ~roof & (pe <= climb) & (pm <= -clr[ti])
                    okk = good & okv[sub, ti] & (extra <= 1e-6)
                    lip = good & LIPC[sub, ti, ki] & ~okk
                    take = okk | lip
                    q = sub[take]
                    R[q, ti], K[q, ti], L[q, ti], P[q, ti], V[q, ti], HT[q, ti] = rk, ki, lip[take], path, vi, top[take]
                    HR[q, ti], RS[q, ti], RE[q, ti] = room_up[take], free[take, 1], free[take, 2]
            # the kit's steepest arc for what its farthest one doesn't clear, within that arc's own (standing) reach
            path = arcs.climb.get(ki)
            if path is None:
                continue
            g_ = shapes[nm][0]
            lvl, xT = arcs.cut(path, dh)
            need = okv & (R > rk) & ((dh - lvl) <= 1e-6)[:, None] & (g_ <= xT)[:, None]
            if not need.any():
                continue
            sub = np.nonzero(need.any(1))[0]
            roof, pe, pm, top, free = _fly(lv, spans, arcs, "arc", path, xa[sub], ya[sub], za[sub], xb[sub], yb[sub],
                                           zb[sub], gap[sub], H, sA_all[sub], sB_all[sub])
            room_up = arcs.apex(path) + H + free[:, 0]
            for ti in range(T):
                take = need[sub, ti] & (R[sub, ti] > rk) & ~roof & (pe <= climb) & (pm <= -clr[ti])
                q = sub[take]
                R[q, ti], K[q, ti], L[q, ti], P[q, ti], V[q, ti], HT[q, ti] = rk, ki, False, path, vi, top[take]
                HR[q, ti], RS[q, ti], RE[q, ti] = room_up[take], free[take, 1], free[take, 2]
    # 2b. the rim step-up (AZ-352): a flight that overshoots the far floor's top meets its sloped rim up to RIM_LIFT
    # under it and the step-up lifts the body on, so its landing level is dh - RIM_LIFT (the edge shape: the arc is
    # cut at the floor's edge); the player tiers and phys, never the zones' fixed free movement
    lift = _rim(lv, spans, xa, ya, za, xb, yb, zb, gap, s0, s1, climb)
    if (lift > 0).any():
        dh2 = dh - lift
        OK2 = np.zeros((n, T, len(KITS)), dtype=bool)
        for ti, tn in enumerate(tiers):
            if tn == "zone":
                continue
            ok2, _, CI2 = env.kits_ok(tn, dh2, shapes["edge"][0], stand)
            OK2[:, ti] = ok2 & ROOM[:, ti, None] & (lift > 0)[:, None]
        _, sA_all, sB_all = shapes["edge"]
        for ki, (kname, rk) in enumerate(KITS):
            need = OK2[:, :, ki] & (R > rk)
            if not need.any():
                continue
            PT = np.stack([arcs.lookup[(tn, ki)][CI2] for tn in tiers], axis=1)
            for path in np.unique(PT[need]).tolist():
                sub = np.nonzero((need & (PT == path)).any(1))[0]
                roof, pe, pm, top, free = _fly(lv, spans, arcs, "arc", path, xa[sub], ya[sub], za[sub], xb[sub],
                                               yb[sub], zb[sub], gap[sub], H, sA_all[sub], sB_all[sub], lift[sub],
                                               zb[sub] - lift[sub], end_back=CELL)
                room_up = arcs.apex(path) + H + free[:, 0]
                for ti in range(T):
                    take = need[sub, ti] & (PT[sub, ti] == path) & (R[sub, ti] > rk) & ~roof & (pe <= climb) \
                        & (pm <= -clr[ti])
                    q = sub[take]
                    R[q, ti], K[q, ti], L[q, ti], P[q, ti], V[q, ti], HT[q, ti] = rk, ki, False, path, 0, top[take]
                    HR[q, ti], DH[q, ti], RS[q, ti], RE[q, ti] = room_up[take], dh2[q], free[take, 1], free[take, 2]
    # monotone tiers: a harder tier may always fly what an easier one flies, so a tier whose own nominal flap
    # ticks lose a flight takes the easier tier's flight (its kit, lip, path and shape)
    for ti in range(1, T):
        take = R[:, ti - 1] < R[:, ti]
        for A_ in (R, K, L, P, V, HT, HR, WO, DH, RS, RE):
            A_[take, ti] = A_[take, ti - 1]
    envR = np.minimum.accumulate(envR, axis=1)
    wall = (R >= 4).all(1)
    # a wall flight that could only pass a solid: the same column, or a descent into (an ascent out of) a region
    # roofed everywhere below the takeoff (the landing) height
    good = w.reg >= 0
    maxceil = np.full(w.nreg, -np.inf)
    np.maximum.at(maxceil, w.reg[good], w.ceil[good])
    reject = wall & ((gap < SWEEP_STEP) | ((dh <= -1.0) & (maxceil[w.reg[j]] < za - 0.2))
                     | ((dh >= 1.0) & (maxceil[w.reg[i]] < zb - 0.2)))
    # a flight whose two ends lie in different air components can only pass a solid (a sealed room is entered by
    # no flight, not even a probe-needed one); a clear flight never splits (counted as a self-check)
    acomp = getattr(w, "acomp", None)
    if acomp is not None:
        split = acomp[i] != acomp[j]
        w.air_split = {"wall": int((split & wall).sum()), "clear": int((split & ~wall).sum())}
        reject |= split
    Rout = np.where(wall[:, None], envR, R)
    # the chosen flight per edge (its first usable tier; a wall flight: the envelope's cheapest kit at the most
    # permissive tier on the full track, or the walk-off) for the hurdle and the damage-volume check
    t0 = np.argmax(Rout < 4, axis=1)
    rows = np.arange(n)
    hurdle = np.where(wall, -np.inf, HT[rows, t0] - za)
    chosen = P[rows, t0].copy()
    shape = V[rows, t0].copy()
    if wall.any():
        kk = np.full(n, -1, dtype=np.int64)
        for ki in range(len(KITS) - 1, -1, -1):
            kk = np.where(anyok[:, -1, ki], ki, kk)
        LK = np.stack([arcs.lookup[(tiers[-1], ki)] for ki in range(len(KITS))])
        alt = np.where(kk >= 0, LK[np.maximum(kk, 0), CELL_I], -1)
        alt = np.where((dh < -climb) & (kk == 0), -2, alt)
        chosen = np.where(wall, alt, chosen)
        shape = np.where(wall, 1, shape)
    hz_own = [()] * n
    if haz is not None and haz[0] is not None and len(haz[1]) and len(haz[0].col):
        vol, owners = haz
        own_arr = np.asarray(sorted(owners))
        for path in np.unique(chosen).tolist():
            if path == -1:
                continue
            for vi in (0, 1):
                sub = np.nonzero((chosen == path) & (shape == vi))[0]
                if not len(sub):
                    continue
                if path == -2:
                    sA = s0[sub]
                    sB = (np.minimum(np.maximum(s1[sub] + SWEEP_STEP, sA + SWEEP_STEP), gap[sub]) if vi == 0
                          else gap[sub])
                else:
                    _, sA, sB = shapes["edge" if vi == 0 else "full"]
                    sA, sB = sA[sub], sB[sub]
                for q in _chunks(gap[sub]):
                    f = sub[q]
                    pid, s, x_, y_, h = _flight_track(lv, arcs, "walk" if path == -2 else "arc", path, xa[f], ya[f],
                                                      za[f], xb[f], yb[f], zb[f], gap[f], sA[q], sB[q])
                    hit, _ = vol.query(lv.col(x_, y_), h, h + H, owners=own_arr)
                    m = hit >= 0
                    for a_, o_ in set(zip(f[pid[m]].tolist(), hit[m].tolist())):
                        hz_own[a_] = tuple(sorted(set(hz_own[a_]) | {int(o_)}))
    prof = np.where(chosen == -2, "walk-off", np.where(chosen >= 0, "arc", "none"))
    prof = np.where(wall, "none", np.char.add(prof.astype(str), np.where(shape == 0, "", " (sample to sample)")))
    return Rout, K, L, wall, hurdle, hz_own, prof, reject, face, gap_e, {"V": V, "P": P, "HR": HR, "WO": WO, "DH": DH,
                                                                          "s0": s0, "SL": SL, "RS": RS, "RE": RE}


# --------------------------------------------------------------------------- the barriers a flight passes over
def _orient(ax, ay, bx, by, cx, cy):
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


class OverTest:
    """Which shut barriers a flight passes over.  A gate member that is
    there while its gate is shut (a toggled solid present at load, a driven
    damage volume that is on; not a crumbling floor, not a drag current) is
    a barrier; a flight whose straight ground track crosses the XY
    projection of one of its triangles, where that triangle reaches down to
    within the body's height of the higher end, goes over (or, for a
    damage volume, through: that is the gate's own edge) the barrier.  So
    does a flight that crosses the members' best-fit vertical plane (its
    ends at least OVER_SIDE_M off it, on opposite sides) within
    OVER_MARGIN_M of the members' extent along it: round the barrier's end,
    over the frame it stands in [proposal: the margin].  ``groups`` are
    (key, owner indices) per gate."""

    def __init__(self, lv: Level, groups, H):
        self.keys, self.H = [], H
        tris, gix = [], []
        for key, oids in groups:
            tri = np.nonzero(np.isin(lv.tri_owner, list(oids)))[0]
            if not len(tri):
                continue
            gix.append(np.full(len(tri), len(self.keys)))
            tris.append(tri)
            self.keys.append(key)
        self.n = len(self.keys)
        if not self.n:
            return
        tri = np.concatenate(tris)
        self.g = np.concatenate(gix)
        self.oi = lv.tri_owner[tri].astype(np.int64)
        P = lv.P[tri]
        self.x, self.y = P[:, :, 0].astype(np.float64), P[:, :, 1].astype(np.float64)
        self.zmin = P[:, :, 2].min(1).astype(np.float64)
        M = OVER_MARGIN_M
        self.bb = [(self.x[self.g == k].min() - M, self.x[self.g == k].max() + M, self.y[self.g == k].min() - M,
                    self.y[self.g == k].max() + M) for k in range(self.n)]
        self.plane = []
        for k in range(self.n):
            GP = np.c_[self.x[self.g == k].ravel(), self.y[self.g == k].ravel()]
            c0 = GP.mean(0)
            _, evec = np.linalg.eigh((GP - c0).T @ (GP - c0))
            nrm, ax = evec[:, 0], evec[:, 1]
            u = (GP - c0) @ ax
            self.plane.append((c0, nrm, ax, float(u.min()) - M, float(u.max()) + M, float(self.zmin[self.g == k].min()),
                               sorted(set(self.oi[self.g == k].tolist()))))

    def _hit(self, xa, ya, xb, yb, t):
        """(len(xa), len(t)) bool: does segment a->b cross triangle t's XY projection (an end inside it, or an edge crossed)?"""
        X, Y = self.x[t][None, :, :], self.y[t][None, :, :]
        ax, ay, bx, by = xa[:, None], ya[:, None], xb[:, None], yb[:, None]
        hit = np.zeros((len(xa), len(t)), dtype=bool)
        for k in range(3):
            px, py, qx, qy = X[:, :, k], Y[:, :, k], X[:, :, (k + 1) % 3], Y[:, :, (k + 1) % 3]
            o1, o2 = _orient(ax, ay, bx, by, px, py), _orient(ax, ay, bx, by, qx, qy)
            o3, o4 = _orient(px, py, qx, qy, ax, ay), _orient(px, py, qx, qy, bx, by)
            hit |= (o1 * o2 <= 0) & (o3 * o4 <= 0) & ~((o1 == 0) & (o2 == 0))
        area = _orient(X[:, :, 0], Y[:, :, 0], X[:, :, 1], Y[:, :, 1], X[:, :, 2], Y[:, :, 2])
        for ex_, ey_ in ((ax, ay), (bx, by)):
            s0 = _orient(X[:, :, 0], Y[:, :, 0], X[:, :, 1], Y[:, :, 1], ex_, ey_)
            s1 = _orient(X[:, :, 1], Y[:, :, 1], X[:, :, 2], Y[:, :, 2], ex_, ey_)
            s2 = _orient(X[:, :, 2], Y[:, :, 2], X[:, :, 0], Y[:, :, 0], ex_, ey_)
            inside = ((s0 >= 0) & (s1 >= 0) & (s2 >= 0)) | ((s0 <= 0) & (s1 <= 0) & (s2 <= 0))
            hit |= inside & (np.abs(area) > 1e-9)
        return hit

    def test(self, xa, ya, za, xb, yb, zb, hz=None, chunk=2_000_000):
        """Per flight: the sorted tuple of group keys it passes over (a group whose damage volume the flight passes
        through, ``hz``, is not)."""
        n = len(xa)
        out = [()] * n
        if not self.n or not n:
            return out
        top = np.maximum(za, zb) + self.H
        x0, x1, y0, y1 = np.minimum(xa, xb), np.maximum(xa, xb), np.minimum(ya, yb), np.maximum(ya, yb)
        found = collections.defaultdict(set)
        for k, (gx0, gx1, gy0, gy1) in enumerate(self.bb):
            q = np.nonzero((x1 >= gx0) & (x0 <= gx1) & (y1 >= gy0) & (y0 <= gy1))[0]
            if not len(q):
                continue
            c0, nrm, ax, u0, u1, zg, oig = self.plane[k]
            sa = (xa[q] - c0[0]) * nrm[0] + (ya[q] - c0[1]) * nrm[1]
            sb = (xb[q] - c0[0]) * nrm[0] + (yb[q] - c0[1]) * nrm[1]
            cr = (sa * sb < 0) & (np.minimum(np.abs(sa), np.abs(sb)) >= OVER_SIDE_M) & (zg <= top[q])
            tt = np.where(cr, sa / np.where(cr, sa - sb, 1.0), 0.0)
            uc = (xa[q] + tt * (xb[q] - xa[q]) - c0[0]) * ax[0] + (ya[q] + tt * (yb[q] - ya[q]) - c0[1]) * ax[1]
            cr &= (uc >= u0) & (uc <= u1)
            for q_ in q[cr].tolist():
                for oi in oig:
                    found[q_].add((k, oi))
            t = np.nonzero(self.g == k)[0]
            step = max(1, chunk // max(len(t), 1))
            for b0 in range(0, len(q), step):
                qq = q[b0:b0 + step]
                h = self._hit(xa[qq], ya[qq], xb[qq], yb[qq], t) & (self.zmin[t][None, :] <= top[qq][:, None])
                for r_, c_ in zip(*np.nonzero(h)):
                    found[int(qq[r_])].add((k, int(self.oi[t[c_]])))
        for q_, ks in found.items():
            own = set(hz[q_]) if hz is not None else set()
            keys = {self.keys[k] for k, oi in ks if oi not in own}
            keys -= {self.keys[k] for k, oi in ks if oi in own}     # through one of its volumes: the gate's own edge
            if keys:
                out[q_] = tuple(sorted(keys))
        return out


# --------------------------------------------------------------------------- the edges
def jump_edges(lv: Level, spans: Spans, w: Walk, env: Env, tiers, sweep=True, haz=None, stats=None, down=None,
               blockers=None, over=None):
    """Region -> region flight edges, keyed (from region, to region): per
    tier the rank (0 true, 1-3 air>=N, 4 none), the cheapest tier's kit and
    lip flag, the witness flight (sample indices, dh, gap) and its
    confidence.  ``haz`` = (Volumes, owners) are the damage volumes and
    downdrafts a flight must not pass through (``down`` names the
    downdrafts); ``blockers`` flags the samples no jump takes off from (a
    spring pad that hops the body); ``over`` (an :class:`OverTest`) keys a
    flight over a shut barrier apart, (from, to, ("over",) + gate keys),
    whatever the other flights between the two regions do; ``stats``
    collects counts."""
    p = w.p
    zone = sweep and "zone" not in tiers
    if zone:            # the zones' fixed free movement (envelope.ZONE), flown first and split off at the end
        tiers = ("zone",) + tuple(tiers)
    # run-up room: the area of the walk group (regions joined by slippery <-> plain walk links)
    if w.cross:
        ca, cb = zip(*w.cross)
        grp = components(w.nreg, ca, cb)
    else:
        grp = np.arange(w.nreg)
    garea = np.bincount(grp, weights=w.reg_count * CELL * CELL)
    small = garea[grp] < SMALL_REGION_M2
    # a takeoff from a small region is a standing jump (a sloped slippery floor, where the body slides and gets no
    # run-up, AZ-347, is no logic floor: AZ-359), and so is one from a near-flat slippery floor, where a run from a
    # stand slides and covers 6-8 m in 3 s against 20 m (L3, Step X.16), until L3 measures the ice run (AZ-366)
    stand_reg = small | w.reg_slip
    cands = []
    big = ~small[np.maximum(w.reg, 0)] & (w.reg >= 0)
    allm = np.ones(len(w.z), dtype=bool)
    NX = lv.NX
    for radius, kits_long in ((SHORT_R, False), (LONG_R, True)):
        if not kits_long:
            to = _bins(w, w.border, 2, keep_max=True)
            la = _bins(w, allm, 2, keep_max=False)
            block = 1500
        else:
            # the flap pass: regions of at least SMALL_REGION_M2 at both ends, 2 m takeoff bins, landing on 2 m
            # border bins plus 4 m interior bins
            to = _bins(w, w.border & big, 4, keep_max=True)
            la = np.union1d(_bins(w, w.border & big, 4, keep_max=False), _bins(w, big, 8, keep_max=False))
            block = 600
        index = RadiusIndex(np.c_[w.x[la], w.y[la]], radius)
        for b0 in range(0, len(to), block):
            tb = to[b0:b0 + block]
            qi, pj, gap = index.pairs(np.c_[w.x[tb], w.y[tb]])
            i, j = tb[qi], la[pj]
            ra, rb = w.reg[i], w.reg[j]
            dh = w.z[j] - w.z[i]
            m = (ra != rb) & (dh <= 2.8) & (dh >= -17.0)
            if kits_long:
                m &= gap > SHORT_R - 1.0
            i, j, gap, ra, rb, dh = i[m], j[m], gap[m], ra[m], rb[m], dh[m]
            if not len(i):
                continue
            stand = stand_reg[ra]
            R = np.zeros((len(i), len(tiers)), dtype=np.int8)
            K = np.zeros((len(i), len(tiers)), dtype=np.int8)
            L = np.zeros((len(i), len(tiers)), dtype=bool)
            for ti, tn in enumerate(tiers):
                if sweep:
                    ok, lipc, _ = env.kits_ok(tn, dh, gap, stand)
                    anyk = ok | lipc
                    R[:, ti] = np.where(anyk.any(1), np.array([rk for _, rk in KITS])[np.argmax(anyk, 1)], 4)
                else:
                    R[:, ti], K[:, ti], L[:, ti] = env.rank(tn, dh, gap, stand)
                side = env.side.get(tn, 0.0)
                if side > 0:
                    live = R[:, ti] < 4
                    if live.any():
                        q = np.nonzero(live)[0]
                        room = _room_ok(lv, spans, w, i[q], j[q], np.maximum(gap[q] - ROOM_FREE_M, 0.0) * side)
                        R[q[~room], ti] = 4
            ok = R.min(1) < 4
            if not ok.any():
                continue
            i, j, gap, ra, rb, dh, R, K, L = (x[ok] for x in (i, j, gap, ra, rb, dh, R, K, L))
            key = ra.astype(np.int64) * w.nreg + rb
            # keep, per key, the KEEP_BEST best by (rank at the most permissive tier, rank at the first, gap) and by
            # (rank at the first tier, gap); with the sweep, also the best per (takeoff 4 m cell, landing 4 m cell),
            # up to KEEP_SPREAD of those per key (the sweep may block the shortest ones)
            sel = set()
            for cols in ((R[:, -1], R[:, 0], gap), (R[:, 0], gap)):
                o = np.lexsort(tuple(reversed(cols)) + (key,))
                ks = key[o]
                head = np.concatenate(([True], ks[1:] != ks[:-1]))
                rankin = np.arange(len(o)) - np.maximum.accumulate(np.where(head, np.arange(len(o)), 0))
                sel.update(o[rankin < KEEP_BEST].tolist())
            if sweep:
                tbx, tby = (w.col[i] % NX) // SPREAD_BIN, (w.col[i] // NX) // SPREAD_BIN
                lbx, lby = (w.col[j] % NX) // SPREAD_BIN, (w.col[j] // NX) // SPREAD_BIN
                o = np.lexsort((gap, R[:, 0], lby, lbx, tby, tbx, key))
                diff = np.zeros(max(len(o) - 1, 0), dtype=bool)
                for arr in (key, tbx, tby, lbx, lby):
                    diff |= arr[o][1:] != arr[o][:-1]
                hs = o[np.concatenate(([True], diff))]
                o2 = hs[np.lexsort((gap[hs], R[hs, 0], key[hs]))]
                ks = key[o2]
                head = np.concatenate(([True], ks[1:] != ks[:-1]))
                rankin = np.arange(len(o2)) - np.maximum.accumulate(np.where(head, np.arange(len(o2)), 0))
                sel.update(o2[rankin < KEEP_SPREAD].tolist())
            sel = np.array(sorted(sel))
            cands.append((i[sel], j[sel], gap[sel], dh[sel], ra[sel], rb[sel], R[sel], K[sel], L[sel]))
    if not cands:
        return {}
    i, j, gap, dh, ra, rb, R, K, L = (np.concatenate(z) for z in zip(*cands))
    n = len(i)
    hurdle = np.full(n, -np.inf)
    hz_own = [()] * n
    wall = np.zeros(n, dtype=bool)
    prof = np.full(n, "envelope", dtype=object)
    face = np.full(n, np.nan)
    gap_e = gap.copy()
    stand = stand_reg[ra]
    T = len(tiers)
    geo = {"V": np.ones((n, T), dtype=np.int8), "P": np.full((n, T), -1, dtype=np.int64),
           "HR": np.full((n, T), np.nan), "WO": np.full((n, T), np.nan), "DH": np.tile(dh[:, None], (1, T)),
           "s0": np.zeros(n), "SL": np.zeros(n), "RS": np.full((n, T), np.inf), "RE": np.full((n, T), np.inf)}
    if sweep:
        R, K, L, wall, hurdle, hz_own, prof, reject, face, gap_e, geo = _resolve_flights(lv, spans, w, env, tiers, i, j,
                                                                                         gap, dh, stand, haz)
        # a takeoff from a spring blocker (every jump from it is a short hop) keeps only its walk-offs
        if blockers is not None and blockers.any():
            bl = blockers[i] & ~np.char.startswith(prof.astype(str), "walk-off")
            if stats is not None:
                stats["flights_from_spring_blockers_dropped"] = int(bl.sum())
            reject = reject | bl
        keep = ~reject
        i, j, gap, dh, ra, rb, R, K, L, wall, hurdle, prof, face, gap_e, stand = (
            x[keep] for x in (i, j, gap, dh, ra, rb, R, K, L, wall, hurdle, prof, face, gap_e, stand))
        geo = {k: v[keep] for k, v in geo.items()}
        hz_own = [h_ for h_, k_ in zip(hz_own, keep.tolist()) if k_]
        if stats is not None:
            stats["flights_swept"] = int(n)
            stats["flights_clear"] = int((~wall).sum())
            stats["flights_rejected_through_a_solid"] = int(reject.sum())
            stats["flights_walk_off"] = int((prof == "walk-off").sum())
            stats["flights_ends_in_two_air_components"] = getattr(w, "air_split", None)
        clear = ~wall & np.array([not x for x in hz_own], dtype=bool)
    else:
        clear = np.ones(n, dtype=bool)
    okey = over.test(w.x[i], w.y[i], w.z[i], w.x[j], w.y[j], w.z[j], hz_own) if over is not None else [()] * len(i)
    if stats is not None and over is not None:
        stats["flights_over_a_shut_barrier"] = int(sum(1 for x in okey if x))
    def cert(q, ti):
        """The certificate of flight q's flight at tier ti (physics.Certificate)."""
        walk = geo["P"][q, ti] == -2
        g = geo["WO"][q, ti] if walk else (gap_e[q] if geo["V"][q, ti] == 0 else gap[q])
        hr = geo["HR"][q, ti]
        cap = FLAP_CAP[KITS[int(K[q, ti])][0]] if K[q, ti] >= 0 else None
        d_ = float(geo["DH"][q, ti])
        roofed = np.isfinite(hr) and not walk
        rs, re_ = (float(geo[k][q, ti]) for k in ("RS", "RE"))
        return physics.Certificate(int(R[q, ti]), float(g), d_, not bool(stand[q]), float(geo["s0"][q]),
                                   float(hr) if roofed else None, bool(walk), bool(L[q, ti]),
                                   None if walk else cap, round(float(dh[q]) - d_, 3),
                                   round(float(geo["SL"][q]), 2) if walk else 0.0,
                                   rs if roofed and math.isfinite(rs) else None,
                                   re_ if roofed and math.isfinite(re_) else None)

    edges = {}
    key = ra.astype(np.int64) * w.nreg + rb
    o = np.lexsort((gap, R[:, 0], R[:, -1], ~clear, key))
    for q in o:
        k = (int(ra[q]), int(rb[q])) + ((("over",) + okey[q],) if okey[q] else ())
        e = edges.get(k)
        if e is None:
            e = edges[k] = {"ranks": [4] * len(tiers), "certs": [None] * len(tiers), "clear": False, "w": None,
                            "lip": False, "kit": None, "fall": 0}
            if okey[q]:
                e["over"] = list(okey[q])
        if clear[q] or not e["clear"]:
            if clear[q] and not e["clear"]:
                e["ranks"] = [4] * len(tiers)
                e["certs"] = [None] * len(tiers)
                e["clear"] = True
                e["w"] = None
            better = False
            for ti in range(len(tiers)):
                if R[q, ti] < e["ranks"][ti]:
                    e["ranks"][ti] = int(R[q, ti])
                    e["certs"][ti] = cert(q, ti)
                    better = True
            if e["w"] is None or better:
                ti0 = next((ti for ti in range(int(zone), len(tiers)) if R[q, ti] < 4), len(tiers) - 1)
                e["w"] = (int(i[q]), int(j[q]))
                e["wall"] = bool(wall[q])
                e["haz"] = list(hz_own[q])
                e["dh"], e["gap"] = float(dh[q]), float(gap[q])
                e["gap_edge"] = float(gap_e[q])
                high = np.isfinite(hurdle[q]) and hurdle[q] > max(dh[q], 0.0) + p["climb"]
                e["hurdle"] = float(hurdle[q]) if high else None
                if sweep and wall[q]:
                    e["kit"] = next((KITS[ki][0] for ki in range(len(KITS)) if KITS[ki][1] == R[q, ti0]), None)
                else:
                    e["kit"] = KITS[int(K[q, ti0])][0] if K[q, ti0] >= 0 else None
                e["lip"] = bool(L[q, ti0])
                e["profile"] = str(prof[q])
                if e["lip"] and np.isfinite(face[q]):
                    e["face_m"] = float(face[q])
                e["fall"] = int(envelope.fall_damage(-dh[q])) if dh[q] < 0 else 0
    for k, e in edges.items():
        if zone:
            e["zone_rank"] = e["ranks"][0]
            e["ranks"], e["certs"] = e["ranks"][1:], e["certs"][1:]
        dh_, gap_ = e["dh"], e["gap"]
        if e["kit"] in FLAP_KITS:
            e["kind"] = "flap"
        elif dh_ < -p["climb"] and gap_ <= 1.5:
            e["kind"] = "drop"
        elif dh_ > p["climb"] and gap_ <= 1.5:
            e["kind"] = "step"
        else:
            e["kind"] = "jump"
        if not e["clear"] and not e.get("wall") and e.get("haz") and down and any(o in down for o in e["haz"]):
            e["conf"] = "probe-needed"
            e["down"] = sorted(o for o in e["haz"] if o in down)
            e["why"] = "the flight passes through a downdraft (pushZ < 0; the flight model has no push)"
        elif not e["clear"] and not e.get("wall") and e.get("haz"):
            e["conf"] = "probe-needed"
            e["why"] = "the flight passes through a damage volume (resolved to a gate edge when it is a gate's)"
        elif not e["clear"]:
            e["conf"] = "probe-needed"
            e["why"] = ("every modelled flight on the straight ground track passes a solid (a wall, a hurdle, a "
                        "ceiling or a roof): a curved path may pass")
        elif w.reg_slip[k[0]] or w.reg_slip[k[1]]:
            # near-flat slippery floors (nz >= floors.SLIP_FLAT_NZ) carry town's walkways: walked as plain floor,
            # a takeoff from one a standing jump (AZ-366), flagged `slip` (a steeper one is no logic floor, AZ-359)
            e["conf"] = "modelled"
            e["slip"] = True
            e["why"] = ("takeoff or landing on a near-flat slippery floor (0x8051): a takeoff from it is a standing "
                        "jump (AZ-366), a landing treated as plain")
        elif e["lip"] and dh_ > LIP_MEASURED + 0.01:
            e["conf"] = "probe-needed"
            e["why"] = "needs the lip lift above the one measured ledge (1.2578 m)"
        elif e["kind"] in ("drop", "step") and not e["lip"] and e.get("hurdle") is None \
                and (e["kind"] == "step" or e.get("profile", "").startswith("walk-off")
                     or e.get("profile") == "envelope"):
            e["conf"] = "geometry"
        else:
            e["conf"] = "modelled"
        if e.get("hurdle") is not None and e["conf"] != "probe-needed":
            e["why"] = f"over a hurdle {e['hurdle']:.1f} m above the takeoff"
    return edges
