"""A body's pose over many clip times at once, through the anim layers'
crossfade (Step 2.118c, AZ-529 (b)): the lowest point X28's
``hang_start`` table holds over the floor
(:func:`azurik_mod.patches._player_character.hold_plan`).

The pose is :func:`~azurik_mod.assets.retarget.origins`' engine model
(0xCB730, 0xCA470) vectorised over times with numpy.  A crossfade is the
layer blend ``docs/RE_XBE.md`` § "The anim layers' crossfade" reads:
0xCAD40 starts the new clip on a layer at weight 0.01 and each tick moves
both layers' weights by dt / 0.25 s (:func:`fade_weight`), the fading
layer's time advancing too; the pose turns each layer's rotation to unit
length and w >= 0 (0xCBB6D-0xCBB7C, :func:`sample`; AZ-825, Step 2.207d),
sums them by weight, then normalises, and lerps their translations
(:func:`blend`).  Sitting 2.118's frame-scored ``hang_start`` fits it: at
``h_k`` the new layer ``k - 1`` ticks in, the prior advancing, guard_air
own x2's placed h1-h8 at rms 0.08 m and kingkong own x2's at 0.003 m
(Step 2.118c's fit of the blend)."""

from __future__ import annotations

from array import array

import numpy as np

from azurkit.core import native
from azurkit.tools.characters import retarget
from azurkit.tools.characters.retarget import FLT_MAX, Clip, Rig

FADE_TICKS = 7.5
"""A crossfade's ticks at 30 Hz: anim+0x14's 0.25 s (0x197564)."""

Pose = tuple[np.ndarray, np.ndarray]
"""Per bone and time: the rotations (bones, times, 4; a layer's
:func:`sample` unit and w >= 0, a :func:`blend` their weighted sum) and
translations (bones, times, 3)."""


def fade_weight(n: float) -> float:
    """The new layer's share of the pose ``n`` ticks after 0xCAD40 started
    it: its weight 0.01 + n / 7.5 over the sum with the fading layer's
    1 - n / 7.5, 1 once the fade is over."""
    if n >= FADE_TICKS:
        return 1.0
    new, old = 0.01 + n / FADE_TICKS, 1.0 - n / FADE_TICKS
    return new / (new + old)


def _curve(keys, ts: np.ndarray) -> np.ndarray:
    """0xD8300 with modes 0 (:func:`~azurik_mod.assets.retarget.evaluate`)
    at every time of ``ts``."""
    k = np.asarray(keys, dtype=float)
    if len(k) == 1:
        return np.full(ts.shape, k[0, 1])
    kt, kv, ki, ko = k.T
    seg = np.clip(np.searchsorted(kt, ts, side="right") - 1, 0, len(kt) - 2)
    t0, v0, o0, t1, v1, i1 = kt[seg], kv[seg], ko[seg], kt[seg + 1], kv[seg + 1], ki[seg + 1]
    dt = t1 - t0
    with np.errstate(all="ignore"):
        s = np.where(dt > 0, (ts - t0) / np.where(dt > 0, dt, 1.0), 0.0)
        m0 = dt * o0
        m1 = np.where(np.isfinite(dt * i1), dt * i1, 0.0)
        a, b = 2 * (v0 - v1) + m1 + m0, 3 * (v1 - v0) - 2 * m0 - m1
        value = np.where((o0 > FLT_MAX) | (dt <= 0), v0, ((a * s + b) * s + m0) * s + v0)
    return np.where(ts <= kt[0], kv[0], np.where(ts >= kt[-1], kv[-1], value))


def canon(q: np.ndarray) -> np.ndarray:
    """Rotations ``q`` (..., 4) as 0xCB730 turns each layer's before
    0xA0B70 blends it: normalised, and negated where w < 0 (the scale
    1/|q| changes sign at 0xCBB6D-0xCBB7C), so two layers holding one turn
    in opposite signs blend as that turn (AZ-825)."""
    n = np.linalg.norm(q, axis=-1, keepdims=True)
    q = q / np.where(n > 0, n, 1.0)
    return np.where(q[..., 3:4] < 0.0, -q, q)


def sample(rig: Rig, clip: Clip | None, ts) -> Pose:
    """``clip`` on ``rig`` at each time of ``ts`` (``None``: the bind),
    the unkeyed components the bones' rest values, each rotation
    :func:`canon`'s (the layer's as the blend reads it)."""
    ts = np.atleast_1d(np.asarray(ts, dtype=float))
    if (got := _sampled(rig, clip, ts)) is not None:
        return got
    keyed = {(tr.target, tr.comp): tr.keys for tr in clip.bones} if clip is not None else {}   # the twin
    q = np.empty((len(rig.bones), len(ts), 4))
    t = np.empty((len(rig.bones), len(ts), 3))
    for k, bone in enumerate(rig.bones):
        for c in range(4):
            keys = keyed.get((k, 3 + c))
            q[k, :, c] = _curve(keys, ts) if keys else bone.q[c]
        for c in range(3):
            keys = keyed.get((k, c))
            t[k, :, c] = _curve(keys, ts) if keys else bone.t[c]
    return canon(q), t


_BIND = (array("q"), array("d"))   # no clip: every component its rest value


def _curves(clip: Clip) -> tuple[array, array] | None:
    """(14 ids a bone: its 7 components' key offset and count, 0 the rest
    value; the keys) of :func:`sample`'s ``clip``, or None (the twin's):
    a key not 4 floats or key times not finite and in order."""
    keyed = {(tr.target, tr.comp): tr.keys for tr in clip.bones}
    flat, at = [], {}
    for (target, comp), keys in keyed.items():
        if type(target) is not int or type(comp) is not int:
            return None
        if not (0 <= target < retarget._TARGETS and 0 <= comp <= 6 and keys):
            continue
        if not (all(retarget._floats(key, 4) and np.isfinite(key[0]) for key in keys)
                and all(a[0] <= b[0] for a, b in zip(keys, keys[1:]))):
            return None
        at[target, comp] = (len(flat) // 4, len(keys))
        for key in keys:
            flat += key
    index = array("q", bytes(8 * 14 * (max((t for t, _ in at), default=-1) + 1)))
    for (t, c), (offset, count) in at.items():
        index[14 * t + 2 * c:14 * t + 2 * c + 2] = array("q", (offset, count))
    return index, array("d", flat)


def _sampled(rig: Rig, clip: Clip | None, ts: np.ndarray) -> Pose | None:
    """:func:`sample` by the compiled kernel (``core.native.sample``), or
    None where its twin answers."""
    r = retarget._packed(rig, retarget._rig_packing)
    c = _BIND if clip is None else retarget._packed(clip, _curves)
    if r is None or c is None or ts.ndim != 1 or not np.isfinite(ts).all():
        return None
    ts = np.ascontiguousarray(ts)
    q, t = np.empty((len(rig.bones), len(ts), 4)), np.empty((len(rig.bones), len(ts), 3))
    return (q, t) if native.sample(r[1], *c, ts.ctypes.data, len(ts), q.ctypes.data, t.ctypes.data) else None


def blend(old: Pose, new: Pose, weight: float) -> Pose:
    """Two layers' pose, ``new`` at ``weight`` (:func:`fade_weight`): the
    rotations (:func:`sample`'s, unit and w >= 0) and the translations
    summed by weight (the pose normalises the rotation, :func:`lowest`)."""
    return (1.0 - weight) * old[0] + weight * new[0], (1.0 - weight) * old[1] + weight * new[1]


def _qmul(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    x1, y1, z1, w1 = np.moveaxis(p, -1, 0)
    x2, y2, z2, w2 = np.moveaxis(q, -1, 0)
    return np.stack((w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2), axis=-1)


def _turn(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    u, w = q[..., :3], q[..., 3:4]
    c = 2.0 * np.cross(u, v)
    return v + w * c + np.cross(u, c)


def _heights(rig: Rig, pose: Pose, points=None, skip=frozenset()) -> np.ndarray:
    """Per point and time, its height over the model's origin (model
    units): each bone of ``pose`` but those of ``skip`` (W26's carriers),
    or with ``points`` (a one-bone rig's mesh, model space at the bind)
    each mesh vertex through the bone's pose (as ``hang_top`` reads it)."""
    q, t = pose
    r = retarget._packed(rig, retarget._rig_packing) if points is None else None
    nb, nt = len(rig.bones), q.shape[1] if q.ndim == 3 else -1
    if (r is not None and q.shape == (nb, nt, 4) and t.shape == (nb, nt, 3) and q.dtype == t.dtype == np.float64):
        q, t, z = np.ascontiguousarray(q), np.ascontiguousarray(t), np.empty((nb, nt))
        if native.heights(*r, q.ctypes.data, t.ctypes.data, nt, z.ctypes.data):   # the compiled kernel's
            return np.stack([a for k, a in enumerate(z) if k not in skip])
    n = np.linalg.norm(q, axis=-1, keepdims=True)   # the twin (core.native)
    q = q / np.where(n > 0, n, 1.0)
    world, at = [], []
    for k, bone in enumerate(rig.bones):
        local = _qmul(_qmul(np.asarray(bone.jo), q[k]), np.asarray(bone.ra))
        if bone.parent < 0:
            world.append(local)
            at.append(t[k])
        else:
            world.append(_qmul(world[bone.parent], local))
            at.append(at[bone.parent] + _turn(world[bone.parent], t[k]))
    if points is not None and len(rig.bones) == 1:
        bind = np.asarray(rig.world[0])
        undo = bind * np.array([-1.0, -1.0, -1.0, 1.0])
        turn = _qmul(world[0], undo)[:, None, :]
        rel = np.asarray(points, dtype=float) - np.asarray(rig.positions[0])
        return (at[0][:, None, :] + _turn(np.broadcast_to(turn, (*turn.shape[:1], len(rel), 4)), rel))[..., 2].T
    return np.stack([a for k, a in enumerate(at) if k not in skip])[..., 2]


def lowest(rig: Rig, pose: Pose, points=None, skip=frozenset()) -> np.ndarray:
    """Per time, the lowest point of ``pose`` over the model's origin,
    model units: its lowest bone but those of ``skip`` (W26's carriers),
    or with ``points`` (a one-bone rig's mesh, model space at the bind)
    its mesh's lowest vertex through the bone's pose (as ``hang_top``
    reads it)."""
    return _heights(rig, pose, points, skip).min(axis=0)


def lowest_many(rig: Rig, poses: list[Pose], points=None, skip=frozenset()) -> list[np.ndarray]:
    """:func:`lowest` of each of ``poses``, joined along time for one pass
    over the bones (Step X.81c: a build's hold and fade read hundreds of
    small poses, each pass's cost the bones' and not the times'); each
    time's value is the one :func:`lowest` gives it alone."""
    if not poses:
        return []
    joined = np.concatenate([q for q, _ in poses], axis=1), np.concatenate([t for _, t in poses], axis=1)
    return np.split(lowest(rig, joined, points, skip), np.cumsum([q.shape[1] for q, _ in poses])[:-1])


def part(pose: Pose, a: int, b: int) -> Pose:
    """``pose`` at its times ``a`` to ``b`` (a view)."""
    return pose[0][:, a:b], pose[1][:, a:b]


def highest(rig: Rig, pose: Pose, points=None, skip=frozenset()) -> np.ndarray:
    """Per time, the highest point of ``pose`` over the model's origin
    (:func:`lowest`'s points): the top ``hang_top`` hangs under the
    zipline's cable (Step 2.175b, AZ-599)."""
    return _heights(rig, pose, points, skip).max(axis=0)


__all__ = ["FADE_TICKS", "Pose", "blend", "canon", "fade_weight", "highest", "lowest", "lowest_many", "part", "sample"]
