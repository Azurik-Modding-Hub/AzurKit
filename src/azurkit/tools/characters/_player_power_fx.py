"""W6's power heads reshaped for what the hand holds (Step 2.182, D703, D707).

The owner (2026-10-25): "for models that don't use the axion, when we use
a power such as water, it makes the visual effects show up at their fists
or other locations. the effect itself is still shaped to the axion
though, can it be reshaped for the weapon that model uses?"  W6 binds the
staff fx's two ends to the body's hands, a carried hoe's carriers or a
fixed point, but the heads under them kept the Axion's shape: 0.75 m
down the staff's axis and 0.65 past its end, centred off the fist.  On
every weapon but the Axion staff (whose heads keep their bytes but on a
copy drawn at another size, below), each
head is now mapped by the owner's pick from Step 2.182's sheet, look B
"Gauntlet" (D707), ``A = T(p) . RA . s . T(-h u)`` in its end's frame
(:class:`Head`): ``u`` the end's out direction (the top's +z, the
bottom's -z), ``h`` the head's centre on it (:data:`HEAD_CENTRES`) or 0
(its end), ``RA`` a quarter turn of ``u`` onto the fist's axis (the hand
bone's signed axis nearest the fist), the hoe's +/-y or (a point) none,
and ``s`` its size:

- **a hand** (:func:`hand_shape`): the end at the wrist joint, the head
  over the fist and up the forearm, x0.45 the hand's reach over
  garret4's;
- **a hoe** (:func:`hoe_shape`): the tip head's end at the blade's inner
  edge, laid past the tip along the hoe, x0.6; the handle end's a x0.2
  cap (the judge's F2: x0.6 there covered the farmer's hands);
- **a handless body's point** (:func:`point_shape`): both heads centred
  upright, x0.6 its height over garret4's, outside its body (F1: at its
  point they sat inside it): over its mesh's top for a chest point, past
  its mesh's front for a marker (where its hit lands) inside its hull;
  and the pools the ends feed, inside them too, take the head's size on
  their sprites, and those outside on their forces, so fire stays a small
  flame at the head: neither a 1 m beam nor, with full-size sprites
  crowded into it, a white blaze under a blue haze of smoke.

How the map is written:

- **A bound end** (a hand, a hoe's carrier) takes its bone's matrix every
  frame (0xCCDF0), so the map goes into each direct child: its
  translate, rotate and scale (and the scale pivot's translation, +0x38);
  each of the 10 rotateZ spins (water3's balls, ice's helix, whirlwind's
  trails) turns about the new axis (its link's plug +0x10 and its
  rotation order +0x6C, its phase dropped), the same way round (its
  link's factor negated where the axis lands reversed); each of the 10 scale links
  (lightning's HitFlash, normal1's spikes) takes the size in its factor.
- **An unbound end** (a point's) takes the map itself.
- **The Axion staff copied** onto a wearer at size k != 1 (Step 2.203,
  :func:`staff_shape`): both heads unturned at their ends, x k, and as
  at a point the sprites of every pool the ends feed and the forces
  outside them x k; at garret4's own size (k 1) its heads keep their bytes.
- **Shared**: the sprites of the pools outside the heads that only the
  ends feed (``pRendererB`` size1 and size2, or their links' factors) x
  :data:`SPRITES` (at a point x its size, those of the pools inside the
  ends too), a renderer or force another pool shares kept (the elemental
  staffs' root bursts, the electric shields' body sparks).
  Spread, speed and orbits follow the transforms (births go through the
  emitter's matrix, 0xD9DE0); colours, ages, timers, emit and spin rates
  are kept, and so is each swing trail's lineLength: 0x7C1A0 draws its
  ends lineLength/2 either way along its node's world z axis, so the
  trail takes its head's size through the map (Step 2.202, M11: x the
  size as well it drew 0.55 x the size squared).
- **Hidden**: W6's 0.001 shrink keeps only the blades (:func:`blades`), so
  the element meshes come back at the head's size; on the hands
  fx_staff_smash's force ring and ring cores too (:data:`RINGS`, F4:
  edge-on they read as flat pink cards through the forearm), the cone
  and particles kept; on garret4's hoe (D618: his powers' heads whole on
  it) only the plain staff's head (:func:`plain`, AZ-782).

A build refuses (D35) and names the graph, end and record: a child of an
end that isn't a transform, a transform under an end at an inherit mode
other than 0 (R1); a child linked in translation, or in rotation on a plug
other than rotateZ or more than once, or a spin whose new plug is linked
(R2); a light, a pVortex or any type :data:`KNOWN` doesn't list under an
end (R3); a hand with no fist and no forearm, a hoe with no blade near
its tip or whose longest side isn't along its carrier's y, a staff graph
whose ends hold no blade, a smash graph with no ring (R4); a value that
isn't a finite f32 (R5); and old bytes not as vanilla's (R6,
``replace_bytes_at``'s ``expected``).
"""

from __future__ import annotations

import collections
import math
import struct
from dataclasses import dataclass

import numpy as np

from azurkit.tools.characters.ports import replace_bytes_at
from azurkit.core.xbr.graph import Euler, Graph, record_offsets
from azurkit.core.xbr.nodes import named_resources, parse_toc

ENDS = ("m_stafftop", "m_staffbottom")
OUT = {"m_stafftop": (0.0, 0.0, 1.0), "m_staffbottom": (0.0, 0.0, -1.0)}
"""Each staff end's out direction in its frame: past the end, away from
the staff's middle (the other end lies 1.55 down z)."""

HEAD_CENTRES = {
    "fx_staff_acid1": 0.18, "fx_staff_acid2": 0.18, "fx_staff_acid3": 0.18,
    "fx_staff_elemental1": 0.15, "fx_staff_elemental2": 0.15, "fx_staff_elemental3": 0.15,
    "fx_staff_fire1": 0.14, "fx_staff_fire2": 0.16, "fx_staff_fire3": 0.15,
    "fx_staff_ice1": 0.12, "fx_staff_ice2": 0.12, "fx_staff_ice3": 0.14,
    "fx_staff_lightning1": 0.12, "fx_staff_lightning2": 0.13, "fx_staff_lightning3": 0.12,
    "fx_staff_normal1": 0.09,
    "fx_staff_smash1": -0.26, "fx_staff_smash2": -0.17, "fx_staff_smash3": -0.07,
    "fx_staff_steam1": -0.19, "fx_staff_steam2": -0.19, "fx_staff_steam3": -0.19,
    "fx_staff_water1": 0.24, "fx_staff_water2": 0.20, "fx_staff_water3": 0.12,
    "fx_staff_whirlwind1": -0.04, "fx_staff_whirlwind2": -0.17, "fx_staff_whirlwind3": -0.30}
"""Each staff graph's head centre on its end's out axis (m, garret4's
size): the middle of its parts' span along it, meshes, emitters and
trails (Step 2.182's census, ``design-mids``); 0 for a graph not listed
(the electric shields)."""

KNOWN = frozenset(("transform", "platform", "pEmitter", "pBurstEmitter", "pSystem", "polyTrail", "pNull",
                   "pAccelerator", "soundEffect"))
"""The node types found under a staff end (vanilla's nine), each with a
rule: a transform is mapped, the rest ride it.  Any other refuses (R3)."""

GARRET4_REACH = 0.201
"""garret4's fist reach (his right hand's farthest descendant from its
joint, m): a hand's head is sized by a body's reach over his."""

HAND, HOE, HANDLE, POINT, SPRITES = 0.45, 0.6, 0.2, 0.6, 0.8
"""Look B's sizes (D707): a hand's head x0.45 its reach over garret4's, a
hoe's tip head x0.6 and its handle end's x0.2 (F2) the copy's size, a
point's heads x0.6 the body's height over garret4's; the shared pools'
sprites x0.8."""

CLEAR = 0.8
"""How far a point's head centre sits outside the body's mesh, in its
size (F1): a head reaches 0.75-0.80 from its centre along its axis."""

RINGS = ("ForceRing", "RingCore")
"""fx_staff_smash's force ring and ring cores (their transforms' names'
starts), hidden on the hands (F4) by their scale links' factors x 0.001
(the links drive their scale, so W6's static shrink can't)."""

SIZES, MAGNITUDES = (17, 18), (5, 6)
"""pRendererB's size1 and size2 and
pAccelerator's nearMagnitude and farMagnitude (attribute indexes,
``default.xbe``'s schema; the test checks them)."""
_F32_MAX = 3.4028234663852886e38


@dataclass(frozen=True)
class Head:
    """One end's map in its end's frame: ``turn`` (RA, rows), the anchor
    ``at`` (p), the ``size`` (s), and whether the head's centre
    (:data:`HEAD_CENTRES`) or its end lands on the anchor."""

    turn: tuple[tuple[float, float, float], ...]
    at: tuple[float, float, float]
    size: float
    centred: bool


@dataclass(frozen=True)
class Shape:
    """Look B on a body: its class (``hand``, ``hoe`` or ``point``; ``staff``, the Axion copied at a size), each
    end's :class:`Head` by bind name, the factors on the sprites and on the
    forces of the pools the ends feed (:data:`SPRITES` and 1, or a point's
    head size for both) and a build-log phrase."""

    kind: str
    heads: dict
    sprites: float
    forces: float
    note: str


def turn_onto(u, d) -> tuple[tuple[float, float, float], ...]:
    """The rotation (rows) taking the unit axis ``u`` onto ``d``: the
    identity, a quarter turn about u x d, or a half turn about the first
    coordinate axis across ``u``."""
    u, d = np.asarray(u, float), np.asarray(d, float)
    if np.allclose(u, d):
        m = np.eye(3)
    elif np.allclose(u, -d):
        w = next(e for e in np.eye(3) if abs(e @ u) < 0.5)
        m = 2 * np.outer(w, w) - np.eye(3)
    else:
        w = np.cross(u, d)
        w /= np.linalg.norm(w)
        k = np.array([[0, -w[2], w[1]], [w[2], 0, -w[0]], [-w[1], w[0], 0]])
        m = k + np.outer(w, w)
    return tuple(tuple(float(round(v, 12)) for v in row) for row in m)


def angles(euler: Euler, m, order: int) -> tuple[float, float, float]:
    """The (rx, ry, rz) that :meth:`Euler.rotation` turns into ``m`` (3x3)
    in ``order`` (Shoemake's Eul_FromHMatrix, static frame)."""
    i, j, k = euler.euler_axes[order]
    p = euler.euler_parity[order]
    cy = math.hypot(m[i][i], m[j][i])
    if cy > 1e-9:
        a = (math.atan2(m[k][j], m[k][k]), math.atan2(-m[k][i], cy), math.atan2(m[j][i], m[i][i]))
    else:
        a = (math.atan2(-m[j][k], m[j][j]), math.atan2(-m[k][i], cy), 0.0)
    out = [0.0, 0.0, 0.0]
    for axis, v in zip((i, j, k), a):
        out[axis] = p * v
    return tuple(out)


def _axis(v) -> tuple[float, float, float]:
    """The signed coordinate axis nearest ``v``."""
    a = int(np.argmax(np.abs(v)))
    return tuple(float(math.copysign(1.0, v[a])) if c == a else 0.0 for c in range(3))


def _fist(characters: bytes, body: str, bone: str, skip: frozenset) -> tuple[np.ndarray, float, np.ndarray | None]:
    """The fist of ``body``'s ``bone`` in that bone's bind frame: the mean of
    its descendants' joints (``skip`` left out: a carried prop's carriers),
    the farthest one's distance, and its parent's joint (``None`` at the
    root)."""
    from azurkit.tools.characters.characters import bone_records, inverse_binds

    recs, inv = bone_records(characters, body), inverse_binds(characters, body)
    names = [r.name for r in recs]
    k = names.index(bone)
    frame = np.array(inv[k], float).reshape(4, 4)

    def here(j: int) -> np.ndarray:
        world = np.linalg.inv(np.array(inv[j], float).reshape(4, 4))
        return (np.append(world[3, :3], 1.0) @ frame)[:3]
    kids, stack = [], [j for j, r in enumerate(recs) if r.parent == k and r.name not in skip]
    while stack:
        j = stack.pop()
        kids.append(j)
        stack += [x for x, r in enumerate(recs) if r.parent == j and r.name not in skip]
    pts = np.array([here(j) for j in kids]) if kids else np.zeros((0, 3))
    centre = pts.mean(0) if len(pts) else np.zeros(3)
    reach = float(np.linalg.norm(pts, axis=1).max()) if len(pts) else 0.0
    return centre, reach, here(recs[k].parent) if recs[k].parent >= 0 else None


def hand_shape(characters: bytes, body: str, hands: tuple[str, str], skip=frozenset()) -> Shape:
    """Look B on ``body``'s ``hands`` (W6's bones, the top end's first):
    each end at its wrist joint, its head turned onto its fist's axis and
    sized :data:`HAND` x the hand's reach over garret4's
    (:data:`GARRET4_REACH`).  :class:`ValueError` (R4) names a hand with
    no fist and no forearm."""
    heads, words = {}, []
    for end, bone in zip(ENDS, hands):
        centre, reach, elbow = _fist(characters, body, bone, frozenset(skip))
        if np.linalg.norm(centre) >= 0.01:
            toward = centre
        elif elbow is not None and np.linalg.norm(elbow) >= 0.01:
            toward = -elbow
        else:
            raise ValueError(f"W6: {body}'s {bone} has no fist and no forearm to lay the power head on (R4)")
        d = _axis(toward)
        f = (reach or GARRET4_REACH) / GARRET4_REACH
        unit = toward / np.linalg.norm(toward)
        heads[end] = Head(turn_onto(OUT[end], d), (0.0, 0.0, 0.0), HAND * f, False)
        words.append(f"{bone} {math.degrees(math.acos(min(1.0, abs(float(unit @ np.asarray(d)))))):.0f} deg off "
                     f"its fist, x{HAND * f:.2f}")
    return Shape("hand", heads, SPRITES, 1.0, f"over each fist from the wrist ({'; '.join(words)})")


def hoe_shape(characters: bytes, prop, k: float) -> Shape:
    """Look B on a carried hoe (``prop``, its copy's size ``k``): in the
    carriers' frame (the blade tip at the tip carrier's origin, the handle
    down -y, :func:`~azurik_mod.patches._player_weapons._donor`) the tip
    head's end at the blade's inner edge, laid past the tip along the hoe
    (:data:`HOE`), and the handle end's head a :data:`HANDLE` cap past the
    handle's end.  :class:`ValueError` (R4) names a hoe with no blade
    within 0.30 of its tip or whose longest side isn't along y."""
    from azurkit.tools.characters._player_weapons import _donor

    pts = np.array([v[0] for v in _donor(characters, prop)[0]], float)
    span = pts.max(0) - pts.min(0)
    blade = pts[pts[:, 1] > -0.30]
    if not len(blade) or int(np.argmax(span)) != 1:
        raise ValueError(f"W6: the {prop.title} has no blade within 0.30 of its tip along its carrier's y (R4)")
    lo, hi = blade.min(0), blade.max(0)
    inner = k * np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
    tip = Head(turn_onto(OUT["m_stafftop"], (0.0, 1.0, 0.0)), tuple(float(v) for v in inner), HOE * k, False)
    end = Head(turn_onto(OUT["m_staffbottom"], (0.0, -1.0, 0.0)), (0.0, 0.0, 0.0), HANDLE * k, False)
    return Shape("hoe", {"m_stafftop": tip, "m_staffbottom": end}, SPRITES, 1.0,
                 f"laid along the {prop.title}, x{HOE * k:.2f} at its blade, x{HANDLE * k:.2f} at its handle's end")


def point_shape(point: tuple[float, float, float], marker: bool, ratio: float,
                hull: tuple[tuple[float, ...], tuple[float, ...]] | None, top: float) -> Shape:
    """Look B at a handless body's fixed ``point`` (W6's, in the player's
    model; ``marker`` where its hit lands, else its chest point), sized
    :data:`POINT` x ``ratio``, its height over garret4's: both heads
    centred upright on an anchor :data:`CLEAR` x their size outside the
    body (F1), over the top of its mesh (``hull``, its low and high
    corners; without one ``top``, its height) for a chest point, and for
    a marker inside the mesh's width and height, past its front (else
    the marker's own), and a marker's never lower than :data:`CLEAR` x
    their size over the floor, the model's origin (Step 2.202, M11:
    firedrake's bite at z 0.04 put its heads 0.48 m under it); the
    sprites of the pools the ends feed, and the forces of those outside
    them, x the size."""
    s = POINT * ratio
    x, y, z = point
    if not marker:
        z = (hull[1][2] if hull else top) + CLEAR * s
    elif hull and hull[0][0] <= x <= hull[1][0] and hull[0][2] <= z <= hull[1][2]:
        y = max(y, hull[1][1] + CLEAR * s)
    if marker:   # Step 2.202 (M11): a marker near the floor lifts its heads' lower end onto it (firedrake's bite at
        z = max(z, CLEAR * s)   # z 0.04 had its x0.64 heads reach 0.48 m under the floor, the model origin)
    at = (float(x), float(y), float(z))
    heads = {end: Head(turn_onto(OUT[end], OUT[end]), at, s, True) for end in ENDS}
    return Shape("point", heads, s, s, f"at ({', '.join(f'{v:.2f}' for v in at)}) "
                 f"{'past its front' if marker else 'over its top'}, x{s:.2f}")


def staff_shape(k: float) -> Shape:
    """The Axion staff copied at size ``k`` (W32 on a wearer whose
    :attr:`~azurik_mod.patches._player_weapons.Loadout.k` isn't 1; Step
    2.203): each end's head sized ``k`` about the end, unturned, its
    blades, particles and trails, and as at a point every pool the ends
    feed, its sprites and the forces outside the heads, with it, so they fit
    the shaft the copy drew ``k`` times garret4's (the carriers' matrices
    are at scale 1: the prop's mesh holds its size, so they don't scale)."""
    unturned = turn_onto(OUT["m_stafftop"], OUT["m_stafftop"])
    return Shape("staff", {end: Head(unturned, (0.0, 0.0, 0.0), k, False) for end in ENDS}, k, k,
                 f"the Axion's at its copy's size, x{k:.3g} about each end")


PLAIN = "fx_staff_normal1"
"""The staff graph the game plays with no power on: the Axion's own head,
its blade, spikes and extra blades (``docs/RE_DATA.md`` "The staff")."""


def plain(fx_raw) -> set[int]:
    """The record offsets of the plain staff's head, all of :data:`PLAIN`:
    what W6 hides on garret4's hoe (Step 2.206b, AZ-782: laid along the
    hoe, his staff's head drew there as a stray dark spiky piece with no
    power on)."""
    return {g.file_offset + ro for g, _, name in _graphs(fx_raw) if name == PLAIN for ro in g.recs if ro is not None}


def blades(fx_raw) -> set[int]:
    """The record offsets W6's shrink keeps hiding: each staff graph's
    transforms named Blade* (its Axion blade meshes) and all of
    :data:`PLAIN` (a plain staff's blades and spikes, :func:`plain`).
    :class:`ValueError` (R4) names a staff graph whose end holds no blade."""
    out = plain(fx_raw)
    for g, ends, name in _graphs(fx_raw):
        if name == PLAIN:
            continue
        kids = _children(g)
        for bind, e in ends.items():
            mine = {g.file_offset + g.recs[c] for c in kids[e] if (g.names[c] or "").startswith("Blade")}
            if name.startswith("fx_staff_") and not mine:
                raise ValueError(f"W6: {name}'s {bind} end holds no Blade transform to hide (R4)")
            out |= mine
    return out


def _graphs(fx_raw):
    """Each graph of ``fx.xbr`` that binds both staff ends: its
    :class:`~azurik_mod.xbr.nodes.Graph`, ``{bind name: record index}``
    of its ends as vanilla binds them (by record name, as W6 rebinds the
    strings) and its resource name's last part."""
    from azurkit.tools.characters._player_character import _staff_graphs

    starts = {recs[0] for recs, _ in _staff_graphs(fx_raw) if recs and recs[0] is not None}   # vanilla's binds
    toc, names = parse_toc(fx_raw), named_resources(fx_raw)
    for entry in toc:
        if entry.tag != "node":
            continue
        recs = record_offsets(fx_raw, entry.file_offset)
        if not recs or recs[0] not in starts:
            continue
        g = Graph(fx_raw, toc, entry, None)
        ends = {g.names[i]: i for i, ro in enumerate(g.recs) if ro is not None and g.names[i] in ENDS
                and g.types[i] == "transform"}
        yield g, ends, (names.get(entry.index) or "").rsplit("/", 1)[-1]


def _children(g: Graph) -> dict[int, list[int]]:
    from azurkit.tools.characters._player_character import _DAG

    kids: dict[int, list[int]] = collections.defaultdict(list)
    for i, ro in enumerate(g.recs):
        if ro is not None and g.types[i] in _DAG:
            kids[struct.unpack_from("<i", g.s, ro + 0x18)[0]].append(i)
    return kids


class _Writes:
    """One graph's writes into the staged ``fx`` document, each with its old
    bytes expected (R6) and its values checked finite f32 (R5)."""

    def __init__(self, fx, g: Graph, graph: str):
        self.fx, self.g, self.graph, self.n = fx, g, graph, 0

    def floats(self, off: int, values, what: str) -> None:
        values = [float(v) for v in values]
        if not all(math.isfinite(v) and abs(v) <= _F32_MAX for v in values):
            raise ValueError(f"W6: {self.graph}'s {what}: {values} isn't a finite f32 (R5)")
        new = struct.pack(f"<{len(values)}f", *values)
        old = self.g.s[off:off + len(new)]
        if new != old:
            replace_bytes_at(self.fx, self.g.file_offset + off, new, expected=old)
            self.n += 1

    def raw(self, off: int, new: bytes) -> None:
        old = self.g.s[off:off + len(new)]
        if new != old:
            replace_bytes_at(self.fx, self.g.file_offset + off, new, expected=old)
            self.n += 1

    def attr(self, i: int, k: int, factor: float, what: str, links: dict) -> None:
        """Record ``i``'s attribute ``k`` x ``factor``: the factors of the
        links that drive it, else its value."""
        driven = links.get((i, k), [])
        for src, n in driven:
            st, _ = self.g.list_at(src, 0x10)
            self.floats(st + 24 * n + 8, [self.g.links(src)[n].factor * factor], f"{what}'s link")
        if not driven:
            st, _ = self.g.list_at(i, 0x08)
            self.floats(st + 4 * k, [self.g.attrs(i)[k] * factor], what)


def reshape(fx, shape: Shape, euler: Euler, bound: bool) -> int:
    """``shape`` on every staff graph of the staged ``fx.xbr`` document
    ``fx`` (module docstring): its children's transforms on a ``bound``
    end, else the end's own; the head pools' sprites and forces, and on
    the hands the smash rings.  Returns the fields written."""
    written = 0
    for g, ends, name in _graphs(bytes(fx.raw)):
        w = _Writes(fx, g, name)
        kids = _children(g)
        links: dict[tuple[int, int], list[tuple[int, int]]] = collections.defaultdict(list)
        for src, ro in enumerate(g.recs):
            for n, lk in enumerate(g.links(src) if ro is not None else ()):
                links[lk.dst, lk.dst_plug].append((src, n))
        inside: set[int] = set()
        for bind, e in ends.items():
            seen, stack = set(), list(kids[e])
            while stack:
                c = stack.pop()
                seen.add(c)
                stack += kids[c]
            for c in seen:
                if g.types[c] not in KNOWN:
                    raise ValueError(f"W6: {name}'s {bind} end holds a {g.types[c]} ({g.names[c]}), which no "
                                     "rule of the reshape covers (R3)")
                if g.types[c] == "transform" and g.xform_fields(c)["mode"] != 0:
                    raise ValueError(f"W6: {name}'s {g.names[c]} under its {bind} end inherits at mode "
                                     f"{g.xform_fields(c)['mode']}, not 0 (R1)")
            inside |= seen
            head = shape.heads[bind]
            h = HEAD_CENTRES.get(name, 0.0) if head.centred else 0.0
            p0 = np.array(head.at) - head.size * np.array(head.turn) @ (h * np.array(OUT[bind]))
            if bound:
                for c in kids[e]:
                    _child(w, g, c, head, p0, euler, links, f"{bind} end's {g.names[c]}")
            else:
                _place(w, g, e, head, p0, euler, f"{bind} end")
        if shape.kind == "hand" and name.startswith("fx_staff_smash"):
            rings = [i for i in sorted(inside) if g.types[i] == "transform" and (g.names[i] or "").startswith(RINGS)]
            if not rings:
                raise ValueError(f"W6: {name}'s ends hold no {' or '.join(RINGS)} transform to hide (R4)")
            for i in rings:
                for k in (7, 8, 9):
                    w.attr(i, k, 0.001, f"{g.names[i]}'s scale", links)
        pools = {}   # each pSystem: its renderer and its components
        for i, ro in enumerate(g.recs):
            if ro is not None and g.types[i] == "pSystem":
                st, n = g.list_at(i, 0x30)
                pools[i] = (struct.unpack_from("<i", g.s, ro + 0x20)[0],
                            [struct.unpack_from("<I", g.s, st + 4 * k)[0] for k in range(n)])
        heads = {i for i, (_, comps) in pools.items() if (shape.kind in ("point", "staff") or i not in inside)
                 and any(c in inside for c in comps) and all(c in inside for c in comps if 0 <= c < len(g.recs)
                                                             and g.types[c] in ("pEmitter", "pBurstEmitter"))}
        # fed by the ends alone; on the hands and the hoe those inside them keep the sprites the owner saw (D707)
        renderers = {r for i, (r, _) in pools.items() if i in heads} - {r for i, (r, _) in pools.items()
                                                                          if i not in heads}
        forces = {c for i in heads for c in pools[i][1] if c not in inside and 0 <= c < len(g.recs)
                  and g.types[c] == "pAccelerator"} - {c for i, (_, comps) in pools.items() if i not in heads
                                                       for c in comps}
        for r in sorted(renderers):
            if not 0 <= r < len(g.recs) or g.types[r] != "pRendererB":
                raise ValueError(f"W6: {name}'s pool fed by its staff ends draws with a "
                                 f"{g.types[r] if 0 <= r < len(g.recs) else 'missing record'}, not a pRendererB (R3)")
            for k in SIZES:
                w.attr(r, k, shape.sprites, f"{g.names[r]}'s size{k - 16}", links)
        for f in sorted(forces) if shape.forces != 1.0 else ():
            for k in MAGNITUDES:
                w.attr(f, k, shape.forces, f"{g.names[f]}'s magnitude", links)
        written += w.n
    return written


def _child(w: _Writes, g: Graph, c: int, head: Head, p0: np.ndarray, euler: Euler, links: dict, what: str) -> None:
    """A bound end's direct child ``c`` mapped by ``head``, ``y -> p0 +
    s RA y`` (``p0 = p - s RA h u``): its T, R, S and scale pivot's
    translation, a spin's plug and order, a scale link's factor (R1,
    R2)."""
    if g.types[c] != "transform":
        raise ValueError(f"W6: {w.graph}'s {what} is a {g.types[c]}, not a transform (R1)")
    x = g.xform_fields(c)
    plugs = {plug: links.get((c, plug), []) for plug in range(10)}
    if any(plugs[k] for k in (1, 2, 3)) or sum(len(plugs[k]) for k in (4, 5, 6)) > 1 or plugs[4] or plugs[5]:
        raise ValueError(f"W6: {w.graph}'s {what} is linked in translation or in rotation other than one "
                         "rotateZ (R2)")
    ra, s = np.array(head.turn, float), head.size
    r = np.array(euler.rotation(*x["r"], x["order"]), float)[:3, :3]
    order = x["order"]
    if plugs[6]:
        if euler.euler_axes[order][2] != 2:
            raise ValueError(f"W6: {w.graph}'s {what} spins on rotateZ inside its order {order} (R2)")
        z = ra @ np.array((0.0, 0.0, 1.0))
        k = int(np.argmax(np.abs(z)))
        order = next(o for o in range(6) if euler.euler_axes[o][2] == k and euler.euler_parity[o] == 1)
        (src, n), = plugs[6]
        st, _ = g.list_at(src, 0x10)
        if k != 2:
            if plugs[4 + k]:
                raise ValueError(f"W6: {w.graph}'s {what}'s spin can't move onto its linked plug {4 + k} (R2)")
            w.raw(st + 24 * n + 0x10, struct.pack("<H", 4 + k))
            w.raw(g.recs[c] + 0x6C, struct.pack("<I", order))
        if z[k] < 0:   # the axis lands reversed (RA z = -e_k): the same turn is the opposite angle
            w.floats(st + 24 * n + 8, [-g.links(src)[n].factor], f"{what}'s spin")
    t, sp, spt, rp, rpt = (np.array(x[f], float) for f in ("t", "sp", "spt", "rp", "rpt"))
    v = spt + sp - rp
    st, _ = g.list_at(c, 0x08)
    w.floats(st + 4, p0 + s * ra @ (t + rpt + rp) - rpt - rp, f"{what}'s translate")
    w.floats(st + 16, angles(euler, ra @ r, order), f"{what}'s rotate")
    w.floats(st + 28, [q * s for q in x["s"]], f"{what}'s scale")
    if np.any(v):
        w.floats(g.recs[c] + 0x38, s * v - sp + rp, f"{what}'s scale pivot translation")
    for k in range(3):
        for src, n in plugs[7 + k]:
            lst, _ = g.list_at(src, 0x10)
            w.floats(lst + 24 * n + 8, [g.links(src)[n].factor * s], f"{what}'s scale link")


def _place(w: _Writes, g: Graph, e: int, head: Head, p0: np.ndarray, euler: Euler, what: str) -> None:
    """An unbound end ``e`` (a point's) mapped whole, T(p) . RA . s . T(-h u)
    (``p0`` its translation), over its own translate, rotate and scale (no
    pivots, R1)."""
    x = g.xform_fields(e)
    if any(np.any(np.array(x[f])) for f in ("sp", "spt", "rp", "rpt")):
        raise ValueError(f"W6: {w.graph}'s {what} has pivots (R1)")
    ra, s = np.array(head.turn, float), head.size
    st, _ = g.list_at(e, 0x08)
    w.floats(st + 4, p0, f"{what}'s translate")
    w.floats(st + 16, angles(euler, ra, x["order"]), f"{what}'s rotate")
    w.floats(st + 28, (s, s, s), f"{what}'s scale")


__all__ = ["CLEAR", "GARRET4_REACH", "HAND", "HANDLE", "HEAD_CENTRES", "HOE", "PLAIN", "POINT", "RINGS", "SPRITES",
           "Head", "Shape", "angles", "blades", "hand_shape", "hoe_shape", "plain", "point_shape", "reshape",
           "staff_shape", "turn_onto"]
