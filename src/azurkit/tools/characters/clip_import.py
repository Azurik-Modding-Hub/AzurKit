"""A body's clips back from glTF animations (Step 2.154, D443: the model
toolkit's clip import), for ``azurik-mod model clips``; their way out is
``azurik-mod model export`` (:mod:`azurik_mod.assets.gltf`, whose layout
this reads back).

The file is a ``.glb`` or ``.gltf`` (untrusted data: only its JSON and
buffers are read) whose animations key the body's bones by node name (a
``<bone>__scale`` helper's scale its bone's).  Each animation is a clip
of its name:

- **Channels to tracks.**  A rotation's values (and a CUBICSPLINE's
  tangents) are the export's JO x q x RA, so the clip's q is the inverse
  of that linear map applied to them; a translation is the bone's own (a
  compensated child of a helper bone has its parent's rest scale divided
  out; one whose parent's scale the animation keys is refused); a scale
  is the bone's (its helper's channel for a helper bone).  Each vector
  becomes a track per component at the channel's key times, a component
  that holds its rest value with flat tangents throughout dropped (the
  export writes an unkeyed one so).  CUBICSPLINE keys keep their
  tangents (both per second, as the game's); LINEAR ones take each
  side's secant (the game's Hermite then runs straight between keys; a
  rotation's straight run, normalised, is glTF's slerp within
  :attr:`ImportedClip.slerp_deg` at each segment's middle: Blender samples
  every frame); STEP ones hold (an out-tangent past FLT_MAX), but a
  channel that never changes (Blender writes a still one STEP, its keys
  within :data:`STILL`) is two flat keys, so the clip exports again.  A LINEAR
  or STEP rotation's keys are made unit (glTF's rule) and turned to the
  shorter way round first.
- **What stays.**  A channel that is the export of the body's clip of
  that name, to float32, keeps that clip's own tracks byte for byte, so an
  unchanged file gives the clip's own bytes; its marker tracks (root
  motion, hit boxes: not exported) are kept too, and its length unless
  the file's extras give one.  A new clip takes its length from its
  extras, else its last key, and no marker track.
- **The check.**  Every clip with a track made from the file is posed
  by the engine model (:func:`~azurik_mod.assets.gltf._engine`) at
  :data:`CHECK_KEYS` of its keys and of the middles between them and at
  :data:`~azurik_mod.assets.gltf.POSE_SAMPLES` even times, and compared
  with the file's own pose by glTF's rules, a LINEAR rotation run as the
  game runs it (straight between its keys, normalised: its distance from
  glTF's slerp is :attr:`ImportedClip.slerp_deg`); a bone more
  than :data:`TOLERANCE` off (1e-5 for CUBICSPLINE) is refused by name.
- **Thinning** (Step 2.158): Blender keys every channel at every frame
  (24 a second), about 20 times vanilla's keys.  Each made track (a kept
  one stays byte for byte) is thinned greedily, in key order: a key is
  dropped while the Hermite between the keys kept round it, with the
  curve's own slope at each (the mean of its in and out tangents), stays
  within ``eps`` of the track at every key and segment middle it spans
  (a rotation's or scale's ``eps`` divided by one plus its bone's reach,
  the farthest bone under it); a kept key next to a kept key keeps its
  own tangent on that side, so an unthinned segment is the file's.  A
  made component within ``eps`` of its rest over the whole clip is
  dropped (its rest plays).  The thinned
  clip is posed against the file's pose at :data:`THIN_TOLERANCE`; past
  it ``eps`` halves (:data:`THIN_EPS`, at most :data:`THIN_HALVINGS`
  times), and then the clip stays unthinned.  A stepped track isn't
  thinned.

:func:`write_clips` puts them into ``characters.xbr``: a clip of that
name rewritten in place (grown by whole pages where it outgrows its
place), a new one added under the body with its ``index.xbr`` record.
Every refusal is a :class:`ValueError` naming the file, clip and channel
(D35).  Nothing here prints a byte or a coordinate.
"""

from __future__ import annotations

import hashlib
import math
import pickle
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from azurkit.tools.characters import gltf as gx
from azurkit.tools.characters import mesh_edit
from azurkit.tools.characters.retarget import FLT_MAX, Clip, Track, _linear, add_clips, evaluate, write_clip
from azurkit.core.xbr.append import append_resources
from azurkit.core.xbr.nodes import named_resources

TOLERANCE = 1e-4
"""How far (a world matrix entry) an imported clip's pose may sit from
the file's (both agree to float rounding)."""
CHECK_KEYS = 16
"""How many of an animation's key times, and of the middles between them,
the check poses (evenly spread), beside :data:`~azurik_mod.assets.gltf.POSE_SAMPLES`."""
_STEP = math.inf
"""A held key's out-tangent (float32 inf: past FLT_MAX, which the game's evaluator holds at)."""
_PATHS = {"translation": 0, "rotation": 3, "scale": 7}
STILL = 1e-6
"""How far a STEP channel's keys may differ (Blender's float noise) and
still be one held value, written as two flat keys."""
THIN_TOLERANCE = 2e-3
"""How far (a world matrix entry: about 2 mm at 1 m) a thinned clip's pose
may sit from the file's."""
THIN_EPS = 1e-3
"""The first per-track bound (a track's value: a quaternion component, a
model unit, a scale) thinning keeps each made track within."""
THIN_HALVINGS = 6
"""How many times ``eps`` halves when a thinned clip fails its posed check."""


@dataclass(frozen=True)
class ImportedClip:
    """One animation read as a clip: its name, the clip, how many of its
    bone tracks it kept from the body's clip of that name and how many it
    made, its channels, their interpolations, the most a LINEAR
    rotation's run sits from slerp (degrees), whether it replaces a
    clip of the body's, its bone tracks' keys before and after thinning,
    and the farthest (model units) a root bone moves from its rest
    (a drawn offset: the game's root motion is a marker track)."""

    name: str
    clip: Clip
    kept: int
    made: int
    channels: int
    interpolations: tuple[str, ...]
    slerp_deg: float
    replaces: bool
    keys_before: int = 0
    keys_after: int = 0
    root_travel: float = 0.0


def _secants(times, values):
    """LINEAR keys' in and out tangents: each side's secant (0 past the ends)."""
    n = len(times)
    ins, outs = np.zeros_like(values), np.zeros_like(values)
    for i in range(n - 1):
        s = (values[i + 1] - values[i]) / (times[i + 1] - times[i])
        outs[i], ins[i + 1] = s, s
    return ins, outs


def _channel(doc, buffers, sampler) -> tuple[str, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """A sampler as (interpolation, times, values, in, out)."""
    times = np.array([x for (x,) in mesh_edit._values(doc, buffers, sampler["input"])], float)
    out = np.array(mesh_edit._values(doc, buffers, sampler["output"]), float)
    how = sampler.get("interpolation", "LINEAR")
    if len(times) < 1 or (len(times) > 1 and not np.all(np.diff(times) > 0)) or times[0] < 0:
        raise ValueError("its key times aren't increasing from 0")
    if how == "CUBICSPLINE":
        if len(out) != 3 * len(times):
            raise ValueError("a CUBICSPLINE output isn't three rows a key")
        out = out.reshape(len(times), 3, -1)
        return how, times, out[:, 1], out[:, 0], out[:, 2]
    if len(out) != len(times):
        raise ValueError(f"a {how} output isn't a row a key")
    if how == "LINEAR":
        a, b = _secants(times, out)
        return how, times, out, a, b
    if how == "STEP":
        zero = np.zeros_like(out)
        return how, times, out, zero, np.full_like(out, _STEP)
    raise ValueError(f"interpolation {how!r} isn't LINEAR, STEP or CUBICSPLINE")


def _shorter(values: np.ndarray) -> np.ndarray:
    """Quaternion keys each turned to the shorter way from the one before."""
    out = values.copy()
    for i in range(1, len(out)):
        if float(out[i] @ out[i - 1]) < 0:
            out[i] = -out[i]
    return out


def _tracks(k: int, first: int, times, values, ins, outs, rest, stepped: bool) -> list[Track]:
    """A vector channel's component tracks (module docstring)."""
    tracks = []
    for c in range(values.shape[1]):
        if np.all(values[:, c] == np.float32(rest[c])) and not np.any(ins[:, c]) and (stepped or not np.any(outs[:, c])):
            continue
        if stepped and np.all(np.abs(values[:, c] - values[0, c]) <= STILL):   # a still channel: flat
            v = float(np.float32(values[0, c]))
            t0, t1 = float(np.float32(times[0])), float(np.float32(times[-1]))
            tracks.append(Track(k, first + c, ((t0, v, 0.0, 0.0), (max(t1, t0 + 1.0 / 60.0), v, 0.0, 0.0))))
            continue
        keys = tuple((float(np.float32(t)), float(np.float32(v)), float(np.float32(a)),
                      _STEP if stepped and i < len(times) - 1 else float(np.float32(o)))
                     for i, (t, v, a, o) in enumerate(zip(times, values[:, c], ins[:, c], outs[:, c])))
        if len(keys) == 1:      # one key holds: the game's tracks hold two
            keys = (keys[0], (keys[0][0] + 1.0 / 60.0, keys[0][1], 0.0, 0.0))
        tracks.append(Track(k, first + c, keys))
    return tracks


def _expected(body, clip: Clip) -> dict[tuple[int, str], tuple]:
    """The export's channels of ``clip`` (float32, as the file holds
    them), by (node, path)."""
    chans, _, _ = gx._channels(body, clip)
    out = {}
    for node, path, (times, v, a, o) in chans:
        if len(times) == 1:
            times, v, a, o = (np.array([times[0], times[0] + 1 / gx.SAMPLE_HZ]), np.repeat(v, 2, 0),
                              np.zeros((2, v.shape[1])), np.zeros((2, v.shape[1])))
        out[node, path] = tuple(np.asarray(x, np.float32).astype(float) for x in (times, v, a, o))
    return out


def _same(got, want) -> bool:
    return all(g.shape == w.shape and np.array_equal(np.asarray(g, np.float32), w) for g, w in zip(got, want))


def read_clips(characters_xbr: bytes, body: str, path: Path, names=None, *,
               bones_only: bool = False) -> list[ImportedClip]:
    """The animations of ``path`` (``names``: those, by name; all by
    default) as clips of the body ``characters/<body>`` (module
    docstring); :class:`ValueError` names the file, clip and rule.  With
    ``bones_only`` a channel on a node that is no bone of the body is
    dropped, not refused (another body's clip lent through the bake, Step
    2.164c: the bones its own mesh added play no role)."""
    path = Path(path)
    try:
        return _read(characters_xbr, body, path, names, bones_only)
    except ValueError as exc:
        raise ValueError(f"{path.name}: {exc}") from None
    except (KeyError, IndexError, TypeError, AttributeError, struct.error, UnicodeDecodeError, OSError) as exc:
        raise ValueError(f"{path.name}: not a glTF this import reads ({type(exc).__name__}: {exc})") from None


def read_key(characters_xbr: bytes, body: str, names=None) -> str | None:
    """A digest of all :func:`read_clips` reads of ``characters_xbr`` for
    ``body`` and ``names``: the body's name, index, bones, binds and helper
    bones and its own clips of those names (an import replaces or keeps
    those; ``_read`` reads nothing else of it), so one read serves every
    archive that agrees on them, whatever other clips it has (Step X.81c);
    ``None`` where the body can't be read (:func:`read_clips` names why).
    The body is read once a ``bytes`` archive (a build asks it of each of
    a recipe's clips)."""
    from azurkit.tools.characters.characters import _kept

    try:
        info = _kept(characters_xbr, ("clip_import.read_key", body), lambda: gx._read(characters_xbr, body))
    except (ValueError, KeyError, IndexError, TypeError, AttributeError, struct.error, UnicodeDecodeError):
        return None
    own = info.clips if names is None else tuple((n, c) for n, c in info.clips if n in set(names))
    return hashlib.sha256(pickle.dumps((info.name, info.index, info.bones, info.binds, info.helpers, own),
                                       pickle.HIGHEST_PROTOCOL)).hexdigest()


def _read(characters_xbr: bytes, body: str, path: Path, names, bones_only: bool = False) -> list[ImportedClip]:
    info = gx._read(characters_xbr, body)
    doc, buffers, _ = mesh_edit._load(path)
    bone_of = {b.name: k for k, b in enumerate(info.bones)}
    nodes = {}
    for i, n in enumerate(doc.get("nodes", [])):
        name = str(n.get("name", ""))
        if name in bone_of:
            nodes[i] = (bone_of[name], "bone")
        elif name.endswith(gx.HELPER) and name.removesuffix(gx.HELPER) in bone_of:
            nodes[i] = (bone_of[name.removesuffix(gx.HELPER)], "helper")
    anims = doc.get("animations", [])
    if names is not None:
        have = {a.get("name") for a in anims}
        missing = [n for n in names if n not in have]
        if missing:
            raise ValueError(f"no animation {', '.join(map(repr, missing))} (it has {len(anims)})")
        anims = [a for a in anims if a.get("name") in set(names)]
    if not anims:
        raise ValueError("no animation to import")
    own = dict(info.clips)
    out = []
    for anim in anims:
        name = str(anim.get("name", ""))
        if not name or not name.isascii() or name != name.lower() or "\0" in name:
            raise ValueError(f"animation {name!r}: a clip's name is lower-case ASCII")
        old = own.get(name)
        expected = _expected(info, old) if old is not None else {}
        groups: dict[tuple[int, int], list[Track]] = {}
        kept_groups: set[tuple[int, int]] = set()
        hows, slerp = set(), 0.0
        scaled = {nodes[c["target"]["node"]][0] for c in anim["channels"]
                  if c["target"].get("node") in nodes and c["target"]["path"] == "scale"}
        for c in anim["channels"]:
            target = c["target"]
            where = f"animation {name!r} channel on node {target.get('node')} {target.get('path')}"
            if target.get("node") not in nodes:
                if bones_only:
                    continue
                raise ValueError(f"{where}: the node is no bone of {info.name}")
            k, kind = nodes[target["node"]]
            p = target["path"]
            if p not in _PATHS:
                raise ValueError(f"{where}: only translation, rotation and scale")
            if (kind == "helper") != (p == "scale" and k in info.helpers):
                raise ValueError(f"{where}: bone {info.bones[k].name}'s {p} lives on "
                                 f"{'its __scale helper' if p == 'scale' else 'its own node'}")
            try:
                how, times, v, a, o = _channel(doc, buffers, anim["samplers"][c["sampler"]])
            except ValueError as exc:
                raise ValueError(f"{where}: {exc}") from None
            hows.add(how)
            node = target["node"]
            if (node, p) in expected and _same((times, v, a, o), expected[node, p]):
                kept_groups.add((k, _PATHS[p]))
                continue
            b = info.bones[k]
            if p == "rotation":
                if how != "CUBICSPLINE":   # unit keys (glTF's rule), so the game's straight run is their nlerp
                    norm = np.linalg.norm(v, axis=1, keepdims=True)
                    if not np.all(norm > 1e-6):
                        raise ValueError(f"{where}: a rotation key of length 0")
                    v = _shorter(v / norm)
                    a, o = _secants(times, v) if how == "LINEAR" else (a, o)
                    slerp = max(slerp, _slerp_gap(v))
                m = np.linalg.inv(np.array(_linear(b.jo, b.ra)))
                v, a = v @ m.T, a @ m.T
                o = o if how == "STEP" else o @ m.T
                rest = b.q
            elif p == "translation":
                rest = b.t
                if info.folds(k):
                    if b.parent in scaled:
                        raise ValueError(f"{where}: its parent's scale is keyed too, so its translation isn't one "
                                         "track")
                    s = np.asarray(info.bones[b.parent].s, float)
                    v, a = v / s, a / s
                    o = o if how == "STEP" else o / s
            else:
                rest = b.s
            groups[(k, _PATHS[p])] = _tracks(k, _PATHS[p], times, v, a, o, rest, how == "STEP")
        # the tracks: the old clip's kept groups in place, the made ones where theirs were, new ones after;
        # a group the file keys nowhere is unkeyed (its node's rest is the bone's: the check holds it so)
        bones_out: list[Track] = []
        placed: set[tuple[int, int]] = set()
        made = 0
        for tr in (old.bones if old is not None else ()):
            g = (tr.target, 0 if tr.comp < 3 else 3 if tr.comp < 7 else 7)
            if g in kept_groups:
                bones_out.append(tr)
            elif g in groups and g not in placed:
                bones_out += groups[g]
                made += len(groups[g])
                placed.add(g)
        for g in sorted(set(groups) - placed):
            bones_out += groups[g]
            made += len(groups[g])
        extras = anim.get("extras") or {}
        last = max((tr.keys[-1][0] for tr in bones_out), default=0.0)
        length = float(extras["length"]) if isinstance(extras.get("length"), (int, float)) else \
            (old.length if old is not None and last <= old.length + 1e-6 else last)
        clip = Clip(float(np.float32(length)), tuple(bones_out), old.markers if old is not None else ())
        before = sum(len(tr.keys) for tr in clip.bones)
        if made:
            _check(info, clip, doc, buffers, anim, name, TOLERANCE if hows - {"CUBICSPLINE"} else gx.TOLERANCE)
            clip = _thinned(info, clip, {id(tr) for g in groups.values() for tr in g}, doc, buffers, anim, name)
        out.append(ImportedClip(name, clip, len(bones_out) - made, made, len(anim["channels"]),
                                tuple(sorted(hows)), slerp, old is not None, before,
                                sum(len(tr.keys) for tr in clip.bones), _root_travel(info, clip)))
    return out


def _rest(info, target: int, comp: int) -> float:
    b = info.bones[target]
    return (b.t[comp] if comp < 3 else b.q[comp - 3] if comp < 7 else b.s[comp - 7])


def _hermite_at(t0, v0, out0, t1, v1, in1, t):
    d = t1 - t0
    s = (t - t0) / d
    return ((2 * s ** 3 - 3 * s ** 2 + 1) * v0 + d * (s ** 3 - 2 * s ** 2 + s) * out0
            + (-2 * s ** 3 + 3 * s ** 2) * v1 + d * (s ** 3 - s ** 2) * in1)


def _thin_track(track: Track, eps: float, rest: float) -> Track | None:
    """``track`` thinned within ``eps`` (module docstring), or ``None``
    when it holds ``rest`` within ``eps`` throughout."""
    keys = track.keys
    if any(k[3] > FLT_MAX for k in keys[:-1]):   # stepped: held between keys
        return None if all(abs(k[1] - rest) <= eps for k in keys) else track
    times = np.array([k[0] for k in keys])
    mids = (times[:-1] + times[1:]) / 2
    samples = np.sort(np.concatenate([times, mids]))
    dense = np.array([evaluate(keys, float(t)) for t in samples])
    if np.all(np.abs(dense - rest) <= eps):
        return None
    if len(keys) <= 2:
        return track
    slope = [(k[2] + k[3]) / 2 for k in keys]
    slope[0], slope[-1] = keys[0][3], keys[-1][2]

    def fits(a: int, b: int) -> bool:
        inside = (samples >= times[a]) & (samples <= times[b])
        got = _hermite_at(times[a], keys[a][1], slope[a], times[b], keys[b][1], slope[b], samples[inside])
        return bool(np.all(np.abs(got - dense[inside]) <= eps))

    kept = [0]
    for j in range(1, len(keys) - 1):
        if not fits(kept[-1], j + 1):
            kept.append(j)
    kept.append(len(keys) - 1)
    if len(kept) == len(keys):
        return track
    out = []
    for n, i in enumerate(kept):
        t, v, a, o = keys[i]
        if n > 0 and kept[n - 1] != i - 1:
            a = float(np.float32(slope[i]))
        if n < len(kept) - 1 and kept[n + 1] != i + 1:
            o = float(np.float32(slope[i]))
        out.append((t, v, a, o))
    return Track(track.target, track.comp, tuple(out), track.modes)


def _reach(info) -> list[float]:
    """Each bone's reach: the farthest any bone under it sits from it at
    rest (model units), so a turn of it moves that far."""
    at = [w[:3, 3] for w in gx._engine(info, None, 0.0)]
    reach = [0.0] * len(info.bones)
    for k in range(len(info.bones) - 1, -1, -1):
        p = info.bones[k].parent
        while p >= 0:
            reach[p] = max(reach[p], float(np.linalg.norm(at[k] - at[p])))
            p = info.bones[p].parent
    return reach


def _thinned(info, clip: Clip, made: set[int], doc, buffers, anim, name: str) -> Clip:
    """``clip`` with its ``made`` tracks (by id) thinned (module docstring):
    a rotation or scale track within ``eps / (1 + its bone's reach)``."""
    eps = THIN_EPS
    reach = _reach(info)
    for _ in range(THIN_HALVINGS + 1):
        bones = []
        for tr in clip.bones:
            e = eps if tr.comp < 3 else eps / (1.0 + reach[tr.target])
            got = _thin_track(tr, e, _rest(info, tr.target, tr.comp)) if id(tr) in made else tr
            if got is not None:
                bones.append(got)
        thin = Clip(clip.length, tuple(bones), clip.markers)
        try:
            _check(info, thin, doc, buffers, anim, name, THIN_TOLERANCE)
        except ValueError:
            eps /= 2
            continue
        return thin
    return clip


def _root_travel(info, clip: Clip) -> float:
    """The farthest the root bone (the parentless one with the most bones
    under it; a prop's own root, such as the bake's vase, isn't it) sits
    from its rest translation along the floor (x and y) over ``clip``'s
    keys (model units): a drop or a rise, as a sit's (Step 2.168, D660),
    keeps the body over its place."""
    under = [0] * len(info.bones)
    for k in range(len(info.bones) - 1, -1, -1):   # parents come first
        if info.bones[k].parent >= 0:
            under[info.bones[k].parent] += under[k] + 1
    k = max((k for k, b in enumerate(info.bones) if b.parent < 0), key=lambda k: under[k])
    rest = info.bones[k].t
    tracks = {tr.comp: tr.keys for tr in clip.bones if tr.target == k and tr.comp < 3}
    worst = 0.0
    for t in sorted({key[0] for keys in tracks.values() for key in keys}):
        d = [(evaluate(tracks[c], t) if c in tracks else rest[c]) - rest[c] for c in range(2)]
        worst = max(worst, math.sqrt(sum(x * x for x in d)))
    return worst


def _slerp_gap(values: np.ndarray) -> float:
    """The most (degrees) a straight run between unit quaternion keys,
    normalised, sits from slerp, at a quarter of a segment (they meet at
    its ends and its middle)."""
    worst, u = 0.0, 0.25
    for p, q in zip(values, values[1:]):
        p, q = p / np.linalg.norm(p), q / np.linalg.norm(q)
        cos = float(np.clip(p @ q, -1.0, 1.0))
        theta = math.acos(cos)
        if theta < 1e-9:
            continue
        run = (1 - u) * p + u * q
        arc = (math.sin((1 - u) * theta) * p + math.sin(u * theta) * q) / math.sin(theta)
        worst = max(worst, math.degrees(2 * math.acos(min(1.0, abs(float(run @ arc) / np.linalg.norm(run))))))
    return worst


def _gltf_value(how, times, v, a, o, t, path, nlerp: bool = False):
    """A channel at ``t`` by glTF's rules (slerp for a LINEAR rotation;
    with ``nlerp``, the game's straight run between its keys,
    normalised)."""
    if how == "CUBICSPLINE":
        return gx._hermite((times, v, a, o), t)[0]
    if t <= times[0]:
        return v[0]
    if t >= times[-1]:
        return v[-1]
    i = int(np.searchsorted(times, t, side="right")) - 1
    if how == "STEP":
        return v[i]
    s = (t - times[i]) / (times[i + 1] - times[i])
    if path != "rotation":
        return (1 - s) * v[i] + s * v[i + 1]
    p, q = v[i] / np.linalg.norm(v[i]), v[i + 1] / np.linalg.norm(v[i + 1])
    if p @ q < 0:
        q = -q
    if nlerp:
        r = (1 - s) * p + s * q
        return r / np.linalg.norm(r)
    theta = math.acos(min(1.0, float(p @ q)))
    if theta < 1e-9:
        return p
    return (math.sin((1 - s) * theta) * p + math.sin(s * theta) * q) / math.sin(theta)


def _check(info, clip: Clip, doc, buffers, anim, name: str, tolerance: float) -> None:
    """The engine model's pose of ``clip`` against the file's own pose of
    ``anim`` at its keys and between them (module docstring), a LINEAR
    rotation run straight between its keys and normalised, as the game
    plays it (:attr:`ImportedClip.slerp_deg` is how far that sits from
    glTF's slerp)."""
    chans = []
    for c in anim["channels"]:
        how, times, v, a, o = _channel(doc, buffers, anim["samplers"][c["sampler"]])
        chans.append((c["target"]["node"], c["target"]["path"], how, times, v, a, o))
    keys = sorted({float(t) for *_, times, _v, _a, _o in chans for t in times})
    step = max(1, len(keys) // CHECK_KEYS)
    samples = set(keys[::step]) | {(x + y) / 2 for x, y in list(zip(keys, keys[1:]))[::step]} | \
        {clip.length * i / (gx.POSE_SAMPLES - 1) for i in range(gx.POSE_SAMPLES)}
    named = {str(n.get("name", "")): i for i, n in enumerate(doc["nodes"])}
    joint = {k: named.get(b.name + gx.HELPER if k in info.helpers else b.name) for k, b in enumerate(info.bones)}
    for t in sorted(samples):
        if t > clip.length + 1e-6:
            continue
        live: dict[int, dict[str, np.ndarray]] = {}
        for node, path, how, times, v, a, o in chans:
            live.setdefault(node, {})[path] = np.asarray(_gltf_value(how, times, v, a, o, t, path, True), float)
        world = gx._worlds(doc, gx._locals(doc, live))
        for k, w in enumerate(gx._engine(info, clip, t)):
            if joint[k] is None or world[joint[k]] is None:
                continue
            off = float(np.abs(world[joint[k]] - gx.ROOT @ w).max())
            if off > tolerance:
                raise ValueError(f"animation {name!r}: bone {info.bones[k].name} at t={t:.3f} sits {off:.1e} off the "
                                 "file's pose")


def write_clips(characters_xbr: bytes, index_xbr: bytes, body: str, clips: list[ImportedClip]
                ) -> tuple[bytes, bytes]:
    """``characters.xbr`` and ``index.xbr`` with ``clips``: each one that
    replaces a clip of the body's rewritten in its place (grown by whole
    pages where it must), each new one added as
    ``characters/<body>/<name>`` with its index record."""
    info = gx._read(characters_xbr, body)
    names = named_resources(characters_xbr)
    by_name = {n.casefold(): i for i, n in names.items()}
    rewrite = {}
    for c in clips:
        if c.replaces:
            rewrite[by_name[f"characters/{info.name}/{c.name}".casefold()]] = write_clip(c.clip)
    out = append_resources(characters_xbr, rewrite=rewrite) if rewrite else characters_xbr
    new = {c.name: c.clip for c in clips if not c.replaces}
    if new:
        out, index_xbr = add_clips(out, index_xbr, info.name, new)
    return out, index_xbr


__all__ = ["ImportedClip", "THIN_TOLERANCE", "TOLERANCE", "read_clips", "read_key", "write_clips"]
