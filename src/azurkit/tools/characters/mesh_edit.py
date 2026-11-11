"""A body's mesh edited (Step 2.142; D332, D390): the moved
vertices of a glTF that ``azurik-mod model export`` wrote and Blender (or
any tool) edited, and a recipe's deform ops, written into
``characters.xbr``'s LOD-0 vertices (W24, a variant's ``mesh``).

The glTF path keeps the topology and moves positions only; the
``subdivide`` op (Step 2.154) adds vertices and triangles, and the body
is then written whole.  :func:`plan` reads the body (LOD 0's
groups, their 60-byte vertices and the strips' triangles), applies the
edit and the ops and checks the result; :func:`write` puts it into a
``characters.xbr`` and checks the bytes it wrote.  Every refusal is a
:class:`ValueError` naming the edit, op or file, and nothing is written
(D35).  :func:`prepare` keeps :func:`plan`'s first step (the topology) and
:func:`positions` runs its position steps on it for other values of the
same ops (Step MK.3a: ``azurik-mod model rest``, a shape slider's ends).

- **What is written.**  A vertex whose position ends more than
  :data:`MOVED` from vanilla's gets its float32 position at +0; every
  vertex whose welded fan holds one gets its normal at +28, recomputed
  (never read from a file): vanilla's normal turned by the shortest
  rotation that takes its fan's area-weighted face normal at vanilla's
  positions to the one at the new positions (Rodrigues, from the cross
  and dot products).  The fan is the vertex's triangles and those of
  every vertex at its bit-identical vanilla position whose stored normal
  lies within 60 degrees of its own (seam copies of one surface; a
  two-sided sash's back faces stay apart).  Vanilla's normals are
  authored (female_2's lie a median 3.9 degrees off that fan normal), so
  turning them keeps their hard edges.  Weights, slot bytes, UVs, the
  +48 pair, palettes, strips and descriptors are kept byte for byte, and
  :func:`write` compares the whole file with its input outside the
  written fields.
- **The glTF** (a ``.glb`` or a ``.gltf`` with its
  buffers beside it or as data URIs; the file is untrusted data and only
  its JSON and buffers are read): the one mesh whose primitives carry
  ``_AZ_VID`` or, as Blender's default export writes it, ``TEXCOORD_1``
  (the export's (group, index); ``UVMap.001`` in Blender), other meshes
  ignored and named.  Its frame comes from the skin: each joint's
  inverse bind against the body's gives the mesh-to-model transform,
  which must be one for every joint (else the bones moved) and the
  model's frame or an axis swap of it (Blender writes glTF's y up).
  Every copy of an id must sit within :data:`COPIES` of the others (a
  seam Blender split), every vertex a triangle uses must be there and
  nothing else, the triangles must be vanilla's with their winding, the
  UVs and each vertex's skin vanilla's (within :data:`UV_CHANGE`,
  :data:`SKIN_CHANGE`: Blender's round trip moves them by 3e-8 and 1e-4).
  Measured on Blender 5.2.2's round trip (Step 2.142's design); another
  tool that changes more fails a named check, never silently.  A body
  with a rest scale off 1 (balthazar's pecs) reads as "the bind pose
  changed", as Blender rebuilds its inverse binds from its rest.
- **The deform ops** (Step 2.143; each centred at ``c``, the bone's bind
  origin plus ``offset``, model units in the body's frame: x right, y
  forward, z up, before the species' scale).  Each sums its displacement
  on the same base positions (the glTF's, then vanilla's).  ``mirror``
  adds the op reflected across x = 0 (``left``/``right`` swapped in its
  ``only``; refused for a centre on x = 0, its own mirror); ``keep``
  names bone subtrees whose vertices (by their heaviest weight) no op
  moves but one whose ``only`` names them; ``groups`` limits an op to
  those LOD-0 mesh groups (a cloth layer lifted off the skin under it:
  a coarse layer's flat triangles would cut a round form); ``name``
  labels an op (a jiggle finds its shape by it).
  - ``scale`` (:class:`ScaleOp`): inside the ellipsoid of half axes
    ``radius``, scaled by ``factors`` per axis at ``c`` falling to 1 at
    the edge: with ``q = (p - c) / radius`` and ``d = |q|``, ``p' = p +
    phi (factors - 1)(p - c)``, ``phi`` the ``profile``: ``cone`` (the
    default) ``(1 - d)^2``, ``smooth`` ``(1 - d^2)^2`` (no tip at the
    centre).  One cone can't fold for factors under 4 (radial slope 1 +
    (s - 1)(1 - d)(1 - 3d)), one smooth under 2.25.
  - ``push`` (:class:`PushOp`): a bump of ``height`` along the unit
    direction ``n`` of ``dir``.  Its frame: ``t`` the z axis less its n
    part, normalised (up), ``s = t x n`` (across); with ``q = p - c``,
    ``u = q.n``, ``A = q.s / r_across`` (``in`` towards x = 0, ``out``
    away; ``out`` both ways for a centre on x = 0), ``B = q.t / r_vert``
    (``up`` above, ``down`` below) and ``rho^2 = A^2 + B^2 < 1``, the
    profile ``b = D + fold (1 - B / rho) / 2 ((1 - rho^4) - D)``, ``D =
    (1 - rho^2)^2 (1 + 2 rho^2)``: the dome ``D``, full at the centre
    and sloping into the body with no edge above (and everywhere at
    ``fold`` 0), blended below towards the round ``1 - rho^4``, which
    meets the body at a fold of finite slope (a square root's infinite
    one folds any op it meets) at ``fold`` 1, the default (a coarse
    cloth layer's few rows read a full fold as a flat underside, so it
    takes a lower one); the gate
    ``g(u)`` 1 in front of the centre, a smoothstep over ``depth`` behind
    it, 0 further back (the far side doesn't move).  ``p' = p + height b g
    n``: ``det J = 1 + height b g' >= 1``, so one push can't fold, and a
    function of position keeps a cloth layer on the skin under it.  With
    ``region`` (Step 2.168) it moves nothing: its ``b g`` is only a jiggle
    bone's share (:func:`shares`).
  - ``taper`` (:class:`TaperOp`): x and y about the vertical line through
    ``c`` scaled by ``f = 1 - (1 - factors) W(z) G(r)``, ``W`` 1 within
    ``plateau`` of ``c``'s z (a pure scale there: the belt's light kept),
    ``(1 - k^2)^2`` over the ``half`` beyond (``k`` the fraction of it), 0
    further; ``G`` 1 within ``reach[0]`` of the line falling by a
    smoothstep to 0 at ``reach[1]`` (the arms don't move).  Factors in
    (0, 1]: ``det J = f_x f_y + k(...) > 0``.
  - ``tuck`` (:class:`TuckOp`; not a field, so it runs after them, in
    recipe order): each vertex of the layer ``groups`` that a field op
    moved, that lies in front
    of the cloth ``under`` (its triangles whose three vertices are in those
    groups and outside the ``skip`` subtrees, facing ``n`` by vanilla's
    normals: a cloth's far side doesn't count), facing ``n`` itself, along
    the unit ``n`` of ``dir`` where the cloth covers it seen along ``n``,
    moves back along
    ``n`` to ``margin`` behind the cloth: the cloth's nearest surface in
    front of the vertex or at most ``window`` behind it (not the far side
    of the body); a vertex vanilla already has nearer its cloth than
    ``margin`` keeps vanilla's distance (vanilla's own layers stay as they
    are), unless ``strict``: then every moved vertex ends ``margin``
    behind (vanilla's own pokes, which a flat cloth hid, show once the
    cloth over them faces the camera).  ``band`` ([lo, hi], bind z) limits
    it to the layer's vertices at those heights (a margin by row: two
    tucks); ``faces`` reads the layer's triangles too (their centroids
    and edge midpoints, then the vertices again), so a coarse cloth's
    flat triangle can't cut through one between its vertices.  A coarse cloth's flat triangles
    otherwise cut a round form the skin under it takes (Step 2.143: the
    top over a bust).
  - ``subdivide`` (:class:`SubdivideOp`, Step 2.154; D438, D443; not
    a field: it runs first, on the base positions): its region, the
    triangles whose centroid lies in the ellipsoid of half axes
    ``radius`` about ``c`` (and its mirror) and whose corners it selects
    (``only``/``keep`` and ``groups``, as a field op), is split until
    each one's longest edge in the final shape (the field ops applied)
    is at most ``edge``: Rivara's longest-edge bisection (a split walks
    to the neighbour whose longest edge is longer first), so no triangle
    is split but along its longest edge, every triangle on a split edge
    is split with it (no T-junction, in any group) and each keeps its
    winding.  A new point is the edge's midpoint, or with ``smooth`` (the
    default) PN triangles' cubic midpoint along the ends' welded normals
    (their faces' area-weighted normal at the base, a twin face turned
    to the first copy's stored normal), computed once per welded edge
    from float32 values in a fixed order so its copies are bit-identical
    (no crack); each copy of it (one per vertex pair: a seam's two get
    two) goes at the end of its group with the pair's UV halfway and
    their weights blended, cut to four and renormalised (in the group's
    palette: no palette grows).  An edge whose half would end longer
    than :data:`TORN` of it where its ends or its middle are moved by
    different ops (a field op stopping at a ``keep``, ``only`` or
    ``groups`` boundary, which no split shortens; one map over the whole
    edge is continuous, however far a ``round`` bends it), a triangle already
    under ``edge`` / :data:`STRETCH` and a sliver (a crack vanilla fills)
    aren't split.  With ``smooth`` every vertex of the region gets a
    smooth normal: the area-weighted normal of its fan in the final
    shape, seam copies joined when their own faces there turn within 60
    degrees of each other (a two-sided layer's sides stay apart, a crease
    vanilla kept with two copies is joined once the ops round it), not
    vanilla's turned.  With ``apart`` {``edges``, ``band``} (Step 2.177b:
    booblord_high's finer bust, whose skin rose through her top's lip
    where the top ends on her side) a triangle whose centroid in the final
    shape lies within ``band`` of an open edge of the ``edges`` groups (in
    the final shape, as the mesh had it before the split) is left as the
    other regions leave it.  With ``normals`` ``"angle"`` (Step 2.177c;
    ``"area"`` by default) a smooth vertex the region holds weighs each
    face of its fan by the face's angle at it, not its area: a cloth's
    crack vanilla fills with long slivers, which the round ops open into
    a fin standing off the surface between two points, leaned those
    points' normals 30-52 degrees once the split made the faces round
    them small (booblord_high's top: dark specks on her bust's side).
    With ``"nearer"`` (Step 2.188) a vertex takes whichever of the two
    lies nearer the mean of its ring's normals (each ring vertex's area
    normal, or its stored one outside the smoothed set): the fin's tips
    take the angle's, and the crack's own points, which the angle rule
    turned further from their ring (a darker notch at her top's edge in
    game), keep the area's.
    The plan then carries the subdivided mesh, and
    :func:`write` writes the body whole (:func:`assemble`, then
    :func:`~azurik_mod.assets.body_codec.write_asset`).
  - ``round`` (:class:`RoundOp`, Step 2.154; D438: a form made
    spherical; not a field: it runs after them, in recipe order, before
    the tucks): the ellipsoid about ``c`` with half axes ``radius`` =
    (across, along, up, down) in ``dir``'s frame (``push``'s: ``along``
    its direction, ``up`` above the centre's plane, ``down`` below), and
    rays from the point ``origin`` behind ``c`` along ``dir`` (inside the
    ellipsoid).  A point at ``r`` from it along the unit ``u``, the
    ellipsoid at ``R`` along ``u``, moves along ``u`` to the smooth
    maximum ``max(r, R) + h^2 k / 4``, ``h = (k - |r - R|) / k`` (C1: the
    crease where the form meets the body filled over ``k``, the
    ``blend``: one width, or ``up`` and ``down`` blended by u's height),
    times ``gate``'s smoothstep of ``u . dir`` (none by default).  So the
    surface inside the ellipsoid lands on it, overhangs and all (a lower
    pole curving back under, which a push can't make), and outside it
    stays.  A radial move keeps every triangle's facing seen from the
    origin, so the op can't fold the surface; it has no det J of its own.
    A mirrored op's two sides act together: each point moves by their
    moves' mean weighted by each one's squared length (a point on x = 0
    stays there).  Two layers on concentric ellipsoids (a cloth's
    ``radius`` its skin's plus a margin, one ``origin`` and ``dir``) stay
    apart along every ray: the smooth maximum rises with both.  Round 2
    of Step 2.154 adds: ``drape`` (the upper half's ``R`` the exit of the
    hull of the section's ellipse and a point of an anchor line, bisected,
    faded across and on rays that barely rise: a slope from the
    collarbone), ``origin`` {back, in} (the rays fanned from nearer
    x = 0), ``bridge`` (:func:`_bridge`: a mirrored pair's surface moved
    onto their smooth union, a U cleavage) and ``beneath`` (:func:`_beneath`:
    a layer kept ``gap`` under another's final surface along its rays).
  - ``bind`` (:class:`BindOp`, Step 2.154): each vertex of a layer in a
    region takes the skin weights of the nearest vertex of the ``to``
    groups in the final shape (:func:`_bind`), so a cloth over a big form
    moves with the skin under it; the body is then written whole.  Round
    6 (D512): ``reach`` mixes every ``to`` vertex's within it (a cloth by
    the neck took the neck's or the shoulder's bones vertex by vertex and
    tore when she moved), ``fade`` mixes the result with the vertex's own
    by the region's falloff.
  - ``hem`` (:class:`HemOp`, Step 2.154): a layer's open edges in a region
    split to ``edge`` with the subdivision, relaxed ``relax`` times at the
    base, and the layer within ``width`` of them drawn ``inset`` towards the
    op's centre after the rounds (:func:`_insets`).
  - ``unwrap`` (:class:`UnwrapOp`, Step 2.154; D456: the dress not
    smeared over a bigger form; it runs last, on the final shape): the
    triangles whose base centroid lies in the ellipsoid of half axes
    ``radius`` about ``c`` (and its mirror) and whose corners it selects,
    each texture island of them (joined through shared vertices, so a UV
    seam parts two) given its UVs again: a vertex a triangle outside the
    region uses keeps its UV, a vertex on the island's edge moves
    ``shrink`` of the way to the island's UV centroid (a small island's
    dark rim left behind), and the rest take the harmonic map of the final
    shape (the cotangent Laplacian, conjugate gradients from their UVs),
    so the texture spreads evenly over the form.  A plan with an unwrap
    writes the body whole.
  - Round 3 of Step 2.154 (D438, D456, D485, D488): a mirrored round's
    ``pair`` (:func:`_pair_ray`: one ray from an origin on x = 0, the
    forms' smooth maximum along it), ``back``, ``inner``, ``taper`` and
    ``taper_in`` half axes (:func:`_shape`), a drape's ``ease``;
    ``relax`` (:class:`RelaxOp`, :func:`_relax`); ``island`` and
    ``atlas`` (:class:`IslandOp`, :class:`AtlasOp`: a region's own UV
    island, the rest laid into a sub-rect; the vertices split at the
    island's edge in :func:`_split_islands`, the UVs laid in
    :func:`_island_uvs`; W30 repaints the material,
    :mod:`azurik_mod.assets.paint`); and ``tube`` (:class:`TubeOp`,
    :func:`_generate`: new geometry no other op moves, with named shares
    for a jiggle chain).
  - Round 6 of Step 2.154 (D513): ``cut`` (:class:`CutOp`, :func:`_cut`,
    :func:`_press`): a layer's triangles in a region past a plane dropped
    and those it crosses cut at it in the shape the fields and rounds
    give (it runs last in the topology, after the tubes), so a cloth ends
    in one straight edge whatever its triangles; its ``press`` sinks the
    cloth by the new edge and the skin under it and swells the bare skin
    past it (a band pressed into soft skin), its ``trim`` lays a cord of
    the cloth's material along the edge that rides it and takes its
    weights and jiggle share.  Round 9 (D549): ``snap`` moves its edge back
    onto the cut's surface after the press (:func:`_snap`) and lays its
    cord as one chain through the whole edge at the ride; ``corner`` adds a
    second plane with the corner between them rounded (:func:`_cut_value`).
  - Step 2.177d (D698): ``thicken`` (:class:`ThickenOp`: a two-sided
    layer's sides moved ``depth`` apart, last of the position steps, and
    the edges they leave open together joined by rims in the topology,
    after the cuts: :func:`_rims`, :func:`_thicken`); Step 2.187 (D724):
    its ``taper`` eases the depth in from where the layer meets the rest
    of its cloth.
  A sum of field ops can fold, so the Jacobian's determinant (analytic)
  must stay above 0 at every vertex a field op moves and at the centroid
  of every triangle it moves.  Nothing is clamped (D23).
- **The drop** (Step 4.3, ``mesh.drop``: booblord's vase): the bone
  subtrees whose vertices (by their heaviest weight) leave LOD 0 with
  every triangle that uses one, before every op (:func:`_drop`).  They
  must be whole groups, the LOD's last, so no other group's number or
  vertex moves; the bones stay (a clip keys a bone by its index).  Her
  base's vase, group 5 on ``vase_joint``, which every clip she plays keys
  at a scale of 0 or 1e-12, drew only in her bind pose (the Characters
  tab's pictures), round her legs.
- **The checks on the result**: vertices vanilla keeps together (a
  bit-identical position) stay within :data:`COPIES`; LOD 1+ isn't
  edited (a build cuts a body's own LODs anew from its edited LOD 0 at
  their vanilla shares, W39, Step 2.166d); :class:`MeshPlan` counts the triangles turned over
  (face normal more than 90 degrees from vanilla's), reported, not
  refused (a big bust's underside turns some legitimately).

The arithmetic is plain Python floats with no transcendental function
(sums in index order, ``sqrt``), so a build writes the same bytes on
every machine.  Nothing here prints a byte or a coordinate.
"""

from __future__ import annotations

import base64
import copy
import functools
import hashlib
import heapq
import itertools
import json
import math
import re
import struct
import urllib.parse
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from azurkit.core import fdlibm, native
from azurkit.tools.characters.characters import (
    VERTEX_SIZE, MeshGroup, body_at, bone_records, inverse_binds, mesh_groups, read_body)
from azurkit.tools.characters.gltf import HELPER
from azurkit.tools.characters import render
from azurkit.core.xbr.nodes import named_resources, parse_toc

Vec = tuple[float, float, float]

LEPP_MAX = 64
"""The longest chain of neighbours a split walks before it splits the
edge it stands on anyway."""
TORN = 0.8
"""A ``subdivide`` edge isn't split when one of its halves would end
longer than this share of it in the final shape: a field op that stops at
a bone or group boundary (``keep``, ``only``, ``groups``) stretches it,
which no split shortens."""
STRETCH = 16.0
"""How far the ops may stretch a ``subdivide`` region: a triangle whose
longest edge is already under ``edge`` / this isn't split again."""
SLIVER = 1e-3
"""A triangle whose doubled area is under this share of its longest edge
squared is a sliver (a crack vanilla fills): ``subdivide`` leaves it."""
SUBDIVIDE_MAX = 400_000
"""The most vertices the ``subdivide`` ops may add (a guard against an
``edge`` so short it never ends; D35 refuses past it)."""
PASSES_MAX = 100
"""The most passes a ``relax`` op (``passes``) or a ``hem`` (``relax``) may
run; a recipe's loader refuses more by name (the shipped recipes run 20 and
40; each pass is work over its region, so 10**12, ten bytes of a recipe,
would be days)."""
TUBE_SIDES_MAX, TUBE_RINGS_MAX, TUBE_POINTS_MAX = 256, 512, 32_768
"""The most sides and rings a ``tube`` may have, and ``(sides + 1) x rings``
(its points), each refused past by name at load, as its ``segments`` past
its rings: the shipped tubes have at most 32 sides, 192 rings and 6,336
points, and a tube's winding work grows as sides x rings squared (at the
caps, seconds)."""
MOVED = 1e-5
"""How far (model units) a vertex must end from vanilla's to be written:
Blender's round trip leaves unmoved ones within 4.8e-7."""
COPIES = 1e-6
"""How far apart one id's copies, or two vertices vanilla keeps at one
position, may end."""
FRAME = 1e-3
"""How far each joint's mesh-to-model transform may sit from their mean,
and the mean from a signed permutation (Blender's: 2.6e-5)."""
SHIFT = 1e-4
"""How far the mesh frame's origin may sit from the model's."""
UV_CHANGE = 1e-4
SKIN_CHANGE = 1e-3
CLOTH_CELL = 0.02
"""A ``tuck``'s grid over its cloth (model units): a query reads the
triangles of its cell, whose bounds hold it (Step 2.154: a subdivided
cloth made the scan of every triangle the plan's slowest part)."""
WELD = 0.5
"""A seam copy joins a vertex's fan when their stored normals' cosine is
above this (60 degrees)."""
CARRIERS = ("_AZ_VID", "TEXCOORD_1")
"""The attributes that carry a vertex's (group, index), in the order read."""
OPS = ("scale", "push", "taper", "tuck", "subdivide", "round", "unwrap", "hem", "bind", "reweight", "relax", "island",
       "atlas", "tube", "cut", "thicken")
PROFILES = ("cone", "smooth")
"""``scale``'s profiles; ``cone`` the default (Step 2.142's bytes)."""


@dataclass(frozen=True)
class ScaleOp:
    """One ``scale`` op of a recipe's ``mesh.ops`` (module docstring)."""

    bone: str
    radius: Vec
    factors: Vec
    offset: Vec = (0.0, 0.0, 0.0)
    mirror: bool = False
    only: tuple[str, ...] = ()
    profile: str = "cone"
    name: str = ""
    groups: tuple[int, ...] = ()
    late: bool = False
    """(Step 2.187, D725, AZ-734: her skin showed through her top's strap
    by her neck, and any move of it shifted her breast bones' places, which
    her clips' rests hold.)  Not a field: its move is the body's last, on
    the final shape (:func:`_late`), and W29 places its jiggle bones from
    the shape before it (:attr:`MeshPlan.late`), so a skin moved deeper
    under its cloth moves no bone."""


@dataclass(frozen=True)
class PushOp:
    """One ``push`` op: ``radius`` is (in, out, up, down); a ``region``
    one moves nothing, its profile only a jiggle bone's share field
    (:func:`shares`, Step 2.168)."""

    bone: str
    direction: Vec
    height: float
    radius: tuple[float, float, float, float]
    depth: float
    offset: Vec = (0.0, 0.0, 0.0)
    fold: float = 1.0
    mirror: bool = False
    only: tuple[str, ...] = ()
    name: str = ""
    groups: tuple[int, ...] = ()
    region: bool = False


@dataclass(frozen=True)
class TaperOp:
    """One ``taper`` op: ``factors`` (x, y), ``reach`` (r0, r1)."""

    bone: str
    factors: tuple[float, float]
    plateau: float
    half: float
    reach: tuple[float, float]
    offset: Vec = (0.0, 0.0, 0.0)
    only: tuple[str, ...] = ()
    name: str = ""
    groups: tuple[int, ...] = ()


@dataclass(frozen=True)
class TuckOp:
    """One ``tuck`` op: the layer ``groups`` moved behind the cloth
    ``under`` along ``direction`` (module docstring)."""

    groups: tuple[int, ...]
    under: tuple[int, ...]
    direction: Vec
    margin: float
    window: float = 0.05
    skip: tuple[str, ...] = ()
    only: tuple[str, ...] = ()
    name: str = ""
    strict: bool = False
    band: tuple[float, float] | None = None
    faces: bool = False


@dataclass(frozen=True)
class SubdivideOp:
    """One ``subdivide`` op (Step 2.154): the region inside the ellipsoid
    of half axes ``radius`` about ``c`` (and its mirror) split until each
    of its edges ends at most ``edge`` long in the final shape (module
    docstring); ``smooth`` puts each new point on the curved surface
    through the old ones and gives the region's vertices smooth normals;
    ``apart`` (groups and a band, Step 2.177b) leaves those groups' open
    edges as the other ops leave them; ``normals`` (``"area"``,
    ``"angle"``, Step 2.177c, or ``"nearer"``, Step 2.188) weighs the
    region's smooth normals."""

    bone: str
    radius: Vec
    edge: float
    offset: Vec = (0.0, 0.0, 0.0)
    mirror: bool = False
    only: tuple[str, ...] = ()
    groups: tuple[int, ...] = ()
    smooth: bool = True
    name: str = ""
    apart: tuple[tuple[int, ...], float] | None = None
    normals: str = "area"


@dataclass(frozen=True)
class RoundOp:
    """One ``round`` op (Step 2.154, D438): the surface inside the
    ellipsoid about ``c`` (half axes ``radius`` = (across, along, up,
    down) in the frame of ``direction``) pushed out onto it along rays
    from the point ``origin`` behind ``c`` (module docstring)."""

    bone: str
    radius: tuple[float, float, float, float]
    origin: float
    blend: tuple[float, float]
    offset: Vec = (0.0, 0.0, 0.0)
    direction: Vec = (0.0, 1.0, 0.0)
    gate: tuple[float, float] | None = None
    mirror: bool = False
    only: tuple[str, ...] = ()
    groups: tuple[int, ...] = ()
    name: str = ""
    drape: tuple[float, float, float, float, float] | None = None
    """(forward, up, fade from, fade to, tilt): the upper half's surface on
    the tangent from a line at the bone's origin plus (forward, up), across
    and ``tilt`` forward per unit towards x = 0 (a chest's curve), to
    the ellipsoid (Step 2.154, D438: a slope from the collarbone, not a
    shelf), faded out across: full where the section's distance from the
    centre is under ``fade from`` of the across half axis, none past
    ``fade to``."""
    bridge: float = 0.0
    """A mirrored pair's smooth union across x = 0 (its width): the
    cleavage a U, not the V where two ellipsoids cut each other."""
    inward: float = 0.0
    """How far the rays' origin sits towards x = 0 from ``origin``'s
    point (a layer's rays fanned out over the form's outer side)."""
    beneath: tuple[tuple[int, ...], float] | None = None
    """(groups, gap): this layer kept at least ``gap`` under those groups'
    final surface along each of its vertices' rays (a skin under its
    cloth where their blends or drapes differ)."""
    pair: bool = False
    """A mirrored op's two forms as one (Step 2.154 round 3, D438): every
    ray from one origin on x = 0 (the mean of the sides' origins), the
    form along it the smooth maximum of the sides' (``bridge`` its width),
    so a point on x = 0 moves as its neighbours do (two sides' averaged
    moves left a slit there) and the cleavage is a U."""
    inner: float = 0.0
    """The across half axis on the side of the centre towards x = 0 (0:
    ``across``): a glute that ends at its cleft."""
    back: float = 0.0
    """The along half axis behind the centre (0: ``along``): a pair's form
    reaching back into the chest round its one origin, so every ray leaves
    it once and the lower pole runs back to its fold."""
    taper: float = 0.0
    """The outer across half axis (away from x = 0) narrowed above the
    centre's plane, to ``1 - taper`` of it at the top (``across (1 - taper
    S(t / up))``, ``S`` the smoothstep: no crease at the centre's plane,
    round 4): a breast's upper pole narrower on the armpit's side, so from
    the front each reads as a round form, not a vest's square corner, and
    its inner slope still meets its mirror's over the sternum."""
    taper_in: float = 0.0
    """The same for the inner across half axis (towards x = 0): the upper
    poles parted over the sternum, a longer cleavage."""
    taper_back: tuple[float, float] = (0.0, 0.0)
    """(share, reach): the outer across half axis narrowed behind the
    centre's plane by ``share S(-n / reach)`` (``reach`` 0: the back half
    axis): a breast's outer side rounded off before the arm (Step 2.154
    round 4)."""
    taper_low: tuple[float, float] = (0.0, 0.0)
    """(share, reach): the same below the centre's plane, ``reach`` 0 the
    down half axis: a lower pole round from the front, not a shelf on the
    belt."""
    midline: tuple[float, ...] | None = None
    """(z from, z to, width[, behind[, span]]): within ``width`` of x = 0
    the move fades out below ``z to`` to none at ``z from`` (a smoothstep in
    each): a glute pair's union kept above the crotch (Step 2.154 round 4);
    with ``behind`` (round 9, D550) only where y lies behind it (a
    smoothstep over ``span`` each way, :data:`MIDLINE_SPAN` by default), so
    the inner thighs in front of the crotch keep the move (a wider span
    eases it in over the thighs' depth: a short one folded the cleft)."""
    inner_blend: tuple[float, float, float] | None = None
    """(down, x full, x none; round 9, D548): the lower blend is ``down``
    within ``x full`` of x = 0, easing back to the op's own by ``x none``
    (a smoothstep of |x|): a butt's underside blended long by its cleft and
    no wider at the thigh's outer side."""
    ease: float = 0.0
    """A drape's lift eased in by a smoothstep over this distance from its
    anchor along its slope: the slope leaves the chest tangent to it."""
    behind: tuple | None = None
    """(y full, y none, share, line; round 11, D606, D607): the move times
    ``share`` past ``y full`` on the side away from ``y none``, easing (a
    smoothstep of y) to none at ``y none``, both from ``line`` ((z, y)
    points: y at the point's z, straight between them and level past the
    ends; none given: y = 0): a hip bone's round on her back half only (y
    none in front of y full) or, swapped (round 11b), on her front half,
    by how far behind or in front of her side's midline a point lies,
    feathered across her side."""
    window: tuple[float, float, float, float] | None = None
    """(z0, z1, z2, z3; round 11): the move none below z0 and above z3,
    full from z1 to z2, a smoothstep of z between: a round's volume kept to
    the heights it is for (a hip bone's, her waist and thighs as they
    were)."""


@dataclass(frozen=True)
class RelaxOp:
    """One ``relax`` op (Step 2.154 round 3, D438): the final surface of
    ``groups`` in the ellipsoid of half axes ``radius`` about ``c`` (and
    its mirror) smoothed ``passes`` times (Taubin's lambda/mu pair, so a
    form keeps its size), each welded point moved by its share of the
    region's falloff ``(1 - d^2)^2``; a point on x = 0 stays on it, and an
    open edge's points stay (``open``: they relax along their loop)."""

    bone: str
    radius: Vec
    passes: int
    offset: Vec = (0.0, 0.0, 0.0)
    mirror: bool = False
    only: tuple[str, ...] = ()
    groups: tuple[int, ...] = ()
    open: bool = False
    name: str = ""


@dataclass(frozen=True)
class HemOp:
    """One ``hem`` op (Step 2.154, D438): the open edges of ``groups`` in
    the ellipsoid of half axes ``radius`` about ``c`` (and its mirror)
    split to at most ``edge`` in the final shape, relaxed along their
    loop ``relax`` times at the base (their ends where the loop leaves the
    region kept), and the layer within ``width`` of them drawn ``inset``
    towards ``c`` at the edge (a cloth layer's lip over a form tapered)."""

    bone: str
    radius: Vec
    edge: float
    offset: Vec = (0.0, 0.0, 0.0)
    mirror: bool = False
    only: tuple[str, ...] = ()
    groups: tuple[int, ...] = ()
    relax: int = 0
    inset: float = 0.0
    width: float = 0.0
    name: str = ""


@dataclass(frozen=True)
class BindOp:
    """One ``bind`` op (Step 2.154, D438): each vertex of ``groups`` in the
    ellipsoid of half axes ``radius`` about ``c`` (and its mirror) takes
    the skin weights of the nearest vertex of ``to`` in the final shape
    (a cloth over a big form follows the skin under it in every pose,
    where their own weights would part them by centimetres)."""

    bone: str
    radius: Vec
    to: tuple[int, ...]
    offset: Vec = (0.0, 0.0, 0.0)
    mirror: bool = False
    only: tuple[str, ...] = ()
    groups: tuple[int, ...] = ()
    name: str = ""
    reach: float = 0.0
    """Above 0 (Step 2.154 round 6, D512): the weights of every ``to``
    vertex within this distance mixed by ``(1 - d^2 / reach^2)^2`` (the
    nearest alone where none is), so neighbouring cloth vertices take
    neighbouring weights: the nearest alone jumps between the bones of a
    neck and a shoulder, and her strap tore into slivers when she moved.
    With a reach a layer may bind to its own group (round 7): its weights
    mixed within the reach, so a skin under a strap bound the same way
    bends as the strap does and doesn't show through it."""
    fade: bool = False
    """The bound weights mixed with the vertex's own by the region's
    falloff ``(1 - d^2)^2`` (all bound at the centre, its own at the
    edge), so the cloth has no seam of weights where the region ends."""
    near: tuple[float, float] | None = None
    """(full, none) (Step 2.154 round 10, D582): the bound weights mixed
    with the vertex's own by its distance to the ``to`` layer's surface in
    the final shape (its triangles sampled every :data:`NEAR_STEP`): all
    bound within ``full``, its own past ``none`` (a smoothstep between), so
    the skin under a strap takes the strap's weights and the skin beside
    it, an arm's, keeps its own.  (Since round 10 a bind
    reads the ``to`` layer's weights as the binds before it left them:
    the strap's mix, not its vanilla weights.)"""


@dataclass(frozen=True)
class ReweightOp:
    """One ``reweight`` op (Step 2.154, D438): in the ellipsoid of half
    axes ``radius`` about ``c`` (and its mirror, ``take`` and ``into``
    mirrored), each selected vertex moves ``share`` of the weight it has
    on the bones ``take`` onto the bone ``into``, times the ellipsoid's
    smooth falloff ``(1 - d^2)^2`` and, with ``z`` [from, to], a smoothstep
    of its height from 0 at ``from`` to 1 at ``to`` (a big butt's cheek
    held by the pelvis, its fold by the thigh)."""

    bone: str
    radius: Vec
    take: tuple[str, ...]
    into: str
    share: float
    z: tuple[float, float] | None = None
    offset: Vec = (0.0, 0.0, 0.0)
    mirror: bool = False
    only: tuple[str, ...] = ()
    groups: tuple[int, ...] = ()
    name: str = ""
    x: tuple[float, float] | None = None
    """[from, to]: times a smoothstep of the vertex's |x| from 0 at
    ``from`` to 1 at ``to`` (Step 2.154 round 3: an inner cheek left to
    the thigh)."""


@dataclass(frozen=True)
class UnwrapOp:
    """One ``unwrap`` op (Step 2.154, D456): the UVs of the region inside
    the ellipsoid of half axes ``radius`` about ``c`` (and its mirror)
    spread again over the final shape, each texture island's edge pulled
    ``shrink`` of the way to its middle (module docstring)."""

    bone: str
    radius: Vec
    offset: Vec = (0.0, 0.0, 0.0)
    mirror: bool = False
    only: tuple[str, ...] = ()
    groups: tuple[int, ...] = ()
    shrink: float = 0.0
    name: str = ""


@dataclass(frozen=True)
class IslandOp:
    """One ``island`` op (Step 2.154 round 3, D456, D482): the triangles
    of ``groups`` whose base centroid lies in the ellipsoid of half axes
    ``radius`` about ``c`` (each side of a mirrored op its own, by the
    side of x = 0 its centroid lies on) cut off as a texture island of
    their own (their vertices split from every other triangle's: a UV
    seam), its UVs the harmonic map of the final shape with its outer
    edge on the ellipse in ``rect`` (u0, v0, u1, v1; ``rects`` one a
    side; its groups' vertices at one stored place laid as one, round 9:
    a surface two groups share), so a form's skin is painted for itself (her mirrored halves
    share every texel in vanilla's layout).  With ``uv`` (u0, v0, u1,
    v1; round 8, D552) only the triangles whose corners' UVs lie in that
    box of vanilla's layout are the island, and they keep vanilla's
    layout, every UV stretched by one map from the box onto the rect,
    its seams kept: her face, which vanilla's artist gave a sixth of the
    texels across that it gave her eyes, painted at four times the
    atlas's density.  Its material must be repainted (the recipe's
    ``textures``)."""

    bone: str
    radius: Vec
    rects: tuple[tuple[float, float, float, float], ...]
    offset: Vec = (0.0, 0.0, 0.0)
    mirror: bool = False
    only: tuple[str, ...] = ()
    groups: tuple[int, ...] = ()
    name: str = ""
    uv: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class AtlasOp:
    """One ``atlas`` op (Step 2.154 round 3): every UV of ``groups``
    outside an island laid into ``rect`` (u0, v0, u1, v1) of a bigger
    texture, so islands fit beside the old layout; the material is
    repainted (the recipe's ``textures``)."""

    groups: tuple[int, ...]
    rect: tuple[float, float, float, float]
    name: str = ""


@dataclass(frozen=True)
class TubeOp:
    """One ``tube`` op (Step 2.154 round 3, D485, D488): new geometry, a
    tube along the Catmull-Rom curve through ``path`` (offsets from
    ``bone``'s bind origin; ``closed`` a loop), its cross-section an
    ellipse of half axes ``radius`` (one a path point, interpolated) across
    (``across``'s direction, made square to the curve) and ``flat`` of it
    deep, ``rings`` rings of ``sides`` points (a multiple of 4 that halves
    to 4: 8, 16, 32), an open tube's last ring closed by a tip point; it
    joins mesh group ``group`` at its end, its UVs round it across ``rect``
    (u0..u1) and along it (v0..v1), its weights ``bone``'s, or with
    ``follow`` the nearest vertex's of those groups at the base.  No other
    op moves it.  ``segments`` n names shares along it (``name 1`` .. ``name
    n``: hats over its length, all 0 at its root, the last 1 at its tip) a
    jiggle bone's ``shape`` takes: a ponytail's chain (D485)."""

    bone: str
    path: tuple[Vec, ...]
    radius: tuple[float, ...]
    group: int
    rect: tuple[float, float, float, float]
    sides: int = 16
    rings: int = 32
    flat: float = 1.0
    across: Vec = (1.0, 0.0, 0.0)
    closed: bool = False
    follow: tuple[int, ...] = ()
    segments: int = 0
    name: str = ""
    fade: tuple[str, float, float] | None = None
    """(bone, from, to) (Step 2.154 round 6, D512): its weights ``bone``'s
    at its root, eased by a smoothstep of the share of its length from
    ``from`` to ``to`` onto this bone's (a ponytail tied at the head and
    lying on the back: its tip moves with the back, not the head)."""
    reach: float | tuple[float, ...] = 0.0
    """Above 0 (round 6, D512): its weights the ``follow`` groups' in the
    final shape, every vertex within ``reach`` of it mixed as a ``bind``'s
    (a necklace lying on a form the ops moved far from where the base's
    nearest vertex is: that one's weights would tear it in a pose); since
    round 10 (D582) its jiggle shares the same mix of theirs
    (:func:`followers`: a pendant between two breasts swings with them);
    since round 11 (D605) one a path point, interpolated along it as its
    ``radius`` (a chain's runs over the shoulders following the skin right
    under them, its reach kept by the pendant)."""
    facets: bool = False
    """(Step 2.154 round 8, D533: "a small faceted gem") each triangle its
    own three vertices with its face's normal, so it shades flat: a cut
    gem's facets, not a smooth bead."""
    smooth: float | tuple[float, ...] = 0.0
    """Above 0, with ``reach`` (round 11b: a chain's runs bending alike in
    a pose, with no Z where neighbouring points took unlike weights):
    each ring's weights the mean of its points', low-passed along the tube
    by a Gaussian of that sigma between the rings' centres (a loop's both
    ways round) and given to every point of the ring; one a path point,
    interpolated along it as ``reach``, a ring at 0 keeping its points'
    own (a pendant's drop); its jiggle share stays its reach's."""
    under: float | tuple[float, ...] = 0.0
    """From 0 to 1, with ``reach`` (round 11b: a chain gone into her where
    its weights weren't the skin's right under it): that share of each
    ring's weights the ``follow`` groups' final surface's at the point of
    their triangles nearest the ring's centre (its corners' weights, bound
    where a bind gave some, by its barycentric coordinates), the rest its
    reach's mix; one a path point as ``reach``, before ``smooth``; its
    jiggle share stays its reach's."""
    skip: tuple[str, ...] = ()
    """Bones whose weights its reach (and ``under``) gives their nearest
    ancestor not listed, before ``smooth`` (Step 2.154b: a chain over her
    collarbones took a little of her arm where the skin under it does, and
    her arm's swing stepped it into a Z)."""
    hang: str = ""
    """A name, with ``reach`` (Step 2.168r): after W29's reskin every
    vertex of the tubes hung under one name takes one weight set, the mean
    of theirs (its four heaviest bones), so a pendant moves as one piece
    (her gem across her cleavage took each breast on its own side and
    stretched into a rod as they moved apart); the jiggle bones' places are
    their vertices' own weights' as before (:func:`followers`)."""


@dataclass(frozen=True)
class ThickenOp:
    """One ``thicken`` op (Step 2.177d, D698: booblord_high's sash, whose
    folds and hem edges showed a sheet of no thickness): the two-sided
    layer of ``groups`` whose triangles' centroids lie in the ellipsoid of
    half axes ``radius`` about ``c`` (and its mirror) and whose corners it
    selects (``only``/``keep``, as a field op), its two sides (the copies
    of a point whose faces there look opposite ways) moved ``depth`` apart
    in the final shape, each along its own side's normal there, and each
    edge the two sides leave open together (one face a side) joined by a
    rim of two triangles facing out of the layer (:func:`_rims`)."""

    bone: str
    radius: Vec
    depth: float
    offset: Vec = (0.0, 0.0, 0.0)
    mirror: bool = False
    only: tuple[str, ...] = ()
    groups: tuple[int, ...] = ()
    name: str = ""
    taper: float = 0.0
    """(Step 2.187, D724, AZ-735: a step showed below her belt where the
    sash's thick part began.)  Above 0, each point's depth eased from none
    where the layer meets the cloth it doesn't thicken (its points a
    triangle outside it shares) to the full depth this far from there (the
    nearest such point at the base, a smoothstep), so the layer's top edge
    ends flush and its far edges keep the full depth; no rim where neither
    end moves.  0, the default: every point its full depth."""


@dataclass(frozen=True)
class CutOp:
    """One ``cut`` op (Step 2.154 round 6, D513: her sash cut on a
    diagonal): the triangles of ``groups`` whose final centroid lies in
    the ellipsoid of half axes ``radius`` about ``c`` (the bone's origin
    plus ``offset``, which the plane passes through) and whose corners lie
    on the plane's far side (``normal``'s) removed, those it crosses cut
    along it, so the layer ends in one clean edge (:func:`_cut`).  With
    ``press`` (depth, width, swell, thick, origin) the cloth by its new
    edge and the ``under`` skin are drawn in (:func:`_press`); with
    ``trim`` (radius, flat, sides, rect) a cord rides the edge."""

    bone: str
    normal: Vec
    radius: Vec
    groups: tuple[int, ...]
    offset: Vec = (0.0, 0.0, 0.0)
    only: tuple[str, ...] = ()
    name: str = ""
    under: tuple[int, ...] = ()
    press: tuple[float, float, float, float, Vec] | None = None
    """(depth, width, swell, thick, origin): within ``width`` of the new
    edge (along the surface, by the nearest edge point) the cloth and the
    skin under it sink ``depth`` towards ``origin`` (the bone's origin
    plus it) at the edge, easing to nothing at ``width``; the cloth more,
    to ``thick`` over its skin there; the skin past the edge rises back
    over ``width`` / 4 and swells ``swell`` over the next ``width``: a
    band of cloth pressed into soft skin."""
    trim: tuple[float, float, int, tuple[float, float, float, float]] | None = None
    """(radius, flat, sides, rect): a cord of the layer's own material
    along each run of the new edge, its section ``radius`` across and
    ``flat`` of it deep (against the surface), ``sides`` round, its UVs
    across ``rect`` (u0..u1 round it, v0..v1 along it), riding the edge
    in the final shape and taking its weights."""
    snap: bool = False
    """(Round 9, D549: her sash's edge one straight line.)  After the press,
    each point of the new edge moved onto the cut's surface in the final
    shape (the hems' insets and the press had moved it up to 8 mm off its
    line), and with ``trim`` one cord through every point of the edge (a
    chain from its end farthest back along the line, nearest point after
    nearest), smoothed and resampled evenly where the edge lies after the
    snap (:func:`_ride`): no break, no corner from an uneven crossing."""
    corner: tuple[Vec, Vec, float] | None = None
    """(normal, offset, radius; round 9): a second plane through the bone's
    origin plus ``offset`` along ``normal``, the layer kept on the near
    side of both, their corner rounded to ``radius`` (the band's foot
    rounded into its lower hem)."""
    uv: tuple[float, float, float, float] | None = None
    """(u0, v0, u1, v1; round 9, D552): only the layer's triangles whose
    corners' UVs lie in that box of the body's layout: a strand of her hair
    that vanilla modelled as a fin of her face's own skin, ended above the
    brow and her skin under it kept."""
    foot: tuple[float, float] | None = None
    """(length, lift; round 11): a snapped cut's cord lifted ``lift`` off
    its edge over ``length`` from its lower end, easing (a smoothstep) to
    none over :data:`CORD_FOOT_EASE` past it: no skin showing past the
    cord on the band's foot."""


Op = (ScaleOp | PushOp | TaperOp | TuckOp | SubdivideOp | RoundOp | UnwrapOp | HemOp | BindOp | ReweightOp | RelaxOp
      | IslandOp | AtlasOp | TubeOp | CutOp | ThickenOp)


@dataclass(frozen=True)
class MeshSpec:
    """A recipe's ``mesh``: a glTF edit (its file and sha256), the bones
    whose vertices the ops keep, the ops, and how the glTF is read."""

    gltf: tuple[str, str] | None = None
    keep: tuple[str, ...] = ()
    ops: tuple[Op, ...] = ()
    gltf_import: str = "positions"
    """How the glTF is read: ``positions`` (Step 2.142, the same topology),
    or (Step 2.154) ``topology`` or ``weights``
    (:mod:`azurik_mod.assets.gltf_import`)."""
    drop: tuple[str, ...] = ()
    """The bone subtrees whose vertices leave LOD 0 (the module docstring's drop, :func:`_drop`)."""


SIZES = {RoundOp: "round", ScaleOp: "scale"}
"""The op kinds a recipe's ``shapes`` (Step 2.164b, D455: a slider's
value) can size (:func:`sized`); a shape naming an op of another kind is
refused by name (the 2.164 critique's B16)."""


def sized(op: Op, value: float) -> Op:
    """``op`` with its size numbers at ``value`` (Step 2.164b, D455;
    ``value`` 1 returns ``op`` itself, so a shape at 1.0 writes no other
    byte).  A ``round``'s form scaled by ``value`` about its rays' root
    (the point ``origin`` behind its centre, or a ``pair``'s one origin on
    x = 0, whose centre's x is scaled about the bone's) across and along
    its direction only (the 2.164b looks judge: a bust grows forward and
    out, a butt back, a hip out): its ``across``, ``along``, ``back`` and
    ``inner`` half axes, ``origin`` and the back taper's reach times it,
    its centre moved along the direction's level part by ``(value - 1)
    origin``, so a form grows from its root inside the body.  Its ``up``
    and ``down`` half axes, low taper, centre's height and ``inward`` are
    kept: its top and underside stay where they were (a bust over her
    belt, a butt and hips over the shorts' hem and under the sash's
    belt), and its rays' origin moves only up or down, by ``(value - 1)
    origin`` times the direction's fall (the 2.164b review's D3: never
    across).  Its drape's anchor, blends, gates and windows are kept.  A
    ``scale``'s factors on the axes it scales (each other than 1) times
    it, about its centre.  :class:`ValueError` for another kind."""
    if value == 1.0:
        return op
    if isinstance(op, RoundOp):
        n, grow = push_frame(op.direction)[0], (value - 1.0) * op.origin
        x = op.offset[0] * value if op.pair else op.offset[0] + grow * n[0]
        return replace(op, radius=(op.radius[0] * value, op.radius[1] * value, op.radius[2], op.radius[3]),
                       origin=op.origin * value, back=op.back * value,
                       inner=op.inner * value, taper_back=(op.taper_back[0], op.taper_back[1] * value),
                       offset=(x, op.offset[1] + grow * n[1], op.offset[2]))
    if isinstance(op, ScaleOp):
        return replace(op, factors=tuple(f if f == 1.0 else f * value for f in op.factors))
    raise ValueError(f"a {type(op).__name__[:-2].lower()} op has no size a shape scales "
                     f"(only {' and '.join(SIZES.values())} ops)")


def shaped(spec: MeshSpec, values: dict[str, float]) -> MeshSpec:
    """``spec`` with every op named in ``values`` (op name: value) sized
    by its value (:func:`sized`; Step 2.164b): the ops a recipe's
    ``shapes`` name, each value the shape's."""
    return replace(spec, ops=tuple(sized(op, values[op.name]) if getattr(op, "name", "") in values else op
                                   for op in spec.ops))


@dataclass(frozen=True)
class GltfEdit:
    """A glTF edit as read: the file's sha256 (a ``.glb``'s bytes;
    a ``.gltf``'s, then each external buffer's in order), the attribute
    the ids came from, the mesh's glTF vertices, how many copies merged
    into their id, the meshes ignored (no id), whether the file is y up,
    and the model-frame position of each vertex it moves (by index into
    the body's LOD-0 vertices)."""

    sha256: str
    carrier: str
    vertices: int
    merged: int
    ignored: tuple[str, ...]
    swapped: bool
    moved: dict[int, Vec]


@dataclass(frozen=True)
class MeshPlan:
    """What :func:`write` writes into the body ``body`` (of ``vertices``
    LOD-0 vertices): float32 positions and unit normals by (group,
    index); the largest move (model units); the recipe's ops and the ops
    after mirrors; the triangles turned over; the least det J the ops
    give (``None`` with no op moving a vertex); the glTF edit, if any; how
    many vertices the ``tuck`` ops moved; and, when ``subdivide`` ops
    changed the topology, how many vertices they added, the subdivided
    mesh (new vertices at the end of their groups), every vertex's final
    float32 position and unit normal."""

    body: str
    vertices: int
    positions: dict[tuple[int, int], Vec]
    normals: dict[tuple[int, int], Vec]
    largest: float
    ops: int
    placed: int
    turned: int
    det_min: float | None
    gltf: GltfEdit | None
    tucked: int = 0
    added: int = 0
    mesh: _Mesh | None = None
    final: tuple[Vec, ...] = ()
    every_normal: tuple[Vec, ...] = ()
    imported: object = None
    rounded: int = 0
    uvs: dict = None
    skins: dict = None
    """The skin weights a ``bind`` gave, by vertex (the subdivided mesh's
    index): {bone: weight}."""
    repaint: tuple[int, ...] = ()
    """The groups whose UVs an ``island`` or ``atlas`` op laid anew (their
    materials must be repainted: the recipe's ``textures``)."""
    late: dict = None
    """Each ``late`` scale's move by vertex (group, index) (Step 2.187):
    in the written positions, which W29 takes back off to place its jiggle
    bones (:func:`~azurik_mod.assets.jiggle.rig`'s ``late``)."""
    dropped: tuple[int, ...] = ()
    """The LOD-0 groups the drop took off (Step 4.3: :func:`_drop`), which :func:`assemble` leaves out."""


# --------------------------------------------------------------------------- the body
@dataclass(frozen=True)
class _Mesh:
    body: str
    lods: int
    groups: tuple[MeshGroup, ...]
    ids: tuple[tuple[int, int], ...]
    keys: tuple[bytes, ...]              # each vertex's position bytes (the weld)
    positions: tuple[Vec, ...]
    normals: tuple[Vec, ...]
    uvs: tuple[tuple[float, float], ...]
    skins: tuple[dict[int, float], ...]  # bone -> summed weight
    heaviest: tuple[int, ...]
    triangles: tuple[tuple[int, int, int], ...]
    names: tuple[str, ...]
    parents: tuple[int, ...]
    origins: tuple[Vec, ...]
    binds: tuple[tuple[float, ...], ...]
    corners: tuple = ()
    """Each triangle's corners' source UVs, where an ``island`` joined
    vertices vanilla's UV seams kept apart (Step 2.154 round 3: W30 reads the
    old texture through them); empty: each vertex's own."""
    fixed: frozenset = frozenset()
    """The vertices a ``tube`` made: no op moves them."""
    segments: tuple = ()
    """Each ``tube``'s named shares: ((name, {vertex: share}), ...)."""
    cuts: tuple = ()
    """Each ``cut`` op's new edge: ((op index, (vertex, ...)), ...)."""
    trims: tuple = ()
    """Each ``cut`` trim's vertex, the edge vertex it rides and its offset
    from that vertex's approximate final position: ((k, src, offset), ...)."""
    tubes: tuple = ()
    """Each ``tube`` with ``reach``: (op index, its vertices, each one's
    reach)."""
    splines: tuple = ()
    """Each ``snap`` cut's one cord, laid at the ride: ((op index, the edge's
    chain of vertices, the rings' vertices, the caps, radius, flat, sides,
    the out origin, its foot), ...)."""


def _f32(v) -> Vec:
    """``v`` as float32 holds it."""
    return struct.unpack("<3f", struct.pack("<3f", *v))


def _read_mesh(characters_xbr: bytes, body: str) -> _Mesh:
    index, _ = body_at(characters_xbr, body)
    name = named_resources(characters_xbr)[index][len("characters/"):]
    every = mesh_groups(characters_xbr, name)
    groups = tuple(g for g in every if g.lod == 0)
    if not groups:
        raise ValueError(f"{name} has no mesh to edit")
    meshes = render.body_meshes(characters_xbr, parse_toc(characters_xbr), index)
    if len(meshes) != len(groups):
        raise ValueError(f"{name}: {len(groups)} LOD-0 groups, {len(meshes)} meshes")
    ids, keys, pos, nrm, uvs, skins, heavy, tris = [], [], [], [], [], [], [], []
    for g, me in zip(groups, meshes):
        first = len(ids)
        for j in range(g.count):
            at = g.vertices + VERTEX_SIZE * j
            cell = characters_xbr[at:at + VERTEX_SIZE]
            p, w, n, uv = struct.unpack_from("<3f", cell), struct.unpack_from("<4f", cell, 12), \
                struct.unpack_from("<3f", cell, 28), struct.unpack_from("<2f", cell, 40)
            skin: dict[int, float] = {}
            top, most = 0, -1.0
            for s in range(4):
                if w[s] > 0:
                    b = cell[56 + s]
                    entry = b - 1 if b <= 12 else b - 2
                    if b == 0 or b == 13 or b > 32 or entry >= len(g.bones):
                        raise ValueError(f"{name} group {g.index} vertex {j}: a weight's slot byte is outside "
                                         f"the group's {len(g.bones)}-bone palette")
                    skin[g.bones[entry]] = skin.get(g.bones[entry], 0.0) + w[s]
                    if w[s] > most:
                        top, most = g.bones[entry], w[s]
            ids.append((g.index, j))
            keys.append(bytes(cell[0:12]))
            pos.append(p)
            nrm.append(n)
            uvs.append(uv)
            skins.append(skin)
            heavy.append(top)
        tris += [(first + int(a), first + int(b), first + int(c)) for a, b, c in me.triangles.tolist()]
    bones = bone_records(characters_xbr, name)
    origins = dict(read_body(characters_xbr, name).bones)
    return _Mesh(name, len({g.lod for g in every}), groups, tuple(ids), tuple(keys), tuple(pos), tuple(nrm),
                 tuple(uvs), tuple(skins), tuple(heavy), tuple(tris), tuple(b.name for b in bones),
                 tuple(b.parent for b in bones), tuple(origins[b.name] for b in bones),
                 inverse_binds(characters_xbr, name))


def _sub(a, b) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


NEAR_ROWS = 4_000_000
"""The float64 distances :func:`_nearest` holds at once (queries a chunk
times points)."""


GRID_PAIRS = 1 << 24
"""Past this many points times queries :func:`_nearest` looks in a grid first (Step 2.179)."""


def _nearest(points, queries, key) -> list[int]:
    """For each of ``queries`` the index into ``points`` (each an x, y, z)
    whose ``key(index, query)`` is least, as ``min`` over every index
    gives it (Step X.63): numpy's squared distances keep the few within
    1e-9 of the least (``key`` is the caller's own squared distance, so it
    differs from numpy's by a few ulps at most), and with more than one
    left ``key`` ranks them, its own tie-break and float arithmetic, so
    the answer is the full scan's on every machine.  Past
    :data:`GRID_PAIRS` a query whose kept few lie well inside the grid
    cells round it is answered from those cells' points
    (:func:`_nearest_cells`, Step 2.179: booblord_high's cloth over her
    skin was 10^9 distances), the rest by the full scan."""
    if not len(queries):
        return []
    P = np.asarray(points, np.float64).reshape(-1, 3)
    Q = np.asarray(queries, np.float64).reshape(-1, 3)
    out: list[int | None] = [None] * len(Q)
    rest = np.arange(len(Q))
    if len(P) * len(Q) > GRID_PAIRS and np.isfinite(P).all() and np.isfinite(Q).all():
        rest = _nearest_cells(P, Q, queries, key, out)
    chunk = max(1, NEAR_ROWS // max(len(P), 1))
    for s in range(0, len(rest), chunk):
        rows = rest[s:s + chunk]
        q = Q[rows]
        d = P[:, 0] - q[:, 0, None]
        d *= d
        for c in (1, 2):
            e = P[:, c] - q[:, c, None]
            e *= e
            d += e
        least = d.min(1)
        near = d <= (least * (1.0 + 1e-9) + 1e-300)[:, None]
        count = near.sum(1)
        first = d.argmin(1)
        for r, at in enumerate(rows.tolist()):
            if count[r] == 1:
                out[at] = int(first[r])
            else:
                query = queries[at]
                out[at] = min(np.flatnonzero(near[r]).tolist(), key=lambda j: key(j, query))
    return out


def _nearest_cells(P: np.ndarray, Q: np.ndarray, queries, key, out: list) -> np.ndarray:
    """:func:`_nearest`'s answers from a grid of ``P`` (cells of twice the
    side of a point's share of their box) into ``out``, for each query
    whose kept few all lie under 0.999 of a cell from it: every point
    outside the 27 cells round its own is farther than a cell, so the
    distances, the least and the few kept are the full scan's, each
    distance the same float64 sums of the same squares; the queries it
    leaves (their indices) go to the scan."""
    low = P.min(0)
    span = np.maximum(P.max(0) - low, 1e-9)
    h = 2.0 * fdlibm.cbrt(float(span[0] * span[1] * span[2] / len(P)))
    cp = np.floor((P - low) / h).astype(np.int64)
    cq = np.floor((Q - low) / h).astype(np.int64)
    base = np.minimum(cp.min(0), cq.min(0)) - 1
    dims = np.maximum(cp.max(0), cq.max(0)) - base + 2
    kp = ((cp[:, 0] - base[0]) * dims[1] + (cp[:, 1] - base[1])) * dims[2] + (cp[:, 2] - base[2])
    kq = ((cq[:, 0] - base[0]) * dims[1] + (cq[:, 1] - base[1])) * dims[2] + (cq[:, 2] - base[2])
    order = np.argsort(kp, kind="stable")
    sk = kp[order]
    steps = np.array([(a * dims[1] + b) * dims[2] + c for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)])
    cells = kq[:, None] + steps[None, :]
    starts = np.searchsorted(sk, cells, "left")
    counts = np.searchsorted(sk, cells, "right") - starts
    bound = fdlibm.sq(0.999 * h)
    rest = []
    per = counts.sum(1)
    s = 0
    while s < len(Q):       # runs of queries holding about NEAR_ROWS pairs
        e = max(s + 1, int(np.searchsorted(np.cumsum(per[s:]), NEAR_ROWS, "right")) + s)
        flat, at, mine = counts[s:e].ravel(), starts[s:e].ravel(), per[s:e]
        total = int(flat.sum())
        rows = np.repeat(np.arange(e - s), mine)
        j = order[np.arange(total) - np.repeat(np.cumsum(flat) - flat, flat) + np.repeat(at, flat)]
        q = Q[s:e]
        d = P[j, 0] - q[rows, 0]
        d *= d
        for c in (1, 2):
            x = P[j, c] - q[rows, c]
            x *= x
            d += x
        firsts = np.cumsum(mine) - mine
        has = mine > 0
        least = np.full(e - s, np.inf)
        least[has] = np.minimum.reduceat(d, firsts[has])
        keep = least * (1.0 + 1e-9) + 1e-300
        near = d <= keep[rows]
        for r in range(e - s):
            if not (has[r] and keep[r] < bound):
                rest.append(s + r)
                continue
            lo, hi = firsts[r], firsts[r] + mine[r]
            kept = j[lo:hi][near[lo:hi]]
            if len(kept) == 1:
                out[s + r] = int(kept[0])
            else:
                query = queries[s + r]
                out[s + r] = min(sorted(kept.tolist()), key=lambda i: key(i, query))
        s = e
    return np.array(rest, np.int64)


def _face(p: list[Vec] | tuple[Vec, ...], t: tuple[int, int, int]) -> Vec:
    a = p[t[0]]
    return _cross(_sub(p[t[1]], a), _sub(p[t[2]], a))


# --------------------------------------------------------------------------- the deform
@dataclass(frozen=True)
class _Placed:
    """An op after mirrors: its label, the op, its centre, a push's frame
    (n, s, t: its direction mirrored with it), its ``only`` (mirrored) and
    the vertices it may move."""

    label: str
    op: Op
    centre: Vec
    frame: tuple[Vec, Vec, Vec] | None
    moves: frozenset[int]
    bones: frozenset[int] | None = None
    kept: frozenset[int] = frozenset()
    rays: tuple[float, ...] = ()
    """A round side's ray origin (s, n, t from the centre in its frame)
    and its drape's anchor line (n, t from the centre, and its forward
    tilt per unit of s)."""
    origin: Vec | None = None
    """A ``pair``'s one ray origin (model frame, on x = 0)."""
    inward_sign: float = 0.0
    """The sign of a step along the side's across axis that moves towards x = 0."""

    def selects(self, heaviest: int, group: int) -> bool:
        """Whether the op may move a vertex of ``group`` whose heaviest
        weight is on bone ``heaviest`` (its ``only``, else not ``keep``;
        its ``groups``)."""
        return ((heaviest in self.bones) if self.bones is not None else heaviest not in self.kept) and \
            (not self.op.groups or group in self.op.groups)


def _subtree(mesh: _Mesh, roots: set[str]) -> set[int]:
    """The bones under (and at) ``roots``."""
    out = set()
    for k in range(len(mesh.names)):
        a = k
        while a >= 0:
            if mesh.names[a] in roots:
                out.add(k)
                break
            a = mesh.parents[a]
    return out


_SIDES = {"left": "right", "right": "left", "Left": "Right", "Right": "Left"}


def _mirrored(name: str) -> str:
    return re.sub("left|right|Left|Right", lambda m: _SIDES[m.group()], name)


def push_frame(direction: Vec) -> tuple[Vec, Vec, Vec]:
    """A push's (n, s, t) for ``direction`` (module docstring);
    :class:`ValueError` for a zero or vertical one (no up across it)."""
    length = _norm(direction)
    if not length > 0:
        raise ValueError("dir is zero")
    n = (direction[0] / length, direction[1] / length, direction[2] / length)
    t = (-n[2] * n[0], -n[2] * n[1], 1.0 - n[2] * n[2])
    up = _norm(t)
    if not up > 1e-6:
        raise ValueError("dir is straight up or down, so no up lies across it")
    t = (t[0] / up, t[1] / up, t[2] / up)
    return n, _cross(t, n), t


def _place(mesh: _Mesh, spec: MeshSpec) -> list[_Placed]:
    """The ops after mirrors (W-3: every bone they name is the body's)."""
    have = set(mesh.names)
    for name in spec.keep:
        if name not in have:
            raise ValueError(f"mesh.keep: {mesh.body} has no bone {name!r}")
    kept = _subtree(mesh, set(spec.keep))
    indices = {g.index for g in mesh.groups}
    out = []
    for i, op in enumerate(spec.ops):
        if isinstance(op, (TuckOp, SubdivideOp, RoundOp, UnwrapOp, HemOp, BindOp, ReweightOp, RelaxOp, IslandOp,
                           AtlasOp, TubeOp, CutOp, ThickenOp)):
            continue
        if op.bone not in have:
            raise ValueError(f"mesh.ops[{i}].bone: {mesh.body} has no bone {op.bone!r}")
        for g in op.groups:
            if g not in indices:
                raise ValueError(f"mesh.ops[{i}].groups: {mesh.body} has no LOD-0 group {g} "
                                 f"(it has {', '.join(map(str, sorted(indices)))})")
        if getattr(op, "region", False) or getattr(op, "late", False):   # a share field only (Step 2.168): no
            continue       # move, no subdivision's estimate; a late scale moves last (:func:`_late`, Step 2.187)
        origin = mesh.origins[mesh.names.index(op.bone)]
        centre = (origin[0] + op.offset[0], origin[1] + op.offset[1], origin[2] + op.offset[2])
        way = op.direction if isinstance(op, PushOp) else None
        sides = [(f"ops[{i}]", centre, way, op.only)]
        if getattr(op, "mirror", False):
            if abs(centre[0]) <= COPIES:
                raise ValueError(f"mesh.ops[{i}].mirror: its centre is on x = 0, so it is its own mirror and would "
                                 "move its region twice: drop mirror")
            sides.append((f"ops[{i}] mirrored", (-centre[0], centre[1], centre[2]),
                          None if way is None else (-way[0], way[1], way[2]), tuple(_mirrored(n) for n in op.only)))
        for label, c, d, only in sides:
            for name in only:
                if name not in have:
                    raise ValueError(f"mesh.{label}.only: {mesh.body} has no bone {name!r}")
            try:
                frame = None if d is None else push_frame(d)
            except ValueError as exc:
                raise ValueError(f"mesh.{label}: {exc}") from None
            bones = frozenset(_subtree(mesh, set(only))) if only else None
            moves = frozenset(k for k, b in enumerate(mesh.heaviest)
                              if (b in bones if bones is not None else b not in kept)
                              and (not op.groups or mesh.ids[k][0] in op.groups))
            out.append(_Placed(label, op, c, frame, moves, bones, frozenset(kept)))
    return out


def _effect(p: Vec, placed: _Placed, jac: bool = False):
    """``placed``'s displacement at ``p`` and (``jac``) its Jacobian's
    rows, or ``None`` outside its region (module docstring)."""
    op, c = placed.op, placed.centre
    u = (p[0] - c[0], p[1] - c[1], p[2] - c[2])
    if isinstance(op, ScaleOp):
        r, s = op.radius, op.factors
        q = (u[0] / r[0], u[1] / r[1], u[2] / r[2])
        d2 = q[0] * q[0] + q[1] * q[1] + q[2] * q[2]
        if not d2 < 1.0:
            return None
        if op.profile == "smooth":
            e = 1.0 - d2
            phi = e * e
            grad = (-4.0 * e * q[0] / r[0], -4.0 * e * q[1] / r[1], -4.0 * e * q[2] / r[2])
        else:
            d = math.sqrt(d2)
            w = 1.0 - d
            phi = w * w
            grad = (0.0, 0.0, 0.0) if d == 0.0 else tuple(-2.0 * w * q[j] / (d * r[j]) for j in range(3))
        disp = (phi * (s[0] - 1.0) * u[0], phi * (s[1] - 1.0) * u[1], phi * (s[2] - 1.0) * u[2])
        if not jac:
            return disp, None
        return disp, tuple(tuple((s[i] - 1.0) * ((phi if i == j else 0.0) + u[i] * grad[j]) for j in range(3))
                           for i in range(3))
    if isinstance(op, PushOp):
        n, sa, ta = placed.frame
        un = _dot(u, n)
        if not un > -op.depth:
            return None
        a, bt = _dot(u, sa), _dot(u, ta)
        r_in, r_out, r_up, r_down = op.radius
        ra = r_in if abs(c[0]) > COPIES and a * sa[0] * c[0] < 0.0 else r_out
        rv = r_up if bt > 0.0 else r_down
        big_a, big_b = a / ra, bt / rv
        rho2 = big_a * big_a + big_b * big_b
        if not rho2 < 1.0:
            return None
        if un >= 0.0:
            g, dg = 1.0, 0.0
        else:
            x = (un + op.depth) / op.depth
            g, dg = x * x * (3.0 - 2.0 * x), 6.0 * x * (1.0 - x) / op.depth
        e = 1.0 - rho2
        db_a = db_b = 0.0
        if rho2 == 0.0:
            b = 1.0
        else:
            rho = math.sqrt(rho2)
            hi, gap = e * e * (3.0 - 2.0 * e), 2.0 * e * (1.0 - e) * (1.0 - e)   # the dome; 1 - rho^4 less it
            k = op.fold * (1.0 - big_b / rho) / 2.0
            b = hi + k * gap
            if jac:
                r3 = 2.0 * rho2 * rho
                slope = 6.0 * e * (1.0 - e) + k * 2.0 * (1.0 - e) * (1.0 - 3.0 * e)   # d b / d e; d e / d A = -2 A
                db_a = -2.0 * big_a * slope + op.fold * big_b * big_a / r3 * gap
                db_b = -2.0 * big_b * slope - op.fold * big_a * big_a / r3 * gap
        k = op.height * b * g
        disp = (k * n[0], k * n[1], k * n[2])
        if not jac:
            return disp, None
        grad = tuple(op.height * (g * (db_a / ra * sa[j] + db_b / rv * ta[j]) + b * dg * n[j]) for j in range(3))
        return disp, tuple(tuple(n[i] * grad[j] for j in range(3)) for i in range(3))
    dz = u[2]
    az = abs(dz)
    if az <= op.plateau:
        big_w, dw = 1.0, 0.0
    elif az < op.plateau + op.half:
        kz = (az - op.plateau) / op.half
        e = 1.0 - kz * kz
        big_w, dw = e * e, (-4.0 * e * kz / op.half) * (1.0 if dz > 0 else -1.0)
    else:
        return None
    r0, r1 = op.reach
    r = math.sqrt(u[0] * u[0] + u[1] * u[1])
    if r <= r0:
        big_g, dgr = 1.0, 0.0
    elif r < r1:
        v = (r - r0) / (r1 - r0)
        big_g, dgr = 1.0 - v * v * (3.0 - 2.0 * v), -6.0 * v * (1.0 - v) / (r1 - r0)
    else:
        return None
    f = (1.0 - (1.0 - op.factors[0]) * big_w * big_g, 1.0 - (1.0 - op.factors[1]) * big_w * big_g)
    disp = ((f[0] - 1.0) * u[0], (f[1] - 1.0) * u[1], 0.0)
    if not jac:
        return disp, None
    rows = []
    for i in range(2):
        a = 1.0 - op.factors[i]
        df = (-a * big_w * dgr * u[0] / r if r > 0 else 0.0, -a * big_w * dgr * u[1] / r if r > 0 else 0.0,
              -a * dw * big_g)
        rows.append(tuple((f[i] - 1.0 if i == j else 0.0) + u[i] * df[j] for j in range(3)))
    return disp, (rows[0], rows[1], (0.0, 0.0, 0.0))


def _tucks(mesh: _Mesh, spec: MeshSpec) -> list[tuple[str, TuckOp, tuple[Vec, Vec, Vec], list[int], list]]:
    """The ``tuck`` ops (W-3 as :func:`_place`): each one's label, frame,
    the layer's vertices it may move and its cloth's triangles."""
    have = set(mesh.names)
    kept = _subtree(mesh, set(spec.keep))
    indices = {g.index for g in mesh.groups}
    out = []
    for i, op in enumerate(spec.ops):
        if not isinstance(op, TuckOp):
            continue
        for key, wanted in (("groups", op.groups), ("under", op.under)):
            for g in wanted:
                if g not in indices:
                    raise ValueError(f"mesh.ops[{i}].{key}: {mesh.body} has no LOD-0 group {g} "
                                     f"(it has {', '.join(map(str, sorted(indices)))})")
        if set(op.groups) & set(op.under):
            raise ValueError(f"mesh.ops[{i}]: group {min(set(op.groups) & set(op.under))} is both the layer and the "
                             "cloth: a layer can't tuck behind itself")
        for key, names in (("skip", op.skip), ("only", op.only)):
            for name in names:
                if name not in have:
                    raise ValueError(f"mesh.ops[{i}].{key}: {mesh.body} has no bone {name!r}")
        try:
            frame = push_frame(op.direction)
        except ValueError as exc:
            raise ValueError(f"mesh.ops[{i}]: {exc}") from None
        bones = _subtree(mesh, set(op.only)) if op.only else None
        skipped = _subtree(mesh, set(op.skip))
        moves = [k for k, b in enumerate(mesh.heaviest)
                 if (b in bones if bones is not None else b not in kept) and mesh.ids[k][0] in op.groups
                 and _dot(mesh.normals[k], frame[0]) > 0.0
                 and (op.band is None or op.band[0] <= mesh.positions[k][2] <= op.band[1])]
        cloth = [t for t in mesh.triangles
                 if all(mesh.ids[v][0] in op.under and mesh.heaviest[v] not in skipped for v in t)
                 and _dot(tuple(sum(mesh.normals[v][i] for v in t) for i in range(3)), frame[0]) > 0.0]
        if not cloth:
            raise ValueError(f"mesh.ops[{i}].under: no triangle of groups {list(op.under)} outside skip to tuck behind")
        out.append((f"ops[{i}]", op, frame, moves, cloth))
    return out


def _cloth_over(pos: list[Vec], cloth: list, frame: tuple[Vec, Vec, Vec], window: float):
    """A function of a point: the depth along ``n`` of the cloth's surface
    over it (``pos``'s triangles seen along ``n``: the largest depth not
    more than ``window`` behind the point), or ``None``."""
    n, s, t = frame
    tris = []
    for tri in cloth:
        (ax, ay, ad), (bx, by, bd), (cx, cy, cd) = ((_dot(pos[v], s), _dot(pos[v], t), _dot(pos[v], n)) for v in tri)
        den = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if abs(den) > 1e-12:
            tris.append((ax, ay, ad, bx - ax, by - ay, bd - ad, cx - ax, cy - ay, cd - ad, den,
                         min(ax, bx, cx), max(ax, bx, cx), min(ay, by, cy), max(ay, by, cy)))

    cell = CLOTH_CELL      # a grid over the cloth seen along n: a query reads its cell's triangles only (the same max)
    grid: dict[tuple[int, int], list] = {}
    for tr in tris:
        for i in range(math.floor(tr[10] / cell), math.floor(tr[11] / cell) + 1):
            for j in range(math.floor(tr[12] / cell), math.floor(tr[13] / cell) + 1):
                grid.setdefault((i, j), []).append(tr)

    def over(q: Vec) -> float | None:
        qx, qy, qd = _dot(q, s), _dot(q, t), _dot(q, n)
        best = None
        for ax, ay, ad, ex, ey, ed, fx, fy, fd, den, x0, x1, y0, y1 in grid.get((math.floor(qx / cell),
                                                                                  math.floor(qy / cell)), ()):
            if not (x0 <= qx <= x1 and y0 <= qy <= y1):
                continue
            px, py = qx - ax, qy - ay
            u = (px * fy - py * fx) / den
            v = (ex * py - ey * px) / den
            if u < 0.0 or v < 0.0 or u + v > 1.0:
                continue
            d = ad + u * ed + v * fd
            if d > qd - window and (best is None or d > best):
                best = d
        return best
    return over


def _tuck(base: list[Vec], final: list[Vec], op: TuckOp, frame: tuple[Vec, Vec, Vec], moves: list[int],
          cloth: list, triangles: list) -> None:
    """One ``tuck`` on ``final`` in place (module docstring).  A vertex
    vanilla already has in front of its cloth (or nearer it than
    ``margin``) may stay as far forward as it was, but for a ``strict``
    tuck.  A ``faces`` tuck reads the layer's triangles after its
    vertices, then the vertices again (a triangle's move can leave one of
    its vertices nearer than ``margin``)."""
    n = frame[0]
    now, then = _cloth_over(final, cloth, frame, op.window), _cloth_over(base, cloth, frame, op.window)

    def vertices() -> None:
        for k in moves:
            q = final[k]
            over = now(q)
            if over is None:
                continue
            allowed = -op.margin
            was = None if op.strict else then(base[k])
            if was is not None:
                allowed = max(allowed, _dot(base[k], n) - was)
            poke = _dot(q, n) - over
            if poke > allowed:
                shift = allowed - poke
                final[k] = (q[0] + shift * n[0], q[1] + shift * n[1], q[2] + shift * n[2])
    vertices()
    if op.faces:
        _tuck_faces(base, final, op, n, now, then, set(moves), triangles)
        vertices()


_SAMPLES = ((1 / 3, 1 / 3, 1 / 3), (0.5, 0.5, 0.0), (0.0, 0.5, 0.5), (0.5, 0.0, 0.5))
"""Where a ``faces`` tuck reads a layer triangle: its centroid and its edges' midpoints."""


def _tuck_faces(base: list[Vec], final: list[Vec], op: TuckOp, n: Vec, now, then, mine: set[int],
                triangles: list) -> None:
    """A ``faces`` tuck's passes (at most 4): each triangle of the layer with a vertex the tuck may move, read at
    :data:`_SAMPLES`; a sample nearer the cloth than its allowance (``tuck``'s) moves the triangle's movable vertices
    back along ``n`` so the sample ends on it (a coarse cloth's flat triangle crossing a finer layer between its
    vertices).  One shift a position (a seam's copies move together), the largest asked."""
    tris = [t for t in triangles if any(v in mine for v in t)]
    at: dict[Vec, list[int]] = {}
    for k in mine:
        at.setdefault(base[k], []).append(k)
    for _ in range(4):
        want: dict[Vec, float] = {}
        for t in tris:
            free = [i for i, v in enumerate(t) if v in mine]
            for lam in _SAMPLES:
                w = sum(lam[i] for i in free)
                if w < 0.25:
                    continue
                p = tuple(sum(lam[i] * final[t[i]][j] for i in range(3)) for j in range(3))
                over = now(p)
                if over is None:
                    continue
                allowed = -op.margin
                if not op.strict:
                    b = tuple(sum(lam[i] * base[t[i]][j] for i in range(3)) for j in range(3))
                    was = then(b)
                    if was is not None:
                        allowed = max(allowed, _dot(b, n) - was)
                poke = _dot(p, n) - over
                if poke > allowed + 1e-6:
                    need = (poke - allowed) / w
                    for i in free:
                        key = base[t[i]]
                        want[key] = max(want.get(key, 0.0), need)
        if not want:
            break
        for key, need in want.items():
            for k in at[key]:
                q = final[k]
                final[k] = (q[0] - need * n[0], q[1] - need * n[1], q[2] - need * n[2])


def _displace(p: Vec, ops: list[_Placed]) -> tuple[Vec, bool]:
    """``p`` moved by ``ops`` (each on ``p``), and whether any holds it."""
    dx = dy = dz = 0.0
    inside = False
    for op in ops:
        got = _effect(p, op)
        if got is None:
            continue
        inside = True
        d = got[0]
        dx += d[0]
        dy += d[1]
        dz += d[2]
    return (p[0] + dx, p[1] + dy, p[2] + dz), inside


def _det(p: Vec, ops: list[_Placed]) -> float:
    """det J of the deform at ``p``: I plus each op's Jacobian
    (:func:`_effect`; at a centre a gradient's singular term is 0)."""
    m = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    for op in ops:
        got = _effect(p, op, True)
        if got is None:
            continue
        for i in range(3):
            for j in range(3):
                m[i][j] += got[1][i][j]
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


# --------------------------------------------------------------------------- the round ops
def _side_name(name: str, mirrored: bool) -> str:
    """A side's name: a mirrored op's mirror takes its name with left and
    right swapped (``breast right`` -> ``breast left``: a jiggle bone a
    side), a name with neither is both sides' (``bust``)."""
    return _mirrored(name) if mirrored else name


def _rounds(mesh: _Mesh, spec: MeshSpec) -> list[list[_Placed]]:
    """The ``round`` ops in recipe order, each as its sides (one, or two
    for a mirrored op: they act together), W-3 as :func:`_place`.  A
    ``pair``'s sides carry their one origin on x = 0, which must lie
    inside both forms."""
    have = set(mesh.names)
    kept = frozenset(_subtree(mesh, set(spec.keep)))
    indices = {g.index for g in mesh.groups}
    out = []
    for i, op in enumerate(spec.ops):
        if not isinstance(op, RoundOp):
            continue
        if op.bone not in have:
            raise ValueError(f"mesh.ops[{i}].bone: {mesh.body} has no bone {op.bone!r}")
        for g in op.groups:
            if g not in indices:
                raise ValueError(f"mesh.ops[{i}].groups: {mesh.body} has no LOD-0 group {g} "
                                 f"(it has {', '.join(map(str, sorted(indices)))})")
        if not (all(r > 0 for r in op.radius) and 0 <= op.origin and (op.pair or op.origin < op.radius[1])
                and all(k > 0 for k in op.blend)):
            raise ValueError(f"mesh.ops[{i}]: its radius and blend must be above 0 and its origin at least 0 and "
                             "under its radius along (the rays start inside the ellipsoid; a pair's may start behind)")
        if not op.pair and (fdlibm.sq(op.origin / op.radius[1])
                            + fdlibm.sq(op.inward / (op.inner or op.radius[0]))) >= 1.0:
            raise ValueError(f"mesh.ops[{i}]: its origin and inward put the rays' start outside the ellipsoid")
        if op.bridge < 0 or (op.bridge > 0 and not op.mirror):
            raise ValueError(f"mesh.ops[{i}].bridge: a mirrored op's smooth union, at least 0")
        if op.pair and not op.mirror:
            raise ValueError(f"mesh.ops[{i}].pair: a mirrored op's two forms as one: mirror it")
        if op.inner < 0 or op.ease < 0 or (op.ease > 0 and op.drape is None):
            raise ValueError(f"mesh.ops[{i}]: inner and ease are at least 0, and ease eases a drape")
        if op.drape is not None and not 0 <= op.drape[2] < op.drape[3] <= 1:
            raise ValueError(f"mesh.ops[{i}].drape.fade: {list(op.drape[2:4])} must rise within 0 to 1")
        bone = mesh.origins[mesh.names.index(op.bone)]
        centre = (bone[0] + op.offset[0], bone[1] + op.offset[1], bone[2] + op.offset[2])
        sides = [(f"ops[{i}]", centre, op.direction, op.only)]
        if op.mirror:
            if abs(centre[0]) <= COPIES:
                raise ValueError(f"mesh.ops[{i}].mirror: its centre is on x = 0, so it is its own mirror: drop mirror")
            d = op.direction
            sides.append((f"ops[{i}] mirrored", (-centre[0], centre[1], centre[2]), (-d[0], d[1], d[2]),
                          tuple(map(_mirrored, op.only))))
        both = []
        for label, c, d, only in sides:
            for name in only:
                if name not in have:
                    raise ValueError(f"mesh.{label}.only: {mesh.body} has no bone {name!r}")
            try:
                frame = push_frame(d)
            except ValueError as exc:
                raise ValueError(f"mesh.{label}: {exc}") from None
            n, sa, ta = frame
            towards = -1.0 if c[0] > 0.0 else 1.0       # x = 0's side
            shift = (towards * op.inward - op.origin * n[0], -op.origin * n[1], -op.origin * n[2])
            rays = (_dot(shift, sa), _dot(shift, n), _dot(shift, ta))
            if op.drape is not None:
                a = (bone[0] - c[0], bone[1] + op.drape[0] - c[1], bone[2] + op.drape[1] - c[2])
                rays += (_dot(a, n), _dot(a, ta), op.drape[4] * towards * sa[0])
            bones = frozenset(_subtree(mesh, set(only))) if only else None
            both.append(_Placed(label, op, c, frame, frozenset(), bones, kept, rays,
                                inward_sign=1.0 if towards * sa[0] > 0.0 else -1.0))
        if op.pair:     # one origin on x = 0: the mean of the sides' own
            own = [tuple(s.centre[j] + s.rays[0] * s.frame[1][j] + s.rays[1] * s.frame[0][j] + s.rays[2] * s.frame[2][j]
                         for j in range(3)) for s in both]
            o = (0.0, (own[0][1] + own[1][1]) / 2.0, (own[0][2] + own[1][2]) / 2.0)
            both = [replace(s, origin=o) for s in both]
        out.append(both)
    return out


def _smooth(x: float) -> float:
    """The smoothstep of ``x`` clamped to 0..1."""
    return 0.0 if x <= 0.0 else 1.0 if x >= 1.0 else x * x * (3.0 - 2.0 * x)


def _drape_inside(op: RoundOp, an: float, at: float, s: float, n: float, t: float, tilt: float = 0.0,
                  sign: float = 0.0) -> tuple[bool, float, float]:
    """Whether the frame point (s, n, t) above the centre's plane lies in
    the drape's hull (the ellipsoid's section at ``s`` and the anchor line's
    point there, ``tilt`` s further forward, the tangent from it to the
    section's upper half), the point's place from the anchor (0) to the
    tangent point (1) and that tangent's length (``sign``: the side's
    :attr:`_Placed.inward_sign`, for an ``inner`` half axis)."""
    an += tilt * s
    across, along, up, _ = op.radius
    if op.inner > 0.0 and s * sign > 0.0:
        across = op.inner
    k2 = 1.0 - fdlibm.sq(s / across)
    if not k2 > 0.0:
        return False, 0.0, 0.0
    k = math.sqrt(k2)
    big_a, big_b = along * k, up * k
    if fdlibm.sq(n / big_a) + fdlibm.sq(t / big_b) <= 1.0:
        return True, 1.0, 0.0
    pn, pt = an / big_a, at / big_b
    d2 = pn * pn + pt * pt
    if not d2 > 1.0:
        return False, 0.0, 0.0
    c1, c2 = 1.0 / d2, math.sqrt(d2 - 1.0) / d2
    one, two = (pn * c1 - c2 * pt, pt * c1 + c2 * pn), (pn * c1 + c2 * pt, pt * c1 - c2 * pn)
    tn, tt = max(one, two, key=lambda q: q[1])
    tn, tt = big_a * tn, big_b * tt
    if not (an <= n <= tn and tn > an):
        return False, 0.0, 0.0
    lam = (n - an) / (tn - an)
    return t <= at + (tt - at) * lam, lam, math.sqrt(fdlibm.sq(tn - an) + fdlibm.sq(tt - at))


def _drape_exit(op: RoundOp, rays: tuple[float, ...], u: tuple[float, float, float], big_r: float, sign: float = 0.0
                ) -> tuple[float, float, float]:
    """Where a ray (``u`` = its s, n, t parts) leaves the drape's hull, the
    place there from the anchor to the tangent point (1 on the ellipsoid)
    and the tangent's length."""
    os_, on_, ot_, an, at, tilt = rays
    us, un, ut = u
    hi = (at - ot_) / ut
    if un - tilt * us < 0.0:       # the anchor line's place along n at the ray's s: an + tilt s
        hi = min(hi, (an + tilt * os_ - on_) / (un - tilt * us))
    if us != 0.0:
        hi = min(hi, (op.radius[0] * (1.0 if us > 0.0 else -1.0) - os_) / us)
    step = big_r + 1e-6

    def inside(x: float):
        return _drape_inside(op, an, at, os_ + x * us, on_ + x * un, ot_ + x * ut, tilt, sign)

    if not hi > step or not inside(step)[0]:
        return big_r, 1.0, 0.0
    lo = step
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if inside(mid)[0]:
            lo = mid
        else:
            hi = mid
    _, lam, length = inside(lo)
    return lo, lam, length


DRAPE_RISE = (0.15, 0.4)
"""A drape acts on the rays whose upward share passes the first, fully
past the second (a hull of a line and an ellipsoid reaches back along the
ellipsoid's equator, where the rays don't rise: none there)."""


def _exit(op: RoundOp, sign: float, o: tuple[float, float, float], u: tuple[float, float, float],
          checked: bool) -> float:
    """Where a ray from the frame point ``o`` along ``u`` (s, n, t parts)
    leaves the ellipsoid of ``op`` (``up`` above the centre's plane,
    ``down`` below, ``inner`` across on x = 0's side): its half picked by
    the ray's rise from an origin on the plane, else (``checked``) by where
    the first answer leaves; 0 for a ray from outside that misses it."""
    os_, on_, ot_ = o
    us, un, ut = u
    across, along, up, down = op.radius

    def solve(across: float, vert: float) -> float:
        a = fdlibm.sq(us / across) + fdlibm.sq(un / along) + fdlibm.sq(ut / vert)
        b = os_ * us / (across * across) + on_ * un / (along * along) + ot_ * ut / (vert * vert)
        cc = fdlibm.sq(os_ / across) + fdlibm.sq(on_ / along) + fdlibm.sq(ot_ / vert) - 1.0
        disc = b * b - a * cc
        if not disc >= 0.0:
            return 0.0          # a pair's ray from behind the form that misses it: no form along it
        return (-b + math.sqrt(disc)) / a

    if op.taper > 0.0 or op.taper_in > 0.0 or op.taper_back[0] > 0.0 or op.taper_low[0] > 0.0:
        return _exit_tapered(op, sign, o, u)
    if not checked:
        vert = up if ut >= 0.0 else down        # the ray stays in its half: the origin is on the equator's plane
        big_r = solve(across, vert)
        if op.inner > 0.0 and (os_ + big_r * us) * sign > 0.0:
            big_r = solve(op.inner, vert)
        return big_r
    # an origin off the centre's planes: the octant where the answer leaves, found by trying (at most 4 more)
    pick = (ut >= 0.0, un >= 0.0, us * sign > 0.0)
    for _ in range(5):
        hi, front, inward = pick
        along = op.radius[1] if front or not op.back else op.back
        big_r = solve(op.inner if inward and op.inner > 0.0 else across, up if hi else down)
        got = (ot_ + big_r * ut >= 0.0, on_ + big_r * un >= 0.0, (os_ + big_r * us) * sign > 0.0)
        if got == pick:
            break
        pick = got
    return big_r


def _across(op: RoundOp, inward: bool, n: float, t: float) -> float:
    """The across half axis at the frame point's (n, t) on its side of the
    centre (``inward``: towards x = 0): ``inner`` there, narrowed by each
    taper's smoothstep share (``taper``/``taper_in`` above the centre's
    plane; ``taper_back`` behind and ``taper_low`` below it, outer side
    only)."""
    across, along, up, down = op.radius
    if inward and op.inner > 0.0:
        across = op.inner
    taper = op.taper_in if inward else op.taper
    if taper > 0.0 and t > 0.0:
        across *= 1.0 - taper * _smooth(t / up)
    if not inward:
        share, reach = op.taper_back
        if share > 0.0 and n < 0.0:
            across *= 1.0 - share * _smooth(-n / (reach or op.back or along))
        share, reach = op.taper_low
        if share > 0.0 and t < 0.0:
            across *= 1.0 - share * _smooth(-t / (reach or down))
    return across


def _shape(op: RoundOp, sign: float, s: float, n: float, t: float) -> float:
    """The form's implicit value at the frame point (s, n, t): under 1
    inside, 1 on it (each half axis by the point's side of the centre's
    planes, ``across`` by :func:`_across`)."""
    _, along, up, down = op.radius
    if op.back > 0.0 and n < 0.0:
        along = op.back
    vert = up if t >= 0.0 else down
    across = _across(op, s * sign > 0.0, n, t)
    return fdlibm.sq(s / across) + fdlibm.sq(n / along) + fdlibm.sq(t / vert)


def _exit_tapered(op: RoundOp, sign: float, o: tuple[float, float, float], u: tuple[float, float, float]) -> float:
    """:func:`_exit` for a tapered form: the first place past the origin
    where :func:`_shape` reaches 1 (stepped out by an eighth of its least
    half axis, then bisected 40 times); 0 when the origin is outside."""
    os_, on_, ot_ = o
    us, un, ut = u
    if not _shape(op, sign, os_, on_, ot_) < 1.0:
        return 0.0
    step = min(op.radius) / 8.0
    lo, hi = 0.0, step
    while _shape(op, sign, os_ + hi * us, on_ + hi * un, ot_ + hi * ut) < 1.0:
        lo, hi = hi, hi + step
        if hi > 4.0:
            return lo
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if _shape(op, sign, os_ + mid * us, on_ + mid * un, ot_ + mid * ut) < 1.0:
            lo = mid
        else:
            hi = mid
    return lo


_RAYS: list = [None]
"""While a :func:`plan` or :func:`shares_each` runs (Step X.65c), the
answers :func:`_ray` gave, by the point and the values of the side and
origin it read (the subdivision, the pass and the approximations ask
most of the same rays): (the ids of the sides and origins asked, their
values' numbers, the answers)."""


def _memo_rays(fn):
    """``fn`` with :data:`_RAYS` kept for the call (the outer call's if
    one is running)."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        if _RAYS[0] is not None:
            return fn(*args, **kwargs)
        _RAYS[0] = ({}, {}, {})
        try:
            return fn(*args, **kwargs)
        finally:
            _RAYS[0] = None
    return run


def _ray(p: Vec, side: _Placed, origin: Vec | None = None):
    """``side``'s ray through ``p``: its unit direction from the op's
    origin (or ``origin``: a pair's), the distance ``r`` along it, the
    form's ``R`` along it (the ellipsoid's, or its drape's), the blend's
    width there, the gate's weight and the drape's share there (1 off the
    drape); ``None`` at the origin.  Asked again in a plan, the answer it
    gave (:data:`_RAYS`); never kept for a point with a zero coordinate
    (``==`` holds 0.0 and -0.0 the same, and a zero's sign reaches the
    bytes), the side's and origin's floats told apart by their repr."""
    memo = _RAYS[0]
    if memo is None or type(p) is not tuple or 0.0 in p:
        return _ray_at(p, side, origin)
    answers = memo[2]
    key = (_ray_slot(memo, side, origin), p)
    ans = answers.get(key, answers)
    if ans is answers:
        ans = answers[key] = _ray_at(p, side, origin)
    return ans


def _ray_slot(memo: tuple, side: _Placed, origin: Vec | None) -> int:
    """The number :data:`_RAYS` keeps ``side``'s rays (from ``origin``) under: one a side's values."""
    ids, values, _ = memo
    got = ids.get((id(side), id(origin)))
    if got is None:         # the side and origin held, so their ids stay theirs
        value = (id(side.op), repr((side.centre, side.frame, side.rays, side.inward_sign, origin)))
        got = ids[(id(side), id(origin))] = (values.setdefault(value, len(values)), side, origin)
    return got[0]


def _rays_ahead(points, side: _Placed, origin: Vec | None = None) -> None:
    """``side``'s rays through each of ``points`` (from ``origin``) the
    compiled kernel answers, in one call, kept in :data:`_RAYS` for
    :func:`_ray`, which takes each as it would have asked it (a ctypes
    call under Pyodide costs some browsers more than its ray); a point
    :func:`_ray` keeps no answer for, or one the twin answers, is left."""
    memo = _RAYS[0]
    if memo is None or (row := _ray_row(side)) is None:
        return
    answers = memo[2]
    slot = _ray_slot(memo, side, origin)
    todo = list(dict.fromkeys(p for p in points if type(p) is tuple and 0.0 not in p and (slot, p) not in answers))
    got = native.rays(row, todo, origin) if todo else None
    for p, ans in zip(todo, got or ()):
        if ans is not False:
            answers[(slot, p)] = ans


_ROWS: dict[int, tuple] = {}
"""Each round side's :func:`_ray_row`, by its id (with the side, so the id stays its own while kept)."""


def _ray_row(side: _Placed):
    """``side``'s doubles as ``native/mesh.c``'s ``az_ray`` reads them
    (its centre, frame, rays and inward sign, then its op's numbers, each
    optional one after a flag), or ``None`` where the twin must read it."""
    got = _ROWS.get(id(side))
    if got is not None and got[0] is side:
        return got[1]
    from array import array

    op = side.op
    try:
        drape = op.drape is not None
        if drape and len(side.rays) < 6:
            return None
        midline = tuple(op.midline or ())
        line = tuple(op.behind[3]) if op.behind is not None else ()
        row = array("d", [*side.centre, *side.frame[0], *side.frame[1], *side.frame[2], *side.rays[:3],
                          *(side.rays[3:6] if drape else (0.0,) * 3), side.inward_sign, *op.radius, op.taper,
                          op.taper_in, *op.taper_back, *op.taper_low, op.back, op.inner, float(drape),
                          *(op.drape if drape else (0.0,) * 5), op.ease, float(op.inner_blend is not None),
                          *(op.inner_blend or (0.0,) * 3), *op.blend, float(op.gate is not None),
                          *(op.gate or (0.0,) * 2), float(len(midline)), *midline, *(0.0,) * (5 - len(midline)),
                          float(op.behind is not None), *(op.behind[:3] if op.behind is not None else (0.0,) * 3),
                          float(len(line)), float(op.window is not None), *(op.window or (0.0,) * 4),
                          *(x for q in line for x in q)])
    except (TypeError, ValueError):
        return None
    if len(row) != 63 + 2 * len(line) or len(midline) not in (0, 3, 4, 5):
        return None
    if len(_ROWS) >= 4096:
        _ROWS.clear()
    _ROWS[id(side)] = (side, row)
    return row


def _ray_at(p: Vec, side: _Placed, origin: Vec | None = None):
    """:func:`_ray`, asked: the compiled kernel's (``core.native.ray``), else its twin's."""
    if (row := _ray_row(side)) is not None and (got := native.ray(row, p, origin)) is not False:
        return got
    op, c = side.op, side.centre
    n, sa, ta = side.frame
    if origin is None:
        os_, on_, ot_ = side.rays[:3]
        o = tuple(c[i] + os_ * sa[i] + on_ * n[i] + ot_ * ta[i] for i in range(3))
    else:
        o = origin
        d = (o[0] - c[0], o[1] - c[1], o[2] - c[2])
        os_, on_, ot_ = _dot(d, sa), _dot(d, n), _dot(d, ta)
    q = (p[0] - o[0], p[1] - o[1], p[2] - o[2])
    r = _norm(q)
    if not r > 0.0:
        return None
    u = (q[0] / r, q[1] / r, q[2] / r)
    us, un, ut = _dot(u, sa), _dot(u, n), _dot(u, ta)
    across = op.radius[0]
    big_r = _exit(op, side.inward_sign, (os_, on_, ot_), (us, un, ut), origin is not None)
    ramp = 1.0
    if op.drape is not None and ut > DRAPE_RISE[0]:
        far, lam, length = _drape_exit(op, (os_, on_, ot_) + side.rays[3:6], (us, un, ut), big_r, side.inward_sign)
        if far > big_r:      # faded out by its section's place across, from fade[0] of the half axis to fade[1]
            lo, hi = op.drape[2], op.drape[3]
            fade = (1.0 - _smooth((abs(os_ + far * us) / across - lo) / (hi - lo))) \
                * _smooth((ut - DRAPE_RISE[0]) / (DRAPE_RISE[1] - DRAPE_RISE[0]))
            if op.ease > 0.0:       # eased in from the anchor: the slope leaves the chest tangent to it
                fade *= _smooth(lam * length / op.ease)
            big_r += fade * (far - big_r)
            ramp = 1.0 - fade * (1.0 - _smooth(lam))
    k_up, k_down = op.blend
    if op.inner_blend is not None:
        kd, x0, x1 = op.inner_blend
        f = _smooth((abs(p[0]) - x0) / (x1 - x0))
        if f < 1.0:         # past x none, the op's own blend to the bit
            k_down = kd + (k_down - kd) * f
    k = k_down + (k_up - k_down) * (1.0 + ut) / 2.0
    if op.gate is None:
        w = 1.0
    else:
        g0, g1 = op.gate
        w = _smooth((un - g0) / (g1 - g0))
    if op.midline is not None:
        z0, z1, width = op.midline[:3]
        fade = (1.0 - _smooth((p[2] - z0) / (z1 - z0))) * (1.0 - _smooth(abs(p[0]) / width))
        if len(op.midline) > 3:      # behind only
            span = op.midline[4] if len(op.midline) > 4 else MIDLINE_SPAN
            fade *= 1.0 - _smooth((p[1] - op.midline[3] + span) / (2.0 * span))
        w *= 1.0 - fade
    if op.behind is not None:
        y_full, y_none, share, line = op.behind
        y = p[1] - _line_at(line, p[2])
        w *= share * (1.0 - _smooth((y - y_full) / (y_none - y_full)))
    if op.window is not None:
        z0, z1, z2, z3 = op.window
        w *= _smooth((p[2] - z0) / (z1 - z0)) * (1.0 - _smooth((p[2] - z2) / (z3 - z2)))
    return u, r, big_r, k, w, ramp


def _line_at(line: tuple[tuple[float, float], ...], z: float) -> float:
    """The y of ``line`` ((z, y) points, z rising) at ``z``: straight
    between its points, level past its ends; 0 for no points."""
    if not line:
        return 0.0
    if z <= line[0][0]:
        return line[0][1]
    for (z0, y0), (z1, y1) in zip(line, line[1:]):
        if z <= z1:
            return y0 + (y1 - y0) * (z - z0) / (z1 - z0)
    return line[-1][1]


def _smooth_max(a: float, b: float, k: float) -> float:
    """``max(a, b) + h^2 k / 4``, ``h = (k - |a - b|) / k`` (C1; plain max for ``k`` 0)."""
    m = a if a > b else b
    if k > 0.0:
        h = (k - abs(a - b)) / k
        if h > 0.0:
            m += h * h * k / 4.0
    return m


def _pair_ray(p: Vec, sides: list[_Placed]):
    """A ``pair``'s ray through ``p`` from its one origin: (u, r, R, k, w,
    (R of each side)), ``R`` the sides' smooth maximum over ``bridge``, the
    blend and the gate their means; ``None`` at the origin."""
    o = sides[0].origin
    one, two = _ray(p, sides[0], o), _ray(p, sides[1], o)
    if one is None or two is None:
        return None
    big_r = _smooth_max(one[2], two[2], sides[0].op.bridge)
    return one[0], one[1], big_r, (one[3] + two[3]) / 2.0, (one[4] + two[4]) / 2.0, (one[2], two[2], one[5], two[5])


def _lift(u: Vec, r: float, big_r: float, k: float, w: float) -> Vec | None:
    """The move along ``u`` from ``r`` to the smooth maximum of ``r`` and
    ``R`` over the blend ``k``, times the gate ``w``; ``None`` where it
    doesn't move."""
    if not (w > 0.0 and r < big_r + k):
        return None
    gap = r - big_r
    h = (k - abs(gap)) / k
    f = (r if gap > 0.0 else big_r) + (h * h * k / 4.0 if h > 0.0 else 0.0)
    step = w * (f - r)
    return (step * u[0], step * u[1], step * u[2])


def _round_move(p: Vec, side: _Placed) -> Vec | None:
    """``side``'s displacement of ``p``: along its ray to the smooth
    maximum of ``r`` and ``R`` (``max + h^2 k / 4``, ``h = (k - |r - R|)
    / k``: C1, the crease at the rim filled over ``k``), times the gate;
    ``None`` where it doesn't move ``p``."""
    got = _ray(p, side)
    if got is None:
        return None
    u, r, big_r, k, w, _ = got
    return _lift(u, r, big_r, k, w)


MIDLINE_SPAN = 0.01
"""How far each way of a ``midline``'s ``behind`` its fade eases out."""
PAIR_SPLIT = 0.01
"""The least width over which a ``pair``'s point shifts from one side's
share to the other's (its ``bridge`` where wider)."""


def _round_share(p: Vec, side: _Placed) -> float:
    """How much of ``side``'s form ``p`` lies in (a jiggle bone's
    share): 1 well inside the ellipsoid, a smoothstep over the blend to 0
    outside it, times the gate; on a drape, falling from the ellipsoid to
    0 at the anchor line.  A ``pair``'s side shares its union's by how much
    nearer its own form is (its mirror's read at ``p`` mirrored), half
    each on x = 0."""
    if side.op.pair:
        mine = _ray(p, side, side.origin)
        other = _ray((-p[0], p[1], p[2]), side, side.origin)
        if mine is None or other is None:
            return 0.5
        _, r, own, k, w, ramp = mine
        big_r = _smooth_max(own, other[2], side.op.bridge)
        split = _smooth(0.5 + (own - other[2]) / (2.0 * max(side.op.bridge, PAIR_SPLIT)))
        return w * ramp * split * _smooth((big_r + k - r) / (2.0 * k))
    got = _ray(p, side)
    if got is None:
        return 1.0
    _, r, big_r, k, w, ramp = got
    return w * ramp * _smooth((big_r + k - r) / (2.0 * k))


def _form_distance(p: Vec, side: _Placed) -> float:
    """``p``'s distance from ``side``'s ellipsoid, outside positive (the
    first-order estimate |q| (|q| - 1) / |grad|, exact on a sphere)."""
    op, c = side.op, side.centre
    n, sa, ta = side.frame
    d = (p[0] - c[0], p[1] - c[1], p[2] - c[2])
    qs, qn, qt = _dot(d, sa), _dot(d, n), _dot(d, ta)
    _, along, up, down = op.radius
    if op.back > 0.0 and qn < 0.0:
        along = op.back
    vert = up if qt >= 0.0 else down
    across = _across(op, qs * side.inward_sign > 0.0, qn, qt)
    k0 = math.sqrt(fdlibm.sq(qs / across) + fdlibm.sq(qn / along) + fdlibm.sq(qt / vert))
    k1 = math.sqrt(fdlibm.sq(qs / (across * across)) + fdlibm.sq(qn / (along * along)) + fdlibm.sq(qt / (vert * vert)))
    return k0 * (k0 - 1.0) / k1 if k1 > 0.0 else -min(op.radius)


BRIDGE_SKIN = 0.01
"""How deep inside a bridged pair's plain union (model units) the bridge
moves a point fully, fading out to none at twice it: it moves the
surface (a pair's averaged moves leave the valley's points a few
millimetres in), not what its crossing rays left deep under it."""


def _union(q: Vec, sides: list[_Placed]) -> tuple[float, float, float]:
    """The smooth union of a mirrored pair's ellipsoids at ``q`` (a
    distance, inside negative): ``min(a, b) - h^2 k / 4``, ``h = (k -
    |a - b|) / k``, ``k`` the op's ``bridge``; ``h``; and the plain
    union's ``min(a, b)``."""
    k = sides[0].op.bridge
    a, b = _form_distance(q, sides[0]), _form_distance(q, sides[1])
    h = (k - abs(a - b)) / k
    return min(a, b) - (h * h * k / 4.0 if h > 0.0 else 0.0), h, min(a, b)


def _bridge(p: Vec, sides: list[_Placed]) -> Vec:
    """``p`` (moved by the pair) moved onto the pair's smooth union where
    both ellipsoids are within the ``bridge`` of it and it lies inside the
    union but near the plain union's surface (:data:`BRIDGE_SKIN`):
    three Newton steps along the union's
    gradient, times the
    smoothstep of the gradient's forward share (the pair's mean
    direction) over 0.5, so the cleavage's front fills to a U and the
    chest behind stays."""
    value, h, plain = _union(p, sides)
    if not (h > 0.0 and value < 0.0):
        return p
    fade = 1.0 - _smooth(-plain / BRIDGE_SKIN - 1.0)
    if not fade > 0.0:
        return p
    fwd = _unit(tuple(sides[0].frame[0][i] + sides[1].frame[0][i] for i in range(3))) or (0.0, 1.0, 0.0)
    q, weight, eps = p, None, 1e-5
    for _ in range(3):
        value = _union(q, sides)[0]
        g = tuple((_union(tuple(q[j] + (eps if j == i else 0.0) for j in range(3)), sides)[0]
                   - _union(tuple(q[j] - (eps if j == i else 0.0) for j in range(3)), sides)[0]) / (2.0 * eps)
                  for i in range(3))
        gg = _dot(g, g)
        if not gg > 0.0:
            return p
        if weight is None:
            weight = fade * _smooth(_dot(g, fwd) / math.sqrt(gg) / 0.5)
            if not weight > 0.0:
                return p
        q = tuple(q[i] - value * g[i] / gg for i in range(3))
    return tuple(p[i] + weight * (q[i] - p[i]) for i in range(3))


def _round_all(p: Vec, rounds: list[list[_Placed]], heaviest: int, group: int, bridge: bool = True) -> Vec:
    """``p`` (a vertex of ``group`` whose heaviest bone is ``heaviest``)
    moved by each ``round`` op in turn; a mirrored op's two sides together,
    by their moves' mean weighted by each one's squared length (smooth,
    and a point on x = 0 stays there), then its ``bridge``
    (:func:`_bridge`; ``bridge`` false leaves it out: the subdivision
    splits by the map without it, a fill of a few millimetres the split
    triangles take as they are)."""
    for sides in rounds:
        p = _round_one(p, [side for side in sides if side.selects(heaviest, group)], bridge)
    return p


def _round_one(p: Vec, mine: list[_Placed], bridge: bool) -> Vec:
    """:func:`_round_all`'s round of ``p`` by the sides ``mine`` it selects."""
    if len(mine) == 2 and mine[0].op.pair:      # one ray from the pair's origin: no averaged moves
        got = _pair_ray(p, mine)
        d = None if got is None else _lift(*got[:5])
        return p if d is None else (p[0] + d[0], p[1] + d[1], p[2] + d[2])
    moves = []
    for side in mine:
        d = _round_move(p, side)
        if d is not None:
            moves.append(d)
    if moves:
        if len(moves) == 1:
            d = moves[0]
        else:
            weights = [_dot(m, m) for m in moves]
            total = sum(weights)
            d = tuple(sum(w * m[c] for w, m in zip(weights, moves)) / total for c in range(3)) \
                if total > 0.0 else (0.0, 0.0, 0.0)
        p = (p[0] + d[0], p[1] + d[1], p[2] + d[2])
    if bridge and len(mine) == 2 and mine[0].op.bridge > 0.0:
        p = _bridge(p, mine)
    return p


def _round_all_each(ps: list[Vec], rounds: list[list[_Placed]], heaviest: list[int], groups: list[int],
                    bridge: bool = True) -> list[Vec]:
    """:func:`_round_all` of each of ``ps`` (its heaviest bone and group
    in ``heaviest`` and ``groups``), a round at a time over all of them,
    so each side's rays are asked at once (:func:`_rays_ahead`): each
    point the same as alone."""
    ps = list(ps)
    for sides in rounds:
        mine = [[side for side in sides if side.selects(h, g)] for h, g in zip(heaviest, groups)]
        asked: dict[tuple[int, int], tuple] = {}
        for p, m in zip(ps, mine):
            origin = m[0].origin if len(m) == 2 and m[0].op.pair else None
            for side in m:
                asked.setdefault((id(side), id(origin)), (side, origin, []))[2].append(p)
        for side, origin, points in asked.values():
            _rays_ahead(points, side, origin)
        ps = [_round_one(p, m, bridge) for p, m in zip(ps, mine)]
    return ps


# --------------------------------------------------------------------------- normals
def _normals(mesh: _Mesh, after: list[Vec], moved: set[int]) -> dict[int, Vec]:
    """The fan rule (module docstring) on every vertex whose welded fan
    holds a vertex of ``moved``; ``after`` every vertex's final position."""
    unit = [tuple(c / n for c in v) if (n := _norm(v)) > 0 else None for v in mesh.normals]
    at: dict[bytes, list[int]] = {}
    for k, key in enumerate(mesh.keys):
        at.setdefault(key, []).append(k)
    tri_of: dict[int, list[int]] = {}
    for t, tri in enumerate(mesh.triangles):
        for v in tri:
            tri_of.setdefault(v, []).append(t)
    out = {}
    for k in range(len(mesh.positions)):
        if unit[k] is None:
            continue
        mates = [j for j in at[mesh.keys[k]] if unit[j] is not None and _dot(unit[k], unit[j]) > WELD]
        fan = sorted({t for j in mates for t in tri_of.get(j, ())})
        if not any(v in moved for t in fan for v in mesh.triangles[t]):
            continue
        g_old, g_new = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        for t in fan:
            f0, f1 = _face(mesh.positions, mesh.triangles[t]), _face(after, mesh.triangles[t])
            for i in range(3):
                g_old[i] += f0[i]
                g_new[i] += f1[i]
        a, b = _norm(g_old), _norm(g_new)
        if not (a > 0 and b > 0):
            continue
        a, b = tuple(x / a for x in g_old), tuple(x / b for x in g_new)
        n = unit[k]
        c = _dot(a, b)
        if c < -0.999999:
            turned = (-n[0], -n[1], -n[2])
        else:   # R n = n + v x n + v x (v x n) / (1 + c), v = a x b (Rodrigues)
            v = _cross(a, b)
            vn = _cross(v, n)
            vvn = _cross(v, vn)
            turned = tuple(n[i] + vn[i] + vvn[i] / (1.0 + c) for i in range(3))
        length = _norm(turned)
        out[k] = _f32(tuple(x / length for x in turned))
    return out


# --------------------------------------------------------------------------- the glTF
_GLB, _JSON, _BIN = b"glTF", 0x4E4F534A, 0x004E4942
_FORMATS = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
_SIZES = {"b": 1, "B": 1, "h": 2, "H": 2, "I": 4, "f": 4}
_SCALE = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}
_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _buffer(uri, folder: Path) -> bytes:
    if not isinstance(uri, str):
        raise ValueError(f"a buffer's uri {uri!r} isn't text")
    if uri.startswith("data:"):
        head, sep, body = uri.partition(",")
        if not sep or not head.endswith(";base64"):
            raise ValueError("a data: buffer that isn't base64")
        return base64.b64decode(body, validate=True)
    rel = urllib.parse.unquote(uri)
    if urllib.parse.urlparse(uri).scheme or rel.startswith(("/", "\\")) or "\\" in rel or ".." in rel.split("/"):
        raise ValueError(f"buffer {uri!r} isn't a file beside the glTF")
    path = (folder / rel).resolve()
    if folder.resolve() not in path.parents:
        raise ValueError(f"buffer {uri!r} isn't a file beside the glTF")
    return path.read_bytes()


def _load(path: Path) -> tuple[dict, list[bytes], str]:
    """The document, its buffers and the file's sha256 (``.glb``: its
    bytes; ``.gltf``: its bytes, then each external buffer's in order)."""
    data = path.read_bytes()
    sha = hashlib.sha256(data)
    chunk = None
    if data[:4] == _GLB:
        version, length = struct.unpack_from("<II", data, 4)
        if version != 2 or length != len(data):
            raise ValueError("a .glb that isn't glTF 2's (its version or length)")
        size, kind = struct.unpack_from("<II", data, 12)
        if kind != _JSON:
            raise ValueError("a .glb whose first chunk isn't JSON")
        doc = json.loads(data[20:20 + size].decode("utf-8"))
        at = 20 + size
        if at + 8 <= len(data):
            size2, kind2 = struct.unpack_from("<II", data, at)
            if kind2 == _BIN:
                chunk = data[at + 8:at + 8 + size2]
    else:
        doc = json.loads(data.decode("utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("its JSON isn't a glTF document")
    if doc.get("asset", {}).get("version") != "2.0":
        raise ValueError("not glTF 2.0")
    if doc.get("extensionsRequired"):
        raise ValueError(f"it needs extensions {', '.join(map(str, doc['extensionsRequired']))} (export without "
                         "compression)")
    buffers = []
    for b in doc.get("buffers", []):
        if "uri" in b:
            blob = _buffer(b["uri"], path.parent)
            if not b["uri"].startswith("data:"):
                sha.update(blob)
        elif chunk is not None and not buffers:
            blob = chunk
        else:
            raise ValueError("a buffer with no data")
        if len(blob) < b["byteLength"]:
            raise ValueError("a buffer shorter than its byteLength")
        buffers.append(blob)
    return doc, buffers, sha.hexdigest()


def _values(doc: dict, buffers: list[bytes], i: int) -> list[tuple]:
    """Accessor ``i``'s rows (normalized integers as glTF scales them)."""
    acc = doc["accessors"][i]
    if "sparse" in acc or "bufferView" not in acc:
        raise ValueError(f"accessor {i} is sparse or has no data")
    view = doc["bufferViews"][acc["bufferView"]]
    fmt, width, count = _FORMATS[acc["componentType"]], _WIDTHS[acc["type"]], acc["count"]
    elem = _SIZES[fmt] * width
    stride = view.get("byteStride") or elem
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    buf = buffers[view["buffer"]]
    if count < 0 or stride < elem or (count and acc.get("byteOffset", 0) + stride * (count - 1) + elem
                                      > view["byteLength"]) or view.get("byteOffset", 0) + view["byteLength"] > len(buf):
        raise ValueError(f"accessor {i} lies outside its view")
    if stride == elem:
        flat = struct.unpack_from(f"<{count * width}{fmt}", buf, start)
        rows = [flat[r * width:(r + 1) * width] for r in range(count)]
    else:
        rows = [struct.unpack_from(f"<{width}{fmt}", buf, start + stride * r) for r in range(count)]
    if fmt == "f":
        if not all(math.isfinite(x) for row in rows for x in row):
            raise ValueError(f"accessor {i} holds a float that isn't finite")
    elif acc.get("normalized"):
        scale = _SCALE[acc["componentType"]]
        rows = [tuple(max(x / scale, -1.0) for x in row) for row in rows]
    return rows


def _carried(rows: list[tuple], mesh: _Mesh) -> bool:
    """Whether ``rows`` are each an exact (group, index) of ``mesh``."""
    counts = {g.index: g.count for g in mesh.groups}
    for g, i in rows:
        rg, ri = round(g), round(i)
        if abs(g - rg) >= 1e-3 or abs(i - ri) >= 1e-3 or not 0 <= ri < counts.get(rg, 0):
            return False
    return True


def _matrix(flat) -> list[list[float]]:
    """A glTF (column-major) 4x4 as rows."""
    return [[float(flat[c * 4 + r]) for c in range(4)] for r in range(4)]


def _inverse(m: list[list[float]]) -> list[list[float]]:
    """An affine 4x4's inverse."""
    a = [row[:3] for row in m[:3]]
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    if det == 0:
        raise ValueError("a bind matrix with no inverse")
    inv = [[(a[(c + 1) % 3][(r + 1) % 3] * a[(c + 2) % 3][(r + 2) % 3]
             - a[(c + 1) % 3][(r + 2) % 3] * a[(c + 2) % 3][(r + 1) % 3]) / det for c in range(3)] for r in range(3)]
    t = [m[r][3] for r in range(3)]
    return [[*inv[r], -sum(inv[r][c] * t[c] for c in range(3))] for r in range(3)] + [[0.0, 0.0, 0.0, 1.0]]


def _mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def _read_edit(path: Path, mesh: _Mesh) -> GltfEdit:
    """The vertices the glTF ``path`` moves on ``mesh`` (the module
    docstring's rules); :class:`ValueError` names the first rule broken."""
    name = path.name
    try:
        return _edit(path, mesh)
    except ValueError as exc:
        raise ValueError(f"{name}: {exc}") from None
    except (KeyError, IndexError, TypeError, AttributeError, struct.error, UnicodeDecodeError, OSError) as exc:
        raise ValueError(f"{name}: not a glTF this import reads ({type(exc).__name__}: {exc})") from None


def skin_frame(doc: dict, buffers: list[bytes], skin: dict, names, binds, body: str, *, new_bones: bool = False
               ) -> tuple[list[int | None], list[tuple[int, float]]]:
    """A glTF skin's joints as the body's bones (a ``__scale`` helper its
    bone's; with ``new_bones``, ``None`` for a joint the body lacks) and
    the mesh frame's axes: each known joint's inverse bind against the
    body's gives the mesh-to-model transform, which must be one for every
    joint (else the bones moved) and the model's frame or an axis swap of
    it (Blender writes glTF's y up), its origin the model's; each axis is
    (the model axis it is, its sign).  :class:`ValueError` names the rule
    broken."""
    bones: list[int | None] = []
    for j in skin["joints"]:
        joint = str(doc["nodes"][j].get("name", ""))
        bone = joint.removesuffix(HELPER)
        if bone not in names:
            if new_bones:
                bones.append(None)
                continue
            raise ValueError(f"the skin's joint {joint!r} is no bone of {body}: the same skeleton only")
        bones.append(names.index(bone))
    ibm = (_values(doc, buffers, skin["inverseBindMatrices"]) if "inverseBindMatrices" in skin
           else [(1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0)] * len(bones))
    if not bones or len(ibm) != len(bones):
        raise ValueError(f"the skin lists {len(bones)} joints and {len(ibm)} inverse binds: export the mesh with "
                         "its armature")
    known = [(b, m) for b, m in zip(bones, ibm) if b is not None]
    if not known:
        raise ValueError(f"no joint of the skin is a bone of {body}")
    frames = [_mul(_inverse(_matrix(binds[b])), _matrix(m)) for b, m in known]
    mean = [[sum(x[r][c] for x in frames) / len(frames) for c in range(4)] for r in range(3)]
    off = [max(abs(x[r][c] - mean[r][c]) for r in range(3) for c in range(4)) for x in frames]
    worst = max(range(len(off)), key=off.__getitem__)
    if off[worst] > FRAME:
        raise ValueError(f"the skeleton's bind pose changed: {names[known[worst][0]]} by {off[worst]:.2g}: "
                         "move vertices, not bones")
    snap = [[float(round(mean[r][c])) for c in range(3)] for r in range(3)]
    permutation = (all(abs(x) in (0.0, 1.0) for row in snap for x in row)
                   and all(sum(abs(x) for x in row) == 1 for row in snap)
                   and all(sum(abs(snap[r][c]) for r in range(3)) == 1 for c in range(3)))
    gap = max(abs(mean[r][c] - snap[r][c]) for r in range(3) for c in range(3))
    if not permutation or gap > FRAME or max(abs(mean[r][3]) for r in range(3)) > SHIFT:
        raise ValueError(f"the mesh frame isn't {body}'s or an axis swap of it: apply no object transform")
    return bones, [next((c, snap[r][c]) for c in range(3) if snap[r][c]) for r in range(3)]


def _edit(path: Path, mesh: _Mesh) -> GltfEdit:
    doc, buffers, sha = _load(path)
    meshes = doc.get("meshes", [])
    found, ignored = [], []
    for mi, m in enumerate(meshes):
        prims = m.get("primitives", [])
        carrier = next((c for c in CARRIERS if prims and all(c in p["attributes"] for p in prims)
                        and (c == "_AZ_VID" or all(_carried(_values(doc, buffers, p["attributes"][c]), mesh)
                                                   for p in prims))), None)
        if carrier:
            found.append((mi, carrier))
        else:
            ignored.append(str(m.get("name", f"mesh {mi}")))
    if not found:
        raise ValueError("no mesh carries a vertex id: edit the file `azurik-mod model export` wrote and keep its "
                         "UVMap.001 (or tick Include > Attributes in Blender's glTF export)")
    if len(found) > 1:
        raise ValueError(f"meshes {', '.join(repr(meshes[mi].get('name', mi)) for mi, _ in found)} all carry vertex "
                         "ids: keep one")
    mi, carrier = found[0]
    nodes = [n for n in doc.get("nodes", []) if n.get("mesh") == mi and "skin" in n]
    if len(nodes) != 1:
        raise ValueError(f"mesh {meshes[mi].get('name', mi)!r} needs one skinned node: export it with its armature")
    skin = doc["skins"][nodes[0]["skin"]]

    bones, axes = skin_frame(doc, buffers, skin, mesh.names, mesh.binds, mesh.body)

    # the vertices, by id
    index = {vid: k for k, vid in enumerate(mesh.ids)}
    seen: dict[int, list[Vec]] = {}
    foreign = total = 0
    uv_changed: set[int] = set()
    skin_changed: set[int] = set()
    tris: Counter = Counter()
    for p in meshes[mi]["primitives"]:
        if p.get("mode", 4) != 4:
            raise ValueError(f"a primitive of mode {p.get('mode')} (triangles only)")
        a = p["attributes"]
        pos = _values(doc, buffers, a["POSITION"])
        ids = _values(doc, buffers, a[carrier])
        if "TEXCOORD_0" not in a:
            raise ValueError("a primitive has no TEXCOORD_0 (its UVs): export them")
        uvs = _values(doc, buffers, a["TEXCOORD_0"])
        sets = []
        n = 0
        while f"JOINTS_{n}" in a and f"WEIGHTS_{n}" in a:
            sets.append((_values(doc, buffers, a[f"JOINTS_{n}"]), _values(doc, buffers, a[f"WEIGHTS_{n}"])))
            n += 1
        if len(ids) != len(pos) or len(uvs) != len(pos) or \
                any(len(js) != len(pos) or len(ws) != len(pos) for js, ws in sets):
            raise ValueError("a primitive's attribute counts differ")
        total += len(pos)
        rows: list[int | None] = []
        for r, (g, i) in enumerate(ids):
            k = index.get((round(g), round(i))) if abs(g - round(g)) < 1e-3 and abs(i - round(i)) < 1e-3 else None
            rows.append(k)
            if k is None:
                foreign += 1
                continue
            seen.setdefault(k, []).append(tuple(s * pos[r][c] for c, s in axes))
            if max(abs(uvs[r][0] - mesh.uvs[k][0]), abs(uvs[r][1] - mesh.uvs[k][1])) > UV_CHANGE:
                uv_changed.add(k)
            weights: dict[int, float] = {}
            for js, ws in sets:
                for j, w in zip(js[r], ws[r]):
                    if w > 0:
                        b = bones[int(j)]
                        weights[b] = weights.get(b, 0.0) + w
            if max((abs(weights.get(b, 0.0) - mesh.skins[k].get(b, 0.0)) for b in {*weights, *mesh.skins[k]}),
                   default=0.0) > SKIN_CHANGE:
                skin_changed.add(k)
        flat = [x for (x,) in _values(doc, buffers, p["indices"])] if "indices" in p else list(range(len(pos)))
        if len(flat) % 3:
            raise ValueError("a primitive's indices aren't whole triangles")
        for t in range(0, len(flat), 3):
            tri = tuple(rows[int(x)] for x in flat[t:t + 3])
            if None not in tri:
                tris[_canonical(tri)] += 1
    if foreign:
        raise ValueError(f"{foreign} vertices with no id of {mesh.body}'s: the same topology only")
    drawn = {v for t in mesh.triangles for v in t}
    missing = len(drawn - set(seen))
    if missing:
        raise ValueError(f"{missing} of {mesh.body}'s vertices missing (Merge by Distance joins seam copies: undo it)")
    for k, copies in seen.items():
        spread = max(max(abs(c[i] - copies[0][i]) for i in range(3)) for c in copies)
        if spread > COPIES:
            g, i = mesh.ids[k]
            raise ValueError(f"vertex ({g}, {i})'s copies lie {spread * 1000:.3g} mm apart: a seam was torn")
    want = Counter(_canonical(t) for t in mesh.triangles)
    if tris != want:
        raise ValueError(f"the triangles changed: {sum((want - tris).values())} missing, "
                         f"{sum((tris - want).values())} new: the same topology only")
    if uv_changed:
        raise ValueError(f"UVs changed at {len(uv_changed)} vertices: this import writes positions only")
    if skin_changed:
        raise ValueError(f"the skin changed at {len(skin_changed)} vertices: this import writes positions; "
                         "weights wait for V6")
    moved = {k: copies[0] for k, copies in sorted(seen.items())
             if _norm(_sub(copies[0], mesh.positions[k])) > MOVED}
    return GltfEdit(sha, carrier, total, sum(len(c) - 1 for c in seen.values()), tuple(ignored),
                    axes != [(0, 1.0), (1, 1.0), (2, 1.0)], moved)


def _canonical(t: tuple[int, int, int]) -> tuple[int, int, int]:
    """A triangle rotated to start at its least vertex (its winding kept)."""
    i = t.index(min(t))
    return t[i:] + t[:i]


def file_sha256(path: Path) -> str:
    """The sha256 a recipe's ``mesh.gltf`` pins (:func:`_load`'s)."""
    try:
        return _load(Path(path))[2]
    except (ValueError, KeyError, TypeError, struct.error, UnicodeDecodeError) as exc:
        raise ValueError(f"{Path(path).name}: not a glTF this import reads ({exc})") from None


# --------------------------------------------------------------------------- the subdivision
@dataclass(frozen=True)
class _Region:
    """A ``subdivide`` op after mirrors: its label, centre, half axes,
    longest edge, smoothness, groups and the bones it splits (``None``:
    every bone ``keep`` doesn't hold)."""

    label: str
    centre: Vec
    radius: Vec
    edge: float
    smooth: bool
    groups: tuple[int, ...]
    bones: frozenset[int] | None
    kept: frozenset[int]
    shrink: float = 0.0
    hem: HemOp | None = None
    to: tuple[int, ...] = ()
    bind: BindOp | None = None
    apart: tuple[tuple[int, ...], float] | None = None
    normals: str = "area"

    def holds(self, p: Vec) -> bool:
        c, r = self.centre, self.radius
        return fdlibm.sq((p[0] - c[0]) / r[0]) + fdlibm.sq((p[1] - c[1]) / r[1]) + fdlibm.sq((p[2] - c[2]) / r[2]) < 1.0

    def selects(self, heaviest: int, group: int) -> bool:
        return ((heaviest in self.bones) if self.bones is not None else heaviest not in self.kept) and \
            (not self.groups or group in self.groups)


def _regions(mesh: _Mesh, spec: MeshSpec, kind=None) -> list[_Region]:
    """The ``subdivide`` ops (or the ``kind`` ops: ``unwrap``) after
    mirrors (W-3: their bones and groups the body's, a positive edge and
    radius)."""
    kind = kind or SubdivideOp
    have = set(mesh.names)
    kept = frozenset(_subtree(mesh, set(spec.keep)))
    indices = {g.index for g in mesh.groups}
    out = []
    for i, op in enumerate(spec.ops):
        if not isinstance(op, kind):
            continue
        if op.bone not in have:
            raise ValueError(f"mesh.ops[{i}].bone: {mesh.body} has no bone {op.bone!r}")
        for g in op.groups:
            if g not in indices:
                raise ValueError(f"mesh.ops[{i}].groups: {mesh.body} has no LOD-0 group {g} "
                                 f"(it has {', '.join(map(str, sorted(indices)))})")
        if not (getattr(op, "edge", 1.0) > 0 and all(r > 0 for r in op.radius)):
            raise ValueError(f"mesh.ops[{i}]: its edge and radius must be above 0")
        origin = mesh.origins[mesh.names.index(op.bone)]
        centre = (origin[0] + op.offset[0], origin[1] + op.offset[1], origin[2] + op.offset[2])
        apart = getattr(op, "apart", None)
        for g in apart[0] if apart is not None else ():
            if g not in indices:
                raise ValueError(f"mesh.ops[{i}].apart.edges: {mesh.body} has no LOD-0 group {g} "
                                 f"(it has {', '.join(map(str, sorted(indices)))})")
        sides = [(f"ops[{i}]", centre, op.only)]
        if op.mirror:
            if abs(centre[0]) <= COPIES:
                raise ValueError(f"mesh.ops[{i}].mirror: its centre is on x = 0, so it is its own mirror: drop mirror")
            sides.append((f"ops[{i}] mirrored", (-centre[0], centre[1], centre[2]), tuple(map(_mirrored, op.only))))
        for label, c, only in sides:
            for name in only:
                if name not in have:
                    raise ValueError(f"mesh.{label}.only: {mesh.body} has no bone {name!r}")
            out.append(_Region(label, c, op.radius, getattr(op, "edge", 0.0), getattr(op, "smooth", False), op.groups,
                               frozenset(_subtree(mesh, set(only))) if only else None, kept,
                               getattr(op, "shrink", 0.0), op if isinstance(op, HemOp) else None,
                               getattr(op, "to", ()), op if isinstance(op, BindOp) else None, apart,
                               getattr(op, "normals", "area")))
    return out


def _angled(mesh: _Mesh, spec: MeshSpec, base: list[Vec], which: set[int]) -> dict[int, str]:
    """The vertices of ``which`` a subdivide region with ``normals``
    ``"angle"`` (Step 2.177c) or ``"nearer"`` (Step 2.188) holds at
    ``base`` and selects, each with the first such region's rule."""
    regions = [r for r in _regions(mesh, spec) if r.normals != "area"]
    out = {}
    for k in which:
        rule = next((r.normals for r in regions if r.holds(base[k]) and r.selects(mesh.heaviest[k], mesh.ids[k][0])),
                    None)
        if rule is not None:
            out[k] = rule
    return out


def _unit(v) -> Vec | None:
    n = _norm(v)
    return (v[0] / n, v[1] / n, v[2] / n) if n > 0 else None


def _subdivide(mesh: _Mesh, spec: MeshSpec, base: list[Vec]) -> tuple[_Mesh, list[Vec], set[int]]:
    """``mesh`` with every ``subdivide`` region split (module docstring)
    and every ``hem`` op's open edges: the new mesh, its base positions
    and the vertices whose normals turn smooth.  ``mesh`` itself when no
    op subdivides."""
    hems = _regions(mesh, spec, HemOp)
    regions = _regions(mesh, spec) + hems
    if not regions:
        return mesh, base, set()
    placed = _place(mesh, spec)
    rounds = _rounds(mesh, spec)
    ids, keys, pos, nrm, uvs = list(mesh.ids), list(mesh.keys), list(mesh.positions), list(mesh.normals), list(mesh.uvs)
    skins, heavy, basep = list(mesh.skins), list(mesh.heaviest), list(base)
    counts = {g.index: g.count for g in mesh.groups}
    group_of = [g for g, _ in ids]
    # welded points: the lowest vertex at each stored position carries the point's base position
    wid_of: list[int] = []
    wkey: dict[bytes, int] = {}
    wpos: list[Vec] = []
    for k, key in enumerate(keys):
        if key not in wkey:
            wkey[key] = len(wpos)
            wpos.append(_f32(basep[k]))
        wid_of.append(wkey[key])
    tris = [tuple(t) for t in mesh.triangles]
    # the points' normals: their faces' at the base, each turned to the first copy's stored normal (a twin's too)
    acc = [[0.0, 0.0, 0.0] for _ in wpos]
    ref: list[Vec | None] = [None] * len(wpos)
    for k in range(len(keys)):
        if ref[wid_of[k]] is None:
            ref[wid_of[k]] = _unit(nrm[k])
    for t in tris:
        f = _face(wpos, tuple(wid_of[v] for v in t))
        for v in t:
            w = wid_of[v]
            r = ref[w] or _unit(f)
            if r is None:
                continue
            sign = 1.0 if _dot(f, r) >= 0.0 else -1.0
            for c in range(3):
                acc[w][c] += sign * f[c]
    wnrm = [_unit(a) or (ref[w] or (0.0, 0.0, 1.0)) for w, a in enumerate(acc)]

    def final(k: int) -> Vec:
        p = basep[k]
        ops = [op for op in placed if op.selects(heavy[k], group_of[k])]
        q = _displace(p, ops)[0] if ops else p
        return _round_all(q, rounds, heavy[k], group_of[k], False) if rounds else q

    finals: dict[int, Vec] = {}

    def fin(k: int) -> Vec:
        if k not in finals:
            finals[k] = final(k)
        return finals[k]

    edge_tris: dict[tuple[int, int], set[int]] = {}

    flats: dict[tuple[int, int, int], bool] = {}    # kept (Step 2.179): the points stay where they are while it splits

    def flat(a: int, b: int, c: int) -> bool:
        """Whether a welded triangle has no area to split (two corners at one
        point, or all three on a line: a crack vanilla fills with a sliver)."""
        got = flats.get((a, b, c))
        if got is None:
            if a == b or b == c or a == c:
                got = True
            else:
                f = _face(wpos, (a, b, c))
                longest = max(_norm(_sub(wpos[a], wpos[b])), _norm(_sub(wpos[b], wpos[c])),
                              _norm(_sub(wpos[c], wpos[a])))
                got = not _norm(f) > SLIVER * longest * longest
            flats[a, b, c] = got
        return got

    def link(t: int) -> None:      # a triangle with no area is never split
        a, b, c = (wid_of[v] for v in tris[t])
        if flat(a, b, c):
            return
        for x, y in ((a, b), (b, c), (c, a)):
            edge_tris.setdefault((min(x, y), max(x, y)), set()).add(t)

    def unlink(t: int) -> None:
        a, b, c = (wid_of[v] for v in tris[t])
        if flat(a, b, c):
            return
        for x, y in ((a, b), (b, c), (c, a)):
            e = (min(x, y), max(x, y))
            edge_tris[e].discard(t)
            if not edge_tris[e]:
                del edge_tris[e]

    for t in range(len(tris)):
        link(t)

    edged: dict[tuple[tuple[int, ...], float], dict] = {}   # apart's open edges: their final points in cells of band

    def near_edge(apart: tuple[tuple[int, ...], float], p: Vec) -> bool:
        """Whether ``p`` lies within ``apart``'s band of an open edge of its
        groups in the final shape (the edges as the mesh had them first,
        each sampled every half band)."""
        groups, band = apart
        if apart not in edged:
            cells: dict[tuple[int, int, int], list[Vec]] = {}
            for (x, y), ts in edge_tris.items():
                if len({frozenset(wid_of[v] for v in tris[t]) for t in ts}) != 1 or \
                        not all(group_of[tris[t][0]] in groups for t in ts):
                    continue
                a, b = fin(rep[x]), fin(rep[y])
                n = max(1, math.ceil(_norm(_sub(a, b)) / (band / 2.0)))
                for j in range(n + 1):
                    q = tuple(a[c] + (b[c] - a[c]) * j / n for c in range(3))
                    cells.setdefault(tuple(math.floor(q[c] / band) for c in range(3)), []).append(q)
            edged[apart] = cells
        cells = edged[apart]
        k = tuple(math.floor(p[c] / band) for c in range(3))
        return any(_norm(_sub(p, q)) < band for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)
                   for q in cells.get((k[0] + a, k[1] + b, k[2] + c), ()))

    version = [0] * len(tris)

    rep: dict[int, int] = {}
    for k in range(len(wid_of)):
        rep.setdefault(wid_of[k], k)
    taken = set(wpos)
    refused: set[tuple[int, int]] = set()    # welded edges a split tore or found an old point on (AZ-660)

    def longest(t: int) -> tuple[int, int]:
        """Triangle ``t``'s longest edge in the final shape (welded, each
        point at its first copy's final position; ties by the points, so
        twins and fins agree), a refused one only when all three are: a
        split halves the edge the ops stretch most, so a form stretched
        one way isn't split across it."""
        w = [wid_of[v] for v in tris[t]]
        f = [fin(rep[x]) for x in w]
        sides = [(_norm(_sub(f[i], f[(i + 1) % 3])), min(w[i], w[(i + 1) % 3]), max(w[i], w[(i + 1) % 3]))
                 for i in range(3)]
        _, x, y = max([side for side in sides if side[1:] not in refused] or sides)
        return x, y

    holding: dict[tuple[int, int, int], list[_Region]] = {}

    def mark(t: int) -> tuple[float, bool] | None:
        """Triangle ``t``'s longest edge in the final shape and whether a
        smooth region holds it, when a region holds its centroid, selects
        its corners and that edge passes the region's ``edge`` (while its
        longest edge now is above ``edge`` / :data:`STRETCH`); else
        ``None``."""
        tri = tris[t]
        w = [wid_of[v] for v in tri]
        if flat(*w) or any((min(w[i], w[(i + 1) % 3]), max(w[i], w[(i + 1) % 3])) in refused for i in range(3)):
            return None      # a refused edge's triangle: its neighbours' splits still reach it
        inside = holding.get(tri)
        if inside is None:      # its corners' (Step 2.179: kept, a triangle is asked again as its neighbours split)
            centre = tuple(sum(wpos[x][c] for x in w) / 3.0 for c in range(3))
            inside = [r for r in regions if r.holds(centre)
                      and all(r.selects(heavy[v], group_of[v]) for v in tri)]
            if any(r.apart is not None for r in inside):
                f = [fin(v) for v in tri]
                at = tuple(sum(q[c] for q in f) / 3.0 for c in range(3))
                inside = [r for r in inside if r.apart is None or not near_edge(r.apart, at)]
            holding[tri] = inside
        if not inside:
            return None
        length = max(_norm(_sub(fin(tri[i]), fin(tri[(i + 1) % 3]))) for i in range(3))
        x, y = longest(t)
        smooth = any(r.smooth for r in inside)
        plain = [r for r in inside if r.hem is None]
        if plain:
            edge = min(r.edge for r in plain)
            if length > edge and _norm(_sub(wpos[x], wpos[y])) > edge / STRETCH:
                return length, smooth
        edge = min((r.edge for r in inside if r.hem is not None), default=None)
        if edge is not None:       # a hem: a triangle on an open edge longer than its edge
            for i in range(3):
                e = (min(w[i], w[(i + 1) % 3]), max(w[i], w[(i + 1) % 3]))
                if _open(e) and _norm(_sub(fin(tri[i]), fin(tri[(i + 1) % 3]))) > edge \
                        and _norm(_sub(wpos[x], wpos[y])) > edge / STRETCH:
                    return length, smooth
        return None

    def _open(e: tuple[int, int]) -> bool:
        """Whether the welded edge ``e`` bounds one face (a two-sided
        layer's twin counted once)."""
        return len({frozenset(wid_of[v] for v in tris[t]) for t in edge_tris.get(e, ())}) == 1

    added = 0

    picks: dict[tuple[int, int], tuple] = {}

    def chosen(h: int, g: int) -> tuple:
        """The field ops and round sides that move a vertex of group ``g`` whose heaviest bone is ``h``."""
        got = picks.get((h, g))
        if got is None:
            got = picks[h, g] = (tuple(i for i, op in enumerate(placed) if op.selects(h, g)),
                                 tuple((i, j) for i, sides in enumerate(rounds) for j, side in enumerate(sides)
                                       if side.selects(h, g)))
        return got

    def split(e: tuple[int, int], smooth: bool) -> list[int] | None:
        """Every triangle on the welded edge ``e`` split at its midpoint
        (each copy of it its own new vertex), unless a field op tears the
        edge; the triangles it made or changed."""
        nonlocal added
        wa, wb = e
        pa, pb = wpos[wa], wpos[wb]
        mid = [(pa[c] + pb[c]) / 2.0 for c in range(3)]
        if smooth:      # PN triangles' edge midpoint: the cubic through both ends along their normals
            na, nb = wnrm[wa], wnrm[wb]
            d = _sub(pb, pa)
            wab, wba = _dot(d, na), -_dot(d, nb)
            mid = [mid[c] - (wab * na[c] + wba * nb[c]) / 8.0 for c in range(3)]
        for t in sorted(edge_tris[e]):     # a field op that stops at a bone or group boundary tears the edge
            ends = [v for v in tris[t] if wid_of[v] in e]
            skin: dict[int, float] = {}
            for v in ends:
                for bone, w in skins[v].items():
                    skin[bone] = skin.get(bone, 0.0) + w
            h = min(skin.items(), key=lambda bw: (-bw[1], bw[0]))[0]
            g = group_of[ends[0]]
            if chosen(heavy[ends[0]], g) == chosen(heavy[ends[1]], g) == chosen(h, g):
                continue       # one continuous map over the edge: a split shortens it, however far a round op bends it
            ops = [op for op in placed if op.selects(h, group_of[ends[0]])]
            fm = _displace(_f32(mid), ops)[0] if ops else _f32(mid)
            if rounds:
                fm = _round_all(fm, rounds, h, group_of[ends[0]], False)
            full = _norm(_sub(fin(ends[0]), fin(ends[1])))
            if max(_norm(_sub(fm, fin(ends[0]))), _norm(_sub(fm, fin(ends[1])))) > TORN * full:
                return None
        point = _f32(mid)
        if point in taken:      # a sliver's chain of points on a line (a crack vanilla fills): none on an old point
            return None
        wm = len(wpos)
        wpos.append(point)
        taken.add(point)
        nb_ = wnrm[wb] if _dot(wnrm[wa], wnrm[wb]) >= 0.0 else tuple(-c for c in wnrm[wb])
        wnrm.append(_unit(tuple(wnrm[wa][c] + nb_[c] for c in range(3))) or wnrm[wa])
        copies: dict[tuple[int, int], int] = {}
        touched = []
        for t in sorted(edge_tris[e]):
            a, b, c = tris[t]
            for r0, r1, r2 in ((a, b, c), (b, c, a), (c, a, b)):
                if {wid_of[r0], wid_of[r1]} == {wa, wb}:
                    break
            key = (min(r0, r1), max(r0, r1))
            m = copies.get(key)
            if m is None:
                g = group_of[r0]
                skin = {}
                for v in (r0, r1):
                    for bone, w in skins[v].items():
                        skin[bone] = skin.get(bone, 0.0) + w / 2.0
                top = sorted(skin.items(), key=lambda bw: (-bw[1], bw[0]))[:4]
                total = sum(w for _, w in top)
                n0, n1 = _unit(nrm[r0]), _unit(nrm[r1])
                if n0 is not None and n1 is not None and _dot(n0, n1) < 0.0:
                    n1 = None
                normal = _unit(tuple((n0 or (0.0, 0.0, 0.0))[i] + (n1 or (0.0, 0.0, 0.0))[i] for i in range(3)))
                m = len(ids)
                ids.append((g, counts[g]))
                counts[g] += 1
                keys.append(b"N" + struct.pack("<I", wm))
                rep.setdefault(wm, len(wid_of))
                wid_of.append(wm)
                pos.append(wpos[wm])
                basep.append(wpos[wm])
                nrm.append(normal or wnrm[wm])
                uvs.append(((uvs[r0][0] + uvs[r1][0]) / 2.0, (uvs[r0][1] + uvs[r1][1]) / 2.0))
                skins.append({bone: w / total for bone, w in top})
                heavy.append(top[0][0])
                group_of.append(g)
                copies[key] = m
                added += 1
                if added > SUBDIVIDE_MAX:
                    raise ValueError(f"mesh: the subdivide ops add more than {SUBDIVIDE_MAX} vertices: "
                                     "a longer edge, or a smaller region")
            unlink(t)
            tris[t] = (r0, m, r2)
            tris.append((m, r1, r2))
            version[t] += 1
            version.append(0)
            link(t)
            link(len(tris) - 1)
            touched += [t, len(tris) - 1]
        return touched

    heap: list[tuple[float, int, int]] = []
    for t in range(len(tris)):
        got = mark(t)
        if got is not None:
            heap.append((-got[0], t, 0))
    heapq.heapify(heap)
    while heap:
        _, t0, ver = heapq.heappop(heap)
        if ver != version[t0]:
            continue
        got = mark(t0)
        if got is None:
            continue
        # Rivara's longest-edge propagation: split an edge only where it is the longest of every triangle on it
        stack = [t0]
        while stack:
            t = stack[-1]
            e = longest(t)
            nxt = next((n for n in sorted(edge_tris.get(e, ())) if n != t and longest(n) != e), None)
            if nxt is not None and len(stack) < LEPP_MAX:
                stack.append(nxt)        # its neighbour's longest edge first
                continue
            touched = split(e, got[1])
            if touched is None:        # torn, or an old point: remembered, never split; the chain's start again
                if e not in refused:
                    refused.add(e)
                    heapq.heappush(heap, (-got[0], t0, version[t0]))
                break
            stack.pop()                # t lay on e: split
            for n in touched:
                got2 = mark(n)
                if got2 is not None:
                    heapq.heappush(heap, (-got2[0], n, version[n]))
    smooth = {k for k in range(len(ids)) if k >= len(mesh.ids) or any(
        r.smooth and r.holds(basep[k]) and r.selects(heavy[k], group_of[k]) for r in regions)}
    for r in hems:      # the hems' loops relaxed at the base, their ends where they leave the region kept
        if not r.hem.relax:
            continue
        ring: dict[int, set[int]] = {}
        for e, ts in edge_tris.items():
            if _open(e):
                t = min(ts)
                if all(r.selects(heavy[v], group_of[v]) for v in tris[t]):
                    ring.setdefault(e[0], set()).add(e[1])
                    ring.setdefault(e[1], set()).add(e[0])
        free = sorted(w for w, nb in ring.items() if len(nb) == 2 and r.holds(wpos[w]))
        fans: dict[int, list[tuple[int, int, int]]] = {}       # each loop point's faces (welded), their first facing
        on_loop = set(free)
        for t in tris:
            wt = tuple(wid_of[v] for v in t)
            if len(set(wt)) == 3 and set(wt) & on_loop and _norm(_face(wpos, wt)) > 0.0:
                for w in set(wt) & on_loop:
                    fans.setdefault(w, []).append(wt)
        facing = {wt: _face(wpos, wt) for fan in fans.values() for wt in fan}
        for _ in range(r.hem.relax):
            for w in free:      # in turn, each step halved until none of its faces turns from its first facing
                a, b = sorted(ring[w])
                was = wpos[w]
                step = [0.5 * ((wpos[a][c] + wpos[b][c]) / 2.0 - was[c]) for c in range(3)]
                for _halve in range(HEM_HALVINGS + 1):
                    wpos[w] = _f32(tuple(was[c] + step[c] for c in range(3)))
                    if all(_dot(_face(wpos, wt), facing[wt]) > 0.0 for wt in fans.get(w, ())):
                        break
                    step = [x / 2.0 for x in step]
                else:
                    wpos[w] = was
        moved = set(free)
        for k in range(len(ids)):
            if wid_of[k] in moved:
                basep[k] = wpos[wid_of[k]]
    groups = tuple(replace(g, count=counts[g.index]) for g in mesh.groups)
    out = _Mesh(mesh.body, mesh.lods, groups, tuple(ids), tuple(keys), tuple(pos), tuple(nrm), tuple(uvs),
                tuple(skins), tuple(heavy), tuple(tris), mesh.names, mesh.parents, mesh.origins, mesh.binds)
    return out, basep, smooth


def _smooth_normals(mesh: _Mesh, after: list[Vec], which: set[int],
                    angled: dict[int, str] | frozenset[int] = frozenset()) -> dict[int, Vec]:
    """Smooth normals at ``after`` for the vertices ``which``: the
    area-weighted normal of every face round the vertex and its seam
    copies whose own faces in ``after`` turn the same way as its own
    (within 60 degrees: a two-sided layer's far side stays apart, and a
    crease vanilla kept with two copies is joined once the ops bend it
    smooth, Step 2.154), each face turned to the vertex's own side (a
    twin face counts once on its side); a vertex of ``angled`` weighs
    each face by its angle there instead (Step 2.177c), or (its rule
    ``"nearer"``, Step 2.188) takes whichever of the two normals lies
    nearer the mean of its ring's (the vertices sharing a face with any
    copy of it: each one's area normal here, else its stored one; those
    within 120 degrees of the normal tried, a dot over -:data:`WELD`)."""
    rule_of = angled if isinstance(angled, dict) else dict.fromkeys(angled, "angle")
    at: dict[bytes, list[int]] = {}
    for k, key in enumerate(mesh.keys):
        at.setdefault(key, []).append(k)
    tri_of: dict[int, list[int]] = {}
    own = [[0.0, 0.0, 0.0] for _ in mesh.positions]
    for t, tri in enumerate(mesh.triangles):
        f = _face(after, tri)
        for v in tri:
            tri_of.setdefault(v, []).append(t)
            for c in range(3):
                own[v][c] += f[c]
    unit = [_unit(n) for n in own]
    stored = [_unit(n) for n in mesh.normals]
    out: dict[int, Vec] = {}
    other: dict[int, Vec | None] = {}     # a "nearer" vertex's angle normal, its area one in ``out`` till chosen
    for k in sorted(which):
        r = unit[k] or stored[k]
        mates = [j for j in at[mesh.keys[k]] if r is None or (unit[j] or stored[j]) is None
                 or _dot(r, unit[j] or stored[j]) > WELD]
        fan = sorted({t for j in mates for t in tri_of.get(j, ())})
        rule = rule_of.get(k)
        acc = [0.0, 0.0, 0.0]
        alt = [0.0, 0.0, 0.0]
        for t in fan:
            tri = mesh.triangles[t]
            f = _face(after, tri)
            if r is None:
                r = _unit(f)
                if r is None:
                    continue
            sign = 1.0 if _dot(f, r) >= 0.0 else -1.0
            if rule is not None:      # the face counts by its angle at the vertex (or the mate it holds), not its area
                i = next(i for i in range(3) if tri[i] in mates)
                p = after[tri[i]]
                u, w, size = _sub(after[tri[(i + 1) % 3]], p), _sub(after[tri[(i + 2) % 3]], p), _norm(f)
                whole = size > 0.0 and _norm(u) > 0.0 and _norm(w) > 0.0
                if rule == "nearer":
                    if whole:
                        weight = sign * fdlibm.acos(max(-1.0, min(1.0, _dot(u, w) / (_norm(u) * _norm(w))))) / size
                        for c in range(3):
                            alt[c] += weight * f[c]
                else:
                    if not whole:
                        continue
                    sign *= fdlibm.acos(max(-1.0, min(1.0, _dot(u, w) / (_norm(u) * _norm(w))))) / size
            for c in range(3):
                acc[c] += sign * f[c]
        n = _unit(acc)
        if n is not None:
            out[k] = _f32(n)
        if rule == "nearer":
            other[k] = _unit(alt)
    if other:
        area = dict(out)
        for k, angle_n in other.items():
            area_n = area.get(k)
            if angle_n is None or area_n is None:
                continue
            own = set(at[mesh.keys[k]])
            ring = sorted({j for m in own for t in tri_of.get(m, ()) for j in mesh.triangles[t]} - own)
            near = [area.get(j) or stored[j] for j in ring]

            def off(n: Vec) -> float:
                mean = [0.0, 0.0, 0.0]
                for q in near:
                    if q is not None and _dot(q, n) > -WELD:
                        q = _unit(q)
                        for c in range(3):
                            mean[c] += q[c]
                m = _unit(mean)
                return -1.0 if m is None else _dot(m, _unit(n))
            if off(angle_n) >= off(area_n):    # the angle's lies nearer (or as near): it is taken
                out[k] = _f32(angle_n)
    return out


BENEATH_CELLS = 48
"""The direction grid a ``beneath`` reads its cloth through: cells of
1/48 on each axis of the unit ray direction."""


def _beneath(mesh: _Mesh, spec: MeshSpec, final: list[Vec]) -> int:
    """Each ``round`` side with ``beneath`` (groups, gap): every vertex it
    selects whose ray from its origin meets those groups' final triangles
    (the nearest crossing past the origin) and ends nearer than ``gap``
    under it (or past it) moved back along the ray to ``gap`` under it;
    ``final`` in place, how many moved.  The cloth's triangles are read
    through a grid over their corners' ray directions (each cell padded
    by one, so a triangle is read wherever a ray could meet it)."""
    group_of = [g for g, _ in mesh.ids]
    moved = 0
    for sides in _rounds(mesh, spec):
        for side in sides:
            if side.op.beneath is None or (side.op.pair and side is not sides[0]):
                continue       # a pair's rays are its first side's
            groups, gap = side.op.beneath
            n, sa, ta = side.frame
            os_, on_, ot_ = side.rays[:3]
            c = side.centre
            o = side.origin or tuple(c[i] + os_ * sa[i] + on_ * n[i] + ot_ * ta[i] for i in range(3))
            cloth = [t for t in mesh.triangles if all(group_of[v] in groups for v in t)
                     and not mesh.fixed.intersection(t)]      # a tube or a cut's cord isn't the cloth
            grid: dict[tuple[int, int, int], list[int]] = {}
            for t, tri in enumerate(cloth):
                dirs = [_unit(_sub(final[v], o)) for v in tri]
                if any(d is None for d in dirs):
                    continue
                lo = [math.floor(min(d[i] for d in dirs) * BENEATH_CELLS) - 1 for i in range(3)]
                hi = [math.floor(max(d[i] for d in dirs) * BENEATH_CELLS) + 1 for i in range(3)]
                for i in range(lo[0], hi[0] + 1):
                    for j in range(lo[1], hi[1] + 1):
                        for k in range(lo[2], hi[2] + 1):
                            grid.setdefault((i, j, k), []).append(t)
            # each cloth triangle's edges from its first corner, that corner to the origin and their cross (no skin
            # point this side moves is the cloth's), read a cell's triangles at once (Step 2.179: booblord_high's
            # finer skin and top asked 2.5 million): the loop's floats, a cell's as numpy's same products and sums
            corners = np.array([[final[w] for w in tri] for tri in cloth], dtype=np.float64).reshape(-1, 3, 3)
            e1, e2, tv = corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0], np.array(o) - corners[:, 0]
            qv = np.stack((tv[:, 1] * e1[:, 2] - tv[:, 2] * e1[:, 1], tv[:, 2] * e1[:, 0] - tv[:, 0] * e1[:, 2],
                           tv[:, 0] * e1[:, 1] - tv[:, 1] * e1[:, 0]), axis=1)
            table = np.concatenate((e1, e2, tv, qv), axis=1)
            read: dict[tuple[int, int, int], np.ndarray] = {}
            at: dict[bytes, list[int]] = {}
            for v in range(len(final)):
                at.setdefault(mesh.keys[v], []).append(v)
            for key in sorted(at):
                copies = at[key]
                if any(group_of[w] in groups for w in copies):
                    continue           # a point the cloth shares: it moves with the cloth
                mine = [w for w in copies if side.selects(mesh.heaviest[w], group_of[w])]
                if not mine:
                    continue
                v = mine[0]
                got = _pair_ray(final[v], sides) if side.op.pair else _ray(final[v], side)
                if got is None or got[1] > got[2] + got[3]:
                    continue           # past the form and its blend: not this layer's
                q = _sub(final[v], o)
                r = _norm(q)
                u = (q[0] / r, q[1] / r, q[2] / r)
                cell = tuple(math.floor(u[i] * BENEATH_CELLS) for i in range(3))
                near = None
                if cell in grid:
                    got = read.get(cell)
                    if got is None:
                        got = read[cell] = table[grid[cell]]
                    a1, a2, a3, b1, b2, b3, t1, t2, t3, q1, q2, q3 = got.T
                    p1, p2, p3 = u[1] * b3 - u[2] * b2, u[2] * b1 - u[0] * b3, u[0] * b2 - u[1] * b1
                    det = a1 * p1 + a2 * p2 + a3 * p3
                    with np.errstate(divide="ignore", invalid="ignore"):
                        x = (t1 * p1 + t2 * p2 + t3 * p3) / det
                        y = (u[0] * q1 + u[1] * q2 + u[2] * q3) / det
                        dist = (b1 * q1 + b2 * q2 + b3 * q3) / det
                        hit = (np.abs(det) >= 1e-12) & (x >= 0.0) & (x <= 1.0) & (y >= 0.0) & (x + y <= 1.0) & (
                            dist > 0.0)   # a thicken's rims are flat here (Step 2.177d): their NaNs miss
                    if hit.any():
                        near = float(dist[hit].min())
                if near is not None and r > near - gap and near - gap > 0.0:
                    for w in mine:
                        final[w] = tuple(o[i] + (near - gap) * u[i] for i in range(3))
                    moved += 1
    return moved


def _insets(mesh: _Mesh, spec: MeshSpec, base: list[Vec], final: list[Vec]) -> int:
    """The ``hem`` ops' insets on ``final`` in place: each vertex a region
    holds (at the base) and selects within ``width`` of one of its open
    edges (welded, a two-sided layer's twin counted once; in the final
    shape) drawn towards the op's centre by ``inset`` times one less the
    smoothstep of its distance over ``width``; how many moved."""
    regions = [r for r in _regions(mesh, spec, HemOp) if r.hem.inset > 0.0 and r.hem.width > 0.0]
    if not regions:
        return 0
    group_of = [g for g, _ in mesh.ids]
    moved = 0
    for r in regions:
        faces: dict[tuple[bytes, bytes], set] = {}
        ends: dict[tuple[bytes, bytes], tuple[int, int]] = {}
        for tri in mesh.triangles:
            if not all(r.selects(mesh.heaviest[v], group_of[v]) for v in tri):
                continue
            key = frozenset(mesh.keys[v] for v in tri)
            for i in range(3):
                a, b = tri[i], tri[(i + 1) % 3]
                e = (min(mesh.keys[a], mesh.keys[b]), max(mesh.keys[a], mesh.keys[b]))
                faces.setdefault(e, set()).add(key)
                ends.setdefault(e, (a, b))
        cell = r.hem.width
        grid: dict[tuple[int, int, int], list] = {}
        for e, fs in faces.items():
            a, b = ends[e]
            if len(fs) != 1 or not (r.holds(base[a]) and r.holds(base[b])):
                continue
            pa, pb = final[a], final[b]
            lo = [math.floor(min(pa[c], pb[c]) / cell) for c in range(3)]
            hi = [math.floor(max(pa[c], pb[c]) / cell) for c in range(3)]
            for i in range(lo[0], hi[0] + 1):
                for j in range(lo[1], hi[1] + 1):
                    for k in range(lo[2], hi[2] + 1):
                        grid.setdefault((i, j, k), []).append((pa, pb))
        if not grid:
            continue
        at: dict[bytes, list[int]] = {}
        for v in range(len(final)):
            if r.selects(mesh.heaviest[v], group_of[v]) and r.holds(base[v]):
                at.setdefault(mesh.keys[v], []).append(v)
        for key in sorted(at):
            v = at[key][0]
            q = final[v]
            ci = [math.floor(q[c] / cell) for c in range(3)]
            best = None
            for i in (-1, 0, 1):
                for j in (-1, 0, 1):
                    for k in (-1, 0, 1):
                        for pa, pb in grid.get((ci[0] + i, ci[1] + j, ci[2] + k), ()):
                            e = _sub(pb, pa)
                            ee = _dot(e, e)
                            x = 0.0 if not ee > 0.0 else min(1.0, max(0.0, _dot(_sub(q, pa), e) / ee))
                            d = _norm(_sub(q, (pa[0] + x * e[0], pa[1] + x * e[1], pa[2] + x * e[2])))
                            if best is None or d < best:
                                best = d
            if best is None or not best < r.hem.width:
                continue
            step = r.hem.inset * (1.0 - _smooth(best / r.hem.width))
            to = _unit(_sub(r.centre, q))
            if to is None or not step > 0.0:
                continue
            for w in at[key]:
                final[w] = (q[0] + step * to[0], q[1] + step * to[1], q[2] + step * to[2])
            moved += 1
    return moved


HEM_HALVINGS = 6
"""How many times a hem's relax halves a loop point's step before it
leaves the point where it was (AZ-673: a full step turned the small
faces beside a cloth's edge over at the base, and the forms magnified
the folds)."""
RELAX_STEPS = (0.5, -0.53)
"""A ``relax`` pass's Taubin pair: a smoothing step, then an inflating
one, so a round form keeps its size where plain smoothing shrinks it."""
MIDLINE = 1e-7
"""A point whose base x is within this of 0 stays on x = 0 (a relax)."""


def _relax(mesh: _Mesh, spec: MeshSpec, base: list[Vec], final: list[Vec]) -> int:
    """The ``relax`` ops (:class:`RelaxOp`) in recipe order on ``final`` in
    place: the welded points of the triangles whose corners an op selects,
    within its region at the base, each moved towards the mean of its
    welded neighbours by the pass's step times its falloff (sorted order,
    plain floats); an open edge's points stay, or (``open``) take their
    loop's two neighbours only; how many points moved."""
    group_of = [g for g, _ in mesh.ids]
    wid: dict[bytes, int] = {}
    wof = [wid.setdefault(key, len(wid)) for key in mesh.keys]
    first: dict[int, int] = {}
    for k, w in enumerate(wof):
        first.setdefault(w, k)
    moved: set[int] = set()
    for i, op in enumerate(spec.ops):
        if not isinstance(op, RelaxOp):
            continue
        if op.passes < 0:
            raise ValueError(f"mesh.ops[{i}].passes: {op.passes} is not a count of passes")
        regions = _regions(mesh, MeshSpec(ops=(op,), keep=spec.keep), RelaxOp)
        chosen = [all(any(r.selects(mesh.heaviest[v], group_of[v]) for r in regions) for v in t) for t in mesh.triangles]
        faces: dict[tuple[int, int], set] = {}
        adj: dict[int, set[int]] = {}
        for t, ok in zip(mesh.triangles, chosen):
            if not ok:
                continue
            w = [wof[v] for v in t]
            if len(set(w)) < 3:
                continue
            key = frozenset(w)
            for a in range(3):
                x, y = w[a], w[(a + 1) % 3]
                faces.setdefault((min(x, y), max(x, y)), set()).add(key)
                adj.setdefault(x, set()).add(y)
                adj.setdefault(y, set()).add(x)
        loop: dict[int, set[int]] = {}
        for (x, y), fs in faces.items():
            if len(fs) == 1:
                loop.setdefault(x, set()).add(y)
                loop.setdefault(y, set()).add(x)
        weight: dict[int, float] = {}
        for w in adj:
            p = base[first[w]]
            best = 0.0
            for r in regions:
                c, rad = r.centre, r.radius
                d2 = sum(fdlibm.sq((p[j] - c[j]) / rad[j]) for j in range(3))
                if d2 < 1.0:
                    best = max(best, fdlibm.sq(1.0 - d2))
            if best > 0.0 and (w not in loop or (op.open and len(loop[w]) == 2)):
                weight[w] = best
        free = sorted(weight)
        nbrs = {w: sorted(loop[w] if w in loop else adj[w]) for w in free}
        pos = {w: final[first[w]] for w in adj}
        mid = {w for w in free if abs(base[first[w]][0]) < MIDLINE}
        for _ in range(op.passes):
            for step in RELAX_STEPS:
                nxt = {}
                for w in free:
                    nb = nbrs[w]
                    q = pos[w]
                    m = tuple(sum(pos[x][j] for x in nb) / len(nb) for j in range(3))
                    f = step * weight[w]
                    nxt[w] = (0.0 if w in mid else q[0] + f * (m[0] - q[0]), q[1] + f * (m[1] - q[1]),
                              q[2] + f * (m[2] - q[2]))
                pos.update(nxt)
        for k, w in enumerate(wof):
            if w in weight and pos[w] != final[k]:
                final[k] = pos[w]
                moved.add(w)
    return len(moved)


BIND_CELL = 0.02
"""A ``bind``'s grid over the layer it copies from (model units)."""
NEAR_STEP = 0.01
"""A ``bind``'s ``near``: its ``to`` layer's triangles sampled at most this
far apart (a coarse strap's vertices sit 2.7 cm from the skin under its
triangles' middles)."""


def _surface_grid(mesh: _Mesh, final: list[Vec], groups: tuple[int, ...]) -> dict[tuple[int, int, int], list[Vec]]:
    """The final surface of the triangles whose corners are all in
    ``groups``: its corners and a barycentric grid at most
    :data:`NEAR_STEP` apart, by :data:`BIND_CELL` cell."""
    group_of = [g for g, _ in mesh.ids]
    out: dict[tuple[int, int, int], list[Vec]] = {}
    for t in mesh.triangles:
        if not all(group_of[v] in groups for v in t):
            continue
        a, b, c = (final[v] for v in t)
        n = max(1, min(12, math.ceil(max(_norm(_sub(b, a)), _norm(_sub(c, b)), _norm(_sub(a, c))) / NEAR_STEP)))
        for i in range(n + 1):
            for j in range(n + 1 - i):
                u, w = i / n, j / n
                q = tuple(a[x] + u * (b[x] - a[x]) + w * (c[x] - a[x]) for x in range(3))
                out.setdefault(tuple(math.floor(q[x] / BIND_CELL) for x in range(3)), []).append(q)
    return out


def _near_surface(grid: dict[tuple[int, int, int], list[Vec]], q: Vec, limit: float) -> float:
    """The least distance from ``q`` to a point of ``grid`` within
    ``limit`` (``limit`` where none is)."""
    span = math.ceil(limit / BIND_CELL)
    ci = tuple(math.floor(q[x] / BIND_CELL) for x in range(3))
    best = limit * limit
    for a in range(-span, span + 1):
        for b in range(-span, span + 1):
            for c in range(-span, span + 1):
                for p in grid.get((ci[0] + a, ci[1] + b, ci[2] + c), ()):
                    d = _dot(_sub(p, q), _sub(p, q))
                    if d < best:
                        best = d
    return math.sqrt(best)


def _bind_nearest(final: list[Vec], grid: dict[tuple[int, int, int], list[int]], ks: list[int]) -> dict[int, int]:
    """Each of ``ks``' nearest vertex of ``grid`` (by :data:`BIND_CELL`
    cell) in ``final``: among those in the 27 cells about its cell, else
    within 2, 4 or 8 cells, the least squared distance, ties to the lower
    index; none past 8 (Step X.65c: by cell, :func:`_nearest` over its
    cells' vertices with the loop's own distance and tie)."""
    by_cell: dict[tuple[int, int, int], list[int]] = {}
    for k in ks:
        by_cell.setdefault(tuple(math.floor(final[k][c] / BIND_CELL) for c in range(3)), []).append(k)
    out: dict[int, int] = {}
    for ci, mine in by_cell.items():
        reach, near = 1, []
        while not near and reach <= 8:
            near = [j for a in range(-reach, reach + 1) for b in range(-reach, reach + 1) for c in range(-reach, reach + 1)
                    for j in grid.get((ci[0] + a, ci[1] + b, ci[2] + c), ())]
            reach *= 2
        if near:
            got = _nearest([final[j] for j in near], [final[k] for k in mine],
                           lambda i, q: (_dot(_sub(final[near[i]], q), _sub(final[near[i]], q)), near[i]))
            out.update((k, near[i]) for k, i in zip(mine, got))
    return out


class _ReachMix:
    """A ``bind`` with a ``reach``'s mix (Step 2.176, as its loop over
    the grid's cells had it, in numpy): of every vertex of ``grid`` (its
    ``to`` layer by :data:`BIND_CELL` cell) in the cells within the reach
    of a point's cell and within the reach of it, ascending, each one's
    ``skins`` weighted by (1 - d^2 / reach^2)^2, each sum sequential in
    that order (:func:`numpy.cumsum` from 0.0), over the weights' sum, by
    bone: the loop's floats."""

    def __init__(self, final: list[Vec], grid: dict[tuple[int, int, int], list[int]], skins: list[dict[int, float]],
                 reach: float) -> None:
        import numpy as np

        self.ks = sorted(j for js in grid.values() for j in js)
        row = {j: n for n, j in enumerate(self.ks)}
        self.at_ = np.array([final[j] for j in self.ks], dtype=np.float64).reshape(-1, 3)
        self.grid = {cell: [row[j] for j in js] for cell, js in grid.items()}
        self.near: dict[tuple[int, int, int], tuple] = {}   # a cell: the rows in the cells about it, ascending, and
        # their x, y and z (Step 2.179: booblord_high's binds asked 34,000 mixes of 883 cells)
        bones = sorted({b for j in self.ks for b in skins[j]})
        self.bones, col = bones, {b: i for i, b in enumerate(bones)}
        self.weights = np.zeros((len(self.ks), len(bones)))
        self.has = np.zeros((len(self.ks), len(bones)), dtype=bool)
        for n, j in enumerate(self.ks):
            for b, x in skins[j].items():
                self.weights[n, col[b]], self.has[n, col[b]] = x, True
        self.bits = np.zeros(len(self.ks), dtype=np.int64)     # each row's bones as bits, while they fit
        if len(bones) < 63:
            for i in range(len(bones)):
                self.bits |= self.has[:, i].astype(np.int64) << i
        self.span, self.r2 = math.ceil(reach / BIND_CELL), reach * reach

    def at(self, q: Vec, cell: tuple[int, int, int]) -> dict[int, float] | None:
        """The mix at ``q`` (in ``cell``), or ``None`` where no vertex is in reach."""
        import numpy as np

        got = self.near.get(cell)
        if got is None:
            n = range(-self.span, self.span + 1)
            rows = np.array(sorted(r for a in n for b in n for c in n for r in self.grid.get(
                (cell[0] + a, cell[1] + b, cell[2] + c), ())), dtype=np.int64)
            at_ = self.at_[rows]
            got = self.near[cell] = (rows, at_[:, 0].copy(), at_[:, 1].copy(), at_[:, 2].copy())
        rows, x, y, z = got
        ux, uy, uz = x - q[0], y - q[1], z - q[2]
        d = ux * ux + uy * uy + uz * uz
        keep = d < self.r2
        rows, d = rows[keep], d[keep]
        if not len(rows):
            return None
        # Python's float power, as the loop's (libm's pow, which isn't numpy's square for 1 in 800)
        w = np.array(list(map(fdlibm.pow, (1.0 - d / self.r2).tolist(), itertools.repeat(2.0))))
        total = np.cumsum(np.concatenate(([0.0], w)))[-1]
        if len(self.bones) < 63:
            held = int(np.bitwise_or.reduce(self.bits[rows]))
            cols = np.array([i for i in range(len(self.bones)) if held >> i & 1], dtype=np.int64)
        else:
            cols = np.flatnonzero(self.has[rows].any(axis=0))
        terms = w[:, None] * self.weights[np.ix_(rows, cols)]
        sums = np.cumsum(np.vstack((np.zeros((1, len(cols))), terms)), axis=0)[-1]
        return {self.bones[c]: float(x) for c, x in zip(cols, sums / total)}


def _bind(mesh: _Mesh, spec: MeshSpec, base: list[Vec], final: list[Vec]) -> dict[int, dict[int, float]]:
    """The ``bind`` ops (:class:`BindOp`): the skin weights each vertex a
    region holds (at the base) and selects takes from the nearest vertex
    of its ``to`` groups in ``final`` (ties to the lower index; read
    through a grid of :data:`BIND_CELL`, its 27 cells about the vertex,
    then wider until one is found), or with ``reach`` from every one
    within it, mixed (:class:`BindOp`), and with ``fade`` mixed with its
    own by the region's falloff, and with ``near`` by its distance to that
    nearest vertex; a ``to`` vertex an earlier bind gave weights lends
    those; by vertex."""
    regions = _regions(mesh, spec, BindOp)
    if not regions:
        return {}
    group_of = [g for g, _ in mesh.ids]
    out: dict[int, dict[int, float]] = {}
    for i, op in enumerate(spec.ops):
        if not isinstance(op, BindOp):
            continue
        indices = {g.index for g in mesh.groups}
        for g in op.to:
            if g not in indices:
                raise ValueError(f"mesh.ops[{i}].to: {mesh.body} has no LOD-0 group {g}")
        if set(op.to) & set(op.groups) and not op.reach > 0.0:
            raise ValueError(f"mesh.ops[{i}]: a layer binds to its own group only with a reach (its weights mixed "
                             "within it)")
    last, prior = None, {}
    for r in regions:
        if r.bind is not last:        # the weights the binds before this one left (a mirror's two regions share)
            last, prior = r.bind, dict(out)
        to = r.to
        grid: dict[tuple[int, int, int], list[int]] = {}
        for k in range(len(final)):
            if group_of[k] in to:
                grid.setdefault(tuple(math.floor(final[k][c] / BIND_CELL) for c in range(3)), []).append(k)
        if not grid:
            continue
        surface = _surface_grid(mesh, final, to) if r.bind is not None and r.bind.near is not None else None
        ks = [k for k in range(len(final)) if r.holds(base[k]) and r.selects(mesh.heaviest[k], group_of[k])]
        nearest = _bind_nearest(final, grid, ks)
        mix = None
        for k in ks:
            if k not in nearest:
                continue
            q = final[k]
            ci = tuple(math.floor(q[c] / BIND_CELL) for c in range(3))
            op = r.bind
            g = 1.0
            if surface is not None:
                n0, n1 = op.near
                g = 1.0 - _smooth((_near_surface(surface, q, n1) - n0) / (n1 - n0))
                if not g > 0.0:
                    continue
            got = dict(prior.get(nearest[k]) or mesh.skins[nearest[k]])
            if op is not None and op.reach > 0.0:
                if mix is None:
                    mix = _ReachMix(final, grid, [prior.get(j) or mesh.skins[j] for j in range(len(final))], op.reach)
                reached = mix.at(q, ci)
                got = got if reached is None else reached
            f = g
            if op is not None and op.fade:
                p, cc, rr = base[k], r.centre, r.radius
                f *= fdlibm.sq(1.0 - sum(fdlibm.sq((p[i] - cc[i]) / rr[i]) for i in range(3)))
            if f < 1.0:
                mixed = {bone: (1.0 - f) * x for bone, x in (prior.get(k) or mesh.skins[k]).items()}
                for bone, x in got.items():
                    mixed[bone] = mixed.get(bone, 0.0) + f * x
                got = {bone: x for bone, x in sorted(mixed.items()) if x > 0.0}
            out[k] = got
    return out


def _reweight(mesh: _Mesh, spec: MeshSpec, base: list[Vec], bound: dict[int, dict[int, float]]
              ) -> dict[int, dict[int, float]]:
    """The ``reweight`` ops (:class:`ReweightOp`) in recipe order on each
    vertex's weights (a ``bind``'s where it gave them): the new weights,
    by vertex."""
    out: dict[int, dict[int, float]] = {}
    group_of = [g for g, _ in mesh.ids]
    names = list(mesh.names)
    for i, op in enumerate(spec.ops):
        if not isinstance(op, ReweightOp):
            continue
        for name in (*op.take, op.into):
            if name not in names:
                raise ValueError(f"mesh.ops[{i}]: {mesh.body} has no bone {name!r}")
        for key, band in (("z", op.z), ("x", op.x)):
            if band is not None and not band[0] < band[1]:
                raise ValueError(f"mesh.ops[{i}].{key}: {list(band)} must rise")
        for r in _regions(mesh, MeshSpec(ops=(op,), keep=spec.keep), ReweightOp):
            mirrored = r.label.endswith("mirrored")
            take = {names.index(_mirrored(n) if mirrored else n) for n in op.take}
            into = names.index(_mirrored(op.into) if mirrored else op.into)
            c, rad = r.centre, r.radius
            for k in range(len(base)):
                p = base[k]
                d2 = sum(fdlibm.sq((p[j] - c[j]) / rad[j]) for j in range(3))
                if not (d2 < 1.0 and r.selects(mesh.heaviest[k], group_of[k])):
                    continue
                f = op.share * fdlibm.sq(1.0 - d2)
                if op.z is not None:
                    f *= _smooth((p[2] - op.z[0]) / (op.z[1] - op.z[0]))
                if op.x is not None:
                    f *= _smooth((abs(p[0]) - op.x[0]) / (op.x[1] - op.x[0]))
                skin = dict(out.get(k) or bound.get(k) or mesh.skins[k])
                held = sum(w for b, w in skin.items() if b in take)
                if not (f > 0.0 and held > 0.0):
                    continue
                for b in take:
                    if b in skin:
                        skin[b] *= 1.0 - f
                skin[into] = skin.get(into, 0.0) + f * held
                out[k] = {b: w for b, w in skin.items() if w > 0.0}
    return out


# --------------------------------------------------------------------------- the UVs
UNWRAP_TOLERANCE = 1e-10
"""The conjugate gradient stops when the residual's squared length falls
under this share of its start."""
UNWRAP_MAX = 4000
"""The most conjugate-gradient steps an island takes."""


def _unwrap(mesh: _Mesh, spec: MeshSpec, base: list[Vec], final: list[Vec]) -> dict[int, tuple[float, float]]:
    """The ``unwrap`` ops (module docstring): each texture island of the
    triangles a region holds (centroid at the base, every corner
    selected; joined through shared vertices, so a UV seam parts two)
    gets its UVs again from the final shape: a vertex a triangle outside
    the region also uses keeps its UV (the texture outside meets it), a
    vertex on the island's edge moves ``shrink`` of the way to the
    island's UV centroid (a small island's dark rim left behind), and
    every other vertex takes the harmonic map of the final shape (the
    cotangent Laplacian, solved by conjugate gradients from its current
    UVs), so the texture spreads evenly over a form an op grew.  The UVs
    that change, by vertex."""
    regions = _regions(mesh, spec, UnwrapOp)
    if not regions:
        return {}
    group_of = [g for g, _ in mesh.ids]
    inside: list[bool] = []
    for tri in mesh.triangles:
        centre = tuple(sum(base[v][c] for v in tri) / 3.0 for c in range(3))
        inside.append(any(r.holds(centre) and all(r.selects(mesh.heaviest[v], group_of[v]) for v in tri)
                          for r in regions))
    shrink_of: list[float] = []
    for tri in mesh.triangles:
        centre = tuple(sum(base[v][c] for v in tri) / 3.0 for c in range(3))
        shrink_of.append(max((r.shrink for r in regions if r.holds(centre)), default=0.0))
    outside = {v for t, tri in enumerate(mesh.triangles) if not inside[t] for v in tri}
    tris_of: dict[int, list[int]] = {}
    for t, tri in enumerate(mesh.triangles):
        if inside[t]:
            for v in tri:
                tris_of.setdefault(v, []).append(t)
    seen: set[int] = set()
    out: dict[int, tuple[float, float]] = {}
    for start in sorted(tris_of):
        if start in seen:
            continue
        island, todo = [], [start]       # vertices joined by the region's triangles
        seen.add(start)
        while todo:
            v = todo.pop()
            island.append(v)
            for t in tris_of[v]:
                for w in mesh.triangles[t]:
                    if w not in seen:
                        seen.add(w)
                        todo.append(w)
        island.sort()
        tris = sorted({t for v in island for t in tris_of[v]})
        edges: dict[tuple[int, int], int] = {}
        for t in tris:
            a, b, c = mesh.triangles[t]
            for x, y in ((a, b), (b, c), (c, a)):
                e = (min(x, y), max(x, y))
                edges[e] = edges.get(e, 0) + 1
        rim = {v for e, n in edges.items() if n == 1 for v in e}
        uv = {v: mesh.uvs[v] for v in island}
        shrink = max(shrink_of[t] for t in tris)
        if shrink > 0.0:
            area = cu = cv = 0.0
            for t in tris:
                a, b, c = (mesh.uvs[v] for v in mesh.triangles[t])
                w = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
                area += w
                cu += w * (a[0] + b[0] + c[0]) / 3.0
                cv += w * (a[1] + b[1] + c[1]) / 3.0
            if area > 0.0:
                cu, cv = cu / area, cv / area
                for v in sorted(rim - outside):
                    u0, v0 = uv[v]
                    uv[v] = (u0 + shrink * (cu - u0), v0 + shrink * (cv - v0))
        free = [v for v in island if v not in outside and v not in rim]
        if not free:
            continue
        at = {v: i for i, v in enumerate(free)}
        rows: list[dict[int, float]] = [{} for _ in free]     # the cotangent Laplacian on the free vertices
        diag = [0.0] * len(free)
        rhs = [[0.0, 0.0] for _ in free]
        for t in tris:
            tri = mesh.triangles[t]
            for i in range(3):      # the angle at tri[i] weighs the opposite edge
                o, a, b = tri[i], tri[(i + 1) % 3], tri[(i + 2) % 3]
                pa, pb = _sub(final[a], final[o]), _sub(final[b], final[o])
                cross = _norm(_cross(pa, pb))
                if not cross > 0.0:
                    continue
                w = 0.5 * _dot(pa, pb) / cross
                for x, y in ((a, b), (b, a)):
                    if x in at:
                        k = at[x]
                        diag[k] += w
                        if y in at:
                            rows[k][at[y]] = rows[k].get(at[y], 0.0) - w
                        else:
                            rhs[k][0] += w * uv[y][0]
                            rhs[k][1] += w * uv[y][1]
        packed = [sorted(r.items()) for r in rows]
        for c in range(2):
            x = [uv[v][c] for v in free]

            def apply(q: list[float]) -> list[float]:
                return [diag[k] * q[k] + sum(w * q[j] for j, w in packed[k]) for k in range(len(q))]
            ax = apply(x)
            r = [rhs[k][c] - ax[k] for k in range(len(x))]
            d = list(r)
            rr = sum(e * e for e in r)
            stop = rr * UNWRAP_TOLERANCE
            for _ in range(UNWRAP_MAX):
                if not rr > stop or rr == 0.0:
                    break
                ad = apply(d)
                dad = sum(d[k] * ad[k] for k in range(len(d)))
                if not dad > 0.0:
                    break
                alpha = rr / dad
                for k in range(len(x)):
                    x[k] += alpha * d[k]
                    r[k] -= alpha * ad[k]
                rr2 = sum(e * e for e in r)
                beta = rr2 / rr
                rr = rr2
                for k in range(len(d)):
                    d[k] = r[k] + beta * d[k]
            for k, v in enumerate(free):
                uv[v] = (x[k], uv[v][1]) if c == 0 else (uv[v][0], x[k])
        for v in island:
            got = struct.unpack("<2f", struct.pack("<2f", *uv[v]))
            if got != tuple(struct.unpack("<2f", struct.pack("<2f", *mesh.uvs[v]))):
                if not all(math.isfinite(z) for z in got):
                    raise ValueError(f"mesh: an unwrap gave {mesh.body} vertex {mesh.ids[v]} a UV that isn't finite")
                out[v] = got
    return out


# --------------------------------------------------------------------------- islands and the atlas
def _island_sides(mesh: _Mesh, spec: MeshSpec) -> list[tuple[_Region, tuple[float, float, float, float], tuple | None]]:
    """The ``island`` ops' sides in recipe order, each with its rect and
    its op's ``uv`` box (None: a harmonic island)."""
    out = []
    for i, op in enumerate(spec.ops):
        if not isinstance(op, IslandOp):
            continue
        sides = _regions(mesh, MeshSpec(ops=(op,), keep=spec.keep), IslandOp)
        if len(op.rects) != len(sides):
            raise ValueError(f"mesh.ops[{i}].rects: {len(op.rects)} rects for {len(sides)} sides (one a side)")
        for r, rect in zip(sides, op.rects):
            if not (0.0 <= rect[0] < rect[2] <= 1.0 and 0.0 <= rect[1] < rect[3] <= 1.0):
                raise ValueError(f"mesh.ops[{i}].rects: {list(rect)} is not a rect inside 0..1 (u0, v0, u1, v1)")
            out.append((r, rect, op.uv))
    return out


def _island_of(mesh: _Mesh, spec: MeshSpec, base: list[Vec]) -> list[int]:
    """Each triangle's island (its index in :func:`_island_sides`) or -1:
    the first side whose region holds its base centroid and selects its
    corners, a mirrored pair's by the side of x = 0 its centroid lies on,
    and whose ``uv`` box (if any) holds its corners' UVs."""
    sides = _island_sides(mesh, spec)
    group_of = [g for g, _ in mesh.ids]
    out = []
    for tri in mesh.triangles:
        centre = tuple(sum(base[v][c] for v in tri) / 3.0 for c in range(3))
        got = -1
        for k, (r, _, box) in enumerate(sides):
            if box is not None and not all(box[0] <= mesh.uvs[v][0] <= box[2] and box[1] <= mesh.uvs[v][1] <= box[3]
                                           for v in tri):
                continue
            if r.holds(centre) and all(r.selects(mesh.heaviest[v], group_of[v]) for v in tri) \
                    and (abs(r.centre[0]) <= COPIES or (centre[0] >= 0.0) == (r.centre[0] > 0.0)):
                got = k
                break
        out.append(got)
    return out


def _split_islands(mesh: _Mesh, spec: MeshSpec, base: list[Vec]) -> tuple[_Mesh, list[Vec]]:
    """``mesh`` with each island one surface of its own: its triangles'
    corners at one stored position (vanilla's UV seams kept them apart)
    become one vertex, the lowest of them where only the island's
    triangles use that position, else a copy at the end of its group (the
    same stored position key, so it welds, moves and takes its normal with
    the others): a UV seam round the island and none in it.  The vertices
    it no longer uses stay, unused."""
    if not any(isinstance(op, IslandOp) for op in spec.ops):
        return mesh, base
    island = _island_of(mesh, spec, base)
    boxed = {k for k, (_, _, box) in enumerate(_island_sides(mesh, spec)) if box is not None}
    users: dict[bytes, set[int]] = {}
    held: dict[int, set[int]] = {}
    for t, tri in enumerate(mesh.triangles):
        for v in tri:
            users.setdefault(mesh.keys[v], set()).add(island[t])
            held.setdefault(v, set()).add(island[t])
    ids, keys, pos, nrm, uvs = list(mesh.ids), list(mesh.keys), list(mesh.positions), list(mesh.normals), list(mesh.uvs)
    skins, heavy, basep = list(mesh.skins), list(mesh.heaviest), list(base)
    counts = {g.index: g.count for g in mesh.groups}
    tris = [list(t) for t in mesh.triangles]
    corners = tuple(tuple(mesh.uvs[v] for v in t) for t in mesh.triangles)
    for k in sorted({i for i in island if i >= 0}):
        rep: dict = {}
        for t, tri in enumerate(tris):
            if island[t] != k:
                continue
            for v in tri:
                if k in boxed:      # vanilla's layout kept: a vertex its own, a copy where others use it too
                    if held[v] == {k}:
                        rep[v] = v
                    continue
                key = (ids[v][0], keys[v])
                if users[keys[v]] == {k}:
                    rep[key] = min(rep.get(key, v), v)
        for t, tri in enumerate(tris):
            if island[t] != k:
                continue
            for c, v in enumerate(tri):
                key = v if k in boxed else (ids[v][0], keys[v])
                if key not in rep:
                    g = ids[v][0]
                    rep[key] = len(ids)
                    ids.append((g, counts[g]))
                    counts[g] += 1
                    for lst in (keys, pos, nrm, uvs, skins, heavy, basep):
                        lst.append(lst[v])
                tri[c] = rep[key]
    groups = tuple(replace(g, count=counts[g.index]) for g in mesh.groups)
    out = _Mesh(mesh.body, mesh.lods, groups, tuple(ids), tuple(keys), tuple(pos), tuple(nrm), tuple(uvs),
                tuple(skins), tuple(heavy), tuple(tuple(t) for t in tris), mesh.names, mesh.parents, mesh.origins,
                mesh.binds, corners)
    return out, basep


def _circle(sides: int) -> list[tuple[float, float]]:
    """``sides`` points round the unit circle from (1, 0) (a multiple of 4
    that halves to 4), by rotation through a step whose cosine and sine
    come from halving 90 degrees with square roots."""
    k, c = sides, 0.0
    while k > 4:
        if k % 2:
            raise ValueError(f"a tube's sides {sides} isn't 4 doubled (8, 16, 32 ...)")
        c, k = math.sqrt((1.0 + c) / 2.0), k // 2
    if k != 4:
        raise ValueError(f"a tube's sides {sides} isn't 4 doubled (8, 16, 32 ...)")
    sn = math.sqrt(max(0.0, 1.0 - c * c))
    out, x, y = [], 1.0, 0.0
    for _ in range(sides):
        out.append((x, y))
        x, y = x * c - y * sn, x * sn + y * c
    return out


def _catmull(pts: list[Vec], closed: bool, t: float) -> tuple[Vec, Vec]:
    """The Catmull-Rom curve through ``pts`` at ``t`` (0..1 over its spans)
    and its tangent (unnormalised)."""
    n = len(pts)
    spans = n if closed else n - 1
    f = t * spans
    i = min(int(f), spans - 1)
    u = f - i

    def at(j: int) -> Vec:
        if closed:
            return pts[j % n]
        if j < 0:
            return tuple(2 * pts[0][c] - pts[1][c] for c in range(3))
        if j >= n:
            return tuple(2 * pts[-1][c] - pts[-2][c] for c in range(3))
        return pts[j]
    p0, p1, p2, p3 = at(i - 1), at(i), at(i + 1), at(i + 2)
    u2, u3 = u * u, u * u * u
    pos = tuple(0.5 * (2 * p1[c] + (p2[c] - p0[c]) * u + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * u2
                       + (3 * p1[c] - p0[c] - 3 * p2[c] + p3[c]) * u3) for c in range(3))
    tan = tuple(0.5 * ((p2[c] - p0[c]) + 2 * (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * u
                       + 3 * (3 * p1[c] - p0[c] - 3 * p2[c] + p3[c]) * u2) for c in range(3))
    return pos, tan


def _generate(mesh: _Mesh, spec: MeshSpec, base: list[Vec]) -> tuple[_Mesh, list[Vec]]:
    """``mesh`` with each ``tube`` op's geometry at the end of its group
    (module docstring of :class:`TubeOp`); its vertices fixed, its named
    shares kept."""
    made_tubes = [(i, op) for i, op in enumerate(spec.ops) if isinstance(op, TubeOp)]
    if not made_tubes:
        return mesh, base
    tubes = list(mesh.tubes)
    ids, keys, pos, nrm, uvs = list(mesh.ids), list(mesh.keys), list(mesh.positions), list(mesh.normals), list(mesh.uvs)
    skins, heavy, basep = list(mesh.skins), list(mesh.heaviest), list(base)
    counts = {g.index: g.count for g in mesh.groups}
    tris = list(mesh.triangles)
    corners = list(mesh.corners) if mesh.corners else None
    fixed = set(mesh.fixed)
    segments = list(mesh.segments)
    names = list(mesh.names)
    group_of = [g for g, _ in mesh.ids]
    for i, op in made_tubes:
        if op.bone not in names:
            raise ValueError(f"mesh.ops[{i}].bone: {mesh.body} has no bone {op.bone!r}")
        if op.group not in counts:
            raise ValueError(f"mesh.ops[{i}].group: {mesh.body} has no LOD-0 group {op.group}")
        if len(op.path) < 2 or len(op.radius) != len(op.path) or not all(r > 0 for r in op.radius):
            raise ValueError(f"mesh.ops[{i}]: a tube needs 2 path points or more, one radius above 0 a point")
        if op.rings < 2 or not op.flat > 0 or op.segments < 0:
            raise ValueError(f"mesh.ops[{i}]: rings at least 2, flat above 0, segments at least 0")
        ring = _circle(op.sides)
        o = mesh.origins[names.index(op.bone)]
        pts = [(o[0] + p[0], o[1] + p[1], o[2] + p[2]) for p in op.path]
        hint = _unit(op.across)
        if hint is None:
            raise ValueError(f"mesh.ops[{i}].across is zero")
        follow = [k for k in range(len(ids)) if group_of[k] in op.follow] if op.follow else []
        if op.follow and not follow:
            raise ValueError(f"mesh.ops[{i}].follow: no vertex of groups {list(op.follow)}")
        if op.fade is not None and (op.fade[0] not in names or not 0.0 <= op.fade[1] < op.fade[2] <= 1.0
                                    or op.follow):
            raise ValueError(f"mesh.ops[{i}].fade: a bone of {mesh.body} and a share rising within 0..1, "
                             "on a tube with no follow")
        reach = op.reach if isinstance(op.reach, tuple) else (op.reach,) * len(op.path)
        if len(reach) != len(op.path) or min(reach) < 0.0:
            raise ValueError(f"mesh.ops[{i}].reach: one a path point (or one for all), at least 0")
        if max(reach) > 0.0 and not op.follow:
            raise ValueError(f"mesh.ops[{i}].reach: the follow groups' weights in the final shape: name them")
        smooth, under = _along_path(op, op.smooth), _along_path(op, op.under)
        if len(smooth) != len(op.path) or min(smooth) < 0.0:
            raise ValueError(f"mesh.ops[{i}].smooth: one a path point (or one for all), at least 0")
        if max(smooth) > 0.0 and (max(reach) <= 0.0 or op.facets):
            raise ValueError(f"mesh.ops[{i}].smooth: low-passes a reach's weights along a tube's rings: give it a "
                             "reach and no facets")
        if op.skip and (max(reach) <= 0.0 or any(n not in names for n in op.skip)
                        or any(mesh.parents[names.index(n)] < 0 for n in op.skip)):
            raise ValueError(f"mesh.ops[{i}].skip: bones of {mesh.body} with a parent, on a tube with a reach")
        if len(under) != len(op.path) or min(under) < 0.0 or max(under) > 1.0:
            raise ValueError(f"mesh.ops[{i}].under: one a path point (or one for all), from 0 to 1")
        if max(under) > 0.0 and (max(reach) <= 0.0 or op.facets):
            raise ValueError(f"mesh.ops[{i}].under: mixes the surface under a tube's rings into its reach's weights: "
                             "give it a reach and no facets")
        if op.hang and max(reach) <= 0.0:
            raise ValueError(f"mesh.ops[{i}].hang: W29 hangs a tube that rides the skin as one piece: give it a reach")
        count = op.rings if op.closed else op.rings
        steps = [k / count for k in range(count)] if op.closed else [k / (count - 1) for k in range(count)]
        frames = []
        prev_s = None
        for t in steps:
            p, tan = _catmull(pts, op.closed, t)
            tu = _unit(tan) or (0.0, 0.0, 1.0)
            s_ = _sub(hint, tuple(_dot(hint, tu) * c for c in tu))
            s_ = _unit(s_) or prev_s or _unit(_cross(tu, (0.0, 0.0, 1.0))) or (1.0, 0.0, 0.0)
            prev_s = s_
            frames.append((p, tu, s_, _cross(tu, s_)))
        length = [0.0]
        for a, b in zip(frames, frames[1:]):
            length.append(length[-1] + _norm(_sub(b[0], a[0])))
        total = length[-1] + (_norm(_sub(frames[0][0], frames[-1][0])) if op.closed else 0.0)
        u0, v0, u1, v1 = op.rect
        g = op.group
        start = len(ids)

        def add(p: Vec, n: Vec, uv: tuple[float, float], frac: float, near_: float = 0.0) -> int:
            k = len(ids)
            ids.append((g, counts[g]))
            counts[g] += 1
            keys.append(b"T" + struct.pack("<I", k))
            q = _f32(p)
            pos.append(q)
            basep.append(q)
            nrm.append(n)
            uvs.append(uv)
            if follow:      # the nearest follow vertex's: resolved() fills them, many at once
                pending.append((k, q))
                skins.append(None)
                heavy.append(None)
            elif op.fade is not None:
                b, f = names.index(op.bone), names.index(op.fade[0])
                w = _smooth((frac - op.fade[1]) / (op.fade[2] - op.fade[1]))
                skin = {b: 1.0 - w} if w < 1.0 else {}
                if w > 0.0:
                    skin[f] = skin.get(f, 0.0) + w
                skins.append(skin)
                heavy.append(b if w < 0.5 else f)
            else:
                b = names.index(op.bone)
                skins.append({b: 1.0})
                heavy.append(b)
            group_of.append(g)
            fixed.add(k)
            fracs.append(frac)
            reaches.append(near_)
            return k

        def resolved() -> None:
            near = _nearest(follow_at, [q for _, q in pending],
                            lambda i, q: (_dot(_sub(base[follow[i]], q), _sub(base[follow[i]], q)), follow[i]))
            for (k, _), i in zip(pending, near):
                skins[k] = dict(mesh.skins[follow[i]])
                heavy[k] = mesh.heaviest[follow[i]]
            pending.clear()
        pending: list[tuple[int, Vec]] = []
        follow_at = [base[j] for j in follow]
        fracs: list[float] = []
        reaches: list[float] = []
        grid = []
        for r_i, (p, tu, sa, de) in enumerate(frames):
            t = steps[r_i]
            f = t * (len(pts) if op.closed else len(pts) - 1)
            j = min(int(f), len(pts) - (1 if not op.closed else 0) - 1)
            w = f - j
            rad = op.radius[j % len(pts)] + w * (op.radius[(j + 1) % len(pts)] - op.radius[j % len(pts)])
            ring_reach = reach[j % len(pts)] + w * (reach[(j + 1) % len(pts)] - reach[j % len(pts)])
            row = []
            for c_i in range(op.sides + 1):
                cx, cy = ring[c_i % op.sides]
                n = tuple(cx * sa[c] + cy * de[c] for c in range(3))
                q = tuple(p[c] + rad * cx * sa[c] + rad * op.flat * cy * de[c] for c in range(3))
                v = v0 + (v1 - v0) * (length[r_i] / total if total > 0 else 0.0)
                row.append(add(q, n, (u0 + (u1 - u0) * c_i / op.sides, v), length[r_i] / total if total else 0.0,
                               ring_reach))
            grid.append(row)
        new_tris = []
        lines = len(grid) if op.closed else len(grid) - 1
        for r_i in range(lines):
            a, b = grid[r_i], grid[(r_i + 1) % len(grid)]
            for c_i in range(op.sides):
                new_tris.append((a[c_i], b[c_i], a[c_i + 1]))
                new_tris.append((a[c_i + 1], b[c_i], b[c_i + 1]))
        if not op.closed:       # the tip
            p, tu, sa, de = frames[-1]
            tip = add(tuple(p[c] + 0.5 * op.radius[-1] * tu[c] for c in range(3)), tu,
                      ((u0 + u1) / 2.0, v1), 1.0, reach[-1])
            last = grid[-1]
            for c_i in range(op.sides):
                new_tris.append((last[c_i], tip, last[c_i + 1]))
        resolved()
        # wind each triangle so its face looks out of the tube (away from its ring's centre)
        out_tris = []
        for t in new_tris:
            f = _face(pos, t)
            centre = tuple(sum(pos[v][c] for v in t) / 3.0 for c in range(3))
            r_i = min(range(len(frames)), key=lambda q: _norm(_sub(frames[q][0], centre)))
            out = _sub(centre, frames[r_i][0])
            out_tris.append(t if _dot(f, out) >= 0.0 else (t[0], t[2], t[1]))
        if op.facets:       # each face its own corners, with its normal: re-made in the same order
            made_v = [(pos[k], uvs[k], fracs[k - start], reaches[k - start]) for k in range(start, len(ids))]
            for k in range(start, len(ids)):
                fixed.discard(k)
            counts[g] -= len(ids) - start
            for lst in (ids, keys, pos, basep, nrm, uvs, skins, heavy, group_of):
                del lst[start:]
            fracs.clear()
            reaches.clear()
            faceted = []
            for t in out_tris:
                n = _unit(_cross(_sub(made_v[t[1] - start][0], made_v[t[0] - start][0]),
                                 _sub(made_v[t[2] - start][0], made_v[t[0] - start][0]))) or (0.0, 0.0, 1.0)
                faceted.append(tuple(add(made_v[v - start][0], n, made_v[v - start][1], made_v[v - start][2],
                                         made_v[v - start][3]) for v in t))
            out_tris = faceted
            resolved()
        tris.extend(out_tris)
        if corners is not None:
            corners.extend(tuple(uvs[v] for v in t) for t in out_tris)
        if max(reach) > 0.0:
            tubes.append((i, tuple(range(start, len(ids))), tuple(reaches)))
        if op.segments:
            made = range(start, len(ids))
            for n_i in range(1, op.segments + 1):
                centre = n_i / op.segments
                share = {}
                for k in made:
                    f = fracs[k - start]
                    h = 1.0 - abs(f - centre) * op.segments
                    if n_i == op.segments and f >= centre:
                        h = 1.0
                    if h > 0.0:
                        share[k] = h
                segments.append((f"{op.name} {n_i}", share))
    groups = tuple(replace(g, count=counts[g.index]) for g in mesh.groups)
    out = _Mesh(mesh.body, mesh.lods, groups, tuple(ids), tuple(keys), tuple(pos), tuple(nrm), tuple(uvs),
                tuple(skins), tuple(heavy), tuple(tris), mesh.names, mesh.parents, mesh.origins, mesh.binds,
                tuple(corners) if corners is not None else (), frozenset(fixed), tuple(segments), mesh.cuts,
                mesh.trims, tuple(tubes))
    return out, basep


CUT_SNAP = 5e-4
"""A vertex within this of a cut's plane (model units) is on it: kept,
and the new edge passes through it (no crossing a hair from it, so no
triangle of no area)."""


def _approx_finals(mesh: _Mesh, spec: MeshSpec, base: list[Vec], which) -> dict[int, Vec]:
    """The vertices ``which`` at the field ops and the rounds (no relax,
    hem inset, beneath or press): where a cut reads the final shape."""
    placed = _place(mesh, spec)
    rounds = _rounds(mesh, spec)
    group_of = [g for g, _ in mesh.ids]
    out, moved = {}, []
    for k in which:
        if k in mesh.fixed:
            out[k] = base[k]
            continue
        ops = [op for op in placed if op.selects(mesh.heaviest[k], group_of[k])]
        out[k] = _displace(base[k], ops)[0] if ops else base[k]
        moved.append(k)
    if rounds:   # the rounds a round at a time over them all (a side's rays at once)
        for k, q in zip(moved, _round_all_each([out[k] for k in moved], rounds, [mesh.heaviest[k] for k in moved],
                                               [group_of[k] for k in moved])):
            out[k] = q
    return out


CORD_STEP = 0.0025
"""A snapped cut's cord: one ring this far apart along its edge."""
CORD_SMOOTH = 3
"""A snapped cut's cord: its edge's chain smoothed this many passes (its
ends kept) before the rings are laid along it."""


def _cut_planes(mesh: _Mesh, op: CutOp):
    """A cut's (c, n, corner): its plane's point and unit normal, and its
    corner's (c2, n2, radius) or None."""
    o = mesh.origins[mesh.names.index(op.bone)]
    c = (o[0] + op.offset[0], o[1] + op.offset[1], o[2] + op.offset[2])
    n = _unit(op.normal)
    corner = None
    if op.corner is not None:
        n2, off2, r = op.corner
        corner = ((o[0] + off2[0], o[1] + off2[1], o[2] + off2[2]), _unit(n2), r)
    return c, n, corner


def _cut_value(q: Vec, planes) -> tuple[float, Vec]:
    """How far past a cut ``q`` lies (positive: dropped) and that value's
    gradient: the plane's signed distance, or with a corner the distance
    from the two half-spaces' intersection with its corner rounded."""
    c, n, corner = planes
    a = _dot(_sub(q, c), n)
    if corner is None:
        return a, n
    c2, n2, r = corner
    b = _dot(_sub(q, c2), n2)
    if a + r > 0.0 and b + r > 0.0:
        length = math.sqrt((a + r) * (a + r) + (b + r) * (b + r))
        return length - r, tuple(((a + r) * n[j] + (b + r) * n2[j]) / length for j in range(3))
    return (a, n) if a >= b else (b, n2)


def _snap(mesh: _Mesh, spec: MeshSpec, final: list[Vec]) -> int:
    """Each ``snap`` cut's edge points onto its surface in ``final`` (in
    place; two Newton steps along the value's gradient): how many moved."""
    edges = dict(mesh.cuts)
    moved = 0
    for i, op in enumerate(spec.ops):
        if not isinstance(op, CutOp) or not op.snap or i not in edges:
            continue
        planes = _cut_planes(mesh, op)
        for k in edges[i]:
            q = final[k]
            for _ in range(2):
                d, g = _cut_value(q, planes)
                gg = _dot(g, g)
                if not gg > 0.0:
                    break
                q = tuple(q[j] - d * g[j] / gg for j in range(3))
            if q != final[k]:
                final[k] = q
                moved += 1
    return moved


def _cut(mesh: _Mesh, spec: MeshSpec, base: list[Vec]) -> tuple[_Mesh, list[Vec]]:
    """``mesh`` with each ``cut`` op (:class:`CutOp`) made: in the shape
    the fields and rounds give (:func:`_approx_finals`), its layer's
    triangles in its region past its plane dropped and those the plane
    crosses cut at it (a crossing per welded edge, each copy of it its own
    vertex on the edge's pair, its UV, weights and normal blended as a
    subdivision's; a quad left after the cut split in two), and with
    ``trim`` a cord along each run of the new edge.  Its new vertices at
    the end of their groups."""
    cuts = [(i, op) for i, op in enumerate(spec.ops) if isinstance(op, CutOp)]
    if not cuts:
        return mesh, base
    names = list(mesh.names)
    ids, keys, pos, nrm, uvs = list(mesh.ids), list(mesh.keys), list(mesh.positions), list(mesh.normals), list(mesh.uvs)
    skins, heavy, basep = list(mesh.skins), list(mesh.heaviest), list(base)
    counts = {g.index: g.count for g in mesh.groups}
    tris = list(mesh.triangles)
    corners = list(mesh.corners) if mesh.corners else None
    fixed = set(mesh.fixed)
    group_of = [g for g, _ in mesh.ids]
    made_cuts, made_trims, made_splines = list(mesh.cuts), list(mesh.trims), list(mesh.splines)
    kept = _subtree(mesh, set(spec.keep))
    for i, op in cuts:
        if op.bone not in names:
            raise ValueError(f"mesh.ops[{i}].bone: {mesh.body} has no bone {op.bone!r}")
        indices = {g.index for g in mesh.groups}
        for g in (*op.groups, *op.under):
            if g not in indices:
                raise ValueError(f"mesh.ops[{i}]: {mesh.body} has no LOD-0 group {g}")
        n = _unit(op.normal)
        if n is None or not all(r > 0 for r in op.radius):
            raise ValueError(f"mesh.ops[{i}]: a cut's normal isn't zero and its radius is above 0")
        if op.corner is not None and (_unit(op.corner[0]) is None or not op.corner[2] > 0.0):
            raise ValueError(f"mesh.ops[{i}].corner: its normal isn't zero and its radius is above 0")
        o = mesh.origins[names.index(op.bone)]
        c = (o[0] + op.offset[0], o[1] + op.offset[1], o[2] + op.offset[2])
        planes = _cut_planes(mesh, op)
        bones = frozenset(_subtree(mesh, set(op.only))) if op.only else None

        def picks(k: int) -> bool:
            h = heavy[k]
            if op.uv is not None and not (op.uv[0] <= uvs[k][0] <= op.uv[2] and op.uv[1] <= uvs[k][1] <= op.uv[3]):
                return False
            return group_of[k] in op.groups and ((h in bones) if bones is not None else h not in kept)
        layer = [t for t, tri in enumerate(tris) if all(picks(v) for v in tri)]
        approx = _approx_finals(replace(mesh, ids=tuple(ids), keys=tuple(keys), positions=tuple(pos),
                                        normals=tuple(nrm), uvs=tuple(uvs), skins=tuple(skins), heaviest=tuple(heavy),
                                        triangles=tuple(tris), fixed=frozenset(fixed)), spec, basep,
                                sorted({v for t in layer for v in tris[t]}))

        def side(k: int) -> float:
            return _cut_value(approx[k], planes)[0]

        def inside(t: int) -> bool:
            q = [sum(approx[v][j] for v in tris[t]) / 3.0 for j in range(3)]
            return sum(fdlibm.sq((q[j] - c[j]) / op.radius[j]) for j in range(3)) < 1.0
        wid: dict[bytes, int] = {}          # each welded point of the layer: its first vertex there
        for k in sorted(approx):
            wid.setdefault(keys[k], k)
        crossing: dict[tuple[int, int], tuple[float, int]] = {}      # welded edge -> (t from its lower end, point no.)
        copies: dict[tuple[int, int], int] = {}
        edge_pts: list[int] = []
        new_tris: dict[int, list[tuple[int, int, int]]] = {}
        run: dict[tuple, set[tuple]] = {}                             # edge point -> its neighbours on the new edge
        point_of: dict[int, tuple] = {}

        def cross(a: int, b: int) -> int:
            """The vertex where the plane crosses the edge a-b (a kept, b past it): a itself when it lies on the
            plane, else a new one (a's copy pair's own)."""
            if abs(side(a)) <= CUT_SNAP:
                point_of[a] = ("v", wid[keys[a]])
                if a not in edge_pts:
                    edge_pts.append(a)
                return a
            wa, wb = wid[keys[a]], wid[keys[b]]
            e = (min(wa, wb), max(wa, wb))
            if e not in crossing:
                sa, sb = side(e[0]), side(e[1])
                crossing[e] = (sa / (sa - sb), len(crossing))
            t, pno = crossing[e]
            lo, hi = (a, b) if wid[keys[a]] == e[0] else (b, a)
            key = (min(a, b), max(a, b))
            m = copies.get(key)
            if m is not None:
                return m
            g = group_of[a]
            skin: dict[int, float] = {}
            for v, w in ((lo, 1.0 - t), (hi, t)):
                for bone, x in skins[v].items():
                    skin[bone] = skin.get(bone, 0.0) + w * x
            top = sorted(skin.items(), key=lambda bw: (-bw[1], bw[0]))[:4]
            total = sum(w for _, w in top)
            n0, n1 = _unit(nrm[lo]) or (0.0, 0.0, 1.0), _unit(nrm[hi]) or (0.0, 0.0, 1.0)
            m = len(ids)
            ids.append((g, counts[g]))
            counts[g] += 1
            keys.append(b"C" + struct.pack("<II", i, pno))
            q = _f32(tuple(basep[lo][j] + t * (basep[hi][j] - basep[lo][j]) for j in range(3)))
            pos.append(q)
            basep.append(q)
            nrm.append(_unit(tuple((1.0 - t) * n0[j] + t * n1[j] for j in range(3))) or n0)
            uvs.append(tuple(uvs[lo][j] + t * (uvs[hi][j] - uvs[lo][j]) for j in range(2)))
            skins.append({bone: w / total for bone, w in top})
            heavy.append(top[0][0])
            group_of.append(g)
            approx[m] = tuple(approx[lo][j] + t * (approx[hi][j] - approx[lo][j]) for j in range(3))
            copies[key] = m
            point_of[m] = ("e", pno)
            edge_pts.append(m)
            return m
        drop = set()
        for t in layer:
            if not inside(t):
                continue
            tri = tris[t]
            far = [side(v) > CUT_SNAP for v in tri]
            if not any(far):
                continue
            drop.add(t)
            if all(far):
                continue
            k = far.index(True) if far.count(True) == 1 else far.index(False)
            a, b, cc = tri[k:] + tri[:k]           # the odd corner first, the winding kept
            if far.count(True) == 1:              # a past it: the quad b, c and the crossings
                pab, pca = cross(b, a), cross(cc, a)
                ring = [pab, b, cc, pca]
            else:                                 # b and c past it: a and the crossings
                pab, pca = cross(a, b), cross(a, cc)
                ring = [a, pab, pca]
            ring = [v for j, v in enumerate(ring) if v != ring[j - 1]]
            new_tris[t] = [(ring[0], ring[j], ring[j + 1]) for j in range(1, len(ring) - 1)] if len(ring) >= 3 else []
            x, y = point_of[pab], point_of[pca]
            if x != y:
                run.setdefault(x, set()).add(y)
                run.setdefault(y, set()).add(x)
        if not drop:
            raise ValueError(f"mesh.ops[{i}]: the cut {op.name or ''} crosses none of its layer's triangles")
        out_tris, out_corners = [], []
        for t, tri in enumerate(tris):
            if t not in drop:
                out_tris.append(tri)
                if corners is not None:
                    out_corners.append(corners[t])
                continue
            for nt in new_tris.get(t, ()):
                out_tris.append(nt)
                if corners is not None:     # an island's source UVs: each corner's own (the cut's blended)
                    out_corners.append(tuple(uvs[v] for v in nt))
        tris = out_tris
        if corners is not None:
            corners = out_corners
        first = {}
        for m in edge_pts:
            first.setdefault(point_of[m], m)
        made_cuts.append((i, tuple(sorted(edge_pts))))
        if op.trim is None:
            continue
        radius, flat, sides, rect = op.trim
        ring = _circle(sides)
        po = op.press[4] if op.press is not None else (0.0, 0.0, 0.0)
        out_o = (o[0] + po[0], o[1] + po[1], o[2] + po[2])
        chains: list[tuple[list[Vec], list[int], tuple[int, ...] | None]] = []
        if op.snap:         # one cord: every edge point in a chain, nearest after nearest, resampled evenly
            line = _unit(_cross(n, (0.0, 1.0, 0.0))) or _unit(_cross(n, (1.0, 0.0, 0.0))) or (1.0, 0.0, 0.0)
            left = sorted({first[x] for x in first}, key=lambda k_: (_dot(approx[k_], line), k_))
            chain_v = [left.pop(0)]
            while left:
                here = approx[chain_v[-1]]
                j_ = min(range(len(left)), key=lambda q_: (_norm(_sub(approx[left[q_]], here)), left[q_]))
                chain_v.append(left.pop(j_))
            if len(chain_v) >= 2:
                cpts = [approx[k_] for k_ in chain_v]
                arc = [0.0]
                for a_, b_ in zip(cpts, cpts[1:]):
                    arc.append(arc[-1] + _norm(_sub(b_, a_)))
                count = max(2, math.ceil(arc[-1] / CORD_STEP) + 1)
                pts, srcs = [], []
                for r_i in range(count):
                    at = arc[-1] * r_i / (count - 1)
                    j_ = max(0, min(len(cpts) - 2, next((q_ for q_ in range(len(arc) - 1) if arc[q_ + 1] >= at),
                                                        len(arc) - 2)))
                    f_ = (at - arc[j_]) / ((arc[j_ + 1] - arc[j_]) or 1.0)
                    pts.append(tuple(cpts[j_][q] + f_ * (cpts[j_ + 1][q] - cpts[j_][q]) for q in range(3)))
                    srcs.append(chain_v[j_] if f_ < 0.5 else chain_v[j_ + 1])
                chains.append((pts, srcs, tuple(chain_v)))
        else:
            seen: set[int] = set()
            for start in sorted(run):
                if start in seen or (len(run[start]) == 2 and any(len(run[x]) != 2 for x in run)):
                    continue
                chain = [start]
                seen.add(start)
                while True:
                    nxt = sorted(x for x in run[chain[-1]] if x not in seen)
                    if not nxt:
                        break
                    chain.append(nxt[0])
                    seen.add(nxt[0])
                if len(chain) >= 2:
                    chains.append(([approx[first[x]] for x in chain], [first[x] for x in chain], None))
        for pts, srcs, spline in chains:
            length = [0.0]
            for a_, b_ in zip(pts, pts[1:]):
                length.append(length[-1] + _norm(_sub(b_, a_)))
            total = length[-1] or 1.0
            u0, v0, u1, v1 = rect
            grid = []
            for r_i, p in enumerate(pts):
                tan = _unit(_sub(pts[min(r_i + 1, len(pts) - 1)], pts[max(r_i - 1, 0)])) or (0.0, 0.0, 1.0)
                out_d = _unit(_sub(p, out_o)) or n
                out_d = _unit(_sub(out_d, tuple(_dot(out_d, tan) * x for x in tan))) or n
                acr = _cross(tan, out_d)
                src = srcs[r_i]
                row = []
                for c_i in range(sides + 1):
                    cx, cy = ring[c_i % sides]
                    nn = tuple(cx * acr[j] + cy * out_d[j] for j in range(3))
                    q = tuple(p[j] + radius * cx * acr[j] + radius * flat * cy * out_d[j] for j in range(3))
                    k = len(ids)
                    g = group_of[src]
                    ids.append((g, counts[g]))
                    counts[g] += 1
                    keys.append(b"R" + struct.pack("<I", k))
                    q = _f32(q)
                    pos.append(q)
                    basep.append(q)
                    nrm.append(nn)
                    uvs.append((u0 + (u1 - u0) * c_i / sides, v0 + (v1 - v0) * length[r_i] / total))
                    skins.append(dict(skins[src]))
                    heavy.append(heavy[src])
                    group_of.append(g)
                    fixed.add(k)
                    made_trims.append((k, src, _sub(q, approx[src])))
                    row.append(k)
                grid.append(row)
            new, caps = [], []
            for r_i in range(len(grid) - 1):
                a_, b_ = grid[r_i], grid[r_i + 1]
                for c_i in range(sides):
                    new += [(a_[c_i], b_[c_i], a_[c_i + 1]), (a_[c_i + 1], b_[c_i], b_[c_i + 1])]
            for end, nb in ((0, 1), (len(grid) - 1, len(grid) - 2)):     # each end capped with a fan
                centre = tuple(sum(pos[k][j] for k in grid[end][:sides]) / sides for j in range(3))
                inner = tuple(sum(pos[k][j] for k in grid[nb][:sides]) / sides for j in range(3))
                way = _unit(_sub(centre, inner)) or n
                k = len(ids)
                src = grid[end][0]
                g = group_of[src]
                ids.append((g, counts[g]))
                counts[g] += 1
                keys.append(b"R" + struct.pack("<I", k))
                q = _f32(tuple(centre[j] + 0.5 * radius * way[j] for j in range(3)))
                pos.append(q)
                basep.append(q)
                nrm.append(_unit(_sub(q, centre)) or n)
                uvs.append(((u0 + u1) / 2.0, v0 if end == 0 else v1))
                s_ = made_trims[[x[0] for x in made_trims].index(src)][1]
                skins.append(dict(skins[s_]))
                heavy.append(heavy[s_])
                group_of.append(g)
                fixed.add(k)
                made_trims.append((k, s_, _sub(q, approx[s_])))
                caps.append(k)
                for c_i in range(sides):
                    new.append((grid[end][c_i], k, grid[end][c_i + 1]))
            if spline is not None:      # laid again where the snapped edge lies (_ride)
                made_splines.append((i, spline, tuple(tuple(row) for row in grid), tuple(caps), radius, flat, sides,
                                     out_o, op.foot))
            fixed_tris = []
            for t in new:       # each face looking out of the cord (away from its run)
                f = _face(pos, t)
                cen = tuple(sum(pos[v][j] for v in t) / 3.0 for j in range(3))
                near = min(range(len(pts)), key=lambda q_: _norm(_sub(pts[q_], cen)))
                fixed_tris.append(t if _dot(f, _sub(cen, pts[near])) >= 0.0 else (t[0], t[2], t[1]))
            tris.extend(fixed_tris)
            if corners is not None:
                corners.extend(tuple(uvs[v] for v in t) for t in fixed_tris)
    groups = tuple(replace(g, count=counts[g.index]) for g in mesh.groups)
    out = replace(mesh, groups=groups, ids=tuple(ids), keys=tuple(keys), positions=tuple(pos), normals=tuple(nrm),
                  uvs=tuple(uvs), skins=tuple(skins), heaviest=tuple(heavy), triangles=tuple(tris),
                  corners=tuple(corners) if corners is not None else (), fixed=frozenset(fixed),
                  cuts=tuple(made_cuts), trims=tuple(made_trims), splines=tuple(made_splines))
    return out, basep


def _two_sided(mesh: _Mesh, spec: MeshSpec, base: list[Vec]) -> list[tuple[ThickenOp, list, dict, dict]]:
    """Each ``thicken`` op's layer at ``base`` (Step 2.177d): the op, its
    triangles (those of no area at ``base`` left out: its rims), for each
    point of the layer two sides share, each copy's (position, side): the
    copies there split by whether their faces look the first copy's way
    (W-3: the op's bones and groups the body's, a radius and depth above
    0), and each such copy's share of the depth (Step 2.187: 1, or with a
    ``taper`` the smoothstep of its distance to the nearest point of the
    layer a triangle outside it shares, over the taper)."""
    if not any(isinstance(op, ThickenOp) for op in spec.ops):
        return []
    regions = _regions(mesh, spec, ThickenOp)
    out, at = [], 0
    for i, op in enumerate(spec.ops):
        if not isinstance(op, ThickenOp):
            continue
        if not op.depth > 0:
            raise ValueError(f"mesh.ops[{i}].depth: {op.depth:g} must be above 0")
        if not op.taper >= 0:
            raise ValueError(f"mesh.ops[{i}].taper: {op.taper:g} must be 0 or above")
        mine = regions[at:at + (2 if op.mirror else 1)]
        at += len(mine)
        tris, fan = [], {}
        for t in mesh.triangles:
            centre = tuple((base[t[0]][c] + base[t[1]][c] + base[t[2]][c]) / 3.0 for c in range(3))
            if not any(r.holds(centre) and all(r.selects(mesh.heaviest[v], mesh.ids[v][0]) for v in t) for r in mine):
                continue
            f = _face(base, t)
            if f == (0.0, 0.0, 0.0):
                continue
            tris.append(t)
            for v in t:
                g = fan.get(v, (0.0, 0.0, 0.0))
                fan[v] = (g[0] + f[0], g[1] + f[1], g[2] + f[2])
        copies: dict[Vec, list[int]] = {}
        for v in sorted(fan):
            copies.setdefault(base[v], []).append(v)
        side = {}
        for q, ks in copies.items():
            first = fan[ks[0]]
            got = {k: 0 if _dot(fan[k], first) >= 0.0 else 1 for k in ks}
            if len(set(got.values())) == 2:
                side.update({k: (q, s) for k, s in got.items()})
        share = dict.fromkeys(side, 1.0)
        if op.taper > 0.0:
            mine_t = set(tris)
            edge = sorted({base[v] for t in mesh.triangles if t not in mine_t for v in t if base[v] in copies
                           and _face(base, t) != (0.0, 0.0, 0.0)})
            for v, (q, _s) in side.items():
                if edge:
                    s = min(min(_norm(_sub(q, e)) for e in edge) / op.taper, 1.0)
                    share[v] = s * s * (3.0 - 2.0 * s)
        out.append((op, tris, side, share))
    return out


def _rims(mesh: _Mesh, spec: MeshSpec, base: list[Vec]) -> _Mesh:
    """``mesh`` with each ``thicken`` op's rims (Step 2.177d): every edge
    of its layer the two sides leave open together (one face a side, its
    copies on opposite sides) joined by two triangles, (a, a', b') and
    (a, b', b) for a face's edge a -> b, which face out of the layer once
    each side moves along its own normal (:func:`_thicken`); with a taper
    (Step 2.187) none where neither end moves, and only the one of area
    where one end doesn't."""
    new = []
    for _op, tris, side, share in _two_sided(mesh, spec, base):
        edges: dict[tuple[Vec, Vec], list[tuple[int, int]]] = {}
        for t in tris:
            for u, v in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                if u in side and v in side:
                    pu, pv = base[u], base[v]
                    edges.setdefault((pu, pv) if pu <= pv else (pv, pu), []).append((u, v))
        for got in edges.values():
            if len(got) != 2:
                continue
            (a, b), (b2, a2) = got
            if base[a2] != base[a] or side[a][1] == side[a2][1] or side[b][1] == side[b2][1]:
                continue
            if share[a] > 0.0:          # (a, a', b') has no area where a's two copies stay together
                new.append((a, a2, b2))
            if share[b] > 0.0:          # nor (a, b', b) where b's do
                new.append((a, b2, b))
    if not new:
        return mesh
    corners = mesh.corners + tuple(tuple(mesh.uvs[v] for v in t) for t in new) if mesh.corners else ()
    return replace(mesh, triangles=mesh.triangles + tuple(new), corners=corners)


def _thicken(mesh: _Mesh, spec: MeshSpec, base: list[Vec], final: list[Vec]) -> None:
    """Each ``thicken`` op's two sides moved ``depth`` apart (Step 2.177d,
    in place, last of the position steps): every copy of a point by half of
    it along its side's normal there in the final shape (the area-weighted
    normal of the faces of all its copies on that side, so a seam's copies
    stay together), times its share (Step 2.187: a taper's)."""
    for op, tris, side, share in _two_sided(mesh, spec, base):
        fan: dict[tuple[Vec, int], Vec] = {}
        for t in tris:
            f = _face(final, t)
            for v in t:
                if v in side:
                    g = fan.get(side[v], (0.0, 0.0, 0.0))
                    fan[side[v]] = (g[0] + f[0], g[1] + f[1], g[2] + f[2])
        moved = {}
        for v in sorted(side):
            n = _unit(fan.get(side[v], (0.0, 0.0, 0.0)))
            if n is not None and share[v] > 0.0:
                h = op.depth / 2.0 * share[v]
                moved[v] = (final[v][0] + h * n[0], final[v][1] + h * n[1], final[v][2] + h * n[2])
        for v, q in moved.items():
            final[v] = q


def _tube_weights(mesh: _Mesh, spec: MeshSpec, final: list[Vec], bound: dict[int, dict[int, float]]
                  ) -> dict[int, dict[int, float]]:
    """Each ``tube`` with ``reach``: its vertices' weights the mix of every
    ``follow`` vertex's within its ``reach`` of it in ``final`` (their bound
    weights where a ``bind`` gave some) by ``(1 - d^2 / reach^2)^2``, the
    nearest alone where none is; by vertex."""
    out: dict[int, dict[int, float]] = {}
    group_of = [g for g, _ in mesh.ids]
    for i, made, reach_of in mesh.tubes:
        op = spec.ops[i]
        cell = max(max(reach_of), BIND_CELL)
        grid: dict[tuple[int, int, int], list[int]] = {}
        own = set(made)
        for k in range(len(final)):
            if group_of[k] in op.follow and k not in mesh.fixed and k not in own:
                grid.setdefault(tuple(math.floor(final[k][c] / cell) for c in range(3)), []).append(k)
        about: dict[tuple, tuple] = {}   # (cell, span): the follow vertices of the cells about it (Step 2.179)

        def around(ci: tuple[int, int, int], span: int) -> tuple:
            got = about.get((ci, span))
            if got is None:
                js = [j for a in range(-span, span + 1) for b in range(-span, span + 1) for c in range(-span, span + 1)
                      for j in grid.get((ci[0] + a, ci[1] + b, ci[2] + c), ())]
                at = np.array([final[j] for j in js], dtype=np.float64).reshape(-1, 3)
                got = about[ci, span] = (np.array(js, dtype=np.int64), at[:, 0].copy(), at[:, 1].copy(), at[:, 2].copy())
            return got
        for k, reach in zip(made, reach_of):
            r2 = reach * reach
            q = final[k]
            ci = tuple(math.floor(q[c] / cell) for c in range(3))
            near, best, span = [], None, 1
            while not near and span <= 8:   # the loop's sums of squares, as numpy's same products and sums
                js, x, y, z = around(ci, span)
                if len(js):
                    ux, uy, uz = x - q[0], y - q[1], z - q[2]
                    d = ux * ux + uy * uy + uz * uz
                    inside = d < r2
                    if inside.any():   # Python's float power, as the loop's (libm's pow, not numpy's square)
                        near = list(zip(js[inside].tolist(), map(fdlibm.pow, (1.0 - d[inside] / r2).tolist(),
                                                                 itertools.repeat(2.0))))
                    least = d.min()
                    nearest = (float(least), int(js[d == least].min()))
                    if best is None or nearest < best:
                        best = nearest
                span *= 2
            if not near and best is not None:
                near = [(best[1], 1.0)]
            got: dict[int, float] = {}
            total = 0.0
            for j, w in sorted(near):
                total += w
                for bone, x in (bound.get(j) or mesh.skins[j]).items():
                    got[bone] = got.get(bone, 0.0) + w * x
            if total > 0.0:
                out[k] = {bone: x / total for bone, x in sorted(got.items())}
        if max(_along_path(op, op.under)) > 0.0:
            out.update(_undered(mesh, op, made, final, out, bound))
        if op.skip:   # a bone's weight to its nearest ancestor not skipped (Step 2.154b)
            skip = {mesh.names.index(n) for n in op.skip}
            for k in (k for k in made if k in out):
                kept: dict[int, float] = {}
                for bone, x in out[k].items():
                    while bone in skip:
                        bone = mesh.parents[bone]
                    kept[bone] = kept.get(bone, 0.0) + x
                out[k] = dict(sorted(kept.items()))
        if max(_along_path(op, op.smooth)) > 0.0:
            out.update(_smoothed(op, made, final, out))
    return out


def _ring_share(op: TubeOp, value, r: int) -> float:
    """A per-path-point field at ring ``r`` of ``op``, interpolated as its reach."""
    v, n, count = _along_path(op, value), len(op.path), op.rings
    f = (r / count) * n if op.closed else (r / (count - 1)) * (n - 1)
    j = min(int(f), n - (1 if not op.closed else 0) - 1)
    return v[j % n] + (f - j) * (v[(j + 1) % n] - v[j % n])


def _closest_on_triangles(q: np.ndarray, A: np.ndarray, B: np.ndarray, C: np.ndarray
                          ) -> tuple[np.ndarray, np.ndarray]:
    """Each triangle's point nearest ``q`` (Ericson's regions): its squared
    distance and its barycentric coordinates (n x 3)."""
    ab, ac, ap = B - A, C - A, q - A
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = q - B
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = q - C
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    with np.errstate(divide="ignore", invalid="ignore"):
        den = va + vb + vc
        v_in, w_in = vb / den, vc / den
        bary = np.stack([1.0 - v_in - w_in, v_in, w_in], 1)
        e_bc = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        e_ac = d2 / (d2 - d6)
        e_ab = d1 / (d1 - d3)
    for mask, row in (((va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0), np.stack([0 * e_bc, 1 - e_bc, e_bc], 1)),
                      ((vb <= 0) & (d2 >= 0) & (d6 <= 0), np.stack([1 - e_ac, 0 * e_ac, e_ac], 1)),
                      ((d6 >= 0) & (d5 <= d6), np.tile([0.0, 0.0, 1.0], (len(A), 1))),
                      ((vc <= 0) & (d1 >= 0) & (d3 <= 0), np.stack([1 - e_ab, e_ab, 0 * e_ab], 1)),
                      ((d3 >= 0) & (d4 <= d3), np.tile([0.0, 1.0, 0.0], (len(A), 1))),
                      ((d1 <= 0) & (d2 <= 0), np.tile([1.0, 0.0, 0.0], (len(A), 1)))):
        bary[mask] = row[mask]
    bary = np.where(np.isfinite(bary).all(1)[:, None], bary, np.array([1.0, 0.0, 0.0]))
    p = bary[:, :1] * A + bary[:, 1:2] * B + bary[:, 2:] * C
    return (fdlibm.sq(p - q)).sum(1), bary


def _undered(mesh: _Mesh, op: TubeOp, made: tuple[int, ...], final: list[Vec], got: dict[int, dict[int, float]],
             bound: dict[int, dict[int, float]]) -> dict[int, dict[int, float]]:
    """A ``tube``'s reach weights ``got`` with each ring's ``under`` share
    (:class:`TubeOp`) the weights of the ``follow`` groups' final surface at
    the point of their triangles nearest the ring's centre, by its
    barycentric coordinates (the nearest within 5 cm of a triangle's
    centroid, else of them all)."""
    group_of = [g for g, _ in mesh.ids]
    tris = np.array([t for t in mesh.triangles if all(group_of[v] in op.follow and v not in mesh.fixed for v in t)],
                    np.int64).reshape(-1, 3)
    F = np.asarray(final, float)
    A, B, C = F[tris[:, 0]], F[tris[:, 1]], F[tris[:, 2]]
    cen = (A + B + C) / 3.0
    width, count = op.sides + 1, op.rings
    out: dict[int, dict[int, float]] = {}
    for r in range(count):
        u = _ring_share(op, op.under, r)
        if u <= 0.0 or not len(tris):
            continue
        ring = list(made[r * width:(r + 1) * width])
        if r == count - 1 and not op.closed:
            ring += list(made[count * width:])
        q = F[ring[:width]].mean(0)
        near = np.where((fdlibm.sq(cen - q)).sum(1) < fdlibm.sq(0.05))[0]
        if not len(near):
            near = np.arange(len(tris))
        d2, bary = _closest_on_triangles(q, A[near], B[near], C[near])
        best = int(np.argmin(d2))
        surface: dict[int, float] = {}
        for v, x in zip(tris[near[best]], bary[best]):
            for bone, w in (bound.get(int(v)) or mesh.skins[int(v)]).items():
                surface[bone] = surface.get(bone, 0.0) + float(x) * w
        for k in ring:
            mix = {bone: (1.0 - u) * x for bone, x in got[k].items()}
            for bone, x in surface.items():
                mix[bone] = mix.get(bone, 0.0) + u * x
            total = sum(mix.values())
            out[k] = {bone: x / total for bone, x in sorted(mix.items()) if x > 0.0}
    return out


def _along_path(op: TubeOp, value) -> tuple[float, ...]:
    """A tube field given once or one a path point, one a path point."""
    return value if isinstance(value, tuple) else (value,) * len(op.path)


def _smoothed(op: TubeOp, made: tuple[int, ...], final: list[Vec], got: dict[int, dict[int, float]]
              ) -> dict[int, dict[int, float]]:
    """A ``tube``'s reach weights ``got`` low-passed along it by its
    ``smooth`` (:class:`TubeOp`): each ring's mean weights mixed by a
    Gaussian of the ring's sigma over the distance between ring centres in
    ``final`` (a loop's the shorter way round, out to 3 sigma), every
    point of the ring (and an open tube's tip, its last ring's) given the
    mix; a ring at sigma 0 keeps its points' own."""
    width, count = op.sides + 1, op.rings
    rings = [made[r * width:(r + 1) * width] for r in range(count)]
    centre = [tuple(sum(final[k][c] for k in ring) / len(ring) for c in range(3)) for ring in rings]
    at = [0.0]
    for a, b in zip(centre, centre[1:]):
        at.append(at[-1] + _norm(_sub(b, a)))
    loop = at[-1] + _norm(_sub(centre[0], centre[-1]))
    mean = []
    for ring in rings:
        m: dict[int, float] = {}
        for k in ring:
            for bone, x in got[k].items():
                m[bone] = m.get(bone, 0.0) + x / len(ring)
        mean.append(m)
    out: dict[int, dict[int, float]] = {}
    for r, ring in enumerate(rings):
        s = _ring_share(op, op.smooth, r)
        if s <= 0.0:
            continue
        mix: dict[int, float] = {}
        total = 0.0
        for q in range(count):
            d = abs(at[q] - at[r])
            if op.closed:
                d = min(d, loop - d)
            if d > 3.0 * s:
                continue
            g = fdlibm.exp(-0.5 * fdlibm.sq(d / s))
            total += g
            for bone, x in mean[q].items():
                mix[bone] = mix.get(bone, 0.0) + g * x
        each = {bone: x / total for bone, x in sorted(mix.items())}
        for k in ring:
            out[k] = dict(each)
        if r == count - 1 and not op.closed:
            for k in made[count * width:]:
                out[k] = dict(each)
    return out


def _press(mesh: _Mesh, spec: MeshSpec, final: list[Vec]) -> int:
    """Each ``cut``'s ``press`` (:class:`CutOp`) on ``final`` in place, then
    its trim set on its edge: how many vertices moved."""
    group_of = [g for g, _ in mesh.ids]
    edges = dict(mesh.cuts)
    moved = 0
    for i, op in enumerate(spec.ops):
        if not isinstance(op, CutOp) or op.press is None or i not in edges:
            continue
        depth, width, swell, thick, po = op.press
        o = mesh.origins[mesh.names.index(op.bone)]
        c = (o[0] + op.offset[0], o[1] + op.offset[1], o[2] + op.offset[2])
        centre = (o[0] + po[0], o[1] + po[1], o[2] + po[2])
        n = _unit(op.normal)
        pts = sorted({_f32(final[k]) for k in edges[i]})
        cell = width
        grid: dict[tuple[int, int, int], list[Vec]] = {}
        for q in pts:
            grid.setdefault(tuple(math.floor(q[j] / cell) for j in range(3)), []).append(q)
        trims = {k for k, _, _ in mesh.trims}
        cloth = [k for k in range(len(final)) if group_of[k] in op.groups and k not in trims]
        skin = [k for k in range(len(final)) if group_of[k] in op.under]
        reach = width + width / 4.0 + (width if swell > 0.0 else 0.0)

        span = math.ceil(reach / cell)
        around: dict[tuple[int, int, int], np.ndarray] = {}   # a cell: its neighbourhood's edge points (Step 2.179)

        def near(q: Vec) -> float | None:
            ci = tuple(math.floor(q[j] / cell) for j in range(3))
            es = around.get(ci)
            if es is None:
                es = around[ci] = np.array([e for a in range(-span, span + 1) for b in range(-span, span + 1)
                                            for cc in range(-span, span + 1)
                                            for e in grid.get((ci[0] + a, ci[1] + b, ci[2] + cc), ())],
                                           dtype=np.float64).reshape(-1, 3)
            if not len(es):
                return None
            dx, dy, dz = q[0] - es[:, 0], q[1] - es[:, 1], q[2] - es[:, 2]
            best = float(np.sqrt(dx * dx + dy * dy + dz * dz).min())     # _norm's: sqrt is correctly rounded
            return best if best < reach else None
        # the cloth's gap over its skin: along its way to the origin, to the skin's nearest face
        sgrid: dict[tuple[int, int, int], list[int]] = {}
        under = set(op.under)
        faces = []
        for tri in mesh.triangles:
            if all(group_of[v] in under for v in tri):
                cen = tuple(sum(final[v][j] for v in tri) / 3.0 for j in range(3))
                sgrid.setdefault(tuple(math.floor(cen[j] / BIND_CELL) for j in range(3)), []).append(len(faces))
                faces.append([final[v] for v in tri])
        # each skin face's first corner and edges, a cell's 27 cells' faces read at once (Step 2.179): the loop's
        # floats, numpy's same products and sums (no vertex moves before every gap is measured)
        corners = np.array(faces, dtype=np.float64).reshape(-1, 3, 3)
        table = np.concatenate((corners[:, 0], corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
        about: dict[tuple[int, int, int], np.ndarray] = {}

        def gap_of(q: Vec, u: Vec) -> float | None:
            ci = tuple(math.floor(q[j] / BIND_CELL) for j in range(3))
            got = about.get(ci)
            if got is None:
                got = about[ci] = table[[t for a in (-1, 0, 1) for b in (-1, 0, 1) for cc in (-1, 0, 1)
                                         for t in sgrid.get((ci[0] + a, ci[1] + b, ci[2] + cc), ())]]
            if not len(got):
                return None
            o1, o2, o3, a1, a2, a3, b1, b2, b3 = got.T
            p1, p2, p3 = u[1] * b3 - u[2] * b2, u[2] * b1 - u[0] * b3, u[0] * b2 - u[1] * b1
            det = a1 * p1 + a2 * p2 + a3 * p3
            t1, t2, t3 = q[0] - o1, q[1] - o2, q[2] - o3
            q1, q2, q3 = t2 * a3 - t3 * a2, t3 * a1 - t1 * a3, t1 * a2 - t2 * a1
            with np.errstate(divide="ignore", invalid="ignore"):
                x = (t1 * p1 + t2 * p2 + t3 * p3) / det
                y = (u[0] * q1 + u[1] * q2 + u[2] * q3) / det
                dist = (b1 * q1 + b2 * q2 + b3 * q3) / det
            hit = (np.abs(det) >= 1e-14) & (x >= 0.0) & (x <= 1.0) & (y >= 0.0) & (x + y <= 1.0) & (dist >= 0.0)
            return float(dist[hit].min()) if hit.any() else None
        steps: dict[int, float] = {}
        for k in cloth:
            q = final[k]
            d = near(q)
            if d is None or not d < width:
                continue
            u = _unit(_sub(centre, q))
            gap = gap_of(q, u) if u is not None else None
            sink = depth + max((gap if gap is not None else thick) - thick, 0.0)
            steps[k] = sink * (1.0 - _smooth(d / width))
        for k in skin:
            q = final[k]
            if sum(fdlibm.sq((q[j] - c[j]) / op.radius[j]) for j in range(3)) >= 1.0:
                continue
            d = near(q)
            if d is None:
                continue
            if _dot(_sub(q, c), n) <= 0.0:          # under the cloth
                if d < width:
                    steps[k] = depth * (1.0 - _smooth(d / width))
            else:                                   # bare: rising back, then the swell
                rise = width / 4.0
                step = depth * (1.0 - _smooth(d / rise)) if d < rise else 0.0
                if swell > 0.0 and d < rise + width:
                    x = (d / (rise + width))
                    step -= swell * 4.0 * x * (1.0 - x)
                steps[k] = step
        for k, step in steps.items():
            if step == 0.0:
                continue
            to = _unit(_sub(centre, final[k]))
            if to is None:
                continue
            final[k] = tuple(final[k][j] + step * to[j] for j in range(3))
            moved += 1
    return moved


CORD_FOOT_EASE = 0.02
"""How far past a cut's ``foot`` its cord's lift eases out (model units)."""


def _ride(mesh: _Mesh, final: list[Vec], approx: dict[int, Vec] | None = None) -> None:
    """Each trim vertex on its edge vertex in ``final`` (in place): the
    edge's final position plus the vertex's offset from it; a snapped cut's
    one cord laid again along its edge where it lies: the chain smoothed
    :data:`CORD_SMOOTH` passes (its ends kept), its rings evenly along it,
    lifted at its foot by the cut's ``foot``."""
    for k, src, off in mesh.trims:
        final[k] = tuple(final[src][j] + off[j] for j in range(3))
    for _, chain, grid, caps, radius, flat, sides, out_o, foot in mesh.splines:
        cpts = [final[k] for k in chain]
        for _ in range(CORD_SMOOTH):
            cpts = [cpts[0]] + [tuple((cpts[q - 1][j] + 2.0 * cpts[q][j] + cpts[q + 1][j]) / 4.0 for j in range(3))
                                for q in range(1, len(cpts) - 1)] + [cpts[-1]]
        arc = [0.0]
        for a, b in zip(cpts, cpts[1:]):
            arc.append(arc[-1] + _norm(_sub(b, a)))
        pts, j = [], 0
        for r in range(len(grid)):
            at = arc[-1] * r / (len(grid) - 1)
            while j < len(arc) - 2 and arc[j + 1] < at:
                j += 1
            f = (at - arc[j]) / ((arc[j + 1] - arc[j]) or 1.0)
            pts.append(tuple(cpts[j][q] + f * (cpts[j + 1][q] - cpts[j][q]) for q in range(3)))
        ring = _circle(sides)

        def out_of(r: int) -> tuple[Vec, Vec]:
            tan = _unit(_sub(pts[min(r + 1, len(pts) - 1)], pts[max(r - 1, 0)])) or (0.0, 0.0, 1.0)
            out_d = _unit(_sub(pts[r], out_o)) or (0.0, 1.0, 0.0)
            return tan, _unit(_sub(out_d, tuple(_dot(out_d, tan) * x for x in tan))) or (0.0, 1.0, 0.0)
        if foot is not None:        # lifted off its edge at its lower end, easing to none along it
            low = 0 if pts[0][2] <= pts[-1][2] else len(pts) - 1
            lifted = []
            for r in range(len(pts)):
                lift = foot[1] * (1.0 - _smooth((arc[-1] * abs(r - low) / (len(grid) - 1) - foot[0]) / CORD_FOOT_EASE))
                out_d = out_of(r)[1]
                lifted.append(tuple(pts[r][q] + lift * out_d[q] for q in range(3)))
            pts = lifted
        for r, row in enumerate(grid):
            p = pts[r]
            tan, out_d = out_of(r)
            acr = _cross(tan, out_d)
            for c, k in enumerate(row):
                cx, cy = ring[c % sides]
                final[k] = tuple(p[q] + radius * cx * acr[q] + radius * flat * cy * out_d[q] for q in range(3))
        for end, nb, k in ((0, 1, caps[0]), (len(grid) - 1, len(grid) - 2, caps[1])):
            centre = tuple(sum(final[v][q] for v in grid[end][:sides]) / sides for q in range(3))
            inner = tuple(sum(final[v][q] for v in grid[nb][:sides]) / sides for q in range(3))
            way = _unit(_sub(centre, inner)) or (0.0, 0.0, 1.0)
            final[k] = tuple(centre[q] + 0.5 * radius * way[q] for q in range(3))


def _harmonic(tris: list[tuple[int, int, int]], final: list[Vec], uv: dict[int, tuple[float, float]],
              free: list[int]) -> None:
    """``uv`` of the ``free`` vertices (in place) the harmonic map of the
    triangles ``tris`` in the final shape: the cotangent Laplacian, solved
    by conjugate gradients from their current UVs, the other vertices of
    ``uv`` fixed."""
    at = {v: i for i, v in enumerate(free)}
    rows: list[dict[int, float]] = [{} for _ in free]
    diag = [0.0] * len(free)
    rhs = [[0.0, 0.0] for _ in free]
    for tri in tris:
        for i in range(3):      # the angle at tri[i] weighs the opposite edge
            o, a, b = tri[i], tri[(i + 1) % 3], tri[(i + 2) % 3]
            pa, pb = _sub(final[a], final[o]), _sub(final[b], final[o])
            cross = _norm(_cross(pa, pb))
            if not cross > 0.0:
                continue
            w = 0.5 * _dot(pa, pb) / cross
            for x, y in ((a, b), (b, a)):
                if x in at:
                    k = at[x]
                    diag[k] += w
                    if y in at:
                        rows[k][at[y]] = rows[k].get(at[y], 0.0) - w
                    else:
                        rhs[k][0] += w * uv[y][0]
                        rhs[k][1] += w * uv[y][1]
    packed = [sorted(r.items()) for r in rows]
    for c in range(2):
        x = _conjugate(packed, diag, [b[c] for b in rhs], [uv[v][c] for v in free])
        for k, v in enumerate(free):
            uv[v] = (x[k], uv[v][1]) if c == 0 else (uv[v][0], x[k])


def _conjugate(packed: list[list[tuple[int, float]]], diag: list[float], b: list[float], x: list[float]
               ) -> list[float]:
    """:func:`_harmonic`'s conjugate gradients on one axis from ``x``
    (Step X.65c, in numpy, the loop's answer to the bit): row ``k`` of
    ``A q`` is ``diag[k] * q[k] + sum(w * q[j] for j, w in packed[k])``,
    Python's ``sum`` (compensated, Neumaier's, since 3.12) taken term by
    term down the rows; the dot products are ``sum`` over their terms and
    the rest elementwise, each step as the loop rounds it."""
    n = len(x)
    width = max((len(row) for row in packed), default=0)
    cols, weights = np.zeros((n, width), np.intp), np.zeros((n, width))
    for k, row in enumerate(packed):
        if row:
            cols[k, :len(row)], weights[k, :len(row)] = zip(*row)
    count = np.array([len(row) for row in packed], np.intp)
    diag_ = np.array(diag, np.float64)

    def apply(q):
        terms = weights * q[cols]
        f = np.where(count > 0, 0.0 + terms[:, 0], 0.0) if width else np.zeros(n)   # sum's int 0 start
        comp = np.zeros(n)
        for t in range(1, width):
            on, e = count > t, terms[:, t]
            s = f + e
            comp = np.where(on, comp + np.where(np.abs(f) >= np.abs(e), (f - s) + e, (e - s) + f), comp)
            f = np.where(on, s, f)
        return diag_ * q + np.where((comp != 0.0) & np.isfinite(comp), f + comp, f)
    with np.errstate(all="ignore"):
        x = np.array(x, np.float64)
        r = np.array(b, np.float64) - apply(x)
        d = r.copy()
        rr = sum((r * r).tolist())
        stop = rr * UNWRAP_TOLERANCE
        for _ in range(UNWRAP_MAX):
            if not rr > stop or rr == 0.0:
                break
            ad = apply(d)
            dad = sum((d * ad).tolist())
            if not dad > 0.0:
                break
            alpha = rr / dad
            x = x + alpha * d
            r = r - alpha * ad
            rr2 = sum((r * r).tolist())
            beta = rr2 / rr
            rr = rr2
            d = r + beta * d
        return x.tolist()


ISLAND_MARGIN = 0.03
"""The share of an island's rect left round its ellipse (the texture's
padding: a mip level's texels don't reach past it)."""
# a circle by its quarter's sines (no transcendental function): 64 points, x = cos, y = sin, in turn
_RING = 64


def _ring_points() -> list[tuple[float, float]]:
    """:data:`_RING` points round the unit circle (cos, sin), from (1, 0)
    turning towards +y, by repeated rotation through a step whose cosine
    and sine come from halving the angle with square roots."""
    c, s = 0.0, 1.0                     # 90 degrees, halved four times: 5.625 degrees = 360 / 64
    for _ in range(4):
        c, s = math.sqrt((1.0 + c) / 2.0), None
        s = math.sqrt(max(0.0, 1.0 - c * c))
    out, x, y = [], 1.0, 0.0
    for _ in range(_RING):
        out.append((x, y))
        x, y = x * c - y * s, x * s + y * c
    return out


def _island_uvs(mesh: _Mesh, spec: MeshSpec, base: list[Vec], final: list[Vec]) -> dict[int, tuple[float, float]]:
    """Each island's UVs (its outer edge on its rect's ellipse by arc
    length in the final shape, starting at its highest point and running
    the way its triangles wind; inner edges free; the rest harmonic), by
    vertex."""
    sides = _island_sides(mesh, spec)
    if not sides:
        return {}
    island = _island_of(mesh, spec, base)
    ring = _ring_points()
    out: dict[int, tuple[float, float]] = {}
    for k, (r, rect, box) in enumerate(sides):
        tris = [t for t, i in zip(mesh.triangles, island) if i == k]
        if not tris:
            raise ValueError(f"mesh: island {r.label} holds no triangle")
        if box is not None:     # vanilla's layout, stretched from the box onto the rect (inside its margin)
            mu, mv = (rect[2] - rect[0]) * ISLAND_MARGIN / 2.0, (rect[3] - rect[1]) * ISLAND_MARGIN / 2.0
            su, sv = (rect[2] - rect[0] - 2.0 * mu) / (box[2] - box[0]), (rect[3] - rect[1] - 2.0 * mv) / (box[3] - box[1])
            for v in sorted({v for t in tris for v in t}):
                u0, v0 = mesh.uvs[v]
                out[v] = struct.unpack("<2f", struct.pack("<2f", rect[0] + mu + (u0 - box[0]) * su,
                                                          rect[1] + mv + (v0 - box[1]) * sv))
            continue
        # one surface across groups (round 9, D552: her right brow's triangles lie in two of her skin's groups, whose
        # vertices at one place are each group's own): the map is laid on one vertex a stored place, each takes its UV
        own: dict[bytes, int] = {}
        one = {v: own.setdefault(mesh.keys[v], v) for v in sorted({v for t in tris for v in t})}
        every = sorted(one)
        tris = [w for w in (tuple(one[v] for v in t) for t in tris) if len(set(w)) == 3]
        half: dict[tuple[int, int], int] = {}
        for a, b, c in tris:
            for x, y in ((a, b), (b, c), (c, a)):
                half[(x, y)] = half.get((x, y), 0) + 1
        nxt: dict[int, int] = {}
        for (x, y) in sorted(half):
            if (y, x) not in half:
                nxt[x] = y            # a boundary half-edge, in the triangles' winding
        loops, seen = [], set()
        for v0 in sorted(nxt):
            if v0 in seen:
                continue
            loop, v = [], v0
            while v not in seen and v in nxt:
                seen.add(v)
                loop.append(v)
                v = nxt[v]
            loops.append(loop)
        if not loops:
            raise ValueError(f"mesh: island {r.label} has no edge (a closed surface can't be laid flat)")
        lengths = [sum(_norm(_sub(final[lp[i]], final[lp[(i + 1) % len(lp)]])) for i in range(len(lp))) for lp in loops]
        outer = loops[max(range(len(loops)), key=lambda i: (lengths[i], -i))]
        top = max(range(len(outer)), key=lambda i: (final[outer[i]][2], -outer[i]))
        outer = outer[top:] + outer[:top]
        total = lengths[loops.index(outer)] if outer in loops else sum(
            _norm(_sub(final[outer[i]], final[outer[(i + 1) % len(outer)]])) for i in range(len(outer)))
        cu, cv = (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0
        ru, rv = (rect[2] - rect[0]) / 2.0 * (1.0 - ISLAND_MARGIN), (rect[3] - rect[1]) / 2.0 * (1.0 - ISLAND_MARGIN)
        uv: dict[int, tuple[float, float]] = {}
        walked = 0.0
        for i, v in enumerate(outer):
            f = walked / total * _RING       # the place round the ring, interpolated between its points
            j = int(f) % _RING
            w = f - int(f)
            (x0, y0), (x1, y1) = ring[j], ring[(j + 1) % _RING]
            x, y = x0 + w * (x1 - x0), y0 + w * (y1 - y0)
            uv[v] = (cu + ru * y, cv - rv * x)     # from the top (v smallest), turning with the winding
            walked += _norm(_sub(final[v], final[outer[(i + 1) % len(outer)]]))
        verts = sorted({v for t in tris for v in t})
        free = [v for v in verts if v not in uv]
        for v in free:
            uv[v] = (cu, cv)
        _harmonic(tris, final, uv, free)
        for v in every:
            got = struct.unpack("<2f", struct.pack("<2f", *uv.get(one[v], (cu, cv))))
            if not all(math.isfinite(z) for z in got):
                raise ValueError(f"mesh: island {r.label} gave {mesh.body} vertex {mesh.ids[v]} a UV that isn't finite")
            out[v] = got
    return out


def _atlas(mesh: _Mesh, spec: MeshSpec, uvs: dict[int, tuple[float, float]], islands: dict) -> tuple[int, ...]:
    """The ``atlas`` ops on ``uvs`` (in place): every vertex of their
    groups outside an island laid into the rect (its UV, an unwrap's or
    its own, which must lie in 0..1); the groups laid anew."""
    indices = {g.index for g in mesh.groups}
    group_of = [g for g, _ in mesh.ids]
    done: set[int] = set()
    for i, op in enumerate(spec.ops):
        if not isinstance(op, AtlasOp):
            continue
        for g in op.groups:
            if g not in indices:
                raise ValueError(f"mesh.ops[{i}].groups: {mesh.body} has no LOD-0 group {g}")
            if g in done:
                raise ValueError(f"mesh.ops[{i}].groups: group {g} is in two atlas ops")
        u0, v0, u1, v1 = op.rect
        if not (0.0 <= u0 < u1 <= 1.0 and 0.0 <= v0 < v1 <= 1.0):
            raise ValueError(f"mesh.ops[{i}].rect: {list(op.rect)} is not a rect inside 0..1 (u0, v0, u1, v1)")
        for k in range(len(mesh.ids)):
            if group_of[k] not in op.groups or k in islands:
                continue
            u, v = uvs.get(k, mesh.uvs[k])
            if not (-1e-3 <= u <= 1.001 and -1e-3 <= v <= 1.001):
                raise ValueError(f"mesh.ops[{i}]: {mesh.body} group {group_of[k]} has UVs outside 0..1 (a tiled "
                                 "texture): it can't be laid into an atlas")
            uvs[k] = struct.unpack("<2f", struct.pack("<2f", u0 + u * (u1 - u0), v0 + v * (v1 - v0)))
        done.update(op.groups)
    return tuple(sorted(done))


# --------------------------------------------------------------------------- the plan and the write
def _drop(mesh: _Mesh, spec: MeshSpec, base: list[Vec]) -> tuple[_Mesh, list[Vec]]:
    """``mesh`` and ``base`` without the vertices of :attr:`MeshSpec.drop`'s
    bone subtrees (by their heaviest weight) and the triangles that use
    them (the module docstring's drop).  :class:`ValueError` names a bone
    the body lacks, a drop that takes no vertex, a group it takes only part
    of and one that isn't among the LOD's last."""
    if not spec.drop:
        return mesh, base
    for name in spec.drop:
        if name not in mesh.names:
            raise ValueError(f"mesh.drop: {mesh.body} has no bone {name!r}")
    bones, named = _subtree(mesh, set(spec.drop)), ", ".join(spec.drop)
    gone = {k for k, b in enumerate(mesh.heaviest) if b in bones}
    groups = sorted({mesh.ids[k][0] for k in gone})
    if not groups:
        raise ValueError(f"mesh.drop: no vertex of {mesh.body} weighs most on {named}")
    for g in groups:
        if any(mesh.ids[k][0] == g and k not in gone for k in range(len(mesh.ids))):
            raise ValueError(f"mesh.drop: {mesh.body} group {g} holds vertices off {named} too: a drop takes "
                             "whole groups")
    order = [g.index for g in mesh.groups]
    if order[len(order) - len(groups):] != groups:
        raise ValueError(f"mesh.drop: {mesh.body} group {groups[0]} isn't among its last LOD-0 groups: a drop "
                         "takes them off the end, so no other group's number moves")
    kept = [k for k in range(len(mesh.ids)) if k not in gone]
    new = {k: i for i, k in enumerate(kept)}
    tris = [t for t in range(len(mesh.triangles)) if all(v in new for v in mesh.triangles[t])]

    def each(values: tuple) -> tuple:
        return tuple(values[k] for k in kept)
    return replace(mesh, groups=tuple(g for g in mesh.groups if g.index not in groups), ids=each(mesh.ids),
                   keys=each(mesh.keys), positions=each(mesh.positions), normals=each(mesh.normals),
                   uvs=each(mesh.uvs), skins=each(mesh.skins), heaviest=each(mesh.heaviest),
                   triangles=tuple(tuple(new[v] for v in mesh.triangles[t]) for t in tris),
                   corners=tuple(mesh.corners[t] for t in tris) if mesh.corners else ()), [base[k] for k in kept]


def _base(mesh: _Mesh, spec: MeshSpec, base_dir: Path | None) -> tuple[list[Vec], GltfEdit | None]:
    """The positions the ops act on: vanilla's, the glTF's where it moves
    them (its file resolved against ``base_dir`` and checked)."""
    base = list(mesh.positions)
    if spec.gltf is None:
        return base, None
    file, sha = spec.gltf
    path = Path(base_dir or ".") / file
    if not path.is_file():
        raise ValueError(f"mesh.gltf.file {file!r}: no such file ({path})")
    edit = _read_edit(path, mesh)
    if edit.sha256 != sha:
        raise ValueError(f"mesh.gltf.file {file!r}: its sha256 is {edit.sha256}, not the recipe's {sha} "
                         "(`azurik-mod model check` prints the row)")
    for k, p in edit.moved.items():
        base[k] = p
    return base, edit


def _mesh_of(asset) -> _Mesh:
    """A decoded body's LOD 0 as :func:`_read_mesh` reads a stored one
    (an imported body's, Step 2.154)."""
    ids, keys, pos, nrm, uvs, skins, heavy, tris = [], [], [], [], [], [], [], []
    groups = []
    for g, grp in enumerate(asset.lods[0].groups):
        first = len(ids)
        for j, v in enumerate(grp.vertices):
            skin = v.skin(grp.palette)
            ids.append((g, j))
            keys.append(struct.pack("<3f", *v.position))
            pos.append(v.position)
            nrm.append(v.normal)
            uvs.append(v.uv)
            skins.append(skin)
            top, most = 0, -1.0
            for w, b in zip(v.weights, v.slots):     # the first slot of the most weight, as _read_mesh reads it
                if w > 0 and w > most:
                    top, most = grp.palette[_code_entry(b)], w
            heavy.append(top)
        tris += [(first + a, first + b, first + c) for a, b, c in grp.triangles]
        groups.append(MeshGroup(0, g, tuple(grp.palette), 0, 0, len(grp.vertices)))
    names = tuple(b.name for b in asset.bones)
    parents = tuple(b.parent for b in asset.bones)
    binds = tuple(struct.unpack_from("<16f", b.record, 0x60) for b in asset.bones)
    origins = []
    for m in binds:
        r0, r1, r2, t = m[0:3], m[4:7], m[8:11], m[12:15]
        det = _dot(r2, _cross(r0, r1))
        origins.append(tuple(-_dot(t, _cross(u, v)) / det for u, v in ((r1, r2), (r2, r0), (r0, r1))))
    return _Mesh(asset.name, len(asset.lods), tuple(groups), tuple(ids), tuple(keys), tuple(pos), tuple(nrm),
                 tuple(uvs), tuple(skins), tuple(heavy), tuple(tris), names, parents, tuple(origins), binds)


def _code_entry(code: int) -> int:
    from azurkit.tools.characters.body_codec import code_entry
    return code_entry(code)


_LAST_PREPARED: list = [None, None]


def _prepared(characters_xbr: bytes, body: str, spec: MeshSpec, base_dir: Path | None):
    """The mesh the ops act on and its base positions: the stored body
    (the glTF's moved positions on it, Step 2.142) or the glTF imported
    with any topology or new weights (Step 2.154, its body decoded), then
    the ``subdivide`` regions split; also the glTF edit, the import, the
    vertices whose normals turn smooth and how many vertices the mesh had
    before the split.  The last one is kept while it is asked of the same
    immutable bytes, by content (W24's plan and each jiggle bone's shares
    ask the same, each of a fresh copy of the staged file, Step X.63: a
    preparation is a minute); callers get their own lists."""
    key = (body, spec, str(base_dir))
    if (type(characters_xbr) is bytes and _LAST_PREPARED[0] is not None and _LAST_PREPARED[1][0] == key
            and (_LAST_PREPARED[0] is characters_xbr or _LAST_PREPARED[0] == characters_xbr)):
        mesh, base, edit, imported, smooth, count = _LAST_PREPARED[1][1]
        return mesh, list(base), edit, imported, set(smooth), count
    got = _prepare(characters_xbr, body, spec, base_dir)
    if type(characters_xbr) is bytes:
        _LAST_PREPARED[:] = [characters_xbr, (key, got)]
    mesh, base, edit, imported, smooth, count = got
    return mesh, list(base), edit, imported, set(smooth), count


def _prepare(characters_xbr: bytes, body: str, spec: MeshSpec, base_dir: Path | None):
    imported = None
    if spec.gltf is not None and spec.gltf_import != "positions":
        from azurkit.tools.characters import gltf_import

        file, sha = spec.gltf
        path = Path(base_dir or ".") / file
        if not path.is_file():
            raise ValueError(f"mesh.gltf.file {file!r}: no such file ({path})")
        imported = gltf_import.read(characters_xbr, body, path, spec.gltf_import)
        if imported.sha256 != sha:
            raise ValueError(f"mesh.gltf.file {file!r}: its sha256 is {imported.sha256}, not the recipe's {sha} "
                             "(`azurik-mod model import` prints the row)")
        mesh, edit = _mesh_of(imported.asset), None
        base = list(mesh.positions)
    else:
        mesh = _read_mesh(characters_xbr, body)
        base, edit = _base(mesh, spec, base_dir)
    mesh, base = _drop(mesh, spec, base)
    count = len(mesh.ids)
    mesh, base, smooth = _subdivide(mesh, spec, base)
    before = len(mesh.ids)
    mesh, base = _split_islands(mesh, spec, base)
    smooth |= set(range(before, len(mesh.ids))) if smooth else set()
    mesh, base = _generate(mesh, spec, base)
    smooth |= set(mesh.fixed)
    before = len(mesh.ids)
    mesh, base = _cut(mesh, spec, base)
    smooth |= set(range(before, len(mesh.ids)))
    mesh = _rims(mesh, spec, base)
    return mesh, base, edit, imported, smooth, count


def shares(characters_xbr: bytes, body: str, spec: MeshSpec, names, base_dir: Path | None = None
           ) -> dict[tuple[int, int], float]:
    """Each LOD-0 vertex's share of the ``push`` and ``round`` ops of
    ``spec`` named in ``names`` (Step 2.143, D428: a jiggle bone's
    region): the largest over them and their mirrors at the vertex's base
    position (a push's ``b g`` of :func:`_effect`'s profile, a round's
    :func:`_round_share`), whatever their ``groups`` and ``only`` (a
    function of position, so a cloth layer and the skin under it take the
    same share), but none for a vertex ``keep`` holds; vertices no op
    reaches left out.  A mirrored op's mirror answers to its name with
    left and right swapped (Step 2.154: ``breast right`` names one side,
    ``breast left`` the other; ``bust`` both).
    :class:`ValueError` names a name no op carries or a named op that is
    neither."""
    return shares_each(characters_xbr, body, spec, [names], base_dir)[0]


class SharesError(ValueError):
    """:func:`shares_each`'s refusal of its ``index``-th names."""

    def __init__(self, message: str, index: int):
        super().__init__(message)
        self.index = index


@_memo_rays
def shares_each(characters_xbr: bytes, body: str, spec: MeshSpec, each, base_dir: Path | None = None
                ) -> list[dict[tuple[int, int], float]]:
    """:func:`shares` of each of ``each``'s names, in one pass over the
    vertices (Step X.63: a jiggle bone each); :class:`SharesError` is
    :func:`shares`' refusal of the first names it refuses, its ``index``
    their place in ``each``."""
    mesh, base, _, _, _, _ = _prepared(characters_xbr, body, spec, base_dir)
    each = [tuple(names) for names in each]
    segments = dict(mesh.segments)
    carried = {op.name for op in spec.ops} | {_side_name(op.name, True) for op in spec.ops if getattr(op, "mirror", False)}
    for at, names in enumerate(each):
        for name in names:
            if name in segments:
                continue
            if name not in carried:
                raise SharesError(f"no mesh op is named {name!r}", at)
            ops = [op for op in spec.ops if name in (op.name, _side_name(op.name, getattr(op, "mirror", False)))]
            if not all(isinstance(op, (PushOp, RoundOp)) for op in ops):
                raise SharesError(f"mesh op {name!r} isn't a push or a round (or a tube's segment)", at)
    wanted = [set(names) for names in each]
    every = set().union(*wanted)
    pushes = [op for op in spec.ops if isinstance(op, PushOp)]
    placed = _place(mesh, MeshSpec(spec.gltf, (), tuple(
        PushOp(op.bone, op.direction, op.height, op.radius, op.depth, op.offset, op.fold, op.mirror, (), op.name)
        for op in pushes)))
    sides = [pl for pl in placed if _side_name(pl.op.name, pl.label.endswith("mirrored")) in every]
    rounds = [replace(pl, bones=None, kept=frozenset())
              for both in _rounds(mesh, MeshSpec(spec.gltf, (), tuple(replace(op, only=(), groups=()) for op in spec.ops
                                                                      if isinstance(op, RoundOp))))
              for pl in both if _side_name(pl.op.name, pl.label.endswith("mirrored")) in every]
    side_of = [[n for n, w in enumerate(wanted) if _side_name(pl.op.name, pl.label.endswith("mirrored")) in w]
               for pl in sides]
    round_of = [[n for n, w in enumerate(wanted) if _side_name(pl.op.name, pl.label.endswith("mirrored")) in w]
                for pl in rounds]
    segment_of = [(segments[name], n) for n, names in enumerate(each) for name in names if name in segments]
    kept = _subtree(mesh, set(spec.keep))
    rides = {k: src for k, src, _ in mesh.trims}
    from azurkit.tools.characters import pool

    shared = (base, mesh.heaviest, kept, rides, sides, side_of, rounds, round_of, segment_of, len(each))
    out: list[dict[tuple[int, int], float]] = [{} for _ in each]
    step = max(1, -(-len(base) // SHARE_RUNS))   # runs of the vertices over worker processes (Step 2.176)
    for rows in pool.each(_share_rows, shared, [(lo, min(lo + step, len(base))) for lo in range(0, len(base), step)]):
        for k, best in rows:
            for n, x in enumerate(best):
                if x > 0.0:
                    out[n][mesh.ids[k]] = x
    return out


SHARE_RUNS = 32
"""How many runs of the vertices :func:`shares_each` splits over worker
processes (:func:`azurik_mod.assets.pool.each`)."""


@_memo_rays
def _share_rows(shared: tuple, span: tuple[int, int]) -> list[tuple[int, list[float]]]:
    """:func:`shares_each`'s pass over the vertices ``span`` gives (lo,
    hi): each one's share of each set of names but a kept one's."""
    base, heaviest, kept, rides, sides, side_of, rounds, round_of, segment_of, width = shared
    points = [base[rides[k]] if k in rides else base[k] for k in range(*span) if heaviest[k] not in kept]
    for side in rounds:   # each side's rays at once (_rays_ahead), as _round_share asks them
        if side.op.pair:
            _rays_ahead(points, side, side.origin)
            _rays_ahead([(-p[0], p[1], p[2]) for p in points], side, side.origin)
        else:
            _rays_ahead(points, side)
    rows = []
    for k in range(*span):
        if heaviest[k] in kept:
            continue
        p = base[rides[k]] if k in rides else base[k]   # a cut's cord: its edge vertex's share
        best = [0.0] * width
        for op, of in zip(sides, side_of):
            got = _effect(p, op)
            if got is not None and op.op.height:
                x = _norm(got[0]) / abs(op.op.height)
                for n in of:
                    best[n] = max(best[n], x)
        for side, of in zip(rounds, round_of):
            x = _round_share(p, side)
            for n in of:
                best[n] = max(best[n], x)
        for share, n in segment_of:
            best[n] = max(best[n], share.get(k, 0.0))
        rows.append((k, best))
    return rows


def followers(characters_xbr: bytes, body: str, spec: MeshSpec, base_dir: Path | None = None
              ) -> dict[tuple[int, int], tuple[tuple[int, ...], float, str]]:
    """Each vertex of a ``tube`` with ``follow`` and ``reach`` (Step 2.154
    round 10, D582): its (group, index) -> (the groups it follows, its
    reach, its ``hang`` name or ``""``: Step 2.168r), so W29 gives it the
    jiggle share of the skin it rides as W24 gave it that skin's weights
    (:func:`_tube_weights`): a pendant in a cleavage swings with the
    breasts beside it, one weight set for all of a hung one."""
    mesh, _, _, _, _, _ = _prepared(characters_xbr, body, spec, base_dir)
    out = {}
    for i, made, reach_of in mesh.tubes:
        op = spec.ops[i]
        if op.follow:
            for k, reach in zip(made, reach_of):
                if reach > 0.0:
                    out[mesh.ids[k]] = (tuple(op.follow), reach, op.hang)
    return out


@dataclass(frozen=True)
class Prepared:
    """A body prepared for a mesh spec (Step MK.3a, :func:`prepare`): the
    spec, the mesh its ops act on (the glTF read, the ``subdivide`` and
    ``hem`` regions split, the ``island`` seams opened, the ``tube``
    geometry and the ``cut`` edges made) and its base positions."""

    spec: MeshSpec
    mesh: _Mesh
    base: tuple[Vec, ...]


def prepare(characters_xbr: bytes, body: str, spec: MeshSpec, base_dir: Path | None = None) -> Prepared:
    """``spec``'s preparation of ``characters/<body>`` (:func:`plan`'s
    first step, the one kept by content): a topology frozen for
    :func:`positions` of other values of its ops (Step MK.3a: a shape
    slider's ends on one mesh)."""
    mesh, base, _, _, _, _ = _prepared(characters_xbr, body, spec, base_dir)
    return Prepared(spec, mesh, tuple(base))


_FROZEN = (SubdivideOp, HemOp, IslandOp, TubeOp, CutOp, ThickenOp)
"""The ops a preparation lays (a ``cut``'s but its press amounts)."""


@_memo_rays
def positions(prepared: Prepared, spec: MeshSpec | None = None) -> tuple[Vec, ...]:
    """Every vertex's rest position as :func:`plan` writes it (float32 in
    the prepared mesh's order; for the prepared spec, its plan's ``final``,
    or vanilla's with its ``positions`` on a mesh it keeps) of
    ``spec``'s position ops (the prepared spec's by default) on
    ``prepared``'s mesh: its fields, rounds, relax, hem insets, beneath,
    press, snap, ride and tucks, no UVs, weights or normals (Step MK.3a,
    D598: a shape slider's value on a frozen topology).  ``spec`` must be
    the prepared spec's ops in its order, each of its kind and name, with
    its glTF, keep and every number its preparation laid (``subdivide``,
    ``hem``, ``island``, ``tube``, a ``cut``'s but its press depth, width,
    swell and thick); else :class:`ValueError` names the op."""
    spec = prepared.spec if spec is None else spec
    base = prepared.spec
    if (spec.gltf, spec.keep, spec.gltf_import) != (base.gltf, base.keep, base.gltf_import):
        raise ValueError("mesh: its gltf and keep must be the prepared spec's")
    kinds = [[(type(op).__name__, getattr(op, "name", "")) for op in s.ops] for s in (base, spec)]
    if kinds[0] != kinds[1]:
        raise ValueError("mesh.ops: not the prepared spec's ops (each of its kind and name, in its order)")
    for i, (was, now) in enumerate(zip(base.ops, spec.ops)):
        if isinstance(was, CutOp):
            was, now = (replace(op, press=op.press and (0.0, 0.0, 0.0, 0.0, op.press[4])) for op in (was, now))
        if isinstance(was, _FROZEN) and was != now:
            raise ValueError(f"mesh.ops[{i}] ({was.name or type(was).__name__}): a number its preparation laid "
                             "changed (subdivide, hem, island, tube, a cut's but its press amounts): prepare it")
    final, *_, late = _positions(prepared.mesh, list(prepared.base), spec)
    return tuple(_written(prepared.mesh, _moved(final, late))[0])


def _positions(mesh: _Mesh, base: list[Vec], spec: MeshSpec) -> tuple[list[Vec], int, float | None, int, int]:
    """:func:`plan`'s position steps: every vertex's final position, the
    ops placed after mirrors, the least det J and how many vertices the
    rounds and the tucks moved."""
    placed = _place(mesh, spec)
    final = list(base)
    det_min = None
    if placed:
        each = [[op for op in placed if k in op.moves] for k in range(len(base))]
        held: set[int] = set()
        for k, ops in enumerate(each):
            if ops:
                final[k], inside = _displace(base[k], ops)
                if inside:
                    held.add(k)
        points: list[tuple[Vec, list[_Placed]]] = [(base[k], each[k]) for k in sorted(held)]
        for tri in mesh.triangles:
            if held.intersection(tri):
                centre = tuple(sum(base[v][i] for v in tri) / 3 for i in range(3))
                for ops in {tuple(each[v]) for v in tri if each[v]}:
                    points.append((centre, list(ops)))
        dets = [_det(p, ops) for p, ops in points]
        bad = [(p, ops) for (p, ops), d in zip(points, dets) if not d > 0]
        if bad:
            labels = sorted({op.label for p, ops in bad for op in ops if _effect(p, op) is not None})
            raise ValueError(f"mesh.ops fold the surface at {len(bad)} points (det J <= 0) inside {', '.join(labels)}: "
                             "lower a factor or height (one cone scale folds from 4) or widen its radius")
        det_min = min(dets) if dets else None
    for k in mesh.fixed:        # a tube's geometry: no op moves it
        final[k] = base[k]
    rounds = _rounds(mesh, spec)
    rounded = 0
    if rounds:      # the round ops, after the fields, in recipe order (each a projection: no det J of its own)
        ks = [k for k in range(len(final)) if k not in mesh.fixed]   # a round at a time over them all
        for k, q in zip(ks, _round_all_each([final[k] for k in ks], rounds, [mesh.heaviest[k] for k in ks],
                                            [mesh.ids[k][0] for k in ks])):
            if q != final[k]:
                final[k] = q
                rounded += 1
    _relax(mesh, spec, base, final)
    _insets(mesh, spec, base, final)
    _beneath(mesh, spec, final)
    _press(mesh, spec, final)
    _snap(mesh, spec, final)
    _ride(mesh, final)
    pushed = {k for k in range(len(base)) if final[k] != base[k]}
    fielded = list(final)
    for _label, op, frame, moves, cloth in _tucks(mesh, spec):
        _tuck(base, final, op, frame, [k for k in moves if k in pushed], cloth, mesh.triangles)
    tucked = sum(1 for a, b in zip(final, fielded) if a != b)
    _thicken(mesh, spec, base, final)
    return final, len(placed), det_min, rounded, tucked, _late(mesh, spec, final)


def _late(mesh: _Mesh, spec: MeshSpec, final: list[Vec]) -> dict[int, Vec]:
    """Each ``late`` scale's move (Step 2.187) by vertex: its displacement
    at each vertex it selects, there in ``final``, its sides' summed; not
    applied: :func:`plan` adds them last, after the binds, tubes and UVs
    (which read the shape before them), as :func:`positions` does.  Its
    det J must stay above 0 at every vertex it moves (as a field's)."""
    ops = tuple(replace(op, late=False) for op in spec.ops if isinstance(op, ScaleOp) and op.late)
    if not ops:
        return {}
    placed = _place(mesh, MeshSpec(spec.gltf, spec.keep, ops))
    out: dict[int, Vec] = {}
    for k in range(len(final)):
        mine = [pl for pl in placed if k in pl.moves and k not in mesh.fixed]
        got = [(pl, _effect(final[k], pl, True)) for pl in mine]
        got = [(pl, e) for pl, e in got if e is not None]
        if not got:
            continue
        if not _det(final[k], [pl for pl, _ in got]) > 0:
            raise ValueError(f"mesh.ops fold the surface (det J <= 0) inside the late {got[0][0].label}: "
                             "lower its factor or widen its radius")
        out[k] = tuple(sum(e[0][i] for _, e in got) for i in range(3))
    return out


def _moved(final: list[Vec], late: dict[int, Vec]) -> list[Vec]:
    """``final`` with the ``late`` scales' moves added (Step 2.187)."""
    out = list(final)
    for k, d in late.items():
        out[k] = (out[k][0] + d[0], out[k][1] + d[1], out[k][2] + d[2])
    return out


def _islands(shared: tuple, _) -> dict[int, tuple[float, float]]:
    """:func:`_island_uvs` of ``shared`` (its arguments), in a worker process (:func:`plan`)."""
    return _island_uvs(*shared)


def _written(mesh: _Mesh, final: list[Vec]) -> tuple[list[Vec], set[int]]:
    """Each vertex's position as :func:`write` writes it (float32 where it
    ends more than :data:`MOVED` from the mesh's, else the mesh's own) and
    the vertices that moved."""
    after = list(mesh.positions)
    moved = {k for k, p in enumerate(final) if _norm(_sub(p, mesh.positions[k])) > MOVED}
    for k in moved:
        after[k] = _f32(final[k])
    return after, moved


@_memo_rays
def plan(characters_xbr: bytes, body: str, spec: MeshSpec, base_dir: Path | None = None) -> MeshPlan:
    """What ``spec`` writes into the body ``characters/<body>`` of the
    vanilla ``characters_xbr`` (its glTF's file resolved against
    ``base_dir``): the glTF's moved vertices, then the ops on them, the
    normals recomputed, every check of the module docstring run.
    :class:`ValueError` names the first that fails (D35)."""
    mesh, base, edit, imported, smooth, vanilla_count = _prepared(characters_xbr, body, spec, base_dir)
    final, placed, det_min, rounded, tucked, late = _positions(mesh, base, spec)
    remapped = _unwrap(mesh, spec, base, final)
    islands = None
    if any(isinstance(op, IslandOp) for op in spec.ops):   # laid in a child while the binds run (Step 2.176)
        from azurkit.tools.characters import pool
        islands = pool.later(pool.each, _islands, (mesh, spec, base, final), [None], None, 1)
    try:
        bound = _bind(mesh, spec, base, final)
        bound.update(_reweight(mesh, spec, base, bound))
        for k, src, _ in mesh.trims:        # a cut's cord takes its edge's weights
            if src in bound:
                bound[k] = dict(bound[src])
        bound.update(_tube_weights(mesh, spec, final, bound))
        failed = None
    except ValueError as exc:
        failed = exc                    # raised after the islands' and the atlas's own, which come first
    laid = islands.result()[0] if islands is not None else _island_uvs(mesh, spec, base, final)
    remapped.update(laid)
    atlased = _atlas(mesh, spec, remapped, laid)
    repaint = tuple(sorted(set(atlased) | {mesh.ids[k][0] for k in laid}))
    if failed is not None:
        raise failed
    after, moved = _written(mesh, _moved(final, late))      # the late scales last (Step 2.187)
    at = {mesh.ids[k]: after[k] for k in sorted(moved)}
    apart = {v: s for _op, _tris, side, _share in _two_sided(mesh, spec, base) for v, (_q, s) in side.items()}
    together: dict[tuple, list[int]] = {}
    for k, key in enumerate(mesh.keys):     # a thickened layer's two sides end apart (Step 2.177d)
        together.setdefault((key, apart.get(k)), []).append(k)
    opened = [max(max(abs(after[j][i] - after[ks[0]][i]) for i in range(3)) for j in ks)
              for ks in together.values() if len(ks) > 1]
    opened = [d for d in opened if d > COPIES]
    if opened:
        raise ValueError(f"mesh: {len(opened)} seams open (vertices {mesh.body} keeps at one place end up to "
                         f"{max(opened) * 1000:.3g} mm apart): a keep or only boundary, or the glTF's edit, tore them")
    by_index = _normals(mesh, after, moved)
    by_index.update(_smooth_normals(mesh, after, smooth, _angled(mesh, spec, base, smooth)))
    normals = {mesh.ids[k]: n for k, n in by_index.items()}
    turned = sum(1 for t in mesh.triangles if moved.intersection(t)
                 and _dot(_face(mesh.positions, t), _face(after, t)) < 0)
    largest = max((_norm(_sub(after[k], mesh.positions[k])) for k in moved), default=0.0)
    added = len(mesh.ids) - vanilla_count
    dropped = ()
    if spec.drop:   # the groups the drop took off (the LOD's last: _drop)
        held = {g.index for g in mesh.groups}
        stored = len(imported.asset.lods[0].groups) if imported is not None else \
            sum(1 for g in mesh_groups(characters_xbr, body) if g.lod == 0)
        dropped = tuple(g for g in range(stored) if g not in held)
    every = ()
    whole = bool(added) or imported is not None or bool(remapped) or bool(bound) or bool(dropped)
    if whole:
        every = tuple(by_index.get(k) or (mesh.normals[k] if k < vanilla_count else
                                          _f32(_unit(mesh.normals[k]) or (0.0, 0.0, 1.0))) for k in range(len(mesh.ids)))
    return MeshPlan(mesh.body, len(mesh.positions), at, normals, largest, len(spec.ops), placed, turned,
                    det_min, edit, tucked, added, mesh if whole else None, tuple(after) if whole else (), every,
                    imported, rounded, remapped, bound, repaint, {mesh.ids[k]: d for k, d in sorted(late.items())},
                    dropped)


def _vanilla_here(before: bytes, plan: MeshPlan, vanilla_xbr: bytes) -> None:
    """W-2: the body's LOD-0 vertices in ``before`` are vanilla's."""
    groups = {g.index: g for g in mesh_groups(before, plan.body) if g.lod == 0}
    vanilla = {g.index: g for g in mesh_groups(vanilla_xbr, plan.body) if g.lod == 0}
    if {i: g.count for i, g in groups.items()} != {i: g.count for i, g in vanilla.items()} or any(
            before[g.vertices:g.vertices + VERTEX_SIZE * g.count]
            != vanilla_xbr[vanilla[i].vertices:vanilla[i].vertices + VERTEX_SIZE * g.count] for i, g in groups.items()):
        raise ValueError(f"W24: {plan.body}'s LOD-0 vertices aren't vanilla's here (an earlier step rewrote them)")


def assemble(characters: bytes, plan: MeshPlan, vanilla_xbr: bytes):
    """A subdividing ``plan`` (one whose ``mesh`` is set) as the body's
    :class:`~azurik_mod.assets.body_codec.BodyAsset`, not yet written:
    each LOD-0 group's vertices at their final positions and normals, its
    new vertices after its old ones (their weights the plan's, cut to
    four, renormalised in float32 and mapped into the group's palette,
    their UVs and the +48 pair zero), its triangles the subdivided mesh's
    in order.  W-2 as :func:`write`."""
    from azurkit.tools.characters import body_codec

    if plan.mesh is None:
        raise ValueError("W24: the plan adds no vertex; write it in place")
    before = bytes(characters)
    _vanilla_here(before, plan, vanilla_xbr)
    if plan.imported is not None:     # an imported body (Step 2.154): its groups, bones and vertices the base
        asset = copy.deepcopy(plan.imported.asset)
    else:
        asset = body_codec.read_asset(before, plan.body)
    mesh = plan.mesh
    groups = {g: grp for g, grp in enumerate(asset.lods[0].groups)}
    local = {}
    for k, (g, j) in enumerate(mesh.ids):
        grp = groups[g]
        p = plan.final[k]
        n = plan.every_normal[k]
        uv = (plan.uvs or {}).get(k)
        bound = (plan.skins or {}).get(k)
        if j < len(grp.vertices):
            v = grp.vertices[j]
            if bound is None:
                grp.vertices[j] = body_codec.Vertex(p, v.weights, n, v.uv if uv is None else uv, v.extra, v.slots)
            else:       # a bind's weights (Step 2.154): mapped into the group's palette, as a new vertex's
                grp.vertices[j] = body_codec.make_vertex(p, n, v.uv if uv is None else uv, bound, grp.palette, v.extra)
        else:
            if j != len(grp.vertices):
                raise ValueError(f"W24: {plan.body} group {g}'s new vertices aren't in order")
            grp.vertices.append(body_codec.make_vertex(p, n, mesh.uvs[k] if uv is None else uv,
                                                       mesh.skins[k] if bound is None else bound, grp.palette))
        local[k] = j
    for grp in groups.values():
        grp.triangles = []
    for t in mesh.triangles:
        g = mesh.ids[t[0]][0]
        groups[g].triangles.append(tuple(local[v] for v in t))
    asset.lods[0].groups = [grp for g, grp in groups.items() if g not in plan.dropped]   # the drop's (Step 4.3)
    return asset


def write(characters: bytearray, plan: MeshPlan, vanilla_xbr: bytes) -> None:
    """W24: ``plan`` into ``characters`` in place, at the offsets its
    current bytes give, then the output checks: the body's LOD-0 vertex
    bytes were vanilla's before (W-2), every written float is finite and
    every normal unit, and the file equals its input outside the written
    fields.  A subdividing plan (Step 2.154) is :func:`assemble`'s asset
    written instead (:func:`~azurik_mod.assets.body_codec.write_asset`:
    the body and its mesh rewritten and grown in place, its groups split
    where they pass the format's limits), ``characters`` then the grown
    file.  :class:`ValueError` on a failure (the caller discards
    ``characters``)."""
    if plan.mesh is not None:
        from azurkit.tools.characters import body_codec

        characters[:] = body_codec.write_asset(bytes(characters), assemble(bytes(characters), plan, vanilla_xbr))
        return
    before = bytes(characters)
    _vanilla_here(before, plan, vanilla_xbr)
    groups = {g.index: g for g in mesh_groups(before, plan.body) if g.lod == 0}
    ranges = []
    for (gi, j), p in plan.positions.items():
        at = groups[gi].vertices + VERTEX_SIZE * j
        struct.pack_into("<3f", characters, at, *p)
        ranges.append((at, at + 12))
    for (gi, j), n in plan.normals.items():
        at = groups[gi].vertices + VERTEX_SIZE * j + 28
        struct.pack_into("<3f", characters, at, *n)
        if not abs(_norm(struct.unpack_from("<3f", characters, at)) - 1.0) <= 1e-3:
            raise ValueError(f"W24: {plan.body} vertex ({gi}, {j})'s normal isn't unit")
        ranges.append((at, at + 12))
    for a, _ in ranges:
        if not all(math.isfinite(x) for x in struct.unpack_from("<3f", characters, a)):
            raise ValueError(f"W24: {plan.body}: a written float isn't finite")
    probe = bytearray(characters)
    for a, b in ranges:
        probe[a:b] = before[a:b]
    if probe != before:
        raise ValueError(f"W24: {plan.body}: the write changed bytes outside its positions and normals")


__all__ = ["CARRIERS", "COPIES", "CutOp", "FRAME", "GltfEdit", "MOVED", "MeshPlan", "MeshSpec", "OPS", "PROFILES", "PushOp",
           "AtlasOp", "IslandOp", "RelaxOp", "RoundOp", "SHIFT", "TubeOp", "SKIN_CHANGE", "SUBDIVIDE_MAX", "PASSES_MAX", "TUBE_POINTS_MAX", "TUBE_RINGS_MAX", "TUBE_SIDES_MAX", "ScaleOp", "SubdivideOp", "TaperOp", "ThickenOp", "TuckOp", "UV_CHANGE", "UnwrapOp", "WELD",
           "SIZES", "SharesError", "assemble", "file_sha256", "plan", "shaped", "shares", "shares_each", "sized",
           "write"]
