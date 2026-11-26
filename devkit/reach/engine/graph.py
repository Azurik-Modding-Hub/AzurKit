"""The reach engine's graph (Step R2.16a; the R2.16 design §2d): outcomes into edges, and the closure per kit.

An outcome that settled (``macros.launch``'s ``settled``: ``obs.settled``) on a node other than its start's is
an edge (from node, to node) at the least air rank its witness needs (:func:`min_rank`: none in rank 0's branch;
in the shield's, rank 1 for at most one flap in the jump, 2 for two, 3 for more: Flaps 1/2/5, and h and air control
are the same for ranks 1-3, physics.py), so reach is monotone in kit by construction.  Its start must stand on the
job's own node (the node its takeoff is on, under the nodes given) or, Step R2.16b, in the job's from-zone (an
aim's ``from``, else the takeoff's zone: a start moved off a raster sliver onto its floor face may stand on another
node of the zone); the edge runs from the node the start stood on.  A start that settled elsewhere is dropped and
counted (AZ-585's kind); an outcome that died, hit a cap, faulted or left the level is no edge.  Each edge keeps,
per rank, its best witness (untainted first, then fewest ticks).  A zone edge (the logic's zones,
``Router.zone_at``) is any settled landing in another zone than its start's, on the start's own node too (one
walkable region can hold several of the logic's zones), with its best witness a rank the same way, and since Step
R2.16d its best :data:`TRIES` kept for :meth:`Graph.hold`, which keeps the best whose body stays in the to-zone
(``hold``), and after them the best whose stay its record already holds (an aim's hit, held as ``aim.run_job`` found
it: that hit ended its job, so no other launch of the job is there to stand in for it); an aim's hit whose own hold
left takes none of them (Step R2.19k: the hold would drop it, and it pushed out a witness that may stay), though its
pair stays in ``cands`` with that rank empty: a launch still landed in its to-zone (``verdict.zone_edges``'
``landed``, the phantom-landing guard).  A retarget's witnesses (job ids ``g...``: ``aim.retarget``'s, aimed at what
a held graph left) take :data:`TRIES` of their own (Step R2.19f+: g1's quicker re-aims that left had pushed out the
witness that stays, so adding them lost e7's truth pair Z117>Z000), and so do the pair stage's (job ids ``p...``:
``sample --pairs``', Step R2.19g2: its aims that left pushed out three of a5's held zone pairs) and the escalation's
(job ids ``e...``: ``sample --escalate``', Step R2.19g3, so it never pushes out a pair stage's or the base's), which
:meth:`Graph.hold` tries after every other (so one that stays never ends a hold before a kernel confirm the plans
without it read, whose touches, MAY and node edge then went: g3's measure lost e7 27 MAY edges so).  What a share's
cap pushes out is kept in the rank's ``spill``, which :meth:`Graph.hold` tries after the rank's tries and its held
one, by the same order (escalations still last), so it is replayed only where none of them stays (AZ-848, Step
4.79g: a second plan of one stage, 4.76c's deep census beside 4.76b's retarget, shares its share, and its quicker
re-aims that left pushed out witnesses that stay; e7, f2 and w1 lost nine zone pair ranks so).  So the hold of a
graph built from more records keeps every zone pair rank the smaller graph's hold kept from that pair's own
candidates (a third zone's credit, AZ-840 below, rests on which confirms a hold reads).  A first
touch-down on a third node the body then left is a MAY candidate; the volumes and pickups its body centre touched are
edges to them (``vol:<id>``, ``pick:<location>``).  A kernel outcome (``by`` "kernel": Step R2.19d's launch backend,
``reach_native.backend``) is a zone witness candidate only: it gives no node edge, MAY candidate or touch itself, and
a zone witness only once its hold (FastL3's confirm) stays, the witness then taking the confirm's re-derived fields
(D845: every counted link has a witness in the game's own code); each confirm the hold runs, staying or not, gives the
touches, MAY candidate and node edge of FastL3's run of the string, as an L3 outcome does (Step R2.19k).  An edge
onto or off a node of the snapshot's frozen world (``Nodes.frozen``: a rig deck at its rest pose, a toggled solid as
loaded) is flagged, as is one that ends swimming (``swim``).  A walk-off that flapped (AZ-838), as L3 ran it or as
FastL3's confirm of a kernel candidate did, gives no zone slot, node edge or touch, only (an L3 run's) a MAY
candidate to where it settled: R6 doesn't write the flap latch (+0x164), so its flaps fly on the snapshot's last
jump's latch, which no seed promises.  A confirm keeps its
kernel candidate's rank
where FastL3's is lower (AZ-839: FastL3 may land early and the kernel's next Y press start a ground jump, so FastL3's
one-jump rank can undercount; the interim guard until the confirm itself checks it), and one whose body holds in a
third zone (not its candidate's start or to-zone) fills that zone pair's rank where the hold kept no witness (AZ-840),
its flags its own.  A zone
witness also carries the zone-mapping flags (R2.16a's skeptic, S4): ``one_region`` (its zones share the walkable
region it took off and landed on), ``takeoff_zone`` (it took off in another zone than its start's: the run-up crossed
a zone line) and ``zone_far`` (the logic's floor sample that names its landing zone lies over :data:`ZONE_FAR_M`
away).

:func:`closure` is each node's reach over the edges usable at an air rank (plus each kit's within-node walk: a node
is one walkable region); :func:`components` its strongly connected components (iterative Tarjan).  Coordinate-free
but for the outcomes it reads.
"""

from __future__ import annotations

import collections

from devkit.reach.engine.macros import min_rank

RANKS = (0, 1, 2, 3)
ZONE_FAR_M = 0.5      # the skeptic's S4 bar: a landing's zone named by a floor sample farther off is suspect
TRIES = 3             # [proposal] a zone pair's witnesses a rank the hold tries, best first (Step R2.16d)
RETARGET = "g"        # a retarget job's id's first letter (``aim.retarget``): its witnesses take TRIES of their own
PAIRS = "p"           # a pair stage job's id's first letter (``sample --pairs``): its witnesses too
ESCALATE = "e"        # an escalation job's id's first letter (``sample --escalate``): its witnesses too


def _kind(jid: str) -> str:
    """A witness's share of a zone pair rank's :data:`TRIES` (the module docstring): a retarget's, a pair stage's, an
    escalation's or the rest's, by its job id."""
    return jid[:1] if jid[:1] in (RETARGET, PAIRS, ESCALATE) else ""


def _order(w: dict) -> tuple:
    return bool(w["taint"]), w["ticks"]


def _better(w: dict, old: dict | None) -> bool:
    return old is None or _order(w) < _order(old)


def _latched(w: dict, o: dict) -> bool:
    """Whether witness ``w``'s string, run as outcome ``o`` (its own or FastL3's confirm of it), is a walk-off that
    flapped: on the snapshot's flap latch (AZ-838, the module docstring)."""
    return w["macro"].partition("-")[0] == "walkoff" and o["flaps"] > 0


class Graph:
    """The edges a set of job records gives over ``nodes`` (:class:`~.nodes.Nodes`): ``edges[(a, b)][rank]`` the
    best witness of each rank, ``zones[(za, zb)][rank]`` the same between the logic's zones, ``cands`` its
    :data:`TRIES` best a rank, ``spill`` what that cap pushed out (AZ-848), ``stayed`` its best whose record holds
    its stay, ``touch`` the volume and pickup
    edges, ``may`` the first-contact candidates, ``counts`` what was dropped and why, ``aimed`` the derived edges an
    aim launched at and ``tried`` those an aim was run for (its aim point and to-zone), and :meth:`fault` an aimed
    edge's floor fault."""

    def __init__(self, nodes, jobs: dict[str, dict], records) -> None:
        self.nodes = nodes
        self.edges: dict[tuple, dict[int, dict]] = collections.defaultdict(dict)
        self.zones: dict[tuple, dict[int, dict]] = collections.defaultdict(dict)
        self.cands: dict[tuple, dict[int, list]] = collections.defaultdict(dict)
        self.spill: dict[tuple, dict[int, list]] = collections.defaultdict(dict)   # the cap's (AZ-848), best first
        self.stayed: dict[tuple, dict[int, dict]] = collections.defaultdict(dict)
        self.touch: dict[tuple, int] = {}
        self.may: dict[tuple, int] = {}
        self.counts = collections.Counter()
        self.start_zone: dict[str, set] = collections.defaultdict(set)
        self.aimed: set[str] = set()          # the derived edges (``from>to:kind:confidence``) an aim ran at
        self.tried: dict[str, tuple] = {}     # the derived edges an aim job ran for: its aim point and to-zone
        self.floor: dict[str, bool] = {}      # per aimed edge, whether L3 stood a body in its to-zone near its target
        self.from_floor: dict[str, bool] = {}  # ... and in its from-zone near its takeoff (aim.other_starts)
        self._fault: dict[str, str | None] = {}
        for rec in records:
            job = jobs.get(rec["key"])
            if job is None:
                self.counts["records with no job"] += 1
                continue
            t = nodes.node_at(job["takeoff_feet"], 0)
            home = job.get("from") or nodes.zone_at(job["takeoff_feet"], False, False)
            if t is None and home is None:
                self.counts["jobs whose takeoff is on no node"] += 1
                continue
            if job.get("edge"):
                self.tried.setdefault(job["edge"], (job.get("aim") or job["target"],
                                                    job["edge"].split(":")[0].split(">")[1]))
                if rec["outcomes"]:
                    self.aimed.add(job["edge"])
                if "floor" in rec:                                  # aim.floor's answer
                    self.floor[job["edge"]] = self.floor.get(job["edge"], False) or rec["floor"]["to"]
                if "from_floor" in rec:
                    self.from_floor[job["edge"]] = (self.from_floor.get(job["edge"], False)
                                                    or bool(rec["from_floor"]["stood"]))
            at: dict[str, tuple] = {}
            for variant, st in rec["starts"].items():
                self.counts["starts"] += 1
                if "settled" not in st:
                    self.counts["starts dropped: none stood"] += 1
                    continue
                a, za = nodes.node_at(st["settled"], 0), nodes.zone_at(st["settled"], False, False)
                if a is not None and a == t:
                    at[variant] = (a, za)
                elif a is not None and za is not None and za == home:
                    self.counts["starts kept by their zone, off the takeoff's node"] += 1
                    at[variant] = (a, za)
                else:
                    self.counts["starts dropped: settled off the region"] += 1
            for k, o in enumerate(rec["outcomes"]):
                if o["start"] not in at:
                    continue
                a, za = at[o["start"]]
                self.counts["launches"] += 1
                self.start_zone[a].add(za)
                self._add(a, za, rec, k, o, job)

    def _flags(self, a: str, b: str, za: str, o: dict) -> list[str]:
        """A zone witness's zone-mapping flags (the module docstring)."""
        n, out = self.nodes, []
        if b == a:
            out.append("one_region")
        if o.get("took") is not None and n.zone_at(o["took"], False, False) not in (None, za):
            out.append("takeoff_zone")
        gap = getattr(n, "zone_gap", None)
        if gap is not None and (g := gap(o["land"], o["land_state"] == 6)) is not None and g > ZONE_FAR_M:
            out.append("zone_far")
        return out

    def _add(self, a: str, za, rec: dict, k: int, o: dict, job: dict) -> None:
        r = min_rank(o)
        w = {"job": rec["key"], "id": rec["id"], "outcome": k, "macro": o["macro"], "string_sha12": o["string_sha12"],
             "ticks": o["ticks"], "taint": o["taint"], "hp_lost": o["hp0"] - o["hp_min"], "flaps": o["flaps"],
             "labels": o["labels"], "kit": o["kit"], "rank": r, "edge": job.get("edge"), "by": o.get("by", "l3"),
             "node": a}
        kernel = w["by"] == "kernel"           # a candidate until FastL3 confirms it (the module docstring)
        self.counts["kernel candidates"] += kernel
        if o["end"] != "settled":
            self.counts[f"launches ended {o['end'].split(':')[0]}"] += 1
        if _latched(w, o):                     # AZ-838: the snapshot's latch (the module docstring)
            self.counts["walk-off flaps on the snapshot's latch, taking no try"] += 1
            if not kernel and (b := self._edges(a, r, w, o, False)) not in (None, a):
                self.may[(a, b)] = min(r, self.may.get((a, b), 9))
            return
        b = self._edges(a, r, w, o, not kernel)
        if b is None:
            if o["end"] == "settled":
                self.counts["launches settled on no node"] += 1
            return
        self.counts["launches back on their start" if b == a else "launches onto another node"] += 1
        zb = self.nodes.zone_at(o["land"], w["swim"], False)
        if za is None or zb is None or za == zb:
            return
        if b == a:
            self.counts["launches back on their start, in another zone"] += 1
        if "hold" in o:                            # an aim's hit, held as it was found
            from devkit.reach.engine.hold import stays
            if not stays(o["hold"], zb, self.nodes.zone_at):     # it left: the hold would drop it, so no try's slot
                self.counts["aim hits whose hold left, taking no try"] += 1
                self.cands[(za, zb)].setdefault(r, [])     # it still landed there (verdict's ``landed``)
                return
        got = self.cands[(za, zb)].setdefault(r, [])
        w = dict(w, flags=self._flags(a, b, za, o))
        if any(x["string_sha12"] == w["string_sha12"] for x in got):   # the same string holds as its twin does
            self.counts["zone witnesses repeating a kept try's string, taking no try"] += 1
        else:
            got.append(w)
            got.sort(key=_order)                   # stable: of equals, the first found stays first
            kind = [i for i, x in enumerate(got) if _kind(x["id"]) == _kind(w["id"])]
            if len(kind) > TRIES:                  # the worst of w's own kind goes: a retarget's, a pair's, the rest's
                spill = self.spill[(za, zb)].setdefault(r, [])     # ... to the rank's spill (AZ-848)
                spill.append(got.pop(kind[-1]))
                spill.sort(key=_order)
        self.zones[(za, zb)][r] = got[0]
        if "hold" in o and _better(w, self.stayed[(za, zb)].get(r)):
            self.stayed[(za, zb)][r] = w

    def _edges(self, a: str, r: int, w: dict, o: dict, add: bool = True) -> str | None:
        """Outcome ``o``'s volume and pickup edges from node ``a``, its MAY candidate and its node edge (witness
        ``w``, at air rank ``r``; none without ``add``: a kernel candidate's), and the node it settled on (None for
        none: it didn't settle, or not on a node)."""
        if add:
            for v in o["volumes"]:
                self.touch[(a, f"vol:{v}")] = min(r, self.touch.get((a, f"vol:{v}"), 9))
            for p in o["picks"]:
                self.touch[(a, f"pick:{p}")] = min(r, self.touch.get((a, f"pick:{p}"), 9))
        if o["end"] != "settled":
            return None
        b = self.nodes.node_at(o["land"], o["land_state"])
        if (add and o["first"] is not None
                and (f := self.nodes.node_at(o["first"], o["first_state"])) not in (None, a, b)):
            self.may[(a, f)] = min(r, self.may.get((a, f), 9))
        if b is None:
            return None
        w["frozen"] = self.nodes.frozen.get(b) or self.nodes.frozen.get(a)
        w["swim"] = o["land_state"] == 6
        if add and b != a and _better(w, self.edges[(a, b)].get(r)):
            self.edges[(a, b)][r] = w
        return b

    def hold(self, answer) -> list[dict]:
        """The hold (``hold``'s module docstring): each zone pair's witness a rank becomes the best of its
        :attr:`cands` whose answer (``answer(w)``: ``hold.replay``'s, None while not replayed) :func:`hold.stays`
        in the pair's to-zone, else its :attr:`stayed` one, else the best of its :attr:`spill` (AZ-848), an
        escalation's tried last (a kernel candidate's answer is FastL3's confirm: the witness kept takes its
        re-derived fields, :func:`confirmed`); a rank none of them stays for goes, and a pair with no rank left.  Each
        confirm it read then adds its touches, MAY candidate and node edge (the module docstring), and a confirm whose
        body holds in a third zone fills that pair's rank where no witness is kept (AZ-840); one whose walk-off
        flapped stays nowhere and gives only its MAY (AZ-838).  While a candidate ahead of any that stays has no
        answer, nothing changes and those candidates are returned: replay them, then call again; one of a spill goes
        with as many unanswered ones after it as the spill's answered ahead of it, so a long spill that leaves takes
        a few calls, not one a candidate (AZ-848)."""
        from devkit.reach.engine.hold import SWIMMING, stays
        want, keep, confirms, spilled, asked = [], {}, [], 0, 0
        for (za, zb), ranks in self.cands.items():
            for r, ws in ranks.items():
                held = self.stayed.get((za, zb), {}).get(r)
                tries = ws + ([held] if held is not None and all(x is not held for x in ws) else [])
                spill = [x for x in self.spill.get((za, zb), {}).get(r, ()) if x is not held]   # AZ-848: the cap's
                ids = {id(x) for x in spill}
                order = sorted(tries + spill, key=lambda x: _kind(x["id"]) == ESCALATE)   # g3's last: the docstring
                for i, w in enumerate(order):
                    if (got := answer(w)) is None:
                        want.append(w)
                        if id(w) in ids:           # a spill's: as many more as the spill answered ahead go too (AZ-848)
                            n = sum(id(x) in ids for x in order[:i])
                            more = [x for x in [x for x in order[i + 1:] if id(x) in ids][:n] if answer(x) is None]
                            want += more
                            asked += 1 + len(more)
                        break
                    if got.get("outcome") is not None:     # a confirm (an aim's hit's: its edges are in)
                        confirms.append((w, got, za, zb))
                        if _latched(w, got["outcome"]):    # AZ-838: FastL3's run of it flapped on the latch
                            continue
                    if stays(got, zb, self.nodes.zone_at):
                        keep[(za, zb), r] = confirmed(w, got)
                        spilled += any(x is w for x in spill)
                        break
        if want:
            self.counts["spilled candidates the hold asked to replay"] += asked   # every call's, so the spill's cost
            return want
        other: dict[tuple, dict] = {}
        latched = 0
        for w, got, za, zb in confirms:      # FastL3's run of the string: its touches, MAY and node edge count
            c = confirmed({k: v for k, v in w.items() if k != "flags"}, got)
            if _latched(w, got["outcome"]):  # AZ-838: only a MAY to where it settled, as an L3 walk-off's
                latched += 1
                if (b := self._edges(w["node"], c["rank"], c, got["outcome"], False)) not in (None, w["node"]):
                    self.may[(w["node"], b)] = min(c["rank"], self.may.get((w["node"], b), 9))
                continue
            b = self._edges(w["node"], c["rank"], c, got["outcome"])
            zc = None if b is None else self.nodes.zone_at(got["land"], got["state"] == SWIMMING, False)
            if (zc not in (None, za, zb) and stays(got, zc, self.nodes.zone_at)
                    and _better(c, other.get(((za, zc), c["rank"])))):     # AZ-840: it holds in a third zone
                other[(za, zc), c["rank"]] = dict(c, flags=self._flags(w["node"], b, za, got["outcome"]))
        self.counts["FastL3 confirms the hold read"] = len(confirms)
        self.counts["FastL3 confirms whose walk-off flapped on the snapshot's latch, taking no try"] = latched
        moved = gone = 0
        self.counts["zone witnesses FastL3 confirmed from the kernel"] = sum(w["by"] == "confirmed"
                                                                              for w in keep.values())
        for pair, ranks in self.cands.items():
            got = {r: keep[pair, r] for r in sorted(ranks) if (pair, r) in keep}
            moved += sum(w is not ranks[r][0] for r, w in got.items())
            gone += len(ranks) - len(got)
            if got:
                self.zones[pair] = got
            else:
                self.zones.pop(pair, None)
        self.counts["zone witnesses the hold took from a later candidate"] = moved
        self.counts["zone witnesses the hold took from the cap's spill"] = spilled
        self.counts["zone ranks the hold left with no witness"] = gone
        n = 0
        for (pair, r), c in other.items():          # where the hold kept none: a launch landed there too (``cands``)
            if r not in self.zones.get(pair, {}):
                self.cands[pair].setdefault(r, [])
                self.zones[pair] = dict(sorted((self.zones.get(pair, {}) | {r: c}).items()))
                n += 1
        self.counts["zone witnesses a confirm held in another zone than its candidate's"] = n
        return []

    def fault(self, edge: str) -> str | None:
        """Derived edge ``edge``'s (``from>to:kind:confidence``) floor fault (AZ-723), None if none or no aim was run
        for it: ``takeoff`` when no start of its aims stood, the ring 0.25 m around the first too (``aim.RING``;
        L3's own answer for those points, but the start search reads a face list that misses floors L3 stands on:
        Step R2.16c's skeptic stood a body 0.25 m off for 28 of 32 before the ring), ``landing`` when no aim of it
        stood a body in its to-zone within ``aim.SCAN_M`` of its target in L3 (:attr:`floor`), or where none tried,
        when the engine's face list holds no floor of its to-zone within ``nodes.SNAP_M`` of its aim's landing
        (``Nodes.floor_near``: only a flag, since that list misses floors L3 stands on: Step R2.16c's review found L3
        standing in the to-zone within 2 m of 145 of 178 such aims), or both."""
        if edge not in self.tried:
            return None
        if edge not in self._fault:
            aim, to = self.tried[edge]
            near = self.floor[edge] if edge in self.floor else self.nodes.floor_near(aim, to)
            bad = (("landing", not near), ("takeoff", edge not in self.aimed))
            self._fault[edge] = "+".join(k for k, b in bad if b) or None
        return self._fault[edge]

    def best(self, pair: tuple, rank: int = 3, zones: bool = False) -> dict | None:
        """The best witness of an edge (a node pair, or with ``zones`` a zone pair) usable at air ``rank``: the
        least rank's, None for none."""
        got = (self.zones if zones else self.edges).get(pair, {})
        r = min((x for x in got if x <= rank), default=None)
        return None if r is None else got[r]

    def witnesses(self, pair: tuple) -> list[dict]:
        """A zone pair's best witness at each rank, least rank first."""
        got = self.zones.get(pair, {})
        return [got[r] for r in sorted(got)]

    def kits(self) -> dict:
        """The closure per kit: at each air rank, the edges usable, the nodes they touch, the strongly connected
        components and the largest one's size."""
        out = {}
        for r in RANKS:
            adj = self.adjacency(r)
            comps = components(adj)
            out[f"air{r}"] = {"edges": sum(len(b) for b in adj.values()),
                              "nodes": len(set(adj) | {x for b in adj.values() for x in b}),
                              "components": len(comps), "largest": max((len(c) for c in comps), default=0)}
        return out

    def adjacency(self, rank: int, zones: bool = False) -> dict[str, set]:
        """Each node's (zone's) successors over the edges usable at air ``rank``."""
        out: dict[str, set] = collections.defaultdict(set)
        for (a, b), got in (self.zones if zones else self.edges).items():
            if any(x <= rank for x in got):
                out[a].add(b)
        return out


def confirmed(w: dict, got: dict) -> dict:
    """Witness ``w`` with the fields of the outcome its hold answer ``got`` re-derived on FastL3 (a kernel
    candidate's confirm, ``reach_native.backend.confirm``; ``by`` "confirmed") and the movers its path touched
    (``route``, the kernel route's answers), the idle ticks its whole-step trip waited before its R6 (``wait``) and
    the parked rigs it touches (``parked``: ``rigs.Router``, Step R2.19h1), else ``w`` as it is."""
    if "route" in got:
        w["route"] = got["route"]
    if "trip" in got:
        w["wait"] = got["trip"]["wait"]
    if got.get("parked"):
        w["parked"] = got["parked"]
    o = got.get("outcome")
    if o is None:
        return w
    w.update({"string_sha12": o["string_sha12"], "ticks": o["ticks"], "taint": o["taint"], "flaps": o["flaps"],
              "hp_lost": o["hp0"] - o["hp_min"], "labels": o["labels"], "by": "confirmed",
              "rank": max(w["rank"], min_rank(o))})      # AZ-839: never under the kernel's (the module docstring)
    return w


def closure(adj: dict, sources) -> set:
    """The nodes reachable from ``sources`` (themselves included) over ``adj``."""
    seen, todo = set(sources), list(sources)
    while todo:
        for b in adj.get(todo.pop(), ()):
            if b not in seen:
                seen.add(b)
                todo.append(b)
    return seen


def components(adj: dict) -> list[list]:
    """The strongly connected components of ``adj`` (iterative Tarjan), each sorted, in discovery order."""
    nodes = sorted(set(adj) | {b for bs in adj.values() for b in bs})
    index, low, on, stack, out, n = {}, {}, set(), [], [], 0
    for root in nodes:
        if root in index:
            continue
        work = [(root, iter(sorted(adj.get(root, ()))))]
        index[root] = low[root] = n
        n += 1
        stack.append(root)
        on.add(root)
        while work:
            v, it = work[-1]
            for w in it:
                if w not in index:
                    index[w] = low[w] = n
                    n += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(sorted(adj.get(w, ())))))
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[v])
                if low[v] == index[v]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on.discard(w)
                        comp.append(w)
                        if w == v:
                            break
                    out.append(sorted(comp))
    return out
