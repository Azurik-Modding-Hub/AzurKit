"""The face a contact touched (Step TD.0): a level's collision triangles in memory, looked up by a point and the
contact normal the game stored.

The player's entity keeps the last contact's normal (+0xB8, :attr:`devkit.sim.obs.Obs.normal`: the classifier
0x85920 writes it) but no pointer to the face or its collision word, so :meth:`Faces.face` finds the face: of the
solid triangles (``W_SOLID`` in the word: the faces a body collides with; the water, push, damage and trigger
volumes are none, and neither is a toggled solid stored off) whose front normal (the ``(p1 - p0) x (p2 - p0)``
winding, floors up, as :class:`azurkit.tools.randomizer.draft.geometry.Level` reads them) agrees with the stored one
within ``tol_deg`` and that the point is in front of (a face stops motion only into its front), the nearest to
the point (the body centre: the body's 0.5 m radius and 1 m half-height put a touched face within about 1.12 m of
it), if one lies within ``radius``.  It answers the face's id (its index in the level's triangle
order), its owner, its collision word with the slippery, climbable and autoSpring bits
(:mod:`azurkit.tools.randomizer.art.collision`'s ``W_*``), its normal z and its distance.  None: no face fits, e.g. a contact
on an edge or a vertex, whose normal points from the contact point to the body [inferred], or one on a moving
platform away from its load-time place (a rig's faces are where the level file puts them).

Pure numpy over a 2-D grid of the triangles' XY bounds (:data:`CELL` m).  Positions stay in memory: a
:class:`Face` holds an id, bits and a distance, never a coordinate.  :class:`Volumes` (Step TD.4) answers the
trigger, push and damage volumes a point is in, by id.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import NamedTuple

import numpy as np

from azurkit.tools.randomizer.art import collision

CELL = 4.0          # the grid's cell, m
RADIUS = 1.5        # a touched face lies this near the body centre [inferred: the 0.5 m by 2 m body, with slack]
TOL_DEG = 2.0       # the stored normal and the face's agree within this [proposal]


class Face(NamedTuple):
    """One looked-up face: ``id`` its index in the level's triangle order, ``owner`` its owner's index (the
    level's ``tern`` owners, :func:`azurkit.tools.randomizer.art.collision.owners`), ``word`` its collision word, ``nz`` its
    unit normal's z and ``dist`` the point's distance to it (m)."""
    id: int
    owner: int
    word: int
    nz: float
    dist: float

    @property
    def slippery(self) -> bool:
        return bool(self.word & collision.W_SLIPPERY)

    @property
    def climbable(self) -> bool:
        return bool(self.word & collision.W_CLIMBABLE)

    @property
    def spring(self) -> bool:
        return bool(self.word & collision.W_AUTOSPRING)


class Faces:
    """A level's triangles ``tris`` (n, 3, 3), their collision ``words`` and ``owners`` (n each); the solid ones
    are indexed for :meth:`face`."""

    def __init__(self, tris, words, owners=None):
        self.P = np.asarray(tris, dtype=np.float64).reshape(-1, 3, 3)
        self.words = np.asarray(words, dtype=np.int64).reshape(-1)
        self.owners = np.zeros(len(self.P), np.int64) if owners is None else np.asarray(owners, np.int64)
        n = np.cross(self.P[:, 1] - self.P[:, 0], self.P[:, 2] - self.P[:, 0])
        ln = np.linalg.norm(n, axis=1, keepdims=True)
        self.n = np.where(ln > 0, n / np.maximum(ln, 1e-12), 0.0)   # a degenerate face matches no normal
        solid = np.nonzero(self.words & collision.W_SOLID)[0]
        Q = self.P[solid]
        lo, hi = np.floor(Q[:, :, :2].min(axis=1) / CELL), np.floor(Q[:, :, :2].max(axis=1) / CELL)
        self.x0, self.y0 = (lo.min(axis=0) if len(lo) else np.zeros(2)).astype(np.int64)
        lo, hi = lo.astype(np.int64) - (self.x0, self.y0), hi.astype(np.int64) - (self.x0, self.y0)
        self.ny = int(hi[:, 1].max()) + 1 if len(hi) else 1
        span = hi - lo + 1
        count = span[:, 0] * span[:, 1]
        tri = np.repeat(solid, count)
        k = np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)   # each face's cells, in order
        cx = np.repeat(lo[:, 0], count) + k // np.repeat(span[:, 1], count)
        cy = np.repeat(lo[:, 1], count) + k % np.repeat(span[:, 1], count)
        key = cx * self.ny + cy
        order = np.argsort(key, kind="stable")
        self.keys, start = np.unique(key[order], return_index=True)
        self.start = np.append(start, len(order))
        self.tri = tri[order]

    @classmethod
    def of_level(cls, lv) -> Faces:
        """A :class:`~azurkit.tools.randomizer.draft.geometry.Level`'s triangles."""
        return cls(lv.P, lv.tri_word, lv.tri_owner)

    @classmethod
    def read(cls, iso: Path, name: str) -> Faces:
        """``gamedata/<name>.xbr``'s collision (``geometry.Level.read``; the caller checks the image)."""
        from azurkit.tools.randomizer.draft.geometry import Level
        return cls.of_level(Level.read(iso, name))

    def near(self, p, r: float) -> np.ndarray:
        """The solid faces whose XY bounds' cells meet the square ``r`` around ``p``."""
        cell = lambda v, o: math.floor(v / CELL) - o   # noqa: E731
        xs = range(max(cell(p[0] - r, self.x0), 0), cell(p[0] + r, self.x0) + 1)
        ys = range(max(cell(p[1] - r, self.y0), 0), min(cell(p[1] + r, self.y0), self.ny - 1) + 1)
        want = np.array([ix * self.ny + iy for ix in xs for iy in ys], np.int64)
        if not len(want) or not len(self.keys):
            return np.zeros(0, np.int64)
        j = np.searchsorted(self.keys, want)
        j = j[(j < len(self.keys)) & (self.keys[np.minimum(j, len(self.keys) - 1)] == want)]
        parts = [self.tri[self.start[k]:self.start[k + 1]] for k in j]
        return np.unique(np.concatenate(parts)) if parts else np.zeros(0, np.int64)

    def face(self, point, normal, *, radius: float = RADIUS, tol_deg: float = TOL_DEG) -> Face | None:
        """The face the stored contact ``normal`` belongs to near ``point`` (the module docstring), or None."""
        nv = np.asarray(normal, dtype=np.float64)
        if not np.all(np.isfinite(nv)) or (ln := float(np.linalg.norm(nv))) == 0.0:
            return None
        cand = self.near(point, radius)
        cand = cand[self.n[cand] @ (nv / ln) >= math.cos(math.radians(tol_deg))]
        if not len(cand):
            return None
        d = _dist(np.asarray(point, dtype=np.float64), self.P[cand], self.n[cand])
        i = int(np.argmin(d))
        if d[i] > radius:
            return None
        t = int(cand[i])
        return Face(t, int(self.owners[t]), int(self.words[t]), float(self.n[t, 2]), float(d[i]))


def _dist(p: np.ndarray, T: np.ndarray, n: np.ndarray) -> np.ndarray:
    """The distance from ``p`` to each triangle of ``T`` (m, 3, 3) with unit normals ``n``: to its plane where
    the point's projection falls inside it, else to its nearest edge; infinite where ``p`` isn't in front of it."""
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    h = np.einsum("ij,ij->i", p - a, n)
    q = p - h[:, None] * n
    inside = np.ones(len(T), bool)
    for u, v in ((a, b), (b, c), (c, a)):
        inside &= np.einsum("ij,ij->i", np.cross(v - u, q - u), n) >= 0
    edge = np.full(len(T), np.inf)
    for u, v in ((a, b), (b, c), (c, a)):
        e = v - u
        t = np.clip(np.einsum("ij,ij->i", p - u, e) / np.maximum(np.einsum("ij,ij->i", e, e), 1e-12), 0.0, 1.0)
        edge = np.minimum(edge, np.linalg.norm(p - (u + t[:, None] * e), axis=1))
    return np.where(h > 0, np.where(inside, h, edge), np.inf)


class Volumes:
    """A level's trigger, push and damage volumes (Step TD.4's census: a site with no solid face, an exit's
    trigger or a push volume, is tried when a body centre enters it): each a non-solid owner's closed mesh, known
    by its lowest face id; :meth:`holding` the ones whose mesh spans a point in its column (a face of it straight
    above and one straight below: either winding).  Positions stay in memory."""

    def __init__(self, P, meshes):
        self.V = [np.asarray(P, dtype=np.float64)[m] for m in meshes]
        self.ids = [int(np.min(m)) for m in meshes]
        self.lo = np.array([V.reshape(-1, 3).min(axis=0) for V in self.V]).reshape(-1, 3)
        self.hi = np.array([V.reshape(-1, 3).max(axis=0) for V in self.V]).reshape(-1, 3)

    @classmethod
    def of_level(cls, lv) -> Volumes:
        """A :class:`~azurkit.tools.randomizer.draft.geometry.Level`'s damage, push and trigger owners."""
        from azurkit.tools.randomizer.draft.geometry import CAT_DAMAGE, CAT_PUSH, CAT_TRIGGER
        return cls(lv.P, [t for oi, o in enumerate(lv.owners)
                          if o["cat"] in (CAT_DAMAGE, CAT_PUSH, CAT_TRIGGER) and len(t := lv.tris_of(oi))])

    def holding(self, point) -> list[int]:
        """The volumes (their ids) whose mesh spans ``point`` (the class docstring)."""
        p = np.asarray(point, dtype=np.float64)
        k = np.nonzero((self.lo <= p).all(axis=1) & (p <= self.hi).all(axis=1))[0]
        return [self.ids[i] for i in k.tolist() if _spans(self.V[i], p)]


def _spans(V: np.ndarray, p: np.ndarray) -> bool:
    """Whether a triangle of ``V`` (n, 3, 3) lies straight above ``p`` and one straight below (or at it)."""
    a, b, c = V[:, 0], V[:, 1], V[:, 2]
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    ok = np.abs(d) > 1e-12
    d = np.where(ok, d, 1.0)
    l1 = ((b[:, 1] - c[:, 1]) * (p[0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (p[1] - c[:, 1])) / d
    l2 = ((c[:, 1] - a[:, 1]) * (p[0] - c[:, 0]) + (a[:, 0] - c[:, 0]) * (p[1] - c[:, 1])) / d
    l3 = 1.0 - l1 - l2
    m = ok & (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
    z = (l1 * a[:, 2] + l2 * b[:, 2] + l3 * c[:, 2])[m]
    return bool((z >= p[2]).any() and (z <= p[2]).any())
