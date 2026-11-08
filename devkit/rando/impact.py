"""``python -m devkit rando impact``: rank the randomizer's unknowns by their impact on the default fill (Modkit's
``rando_impact.py``: D168 (1), the research report's P1, its Step X.3; Step 4.13b).

D157 proves spots in xemu until the default settings fill 99 % of seeds (D143: progression goes only on proven
spots) and D158 walks the level files' ``assumed`` edges in xemu. This dev tool orders both queues by counterfactual
solves on the shipped database (or ``--db``) under its default settings, over a fixed seed sample (``--seeds``):

- **Spots** (D157). A candidate is an unproven non-gem authored pool spot a progression item could take once proven
  (not excluded, pre-filled or a vault: ``_Slots.open_proven``'s filter). Two cheap proxies rank them: the failing
  seeds (and attempts) in whose stuck reach it lies (the reach of a progression item that found no free proven
  spot), and the progression items that, alone on it with no other progression held, are collected there (a
  first-sphere spot: the way back may need that item; a stuck opener's reach holds no non-gem spot at all, so
  only these give the opener a place); then the earliest sphere of vanilla's playthrough. The top ``--singles``
  are pretended proven one at a time and the fill re-run on every seed: the gain in seeds that fill. Then a greedy
  set: each round tries the ``--width`` best-ranked candidates on the seeds still failing (round 1 reads the
  singles), keeps the one that fixes most (the ranking breaks ties and picks when none fixes one alone), re-runs
  the seeds that filled, and stops at ``--target`` of the seeds, after ``--rounds``, or when no candidate is left.
- **Edges** (D158). Every ``assumed`` edge (the loader's count: an edge with no confidence is assumed) is removed in
  turn and the logic recompiled: does the vanilla placement still win and collect everything, how many locations
  every item held from the start no longer reaches (cut), how many vanilla's playthrough loses or collects in a
  later sphere, and how many proven open spots the fill's opening reach (every unplaced item it reads assumed, and
  the same without the progression items) loses. A cut fails every fill's verify (the reach is monotone in the items
  held, D113), so its fill rate is 0 with no run; the ``--edge-fills`` other edges with most effect get the fill
  re-run on every seed. Edges rank by tier (breaks vanilla's victory, cuts locations, lowers the fill rate, changes
  the playthrough or the opening, no effect: it can wait), then by size.

The fill is :func:`azurkit.tools.randomizer.planner.fill.fill`'s attempt loop with the proven set swapped (the writer's
layout check aside). Each of ``--jobs`` processes loads and compiles the database once (the solver compiles each
option set once per :class:`~azurkit.tools.randomizer.planner.solver.Logic`) and recompiles only with an edge removed.
It writes ``impact.json`` (everything) and ``impact.txt`` (the greedy set and the top ``--top`` spots and edges,
each with its level, its place and why) to ``--out`` and prints each stage's wall time. It reads only the randomizer
database and the realm authoring files (for the places' names: ``devkit/rando/draft/authoring``, which the authoring's
port brings; until then the places are named by their zones), no game files, and prints no game bytes.

    uv run --locked python -m devkit rando impact --out DIR [--seeds 0-49] [--jobs 12] [--db DIR]
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import math
import multiprocessing
import re
import time
import tomllib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from azurkit.tools.randomizer.planner.fill import (
    MAX_ATTEMPTS,
    _Slots,
    _Stuck,
    db_digest,
    known_traps,
    settings_digest,
    settings_table,
    stream,
)
from azurkit.tools.randomizer.planner.loader import load_database
from azurkit.tools.randomizer.planner.settings import MOVEMENT_TIERS, category
from azurkit.tools.randomizer.planner.solver import Logic
from devkit.xemu.queue import BatchToken

AUTHORING = Path(__file__).resolve().parent / "draft" / "authoring"   # the realm steps' node names (comments), hand edges
TIERS = ("breaks vanilla", "cuts locations", "lowers the fill rate", "changes the playthrough", "no effect")
CHUNK = 10                                               # seeds per edge-fill unit (one recompile each)


class Ctx:
    """A database's logic, compiled once, and the fill's facts under its default settings."""

    def __init__(self, db) -> None:
        self.db, self.st = db, db.defaults
        self.logic = lg = Logic(db)
        self.slots = s = _Slots(lg)
        self.proven = s.proven
        self.reads = lg.reads(self.st)
        self.digest = settings_digest(self.st)
        self.cands = frozenset(loc for loc in s.pool if loc not in s.proven and s.kind[loc] == "nongem"
                               and loc not in s.excluded and loc not in s.prefilled and loc not in s.vault)
        self.open = frozenset(s.open_proven())
        self.known = None

    def fill(self, seed: str, extra=()) -> tuple[int | None, list[list[str]]]:
        """``seed``'s default fill with ``extra`` proven too: the first attempt that passes (None: none of
        :data:`MAX_ATTEMPTS`) and, when none does, the candidates in each stuck progression item's reach."""
        if self.known is None:
            self.known = known_traps(self.logic, self.st)
        extra = frozenset(extra)
        self.slots.proven = self.proven | extra
        stuck = []
        try:
            for k in range(MAX_ATTEMPTS):
                try:
                    self.slots.attempt(self.st, self.reads, lambda name, k=k: stream(
                        str(seed), name if k == 0 else f"attempt{k}/{name}", self.digest), self.known)
                except _Stuck as exc:
                    if exc.item is not None:          # no safe proven spot for exc.item
                        stuck.append(sorted(exc.got & self.cands - extra))
                    continue
                return k, []
            return None, stuck
        finally:
            self.slots.proven = self.proven

    def _state(self) -> tuple[dict, list[str], list[str]]:
        """The fill's opening state (fill.py's ``attempt``): the pre-filled placement, every unplaced item the
        logic reads (assumed), and those that aren't progression."""
        s, lg = self.slots, self.logic
        placed = dict(s.prefilled)
        placed.update((loc, it) for loc, it in s.vanilla.items()
                      if category(s.names.base[it]) in self.st.exclude_categories)
        read = {name for name, cs in lg.items.items() if cs.keys() & self.reads.keys()}
        assumed = sorted(s.vanilla[loc] for loc in s.pool if loc not in placed and s.vanilla[loc] in read)
        return placed, assumed, [it for it in assumed if s.cls[it] != "progression"]

    def opening(self) -> tuple[frozenset[str], frozenset[str]]:
        """The fill's opening reach: all assumed, and no progression item assumed."""
        placed, assumed, late = self._state()
        return (self.logic.reach(self.st, placed, assumed, traps=False).locations,
                self.logic.reach(self.st, placed, late, traps=False).locations)

    def first(self, spot: str) -> tuple[list[str], int]:
        """The progression items that, put alone on ``spot`` at the opening with no progression item assumed,
        are collected there (``spot`` is a first-sphere spot for them: the way back may need the item itself),
        and the most non-gem spots one of them then reaches."""
        placed, _, late = self._state()
        nongem = {loc for loc in self.slots.pool if self.slots.kind[loc] == "nongem"}
        out, most = [], 0
        for item in sorted({it for it in self.slots.cls if self.slots.cls[it] == "progression"}):
            got = self.logic.reach(self.st, {**placed, spot: item}, late, traps=False).locations
            if spot in got:
                out.append(item)
                most = max(most, len(got & nongem))
        return out, most

    def profile(self) -> dict:
        """What an edge's removal is measured by: vanilla's playthrough (victory, everything collected, each
        location's sphere), what every item held from the start reaches, and the opening's proven open spots."""
        lg, st = self.logic, self.st
        authored = frozenset(loc for loc, lvl in lg.pool.items() if lvl not in self.db.stubs)
        trace = []
        van = lg.reach(st, None, trace=trace, traps=False)
        every = [lg.vanilla[loc][0] for loc in sorted(lg.pool) for _ in range(lg.vanilla[loc][1])]
        opening, late = self.opening()
        return {"victory": van.victory, "full": not (authored - van.locations - lg.forfeitable),
                "sphere": {loc: i for i, sp in enumerate(trace, 1) for loc in sp.locations if loc in authored},
                "every": authored & lg.reach(st, None, every, traps=False).locations,
                "open": self.open & opening, "late": self.open & late}


# ---- the workers: each loads and compiles once; an edge unit recompiles with its edge removed --------------------
_W: dict = {}


def _init(root: str | None) -> None:
    db = load_database(Path(root)) if root else load_database()
    _W.clear()
    _W.update(db=db, edge=None, base=Ctx(db))
    _W["profile"] = _W["base"].profile()


def _restore() -> None:
    if _W["edge"] is not None:
        (lvl, i), e, _ = _W["edge"]
        _W["db"].levels[lvl]["edge"].insert(i, e)
        _W["edge"] = None


def _without(key: tuple[str, int]) -> Ctx:
    """The database with edge ``key`` (level, index) removed, compiled; kept for the next unit."""
    if _W["edge"] is None or _W["edge"][0] != key:
        _restore()
        lvl, i = key
        e = _W["db"].levels[lvl]["edge"].pop(i)
        _W["edge"] = (key, e, None)
        _W["edge"] = (key, e, Ctx(_W["db"]))
    return _W["edge"][2]


def _effects(base: dict, ctx: Ctx) -> dict:
    p = ctx.profile()
    later = {loc: p["sphere"][loc] - n for loc, n in base["sphere"].items() if p["sphere"].get(loc, 0) > n}
    cut = sorted(base["every"] - p["every"] - ctx.logic.forfeitable)
    return {"victory": p["victory"], "full": p["full"], "vanilla_lost": len(base["sphere"].keys() - p["sphere"]),
            "cut": len(cut), "cut_ids": cut[:5], "later": len(later), "spheres_later": sum(later.values()),
            "open_lost": len(base["open"] - p["open"]), "late_lost": len(base["late"] - p["late"])}


def _run(unit: tuple):
    kind, *args = unit
    if kind == "fill":                      # ("fill", extra proven, seed)
        _restore()
        return _W["base"].fill(args[1], args[0])
    if kind == "first":                     # ("first", spot)
        _restore()
        return _W["base"].first(args[0])
    if kind == "edge":                      # ("edge", key)
        return _effects(_W["profile"], _without(args[0]))
    ctx = _without(args[0])                 # ("edgefill", key, seeds)
    return [ctx.fill(seed)[0] is not None for seed in args[1]]


class Runner:
    """Maps units over ``jobs`` processes (this one when 1), each with the database compiled once; one unit at a
    time while an xemu sitting waits for a slot (``BatchToken``, Step X.8)."""

    def __init__(self, root: Path | None, jobs: int) -> None:
        arg = str(root) if root else None
        _init(arg)
        self.pool = self.token = None
        if jobs > 1:
            self.pool = ProcessPoolExecutor(jobs, mp_context=multiprocessing.get_context("spawn"), initializer=_init,
                                            initargs=(arg,))
            self.token = BatchToken("rando impact", jobs)

    def map(self, units: list) -> list:
        if self.pool is None:
            try:
                return [_run(u) for u in units]
            finally:
                _restore()
        return list(self.token.ordered(self.pool, _run, [(u,) for u in units]))

    def close(self) -> None:
        if self.pool is not None:
            self.token.close()
            self.pool.shutdown()


# ---- the spots (D157) ----------------------------------------------------------------------------------------------
def _fills(results: dict) -> int:
    return sum(k is not None for k, _ in results.values())


def proxy(results: dict, exclude=frozenset()) -> dict[str, tuple[int, int]]:
    """Each candidate -> (failing seeds, stuck attempts) whose stuck reach holds it."""
    seeds, tries = collections.Counter(), collections.Counter()
    for k, stuck in results.values():
        if k is None:
            for got in stuck:
                tries.update(set(got) - exclude)
            seeds.update({c for got in stuck for c in got} - exclude)
    return {c: (seeds[c], tries[c]) for c in seeds}


def ranked(results: dict, first: dict, sphere: dict, exclude=frozenset()) -> list[tuple[str, tuple]]:
    """The candidates, best first, each with its key: in the most failing seeds' stuck reaches, then a
    first-sphere spot for the most progression items, opening the most, then the earliest sphere of vanilla's
    playthrough (none: last)."""
    px = proxy(results, exclude)
    keys = {c: (*px.get(c, (0, 0)), len(first[c][0]), first[c][1], -sphere.get(c, 999)) for c in first
            if c not in exclude}
    return sorted(keys.items(), key=lambda ck: (tuple(-x for x in ck[1]), ck[0]))


def _trial(runner: Runner, chosen: list[str], cands: list[str], seeds: list[str]) -> dict[str, dict]:
    units = [("fill", tuple(chosen) + (c,), s) for c in cands for s in seeds]
    out = {c: {} for c in cands}
    for (_, extra, s), r in zip(units, runner.map(units)):
        out[extra[-1]][s] = r
    return out


def greedy(runner: Runner, seeds: list[str], base: dict, first: dict, sphere: dict, singles: dict, width: int,
           target: float, rounds: int) -> dict:
    need = math.ceil(target * len(seeds) - 1e-9)
    chosen, results, steps, stop = [], base, [], None
    while _fills(results) < need:
        if len(chosen) >= rounds:
            stop = f"{rounds} rounds"
            break
        order = ranked(results, first, sphere, frozenset(chosen))[:width]
        if not order:
            stop = "no candidate left"
            break
        top, key = [c for c, _ in order], dict(order)
        failing = [s for s in seeds if results[s][0] is None]
        passing = [s for s in seeds if results[s][0] is not None]
        tried = {c: singles[c] for c in top if not chosen and c in singles}
        tried.update(_trial(runner, chosen, [c for c in top if c not in tried], failing))
        fixed = {c: sum(tried[c][s][0] is not None for s in failing) for c in top}
        best = min(top, key=lambda c: (-fixed[c], top.index(c)))
        new = dict(results)
        new.update({s: tried[best][s] for s in failing})
        new.update(tried[best] if all(s in tried[best] for s in passing)
                   else _trial(runner, chosen, [best], passing)[best])
        chosen.append(best)
        steps.append({"spot": best, "fills": _fills(new), "fixed": fixed[best],
                      "broken": sum(new[s][0] is None for s in passing), "key": list(key[best])})
        results = new
    return {"target": target, "need": need, "reached": _fills(results) >= need, "stop": stop, "proofs": steps}


# ---- places --------------------------------------------------------------------------------------------------------
def _named() -> dict[str, str]:
    """Each node the authoring names -> its comment (``[names]``: node = zone  # what it is)."""
    out = {}
    for p in sorted(AUTHORING.glob("*.toml")):
        section = None
        for line in p.read_text(encoding="utf-8").splitlines():
            if m := re.match(r"\s*\[([^\]]+)\]", line):
                section = m.group(1)
            elif section == "names" and (m := re.match(r'\s*(\w+)\s*=\s*"[^"]*"\s*#\s*(.+)', line)):
                out[m.group(1)] = m.group(2).strip()
    return out


class Places:
    """Human-readable places: a node's name from the authoring, else its zones and what it holds; an edge's
    source: the authoring's hand edge between its nodes' zones, else the derived probe-needed edges there."""

    def __init__(self, ctx: Ctx) -> None:
        db = self.db = ctx.db
        self.named = _named()
        self.vanilla = ctx.logic.vanilla
        self.held = collections.defaultdict(list)
        for loc, node in db.node_of.items():
            self.held[node].append(loc)
        self.hand = collections.defaultdict(list)
        for p in sorted(AUTHORING.glob("*.toml")):
            for e in tomllib.loads(p.read_text(encoding="utf-8")).get("edge", []):
                self.hand[(e["from"], e["to"])].append(e.get("why", ""))
        self.probes = collections.defaultdict(collections.Counter)
        for doc in db.derived.values():
            for e in doc.get("edges", ()):
                if e.get("confidence") == "probe-needed":
                    self.probes[(e["from"], e["to"])][f"{e['kind']}/{e.get('probe')}"] += 1

    def zones(self, node: str) -> list[str]:
        row = self.db.nodes[node][1] if node in self.db.nodes else {}
        return [a.split(":", 1)[1] for a in row.get("anchors", []) if a.startswith("zone:")]

    def node(self, node: str) -> str:
        if not node:
            return "(an arrival into the level)"
        if node in self.named:
            return f"{node}: {self.named[node]}"
        zs = self.zones(node) or (self.db.nodes[node][1].get("anchors", []) if node in self.db.nodes else [])
        items = collections.Counter(self.vanilla[loc][0] for loc in self.held.get(node, ()) if loc in self.vanilla)
        holds = ", ".join(f"{it} x{n}" if n > 1 else it for it, n in items.most_common(4))
        return (f"{node}: unnamed, {', '.join(zs[:3])}{f' (+{len(zs) - 3})' if len(zs) > 3 else ''}"
                + (f"; holds {holds}" if holds else ""))

    def source(self, e: dict) -> str:
        za, zb = self.zones(e["from"]) if e["from"] else [], self.zones(e["to"]) if e["to"] else []
        whys = [w for a in za for b in zb for w in self.hand.get((a, b), ())]
        if whys:
            w = whys[0]
            return "hand edge: " + (w if len(w) <= 240 else w[:237] + "...")
        probes = collections.Counter()
        for a in za:
            for b in zb:
                probes.update(self.probes.get((a, b), {}))
        if probes:
            return "derived probe-needed edges between its zones: " + ", ".join(
                f"{k} x{n}" for k, n in sorted(probes.items(), key=lambda kv: (-kv[1], kv[0])))
        return "no direct derived or hand edge between its zones (a path through zones the authoring contracted)"


# ---- the analysis --------------------------------------------------------------------------------------------------
def _assumed(db) -> list[tuple[str, int]]:
    return [(lvl, i) for lvl in sorted(db.levels) for i, e in enumerate(db.levels[lvl]["edge"])
            if e.get("confidence", "assumed") == "assumed"]


def _changes(e: dict) -> bool:
    return bool(not e["full"] or e["vanilla_lost"] or e["later"] or e["open_lost"] or e["late_lost"])


def _tier(e: dict, base: int) -> int:
    if not e["victory"]:
        return 0
    if e["cut"]:
        return 1
    if e.get("fills") is not None and e["fills"] < base:
        return 2
    return 3 if _changes(e) else 4


def analyse(root: Path | None, seeds: list[str], jobs: int = 12, singles: int = 24, width: int = 12,
            edge_fills: int = 12, rounds: int = 10, target: float = 0.99) -> dict:
    """The whole ranking (the module docstring), as the JSON report's object."""
    wall, t0 = {}, time.perf_counter()
    runner = Runner(root, jobs)
    try:
        ctx = _W["base"]
        db, n = ctx.db, len(seeds)
        tier_no = MOVEMENT_TIERS.index(ctx.st.movement_tier) + 1
        wall["start"] = time.perf_counter() - t0

        t = time.perf_counter()
        base = dict(zip(seeds, runner.map([("fill", (), s) for s in seeds])))
        base_fills = _fills(base)
        wall["baseline"] = time.perf_counter() - t
        print(f"baseline: {wall['baseline']:.0f} s", flush=True)

        t = time.perf_counter()
        spots_ = sorted(ctx.cands | ctx.open)
        first = dict(zip(spots_, runner.map([("first", c) for c in spots_])))
        wall["first_sphere"] = time.perf_counter() - t
        print(f"first_sphere: {wall['first_sphere']:.0f} s", flush=True)

        t = time.perf_counter()
        px = proxy(base)
        cand_first = {c: first[c] for c in ctx.cands}
        sphere = _W["profile"]["sphere"]
        picked = [c for c, _ in ranked(base, cand_first, sphere)[:singles]]
        single = _trial(runner, [], picked, seeds)
        wall["singles"] = time.perf_counter() - t
        print(f"singles: {wall['singles']:.0f} s", flush=True)

        t = time.perf_counter()
        chosen = greedy(runner, seeds, base, cand_first, sphere, single, width, target, rounds)
        wall["greedy"] = time.perf_counter() - t
        print(f"greedy: {wall['greedy']:.0f} s", flush=True)

        t = time.perf_counter()
        keys = _assumed(db)
        eff = dict(zip(keys, runner.map([("edge", k) for k in keys])))
        wall["edges"] = time.perf_counter() - t
        print(f"edges: {wall['edges']:.0f} s", flush=True)

        t = time.perf_counter()
        fill_keys = sorted((k for k in keys if not eff[k]["cut"] and _changes(eff[k])), key=lambda k: (
            not eff[k]["victory"], -eff[k]["vanilla_lost"], -eff[k]["late_lost"], -eff[k]["open_lost"],
            -eff[k]["spheres_later"], k))[:edge_fills]     # where the fill decides the tier first
        units = [("edgefill", k, tuple(seeds[i:i + CHUNK])) for k in fill_keys for i in range(0, n, CHUNK)]
        got = collections.Counter()
        for (_, k, _), r in zip(units, runner.map(units)):
            got[k] += sum(r)
        for k in keys:
            if eff[k]["cut"]:
                eff[k].update(fills=0, fills_by="implied: every fill's verify misses the cut locations")
            elif k in fill_keys:
                eff[k].update(fills=got[k], fills_by="measured")
        wall["edge_fills"] = time.perf_counter() - t
        print(f"edge_fills: {wall['edge_fills']:.0f} s", flush=True)
    finally:
        runner.close()
    wall["total"] = time.perf_counter() - t0

    places = Places(ctx)
    opening, late = (_W["profile"]["open"], _W["profile"]["late"])
    reach_open, reach_late = ctx.opening()
    failing = n - base_fills
    every = len({it for it, c in ctx.slots.cls.items() if c == "progression"})
    key = dict(ranked(base, cand_first, sphere))

    def firsts(c: str) -> str:
        items, most = first[c]
        if not items:
            return "no first-sphere spot" + (f" (vanilla collects it in sphere {sphere[c]})" if c in sphere else "")
        return (f"a first-sphere spot for {'any progression item' if len(items) == every else ', '.join(items)} "
                f"(collected with nothing else held; opens up to {most} non-gem spots)")

    spots = []
    for c in sorted(ctx.cands):
        lvl, node = ctx.logic.pool[c], db.node_of.get(c, "")
        fills = _fills(single[c]) if c in single else None
        row = ctx.logic.location_rows.get(c, {})
        early = ("reachable at the fill's opening with no progression item" if c in reach_late else
                 "reachable at the fill's opening once progression is assumed" if c in reach_open else
                 "not reachable at the fill's opening")
        p = px.get(c, (0, 0))
        spots.append({
            "id": c, "level": lvl, "node": node, "place": places.node(node), "vanilla": ctx.logic.vanilla[c][0],
            "requires": row.get("requires", "true"), "note": row.get("note", ""), "stuck": list(p),
            "first_sphere_for": first[c][0], "opens": first[c][1], "vanilla_sphere": sphere.get(c),
            "fills": fills, "gain": None if fills is None else fills - base_fills,
            "fixed": None if fills is None else sum(single[c][s][0] is not None for s in seeds if base[s][0] is None),
            "broken": None if fills is None else sum(single[c][s][0] is None for s in seeds if base[s][0] is not None),
            "early": early,
            "why": "; ".join([*([f"in the stuck reach of {p[0]} of {failing} failing seeds ({p[1]} attempts)"]
                                if p[0] else []), firsts(c), early,
                              f"proven alone: {fills} of {n} seeds fill ({fills - base_fills:+d})" if fills is not None
                              else f"not run (below the top {singles})"]),
            "_rank": (fills is None, -(fills or 0), tuple(-x for x in key.get(c, (0, 0, 0, 0))), c)})
    spots.sort(key=lambda r: r.pop("_rank"))
    first_proven = {c: first[c][0] for c in sorted(ctx.open) if first[c][0]}

    edges = []
    for k in keys:
        lvl, i = k
        e, x = db.levels[lvl]["edge"][i], eff[k]
        out_of_logic = not e.get("logic", True) or e.get("difficulty", 1) > tier_no or e.get("difficulty", 1) < 1
        tier = _tier(x, base_fills)
        why = []
        if not x["victory"]:
            why.append(f"vanilla can't win without it ({x['vanilla_lost']} vanilla locations lost)")
        elif not x["full"]:
            why.append(f"vanilla wins but no longer collects {x['vanilla_lost']} locations")
        if x["cut"]:
            why.append(f"cuts {x['cut']} locations even with every item ({', '.join(x['cut_ids'])}"
                       f"{', ...' if x['cut'] > len(x['cut_ids']) else ''}): no seed can fill")
        elif x.get("fills") is not None:
            why.append(f"the fill: {base_fills} -> {x['fills']} of {n} seeds")
        if x["later"]:
            why.append(f"vanilla collects {x['later']} locations later ({x['spheres_later']} spheres in all)")
        if x["late_lost"] or x["open_lost"]:
            why.append(f"the fill's opening loses {x['late_lost']} proven spots with no progression item, "
                       f"{x['open_lost']} with all assumed")
        if not why:
            why.append("no effect on the default logic" + (
                " (out of it: " + ("logic = false" if not e.get("logic", True) else
                                   f"difficulty {e.get('difficulty', 1)} above {ctx.st.movement_tier}")
                + "; R_phys only)" if out_of_logic else ""))
        edges.append({
            "level": lvl, "index": i, "from": e["from"], "to": e["to"], "kind": e["kind"],
            "requires": e.get("requires", "true"), "difficulty": e.get("difficulty", 1),
            "logic": e.get("logic", True), "through": e.get("through", []), "exit": e.get("exit"),
            "explicit": "confidence" in e, "in_default_logic": not out_of_logic, "tier": TIERS[tier],
            "from_place": places.node(e["from"]), "to_place": places.node(e["to"]), "source": places.source(e),
            **{f: x[f] for f in ("victory", "full", "vanilla_lost", "cut", "cut_ids", "later", "spheres_later",
                                 "open_lost", "late_lost")},
            "fills": x.get("fills"), "fills_by": x.get("fills_by", "not run"), "why": "; ".join(why),
            "_rank": (tier, -x["cut"], -x["vanilla_lost"], -(base_fills - x["fills"] if x.get("fills") is not None
                                                             else 0),
                      -x["late_lost"], -x["open_lost"], -x["spheres_later"], lvl, i)})
    edges.sort(key=lambda r: r.pop("_rank"))
    for proof in chosen["proofs"]:
        s = next(s for s in spots if s["id"] == proof["spot"])
        proof.update(level=s["level"], place=s["place"], vanilla=s["vanilla"])
    return {
        "step": "X.3", "decision": "D168 (1)", "date": datetime.date.today().isoformat(), "db_digest": db_digest(db),
        "settings": settings_table(ctx.st), "seeds": seeds, "jobs": jobs, "wall_s": {k: round(v, 1) for k, v in
                                                                                       wall.items()},
        "params": {"singles": singles, "width": width, "edge_fills": edge_fills, "rounds": rounds, "target": target},
        "baseline": {"fills": base_fills, "of": n, "failing": [s for s in seeds if base[s][0] is None],
                     "open_proven": len(ctx.open), "open_proven_no_progression": len(late),
                     "open_proven_all_assumed": len(opening), "candidates": len(ctx.cands),
                     "candidates_in_a_stuck_reach": len(px), "candidates_first_sphere": sum(
                         1 for c in ctx.cands if first[c][0]),
                     "open_proven_first_sphere": {c: (items if len(items) < every else ["any"])
                                                  for c, items in first_proven.items()},
                     "assumed_edges": len(keys)},
        "greedy": chosen, "spots": spots, "edges": edges,
        "edge_tiers": dict(collections.Counter(e["tier"] for e in edges))}


def text(doc: dict, top: int) -> str:
    """The ranked text report."""
    b, n, g = doc["baseline"], len(doc["seeds"]), doc["greedy"]
    st = doc["settings"]
    lines = [f"Step X.3 impact ranking (D168 (1), D157, D158), {doc['date']}, database {doc['db_digest'][:12]}",
             f"settings: the defaults (skip_ceiling {st['skip_ceiling']}, {st['movement_tier']}, dark_fire "
             f"{st['dark_fire']}); seeds {doc['seeds'][0]}..{doc['seeds'][-1]} ({n}); {doc['jobs']} processes",
             "wall time (s): " + ", ".join(f"{k} {v}" for k, v in doc["wall_s"].items()),
             f"baseline: {b['fills']} of {n} seeds fill ({100 * b['fills'] / n:.0f} %); {b['open_proven']} proven open "
             f"spots, of which the fill's opening reaches {b['open_proven_all_assumed']} with all assumed and "
             f"{b['open_proven_no_progression']} with no progression item; {b['candidates']} unproven candidate "
             f"spots, {b['candidates_in_a_stuck_reach']} in a failing seed's stuck reach and "
             f"{b['candidates_first_sphere']} first-sphere spots; {b['assumed_edges']} assumed edges",
             f"first-sphere proven open spots (collected with only their own item, from the start): "
             + ("; ".join(f"{c} for {', '.join(it)}" for c, it in b["open_proven_first_sphere"].items()) or "none"),
             "",
             f"GREEDY PROOFS (D157): to {g['target']:.0%} of the seeds ({g['need']} of {n})"]
    for r, p in enumerate(g["proofs"], 1):
        lines.append(f"  {r}. {p['spot']} ({p['place']}; vanilla {p['vanilla']}): {p['fills']} of {n} fill "
                     f"(fixed {p['fixed']}, broke {p['broken']})")
    lines.append(f"  result: {len(g['proofs'])} proofs " + (f"reach {g['need']} of {n}" if g["reached"] else
                                                              f"don't reach {g['need']} of {n} (stopped: {g['stop']})"))
    lines += ["", f"TOP {top} SPOTS TO PROVE (D157): one proof each, by fill gain, then stuck reaches and first "
                  f"spheres"]
    for r, s in enumerate(doc["spots"][:top], 1):
        gain = "not run" if s["gain"] is None else f"{s['gain']:+d} ({s['fills']}/{n}, fixed {s['fixed']}, " \
                                                  f"broke {s['broken']})"
        lines += [f"  {r:2}. {s['id']}  {gain}",
                  f"      {s['level']} {s['place']}; vanilla {s['vanilla']}"
                  + (f"; requires {s['requires']}" if s["requires"] != "true" else ""),
                  f"      why: {s['why']}"]
    lines += ["", f"TOP {top} EDGES TO WALK (D158): by tier ({', '.join(TIERS)}), then size"]
    for r, e in enumerate(doc["edges"][:top], 1):
        extra = "".join([f", difficulty {e['difficulty']}" if e["difficulty"] != 1 else "",
                         f", through {', '.join(e['through'])}" if e["through"] else "",
                         f", exit {e['exit']}" if e["exit"] else "", ", logic = false" if not e["logic"] else ""])
        lines += [f"  {r:2}. [{e['tier']}] {e['level']} edge #{e['index']}: {e['from'] or '(arrival)'} > "
                  f"{e['to']} ({e['kind']}, requires {e['requires']}{extra})",
                  f"      from {e['from_place']}", f"      to   {e['to_place']}",
                  f"      source: {e['source']}", f"      why: {e['why']}"]
    lines += ["", "EDGES BY TIER: " + ", ".join(f"{t} {doc['edge_tiers'].get(t, 0)}" for t in TIERS),
              f"  of the no-effect ones, out of the default logic: "
              f"{sum(1 for e in doc['edges'] if e['tier'] == 'no effect' and not e['in_default_logic'])}"]
    return "\n".join(lines) + "\n"


def _seeds(text_: str) -> list[str]:
    out = []
    for part in text_.split(","):
        a, _, b = part.partition("-")
        out += [str(s) for s in range(int(a), int(b) + 1)] if b else [a.strip()]
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m devkit rando impact", description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", type=Path, required=True, help="the folder for impact.json and impact.txt")
    ap.add_argument("--db", type=Path, help="a database folder (default: the shipped one)")
    ap.add_argument("--seeds", default="0-49", help="the seed sample: A-B ranges and single seeds, comma-separated")
    ap.add_argument("--jobs", type=int, default=12)
    ap.add_argument("--singles", type=int, default=24, help="the best-ranked candidates proven one at a time")
    ap.add_argument("--width", type=int, default=12, help="candidates each greedy round tries")
    ap.add_argument("--rounds", type=int, default=10, help="the greedy's most proofs")
    ap.add_argument("--target", type=float, default=0.99, help="the greedy's fill rate")
    ap.add_argument("--edge-fills", type=int, default=12, help="edges whose removal gets the fill re-run")
    ap.add_argument("--top", type=int, default=30, help="the text report's rows per list")
    args = ap.parse_args(argv)
    doc = analyse(args.db, _seeds(args.seeds), args.jobs, args.singles, args.width, args.edge_fills, args.rounds,
                  args.target)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "impact.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    (args.out / "impact.txt").write_text(text(doc, args.top), encoding="utf-8")
    print(f"wall (s): {doc['wall_s']}; baseline {doc['baseline']['fills']} of {len(doc['seeds'])}; greedy "
          f"{len(doc['greedy']['proofs'])} proofs, reached {doc['greedy']['reached']}; wrote {args.out}")
    return 0
