"""A variant's jiggle bones (Step 2.143; D403, D428): a body's bust and
glutes swinging on baked springs in every clip it plays, with no runtime
code (the game has no secondary-motion system).

- **The bones** (:func:`rig`, W29): leaf bones that weight no vertex,
  have no child and no clip keys (female_2's ``joint32`` under the jaw,
  ``joint39`` under a brow), or new bones the body lacks (Step 2.154,
  D444: added after the last, :func:`~azurik_mod.assets.skeleton.add_bone`),
  get their 160-byte records written, keeping their name: parent the
  recipe's (an index below theirs, so the engine's one-pass order holds),
  RA and the rest rotation identity, JO the parent's bind world rotation
  inverted (the bone's frame is the model's axes at bind), the rest
  translation the bone's bind origin in its parent's frame, scale 1, and
  the inverse bind the translation to that origin, so at rest the bone
  skins as its parent does.  Its origin is the centroid of the vertices
  it takes, weighted by their share, on the mid-plane; a recipe ``from``
  another whose mesh differs (Step 2.177b: finer triangles where her
  forms curve, which pull a centroid by their count) places each bone
  where that recipe's own build does (``at``), so her springs and her
  clips' rests stay that recipe's.
- **The palettes**: a group whose vertices a jiggle bone reaches needs a
  palette entry for it, and female_2's skin is at the cap (31).  The
  recipe's ``frees`` empty entries: ``into`` merges a bone's weights
  into its parent's entry (exact: the build checks the bone is a child
  of that parent no clip keys, so the two skin alike in every pose), or
  ``drop`` drops weights all under :data:`DROP` and renormalises; the
  freed entries, in order, are re-aimed at the jiggle bones.  A group
  with no freed entry left takes a new one (Step 2.154): the write
  (:func:`~azurik_mod.assets.body_codec.write_asset`, which writes the
  rigged body) splits a group past 31 bones into groups of its material.
  :func:`rig` works on the decoded body, or on one W24 assembled and
  hasn't written (a subdivided mesh), so the shares' (group, index) ids
  are the ones it weighs.
- **The reskin**: each vertex a bone's ``shape`` reaches (the
  :func:`~azurik_mod.assets.mesh_edit.shares` of the recipe's ``push``
  or ``round`` ops so named, a mirrored op's mirror by its name with left
  and right swapped: a function of position, so the top and the skin
  under it take the same) gives ``weight`` x its share to the bone, taken from its
  weights on the bones the bone ``takes`` (its parent and the bones that
  move with it: the spine for a bust, the pelvis for the glutes) in
  proportion, at most all of them (bones that take from the same bones,
  a breast each, split what those hold in proportion to what they ask
  where they ask more): a vertex that follows a limb keeps
  following it, a cloth layer and the skin under it take the same weight
  wherever their taken bones hold it (so they swing together), and at rest
  or in a clip that doesn't key the bone every vertex moves as before but
  for the taken bones' blend; a vertex with four weights first folds one taken
  weight into another taken bone nearest it in the hierarchy (else its
  smallest weight into its nearest relative).  A bone that ``takes``
  its parent, a jiggle bone listed before it (Step 2.168, D575: a
  squish under a breast), reskins in a second pass from the weights the
  first left, so at rest its region skins as before; no other jiggle
  bone may be taken.
  Slot 0 holds the heaviest, the weights sum to 1 in float32, an unused
  slot is 0 with byte 0.
- **The spring** (:func:`keyed`, in W28's last pass over every clip she
  plays): two virtual masses per bone, at its origin plus and minus its
  ``sides`` (the share-weighted mean of |x| of its vertices) along x,
  each a damped spring of ``freq`` Hz and damping ratio ``damping`` in
  real time at the clip's playback ``rate`` (the one the game plays it
  at, AZ-648), driven in the parent's frame by the parent's motion: the
  anchor's acceleration (sampled at :data:`SIM_HZ` of real time,
  smoothed by a binomial kernel near a Gaussian of :data:`SMOOTH_HZ`,
  differenced twice in clip time, so as the clip moves at its own pace:
  the game plays a clip faster to cover ground or time a move, which
  swings the forms back at their own frequency but throws them no
  harder (her walk, a stroll, at 4.7-6.6 times its pace in the walk
  slot), times ``gain``: a clip's motion is gentler than the move it
  stands for, her walk played for her run) and gravity turned
  into the parent's frame against its bind times ``hang`` (so bending
  over hangs the forms down, and rest is 0), the sum through a soft
  limit of ``drive`` (``u / sqrt(1 + (u / drive)^2)`` on its length);
  a clip the recipe's ``loops``
  names (one the game cycles; its first and last pose alike, else
  refused) runs three times and keeps the last, any other is a one-shot:
  it starts at rest and eases back to rest over its last
  :data:`RELEASE`, the eased value the limited one times the ease.
  Where the masses' swing would pass its ``travel`` (their mean) or its
  ``turn`` (their difference over ``2 sides``), the whole clip's swing is
  scaled down to it, so through the limits below its peak is at most
  1/sqrt(2) of the stop and no tick jumps from one stop to the other (the first
  sitting's ladder, AZ-648); a ladder's swing still passes rest from
  near one stop toward the other about every 7.5 ticks (the re-sitting's
  skeptic, [inferred] from the offset's size alone).
  The masses' mean, through a soft limit of ``travel``, is the bone's
  translation; their difference over
  ``2 sides`` its roll (about the forward axis) and yaw (about up),
  each through the same limit at ``turn`` radians, keyed as the rest
  rotation's y and z components at half the angle (the pose normalises
  q; w keeps its rest 1).  Keys at ``keys`` per clip second, or six a
  cycle where the clip plays slower, with monotone tangents, so no curve
  overshoots its keys (a swing from one limit to the other is fast).
  Arithmetic is plain floats with ``sqrt`` the only function, in index
  order, so a build writes the same bytes on every machine.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, replace
from pathlib import Path

from azurkit.core import fdlibm
from azurkit.tools.characters import body_codec, mesh_edit, skeleton
from azurkit.tools.characters.characters import BoneRecord
from azurkit.tools.characters.retarget import Clip, Rig, Track, evaluate, qinv, qmul, _turn

Vec = tuple[float, float, float]
Quat = tuple[float, float, float, float]

DROP = 5e-4
"""The most a ``drop`` free may take from a vertex (weights under it
move a vertex at most 0.5 mm per metre of the bone's swing)."""
MIN_SHARE = 1e-3
"""A jiggle weight under this isn't written (the vertex keeps its own)."""
SIM_HZ = 120.0
"""How often (real time) the spring is stepped."""
SMOOTH_HZ = 6.0
"""The drive's smoothing: a binomial kernel of variance (SIM_HZ / (2 pi
SMOOTH_HZ))^2 samples, so a clip's tangent breaks don't spike it."""
GRAVITY = 9.8
"""m/s^2, divided by the body's drawn scale into model units."""
RELEASE = 0.25
"""Real seconds over which a one-shot clip's spring eases to rest at its
end (at most 0.4 of the clip), so the next clip, which starts at rest,
takes it there over the game's crossfade."""
LOOP_TOLERANCE = (0.02, 0.05)
"""How near (model units, and its world rotation's components) a
looping clip's parent chain must end to where it starts (:func:`closes`;
her own walk's seam is 5 mm and 0.018 off; a landing's 14 cm)."""
TAIL_CELL = 0.012
"""A cleared chain's points: one vertex a cell this wide (model units),
the nearest its centre (so a point between two misses her by under 2 mm
on a 2.5 cm tube)."""
SKIN_CELL = 0.015
"""The skin a chain is kept out of: one vertex a cell this wide."""
SKIN_REACH = 0.08
"""A chain point whose nearest skin point is farther than this is clear."""
SKIN_SPAN = 2.0
"""The skin taken: within this many times the chain's length of its root at
rest (bent over, her tail reaches her glutes)."""
CLEAR_TURN = 1.2
"""The most a link is turned (radians) to clear the body: the first about
either axis, one under it about both together (it bends on its parent)."""
CLEAR_NEAR = 0.03
"""A link's points tested while it turns: those within this of their least
distance before it turns (the rest only move away)."""


@dataclass(frozen=True)
class Free:
    """A palette entry emptied: ``bone``'s in mesh group ``group``,
    merged ``into`` its parent's or (``None``) dropped."""

    group: int
    bone: str
    into: str | None


@dataclass(frozen=True)
class Bone:
    """A jiggle bone: its ``role`` (its name in the log), the leaf
    ``bone`` it rewrites, its ``parent``, the push ops (by name) whose
    region it takes in the mesh ``groups`` it names (the first the skin;
    a vertex of another, a cloth layer over it, takes the share of the
    skin vertex nearest it in the edited shape, so the layer swings with
    it), the bones whose
    weights it ``takes`` (near-rigid with the parent: a limb's stay, so
    the reskin moves no vertex off its limb), the share of them it takes
    at a share of 1 (``weight``), and its spring (``drive``, the soft
    cap on its drive in model units/s^2, ``None`` for none); with a
    real-time ``spring`` (a :class:`~azurik_mod.assets.jiggle_rt.Spring`,
    Step 2.156) X41 drives it in game and no clip keys it (its baked
    fields unused); ``keyed`` (Step 2.168, D575) neither: only its
    recipe's own clips key it (a squish under a breast: a child of a
    spring's bone rides its swing), unkeyed it skins as its parent."""

    role: str
    bone: str
    parent: str
    shape: tuple[str, ...]
    groups: tuple[int, ...]
    takes: tuple[str, ...]
    weight: float
    freq: float
    damping: float
    travel: float
    turn: float
    hang: float = 1.0
    gain: float = 1.0
    drive: float | None = None
    spring: object | None = None
    grade: tuple[float, float, float] | None = None
    """(z from, z to, floor): the share times ``floor`` at or below the
    edited shape's height ``z from``, rising by a smoothstep to 1 at ``z
    to`` (Step 2.154: a glute's lower cheek follows the thigh)."""
    keyed: bool = False


@dataclass(frozen=True)
class Clear:
    """A recipe's ``jiggle.clear`` (Step 2.154b, D617): a chain of baked
    jiggle bones (``links``, by bone, root first, each the next's parent:
    a ponytail) kept out of the body: the vertices of mesh groups
    ``groups`` whose heaviest bone is one of ``bones`` (her skin; since
    Step 2.169c also her forearms' group, AZ-739: female_2's forearms and
    hands are a group of their own, so her slope slide put her ponytail
    through her forearm), by ``standoff`` model units, or as near as at
    rest where a point sits nearer there; in a clip ``clips`` names (by
    the last part of its name, as :class:`Spec`'s ``still``), out of only
    the groups it lists (Step 2.169c's review: in her landing's first
    frames the turn out of her raised forearm stood her tail straight up
    over her head and cleared nothing, so g4/touchdown keeps it out of
    her skin alone, as before AZ-739); in a clip ``held`` names (a death,
    whose last pose the game holds), solved from its end with each link
    turned for every point under it too (:class:`Collider`'s ``held``,
    Step 2.169d: lying dead in g4/die_2 her tail went up to 34 mm through
    her right forearm, where a turn held from her landing and links that
    clear only their own points left it), each link under a lifted one
    then turned back toward its unturned way as far as the tail under it
    stays out (Step 2.193, AZ-762: the first link's lift stood her whole
    tail 31 degrees up off the floor)."""

    links: tuple[str, ...]
    groups: tuple[int, ...]
    bones: tuple[str, ...]
    standoff: float = 0.004
    clips: tuple[tuple[str, tuple[int, ...]], ...] = ()
    held: tuple[str, ...] = ()


@dataclass(frozen=True)
class Spec:
    """A recipe's ``jiggle``: its ``frees``, ``bones``, key rate, the
    clips it keys no spring into (``still``: calm clips whose drive moves
    the forms a few millimetres, and whose places hold no more keys) and
    the clips the game cycles (``loops``), each by the last part of its
    name under the body (so a lent ``g4/`` clip and a build's copy of it
    are one); ``springs``, bones of the body as it is that X41 swings on
    real-time springs with no reskin (Step 2.156, D485: a chain's links;
    each a :class:`Bone` with a ``spring`` and no shape); ``clear``, a
    chain kept out of the body (:class:`Clear`)."""

    frees: tuple[Free, ...]
    bones: tuple[Bone, ...]
    keys: float = 15.0
    still: tuple[str, ...] = ()
    loops: tuple[str, ...] = ()
    springs: tuple[Bone, ...] = ()
    clear: Clear | None = None


@dataclass(frozen=True)
class Placed:
    """A jiggle bone as :func:`rig` wrote it: its index, its parent's,
    its bind origin, its sides' half-span, its rest translation, how many
    vertices it took by group and the largest weight it took."""

    bone: Bone
    index: int
    parent: int
    origin: Vec
    sides: float
    rest: Vec
    reach: dict
    largest: float


@dataclass(frozen=True)
class Rigged:
    """:func:`rig`'s result: the bones placed, the vertices whose fourth
    weight it folded (and the largest such weight), the entries each
    group's jiggle bones took (group -> [(entry, bone index)]), the bones
    whose weights it merged into their parents' (no clip may key them),
    and how many palette entries its frees emptied and how many it
    appended (a group with no freed entry left); its clear's collider, and
    one for each clip the clear names with its own groups (Step 2.169c)."""

    bones: tuple[Placed, ...]
    folded: int
    fold_largest: float
    entries: dict
    freed: tuple[int, ...]
    emptied: int
    added: int
    clear: Collider | None = None
    clip_clears: tuple[tuple[str, Collider], ...] = ()


@dataclass(frozen=True)
class Collider:
    """A :class:`Clear` made on the rigged body (:func:`collider`): the
    links' bone indices, the first one's pivot (a bone and the point in its
    inverse-bind frame: the chain's root, extrapolated one link up from the
    first two origins; each next link turns about the point halfway to its
    parent's origin, :func:`_clear`), and two point sets as numpy arrays,
    each point with four
    bones, weights and its place in each bone's inverse-bind frame (as
    the engine skins it): the chain's (from the vertices its links weigh,
    one per :data:`TAIL_CELL` cell, with the link weighing it most and
    the least signed distance it may come to) and the skin's (one per
    :data:`SKIN_CELL` cell within the chain's reach, with its normal);
    ``held`` for a held clip's (:class:`Clear`'s ``held``: :func:`_clear`
    from its last key back, each link turned for the points of the links
    under it too)."""

    links: tuple[int, ...]
    pivot: tuple[int, Vec]
    tail: dict
    skin: dict
    held: bool = False


def _slot_byte(entry: int) -> int:
    """A palette entry's slot code (``docs/RE_DATA.md``: b - 1 for 1-12, b - 2 for 14-32; past 30 the
    codec's wide code, which the write splits away)."""
    return body_codec.slot_code(entry)


def _entry(byte: int) -> int:
    return body_codec.code_entry(byte)


def _composed(rig: Rig) -> list[Vec]:
    """Each bone's origin in the model from its rest values (the pose at
    rest, as the engine composes it)."""
    out: list[Vec] = []
    for b in rig.bones:
        out.append(tuple(b.t) if b.parent < 0 else
                   tuple(p + d for p, d in zip(out[b.parent], _turn(rig.world[b.parent], b.t))))
    return out


def _rig_of(asset) -> Rig:
    """``asset``'s rig as :meth:`Rig.read` reads it from a file: each
    bone's record, its bind position (its inverse bind's, p M = 0) and
    its composed bind rotation."""
    bones, positions, world = [], [], []
    for b in asset.bones:
        f = struct.unpack_from("<18f", b.record, 0x10)
        rec = BoneRecord(b.name, struct.unpack_from("<h", b.record, 8)[0], bool(b.record[0xB]), f[0:4], f[4:8],
                         f[8:11], f[11:15], f[15:18])
        m = struct.unpack_from("<16f", b.record, 0x60)
        r0, r1, r2, t = m[0:3], m[4:7], m[8:11], m[12:15]
        det = _dot3(r2, _cross3(r0, r1))
        positions.append(tuple(-_dot3(t, _cross3(u, v)) / det for u, v in ((r1, r2), (r2, r0), (r0, r1))))
        local = qmul(qmul(rec.jo, rec.q), rec.ra)
        world.append(local if rec.parent < 0 else qmul(world[rec.parent], local))
        bones.append(rec)
    return Rig(asset.name, tuple(bones), tuple(positions), tuple(world), tuple(m.name for m in asset.markers))


def _cross3(a, b) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot3(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def rig(characters: bytearray, vanilla: bytes, body: str, spec: Spec, mesh: mesh_edit.MeshSpec,
        base_dir: Path | None = None, *, asset=None, at: dict | None = None, late: dict | None = None) -> Rigged:
    """W29: ``spec``'s bones, frees and reskin (module docstring) done on
    the body of ``characters`` (or on ``asset``, a body W24 assembled and
    hasn't written: a subdivided mesh, Step 2.154), after W24 (the shares
    read ``vanilla``'s positions, as the ops do), and the body written
    into ``characters`` in place
    (:func:`~azurik_mod.assets.body_codec.write_asset`: a group whose
    palette passes 31 is split); ``at``: {role: (origin, sides)}, the
    places a bone takes instead of its vertices' centroid (a recipe from
    another's, Step 2.177b); ``late``: {(group, index): move}, the plan's
    ``late`` scales' moves (:attr:`~azurik_mod.assets.mesh_edit.MeshPlan.late`,
    Step 2.187), taken off every position the rig reads, so they move no
    bone's place.  It rigs LOD 0; a body's LODs past it (garret4's LOD 1,
    which his realtime shadow draws: AZ-783) keep their skin, a leaf bone
    one of them weighs refused as LOD 0's are, and W39 cuts them anew from
    the rigged LOD 0 (:func:`~azurik_mod.patches._player_character.write_lods`:
    the recipe's mesh, which its bones' shapes need, asks it), so they swing
    as it does.  :class:`ValueError` names what blocks it
    (D35); ``characters`` is left as it was."""
    data = bytes(characters)
    if asset is None:
        asset = body_codec.read_asset(data, body)
    rig_ = _rig_of(asset)
    records = rig_.bones
    names = [b.name for b in records]
    index = {n: k for k, n in enumerate(names)}
    groups = asset.lods[0].groups
    children = {b.parent for b in records}
    used = {b for lod in asset.lods for g in lod.groups for b in g.palette}   # a leaf no LOD's mesh uses
    roles = set()
    earlier: set[str] = set()       # new bones the recipe adds before this one (a chain's links, Step 2.154 round 3)
    for i, jb in enumerate(spec.bones):
        where = f"jiggle.bones[{i}]"
        if jb.role in roles:
            raise ValueError(f"{where}.role {jb.role!r} is taken")
        roles.add(jb.role)
        if jb.parent not in index and jb.parent not in earlier:
            raise ValueError(f"{where}.parent: {body} has no bone {jb.parent!r} (nor does an earlier new jiggle bone)")
        if jb.bone not in index:
            earlier.add(jb.bone)
            continue                    # a new bone (Step 2.154, D444): added after the last, under its parent
        k = index[jb.bone]
        if k in children or k in used:
            raise ValueError(f"{where}.bone {jb.bone!r} has a child or weights a vertex: a leaf no mesh uses only")
        if index[jb.parent] >= k:
            raise ValueError(f"{where}.parent {jb.parent!r} comes after {jb.bone!r} in the bone table "
                             "(the engine poses a parent first)")
    if len({jb.bone for jb in spec.bones}) < len(spec.bones):
        raise ValueError("jiggle.bones: two take the same bone")
    for jb in spec.bones:
        if jb.bone not in index:
            if index[jb.parent] >= len(rig_.positions):        # its parent a link added just before it
                rig_ = _rig_of(asset)
            index[jb.bone] = skeleton.add_bone(asset, jb.bone, jb.parent, rig_.positions[index[jb.parent]])
    if len(asset.bones) > len(records):
        rig_ = _rig_of(asset)
        records = rig_.bones

    # the frees
    freed: dict[int, list[int]] = {}
    gone = []
    for i, f in enumerate(spec.frees):
        where = f"jiggle.frees[{i}]"
        if not 0 <= f.group < len(groups):
            raise ValueError(f"{where}.group: {body} has no LOD-0 group {f.group}")
        g = groups[f.group]
        if f.bone not in index or index[f.bone] not in g.palette:
            raise ValueError(f"{where}.bone {f.bone!r} isn't in group {f.group}'s palette")
        e = g.palette.index(index[f.bone])
        into = None
        if f.into is not None:
            if f.into not in index or index[f.into] not in g.palette:
                raise ValueError(f"{where}.into {f.into!r} isn't in group {f.group}'s palette")
            if records[index[f.bone]].parent != index[f.into] or index[f.bone] in children:
                raise ValueError(f"{where}: {f.bone!r} isn't a leaf child of {f.into!r}, so merging its weights "
                                 "isn't exact")
            into = g.palette.index(index[f.into])
        for j, v in enumerate(g.vertices):
            w = list(v.weights)
            slots = list(v.slots)
            mine = [s for s in range(4) if w[s] > 0 and _entry(slots[s]) == e]
            if not mine:
                continue
            if into is None:
                if max(w[s] for s in mine) >= DROP:
                    raise ValueError(f"{where}: {f.bone!r} weighs a vertex of group {f.group} "
                                     f"{max(w[s] for s in mine):.2g}, not under {DROP:g}: merge it into its parent")
                for s in mine:
                    w[s], slots[s] = 0.0, 0
            else:
                target = next((s for s in range(4) if w[s] > 0 and _entry(slots[s]) == into), None)
                for s in mine:
                    if target is None:
                        slots[s], target = _slot_byte(into), s
                    else:
                        w[target] += w[s]
                        w[s], slots[s] = 0.0, 0
            g.vertices[j] = _put(v, w, slots)
        freed.setdefault(f.group, []).append(e)
        if into is not None:
            gone.append(index[f.bone])

    # the shares and the reskin
    shares = {}
    late = late or {}
    plain = {(gi, j): _before(v.position, late.get((gi, j))) for gi, g in enumerate(groups)
             for j, v in enumerate(g.vertices)}   # the shape as edited, before its late moves (Step 2.187)
    riders = mesh_edit.followers(vanilla, body, mesh, base_dir) if mesh is not None else {}
    rides: dict = {}    # _ridden's rides, kept for every bone
    try:
        fields = mesh_edit.shares_each(vanilla, body, mesh, [jb.shape for jb in spec.bones], base_dir)
    except mesh_edit.SharesError as exc:
        raise ValueError(f"jiggle.bones[{exc.index}].shape: {exc}") from None
    under: dict[int, dict] = {}   # a skin group: each cloth vertex's nearest skin vertex, for every bone (Step 2.176)
    for jb, field in zip(spec.bones, fields):
        mine = {vid: x for vid, x in field.items() if vid[0] == jb.groups[0]}
        cloth = [vid for vid in plain if vid[0] in jb.groups[1:] and vid in field]
        # a cloth layer swings with the skin under it: the skin vertex nearest it now (ties to the lower vertex)
        known = under.setdefault(jb.groups[0], {})
        ask = [vid for vid in cloth if vid not in known]
        if ask:
            skin = [(vid, plain[vid]) for vid in plain if vid[0] == jb.groups[0]]
            nearest = mesh_edit._nearest([p for _, p in skin], [plain[vid] for vid in ask],
                                         lambda j, p: (fdlibm.sq(skin[j][1][0] - p[0]) + fdlibm.sq(skin[j][1][1] - p[1])
                                                       + fdlibm.sq(skin[j][1][2] - p[2]), skin[j][0]))
            known.update((vid, skin[j][0]) for vid, j in zip(ask, nearest))
        for vid in cloth:
            if known[vid] in mine:
                mine[vid] = mine[known[vid]]
        mine.update(_ridden(riders, mine, plain, set(jb.groups), rides))
        if jb.grade is not None:
            z0, z1, floor = jb.grade
            for vid in mine:
                x = (plain[vid][2] - z0) / (z1 - z0)
                mine[vid] *= floor + (1.0 - floor) * (0.0 if x <= 0.0 else 1.0 if x >= 1.0 else x * x * (3.0 - 2.0 * x))
        shares[jb.role] = mine
    entries: dict[int, list[tuple[int, int]]] = {}
    added = 0
    for gi, g in enumerate(groups):
        reach = [jb for jb in spec.bones if any(
            (gi, j) in shares[jb.role] and jb.weight * shares[jb.role][gi, j] >= MIN_SHARE
            for j in range(len(g.vertices)))]
        if not reach:
            continue
        free = list(freed.get(gi, []))
        while len(free) < len(reach):      # no freed entry left: a new one (the write splits a group past 31)
            g.palette.append(-1)
            free.append(len(g.palette) - 1)
            added += 1
        entries[gi] = [(free[n], index[jb.bone]) for n, jb in enumerate(reach)]
        for e, k in entries[gi]:
            g.palette[e] = k
    takes = {}
    jiggled = {jb.bone for jb in spec.bones}
    later = []                          # bones taking from their parent jiggle bone: a second pass (Step 2.168)
    for i, jb in enumerate(spec.bones):
        for name in jb.takes:
            if name not in index:
                raise ValueError(f"jiggle.bones[{i}].takes: {body} has no bone {name!r}")
            if name in jiggled and (name != jb.parent or i <= [b.bone for b in spec.bones].index(name)):
                raise ValueError(f"jiggle.bones[{i}].takes: {name!r} is a jiggle bone; a bone takes from one only "
                                 "as its parent, listed before it")
        if jiggled & set(jb.takes):
            later.append(jb.role)
        takes[jb.role] = {index[n] for n in jb.takes}
    depth = {}
    for k, b in enumerate(records):
        depth[k] = 0 if b.parent < 0 else depth[b.parent] + 1
    folded, fold_largest = 0, 0.0
    taken: dict[str, list[tuple[float, Vec]]] = {jb.role: [] for jb in spec.bones}
    reach_by: dict[str, dict[int, int]] = {jb.role: {} for jb in spec.bones}
    for phase in (False, True):   # the bones taking from the body's bones, then those taking from their parent's
        for gi, g in enumerate(groups):
            if gi not in entries:
                continue
            slot_of = {k: e for e, k in entries[gi]}
            for j, v in enumerate(g.vertices):
                mine = [(jb, shares[jb.role].get((gi, j), 0.0)) for jb in spec.bones
                        if index[jb.bone] in slot_of and (jb.role in later) == phase]
                mine = [(jb, x) for jb, x in mine if x > 0.0]
                if not mine:
                    continue
                w = v.weights
                have: dict[int, float] = {}
                for s in range(4):
                    if w[s] > 0:
                        have[_entry(v.slots[s])] = have.get(_entry(v.slots[s]), 0.0) + w[s]
                gets = []
                for jb, share in mine:
                    src = [e for e in have if g.palette[e] in takes[jb.role]]
                    part = min(jb.weight * share, sum(have[e] for e in src))
                    if part >= MIN_SHARE:
                        gets.append((jb, share, src))
                if not gets:
                    continue
                while len(have) + len(gets) > 4:   # room for the bones: fold a taken weight into another taken, else
                    src = sorted({e for _, _, es in gets for e in es if e in have}, key=lambda e: (have[e], e))
                    if len(src) > 1:                # the smallest weight it doesn't take into its nearest relative
                        small, rest = src[0], src[1:]
                    else:
                        small = min((e for e in have if e not in src), key=lambda e: (have[e], e))
                        rest = [e for e in have if e != small]
                    near = min(rest, key=lambda e: (_hops(records, depth, g.palette[small], g.palette[e]), -have[e], e))
                    fold_largest = max(fold_largest, have[small])
                    have[near] += have.pop(small)
                    folded += 1
                new = dict(have)
                p = plain[gi, j]
                for jb, share, _ in gets:
                    src = [e for e in new if g.palette[e] in takes[jb.role]]
                    held = sum(new[e] for e in src)
                    # bones taking from the same bones (a breast each, Step 2.154) split what those hold by what
                    # they ask
                    asked = sum(o.weight * s for o, s, _ in gets if takes[o.role] & takes[jb.role])
                    was = sum(have[e] for e in have if g.palette[e] in takes[jb.role])
                    mine_share = jb.weight * share
                    part = min(mine_share * was / asked if asked > mine_share and asked > was else mine_share, held)
                    if not part > 0.0:
                        continue
                    x = 0.0
                    for e in src:   # the same weight wherever the taken bones hold enough: a layer and its skin alike
                        give = new[e] * part / held
                        new[e] -= give
                        x += give
                    e = slot_of[index[jb.bone]]
                    new[e] = new.get(e, 0.0) + x
                    taken[jb.role].append((x, p))
                    reach_by[jb.role][gi] = reach_by[jb.role].get(gi, 0) + 1
                order = sorted(((e, x) for e, x in new.items() if x > 0.0), key=lambda kv: (-kv[1], kv[0]))
                weights = [x for _, x in order] + [0.0] * (4 - len(order))
                slots = [_slot_byte(e) for e, _ in order] + [0] * (4 - len(order))
                g.vertices[j] = _put(v, weights, slots)

    # the records
    worlds, origins = rig_.world, _composed(rig_)
    placed = []
    for jb in spec.bones:
        k, p = index[jb.bone], index[jb.parent]
        pts = taken[jb.role]
        if not pts:
            raise ValueError(f"jiggle: {jb.role}'s shape {list(jb.shape)} reaches no vertex of a group with a "
                             "freed entry")
        mass = sum(x for x, _ in pts)
        origin = tuple(sum(x * q[c] for x, q in pts) / mass for c in range(3))
        sides = sum(x * abs(q[0] - origin[0]) for x, q in pts) / mass
        if at and jb.role in at:
            origin, sides = at[jb.role]
        jo = qinv(worlds[p])
        rest = _turn(jo, tuple(a - b for a, b in zip(origin, origins[p])))
        rec = bytearray(asset.bones[k].record)
        struct.pack_into("<h", rec, 8, p)
        struct.pack_into("<4f", rec, 0x10, 0.0, 0.0, 0.0, 1.0)
        struct.pack_into("<4f", rec, 0x20, *jo)
        struct.pack_into("<3f", rec, 0x30, *rest)
        struct.pack_into("<4f", rec, 0x3C, 0.0, 0.0, 0.0, 1.0)
        struct.pack_into("<3f", rec, 0x4C, 1.0, 1.0, 1.0)
        struct.pack_into("<16f", rec, 0x60, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0,
                         -origin[0], -origin[1], -origin[2], 1.0)
        asset.bones[k] = body_codec.Bone(asset.bones[k].name, bytes(rec))
        placed.append(Placed(jb, k, p, origin, sides, tuple(rest), dict(reach_by[jb.role]),
                             max(x for x, _ in pts)))
        if any(other.parent == jb.bone for other in spec.bones):     # a chain's next link reads this one placed
            rig_ = _rig_of(asset)
            worlds, origins = rig_.world, _composed(rig_)
    _check(asset, placed)
    clear, clip_clears = None, ()
    if spec.clear is not None:
        groups_ = [(g.palette, [(v.position, v.normal, v.weights, tuple(_entry(s) for s in v.slots))
                                for v in g.vertices]) for g in groups]
        binds = [struct.unpack_from("<16f", b.record, 0x60) for b in asset.bones]
        made = {gs: collider(_rig_of(asset), binds, groups_, placed, replace(spec.clear, groups=gs))
                for gs in {spec.clear.groups, *(gs for _, gs in spec.clear.clips)}}
        own = dict(spec.clear.clips)
        clear = made[spec.clear.groups]
        clip_clears = tuple((c, replace(made[gs], held=True) if c in spec.clear.held else made[gs])
                            for c, gs in spec.clear.clips) + tuple(
            (c, replace(clear, held=True)) for c in spec.clear.held if c not in own)   # Step 2.169d
    _hang(groups, riders)
    characters[:] = body_codec.write_asset(data, asset)
    return Rigged(tuple(placed), folded, fold_largest, entries, tuple(gone),
                  sum(len(v) for v in freed.values()), added, clear, clip_clears)


def _ib(m, v, move: bool = True) -> Vec:
    """``v`` through the inverse bind ``m`` (16 floats, row vectors: the
    engine's skinning), or its turn alone."""
    return tuple(v[0] * m[j] + v[1] * m[4 + j] + v[2] * m[8 + j] + (m[12 + j] if move else 0.0) for j in range(3))


def _points(rows, binds, normals: bool) -> dict:
    """Point rows (position, normal, four weights, four bones) as numpy
    arrays: bones ``B``, weights ``W``, each place in its bone's inverse-bind
    frame ``U`` (and normal ``UN``)."""
    import numpy as np
    out = {"B": np.array([r[3] for r in rows], dtype=np.int64).reshape(-1, 4),
           "W": np.array([r[2] for r in rows], dtype=np.float64).reshape(-1, 4),
           "U": np.array([[_ib(binds[b], r[0]) for b in r[3]] for r in rows], dtype=np.float64).reshape(-1, 4, 3)}
    if normals:
        out["UN"] = np.array([[_ib(binds[b], r[1], False) for b in r[3]] for r in rows],
                             dtype=np.float64).reshape(-1, 4, 3)
    return out


def _matrix(q: Quat) -> tuple:
    x, y, z, w = q
    return ((1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)),
            (2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)),
            (2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)))


def _skinned(pts: dict, R, O, sel=None, normals: bool = False):
    """``pts`` (or rows ``sel`` of them) skinned by the bones' world
    rotations ``R`` (3x3 each) and origins ``O`` (numpy, by bone): positions,
    or unit normals.  Element-wise in a fixed order, so every machine sums
    alike."""
    import numpy as np
    B, W, U = pts["B"], pts["W"], pts["UN" if normals else "U"]
    if sel is not None:
        B, W, U = B[sel], W[sel], U[sel]
    out = np.zeros((len(B), 3))
    for s in range(4):
        r, u, w = R[B[:, s]], U[:, s], W[:, s]
        for c in range(3):
            turned = r[:, c, 0] * u[:, 0] + r[:, c, 1] * u[:, 1] + r[:, c, 2] * u[:, 2]
            out[:, c] += w * (turned if normals else O[B[:, s], c] + turned)
    if normals:
        out /= np.sqrt(out[:, 0] * out[:, 0] + out[:, 1] * out[:, 1] + out[:, 2] * out[:, 2])[:, None]
    return out


def _signed(P, X, N):
    """Each point of ``P``'s signed distance from the skin points ``X``
    (normals ``N``): along the nearest one's normal (inf past
    :data:`SKIN_REACH`; its distance where the point lies more than
    :data:`SKIN_CELL` aside of it and more aside than over or under it: past
    an edge, not over or under the skin), and that normal."""
    import numpy as np
    box = np.all((X >= P.min(0) - SKIN_REACH) & (X <= P.max(0) + SKIN_REACH), axis=1)   # the rest are out of reach
    if not box.any():
        return np.full(len(P), np.inf), np.zeros((len(P), 3))
    X, N = X[box], N[box]
    dx, dy, dz = (P[:, None, c] - X[None, :, c] for c in range(3))
    d2 = dx * dx + dy * dy + dz * dz
    j = np.argmin(d2, axis=1)
    near = d2[np.arange(len(P)), j]
    d = (P[:, 0] - X[j, 0]) * N[j, 0] + (P[:, 1] - X[j, 1]) * N[j, 1] + (P[:, 2] - X[j, 2]) * N[j, 2]
    aside = near - d * d
    beside = (aside > SKIN_CELL * SKIN_CELL) & (aside > d * d)   # past an edge, not over or under the skin: out
    d = np.where(beside, np.sqrt(near), d)
    d = np.where(near <= SKIN_REACH * SKIN_REACH, d, np.inf)
    return d, N[j]


def _cells(rows, cell: float) -> list:
    """One row a ``cell``-wide cube, the nearest its centre (ties to the
    first), in the cubes' order."""
    best = {}
    for n, r in enumerate(rows):
        p = r[0]
        key = (math.floor(p[0] / cell), math.floor(p[1] / cell), math.floor(p[2] / cell))
        d = sum(fdlibm.sq(p[c] - (key[c] + 0.5) * cell) for c in range(3))
        if key not in best or (d, n) < best[key][0]:
            best[key] = ((d, n), r)
    return [best[k][1] for k in sorted(best)]


def _rest(rig_: Rig):
    import numpy as np
    R, O = np.zeros((len(rig_.bones), 3, 3)), np.zeros((len(rig_.bones), 3))
    for k, (q, o) in enumerate(zip(rig_.world, _composed(rig_))):
        R[k], O[k] = _matrix(q), o
    return R, O


def collider(rig_: Rig, binds, groups, placed, clear: Clear) -> Collider:
    """``clear`` made on a rigged body (:class:`Collider`): ``rig_`` its
    bones, ``binds`` their inverse binds (16 floats each), ``groups`` each
    LOD-0 group's (palette, [(position, normal, weights, palette entries)]),
    ``placed`` the jiggle bones as :func:`rig` placed them.
    :class:`ValueError` names a link that isn't a baked jiggle bone, a
    chain that isn't one, a group or bone the body hasn't."""
    import numpy as np
    names = [b.name for b in rig_.bones]
    by_bone = {pl.bone.bone: pl for pl in placed}
    chain = []
    for c, name in enumerate(clear.links):
        pl = by_bone.get(name)
        if pl is None or pl.bone.spring is not None or pl.bone.keyed:
            raise ValueError(f"jiggle.clear.links[{c}]: {name!r} is no baked jiggle bone")
        if c and pl.parent != chain[-1].index:
            raise ValueError(f"jiggle.clear.links[{c}]: {name!r}'s parent isn't {clear.links[c - 1]!r}")
        if c and pl.bone.freq != chain[0].bone.freq:
            raise ValueError(f"jiggle.clear.links[{c}]: {name!r}'s freq isn't {clear.links[0]!r}'s (one key rate)")
        chain.append(pl)
    if not chain:
        raise ValueError("jiggle.clear.links: none")
    for g in clear.groups:
        if not 0 <= g < len(groups):
            raise ValueError(f"jiggle.clear.group: no LOD-0 group {g}")
    body = set()
    for i, name in enumerate(clear.bones):
        if name not in names:
            raise ValueError(f"jiggle.clear.bones[{i}]: no bone {name!r}")
        body.add(names.index(name))
    links = [pl.index for pl in chain]
    o = [pl.origin for pl in chain]
    root = tuple(2.0 * a - b for a, b in zip(o[0], o[1])) if len(o) > 1 else o[0]
    pivot = (chain[0].parent, _ib(binds[chain[0].parent], root))
    tail, skin = [], []
    for gi, (palette, verts) in enumerate(groups):
        for p, n, w, entries in verts:
            bones = tuple(palette[e] if x > 0.0 else 0 for e, x in zip(entries, w))
            row = (p, n, tuple(x if x > 0.0 else 0.0 for x in w), bones)
            on = sum(x for b, x in zip(bones, row[2]) if b in links)
            if on >= 0.5:   # a point its links move (one riding the parent more is the parent's)
                tail.append(row)
            elif on > 0.0:
                continue
            elif gi in clear.groups and bones[max(range(4), key=lambda s: (row[2][s], -s))] in body:
                skin.append(row)
    if not tail:
        raise ValueError("jiggle.clear.links: they weigh no vertex half or more")
    tail = _cells(tail, TAIL_CELL)
    span = SKIN_SPAN * max(math.dist(root, r[0]) for r in tail)
    skin = _cells([r for r in skin if math.dist(root, r[0]) <= span], SKIN_CELL)
    if not skin:
        raise ValueError(f"jiggle.clear: groups {list(clear.groups)} have no vertex of its bones within the chain's "
                         "reach")
    t, s = _points(tail, binds, False), _points(skin, binds, True)
    owner = []
    for r in tail:
        on = [max((x for b, x in zip(r[3], r[2]) if b == k), default=0.0) for k in links]
        owner.append(max(range(len(links)), key=lambda c: (on[c], -c)))
    t["owner"] = np.array(owner, dtype=np.int64)
    R, O = _rest(rig_)
    d, _ = _signed(_skinned(t, R, O), _skinned(s, R, O), _skinned(s, R, O, normals=True))
    t["target"] = np.minimum(d, clear.standoff)
    return Collider(tuple(links), pivot, t, s)


def _ridden(riders: dict, mine: dict, plain: dict, groups: set[int], rides: dict | None = None) -> dict:
    """A tube's vertices that ride the skin (``follow`` and ``reach``,
    :func:`~azurik_mod.assets.mesh_edit.followers`; Step 2.154 round 10,
    D582): each one's share the mix of ``mine`` (0 where a vertex has none)
    over the vertices of the groups it follows within its reach in the
    edited shape, by (1 - d^2 / reach^2)^2, as W24 mixed their weights, the
    nearest alone where none is in reach; only those above 0.  ``rides``
    keeps :func:`_rides` by (follow, reach) for the next bone's call on
    the same ``riders`` and ``plain`` (Step 2.176: they don't depend on
    ``mine``)."""
    out = {}
    keys = sorted({v[:2] for v in riders.values() if groups & set(v[0])})
    for follow, reach in keys:
        got = None if rides is None else rides.get((follow, reach))
        if got is None:
            got = _rides(riders, plain, follow, reach)
            if rides is not None:
                rides[follow, reach] = got
        for vid, near, total, best in got:
            mixed = 0.0
            for j, w in near:
                mixed += w * mine.get(j, 0.0)
            if total == 0.0 and best is not None:
                total, mixed = 1.0, mine.get(best[1], 0.0)
            if total > 0.0 and mixed > 0.0:
                out[vid] = mixed / total
    return out


def _rides(riders: dict, plain: dict, follow: tuple[int, ...], reach: float) -> list:
    """Each vertex of ``riders`` that follows ``follow`` within ``reach``
    (in order): the vertices of those groups in its reach in the order
    :func:`_ridden` mixes them, each with its weight (1 - d^2 /
    reach^2)^2, their weights' sum, and the nearest of them all (its
    squared distance and vertex, or ``None``)."""
    cell = reach
    grid: dict[tuple[int, int, int], list[tuple[int, int]]] = {}
    for vid in sorted(plain):
        if vid[0] in follow and vid not in riders:
            p = plain[vid]
            key = (math.floor(p[0] / cell), math.floor(p[1] / cell), math.floor(p[2] / cell))
            grid.setdefault(key, []).append(vid)
    r2 = reach * reach
    out = []
    for vid in sorted(v for v, f in riders.items() if f[:2] == (follow, reach)):
        q = plain[vid]
        ci = (math.floor(q[0] / cell), math.floor(q[1] / cell), math.floor(q[2] / cell))
        total, near = 0.0, []
        best, span = None, 1
        while total == 0.0 and span <= 8:
            for a in range(-span, span + 1):
                for b in range(-span, span + 1):
                    for c in range(-span, span + 1):
                        for j in grid.get((ci[0] + a, ci[1] + b, ci[2] + c), ()):
                            p = plain[j]
                            d = fdlibm.sq(p[0] - q[0]) + fdlibm.sq(p[1] - q[1]) + fdlibm.sq(p[2] - q[2])
                            if d < r2:
                                w = fdlibm.sq(1.0 - d / r2)
                                total += w
                                near.append((j, w))
                            if best is None or (d, j) < best:
                                best = (d, j)
            span *= 2
        out.append((vid, near, total, best))
    return out


def _before(p, move) -> tuple[float, float, float]:
    """``p`` with a late scale's ``move`` taken off (Step 2.187), or as it is."""
    return tuple(p) if move is None else (p[0] - move[0], p[1] - move[1], p[2] - move[2])


def _hang(groups, riders: dict) -> None:
    """Every vertex of the tubes hung under one name (a ``tube``'s ``hang``,
    ``riders``' third field; Step 2.168r) given one weight set, the mean of
    their weights by bone, its four heaviest renormalized, so a pendant moves
    as one piece; after the reskin and the bones' places, which keep their
    own weights' (a pendant across a cleavage took each breast on its own
    side, and stretched as they moved apart)."""
    hung: dict[str, list[tuple[int, int]]] = {}
    for vid, (*_, name) in sorted(riders.items()):
        if name:
            hung.setdefault(name, []).append(vid)
    for name, vids in hung.items():
        mean: dict[int, float] = {}
        for gi, j in vids:
            g = groups[gi]
            for w, slot in zip(g.vertices[j].weights, g.vertices[j].slots):
                if w > 0:
                    bone = g.palette[_entry(slot)]
                    mean[bone] = mean.get(bone, 0.0) + w / len(vids)
        top = sorted(mean.items(), key=lambda kv: (-kv[1], kv[0]))[:4]
        total = sum(x for _, x in top)
        for gi, j in vids:
            g = groups[gi]
            entry = {bone: e for e, bone in enumerate(g.palette)}
            missing = [bone for bone, _ in top if bone not in entry]
            if missing:
                raise ValueError(f"jiggle: the tubes hung as {name!r} span groups: group {gi}'s palette has no bone "
                                 f"{missing[0]}")
            g.vertices[j] = _put(g.vertices[j], [x / total for _, x in top], [_slot_byte(entry[b]) for b, _ in top])


def _hops(records, depth: dict[int, int], a: int, b: int) -> int:
    """How many parent links join bones ``a`` and ``b``."""
    n = 0
    while a != b:
        if a < 0 or b < 0:   # two root trees: never near
            return len(records)
        if depth[a] >= depth[b]:
            a = records[a].parent
        else:
            b = records[b].parent
        n += 1
    return n


def _put(v, weights, slots):
    """``v`` with four weights (float32, the heaviest absorbing the
    rounding so they sum to 1 within 1e-6) and slot codes, heaviest first
    (vanilla's rule: slot 0 the heaviest)."""
    pairs = sorted(((struct.unpack("<f", struct.pack("<f", x))[0], b) for x, b in zip(weights, slots) if x > 0),
                   key=lambda xb: (-xb[0], xb[1]))
    if pairs:
        rest = sum(x for x, _ in pairs[1:])
        pairs[0] = (struct.unpack("<f", struct.pack("<f", 1.0 - rest))[0], pairs[0][1])
        pairs.sort(key=lambda xb: (-xb[0], xb[1]))
    pairs += [(0.0, 0)] * (4 - len(pairs))
    return body_codec.Vertex(v.position, tuple(x for x, _ in pairs), v.normal, v.uv, v.extra, tuple(b for _, b in pairs))


def _check(asset, placed: list[Placed]) -> None:
    """Each jiggle bone at rest skins as the identity (its composed rest
    world against its inverse bind), and every rewritten vertex's weights
    sum to 1 within 1e-6 (D35 if not)."""
    rig_ = _rig_of(asset)
    origins = _composed(rig_)
    for pl in placed:
        w = rig_.world[pl.index]
        o = origins[pl.index]
        err = max(max(abs(a - b) for a, b in zip(_turn(w, ax), ax)) for ax in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
                                                                              (0.0, 0.0, 1.0)))
        err = max(err, max(abs(a - b) for a, b in zip(o, pl.origin)))
        if err > 1e-5:
            raise ValueError(f"jiggle: {pl.bone.role}'s record doesn't put it at its origin at rest ({err:.2g})")
    for gi, g in enumerate(asset.lods[0].groups):
        for j, v in enumerate(g.vertices):
            if any(x > 0 for x in v.weights) and abs(sum(v.weights) - 1.0) > 1e-6:
                raise ValueError(f"jiggle: group {gi} vertex {j}'s weights sum to {sum(v.weights):.7f}")


# --------------------------------------------------------------------------- the spring
def _chain(rig: Rig, k: int) -> list[int]:
    out = []
    while k >= 0:
        out.append(k)
        k = rig.bones[k].parent
    return out[::-1]


def _posed(rig: Rig, clip: Clip, chain: list[int]):
    """A function of clip time: the last bone of ``chain`` (root first)'s
    posed world rotation and origin, by the engine model on the chain
    alone (:func:`~azurik_mod.assets.retarget.pose`, ``origins``)."""
    rot: dict[int, dict[int, tuple]] = {}
    tra: dict[int, dict[int, tuple]] = {}
    mine = set(chain)
    for tr in clip.bones:
        if tr.target in mine:
            if 3 <= tr.comp <= 6:
                rot.setdefault(tr.target, {})[tr.comp - 3] = tr.keys
            elif tr.comp <= 2:
                tra.setdefault(tr.target, {})[tr.comp] = tr.keys

    def at(t: float) -> tuple[Quat, Vec]:
        world, origin = None, None
        for k in chain:
            b = rig.bones[k]
            comps = rot.get(k, {})
            q = tuple(evaluate(comps[c], t) if c in comps else b.q[c] for c in range(4))
            n = math.sqrt(sum(c * c for c in q)) or 1.0
            local = qmul(qmul(b.jo, tuple(c / n for c in q)), b.ra)
            tc = tra.get(k, {})
            tl = tuple(evaluate(tc[c], t) if c in tc else b.t[c] for c in range(3))
            if world is None:
                world, origin = local, tl
            else:
                origin = tuple(o + d for o, d in zip(origin, _turn(world, tl)))
                world = qmul(world, local)
        return world, origin
    return at


def _binomial(n: int) -> list[int]:
    row = [1]
    for _ in range(n):
        row = [a + b for a, b in zip([0, *row], [*row, 0])]
    return row


def _smooth(samples: list[Vec], loop: bool, kernel: list[int]) -> list[Vec]:
    half, total, n = len(kernel) // 2, sum(kernel), len(samples)
    out = []
    for i in range(n):
        acc = [0.0, 0.0, 0.0]
        for j, c in enumerate(kernel):
            m = i + j - half
            m = m % (n - 1) if loop else min(max(m, 0), n - 1)   # a loop's last sample is its first
            p = samples[m]
            acc[0] += c * p[0]
            acc[1] += c * p[1]
            acc[2] += c * p[2]
        out.append((acc[0] / total, acc[1] / total, acc[2] / total))
    return out


def _limit(u: float, cap: float) -> float:
    return u / math.sqrt(1.0 + (u / cap) * (u / cap))


def _vlimit(v: Vec, cap: float) -> Vec:
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if n == 0.0:
        return v
    s = _limit(n, cap) / n
    return (v[0] * s, v[1] * s, v[2] * s)


def closes(rig: Rig, clip: Clip, parents: list[int]) -> bool:
    """Whether ``clip`` ends where it starts on each parent's chain (its
    world rotation and origin within :data:`LOOP_TOLERANCE`), as a clip
    whose spring runs as a loop must."""
    for p in parents:
        at = _posed(rig, clip, _chain(rig, p))
        (q0, o0), (q1, o1) = at(0.0), at(clip.length)
        same = min(max(abs(a - b) for a, b in zip(q0, q1)), max(abs(a + b) for a, b in zip(q0, q1)))
        if same > LOOP_TOLERANCE[1] or max(abs(a - b) for a, b in zip(o0, o1)) > LOOP_TOLERANCE[0]:
            return False
    return True


def keyed(rig: Rig, clip: Clip, placed: tuple[Placed, ...], keys: float, rate: float, drawn: float,
          loop: bool | set, clear: Collider | None = None) -> tuple[Clip, dict]:
    """``clip`` with each placed bone's spring keyed (module docstring),
    played at ``rate`` (clip seconds a real second) by a body drawn at
    ``drawn``, as a loop or not (or a set: the bones that loop, the rest
    one-shots), its chain kept out of the body by ``clear``
    (:func:`_clear`) where every link of it is baked here (a recipe's own
    clip that keys them, Step 2.168, poses the chain itself: the whip's);
    and per role the largest translation and
    angle its spring keys (model units, radians).  :class:`ValueError`
    where the clip keys a jiggle bone already."""
    jiggles = {pl.index for pl in placed}
    if any(tr.target in jiggles for tr in clip.bones):
        raise ValueError("it keys a jiggle bone already")
    g = GRAVITY / drawn
    length = clip.length
    home = _composed(rig)
    tracks: list[Track] = []
    flats = []
    peaks = {}
    loops = loop
    for pl in placed:
        jb = pl.bone
        loop = loops if isinstance(loops, bool) else pl.index in loops     # a set: the bones that loop (Step 2.154)
        omega = 2.0 * math.pi * jb.freq
        rate_hz = max(keys, 6.0 * jb.freq / rate)
        n_keys = max(2, math.ceil(length * rate_hz - 1e-9) + 1)
        h = length / (n_keys - 1)
        sub = max(1, math.ceil(h / (rate / SIM_HZ) - 1e-9))
        dtau = h / sub
        dt = dtau / rate
        n = (n_keys - 1) * sub + 1
        at = _posed(rig, clip, _chain(rig, pl.parent))
        bind = rig.world[pl.parent]
        sides = [_turn(qinv(bind), (pl.origin[0] + sign * pl.sides - home[pl.parent][0],
                                    pl.origin[1] - home[pl.parent][1], pl.origin[2] - home[pl.parent][2]))
                 for sign in (-1.0, 1.0)]
        rel, anchors = [], ([], [])
        for i in range(n):
            w, o = at(dtau * i)
            rel.append(qmul(w, qinv(bind)))   # the parent turned from its bind, in the model
            for s in range(2):
                anchors[s].append(tuple(a + b for a, b in zip(o, _turn(w, sides[s]))))
        sigma = 1.0 / (2.0 * math.pi * SMOOTH_HZ * dt)
        kernel = _binomial(max(2, round(4.0 * sigma * sigma)))
        drives = []
        for s in range(2):
            path_s = anchors[s]
            if loop:   # close the seam by a line (no acceleration of its own), so it kicks the spring nowhere
                gap = tuple(b - a for a, b in zip(path_s[0], path_s[-1]))
                path_s = [tuple(c - gap[k] * i / (n - 1) for k, c in enumerate(q)) for i, q in enumerate(path_s)]
            pts = _smooth(path_s, loop, kernel)
            d = []
            for i in range(n):
                if loop:
                    a0, a2 = pts[(i - 1) % (n - 1)], pts[(i + 1) % (n - 1)]
                else:
                    a0, a2 = pts[max(i - 1, 0)], pts[min(i + 1, n - 1)]
                if not loop and (i == 0 or i == n - 1):
                    acc = None
                else:
                    acc = tuple((x + z - 2.0 * y) / (dtau * dtau) for x, y, z in zip(a0, pts[i], a2))
                d.append(acc)
            if not loop:   # the ends hold their neighbours' (one-sided)
                d[0], d[-1] = d[1] if n > 2 else (0.0, 0.0, 0.0), d[-2] if n > 2 else (0.0, 0.0, 0.0)
            # in the parent's frame against its bind: gravity less the anchor's acceleration, less rest's sag
            drive = []
            for i in range(n):
                acc = d[i] or (0.0, 0.0, 0.0)
                inv = qinv(rel[i])
                f = _turn(inv, (-jb.gain * acc[0], -jb.gain * acc[1], -jb.gain * acc[2]))
                down = _turn(inv, (0.0, 0.0, -g))
                u = (f[0] + jb.hang * down[0], f[1] + jb.hang * down[1], f[2] + jb.hang * (down[2] + g))
                drive.append(u if jb.drive is None else _vlimit(u, jb.drive))
            drives.append(drive)
        state = [[(0.0, 0.0, 0.0), (0.0, 0.0, 0.0)] for _ in range(2)]
        passes = 3 if loop else 1
        path = [[None] * n for _ in range(2)]
        for pas in range(passes):
            for s in range(2):
                x, v = state[s]
                for i in range(n):
                    if pas == passes - 1:
                        path[s][i] = (x, v)
                    if i == n - 1:
                        break
                    dv = tuple(drives[s][i][c] - omega * omega * x[c] - 2.0 * jb.damping * omega * v[c]
                               for c in range(3))
                    v = tuple(v[c] + dt * dv[c] for c in range(3))
                    x = tuple(x[c] + dt * v[c] for c in range(3))
                state[s] = [x, v]
        if loop:   # the seam: the last pass's end is its start
            for s in range(2):
                path[s][-1] = path[s][0]
        span = 2.0 * pl.sides if pl.sides > 0 else 1.0
        wide = max(math.sqrt(sum(fdlibm.sq((a + b) / 2.0) for a, b in zip(path[0][i][0], path[1][i][0])))
                   for i in range(n))
        turned = max(max(abs(path[0][i][0][2] - path[1][i][0][2]), abs(path[1][i][0][1] - path[0][i][0][1])) / span
                     for i in range(n))
        fit = min(1.0, jb.travel / wide if wide > jb.travel else 1.0, jb.turn / turned if turned > jb.turn else 1.0)
        if fit < 1.0:   # the whole swing scaled to its stops, which the limits then cap at 1/sqrt(2) of them
            path = [[(tuple(fit * c for c in x), v) for x, v in path[s]] for s in range(2)]

        release = 0.0 if loop else min(RELEASE * rate, 0.4 * length)

        def pose_at(i: int):
            (xl, _), (xr, _) = path[0][i], path[1][i]
            k = 1.0
            if release > 0.0 and dtau * i > length - release:   # a one-shot eases to rest by its end
                u = (length - dtau * i) / release
                k = u * u * (3.0 - 2.0 * u)
            mean = tuple(k * c for c in _vlimit(tuple((a + b) / 2.0 for a, b in zip(xl, xr)), jb.travel))
            roll = k * _limit((xl[2] - xr[2]) / span, jb.turn)
            yaw = k * _limit((xr[1] - xl[1]) / span, jb.turn)
            return mean, roll, yaw
        values = [pose_at(i) for i in range(n)]
        peaks[jb.role] = (max(math.sqrt(sum(c * c for c in m)) for m, _, _ in values),
                          max(max(abs(r), abs(y)) for _, r, y in values))
        flats.append((pl, [_flat(values[j * sub], pl, bind) for j in range(n_keys)], h, loop))
    if clear is not None and set(clear.links) <= jiggles:
        _clear(rig, clip, clear, flats)
    for pl, flat, h, loop in flats:   # a turned link's sixth number its rotation's x (Step 2.154b)
        n_keys = len(flat)
        for c in range(len(flat[0])):
            made = _monotone([length * j / (n_keys - 1) for j in range(n_keys)], [f[c] for f in flat], h, loop)
            tracks.append(Track(pl.index, (0, 1, 2, 4, 5, 3)[c], made))
    return Clip(clip.length, (*clip.bones, *tracks), clip.markers), peaks


def _keyed_one(shared: tuple, job: tuple):
    rig_, keys, drawn, clear = shared
    clip, placed, rate, loop, which = job
    try:
        return keyed(rig_, clip, placed, keys, rate, drawn, loop, clear.get(which))
    except ValueError as exc:
        return exc


def keyed_each(rig_: Rig, keys: float, drawn: float, clear: dict,
               jobs: list[tuple[Clip, tuple[Placed, ...], float, bool | set, object]]) -> list:
    """:func:`keyed` of each of ``jobs`` (a clip, the bones it bakes: a
    recipe's own clip may key some itself, Step 2.168; its rate, its loop
    and its key in ``clear``, the colliders by key: the clear's, or a
    clip's own groups', Step 2.169c; none there, none) with the rest of
    its arguments: each one's (clip, peaks), or the
    :class:`ValueError` it raised, in ``jobs``' order.  A clip's keys
    depend on it and those alone, so they are keyed in worker processes
    (:func:`azurik_mod.assets.pool.each`, the longest clips first: booblord
    v4's 59 were half her build one after another, Step 2.176)."""
    from azurkit.tools.characters import pool

    return pool.each(_keyed_one, (rig_, keys, drawn, clear), jobs, cost=lambda n: jobs[n][0].length)


CLEAR_TOL = 1e-4
"""How far (model units) inside its least distance a chain point may stay."""
CLEAR_EASE = 2
"""Keys over which a link's turn eases in before and out after a contact."""
CLEAR_SUB = 4
"""Frames a key's span the collider looks at (a move faster than the keys:
g4/fall_attack's head turns 10 degrees in its first 14 ms)."""
CLEAR_STEPS = 8
"""A turn's binary search: steps (1.2 rad / 256, 2.6 mm at 55 cm)."""
CLEAR_HOLD = (2 * CLEAR_EASE + 4) * CLEAR_SUB
"""Frames within which a link's turns about an axis all go one way, so a
turn the other way eases in only after a key at rest (Step 2.154b's
review 2: roll_forward's first link went -40 to +38 degrees in one key)."""
CLEAR_DRAPE = 0.004
"""How far (model units) past its least distance a held clip's drape keeps
each point it lays back down (Step 2.193: the collider's skin is a cell's
sample of hers, so a drape to the line put booblord_high's tail 4.9 mm into
her on one tick of die_2's landing)."""
CLEAR_DRAPE_RATE = 4.0
"""How fast a held clip's drape on a link may change, its whole share a
second (a quarter second from undraped to draped or back; Step 2.193's
record, F1: draped key by key, as far as each key alone allowed, her tail
flicked 9 cm back and forth in two ticks of die_2's fall)."""
CLEAR_REST = 0.25
"""Where a held clip has come to rest: no point of the skin farther than
this (model units) from its held last pose.  From there on no key drapes a
link further than a later key does, so the tail lies still or settles
(Step 2.193's record, R2: lying dead in die_2 her tail rose 27 degrees off
her arm after she had stopped)."""


def _posed_all(rig: Rig, clip: Clip, ks):
    """:func:`_posed` for the bones ``ks`` and their ancestors at once: a
    function of clip time, each one's posed world rotation and origin."""
    need = set()
    for k in ks:
        while k >= 0 and k not in need:
            need.add(k)
            k = rig.bones[k].parent
    depth = {}
    for k in sorted(need):
        p = rig.bones[k].parent
        depth[k] = 0 if p < 0 else 1 + (depth[p] if p in depth else len(_chain(rig, p)))
    order = sorted(need, key=lambda k: (depth[k], k))
    rot: dict[int, dict[int, tuple]] = {}
    tra: dict[int, dict[int, tuple]] = {}
    for tr in clip.bones:
        if tr.target in need:
            if 3 <= tr.comp <= 6:
                rot.setdefault(tr.target, {})[tr.comp - 3] = tr.keys
            elif tr.comp <= 2:
                tra.setdefault(tr.target, {})[tr.comp] = tr.keys

    def at(t: float) -> dict:
        out = {}
        for k in order:
            b = rig.bones[k]
            comps = rot.get(k, {})
            q = tuple(evaluate(comps[c], t) if c in comps else b.q[c] for c in range(4))
            n = math.sqrt(sum(c * c for c in q)) or 1.0
            local = qmul(qmul(b.jo, tuple(c / n for c in q)), b.ra)
            tc = tra.get(k, {})
            tl = tuple(evaluate(tc[c], t) if c in tc else b.t[c] for c in range(3))
            if b.parent < 0:
                out[k] = (local, tl)
            else:
                w, o = out[b.parent]
                out[k] = (qmul(w, local), tuple(a + d for a, d in zip(o, _turn(w, tl))))
        return out
    return at


def _clear(rig: Rig, clip: Clip, col: Collider, flats: list) -> None:
    """The collider (Step 2.154b, D617): ``col``'s chain at each key,
    posed by the clip and its springs (``flats``: (placed, its keys' five
    numbers, h, loop) by bone), each link from the root pitched about its
    pivot (the chain's root for the first; for the rest the point halfway
    to the parent's origin, where the tube's weights are shared half and
    half, so a bend stretches its skin less) about its parent's
    side-to-side axis as posed, by the least that brings every point it
    weighs most to its least distance: a binary search of
    :data:`CLEAR_STEPS` up to :data:`CLEAR_TURN` over the points the most
    turn clears (a point no turn of this link clears, her arm through her
    tail's root, is left).  Where the pitch leaves some, the link is swung
    instead (about its parent's fore-aft axis: sideways, out of an arm),
    or swung on the pitch, where that clears them all.  Each turn goes the
    way of the link's nearest turn within :data:`CLEAR_HOLD` frames (round
    the seam in a loop) and only that, else its parent link's way at that frame (the other where
    that can't clear), else the way that clears with less (a tail swung
    into her back goes back the way it came), so its keys don't flip
    across and the links bend alike (a held clip's, ``col.held``, from
    its last key back, so its held last pose takes the way it clears by
    and the frames before it follow, each link turned for the points of
    the links under it too, so a link lifts the tail over what the next
    one can't clear from its root: Step 2.169d; then each link under a
    lifted one is turned back toward its unturned way, its ancestors'
    pitch and swing undone, as far as no point under it comes within
    :data:`CLEAR_DRAPE` of its least distance, keys in order, its share
    changing at most :data:`CLEAR_DRAPE_RATE` and, once the clip has come to
    rest (:data:`CLEAR_REST`), never more than a later key's: Step 2.193's
    drape).  It looks at
    :data:`CLEAR_SUB` frames
    a key's span (the springs lerped between keys; a frame between keys
    the turns of its keys lerped clear is left to them), each key holding
    the most the frames of the spans beside it need (under the first link
    both turns together at most :data:`CLEAR_TURN`).  Each link's turns
    over the clip are then eased: a key takes the largest of its
    neighbours' turns over :data:`CLEAR_EASE` keys each way (round the
    seam in a loop), scaled down linearly, so the chain lifts off before a
    contact and settles after it, not in one key.  The links under it ride
    the turn.  A key it turns is rewritten as the link's local translation
    and rotation (x, y, z over w: the rest's w 1), its x a sixth number; a
    key it doesn't turn is left as it was."""
    import numpy as np
    where = {f[0].index: i for i, f in enumerate(flats)}
    chain = [where[k] for k in col.links]
    links = list(col.links)
    n_keys, loop = len(flats[chain[0]][1]), flats[chain[0]][3]
    if any(len(flats[i][1]) != n_keys for i in chain):
        raise ValueError("jiggle.clear: its links key at different rates")
    body = {int(k) for k in np.unique(col.skin["B"])} | {int(k) for k in np.unique(col.tail["B"])}
    body |= {col.pivot[0], rig.bones[links[0]].parent}
    at = _posed_all(rig, clip, sorted(body - set(links)))
    tail, target, owner = col.tail, col.tail["target"], col.tail["owner"]
    count = n_keys - 1 if loop else n_keys
    frames = []        # CLEAR_SUB a key's span: the body, its skin and the chain on its springs alone (their keys lerped)
    for f in range((n_keys - 1) * CLEAR_SUB + (0 if loop else 1)):
        j, q = divmod(f, CLEAR_SUB)
        u = q / CLEAR_SUB
        posed = at(clip.length * (j + u) / (n_keys - 1))
        R, O = np.zeros((len(rig.bones), 3, 3)), np.zeros((len(rig.bones), 3))
        for k, (qq, o) in posed.items():
            R[k], O[k] = _matrix(qq), o
        W, Og = [], []
        for c, k in enumerate(links):
            a, z = flats[chain[c]][1][j], flats[chain[c]][1][min(j + 1, n_keys - 1)]
            b, f5 = rig.bones[k], [x + u * (y - x) for x, y in zip(a, z)]
            pw, po = (W[c - 1], Og[c - 1]) if c else posed[b.parent]
            n = math.sqrt(f5[3] * f5[3] + f5[4] * f5[4] + 1.0)
            local = qmul(qmul(b.jo, (0.0, f5[3] / n, f5[4] / n, 1.0 / n)), b.ra)
            W.append(qmul(pw, local))
            Og.append(tuple(x + d for x, d in zip(po, _turn(pw, f5[:3]))))
        frames.append((posed, R, O, W, Og, _skinned(col.skin, R, O), _skinned(col.skin, R, O, normals=True)))

    def eased(c: int, f: int) -> tuple[float, float]:
        j, q = divmod(f, CLEAR_SUB)
        nxt = angle[c][(j + 1) % count] if q else (0.0, 0.0)
        return tuple(a + (b - a) * q / CLEAR_SUB for a, b in zip(angle[c][j], nxt))

    def turned(f: int, upto: int, extra: tuple = (0.0, 0.0), c_extra: int = -1):
        """Frame ``f``'s chain with links before ``upto`` turned as eased (lerped between keys), link ``c_extra``
        by ``extra`` (pitch, swing): each one's worlds and origins."""
        posed, W0, O0 = frames[f][0], frames[f][3], frames[f][4]
        W, Og = list(W0), list(O0)
        for c in range(len(links)):
            p, s = extra if c == c_extra else (eased(c, f) if c < upto else (0.0, 0.0))
            if not (p or s):
                continue
            if c:   # between its origin and its parent's, where the tube's weights are shared half and half
                J = tuple((a + b) / 2.0 for a, b in zip(Og[c - 1], Og[c]))
            else:
                pk, pu = col.pivot
                J = tuple(a + b for a, b in zip(posed[pk][1], _turn(posed[pk][0], pu)))
            parent = rig.bones[links[c]].parent
            carried = qmul(W[c - 1] if c else posed[parent][0], qinv(rig.world[parent]))
            e = (0.0, 0.0, 0.0, 1.0)
            for v, axis in ((p, (1.0, 0.0, 0.0)), (s, (0.0, 1.0, 0.0))):   # pitched, then swung about its pitched
                if v:                                                      # fore-aft axis
                    e = qmul(e, (*(a * fdlibm.sin(v / 2.0) for a in _turn(carried, axis)), fdlibm.cos(v / 2.0)))
            for m in range(c, len(links)):
                W[m] = qmul(e, W[m])
                Og[m] = tuple(a + b for a, b in zip(J, _turn(e, tuple(x - y for x, y in zip(Og[m], J)))))
        return W, Og

    def short(f: int, W, Og, sel):
        R, O, X, N = frames[f][1], frames[f][2], frames[f][5], frames[f][6]
        for m, k in enumerate(links):
            R[k], O[k] = _matrix(W[m]), Og[m]
        return target[sel] - _signed(_skinned(tail, R, O, sel), X, N)[0]

    def least(f: int, c: int, sel, axis: int, base: float, ways: tuple, cheaper: bool, hint: float = 0.0,
              whole: bool = False):
        """Link ``c``'s least turn about ``axis`` (0 pitch, 1 swing; the other ``base``) at frame ``f`` that
        clears each point of ``sel`` its most turn (:data:`CLEAR_TURN`) clears, the rest left (``whole``: none,
        or no turn): (how many it leaves short, its size, way's rank, the turn), the first of ``ways`` that leaves
        none (``cheaper``: the least, or that leaves fewest).  The search starts by ``hint``, the turn its frame
        before took, where it is this way."""
        limit = CLEAR_TURN - abs(base) if c else CLEAR_TURN
        found = []
        for rank, sign in enumerate(ways):

            def clear(v: float, pts) -> bool:
                return not short(f, *turned(f, c, (base, sign * v) if axis else (sign * v, base), c), pts).max() > \
                    CLEAR_TOL
            stuck = short(f, *turned(f, c, (base, sign * limit) if axis else (sign * limit, base), c), sel) > CLEAR_TOL
            ok, lo, hi, steps = sel[~stuck], 0.0, limit, CLEAR_STEPS
            if stuck.any() and (whole or not len(ok) or clear(0.0, ok)):   # the rest no turn this way clears
                hi = steps = 0
            elif sign * hint > 0.0:   # a bracket a sixteenth of the most wide by the turn before, where it holds
                h, d = min(abs(hint), limit), limit / 16.0
                if clear(h, ok):
                    lo, hi = max(h - d, 0.0), h
                    if lo and clear(lo, ok):
                        lo, hi = 0.0, lo
                else:
                    lo, hi = h, min(h + d, limit)
                    if hi < limit and not clear(hi, ok):
                        lo, hi = hi, limit
                steps = 4 if hi - lo <= d + 1e-12 else CLEAR_STEPS
            for _ in range(steps):
                mid = (lo + hi) / 2.0
                if clear(mid, ok):
                    hi = mid
                else:
                    lo = mid
            found.append((int(stuck.sum()), hi, rank, sign * hi))
            if not (found[-1][0] or cheaper):
                break
        return min(found)

    angle = [[(0.0, 0.0)] * count for _ in links]
    n = len(frames)
    back = col.held and not loop   # a held clip's from its end (Step 2.169d)
    for c in range(len(links)):
        own = np.nonzero(owner >= c if col.held else owner == c)[0]
        need = [(0.0, 0.0)] * n
        keys, between = range(0, n, CLEAR_SUB), [f for f in range(n) if f % CLEAR_SUB]
        order = [*keys[::-1], *between[::-1]] if back else [*keys, *between]
        for f in (order if len(own) else ()):
            W, Og = turned(f, c)     # its keys' frames first, then those between, which their turns may clear
            gap = short(f, W, Og, own)
            if not gap.max() > CLEAR_TOL:
                continue
            j, q = divmod(f, CLEAR_SUB)
            if back:   # its key after's turn, the one it took
                hint = need[f + CLEAR_SUB] if f + CLEAR_SUB < n else (0.0, 0.0)
            else:
                hint = need[f - CLEAR_SUB] if f >= CLEAR_SUB else (0.0, 0.0)
            if q:
                a, b = need[j * CLEAR_SUB], need[(j + 1) * CLEAR_SUB % n]
                hint = tuple(x + (y - x) * q / CLEAR_SUB for x, y in zip(a, b))
                if any(hint) and not short(f, *turned(f, c, hint, c), own).max() > CLEAR_TOL:
                    continue
            up = eased(c - 1, f) if c else (0.0, 0.0)

            def ways(axis: int) -> tuple[tuple, bool]:   # the way of its nearest turn within CLEAR_HOLD frames and
                # only that; else its parent link's way, the other where that can't clear; else the cheaper (a tail
                # swung into her back goes back the way it came)
                near = [d for d in range(-CLEAR_HOLD, CLEAR_HOLD + 1)   # round the seam in a loop, as the ease
                        if (loop or 0 <= f + d < n) and need[(f + d) % n][axis]]
                if near:
                    return (math.copysign(1.0, need[(f + min(near, key=lambda d: (abs(d), d))) % n][axis]),), False
                return ((math.copysign(1.0, up[axis]), -math.copysign(1.0, up[axis])), False) if up[axis] else \
                    ((1.0, -1.0), True)

            def solve(sel):   # pitched; where that leaves some short, swung, or swung on the pitch, where that
                pitch = least(f, c, sel, 0, 0.0, *ways(0), hint=hint[0])   # clears them all; else the pitch alone
                if not pitch[0]:
                    return pitch[3], 0.0
                swing = least(f, c, sel, 1, 0.0, *ways(1), hint=hint[1], whole=True)
                if not swing[0]:
                    return 0.0, swing[3]
                both = least(f, c, sel, 1, pitch[3], *ways(1), hint=hint[1], whole=True)
                return (pitch[3], both[3]) if not both[0] else (pitch[3], 0.0)
            got, far = solve(own[gap > -CLEAR_NEAR]), own[gap <= -CLEAR_NEAR]
            if len(far) and short(f, *turned(f, c, got, c), far).max() > CLEAR_TOL:   # one farther off went in
                got = solve(own)
            need[f] = got
        at_key = [[0.0, 0.0] for _ in range(count)]   # a key holds the most its spans each side need, so no frame
        for f, v in enumerate(need):                   # between keys is short
            j = f // CLEAR_SUB
            for i in ((j,) if f % CLEAR_SUB == 0 else (j, (j + 1) % count if loop else j + 1)):
                for axis in (0, 1):
                    if i < count and abs(v[axis]) > abs(at_key[i][axis]):
                        at_key[i][axis] = v[axis]
        for v in at_key if c else ():   # under the first, both turns together at most CLEAR_TURN (frames apart may
            over = (abs(v[0]) + abs(v[1])) / CLEAR_TURN   # want one each)
            if over > 1.0:
                v[0], v[1] = v[0] / over, v[1] / over
        for j in range(count):      # eased: the largest neighbour's turn, scaled down with its distance in keys
            best = [0.0, 0.0]
            for d in range(-CLEAR_EASE, CLEAR_EASE + 1):
                i = (j + d) % count if loop else j + d   # a loop's ease wraps past its seam
                for axis in range(2 if 0 <= i < count else 0):
                    v = at_key[i][axis] * (1.0 - abs(d) / (CLEAR_EASE + 1.0))
                    if abs(v) > abs(best[axis]):
                        best[axis] = v
            angle[c][j] = tuple(best)
    if back:   # a held clip's drape (Step 2.193, AZ-762): each link under a lifted one turned back toward its unturned
        # way (its ancestors' pitch and swing undone) as far as no point of the tail under it comes within CLEAR_DRAPE
        # of its least distance (or nearer than undraped, one it already was) at its key and every frame of the spans
        # beside it, both turns together at
        # most CLEAR_TURN, keys in order (the one before already draped, the one after not yet), so a tail lifted
        # over her arm lies back down past it instead of standing up off her; each link's share then changes at most
        # CLEAR_DRAPE_RATE a second (a key's share no more than the key before's plus that, then none more than the
        # key after's plus it) and, from where the clip comes to rest (its skin within CLEAR_REST of its last
        # pose's), no key's more than the key after's, both only ever lowering a share (toward the undraped way)
        step = CLEAR_DRAPE_RATE * clip.length / max(n_keys - 1, 1)
        rest = count
        while rest > 0 and np.linalg.norm(frames[(rest - 1) * CLEAR_SUB][5] - frames[-1][5], axis=-1).max() <= CLEAR_REST:
            rest -= 1
        for c in range(1, len(links)):
            own = np.nonzero(owner >= c)[0]
            share: list = [None] * count
            for j in range(count):
                up = tuple(sum(angle[a][j][x] for a in range(c)) for x in (0, 1))
                if abs(up[0]) + abs(up[1]) < 1e-3:
                    continue
                base, window = angle[c][j], range(max(0, (j - 1) * CLEAR_SUB + 1), min(n, (j + 1) * CLEAR_SUB))
                was = {f: np.maximum(short(f, *turned(f, len(links)), own), CLEAR_TOL - CLEAR_DRAPE) for f in window}

                def out(share: float) -> bool:
                    angle[c][j] = (base[0] - share * up[0], base[1] - share * up[1])
                    if abs(angle[c][j][0]) + abs(angle[c][j][1]) > CLEAR_TURN:
                        return False
                    return all(not (short(f, *turned(f, len(links)), own) > was[f]).any() for f in window)
                lo, hi = 0.0, 1.0 if not j or share[j - 1] is None else min(1.0, share[j - 1][0] + step)
                if out(hi):
                    lo = hi
                else:
                    for _ in range(CLEAR_STEPS):
                        mid = (lo + hi) / 2.0
                        lo, hi = (mid, hi) if out(mid) else (lo, mid)
                    out(lo)
                share[j] = (lo, base, up)
            for j in range(count - 2, -1, -1):
                if share[j] is None or share[j + 1] is None:
                    continue
                cap = share[j + 1][0] + (0.0 if j >= rest else step)
                if share[j][0] > cap:
                    _, base, up = share[j]
                    share[j] = (cap, base, up)
                    angle[c][j] = (base[0] - cap * up[0], base[1] - cap * up[1])
    for c, i in enumerate(chain):
        if not any(p or s for p, s in angle[c]):
            continue
        new, xs = list(flats[i][1]), [0.0] * n_keys
        for j in range(count):
            if not any(angle[c][j]):
                continue
            W, Og = turned(j * CLEAR_SUB, len(links))
            b = rig.bones[links[c]]
            pw, po = (W[c - 1], Og[c - 1]) if c else frames[j * CLEAR_SUB][0][b.parent]
            q = qmul(qmul(qinv(b.jo), qmul(qinv(pw), W[c])), qinv(b.ra))
            q = q if q[3] > 0.0 else tuple(-x for x in q)
            tl = _turn(qinv(pw), tuple(a - b for a, b in zip(Og[c], po)))
            new[j], xs[j] = (*tl, q[1] / q[3], q[2] / q[3]), q[0] / q[3]
        if loop:
            new[-1], xs[-1] = new[0], xs[0]
        pl, _, h, lp = flats[i]
        flats[i] = (pl, [(*f, x) for f, x in zip(new, xs)], h, lp)


def _monotone(times: list[float], values: list[float], h: float, loop: bool) -> tuple:
    """Hermite keys through ``values`` with Fritsch-Carlson tangents (0 at
    a turn or a flat end, else the secants' mean bounded by three times
    each), so no curve between two keys leaves their range: the spring's
    swing from one limit to the other can't overshoot its travel (a loop
    wraps its secants at the seam)."""
    n = len(values)
    sec = [(values[j + 1] - values[j]) / h for j in range(n - 1)]
    out = []
    for j in range(n):
        if 0 < j < n - 1 or (loop and n > 2):
            a = sec[j - 1] if j > 0 else sec[-1]
            b = sec[j] if j < n - 1 else sec[0]
            m = 0.0 if a * b <= 0.0 else math.copysign(min(abs(a + b) / 2.0, 3.0 * abs(a), 3.0 * abs(b)), a)
        else:
            m = 0.0
        out.append((times[j], values[j], m, m))
    return tuple(out)


def _flat(value, pl: Placed, bind: Quat) -> tuple[float, ...]:
    """A pose value as the five keyed numbers: the rest translation plus
    the mean offset in the parent's frame; the rotation's y and z at half
    the roll and yaw."""
    mean, roll, yaw = value
    off = _turn(qinv(bind), mean)
    return (pl.rest[0] + off[0], pl.rest[1] + off[1], pl.rest[2] + off[2], roll / 2.0, yaw / 2.0)


__all__ = ["DROP", "Bone", "Free", "MIN_SHARE", "Placed", "Rigged", "SIM_HZ", "SMOOTH_HZ", "Spec", "closes", "keyed",
           "keyed_each", "rig"]
