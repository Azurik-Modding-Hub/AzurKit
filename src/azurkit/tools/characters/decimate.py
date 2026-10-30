"""A LOD's mesh cut to fewer triangles (Step 2.166a, D537: the decimator).

:func:`decimate` takes a :class:`~azurik_mod.assets.body_codec.Lod` and
returns a new one whose ``bmsh`` is ``None`` (the writer,
:func:`~azurik_mod.assets.body_codec.write_asset`, appends it), drawing
at most ``ratio`` of the input's triangles, or as few as stay within
``max_error`` metres, whichever stops first; :func:`lod_chain` cuts LOD k
from LOD k-1.  Pure Python with no dependency, deterministic: every order
is by index, so no hash order reaches the output.

- **Points and wedges.**  A group's vertices are welded by their float32
  position; a point's distinct vertices are its wedges (a UV seam, a
  hard normal, a two-sided part's back).
- **Half-edge collapse** P -> Q: Q keeps its place, and each wedge u of P
  becomes the wedge the triangles on the edge PQ use at Q.  So every
  output vertex is an input vertex of its group (its weights, slot
  bytes, normal and UV as stored), no palette gains a bone, and a seam
  moves only along itself with its twin edge: a wedge of P that no
  triangle on PQ maps, or that one maps to two wedges, refuses the
  collapse, so UVs never tear.
- **Locked points** never move (they may take a collapse): a position
  another group holds too (a material border, or a palette split of one
  material), an edge three triangles share or two of one winding, a fan
  that isn't one disc or one open fan, a triangle with two corners at
  one point, where a two-sided part meets one-sided triangles, and a
  two-sided part whose twins disagree.
- **Borders** (an edge one triangle holds: a hem, cut cloth, a torn
  edge) collapse only along themselves.
- **Two-sided parts**: a triangle whose points are another's in reverse
  is that one's back (female_2 has 354).  The backs are taken out, the
  fronts simplified once, and each surviving front's back drawn again from
  its corners' twins (the back's wedge at each point), so both sides
  match.
- **Refused collapses**: P's and Q's neighbours shared other than across
  PQ's triangles (the link condition, which keeps the surface a
  manifold), a triangle doubled, a triangle whose normal turns to a dot of
  :data:`MIN_DOT` or less with its old one (a flip or a sliver) or that
  shrinks to nothing.
- **Cost** (the order only): Garland-Heckbert quadrics (each triangle's
  plane by its area, each border edge's perpendicular plane at
  :data:`BORDER_WEIGHT` times its length squared), as a mean squared
  distance in metres, plus a skin term: the L1 distance of each wedge's
  weights by bone from its target's, times the edge's length squared,
  times :data:`SKIN_K`.  The cheapest collapse goes first, ties by point
  index.
- **Stops**: at ``ratio`` of the drawn triangles, or when no collapse is
  left that keeps every input position within ``max_error`` metres of
  the cut surface (:func:`azurik_mod.assets.lods.pixel_error`: pixels at
  a distance in metres).  Each input position is held by a live triangle
  it lies within ``max_error`` of (at first one of its own); a collapse
  that moves or drops a triangle finds each position that triangle held
  a triangle of the new fan, or of the fans around it, within
  ``max_error``, or is refused (a measured bound, not the quadric's mean).

A group left with no triangle is dropped.  Nothing here prints a byte or
a coordinate.
"""

from __future__ import annotations

import heapq
import math
import pickle
from collections.abc import Sequence

from azurkit.tools.characters.body_codec import Group, Lod, Vertex, code_entry, read_asset, slot_code, write_asset

BORDER_WEIGHT = 10.0
"""A border edge's plane weight, per metre squared of its length (a
triangle's plane weighs its area)."""
SKIN_K = 0.5
"""The skin term's factor: a collapse between wedges skinned wholly to
different bones (L1 distance 2) costs as much as moving the length of
its edge."""
MIN_DOT = 0.2
"""The least cosine between a moved triangle's old and new normals."""
_TINY = 1e-24


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _plane(n, d: float, w: float) -> list[float]:
    """The quadric of the plane n.x + d = 0 (n a unit normal) at weight w."""
    a, b, c = n
    return [w * a * a, w * a * b, w * a * c, w * a * d, w * b * b, w * b * c, w * b * d, w * c * c, w * c * d,
            w * d * d, w]


def _add(q: list[float], r: Sequence[float]) -> None:
    for i in range(11):
        q[i] += r[i]


def _error(q: Sequence[float], x) -> float:
    """The quadric's weighted squared distance at ``x``, over its weight."""
    if q[10] <= 0.0:
        return 0.0
    X, Y, Z = x
    e = (q[0] * X * X + q[4] * Y * Y + q[7] * Z * Z + q[9]
         + 2.0 * (q[1] * X * Y + q[2] * X * Z + q[3] * X + q[5] * Y * Z + q[6] * Y + q[8] * Z))
    return max(e, 0.0) / q[10]


def _seg2(x, a, b) -> float:
    """The squared distance from ``x`` to the segment ab."""
    ab, ax = _sub(b, a), _sub(x, a)
    ll = _dot(ab, ab)
    k = 0.0 if ll <= 0.0 else min(max(_dot(ax, ab) / ll, 0.0), 1.0)
    d = (ax[0] - k * ab[0], ax[1] - k * ab[1], ax[2] - k * ab[2])
    return _dot(d, d)


def _tri2(x, a, b, c) -> float:
    """The squared distance from ``x`` to the triangle abc: its plane's
    where ``x`` falls inside it, else the nearest edge's."""
    ab, ac, ax = _sub(b, a), _sub(c, a), _sub(x, a)
    n = _cross(ab, ac)
    nn = _dot(n, n)
    if nn > _TINY:
        d00, d01, d11, d20, d21 = _dot(ab, ab), _dot(ab, ac), _dot(ac, ac), _dot(ax, ab), _dot(ax, ac)
        s = (d11 * d20 - d01 * d21) / nn
        t = (d00 * d21 - d01 * d20) / nn
        if s >= 0.0 and t >= 0.0 and s + t <= 1.0:
            h = _dot(ax, n)
            return h * h / nn
    return min(_seg2(x, a, b), _seg2(x, b, c), _seg2(x, c, a))


def _turns(a: tuple[int, int, int], b: tuple[int, int, int]) -> bool:
    """``b`` is ``a``'s three points in the reverse winding."""
    rev = (a[0], a[2], a[1])
    return b in (rev, rev[1:] + rev[:1], rev[2:] + rev[:2])


def drawn(lod: Lod) -> int:
    """The triangles ``lod`` draws."""
    return sum(len(g.triangles) for g in lod.groups)


class _Work:
    """One decimation's state (the module docstring)."""

    def __init__(self, lod: Lod):
        self.groups = lod.groups
        verts, vgroup, tris = [], [], []
        for g, grp in enumerate(lod.groups):
            base = len(verts)
            verts += grp.vertices
            vgroup += [g] * len(grp.vertices)
            tris += [[base + t[0], base + t[1], base + t[2]] for t in grp.triangles]
        self.verts, self.vgroup, self.tris = verts, vgroup, tris
        self.tgroup = [g for g, grp in enumerate(lod.groups) for _ in grp.triangles]
        used = sorted({c for t in tris for c in t})
        key: dict = {}
        vpoint = [-1] * len(verts)
        pos, owners = [], {}
        for v in used:
            p = verts[v].position
            k = key.get((vgroup[v], p))
            if k is None:
                k = key[(vgroup[v], p)] = len(pos)
                pos.append(p)
            vpoint[v] = k
            owners.setdefault(p, set()).add(vgroup[v])
        n = len(pos)
        self.vpoint, self.pos = vpoint, pos
        locked = [len(owners[p]) > 1 for p in pos]
        self.tp = [tuple(vpoint[c] for c in t) for t in tris]
        nt = len(tris)

        # two-sided parts: a triangle and its reverse twin; any other repeat locks its points
        byset: dict = {}
        for t, pts in enumerate(self.tp):
            if len(set(pts)) == 3:
                byset.setdefault(frozenset(pts), []).append(t)
            else:
                for p in pts:
                    locked[p] = True
        self.back = {}
        is_back = [False] * nt
        for ts in byset.values():
            if len(ts) == 2 and _turns(self.tp[ts[0]], self.tp[ts[1]]):
                self.back[ts[0]] = ts[1]
                is_back[ts[1]] = True
            elif len(ts) > 1:
                for p in self.tp[ts[0]]:
                    locked[p] = True
        twin: dict[int, int] = {}
        bad: set[int] = set()
        self.bcorner = {}
        for f, b in self.back.items():
            at = {vpoint[c]: c for c in tris[b]}
            bc = tuple(at[vpoint[c]] for c in tris[f])
            self.bcorner[f] = bc
            for c, d in zip(tris[f], bc):
                if twin.setdefault(c, d) != d:
                    bad.add(c)
                    locked[vpoint[c]] = True
        self.twin = {c: d for c, d in twin.items() if c not in bad}
        self.is_back = is_back
        self.orig = [tuple(t) for t in tris]

        self.alive = [not b for b in is_back]
        self.fan: list[set[int]] = [set() for _ in range(n)]
        two, one = [False] * n, [False] * n
        for t in range(nt):
            if self.alive[t]:
                for p in set(self.tp[t]):
                    self.fan[p].add(t)
                    if t in self.back:
                        two[p] = True
                    else:
                        one[p] = True
        self.two = [a and not b for a, b in zip(two, one)]
        for p in range(n):
            if two[p] and one[p]:
                locked[p] = True

        # edges: non-manifold ones lock, open ones are borders
        uses: dict = {}
        for t in range(nt):
            if self.alive[t] and len(set(self.tp[t])) == 3:
                a, b, c = self.tp[t]
                for e in ((a, b), (b, c), (c, a)):
                    uses.setdefault((min(e), max(e)), []).append(e)
        self.border = [False] * n
        open_edges = set()
        for (x, y), lst in uses.items():
            if len(lst) > 2 or (len(lst) == 2 and lst[0] == lst[1]):
                locked[x] = locked[y] = True
            elif len(lst) == 1:
                self.border[x] = self.border[y] = True
                open_edges.add(lst[0])
        for p in range(n):
            if self.fan[p] and not locked[p] and not self._one_ring(p):
                locked[p] = True
        self.locked = locked

        self.quad = [[0.0] * 11 for _ in range(n)]
        for t in range(nt):
            if not self.alive[t] or len(set(self.tp[t])) != 3:
                continue
            a, b, c = (pos[p] for p in self.tp[t])
            nv = _cross(_sub(b, a), _sub(c, a))
            ln = math.sqrt(_dot(nv, nv))
            if ln <= 0.0:
                continue
            nn = (nv[0] / ln, nv[1] / ln, nv[2] / ln)
            q = _plane(nn, -_dot(nn, a), ln / 2.0)
            for p in self.tp[t]:
                _add(self.quad[p], q)
            x, y, z = self.tp[t]
            for e in ((x, y), (y, z), (z, x)):
                if e in open_edges:
                    ev = _sub(pos[e[1]], pos[e[0]])
                    m = _cross(ev, nn)
                    lm = math.sqrt(_dot(m, m))
                    if lm <= 0.0:
                        continue
                    m = (m[0] / lm, m[1] / lm, m[2] / lm)
                    q = _plane(m, -_dot(m, pos[e[0]]), BORDER_WEIGHT * _dot(ev, ev))
                    _add(self.quad[e[0]], q)
                    _add(self.quad[e[1]], q)
        self.norm = [self._normal(t) for t in range(nt)]
        self.skins: dict[int, dict[int, float]] = {}
        self.count = sum(1 + (t in self.back) for t in range(nt) if self.alive[t])
        self.point_alive = [bool(f) for f in self.fan]
        self.held: dict[int, set[int]] | None = None

    def hold(self) -> None:
        """Each input position held by its lowest live triangle (it is that
        triangle's corner), for :meth:`rehome`."""
        self.held = {}
        for p, f in enumerate(self.fan):
            if f:
                self.held.setdefault(min(f), set()).add(p)

    def rehome(self, p: int, q: int, limit2: float) -> dict[int, tuple[int, int]] | None:
        """Where each input position a triangle of ``p``'s fan holds lies
        after the collapse p -> q, as {position: (old triangle, new)} for
        those that move: on its own triangle, moved, while that stays
        within ``limit2`` (a squared distance), else the nearest of
        ``q``'s new fan, else of the fans around it, ties by index;
        ``None`` when one has no triangle within ``limit2``."""
        fp = self.fan[p]
        on = fp & self.fan[q]
        pos, tp, held = self.pos, self.tp, self.held
        moved = {t: tuple(pos[q] if x == p else pos[x] for x in tp[t]) for t in fp - on}
        near = sorted((self.fan[q] - on) | moved.keys())
        wide: list[int] | None = None
        out: dict[int, tuple[int, int]] = {}
        for t in sorted(fp):
            for i in sorted(held.get(t, ())):
                x = pos[i]
                if t in moved and _tri2(x, *moved[t]) <= limit2:
                    continue
                best = min(((_tri2(x, *(moved.get(u) or [pos[y] for y in tp[u]])), u) for u in near),
                           default=(math.inf, -1))
                if best[0] > limit2:
                    if wide is None:
                        ring = {q if y == p else y for u in near for y in tp[u]} - {q}
                        wide = sorted({u for y in ring for u in self.fan[y]} - on - set(near))
                    best = min([(_tri2(x, *(pos[y] for y in tp[u])), u) for u in wide] + [best])
                    if best[0] > limit2:
                        return None
                out[i] = (t, best[1])
        return out

    def _normal(self, t: int):
        a, b, c = (self.pos[x] for x in self.tp[t])
        return _cross(_sub(b, a), _sub(c, a))

    def _one_ring(self, p: int) -> bool:
        """``p``'s triangles make one closed disc (an inner point) or one
        open fan (a border point)."""
        nxt: dict[int, int] = {}
        for t in self.fan[p]:
            a, b, c = self.tp[t]
            x, y = (b, c) if a == p else (c, a) if b == p else (a, b)
            if x in nxt:
                return False
            nxt[x] = y
        starts = set(nxt) - set(nxt.values())
        if self.border[p]:
            if len(starts) != 1:
                return False
            x = next(iter(starts))
        else:
            if starts:
                return False
            x = min(nxt)
        first, steps = x, 0
        while x in nxt and steps <= len(nxt):
            x = nxt[x]
            steps += 1
            if x == first:
                break
        return steps == len(self.fan[p])

    def skin(self, v: int) -> dict[int, float]:
        s = self.skins.get(v)
        if s is None:
            s = self.skins[v] = self.verts[v].skin(self.groups[self.vgroup[v]].palette)
        return s

    def neighbours(self, p: int) -> set[int]:
        out = {x for t in self.fan[p] for x in self.tp[t]}
        out.discard(p)
        return out

    def wedge_map(self, p: int, q: int) -> dict[int, int] | None:
        """Each wedge of ``p`` and the one the triangles on the edge pq use
        at ``q``, or ``None`` when one has no such triangle or two (the
        collapse would tear a seam), the edge is gone, isn't a border
        edge from a border point, or ``p`` is locked."""
        if self.locked[p] or not (self.point_alive[p] and self.point_alive[q]):
            return None
        fp = self.fan[p]
        on = fp & self.fan[q]
        if len(on) != (1 if self.border[p] else 2):
            return None
        tris, vpoint = self.tris, self.vpoint
        wedges: dict[int, int] = {}
        for t in on:
            u = v = -1
            for c in tris[t]:
                if vpoint[c] == p:
                    u = c
                elif vpoint[c] == q:
                    v = c
            if wedges.setdefault(u, v) != v:
                return None
        for t in fp:
            for c in tris[t]:
                if vpoint[c] == p and c not in wedges:
                    return None
        if self.two[p] and any(v not in self.twin for v in wedges.values()):
            return None
        return wedges

    def cost(self, p: int, q: int, wedges: dict[int, int]) -> float:
        """The collapse p -> q's cost (the module docstring)."""
        qp, qq = self.quad[p], self.quad[q]
        xp, xq = self.pos[p], self.pos[q]
        cost = _error([a + b for a, b in zip(qp, qq)], xq)
        d = _sub(xp, xq)
        length2 = _dot(d, d)
        if length2 > 0.0:
            worst = 0.0
            for u, v in wedges.items():
                su, sv = self.skin(u), self.skin(v)
                worst = max(worst, sum(abs(su.get(b, 0.0) - sv.get(b, 0.0)) for b in sorted(su.keys() | sv.keys())))
            cost += SKIN_K * worst * length2
        return cost

    def allowed(self, p: int, q: int) -> bool:
        """The collapse p -> q keeps the surface a manifold, doubles no
        triangle and turns none past :data:`MIN_DOT` or to nothing."""
        fp, fq = self.fan[p], self.fan[q]
        on = fp & fq
        tp = self.tp
        opposite = {x for t in on for x in tp[t]} - {p, q}
        if self.neighbours(p) & self.neighbours(q) != opposite:
            return False
        rest = fp - on
        if not rest:
            return True
        there = {frozenset(tp[t]) for t in fq - on}
        pos, norm = self.pos, self.norm
        xq = pos[q]
        for t in rest:
            pts = tp[t]
            if frozenset(q if x == p else x for x in pts) in there:
                return False
            a, b, c = (xq if x == p else pos[x] for x in pts)
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            nn = nx * nx + ny * ny + nz * nz
            if nn <= _TINY:
                return False
            ox, oy, oz = norm[t]
            no = ox * ox + oy * oy + oz * oz
            if no > _TINY and ox * nx + oy * ny + oz * nz <= MIN_DOT * math.sqrt(no * nn):
                return False
        return True

    def collapse(self, p: int, q: int, wedges: dict[int, int], moves: dict[int, tuple[int, int]] | None) -> None:
        on = self.fan[p] & self.fan[q]
        for i, (t, u) in sorted((moves or {}).items()):
            self.held[t].discard(i)
            self.held.setdefault(u, set()).add(i)
        for t in on:
            self.alive[t] = False
            self.count -= 1 + (t in self.back)
            for x in self.tp[t]:
                self.fan[x].discard(t)
        for t in self.fan[p]:
            self.tris[t] = [wedges.get(c, c) for c in self.tris[t]]
            self.tp[t] = tuple(q if x == p else x for x in self.tp[t])
            self.norm[t] = self._normal(t)
            self.fan[q].add(t)
        self.fan[p] = set()
        self.point_alive[p] = False
        _add(self.quad[q], self.quad[p])

    def lod(self) -> Lod:
        """The surviving triangles as a :class:`Lod` (module docstring)."""
        per: list[list[tuple[int, int, int]]] = [[] for _ in self.groups]
        front = {b: f for f, b in self.back.items()}
        for t, g in enumerate(self.tgroup):
            if self.is_back[t]:
                f = front[t]
                if not self.alive[f]:
                    continue
                if tuple(self.tris[f]) == self.orig[f]:
                    per[g].append(self.orig[t])
                else:
                    b = [d if c == o else self.twin[c] for c, o, d in zip(self.tris[f], self.orig[f], self.bcorner[f])]
                    per[g].append((b[0], b[2], b[1]))
            elif self.alive[t]:
                per[g].append(tuple(self.tris[t]))
        out = []
        for g, grp in enumerate(self.groups):
            tris = per[g]
            if tris:
                keep = sorted({c for t in tris for c in t})
                local = {c: n for n, c in enumerate(keep)}
                out.append(Group(list(grp.palette), [self.verts[c] for c in keep],
                                 [tuple(local[c] for c in t) for t in tris], grp.material, grp.fvf, grp.vb, grp.pb))
        return Lod(None, out)


def decimate(lod: Lod, ratio: float | None = None, *, max_error: float | None = None) -> Lod:
    """``lod`` cut to at most ``ratio`` of its drawn triangles, or as far
    as every input position stays within ``max_error`` metres of the cut
    surface (the module docstring), as a new :class:`Lod` with ``bmsh``
    ``None``; ``lod`` is unchanged.  :class:`ValueError` for neither
    stop, or one that isn't a finite number of at least 0."""
    for name, x in (("ratio", ratio), ("max_error", max_error)):
        if x is not None and not (math.isfinite(x) and x >= 0):
            raise ValueError(f"decimate: {name} {x!r} isn't a finite number of at least 0")
    if ratio is None and max_error is None:
        raise ValueError("decimate: give a ratio, a max_error or both to stop at")
    work = _Work(lod)
    target = -1.0 if ratio is None else ratio * work.count
    limit = None if max_error is None else max_error * max_error
    if limit is not None:
        work.hold()
    heap: list[tuple[float, int, int]] = []
    blocked: dict[int, set[int]] = {}

    def offer(p: int, q: int) -> None:
        wedges = work.wedge_map(p, q)
        if wedges is None:
            blocked.setdefault(p, set()).add(q)
        else:
            heapq.heappush(heap, (work.cost(p, q, wedges), p, q))

    for p in range(len(work.pos)):
        if work.point_alive[p] and not work.locked[p]:
            for q in sorted(work.neighbours(p)):
                offer(p, q)
    while heap and work.count > target:
        cost, p, q = heapq.heappop(heap)
        if not (work.point_alive[p] and work.point_alive[q]):
            continue
        wedges = work.wedge_map(p, q)
        if wedges is None or not work.allowed(p, q):
            blocked.setdefault(p, set()).add(q)
            continue
        now = work.cost(p, q, wedges)
        if now > cost * (1 + 1e-9) + 1e-30:
            heapq.heappush(heap, (now, p, q))
            continue
        moves = None if limit is None else work.rehome(p, q, limit)
        if limit is not None and moves is None:
            blocked.setdefault(p, set()).add(q)
            continue
        work.collapse(p, q, wedges, moves)
        blocked.pop(p, None)
        ring = sorted(work.neighbours(q))
        for x in ring:
            offer(q, x)
            offer(x, q)
        for x in ring:          # what a changed neighbourhood may now allow
            for y in sorted(blocked.pop(x, set()) - {q}):
                offer(x, y)
    return work.lod()


SHADOW_RATIO = 0.05
"""A shadow LOD's share of LOD 0's triangles (Step 2.166c, D115): a
realtime shadow draws a silhouette, so the cut is coarse and its load
runs small (the X.68 audit's 5 %), as far as :data:`SHADOW_ERROR` lets
it go (booblord v4 stops at 0.196: her two-sided cloth's non-manifold
edges lock half its points)."""
SHADOW_ERROR = 0.02
"""How far (model units, metres at scale 1) a shadow LOD may leave any
point of LOD 0 (Step 2.166c, D115): about a texel of garret4's 2.5 m
``shadowSize`` [inferred: the shadow texture's size isn't read]; an
unbounded cut to the ratio moved booblord's surface 70 cm."""
SHADOW_MIN = 20_000
"""The LOD 0 triangles past which a one-LOD body the player wears takes a
shadow LOD unless its recipe says ``"lods": {"shadow": false}`` (Step
2.166c, D115): over twice every vanilla body's (balthazar_spider's 8,615
the most of a one-LOD one), so no vanilla body takes one."""


def by_material(lod: Lod, *, weld: bool = False) -> Lod:
    """``lod`` with the groups of one material (and FVF and D3D headers)
    as one, in first-group order: the palettes joined, each vertex's slot
    codes renamed into the joined one (:func:`~azurik_mod.assets.body_codec.slot_code`,
    past 31 entries until the write's regroup splits it again) and the
    vertices equal after that kept once, so a palette split (or the push
    buffer's cap) locks no border for :func:`decimate`; with ``weld``
    one vertex a position (its first), so no seam, hard normal or facet
    holds a collapse back either (a mesh drawn only as a shadow).  A
    triangle left with two corners on one vertex (no area) is dropped."""
    merged: dict = {}
    for g in lod.groups:
        key = (g.material, g.fvf, g.vb, g.pb)
        palette, verts, index, tris = merged.setdefault(key, ([], [], {}, []))
        palette += [b for b in g.palette if b not in palette]
        local = []
        for v in g.vertices:
            codes = tuple(slot_code(palette.index(g.palette[code_entry(c)])) if w > 0 else 0
                          for w, c in zip(v.weights, v.slots))
            v = Vertex(v.position, v.weights, v.normal, v.uv, v.extra, codes)
            k = v.position if weld else v
            if k not in index:
                index[k] = len(verts)
                verts.append(v)
            local.append(index[k])
        tris += [t for t in ((local[a], local[b], local[c]) for a, b, c in g.triangles) if len(set(t)) == 3]
    return Lod(lod.bmsh, [Group(p, v, t, *key) for key, (p, v, _, t) in merged.items()])


_AHEAD: list = [None]
"""The cut :func:`cut_ahead` or :func:`chain_ahead` started: its job and input's pickle, its future and its source."""


def _cut(shared: tuple, lod: Lod) -> Lod:
    """:func:`decimate` of ``lod`` at ``shared``'s ratio and max_error, in a worker process (:func:`cut_ahead`)."""
    ratio, max_error = shared
    return decimate(lod, ratio, max_error=max_error)


def _chain(shared: tuple, lod: Lod) -> list[Lod]:
    """:func:`lod_chain` of ``lod`` at ``shared``'s ratios and max_errors, in a worker process (:func:`chain_ahead`)."""
    ratios, max_errors = shared
    return lod_chain(lod, ratios, max_errors=max_errors)


def _ahead_key(job, lod: Lod, shared: tuple) -> bytes:
    return pickle.dumps((job.__name__, lod, shared), pickle.HIGHEST_PROTOCOL)


def _start(job, shared: tuple, lod: Lod, source: object) -> None:
    from azurkit.tools.characters import pool

    _AHEAD[0] = (_ahead_key(job, lod, shared), pool.later(pool.each, job, shared, [lod], None, 1), source)


def _taken(job, shared: tuple, lod: Lod):
    """The kept cut of ``lod`` by ``job`` at ``shared``, or ``job``'s own now; the kept one is let go either way."""
    ahead, _AHEAD[0] = _AHEAD[0], None
    if ahead is not None and ahead[0] == _ahead_key(job, lod, shared):
        return ahead[1].result()[0]
    return job(shared, lod)


def cut_ahead(lod0: Lod, ratio: float = SHADOW_RATIO, max_error: float | None = SHADOW_ERROR, *,
              source: object = None) -> None:
    """:func:`shadow_lod`'s cut of ``lod0`` started in a worker process
    (Step 2.179: booblord_high's was a sixth of her build), so the build
    works on while it runs: the next :func:`shadow_lod` of a LOD 0 that
    pickles as this one's at the same ``ratio`` and ``max_error`` takes it
    (any other cuts its own).  One is kept, with ``source`` (what the
    caller read ``lod0`` from, :func:`ahead_of`)."""
    _start(_cut, (ratio, max_error), by_material(lod0, weld=True), source)


def chain_ahead(lod0: Lod, ratios: Sequence[float], max_errors: Sequence[float | None] | None = None, *,
                source: object = None) -> None:
    """:func:`screen_lods`' cuts of ``lod0`` started in a worker process
    as :func:`cut_ahead` starts a shadow's (Step 2.166d: booblord_high's
    took 31-50 s): the next :func:`screen_lods` of a LOD 0 that pickles as
    this one's at the same ``ratios`` and ``max_errors`` takes them."""
    _start(_chain, (tuple(ratios), None if max_errors is None else tuple(max_errors)), by_material(lod0), source)


def ahead_of(source: object) -> bool:
    """Whether the cut :func:`cut_ahead` keeps, not yet taken, was started from ``source`` itself."""
    return _AHEAD[0] is not None and source is not None and _AHEAD[0][2] is source


def shadow_lod(characters_xbr: bytes, body: str, ratio: float = SHADOW_RATIO,
               max_error: float | None = SHADOW_ERROR) -> tuple[bytes, Lod]:
    """``characters_xbr`` with the one-LOD body ``body``'s LOD 0, its
    groups joined by material and welded (:func:`by_material`: its seams'
    UVs and normals are no shadow's), cut to ``ratio`` of its triangles
    or as far as every point stays within ``max_error`` (:func:`decimate`,
    or the cut :func:`cut_ahead` started of the same LOD)
    and written as its LOD 1
    (:func:`~azurik_mod.assets.body_codec.write_asset` appends it,
    regrouped), and that LOD: what a realtime shadow draws
    (:data:`~azurik_mod.assets.lods.SHADOW_LOD`) in LOD 0's place.
    :class:`ValueError` for a body with more LODs."""
    asset = read_asset(characters_xbr, body)
    if len(asset.lods) != 1:
        raise ValueError(f"shadow LOD: {asset.name} has {len(asset.lods)} LODs, and its shadow draws its own LOD 1")
    asset.lods.append(_taken(_cut, (ratio, max_error), by_material(asset.lods[0], weld=True)))
    return write_asset(characters_xbr, asset), asset.lods[1]


def screen_lods(characters_xbr: bytes, body: str, ratios: Sequence[float],
                max_errors: Sequence[float | None] | None = None) -> tuple[bytes, list[Lod]]:
    """``characters_xbr`` with the body ``body``'s LODs past LOD 0 cut anew
    from its LOD 0 (Step 2.166d, W39): its groups joined by material
    (:func:`by_material`, so no palette split locks a border; its seams,
    UVs and normals kept), LOD k at most ``ratios[k-1]`` of its triangles
    or within ``max_errors[k-1]`` metres of LOD k-1 (:func:`lod_chain`),
    and written after LOD 0
    (:func:`~azurik_mod.assets.body_codec.write_asset` appends each,
    regrouped; the old ones stay in the file unreferenced); no ``ratios``
    drops them.  The cuts :func:`chain_ahead` started of the same LOD 0
    are taken.  The file and the new LODs."""
    asset = read_asset(characters_xbr, body)
    shared = (tuple(ratios), None if max_errors is None else tuple(max_errors))
    cuts = _taken(_chain, shared, by_material(asset.lods[0])) if ratios else []
    asset.lods[1:] = cuts
    return write_asset(characters_xbr, asset), cuts


def vanilla_shares(characters_xbr: bytes, body: str) -> list[float]:
    """Each of the body ``body``'s LODs past LOD 0 as a share of its LOD
    0's triangles in ``characters_xbr`` (the image's): the ratios W39 cuts
    an edited body's own LODs anew at (Step 2.166d); none for a one-LOD
    body."""
    lods = read_asset(characters_xbr, body).lods
    return [drawn(lod) / drawn(lods[0]) for lod in lods[1:]]


def lod_chain(lod0: Lod, ratios: Sequence[float], *, max_errors: Sequence[float | None] | None = None) -> list[Lod]:
    """LODs 1.. of ``lod0``: LOD k at most ``ratios[k-1]`` of LOD 0's
    triangles (or within ``max_errors[k-1]`` metres of LOD k-1), each cut
    from the one before (:func:`decimate`)."""
    errors = list(max_errors) if max_errors is not None else [None] * len(ratios)
    if len(errors) != len(ratios):
        raise ValueError(f"lod_chain: {len(ratios)} ratios but {len(errors)} errors")
    n0, prev, out = drawn(lod0), lod0, []
    for r, e in zip(ratios, errors):
        have = drawn(prev)
        prev = decimate(prev, None if r is None else (r * n0 / have if have else 0.0), max_error=e)
        out.append(prev)
    return out


__all__ = ["BORDER_WEIGHT", "MIN_DOT", "SHADOW_ERROR", "SHADOW_MIN", "SHADOW_RATIO", "SKIN_K", "by_material",
           "chain_ahead", "cut_ahead", "decimate", "drawn", "lod_chain", "screen_lods", "shadow_lod", "vanilla_shares"]
