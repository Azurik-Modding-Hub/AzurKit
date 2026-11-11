"""A character body out to glTF 2.0 for Blender (Step 2.139, D332, D388): its
skeleton, skin, most detailed mesh, textures and clips, written and then
checked against the game's own model before anything is kept.

The layout (``azurik-mod model export``; the evidence is Step 2.139's design
and its probes, every body and clip of the USA disc):

- **Nodes.** One per bone, in the body's order and under its name: its rest
  translation (+0x30), its rotation JO x q x RA normalised (Hamilton,
  (x, y, z, w), the engine's local rotation, 0xCA470), its rest scale
  (+0x4C).  Then a ``<bone>__scale`` helper for each bone that has children
  and a scale that isn't always 1 (its rest scale, or a key or tangent of a
  scale track in any of the body's clips): the engine keeps a compensated
  bone's scale off its children (segment-scale compensation, read from
  0xCA470, ``docs/RE_DATA.md``), which glTF can't, so the helper
  (a child of the bone, no translation or rotation) carries the scale and
  the bone's vertices, the bone none, and a compensated child's translation
  is multiplied by the parent's scale.  The set is the body's alone (its
  rest and every clip), whatever ``clips`` exports.  Then the root, named
  after the body, turning the model's z up to glTF's y up (X -90 degrees,
  Level Studio's; no channel touches it, so every clip stays in the model's
  frame: in Blender, with Global on, the coordinates are the game's and the
  body faces +Y), and the mesh node, a scene root beside it.
- **Skin.** Every bone and helper is a joint; each inverse bind is the bone
  record's +0x60 matrix as is (D3D's row-vector rows are glTF's columns), a
  helper repeating its bone's.
- **Mesh.** One primitive per group of LOD 0 (``render.body_meshes``' strip
  triangles), its material the group's (``gshd``, row).  POSITION (+0),
  TEXCOORD_0 (+40, no flip: D3D's and glTF's origin are both the top left)
  and WEIGHTS_0 (+12) as stored; NORMAL (+28) normalised, a zero one
  replaced by its triangles' area-weighted normal; JOINTS_0 from the four
  bone-slot bytes at +56, one per weight: byte b names palette entry b-1 for
  1-12 and b-2 for 14-32, never 13 (the palette upload at 0x9B320, Step
  2.130; every one of the 545,661 live weights of every LOD decodes inside
  its group's palette and names every entry of it, where b-1 for every b
  throws 13,197 out: Step 2.139's critique, probe 2), so the joint is the
  palette's bone, or its helper.  Two live weights naming one joint (57
  jellyfish vertices) are summed into the first, which glTF needs.
  ``_AZ_VID`` is each vertex's (group, index), exact in floats, and
  ``TEXCOORD_1`` the same pair (Blender's ``UVMap.001``: its default
  export drops ``_AZ_VID`` and keeps a second UV map), for the
  same-topology import (:mod:`azurik_mod.assets.mesh_edit`, Step 2.142).
- **Materials and textures.** One per (``gshd``, row), base colour only:
  stage 0's ``surf`` (``render.surf_image``'s base level; an animated list's
  first frame) as ``<slug>_surf<TOC>.png``, every other stage's written
  beside it, the shader's fields in the extras.  Double-sided: 991
  triangles of the disc's bodies wind the other way, and the game's cull
  mode is unread.
- **Clips.** One animation per clip with a bone track, CUBICSPLINE.  Each
  vector is split at the union of its components' key times, a component's
  value and its left and right slopes taken there (an unkeyed one its rest
  value, slope 0), and a rotation's (in, value, out) turned through JO and
  RA: a Hermite segment restricted to a sub-interval is the cubic of its
  end values and slopes, and the engine and glTF both normalise after
  interpolating, so the curve is the game's exactly (its values aren't unit
  quaternions).  A compensated child's translation is multiplied by its
  helper parent's scale (a constant, or the parent's curve times the
  child's rest translation, both exact; where both animate, the product
  sampled at :data:`~azurik_mod.assets.retarget.SAMPLE_HZ` plus both key
  sets).  Markers (root motion, hit boxes) and LOD 1+ are not exported.

:func:`check_export` reads the written files back, alone, and checks them:
C1 the buffers against the source, C2 the rest pose skinned by glTF's
rules against the engine model's within :data:`TOLERANCE` m, C3 the
weights, C4 every live joint inside its group's palette, C5 the clips and
their channels, C6 every joint of every clip at :data:`POSE_SAMPLES` times
and its first keys against the engine model, C7 each PNG against its
decoded texture, C8 the file's structure.  C2 and C4 can't tell a right
slot decode from a wrong one (at rest every joint's world times its
inverse bind is the identity, and C4 re-applies the decode); the
bijection above is the decode's pin (``tests/test_model_export.py``).
The engine model is the one :func:`azurik_mod.assets.retarget.pose` and
the bake's sittings stand on, plus scale and its compensation.

The buffer layout (one 4-byte aligned view per accessor, bounds on
POSITION and every sampler input, the root's quaternion) and C8's
structural checks are ported from Azurik Level Studio's ``write_gltf`` and
``validate_gltf`` (MIT, ``NOTICE.md``).  Needs numpy (a runtime dependency).
The files are game assets: nothing here prints a byte or a coordinate.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import struct
import tempfile
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from azurkit.core import fdlibm, inflate
from azurkit.tools.characters.characters import BoneRecord, body_at, bone_records, inverse_binds, mesh_groups
from azurkit.tools.characters.retarget import FLT_MAX, SAMPLE_HZ, Clip, _linear, _slopes, evaluate, qmul, qnorm, read_clip
from azurkit.tools.characters import render
from azurkit.tools.characters.draw import png_rgba
from azurkit.core.xbr.nodes import named_resources, parse_toc

VERSION = 1
GENERATOR = "azurik-mod model export"
ROOT_ROTATION = (-math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5))
"""The root node's quaternion: X -90 degrees, the model's +z to glTF's +y."""
TOLERANCE = 1e-5
"""How far (m, or a matrix entry) a check lets the file sit off the game."""
POSE_SAMPLES = 16
"""Even times per clip C6 checks, beside each clip's first keys."""
HELPER = "__scale"
_FLOAT, _UBYTE, _USHORT, _UINT = 5126, 5121, 5123, 5125
_COMPONENTS = {_FLOAT: "<f4", _UBYTE: "u1", _USHORT: "<u2", _UINT: "<u4", 5120: "i1", 5122: "<i2"}
_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
_PATHS = {"translation": 3, "rotation": 4, "scale": 3}


# --------------------------------------------------------------------------- the body
@dataclass(frozen=True)
class _Body:
    """A body as the export lays it out: its name, TOC index, bones, inverse
    binds, every clip under it (name, clip) and its helper bones."""

    name: str
    index: int
    bones: tuple[BoneRecord, ...]
    binds: tuple[tuple[float, ...], ...]
    clips: tuple[tuple[str, Clip], ...]
    helpers: tuple[int, ...]

    @property
    def slug(self) -> str:
        return self.name.replace("/", "_")

    @property
    def nodes(self) -> int:
        """The joint count: the bones, then the helpers."""
        return len(self.bones) + len(self.helpers)

    def helper(self, k: int) -> int | None:
        """Bone ``k``'s helper node, or ``None``."""
        return len(self.bones) + self.helpers.index(k) if k in self.helpers else None

    def joint(self, k: int) -> int:
        """The node bone ``k``'s vertices skin to: its helper, else its own."""
        h = self.helper(k)
        return k if h is None else h

    def folds(self, k: int) -> bool:
        """Whether bone ``k``'s translation carries its parent's scale (a
        compensated child of a helper bone)."""
        p = self.bones[k].parent
        return p >= 0 and p in self.helpers and self.bones[k].compensate


def _moving_scale(keys) -> bool:
    """Whether a scale track ever leaves 1: a key value, or a tangent that
    bends the curve between keys."""
    return any(k[1] != 1.0 or (math.isfinite(k[2]) and k[2] != 0.0) or (abs(k[3]) <= FLT_MAX and k[3] != 0.0)
               for k in keys)


def _check_clip(body: str, name: str, clip: Clip, nb: int) -> None:
    """Refuse (D35) a clip the export can't hold exactly: a bone track on
    no bone, two tracks on one component, a pre/post mode but 0, a time
    below 0 or out of order, or a key a CUBICSPLINE can't hold (a step, a
    tangent that isn't finite)."""
    seen = set()
    for tr in clip.bones:
        where = f"{body}/{name}: bone track {tr.target} component {tr.comp}"
        if not (0 <= tr.target < nb and 0 <= tr.comp <= 9) or (tr.target, tr.comp) in seen:
            raise ValueError(f"{where}: no such bone or component, or keyed twice")
        seen.add((tr.target, tr.comp))
        if tr.modes != (0, 0):
            raise ValueError(f"{where}: pre/post modes {tr.modes} (only 0, 0 export)")
        times = [k[0] for k in tr.keys]
        if not times or times[0] < 0 or any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError(f"{where}: its key times aren't increasing from 0")
        if not all(math.isfinite(k[0]) and math.isfinite(k[1]) for k in tr.keys) or \
                any(not abs(k[3]) <= FLT_MAX for k in tr.keys[:-1]) or any(not math.isfinite(k[2]) for k in tr.keys[1:]):
            raise ValueError(f"{where}: a stepped key or a tangent that isn't finite (no exact CUBICSPLINE)")


def _read(characters_xbr: bytes, body: str) -> _Body:
    """The body ``characters/<body>`` (case-blind) and all its clips."""
    index, _ = body_at(characters_xbr, body)
    toc, names = parse_toc(characters_xbr), named_resources(characters_xbr)
    name = names[index][len("characters/"):]
    bones = bone_records(characters_xbr, name)
    if not bones:
        raise ValueError(f"characters.xbr: body {name!r} has no bones")
    for k, b in enumerate(bones):
        if not -1 <= b.parent < k:
            raise ValueError(f"characters.xbr: body {name!r} bone {b.name!r} has parent {b.parent}")
    prefix = f"characters/{name}/".casefold()
    clips = []
    for i, n in sorted(names.items(), key=lambda item: item[1].casefold()):
        if n.casefold().startswith(prefix) and toc[i].tag == "banm":
            clip = read_clip(characters_xbr, toc[i].file_offset)
            _check_clip(name, n[len(prefix):], clip, len(bones))
            clips.append((n[len(prefix):], clip))
    return _Body(name, index, bones, inverse_binds(characters_xbr, name), tuple(clips), _helpers(bones, clips))


def _helpers(bones, clips) -> tuple[int, ...]:
    """The bones a child hangs from whose scale isn't 1 at rest or moves in
    a clip (each clip's scale tracks read once, not once a bone)."""
    kids = {b.parent for b in bones if b.parent >= 0}
    scaled = {tr.target for _, c in clips for tr in c.bones if 7 <= tr.comp <= 9 and _moving_scale(tr.keys)}
    return tuple(k for k in range(len(bones)) if k in kids and (any(c != 1.0 for c in bones[k].s) or k in scaled))


def _rest_trs(body: _Body, k: int) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """Bone ``k``'s node rest translation, rotation and scale (float64)."""
    b = body.bones[k]
    t = b.t if not body.folds(k) else tuple(x * s for x, s in zip(b.t, body.bones[b.parent].s))
    s = (1.0, 1.0, 1.0) if k in body.helpers else b.s
    return t, qnorm(qmul(qmul(b.jo, b.q), b.ra)), s


# --------------------------------------------------------------------------- channels
Channel = tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]   # times, values, in, out (rows: keys)


def _merge(curves: dict[int, tuple], rest: Sequence[float]) -> Channel:
    """Per-component curves as one vector channel at the union of their key
    times: each component's value and left and right slopes there (the
    rest value and 0 where it has no curve)."""
    times = sorted({k[0] for keys in curves.values() for k in keys})
    vals = np.tile(np.asarray(rest, float), (len(times), 1))
    ins, outs = np.zeros_like(vals), np.zeros_like(vals)
    for c, keys in curves.items():
        for i, u in enumerate(times):
            vals[i, c] = evaluate(keys, u)
            ins[i, c], outs[i, c] = _slopes(keys, u)
    return np.array(times, float), vals, ins, outs


def _hermite(ch: Channel, u: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A channel at ``u`` by glTF's CUBICSPLINE rule, with its slope just
    before and just after (held, slope 0, outside its keys)."""
    times, v, a, b = ch
    zero = np.zeros_like(v[0])
    if u <= times[0]:
        return v[0], zero, (b[0] if u == times[0] and len(times) > 1 else zero)
    if u >= times[-1]:
        return v[-1], (a[-1] if u == times[-1] else zero), zero
    i = int(np.searchsorted(times, u, side="right")) - 1
    if u == times[i]:
        return v[i], a[i], b[i]
    d = times[i + 1] - times[i]
    s = (u - times[i]) / d
    val = ((2 * fdlibm.cube(s) - 3 * fdlibm.sq(s) + 1) * v[i] + d * (fdlibm.cube(s) - 2 * fdlibm.sq(s) + s) * b[i]
           + (-2 * fdlibm.cube(s) + 3 * fdlibm.sq(s)) * v[i + 1] + d * (fdlibm.cube(s) - fdlibm.sq(s)) * a[i + 1])
    der = ((6 * fdlibm.sq(s) - 6 * s) * v[i] + d * (3 * fdlibm.sq(s) - 4 * s + 1) * b[i]
           + (-6 * fdlibm.sq(s) + 6 * s) * v[i + 1] + d * (3 * fdlibm.sq(s) - 2 * s) * a[i + 1]) / d
    return val, der, der


def _product(sp: Channel, tc: Channel) -> Channel:
    """The product of two channels, sampled at :data:`SAMPLE_HZ` (float32
    times) plus both key sets, with product-rule slopes."""
    keys = set(sp[0]) | set(tc[0])
    lo, hi = min(keys), max(keys)
    grid = keys | {float(np.float32(lo + i / SAMPLE_HZ)) for i in range(int((hi - lo) * SAMPLE_HZ) + 1)}
    vals, ins, outs = [], [], []
    times = sorted(u for u in grid if lo <= u <= hi)
    for u in times:
        s, sa, sb = _hermite(sp, u)
        t, ta, tb = _hermite(tc, u)
        vals.append(s * t)
        ins.append(sa * t + s * ta)
        outs.append(sb * t + s * tb)
    return np.array(times), np.array(vals), np.array(ins), np.array(outs)


def _scaled(ch: Channel, by) -> Channel:
    by = np.asarray(by, float)
    return ch[0], ch[1] * by, ch[2] * by, ch[3] * by


def _channels(body: _Body, clip: Clip) -> tuple[list[tuple[int, str, Channel]], int, int]:
    """``clip``'s glTF channels, (node, path, channel) in bone order
    (translation, rotation, scale), and how many translations are derived
    from a parent's scale and how many of them sampled."""
    by: dict[int, dict[int, tuple]] = {}
    for tr in clip.bones:
        by.setdefault(tr.target, {})[tr.comp] = tr.keys
    out, derived, sampled = [], 0, 0
    for k, b in enumerate(body.bones):
        comps = by.get(k, {})
        tcur = {c: comps[c] for c in (0, 1, 2) if c in comps}
        qcur = {c - 3: comps[c] for c in (3, 4, 5, 6) if c in comps}
        scur = {c - 7: comps[c] for c in (7, 8, 9) if c in comps}
        pcur = {c - 7: by.get(b.parent, {})[c] for c in (7, 8, 9) if body.folds(k) and c in by.get(b.parent, {})}
        if tcur and not body.folds(k):
            out.append((k, "translation", _merge(tcur, b.t)))
        elif tcur and not pcur:
            out.append((k, "translation", _scaled(_merge(tcur, b.t), body.bones[b.parent].s)))
        elif pcur and not tcur:
            out.append((k, "translation", _scaled(_merge(pcur, body.bones[b.parent].s), b.t)))
            derived += 1
        elif pcur:
            out.append((k, "translation", _product(_merge(pcur, body.bones[b.parent].s), _merge(tcur, b.t))))
            derived, sampled = derived + 1, sampled + 1
        if qcur:
            m = np.array(_linear(b.jo, b.ra))
            times, v, a, o = _merge(qcur, b.q)
            out.append((k, "rotation", (times, v @ m.T, a @ m.T, o @ m.T)))
        if scur:
            out.append((body.joint(k), "scale", _merge(scur, b.s)))
    return out, derived, sampled


def _expected_channels(body: _Body, clip: Clip) -> int:
    """C5: the keyed (bone, T | R | S) groups plus the translations a
    parent's scale derives."""
    keyed = {(t, 0 if c < 3 else 1 if c < 7 else 2) for t, c in ((tr.target, tr.comp) for tr in clip.bones)}
    scaled = {tr.target for tr in clip.bones if 7 <= tr.comp <= 9}
    derived = sum(1 for k, b in enumerate(body.bones)
                  if body.folds(k) and b.parent in scaled and (k, 0) not in keyed)
    return len(keyed) + derived


# --------------------------------------------------------------------------- the engine model
def _rot(q) -> np.ndarray:
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _trs(t, q, s) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = _rot(q) * np.asarray(s, float)[None, :]
    m[:3, 3] = t
    return m


ROOT = _trs((0.0, 0.0, 0.0), ROOT_ROTATION, (1.0, 1.0, 1.0))


def _engine(body: _Body, clip: Clip | None, t: float) -> list[np.ndarray]:
    """Each bone's skinning world (model frame) when ``clip`` plays at
    ``t`` (``None``: the rest pose): its local rotation JO x q x RA, and a
    compensated child's translation times its parent's scale under the
    parent's world without that scale."""
    keyed: dict[tuple[int, int], tuple] = {(tr.target, tr.comp): tr.keys for tr in clip.bones} if clip else {}

    def value(k, first, rest):
        return [evaluate(keyed[k, first + i], t) if (k, first + i) in keyed else rest[i] for i in range(len(rest))]

    unscaled, world = [], []
    for k, b in enumerate(body.bones):
        tt, q, s = value(k, 0, b.t), qnorm(value(k, 3, b.q)), value(k, 7, b.s)
        local = _trs(tt, qnorm(qmul(qmul(b.jo, q), b.ra)), (1.0, 1.0, 1.0))
        if b.parent >= 0 and b.compensate:
            local[:3, 3] *= value(b.parent, 7, body.bones[b.parent].s)
            local = unscaled[b.parent] @ local
        elif b.parent >= 0:
            local = world[b.parent] @ local
        unscaled.append(local)
        world.append(local @ np.diag([*s, 1.0]))
    return world


# --------------------------------------------------------------------------- the mesh
@dataclass
class _Group:
    """One LOD-0 group as the export writes it."""

    index: int
    positions: np.ndarray     # (n, 3) float32, as stored
    uvs: np.ndarray           # (n, 2) float32, as stored
    normals: np.ndarray       # (n, 3) float32, unit
    joints: np.ndarray        # (n, 4) node indices
    weights: np.ndarray       # (n, 4) float32
    triangles: np.ndarray     # (m, 3)
    material: tuple[int, int]
    merged: int
    replaced: int


def _groups(characters_xbr: bytes, toc, body: _Body) -> list[_Group]:
    """Body's LOD-0 groups: the +56 slot bytes decoded through each
    group's palette (D35: a live weight on a byte or entry outside it
    refuses the body), duplicates merged, zero normals replaced."""
    meshes = render.body_meshes(characters_xbr, toc, body.index)
    groups = [g for g in mesh_groups(characters_xbr, body.name) if g.lod == 0]
    if len(meshes) != len(groups) or not groups:
        raise ValueError(f"characters.xbr: body {body.name!r}: {len(groups)} LOD-0 groups, {len(meshes)} meshes")
    out = []
    for g, me in zip(groups, meshes):
        raw = np.frombuffer(characters_xbr, np.uint8, 60 * g.count, g.vertices).reshape(g.count, 60)
        pos, w = raw[:, 0:12].copy().view("<f4"), raw[:, 12:28].copy().view("<f4")
        nrm, uv = raw[:, 28:40].copy().view("<f4").astype(float), raw[:, 40:48].copy().view("<f4")
        slots = raw[:, 56:60].astype(int)
        where = f"{body.name} group {g.index}"
        if not (np.isfinite(pos).all() and np.isfinite(w).all() and np.isfinite(uv).all()) or (w < 0).any():
            raise ValueError(f"{where}: a position, UV or weight isn't finite, or a weight is negative")
        live = w > 0
        entry = np.where(slots <= 12, slots - 1, slots - 2)
        bad = live & ((slots == 0) | (slots == 13) | (slots > 32) | (entry >= len(g.bones)))
        if bad.any():
            v = int(np.argwhere(bad)[0][0])
            raise ValueError(f"{where} vertex {v}: a weight's slot byte is outside the group's "
                             f"{len(g.bones)}-bone palette")
        if any(not 0 <= p < len(body.bones) for p in g.bones):
            raise ValueError(f"{where}: its palette names a bone the body hasn't")
        palette = np.array(g.bones or (0,))
        bones = np.where(live, palette[np.clip(entry, 0, len(palette) - 1)], -1)
        joints = np.array([[body.joint(k) if k >= 0 else 0 for k in row] for row in bones], np.int64).reshape(-1, 4)
        weights = np.where(live, w, 0).astype(np.float32)
        merged = 0
        pairs = [(i, j) for i in range(4) for j in range(i + 1, 4)]
        twice = np.any([live[:, i] & live[:, j] & (joints[:, i] == joints[:, j]) for i, j in pairs], 0)
        for v in np.flatnonzero(twice):
            for i in range(4):
                for j in range(i + 1, 4):
                    if weights[v, i] > 0 and weights[v, j] > 0 and joints[v, i] == joints[v, j]:
                        weights[v, i] += weights[v, j]
                        weights[v, j], joints[v, j] = 0, 0
                        merged += 1
        tri = me.triangles.astype(np.int64)
        length = np.linalg.norm(nrm, axis=1)
        zero = ~(length >= 0.5)
        if zero.any():
            p = pos.astype(float)
            face = np.cross(p[tri[:, 1]] - p[tri[:, 0]], p[tri[:, 2]] - p[tri[:, 0]])
            acc = np.zeros_like(p)
            for c in range(3):
                np.add.at(acc, tri[:, c], face)
            fix = np.linalg.norm(acc, axis=1)
            nrm[zero] = np.where(fix[zero, None] > 0, acc[zero] / np.maximum(fix[zero, None], 1e-30), (0.0, 0.0, 1.0))
            length[zero] = 1.0
        out.append(_Group(g.index, pos, uv, (nrm / length[:, None]).astype(np.float32), joints, weights, tri,
                          (me.gshd, me.row), merged, int(zero.sum())))
    return out


# --------------------------------------------------------------------------- writing
class _Writer:
    """One buffer: one 4-byte aligned view per accessor (Level Studio's
    ``write_gltf`` layout), identical sampler inputs shared."""

    def __init__(self) -> None:
        self.bin = bytearray()
        self.views: list[dict] = []
        self.accessors: list[dict] = []
        self._shared: dict[bytes, int] = {}

    def add(self, values: np.ndarray, kind: str, component: int, target: int | None = None,
            bounds: bool = False, share: bool = False) -> int:
        a = np.ascontiguousarray(values, dtype=_COMPONENTS[component])
        blob = a.tobytes()
        if share and blob in self._shared:
            return self._shared[blob]
        if component == _FLOAT and not np.isfinite(a).all():
            raise ValueError("a glTF float isn't finite")
        self.bin.extend(b"\0" * (-len(self.bin) % 4))
        view = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(blob)}
        if target:
            view["target"] = target
        self.bin.extend(blob)
        self.views.append(view)
        width = _WIDTHS[kind]
        acc = {"bufferView": len(self.views) - 1, "componentType": component, "count": a.size // width, "type": kind}
        if bounds:
            rows = a.reshape(-1, width)
            acc["min"], acc["max"] = [x.item() for x in rows.min(0)], [x.item() for x in rows.max(0)]
        self.accessors.append(acc)
        if share:
            self._shared[blob] = len(self.accessors) - 1
        return len(self.accessors) - 1


def _f32(values) -> list[float]:
    return [float(np.float32(v)) for v in values]


def _surf_frames(characters_xbr: bytes, toc, index: int) -> int:
    """An animated ``surf`` list's frame count, else 1."""
    kind, count = struct.unpack_from("<II", characters_xbr, toc[index].file_offset)
    return count if kind == 1 else 1


@dataclass(frozen=True)
class Export:
    """What :func:`export_body` wrote: the files, the layout's counts and
    the checks' numbers (:class:`CheckReport`)."""

    gltf: Path
    body: str
    groups: int
    vertices: int
    triangles: int
    bones: int
    helpers: int
    materials: int
    textures: int
    clips: int
    channels: int
    derived: int
    sampled: int
    skipped: tuple[str, ...]
    merged: int
    replaced: int
    checks: CheckReport


def _document(characters_xbr: bytes, body: _Body, clips: Sequence[tuple[str, Clip]], source_vanilla: bool
              ) -> tuple[dict, bytes, dict[str, bytes], dict]:
    """The glTF JSON, its buffer, its PNGs by name and the layout's counts."""
    toc = parse_toc(characters_xbr)
    slug, nb = body.slug, len(body.bones)
    w = _Writer()
    groups = _groups(characters_xbr, toc, body)

    nodes = []
    for k, b in enumerate(body.bones):
        t, r, s = _rest_trs(body, k)
        node = {"name": b.name, "translation": _f32(t), "rotation": _f32(r), "scale": _f32(s),
                "extras": {"bone": k, "compensate": b.compensate}}
        kids = [c for c, cb in enumerate(body.bones) if cb.parent == k and (k not in body.helpers or cb.compensate)]
        if k in body.helpers:
            kids.append(body.helper(k))
        if kids:
            node["children"] = kids
        nodes.append(node)
    for k in body.helpers:
        node = {"name": body.bones[k].name + HELPER, "scale": _f32(body.bones[k].s), "extras": {"helper_of": k}}
        kids = [c for c, cb in enumerate(body.bones) if cb.parent == k and not cb.compensate]
        if kids:
            node["children"] = kids
        nodes.append(node)
    root, mesh_node = len(nodes), len(nodes) + 1

    # materials and textures
    materials, images, files, by_key, by_surf = [], [], {}, {}, {}
    for g in groups:
        if g.material in by_key:
            continue
        mt = render.material(characters_xbr, toc, *g.material)
        name = f"{slug}_row{g.material[1]}"
        if any(m["name"] == name for m in materials):
            name = f"{slug}_gshd{g.material[0]}_row{g.material[1]}"
        opacity = mt.get("opacity", 1.0)
        mat = {"name": name, "pbrMetallicRoughness": {
            "baseColorFactor": [1.0, 1.0, 1.0, min(max(opacity, 0.0), 1.0) if math.isfinite(opacity) else 1.0],
            "metallicFactor": 0.0, "roughnessFactor": 1.0}, "doubleSided": True}
        if mt.get("blend", 500) != 500:
            mat["alphaMode"] = "BLEND"
        elif not mt.get("flags", 0) & 0x10 and mt.get("alpha_ref", 0.0) > 0:
            mat["alphaMode"], mat["alphaCutoff"] = "MASK", min(float(mt["alpha_ref"]), 1.0)
        stages = []
        for s in mt.get("textures", []):
            fname = f"{slug}_surf{s}.png"
            if fname not in files:
                files[fname] = png_rgba(render.surf_image(characters_xbr, toc, s))
            stages.append({"surf": s, "file": fname, "frames": _surf_frames(characters_xbr, toc, s)})
        if stages:
            first = stages[0]["surf"]
            if first not in by_surf:
                by_surf[first] = len(images)
                images.append({"name": f"{slug}_surf{first}", "uri": stages[0]["file"]})
            mat["pbrMetallicRoughness"]["baseColorTexture"] = {"index": by_surf[first]}
        mat["extras"] = {"azurik": {"gshd": g.material[0], "row": g.material[1],
                                    **{k: v for k, v in mt.items() if k != "textures"}, "stages": stages}}
        by_key[g.material] = len(materials)
        materials.append(mat)

    primitives = []
    for g in groups:
        if not len(g.triangles):
            continue
        n = len(g.positions)
        vid = np.stack([np.full(n, g.index, np.float32), np.arange(n, dtype=np.float32)], 1)
        attributes = {
            "POSITION": w.add(g.positions, "VEC3", _FLOAT, 34962, bounds=True),
            "NORMAL": w.add(g.normals, "VEC3", _FLOAT, 34962),
            "TEXCOORD_0": w.add(g.uvs, "VEC2", _FLOAT, 34962),
            "JOINTS_0": w.add(g.joints, "VEC4", _UBYTE if body.nodes <= 256 else _USHORT, 34962),
            "WEIGHTS_0": w.add(g.weights, "VEC4", _FLOAT, 34962),
            "_AZ_VID": w.add(vid, "VEC2", _FLOAT, 34962),
            "TEXCOORD_1": w.add(vid, "VEC2", _FLOAT, 34962),
        }
        index_type = _USHORT if n < 0xFFFF else _UINT
        primitives.append({"attributes": attributes, "indices": w.add(g.triangles.ravel(), "SCALAR", index_type, 34963),
                           "material": by_key[g.material], "mode": 4, "extras": {"group": g.index}})

    binds = np.array([body.binds[k] for k in range(nb)] + [body.binds[k] for k in body.helpers], np.float32)
    skin = {"name": slug, "joints": list(range(body.nodes)), "skeleton": root,
            "inverseBindMatrices": w.add(binds, "MAT4", _FLOAT)}

    animations, channels, derived, sampled, skipped = [], 0, 0, 0, []
    for name, clip in clips:
        chans, d, s = _channels(body, clip)
        if not chans:
            skipped.append(name)
            continue
        derived, sampled, channels = derived + d, sampled + s, channels + len(chans)
        anim = {"name": name, "channels": [], "samplers": [],
                "extras": {"length": clip.length, "marker_tracks": len(clip.markers)}}
        for node, path, (times, v, a, o) in chans:
            if len(times) == 1:     # a constant: CUBICSPLINE wants two keys
                times, v, a, o = (np.array([times[0], times[0] + 1 / SAMPLE_HZ]), np.repeat(v, 2, 0),
                                  np.zeros((2, v.shape[1])), np.zeros((2, v.shape[1])))
            kind = {3: "VEC3", 4: "VEC4"}[v.shape[1]]
            anim["samplers"].append({
                "input": w.add(np.asarray(times, np.float32), "SCALAR", _FLOAT, bounds=True, share=True),
                "interpolation": "CUBICSPLINE",
                "output": w.add(np.stack([a, v, o], 1).reshape(-1, v.shape[1]), kind, _FLOAT)})
            anim["channels"].append({"sampler": len(anim["samplers"]) - 1, "target": {"node": node, "path": path}})
        animations.append(anim)

    nodes.append({"name": slug, "rotation": list(ROOT_ROTATION),
                  "children": [k for k, b in enumerate(body.bones) if b.parent < 0],
                  "extras": {"azurik": {
                      "body": body.name, "toc": body.index, "version": VERSION,
                      "characters_sha256": hashlib.sha256(characters_xbr).hexdigest()[:12], "vanilla": source_vanilla,
                      "lod": f"0 of {len({g.lod for g in mesh_groups(characters_xbr, body.name)})}",
                      "units": "metres; the model's frame: x right, y forward, z up",
                      "conversion": "root X -90 degrees (z up to y up)", "vid": "_AZ_VID and TEXCOORD_1 = (group, index)",
                      "helpers": {nodes[body.helper(k)]["name"]: body.bones[k].name for k in body.helpers},
                      "skipped_clips": skipped, "merged_joints": sum(g.merged for g in groups),
                      "replaced_normals": sum(g.replaced for g in groups)}}})
    nodes.append({"name": f"{slug}_mesh", "mesh": 0, "skin": 0})
    doc = {"asset": {"version": "2.0", "generator": GENERATOR}, "scene": 0,
           "scenes": [{"name": slug, "nodes": [root, mesh_node]}], "nodes": nodes,
           "meshes": [{"name": slug, "primitives": primitives}], "skins": [skin], "materials": materials}
    if images:
        doc["samplers"] = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]
        doc["images"] = images
        doc["textures"] = [{"sampler": 0, "source": i} for i in range(len(images))]
    if animations:
        doc["animations"] = animations
    doc["accessors"], doc["bufferViews"] = w.accessors, w.views
    doc["buffers"] = [{"uri": f"{slug}.bin", "byteLength": len(w.bin)}]
    counts = {"groups": len(primitives), "vertices": sum(len(g.positions) for g in groups),
              "triangles": sum(len(g.triangles) for g in groups), "materials": len(materials),
              "textures": len(files), "clips": len(animations), "channels": channels, "derived": derived,
              "sampled": sampled, "skipped": tuple(skipped), "merged": sum(g.merged for g in groups),
              "replaced": sum(g.replaced for g in groups)}
    return doc, bytes(w.bin), files, counts


def _refuse_out(out: Path, protect: Sequence[Path]) -> None:
    """D36: ``out`` must be a new or empty folder that is none of ``protect``
    (the inputs read) and inside none of them (its caller keeps it outside a
    checkout and the images' folders: exported files are game assets)."""
    real = out.resolve()
    for p in map(Path, protect):
        if p.exists() and real.exists() and real.samefile(p):
            raise ValueError(f"--out {out} is the same file as {p}, which it reads")
        if p.is_dir() and (real == p.resolve() or p.resolve() in real.parents):
            raise ValueError(f"--out {out} is inside {p}, which it reads")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"--out {out} already holds something; give a new or empty folder")


def export_body(characters_xbr: bytes, body: str, out: Path, clips: Sequence[str] | None = None, *,
                source_vanilla: bool = True, protect: Sequence[Path] = ()) -> Export:
    """Write the body ``characters/<body>`` (case-blind) into the new or
    empty folder ``out`` as ``<slug>.gltf``, ``<slug>.bin`` and its PNGs,
    with ``clips`` (by name; every clip by default), then check the
    written files (:func:`check_export`) and only then move them into
    ``out``: a refusal or failed check writes nothing and raises
    :class:`ValueError` naming it (D35).  ``protect``: inputs ``out`` may
    not be or sit in (the ISO read)."""
    out = Path(out).absolute()
    _refuse_out(out, protect)
    info = _read(characters_xbr, body)
    names = [n for n, _ in info.clips]
    if clips is None:
        chosen = list(info.clips)
    else:
        folded = {n.casefold(): i for i, n in enumerate(names)}
        unknown = [c for c in clips if c.casefold() not in folded]
        if unknown:
            raise ValueError(f"{info.name} has no clip {', '.join(map(repr, unknown))} (it has {len(names)})")
        chosen = [info.clips[i] for i in dict.fromkeys(folded[c.casefold()] for c in clips)]
    doc, blob, files, counts = _document(characters_xbr, info, chosen, source_vanilla)
    out.parent.mkdir(parents=True, exist_ok=True)
    part = Path(tempfile.mkdtemp(prefix=f".{out.name}.part-", dir=out.parent))
    try:
        gltf = part / f"{info.slug}.gltf"
        gltf.write_text(json.dumps(doc, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        (part / f"{info.slug}.bin").write_bytes(blob)
        for name, data in files.items():
            (part / name).write_bytes(data)
        report = check_export(gltf, characters_xbr, info.name, [n for n, _ in chosen])
        if out.exists():
            out.rmdir()
        part.rename(out)
    except BaseException:
        shutil.rmtree(part, ignore_errors=True)
        raise
    return Export(gltf=out / gltf.name, body=info.name, bones=len(info.bones), helpers=len(info.helpers),
                  checks=report, **counts)


# --------------------------------------------------------------------------- reading back
def _read_png(data: bytes) -> np.ndarray:
    """One of our own PNGs (8-bit RGBA, one zlib stream, filter 0 rows) as
    (h, w, 4) uint8."""
    if data[:8] != (b"\x89PNG" + "\r\n\x1a\n".encode("latin-1")):
        raise ValueError("not a PNG")
    at, idat, head = 8, bytearray(), None   # grown in place: bytes += copies all before it
    while at < len(data):
        n, tag = struct.unpack_from(">I4s", data, at)
        chunk = data[at + 8:at + 8 + n]
        if zlib.crc32(tag + chunk) & 0xFFFFFFFF != struct.unpack_from(">I", data, at + 8 + n)[0]:
            raise ValueError(f"PNG chunk {tag!r}: bad CRC")
        if tag == b"IHDR":
            head = struct.unpack(">IIBBBBB", chunk)
        elif tag == b"IDAT":
            idat += chunk
        at += 12 + n
    if head is None or head[2:] != (8, 6, 0, 0, 0):
        raise ValueError("PNG isn't 8-bit RGBA, uninterlaced")
    w, h = head[:2]
    rows = np.frombuffer(inflate.png_rows(idat, w, h, 4), np.uint8).reshape(h, 1 + 4 * w)
    if rows[:, 0].any():
        raise ValueError("PNG row filter isn't 0")
    return rows[:, 1:].reshape(h, w, 4)


def _structure(gltf: Path) -> tuple[dict, list[np.ndarray]]:
    """C8 (Level Studio's ``validate_gltf``, plus the skin's and the
    animations' rules): the document and each accessor's values; raises
    naming the first rule broken."""
    doc = json.loads(gltf.read_text(encoding="utf-8"))

    def need(ok: bool, why: str) -> None:
        if not ok:
            raise ValueError(f"C8 structure: {why}")

    def local(uri) -> Path:
        need(isinstance(uri, str) and "/" not in uri and "\\" not in uri and ":" not in uri, f"URI {uri!r} isn't local")
        need((gltf.parent / uri).is_file(), f"{uri} is missing")
        return gltf.parent / uri

    need(doc.get("asset", {}).get("version") == "2.0", "not glTF 2.0")
    buffers = [local(b["uri"]).read_bytes() for b in doc["buffers"]]
    need(all(len(d) == b["byteLength"] for d, b in zip(buffers, doc["buffers"])), "a buffer's length")
    values = []
    for i, acc in enumerate(doc["accessors"]):
        view = doc["bufferViews"][acc["bufferView"]]
        dtype, width = np.dtype(_COMPONENTS[acc["componentType"]]), _WIDTHS[acc["type"]]
        start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        length = acc["count"] * width * dtype.itemsize
        need(acc["count"] > 0 and "byteStride" not in view and view.get("byteOffset", 0) % 4 == 0
             and start % dtype.itemsize == 0 and acc.get("byteOffset", 0) + length <= view["byteLength"]
             and view.get("byteOffset", 0) + view["byteLength"] <= len(buffers[view["buffer"]]),
             f"accessor {i} outside its view or misaligned")
        a = np.frombuffer(buffers[view["buffer"]], dtype, acc["count"] * width, start).reshape(acc["count"], width)
        need(dtype.kind != "f" or bool(np.isfinite(a).all()), f"accessor {i} holds a float that isn't finite")
        for key, fn in (("min", np.min), ("max", np.max)):
            if key in acc:
                need(list(fn(a, 0)) == acc[key], f"accessor {i}'s {key} isn't its data's")
        values.append(a)
    for im in doc.get("images", []):
        need(local(im["uri"]).suffix == ".png", f"image {im['uri']} isn't a PNG")
    need(all(0 <= t["source"] < len(doc.get("images", [])) for t in doc.get("textures", [])), "a texture's image")
    for m in doc["materials"]:
        tex = m.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        need(not tex or 0 <= tex["index"] < len(doc.get("textures", [])), f"material {m['name']}'s texture")
    for p in (p for mesh in doc["meshes"] for p in mesh["primitives"]):
        pos = doc["accessors"][p["attributes"]["POSITION"]]
        need(p.get("mode", 4) == 4 and pos["type"] == "VEC3" and pos["componentType"] == _FLOAT
             and "min" in pos and "max" in pos, "a primitive's mode or POSITION")
        need(all(doc["accessors"][a]["count"] == pos["count"] for a in p["attributes"].values()),
             "a primitive's attribute counts differ")
        n = values[p["attributes"]["NORMAL"]]
        need(bool(np.all(np.abs(np.linalg.norm(n.astype(float), axis=1) - 1) <= 1e-6)), "a normal isn't unit")
        idx = values[p["indices"]]
        need(len(idx) % 3 == 0 and int(idx.max()) < pos["count"], "an index past its primitive's vertices")
        need(0 <= p["material"] < len(doc["materials"]), "a primitive's material")
    parents: dict[int, int] = {}
    for i, node in enumerate(doc["nodes"]):
        for c in node.get("children", []):
            need(0 <= c < len(doc["nodes"]) and c not in parents, f"node {c} has two parents or doesn't exist")
            parents[c] = i
        if "rotation" in node:
            need(abs(math.hypot(*node["rotation"]) - 1) <= 1e-6, f"node {node['name']}'s rotation isn't unit")
    seen, stack = set(), list(doc["scenes"][doc["scene"]]["nodes"])
    need(all(r not in parents for r in stack), "a scene root has a parent")
    while stack:
        i = stack.pop()
        need(i not in seen, f"node {i} is reached twice")
        seen.add(i)
        stack += doc["nodes"][i].get("children", [])
    need(len(seen) == len(doc["nodes"]), "a node isn't reachable from the scene")
    for skin in doc["skins"]:
        need(len(set(skin["joints"])) == len(skin["joints"]) == doc["accessors"][skin["inverseBindMatrices"]]["count"],
             "the skin's joints repeat or don't match its inverse binds")
    for i, node in enumerate(doc["nodes"]):
        if "skin" in node:
            need("mesh" in node and i not in parents, "the skinned mesh node isn't a scene root")
    for anim in doc.get("animations", []):
        targets = [(c["target"]["node"], c["target"]["path"]) for c in anim["channels"]]
        need(bool(targets) and len(set(targets)) == len(targets), f"animation {anim['name']} repeats a target")
        for c in anim["channels"]:
            s = anim["samplers"][c["sampler"]]
            times, out = values[s["input"]][:, 0], values[s["output"]]
            need(s["interpolation"] == "CUBICSPLINE" and len(times) >= 2 and times[0] >= 0
                 and bool(np.all(np.diff(times) > 0)) and "min" in doc["accessors"][s["input"]]
                 and len(out) == 3 * len(times) and out.shape[1] == _PATHS[c["target"]["path"]],
                 f"animation {anim['name']}'s sampler {c['sampler']}")
    return doc, values


@dataclass(frozen=True)
class CheckReport:
    """:func:`check_export`'s numbers: the rest pose's largest distance
    from the engine model's (m) and the engine's own from the file's
    positions (a rest scale's, Balthazar's pecs: not a failure), the
    weights' largest distance from summing to 1, and over every clip's
    checked poses the largest matrix entry, position (m) and rotation
    (degrees) off the engine's, with where; the clips, channels and PNGs
    checked."""

    rest_m: float
    rest_offset_m: float
    weight_sum: float
    clip_matrix: float
    clip_pos_m: float
    clip_rot_deg: float
    worst_clip: str
    clips: int
    channels: int
    textures: int


def _sampler(doc: dict, values: list[np.ndarray], s: dict) -> Channel:
    times = values[s["input"]][:, 0].astype(float)
    out = values[s["output"]].astype(float).reshape(len(times), 3, -1)
    return times, out[:, 1], out[:, 0], out[:, 2]


def _worlds(doc: dict, locals_: list[np.ndarray]) -> list[np.ndarray]:
    """Every node's world matrix from its local one (parents first)."""
    world: list[np.ndarray | None] = [None] * len(doc["nodes"])
    stack = [(r, np.eye(4)) for r in doc["scenes"][doc["scene"]]["nodes"]]
    while stack:
        i, parent = stack.pop()
        world[i] = parent @ locals_[i]
        stack += [(c, world[i]) for c in doc["nodes"][i].get("children", [])]
    return world


def _locals(doc: dict, live: dict[int, dict[str, np.ndarray]] | None = None) -> list[np.ndarray]:
    """Every node's local matrix: its TRS, ``live``'s values where a
    channel sets them (the rotation normalised, as glTF has it)."""
    out = []
    for i, node in enumerate(doc["nodes"]):
        got = (live or {}).get(i, {})
        r = np.asarray(got.get("rotation", node.get("rotation", (0, 0, 0, 1))), float)
        out.append(_trs(got.get("translation", node.get("translation", (0, 0, 0))), r / np.linalg.norm(r),
                        got.get("scale", node.get("scale", (1, 1, 1)))))
    return out


def check_export(gltf: Path, characters_xbr: bytes, body: str, clips: Sequence[str] | None = None) -> CheckReport:
    """C1-C8 (the module docstring) on the written ``gltf`` against the
    body ``characters/<body>`` and its ``clips`` (every clip by default);
    :class:`ValueError` naming the check, the body and the worst vertex,
    joint or clip on the first that fails."""
    doc, values = _structure(gltf)
    info = _read(characters_xbr, body)
    toc = parse_toc(characters_xbr)
    nb = len(info.bones)
    joints = doc["skins"][0]["joints"]
    ibm = values[doc["skins"][0]["inverseBindMatrices"]].astype(float).reshape(-1, 4, 4).transpose(0, 2, 1)
    source_ibm = [np.array(m, np.float32).astype(float).reshape(4, 4).T for m in info.binds]

    def fail(check: str, why: str) -> None:
        raise ValueError(f"{check} {info.name}: {why}")

    if len(joints) != info.nodes or doc["nodes"][doc["skins"][0]["skeleton"]].get("rotation") != list(ROOT_ROTATION):
        fail("C8", "the joints or the root's rotation aren't the layout's")
    if any(not np.array_equal(ibm[j], source_ibm[k])
           for j, k in enumerate(list(range(nb)) + list(info.helpers))):
        fail("C1", "an inverse bind isn't the bone record's")

    # C1-C4 and C2: the mesh, its skin and the rest pose
    groups = {g.index: g for g in mesh_groups(characters_xbr, info.name) if g.lod == 0}
    drawn = {g: me.triangles for g, me in zip(groups, render.body_meshes(characters_xbr, toc, info.index))
             if len(me.triangles)}
    if [p["extras"]["group"] for p in doc["meshes"][0]["primitives"]] != list(drawn):
        fail("C1", "the primitives aren't the LOD-0 groups that draw triangles")
    rest_world = _worlds(doc, _locals(doc))
    skin = np.array([rest_world[joints[j]] @ ibm[j] for j in range(len(joints))])
    engine = _engine(info, None, 0.0)
    engine_skin = np.array([ROOT @ engine[k] @ source_ibm[k] for k in range(nb)])
    rest_m = rest_offset_m = weight_sum = 0.0
    for p in doc["meshes"][0]["primitives"]:
        a = p["attributes"]
        vid = values[a["_AZ_VID"]].astype(np.int64)
        g = groups.get(int(vid[0, 0]))
        if g is None or not (vid[:, 0] == g.index).all() or not np.array_equal(vid[:, 1], np.arange(g.count)) \
                or not np.array_equal(values[a["TEXCOORD_1"]], values[a["_AZ_VID"]]):
            fail("C1", f"primitive {p['extras']} isn't one group's vertices in order")
        raw = np.frombuffer(characters_xbr, np.uint8, 60 * g.count, g.vertices).reshape(g.count, 60)
        pos, uv = values[a["POSITION"]], values[a["TEXCOORD_0"]]
        if pos.tobytes() != raw[:, 0:12].tobytes() or uv.tobytes() != raw[:, 40:48].tobytes() or \
                not np.array_equal(values[p["indices"]].reshape(-1, 3), drawn[g.index]):
            fail("C1", f"group {g.index}'s positions, UVs or triangles aren't the source's")
        nrm, src = values[a["NORMAL"]].astype(float), raw[:, 28:40].copy().view("<f4").astype(float)
        keep = np.linalg.norm(src, axis=1) >= 0.5
        cos = np.where(keep, (nrm * src).sum(1) / np.maximum(np.linalg.norm(src, axis=1), 1e-30), 1.0)
        if cos.min() < fdlibm.cos(math.radians(0.1)):
            fail("C1", f"group {g.index} vertex {int(np.argmin(cos))}'s normal is off the source's")
        jw, ww = values[a["JOINTS_0"]].astype(np.int64), values[a["WEIGHTS_0"]].astype(float)
        sw = raw[:, 12:28].copy().view("<f4").astype(float)
        slots = raw[:, 56:60].astype(np.int64)
        entry = np.where(slots <= 12, slots - 1, slots - 2)
        live = sw > 0
        allowed = {info.joint(b) for b in g.bones}
        for v in range(g.count):
            mine, theirs = {}, {}
            for i in range(4):
                if ww[v, i] < 0:
                    fail("C3", f"group {g.index} vertex {v} has a negative weight")
                if ww[v, i] > 0:
                    if jw[v, i] in mine:
                        fail("C3", f"group {g.index} vertex {v} names joint {jw[v, i]} twice")
                    if jw[v, i] not in allowed:
                        fail("C4", f"group {g.index} vertex {v}'s joint {jw[v, i]} isn't in its palette")
                    mine[jw[v, i]] = ww[v, i]
                if live[v, i]:
                    j = info.joint(g.bones[entry[v, i]])
                    theirs[j] = theirs.get(j, 0.0) + sw[v, i]
            if mine.keys() != theirs.keys() or any(abs(mine[j] - theirs[j]) > 1e-7 for j in mine):
                fail("C1", f"group {g.index} vertex {v}'s skin isn't the source's")
        weight_sum = max(weight_sum, float(np.abs(ww.sum(1) - 1).max()))
        if weight_sum > TOLERANCE:
            fail("C3", f"group {g.index}'s weights sum {weight_sum:.1e} off 1")
        p4 = np.concatenate([pos.astype(float), np.ones((g.count, 1))], 1)
        got = np.einsum("vi,vixy,vy->vx", ww, skin[jw], p4)[:, :3]
        bones = np.where(live, np.array(g.bones or (0,))[np.clip(entry, 0, max(len(g.bones) - 1, 0))], 0)
        want = np.einsum("vi,vixy,vy->vx", np.where(live, sw, 0), engine_skin[bones], p4)[:, :3]
        d = np.linalg.norm(got - want, axis=1)
        rest_m = max(rest_m, float(d.max()))
        if rest_m > TOLERANCE:
            fail("C2", f"group {g.index} vertex {int(np.argmax(d))} sits {rest_m:.1e} m off the engine's rest pose")
        model = (ROOT.T @ np.concatenate([want, np.ones((g.count, 1))], 1).T).T[:, :3]
        rest_offset_m = max(rest_offset_m, float(np.linalg.norm(model - pos, axis=1).max()))

    # C5 and C6: the clips
    wanted = [n for n, _ in info.clips] if clips is None else list(clips)
    by_name = dict(info.clips)
    played = [n for n in wanted if by_name[n].bones]
    anims = doc.get("animations", [])
    if [a["name"] for a in anims] != played:
        fail("C5", f"{len(anims)} animations, the clips with a bone track are {len(played)}")
    clip_m = clip_pos = clip_deg = 0.0
    where, channels = "", 0
    for anim in anims:
        clip = by_name[anim["name"]]
        if len(anim["channels"]) != _expected_channels(info, clip):
            fail("C5", f"{anim['name']} has {len(anim['channels'])} channels, not {_expected_channels(info, clip)}")
        channels += len(anim["channels"])
        decoded = [(c["target"]["node"], c["target"]["path"], _sampler(doc, values, anim["samplers"][c["sampler"]]))
                   for c in anim["channels"]]
        times = {clip.length * i / (POSE_SAMPLES - 1) for i in range(POSE_SAMPLES)}
        times |= {k[0] for tr in clip.bones[:3] for k in tr.keys[:3]}
        for t in sorted(times):
            live_trs: dict[int, dict[str, np.ndarray]] = {}
            for node, path, ch in decoded:
                live_trs.setdefault(node, {})[path] = np.float32(_hermite(ch, t)[0]).astype(float)
            world = _worlds(doc, _locals(doc, live_trs))
            for k, w in enumerate(_engine(info, clip, t)):
                mine, e = world[info.joint(k)], ROOT @ w
                m = float(np.abs(mine - e).max())
                pos = float(np.linalg.norm(mine[:3, 3] - e[:3, 3]))
                ra = mine[:3, :3] / np.linalg.norm(mine[:3, :3], axis=0)
                re_ = e[:3, :3] / np.linalg.norm(e[:3, :3], axis=0)
                deg = math.degrees(fdlibm.acos(min(1.0, max(-1.0, (np.trace(ra.T @ re_) - 1) / 2))))
                if m > clip_m:
                    clip_m, where = m, f"{anim['name']} t={t:.3f} {info.bones[k].name}"
                clip_pos, clip_deg = max(clip_pos, pos), max(clip_deg, deg)
        if clip_m > TOLERANCE:
            fail("C6", f"{where} sits {clip_m:.1e} off the engine's pose")

    # C7: the textures
    stages = {s["file"]: s["surf"] for m in doc["materials"] for s in m["extras"]["azurik"]["stages"]}
    for name, surf in stages.items():
        if not np.array_equal(_read_png((gltf.parent / name).read_bytes()), render.surf_image(characters_xbr, toc, surf)):
            fail("C7", f"{name} isn't its decoded texture")
    return CheckReport(rest_m, rest_offset_m, weight_sum, clip_m, clip_pos, clip_deg, where, len(anims),
                       channels, len(stages))


def vanilla_characters(characters_xbr: bytes) -> bool:
    """Whether ``characters_xbr`` is a release's vanilla file (its
    manifest's sha256): the root's extras say so, and the import will
    refuse anything else (D27)."""
    from azurkit.core import gate

    sha = hashlib.sha256(characters_xbr).hexdigest()
    return any(r.files.get("gamedata/characters.xbr", (0, ""))[1] == sha for r in gate.RELEASES)


def resolve_body(characters_xbr: bytes, config_xbr: bytes, name: str) -> tuple[str, str | None]:
    """The body ``name`` names, and the species that wears it when
    ``name`` is a ``critters_engine`` species rather than a body
    (``town_female_2`` wears ``townspeople/female_2``); :class:`ValueError`
    when it is neither."""
    try:
        return _read_name(characters_xbr, name), None
    except ValueError:
        pass
    from azurkit.tools.characters.ports import XbrDocument

    cell = XbrDocument.from_bytes(config_xbr).keyed_section("critters_engine").find_cell(name, "body")
    worn = cell.string_value if cell is not None and cell.type_code == 2 else None
    if not worn:
        raise ValueError(f"{name!r} is neither a characters.xbr body nor a species with a body")
    return _read_name(characters_xbr, worn), name


def _read_name(characters_xbr: bytes, body: str) -> str:
    index, _ = body_at(characters_xbr, body)
    return named_resources(characters_xbr)[index][len("characters/"):]


__all__ = ["CheckReport", "Export", "GENERATOR", "HELPER", "POSE_SAMPLES", "ROOT_ROTATION", "TOLERANCE", "VERSION",
           "check_export", "export_body", "resolve_body", "vanilla_characters"]
