"""A character body and its animation clips, read from ``characters.xbr``
by name (Step 2.21a, D112).

The engine loads a species' model from ``characters/<body>`` and plays a
clip ``<name>`` as ``characters/<body>/<name>`` (0x4B600; case-blind:
``water_lizardX``'s resource is ``characters/water_lizardx``). The
player-model swap (``azurik_mod.patches._player_character``) reads which
clips a body has, how long each is, and which of them switch its damage
marker on.

Layouts (``docs/RE_DATA.md`` § "Character bodies, their clips and the
damage marker"; a self-relative pointer is relative to its own field):

- ``body``: +0 bone count, +4 pointer to 160-byte bone records, whose
  +4 is a pointer to the bone's name and +0x60 the bone's inverse bind
  matrix (16 f32 by rows, the translation last); +0x18 marker count,
  +0x1C pointer to 0x38-byte
  marker records: +0 name length, +4 name pointer, then 12 f32
  defaults, of which +0x30 is the length and +0x34 the active value (the
  runtime marker's +0x2C and +0x30).
- ``banm``: +8 marker-track count, +0xC pointer to 0x14-byte tracks,
  +0x10 the clip's length in seconds (f32); a track:
  +4 key count, +8 pointer to 16-byte keys (f32 time, f32 value, ...),
  +0xC the target marker's index, +0x10 the component (10 length,
  11 active).

A clip deals damage when it turns the body's ``m_damage`` or
``m_damage2`` marker on: the per-critter damage pass (0x43A80) builds a
hit box only while the marker's active value is at least 0.5 and its
length above 0.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from azurkit.core.xbr.nodes import named_resources, parse_toc

DAMAGE_MARKERS = ("m_damage", "m_damage2")
_LENGTH, _ACTIVE = 10, 11            # a marker track's components


@dataclass(frozen=True)
class Body:
    """A body in ``characters.xbr``: its clips and the clips among them
    that switch a damage marker on, each sorted by name, and each clip's
    length in seconds (``banm`` +0x10), in ``clips``' order; its markers'
    names, in the body's order; its top, the highest of its bones (0.0
    with no bones; a critter is drawn at its species' ``scale`` times
    that); its bones, in the body's order, each ``(name, (x, y, z))``
    with its bind-pose position in model units (x to the model's right,
    y forward, z up).  When a damage clip's window opens is
    :func:`damage_windows`' (Step 2.104, AZ-524)."""

    name: str
    clips: tuple[str, ...]
    damage_clips: tuple[str, ...]
    lengths: tuple[float, ...]
    markers: tuple[str, ...] = ()
    top: float = 0.0
    bones: tuple[tuple[str, tuple[float, float, float]], ...] = ()

    def length(self, clip: str) -> float:
        """``clip``'s length in seconds; :class:`ValueError` if the body
        has no such clip."""
        if clip not in self.clips:
            raise ValueError(f"characters.xbr: body {self.name!r} has no clip {clip!r}")
        return self.lengths[self.clips.index(clip)]


def _i32(data, at: int) -> int:
    return struct.unpack_from("<i", data, at)[0]


def _f32(data, at: int) -> float:
    return struct.unpack_from("<f", data, at)[0]


def _ptr(data, at: int) -> int:
    """The target of the self-relative pointer at ``at``."""
    return at + _i32(data, at)


def _cstr(data, at: int) -> str:
    return bytes(data[at:data.index(b"\x00", at)]).decode("ascii")


@dataclass(frozen=True)
class BoneRecord:
    """A bone record's pose fields (Step 2.87; ``docs/RE_DATA.md`` §
    "Character bodies"): its parent's index (+8, i16; -1 the root
    matrix), the segment-scale-compensate flag (+0xB), the rotate-axis
    quaternion RA (+0x10) and joint-orient quaternion JO (+0x20), each
    (x, y, z, w), and its rest translation (+0x30), rotation (+0x3C) and
    scale (+0x4C).  0xCA470 builds its local rotation JO x q x RA
    (Hamilton), q the clip's or else the rest rotation."""

    name: str
    parent: int
    compensate: bool
    ra: tuple[float, float, float, float]
    jo: tuple[float, float, float, float]
    t: tuple[float, float, float]
    q: tuple[float, float, float, float]
    s: tuple[float, float, float]


def body_at(characters_xbr: bytes, body: str) -> tuple[int, int]:
    """The TOC index and file offset of the body ``characters/<body>``;
    :class:`ValueError` if there is none."""
    toc, names = parse_toc(characters_xbr), named_resources(characters_xbr)
    index = {name.casefold(): i for i, name in names.items()}.get(f"characters/{body}".casefold())
    if index is None or toc[index].tag != "body":
        raise ValueError(f"characters.xbr: no body {body!r}")
    return index, toc[index].file_offset


def bone_records(characters_xbr: bytes, body: str) -> tuple[BoneRecord, ...]:
    """The body ``characters/<body>``'s bone records, in its order
    (:class:`BoneRecord`); :class:`ValueError` if it has no body."""
    at = body_at(characters_xbr, body)[1]
    table = _ptr(characters_xbr, at + 4)
    out = []
    for b in range(_i32(characters_xbr, at)):
        rec = table + 160 * b
        f = struct.unpack_from("<18f", characters_xbr, rec + 0x10)
        out.append(BoneRecord(_cstr(characters_xbr, _ptr(characters_xbr, rec + 4)),
                              struct.unpack_from("<h", characters_xbr, rec + 8)[0],
                              bool(characters_xbr[rec + 0xB]), f[0:4], f[4:8], f[8:11], f[11:15], f[15:18]))
    return tuple(out)


def inverse_binds(characters_xbr: bytes, body: str) -> tuple[tuple[float, ...], ...]:
    """Each bone's inverse bind matrix (its record's +0x60), 16 floats as
    the game holds a matrix (D3D rows, the translation last), in the
    body's order: a point in the model times it is the point in the
    bone's bind frame (:func:`_bones`).  :class:`ValueError` if the body
    has no body."""
    at = body_at(characters_xbr, body)[1]
    table = _ptr(characters_xbr, at + 4)
    return tuple(struct.unpack_from("<16f", characters_xbr, table + 160 * b + 0x60)
                 for b in range(_i32(characters_xbr, at)))


def _damage_markers(data, at: int) -> dict[int, tuple[float, float]]:
    """``{marker index: (default length, default active)}`` of the body
    at ``at``'s damage markers."""
    table = _ptr(data, at + 0x1C)
    out = {}
    for i in range(_i32(data, at + 0x18)):
        rec = table + 0x38 * i
        if _cstr(data, _ptr(data, rec + 4)) in DAMAGE_MARKERS:
            out[i] = (_f32(data, rec + 0x30), _f32(data, rec + 0x34))
    return out


def _markers(data, at: int) -> tuple[str, ...]:
    """The names of the body at ``at``'s markers, in its order."""
    table = _ptr(data, at + 0x1C)
    return tuple(_cstr(data, _ptr(data, table + 0x38 * i + 4)) for i in range(_i32(data, at + 0x18)))


def _cross(a, b) -> tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def _bones(data, at: int) -> tuple[tuple[str, tuple[float, float, float]], ...]:
    """The body at ``at``'s bones, each ``(name, bind-pose position)``.
    A bone's inverse bind matrix M (rows r0-r2, the translation t last)
    takes its origin p to zero, p M = 0, so p = -t R^-1: by Cramer's
    rule each coordinate is -t . (the other two rows' cross) / det R."""
    table = _ptr(data, at + 4)
    out = []
    for b in range(_i32(data, at)):
        rec = table + 160 * b
        m = struct.unpack_from("<16f", data, rec + 0x60)
        r0, r1, r2, t = m[0:3], m[4:7], m[8:11], m[12:15]
        det = _dot(r2, _cross(r0, r1))
        p = tuple(-_dot(t, _cross(u, v)) / det for u, v in ((r1, r2), (r2, r0), (r0, r1)))
        out.append((_cstr(data, _ptr(data, rec + 4)), p))
    return tuple(out)


def _switches_damage(data, at: int, markers: dict[int, tuple[float, float]]) -> bool:
    """Whether the clip at ``at`` turns one of ``markers`` on: some key of
    its active part (or its default, with no active track) at 0.5 or
    more, and some key of its length part (or its default) above 0."""
    keys: dict[tuple[int, int], list[tuple[float, float]]] = {}
    table = _ptr(data, at + 0xC)
    for k in range(_i32(data, at + 8)):
        rec = table + 0x14 * k
        target, part = _i32(data, rec + 0xC), _i32(data, rec + 0x10)
        if target in markers and part in (_LENGTH, _ACTIVE):
            first = _ptr(data, rec + 8)
            keys[target, part] = [(_f32(data, first + 16 * j), _f32(data, first + 16 * j + 4))
                                  for j in range(_i32(data, rec + 4))]
    return any(any(v >= 0.5 for _, v in keys.get((m, _ACTIVE), [(0.0, active)]))
               and max(v for _, v in keys.get((m, _LENGTH), [(0.0, length)])) > 0
               for m, (length, active) in markers.items())


def body_names(characters_xbr: bytes) -> frozenset[str]:
    """Every body ``characters_xbr`` has a model for, case-folded
    (``water_lizardx``, ``bosses/air_guardian``)."""
    toc = parse_toc(characters_xbr)
    return frozenset(name[len("characters/"):].casefold()
                     for i, name in named_resources(characters_xbr).items()
                     if toc[i].tag == "body" and name.startswith("characters/"))


STILL_CLIPS = frozenset({"idle", "sit"})
"""The clips an object's body may hold (:func:`object_bodies`): a rest pose, nothing that moves it."""


def object_bodies(characters_xbr: bytes) -> frozenset[str]:
    """The bodies ``characters_xbr`` has that are objects, not creatures,
    case-folded (D1034: the Characters tab's Show objects): at most two
    bones (one rigid bone, obsidian's two) and no clip directly under it
    but :data:`STILL_CLIPS` (none for a statue or a fragment). On the
    vanilla discs the 73 pickups' and the clipless gargoylestone's and
    tesla_tree's; the boulder's own run and die make it a creature."""
    toc, bodies, clips = parse_toc(characters_xbr), {}, {}
    for i, name in named_resources(characters_xbr).items():
        key = name.casefold()
        if not key.startswith("characters/"):
            continue
        rest = key[len("characters/"):]
        if toc[i].tag == "body":
            bodies[rest] = toc[i].file_offset
        elif toc[i].tag == "banm":
            body, _, clip = rest.rpartition("/")
            clips.setdefault(body, set()).add(clip)
    return frozenset(body for body, at in bodies.items()
                     if _i32(characters_xbr, at) <= 2 and clips.get(body, set()) <= STILL_CLIPS)


def read_body(characters_xbr: bytes, body: str, dirs: tuple[str, ...] = ()) -> Body | None:
    """The body ``characters/<body>`` of ``characters_xbr``, or ``None``
    if it has none: its clips are the clips directly under it and, for
    each of ``dirs`` (a subdirectory such as a variant's ``v/``, Step
    2.137), the clips directly in that one, named with it (``v/spin``).
    :class:`ValueError` if the body or a clip of it doesn't parse."""
    toc, names = parse_toc(characters_xbr), named_resources(characters_xbr)
    key = f"characters/{body}".casefold()
    by_name = {name.casefold(): i for i, name in names.items()}
    index = by_name.get(key)
    if index is None or toc[index].tag != "body":
        return None
    prefix = key + "/"

    def listed(rest: str) -> bool:
        return "/" not in rest or any(rest.startswith(d) and "/" not in rest[len(d):] for d in dirs)
    clips = {name[len(prefix):]: toc[i].file_offset for i, name in names.items()
             if name.casefold().startswith(prefix) and listed(name[len(prefix):])
             and toc[i].tag == "banm"}
    at = toc[index].file_offset
    try:
        markers = _damage_markers(characters_xbr, at)
        damage = sorted(clip for clip, clip_at in clips.items()
                        if markers and _switches_damage(characters_xbr, clip_at, markers))
        lengths = tuple(_f32(characters_xbr, clips[clip] + 0x10) for clip in sorted(clips))
        marker_names, bones = _markers(characters_xbr, at), _bones(characters_xbr, at)
    except (struct.error, ValueError, IndexError, ZeroDivisionError) as exc:
        raise ValueError(f"characters.xbr: body {body!r} doesn't parse: {exc}") from None
    top = max((p[2] for _, p in bones), default=0.0)
    return Body(body, tuple(sorted(clips)), tuple(damage), lengths, marker_names, top, bones)


def _linear(keys: list[tuple[float, float]], t: float) -> float:
    """``keys``' (time, value) pairs at ``t``, linear between them and
    held past either end."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * ((t - t0) / (t1 - t0) if t1 > t0 else 0.0)
    return keys[-1][1]


def damage_anchor(characters_xbr: bytes, body: str, clip: str) -> tuple[float, float, float]:
    """Where the body ``characters/<body>``'s ``m_damage`` sits, in model
    units, at the middle of ``clip``'s damage window (the keys that hold
    its active value at 0.5 or more): its translation tracks (components
    0-2) there, linear between keys (the game's 0xD8300 is a Hermite; an
    anchor needs no more), and its defaults where the clip keys none.
    :class:`ValueError` if the body has no ``m_damage`` or the clip
    never switches it on."""
    toc, names = parse_toc(characters_xbr), named_resources(characters_xbr)
    by_name = {name.casefold(): i for i, name in names.items()}
    body_i, clip_i = (by_name.get(f"characters/{key}".casefold()) for key in (body, f"{body}/{clip}"))
    if body_i is None or clip_i is None:
        raise ValueError(f"characters.xbr: no body {body!r} with a clip {clip!r}")
    at = toc[body_i].file_offset
    table = _ptr(characters_xbr, at + 0x1C)
    marker = next((i for i in range(_i32(characters_xbr, at + 0x18))
                   if _cstr(characters_xbr, _ptr(characters_xbr, table + 0x38 * i + 4)) == "m_damage"), None)
    if marker is None:
        raise ValueError(f"characters.xbr: body {body!r} has no m_damage")
    defaults = struct.unpack_from("<3f", characters_xbr, table + 0x38 * marker + 8)
    keys: dict[int, list[tuple[float, float]]] = {}
    at = toc[clip_i].file_offset
    tracks = _ptr(characters_xbr, at + 0xC)
    for k in range(_i32(characters_xbr, at + 8)):
        rec = tracks + 0x14 * k
        if _i32(characters_xbr, rec + 0xC) == marker:
            first = _ptr(characters_xbr, rec + 8)
            keys[_i32(characters_xbr, rec + 0x10)] = [
                (_f32(characters_xbr, first + 16 * j), _f32(characters_xbr, first + 16 * j + 4))
                for j in range(_i32(characters_xbr, rec + 4))]
    on = [t for t, v in keys.get(_ACTIVE, ()) if v >= 0.5]
    if not on:
        raise ValueError(f"characters.xbr: {body!r}'s {clip!r} never switches m_damage on")
    mid = (on[0] + on[-1]) / 2
    return tuple(_linear(keys[c], mid) if keys.get(c) else defaults[c] for c in range(3))


def marker_records(characters_xbr: bytes, body: str) -> tuple[tuple[str, tuple[float, ...]], ...]:
    """The body ``characters/<body>``'s markers, in its order: each name
    and its twelve defaults (position, rotation, extents, length, active:
    the record's +8 on).  :class:`ValueError` if it has no body."""
    toc, names = parse_toc(characters_xbr), named_resources(characters_xbr)
    index = {name.casefold(): i for i, name in names.items()}.get(f"characters/{body}".casefold())
    if index is None or toc[index].tag != "body":
        raise ValueError(f"characters.xbr: no body {body!r}")
    at = toc[index].file_offset
    table = _ptr(characters_xbr, at + 0x1C)
    return tuple((_cstr(characters_xbr, _ptr(characters_xbr, table + 0x38 * i + 4)),
                  struct.unpack_from("<12f", characters_xbr, table + 0x38 * i + 8))
                 for i in range(_i32(characters_xbr, at + 0x18)))


CAMERA_MARKER = "m_head"
"""The marker the cameras aim at: a critter's camera point (0x41F40, its
vtable slot +0xB0, which only the cameras call) is its body's marker of
this exact name in the world (0xCB2A0), scaled by the critter's +0x188;
a body without one gives the critter's feet (Step 2.23c)."""


def _body_at(characters_xbr: bytes, body: str) -> int | None:
    """The file offset of the body ``characters/<body>``, or ``None``."""
    toc, names = parse_toc(characters_xbr), named_resources(characters_xbr)
    index = next((i for i, name in names.items() if name.casefold() == f"characters/{body}".casefold()), None)
    return None if index is None or toc[index].tag != "body" else toc[index].file_offset


def marker_default(characters_xbr: bytes, body: str, marker: str) -> tuple[float, float, float] | None:
    """Where the body ``characters/<body>``'s marker ``marker`` rests, its
    default position in model units (the record's +8), or ``None`` when
    the body has no such marker (garret4's ``m_head``: 1.9925 m, the
    camera point, Step 2.68)."""
    at = _body_at(characters_xbr, body)
    if at is None:
        return None
    table = _ptr(characters_xbr, at + 0x1C)
    for i in range(_i32(characters_xbr, at + 0x18)):
        rec = table + 0x38 * i
        if _cstr(characters_xbr, _ptr(characters_xbr, rec + 4)) == marker:
            return struct.unpack_from("<3f", characters_xbr, rec + 8)
    return None


def mesh_points(characters_xbr: bytes, body: str) -> list[tuple[float, float, float]]:
    """The model-space positions of the body ``characters/<body>``'s most
    detailed mesh's vertices (``docs/XBR_FORMAT.md`` § "Graphics
    resources": ``body`` +8 the LOD count and +12 the LODs' ``bmsh`` TOC
    indices; a ``bmsh`` +0 its group count and +4 its 40-byte groups,
    each +24 a vertex count and +28 its 60-byte vertices, a float
    position first); ``[]`` when it has none."""
    at = _body_at(characters_xbr, body)
    if at is None or _i32(characters_xbr, at + 8) <= 0:
        return []
    toc = parse_toc(characters_xbr)
    bmsh = toc[_i32(characters_xbr, _ptr(characters_xbr, at + 12))].file_offset
    groups = _ptr(characters_xbr, bmsh + 4)
    out = []
    for k in range(_i32(characters_xbr, bmsh)):
        group = groups + 40 * k
        vertices = _ptr(characters_xbr, group + 28)
        out += [struct.unpack_from("<3f", characters_xbr, vertices + 60 * j)
                for j in range(_i32(characters_xbr, group + 24))]
    return out


def mesh_bounds(characters_xbr: bytes, body: str) -> tuple[tuple[float, ...], tuple[float, ...]] | None:
    """The model-space bounds (low, high) of the body ``characters/<body>``'s
    most detailed mesh (:func:`mesh_points`), or ``None`` when it has none."""
    low, high = [math.inf] * 3, [-math.inf] * 3
    for point in mesh_points(characters_xbr, body):
        for axis, v in enumerate(point):
            low[axis], high[axis] = min(low[axis], v), max(high[axis], v)
    return (tuple(low), tuple(high)) if low[0] <= high[0] else None


VERTEX_SIZE = 60
"""A ``bmsh`` vertex's size (FVF 0x1021C): its float position, four blend
weights at +12, its normal at +28, its UV at +40, an unused float pair at
+48 and four bone-slot bytes at +56 (declaration 0x1A7C08)."""


@dataclass(frozen=True)
class MeshGroup:
    """One group of one LOD of a body's mesh (``docs/XBR_FORMAT.md`` §
    "Graphics resources"): its LOD and index in it, its bone list (group
    +4 the count, +8 an i32 self-relative pointer to that many i32 bone
    indices, which the body draw loads each bone's world matrix times its
    inverse bind for: 0x3F2D2-0x3F34F, 0xCC8B7-0xCC92D) and that list's
    file offset, and its vertices (+28, :data:`VERTEX_SIZE` bytes each)
    with their count (+24)."""

    lod: int
    index: int
    bones: tuple[int, ...]
    bones_at: int
    vertices: int
    count: int


def mesh_groups(characters_xbr: bytes, body: str) -> tuple[MeshGroup, ...]:
    """Every group of every LOD of the body ``characters/<body>``'s mesh
    (:class:`MeshGroup`), LOD by LOD; ``()`` for a body with no mesh or no
    such body."""
    at = _body_at(characters_xbr, body)
    if at is None:
        return ()
    toc = parse_toc(characters_xbr)
    out = []
    for lod in range(max(_i32(characters_xbr, at + 8), 0)):
        bmsh = toc[_i32(characters_xbr, _ptr(characters_xbr, at + 12) + 4 * lod)].file_offset
        groups = _ptr(characters_xbr, bmsh + 4)
        for k in range(_i32(characters_xbr, bmsh)):
            group = groups + 40 * k
            n = _i32(characters_xbr, group + 4)
            bones_at = _ptr(characters_xbr, group + 8) if n > 0 else 0
            bones = struct.unpack_from(f"<{n}i", characters_xbr, bones_at) if n > 0 else ()
            out.append(MeshGroup(lod, k, bones, bones_at, _ptr(characters_xbr, group + 28),
                                 _i32(characters_xbr, group + 24)))
    return tuple(out)


FLAT = 0.25
"""A mesh whose top is lower than this fraction of its longest side lies
flat: :func:`height` takes that side instead."""


def height(characters_xbr: bytes, body: Body) -> float:
    """How tall ``body`` is drawn in model units, the measure the size
    option scales by (Step 2.68): the top of its most detailed mesh above
    its feet (:func:`mesh_bounds`' high z; garret4's 2.002, kingkong's
    golem 3.38, where the top of its bones is 3.03), else, for a mesh
    that lies flat (its top under :data:`FLAT` of its longest side: the
    water tentacles, 7.5-24 m along y; the firefly's 17 cm wings;
    fire_shard; the bird; the jellyfish, which hangs below its feet),
    that longest side; the top of its bones (:attr:`Body.top`) for a
    body with no mesh, 0.0 for one with neither."""
    bounds = mesh_bounds(characters_xbr, body.name)
    if bounds is None:
        return max(body.top, 0.0)
    longest = max(h - lo for lo, h in zip(*bounds))
    top = bounds[1][2]
    return top if top >= FLAT * longest else longest


ROOT_NODE = "m_feet"
"""The node whose motion an attack move and the roll travel by:
player_attack_root_motion (0x8C630) samples its translation through
0xCACD0 (Step 2.21b)."""


def moves_root(characters_xbr: bytes, body: str, clip: str) -> bool:
    """Whether ``clip`` of the body ``characters/<body>`` moves its
    :data:`ROOT_NODE` along x or y: a marker track on the node's
    component 0 or 1 whose keys don't all hold one value.  A body without
    the node, or without the clip, moves nothing."""
    toc, names = parse_toc(characters_xbr), named_resources(characters_xbr)
    by_name = {name.casefold(): i for i, name in names.items()}
    body_i = by_name.get(f"characters/{body}".casefold())
    clip_i = by_name.get(f"characters/{body}/{clip}".casefold())
    if body_i is None or clip_i is None:
        return False
    at = toc[body_i].file_offset
    table = _ptr(characters_xbr, at + 0x1C)
    nodes = {i for i in range(_i32(characters_xbr, at + 0x18))
             if _cstr(characters_xbr, _ptr(characters_xbr, table + 0x38 * i + 4))
             .casefold() == ROOT_NODE}
    at = toc[clip_i].file_offset
    tracks = _ptr(characters_xbr, at + 0xC)
    for k in range(_i32(characters_xbr, at + 8)):
        rec = tracks + 0x14 * k
        if _i32(characters_xbr, rec + 0xC) in nodes and _i32(characters_xbr, rec + 0x10) in (0, 1):
            first = _ptr(characters_xbr, rec + 8)
            if len({_f32(characters_xbr, first + 16 * j + 4)
                    for j in range(_i32(characters_xbr, rec + 4))}) > 1:
                return True
    return False


# --- a clip's damage windows and their boxes (Step 2.61's evaluator; 2.70) --

MELEE_REACH = 4.0
"""Step 2.61's line between melee and ranged, in metres: an attack whose
damage box reaches no farther than this horizontally from the feet is
melee (X13's reach-to-ground applies to it); beyond it, ranged (a beam,
a breath)."""

SAMPLE_STEP = 1 / 300.0
"""How finely :func:`damage_windows` samples a clip, in seconds."""
_RIPPLE = 0.05
"""Windows this close (s) are one: a gap of a few samples is the cubic's
ripple across 0.5, not a second swing."""


@dataclass(frozen=True)
class DamageWindow:
    """One stretch of a clip in which a damage marker is on (active at
    least 0.5, length above 0), and its box at the critter's scale, in
    metres from the feet (x to the right, y ahead, z up): ``low`` and
    ``high`` bound every box over the window (its sweep), ``reach`` is the
    farthest horizontal point of that sweep from the feet and ``near``
    the nearest any one box of it comes to them (:func:`near`, 0 for a
    box over them; Step 2.70b: a swinging box's sweep can span the feet
    while every box stays metres off)."""

    marker: str
    on: float
    off: float
    low: tuple[float, float, float]
    high: tuple[float, float, float]
    reach: float
    near: float

    @property
    def forward(self) -> float:
        """How far straight ahead of the feet the window's sweep reaches
        (:func:`forward`), the logic's reach (D237; Step 2.137, AZ-604):
        ``reach``, its corner, overstates a square box by up to sqrt 2."""
        return forward(self.low, self.high)


FACING_HALF = 0.25
"""How far (m) to either side of the facing line a box may stand and
still count as reaching straight ahead (:func:`forward`): a small
target's half-width (garret4's attack_1 box stands 0.042 m off it)."""


def forward(low, high) -> float:
    """How far straight ahead of the feet an upright box from ``low`` to
    ``high`` reaches (Step 2.137, AZ-604): its far side's y when it comes
    within :data:`FACING_HALF` of the facing line (x = 0), else 0.0 (a
    box beside the line, which no target dead ahead meets), and 0.0 for a
    box wholly behind the feet."""
    dx = 0.0 if low[0] <= 0.0 <= high[0] else min(abs(low[0]), abs(high[0]))
    return high[1] if dx <= FACING_HALF and high[1] > 0.0 else 0.0


def near(low, high) -> float:
    """How near (horizontally) an upright box from ``low`` to ``high``
    comes to the feet, the origin: 0 when it stands over them."""
    return math.hypot(*(0.0 if a <= 0.0 <= b else min(abs(a), abs(b)) for a, b in zip(low[:2], high[:2])))


def _tracks(data, clip_at: int) -> list[tuple[int, int, int, int, list[tuple[float, ...]]]]:
    """A clip's marker tracks: ``(pre mode, post mode, marker, component,
    keys)``, each key ``(time, value, in tangent, out tangent)``."""
    table = _ptr(data, clip_at + 0xC)
    out = []
    for k in range(_i32(data, clip_at + 8)):
        rec = table + 0x14 * k
        first = _ptr(data, rec + 8)
        pre, post = struct.unpack_from("<2H", data, rec)
        out.append((pre, post, _i32(data, rec + 0xC), _i32(data, rec + 0x10),
                    [struct.unpack_from("<4f", data, first + 16 * j) for j in range(_i32(data, rec + 4))]))
    return out


def track_value(pre: int, post: int, keys, t: float) -> float | None:
    """A marker track at clip time ``t``, as the game's curve evaluator
    0xD8300 reads it: a cubic Hermite between keys, each tangent times the
    keys' spacing, a non-finite tangent holding the key's value (a step);
    before the first key or after the last, mode 0 holds the end key, 1
    extends it along its tangent and 2-4 wrap.  ``None`` with no keys."""
    if not keys:
        return None
    t0, t1 = keys[0][0], keys[-1][0]
    if len(keys) == 1:
        return keys[0][1]
    if t < t0 or t > t1:
        mode = pre if t < t0 else post
        if mode in (2, 3, 4) and t1 > t0:
            t = t0 + math.fmod(t - t0, t1 - t0)
            if t < t0:
                t += t1 - t0
        elif mode == 1:
            key = keys[0] if t < t0 else keys[-1]
            tangent = key[2] if t < t0 else key[3]
            return key[1] + (t - key[0]) * tangent if math.isfinite(tangent) else key[1]
        else:
            return keys[0][1] if t < t0 else keys[-1][1]
    k = 0
    while k + 1 < len(keys) - 1 and t >= keys[k + 1][0]:
        k += 1
    a, b = keys[k], keys[k + 1]
    dt = b[0] - a[0]
    if dt <= 0:
        return b[1]
    s = (t - a[0]) / dt
    m0, m1 = dt * a[3], dt * b[2]
    if not (math.isfinite(m0) and math.isfinite(m1)):
        return a[1]
    p0, p1 = a[1], b[1]
    d = p0 - p1
    return (((d + d + m1 + m0) * s + ((p1 - p0) * 3 - (m0 + m0) - m1)) * s + m0) * s + p0


def _rotate(q, v) -> tuple[float, float, float]:
    """``v`` rotated by the quaternion ``q`` = (x, y, z, w), normalized: the
    model-space direction 0xA0770's matrix gives a box axis."""
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    r = ((1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
         (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
         (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)))
    return tuple(sum(r[i][j] * v[j] for j in range(3)) for i in range(3))


def _box(values, scale: float) -> tuple[list[float], list[float]]:
    """The model-space bounds of a marker's box (its 12 values: position,
    quaternion, extents, length, active) at ``scale``: centre the
    position, half extents the extents times the length, rotated (the
    damage pass 0x43A80 through 0xCA390)."""
    pos, q, half = values[0:3], values[3:7], [abs(e * values[10]) for e in values[7:10]]
    low, high = [math.inf] * 3, [-math.inf] * 3
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                corner = _rotate(q, (sx * half[0], sy * half[1], sz * half[2]))
                for i in range(3):
                    p = (corner[i] + pos[i]) * scale
                    low[i], high[i] = min(low[i], p), max(high[i], p)
    return low, high


_LAST: tuple[bytes | None, dict] = (None, {})   # the last bytes characters.xbr seen, and its results (_kept)


def _kept(characters_xbr, key: tuple, compute):
    """``compute()``, kept by ``key`` while ``characters_xbr`` is the last
    immutable ``bytes`` buffer asked about (Step X.55: a model swap asks
    about the same clips of its one buffer about twice each); a buffer
    that can change (a bytearray) is computed every time."""
    global _LAST
    if type(characters_xbr) is not bytes:
        return compute()
    last = _LAST
    if last[0] is not characters_xbr:      # held here, so its id can't name another buffer meanwhile
        last = _LAST = (characters_xbr, {})
    if key not in last[1]:
        last[1][key] = compute()
    return last[1][key]


def _damage_samples(characters_xbr: bytes, body: str, clip: str) -> tuple[tuple[str, float, tuple[float, ...]], ...]:
    """Each sample, every :data:`SAMPLE_STEP` seconds, at which ``clip`` of
    the body ``characters/<body>`` has its ``m_damage`` or ``m_damage2``
    on (active at least 0.5, length above 0): ``(marker, t, its 12
    values)``, by marker in the body's order, then by time; ``()`` for a
    body or clip that doesn't exist."""
    return _kept(characters_xbr, ("samples", body, clip), lambda: _sample_damage(characters_xbr, body, clip))


def _sample_damage(characters_xbr: bytes, body: str, clip: str) -> tuple[tuple[str, float, tuple[float, ...]], ...]:
    toc, names = parse_toc(characters_xbr), named_resources(characters_xbr)
    by_name = {name.casefold(): i for i, name in names.items()}
    body_i = by_name.get(f"characters/{body}".casefold())
    clip_i = by_name.get(f"characters/{body}/{clip}".casefold())
    if body_i is None or clip_i is None:
        return ()
    at, clip_at = toc[body_i].file_offset, toc[clip_i].file_offset
    table = _ptr(characters_xbr, at + 0x1C)
    length = _f32(characters_xbr, clip_at + 0x10)
    tracks = _tracks(characters_xbr, clip_at)
    out = []
    for m in range(_i32(characters_xbr, at + 0x18)):
        rec = table + 0x38 * m
        name = _cstr(characters_xbr, _ptr(characters_xbr, rec + 4))
        if name not in DAMAGE_MARKERS:
            continue
        defaults = struct.unpack_from("<12f", characters_xbr, rec + 8)
        mine = [tr for tr in tracks if tr[2] == m and 0 <= tr[3] < 12]
        for s in range(int(round(length / SAMPLE_STEP)) + 1):
            t = min(s * SAMPLE_STEP, length)
            values = list(defaults)
            for pre, post, _, part, keys in mine:
                v = track_value(pre, post, keys, t)
                if v is not None:
                    values[part] = v
            if values[_ACTIVE] >= 0.5 and values[_LENGTH] > 0:
                out.append((name, t, tuple(values)))
    return tuple(out)


def damage_boxes(characters_xbr: bytes, body: str, clip: str,
                 scale: float = 1.0) -> tuple[tuple[str, float, tuple[float, ...], tuple[float, ...]], ...]:
    """Each box :func:`damage_windows` bounds: ``(marker, t, low, high)``
    every :data:`SAMPLE_STEP` seconds its marker is on, in metres from the
    feet at ``scale`` (Step 2.197b: per tick, AZ-766)."""
    return tuple((name, t, *map(tuple, _box(values, scale)))
                 for name, t, values in _damage_samples(characters_xbr, body, clip))


def damage_windows(characters_xbr: bytes, body: str, clip: str,
                   scale: float = 1.0) -> tuple[DamageWindow, ...]:
    """Every window in which ``clip`` of the body ``characters/<body>``
    switches its ``m_damage`` or ``m_damage2`` on, with its box at
    ``scale`` (the critter's ``scale``), sampled every
    :data:`SAMPLE_STEP` seconds; ``()`` for a clip that switches none on
    or a body or clip that doesn't exist.  The game builds the box each
    tick the marker is on (the damage pass 0x43A80)."""
    return _kept(characters_xbr, ("windows", body, clip, scale, math.copysign(1.0, scale)),   # -0.0 apart from 0.0
                 lambda: _windows(characters_xbr, body, clip, scale))


def _windows(characters_xbr: bytes, body: str, clip: str, scale: float) -> tuple[DamageWindow, ...]:
    runs: dict[str, list[list]] = {}
    for name, t, values in _damage_samples(characters_xbr, body, clip):
        mine = runs.setdefault(name, [])
        if mine and t - mine[-1][1] <= _RIPPLE:
            mine[-1][1] = t
            mine[-1][2].append(values)
        else:
            mine.append([t, t, [values]])
    out = []
    for name, mine in runs.items():
        for on, off, samples in mine:
            low, high, closest = [math.inf] * 3, [-math.inf] * 3, math.inf
            for values in samples:
                a, b = _box(values, scale)
                low = [min(x, y) for x, y in zip(low, a)]
                high = [max(x, y) for x, y in zip(high, b)]
                closest = min(closest, near(a, b))
            reach = max(math.hypot(x, y) for x in (low[0], high[0]) for y in (low[1], high[1]))
            out.append(DamageWindow(name, on, off, tuple(low), tuple(high), reach, closest))
    return tuple(sorted(out, key=lambda w: (w.on, w.marker)))


def first_contact(characters_xbr: bytes, body: str, clip: str, scale: float, ahead: float,
                  radius: float, tall: float, reach: float = 1.0,
                  span: tuple[float, float] = (0.0, math.inf), fill: bool = False) -> float | None:
    """When, in clip seconds from ``span[0]`` to ``span[1]``, a damage box
    of ``clip`` (:func:`damage_windows`' boxes at ``scale``) first meets an
    upright target ``radius`` m round and ``tall`` m high standing on the
    ground dead ahead, its near side ``ahead`` m in front of the feet
    (Step 2.105, AZ-495): the box's bounds against the target's circle and
    height, sampled every :data:`SAMPLE_STEP` seconds, its reach ``reach``
    times as X13 grows it (its x and y bounds that many times, its height
    about its centre), and with ``fill`` (X13's fill in its column, Step
    2.132, AZ-605; its reach-to-ground before, Step 2.106, AZ-534) the
    bounds filled as X13 fills the box, which they then are: unless the
    whole box is behind the feet, its near side back to them and across
    the facing line, and a bottom above the feet down to them, its far
    sides and top kept; ``None`` when it never does."""
    centre = ahead + radius
    met = []
    for _, t, values in _damage_samples(characters_xbr, body, clip):
        if not span[0] <= t <= span[1]:
            continue
        a, b = _box(values, scale)
        mid, half = (a[2] + b[2]) / 2, (b[2] - a[2]) / 2 * reach
        x0, x1, y0, y1 = a[0] * reach, b[0] * reach, a[1] * reach, b[1] * reach
        low, top = mid - half, mid + half
        if fill:
            if y1 >= 0.0:
                x0, x1, y0 = min(x0, 0.0), max(x1, 0.0), min(y0, 0.0)
            low = min(low, 0.0)
        if top < 0.0 or low > tall:
            continue
        dx = 0.0 if x0 <= 0.0 <= x1 else min(abs(x0), abs(x1))
        dy = 0.0 if y0 <= centre <= y1 else min(abs(y0 - centre), abs(y1 - centre))
        if math.hypot(dx, dy) <= radius:
            met.append(t)
    return min(met, default=None)


def marker_peak(characters_xbr: bytes, body: str, marker: str, part: int) -> float | None:
    """The highest value component ``part`` (0-11, :func:`marker_records`'
    order; 2 is z) of the body ``characters/<body>``'s marker ``marker``
    (case-folded) takes: at rest (its default) or in any clip under the
    body, the bake's ``g4/`` clips included, sampled every
    :data:`SAMPLE_STEP` seconds and at each key; ``None`` when the body
    has no such marker."""
    toc, names = parse_toc(characters_xbr), named_resources(characters_xbr)
    key = f"characters/{body}".casefold()
    index = next((i for i, name in names.items() if name.casefold() == key), None)
    if index is None or toc[index].tag != "body":
        return None
    at = toc[index].file_offset
    table = _ptr(characters_xbr, at + 0x1C)
    m = next((i for i in range(_i32(characters_xbr, at + 0x18))
              if _cstr(characters_xbr, _ptr(characters_xbr, table + 0x38 * i + 4)).casefold() == marker.casefold()),
             None)
    if m is None:
        return None
    peak = _f32(characters_xbr, table + 0x38 * m + 8 + 4 * part)
    for i, name in names.items():
        if toc[i].tag != "banm" or not name.casefold().startswith(key + "/"):
            continue
        length = _f32(characters_xbr, toc[i].file_offset + 0x10)
        for pre, post, target, comp, keys in _tracks(characters_xbr, toc[i].file_offset):
            if target == m and comp == part and keys:
                times = {k[0] for k in keys if 0.0 <= k[0] <= length}
                times |= {min(s * SAMPLE_STEP, length) for s in range(int(length / SAMPLE_STEP) + 2)}
                peak = max(peak, *(track_value(pre, post, keys, t) for t in times))
    return peak


__all__ = ["Body", "BoneRecord", "CAMERA_MARKER", "DAMAGE_MARKERS", "DamageWindow", "MELEE_REACH", "MeshGroup",
           "ROOT_NODE", "FACING_HALF", "FLAT", "SAMPLE_STEP", "VERTEX_SIZE", "body_at", "body_names", "bone_records", "damage_anchor",
           "damage_boxes", "damage_windows", "first_contact", "forward", "height", "marker_default", "marker_peak", "marker_records", "mesh_bounds",
           "mesh_groups", "moves_root", "near", "read_body", "track_value"]
