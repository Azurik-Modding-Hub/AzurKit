"""The native movement and collision kernel (Step R2.17's prototype; the reach engine's launch backend since Step
R2.19d, :mod:`.backend`): the player's ground and air ticks and the game's move code, ported from the USA
``default.xbe`` to C (``kernel.c``, whose header lists what is ported and what isn't), run against a level's real
collision triangles at native speed; FastL3 (``devkit.reach.l3_fast``) stays the proof (D845).

``build()`` compiles ``controllers.c`` (Step R2.19p: the launch controllers, built with ``kernel.c`` as one unit,
which it includes) once per source and flags with the pinned ziglang wheel's ``zig cc`` (:data:`FLAGS`: the host's CPU)
into the AzurKit user cache and loads it with ctypes; :class:`World` is a level's solid triangles (``geometry.Level``'s
present gameSolid faces at their load pose, less the platforms a census finds absent) with a 2 m grid, each face's springboard height beside (:func:`springs`), and since Step R2.19h1 its movers
(:meth:`World.movers`: a rig's triangles in its frame and its pose table from the game's whole steps, posed at the
world's clock, a body on one carried); :class:`Fields` its push and water volumes (:func:`fields`: the swim, the air's
pushes, or a stop where a volume moves or switches); :class:`Player` one body's state, stepped by :meth:`World.run`
over a pad string (``l3.Pad`` s).  Dev
tooling (``devkit/reach/reach_engine.py --backend kernel``, ``devkit/reach/native_check.py``): never a CLI verb.  Positions
stay in memory.
"""

from __future__ import annotations

import ctypes
import functools
import hashlib
import importlib.util
import math
import os
import subprocess
from pathlib import Path

import numpy as np

SRC = Path(__file__).with_name("controllers.c")   # includes kernel.c: one unit
SOURCES = (Path(__file__).with_name("kernel.c"), SRC)
CELL = 2.0
RH, RV = 0.5, 1.0
Y, LT, BLACK = 1, 2, 4
STOP = {0: "", 1: "state", 2: "water", 3: "push", 4: "stepup", 5: "lip", 6: "catch", 7: "climb", 8: "roll"}
TRIES = {16: "ice"}        # a note that counts as a flag (8, the classifier's dead stop, is ported: no flag)
FLAGS = ("-O3", "-march=native", "-shared", "-fPIC")   # zig cc's flags (part of a kernel record's key; the
                                                       # controllers' own contraction is off by a pragma, R2.19p)


class Contact(ctypes.Structure):
    _fields_ = [("t", ctypes.c_double), ("d", ctypes.c_double), ("n", ctypes.c_double * 3),
                ("p", ctypes.c_double * 3), ("tri", ctypes.c_int), ("kind", ctypes.c_int), ("word", ctypes.c_uint32),
                ("src", ctypes.c_int),     # -1 the static world, else the mover (``tri`` its own index)
                ("s", ctypes.c_double)]


class Move(ctypes.Structure):
    _fields_ = [("pos", ctypes.c_double * 3), ("vel", ctypes.c_double * 3), ("w", ctypes.c_double * 3),
                ("dt", ctypes.c_double), ("f35", ctypes.c_int), ("out", ctypes.c_double * 3),
                ("vout", ctypes.c_double * 3), ("contact", ctypes.c_int), ("contacts", ctypes.c_int),
                ("fallback", ctypes.c_int), ("first", Contact), ("A", Contact), ("B", Contact), ("Cc", Contact),
                ("rh", ctypes.c_double), ("rv", ctypes.c_double)]


class Player(ctypes.Structure):
    _fields_ = [("pos", ctypes.c_double * 3), ("vel", ctypes.c_double * 3), ("normal", ctypes.c_double * 3),
                ("peak_z", ctypes.c_double), ("gauge", ctypes.c_double), ("ac", ctypes.c_double),
                ("h", ctypes.c_double), ("fall_ref", ctypes.c_double), ("state", ctypes.c_int),
                ("flaps_used", ctypes.c_int), ("flaps_max", ctypes.c_int), ("shield", ctypes.c_int),
                ("latch_y", ctypes.c_int), ("prev_y", ctypes.c_int), ("attached", ctypes.c_int),
                ("f35", ctypes.c_int), ("word", ctypes.c_uint32), ("stop", ctypes.c_int), ("tries", ctypes.c_int),
                ("contacts", ctypes.c_int), ("clip", ctypes.c_int), ("d4", ctypes.c_double),
                ("state_t", ctypes.c_double), ("on", ctypes.c_int), ("tick", ctypes.c_int64),
                ("spring", ctypes.c_double), ("fields", ctypes.c_uint32), ("push", ctypes.c_double * 3),
                ("depth", ctypes.c_double)]
    # ``on`` the mover the body last stood on (-1 none), ``tick`` the movers' clock (``World.run`` steps it)


class Pad(ctypes.Structure):
    _fields_ = [("sx", ctypes.c_float), ("sy", ctypes.c_float), ("cx", ctypes.c_float), ("cy", ctypes.c_float),
                ("buttons", ctypes.c_int32)]


class Consts(ctypes.Structure):
    """The controllers' named constants (``controllers.c``), filled from their Python modules
    (``backend._consts``)."""
    _fields_ = ([(k, ctypes.c_int) for k in ("ticks", "air_cap", "run_cap", "stuck", "still", "settle", "swim_hold",
                                             "jump_hold", "chain0", "chain1", "roll_y", "roll_tap", "roll_period",
                                             "roll_ticks", "cast_wait", "turn", "home_ticks", "brake_ticks", "tries")]
                + [("airborne", ctypes.c_int * 2), ("dead", ctypes.c_int * 2), ("settled", ctypes.c_int * 2),
                   ("swimming", ctypes.c_int), ("slide", ctypes.c_int)]
                + [(k, ctypes.c_double) for k in ("flap_margin", "h_air", "descent_d", "gravity", "fps", "flap_mult",
                                                  "short_m", "home_m", "brake_v", "cam_rate", "snap_deg", "dead_raw",
                                                  "raw_scale", "gate_raw", "flat_nz", "rest_mps", "dt", "gdt",
                                                  "blend")])


class Mac(ctypes.Structure):
    """A ``macros.Macro`` (``kind`` 0 walkoff, 1 runjump, 2 standjump, 3 rolljump; ``ac`` its kit's air control)."""
    _fields_ = [("kind", ctypes.c_int), ("flaps", ctypes.c_int), ("rolls", ctypes.c_int), ("recast", ctypes.c_int),
                ("hold", ctypes.c_int), ("curve", ctypes.c_double), ("lead", ctypes.c_double), ("ac", ctypes.c_double)]


class Fam(ctypes.Structure):
    """A launch family's controller (``ctl`` 0 ``macros._Run``, 1 ``aim.Aim``, 2 ``aim.Sched``) and its fields."""
    _fields_ = [("ctl", ctypes.c_int), ("n", ctypes.c_int), ("hp", ctypes.c_int), ("has_target", ctypes.c_int),
                ("has_home", ctypes.c_int), ("nsched", ctypes.c_int), ("heading", ctypes.c_double),
                ("cam", ctypes.c_double), ("back", ctypes.c_double), ("start", ctypes.c_double * 3),
                ("target", ctypes.c_double * 3), ("home", ctypes.c_double * 3),
                ("sched", ctypes.POINTER(ctypes.c_double))]


class LOut(ctypes.Structure):
    """A C launch's answer: its end (0 ticks, 1 settled, 2 unsettled, 3 walked off, 4 dead, 5 air cap, 6 stuck,
    7 stayed, 8 the kernel's flag with its ``code``), rows, the rows an outcome reads (-1 none) and its segments."""
    _fields_ = ([(k, ctypes.c_int) for k in ("end", "code", "n", "first", "first_state", "air", "took", "took_state",
                                             "last_state", "flaps", "seg0", "nseg")]
                + [(k, ctypes.c_double * 3) for k in ("last", "firstp", "tookp")])


class Seg(ctypes.Structure):
    """A run of equal pads: ``n`` ticks of the stick, the buttons (1 y, 2 lt, 4 black) and the camera's f32 pair."""
    _fields_ = [("n", ctypes.c_int), ("buttons", ctypes.c_int), ("sx", ctypes.c_double), ("sy", ctypes.c_double),
                ("cx", ctypes.c_double), ("cy", ctypes.c_double)]


def _cache() -> Path:
    from platformdirs import user_cache_dir
    p = Path(user_cache_dir("AzurKit")) / "reach-native"
    p.mkdir(mode=0o700, parents=True, exist_ok=True)
    return p


def zig_version() -> str:
    """The pinned ziglang wheel's version (part of a kernel record's key)."""
    from importlib.metadata import version
    return version("ziglang")


@functools.cache
def build() -> ctypes.CDLL:
    """The kernel and its controllers, compiled once per source and :data:`FLAGS` (``-O3``, the host CPU) and
    loaded; a process that compiled it beside another loads the one installed first."""
    h = hashlib.sha256(" ".join(FLAGS).encode())
    for f in SOURCES:
        h.update(f.read_bytes())
    sha = h.hexdigest()[:12]
    out = _cache() / f"kernel-{sha}.so"
    if not out.exists():
        spec = importlib.util.find_spec("ziglang")
        if spec is None:
            raise RuntimeError("zig is missing: `uv sync` installs the ziglang wheel")
        tmp = out.with_suffix(f".{os.getpid()}.part")
        env = {"ZIG_GLOBAL_CACHE_DIR": str(_cache() / "zig-cache"), "ZIG_LOCAL_CACHE_DIR": str(_cache() / "zig-cache")}
        done = subprocess.run([str(Path(spec.origin).with_name("zig")), "cc", *FLAGS, "-o", str(tmp), str(SRC)],
                              env=os.environ | env, capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError(f"zig cc failed on {SRC.name}:\n{done.stderr.strip()}")
        try:
            os.replace(tmp, out)
        except PermissionError:      # Windows: another process built it at once and has loaded it (same name:
            if not out.exists():     # same source and flags), which Windows won't replace
                raise
            tmp.unlink()
    lib = ctypes.CDLL(str(out))
    lib.w_new.restype = ctypes.c_void_p
    lib.w_new.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double, ctypes.c_double]
    lib.w_free.argtypes = [ctypes.c_void_p]
    lib.w_tests.restype = ctypes.c_int64
    lib.w_tests.argtypes = [ctypes.c_void_p]
    lib.w_sweep.restype = ctypes.c_int
    lib.w_sweep.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_double * 3), ctypes.POINTER(ctypes.c_double * 3),
                            ctypes.c_double, ctypes.c_double, ctypes.POINTER(Contact)]
    lib.w_move.argtypes = [ctypes.c_void_p, ctypes.POINTER(Move)]
    lib.p_step.restype = ctypes.c_int
    lib.p_step.argtypes = [ctypes.c_void_p, ctypes.POINTER(Player), ctypes.POINTER(Pad)]
    lib.p_run.restype = ctypes.c_int
    lib.p_run.argtypes = [ctypes.c_void_p, ctypes.POINTER(Player), ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
    lib.w_movers.argtypes = [ctypes.c_void_p, ctypes.c_int] + [ctypes.c_void_p] * 6
    lib.w_present.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.w_clock.argtypes = [ctypes.c_void_p, ctypes.c_int64]
    lib.w_spring.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    lib.w_mspring.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    lib.f_new.restype = ctypes.c_void_p
    lib.f_free.argtypes = [ctypes.c_void_p]
    lib.f_add.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
    lib.w_fields.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    lib.f_probe.restype = ctypes.c_int
    lib.f_probe.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_double * 3), ctypes.POINTER(ctypes.c_double * 5)]
    lib.p_launches.restype = ctypes.c_int
    lib.p_launches.argtypes = [ctypes.c_void_p, ctypes.POINTER(Player), ctypes.POINTER(Consts), ctypes.POINTER(Fam),
                               ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64)]
    lib.c_hypot.restype = ctypes.c_double
    lib.c_hypot.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_double * 3)]
    return lib


def _kept(level, absent) -> np.ndarray:
    from azurkit.tools.randomizer.draft.geometry import SOLID_CATS
    from azurkit.tools.randomizer.art import collision
    present = np.array([o["present"] and o["oi"] not in set(absent) for o in level.owners])[level.tri_owner]
    keep = ((level.tri_word & collision.W_SOLID) != 0) & np.isin(level.tri_cat, SOLID_CATS) & present
    return keep & (np.linalg.norm(np.cross(level.P[:, 1] - level.P[:, 0], level.P[:, 2] - level.P[:, 0]), axis=1)
                   > 1e-12)


def solid(level, absent=()) -> tuple[np.ndarray, np.ndarray]:
    """``level``'s (``geometry.Level``) present gameSolid triangles in world space, (n, 3, 3), and their words, less
    the owners ``absent`` names (``devkit/reach/native_census.py``: platforms the game's world doesn't hold there)."""
    keep = _kept(level, absent)
    return np.ascontiguousarray(level.P[keep], dtype=np.float64), np.ascontiguousarray(level.tri_word[keep],
                                                                                       dtype=np.int32)


def spring_of(owner: dict) -> float:
    """An owner's springboard height: an autoSpring (word 0x04) platform's ``springboard`` attribute, which jump_init
    takes as h (0x890C6; 0: the kit's jump), else 0."""
    from azurkit.tools.randomizer.art import collision
    return float((owner.get("attrs") or {}).get("springboard", 0.0)) if (owner["word"] or 0) & collision.W_AUTOSPRING \
        else 0.0


def springs(level, absent=()) -> np.ndarray:
    """Each of :func:`solid`'s faces' springboard height (:func:`spring_of` its owner)."""
    S = np.array([spring_of(o) for o in level.owners])
    return np.ascontiguousarray(S[level.tri_owner[_kept(level, absent)]], dtype=np.float64)


STOP_WATER, STOP_PUSH = 2, 3


def fields(level) -> list[dict]:
    """``level``'s push and water volumes as the volume query 0x60BD0 meets them (``kernel.c``'s header): each field
    owner's (word 0x20) faces in world space, its word and world push (a pushEnable volume's pushX/Y/Z through its
    world matrix, 0x79EFE) and ``stop``: 0, or the stop it raises where its pose or word can change from the load's
    (it moves, is approximately placed, or a link drives a plug of it: STOP_WATER or STOP_PUSH, as its word says;
    R2.19h1 records them); one not present at load is left out unless a link drives it."""
    from azurkit.tools.randomizer.draft.geometry import CAT_PUSH, CAT_WATER
    from azurkit.tools.randomizer.art import collision, nodes
    out = []
    for oi, o in enumerate(level.owners):
        word = o["word"] or 0
        if o["cat"] not in (CAT_PUSH, CAT_WATER) or not len(t := level.tris_of(oi)):
            continue
        changes = bool(o["moved"] or o["approx"] or o["driven"])
        if not o["present"] and not changes:
            continue
        if not word & collision.W_FIELD and not changes:
            continue
        a = o.get("attrs") or {}
        local = tuple(float(a.get(k, 0.0)) for k in ("pushX", "pushY", "pushZ"))
        if word & collision.W_PUSH:
            m = o["world"]
            p0 = np.array(nodes.apply(m, (0.0, 0.0, 0.0)))
            push = tuple(float(x) for x in np.array(nodes.apply(m, local)) - p0)
        else:
            push = local
        stop = (STOP_WATER if word & collision.W_WATER or o["cat"] == CAT_WATER else STOP_PUSH) if changes else 0
        out.append({"oi": oi, "P": np.asarray(level.P[t], np.float64), "word": word, "push": push, "stop": stop})
    return out


class Fields:
    """:func:`fields`' volumes in the kernel: each a :class:`World` of its faces as given then reversed (a ray up meets
    the copy facing down; ``zs`` 1: the query's rays), with its box, word, push and stop."""

    def __init__(self, vols) -> None:
        self.lib = build()
        self.ptr = self.lib.f_new()
        self.meshes = []
        for v in vols:
            P = np.asarray(v["P"], np.float64).reshape(-1, 3, 3)
            mesh = World(np.concatenate([P, P[:, ::-1]]), np.full(2 * len(P), v["word"], np.int32), 1.0)
            lo, hi = (np.ascontiguousarray(f(P.reshape(-1, 3), axis=0), np.float64) for f in (np.min, np.max))
            push = np.ascontiguousarray(v["push"], np.float64)
            self.lib.f_add(self.ptr, mesh.ptr, len(P), lo.ctypes.data, hi.ctypes.data, int(v["word"]) & 0xFFFFFFFF,
                           push.ctypes.data, int(v["stop"]))
            self.meshes.append(mesh)
        self.n = len(vols)

    def __del__(self) -> None:
        if getattr(self, "ptr", None):
            self.lib.f_free(self.ptr)
            self.ptr = None

    def at(self, q) -> tuple[int, int, tuple[float, float, float], float]:
        """The query at ``q``: its stop, the words, the push and the depth (-50: under no surface)."""
        out = (ctypes.c_double * 5)()
        stop = self.lib.f_probe(self.ptr, ctypes.byref((ctypes.c_double * 3)(*q)), ctypes.byref(out))
        return stop, int(out[0]), (out[1], out[2], out[3]), out[4]


class World:
    """A level's solid triangles in the kernel (``P`` (n, 3, 3) world space, ``words`` their collision words)."""

    def __init__(self, P: np.ndarray, words: np.ndarray, zs: float = RH / RV, spring=None) -> None:
        """``zs`` the sweep space's z scale (its body's rh / rv: the player's by default); ``spring`` each face's
        springboard height (:func:`springs`)."""
        self.lib = build()
        self._P, self._w = np.ascontiguousarray(P, np.float64), np.ascontiguousarray(words, np.int32)
        self.ptr = self.lib.w_new(len(P), self._P.ctypes.data, self._w.ctypes.data, CELL, zs)
        self.n = len(P)
        if spring is not None:
            self._s = np.ascontiguousarray(spring, np.float64)
            self.lib.w_spring(self.ptr, self._s.ctypes.data)

    def __del__(self) -> None:
        if getattr(self, "ptr", None):
            self.lib.w_free(self.ptr)
            self.ptr = None

    @property
    def tests(self) -> int:
        return self.lib.w_tests(self.ptr)

    def sweep(self, c0, c1, rh: float = RH, rv: float = RV) -> Contact | None:
        out = Contact()
        a, b = (ctypes.c_double * 3)(*c0), (ctypes.c_double * 3)(*c1)
        return out if self.lib.w_sweep(self.ptr, ctypes.byref(a), ctypes.byref(b), rh, rv, ctypes.byref(out)) else None

    def move(self, pos, vel, w, dt: float, f35: int = 0) -> Move:
        m = Move()
        m.pos[:], m.vel[:], m.w[:], m.dt, m.f35 = pos, vel, w, dt, f35
        self.lib.w_move(self.ptr, ctypes.byref(m))
        return m

    def movers(self, tris, words, poses, cycles, springs=None) -> None:
        """The world's movers (Step R2.19h1), replacing any: mover m's triangles ``tris[m]`` ((n, 3, 3), its own
        frame) and their collision ``words[m]``, its pose table ``poses[m]`` ((T, 4, 4) row vectors: world = local
        @ M[:3, :3] + M[3, :3], a row a tick of the game's whole steps), whether it cycles (``cycles[m]``: the
        row wraps; else it holds its last) and its springboard height (``springs[m]``, :func:`spring_of`; none:
        0).  All present, the clock at 0."""
        tris = [np.asarray(t, np.float64).reshape(-1, 3, 3) for t in tris]
        start = np.concatenate([[0], np.cumsum([len(t) for t in tris])]).astype(np.int64)
        self._m = (start, np.ascontiguousarray(np.concatenate(tris) if tris else np.zeros((0, 3, 3)), np.float64),
                   np.ascontiguousarray(np.concatenate([np.asarray(w, np.int32).reshape(-1) for w in words])
                                        if words else np.zeros(0), np.int32),
                   np.asarray([len(q) for q in poses], np.int64), np.asarray(cycles, np.int32),
                   np.ascontiguousarray(np.concatenate([np.asarray(q, np.float64).reshape(-1, 16) for q in poses])
                                        if poses else np.zeros((0, 16)), np.float64))
        self.nm = len(tris)
        self.lib.w_movers(self.ptr, self.nm, *(a.ctypes.data for a in self._m))
        if springs is not None and self.nm:
            self._ms = np.ascontiguousarray(springs, np.float64)
            self.lib.w_mspring(self.ptr, self._ms.ctypes.data)

    def present(self, m: int, on: bool) -> None:
        """Mover ``m`` in the world or not (the present mask)."""
        self.lib.w_present(self.ptr, m, int(on))

    def clock(self, tick: int) -> None:
        """The pose row the movers stand at for :meth:`sweep` (a run sets it each tick from its player's clock)."""
        self.lib.w_clock(self.ptr, tick)

    def fields(self, f: Fields | None) -> None:
        """The volumes each tick's query meets on this world (kept alive with it)."""
        self._fields = f
        self.lib.w_fields(self.ptr, f.ptr if f is not None else None)

    def run(self, p: Player, pads) -> np.ndarray:
        """Step ``p`` over ``pads`` (``Pad`` s, or ``l3.Pad`` s): per tick run, pos (3), vel (3), state, flaps used,
        the move's contacts and its code (stop + 16 x tries); it stops early at a stop."""
        arr = (Pad * len(pads))(*[pad if isinstance(pad, Pad) else to_pad(pad) for pad in pads])
        out = np.zeros((len(pads), 10), np.float64)
        n = self.lib.p_run(self.ptr, ctypes.byref(p), len(pads), ctypes.addressof(arr), out.ctypes.data)
        return out[:n]


def to_pad(pad) -> Pad:
    """An ``l3.Pad`` (its camera as the exact f32 pair ``cam``, or a yaw) as the kernel's."""
    if pad.cam is not None:
        cx, cy = pad.cam
    else:
        cx, cy = -math.sin(pad.yaw or 0.0), math.cos(pad.yaw or 0.0)
    b = (Y if "y" in pad.buttons else 0) | (LT if "lt" in pad.buttons else 0) | (BLACK if "black" in pad.buttons else 0)
    return Pad(pad.stick[0], pad.stick[1], cx, cy, b)


def player(pos, vel, state: int, normal, *, flaps_max: int = 0, flaps_used: int = 0, peak_z: float = -3.4e38,
           gauge: float = 1.0, tick: int = 0) -> Player:
    """A body at ``pos`` (its centre) with the kit's Flaps (0: no air shield), the movers' clock at ``tick``."""
    p = Player()
    p.pos[:], p.vel[:], p.normal[:] = pos, vel, normal
    p.state, p.flaps_max, p.flaps_used, p.shield = state, flaps_max, flaps_used, int(flaps_max > 0)
    p.peak_z, p.gauge, p.attached = peak_z, gauge, int(state in (0, 3))
    p.ac, p.h = 9.0, 1.1          # the entity's until a jump or flap reinits them (a walk-off keeps 9: physics.py)
    p.on, p.tick = -1, tick
    return p
