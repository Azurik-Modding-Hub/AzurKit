"""The reach engine's pair stage (Step R2.19g2, PLAN-v3's g2; D845): the truth set's frame of zone pairs and its pair
aim, shared by ``devkit/reach/reach_truth.py`` (R, the reference search) and ``devkit/reach/reach_engine.py sample --pairs``
(a pass-1 aim at each frame pair the engine's graph lacks at its kit).

The frame (:func:`frame`, Step R2.19c; written once a level, zoning and seed, to the private
``reach-truth/<level>/truth``): the ordered zone pairs inside a widened envelope per kit (``k0``: rank 0, no
shield; ``air3``: the shield's rank 3, Flaps 5): some pair of the two zones' border points (the logic walk's border
samples, the swim water's surface, on a :data:`BIN_M` grid) lies within :data:`WIDEN` x the frame-perfect running
travel at their height difference (``physics.Envelope.travel``), the drop at most :data:`DROP_M` and the rise at most
the kit's rise + :data:`RISE_PLUS_M` (above the highest rise the envelope has a travel at, that travel).  Its
strata: ``dm`` (a derived jump or flap edge of the pair, modelled), ``dp`` (one probe-needed, none modelled) and
``nd`` (no derived edge at all), each crossed with the kit (a derived pair's: the air of the edge it aims at, a
modelled one first, k0 at 0 else air3, inside the envelope or not; an ``nd`` pair is in each kit whose envelope holds
it); a pair with only other derived edges (drops, steps, swims, rigs, skips) is counted and left out.  Each
stratum's pairs are in a seeded order (sha256 of the seed, level, stratum and pair), so a sample is the first N, and
a larger one holds every smaller one.  A frame's sha is of its pairs and parameters, not of the code that wrote it
(``truth_sha12``: reach_truth.py's before Step R2.19g2, this file's since).

A pair's aim (:class:`Aims`): from the derived flight where the pair has one, else a run jump from the two zones'
points the envelope's slack ranks best (with air3 Flaps 5, the envelope's flap schedule beside it), stopping at the
kit's rank in the to-zone.  Its edge names who aims: R's ``truth:modelled`` (every pass, its confidence ``aim.MORE``'s)
or the pair stage's :data:`EDGE` (pass 1 alone: ``nd`` is no ``aim.MORE`` confidence), so the two key apart.

The pair stage (:func:`queue`): every ``nd`` frame pair the graph holds no zone witness for at its kit's rank or
under, in groups of at most :data:`GROUP` targets of one from-zone, kit and tier (:func:`tier`: ``nd-k0``, then
``nd-air3`` at slack <= :data:`BAND_M`, "near", and the rest, "far"), in the frame's seeded order; the groups in
the tiers' order (PLAN-v3's: nd-k0 first, then near, then far, whatever a level's rates say), then the frame's (a
group's first target's place: within a tier, the budget's cut is the frame's own seeded sample, as R's are, so a
bench's yield is the tier's); each group's expected links (the tier's rate, :func:`rates`) and CPU-seconds
(:data:`COST_S` a target) are named beside it.  A budget ends the queue, and what it
leaves is named by tier (:func:`tally`; D845: an order, never a prune, so never "unreachable").  ``dm`` and ``dp``
pairs are the base's: the targeted pass, the refinement and the backstop aim at their derived flights.  No ``aim.py``
edit, so no aim's key moves: an aim job holds one target, so a group is the queue's unit and each of its targets is
its own job and record.

The escalation (:func:`escalate`, Step R2.19g3, PLAN-v3's g3): a pair stage aim whose pair the graph still lacks at
its kit and whose pass 1 came within a tier (:data:`TIERS_M`; :func:`near_m`, from its record: the least distance from
a pass-1 landing or first touch-down to the to-zone's landing-side points, map-recall's gate) gets the same aim with
``more`` (passes 2-6, ``aim.more``), ids ``ea<n>``; once that has run and the pair is still lacking, ``aim.refine``'s
launches at the same target, twinned to the pass-1 aim (``aim.twinned``: its floor and start answers, none of its
macros), every pass, ids ``er<n>`` (R's own later stages, where they fail); k0 first, then nearest.  A farther pair
waits for a wider tier.  The distances are the records', so nothing new runs to choose and no ``aim.py`` edit moves a
key.  Positions stay in memory and the private cache.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

from devkit.reach.engine import aim, cache, runner
from devkit.reach.engine.graph import ESCALATE, PAIRS
from devkit.sim.inputs import heading_to

WIDEN = 1.25          # [PLAN-v2 §1.3] the frame's reach: this x the frame-perfect travel at the pair's dz
DROP_M = 40.0         # [PLAN-v2 §1.3] the deepest drop in the frame
RISE_PLUS_M = 1.0     # [PLAN-v2 §1.3] the highest rise: the kit's rise + this
DZ_STEP = 0.25        # the envelope table's step (m)
BIN_M, BIN_Z = 2.0, 1.0   # [default D115] a zone's border points, one a 2 m square and 1 m of height
KITS = {"k0": 0, "air3": 3}    # the engine's two kit branches (``macros.KITS``) and the rank each searches at
STRATA = tuple(f"{c}-{k}" for c in ("dm", "dp", "nd") for k in KITS)
SEED = 219            # [default D115] the frame's seed (Step R2.19)
PICK_TRIES = 64       # a non-derived pair's takeoff: the best-ranked of this many points on a walkable region
EDGE = "pair:nd"      # the pair stage's aims' edge tail: pass 1 alone (``aim.MORE``), keyed apart from R's
GROUP = 32            # [PLAN-v3 g2] at most this many targets a (from-zone, kit) group
BAND_M = -20.0        # [PLAN-v3 g2] an nd-air3 pair this far inside its envelope or more is "near" (map-recall
                      # N2b: all 18 of c1's R-real nd-air3 pairs lie there)
TIERS = ("nd-k0", "nd-air3-near", "nd-air3-far")
MIN_ROWS = 20         # [default D115] a tier's own rate needs this many frozen rows (the level's share, as many)
LEVEL_SHARE = 0.4     # [default D115, the design's] with too few, the level's nd R-real share x this
PRIOR = {"nd-k0": 0.073, "nd-air3-near": 0.053, "nd-air3-far": 0.0}   # [default D115] with no rows: p1-aims' pass-1
                      # hits on c1's 302 pairs (k0 11/150, air3 8/152), none of them far (map-recall N2b)
COST_S = {"kernel": {"k0": 0.26, "air3": 0.32}, "l3": {"k0": 0.78, "air3": 0.99}}   # [default D115] a pass-1 pair
                      # aim's CPU-s by route and kit (design-arith §3: FastL3 measured, the kernel's range's middle)
TIERS_M = (1.0, 2.0, 3.0, 5.0, 10.0)   # [PLAN-v3 g3] the escalation's tiers: how near a pair aim's pass 1 came (m)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _zid(level: str, z: int) -> str:
    return f"{level}.Z{int(z):03d}"


def folder(level: str) -> Path:
    """The level's private truth folder (``reach-truth/<level>/truth`` in the user data folder, mode 700, not the
    cache, which can be purged: the frozen truth set lives there): frames and R's frozen rows."""
    from platformdirs import user_data_path
    p = user_data_path("AzurKit", appauthor=False) / "reach-truth" / level / "truth"
    p.mkdir(mode=0o700, parents=True, exist_ok=True)
    return p


def rows(level: str, name: str, where: Path | None = None) -> list[dict]:
    """The rows frozen under ``name`` (``truth/<name>.jsonl``; ``where`` another folder)."""
    text = ((where or folder(level)) / f"{name}.jsonl").read_text(encoding="utf-8")
    return [json.loads(x) for x in text.splitlines()]


# -- the frame ---------------------------------------------------------------------------------------------------------

def _table(rank: int) -> tuple:
    """Rank ``rank``'s envelope as a table: dz from -:data:`DROP_M` to just under its rise, and the frame-perfect
    running travel at each, the levels with none left out (air3 has none at its rise itself); and the rise."""
    from devkit.rando.physics import envelope
    env = envelope()
    top = env.levels(rank)[0]
    dz = np.append(np.arange(-DROP_M, top, DZ_STEP), top)
    tr = [env.travel(rank, float(h)) for h in dz]
    ok = [i for i, v in enumerate(tr) if v is not None]
    return dz[ok], np.array([tr[i] for i in ok]), float(top)


def _reach(dz, table) -> np.ndarray:
    """The frame's reach at each ``dz`` (:data:`WIDEN` x the travel; above the table's highest level its travel, up
    to the rise + :data:`RISE_PLUS_M`), -inf outside."""
    g, t, top = table
    r = WIDEN * np.interp(dz, g, t)
    return np.where((dz >= -DROP_M) & (dz <= top + RISE_PLUS_M), r, -np.inf)


def _binned(p: dict) -> dict:
    """One point a zone, :data:`BIN_M` square and :data:`BIN_Z` of height (the lowest index in it)."""
    key = np.stack([p["zone"], np.floor(p["x"] / BIN_M), np.floor(p["y"] / BIN_M), np.floor(p["z"] / BIN_Z)], 1)
    _, first = np.unique(key.astype(np.int64), axis=0, return_index=True)
    first.sort()
    return {k: v[first] for k, v in p.items()}


def _bin_border(p: dict) -> dict:
    """The points of ``p`` (binned) with a zone's bin missing among their 8 neighbours across (any height)."""
    bx, by = np.floor(p["x"] / BIN_M).astype(np.int64), np.floor(p["y"] / BIN_M).astype(np.int64)
    off = 1 << 20

    def code(z, x, y):
        return (z.astype(np.int64) << 42) | ((x + off) << 21) | (y + off)
    have = np.unique(code(p["zone"], bx, by))
    edge = np.zeros(len(bx), dtype=bool)
    for dx, dy in ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)):
        edge |= ~np.isin(code(p["zone"], bx + dx, by + dy), have)
    return {k: v[edge] for k, v in p.items()}


def _points(nodes) -> tuple[dict, dict]:
    """(takeoff side, landing side): the logic walk's border samples, binned, and on the landing side the swim
    water's surface too (each water column's top, binned, its zone's border only); each with x, y, z, its zone and
    ``idx`` (the logic sample, or the logic walk's sample count + the water node)."""
    lw, zo = nodes.logic, np.asarray(nodes.R.zone_of)
    j = np.nonzero(lw.border & (lw.reg_soft >= 0))[0]
    floor = _binned({"x": lw.x[j].astype(np.float64), "y": lw.y[j].astype(np.float64),
                     "z": lw.z[j].astype(np.float64), "zone": zo[lw.reg_soft[j]].astype(np.int64), "idx": j})
    wg = nodes.wg
    if not len(getattr(wg, "col", ())):
        return floor, floor
    n = np.nonzero(wg.lab >= 0)[0]
    cx, cy = nodes.lv.cxy(wg.col[n])
    water = _bin_border(_binned({"x": np.asarray(cx, np.float64), "y": np.asarray(cy, np.float64),
                                 "z": wg.hi[n].astype(np.float64), "zone": zo[lw.nreg + wg.lab[n]].astype(np.int64),
                                 "idx": len(lw.col) + n}))
    return floor, {k: np.concatenate([floor[k], water[k]]) for k in floor}


def _pairs(src: dict, dst: dict, tables: dict) -> dict[str, dict[tuple, float]]:
    """Per kit, every ordered zone pair (from ``src``'s zones to ``dst``'s, two zones) some point pair of which is
    inside the kit's frame (:func:`_reach`), with its least slack (distance less the reach; <= 0)."""
    far = max(float(_reach(t[0], t).max()) for t in tables.values())
    gx, gy = np.floor(dst["x"] / far).astype(np.int64), np.floor(dst["y"] / far).astype(np.int64)
    cells: dict[tuple, np.ndarray] = {}
    order = np.lexsort((gy, gx))
    keys = np.stack([gx[order], gy[order]], 1)
    cut = np.nonzero(np.any(keys[1:] != keys[:-1], axis=1))[0] + 1
    for part in np.split(order, cut):
        cells[(int(gx[part[0]]), int(gy[part[0]]))] = part
    fx, fy = np.floor(src["x"] / far).astype(np.int64), np.floor(src["y"] / far).astype(np.int64)
    nz = int(max(src["zone"].max(), dst["zone"].max())) + 1
    got: dict[str, list] = {k: [] for k in tables}
    for cx, cy in sorted(set(zip(fx.tolist(), fy.tolist()))):
        f = np.nonzero((fx == cx) & (fy == cy))[0]
        c = [cells[(cx + a, cy + b)] for a in (-1, 0, 1) for b in (-1, 0, 1) if (cx + a, cy + b) in cells]
        if not c:
            continue
        c = np.concatenate(c)
        d = np.hypot(src["x"][f, None] - dst["x"][None, c], src["y"][f, None] - dst["y"][None, c])
        dz = dst["z"][None, c] - src["z"][f, None]
        pair = src["zone"][f, None] * nz + dst["zone"][None, c]
        other = src["zone"][f, None] != dst["zone"][None, c]
        for k, t in tables.items():
            s = d - _reach(dz, t)
            m = other & (s <= 0.0)
            if m.any():
                got[k].append(np.stack([pair[m].astype(np.float64), s[m]], 1))
    out = {}
    for k, parts in got.items():
        a = np.concatenate(parts) if parts else np.zeros((0, 2))
        a = a[np.lexsort((a[:, 1], a[:, 0]))]
        first = np.concatenate(([True], a[1:, 0] != a[:-1, 0])) if len(a) else np.zeros(0, dtype=bool)
        out[k] = {(int(p) // nz, int(p) % nz): float(s) for p, s in a[first]}
    return out


def _derived(level: str, derived: dict) -> dict[tuple, dict]:
    """Per (from zone, to zone) of the derived edges: ``cls`` dm, dp or other (:func:`frame`), ``edge`` (the jump or
    flap edge an aim flies: a modelled one first, then the least air, then a jump) and ``kit`` (a dm/dp pair's: that
    edge's air, k0 at 0)."""
    from devkit.rando.draft.author import dnf
    out: dict[tuple, dict] = {}
    for d in derived.get("edges", ()):
        p = (d["from"], d["to"])
        got = out.setdefault(p, {"cls": "other", "kit": None, "edge": None, "rank": None})
        conf = d.get("confidence")
        if d["kind"] not in ("jump", "flap") or conf not in ("modelled", "probe-needed"):
            continue
        airs = [max((a[1] for a in t), default=0) for t in dnf(d.get("requires", "true")) if all(a[0] == "air" for a in t)]
        air = min(airs) if airs else int((d.get("cert") or {}).get("rank") or 0)
        cls = "dm" if conf == "modelled" else "dp"
        rank = (cls != "dm", air, d["kind"] != "jump")
        if got["cls"] == "other" or rank < got["rank"]:
            got.update(cls=cls, edge=f"{d['from']}>{d['to']}:{d['kind']}:{conf}", rank=rank)
            got["kit"] = "k0" if air == 0 else "air3"
    return out


def _order(seed: int, level: str, stratum: str, pairs) -> list:
    return sorted(pairs, key=lambda p: _sha(f"{seed}/{level}/{stratum}/{p[0]}>{p[1]}"))


def frame_sha(doc: dict) -> str:
    """A frame's sha12: of its pairs and parameters, not of the code that wrote it."""
    return cache.sha12({k: v for k, v in doc.items() if k != "truth_sha12"})


def frame_path(level: str, zoning: str, seed: int, where: Path | None = None) -> Path:
    """The level's frame file of ``zoning`` and ``seed`` (in :func:`folder`, or ``where``)."""
    return (where or folder(level)) / f"frame-{zoning[:12]}-{seed}.json.gz"


def frame(level: str, nodes, derived: dict, seed: int = SEED, where: Path | None = None) -> dict:
    """The frame (the module docstring) of ``level`` over ``nodes`` (``reach_engine.nodes.Nodes``) and its
    ``derived`` file, written privately once (a frame there of the same zoning and seed must be this one: frozen,
    never rewritten); its counts."""
    from azurkit.tools.randomizer.planner.proofs import zoning
    tables = {k: _table(r) for k, r in KITS.items()}
    src, dst = _points(nodes)
    got = _pairs(src, dst, tables)
    der = _derived(level, derived)
    strata: dict[str, list] = {s: [] for s in STRATA}
    other = {k: 0 for k in KITS}
    for k in KITS:
        for (za, zb), s in got[k].items():
            p = (_zid(level, za), _zid(level, zb))
            cls = der.get(p, {}).get("cls")
            if cls is None:
                strata[f"nd-{k}"].append([*p, round(s, 3)])
            elif cls == "other":
                other[k] += 1
    named = {k: {(_zid(level, za), _zid(level, zb)): s for (za, zb), s in got[k].items()} for k in KITS}
    inside = {s: 0 for s in STRATA}
    for p, d in der.items():
        if d["cls"] in ("dm", "dp"):
            s = named[d["kit"]].get(p)
            strata[f"{d['cls']}-{d['kit']}"].append([*p, None if s is None else round(s, 3)])
            inside[f"{d['cls']}-{d['kit']}"] += p in named[d["kit"]]
    strata = {s: _order(seed, level, s, v) for s, v in strata.items()}
    zoned = zoning(derived)
    doc = {"level": level, "zoning": zoned[:12], "seed": seed, "widen": WIDEN, "drop_m": DROP_M,
           "rise_plus_m": RISE_PLUS_M, "bin_m": [BIN_M, BIN_Z], "truth_sha12": _sha(Path(__file__).read_text(
               encoding="utf-8"))[:12], "strata": strata}
    path, sha = frame_path(level, zoned, seed, where), frame_sha(doc)
    if path.exists():
        old = json.loads(gzip.decompress(path.read_bytes()))
        if frame_sha(old) != sha:
            raise SystemExit(f"{path.name} holds another frame ({frame_sha(old)}): frozen, never rewritten")
    else:
        cache.write(path, doc, zipped=True)
    return {"level": level, "zoning": zoned[:12], "seed": seed, "frame_sha12": sha,
            "envelope": {k: {"rise_m": round(t[2], 2), "reach_max_m": round(float(_reach(t[0], t).max()), 2)}
                         for k, t in tables.items()},
            "points": {"takeoff_side": len(src["x"]), "landing_side": len(dst["x"])},
            "pairs_in_envelope": {k: len(v) for k, v in got.items()},
            "other_derived_left_out": other, "strata": {s: len(v) for s, v in strata.items()},
            "derived_inside_envelope": inside}


# -- a pair's aim ------------------------------------------------------------------------------------------------------

class Aims:
    """A level's pair aims (the module docstring): its nodes, derived file, zoning, envelope tables, border points
    and derived edges; ``edge`` the aims' edge tail (:data:`EDGE`, R's ``truth:modelled``)."""

    def __init__(self, level: str, derived: dict, nodes, edge: str = EDGE) -> None:
        from azurkit.tools.randomizer.planner.proofs import zoning
        self.level, self.derived, self.nodes, self.edge = level, derived, nodes, edge
        self.zoned = zoning(derived)[:12]
        self.tables = {k: _table(r) for k, r in KITS.items()}
        self.src, self.dst = _points(nodes)
        self.der = _derived(level, derived)
        self.flights: dict[str, dict] = {}

    def prepare(self, pairs) -> None:
        """The derived flights (``aim.aim_jobs``) of the derived edges an aim at ``pairs`` flies."""
        edges = {e for p in pairs if (e := self.der.get(p, {}).get("edge"))} - set(self.flights)
        if edges:
            self.flights.update({j["edge"]: j for j in aim.aim_jobs(self.nodes, self.derived, only=edges)})

    def _zone(self, side: dict, z: str) -> np.ndarray:
        return np.nonzero(side["zone"] == int(z.rsplit(".Z", 1)[1]))[0]

    def _ranked(self, za: str, zb: str, kit: str) -> list[tuple[int, int]]:
        """The (takeoff point, landing point) pairs of ``za`` and ``zb``, best slack first."""
        f, t = self._zone(self.src, za), self._zone(self.dst, zb)
        if not len(f) or not len(t):
            return []
        s, d = self.src, self.dst
        sl = (np.hypot(s["x"][f, None] - d["x"][None, t], s["y"][f, None] - d["y"][None, t])
              - _reach(d["z"][None, t] - s["z"][f, None], self.tables[kit]))
        k = np.argsort(sl, axis=None, kind="stable")[:PICK_TRIES * 4]
        return [(int(f[i // len(t)]), int(t[i % len(t)])) for i in k]

    def _xyz(self, side: dict, i: int) -> tuple[float, float, float]:
        return float(side["x"][i]), float(side["y"][i]), float(side["z"][i])

    def aim_job(self, jid: str, za: str, zb: str, kit: str) -> tuple[dict | None, str | None]:
        """The pair's aim (the module docstring; a derived pair's flight once :meth:`prepare` has read it), id
        ``jid``, or None and why."""
        from devkit.rando.physics import envelope
        nodes, edge = self.nodes, f"{za}>{zb}:{self.edge}"
        stop = {"air": KITS[kit], "to": zb, "zoning": self.zoned}
        d = self.der.get((za, zb), {})
        if (j := self.flights.get(d.get("edge"))) is not None:
            c = next(e for e in self.derived["edges"]
                     if f"{e['from']}>{e['to']}:{e['kind']}:{e['confidence']}" == d["edge"]).get("cert") or {}
            kind, _, flaps = j["cert"]
            env = (list(envelope().schedule(int(c["rank"]), float(j["target"][2] - j["takeoff_feet"][2]),
                                            c.get("headroom"), c.get("flaps")))
                   if kind != "walkoff" and flaps > 0 and c.get("rank") is not None else [])
            j = {k: v for k, v in j.items() if k not in ("env", "id", "key")}
            return dict(j, id=jid, edge=edge, stop=stop, **({"env": env} if env else {})), None
        ns = len(nodes.logic.col)
        for n, (i, t) in enumerate(self._ranked(za, zb, kit)):
            if n >= PICK_TRIES:
                break
            src = self._xyz(self.src, i)
            if (r := nodes.region_at(src)) is None:
                continue
            q = self._xyz(self.dst, t)
            moved = q if self.dst["idx"][t] >= ns else aim._inside(nodes, src, int(self.dst["idx"][t]))
            dst = (nodes.snap(moved, zb) or moved) if self.dst["idx"][t] < ns else q
            return self.aim_at(jid, za, zb, kit, src, dst, moved, r), None
        return None, "no takeoff point on a walkable region"

    def aim_at(self, jid: str, za: str, zb: str, kit: str, src, dst, moved, region: int) -> dict:
        """A run jump's aim from ``src`` (on walkable region ``region``) at ``dst`` (``moved`` unsnapped; the module
        docstring): a non-derived pair's, or the generator's class check (``reach_truth._classed``)."""
        from devkit.rando.physics import envelope
        from devkit.reach.engine.nodes import Takeoff
        nodes, edge = self.nodes, f"{za}>{zb}:{self.edge}"
        stop = {"air": KITS[kit], "to": zb, "zoning": self.zoned}
        flaps = 0 if kit == "k0" else aim.FLAPS_OF_RANK[3]
        tk = Takeoff(-1, -1, region, src, heading_to(src, dst), tuple(nodes.cells([src])[0]))
        env = list(envelope().schedule(3, float(dst[2] - src[2]), None, flaps)) if flaps else []
        return runner._job(nodes, tk, tk.heading, aim.aims("runjump", kit, flaps), za, id=jid, edge=edge,
                           target=list(dst), aim=list(moved), stop=stop, target_cells=nodes.cells([dst])[0][:1],
                           cert=["runjump", kit, flaps], **{"from": za}, **({"env": env} if env else {}))


# -- the pair stage ----------------------------------------------------------------------------------------------------

def tier(stratum: str, slack: float) -> str:
    """An nd frame pair's tier (the module docstring)."""
    if stratum == "nd-k0":
        return "nd-k0"
    return "nd-air3-near" if slack <= BAND_M else "nd-air3-far"


def _lacks(zones: dict, za: str, zb: str, kit: str) -> bool:
    """``zones`` (the graph's: pair -> {rank: witness}) holds the pair at no rank up to ``kit``'s."""
    return not any(r <= KITS[kit] for r in zones.get((za, zb), ()))


def rates(frozen: list[dict], zones: dict) -> dict[str, dict]:
    """Each tier's expected links a target, and whence: of R's ``frozen`` rows of the level (a pair frozen under two
    names once, the last) whose pair ``zones`` lacks at its kit, as the queue's targets are (:func:`queue`), its
    pass-1 aim's hit share where the tier has :data:`MIN_ROWS` rows, else the level's nd R-real share x
    :data:`LEVEL_SHARE` where its nd rows are as many, else :data:`PRIOR`."""
    nd = list({(r["stratum"], r["from"], r["to"]): r for r in frozen
               if r["stratum"].startswith("nd-") and not r.get("na")
               and _lacks(zones, r["from"], r["to"], r["stratum"].split("-")[1])}.values())
    share = sum(bool(r.get("real")) for r in nd) / len(nd) * LEVEL_SHARE if len(nd) >= MIN_ROWS else None
    out = {}
    for t in TIERS:
        rs = [r for r in nd if tier(r["stratum"], r["slack"]) == t]
        if len(rs) >= MIN_ROWS:
            out[t] = {"rate": sum(r.get("by") == "aim pass 1" for r in rs) / len(rs), "from": f"{len(rs)} rows"}
        elif share is not None:
            out[t] = {"rate": share, "from": f"the level's {len(nd)} nd rows x {LEVEL_SHARE}"}
        else:
            out[t] = {"rate": PRIOR[t], "from": "prior"}
    return out


def queue(strata: dict, zones: dict, rate: dict, cost: dict, budget_s: float | None = None) -> tuple[list, list]:
    """The pair stage's groups (the module docstring) of the frame's nd ``strata`` (stratum -> [from, to, slack])
    whose pair ``zones`` (the graph's: pair -> {rank: witness}) holds at no rank up to its kit's: those the budget
    (``budget_s`` CPU-seconds, None: all) takes in order, and those it leaves.  Each: ``from``, ``kit``, ``tier``,
    ``at`` (its first target's place in its stratum), ``targets`` ([from, to, slack], in the frame's order),
    ``links`` (expected: ``rate`` a target by tier) and ``cpu_s`` (``cost`` a target by kit)."""
    by: dict[tuple, list] = {}
    for s in ("nd-k0", "nd-air3"):
        kit = s.split("-")[1]
        for n, (za, zb, slack) in enumerate(strata.get(s, ())):
            if _lacks(zones, za, zb, kit):
                by.setdefault((za, kit, tier(s, slack)), []).append((n, [za, zb, slack]))
    groups = []
    for (za, kit, t), ts in by.items():
        for k in range(0, len(ts), GROUP):
            part = ts[k:k + GROUP]
            groups.append({"from": za, "kit": kit, "tier": t, "at": part[0][0], "targets": [q for _, q in part],
                           "links": rate[t] * len(part), "cpu_s": cost[kit] * len(part)})
    groups.sort(key=lambda g: (TIERS.index(g["tier"]), -rate[g["tier"]] / cost[g["kit"]], g["at"]))
    spent = 0.0
    for n, g in enumerate(groups):
        if budget_s is not None and spent + g["cpu_s"] > budget_s:
            return groups[:n], groups[n:]
        spent += g["cpu_s"]
    return groups, []


def tally(groups: list) -> dict[str, dict]:
    """``groups``' pairs, groups, expected links and CPU-hours by tier."""
    out: dict[str, dict] = {}
    for g in groups:
        d = out.setdefault(g["tier"], {"pairs": 0, "groups": 0, "expected_links": 0.0, "cpu_h": 0.0})
        d["pairs"] += len(g["targets"])
        d["groups"] += 1
        d["expected_links"] += g["links"]
        d["cpu_h"] += g["cpu_s"] / 3600
    return {t: d | {"expected_links": round(d["expected_links"], 1), "cpu_h": round(d["cpu_h"], 3)}
            for t, d in sorted(out.items(), key=lambda x: TIERS.index(x[0]))}


# -- the escalation ----------------------------------------------------------------------------------------------------

def near_m(rec: dict, pts: np.ndarray) -> float | None:
    """How near a pair aim's pass 1 came to its to-zone (record ``rec``): the least 3-D distance from a pass-1 landing
    or first touch-down to ``pts`` ((n, 3): the to-zone's landing-side points, :func:`_points`'), None for none."""
    got = [p for o in rec["outcomes"] if o.get("pass") == 1 for p in (o.get("land"), o.get("first")) if p is not None]
    if not got or not len(pts):
        return None
    return float(np.sqrt(((np.asarray(got, np.float64)[:, None] - pts[None]) ** 2).sum(-1).min()))


def _pair(j: dict) -> tuple[str, str, str]:
    return j["from"], j["stop"]["to"], j["cert"][1]


def escalate(jobs: dict, recs: dict, dst: dict, zones: dict, tier_m: float, kits=tuple(KITS)) -> tuple[list, list]:
    """The escalation (the module docstring) of a graph's ``jobs`` and ``recs`` (by key; ``zones`` the graph's: pair ->
    {rank: witness}; ``dst`` the frame's landing side, :func:`_points`): of each pair stage aim (ids ``p...``, kit in
    ``kits``, a record) whose pair ``zones`` holds at no rank up to its kit's, the one that came nearest
    (:func:`near_m`); within ``tier_m``, its escalated aim (``more``) or, once one of those has a record, its
    refinement twinned to the pass-1 aim, ``near_m`` beside each (no key part), k0 first, then nearest; and those that
    wait, [from, to, kit, metres or None]."""
    ran = {_pair(j) for k, j in jobs.items() if j["id"].startswith(ESCALATE + "a") and k in recs}
    best: dict[tuple, tuple] = {}
    pts: dict[str, np.ndarray] = {}
    for k, j in jobs.items():
        if j["id"][:1] != PAIRS or k not in recs or (p := _pair(j))[2] not in kits or not _lacks(zones, *p):
            continue
        if p[1] not in pts:
            i = np.nonzero(dst["zone"] == int(p[1].rsplit(".Z", 1)[1]))[0]
            pts[p[1]] = np.stack([dst["x"][i], dst["y"][i], dst["z"][i]], 1).astype(np.float64)
        m = near_m(recs[k], pts[p[1]])
        if p not in best or (m is not None and (best[p][0] is None or m < best[p][0])):
            best[p] = (m, k, j)
    out, wait = [], []
    for p, (m, k, j) in sorted(best.items(), key=lambda x: (x[0][2] != "k0", x[1][0] is None, x[1][0] or 0.0, x[0])):
        if m is None or m > tier_m:
            wait.append([*p, m])
            continue
        own = {x: v for x, v in j.items() if x not in ("key", "backend", "group")}
        own |= {"more": True, "near_m": round(m, 2)}
        if p not in ran:
            out.append(dict(own, id=f"{ESCALATE}a{len(out)}"))
            continue
        r = {x: v for x, v in own.items() if x != "env"}
        r.update(id=f"{ESCALATE}r{len(out)}", macros=[list(x) for x in aim.refine(*j["cert"])])
        out.append(aim.twinned(r, j, recs[k]))
    return out, wait
