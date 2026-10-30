"""A body's skeleton edited (Step 2.154, D443, D444): a bone added with
its name, parent and bind pose, or a bone renamed, in a
:class:`~azurik_mod.assets.body_codec.BodyAsset` that
:func:`~azurik_mod.assets.body_codec.write_asset` then writes.

Every table a clip, a marker or a mesh indexes stays as it was: a clip's
bone tracks, a group's palette and the pose's scratch slice name bones by
index (``docs/RE_DATA.md`` § "How a clip binds to a body"), so a new bone
goes after the last (no index moves, and the pose, which runs each
parent before its children, reaches its parent first); markers are their
own table.  A clip keys no new bone, so it holds its rest pose, which is
its bind.  A name is looked up only by name (an fx bind, the swap's
hand and staff binds, this toolkit's recipes), so a rename changes no
index; what looked a bone up by its old name no longer finds it.

**A new bone's record** (160 bytes, its parent's as the template for the
fields nothing reads, +0x58's exporter value among them): parent the
given one, no segment-scale compensation, RA and the rest rotation the
identity, JO the bone's bind rotation in its parent's bind frame (the
parent's composed bind rotation inverted, times the bind rotation
asked: the model's axes by default), the rest translation its bind
origin in that frame, scale 1, and the inverse bind the inverse of that
bind (D3D rows: the rotation's rows, then minus the origin times them),
so at rest the bone skins as the identity.  :func:`rest_worlds` composes
every bone's rest world by the engine model (0xCA470: JO x q x RA, the
rows scaled by S, a compensated child's translation times its parent's
scale) and :func:`add_bone` checks the new bone's against its inverse
bind.  A parent whose composed bind isn't rigid (a rest scale off 1 above
it) is refused: a bone under it can't hold an arbitrary bind rotation.
Plain floats with ``sqrt`` only, so a build writes the same bytes on
every machine; nothing here prints a byte or a coordinate.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Sequence

from azurkit.tools.characters.body_codec import BONE_RECORD, BodyAsset, Bone

Quat = tuple[float, float, float, float]
Vec = tuple[float, float, float]
Matrix = list[list[float]]

PARENT_MAX = 0x7FFF
"""The largest index a record's i16 parent holds."""
RIGID = 1e-5
"""How far a parent's composed bind may sit from a rotation."""


def fields(bone: Bone) -> dict:
    """A bone record's pose fields (``characters.BoneRecord``'s)."""
    f = struct.unpack_from("<18f", bone.record, 0x10)
    return {"parent": bone.parent, "compensate": bool(bone.record[0xB]), "ra": f[0:4], "jo": f[4:8],
            "t": f[8:11], "q": f[11:15], "s": f[15:18],
            "bind": struct.unpack_from("<16f", bone.record, 0x60)}


def _qmul(p, q) -> Quat:
    x1, y1, z1, w1 = p
    x2, y2, z2, w2 = q
    return (w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2)


def _qnorm(q) -> Quat:
    n = math.sqrt(sum(c * c for c in q))
    if not n > 0:
        raise ValueError("a zero rotation")
    return tuple(c / n for c in q)


def _rot(q) -> Matrix:
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def _mat(r: Matrix, t, s=(1.0, 1.0, 1.0)) -> Matrix:
    return [[r[i][0] * s[0], r[i][1] * s[1], r[i][2] * s[2], t[i]] for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]]


def _mul(a: Matrix, b: Matrix) -> Matrix:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def rest_worlds(asset: BodyAsset) -> list[Matrix]:
    """Each bone's rest world (4x4, column vectors, the model's frame) by
    the engine model (module docstring)."""
    unscaled: list[Matrix] = []
    world: list[Matrix] = []
    for b in asset.bones:
        f = fields(b)
        local = _mat(_rot(_qnorm(_qmul(_qmul(f["jo"], _qnorm(f["q"])), f["ra"]))), f["t"])
        p = f["parent"]
        if p >= 0 and f["compensate"]:
            ps = fields(asset.bones[p])["s"]
            for i in range(3):
                local[i][3] *= ps[i]
            local = _mul(unscaled[p], local)
        elif p >= 0:
            local = _mul(world[p], local)
        unscaled.append(local)
        world.append(_mat([row[:3] for row in local[:3]], [row[3] for row in local[:3]], f["s"]))
    return world


def _world_rotation(asset: BodyAsset, k: int) -> Quat:
    """Bone ``k``'s composed bind rotation as a quaternion (its chain's
    JO q RA, root first)."""
    chain = []
    while k >= 0:
        chain.append(k)
        k = asset.bones[k].parent
    q: Quat = (0.0, 0.0, 0.0, 1.0)
    for j in reversed(chain):
        f = fields(asset.bones[j])
        q = _qnorm(_qmul(q, _qnorm(_qmul(_qmul(f["jo"], _qnorm(f["q"])), f["ra"]))))
    return q


def _rigid(m: Matrix) -> bool:
    r = [row[:3] for row in m[:3]]
    return all(abs(sum(r[k][i] * r[k][j] for k in range(3)) - (1.0 if i == j else 0.0)) <= RIGID
               for i in range(3) for j in range(3))


def _check_name(asset: BodyAsset, name: str) -> None:
    if not name or not name.isascii() or "\0" in name:
        raise ValueError(f"bone name {name!r}: non-empty ASCII without a NUL")
    if name in asset.bone_names:
        raise ValueError(f"{asset.name} has a bone {name!r} already")


def add_bone(asset: BodyAsset, name: str, parent: str | None, origin: Sequence[float],
             rotation: Sequence[float] = (0.0, 0.0, 0.0, 1.0)) -> int:
    """A bone ``name`` added after the last one, under ``parent`` (a
    bone's name; ``None`` a root), its bind origin ``origin`` and bind
    rotation ``rotation`` ((x, y, z, w), the model's frame) as asked
    (module docstring); its index.  :class:`ValueError` for a taken or
    bad name, an unknown parent, one whose bind isn't rigid, or a bind
    that doesn't compose back to the one asked."""
    _check_name(asset, name)
    if len(asset.bones) + 1 > PARENT_MAX:
        raise ValueError(f"{asset.name}: {len(asset.bones) + 1} bones, past the {PARENT_MAX} an i16 parent names")
    o = tuple(float(c) for c in origin)
    rq = _qnorm(tuple(float(c) for c in rotation))
    if len(o) != 3 or len(rq) != 4 or not all(math.isfinite(c) for c in (*o, *rq)):
        raise ValueError(f"bone {name!r}: its origin needs three finite numbers and its rotation four")
    worlds = rest_worlds(asset)
    if parent is None:
        p, template = -1, asset.bones[0].record if asset.bones else bytes(BONE_RECORD)
        pq, pw = (0.0, 0.0, 0.0, 1.0), _mat(_rot((0.0, 0.0, 0.0, 1.0)), (0.0, 0.0, 0.0))
    else:
        p = asset.bone(parent)
        if not _rigid(worlds[p]):
            raise ValueError(f"bone {name!r}: its parent {parent!r}'s bind carries a scale, so no bind rotation "
                             "under it is exact: choose a parent with rest scale 1 above it")
        template, pq, pw = asset.bones[p].record, _world_rotation(asset, p), worlds[p]
    r = [row[:3] for row in pw[:3]]
    d = [o[i] - pw[i][3] for i in range(3)]
    t = tuple(sum(r[k][i] * d[k] for k in range(3)) for i in range(3))     # R_parent^T (o - parent origin)
    jo = _qnorm(_qmul((-pq[0], -pq[1], -pq[2], pq[3]), rq))
    br = _rot(rq)
    rows = [br[0][0], br[0][1], br[0][2], 0.0, br[1][0], br[1][1], br[1][2], 0.0, br[2][0], br[2][1], br[2][2], 0.0,
            -sum(o[k] * br[k][0] for k in range(3)), -sum(o[k] * br[k][1] for k in range(3)),
            -sum(o[k] * br[k][2] for k in range(3)), 1.0]
    rec = bytearray(template)
    struct.pack_into("<h", rec, 8, p)
    rec[0xA], rec[0xB] = 0, 0
    struct.pack_into("<4f", rec, 0x10, 0.0, 0.0, 0.0, 1.0)
    struct.pack_into("<4f", rec, 0x20, *jo)
    struct.pack_into("<3f", rec, 0x30, *t)
    struct.pack_into("<4f", rec, 0x3C, 0.0, 0.0, 0.0, 1.0)
    struct.pack_into("<3f", rec, 0x4C, 1.0, 1.0, 1.0)
    struct.pack_into("<16f", rec, 0x60, *rows)
    asset.bones.append(Bone(name, bytes(rec)))
    k = len(asset.bones) - 1
    w = rest_worlds(asset)[k]
    m = struct.unpack_from("<16f", rec, 0x60)
    err = max(max(abs(w[i][3] - o[i]) for i in range(3)),
              max(abs(w[i][j] - br[i][j]) for i in range(3) for j in range(3)),
              max(abs(m[4 * i + j] - br[i][j]) for i in range(3) for j in range(3)),
              max(abs(m[12 + j] + sum(o[i] * br[i][j] for i in range(3))) for j in range(3)))
    if err > 1e-5:
        asset.bones.pop()
        raise ValueError(f"bone {name!r}: its record composes {err:.2g} off the bind asked")
    return k


def rename_bone(asset: BodyAsset, old: str, new: str) -> None:
    """Bone ``old`` renamed ``new``; :class:`ValueError` for an unknown
    bone or a taken or bad name."""
    k = asset.bone(old)
    if new == old:
        return
    _check_name(asset, new)
    asset.bones[k] = Bone(new, asset.bones[k].record)


__all__ = ["PARENT_MAX", "add_bone", "fields", "rename_bone", "rest_worlds"]
