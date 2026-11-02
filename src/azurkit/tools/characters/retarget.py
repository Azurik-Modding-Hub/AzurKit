"""garret4's clips baked onto another humanoid body's rig (Steps 2.87,
2.88; D226, the owner: "also try and make humanoids work").

A clip writes local rotations in its own body's joint frames and binds
to a body by raw bone index (``docs/RE_DATA.md`` § "How a clip binds to
a body"), so garret4's clips play on another rig only when rewritten for
it.  This module rewrites them at build time, exactly:

- **The engine model** (:func:`pose`; 0xCB730, 0xCA470,
  ``docs/RE_XBE.md``): a pose starts each bone from its record's rest
  translation, rotation and scale, lets the clip's tracks (cubic Hermite,
  0xD8300: :func:`evaluate`) replace components, normalises the rotation
  and builds the local rotation JO x q x RA (Hamilton), world = parent
  world x local.
- **The role map** (:func:`role_map`): each of garret4's core, finger and
  loincloth bones finds the target's bone of its name family
  (:data:`FAMILIES`: Balthazar's forearm is ``right_arm``, his hand
  ``right_w``), on garret4's side of the bind pose by the bone's x sign
  (his arm names are mirrored), below the target of garret4's nearest
  mapped ancestor, nearest first; :data:`MAPS` lists the bodies the bake
  serves and their overrides (a rig named its own way: keylord's, the
  elementals', the golem's).  A body without two legs, two arms, a spine
  and a head (unless its overrides leave the head unmapped: the golem's)
  is refused; a body with no clips (gargoylestone, tesla_tree) maps no
  bone, so garret4's clips baked onto it are timers: his length and
  markers (Step 2.89), and its root bones ride his ``m_feet`` over the
  drawn scale D (Step 2.127, AZ-562): the game places the model at the
  entity less the clip's ``m_feet`` unscaled and draws the bones x D, so
  a bone held at its bind was drawn that far off its entity wherever his
  ``m_feet`` leaves his origin (a frag 1.95 m under the floor at a
  ladder's top), and riding ``m_feet`` x 1 drew it (D - 1) x ``m_feet``
  too far the other way (Step 2.118c's dropped fix); each root's
  translation is its rest plus his ``m_feet`` keys / D, so the drawn
  body is at its entity in every clip and crossfade.
- **The re-pose** (:class:`Retarget`): each mapped bone's bind turns, in
  the world, so its segment points along garret4's (a bone with no mapped
  segment child turns with its mapped parent).
- **The bake** (:func:`bake_clip`): with k mapped from garret4's g and its
  nearest mapped ancestor from gp, q_k(t) = A x [JO q(t) RA over
  garret4's path gp..g] x C, A and C constant (the binds, JO, RA and the
  re-pose), so a mapped bone's world rotation moves from its re-posed
  bind exactly as garret4's moves from his.  Where the path holds one
  bone it is a constant 4x4 matrix on garret4's keys, split at the union
  of the four components' key times (a Hermite curve is linear in its
  values and tangents, and the engine normalises the result): exact.
  Where it folds an animated bone the target lacks (garret4's
  ``*_shoulder_2`` under Balthazar's one clavicle) it is sampled at
  :data:`SAMPLE_HZ` plus garret4's key times.  The model sits at the
  entity minus the clip's ``m_feet`` (0x42E40), which stays garret4's,
  so the root's translation plays his horizontal motion unscaled and his
  height over ``m_feet`` times the hip-height ratio (its thighs' bind
  height over his, its leg length: a child's 0.67): the body's feet ride
  ``m_feet`` as his do (a hoist ends with them on the ledge).  The
  bones and markers are drawn x D (the build's drawn scale) while that
  ``m_feet`` is subtracted unscaled, so where it moves the drawn body
  leads its entity by (D - 1) x ``m_feet``; the roll (Step 2.133,
  AZ-608), whose ``m_feet`` runs 4.07 m forward, is baked drawn about
  the entity instead (:func:`centred`).  A clip :data:`FLOORED` names
  for its body has its root raised through the clip wherever a bone
  is under the floor (:func:`floored`: the golem's roll, whose tuck put
  its long arms 2.2 units under it, AZ-629).
  Other translation and scale tracks are dropped.  Marker tracks keep
  garret4's keys, remapped by name to the body's markers,
  :data:`ADDED_MARKERS` added to it.  A prop on a root of its own (no
  mapped bone above it: the townswomen's ``vase_joint``, which
  town_female_4's clips carry on her head at x0.4 and the others' at
  x0, the water elemental's blob chain, x0 but mid-throw) would hold its
  bind at full size (the vase's the model's origin, round her hips; the
  blob's the T-pose left hand), so every baked clip scales it to zero
  (Step 2.88b); the blob rides the left hand, but at x0 outside its
  throws hidden looks as following the hand would.
- **Victories only** (Step 2.121, D299): a body whose other clips are
  its own (``--player-character-anims own``) takes
  garret4's six victories baked with no marker grown (``grow=False``:
  its markers stay its own, so X9 keeps its ladder and hoist), its root
  lifted by :attr:`Retarget.lift` so it cuts in from its own idle at
  that idle's height (the elementals hover 0.3 m in theirs).
- **Storage** (:func:`bake_body`): the baked clips go into
  ``characters.xbr`` as ``characters/<body>/g4/<clip>`` and their keys
  into ``index.xbr`` (:mod:`azurik_mod.xbr.append`); the body's marker
  table grows in place.  A species load finds ``g4/<clip>`` as
  ``characters/<body>/g4/<clip>`` (0x4B600's ``characters/%s/%s``).
"""

from __future__ import annotations

import math
import struct
import weakref
from array import array
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

from azurkit.core import fdlibm, native
from azurkit.tools.characters.characters import (
    DAMAGE_MARKERS,
    BoneRecord,
    body_at,
    bone_records,
    marker_records,
    read_body,
)
from azurkit.tools.characters.index_xbr import IndexRecord, add_index_records
from azurkit.core.xbr.append import NewResource, append_resources
from azurkit.core.xbr.nodes import named_resources, parse_toc

PLAYER = "garret4"
BAKED_DIR = "g4/"
"""A baked clip's name under its body: ``characters/<body>/g4/<clip>``."""
SAMPLE_HZ = 60.0
"""How often a bone that folds an animated garret4 bone is sampled."""
ADDED_MARKERS = ("m_feet", "m_grab", "m_attacklevel")
"""The markers the player's code and fx read that a baked body gains (with
garret4's defaults) when it lacks them: root motion, ledge alignment and
the swing's trail (the 28 ``fx_staff_*`` graphs bind ``m_attacklevel``).
The staff-hits-wall sweep that marker gates never runs on a baked body,
which has no staff bone: X17 turns it off wherever a clip raises the
marker (AZ-441)."""
FLT_MAX = 3.4028234663852886e38

Quat = tuple[float, float, float, float]          # (x, y, z, w)
Key = tuple[float, float, float, float]           # time, value, in, out (per second)
_I: Quat = (0.0, 0.0, 0.0, 1.0)


# --- quaternions (Hamilton) -------------------------------------------------
def qmul(p: Quat, q: Quat) -> Quat:
    x1, y1, z1, w1 = p
    x2, y2, z2, w2 = q
    return (w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2)


def qinv(q: Quat) -> Quat:
    return (-q[0], -q[1], -q[2], q[3])


def qnorm(q) -> Quat:
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


def qangle(p: Quat, q: Quat) -> float:
    """Degrees between two rotations."""
    return math.degrees(2 * fdlibm.acos(min(1.0, abs(sum(a * b for a, b in zip(qnorm(p), qnorm(q)))))))


def _aim(a, b) -> Quat:
    """The smallest rotation taking direction ``a`` to ``b``."""
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    if na < 1e-6 or nb < 1e-6:
        return _I
    c = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    w = na * nb + sum(x * y for x, y in zip(a, b))
    if w < 1e-9 * na * nb:      # opposite: a half turn about any axis normal to a
        p = (1.0, 0.0, 0.0) if abs(a[0]) < 0.9 * na else (0.0, 1.0, 0.0)
        c = (a[1] * p[2] - a[2] * p[1], a[2] * p[0] - a[0] * p[2], a[0] * p[1] - a[1] * p[0])
        w = 0.0
    return qnorm((*c, w))


def _linear(a: Quat, c: Quat) -> list[list[float]]:
    """The 4x4 matrix M with a x q x c = M q (q as x, y, z, w)."""
    cols = [qmul(qmul(a, e), c) for e in ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))]
    return [[cols[j][i] for j in range(4)] for i in range(4)]


# --- clips (banm) -------------------------------------------------------------
@dataclass(frozen=True)
class Track:
    """One curve of a clip: its target bone or marker's index, the
    component (bones: 0-2 T, 3-6 q, 7-9 S; markers ``docs/RE_DATA.md``),
    its keys (time, value, in- and out-tangent per second; an out-tangent
    past FLT_MAX holds the value) and its pre/post modes."""

    target: int
    comp: int
    keys: tuple[Key, ...]
    modes: tuple[int, int] = (0, 0)


@dataclass(frozen=True)
class Clip:
    """A ``banm``: its length in seconds, bone tracks and marker tracks."""

    length: float
    bones: tuple[Track, ...]
    markers: tuple[Track, ...]


def read_clip(data, at: int) -> Clip:
    """The ``banm`` at ``at``: a 0x14-byte header (+0 bone-track count,
    +4 their self-relative pointer, +8 marker-track count, +0xC their
    pointer, +0x10 the length), 0x14-byte tracks (u16 pre and post mode,
    i32 key count, a self-relative pointer to the keys, i32 target, i32
    component) and 16-byte keys."""
    def i32(a: int) -> int:
        return struct.unpack_from("<i", data, a)[0]

    groups = []
    for count, ptr in ((0, 4), (8, 0xC)):
        base = at + ptr + i32(at + ptr)
        tracks = []
        for k in range(i32(at + count)):
            rec = base + 0x14 * k
            pre, post, n = struct.unpack_from("<HHi", data, rec)
            keys = rec + 8 + i32(rec + 8)
            target, comp = struct.unpack_from("<ii", data, rec + 0xC)
            tracks.append(Track(target, comp, tuple(struct.unpack_from("<4f", data, keys + 16 * j)
                                                    for j in range(n)), (pre, post)))
        groups.append(tuple(tracks))
    return Clip(struct.unpack_from("<f", data, at + 0x10)[0], *groups)


def write_clip(clip: Clip) -> bytes:
    """``clip`` as a ``banm`` (:func:`read_clip`'s layout: the tracks after
    the header, bone tracks first, then every track's keys in order)."""
    tracks = (*clip.bones, *clip.markers)
    head = struct.pack("<iiiif", len(clip.bones), 0x14 - 4, len(clip.markers),
                       0x14 + 0x14 * len(clip.bones) - 0xC, clip.length)
    recs, keys = bytearray(), bytearray()
    at = 0x14 + 0x14 * len(tracks)
    for k, tr in enumerate(tracks):
        rec = 0x14 + 0x14 * k
        recs += struct.pack("<HHiiii", *tr.modes, len(tr.keys), at + len(keys) - (rec + 8), tr.target, tr.comp)
        keys += b"".join(struct.pack("<4f", *key) for key in tr.keys)
    return head + bytes(recs) + bytes(keys)


def _segment(keys, t: float, left: bool) -> int:
    """The index of the key starting the segment holding ``t`` (from the
    left, the segment ending at a key time ``t``)."""
    lo, hi = 0, len(keys) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if keys[mid][0] < t or (not left and keys[mid][0] == t):
            lo = mid
        else:
            hi = mid
    return lo


def _cubic(keys, lo: int, t: float) -> tuple[float, float]:
    """The segment from key ``lo``'s value and slope (per second) at ``t``."""
    t0, v0, _, o0 = keys[lo]
    t1, v1, i1, _ = keys[lo + 1]
    dt = t1 - t0
    if o0 > FLT_MAX or dt <= 0:
        return v0, 0.0
    s = (t - t0) / dt
    m0 = dt * o0
    m1 = dt * i1 if math.isfinite(dt * i1) else 0.0
    a, b = 2 * (v0 - v1) + m1 + m0, 3 * (v1 - v0) - 2 * m0 - m1
    return ((a * s + b) * s + m0) * s + v0, (3 * a * s * s + 2 * b * s + m0) / dt


def evaluate(keys, t: float) -> float:
    """0xD8300 with modes 0: the first or last key's value outside the
    keys, else the cubic Hermite of the segment holding ``t``."""
    if t <= keys[0][0]:
        return keys[0][1]
    if t >= keys[-1][0]:
        return keys[-1][1]
    return _cubic(keys, _segment(keys, t, False), t)[0]


def _slopes(keys, t: float) -> tuple[float, float]:
    """The curve's slope just before and just after ``t``."""
    left = _cubic(keys, _segment(keys, t, True), t)[1] if keys[0][0] < t <= keys[-1][0] else 0.0
    right = _cubic(keys, _segment(keys, t, False), t)[1] if keys[0][0] <= t < keys[-1][0] else 0.0
    return left, right


def _stepped(keys) -> bool:
    return any(k[3] > FLT_MAX for k in keys[:-1])


# --- rigs ---------------------------------------------------------------------
@dataclass(frozen=True)
class Rig:
    """A body's bones (:class:`~azurik_mod.assets.characters.BoneRecord`),
    their bind-pose positions and bind world rotations (composed from the
    rest values, which reproduce the inverse binds), and its markers."""

    name: str
    bones: tuple[BoneRecord, ...]
    positions: tuple[tuple[float, float, float], ...]
    world: tuple[Quat, ...]
    markers: tuple[str, ...]

    @classmethod
    def read(cls, characters_xbr: bytes, body: str) -> Rig:
        bones, info = bone_records(characters_xbr, body), read_body(characters_xbr, body)
        world: list[Quat] = []
        for b in bones:
            local = qmul(qmul(b.jo, b.q), b.ra)
            world.append(local if b.parent < 0 else qmul(world[b.parent], local))
        return cls(body, bones, tuple(p for _, p in info.bones), tuple(world), info.markers)

    def ancestors(self, k: int) -> list[int]:
        out, p = [], self.bones[k].parent
        while p >= 0:
            out.append(p)
            p = self.bones[p].parent
        return out


def pose(rig: Rig, clip: Clip, t: float) -> list[Quat]:
    """The engine model (0xCB730, 0xCA470): each bone's world rotation
    when ``clip`` plays on ``rig`` at ``t`` (unkeyed components take the
    bone's rest rotation)."""
    got = _engine(rig, clip, (t,), False)
    if got is None:
        return _pose(rig, clip, t)
    w = got[0]
    return [tuple(w[j:j + 4]) for j in range(0, len(w), 4)]


def origins(rig: Rig, clip: Clip, t: float) -> list[tuple[float, float, float]]:
    """Each bone's origin in the model when ``clip`` plays on ``rig`` at
    ``t`` (the engine model, :func:`pose`; scale left out, every bone's
    rest scale being 1 on the bodies X3 follows): its parent's origin plus
    its translation (the clip's, else its rest one) turned by the
    parent's world rotation.  X3's box follows a hand's (Step 2.70b)."""
    return origins_at(rig, clip, (t,))[0]


def origins_at(rig: Rig, clip: Clip, times) -> list[list[tuple[float, float, float]]]:
    """:func:`origins` at each of ``times``, in one call of the compiled
    kernel (``core.native.origins``; its twin :func:`_origins` without it)."""
    got = _engine(rig, clip, times, True)
    if got is None:
        return [_origins(rig, clip, t) for t in times]
    o, n = got[1], 3 * len(rig.bones)
    return [[tuple(o[j:j + 3]) for j in range(i, i + n, 3)] for i in range(0, len(o), n)]


def _pose(rig: Rig, clip: Clip, t: float) -> list[Quat]:
    """:func:`pose`'s twin, the reference (``core.native``)."""
    keyed: dict[int, dict[int, tuple[Key, ...]]] = {}
    for tr in clip.bones:
        if 3 <= tr.comp <= 6:
            keyed.setdefault(tr.target, {})[tr.comp - 3] = tr.keys
    world: list[Quat] = []
    for k, b in enumerate(rig.bones):
        comps = keyed.get(k, {})
        q = qnorm(tuple(evaluate(comps[c], t) if c in comps else b.q[c] for c in range(4)))
        local = qmul(qmul(b.jo, q), b.ra)
        world.append(local if b.parent < 0 else qmul(world[b.parent], local))
    return world


def _origins(rig: Rig, clip: Clip, t: float) -> list[tuple[float, float, float]]:
    """:func:`origins`' twin, the reference (``core.native``)."""
    world = _pose(rig, clip, t)
    keyed = {(tr.target, tr.comp): tr.keys for tr in clip.bones if tr.comp <= 2}
    out: list[tuple[float, float, float]] = []
    for k, b in enumerate(rig.bones):
        local = [evaluate(keyed[k, c], t) if (k, c) in keyed else b.t[c] for c in range(3)]
        out.append(tuple(local) if b.parent < 0 else
                   tuple(p + d for p, d in zip(out[b.parent], _turn(world[b.parent], local))))
    return out


_PACKED: dict[tuple, tuple] = {}   # (id(a rig or clip), its packer) -> (a weak reference to it, its packing)
_TARGETS = 1024                  # the bones a clip's packing indexes (a rig past it: the twins)


def _packed(obj, make):
    """``make(obj)``, once while ``obj`` lives (kept by its id, never
    hashed: a clip's hash walks every key)."""
    key = (id(obj), make)
    got = _PACKED.get(key)
    if got is None or got[0]() is not obj:
        got = _PACKED[key] = (weakref.ref(obj, lambda _, k=key: _PACKED.pop(k, None)), make(obj))
    return got[1]


def _floats(values, n: int) -> bool:
    return len(values) == n and all(type(v) is float for v in values)


def _rig_packing(rig: Rig) -> tuple[array, array] | None:
    """(parents, 15 doubles a bone: jo, rest q, ra, rest t), or None
    where the kernel can't take the rig (a parent not before its child,
    a value not a float, past :data:`_TARGETS` bones): the twins'."""
    bones = rig.bones
    if len(bones) > _TARGETS or not all(type(b.parent) is int and b.parent < k for k, b in enumerate(bones)):
        return None
    if not all(_floats(b.jo, 4) and _floats(b.q, 4) and _floats(b.ra, 4) and _floats(b.t, 3) for b in bones):
        return None
    return array("q", [b.parent for b in bones]), array("d", [x for b in bones for x in (*b.jo, *b.q, *b.ra, *b.t)])


def _keys(tracks) -> tuple[dict, array] | None:
    """Each (target, component) the last of ``tracks`` (target,
    component, keys) keys, its key offset and count in the packed keys;
    None where a key isn't 4 floats, a track has none or its one key's
    time is NaN (no end of the track holds a time, so :func:`evaluate`
    looks for a second key: the twin raises)."""
    keyed = {}
    for target, comp, keys in tracks:
        keyed[target, comp] = keys
    flat, at = [], {}
    for tc, keys in keyed.items():
        if not keys or not all(_floats(key, 4) for key in keys) or len(keys) == 1 and math.isnan(keys[0][0]):
            return None
        at[tc] = (len(flat) // 4, len(keys))
        for key in keys:
            flat += key
    return at, array("d", flat)


def _clip_packing(clip: Clip) -> tuple[array, array] | None:
    """(14 ids a bone: its 7 components' key offset and count, the keys)
    of ``clip``'s bone tracks, or None (the twins')."""
    got = _keys((tr.target, tr.comp, tr.keys) for tr in clip.bones if 0 <= tr.target < _TARGETS and 0 <= tr.comp <= 6)
    if got is None:
        return None
    at, keys = got
    index = array("q", bytes(8 * 14 * (max((t for t, _ in at), default=-1) + 1)))
    for (t, c), (offset, count) in at.items():
        index[14 * t + 2 * c:14 * t + 2 * c + 2] = array("q", (offset, count))
    return index, keys


def _engine(rig: Rig, clip: Clip, times, origin: bool) -> tuple[array, array | None] | None:
    """``core.native.origins`` of ``rig`` and ``clip`` at ``times``, or
    None where the twins answer (no library, a rig or clip it can't take,
    a time not finite)."""
    r, c = _packed(rig, _rig_packing), _packed(clip, _clip_packing)
    if r is None or c is None:
        return None
    if not all(type(t) is float and math.isfinite(t) or type(t) is int and abs(t) < 1 << 53 for t in times):
        return None
    ts = array("d", times)
    return native.origins(*r, *c, ts, origin=origin)


def _turn(q: Quat, v) -> tuple[float, float, float]:
    """``v`` turned by the unit quaternion ``q``."""
    return qmul(qmul(q, (*v, 0.0)), qinv(q))[:3]


# --- the role map -------------------------------------------------------------
_FINGERS = ("thumb", "indexfgr", "middlefgr", "ringfgr", "pinkyfgr")
FAMILIES: dict[str, tuple[str, ...]] = {
    "hip": ("hip",), "leg_1": ("leg_1",), "leg_2": ("leg_2",), "ankle": ("ankle",),
    "foot_1": ("foot_1",), "foot_2": ("foot_2",),
    "shoulder": ("shoulder", "shoulder_2", "shoulder_3"), "shoulder_2": ("shoulder_2",),
    "arm_1": ("arm_1",), "arm_2": ("arm_2", "arm", "arm1"), "hand": ("hand", "w"),
    "hand_endnode": ("hand_endnode",),
    **{f"{f}_{n}": (f"{f}_{n}",) for f in _FINGERS for n in (1, 2, 3)},
}
"""Each sided garret4 bone (``left_``/``right_`` off) and the names (side
off) a body's bone playing it may carry."""
CENTRAL = ("root_joint", "spine_1", "spine_2", "spine_3", "spine_endnode", "neck", "head", "jaw",
           *(f"loincloth_{s}_{n}" for s in ("front", "back") for n in (1, 2, 3)), "ring_front")
"""garret4's unsided bones a body's bone of the same name plays."""
AIM: dict[str, tuple[str, ...]] = {
    "hip": ("leg_1",), "leg_1": ("leg_2",), "leg_2": ("ankle",), "ankle": ("foot_2",), "foot_1": ("foot_2",),
    "shoulder": ("shoulder_2", "arm_1"), "shoulder_2": ("arm_1",), "arm_1": ("arm_2",), "arm_2": ("hand",),
    "hand": ("hand_endnode",), **{f"{f}_{n}": (f"{f}_{n + 1}",) for f in _FINGERS for n in (1, 2)},
    "spine_1": ("spine_2", "spine_3", "spine_endnode", "neck", "head"),
    "spine_2": ("spine_3", "spine_endnode", "neck", "head"), "spine_3": ("spine_endnode", "neck", "head"),
    "spine_endnode": ("neck", "head"), "neck": ("head",),
    **{f"loincloth_{s}_{n}": (f"loincloth_{s}_{n + 1}",) for s in ("front", "back") for n in (1, 2)},
}
"""Each role's segment: the first of these (same side) the body maps sets
the direction its bind re-poses to."""
REQUIRED = (*(f"{s}_{b}" for s in ("left", "right") for b in ("leg_1", "leg_2", "ankle", "arm_1", "arm_2", "hand")),
            "spine_1", "head")
"""Two legs, two arms, a spine and a head: a body without them keeps its
own clips (D229), but a role its :data:`MAPS` overrides set to ``None``
(the golem's head, Step 2.134a) isn't required."""
_SIDES = (("left", "l"), ("right", "r"))
_KEYLORD: dict[str, str | None] = {
    "spine_endnode": "joint13", "left_hand_endnode": "joint38", "right_hand_endnode": "joint37",
    **{f"{s}_{g}": f"{s}_{t}" for s, _ in _SIDES for g, t in (
        ("foot_1", "foot"), ("foot_2", "toes"), ("thumb_1", "thumb_1"), ("thumb_2", "thumb_2"),
        *((f"{f}fgr_{n}", f"{t}_fgr_{n}") for f, t in (("index", "index"), ("middle", "mid"),
                                                      ("pinky", "pinky")) for n in (1, 2)))},
}
"""keylord's and overlord's rig (one rig, Step 2.88): its feet, toes and
fingers named its own way, its spine and hand ends numbered, its thumbs
on its hand (garret4's on his hand's end)."""
_ELEMENTAL: dict[str, str | None] = {
    "root_joint": "tail", "spine_1": "spine01", "spine_2": "spine02", "spine_3": "spine03",
    "spine_endnode": "spine04", "neck": "spine05",
    **{f"{s}_{g}": f"{x}_{t}" for s, x in _SIDES for g, t in (
        ("leg_1", "leg_1"), ("leg_2", "leg_2"), ("ankle", "foot_1"), ("foot_2", "foot_2"),
        ("shoulder", "shoulder"), ("arm_1", "arm01"), ("arm_2", "arm02"), ("hand", "wrist"),
        *((f"{f}_{n}", f"{t}0{n}") for f, t in (("thumb", "thumb"), ("indexfgr", "index"),
                                                 ("middlefgr", "middle"), ("ringfgr", "ring"),
                                                 ("pinkyfgr", "pinky")) for n in (1, 2, 3)))},
}
"""The fire, water and air elementals' rig (Step 2.88): ``l_``/``r_`` on
garret4's sides, its root ``tail``, its neck ``spine05`` (two more
neck bones, held, under the head), its ankle ``*_foot_1`` and its hand
``*_wrist`` (past a held forearm twist bone)."""
_GOLEM: dict[str, str | None] = {
    "spine_1": "torso_bottom", "spine_endnode": "torso_top",
    **dict.fromkeys(("spine_2", "spine_3", "neck", "head", "jaw"), None),
    **{f"{s}_{g}": t.replace("X", s) if t else None for s, _ in _SIDES for g, t in (
        ("leg_1", "leg_X_1"), ("leg_2", "leg_X_2"), ("ankle", "foot_X_1"), ("foot_2", "foot_X_2"),
        ("arm_1", "arm_X_1"), ("arm_2", "arm_X_2"), ("hand", "hand_X_1"), ("hand_endnode", "hand_X_2"),
        ("thumb_1", "hand_X_thumb_1"), ("thumb_2", "hand_X_thumb_2"), ("indexfgr_1", "hand_X_index_1"),
        ("indexfgr_2", "hand_X_index_2"), ("middlefgr_1", "hand_X_midfgr_1"), ("middlefgr_2", "hand_X_midfgr_2"),
        ("pinkyfgr_1", "hand_X_pinky_1"), ("pinkyfgr_2", "hand_X_pinky_2"),
        *((b, None) for b in ("hip", "shoulder", "shoulder_2", "foot_1", "ringfgr_1", "ringfgr_2", "ringfgr_3",
                              "thumb_3", "indexfgr_3", "middlefgr_3", "pinkyfgr_3")))},
}
"""The golem's rig (kingkong's body; Step 2.134a, D340, D355): the side in
the middle of its names (``arm_left_1``, ``leg_right_2``), its torso two
bones (``torso_bottom``, ``torso_top``) and no neck or head, so its head
is left unmapped (:func:`role_map`); its ankle ``foot_X_1``, its hand
``hand_X_1`` and four fingers of two joints; its forearm twist
``arm_X_3``, toes ``foot_X_3`` and back cables follow their parents.
Its shins slant back, so the re-pose turns them 41.6 degrees."""
MAPS: dict[str, dict[str, str | None]] = {
    "balthazar_airship": {},
    "keylord": _KEYLORD, "overlord": _KEYLORD, "golem": _GOLEM,
    **dict.fromkeys(("fire_elemental", "water_elemental", "air_elemental"), _ELEMENTAL),
    **dict.fromkeys((f"townspeople/{b}" for b in (
        *(f"male_{n}" for n in range(1, 10)), *(f"male_farmer_{n}" for n in range(1, 7)),
        *(f"female_{n}" for n in range(1, 5)), *(f"child_{n}" for n in range(1, 4)),
        *(f"child_farmer_{n}" for n in range(1, 4)), "girlchild_1", "girlchild_2",
        "girlchild_farmer_1", "girlchild_farmer_2")), {}),
}
"""The bodies the bake serves (case-folded), each with its overrides
({garret4 bone: the body's bone, or None to leave it unmapped}): Step
2.78's census grades them A (Balthazar and the 29 townspeople: garret4's
rig, the women and children with one clavicle, the children at two
thirds his height; the townsmen since Step 2.89, D239) or B (keylord and
overlord, the elementals; the golem since Step 2.134a, D355)."""
TARGETS_EXTRA: dict[str, dict[str, str | None]] = {"garret4": {}}
"""Bodies the bake serves as a target only, never as a body a build maps
(Step 2.161d, the 2.161 design's L5: garret4's own rig, onto which a
weapon picked for him bakes its style, bare hands' ``t/`` kit or
Balthazar's ``b/`` build; every role his own bone, his staff chain, a
root of its own, a prop the bake hides).  Only :class:`Retarget` and
the weapons' grip read it (:data:`TARGETS`), so no reader of
:data:`MAPS` (the defaults, the victories, the variants) takes him for
a swapped body."""
TARGETS: dict[str, dict[str, str | None]] = {**MAPS, **TARGETS_EXTRA}
"""Every body the bake can bake onto, with its overrides (:data:`MAPS`
and :data:`TARGETS_EXTRA`)."""
LIFTS: dict[str, float] = {"golem": 0.07}
"""How far (model units) each baked clip's root rises on a body whose
baked feet sit off its own (:attr:`Retarget.lift`; case-folded body
names): the golem's re-posed shins put garret4's idle baked onto it
0.136 under its own idle's lowest bone, and its jump's take-off 0.166
and landing -0.017 under, so 0.07 splits the cuts from its own idle
(Balanced keeps it) into the take-off and back from the landing
(-0.10 / +0.09; 0.133 would match the idles but drop the landing 0.15:
Step 2.134a's judging of the golem's feet)."""
FLOORED: dict[str, frozenset[str]] = {"golem": frozenset({"roll_forward"})}
"""The baked clips (by body, case-folded) :func:`floored` raises through
the clip (Step 2.134a; D420, the owner: "Garret's roll, lifted";
AZ-629): garret4's roll baked onto the golem's rig tucks its hands
2.20 model units under the floor (10.6 m at kingkong's own size), its
ends' lowest bone (a toe) 0.08 and 0.19 under."""
_SIDE_EPS = 0.005


def _split(name: str) -> tuple[str, int]:
    """A bone name's stem and side by its name (-1 left, +1 right, 0)."""
    low = name.casefold()
    for prefix, side in (("left_", -1), ("right_", 1)):
        if low.startswith(prefix):
            return low[len(prefix):], side
    return low, 0


def role_map(target: Rig, garret4: Rig, overrides: dict[str, str | None] | None = None) -> dict[int, int]:
    """``{target bone: garret4 bone}`` (module docstring); garret4's
    bones are taken in his order (a parent before its children), each
    from the target bones not yet taken.  :class:`ValueError` names the
    roles of :data:`REQUIRED` a body lacks, but one its ``overrides``
    leave unmapped on purpose (``None``: the golem's head, Step 2.134a)."""
    overrides = {k.casefold(): v for k, v in (overrides or {}).items()}
    names = {b.name.casefold(): k for k, b in enumerate(target.bones)}
    by_g: dict[int, int] = {}
    for g, bone in enumerate(garret4.bones):
        low = bone.name.casefold()
        stem, named_side = _split(low)
        if low in overrides:
            pick = overrides[low]
            if pick is not None:
                by_g[g] = names[pick.casefold()]
            continue
        if named_side:
            family = FAMILIES.get(stem)
            side = 1 if garret4.positions[g][0] > 0 else -1
        else:
            family, side = ((low,) if low in CENTRAL else None), 0
        if family is None:
            continue
        anchor = next((by_g[a] for a in garret4.ancestors(g) if a in by_g), None)
        best = None
        for k, tb in enumerate(target.bones):
            if k in by_g.values() or _split(tb.name)[0] not in family:
                continue
            if side and target.positions[k][0] * side <= _SIDE_EPS:
                continue
            up = target.ancestors(k)
            if anchor is not None and anchor not in up:
                continue
            depth = up.index(anchor) if anchor is not None else len(up)
            if best is None or depth < best[0]:
                best = (depth, k)
        if best is not None:
            by_g[g] = best[1]
    have = {garret4.bones[g].name.casefold() for g in by_g}
    missing = [r for r in REQUIRED if r not in have and overrides.get(r, "") is not None]
    if missing:
        raise ValueError(f"{target.name}: garret4's clips can't be baked onto it: no bone plays "
                         f"{', '.join(missing)}")
    return {k: g for g, k in by_g.items()}


class Retarget:
    """garret4's rig mapped onto ``body``'s (:func:`role_map`, the
    re-pose, the hip ratio), its markers grown by :data:`ADDED_MARKERS`
    unless not ``grow``; :func:`bake_clip` uses it.  With a ``lender``
    other than garret4 (Step 2.134a; since Step 2.159a a townsfolk
    family's rig, whose bare-hands kit bakes onto each body of the
    family), that body's rig in his place: each of ``body``'s bones
    takes the lender's bone that plays the same garret4 role (the role
    map of each, :func:`role_map`; garret4's names name the roles for the
    re-pose's aim), so :attr:`garret4` is the lender's rig.  ``stand``, the
    body's own clip its idle slot plays when only some of garret4's
    clips are baked onto it (Step 2.121), sets :attr:`lift`: how far
    its lowest mapped bone sits at that clip's t 0 above where garret4's
    idle baked onto it puts it, which every baked clip's root rises by,
    so the body cuts in from its own idle at its height (without, ``lift``:
    a body's :data:`LIFTS` entry, else 0).
    :class:`ValueError` when the body isn't one :data:`TARGETS` lists or
    one with no clips (which maps no bone: his clips are timers on it),
    or can't be mapped, or the lender isn't one :data:`MAPS` lists."""

    def __init__(self, characters_xbr: bytes, body: str, *, grow: bool = True, stand: str | None = None,
                 lift: float = 0.0, lender: str = PLAYER):
        mapped = body.casefold() in TARGETS
        if not mapped and read_body(characters_xbr, body).clips:
            raise ValueError(f"{body}: no garret4 role map (retarget.MAPS)")
        g4 = Rig.read(characters_xbr, PLAYER)
        self.garret4 = g4 if lender == PLAYER else Rig.read(characters_xbr, lender)
        self.target = target = Rig.read(characters_xbr, body)
        roles = role_map(target, g4, TARGETS[body.casefold()]) if mapped else {}   # its bone -> the role it plays
        if lender == PLAYER:
            lent = None
        elif lender.casefold() in MAPS and mapped:   # each role's bone of the lender's
            lent = {g: s for s, g in role_map(self.garret4, g4, MAPS[lender.casefold()]).items()}
        else:
            raise ValueError(f"{lender}'s clips can't be baked onto {body}: no role map for both (retarget.MAPS)")
        self.source = roles if lent is None else {k: lent[g] for k, g in roles.items() if g in lent}
        mine = {m.casefold() for m in target.markers}
        self.added = tuple((n, d) for n, d in marker_records(characters_xbr, PLAYER)
                           if grow and n.casefold() in ADDED_MARKERS and n.casefold() not in mine)
        markers = [m.casefold() for m in (*target.markers, *(n for n, _ in self.added))]
        self.markers = {i: markers.index(m.casefold()) for i, m in enumerate(self.garret4.markers)
                        if m.casefold() in markers}
        self.feet = next((i for i, m in enumerate(self.garret4.markers) if m.casefold() == "m_feet"), -1)
        g_root = next(g for g, b in enumerate(self.garret4.bones) if b.parent < 0)
        self.root = next((k for k, g in self.source.items() if g == g_root), None)
        if self.root is not None and target.bones[self.root].parent >= 0:
            raise ValueError(f"{body}: the bone garret4's root maps to isn't a root")
        # the props: the bones under no mapped bone, which a baked clip hides
        self.props = tuple(k for k in range(len(target.bones)) if self.source and k not in self.source
                           and not any(a in self.source for a in target.ancestors(k)))
        # the hip-height ratio: the thighs' bind height over garret4's (the leg
        # length; an elemental's root isn't at its thighs' height)
        thighs = [(k, g) for k, g in self.source.items()
                  if g4.bones[roles[k]].name.casefold() in ("left_leg_1", "right_leg_1")]
        self.hip = (sum(target.positions[k][2] for k, _ in thighs)
                    / sum(self.garret4.positions[g][2] for _, g in thighs)) if thighs else 1.0
        self.mapped_parent: dict[int, int] = {}
        self.repose: dict[int, Quat] = {}
        g_index = {b.name.casefold(): g for g, b in enumerate(g4.bones)}   # the roles, by garret4's names
        mapped = {roles[k]: k for k in self.source}
        for k in sorted(self.source, key=lambda k: len(target.ancestors(k))):   # parents first
            g = self.source[k]
            p = next((a for a in target.ancestors(k) if a in self.source), -1)
            gp = self.source[p] if p >= 0 else -1
            if gp >= 0 and gp not in self.garret4.ancestors(g):
                raise ValueError(f"{body}: {target.bones[k].name}'s chain from "
                                 f"{target.bones[p].name} isn't garret4's ancestry path")
            self.mapped_parent[k] = p
            stem, side = _split(g4.bones[roles[k]].name)
            prefix = {-1: "left_", 1: "right_", 0: ""}[side]
            child = next((g_index[prefix + c] for c in AIM.get(stem, ())
                          if g_index.get(prefix + c) in mapped), None)
            if child is None:
                self.repose[k] = self.repose.get(p, _I)
            else:
                d_t = [a - b for a, b in zip(target.positions[mapped[child]], target.positions[k])]
                d_g = [a - b for a, b in zip(self.garret4.positions[self.source[mapped[child]]],
                                             self.garret4.positions[g])]
                self.repose[k] = _aim(d_t, d_g)
        self.lift = lift if self.root is not None else 0.0
        if stand is not None and self.root is not None:
            def low(clip: Clip) -> float:
                at = origins(target, clip, 0.0)
                return min(at[k][2] for k in self.source)

            self.lift = (low(named_clip(characters_xbr, body, stand))
                         - low(bake_clip(self, named_clip(characters_xbr, PLAYER, "idle"))))

    def rest(self, k: int) -> Quat:
        """Target bone ``k``'s re-posed bind world rotation."""
        return qmul(self.repose.get(k, _I), self.target.world[k])


# --- the bake -----------------------------------------------------------------
def _varies(comps: dict[int, tuple[Key, ...]]) -> bool:
    return any(len({k[1] for k in keys}) > 1 or any(k[2] or k[3] for k in keys) for keys in comps.values())


def bake_clip(rt: Retarget, clip: Clip, drawn: float = 1.0) -> Clip:
    """garret4's ``clip`` for ``rt``'s body (module docstring); on a body
    with no clips (a timer bake) each root bone at its rest plus his
    ``m_feet`` keys over ``drawn``, the scale the game draws it at, in
    each component some key of which leaves 1 mm (none at a ``drawn`` of
    0 or not finite)."""
    G, B = rt.garret4, rt.target
    rot: dict[int, dict[int, tuple[Key, ...]]] = {}
    trans: dict[int, dict[int, tuple[Key, ...]]] = {}
    for tr in clip.bones:
        if 3 <= tr.comp <= 6:
            rot.setdefault(tr.target, {})[tr.comp - 3] = tr.keys
        elif tr.comp <= 2:
            trans.setdefault(tr.target, {})[tr.comp] = tr.keys

    def local(c: int, t: float) -> Quat:
        b, comps = G.bones[c], rot.get(c, {})
        return qmul(qmul(b.jo, qnorm(tuple(evaluate(comps[i], t) if i in comps else b.q[i]
                                           for i in range(4)))), b.ra)

    out: list[Track] = []
    for k in sorted(rt.source):
        g, p = rt.source[k], rt.mapped_parent[k]
        gp = rt.source[p] if p >= 0 else -1
        chain, c = [], g
        while c != gp:
            chain.append(c)
            c = G.bones[c].parent
        chain.reverse()
        par = B.bones[k].parent
        a = qmul(qmul(qmul(qinv(B.bones[k].jo), qinv(B.world[par]) if par >= 0 else _I),
                      qinv(rt.repose.get(p, _I))), G.world[gp] if gp >= 0 else _I)
        c_ = qmul(qmul(qinv(G.world[g]), rt.rest(k)), qinv(B.bones[k].ra))
        folded = [f for f in chain[:-1] if _varies(rot.get(f, {}))]
        comps = rot.get(g, {})
        if folded or any(_stepped(keys) for keys in comps.values()):
            out += _sampled(rt, k, clip.length, chain, a, c_, rot)
            continue
        for f in chain[:-1]:
            a = qmul(a, local(f, 0.0))
        m = _linear(qmul(a, G.bones[g].jo), qmul(G.bones[g].ra, c_))
        times = sorted({key[0] for keys in comps.values() for key in keys}) or [0.0]
        rows = _linear_rows(comps, G.bones[g].q, m, times)
        out += _tracks(k, B.bones[k].q, clip.length,
                       [[(t, v[r], i[r], o[r]) for t, v, i, o in rows] for r in range(4)])
    if rt.root is not None:     # the height over m_feet x the hip ratio, horizontal as garret4's
        g_root, rest = rt.source[rt.root], B.bones[rt.root].t
        t0 = (rest[0], rest[1], rest[2] + rt.lift)
        roots = dict(trans.get(g_root, {}))
        feet = next((tr.keys for tr in clip.markers if tr.target == rt.feet and tr.comp == 2), None)
        if feet is not None:
            out.append(_root_height(rt, t0[2], G.bones[g_root].t[2], roots.pop(2, None), feet))
        elif rt.lift and 2 not in roots:
            out.append(Track(rt.root, 2, ((0.0, t0[2], 0.0, 0.0), (clip.length, t0[2], 0.0, 0.0))))
        for comp, keys in sorted(roots.items()):
            s, base = (rt.hip if comp == 2 else 1.0), G.bones[g_root].t[comp]
            out.append(Track(rt.root, comp, tuple(
                (t, t0[comp] + s * (v - base), s * i, o if o > FLT_MAX else s * o) for t, v, i, o in keys)))
    if not rt.source and drawn and math.isfinite(drawn):   # a timer bake (Step 2.127, AZ-562)
        feet = [tr for tr in clip.markers if tr.target == rt.feet and tr.comp <= 2
                and any(abs(key[1]) > 1e-3 for key in tr.keys)]
        out += [Track(k, tr.comp, tuple((t, b.t[tr.comp] + v / drawn, i / drawn, o if o > FLT_MAX else o / drawn)
                                        for t, v, i, o in tr.keys), tr.modes)
                for k, b in enumerate(B.bones) if b.parent < 0 for tr in feet]
    out += [Track(k, comp, ((0.0, 0.0, 0.0, 0.0), (clip.length, 0.0, 0.0, 0.0)))
            for k in rt.props for comp in (7, 8, 9)]
    markers = [Track(rt.markers[tr.target], tr.comp, tr.keys, tr.modes)
               for tr in clip.markers if tr.target in rt.markers]
    return Clip(clip.length, tuple(sorted(out, key=lambda tr: (tr.target, tr.comp))),
                tuple(sorted(markers, key=lambda tr: (tr.target, tr.comp))))


def _linear_rows(comps: dict[int, tuple[Key, ...]], rest: Quat, m, times: list[float]) -> list:
    """bake_clip's rows on its linear path: at each of ``times``, (t, m x
    the components' values, m x their left slopes, m x their right
    slopes), ``comps`` keyed, the others at ``rest``."""
    rows = _rows(native.linear, [rest], [comps], m, times)
    if rows is not None:
        return rows
    rows = []   # the twin (core.native)
    for t in times:
        v = [evaluate(comps[i], t) if i in comps else rest[i] for i in range(4)]
        s = [_slopes(comps[i], t) if i in comps else (0.0, 0.0) for i in range(4)]
        rows.append((t, *([sum(m[r][i] * x[i] for i in range(4)) for r in range(4)]
                          for x in (v, [l for l, _ in s], [r for _, r in s]))))
    return rows


def _rows(kernel, links, comps: list[dict[int, tuple[Key, ...]]], consts, times: list[float], *more) -> list | None:
    """``kernel`` (``core.native.linear`` or ``chain``) over ``links``
    (a rest rotation, or bones: their jo, rest q and ra), ``comps`` (each
    link's keyed components) and ``consts`` (rows of 4 floats), as rows of
    (t, value, left slope, right slope); None where the twin answers (no
    library, a value or time it can't take)."""
    if not all(type(t) is float and math.isfinite(t) for t in (*times, *more)):
        return None
    flat = [x for row in consts for x in row]
    quats = [q for b in links for q in ((b,) if isinstance(b, tuple) else (b.jo, b.q, b.ra))]
    vals = [x for q in quats for x in q]
    if not (all(_floats(row, 4) for row in (*consts, *quats))):
        return None
    got = _keys((i, c, keys) for i, mine in enumerate(comps) for c, keys in mine.items())
    if got is None or any(type(c) is not int or not 0 <= c < 4 for _, c in got[0]):
        return None
    index = array("q", bytes(64 * len(comps)))
    for (i, c), (offset, count) in got[0].items():
        index[8 * i + 2 * c:8 * i + 2 * c + 2] = array("q", (offset, count))
    ts = array("d", times)
    if kernel is native.linear:
        out = kernel(index, got[1], array("d", vals), array("d", flat), ts)
    else:
        out = kernel(array("d", vals), index, got[1], array("d", flat[:4]), array("d", flat[4:]), ts, *more)
    if out is None:
        return None
    return [(t, out[12 * j:12 * j + 4], out[12 * j + 4:12 * j + 8], out[12 * j + 8:12 * j + 12])
            for j, t in enumerate(times)]


def _root_height(rt: Retarget, t0: float, base: float, root, feet) -> Track:
    """The root's z track where garret4's ``m_feet`` z moves (``feet``;
    ``root`` his root z keys, ``None`` when unkeyed): t0 + hip x (z - base
    - f) + f, so the body's feet sit on ``m_feet``, where the model is
    placed (0x42E40), as his do; split at the union of both curves' key
    times, exact."""
    curves = [keys for keys in (root, feet) if keys is not None]
    if any(_stepped(keys) for keys in curves):
        raise ValueError(f"{rt.target.name}: garret4's root or m_feet height steps in a clip")

    def at(keys, t: float, rest: float) -> tuple[float, float, float]:
        return (evaluate(keys, t), *_slopes(keys, t)) if keys is not None else (rest, 0.0, 0.0)

    rows = []
    for t in sorted({key[0] for keys in curves for key in keys}):
        (z, zi, zo), (f, fi, fo) = at(root, t, base), at(feet, t, 0.0)
        rows.append((t, t0 + rt.hip * (z - base - f) + f, rt.hip * (zi - fi) + fi, rt.hip * (zo - fo) + fo))
    return Track(rt.root, 2, tuple(rows))


def _tracks(k: int, rest: Quat, length: float, comps: list[list[Key]]) -> list[Track]:
    """Bone ``k``'s rotation tracks from each component's keys; a constant
    component at the bone's rest value is left out (the pose starts from
    it), any other constant one keeps two keys (no vanilla track has
    fewer)."""
    out = []
    for r, keys in enumerate(comps):
        if len({round(key[1], 7) for key in keys}) == 1 and not any(key[2] or key[3] for key in keys):
            if abs(keys[0][1] - rest[r]) < 1e-6:
                continue
            keys = [(0.0, keys[0][1], 0.0, 0.0), (length, keys[0][1], 0.0, 0.0)]
        out.append(Track(k, 3 + r, tuple(keys)))
    return out


def _sampled(rt: Retarget, k: int, length: float, chain: list[int], a: Quat, c: Quat, rot) -> list[Track]:
    """Bone ``k``'s rotation sampled at :data:`SAMPLE_HZ` and garret4's
    key times on its path (an animated folded bone makes it nonlinear),
    with one-sided slopes."""
    known = sorted({0.0, length} | {key[0] for f in chain for keys in rot.get(f, {}).values() for key in keys
                                     if 0.0 <= key[0] <= length})
    n = max(2, math.ceil(length * SAMPLE_HZ) + 1)
    grid = [length * i / (n - 1) for i in range(n)]
    times = sorted(set(known) | {t for t in grid if min(abs(t - u) for u in known) > 2e-3})
    rows = _chain_rows([rt.garret4.bones[f] for f in chain], [rot.get(f, {}) for f in chain], a, c, times, length)
    return _tracks(k, rt.target.bones[k].q, length,
                   [[(t, q[r], i[r], o[r]) for t, q, i, o in rows] for r in range(4)])


def _chain_rows(links: list[BoneRecord], comps: list[dict[int, tuple[Key, ...]]], a: Quat, c: Quat,
                times: list[float], length: float, h: float = 1e-5) -> list:
    """:func:`_sampled`'s rows: at each of ``times``, (t, a x the chain's
    local rotations (``links``' bones, ``comps`` their keyed components)
    x c, normalised and kept on the side of the one before; its slopes
    over ``h`` either side, inside 0 to ``length``)."""
    rows = _rows(native.chain, links, comps, (a, c), times, length, h)
    if rows is not None:
        return rows

    def at(t: float, ref: Quat | None) -> Quat:   # the twin (core.native)
        prod = _I
        for b, mine in zip(links, comps):
            prod = qmul(prod, qmul(qmul(b.jo, qnorm(tuple(evaluate(mine[i], t) if i in mine else b.q[i]
                                                          for i in range(4)))), b.ra))
        q = qnorm(qmul(qmul(a, prod), c))
        return tuple(-x for x in q) if ref is not None and sum(x * y for x, y in zip(q, ref)) < 0 else q

    rows, prev = [], None
    for t in times:
        q = at(t, prev)
        lo, hi = max(0.0, t - h), min(length, t + h)
        ql, qr = at(lo, q), at(hi, q)
        rows.append((t, q, [(x - y) / (t - lo) if t > lo else 0.0 for x, y in zip(q, ql)],
                     [(y - x) / (hi - t) if hi > t else 0.0 for x, y in zip(q, qr)]))
        prev = q
    return rows


def _plus(keys, more) -> tuple[Key, ...]:
    """The curve ``keys`` plus the curve ``more``, exact: split at the
    union of both curves' key times, each key the sum's value and its
    slope on either side (a Hermite curve is linear in its values and
    tangents)."""
    rows = []
    for t in sorted({k[0] for k in keys} | {k[0] for k in more}):
        (ki, ko), (mi, mo) = _slopes(keys, t), _slopes(more, t)
        rows.append((t, evaluate(keys, t) + evaluate(more, t), ki + mi, ko + mo))
    return tuple(rows)


FLOOR_FINE = 4
"""How many times as often as its keys :func:`floored` samples a clip's
lowest bone (each key the most it needs within a key of it, so the
curve between keys stays over the floor)."""


def floored(rt: Retarget, clip: Clip) -> Clip:
    """``clip``, baked onto ``rt``'s body, with its root raised wherever
    its lowest bone (any but a hidden prop's, from the clip's ``m_feet``
    height: the floor) is under the floor, by that much (Step 2.134a,
    D420, AZ-629): keyed at :data:`SAMPLE_HZ`, each key the most it
    needs within a key's time of it (sampled :data:`FLOOR_FINE` times as
    often), with monotone slopes (Fritsch-Carlson: 0 at an end or a
    turn, so between two keys the lift stays between their values, never
    under what that stretch needs nor under 0), added to the root's
    height track; the clip itself on a body with no mapped root or no
    bone under the floor."""
    if rt.root is None:
        return clip
    feet = next((tr.keys for tr in clip.markers if tr.target == rt.markers.get(rt.feet) and tr.comp == 2), None)
    shown = [k for k in range(len(rt.target.bones)) if k not in rt.props]
    n = max(2, math.ceil(clip.length * SAMPLE_HZ) + 1)
    times = [clip.length * i / (n - 1) for i in range(n)]

    def under(t: float) -> float:
        at = origins(rt.target, clip, t)
        return max(0.0, (evaluate(feet, t) if feet is not None else 0.0) - min(at[k][2] for k in shown))
    fine = [under(clip.length * j / ((n - 1) * FLOOR_FINE)) for j in range((n - 1) * FLOOR_FINE + 1)]
    need = [max(fine[max(0, (i - 1) * FLOOR_FINE):(i + 1) * FLOOR_FINE + 1]) for i in range(n)]
    if not any(need):
        return clip
    h = times[1] - times[0]
    steps = [(b - a) / h for a, b in zip(need, need[1:])]
    slopes = [0.0, *(0.0 if a * b <= 0 else math.copysign(min(abs(a + b) / 2, 3 * abs(a), 3 * abs(b)), a)
                     for a, b in zip(steps, steps[1:])), 0.0]
    lift = tuple((t, v, d, d) for t, v, d in zip(times, need, slopes))
    root = next((tr for tr in clip.bones if (tr.target, tr.comp) == (rt.root, 2)), None)
    rest = rt.target.bones[rt.root].t[2]
    keys = root.keys if root is not None else ((0.0, rest, 0.0, 0.0), (clip.length, rest, 0.0, 0.0))
    if _stepped(keys):
        raise ValueError(f"{rt.target.name}: its baked root height steps, so it can't be raised off the floor")
    bones = [tr for tr in clip.bones if tr is not root] + [Track(rt.root, 2, _plus(keys, lift))]
    return Clip(clip.length, tuple(sorted(bones, key=lambda tr: (tr.target, tr.comp))), clip.markers)


def stretched(clip: Clip, length: float) -> Clip:
    """``clip`` played over ``length`` seconds, slower or faster as a
    whole (Step 2.121): every key, bone and marker alike, at k times its
    time with its tangents over k (k = ``length`` over the clip's), a
    held one (FLT_MAX or past) kept, so each segment is the same curve k
    times as long (0xD8300 scales a tangent by its segment's span); the
    length exactly ``length``."""
    k = length / clip.length

    def keys(tr: Track) -> Track:
        return replace(tr, keys=tuple((t * k, v, i if abs(i) >= FLT_MAX else i / k, o if abs(o) >= FLT_MAX else o / k)
                                      for t, v, i, o in tr.keys))

    return Clip(length, tuple(map(keys, clip.bones)), tuple(map(keys, clip.markers)))


def turned(rig: Rig, clip: Clip, turns: dict[int, Quat]) -> Clip:
    """``clip`` with each bone ``k`` of ``turns`` turned by its rotation
    ``r`` before its own: q'(t) = r x q(t) (Step 2.143, D428: a variant's
    ``arms``), so its local rotation is JO r q RA and its subtree turns
    with it.  Left multiplication by a unit quaternion is an orthogonal 4x4
    map, so it keeps the pose's normalisation, and a Hermite curve is
    linear in its values and tangents: the four components are split at
    the union of their key times (an unkeyed one at the bone's rest) and
    each new key is the map of the old values and slopes there, exact
    (:func:`_tracks` leaves a component out that ends constant at the
    rest).  The other tracks are kept in their order, the new ones in
    place of the bone's old rotation tracks.  :class:`ValueError` where a
    turned curve steps or isn't played with modes 0."""
    out: list[Track] = []
    done: set[int] = set()
    for tr in clip.bones:
        if tr.target in turns and 3 <= tr.comp <= 6:
            if tr.target not in done:
                out += _turned_tracks(rig, clip, tr.target, turns[tr.target])
                done.add(tr.target)
        else:
            out.append(tr)
    for k in sorted(set(turns) - done):
        out += _turned_tracks(rig, clip, k, turns[k])
    return Clip(clip.length, tuple(out), clip.markers)


def eased(clip: Clip, window: tuple[float, float, float]) -> Callable[[float], float]:
    """The weight a windowed turn has at clip time ``t``: 1 from
    ``window[0]`` to ``window[1]`` (shares of the clip's length), a
    smoothstep over ``window[2]`` of it before and after, 0 elsewhere."""
    a, b, ease = (w * clip.length for w in window)

    def weight(t: float) -> float:
        if a <= t <= b:
            return 1.0
        if ease <= 0.0:   # a hard edge: no margin to divide by
            return 0.0
        x = (t - (a - ease)) / ease if t < a else ((b + ease) - t) / ease
        return 0.0 if x <= 0.0 else x * x * (3.0 - 2.0 * x)
    return weight


def turned_over(rig: Rig, clip: Clip, k: int, axis, degrees: float, window: tuple[float, float, float]) -> Clip:
    """``clip`` with bone ``k`` turned ``degrees`` about ``axis`` (the
    model's frame at bind, taken into the bone's joint frame as
    :func:`turned`'s ``arms`` are) by the weight :func:`eased` gives
    ``window`` (Step 2.154: a sash kept out of a bigger form in one stretch
    of a jump): q'(t) = r(w(t)) x q(t), r(w) the turn by w of the angle,
    sampled at :data:`SAMPLE_HZ` and the bone's key times with one-sided
    slopes (the product of two curves isn't one Hermite).  The other
    tracks are kept; :class:`ValueError` where the bone's rotation steps
    or isn't played with modes 0."""
    comps = {tr.comp - 3: tr for tr in clip.bones if tr.target == k and 3 <= tr.comp <= 6}
    if any(_stepped(tr.keys) or tr.modes != (0, 0) for tr in comps.values()):
        raise ValueError(f"{rig.bones[k].name}'s rotation steps or isn't played with modes 0, so it can't be turned")
    b = rig.bones[k]
    frame = qmul(rig.world[b.parent], b.jo) if b.parent >= 0 else b.jo
    ax = _turn(qinv(frame), axis)
    length = math.sqrt(sum(x * x for x in ax))
    ax = tuple(x / length for x in ax)
    weight = eased(clip, window)
    rest = b.q

    def at(t: float) -> Quat:
        q = tuple(evaluate(comps[i].keys, t) if i in comps else rest[i] for i in range(4))
        half = math.radians(degrees) * weight(t) / 2.0
        return qmul((*(fdlibm.sin(half) * x for x in ax), fdlibm.cos(half)), q)

    n = max(2, math.ceil(clip.length * SAMPLE_HZ) + 1)
    known = sorted({0.0, clip.length} | {key[0] for tr in comps.values() for key in tr.keys if 0.0 <= key[0] <= clip.length})
    grid = [clip.length * i / (n - 1) for i in range(n)]      # as _sampled: no grid time within 2 ms of a key's
    times = sorted(set(known) | {t for t in grid if min(abs(t - u) for u in known) > 2e-3})
    h, rows = 1e-5, []
    for t in times:
        q = at(t)
        lo, hi = max(0.0, t - h), min(clip.length, t + h)
        ql, qr = at(lo), at(hi)
        rows.append((t, q, [(x - y) / (t - lo) if t > lo else 0.0 for x, y in zip(q, ql)],
                     [(y - x) / (hi - t) if hi > t else 0.0 for x, y in zip(q, qr)]))
    new = _tracks(k, rest, clip.length, [[(t, q[c], i[c], o[c]) for t, q, i, o in rows] for c in range(4)])
    out: list[Track] = []
    done = False
    for tr in clip.bones:
        if tr.target == k and 3 <= tr.comp <= 6:
            if not done:
                out += new
                done = True
        else:
            out.append(tr)
    if not done:
        out += new
    return Clip(clip.length, tuple(out), clip.markers)


def _turned_tracks(rig: Rig, clip: Clip, k: int, r: Quat) -> list[Track]:
    comps = {tr.comp - 3: tr for tr in clip.bones if tr.target == k and 3 <= tr.comp <= 6}
    if any(_stepped(tr.keys) or tr.modes != (0, 0) for tr in comps.values()):
        raise ValueError(f"{rig.bones[k].name}'s rotation steps or isn't played with modes 0, so it can't be turned")
    rest = rig.bones[k].q
    m = _linear(r, _I)
    rows = []
    for t in sorted({key[0] for tr in comps.values() for key in tr.keys} or {0.0, clip.length}):
        v = [evaluate(comps[i].keys, t) if i in comps else rest[i] for i in range(4)]
        s = [_slopes(comps[i].keys, t) if i in comps else (0.0, 0.0) for i in range(4)]
        rows.append((t, *([sum(m[row][i] * x[i] for i in range(4)) for row in range(4)]
                          for x in (v, [a for a, _ in s], [b for _, b in s]))))
    return _tracks(k, rest, clip.length, [[(t, v[c], i[c], o[c]) for t, v, i, o in rows] for c in range(4)])


def quiet(clip: Clip, marks: Iterable[int]) -> Clip:
    """``clip`` without its tracks on the markers ``marks`` (their
    indices on its body), which then hold their defaults: W17's copy of
    a clip that switches its body's own damage field on (Step 2.75e),
    and a victory played on a body's attack (Step 2.121), each marker
    it would switch on off as its defaults are."""
    marks = set(marks)
    return replace(clip, markers=tuple(tr for tr in clip.markers if tr.target not in marks))


def centred(clip: Clip, drawn: float, feet: int, roots: dict[int, tuple[float, ...]],
            keep: Iterable[int] = ()) -> Clip:
    """``clip`` drawn about its entity at the drawn scale ``drawn`` (Step
    2.133, AZ-608): the game places the model at the entity less the
    clip's ``m_feet`` (marker ``feet``) unscaled (0x42E40) and draws its
    bones and markers x D, so where ``m_feet`` leaves the origin the
    drawn body sat (D - 1) x ``m_feet`` off the pose about the entity
    (garret4's ``roll_forward`` on keylord own, D 2: 4.07 m ahead at the
    roll's end, then a slide back over the exit crossfade).  Each
    horizontal translation in model space, every root bone's of
    ``roots`` (its index -> its rest translation, for a component it
    doesn't key) and every keyed marker's but ``m_feet``'s, becomes
    itself less (1 - 1/D) x ``m_feet``'s, split at the union of both
    curves' key times (a Hermite curve is linear in its values and
    tangents): exact, so the drawn body is the pose about the entity x D
    through the clip and both crossfades (each blend is linear).
    ``m_feet`` keeps its tracks, so the root motion is the same, and so
    do the markers ``keep`` (their indices: an attack's damage markers,
    Step 2.175, AZ-623, so its boxes hit where the build's reach reads
    them, D x the clip's from where the attack starts).  The
    clip as it is at a ``drawn`` of 1, 0 or not finite, or with no
    horizontal ``m_feet`` track; :class:`ValueError` where a curve it
    combines steps or isn't played with modes 0."""
    lead = {tr.comp: tr for tr in clip.markers if tr.target == feet and tr.comp in (0, 1)}
    if drawn == 1.0 or not drawn or not math.isfinite(drawn) or not lead:
        return clip
    c = 1.0 - 1.0 / drawn

    def less(tr: Track | None, rest: float, comp: int) -> tuple[Key, ...]:
        f = lead[comp].keys
        if any(t.modes != (0, 0) or _stepped(t.keys) for t in (lead[comp], tr) if t is not None):
            raise ValueError("a curve centred on m_feet steps or isn't played with modes 0")
        keys = tr.keys if tr is not None else None

        def at(k, t: float) -> tuple[float, float, float]:
            return (evaluate(k, t), *_slopes(k, t)) if k is not None else (rest, 0.0, 0.0)

        rows = []
        for t in sorted({key[0] for k in (keys, f) if k is not None for key in k}):
            (v, vi, vo), (w, wi, wo) = at(keys, t), at(f, t)
            rows.append((t, v - c * w, vi - c * wi, vo - c * wo))
        return tuple(rows)

    have = {(tr.target, tr.comp): tr for tr in clip.bones}
    bones = [tr for tr in clip.bones if not (tr.target in roots and tr.comp in lead)]
    bones += [Track(k, comp, less(have.get((k, comp)), roots[k][comp], comp), (0, 0))
              for k in roots for comp in sorted(lead)]
    keep = {feet, *keep}
    markers = [replace(tr, keys=less(tr, 0.0, tr.comp)) if tr.comp in lead and tr.target not in keep else tr
               for tr in clip.markers]
    return Clip(clip.length, tuple(sorted(bones, key=lambda tr: (tr.target, tr.comp))), tuple(markers))


# --- storage ------------------------------------------------------------------
def named_clip(characters_xbr: bytes, body: str, clip: str) -> Clip:
    """The clip ``characters/<body>/<clip>`` (:func:`read_clip`).
    :class:`ValueError` when ``characters_xbr`` has no such clip."""
    toc = parse_toc(characters_xbr)
    i = next((i for i, n in named_resources(characters_xbr).items()
              if n.casefold() == f"characters/{body}/{clip}".casefold()), None)
    if i is None or toc[i].tag != "banm":
        raise ValueError(f"characters.xbr: body {body!r} has no clip {clip!r}")
    return read_clip(characters_xbr, toc[i].file_offset)


def grow_markers(payload: bytes, added: Iterable[tuple[str, tuple[float, ...]]]) -> bytes:
    """A ``body`` payload with ``added`` (name, twelve defaults) after its
    markers: the marker table moves to the payload's end (4-aligned), the
    old records first so their indices hold (each name pointer re-aimed
    at its old string), the new names after it; +0x18 and +0x1C follow."""
    added = list(added)
    if not added:
        return payload
    out = bytearray(payload) + bytes(-len(payload) % 4)
    count = struct.unpack_from("<i", out, 0x18)[0]
    old = 0x1C + struct.unpack_from("<i", out, 0x1C)[0]
    table = len(out)
    names = table + 0x38 * (count + len(added))
    out += bytes(names - table)
    for i in range(count):
        rec, src = table + 0x38 * i, old + 0x38 * i
        out[rec:rec + 0x38] = payload[src:src + 0x38]
        struct.pack_into("<i", out, rec + 4, src + 4 + struct.unpack_from("<i", payload, src + 4)[0] - (rec + 4))
    for j, (name, defaults) in enumerate(added):
        rec = table + 0x38 * (count + j)
        struct.pack_into("<ii12f", out, rec, len(name), len(out) - (rec + 4), *defaults)
        out += name.encode("ascii") + b"\0"
    struct.pack_into("<ii", out, 0x18, count + len(added), table - 0x1C)
    return bytes(out)


def baked_key(body: str, clip: str, into: str = BAKED_DIR) -> str:
    """The key of garret4's ``clip`` baked onto ``body`` (a lender's
    under ``into``)."""
    return f"characters/{body}/{into}{clip}".casefold()


def bake_body(characters_xbr: bytes, index_xbr: bytes, body: str, clips: Iterable[str], *,
              grow: bool = True, stand: str | None = None, drawn: float = 1.0,
              lift: float = 0.0, centre: Iterable[str] = (), lunges: Iterable[str] = (), lender: str = PLAYER,
              into: str = BAKED_DIR, quiet_markers: Iterable[str] = (),
              post: Callable[[str, Clip, Clip], Clip] | None = None,
              given: dict[str, Clip] | None = None) -> tuple[bytes, bytes]:
    """``characters.xbr`` and ``index.xbr`` with garret4's ``clips`` (or
    ``lender``'s, under ``into``, each without its tracks on the body's
    markers named in ``quiet_markers``: :func:`quiet`; with ``given``,
    each clip as given there, keyed on the lender's rig, not read from
    ``characters.xbr``: Step 2.159a's kit) baked
    onto ``body`` (:class:`Retarget` with ``grow``, ``stand`` and ``lift``,
    :func:`bake_clip` at the drawn scale ``drawn``, those of ``centre``
    drawn about the entity there, :func:`centred`: the roll, Step 2.133,
    and those of ``lunges`` with their damage markers kept, an attack that
    moves ``m_feet``, Step 2.175, AZ-623;
    and :data:`FLOORED`'s raised off the floor, :func:`floored`; each
    then handed to ``post`` with its name and the clip it bakes, the
    player-model swap's W26, Step 2.134b)
    under :func:`baked_key` and, with ``grow``,
    :data:`ADDED_MARKERS` added to its marker table.  :class:`ValueError`
    names what blocks it (D35)."""
    rt = Retarget(characters_xbr, body, grow=grow, stand=stand, lift=lift, lender=lender)
    centre, lunges = set(centre), set(lunges)
    names_of = [m.casefold() for m in (*rt.target.markers, *(n for n, _ in rt.added))]
    hush = {names_of.index(m.casefold()) for m in quiet_markers if m.casefold() in names_of}
    toc, names = parse_toc(characters_xbr), named_resources(characters_xbr)
    by_name = {n.casefold(): i for i, n in names.items()}
    index, at = body_at(characters_xbr, body)
    payload = grow_markers(bytes(characters_xbr[at:at + toc[index].size]), rt.added)
    from azurkit.tools.characters import pool

    jobs, stop = [], None
    for clip in sorted(set(clips)):
        i = by_name.get(f"characters/{lender}/{clip}".casefold()) if given is None else None
        if given is not None and clip in given:
            source = given[clip]
        elif i is None or toc[i].tag != "banm":
            stop = ValueError(f"{lender} has no clip {clip!r} to bake onto {body}")   # after the clips before it
            break
        else:
            source = read_clip(characters_xbr, toc[i].file_offset)
        jobs.append((clip, source, clip in centre | lunges, clip in lunges, clip in FLOORED.get(body.casefold(), ())))
    new = []
    for (clip, source, *_), baked in zip(jobs, pool.each(_baked, (rt, drawn, hush, names_of, body), jobs,
                                                          cost=lambda n: jobs[n][1].length)):   # Step 2.176
        if isinstance(baked, ValueError):
            raise baked
        if post is not None:
            baked = post(clip, source, baked)
        new.append(NewResource(baked_key(body, clip, into), "banm", write_clip(baked)))
    if stop is not None:
        raise stop
    grown = append_resources(characters_xbr, new, rewrite={index: payload})
    return grown, add_index_records(index_xbr, [IndexRecord(r.name, "characters.xbr", r.tag) for r in new])


def _baked(shared: tuple, job: tuple):
    """:func:`bake_body`'s bake of one clip before its ``post``, in a worker
    process: the clip, or the :class:`ValueError` a step raised (its
    drawing about the body's centre's named)."""
    rt, drawn, hush, names_of, body = shared
    clip, source, about, lunge, floor = job
    try:
        baked = quiet(bake_clip(rt, source, drawn), hush)
        if about and rt.root is not None and rt.feet in rt.markers:
            try:
                baked = centred(baked, drawn, rt.markers[rt.feet], {rt.root: rt.target.bones[rt.root].t},
                                {names_of.index(m) for m in DAMAGE_MARKERS if m in names_of} if lunge else ())
            except ValueError as exc:
                return ValueError(f"garret4's {clip} drawn about {body}'s centre: {exc}")
        return floored(rt, baked) if floor else baked
    except ValueError as exc:
        return exc


def add_clips(characters_xbr: bytes, index_xbr: bytes, body: str, clips: dict[str, Clip],
              markers: Iterable[tuple[str, tuple[float, ...]]] = ()) -> tuple[bytes, bytes]:
    """``characters.xbr`` and ``index.xbr`` with ``clips`` (a name under
    ``body`` -> its clip) added as ``characters/<body>/<name>``, as
    :func:`bake_body` adds its clips (the player-model swap's W17 copies,
    Step 2.75e), and ``markers`` (name, twelve defaults) grown on the body
    (:func:`grow_markers`; W27, Step 2.134b)."""
    new = [NewResource(f"characters/{body}/{name}".casefold(), "banm", write_clip(clip))
           for name, clip in sorted(clips.items())]
    markers = list(markers)
    if markers:
        index, at = body_at(characters_xbr, body)
        rewrite = {index: grow_markers(bytes(characters_xbr[at:at + parse_toc(characters_xbr)[index].size]), markers)}
    return (append_resources(characters_xbr, new, rewrite=rewrite if markers else None),
            add_index_records(index_xbr, [IndexRecord(r.name, "characters.xbr", r.tag) for r in new]))


__all__ = ["ADDED_MARKERS", "AIM", "BAKED_DIR", "CENTRAL", "Clip", "FAMILIES", "FLOOR_FINE", "FLOORED", "LIFTS", "MAPS",
           "REQUIRED", "Retarget", "Rig", "SAMPLE_HZ", "TARGETS", "TARGETS_EXTRA", "Track", "add_clips", "bake_body",
           "bake_clip", "baked_key",
           "centred", "evaluate", "floored", "grow_markers", "named_clip", "origins", "pose", "qangle", "qinv", "qmul",
           "quiet", "read_clip", "role_map", "stretched", "turned", "write_clip"]
