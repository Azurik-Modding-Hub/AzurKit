"""Certify the randomizer's spots and edges with L3, the simulator of the game's own code (Step X.7, D170, D172).

A spot or an edge counts as proven ``by = "l3"`` once an L3 input string that reaches it has replayed in xemu with
the same trajectory, tick for tick (D170), and its record is in ``src/azurkit/tools/randomizer/data/proofs.jsonl``
(``azurkit.tools.randomizer.planner.proofs``: the claim, the start as a recipe, the string, the outcome; no
coordinates, no RAM).  The pipeline keeps its public files in a folder ``DIR`` (targets, counts, strings, hashes);
the private parts (the reach models, the teleport points) go to the L3 store's ``x7`` folder (mode 700,
``devkit.sim.l3.store``), where the snapshots are (a level's reach model: ``devkit.reach.models.reach_path``).

1. ``plan``: the top spots and edges of ``devkit/rando/impact.py``'s ``impact.json`` files become targets, each a
   level, a kit (element levels), a start zone and a goal.  A spot starts in the level's arrival node from which the
   logic reaches it with nothing held (fewest assumed edges), touches it and comes back there; an edge walks from
   its from-node to its to-node holding its requirement, when that is element levels.  Anything else (a button, a
   flag, an event, a key) is reported as not set up.  Each level gets an R7 hop (an exit into it).
2. ``sitting DIR W snapshots``, in a sandbox (``python -m devkit xemu oracle up``): per level and kit, ``loadvm vanilla-rz-new``
   (a new game: the level's items untaken), the hop, the kit (R2's element levels and every first-pickup popup
   bit, so a pickup opens no dialog), until the stick moves the player, ``savevm`` into the sandbox's clone and an
   L3 snapshot at the scene tick.
3. ``search DIR``: per target (edges first), the start: the snapshot's own spot when it lies in the start zone, else
   a teleport (R6) onto the start zone's sample (a floor or the water) nearest the goal that lands and settles
   there; the guidance: the logic profile's route graph, or the phys profile's when the logic's has no path from
   the start, else the straight line to where the goal's field reaches; seeds: the route planner's plan and earlier
   runs' winners from the same start; then ``l3_pool.solve_many``, every target of a level and kit at once on one
   persistent worker pool on its snapshot (Go-Explore, derived seeds, a step budget, the lowest seed index that
   reaches wins, whatever the worker count); a spot's way back is a second leg chained on the first.  The winner is
   checked again in whole steps (enemies, rigs and the pickup move there).  Failures say why: every seed explored
   all it reached (the logic is wrong, or the move set misses a way) or the step budget ran out; a failure whose
   runs read what L3 doesn't model (their taint: a file read, a clock, a high page, a kernel call) is
   ``inconclusive``, never a refutation.  A failed leg keeps its faults by site, its kernel taints' callers and
   each seed's stall (the edge ahead of its best cell, at the plan's level edge), collected in ``stalls.json``
   (Step X.52).
4. ``sitting DIR W replays``: per winner, ``loadvm`` the level's state, a fresh snapshot, L3 reruns the string from
   it (whole steps; it must still reach), then ``Sandbox.replay`` and ``l3_compare``: proven when every tick's body
   centre, state and HP match; then a snapshot exactly where the replay halted, linked to its parent (D172's
   chain: no tick between two segments goes unrecorded).  A skip to a pickup is proven where xemu takes it
   (``pickup_at``); a recorded pickup proof the fixed rule (AZ-389) doesn't keep is replayed again.  A tour
   target's replay has stops (a level load ends it there) and an outcome (AZ-474, :func:`judge`): an exit is
   proven by its destination's or its movie's load, a pickup or a counted item's reach by its item taken, each
   within the string or a tail of neutral ticks after it (:func:`tail`), a walk by every tick equal; a placed start
   within 1 m of the goal, or of the load when sooner, is ``near`` and proves no hop.
5. ``apply DIR --sitting NAME``: writes each proof's record into ``proofs.jsonl`` and ``proven = { by = "l3", ref =
   "<sitting>/<string sha12>@<meta sha12>" }`` into the authoring files (a spot's ``[[location]]``, an edge's
   ``[[probed]]`` walk); then run ``python -m devkit rando author`` for the levels.
6. ``recheck``: after a re-derive (zones are renumbered), re-run every record's string in L3 from its kept snapshot
   and re-zone its claim under the current derive (``--write`` rewrites the records and the ``[[probed]]`` walks).
7. ``pickups DIR``: every recorded pickup proof in ``DIR`` judged again under the fixed rule (AZ-389: xemu took the
   goal's own item), reading the folder only (``--out FILE``: the result as JSON there); one that no longer holds is
   replayed again by ``sitting DIR W replays``.

Step R1.16 (D206): ``plan --tour PROGRESS`` makes the targets from a progress file's ``certify`` list (the golden
seed's tour of the spheres xemu doesn't play, progression only, and each counted item's pickup from its node): a walk
from its from-node's zone to its to-node's zones, an exit (a cart, a disc teleport) into its trigger, a pickup or a
counted item from its node to the location, each at the tour's kit; an action (a barrier, a button, an event, a
minigame), a hop whose rule asks world state a new game plus a hop doesn't give and a pickup whose location's own gate
does (a blocker, a keylock door) are listed as not set up.  A tour
target's kit is set in L3 (``Segment.kit``), so one snapshot a level serves it (group ``<level>-k0``); ``adopt`` takes
each such group's newest earlier snapshot from the store (no sitting).  Then ``sitting snapshots``, ``search`` and
``sitting replays`` as above; ``apply`` writes nothing for them (the folder's results and replays are R1.16's record).

Step R1.29 (AZ-455): ``plan --spots`` takes location ids, each from the arrival whose way there and back asks the
least element levels (:func:`_local_path`'s ``kits``, a ``through`` barrier's crossing asked with its edge: AZ-517),
that kit, lowered to the most rando check takes a proof at (:func:`logic_kit`, AZ-570), set in L3 as a tour
target's, a spot its generated ``gated_by`` gates not set up; the search starts at
the hop's own arrival when it lies in that arrival node, else by R6 into it (``search --placed``: always by R6, at
least 2 m off the spot; ``--touch M``: the spot's reach in m, kept in ``targets.json`` for its checks), and its
whole-step check says whether L3 took the spot's own item (:func:`l3_taken`).  A spot is at a location
(:func:`at_location`, Step R1.29b): its goal is its item's own touch round where it rests and an R6 start stands in
the item's own cell (AZ-488's rule; ``--touch`` only for a species with no touch).  A spot's replay is judged by
:func:`judge_spot`: every tick L3's, xemu took its item, and no teleport within a metre of it for a start.
``apply`` writes its record (its way back walked only when the string started in the node it ends in) and its
mark, in the authoring's own ``[[location]]`` when it holds one (:func:`_mark_location`).

    uv run --locked python -m devkit reach l3-certify plan --impact IMPACT.json [MORE.json ...] --out DIR [--top 10]
    uv run --locked python -m devkit reach l3-certify plan --tour PROGRESS.json --out DIR
    uv run --locked python -m devkit reach l3-certify plan --spots ID [ID ...] --out DIR
    uv run --locked python -m devkit reach l3-certify sitting DIR W snapshots
    uv run --locked python -m devkit reach l3-certify adopt DIR
    uv run --locked python -m devkit reach l3-certify search DIR [--jobs 8] [--workers 16] [--steps 400000] [--only KEY]
        [--scene] [--dive 0.25] [--placed] [--touch 0.75]
    uv run --locked python -m devkit reach l3-certify sitting DIR W replays [--only KEY ...]
    uv run --locked python -m devkit reach l3-certify apply DIR --sitting NAME
    uv run --locked python -m devkit reach l3-certify apply-skips DIR --sitting NAME [--unreplayed] [--only ID ...]
        [--zoning SHA256]
    uv run --locked python -m devkit reach l3-certify recheck [--level L ...] [--write]
    uv run --locked python -m devkit reach l3-certify pickups DIR [--out FILE]

Dev only (devkit, Step 4.13d2), never a player's verb and never in pytest; the sandbox rules are the azurik-xemu-oracle skill's.
"""

from __future__ import annotations

import argparse
import collections
import functools
import gzip
import hashlib
import heapq
import itertools
import json
import math
import struct
import time
import tomllib
from pathlib import Path

from azurkit.tools.randomizer.live import recipes
from azurkit.tools.randomizer.planner import proofs as pr
from azurkit.tools.randomizer.planner.loader import DATA_DIR
from devkit.rando.draft.author import AUTHORING, dnf, read_derived
from devkit.rando.draft.l3_goal import (PROBES, ExitGoal, ObjectGoal, RouteGoal, exit_nodes, heading_to,
                                        item_touch, load_router, object_points, route_seed, router_of)
from devkit.reach.models import reach_path as _reach_path   # the level's reach model (Step 4.13d1's home of it)
from devkit.sim import corpus, douse as dz, l3
from devkit.sim.l3 import Pad
from devkit.sim.l3_search import (AIRBORNE, CAST_WAIT, DEAD, Limits, Seg, Segment, exits_text, expand, flaps_of,
                                  lands_alive, segments, settled, solve, stall_name, start_of, string_sha12)

ELEMENTS = recipes.ELEMENTS
INV_POPUPS = 0x14   # the inventory's first-pickup popup bits (R2's set_kit sets them all)
GEMS = ("emer", "diam", "ruby", "sapp")   # a gem on the way is no proof of another item
SETTLE = 20
START_TAG = "vanilla-rz-new"
GOAL_MODULE = "devkit.rando.draft.l3_goal"
PROOFS = DATA_DIR / pr.FILE


def _write(path: Path, doc) -> None:
    """``doc`` whole or not at all (AZ-640: ``results.json`` is rewritten as each target ends, so a kill mid-write
    must leave the last whole file): a temp file beside ``path``, then a rename over it."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def private() -> Path:
    """The pipeline's private folder: the L3 store's ``x7`` (mode 700)."""
    p = l3.store() / "x7"
    p.mkdir(mode=0o700, exist_ok=True)
    p.chmod(0o700)
    return p


def _priv(d: Path, key: str) -> Path:
    """A target's private start (its teleport point and leg goals) for the folder ``d``: ``x7/by-dir/<sha12 of
    d>/<key>.json`` (Step R1.29: two folders searching one key overwrote each other's flat ``x7/<key>.json``)."""
    return private() / "by-dir" / hashlib.sha256(str(d.resolve()).encode()).hexdigest()[:12] / f"{key}.json"


def _read_priv(d: Path, key: str) -> dict:
    """:func:`_priv`'s start, else a folder's older flat ``x7/<key>.json``."""
    p = _priv(d, key)
    return _read(p if p.exists() else private() / f"{key}.json")


def _write_priv(d: Path, key: str, doc: dict) -> None:
    p = _priv(d, key)
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _write(p, doc)


def kit_label(kit: dict) -> str:
    return "-".join(f"{k}{v}" for k, v in sorted(kit.items()) if v) or "k0"


def place_bytes(feet, yaw: float, cell: int) -> bytes:
    """R6's place struct (``L3.teleport`` writes the same), whose sha12 names a teleport in a record."""
    return recipes.place_struct(feet, yaw, cell=cell)


# -- 1. plan --------------------------------------------------------------------------------------------------------

def _db():
    levels = {p.stem: tomllib.loads(p.read_text(encoding="utf-8")) for p in sorted((DATA_DIR / "levels").glob("*.toml"))}
    gens = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((DATA_DIR / "generated").glob("*.json"))}
    level_of = {n["id"]: lvl for lvl, doc in levels.items() for n in doc.get("node", [])}
    return levels, gens, level_of


def _zones(doc: dict, node: str) -> list[str]:
    n = next(n for n in doc["node"] if n["id"] == node)
    return [a[5:] for a in n.get("anchors", []) if a.startswith("zone:")]


def _arrivals(level: str, levels, gens, level_of) -> dict[str, tuple[str, str, bool]]:
    """{node of ``level`` an exit from another level arrives in: (dest, spot, on a floor) of that exit (an R7
    hop; one the derive puts in no zone may drop the player to its death: e2's E5a_E2a)}."""
    objs = {o["id"]: o for o in json.loads(gzip.decompress((DATA_DIR / "derived" / f"{level}.json.gz").read_bytes()))
            .get("objects", [])}
    out = {}
    for src, doc in levels.items():
        if src == level:
            continue
        exits = {x["id"]: x for x in gens.get(src, {}).get("exits", [])}
        for e in doc.get("edge", []):
            x = exits.get(e.get("exit"))
            if e.get("kind") in ("exit", "teleport", "cart") and level_of.get(e["to"]) == level and x and x.get("spot"):
                floor = bool(objs.get(x.get("arrival"), {}).get("main_zone"))
                if floor or e["to"] not in out:
                    out[e["to"]] = (x["dest"], x["spot"], floor)
    return out


def _hop(arr: dict, node: str) -> list[str]:
    """The R7 hop into a level: the exit arriving in ``node`` if it lands on a floor, else one that does."""
    ok = sorted(n for n, a in arr.items() if a[2])
    a = arr[node] if node in arr and arr[node][2] else arr[ok[0]] if ok else arr.get(node) or arr[sorted(arr)[0]]
    return [a[0], a[1]]


def _kit(requires: str) -> dict | None:
    """The element levels a requirement asks (one term of element counters), None if it asks anything else."""
    terms = dnf(requires)
    return _kit_of(terms[0]) if len(terms) == 1 else None


def _through(db, bid: str, a: str, b: str) -> str:
    """Crossing the barrier ``bid`` from node ``a`` to ``b`` as a requirement (``solver.passes``, AZ-517): its
    destroy requirement (the generated one or its override, and the hand one) where it stays destroyed or ``a`` is
    one of its ``destroy_from`` nodes, or its bypass a -> b; ``false`` if neither."""
    o = db.hand[bid][2]
    gen = db.generated_objects[o["of"]][2] if "of" in o else {}
    base = o["override_requires"] if "override_requires" in o else (gen.get("requires") or "false") if "of" in o \
        else "true"
    persist = o.get("persist", gen.get("persist", "permanent"))
    opened = (f"({base}) & ({o.get('requires', 'true')})" if persist == "permanent" or a in o.get("destroy_from", ())
              else "false")
    bypass = o.get("bypass", {}).get(f"{a}->{b}")
    return f"({opened}) | ({bypass})" if bypass else opened


def _local_path(doc: dict, src: str, dst: str, kits: bool = False, through=None):
    """The level-file path src -> dst over walk edges in logic that need nothing (fewest assumed edges, then
    fewest edges): [(index, from, to, confidence)], None if there is none.  With ``kits`` (Step R1.29) a walk edge
    asking element levels alone (one term of element counters) counts too, and the path is the one asking the
    least kit (the sum of the levels it asks, each element's most), then fewest assumed edges, then fewest edges:
    ``(path, kit)``.  ``through(barrier, from, to)`` (AZ-517) is a crossing's requirement, asked with the edge's
    own for each barrier its ``through`` names."""
    adj = collections.defaultdict(list)
    for i, e in enumerate(doc.get("edge", [])):
        if e.get("kind") == "walk" and e.get("logic", True) and e.get("difficulty", 1) <= 3:
            req = " & ".join(f"({r})" for r in [e.get("requires", "true"), *(
                through(x, e["from"], e["to"]) for x in (e.get("through", ()) if through else ()))])
            needs = [k for term in dnf(req) if (k := _kit_of(term)) is not None]
            for need in needs if kits else [{}] if {} in needs else []:
                adj[e["from"]].append((e["to"], i, e.get("confidence", "assumed"), need))
    none = tuple(0 for _ in ELEMENTS)
    start = (src, none)
    best, prev, heap = {start: (0, 0, 0)}, {start: None}, [(0, 0, 0, src, none)]
    end = None
    while heap:
        nk, na, nn, u, kit = heapq.heappop(heap)
        if (nk, na, nn) > best[(u, kit)]:
            continue
        if u == dst:
            end = (u, kit)
            break
        for v, i, conf, need in adj[u]:
            k2 = tuple(max(lv, need.get(el, 0)) for el, lv in zip(ELEMENTS, kit))
            c = (sum(k2), na + (conf == "assumed"), nn + 1)
            if c < best.get((v, k2), (math.inf, 0, 0)):
                best[(v, k2)], prev[(v, k2)] = c, ((u, kit), i, conf)
                heapq.heappush(heap, (*c, v, k2))
    if end is None:
        return None
    path, at = [], end
    while prev[at]:
        was, i, conf = prev[at]
        path.append((i, was[0], at[0], conf))
        at = was
    return (path[::-1], {el: lv for el, lv in zip(ELEMENTS, end[1]) if lv}) if kits else path[::-1]


def _kit_of(term) -> dict | None:
    """A DNF term's element levels ({element: level}), None if it asks anything else."""
    if any(a[0] not in ELEMENTS or not isinstance(a[1], int) for a in term):
        return None
    return {a[0]: a[1] for a in term}


def _spot_rows(ids, db) -> list[dict]:
    """``plan --spots``' rows (Step R1.29): each location id's level, node and its level-file ``requires``."""
    level_of = {n["id"]: lvl for lvl, doc in db.levels.items() for n in doc.get("node", [])}
    rows = []
    for loc in ids:
        if loc not in db.node_of:
            raise SystemExit(f"{loc}: not a pool location with a node")
        lvl = level_of[db.node_of[loc]]
        req = next((x.get("requires", "true") for x in db.levels[lvl].get("location", ()) if x["id"] == loc), "true")
        rows.append({"id": loc, "level": lvl, "node": db.node_of[loc], "requires": req})
    return rows


def logic_kit(logic, loc: str, kit: dict) -> tuple[dict | None, str | None]:
    """AZ-570: the most of ``kit`` (each element at or under its level) at which rando check takes an L3 string to
    pool location ``loc`` (``Logic.kit_short``, AZ-543: the logic never collects it holding less, going in, or
    leaving with the spot's own item, which the string takes), each element it refuses lowered a level at a time:
    (that kit, None), or (None, the refusal) when it refuses even none of that element."""
    kit = dict(kit)
    while (bad := logic.kit_short(loc, kit)) is not None:
        if not kit.get(bad[0]):
            return None, bad[1]
        kit[bad[0]] -= 1
    return {e: n for e, n in kit.items() if n}, None


def plan(impacts: list[Path], out: Path, top: int, spots=()) -> list[dict]:
    """The targets: ``impacts``' top spots and edges, and ``spots`` (location ids, Step R1.29), which may start
    holding the element levels their way from an arrival asks (:func:`_local_path`'s ``kits``), lowered to what the
    logic collects it holding (:func:`logic_kit`, AZ-570: the way's own kept as ``kit_way``), and set that kit in
    L3 (group ``<level>-k0``, as a tour target's)."""
    from azurkit.tools.randomizer.planner.loader import load_database
    from azurkit.tools.randomizer.planner.solver import Logic
    docs = [_read(p) for p in impacts]
    levels, gens, level_of = _db()
    db = load_database()
    logic = Logic(db) if spots else None
    gated = {x["id"]: x.get("gated_by", []) for g in gens.values() for x in g.get("locations", [])}
    targets, seen = [], set()
    for s, kits in [(s, False) for d in docs for s in d["spots"][:top]] + [(s, True) for s in
                                                                          _spot_rows(spots, db)]:
        lvl, doc = s["level"], levels[s["level"]]
        t = {"key": f"spot-{s['id'].replace('/', '_')}", "kind": "spot", "id": s["id"], "level": lvl,
             "node": s["node"], "goal": s["id"]}
        if t["key"] in seen:
            continue
        seen.add(t["key"])
        kit = _kit(s.get("requires", "true"))
        arr = _arrivals(lvl, levels, gens, level_of)
        ways = {}
        for a in arr:
            there, back = (_local_path(doc, u, v, kits, functools.partial(_through, db))
                           for u, v in ((a, s["node"]), (s["node"], a)))
            if there is not None and back is not None and kit is not None:
                need = {} if not kits else {e: max(there[1].get(e, 0), back[1].get(e, 0)) for e in ELEMENTS}
                ways[a] = (there[0] if kits else there,
                           {e: n for e in ELEMENTS if (n := max(need.get(e, 0), kit.get(e, 0)))})
        if gated.get(s["id"]):
            gates = [f"{g} ({db.generated_objects[g][1]})" for g in gated[s["id"]]]
            t["skip"] = f"its item only its gate gives, not a touch: gated_by {', '.join(gates)}"
        elif kit is None:
            t["skip"] = f"the spot itself asks {s['requires']} (not element levels alone)"
        elif not ways:
            held = "element levels alone" if kits else "nothing held"
            t["skip"] = (f"no arrival of the level reaches it and back with {held} (its way needs a button, a flag, "
                         "an event or an item a vanilla state plus a teleport doesn't give)")
        else:
            a = min(ways, key=lambda a: (sum(ways[a][1].values()) if kits else 0,
                                         sum(c == "assumed" for *_, c in ways[a][0]), len(ways[a][0]), a))
            t.update(start_node=a, start=_zones(doc, a)[0], back=_zones(doc, a), kit=ways[a][1] if kits else kit,
                     hop=_hop(arr, a), path=[f"{u}>{v} #{i} {c}" for i, u, v, c in ways[a][0]])
            if kits:
                t.update(group=f"{lvl}-k0", kit_l3=True)
                held, why = logic_kit(logic, s["id"], t["kit"])
                if held is None:
                    t["skip"] = f"rando check takes a proof of it at no kit (its string leaves holding its item): {why}"
                elif held != t["kit"]:
                    t.update(kit=held, kit_way=t["kit"])
        targets.append(t)
    for e in [e for d in docs for e in d["edges"][:top]]:
        lvl = e["level"]
        t = {"key": f"edge-{lvl}-{e['from']}-{e['to']}", "kind": "edge", "level": lvl, "from": e["from"],
             "to": e["to"], "requires": e["requires"], "rank_index": e["index"]}
        if t["key"] in seen:
            continue
        seen.add(t["key"])
        kit = _kit(e["requires"])
        arr = _arrivals(lvl, levels, gens, level_of)
        if e["kind"] != "walk" or not e["from"]:
            t["skip"] = f"a {e['kind']} edge (an exit or arrival, not a walk)"
        elif kit is None:
            t["skip"] = f"it asks {e['requires']}: world state a vanilla state plus a teleport doesn't give"
        elif not arr:
            t["skip"] = "no exit arrives in the level"
        else:
            t.update(start=_zones(levels[lvl], e["from"])[0], goal=_zones(levels[lvl], e["to"]), kit=kit,
                     hop=_hop(arr, e["from"]))
        targets.append(t)
    out.mkdir(parents=True, exist_ok=True)
    _write(out / "targets.json", {"step": "R1.29" if spots and not impacts else "X.7",
                                  "impact": [p.name for p in impacts], "top": top, "targets": targets})
    return targets


TOUR_HOPS = ("walk", "exit", "cart", "teleport")


def plan_tour(progress: Path, out: Path) -> list[dict]:
    """Step R1.16's targets from ``progress``'s ``certify`` list (the module docstring), into ``out/targets.json``."""
    levels, gens, level_of = _db()
    doc, targets = _read(progress), []
    opened = {}             # (level, {from, to}) -> (barrier, tour index): a barrier the tour removes, either way
    for e in [e for e in doc.get("sample", ()) if e.get("tour") == "1-2-3"] + doc["certify"]:
        if e["kind"] == "barrier":
            opened.setdefault((e["level"], frozenset((e["from"], e["to"]))),
                              (e["goal"], e["index"] if e in doc["certify"] else -1))
    gates = {x["id"]: x["requires"] for d in levels.values() for x in d.get("location", ())
             if x.get("requires", "true") != "true"}          # a location's own gate (a blocker, a keylock door)
    for c in doc["certify"]:
        lvl, kind = c["level"], c["kind"]
        t = {"key": c["key"], "kind": kind, "tour": True, "sphere": c["sphere"], "level": lvl, "from": c["from"],
             "to": c["to"], "id": c["goal"]}
        gate = gates.get(c["goal"]) if kind in ("pickup", "reach") else None
        arr = _arrivals(lvl, levels, gens, level_of) if lvl in levels else {}
        zones = _zones(levels[lvl], c["from"]) if lvl in levels and any(
            n["id"] == c["from"] for n in levels[lvl]["node"]) else []
        crossed = opened.get((lvl, frozenset((c["from"], c["to"]))))
        if kind not in TOUR_HOPS + ("pickup", "reach"):
            t["skip"] = f"a {kind}: real input in xemu (an action), no L3 search"
        elif kind in ("pickup", "reach") and not c["goal"].startswith(f"{lvl}/"):
            t["skip"] = (f"its location {c['goal']} is a creature's drop (characters.xbr), placed where it dies: no "
                         "place in the level file, and a fight first")
        elif kind in TOUR_HOPS and crossed and crossed[1] < c["index"]:
            t["skip"] = (f"it crosses {crossed[0]}, a barrier the tour removed before it: world state a new game "
                         "plus a hop doesn't give")
        elif not any(all(a[0] in ELEMENTS and isinstance(a[1], int) for a in term)   # a term of element levels
                     for term in dnf(c.get("requires") or "true")):                    # alone (a skip's is off)
            t["skip"] = f"it asks {c['requires']}: world state a new game plus a hop doesn't give"
        elif gate and not any(all(a[0] in ELEMENTS and isinstance(a[1], int) and c["kit"].get(a[0], 0) >= a[1]
                                  for a in term) for term in dnf(gate)):
            t["skip"] = f"its location asks {gate}: world state a new game plus a hop doesn't give"
        elif not arr or not zones:
            t["skip"] = "no exit arrives in the level" if not arr else f"{c['from']} anchors no zone"
        else:
            trigger = kind in TOUR_HOPS[1:] and c["goal"].count("/") == 2      # an exit's generated id
            t.update(start=zones[0], kit={e: n for e, n in c["kit"].items() if n}, hop=_hop(arr, c["from"]),
                     goal=c["goal"] if trigger or kind in ("pickup", "reach") else _zones(levels[level_of[c["to"]]],
                                                                                         c["to"]),
                     group=f"{lvl}-k0", kit_l3=True,     # one snapshot a level, the kit set in L3 (Segment.kit)
                     **({"exit": True} if trigger else {}))
        targets.append(t)
    out.mkdir(parents=True, exist_ok=True)
    _write(out / "targets.json", {"step": "R1.16", "progress": str(progress.name), "targets": targets})
    return targets


def _goal(router, t: dict, target, air: int):
    """A leg's goal: an exit's trigger (a tour target's ``exit``, Step R1.16) or a route target (zones, a spot, its
    reach the target's ``touch`` when a search set one, Step R1.29; a pickup's or a counted item's location by its
    item's own touch, :func:`touch_of`)."""
    if t.get("exit") and target == t["goal"]:
        return ExitGoal(router, target, air=air)
    item = touch_of(t) if target == t.get("goal") else None
    return RouteGoal(router, target, air=air, touch=item if item is not None else t.get("touch", 0.75))


_ENGINE: list = []


def _engine():
    """config.xbr's ``critters_engine`` table of the vanilla ISO (read once)."""
    if not _ENGINE:
        from devkit.sim.ports import vanilla_iso
        from devkit.sim.ports import read_file
        from azurkit.tools.characters.ports import XbrDocument
        doc = XbrDocument.from_bytes(read_file(str(vanilla_iso()), "gamedata/config.xbr"))
        _ENGINE.append(doc.keyed_section("critters_engine"))
    return _ENGINE[0]


def location(goal: str) -> dict | None:
    """The generated record of location ``goal`` (``e5/g0/r4263``)."""
    doc = _read(DATA_DIR / "generated" / f"{goal.split('/')[0]}.json")
    return next((x for x in doc["locations"] if x["id"] == goal), None)


def touch_of(t: dict) -> tuple | None:
    """A pickup's, a counted item's or a spot's touch (``l3_goal.item_touch``: R, Z, hz) for its location's vanilla
    item (the certify replays run the vanilla disc); None for another target (AZ-483, :func:`at_location`)."""
    if not at_location(t):
        return None
    loc = location(t["goal"])
    return item_touch(_engine(), loc["template"]) if loc else None


# -- 2 and 4. the sitting --------------------------------------------------------------------------------------------

def hop(sb, xo, dest: str, spot: str, budget: float = 240.0) -> dict:
    """R7 (RAM_RECIPES 5.3, placed): a level request for ``dest`` at ``spot``, then 20 steady player ticks in the
    new level (A on a stall: a dialog)."""
    for va, data in recipes.hop(sb.read_u32, dest, spot):   # azurkit.tools.randomizer.live.recipes: the shared RAM recipes
        sb.write(va, data)
    t0, loaded, n, last = time.monotonic(), False, 0, 0.0
    while time.monotonic() - t0 < budget:
        eip = sb.wait_bp([xo.PLAYER_TICK, xo.LOAD_LEVEL], 2.5)
        if eip is None:
            if time.monotonic() - last > 2.5:
                sb.run()
                sb.press("a", seconds=0.3)
                last = time.monotonic()
            continue
        if eip == xo.LOAD_LEVEL:
            loaded, n = True, 0
            continue
        ent = sb.read_u32(sb.g.regs()["esp"] + 4)
        if loaded and sb.entity_row(ent)["state"] in (0, 3, 6):
            n += 1
            if n >= SETTLE:
                return {"ok": True, "s": round(time.monotonic() - t0, 1)}
    return {"ok": False, "s": round(time.monotonic() - t0, 1)}


def set_kit(sb, kit: dict) -> None:
    """R2 (placed): each element level the kit's, the others 0; every first-pickup popup bit set."""
    for va, data in recipes.element_levels(sb.read_u32, {e: int(kit.get(e, 0)) for e in ELEMENTS}):
        sb.write(va, data)
    sb.write_u32(recipes.chain(sb.read_u32)["inv"] + INV_POPUPS, 0xFFFFFFFF)


def _group(t: dict) -> str:
    """A target's snapshot group: its level and kit, or the loadvm state it starts from (Step R1.8g)."""
    return t.get("group") or f"{t['level']}-{kit_label(t['kit'])}"


def _groups(targets) -> dict[str, dict]:
    out = {}
    for t in targets:
        if "skip" not in t:
            out.setdefault(_group(t), {"level": t["level"], "kit": {} if t.get("kit_l3") else t["kit"],
                                       "hop": t["hop"], "loadvm": t.get("loadvm", START_TAG),
                                       "keys": []})["keys"].append(t["key"])
    return out


def until_movable(sb, g: str, step_s: float = 5.0, most_s: float = 90.0) -> float:
    """Run the guest until the stick moves the player in L3 (an arrival can hold it: e2's intro, e7's lift),
    checked every ``step_s`` s on a throwaway snapshot (deleted); the seconds waited."""
    waited = 0.0
    while True:
        label = f"x7m-{g}-{time.strftime('%H%M%S')}-{int(waited)}"
        try:
            sb.snapshot(label)
        except SystemExit:             # no player tick: a dialog or a cutscene (A clears a dialog, placed)
            sb.run()
            sb.press("a", seconds=0.3)
            time.sleep(step_s)
            waited += step_s
            if waited >= most_s:
                raise
            continue
        path = l3.snapshot_path(label)
        try:
            rows = l3.L3(l3.read_snapshot(path), sb._xbe("dvd.iso")).run([Pad((0.0, 1.0))] * 20)
        finally:
            path.unlink()
        if math.dist(rows[0].pos, rows[-1].pos) > 1.0 or waited >= most_s:
            return waited
        sb.run()
        time.sleep(step_s)
        waited += step_s


def _snap_info(label: str, info: dict) -> dict:
    meta = l3.read_meta(l3.snapshot_path(label))
    return {"label": label, "meta_sha12": l3.meta_sha12(meta),
            **{k: info[k] for k in ("pages", "sha12", "level", "hp", "xemu", "iso_sha12")}}


def sitting_snapshots(d: Path, sb, xo) -> None:
    targets = _read(d / "targets.json")["targets"]
    snaps = _read(d / "snapshots.json") if (d / "snapshots.json").exists() else {}
    for g, grp in sorted(_groups(targets).items()):
        if "tag" in snaps.get(g, {}):          # an adopted snapshot has no state in W: take it again
            continue
        sb.loadvm(grp["loadvm"])
        h = hop(sb, xo, *grp["hop"]) if grp["hop"] else {"ok": True, "s": 0.0}
        if not h["ok"]:
            snaps[g] = {"error": f"the hop {grp['hop']} didn't settle in {h['s']} s"}
            _write(d / "snapshots.json", snaps)
            continue
        set_kit(sb, grp["kit"])
        sb.player()
        waited = until_movable(sb, g)
        tag = f"x7-{g}-{time.strftime('%H%M%S')}"
        sb.savevm(tag)
        label = f"x7-{g}-{time.strftime('%H%M%S')}"
        info = sb.snapshot(label, scene=True)
        snaps[g] = {"tag": tag, "hop_s": h["s"], "kit": grp["kit"], "hop": grp["hop"], "waited_s": waited,
                    "loadvm": grp["loadvm"], **_snap_info(label, info)}
        _write(d / "snapshots.json", snaps)
        print(g, json.dumps(snaps[g]), flush=True)


def adopt(d: Path) -> dict:
    """Snapshots without a sitting (Step R1.16): each group of a kit set in L3 (``<level>-k0`` from a new game) takes
    the store's newest earlier snapshot of that group (a sitting's ``<name>-<level>-k0-<HHMMSS>``), format 3 (real
    reads, high pages) first.  Searches run on it; ``sitting snapshots`` takes the group again for the replays (an
    adopted one has no state in a sandbox), and the replays re-run each string from that one in L3 first."""
    import re
    targets = _read(d / "targets.json")["targets"]
    snaps = _read(d / "snapshots.json") if (d / "snapshots.json").exists() else {}
    for g, grp in sorted(_groups(targets).items()):
        if "label" in snaps.get(g, {}) or grp["kit"] or grp["loadvm"] != START_TAG:
            continue
        found = []
        for path in l3.store().glob(f"*-{g}-*.l3snap"):
            if not re.fullmatch(rf"[a-z0-9]+-{re.escape(g)}-\d{{6}}", path.stem):
                continue
            with open(path, "rb") as f:
                fmt = l3._header(f, path)[0].get("format", 1)
            meta = l3.read_meta(path)
            if meta.get("level", "").rsplit("/", 1)[-1] == grp["level"] and meta.get("hp") and "scene" in meta:
                found.append((fmt, path.stat().st_mtime, path.stem, meta))
        if not found:
            continue
        fmt, _, label, meta = max(found)
        snaps[g] = {"label": label, "adopted": True, "format": fmt, "kit": {}, "loadvm": START_TAG,
                    "meta_sha12": l3.meta_sha12(meta), **{k: meta.get(k) for k in ("level", "hp", "xemu",
                                                                                     "iso_sha12")}}
    _write(d / "snapshots.json", snaps)
    return snaps


def _verify(sim, target: dict, legs: list, router, kit: dict | None = None, tail: int = 0) -> dict:
    """Run a target's legs end to end in ``sim`` (from the snapshot, with ``kit`` set in L3: a skip's rung): the
    pads, the rows, whether each leg's goal is met at its last tick (an item's touch or an exit's fire: at any
    tick), the row each leg first meets it at (``goal_at``) and the row the start settled at (``start_at``: the
    string follows it).  In whole steps an item's or an exit's outcome is the game's own (AZ-483): ``outcome_at``,
    the row L3's inventory first gains the goal's item (past the rows' own writes) or its levelSwitch fires
    (``outcome``: the level and movie; the run ends there), the settle's last row when the placement did it; with
    ``tail``, up to that many neutral ticks after the string (and an exit's timer wait) until it comes
    (``string_end``: the rows before them).  The target's own outcome after the settle (``outcome_own``: its item's
    field, a fire of the exit's own level) meets the last leg's goal even when it came in the tail: at the first
    row from the leg's start in the goal, else the outcome's.  A leg of ``parts`` (a douse, Step R1.29e) meets a
    zone goal when its last row is in it (the douse's walk may end in it, its last part then a tick); a leg's
    ``lead`` ticks (an air kit's recast before its way back, :func:`leg_lead`, which its search didn't run) count
    for no goal row, so a way back that starts in its goal still meets it at its last."""
    sim.reset()
    scene = getattr(sim, "scene", False)
    item = scene and target.get("kind") in ITEMS and str(target.get("goal")).count("/") == 2
    want = (goal_fields(target["goal"]) or set()) if item else set()
    inv = recipes.chain(sim.u32)["inv"] if want else 0
    before = sim.read(inv, recipes.INV_SAVED) if want else b""
    fires = sim.fires if scene and target.get("exit") else None      # L3's levelSwitch fires (Step X.52b)
    if fires is not None:
        fires.clear()
    first = legs[0]
    _, row, cam, setup, setup_rows = start_of(sim, Segment(first["snapshot"], teleport=first["teleport"],
                                                            settle=SETTLE, kit=kit))
    rows_all, pads_all = list(setup_rows), list(setup)
    settled = want and gained(sim, inv, want, before, setup_rows) or bool(fires)
    out = {"outcome_at": max(0, len(setup_rows) - 1) if settled else None,
           "outcome": list(fires[0][1:]) if fires else None}

    def step(p) -> bool:
        """One tick; False once the outcome came (an exit's fire ends the run: the load after it isn't L3's)."""
        prev = sim.read(inv, recipes.INV_SAVED) if want and out["outcome_at"] is None else None
        try:
            r = sim.step(p)
        except l3.L3Error:
            if not fires:
                raise
            r = None
        if fires and out["outcome_at"] is None:
            out.update(outcome_at=len(rows_all), outcome=list(fires[0][1:]))
        elif prev is not None and gained(sim, inv, want, prev, [r]):
            out["outcome_at"] = len(rows_all)
        if r is not None:
            rows_all.append(r)
            pads_all.append(p)
        return not fires
    ok, at, goal, live = [], [], None, not fires
    for leg in legs:
        goal = _goal(router, target, leg["target"], (kit or target["kit"]).get("air", 0))
        string, cam = leg_pads(leg, cam)
        n0 = len(rows_all)
        for p in string:
            if not live or not (live := step(p)):
                break
        rows = rows_all[n0:]
        hit = next((k for k, r in enumerate(rows) if k >= leg.get("lead", 0) and goal.reached(r)), None)
        doused = bool(leg.get("parts")) and bool(rows)    # its douse's walk may end in its goal (Step R1.29e)
        ok.append(hit is not None if getattr(goal, "touch", None) is not None or fires else
                  goal.reached(rows[-1]) if doused else hit == len(rows) - 1)
        at.append(None if hit is None else n0 + hit)   # an item's touch takes it at once; a fire ends the run
    end, start_at = len(rows_all), max(0, len(setup_rows) - 1)
    for _ in range(tail + getattr(goal, "wait", 0) if tail and (want or fires is not None) else 0):
        if out["outcome_at"] is not None or not live or not (live := step(Pad())):
            break
    own = out["outcome_at"] is not None and out["outcome_at"] > start_at and (     # the item's own field, or a
        fires is None or out["outcome"][0] == getattr(goal, "dest", None))           # fire of the exit's own level
    if own and ok and not ok[-1]:       # the game's outcome came past the string's check (its tail): the last leg
        k = next((k for k in range(n0, len(rows_all)) if goal.reached(rows_all[k])), None)   # met its goal there
        ok[-1], at[-1] = True, k if k is not None else min(out["outcome_at"], len(rows_all) - 1)
    return {"pads": pads_all, "rows": rows_all, "ok": ok, "goal_at": at, "start_at": start_at,
            "string_end": end, "outcome_own": own, **out}


def _verify_again(sim, target: dict, legs: list, router, kit: dict | None = None) -> tuple[dict | None, dict]:
    """:func:`_verify`, run once more when L3 stops on the way (AZ-640: a warm render past its wall-clock cap on a
    loaded host; :func:`_verify` resets ``sim``): its result and ``{}``, or None and what a second stop records
    (``verified`` False, ``inconclusive``, ``verify_fault``: its site, ``why``), so a real loop (Step R1.29b's render
    at 0xF4EDF) stays visible and the caller keeps the legs."""
    for again in (False, True):
        try:
            return _verify(sim, target, legs, router, kit), {}
        except l3.L3Error as ex:
            if again:
                return None, {"verified": False, "inconclusive": True, "verify_fault": ex.site,
                              "why": f"the end-to-end verify stopped twice: {ex}"}


def leg_pads(leg: dict, cam: float) -> tuple[list, float]:
    """A leg's pads from a camera at ``cam`` and the camera after them: its ``segs`` (``l3_search.Seg`` lists),
    or its ``parts`` in turn (Step R1.29e: a doused leg's way to the barrier, the douse's own pads, ``l3.pads``
    segments, and the way on from it)."""
    out = []
    for part in leg.get("parts") or [{"segs": leg["segs"]}]:
        if "pads" in part:
            more = l3.pads(part["pads"])
            cam = more[-1].yaw if more and more[-1].yaw is not None else cam
        else:
            more, cam = expand([Seg(*x) for x in part["segs"]], cam)
        out += more
    return out, cam


def _legs(label: str, start: dict, goals: list, legs: list) -> list[dict]:
    """The legs :func:`_verify` runs: each searched leg from the start, by its segments or its parts."""
    return [{"snapshot": label, "teleport": start["teleport"], "target": g_, "lead": leg.get("lead", 0),
             **({"parts": leg["parts"]} if leg.get("parts") else {"segs": leg["segs"]})} for g_, leg in zip(goals, legs)]


def gained(sim, inv: int, want: set, before: bytes, rows) -> bool:
    """Whether L3's inventory at ``inv`` holds more of a ``want`` field than ``before`` with ``rows``' own writes
    (the kit's levels) laid over it: a pickup adds, the cast's fuel only spends."""
    was, now = _after_writes(before, inv, rows), recipes.inventory(sim.read(inv, recipes.INV_SAVED))
    return any(now[f] > was[f] for f in want)


def _settled_zone(router, r) -> str | None:
    """The zone a row stands or swims in (AZ-590, D719): only a settled body (``l3_search.settled``: standing,
    swimming, or at rest on near-flat ice, AZ-737) is read, and only in the zone of the floor its feet are on or the
    water holding it (``Router.zone_at`` with no fallback), never of a floor under a rig's tooth or a ledge's top it
    stands on; a body in the air, climbing or in any other state is in no zone."""
    if not settled(r):
        return None
    return r.zone or router.zone_at((r.pos[0], r.pos[1], r.pos[2] - 1.0), prefer_water=r.state == 6, fallback=False)


def _outcome(rows, router) -> dict:
    """Counts of a run: the states in order, the zones a settled body visited in order (:func:`_settled_zone`), the
    least HP."""
    zones, states = [], []
    for r in rows:
        z = _settled_zone(router, r)
        if z and (not zones or zones[-1] != z):
            zones.append(z)
        if not states or states[-1] != r.state:
            states.append(r.state)
    return {"zones": zones, "states": [hex(s) for s in states], "hp_min": min(r.hp for r in rows)}


def inventory_fields(inv0: bytes, inv1: bytes, inv: int, rows) -> list[str]:
    """The inventory fields (``recipes.inventory``'s names; the day clock and popup bits left out) xemu changed
    replaying ``rows``, from its saved bytes at ``inv`` before (``inv0``) and after (``inv1``) the replay, past the
    replay's own writes (each row's after the pad: the kit's element levels, R2): a pickup, the cast's fuel."""
    was, now = _after_writes(inv0, inv, rows), recipes.inventory(inv1)
    return sorted(f for f in now if now[f] != was[f])


def _after_writes(inv0: bytes, inv: int, rows) -> dict[str, int]:
    """The inventory (``recipes.inventory``) the saved bytes ``inv0`` at ``inv`` hold after ``rows``' own writes."""
    b = bytearray(inv0)
    for r in rows:
        for va, data in r.writes[1:]:
            lo, hi = max(va, inv), min(va + len(data), inv + len(b))
            if lo < hi:
                b[lo - inv:hi - inv] = data[lo - va:hi - va]
    return recipes.inventory(bytes(b))


def goal_fields(goal: str) -> set[str] | None:
    """The inventory fields a pickup at location ``goal`` (a generated id, ``e5/g0/r4263``) changes: its vanilla
    item's (``recipes.item_fields``; the skips are vanilla's, replayed on the vanilla disc)."""
    doc = _read(DATA_DIR / "generated" / f"{goal.split('/')[0]}.json")
    item = next((x["item"] for x in doc["locations"] if x["id"] == goal), None)
    return recipes.item_fields(item) if item else None


def l3_inventory(sim, kit: dict) -> dict[str, int]:
    """The inventory (``recipes.inventory``) at ``sim``'s snapshot with ``kit``'s element levels (R2 writes each
    element's, the others 0): what a run from it holds before any pickup (``sim`` is reset)."""
    sim.reset()
    inv = recipes.chain(sim.u32)["inv"]
    return recipes.inventory(sim.read(inv, recipes.INV_SAVED)) | {f"level.{e}": int(kit.get(e, 0)) for e in ELEMENTS}


def l3_taken(sim, goal: str, was: dict[str, int]) -> list[str]:
    """The goal's own item's inventory fields (:func:`goal_fields`) ``sim`` changed from ``was`` by the end of the
    run it just made (Step R1.29): in whole steps L3 runs the pickup's touch as the game does, so this is what xemu
    takes too, where the goal's 0.75 m touch alone isn't (AZ-483)."""
    now = recipes.inventory(sim.read(recipes.chain(sim.u32)["inv"], recipes.INV_SAVED))
    return sorted(f for f in goal_fields(goal) or () if now[f] != was[f])


def judge_spot(t: dict, equal: bool, fields, start_m: float | None, placed: bool) -> dict:
    """A spot's replay judged by its outcome (Step R1.29, AZ-474's rule for a location): proven when the body
    centre, state and HP are L3's on every tick there and back (``equal``), xemu took the goal's own item (its
    vanilla item's inventory field, :func:`goal_fields`, among ``fields``) and the start isn't ``near``: placed
    (R6) within :data:`NEAR_M` of where the string first stands at the spot (``start_m``; the hop's own arrival
    is never near).  The start's straight line goes in as a band (:func:`_band`)."""
    want = goal_fields(t["goal"]) or set()
    taken = sorted(want & set(fields))
    band = None if start_m is None else _band(start_m)
    near = bool(placed and start_m is not None and start_m <= NEAR_M)
    why = ("the body, state or HP differ from L3's, or the replay stopped early" if not equal else
           f"the goal's item not taken: xemu changed {sorted(fields) or 'nothing'}" if not taken else
           f"near: the placed start stands {band} from the spot" if near else None)
    return {"judged_by": "item", "taken": taken, "placed": placed, "start_goal_band": band, "near": near,
            "proven": why is None, "why": why}


def pickup_at(t: dict, cmp: dict, fields) -> tuple[int | None, str]:
    """(the tick, "") when a skip to a pickup (a location id) is proven by xemu taking the pickup, else (None, why
    not) (Step R1.8g; default taken under D115): the replay is equal on every tick until xemu's inventory changes
    and L3's, which doesn't model the pickup, doesn't.  So the first tick that differs differs in the inventory hash
    alone, xemu took the goal's item (``fields``, :func:`inventory_fields`, holds one of :func:`goal_fields`: not
    the kit's levels or the cast's fuel; AZ-389), and the body centre is equal on every tick before that one (and on
    tick 0, whatever it is)."""
    fd, err = cmp.get("first_diff"), cmp.get("first_err_tick")
    if t.get("kind") != "skip" or str(t.get("goal")).count("/") != 2:
        return None, "not a skip to a pickup"
    if not fd or fd[1] != ["inv_sha12"]:
        return None, f"the first difference is {fd}, not the inventory hash alone"
    want = goal_fields(t["goal"]) or set()
    if not want & set(fields):
        return None, f"xemu's inventory changed {sorted(fields) or 'nothing'}, not the goal's {sorted(want)}"
    if err is not None and (err == 0 or err < fd[0]):
        return None, f"the body differs from tick {err} (the inventory from tick {fd[0]})"
    return fd[0], ""


def _fields_at(offsets) -> set[str]:
    """The inventory fields whose words hold the bytes at ``offsets`` (an older record's raw offsets)."""
    z = bytes(recipes.INV_SAVED)
    base = recipes.inventory(z)
    return {f for o in offsets if 0 <= o < len(z)
            for f, v in recipes.inventory(z[:o] + b"\1" + z[o + 1:]).items() if v != base[f]}


def stale_pickup(t: dict, row: dict) -> str | None:
    """Why a replay's recorded pickup proof (``pickup_at``) doesn't hold under :func:`pickup_at`'s rule (AZ-389),
    from the record alone; None when it holds or isn't one.  A player-tick replay recorded before AZ-389's fix
    compared inventory hashes holding the day clock, which L3 doesn't advance there, so its first difference was the
    clock's and its pickup tick is unknown: only a new replay can judge it (``sitting DIR W replays`` does).  An
    older record holds raw offsets measured before the replay's own writes, which set every element level, so its
    levels can't tell a pickup from the kit: only its other fields count."""
    if row.get("pickup_at") is None:
        return None
    if row.get("l3_mode") != "scene" and row.get("inv_sha12_from") != recipes.INV_CLOCK:
        return "a player-tick replay judged with the day clock in the inventory hash: replay it"
    fields = row.get("inventory_fields")
    if fields is None:
        fields = _fields_at(row.get("inventory_changed_offsets", ())) - {f"level.{e}" for e in recipes.ELEMENTS}
    return pickup_at(t, row, fields)[1] or None


def recheck_pickups(d: Path) -> dict:
    """Every target in ``d`` whose recorded replay proves a pickup, judged again under the fixed rule
    (:func:`stale_pickup`; AZ-389), reading the folder only: per target whether its proof holds and why not, with
    counts of the folder's results, replays and pickup proofs."""
    targets = {t["key"]: t for t in _read(d / "targets.json")["targets"]}
    results = _read(d / "results.json") if (d / "results.json").exists() else {}
    reps = _read(d / "replays.json") if (d / "replays.json").exists() else {}
    rows = {key: {"mode": row.get("l3_mode"), "pickup_at": row["pickup_at"], "why": stale_pickup(targets[key], row)}
            for key, row in sorted(reps.items()) if row.get("pickup_at") is not None}
    for r in rows.values():
        r["holds"] = r["why"] is None
    return {"results": len(results), "verified": sum(bool(r.get("verified")) for r in results.values()),
            "replays": len(reps), "proven": sum(bool(r.get("proven")) for r in reps.values()),
            "pickup_proofs": len(rows), "no_longer_hold": sorted(k for k, r in rows.items() if not r["holds"]),
            "pickups": rows}


def _string_sha12(res: dict, priv: dict) -> str:
    """The sha12 a replay of a search result's string gets (``string_sha12`` after the teleport's place struct)."""
    tp = priv["start"]["teleport"]
    place = place_bytes(tp[0], tp[1], priv["start"]["cell"]) if tp else b""
    return hashlib.sha256(place + json.dumps(res["segments"], sort_keys=True).encode()).hexdigest()[:12]


RULE = "az483"       # a tour target's replay judged by its outcome (:func:`judge`, AZ-474) on the game's own pickup and
                     # trigger tests (AZ-483); one judged before is replayed again
ITEM_RULE = "az699"  # an item's (:data:`ITEMS`), with a take on the way read as another item's (AZ-699)
TAIL = 150           # neutral ticks a replay runs on past its string, at most, for an exit's load or a pickup's item
TAIL_WAIT_S = 60.0   # a tail's wait through a cutscene or a load with no tick of the player's before it gives up
NEAR_M = 1.0         # a placed (R6) start this near where the string's outcome came proves no hop (AZ-474)
BANDS = ((1.0, "<=1 m"), (3.0, "1-3 m"), (10.0, "3-10 m"))
ITEMS = ("pickup", "reach")   # a tour target at a location (a pickup, a counted item's reach): proven by its item


def at_location(t: dict) -> bool:
    """Whether a target stands at a location (a generated id): a tour target's pickup or counted item's reach
    (:data:`ITEMS`) or a ``plan --spots`` spot (Step R1.29b), whose item spawns only in its own cell and is taken by
    its own touch (:func:`item_cell`, :func:`touch_of`)."""
    return (t.get("kind") in ITEMS or t.get("kind") == "spot") and str(t.get("goal")).count("/") == 2


def exit_loads(goal: str) -> set[str]:
    """The level paths whose load shows an exit (a generated id, ``d1/g0/r2271``) fired: its generated ``dest`` and,
    when it has one, its ``movie`` (a fired switch's movie plays first, ``load_level_from_path`` taking it as the
    path [observed: r2271 loaded ``bink:death.bik`` first in R1.16c's chain and R1.16d's replays]; cut at the 0x50 bytes
    ``level_path`` reads)."""
    doc = _read(DATA_DIR / "generated" / f"{goal.split('/')[0]}.json")
    x = next((x for x in doc.get("exits", ()) if x["id"] == goal), None)
    return set() if x is None else {x["dest"], *((x["movie"][:0x50],) if x.get("movie") else ())}


def tail(sb, xo, ent: int, until, ticks: int = TAIL, stall_s: float = 4.0, wait_s: float = TAIL_WAIT_S) -> dict:
    """A replay's tail (AZ-474), from where ``replay`` with ``stops`` halted (the player's update entry past its
    string's last tick, or a stall: a movie or a fade with no player update): the neutral pad at each of ``ent``'s
    updates until ``until()`` holds there (the outcome: halted at that entry), at most ``ticks``; a level load
    (``load_level_from_path``: an exit fired) ends it there, halted at the load, instead of running on; no new tick
    of ``ent``'s for ``wait_s`` of wall time (a cutscene that never ends, a dialog, another entity's updates alone)
    ends it where it stands.  ``{"at": "until" | "ticks" | "load" | "stall", "k": the neutral ticks written,
    "level": the path a load names}``; no breakpoints left."""
    g = sb.halt()
    vas = [l3.PLAYER_UPDATE, xo.LOAD_LEVEL]
    out, last, since = {"at": None, "k": 0}, None, time.monotonic()
    xo.arm(g, vas)
    try:
        r = g.regs()
        while True:
            if r["eip"] == xo.LOAD_LEVEL:
                out.update(at="load", level=xo.level_path(g))
                return out
            if r["eip"] == l3.PLAYER_UPDATE and r["ecx"] == ent:
                clock = struct.unpack("<d", g.read(ent + 0x18, 8))[0]
                if clock != last:                       # a new tick (a repeated report of one entry folds)
                    last, since = clock, time.monotonic()
                    if until():
                        out["at"] = "until"
                        return out
                    if out["k"] >= ticks:
                        out["at"] = "ticks"
                        return out
                    sb.write_pad(Pad())
                    out["k"] += 1
            xo.resume(g, vas)
            sb._halted = False
            while not sb._wait(stall_s):
                if time.monotonic() - since >= wait_s:
                    out["at"] = "stall"
                    return out
                g.cont()                                # the breakpoints stay armed through the wait
                sb._halted = False
            if time.monotonic() - since >= wait_s:      # stops, but none a tick of the player's
                out["at"] = "stall"
                return out
            r = g.regs()
    finally:
        g.cmd("?")


def _band(m: float) -> str:
    return next((b for lim, b in BANDS if m <= lim), ">10 m")


def judge(t: dict, rows: list, got: list[dict], *, goal_at: int | None, start_at: int, stop: dict,
          tail_: dict | None, fields, placed: bool, outcome_at: int | None = None) -> dict:
    """A tour target's replay judged by its outcome (AZ-474; defaults taken under D115).  ``rows``: L3's (the
    settle, then the string), ``got``: xemu's (``replay`` with ``stops``, which ``stop`` describes), ``tail_``:
    :func:`tail`'s (None: none ran), ``fields``: the inventory fields xemu changed past the replay's own writes
    (:func:`inventory_fields`), ``goal_at``: the row the string first stands in its goal at, ``start_at``: the
    row its start settled at, ``placed``: the start is a teleport (R6), ``outcome_at``: the row L3's own whole
    steps took the item at (:func:`_verify`; None in player ticks, which never take one).

    - an exit (a cart, a disc teleport): xemu loads its destination or its movie (:func:`exit_loads`) within the
      string or its tail, and the body centre, state and HP are L3's on every tick through the goal's (the
      trigger's own pull and the load come after it; a load or a stall inside the string, the game's field wider
      than the goal's: every tick before it, none of them the settle's);
    - a pickup or a counted item's reach (:data:`ITEMS`): xemu takes the goal's own item (its vanilla item's
      inventory field, :func:`goal_fields`; the disc is vanilla) within the string or its tail, and the body is
      L3's on every tick through the goal's, or before the tick the item was taken when that comes sooner: in
      player ticks where xemu's inventory first differs from L3's (L3 doesn't model it), in whole steps where L3's
      own inventory took it (xemu's hash then equals L3's, AZ-486); a take past the settle and more than a tick
      before the goal's is another item on the way (an obsidian elsewhere, AZ-699), so the body must match
      through the goal's and xemu's inventory change again from a tick before it (or in a tail that started
      with the goal's fields unchanged);
    - anything else (a walk): every tick's body centre, state and HP equal and the replay ran to the string's end,
      with no load or stall.
    A start placed within :data:`NEAR_M` of where the string first stands in its goal, or of where xemu's outcome
    came when that is sooner (a load inside the string; one in the settle: 0 m), is ``near``: the placement, not
    the string, crossed the hop, so it stays out of ``proven`` unless the target is at a location (standing on it
    is the claim; the item taken is the proof).  An outcome at or before the settle's last row is ``settle``: the
    placement took it, which proves nothing, not even near (AZ-486).  The start's straight line to that point goes
    in as a band."""
    exit_ = bool(t.get("exit"))
    rule = "load" if exit_ else "item" if t["kind"] in ITEMS else "body"
    split = next((k for k, (a, b) in enumerate(zip(rows, got))
                  if tuple(a.pos) != tuple(b["pos"]) or a.state != b["state"] or a.hp != b["hp"]), None)
    out: dict = {"judged_by": rule, "split_at": split, "stop": {k: v for k, v in stop.items() if k != "level"},
                 "tail": {k: v for k, v in tail_.items() if k != "level"} if tail_ else None}
    loaded = stop.get("level") if stop.get("at") == "load" else (tail_ or {}).get("level") \
        if (tail_ or {}).get("at") == "load" else None
    to = goal_at                                # the last tick the body must match through
    if rule == "load":
        want = exit_loads(t["goal"])
        seen = loaded in want
        if stop.get("at") in ("load", "stall"):  # the trigger took over inside the string
            to = len(got) - 1
        out["loaded"] = loaded
        what = f"no load of {' or '.join(sorted(want))}" + (f" (loaded {loaded})" if loaded else "")
    elif rule == "item":
        want = goal_fields(t["goal"]) or {f for f in fields if f not in GEMS}
        seen = bool(want & set(fields))
        inv_at = next((k for k, (a, b) in enumerate(zip(rows, got)) if a.obs is not None and b.get("obs")
                       is not None and a.obs.inv_sha12 != b["obs"].inv_sha12), None)
        took = outcome_at if outcome_at is not None and (inv_at is None or inv_at > outcome_at) else inv_at
        what = f"the goal's item not taken: xemu changed {sorted(fields) or 'nothing'}"
        if took is not None and goal_at is not None and start_at < took < goal_at - 1:
            # taken on the way, not in the goal's touch: another item (AZ-699), so the goal's own take comes later:
            # an inventory change from a tick before the touch on, or a tail that ran ticks before its take
            inv = [g["obs"].inv_sha12 if g.get("obs") is not None else None for g in got]
            later = any(None not in (a, b) and a != b for a, b in zip(inv[goal_at - 2:], inv[goal_at - 1:]))
            if not (later or (tail_ or {}).get("at") == "until" and tail_.get("k")):
                seen, what = False, (f"the goal's item not taken: xemu's inventory changed on the way (tick {took}) "
                                     f"and not from tick {goal_at - 1}")
            took = None
        to = goal_at if took is None or goal_at is None else min(goal_at, took - 1)
        out.update(taken=sorted(want & set(fields)), inventory_at=inv_at, taken_at=took)
    m = None if to is None else 0.0 if to <= start_at else math.dist(rows[start_at].pos, rows[to].pos)
    out.update(start_goal_band=None if m is None else _band(m), placed=placed,
               near=bool(placed and m is not None and m <= NEAR_M))
    if rule == "body":
        ok = stop.get("at") == "entry" and len(got) == len(rows) and split is None
        why = None if ok else (f"the replay stopped ({stop.get('at')}) at tick {len(got)} of {len(rows)}"
                               if len(got) != len(rows) or stop.get("at") != "entry" else
                               f"the body, state or HP differ from tick {split}")
    else:                                       # the outcome came after the settle (AZ-486)
        settled = (out.get("taken_at") is None or out["taken_at"] > start_at) if rule == "item" else \
            not (stop.get("at") in ("load", "stall") and len(got) - 1 < start_at)    # the load came after it
        body = to is not None and len(got) > to and (split is None or split > to)
        ok = seen and body and settled
        out["settle"] = seen and not settled
        if out["settle"]:
            out["near"] = False
        why = None if ok else what if not seen else (
            f"the placement took it in its settle (tick {out['taken_at']}): no hop" if not settled and rule == "item"
            else f"the load came at tick {len(got)}, in the start's settle" if not settled else
            f"the body, state or HP differ from tick {split}, before the goal's (tick {to})" if to is not None
            and len(got) > to else f"the replay stopped ({stop.get('at')}) at tick {len(got)}, before the goal's")
        out["outcome_seen"] = seen
    if ok and out["near"] and rule != "item":
        ok, why = False, f"near: the placed start stands {out['start_goal_band']} from the goal"
    return {**out, "proven": ok, "why": why}


def rule_of(t: dict) -> str:
    """The rule a tour target's replay is judged by now: an item's :data:`ITEM_RULE`, else :data:`RULE`."""
    return ITEM_RULE if t.get("kind") in ITEMS and not t.get("exit") else RULE


def stale(t: dict, row: dict) -> str | None:
    """Why a recorded replay is replayed again: a pickup proof the fixed rule doesn't keep (AZ-389), or a tour
    target's judged before its outcome counted (AZ-474) or, for an item or an exit, before AZ-483's goals, and for
    an item before AZ-699's take (a walk's rule, every tick equal, is AZ-474's still)."""
    outcome = t.get("exit") or t.get("kind") in ITEMS
    if t.get("tour") and row.get("rule") != rule_of(t) and (outcome or row.get("rule") != "az474"):
        return "judged before the current outcome rule (AZ-474, AZ-483, AZ-699)"
    return stale_pickup(t, row)


POPUP_STALL_S = 4.0   # no player update this long during a spot's replay: a popup (a first gem), cleared with A
POPUPS = 6


def _quiet(g) -> None:
    """Drop the stop replies a stall's interrupt left on the gdbstub connection (a later 'g' would read one)."""
    g.s.settimeout(0.3)
    try:
        while True:
            g._recv()
    except TimeoutError:
        pass
    finally:
        g.s.settimeout(10.0)


def replay_clearing(sb, xo, pads: list, rows: list, meta: dict) -> tuple[list[dict], dict]:
    """``Sandbox.replay`` from the halted start, a popup on the way cleared (Step R1.29, as ``xemu_chain``'s replay):
    a stall of :data:`POPUP_STALL_S` gets A until the player's update entry comes back at the same tick (the event
    clock checked: no tick lost), then the rest replays from there; (xemu's rows, how it ended, with ``popups``)."""
    got, m, popups = [], meta, 0
    while True:
        stops: dict = {}
        part = sb.replay(pads[len(got):], rows[len(got):], m, timeout=POPUP_STALL_S, stops=stops)
        got += [{**r, "k": r["k"] + len(got)} for r in part]
        if stops.get("at") != "stall" or len(got) >= len(rows) or popups >= POPUPS:
            return got, {**stops, "k": len(got), "popups": popups}
        popups += 1
        g, ent = sb.halt(), meta["entity"]
        _quiet(g)
        xo.arm(g, [l3.PLAYER_UPDATE])
        try:
            for _ in range(12):
                _quiet(g)
                xo.resume(g, [l3.PLAYER_UPDATE])
                sb._halted = False
                if sb._wait(POPUP_STALL_S) and g.regs()["ecx"] == ent:
                    break
                g.cont()                            # the popup: A, the breakpoint armed
                sb._halted = False
                sb.hold("a")
                time.sleep(0.3)
                sb.release_btn("a")
            else:
                return got, {"at": "stall", "k": len(got), "popups": popups}
        finally:
            g.cmd("?")
        clock = struct.unpack("<d", g.read(ent + 0x18, 8))[0]
        if round((clock - meta["clock"]) * 30) != len(got):
            return got, {"at": "lost", "k": len(got), "popups": popups}
        m = {**meta, "at": "update", "clock": clock, "start_sha12": xo.start_hash(g.read, ent)}


def sitting_replays(d: Path, sb, xo, only=(), chain: bool = True) -> None:
    targets = {t["key"]: t for t in _read(d / "targets.json")["targets"]}
    snaps = _read(d / "snapshots.json")
    results = _read(d / "results.json")
    reps = _read(d / "replays.json") if (d / "replays.json").exists() else {}
    xbe = sb._xbe("dvd.iso")
    for key, res in sorted(results.items()):
        if not res.get("verified") or (only and key not in only):
            continue
        priv = _read_priv(d, key)
        t = targets[key]
        if key in reps and reps[key].get("sha12") in (None, _string_sha12(res, priv)) and not stale(t, reps[key]):
            continue                            # replayed already (a new search's string, a pickup proof the fixed
                                                # rule doesn't keep, AZ-389, or a tour target's judged before its
                                                # outcome counted, AZ-474, is replayed again)
        g = _group(t)
        kit = res.get("kit")
        router = _router(t["level"])
        sb.loadvm(snaps[g]["tag"])
        label = f"x7r-{key[:40]}-{time.strftime('%H%M%S')}"
        info = sb.snapshot(label, scene=True)
        snap = l3.read_snapshot(l3.snapshot_path(label))
        legs = _legs(label, priv["start"], priv["targets"], res["legs"])
        v, mode = None, "scene"
        try:                                    # whole steps run the item's own pickup and a tail up to it (AZ-483)
            v = _verify(l3.L3(snap, xbe, scene=True), t, legs, router, kit, tail=TAIL if t.get("tour") else 0)
        except l3.L3Error:
            pass
        if v is None or not all(v["ok"]):       # whole steps stop or miss: the player update alone
            v, mode = _verify(l3.L3(snap, xbe), t, legs, router, kit), "tick"
        row = {"label": label, "meta_sha12": l3.meta_sha12(snap.meta), "pages_sha12": info["sha12"],
               "l3_reaches": v["ok"], "l3_mode": mode, "hp_min": min(r.hp for r in v["rows"]),
               "most_flaps": max(flaps_of(r) for r in v["rows"]), **({"rule": rule_of(t)} if t.get("tour") else {})}
        if all(v["ok"]):
            inv = recipes.chain(sb.read_u32)["inv"]
            inv0 = sb.read(inv, recipes.INV_SAVED)
            stop: dict = {}                     # a level load ends the replay there, a stall where it stood (AZ-474)
            if t["kind"] == "spot":             # a gem's first popup on the way is cleared (Step R1.29)
                got, stop = replay_clearing(sb, xo, v["pads"], v["rows"], snap.meta)
            else:
                got = sb.replay(v["pads"], v["rows"], snap.meta, timeout=10.0, stops=stop)
            done = v["rows"][:len(got)]
            tail_ = None
            if t.get("tour") and (stop.get("at") == "entry" and (t.get("exit") or t["kind"] in ITEMS)
                                  or stop.get("at") == "stall" and t.get("exit")):   # a movie or a fade: its load
                was = _after_writes(inv0, inv, done)
                want = goal_fields(t["goal"]) if t["kind"] in ITEMS else None
                want = want or {f for f in was if f not in GEMS}

                def taken() -> bool:            # an exit's outcome is the load alone (the tail stops there)
                    now = recipes.inventory(sb.read(inv, recipes.INV_SAVED))
                    return not t.get("exit") and any(now[f] != was[f] for f in want)
                tail_ = tail(sb, xo, snap.meta["entity"], taken)
            inv1 = sb.read(inv, recipes.INV_SAVED)
            cmp = xo.l3_compare(v["rows"], got)
            corpus.record(snap.meta, mode == "scene", v["pads"][:len(got)], done, got,    # the conformance corpus
                          disc=sb.disc_source())
            tp = priv["start"]["teleport"]
            place = place_bytes(tp[0], tp[1], priv["start"]["cell"]) if tp else b""
            fields = inventory_fields(inv0, inv1, inv, done)
            end = v["string_end"]               # the string's own sha12 (the replay also runs L3's tail)
            row.update(cmp, sha12=string_sha12(v["pads"][:end], place, rows=v["rows"][:end]),
                       inventory_changed=bool(fields), inventory_fields=fields, inv_sha12_from=recipes.INV_CLOCK,
                       proven=bool(cmp["ticks"] == cmp["l3_ticks"] and cmp["max_err_m"] == 0.0
                                   and not cmp["states_differ"] and not cmp["hp_differ"]),
                       outcome=_outcome(v["rows"], router))
            if t.get("tour"):                   # judged by its outcome (AZ-474)
                row.update(judge(t, v["rows"], got, goal_at=v["goal_at"][0], start_at=v["start_at"], stop=stop,
                                 tail_=tail_, fields=fields, placed=tp is not None, outcome_at=v.get("outcome_at")))
            elif t["kind"] == "spot":           # by its item taken, from a start not on it (Step R1.29)
                g0, s0 = v["goal_at"][0], v["start_at"]
                row.update(judge_spot(t, row["proven"], fields, None if g0 is None else
                                      math.dist(v["rows"][s0].pos, v["rows"][g0].pos), tp is not None), stop=stop)
            elif not row["proven"] and (at := pickup_at(t, cmp, fields)[0]) is not None:
                row.update(proven=True, pickup_at=at)      # the string reached the pickup where xemu took it
            row.pop("err_at", None)
            row["path_m"] = round(row["path_m"], 1)
            at_entry = stop.get("at") == "entry" and (tail_ is None or tail_["at"] in ("until", "ticks"))
            if row["proven"] and chain and at_entry:   # D172: the next segment starts exactly where this one's
                parent = {"snapshot": label, "meta_sha12": row["meta_sha12"], "string_sha12": row["sha12"],
                          **({"drained": tail_["k"]} if tail_ else {})}    # replay (and its tail) halted
                nxt = sb.snapshot(f"{label}-end", here=True, parent=parent)
                row["next"] = _snap_info(f"{label}-end", nxt)
        reps[key] = row
        _write(d / "replays.json", reps)
        print(key, json.dumps({k: v for k, v in row.items() if k not in ("label", "outcome", "next")}), flush=True)


# -- 3. search -------------------------------------------------------------------------------------------------------

_ROUTERS: dict[tuple, object] = {}


def _teleport(level: str, r6: dict) -> tuple | None:
    """A record's R6 teleport (feet, yaw, cell) from the reach model its sample was taken on: the first of the
    level's kept models (the first built, then those keyed by a zoning) whose sample gives the record's place.
    Step X.7's records hashed a -0.0 yaw with its sign, which ``place_bytes`` reads as 0.0 (since Step X.9), so
    either form names the place."""
    for path in sorted((private() / "reach").glob(f"{level}[.@]*pkl")):
        try:
            p = load_router(str(path), r6["prof"]).pt(r6["sample"])
        except IndexError:
            continue
        forms = (place_bytes(p, r6["yaw"], r6["cell"]),
                 recipes.place_struct(p, quat=recipes.yaw_quat(r6["yaw"]), cell=r6["cell"]))
        if r6["place_sha12"] in {hashlib.sha256(b).hexdigest()[:12] for b in forms}:
            return p, r6["yaw"], r6["cell"]
    return None


def leg_guide(make, row):
    """(profile, goal, spec) a leg searches with (Step X.53, AZ-593): ``make("logic")``'s (a goal and its factory
    spec), else, when the logic's route graph has no way from the leg's start ``row`` and the light trick graph at
    the leg's air does, ``make("trick")``'s (its sweep, one-sided recheck, hops and lifts, doubts costed; it was
    the phys profile's, the envelope alone).  A goal with no vertex keeps the logic's (its direct line)."""
    goal, spec = make("logic")
    if not goal.finite_at(row):
        alt = make("trick")
        if alt[0].finite_at(row):
            return ("trick", *alt)
    return "logic", goal, spec


def _router(level: str, prof: str = "logic"):
    """The level's route graph (``route.Router``) for ``prof`` from the private reach pickle, kept per process."""
    if (level, prof) not in _ROUTERS:
        _ROUTERS[(level, prof)] = load_router(str(_reach_path(level)), prof)
    return _ROUTERS[(level, prof)]


def _feet(row) -> tuple:
    return (row.pos[0], row.pos[1], row.pos[2] - 1.0)


PLACED_OFF_M = 2.0   # ``search --placed``: a spot's R6 start this far from its point, or this far beyond its item's
                     # touch radius, at least (never near, AZ-474: the string, not the placement, walks the last metre)


def _start(sim, router, t: dict, goal, scene_sim=None, placed: bool = False) -> dict | None:
    """A target's start: the snapshot's own spot when it lies in the start zone (no teleport), else a teleport
    (R6) onto a sample of the start zone (a floor, any clearance, or the water) nearest the goal (cost to go; where
    the route graph has no way, nearest the item's point, AZ-531) that lands and settles there, and with
    ``scene_sim`` (whole steps on the same snapshot) where the player's update keeps running every tick too: a
    place where it stops (w1's town side: xemu stalls there as well) is no start.
    A ``plan --spots`` spot (Step R1.29) starts at the snapshot's own spot (the hop's arrival) when it lies in any
    zone of the spot's arrival node (:func:`_start_zones`): a teleport nearest the goal can stand on the spot, which
    proves nothing, and a snapshot that a group's other hop put elsewhere would never come back where it started.
    With ``placed`` such a spot always starts by R6, on the start zone's sample nearest the goal at least
    :data:`PLACED_OFF_M` from the spot's point, or that far beyond its item's touch radius (Step R1.29b: a start
    just outside the touch stands within 1 m of where the string first touches it), horizontally (a placed start's
    band is recorded; within 1 m it proves nothing).
    ``{"teleport": (feet, yaw, cell) | None, "sample", "cell", "zone", "how"}`` (``zone``: where the string starts);
    None if none does.  The teleport point is private; its sample id and the place struct's sha12 go into the
    record.  A pickup's or a counted item's start is placed in the item's own cell (the room its generator stands in,
    :func:`item_cell`: placed with the room the snapshot stood in, the item never spawns, AZ-488; when no sample
    settles there, the start zone lies in another room: the snapshot's cell then); an item's or an exit's on the
    nearest samples outside its touch or trigger (:func:`in_goal`: there the placement takes it in the settle, no
    hop), when the zone has any.  Where neither cell settles there (the start zone in a room neither stands in),
    every other cell of the level's list (the world's cell array ``[world+0x28]``) for each sample in turn, the
    rooms whose locations stand nearest it first (:func:`room_order`: a wrong room's placement can settle, its items
    never spawning, AZ-488; AZ-382: an R6 placement keeps the player in the cell it names, and in another room's
    cell the body doesn't land or the player's update stops: w1's two fire-wall skips never had a start)."""
    import numpy as np
    sim.reset()
    r = sim.run([Pad()] * SETTLE)[-1]
    spot = t["kind"] == "spot" and t.get("kit_l3")
    z = router.zone_at(_feet(r), prefer_water=r.state == 6) if settled(r) else None
    if t["start"] is None or z is not None and not (spot and placed) and z in _start_zones(t):
        return {"teleport": None, "sample": None, "cell": None, "zone": z, "how": "the snapshot's own spot"}
    zn = int(t["start"].rsplit(".Z", 1)[1])
    zo, ns, w, wg = router.R.zone_of, router.ns, router.w, router.wg
    node = router.node[:ns]
    land = np.nonzero((node >= 0) & (zo[np.maximum(node, 0)] == zn))[0]
    wl = np.nonzero(wg.lab >= 0)[0] if len(wg.col) else np.zeros(0, dtype=np.int64)
    water = ns + wl[zo[w.nreg + wg.lab[wl]] == zn]
    js = np.concatenate([land, water]).astype(np.int64)
    if not len(js):
        return None
    if spot and placed and (goal.gp is not None or getattr(goal, "touch", None) is not None):
        (cx, cy, _), r = (goal.touch[0], goal.touch[1]) if getattr(goal, "touch", None) is not None else (goal.gp, 0.0)
        js = js[np.hypot(router.X[js] - cx, router.Y[js] - cy) >= PLACED_OFF_M + r]
    cost, far = goal.dist[js], 1e9      # off the route graph (no finite cost, AZ-531): nearest the item's point first
    aim = goal.touch[0] if getattr(goal, "touch", None) is not None else getattr(goal, "gp", None)
    if aim is not None and not np.isfinite(cost).all():
        far = 1e9 + np.sqrt((router.X[js] - aim[0]) ** 2 + (router.Y[js] - aim[1]) ** 2 + (router.Z[js] - aim[2]) ** 2)
    order = np.lexsort((-router.clear[js], np.where(np.isfinite(cost), cost, far)))
    cells, own = recipes.chain(sim.u32)["cells"], item_cell(t)
    near = js[order].tolist()
    sim.reset()
    here = (sim.u32(sim.u32(sim.entity + 0x20) + 0x158) - cells) // 0xB4      # the cell the snapshot stands in
    picks = ([v for v in near if not in_goal(goal, router.pt(v))] or near)[:16]
    tries = [(v, own) for v in picks if own is not None] + [(v, here) for v in picks if own != here]
    rooms = room_order(t["level"], getattr(router, "lv", None), [router.pt(v) for v in picks])
    tries += [(v, c) for v, order in zip(picks, rooms) for c in order if c not in (own, here)]
    for v, cell in tries:
        p = router.pt(v)                # the item's cell first; a start zone in another room settles only in its
        nx = int(goal.nxt[v]) if goal.nxt[v] >= 0 else v      # own, and the walk takes the player into the item's
        yaw = heading_to(p, router.pt(nx)) if nx != v else 0.0   # ([inferred] the game moves his cell), where it spawns
        sim.reset()
        try:
            sim.teleport(p, yaw, cell=cell)
            r = sim.run([Pad()] * SETTLE)[-1]
        except l3.L3Error:              # whole steps can hang on a sample (Step R1.29b: the render 0x54800 looping
            continue                    # at 0xF4EDF after an R6 in w4 and f3): the next sample
        if settled(r) and router.zone_at(_feet(r), prefer_water=r.state == 6) == t["start"]:
            if scene_sim is not None:
                try:
                    scene_sim.reset()
                    scene_sim.teleport(p, yaw, cell=cell)
                    scene_sim.run([Pad()] * SETTLE)
                except l3.L3Error:
                    continue
            return {"teleport": (list(p), yaw, cell), "sample": v, "cell": cell, "zone": t["start"],
                    "how": f"R6 onto a {'water' if v >= ns else 'floor'} sample of {t['start']}"}
    return None


def _start_zones(t: dict) -> list:
    """The zones a target's string may start in without a teleport: its start zone, and for a ``plan --spots`` spot
    (Step R1.29) any zone of its arrival node, which its way back ends in (D122: a location proof comes back to
    where it started)."""
    return t["back"] if t["kind"] == "spot" and t.get("kit_l3") else [t["start"]]


START_OUT = 1.2      # a start sample this many times the touch's radii out of it, at least (the settle may slide it)


def item_cell(t: dict) -> int | None:
    """The cell (room) a pickup's, a counted item's or a spot's generator stands in, its index in the level's cell
    list (the world's cell array, which R6's place struct names): its item spawns only while the player is in it
    (AZ-488); None for another target (:func:`at_location`)."""
    if not at_location(t):
        return None
    doc = _read(DATA_DIR / "generated" / f"{t['goal'].split('/')[0]}.json")
    loc = next((x for x in doc["locations"] if x["id"] == t["goal"]), None)
    return doc["cells"].index(loc["cell"]) if loc and loc.get("cell") in doc["cells"] else None


def room_order(level: str, lv, points) -> list[list[int]]:
    """For each of ``points`` the level's cells (rooms: indices into its list, the world's cell array, whose index
    R6's place struct names) to place a start there in (AZ-382): those the level's locations stand in by their
    nearest location (``lv.rec_points``, the level's mesh), then the cells no location stands in (the sky's, the
    default cell), in list order; all in list order without ``lv``.  Positions stay in memory."""
    import numpy as np
    doc = _read(DATA_DIR / "generated" / f"{level}.json")
    cells = doc.get("cells", [])
    at = []                             # (cell, a location's points)
    for x in doc.get("locations", ()) if lv is not None else ():
        if x.get("cell") in cells:
            try:
                q = np.asarray(lv.rec_points(x["id"])[0], dtype=float).reshape(-1, 3)
            except (KeyError, IndexError, ValueError):
                continue
            if len(q):
                at.append((cells.index(x["cell"]), q))
    out = []
    for p in points:
        near: dict[int, float] = {}
        for c, q in at:
            near[c] = min(near.get(c, math.inf), float(np.min(np.linalg.norm(q - np.asarray(p, dtype=float), axis=1))))
        out.append(sorted(range(len(cells)), key=lambda c: (near.get(c, math.inf), c)))
    return out


def in_goal(goal, feet) -> bool:
    """Whether a body standing on ``feet`` is in an item's touch (1.2 times it, :func:`in_touch`, round where it
    rests or where it spawns, its point, before it falls) or an exit's trigger (``ExitGoal.reached``): a start there
    would take or fire it in its settle."""
    if getattr(goal, "touch", None) is not None:
        _, R, Z = goal.touch
        return in_touch(goal.touch, feet) or goal.gp is not None and in_touch((goal.gp, R, Z), feet)
    if isinstance(goal, ExitGoal):
        import types
        return goal.reached(types.SimpleNamespace(pos=(feet[0], feet[1], feet[2] + 1.0), state=0, hp=1, zone=None))
    return False


def in_touch(touch, feet, out: float = START_OUT) -> bool:
    """Whether a body standing on ``feet`` has its centre within ``out`` times an item's touch (``RouteGoal.touch``:
    the centre, R, Z); False without one."""
    if touch is None:
        return False
    (cx, cy, cz), R, Z = touch
    return ((feet[0] - cx) ** 2 + (feet[1] - cy) ** 2) / (R * R) + (feet[2] + 1.0 - cz) ** 2 / (Z * Z) <= out * out


LEG_TICKS = 6000     # a leg's longest string (Step R1.29e; was 2,400: w1/g0/r1717's proven way ran 2,386 ticks, and
                     # R1.29d's e6/g0/r2789 and f3/g0/r1000 start 113 s and 121 s from their spots)
LEG_FALL = 210       # ticks a branch may stay in the air (Step R1.29e; was 120: 3 flaps landing 10 m lower take 128
                     # ticks, 4 at level 123, 5 take 133-185, the physics envelope)
AIR_CAST = 0.04      # an air kit's share of segments that recast the armor (LT+Y), as a skip rung's
RECAST = (1 + CAST_WAIT, None, 0, 0, 1)   # an air kit's way back starts with the gauge full: LT+Y at rest, the armor
                                          # on the tick after (a recast refills the gauge, RE_MOVEMENT)


APPROACH_M = 3.0     # a douse's approach ends within this of the barrier's shape (the chain's station, Chain.stations)


def plan_steps(t: dict, n: int = 0, db=None) -> tuple[dict, list[tuple[int, str]]]:
    """(the level file, leg ``n``'s level edges on the logic's way in order: (index, ``from>to #index
    confidence``)): the way there (the target's ``path``) or the way back (``plan``'s: :func:`_local_path` from its
    node to its start node with ``kits`` and :func:`_through`)."""
    from azurkit.tools.randomizer.planner.loader import load_database
    doc = _db()[0][t["level"]]
    if n == 0:
        return doc, [(int(x.split("#", 1)[1].split()[0]), x) for x in t.get("path", ())]
    back = _local_path(doc, t["node"], t["start_node"], True, functools.partial(_through, db or load_database())) \
        if t.get("node") and t.get("start_node") else None
    return doc, [(i, f"{u}>{v} #{i} {c}") for i, u, v, c in (back[0] if back else ())]


def plan_edge(doc: dict, steps: list[tuple[int, str]], stall: dict) -> str | None:
    """The plan's level edge a search's stall (``l3_search.Result.stall``, Step X.52) lies at: the first of
    ``steps`` (:func:`plan_steps`) whose from-node holds the region edge's from-zone and whose to-node its to-zone,
    else the first whose from-node holds the stalled cell's zone; None for neither (a level file changed since the
    plan names no zones for what it lost)."""
    zones = {n["id"]: [a[5:] for a in n.get("anchors", []) if a.startswith("zone:")] for n in doc.get("node", [])}
    edges = doc.get("edge", [])
    ends = [(s, zones.get(edges[i]["from"], []), zones.get(edges[i]["to"], [])) for i, s in steps if i < len(edges)]
    return next((s for s, a, b in ends if stall.get("from") in a and stall.get("to") in b), None) or next(
        (s for s, a, _ in ends if stall.get("zone") in a), None)


def stalls(results: dict) -> dict:
    """``stalls.json`` (Step X.52): each target's legs not found, every seed's ``why``, best cost to go and stall
    (the region edge ahead of its least-cost cell: id, kind, confidence, the zones at its ends, the plan's level edge
    it lies at): measured candidates for R1.23's and R1.24's unsound ``assumed`` or ``probe-needed`` edges, never
    proof.  Ids, zones and costs only."""
    out = {}
    for key, r in sorted(results.items()):
        rows = [{"leg": leg["n"], "goal": leg["goal"], "seed": x.get("index"), "why": x["why"],
                 "best_cost_s": x.get("best_cost_s"), "start_cost_s": leg.get("start_cost_s"), **x["stall"]}
                for leg in r.get("legs", ()) if not leg.get("segs") and not leg.get("parts")
                for x in leg.get("runs", ()) if x.get("stall")]
        if rows:
            out[key] = rows
    return out


def _tally(runs) -> tuple[dict, dict, dict]:
    """The runs' faults by site, their kernel taints' sites (Step X.52) and the branches that left the level, by the
    level they load (Step X.52b), merged."""
    faults, at, exits = collections.Counter(), collections.defaultdict(set), collections.Counter()
    for x in runs:
        faults.update(x.get("fault_sites") or {})
        exits.update(x.get("exits") or {})
        for k, v in (x.get("taint_at") or {}).items():
            at[k].update(v)
    return dict(faults.most_common()), {k: sorted(v) for k, v in sorted(at.items())}, dict(sorted(exits.items()))


def crossings(t: dict, n: int = 0) -> list[dict]:
    """The barriers a spot's leg ``n`` crosses on the logic's way, in order (Step R1.29e; every one, Step R1.29f): a
    level edge of the way there or back (:func:`plan_steps`) whose ``through`` names one, as a douse needs it: the
    barrier, its shape (a generated id), the staff's elements, the least element levels its crossing asks (``kit``,
    :func:`_through`), the edge's from- and to-node zones."""
    from azurkit.tools.randomizer.planner.loader import load_database
    from azurkit.tools.randomizer.planner.plan import CASTS
    db = load_database()
    doc, steps = plan_steps(t, n, db)
    out = []
    for i, step in steps:
        e = doc["edge"][i]
        for bid in e.get("through", ()):
            o = db.hand[bid][2]
            gen = db.generated_objects[o["of"]][2] if "of" in o else {}
            kits = [k for term in dnf(_through(db, bid, e["from"], e["to"])) if (k := _kit_of(term)) is not None]
            out.append({"leg": n, "barrier": bid, "edge": step, "shape": (gen.get("shapes") or [o.get("of")])[0],
                        "elements": [CASTS[c] for c in gen.get("elements") or "" if c in CASTS],
                        "kit": min(kits, key=lambda k: (sum(k.values()), sorted(k.items())), default={}),
                        "from_zones": _zones(doc, e["from"]), "to_zones": _zones(doc, e["to"])})
    return out


def crossing(t: dict, n: int = 0) -> dict | None:
    """The first barrier of :func:`crossings` (None for none)."""
    return next(iter(crossings(t, n)), None)


def _add(L: dict, segs, cam: float) -> None:
    """Append searched segments (from a camera at ``cam``) to a target's string so far: to its prefix, or once a
    douse put pads in its tail, to the tail as pads (the camera after them kept)."""
    if L["tail"]:
        more, L["cam"] = expand([Seg(*x) for x in segs], cam)
        L["tail"] = L["tail"] + segments(more)
    else:
        L["prefix"] = L["prefix"] + [tuple(x) for x in segs]


def _douse(sim, label: str, L: dict, c: dict, lvl: str, scene: bool) -> dict:
    """Cross barrier ``c`` (:func:`crossing`) from where a target's string so far ends: ``sim.douse`` on ``sim``
    (whole steps), its pads added to the string's tail; its summary, ``passed`` False when the feet don't end in the
    crossing's to-node (or ``stopped``, an L3Error's text).  A barrier not in the way there (``sim.douse.in_the_way``
    on the to-node's cost to go, as ``Chain.staff``) is crossed by nothing: passed, ``not_in_the_way``, no pads."""
    out, R = L["out"], _router(lvl)
    p = object_points(R.lv, c["shape"])
    centre, to = tuple(float(x) for x in (p.min(axis=0) + p.max(axis=0)) / 2), set(c["to_zones"])
    try:
        seg = Segment(label, teleport=L["start"]["teleport"], settle=SETTLE, prefix=L["prefix"], scene=scene,
                      kit=out.get("kit"), tail=L["tail"])
        _, row, cam, _, _ = leg_start(sim, seg)
        if not dz.in_the_way(RouteGoal(R, c["to_zones"]).cost, centre, row.pos):
            return {"passed": True, "ticks": 0, "attacks": 0, "not_in_the_way": True, "pads": []}
        res = dz.douse(sim, row, centre, c["elements"], lambda r: _settled_zone(R, r) in to, cam)   # AZ-590
    except l3.L3Error as ex:
        return {"passed": False, "stopped": str(ex)}
    if res.passed:
        L["tail"], L["cam"] = L["tail"] + segments(res.pads), res.cam
    return {**res.summary(), "pads": segments(res.pads)}


def _doused(P: dict | None, leg: dict, info: dict, pads: list) -> dict:
    """A doused leg so far (Step R1.29f), after one more barrier: ``leg`` the search to it, ``info`` its douse's
    outcome and ``pads`` its pads; the pieces in turn (``parts``), their ticks, the least robustness, the approach
    legs and the douses' outcomes."""
    P = P or {"parts": [], "ticks": 0, "robustness": 1.0, "approach": [], "douse": [], "cam": leg["cam"]}
    return {**P, "parts": P["parts"] + [{"segs": leg["segs"]}, {"pads": pads}],
            "ticks": P["ticks"] + leg["ticks"] + info["ticks"],
            "robustness": min(P["robustness"], leg["robustness"] or 0.0),
            "approach": P["approach"] + [leg], "douse": P["douse"] + [info]}


def _doused_leg(P: dict, leg: dict, w: dict | None) -> dict:
    """A doused leg's record (Step R1.29f): ``leg`` the search on from its last barrier (``w`` its winner, None for
    none) after :func:`_doused`'s pieces ``P``; one douse's ``approach`` and ``douse`` stay single, as before."""
    one = len(P["douse"]) == 1
    return {**leg, "approach": P["approach"][0] if one else P["approach"],
            "douse": P["douse"][0] if one else P["douse"], "segs": None, "cam": P["cam"],
            **({"parts": P["parts"] + [{"segs": w["segs"]}], "ticks": P["ticks"] + w["ticks"],
                "robustness": min(P["robustness"], w["robustness"] or 0.0)} if w else {})}


def leg_limits(steps: int, wall_cap: float | None, dive: float, air: int, used: int = 0,
               plateau: int | None = None) -> Limits:
    """A spot's or an edge's leg's search (Step R1.29e): :data:`LEG_TICKS` for the whole leg (``used``: its ticks
    before this search, a lead or a douse's way to its barrier and the douse) and :data:`LEG_FALL`, and with an air
    kit recasts (:data:`AIR_CAST`); ``plateau`` (Step X.52): a seed ends after that many steps with no new best."""
    return Limits(steps=steps, wall_cap_s=wall_cap, ticks=max(1, LEG_TICKS - used), fall=LEG_FALL, dive=dive,
                  cast=AIR_CAST if air else 0.0, plateau=plateau)


def leg_lead(n: int, air: int) -> list:
    """What leg ``n``'s string starts with before its search (Step R1.29e): an air kit's way back, :data:`RECAST`
    (the way there may have spent the gauge)."""
    return [list(RECAST)] if n and air else []


def leg_start(sim, seg: Segment):
    """``start_of`` from the snapshot, as the workers and the replay run it: ``sim`` reset first (the leader's
    simulator ran the last target's start, or a douse, Step R1.29e), and left at the start.  A start whose row is
    dead (state 7 or HP 0: the way there took its touch on the way to a death) raises ``L3Error`` at site ``dead
    start`` (AZ-571), and one off the floor whose body dies before it lands (``l3_search.lands_alive``: a touch high
    over a lethal drop), at rest and holding its string's last stick, at site ``doomed start`` (AZ-627), so no leg is
    searched from either: the way there's ``confirm`` passed its touch at rest or on that stick."""
    sim.reset()
    out = start_of(sim, seg)
    row = out[1]
    if row.state == DEAD or row.hp <= 0:
        raise l3.L3Error(f"the leg starts dead (state {row.state}{', HP 0' if row.hp <= 0 else ''})",
                         site="dead start")
    if not settled(row):
        doomed, how = lands_alive(sim, out[2]) == "dies", "at rest"
        held = next((p for p in reversed(out[3]) if any(p.stick)), None)   # past an air kit's RECAST at rest
        if doomed and held is not None and row.state in AIRBORNE:
            sim.reset(out[0])
            doomed, how = lands_alive(sim, out[2], held=held, air=True) == "dies", "at rest and on its last stick"
        sim.reset(out[0])
        if doomed:
            raise l3.L3Error(f"the leg starts off the floor (state {row.state:#x}) and dies {how} before it lands",
                             site="doomed start")
    return out


def search_all(d: Path, jobs: int, steps: int, wall_cap: float | None, only=(), scene: bool = False,
               redo: bool = False, workers: int | None = None, dive: float = 0.0, placed: bool = False,
               touch: float = 0.75, douse: bool = False, plateau: int | None = None) -> None:
    """Search every target at once: per level and kit, one persistent worker pool on its snapshot
    (``l3_pool.Pool``, ``workers`` processes) runs every target's first leg, then every spot's way back, each with
    ``jobs`` derived seeds (``l3_pool.solve_many``: the same winners whatever the worker count).  ``scene``: whole
    steps (rigs, bridges, enemies and pickups move; 5-10x slower), for a target the player-tick search exhausted
    on static geometry; ``redo``: search a target again even when results.json has it; ``dive`` (Step R1.29): the
    share of segments in the water that dive (``Limits.dive``), and a spot's depth under a swimming row counts in
    its cost (``RouteGoal``'s ``dive``); ``placed``: a spot starts by R6 off the spot (:func:`_start`); ``touch``: a
    spot's goal reach in m (the whole-step check, ``l3_taken``, tells whether the game's own touch took it).
    Each leg searches with :func:`leg_limits`; an air kit's way back starts with :data:`RECAST` (the way there may
    have spent the gauge), kept as its string's first segment; a leg records and prints how many cells each seed
    left at the tick cap (``capped``).  ``douse`` (Step R1.29e, whole steps): a leg through barriers on the logic's
    way (:func:`crossings`: the way there's or the way back's level edges, each in turn, Step R1.29f) is searched
    to within :data:`APPROACH_M` of the first barrier's shape on its near side (``ObjectGoal``), crossed by
    ``sim.douse`` (the staff's elements cast, attacks on the walk; the kit gets the element levels every crossing
    asks), searched on to the next barrier and crossed the same way, then searched on to the leg's goal; the leg
    keeps those pieces as ``parts`` (each douse's pads, ``l3.pads`` segments) and ``douse`` lists each crossing's
    outcome.  Diagnostics (Step X.52): every target prints a line (one with no snapshot or no start too); a seed
    ends at ``plateau`` steps with no new best cost to go (default: never); a leg not found
    records its runs' faults by site and kernel taints' sites (``faults``, ``taint_at``) and each seed's stall,
    the edge ahead of its best cell with the plan's level edge it lies at (``plan``), collected in DIR's
    ``stalls.json`` (:func:`stalls`); a leg whose every seed's start failed in the workers says so."""
    from devkit.sim.ports import vanilla_iso
    from devkit.sim.ports import read_file
    from azurkit.tools.randomizer.planner.loader import load_database
    from devkit.reach.l3_pool import Pool, Problem, solve_many
    xbe = read_file(str(vanilla_iso()), "default.xbe")
    targets = _read(d / "targets.json")["targets"]
    snaps = _read(d / "snapshots.json")
    results = _read(d / "results.json") if (d / "results.json").exists() else {}
    priors: dict[tuple, list] = collections.defaultdict(list)      # (level, start zone) -> earlier runs' winners
    for t in targets:
        r = results.get(t["key"], {})
        if r.get("verified") and r.get("legs") and r["legs"][0].get("segs"):
            priors[(t["level"], t["start"])].append([tuple(x) for x in r["legs"][0]["segs"]])
    groups: dict[str, list] = collections.defaultdict(list)
    touched = False
    for t in sorted(targets, key=lambda t: (t["kind"] != "edge", targets.index(t))):
        key = t["key"]
        if "skip" in t or (key in results and not redo) or (only and key not in only):
            continue
        g = _group(t)
        if "label" not in snaps.get(g, {}):
            results[key] = {"reached": False, "why": f"no snapshot for {g}"}
            print(key, json.dumps(results[key]), flush=True)
            continue
        groups[snaps[g]["label"]].append(t)
        if t["kind"] == "spot" and t.get("touch", 0.75) != touch:   # this search's reach, which the verify and
            touched = True                                          # the replays judge it with too
            if touch == 0.75:
                del t["touch"]
            else:
                t["touch"] = touch
    _write(d / "results.json", results)
    if touched:
        _write(d / "targets.json", {**_read(d / "targets.json"), "targets": targets})
    plateau = plateau or None
    db = functools.cache(load_database)          # a way back's plan steps (a stall's plan edge), loaded once
    for label, ts in groups.items():
        lvl, t0 = ts[0]["level"], time.monotonic()
        sim = l3.L3(l3.read_snapshot(l3.snapshot_path(label)), xbe, scene=scene)
        reach = str(_reach_path(lvl))
        live = {}         # key -> the target's search so far: its strings as a prefix (Segs) and a tail (pads)
        for t in ts:
            goals = [t["goal"]] + ([t["back"]] if t["kind"] == "spot" else [])
            cross = [crossings(t, n) if douse else [] for n in range(len(goals))]
            kit = dict(t["kit"])
            for c in (c for cs in cross for c in cs):   # the douses' element levels too (their destroy requirement)
                kit = {e: n for e in ELEMENTS if (n := max(kit.get(e, 0), c["kit"].get(e, 0)))}
            start = _start(sim, _router(lvl), t, _goal(_router(lvl), t, goals[0], t["kit"].get("air", 0)),
                           placed=placed)
            if start is None:
                results[t["key"]] = {"reached": False, "why": "no sample of the start zone lands and settles there"}
                print(t["key"], json.dumps(results[t["key"]]), flush=True)
                continue
            out = {"reached": True, "start": start["how"], "mode": "scene" if scene else "tick", "legs": [],
                   **({"kit": kit} if t.get("kit_l3") or any(cross) else {})}
            live[t["key"]] = {"t": t, "start": start, "goals": goals, "out": out, "cross": cross, "prefix": [],
                              "tail": [], "cam": None, "parts": None}
        with Pool(label, xbe, workers=workers, name="l3 certify") as pool:
            for n in (0, 1):
                for i in itertools.count():       # leg n's piece i: the way to its barrier i, or on from its last
                    ins = [k for k, L in live.items() if L["out"]["reached"] and n < len(L["goals"]) and
                           i <= len(L["cross"][n]) and (i == 0 or L["parts"] is not None)]
                    if not ins:
                        break
                    batch = []
                    for key in ins:
                        L = live[key]
                        t, out = L["t"], L["out"]
                        air, target = t["kit"].get("air", 0), L["goals"][n]
                        approach = L["cross"][n][i] if i < len(L["cross"][n]) else None
                        if i == 0:
                            L["lead"], L["parts"] = leg_lead(n, air), None
                            _add(L, L["lead"], L["cam"])
                        used = sum(x[0] for x in L["lead"]) if i == 0 else L["parts"]["ticks"]   # its ticks so far
                        seg = Segment(label, teleport=L["start"]["teleport"], settle=SETTLE, prefix=L["prefix"],
                                      scene=scene, kit=out.get("kit"), tail=L["tail"])
                        try:
                            _, row, _, _, _ = leg_start(sim, seg)    # the leg's start row as the workers have it
                        except l3.L3Error as ex:            # whole steps stop on the way (a death, a cutscene): no leg
                            out.update(reached=False, why=f"leg {n}: its start doesn't run: {ex}")
                            continue

                        def goal_of(prof):
                            R_ = router_of(reach, prof, air) if prof == "trick" else _router(lvl, prof)
                            if approach:
                                c = approach
                                return ObjectGoal(R_, c["shape"], radius=APPROACH_M,
                                                  side=c["from_zones"], air=air), {
                                    "module": GOAL_MODULE, "factory": "make_object_goal",
                                    "kwargs": {"reach": reach, "obj": c["shape"], "prof": prof, "air": air,
                                               "radius": APPROACH_M, "side": c["from_zones"]}}
                            g = _goal(R_, t, target, air)
                            return g, {"module": GOAL_MODULE, "factory": "make_exit_goal",
                                       "kwargs": {"reach": reach, "exit_id": target, "prof": prof, "air": air}} \
                                if isinstance(g, ExitGoal) else {
                                    "module": GOAL_MODULE, "factory": "make_goal",
                                    "kwargs": {"reach": reach, "target": target, "prof": prof, "air": air,
                                               **({"dive": True} if dive else {}),
                                               **({"touch": list(g.touch_shape)} if g.touch_shape else
                                                  {"touch": t["touch"]} if "touch" in t else {})}}
                        prof, goal, spec = leg_guide(goal_of, row)   # the logic's, else the trick graph's
                        aim = exit_nodes(goal.R, target) if isinstance(goal, ExitGoal) else \
                            target if n == 0 else t["start"]
                        seeds = [s_ for s_ in [route_seed(goal.R, _feet(row), aim, air=air)] if s_]
                        seeds += priors[(lvl, t["start"])] if n == 0 and i == 0 and not approach else []
                        batch.append((key, prof, goal.finite_at(row), round(goal.cost(row), 1), len(seeds),
                                      Problem(seg, spec, leg_limits(steps, wall_cap, dive, air, used, plateau), jobs,
                                              seeds)))
                    for (key, prof, on_graph, cost, nseeds, _), r in zip(batch,
                                                                         solve_many(pool, [b[-1] for b in batch])):
                        L = live[key]
                        t, out, w = L["t"], L["out"], r["winner"]
                        approach = L["cross"][n][i] if i < len(L["cross"][n]) else None
                        lead = L["lead"] if i == 0 else []
                        capped = [x.get("capped", 0) for x in r["runs"]]
                        name = ("the barrier" if approach else "the spot" if t["kind"] == "spot" and n == 0 else
                                "back to the start zone" if n else "the to-node")
                        leg = {"n": n, "goal": name, "prof": prof, "on_graph": on_graph, "start_cost_s": cost,
                               "seeds": nseeds, "problem": r["problem"], "seconds": r["seconds"], "runs": r["runs"],
                               "capped": capped,
                               **({"segs": lead + w["segs"], "ticks": w["ticks"] + sum(x[0] for x in lead),
                                   "robustness": w["robustness"], "cam": w["cam"], "winner_index": w["index"],
                                   "taint": w["taint"], **({"lead": sum(x[0] for x in lead)} if lead else {}),
                                   **({"trial_errors": w["trial_errors"]} if w.get("trial_errors") else {})}
                                  if w else {})}
                        faults, taint_at, exits = _tally(r["runs"])
                        if not w:                            # each seed's stall at the plan's level edge
                            pdoc, psteps = plan_steps(t, n, db() if n else None)
                            for x in r["runs"]:
                                if x.get("stall"):
                                    x["stall"]["plan"] = plan_edge(pdoc, psteps, x["stall"])
                        print(key, f"leg {n} ({name}): cells at the {LEG_TICKS}-tick cap per seed {capped}",
                              *([f"faults {faults}"] if faults else []),
                              *([f"taint at {taint_at}"] if taint_at else []),
                              *([exits_text(exits)] if exits else []),
                              *([f"stalls {[stall_name(x['stall']) for x in r['runs'] if x.get('stall')]}"]
                                if not w else []), flush=True)
                        if not approach and L["parts"] is not None:   # a doused leg: to each barrier, its douse,
                            leg, L["parts"] = _doused_leg(L["parts"], leg, w), None      # and on from the last
                        if not approach or not w:
                            out["legs"].append(leg)
                        if not w:
                            out["reached"] = False
                            why = collections.Counter(x["why"].split(":")[0] for x in r["runs"])
                            exhausted = why.get("exhausted", 0)
                            taint = sorted({f for x in r["runs"] for f in x.get("taint", ())})
                            out["taint"], out["inconclusive"] = taint, bool(taint) or exhausted < len(r["runs"])
                            out["faults"], out["taint_at"], out["exits"] = faults, taint_at, exits
                            out["why"] = (f"leg {n} ({name}): its start doesn't run in the workers: "
                                          f"{r['runs'][0]['why'][len('start: '):]}"
                                          if why.get("start") == len(r["runs"]) else
                                          f"leg {n} ({name}): inconclusive: the searches read what L3 doesn't model "
                                          f"({', '.join(taint)})" if taint else
                                          f"leg {n} ({name}): every seed's search explored all it reached ({exhausted} "
                                          f"of {len(r['runs'])}): the logic is wrong or the move set misses a way"
                                          if exhausted == len(r["runs"]) else
                                          f"leg {n} ({name}): no seed reached it ({dict(why)})")
                            continue
                        _add(L, w["segs"], w["cam"])
                        if approach:                         # the douse, from where the way to the barrier ends
                            c = approach
                            d_ = _douse(sim, label, L, c, lvl, scene)
                            info = {k: c[k] for k in ("barrier", "edge", "elements")} | {
                                k: v for k, v in d_.items() if k != "pads"}
                            out.setdefault("douse", []).append({"leg": n, **info})
                            if d_["passed"]:
                                L["parts"] = _doused(L["parts"], leg, info, d_["pads"])
                            else:
                                out["legs"].append({**leg, "douse": info})
                                out.update(reached=False,
                                           why=f"leg {n}: the douse of {c['barrier']} didn't pass ({info})")
        for key, L in live.items():
            t, start, goals, out = L["t"], L["start"], L["goals"], L["out"]
            out["seconds"], v = round(time.monotonic() - t0, 1), None
            if out["reached"]:      # end to end, then in whole steps (enemies, rigs and the pickup move there)
                legs_ = _legs(label, start, goals, out["legs"])
                was = l3_inventory(sim, out.get("kit") or t["kit"]) if t["kind"] == "spot" else None
                v, fault = _verify_again(sim, t, legs_, _router(lvl), out.get("kit"))
                out.update(fault)   # stopped twice: inconclusive, the legs kept and no whole-steps verify
            if v is not None:
                out.update(verified=all(v["ok"]), ticks=len(v["rows"]), outcome=_outcome(v["rows"], _router(lvl)),
                           segments=segments(v["pads"], v["rows"]))
                ssim = sim if scene else l3.L3(sim.snap, xbe, scene=True)
                try:                # whole steps: a pickup's own item taken there too (the game's outcome, AZ-483)
                    sv = v if scene else _verify(ssim, t, legs_, _router(lvl), out.get("kit"), tail=TAIL)
                    out["scene_ok"] = sv["ok"]
                    if t.get("exit") or t["kind"] in ITEMS and touch_of(t) is not None and goal_fields(t["goal"]):
                        out["scene_outcome"] = sv["outcome_own"]     # an item's field taken, the exit's switch fired
                except l3.L3Error as ex:
                    out["scene_ok"] = f"whole steps stopped: {ex}"
                if was is not None and isinstance(out["scene_ok"], list):   # whole steps run the pickup (R1.29)
                    out["l3_taken"] = l3_taken(ssim, t["goal"], was)
            _write_priv(d, key, {"start": start, "targets": goals})
            results[key] = out
            _write(d / "results.json", results)     # each target as it ends: an error later loses no other one
            print(key, json.dumps({k: v for k, v in out.items() if k not in ("legs", "segments", "outcome")}),
                  [(x["n"], x["prof"], x.get("ticks"), x.get("robustness"), x["seconds"]) for x in out["legs"]],
                  flush=True)
        _write(d / "stalls.json", stalls(results))


# -- skips (Step R1.8g; D183, D177, D178) ----------------------------------------------------------------------------

RUNGS = ((0, 0), (1, 1), (2, 2), (3, 3), (3, None))   # D183's ladder: (air level, most flaps in one jump); None: the
                                                      # armor's own cap (air 3: 5).  0 flaps -> no air, 1 -> air 1, 2 ->
                                                      # air 2, 3 or more -> air 3
TIERS = (("standard", 0.50), ("hard", 0.05), ("frame_perfect", 0.0))   # robustness under jitter -> the tier it
                                                      # supports, difficulty 2-4 (D259: 50%+ standard, 5-50% hard,
                                                      # else frame_perfect; Safe folds into Standard); devkit/xemu/chain.py's
                                                      # and devkit/reach/l3_contact.py's too
SKIP_TRIALS = 32                                      # jittered copies a winner is graded on
# The skips L3 searches: the level; the start zone (None: the snapshot's own spot); the goal (a zone, zones, or a
# pickup's generated id); the way back (a spot's, D122); ``roll``: the move set rolls (BLACK) too; ``scene``: search
# in whole steps (an enemy, a rig or a field decides it); ``loadvm``: a state other than a new game plus a hop;
# ``rungs``: an easier variant keeps its own air (D183) and searches that rung only; ``extra``: the kit's other
# elements (its ``requires``); ``shape``: other search limits (another string when xemu refuses one).
SKIPS = {
    "w1.firewall01_air1_beach_town": dict(level="w1", start="w1.Z004", goal="w1.Z047"),
    "w1.firewall01_air2_beach_town": dict(level="w1", start="w1.Z004", goal="w1.Z047", rungs=((2, 2),)),
    "w1.firewall01_air1_town_beach": dict(level="w1", start="w1.Z047", goal="w1.Z004"),
    "town.firewall02_air1": dict(level="town", start="town.Z013", goal="town.Z004"),
    "f1.flamespout6_air1": dict(level="f1", start="f1.Z019", goal="f1.Z030"),
    "e2.steam_group_air1": dict(level="e2", start="e2.Z005", goal="e2.Z074"),
    "e2.steam_group_air2": dict(level="e2", start="e2.Z005", goal="e2.Z074", rungs=((2, 2),)),
    "e6.acidblock02_air1": dict(level="e6", start="e6.Z076", goal="e6.Z049"),
    "e6.acidblock02_air2": dict(level="e6", start="e6.Z076", goal="e6.Z049", rungs=((2, 2),)),
    "w2.firewall02_air3": dict(level="w2", start="w2.Z006", goal="w2.Z041"),
    "f2.acidblock04_fly_around": dict(level="f2", start="f2.Z000", goal="f2.Z008"),
    "f6.rjump_terraces": dict(level="f6", start="f6.Z002", goal="f6.Z011", roll=True),
    "a6.rjump_platforms": dict(level="a6", start="a6.Z034", goal="a6.Z003", roll=True, scene=True),
    "life.rjump_second_switch": dict(level="life", start="life.Z001", goal="life.Z011", roll=True),
    "w3.iceclimb_frag_fire1": dict(level="w3", start="w3.Z000", goal="w3/g1/r2018", back="w3.Z000"),
    "e6.slide_flight": dict(level="e6", start="e6.Z000", goal="e6.Z011", back="e6.Z000"),
    "f4.ledgepop": dict(level="f4", start="f4.Z015", goal="f4.Z157"),
    # floor 8's shaft ring -> floor 9, the deck called from floor 1, where a new game's town arrival leaves it (R2.17)
    "d1.elevator_bounce": dict(level="d1", start="d1.Z018", goal="d1.Z005", scene=True),
    "e5.frag_fire3_earth1": dict(level="e5", start="e5.Z401", goal="e5/g0/r4263", rungs=((0, 0),),
                                 extra={"earth": 1, "water": 2}),
}


def skip_kit(air: int, extra: dict) -> dict:
    """A rung's kit: its air level and the skip's other elements (the armor is cast by input when air > 0)."""
    return {**extra, **({"air": air} if air else {})}


def tier(robust: float) -> int:
    """D177, D259: a string's difficulty from its robustness under jitter (under 5%, or only the exact string: 4)."""
    return next((d for d, (_, p) in enumerate(TIERS, 2) if robust >= p), 4)


def plan_skips(out: Path, only=()) -> list[dict]:
    """The skip targets (:data:`SKIPS`) with their snapshot group and hop."""
    levels, gens, level_of = _db()
    tricks = {x["id"]: x for x in tomllib.loads((DATA_DIR / "tricks.toml").read_text(encoding="utf-8"))["skip"]}
    targets = []
    for sid, spec in SKIPS.items():
        if only and sid not in only:
            continue
        lvl = spec["level"]
        t = {"key": f"skip-{sid}", "kind": "skip", "id": sid, "level": lvl, "start": spec["start"],
             "goal": spec["goal"], "back": spec.get("back"), "kit": {}, "roll": spec.get("roll", False),
             "scene": spec.get("scene", False), "rungs": [list(r) for r in spec.get("rungs", RUNGS)],
             "extra": spec.get("extra", {}), "requires_was": tricks[sid].get("requires"),
             **({"shape": spec["shape"]} if "shape" in spec else {})}
        if spec.get("loadvm"):
            t.update(loadvm=spec["loadvm"], group=f"{spec['loadvm']}-k0", hop=None)
        else:
            node = next((n["id"] for n in levels[lvl]["node"] if f"zone:{spec['start']}" in n.get("anchors", [])),
                        None) if spec["start"] else None
            t["hop"] = _hop(_arrivals(lvl, levels, gens, level_of), node)
        targets.append(t)
    out.mkdir(parents=True, exist_ok=True)
    _write(out / "targets.json", {"step": "R1.8g", "targets": targets})
    return targets


def _search_rung(t: dict, label: str, start: dict, goals: list, kit: dict, flaps, steps: int, wall_cap: float | None,
                 jobs: int, xbe: bytes, scene: bool, strings: list, pool) -> dict:
    """One rung of a skip: each leg (the goal, then the way back) searched with ``kit`` set in L3 and at most
    ``flaps`` flaps in one jump, ``jobs`` derived seeds on ``pool`` (the snapshot's worker pool); the legs'
    winners, or why not and whether a run read what L3 doesn't model (``taint``: then a miss is inconclusive)."""
    lvl, air = t["level"], kit.get("air", 0)
    sim = l3.L3(l3.read_snapshot(l3.snapshot_path(label)), xbe, scene=scene)
    reach = str(_reach_path(lvl))
    limits = Limits(steps=steps, wall_cap_s=wall_cap, flaps=flaps, roll=0.1 if t["roll"] else 0.0,
                    cast=0.04 if air else 0.0, **t.get("shape", {}))
    out = {"air": air, "flaps": flaps, "kit": kit, "mode": "scene" if scene else "tick", "reached": True, "legs": []}
    prefix, t0 = [], time.monotonic()
    for n, target in enumerate(goals):
        seg = Segment(label, teleport=start["teleport"], settle=SETTLE, prefix=prefix, scene=scene, kit=kit)
        _, row, _, _, _ = start_of(sim, seg)
        def goal_of(prof, target=target):
            return RouteGoal(router_of(reach, prof, air) if prof == "trick" else _router(lvl, prof), target, air=air), {
                "module": GOAL_MODULE, "factory": "make_goal",
                "kwargs": {"reach": reach, "target": target, "prof": prof, "air": air}}
        prof, goal, spec = leg_guide(goal_of, row)          # the logic's, else the trick graph's
        seeds = [x for x in [route_seed(goal.R, _feet(row), target, air=air)] if x] + (strings if n == 0 else [])
        r = solve(seg, spec, xbe, limits=limits, seeds=jobs, strings=seeds, trials=SKIP_TRIALS, pool=pool)
        w = r["winner"]
        taint = sorted(set().union(*(x.get("taint", ()) for x in r["runs"])))
        out["legs"].append({"n": n, "goal": "the skip's goal" if n == 0 else "back", "prof": prof,
                            "start_cost_s": round(goal.cost(row), 1), "seeds": len(seeds), "problem": r["problem"],
                            "seconds": r["seconds"], "runs": r["runs"], "taint": taint,
                            **({"segs": w["segs"], "ticks": w["ticks"], "robustness": w["robustness"],
                                "flaps": w["flaps"], "cam": w["cam"], "winner_index": w["index"]} if w else {})})
        if not w:
            out["reached"] = False
            why = collections.Counter(x["why"].split(":")[0] for x in r["runs"])
            out["why"] = (f"leg {n}: every seed explored all it reached" if why.get("exhausted", 0) == len(r["runs"])
                          else f"leg {n}: the step budget ran out ({dict(why)})")
            out["taint"] = taint      # empty: a clean miss (a refutation within the budget); else inconclusive
            break
        prefix = prefix + [tuple(x) for x in w["segs"]]
    out["seconds"] = round(time.monotonic() - t0, 1)
    return out


def _check_rung(t: dict, label: str, start: dict, goals: list, rung: dict, xbe: bytes) -> dict:
    """A reached rung end to end in L3 (its own mode), then in whole steps: the pads, rows and verdicts; an end to
    end that stops twice (:func:`_verify_again`) gives no whole steps and what it records."""
    legs_ = [{"snapshot": label, "teleport": start["teleport"], "target": g_, "segs": leg["segs"]}
             for g_, leg in zip(goals, rung["legs"])]
    snap = l3.read_snapshot(l3.snapshot_path(label))
    v, fault = _verify_again(l3.L3(snap, xbe, scene=rung["mode"] == "scene"), t, legs_, _router(t["level"]),
                             rung["kit"])
    if v is None:
        return {"v": None, "sv": None, "scene_ok": False, **fault}
    try:
        sv = v if rung["mode"] == "scene" else _verify(l3.L3(snap, xbe, scene=True), t, legs_, _router(t["level"]),
                                                       rung["kit"])
        scene_ok = all(sv["ok"]) and min(r.hp for r in sv["rows"]) > 0
    except l3.L3Error:          # the start runs in whole steps (``_start`` checked it): the string stops them, as a
        sv, scene_ok = None, False   # level switch or a cutscene would; xemu would stall there too
    return {"v": v, "sv": sv, "verified": all(v["ok"]), "scene_ok": scene_ok}


def search_skips(d: Path, jobs: int, steps: int, wall_cap: float | None, only=(), redo: bool = False,
                 out_name: str = "results.json") -> None:
    """Each skip's D183 ladder: its top rung first (is it reachable at all?), then from the bottom up; the first
    rung that reaches (and holds in whole steps) sets the air its ``requires`` asks.  A tick-mode winner that whole
    steps refuse (a field's hit, an enemy) is searched again in whole steps, seeded with it."""
    from devkit.sim.ports import vanilla_iso
    from devkit.sim.ports import read_file
    xbe = read_file(str(vanilla_iso()), "default.xbe")
    targets = _read(d / "targets.json")["targets"]
    snaps = _read(d / "snapshots.json")
    rpath = d / out_name                 # several searches at once each write their own file; merge them after
    results = _read(rpath) if rpath.exists() else {}
    for t in targets:
        key = t["key"]
        if (key in results and not redo) or (only and key not in only and t["id"] not in only):
            continue
        g = _group(t)
        if "label" not in snaps.get(g, {}):
            results[key] = {"reached": False, "why": f"no snapshot for {g}"}
            _write(rpath, results)
            continue
        label, lvl = snaps[g]["label"], t["level"]
        goals = [t["goal"]] + ([t["back"]] if t["back"] else [])
        snap = l3.read_snapshot(l3.snapshot_path(label))
        sim = l3.L3(snap, xbe)
        start = _start(sim, _router(lvl), t, RouteGoal(_router(lvl), goals[0], air=3), l3.L3(snap, xbe, scene=True))
        if start is None:
            results[key] = {"reached": False, "why": "no sample of the start zone lands and settles there"}
            _write(rpath, results)
            continue
        rungs = [tuple(r) for r in t["rungs"]]
        order = [rungs[-1]] + rungs[:-1]
        from devkit.reach.l3_pool import Pool
        pool = Pool(label, xbe, workers=jobs, name="l3 skips")
        out = {"start": start["how"], "rungs": [], "reached": False}
        strings, top, best = [], None, None
        try:
            for i, (air, fl) in enumerate(order):
                if i and top is None:
                    break                                   # the top rung missed: the lower ones are not searched
                kit = skip_kit(air, t["extra"])
                try:
                    rung = _search_rung(t, label, start, goals, kit, fl, steps, wall_cap, jobs, xbe, t["scene"], strings,
                                        pool)
                except l3.L3Error as ex:             # the start itself doesn't run (whole steps after a teleport)
                    rung = {"air": air, "flaps": fl, "kit": kit, "mode": "scene" if t["scene"] else "tick",
                            "reached": False, "why": f"the start doesn't run: {ex}", "legs": []}
                if rung["reached"]:
                    chk = _check_rung(t, label, start, goals, rung, xbe)
                    if chk["verified"] and chk["scene_ok"] is False and rung["mode"] == "tick":
                        seeds = [[tuple(x) for x in rung["legs"][0]["segs"]]]
                        try:
                            again = _search_rung(t, label, start, goals, kit, fl, max(steps // 4, 20_000), wall_cap,
                                                 jobs, xbe, True, seeds, pool)
                        except l3.L3Error as ex:
                            again = {"reached": False, "why": f"the start doesn't run in whole steps: {ex}"}
                        rung["scene_retry"] = {k: v for k, v in again.items() if k != "legs"}
                        if again["reached"]:
                            rung, chk = again, _check_rung(t, label, start, goals, again, xbe)
                    rung.update({k: v for k, v in chk.items() if k not in ("v", "sv")})
                    if chk["verified"] and chk["scene_ok"] is True:
                        v = chk["sv"]
                        rung.update(ticks=len(v["rows"]), outcome=_outcome(v["rows"], _router(lvl)),
                                    segments=segments(v["pads"], v["rows"]),
                                    most_flaps=max(flaps_of(r) for r in v["rows"]),
                                    robustness=min(x["robustness"] for x in rung["legs"]))
                        strings.append([tuple(x) for x in rung["legs"][0]["segs"]])
                        if i == 0:
                            top = rung
                        else:
                            best = rung
                out["rungs"].append({k: v for k, v in rung.items() if k not in ("segments",)})
                print(key, f"rung air {air} flaps {fl}:", json.dumps({k: rung.get(k) for k in (
                    "reached", "why", "taint", "mode", "verified", "scene_ok", "most_flaps", "robustness", "seconds")}),
                      flush=True)
                if best is not None:
                    break
        finally:
            pool.close()
        win = best or top
        if win is not None:
            out.update(reached=True, verified=True, kit=win["kit"], air=win["air"], flaps=win["flaps"],
                       most_flaps=win["most_flaps"], robustness=win["robustness"], tier=tier(win["robustness"]),
                       legs=win["legs"], ticks=win["ticks"], outcome=win["outcome"], segments=win["segments"],
                       mode=win["mode"], scene_ok=win["scene_ok"])
        else:
            out["why"] = next((r.get("why") or f"verified {r.get('verified')}, whole steps {r.get('scene_ok')}"
                               for r in out["rungs"]), "no rung searched")
        _write_priv(d, key, {"start": start, "targets": goals})
        results[key] = out
        _write(rpath, results)
        print(key, json.dumps({k: out.get(k) for k in ("reached", "why", "air", "most_flaps", "robustness", "tier")}),
              flush=True)


# -- 5. apply --------------------------------------------------------------------------------------------------------

def _record(sitting: str, t: dict, snap: dict, res: dict, rep: dict, priv: dict) -> dict:
    """A proof record (``proofs.record_problem``) for a proven target: coordinate-free.  A spot's ``returned``
    holds only when its string started in its arrival node (``priv``'s start zone, :func:`_start`), whose zones its
    way back ends in; a start kept without its zone says nothing, so it doesn't hold.  Its kit is the one the string
    ran with (:func:`run_kit`)."""
    st, kit = priv["start"], run_kit(t, res)
    hop_ = snap.get("hop") or t.get("hop")
    setup = [["loadvm", snap.get("loadvm", START_TAG)], *([["R7", *hop_]] if hop_ else []), ["R2", snap["kit"]]]
    if st["teleport"] is not None:
        tp = st["teleport"]
        setup.append(["R6", {"prof": "logic", "sample": st["sample"], "yaw": round(tp[1], 6), "cell": st["cell"],
                             "place_sha12": hashlib.sha256(place_bytes(tp[0], tp[1], st["cell"])).hexdigest()[:12]}])
    setup.append(["settle", SETTLE])
    if t.get("kit_l3") or "kit" in res:     # the kit set in L3 and by the replay's own writes (R2), with air cast
        setup += [["R2", kit]] + ([["cast", "LT+Y"]] if kit.get("air") else [])
    claim = {"kind": "location", "level": t["level"], "id": t["id"]} if t["kind"] == "spot" else \
        {"kind": "edge", "level": t["level"], "from": t["start"], "to": t["goal"][0]}
    claim.update(kit=kit, zoning=pr.zoning(read_derived(t["level"])))
    return {"format": pr.FORMAT, "ref": pr.ref_of(sitting, rep["sha12"], rep["meta_sha12"]), "claim": claim,
            "start": {"snapshot": {"label": rep["label"], "meta_sha12": rep["meta_sha12"],
                                   "pages_sha12": rep["pages_sha12"], "at": "scene", "level": snap["level"],
                                   "tag": snap["tag"], "xemu": snap["xemu"], "iso_sha12": snap["iso_sha12"]},
                      "setup": setup, "observed": {"hp": snap["hp"]}},
            "string": {"sha12": rep["sha12"], "ticks": rep["ticks"], "input": "analog-ram",
                       "segments": res["segments"],
                       "legs": [{"goal": x["goal"], "ticks": x["ticks"], "robustness": x["robustness"],
                                 "prof": x["prof"], "problem": x["problem"], "winner_index": x["winner_index"]}
                                for x in res["legs"]]},
            "l3": {"mode": rep["l3_mode"], "unicorn": "2.1.4", "scene_ok": res.get("scene_ok")},
            "outcome": {"reached": True, "returned": st.get("zone") in t["back"] if t["kind"] == "spot" else None,
                        **rep["outcome"],
                        "inventory_changed": rep["inventory_changed"],
                        **({k: rep[k] for k in ("taken", "start_goal_band") if k in rep})},
            "replay": {"sitting": sitting, "ticks": rep["ticks"], "equal": True, "max_err_m": rep["max_err_m"],
                       "next": rep.get("next", {}).get("meta_sha12")}}


def run_kit(t: dict, res: dict) -> dict:
    """The element levels a target's string ran with: its search result's (set in L3: a ``plan --spots`` spot's, or
    with a douse's destroy requirement added, Step R1.29e), else the target's (the snapshot's)."""
    return res["kit"] if "kit" in res else t["kit"]


def _mark_location(text: str, loc: str, mark: str, note: str) -> str | None:
    """An authoring file's text with ``mark`` (a proven line) in ``loc``'s ``[[location]]`` after its id and
    ``note`` added to its note (Step R1.29: a conservative-kit spot keeps its requires); None when the block has
    a proven mark already."""
    lines = text.split("\n")
    i = lines.index(f'id = "{loc}"')
    end = next((j for j in range(i + 1, len(lines)) if not lines[j].strip() or lines[j].startswith("[")), len(lines))
    if any(x.startswith("proven = ") for x in lines[i + 1:end]):
        return None
    n = next((j for j in range(i + 1, end) if lines[j].startswith('note = "') and lines[j].endswith('"')), None)
    if n is None:
        lines.insert(end, f'note = "{note}"')
    else:
        lines[n] = f'{lines[n][:-1]}. {note[0].upper()}{note[1:]}"'
    lines.insert(i + 1, mark)
    return "\n".join(lines)


def apply(d: Path, sitting: str) -> list[str]:
    doc = _read(d / "targets.json")
    targets, step = {t["key"]: t for t in doc["targets"]}, doc.get("step", "X.7")
    snaps, results, reps = _read(d / "snapshots.json"), _read(d / "results.json"), _read(d / "replays.json")
    records, problems = pr.read_proofs(PROOFS)
    if problems:
        raise SystemExit(f"{PROOFS}: {problems}")
    done = []
    for key, rep in sorted(reps.items()):
        if not rep.get("proven") or targets[key].get("tour"):      # R1.16's tour targets: the folder is the record
            continue
        t, res = targets[key], results[key]
        snap, kit = snaps[_group(t)], run_kit(t, res)
        priv = _read_priv(d, key)
        rec = _record(sitting, t, snap, res, rep, priv)
        if why := pr.record_problem(rec):
            raise SystemExit(f"{key}: the record is malformed: {why}")
        ref = rec["ref"]
        if t.get("no_apply"):                 # a contact case between zones the authoring keeps in no node: the record
            records.setdefault(ref, rec)      # is evidence, but no walk upgrades an edge
            done.append(f"{key} (record only)")
            continue
        rob = min(x["robustness"] for x in res["legs"])
        path = AUTHORING / f"{t['level']}.toml"
        text = path.read_text(encoding="utf-8")
        if ref in text:
            continue
        how = (f"Step {step}: an L3 input string of {rep['ticks']} ticks (robustness {rob:.2f} under jitter) from "
               f"{priv['start'].get('zone') or t['start']} ({res['start']}; placed: R7 hop, R2 kit "
               f"{kit_label(kit)})")
        if t["kind"] == "spot":
            note = f"{how} touches it and comes back; xemu replayed it tick for tick (sitting {sitting})"
            if rep.get("taken"):
                note += f", taking its item ({', '.join(rep['taken'])}; start {rep.get('start_goal_band')} away)"
            mark = f'proven = {{ by = "l3", ref = "{ref}" }}'
            if f'id = "{t["id"]}"' in text:
                text = _mark_location(text, t["id"], mark, note)
                if text is None:
                    print(f"{key}: {path.name}'s [[location]] for {t['id']} has a proven mark already")
                    continue
            else:
                text += f'\n[[location]]\nid = "{t["id"]}"\n{mark}\nnote = "{note}"\n'
        else:
            note = f"{how} reaches {t['to']}; xemu replayed it tick for tick (sitting {sitting})"
            need = " & ".join(f"{k}>={v}" for k, v in sorted(kit.items()) if v) or "true"
            text += (f'\n[[probed]]\nfrom = "{t["start"]}"\nto = "{t["goal"][0]}"\nkit = "{need}"\n'
                     f'proven = {{ by = "l3", ref = "{ref}" }}\nnote = "{note}"\n')
        records[ref] = rec
        path.write_text(text, encoding="utf-8")
        done.append(key)
    pr.write_proofs(PROOFS, records)
    return done


def apply_skips(d: Path, sitting: str, unreplayed: bool = False, only=(), zoning: str | None = None) -> list[str]:
    """A proof record per skip whose winner xemu replayed tick for tick (D177): the claim names the skip, its kit
    (the rung's) and the most flaps it made in one jump (D183); ``tricks.toml`` then points ``confirmed`` at it.
    ``unreplayed`` (D277, Step R1.31: a skip the simulator did with the kit it encodes is confirmed, no xemu replay
    owed): a record per winner that held in whole steps, with no replay (``replay.rule`` D277) and the claim's
    ``zoning`` the reach model's the search ran on (``zoning``; default the level's current one, as for a replay)."""
    targets = {t["key"]: t for t in _read(d / "targets.json")["targets"]}
    snaps, results = _read(d / "snapshots.json"), _read(d / "results.json")
    reps = {} if unreplayed else _read(d / "replays.json")
    if unreplayed:     # what a replay would name: the string's sha12 and the snapshot it ran from
        for key, res in results.items():
            t = targets.get(key)
            if t is not None and t["kind"] == "skip" and res.get("reached") and res.get("verified") is True:
                snap = snaps[_group(t)]
                reps[key] = {"proven": True, "sha12": _string_sha12(res, _read_priv(d, key)),
                             "meta_sha12": snap["meta_sha12"], "label": snap["label"],
                             "pages_sha12": snap.get("pages_sha12"), "l3_mode": res["mode"], "ticks": res["ticks"],
                             "outcome": res["outcome"], "inventory_changed": None, "max_err_m": None}
    records, problems = pr.read_proofs(PROOFS)
    if problems:
        raise SystemExit(f"{PROOFS}: {problems}")
    done = []
    for key, rep in sorted(reps.items()):
        t = targets.get(key)
        if t is None or t["kind"] != "skip" or not rep.get("proven") or (only and t["id"] not in only):
            continue
        res, priv = results[key], _read_priv(d, key)
        if _string_sha12(res, priv) != rep["sha12"]:
            raise SystemExit(f"{key}: the search's string isn't the one xemu replayed (search again, or replay it)")
        rec = _record(sitting, {**t, "kind": "edge", "start": t["start"] or "", "goal": [""]}, snaps[_group(t)],
                      res, rep, priv)
        rec["claim"] = {"kind": "skip", "level": t["level"], "id": t["id"], "kit": res["kit"],
                        "flaps": rep.get("most_flaps", res["most_flaps"]),
                        "zoning": zoning or pr.zoning(read_derived(t["level"]))}   # its search's reach model's
        if unreplayed:
            rec["replay"] = {"rule": "D277", "equal": None, "sitting": None}
        rec["start"]["setup"].append(["R2", res["kit"]])
        if res["kit"].get("air"):
            rec["start"]["setup"].append(["cast", "LT+Y"])
        rec["outcome"]["returned"] = True if t.get("back") else None
        rec["outcome"]["hp_min"] = rep.get("hp_min", rec["outcome"].get("hp_min"))
        rec["string"]["robustness"] = res["robustness"]
        if rep.get("pickup_at") is not None:     # equal on every tick before xemu took the pickup, the goal
            rec["replay"].update(pickup_at=rep["pickup_at"], max_err_m=0.0)
        if why := pr.record_problem(rec):
            raise SystemExit(f"{key}: the record is malformed: {why}")
        records[rec["ref"]] = rec
        done.append(f"{t['id']} {rec['ref']} air {res['kit'].get('air', 0)} flaps {rec['claim']['flaps']} "
                    f"robustness {res['robustness']:.2f} -> {tier(res['robustness'])}")
    pr.write_proofs(PROOFS, records)
    return done


# -- 6. recheck -------------------------------------------------------------------------------------------------------

def recheck(levels=(), write: bool = False) -> list[dict]:
    """Re-run every record's string in L3 from its kept snapshot and re-zone its claim under the current derive:
    per record, the old and new from/to zones (an edge), whether the string still reaches, and the stamps.  With
    ``write``, the records and the authoring's ``[[probed]]`` walks get the new zones and stamp."""
    from devkit.sim.ports import vanilla_iso
    from devkit.sim.ports import read_file
    records, problems = pr.read_proofs(PROOFS)
    if problems:
        raise SystemExit(f"{PROOFS}: {problems}")
    xbe = read_file(str(vanilla_iso()), "default.xbe")
    out = []
    for ref, rec in sorted(records.items()):
        c = rec["claim"]
        lvl = c["level"]
        if levels and lvl not in levels:
            continue
        stamp = pr.zoning(read_derived(lvl))
        router = _router(lvl)       # the reach model of the current zoning
        snap = l3.read_snapshot(l3.snapshot_path(rec["start"]["snapshot"]["label"]))
        sim = l3.L3(snap, xbe, scene=rec["l3"]["mode"] == "scene")
        teleport = None
        for step in rec["start"]["setup"]:
            if step[0] == "R6":
                teleport = _teleport(lvl, step[1])
                if teleport is None:
                    raise SystemExit(f"{ref}: no kept reach model's sample is the record's teleport")
        rows = []
        if teleport is not None:
            rows.append(sim.teleport(teleport[0], teleport[1], cell=teleport[2]))
        rows += sim.run([Pad()] * SETTLE)
        string = l3.pads(rec["string"]["segments"])[len(rows):]
        rows += sim.run(string)
        oc = _outcome(rows, router)
        row = {"ref": ref, "level": lvl, "kind": c["kind"], "zoning_current": c["zoning"] == stamp,
               "zones_old": [c.get("from"), c.get("to")] if c["kind"] == "edge" else None,
               "zones_new": [oc["zones"][0] if oc["zones"] else None, oc["zones"][-1] if oc["zones"] else None],
               "same_states": oc["states"] == rec["outcome"]["states"], "hp_min": oc["hp_min"]}
        if write and (c["kind"] == "edge" and row["zones_new"] != row["zones_old"] or not row["zoning_current"]):
            path = AUTHORING / f"{lvl}.toml"
            text = path.read_text(encoding="utf-8")
            if c["kind"] == "edge":
                old_from, old_to = c["from"], c["to"]
                c["from"], c["to"] = row["zones_new"]
                text = text.replace(f'from = "{old_from}"\nto = "{old_to}"\nkit = ', f'from = "{c["from"]}"\nto = "{c["to"]}"\nkit = ')
            c["zoning"] = stamp
            rec["outcome"].update(zones=oc["zones"])
            path.write_text(text, encoding="utf-8")
            row["rewritten"] = True
        out.append(row)
        print(json.dumps(row), flush=True)
    if write:
        pr.write_proofs(PROOFS, records)
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--impact", type=Path, nargs="+")
    p.add_argument("--tour", type=Path, help="R1.16's progress.json: its certify list as the targets")
    p.add_argument("--spots", nargs="+", default=(), help="location ids (Step R1.29): each from the arrival whose "
                   "way there and back asks the least element levels, that kit set in L3")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--top", type=int, default=10)
    p = sub.add_parser("sitting")
    p.add_argument("dir", type=Path)
    p.add_argument("w")
    p.add_argument("what", choices=("snapshots", "replays"))
    p.add_argument("--only", nargs="*", default=())
    p.add_argument("--no-chain", action="store_true", help="no snapshot where a proven replay halts")
    p = sub.add_parser("adopt", help="each group's newest earlier snapshot from the store (no sitting)")
    p.add_argument("dir", type=Path)
    p = sub.add_parser("search")
    p.add_argument("dir", type=Path)
    p.add_argument("--jobs", type=int, default=8, help="seeds per leg")
    p.add_argument("--workers", type=int, default=None, help="pool processes (default: the cores, at most 16)")
    p.add_argument("--steps", type=int, default=400_000, help="each seed's step budget per leg (emulated ticks)")
    p.add_argument("--wall-cap", type=float, default=None, help="a safety net in seconds (never a verdict; default: "
                   "--steps at 4 a second, l3_search.WALL_RATE, so a slow scene runs its steps)")
    p.add_argument("--only", nargs="*", default=())
    p.add_argument("--scene", action="store_true", help="whole steps: rigs, bridges, enemies and pickups move")
    p.add_argument("--redo", action="store_true", help="search a target again even when results.json has it")
    p.add_argument("--dive", type=float, default=0.0, help="the share of segments in the water that dive (BLACK "
                   "held), a spot's depth under a swimming row counting in its cost (Step R1.29)")
    p.add_argument("--touch", type=float, default=0.75, help="a spot's goal reach around its point in m when its "
                   "item's species has no touch (Step R1.29; the whole-step check says whether the game took it)")
    p.add_argument("--placed", action="store_true", help="a spot starts by R6 on its start zone's sample nearest "
                   f"the goal at least {PLACED_OFF_M} m off it, not at the hop's arrival (Step R1.29)")
    p.add_argument("--douse", action="store_true", help="with --scene: a leg (the way there or back) through a "
                   "barrier (a level edge's through) searched to it, crossed by sim.douse, then on to its goal "
                   "(Step R1.29e)")
    p.add_argument("--plateau", type=int, default=None, help="a seed ends after this many steps with no new best "
                   "cost to go, naming the edge ahead (default: never; Step X.52)")
    p = sub.add_parser("apply")
    p.add_argument("dir", type=Path)
    p.add_argument("--sitting", required=True)
    p = sub.add_parser("plan-skips")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--only", nargs="*", default=())
    p = sub.add_parser("search-skips")
    p.add_argument("dir", type=Path)
    p.add_argument("--jobs", type=int, default=6)
    p.add_argument("--steps", type=int, default=150_000, help="each seed's step budget per leg and rung")
    p.add_argument("--wall-cap", type=float, default=None)
    p.add_argument("--only", nargs="*", default=())
    p.add_argument("--redo", action="store_true")
    p.add_argument("--results", default="results.json", help="the results file in DIR (one per parallel search)")
    p = sub.add_parser("apply-skips")
    p.add_argument("dir", type=Path)
    p.add_argument("--sitting", required=True)
    p.add_argument("--unreplayed", action="store_true", help="D277: a record per winner that held in whole steps, "
                   "with no xemu replay (the simulator's run confirms a skip)")
    p.add_argument("--only", nargs="*", default=(), help="these skip ids only")
    p.add_argument("--zoning", help="the claim's zoning: the sha256 the search's reach model was made under "
                   "(default: the level's current one)")
    p = sub.add_parser("recheck")
    p.add_argument("--level", nargs="*", default=())
    p.add_argument("--write", action="store_true")
    p = sub.add_parser("pickups", help="every recorded pickup proof judged again under the fixed rule (AZ-389)")
    p.add_argument("dir", type=Path)
    p.add_argument("--out", type=Path, help="also write the result here (JSON; never into DIR)")
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        if bool(a.impact or a.spots) == bool(a.tour):
            raise SystemExit("plan takes --impact or --spots, or --tour")
        for t in plan_tour(a.tour, a.out) if a.tour else plan(a.impact or [], a.out, a.top, a.spots):
            print(t["key"], t.get("skip") or f"from {t['start']} kit {kit_label(t['kit'])} hop {t['hop'][1]}")
    elif a.cmd == "sitting":
        from devkit.xemu import oracle as xo
        sb = xo.Sandbox.attach(a.w, wait_s=14400)
        if a.what == "snapshots":
            sitting_snapshots(a.dir, sb, xo)
        else:
            sitting_replays(a.dir, sb, xo, set(a.only), chain=not a.no_chain)
    elif a.cmd == "adopt":
        for g, snap in sorted(adopt(a.dir).items()):
            print(g, snap.get("label"), "format", snap.get("format"), snap.get("xemu"), snap.get("meta_sha12"))
    elif a.cmd == "search":
        if a.douse and not a.scene:
            raise SystemExit("--douse needs --scene: only whole steps run a barrier's graph")
        search_all(a.dir, a.jobs, a.steps, a.wall_cap, set(a.only), scene=a.scene, redo=a.redo,
                   workers=a.workers, dive=a.dive, placed=a.placed, touch=a.touch, douse=a.douse, plateau=a.plateau)
    elif a.cmd == "apply":
        print("\n".join(apply(a.dir, a.sitting)) or "nothing proven")
    elif a.cmd == "plan-skips":
        for t in plan_skips(a.out, set(a.only)):
            print(t["key"], t["level"], t["start"], "->", t["goal"], "hop", t["hop"], "loadvm", t.get("loadvm"))
    elif a.cmd == "search-skips":
        search_skips(a.dir, a.jobs, a.steps, a.wall_cap, set(a.only), redo=a.redo, out_name=a.results)
    elif a.cmd == "apply-skips":
        print("\n".join(apply_skips(a.dir, a.sitting, a.unreplayed, set(a.only), a.zoning)) or "nothing proven")
    elif a.cmd == "pickups":
        if a.out and a.dir.resolve() in a.out.resolve().parents:
            raise SystemExit("--out goes outside DIR: pickups only reads the folder")
        doc = recheck_pickups(a.dir)
        if a.out:
            _write(a.out, doc)
        print(json.dumps({k: v for k, v in doc.items() if k != "pickups"}))
    else:
        recheck(a.level, a.write)


if __name__ == "__main__":
    main()
