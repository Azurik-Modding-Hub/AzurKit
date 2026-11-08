"""The reach engine's verdicts and its recall report (Step R2.16a; the R2.16 design §1, §2f, §2g).

Every derived zone edge, hand edge and level row checked gets one verdict at the launch set R0:

- ``FOUND``: an engine witness settles in its to-zone from its from-zone (a level row or a hand edge: the engine's
  zone edges, closed, with the derive's own non-flight edges at that kit, reach a to-zone from a from-zone);
  a zone edge FOUND only above its kit's air rank says so (``rank``);
- ``DATA`` (a level row or a hand edge): the derive's own non-flight edges reach it alone, so no engine edge backs
  it or is needed;
- ``MAY``: attempted (the run launched from its from-zone; a row's: from a zone its from-zones reach) and not
  found: queued for a finer resolution; ``why`` says whether the derive put the flight there (any derived
  flight's confidence; for a row, the derive's whole zone graph at its terms reaches it) or not even that, and
  a derived flight's ``fault`` is ``landing`` when the engine's face list holds no to-zone floor near its aim's
  landing (``Graph.fault``: a flag, since that list misses floors L3 stands on);
- ``NO``: outside the [phys] envelope (the design's; never given at R0, which has no envelope check: the derive's
  graph holds no hand edge, so a way it misses isn't refuted);
- ``N/A``: not attempted: no launch from its from-zone in this run, an unfound derived flight whose aims' starts
  all fell in L3, the ring of starts 0.25 m around too (``Graph.fault``, AZ-723: ``fault`` holds ``takeoff``; the
  engine's start search reads a face list that misses floors L3 stands on, so it is no proof the floor isn't
  there; it counts as attempted, and the refinement still tries it), or a requirement no kit branch stands for
  (``false``; water, fire or earth levels, an event, a flag or a skip with no witness; for a row or a hand edge, a
  term asking for more than air, an element level, a button or discs, that R0 doesn't find: its branches hold none
  of them); ``derive`` says whether the derive's graph reaches it.  A hand edge is FOUND or N/A (the design §8):
  one R0 tried and didn't find is N/A with its ``why`` (its move may be outside R0).

A derived flight with no pure-air term (water, fire or earth levels, an event or a flag beside its air: Step
R2.16d's grading) is FOUND by a witness at its terms' air, which ran without the rest (more kit or a world flag only
adds ways: w1's 31 such witnesses all land the same when replayed with their term's elements set), its ``extra``
naming them.  A row the derive itself got wrong carries ``derive``: ``requires false`` (with the engine's witness
rank in ``refuted`` when it has one), a phantom landing (N/A: no aim stood a body in L3 in its to-zone within
2.5 m of its target, ``Graph.floor``, and no launch of the run lands in that zone) or a phantom takeoff (N/A: no
start of its aims stood and L3 stands no body in its from-zone within 2.5 m of its takeoff, ``Graph.from_floor``,
``aim.other_starts``); the report's ``graded`` recall
leaves those rows out of its denominator, beside the bar's ``recall`` over every row.

The derive's non-flight edges it closes over (:data:`GIVEN`): geometry and data edges (swims, drops and steps by
geometry, gates, teleports) and modelled pushes, slides and walks; its flights (jumps, flaps, modelled and
probe-needed drops and steps) come from the engine.  A found witness is the evidence (D277; D661: no jitter
replays, no may/must split).  :func:`witness` writes an edge's witness as a ``proofs.jsonl`` ``azurik-l3-proof/1``
record (claim kind ``edge``, no coordinate) whose xemu replay is owed (R2.16c: ``replay`` holds ``owed``);
:func:`report` is the recall report.  Pure.
"""

from __future__ import annotations

import collections

from devkit.rando.draft.author import dnf, implies
from devkit.reach.engine.graph import closure
from devkit.reach.engine.macros import KITS
from devkit.reach.engine.runner import CAST, SETTLE_START

FOUND, DATA, MAY, NO, NA = "FOUND", "DATA", "MAY", "NO", "N/A"
ORDER = {FOUND: 0, DATA: 1, MAY: 2, NO: 3, NA: 4}
WORLD = ("skip", "event", "flag")        # atoms the snapshot's frozen world and M0 stand for in no branch
FLIGHTS = ("jump", "flap", "drop", "step")
GIVEN = {("geometry", None), ("data", None), ("modelled", "push"), ("modelled", "slide"), ("modelled", "walk")}
SITTING = "r2.16d"                       # a witness record's ref prefix: the step that ran it
FAULTS = {"landing": "no floor of its to-zone near its aim's landing (L3's within 2.5 m, else the face list's)",
          "takeoff": "no start of its aims stood in L3, nor one 0.25 m around"}
PHANTOM = "no L3 floor of its to-zone within 2.5 m of its landing, and no launch lands in its to-zone"
PHANTOM_TAKEOFF = "no start of its aims stood, and L3 stands no body in its from-zone within 2.5 m of its takeoff"


def pure_air(term: frozenset) -> int | None:
    """A term's air level when air is all it asks (0 for none), else None."""
    if any(a[0] != "air" for a in term):
        return None
    return max((a[1] for a in term), default=0)


def _given(e: dict) -> bool:
    if e["kind"] in FLIGHTS and e.get("confidence") != "geometry":
        return False
    return (e.get("confidence"), None) in GIVEN or (e.get("confidence"), e["kind"]) in GIVEN


def _derived_adj(derived: dict, term: frozenset, pick) -> dict:
    adj: dict[str, set] = collections.defaultdict(set)
    for e in derived.get("edges", ()):
        if e["kind"] != "skip" and pick(e) and any(implies(term, t) for t in dnf(e.get("requires", "true"))):
            adj[e["from"]].add(e["to"])
    return adj


def _union(*adjs) -> dict:
    out: dict[str, set] = collections.defaultdict(set)
    for adj in adjs:
        for a, bs in adj.items():
            out[a] |= bs
    return out


def ran_from(graph) -> set:
    """The zones the run launched from (a start that stood in each)."""
    return {z for zs in graph.start_zone.values() for z in zs if z}


def zone_edges(derived: dict, graph, kinds=("jump", "flap"), confs=("modelled",)) -> list[dict]:
    """A verdict per derived zone edge of ``kinds`` and ``confs`` (index ``i`` in the derived file's edges)."""
    out, ran, landed = [], ran_from(graph), {zb for _, zb in graph.cands}     # where a launch landed, held or not
    for i, e in enumerate(derived.get("edges", ())):
        if e["kind"] not in kinds or e.get("confidence") not in confs:
            continue
        row = {"i": i, "from": e["from"], "to": e["to"], "kind": e["kind"], "confidence": e.get("confidence"),
               "requires": e.get("requires")}
        terms = dnf(e.get("requires", "true"))
        airs = [x for t in terms if (x := pure_air(t)) is not None]
        w = graph.best((e["from"], e["to"]), 3, zones=True)
        if not terms:
            out.append(row | {"verdict": NA, "why": "requires false", "derive": "requires false"}
                       | ({"refuted": w["rank"]} if w is not None else {}))
            continue
        if not airs:
            air, t = min((max((a[1] for a in t if a[0] == "air"), default=0), sorted(t)) for t in terms)
            if w is None:
                out.append(row | {"verdict": NA, "why": f"needs {e.get('requires')}: no kit branch holds it"})
                continue
            row |= {"extra": [f"{a[0]}:{a[1]}" for a in t if a[0] != "air"]}
            airs = [air]
        row["air"] = air = min(airs)
        edge = f"{e['from']}>{e['to']}:{e['kind']}:{e.get('confidence')}"
        fault = None if w is not None else graph.fault(edge)
        if fault and "landing" in fault and edge in graph.floor and e["to"] not in landed:
            out.append(row | {"verdict": NA, "fault": fault, "why": f"the derive's flight: {PHANTOM}",
                              "derive": "no L3 floor at its landing"})
        elif fault and "takeoff" in fault and graph.from_floor.get(edge) is False:
            out.append(row | {"verdict": NA, "fault": fault, "why": f"the derive's flight: {PHANTOM_TAKEOFF}",
                              "derive": "no L3 floor at its takeoff"})
        elif fault and "takeoff" in fault:
            why = "the engine's start search (AZ-723): " + " and ".join(FAULTS[k] for k in fault.split("+"))
            out.append(row | {"verdict": NA, "fault": fault, "why": why})
        elif w is None and e["from"] not in ran:
            out.append(row | {"verdict": NA, "why": "not attempted: no launch from its from-zone"})
        elif w is None:
            out.append(row | {"verdict": MAY, "why": "the derive's flight; nothing at R0 settled there"
                              + (f" ({FAULTS[fault]})" if fault else "")} | ({"fault": fault} if fault else {}))
        else:
            out.append(row | {"verdict": FOUND, "rank": w["rank"], "over": w["rank"] > air, "witness": _wid(w)})
    return out


def _wid(w: dict) -> dict:
    return {k: w[k] for k in ("job", "id", "outcome", "macro", "string_sha12", "ticks", "rank", "flaps", "hp_lost",
                              "labels", "kit", "flags", "by", "route", "wait", "parked") if k in w} | {
        "tainted": bool(w["taint"]), "frozen": w.get("frozen"), "swim": w.get("swim")}


def reach_verdict(derived: dict, graph, sources, targets, requires: str) -> dict:
    """The verdict of a way from zones ``sources`` to zones ``targets`` under ``requires`` (a level row or a hand
    edge): per term, the derive's given edges at the term alone (DATA), else with the engine's zone edges at its
    air level (FOUND), else MAY (the derive's whole graph at the term
    reaches it, or not even that); a term with a frozen-world atom, or none launched from, N/A, as is one asking
    for more than air that isn't found.  The best term's verdict, and the term."""
    sources, targets, ran = set(sources), set(targets), ran_from(graph)
    best = None
    for t in dnf(requires or "true"):
        if (world := sorted(f"{a[0]}:{a[1]}" for a in t if a[0] in WORLD)):
            got = {"verdict": NA, "why": f"needs {', '.join(world)}: the frozen world and M0 hold none"}
        else:
            air = min(3, max((a[1] for a in t if a[0] == "air"), default=0))
            given = _union(graph.adjacency(air, zones=True), _derived_adj(derived, t, _given))
            near = closure(given, sources)
            derive = bool(closure(_union(given, _derived_adj(derived, t, lambda e: True)), sources) & targets)
            if closure(_derived_adj(derived, t, _given), sources) & targets:
                got = {"verdict": DATA, "air": air, "why": "the derive's given edges alone reach it"}
            elif near & targets:
                got = {"verdict": FOUND, "air": air}
            elif not near & ran:
                got = {"verdict": NA, "air": air, "derive": derive,
                       "why": "not attempted: no launch from a zone its from-zones reach"}
            elif derive:
                got = {"verdict": MAY, "air": air, "why": "the derive's graph reaches it; the engine's at R0 doesn't"}
            else:
                got = {"verdict": MAY, "air": air, "why": "neither the engine's nor the derive's graph reaches it "
                                                          "at R0 (no envelope check: not refuted)"}
            if got["verdict"] == MAY and (more := sorted(f"{a[0]}>={a[1]}" if isinstance(a[1], int) else
                                                         f"{a[0]}:{a[1]}" for a in t if a[0] != "air")):
                got |= {"verdict": NA, "derive": derive, "why": f"needs {', '.join(more)}: no R0 kit branch holds "
                                                                f"it ({got['why']})"}
        if best is None or ORDER[got["verdict"]] < ORDER[best["verdict"]]:
            best = got | {"term": " & ".join(sorted(f"{a[0]}>={a[1]}" if isinstance(a[1], int) else f"{a[0]}:{a[1]}"
                                                    for a in t)) or "true"}
    return best or {"verdict": NA, "why": "requires false"}


def rows(derived: dict, level_doc: dict, graph, confs=("assumed",)) -> list[dict]:
    """A verdict per level row (``levels/<level>.toml``'s ``[[edge]]``) of ``confs``: its from-node's zones (the
    node's ``zone:`` anchors) to its to-node's."""
    zones = {n["id"]: [a[5:] for a in n.get("anchors", ()) if a.startswith("zone:")] for n in level_doc.get("node", ())}
    out = []
    for k, e in enumerate(level_doc.get("edge", ())):
        if e.get("confidence") in confs:
            out.append({"row": k, "from": e["from"], "to": e["to"], "requires": e.get("requires"),
                        "confidence": e.get("confidence"),
                        **reach_verdict(derived, graph, zones.get(e["from"], ()), zones.get(e["to"], ()),
                                        e.get("requires"))})
    return out


def _hand_fix(v: dict) -> dict:
    if v["verdict"] == MAY:
        v |= {"verdict": NA, "why": f"tried, not found at R0 (a hand edge's move may be outside it): {v['why']}"}
    return v


def hand(derived: dict, spec: dict, graph) -> list[dict]:
    """A verdict per hand ``[[edge]]`` of the level's authoring (zone to zone): FOUND or N/A (the module
    docstring)."""
    return [{"hand": k, "from": e["from"], "to": e["to"], "requires": e.get("requires"),
             **_hand_fix(reach_verdict(derived, graph, [e["from"]], [e["to"]], e.get("requires")))}
            for k, e in enumerate(spec.get("edge", ()))]


def witness(level: str, w: dict, rec: dict, heading: float, snap: dict, zoning: str, ends: tuple) -> dict:
    """An engine edge's witness (``w``, from job record ``rec``; ``heading`` its job's, unless its start holds its own
    ``yaw``: an aim's turned pass) as a ``proofs.jsonl`` record:
    the claim (``ends``: its from and to zones, or node keys off every zone), the start as a recipe on the
    snapshot (``snap``: its metadata, as a record names it; a routed witness's ``wait`` idle ticks first, the
    whole-step trip's that held: ``rigs.Router.tripped``), the string, the outcome; its xemu replay owed."""
    from azurkit.tools.randomizer.planner import proofs as pr
    o = rec["outcomes"][w["outcome"]]
    st = rec["starts"][o["start"]]
    kit = KITS[o["kit"]]
    setup = [["R6", {"prof": "walk_game", "job": rec["key"], "start": o["start"],
                     "yaw": round(st.get("yaw", heading), 6), "cell": st["cell"], "place_sha12": st["place_sha12"]}],
             ["settle", SETTLE_START], ["R2", kit]]
    setup = ([["idle", w["wait"]]] if w.get("wait") else []) + setup + ([list(CAST)] if kit.get("air") else [])
    return {"format": pr.FORMAT, "ref": pr.ref_of(SITTING, o["string_sha12"], snap["meta_sha12"]),
            "claim": {"kind": "edge", "level": level, "from": ends[0], "to": ends[1], "kit": kit, "zoning": zoning,
                      "min_air": w["rank"], "flaps": o["flaps"]},
            "start": {"snapshot": {k: snap.get(k) for k in ("label", "meta_sha12", "at", "level", "tag", "xemu",
                                                             "iso_sha12")},
                      "setup": setup, "observed": {"hp": o["hp0"]}},
            "string": {"sha12": o["string_sha12"], "ticks": o["ticks"], "input": "analog-ram",
                       "segments": o["segments"]},
            "l3": {"mode": "tick", "engine": "reach_engine", "taint": o["taint"]},
            "outcome": {"reached": True, "returned": None, "end": o["end"], "hp_min": o["hp_min"],
                        "labels": o["labels"], "volumes": len(o["volumes"])},
            "replay": {"owed": "R2.16c", "equal": None}}


def report(level: str, derived: dict, level_doc: dict, spec: dict, graph) -> dict:
    """The recall report (the design §8's R2.16a check): the derived modelled jump and flap zone edges' verdicts
    (``recall``, the bar's: FOUND at the edge's own kit over all of them; ``recall_attempted`` the same over those
    attempted, a slice's; ``recall_any_rank`` counting finds above the edge's kit too; and the same over the edges
    an aim ran at, modelled and probe-needed, the targeted pass's), the probe-needed
    ones' (the engine backing the derive's "a curved path may pass"), every hand edge's and every assumed and
    physics row's, the engine's zone edges the derive has no edge for (AZ-626's kind), the closure per kit and the
    graph's counts.  Ids and counts only."""
    def tally(xs):
        return dict(collections.Counter(x["verdict"] for x in xs))

    def share(n, d):
        return round(n / len(d), 4) if d else None
    mod = zone_edges(derived, graph)
    probe = zone_edges(derived, graph, confs=("probe-needed",))
    tried = [x for x in mod if x["verdict"] != NA or x.get("fault")]       # a takeoff fault's aims did run
    at_kit = [x for x in tried if x["verdict"] == FOUND and not x["over"]]
    graded = [x for x in mod if not x.get("derive")]
    anyk = [x for x in tried if x["verdict"] == FOUND]
    aimed = [x for x in mod + probe if f"{x['from']}>{x['to']}:{x['kind']}:{x['confidence']}" in graph.aimed]
    have = {(e["from"], e["to"]) for e in derived.get("edges", ())}
    news = [pair for pair in graph.zones if pair not in have]
    new = sorted(f"{a}>{b}@{min(graph.zones[(a, b)])}" for a, b in news)
    flags = collections.Counter(f for pair in news for f in graph.best(pair, zones=True)["flags"])
    out = {"level": level, "launch_set": "R0",
           "modelled": {"edges": len(mod), "attempted": len(tried), "verdicts": tally(mod),
                        "floor_faults": dict(collections.Counter(x["fault"] for x in mod if x.get("fault"))),
                        "found_at_kit": len(at_kit), "found_any_rank": len(anyk),
                        "recall": share(len(at_kit), mod), "recall_attempted": share(len(at_kit), tried),
                        "recall_any_rank": share(len(anyk), mod), "bar": 0.85,
                        "bar_met": bool(mod) and len(at_kit) / len(mod) >= 0.85,
                        "graded": {"edges": len(graded), "recall": share(sum(x["verdict"] == FOUND and not x["over"]
                                                                      for x in graded), graded),
                                   "out": dict(collections.Counter(x["derive"] for x in mod if x.get("derive")))},
                        "derive": {"refuted": sorted(f"{x['from']}>{x['to']}@{x['refuted']}" for x in mod
                                                     if "refuted" in x),
                                   "found_above_kit": sum(x["verdict"] == FOUND and x["over"] for x in mod)}},
           "run_zones": len(ran_from(graph)),
           "aimed": {"edges": len(aimed), "verdicts": tally(aimed),
                     "recall": share(sum(x["verdict"] == FOUND and not x["over"] for x in aimed), aimed),
                     "recall_any_rank": share(sum(x["verdict"] == FOUND for x in aimed), aimed)},
           "probe_needed": {"edges": len(probe), "verdicts": tally(probe)},
           "hand": hand(derived, spec, graph), "assumed": rows(derived, level_doc, graph),
           "physics": rows(derived, level_doc, graph, ("physics",)),
           "engine_only": {"zone_edges": len(new), "first": new[:50], "flags": dict(flags),
                           "clean": sum(not graph.best(pair, zones=True)["flags"] for pair in news)},
           "closure": graph.kits(), "counts": dict(graph.counts), "touches": len(graph.touch), "may_first_contact":
               len(graph.may)}
    for k in ("hand", "assumed", "physics"):
        out[f"{k}_verdicts"] = tally(out[k])
    return out
