"""Run the exhaustive reach engine (Step R2.16a, ``devkit.reach.engine``) on one level, in shadow: launches
from every walkable region's boundary on simulator Level 3, their edges, closure and verdicts, checked against the
level's derived modelled jump and flap zone edges, hand edges and assumed rows.

``sample`` writes a plan (the jobs: R0's fan of every takeoff at 3 headings and 14 launches, and with
``--targeted`` the targeted pass's aims at each derived jump and flap zone edge's witness flight, steered by the
predictive landing control at its landing on its floor face; and the sha12 of the volumes and pickups its touches
are judged against, a file beside it, part of each job's key) to the private cache; ``--spacing`` and
``--min-area`` set the takeoffs' (2 m, 4 m2: the design's R0), ``--region`` keeps the takeoffs of those walkable
regions only (a slice), ``--limit`` the first N jobs.  With ``--refine PLAN ... --snapshot LABEL`` it samples the
refinement instead (Step R2.16b, ``aim.refine_jobs``): on the derived jump and flap zone edges those plans' run
left MAY, unattempted or found only above their kit (their aims' envelope pass left out: ``aim.unscheduled``),
every R0 launch, the roll jumps and a recast at each one's
target (none its aim twin in those plans ran, and from the twin's floor and start answers: ``aim.twinned``), and R0's
fan and the roll jumps from the walkable regions under ``--min-area`` in their from-zones.
``run`` runs the plans' jobs the cache doesn't hold yet on an L3 worker pool on ``--snapshot`` (a label in
``--store``, by default the L3 store's ``reach-live`` folder of per-level start snapshots; each job's record
written as it finishes, so a stopped run resumes; a job that raises is counted in ``errors`` and tried again next
run, as is one with a step L3's watchdog stopped for time, ``reach_engine.worker``: the host's load, never the game's
fault), and ``graph``, ``diff`` and ``witness`` write the public results (each over every plan its ``--plan`` names, so
a refinement's plan adds to its run's): the engine's zone edges and its closure per kit, the recall report
(``reach_engine.verdict.report``) and the FOUND edges' witnesses as ``azurik-l3-proof/1`` edge records (replay
owed).  Each, and ``sample --refine``, first holds every zone witness (Step R2.16d, ``reach_engine.hold``): the
witnesses whose answer the cache doesn't hold yet are replayed on a pool of ``--workers`` (a zone edge keeps its
best witness a rank whose body stays in its to-zone 60 idle ticks on).  A found witness is the evidence (D277;
D661: no jitter replays).  Shadow only (the plan freeze holds until R1.17): nothing here writes
``src/azurkit/tools/randomizer/data``.  A CPU-heavy batch job: run ``run`` under
``nice -n 19`` with at most the workers the machine can spare; the pool gives way to a waiting xemu sitting
(``xemu_queue.BatchToken``).  ``--l3 fast`` (the default, Step R2.19a) runs every pool's player ticks on FastL3
(``sim.l3_fast``: on the patched libunicorn once ``devkit/reach/unicorn/build_unicorn.py`` has built it, else on the stock wheel)
with the aimed jobs' lossless tick cuts (``reach_engine.fast``); ``--l3 base`` runs round 1's L3 on the stock wheel.
On Step R2.19a's bench both gave the same records byte for byte, so a record is reused whichever ran it.  An
unmapped write below L3's high pages names a different fault site, never a different find; a fetch from a data page
faults in FastL3 alone (``sim.l3_fast``): a lost find, never a false one (neither happened on the bench).  Each
record names what ran it (``l3_impl``, Step R2.19b), and a fast ``run`` ends with its audits (``reach_engine.worker``:
about 1 job in 500 again on base L3, 1 in 1,000 with the patched library's x87 check), stopping with exit 1 if any
record or x87 result differs.

``--backend kernel`` (Step R2.19d, ``devkit.reach.native.backend``) runs each job's starts, kits, aligns and
launches on the native kernel under the same controllers, an aim's floor scans and every launch the kernel flags on
FastL3; a kernel outcome is a candidate FastL3 confirms before it counts (an aim's hit as it is found, any other zone
witness at the hold: from a start L3 stands, its string run again from the snapshot, the outcome re-derived from
L3's rows).  Its records are keyed apart
(the kernel's code, the compiler, and the snapshot's platform census, made once per snapshot into the level's cache
folder); a plan named ``NAME@l3`` or ``NAME@kernel`` runs on that backend whatever ``--backend`` says, so one graph
reads both.  A kernel ``run`` reports its launches' flags and its drift audit (about 1 job in 100: each kernel launch
that settled run again on FastL3; a level stage over 2 % silent drift is named, its plan to run with ``@l3``).
``sample --backstop modelled|all --refine PLAN ... --snapshot LABEL`` writes the FastL3 backstop (D846): the aims
and the refinement's aims at each derived jump and flap zone edge of those confidences the plans leave unfound at its
kit (every pass at a modelled edge, pass 1 at a probe-needed one: ``aim.MORE``), an L3 plan whatever ``--backend``
says.  ``sample --retarget PLAN ... --snapshot LABEL [--gate-m 3.0]`` (Step R2.19f+'s g1,
``aim.retarget``) aims at what those plans' graph left: rank 0 at a truth-frame non-derived k0 pair held only above
it, a zone rank the hold left with no witness, and a probe-needed edge unfound at its kit whose pass 1 came within
``--gate-m`` of its to-zone (with its refinement); ids ``g<class><n>``, on ``--backend``'s route.
``sample --pairs --refine PLAN ... --snapshot LABEL [--budget CPU-H] [--truth NAME ...]`` writes the pair stage
(Step R2.19g2, ``reach_engine.candidates``): a pass-1 aim (ids ``p<n>``) at each nd pair of the level's truth frame
(``devkit/reach/reach_truth.py frame``) the plans' graph holds no zone witness for at its kit, R's own aim keyed apart, in
groups of at most 32 targets of one from-zone, kit and tier, the tiers in PLAN-v3's order (nd-k0, near, far),
each group's expected links named (the tier's pass-1 hit share in R's rows frozen under ``--truth`` names whose
pair the graph lacks at its kit, else a prior) and its price (a target's by ``--backend``); the budget ends the
queue, and the plan names what it leaves by tier, those pairs too ("not searched", never unreachable: D845);
``--slice F`` keeps each nd stratum's first fraction F in the frame's order.
``sample --escalate M --refine PLAN ... --snapshot LABEL [--kit k0|air3]`` writes the escalation (Step R2.19g3,
``candidates.escalate``) at tier M metres (PLAN-v3's ladder: 1, 2, 3, 5, 10): each pair stage aim in those plans whose
pair their graph still lacks at its kit and whose pass 1 came within M of its to-zone (from its record) gets the same
aim with every pass (ids ``ea<n>``) or, once those plans hold that aim's record, the refinement twinned to the pass-1
aim (ids ``er<n>``), k0 first; the pairs that wait for a wider tier are named in the plan by kit and tier.  Run, then
sample again with the escalation's plan added, so a tier is two plans; a wider tier holds a narrower's jobs (cached).

    uv run --locked python -m devkit reach reach-engine sample LEVEL --plan NAME [--region N ...] [--targeted]
        [--no-fan] [--spacing 2.0] [--min-area 4.0] [--limit N] [--refine PLAN ... --snapshot LABEL]
        [--backstop modelled|all | --pairs [--budget CPU-H] [--slice F] [--truth NAME ...] | --escalate M [--kit K]]
        [--retarget PLAN ... --snapshot LABEL [--gate-m M]] [--backend l3|kernel]
    nice -n 19 uv run --locked python -m devkit reach reach-engine run LEVEL --plan NAME ... --snapshot LABEL
        [--workers N] [--l3 fast|base] [--backend l3|kernel]
    nice -n 19 uv run --locked python -m devkit reach reach-engine graph LEVEL --plan NAME ... --snapshot LABEL
        --out EDGES.json [--workers N]
    nice -n 19 uv run --locked python -m devkit reach reach-engine diff LEVEL --plan NAME ... --snapshot LABEL
        --out REPORT.json [--workers N]
    nice -n 19 uv run --locked python -m devkit reach reach-engine witness LEVEL --plan NAME ... --snapshot LABEL
        --out FILE.jsonl [--workers N]

Outputs (``--out``: mode 0600, never over a file there, ``l3.private_out``) hold ids, counts and string hashes;
the plans and outcomes (positions and strings) stay in the AzurKit user cache's
``reach-engine/<level>`` (mode 700).  Dev tooling: never in pytest, never a CLI verb.
"""

from __future__ import annotations

import argparse
import collections
import functools
import gzip
import json
import math
import os
import pickle
import sys
import time
import tomllib
from pathlib import Path

from devkit.reach.engine import aim, cache, hold, runner, verdict  # noqa: E402
from devkit.reach.engine.graph import Graph  # noqa: E402
from devkit.reach.engine.nodes import Nodes  # noqa: E402
from devkit.sim import l3  # noqa: E402

SNAP_KEYS = ("label", "at", "level", "tag", "xemu", "iso_sha12")   # a snapshot's metadata a record may name


def _nodes(level: str) -> Nodes:
    from devkit.reach import models
    return Nodes(models.read(models.reach_path(level)))


def _plan_path(level: str, name: str) -> Path:
    return cache.folder(level) / "plans" / f"{name}.json.gz"


LIVE = "reach-live"   # the L3 store's folder of the engine's per-level start snapshots (Step R2.16c, its README.txt)


def _store(store: str | None) -> Path:
    """The snapshot store ``--store`` names, by default the L3 store's :data:`LIVE` folder."""
    return Path(store) if store else l3.store() / LIVE


def _snap(label: str, store: str | None = None) -> dict:
    meta = l3.read_meta(l3.snapshot_path(label, _store(store)))
    return {**{k: meta.get(k) for k in SNAP_KEYS}, "label": label, "meta_sha12": l3.meta_sha12(meta),
            "store": str(_store(store))}


def _plan(level: str, plan: str, snap: dict, backend: str = "l3") -> dict:
    """The plan ``plan`` (``NAME`` on ``backend``, ``NAME@l3`` or ``NAME@kernel`` on that one; a backstop plan on
    L3's), each job keyed on ``snap`` (a kernel job by ``reach_native.backend.key``: its ``backend`` set); one
    sampled before its targets were keyed is refused."""
    name, _, on = plan.partition("@")
    doc = json.loads(gzip.decompress(_plan_path(level, name).read_bytes()))
    if f"/{level}" not in str(snap["level"]):
        raise SystemExit(f"snapshot {snap['label']} is of {snap['level']}, not {level}")
    if "touch" not in doc:
        raise SystemExit(f"plan {name} names no targets file: sample it again")
    doc["backend"] = on = doc.get("backend") or on or backend
    census = _census_of(level, snap)[1] if on == "kernel" else None
    for j in doc["jobs"]:
        j["key"] = cache.job_key(j, snap["meta_sha12"], touch=doc["touch"])
        if census is not None:
            from devkit.reach.native import backend as KB
            j["key"], j["backend"] = KB.key(j["key"], census), "kernel"
    return doc


def _plans(level: str, plans, snap: dict, backend: str = "l3") -> list[dict]:
    """The jobs of every plan in ``plans`` (:func:`_plan`), each key once."""
    out = {}
    for name in plans:
        for j in _plan(level, name, snap, backend)["jobs"]:
            out.setdefault(j["key"], j)
    return list(out.values())


_CENSUS: dict = {}


def _census_of(level: str, snap: dict) -> tuple[dict, str]:
    """The kernel's platform census of the snapshot (``reach_native.backend.census``) and its sha12, once a run."""
    from devkit.sim.ports import vanilla_iso
    from devkit.sim.ports import read_file
    from devkit.reach.native import backend as KB
    from devkit.reach.l3_pool import Worker
    if (level, snap["meta_sha12"]) in _CENSUS:
        return _CENSUS[level, snap["meta_sha12"]]

    def sim():
        return Worker(snap["label"], snap["store"], read_file(str(vanilla_iso()), "default.xbe"), None).sim(
            False, deep=False)
    _CENSUS[level, snap["meta_sha12"]] = got = KB.census(level, snap, sim)
    return got


def _kernel(level: str, snap: dict, jobs, touch: Path | None) -> dict | None:
    """The kernel workers' spec (``reach_native.backend.install``) when ``jobs`` hold a kernel job, else None."""
    if not any(j.get("backend") == "kernel" for j in jobs):
        return None
    return {"level": level, "absent": _census_of(level, snap)[0]["absent"], "touch": touch and str(touch)}


def sample(a) -> dict:
    """The plan (the module docstring), written privately; its counts."""
    from devkit.rando.draft.author import read_derived
    nodes = _nodes(a.level)
    jobs, pairs, esc = [], None, None
    if a.pairs:
        if not (a.refine and a.snapshot):
            raise SystemExit("--pairs needs --refine PLAN ... and --snapshot (the run whose graph it fills)")
        jobs, pairs = _pair_jobs(a, nodes)
    elif a.escalate is not None:
        if not (a.refine and a.snapshot):
            raise SystemExit("--escalate needs --refine PLAN ... and --snapshot (the pair stage's run and its graph)")
        jobs, esc = _escalate(a, nodes)
    elif a.backstop:
        if not (a.refine and a.snapshot):
            raise SystemExit("--backstop needs --refine PLAN ... and --snapshot (the run it backs up)")
        _, _, _, _, _, g = _graph(argparse.Namespace(level=a.level, plan=a.refine, snapshot=a.snapshot, store=a.store,
                                                     workers=a.workers, l3=a.l3, backend=a.backend), nodes)
        derived = read_derived(a.level)
        confs = ("modelled",) if a.backstop == "modelled" else ("modelled", "probe-needed")
        left = {f"{v['from']}>{v['to']}:{v['kind']}:{v['confidence']}" for c in confs
                for v in verdict.zone_edges(derived, g, confs=(c,)) if v["verdict"] != verdict.FOUND or v.get("over")}
        jobs = (aim.aim_jobs(nodes, derived, only=left)
                + aim.aim_jobs(nodes, derived, only=left, macro_set=aim.refine, prefix="r", sched=False))
    elif a.retarget:
        if not a.snapshot:
            raise SystemExit("--retarget needs --snapshot (the run whose graph it aims at)")
        jobs, why = _retarget(a, nodes)
        print(json.dumps(why), flush=True)
    elif a.refine:
        if not a.snapshot:
            raise SystemExit("--refine needs --snapshot (the run whose verdicts it refines)")
        _, _, by_key, recs, _, g = _graph(argparse.Namespace(level=a.level, plan=a.refine, snapshot=a.snapshot,
                                                             store=a.store, workers=a.workers, l3=a.l3,
                                                             backend=a.backend), nodes, aim.unscheduled)
        derived = read_derived(a.level)
        verdicts = [v for confs in (("modelled",), ("probe-needed",))
                    for v in verdict.zone_edges(derived, g, confs=confs)]
        twins = {j["id"][1:]: (j, r) for r in recs if (j := by_key[r["key"]])["id"][0] == "a"}
        jobs = aim.refine_jobs(nodes, derived, verdicts, a.min_area, set(a.region) if a.region else None, twins)
    elif not a.no_fan:
        jobs += runner.fan_jobs(nodes, nodes.takeoffs(a.spacing, a.min_area, set(a.region) if a.region else None))
    if a.targeted and not a.refine and not a.retarget:
        aims = aim.aim_jobs(nodes, read_derived(a.level))
        jobs += [j for j in aims if not a.region or j["region"] in a.region]
    jobs = jobs[:a.limit] if a.limit else jobs
    touch = nodes.targets()
    if not (tp := cache.folder(a.level) / f"targets-{cache.sha12(touch)}.json").exists():
        cache.write(tp, touch)
    cache.write(_plan_path(a.level, a.plan[0]), {"level": a.level, "spacing": a.spacing, "min_area": a.min_area,
                                                 "regions": a.region, "refine": a.refine, "touch": cache.sha12(touch),
                                                 "jobs": jobs, **({"backend": "l3", "backstop": a.backstop}
                                                                  if a.backstop else {}),
                                                 **({"pairs": pairs} if pairs else {}),
                                                 **({"escalate": esc} if esc else {})}, zipped=True)
    return {"level": a.level, "plan": a.plan[0], "jobs": len(jobs), "fan": sum(j["id"][0] in "ts" for j in jobs),
            "aims": sum(j["id"][0] in "ar" for j in jobs), "launches": sum(len(j["macros"]) for j in jobs),
            "regions": len({j["region"] for j in jobs}), "walk_regions": nodes.walk.nreg,
            **({"pairs": {k: v for k, v in pairs.items() if k != "rest"}} if pairs else {}),
            **({"escalate": {k: v for k, v in esc.items() if k != "waiting"}} if esc else {})}


def _pair_jobs(a, nodes: Nodes) -> tuple[list[dict], dict]:
    """``sample --pairs`` (the module docstring; ``reach_engine.candidates``): the pass-1 aims of the queue's groups
    the budget takes (of each nd stratum's first ``--slice`` fraction in the frame's order), each job's ``group``
    and ``tier`` beside it (no key part), and the plan's ``pairs`` record: the frame, the rates, the slice, the
    budget, what it took and left by tier (``candidates.tally``), the targets with no aim and the pairs left, by
    tier in the queue's order."""
    from devkit.rando.draft.author import read_derived
    from azurkit.tools.randomizer.planner.proofs import zoning
    from devkit.reach.engine import candidates as C
    derived = read_derived(a.level)
    if not (fp := C.frame_path(a.level, zoning(derived), C.SEED)).exists():
        raise SystemExit(f"no frame {fp.name}: run `devkit reach reach-truth frame {a.level}` first")
    fdoc = json.loads(gzip.decompress(fp.read_bytes()))
    _, _, _, _, _, g = _graph(argparse.Namespace(level=a.level, plan=a.refine, snapshot=a.snapshot, store=a.store,
                                                 workers=a.workers, l3=a.l3, backend=a.backend), nodes)
    rates = C.rates([r for name in a.truth or () for r in C.rows(a.level, name)], g.zones)
    strata = {s: v[:math.ceil(len(v) * a.slice)] if a.slice is not None else v for s, v in fdoc["strata"].items()}
    taken, left = C.queue(strata, g.zones, {t: v["rate"] for t, v in rates.items()}, C.COST_S[a.backend],
                          None if a.budget is None else a.budget * 3600)
    aims, jobs, none = C.Aims(a.level, derived, nodes), [], collections.Counter()
    for n, grp in enumerate(taken):
        for za, zb, _ in grp["targets"]:
            j, _why = aims.aim_job(f"p{len(jobs)}", za, zb, grp["kit"])
            if j is None:
                none[grp["tier"]] += 1
            else:
                jobs.append(dict(j, group=n, tier=grp["tier"]))
    rest: dict[str, list] = {}
    for grp in left:
        rest.setdefault(grp["tier"], []).extend([za, zb] for za, zb, _ in grp["targets"])
    return jobs, {"frame": fp.name, "frame_sha12": C.frame_sha(fdoc), "truth": a.truth, "rates": rates,
                  "slice": a.slice, "budget_cpu_h": a.budget, "price_s": C.COST_S[a.backend], "taken": C.tally(taken),
                  "left": C.tally(left), "no_aim": dict(none), "rest": rest}


def _escalate(a, nodes: Nodes) -> tuple[list[dict], dict]:
    """``sample --escalate`` (the module docstring; ``candidates.escalate`` on the plans' graph, its hold done): its
    jobs, and the plan's ``escalate`` record: the tier, the kits, the aims and refinements by kit, and the pairs that
    wait, by kit and the tier that would take each (``waiting``: each pair, its kit and metres)."""
    from devkit.reach.engine import candidates as C
    _, _, by_key, recs, _, g = _graph(argparse.Namespace(level=a.level, plan=a.refine, snapshot=a.snapshot,
                                                         store=a.store, workers=a.workers, l3=a.l3,
                                                         backend=a.backend), nodes)
    kits = (a.kit,) if a.kit else tuple(C.KITS)
    jobs, wait = C.escalate(by_key, {r["key"]: r for r in recs}, C._points(nodes)[1], g.zones, a.escalate, kits)

    def tier(m):
        return "no landing" if m is None else next((f"{t:g} m" for t in C.TIERS_M if m <= t), "farther")
    return jobs, {"tier_m": a.escalate, "kits": kits,
                  "jobs": dict(collections.Counter(f"{j['id'][:2]} {j['cert'][1]}" for j in jobs)),
                  "wait": dict(collections.Counter(f"{w[2]} {tier(w[3])}" for w in wait)), "waiting": wait}


def _retarget(a, nodes: Nodes) -> tuple[list[dict], dict]:
    """``sample --retarget``'s jobs (``aim.retarget`` on the plans' graph, its hold done, with the level's truth frame's
    non-derived k0 pairs when ``reach_truth.py frame`` wrote one at the derived file's zoning and its seed) and their
    counts by class."""
    from azurkit.tools.randomizer.planner.proofs import zoning
    from devkit.rando.draft.author import read_derived
    from devkit.reach.engine import candidates as C
    _, _, by_key, recs, _, g = _graph(argparse.Namespace(level=a.level, plan=a.retarget, snapshot=a.snapshot,
                                                         store=a.store, workers=a.workers, l3=a.l3,
                                                         backend=a.backend), nodes)
    derived = read_derived(a.level)
    fp = C.folder(a.level) / f"frame-{zoning(derived)[:12]}-219.json.gz"   # the truth set's folder
    frame = [tuple(p[:2]) for p in json.loads(gzip.decompress(fp.read_bytes()))["strata"]["nd-k0"]] \
        if fp.exists() else []
    verdicts = verdict.zone_edges(derived, g, confs=("probe-needed",))
    jobs = aim.retarget(nodes, derived, g, {r["key"]: r for r in recs}, by_key, frame, verdicts, a.gate_m)
    return jobs, {"retarget": dict(collections.Counter(j["id"][:2] for j in jobs)), "frame_nd_k0": len(frame),
                  "gate_m": a.gate_m}


def _zones(level: str, jobs) -> Path | None:
    """The pickled ``nodes.Zones`` the aimed jobs stop by (``aim.hit``), written once per zoning to the private
    cache; None when no job stops.  A plan sampled under another zoning is refused."""
    from devkit.rando.draft.author import read_derived
    from azurkit.tools.randomizer.planner.proofs import zoning
    from devkit.reach.engine.nodes import Zones
    if not (got := {j["stop"]["zoning"] for j in jobs if j.get("stop")}):
        return None
    if got != {now := zoning(read_derived(level))[:12]}:
        raise SystemExit("the plan's aims name another zoning than the level's derived file: sample them again")
    if not (p := cache.folder(level) / f"zones-{now}.pkl").exists():
        cache.write_bytes(p, pickle.dumps(Zones(_nodes(level)), protocol=pickle.HIGHEST_PROTOCOL))
    return p


def _pool(snap: dict, workers: int | None, mode: str = "fast", x87: str | None = None, kernel: dict | None = None):
    """The L3 worker pool on ``snap``: ``mode`` fast (the module docstring) with the patched library's switches set
    in this process's environment when it is built (every worker the pool spawns inherits them), base with them
    cleared; either way each worker's ``reach_engine.worker.setup`` (a step stopped for time is its job's error,
    each record stamped ``l3_impl``; ``x87`` a folder: the x87 check mode on, its counts written there); with
    ``kernel`` (:func:`_kernel`'s spec) the kernel route's (``reach_native.backend.setup``) instead."""
    from devkit.sim.ports import vanilla_iso
    from devkit.sim.ports import read_file
    from devkit.reach.engine import worker
    from devkit.reach import l3_fast
    from devkit.reach.l3_pool import Pool
    for k in ("LIBUNICORN_PATH", *l3_fast.SWITCHES):
        os.environ.pop(k, None)
    kw = {"setup": worker.setup}
    if mode == "fast":
        os.environ.update(l3_fast.worker_env(check=x87 is not None))
        kw = {"fast": True, "setup": functools.partial(worker.setup, True, x87)}
    if kernel is not None:
        from devkit.reach.native import backend as KB
        kw = {"fast": mode == "fast", "setup": functools.partial(KB.setup, kernel, x87, mode == "fast")}
    return Pool(snap["label"], read_file(str(vanilla_iso()), "default.xbe"), store=snap["store"], workers=workers,
                name="reach engine", **kw)


def _library(mode: str) -> str:
    """Which libunicorn a ``mode`` pool's workers run (:func:`_pool`)."""
    return "patched" if mode == "fast" and "LIBUNICORN_PATH" in os.environ else "wheel"


def run(a) -> dict:
    """Run the plan's jobs the cache doesn't hold, a few per task, every worker busy to the end, logging counts
    every few tasks."""
    snap, base = _snap(a.snapshot, a.store), cache.folder(a.level)
    docs = [_plan(a.level, name, snap) for name in a.plan]
    if len({d["touch"] for d in docs}) != 1:
        raise SystemExit("the plans judge touches against different targets: sample them again")
    jobs, touch = _plans(a.level, a.plan, snap, a.backend), base / f"targets-{docs[0]['touch']}.json"
    if not touch.exists():
        raise SystemExit(f"the plan's targets file {touch.name} is gone: sample it again")
    if len({j.get("backend", "l3") for j in jobs}) > 1:
        raise SystemExit("a run is one backend's: run the l3 and the kernel plans apart")
    todo = [j for j in jobs if not cache.path(base, j["key"]).exists()]
    zones = _zones(a.level, todo)
    kernel = _kernel(a.level, snap, jobs, touch)
    done, ticks, t0, ends, errors, ran, drift, flags = 0, 0, time.time(), {}, 0, [], {}, {}
    print(json.dumps({"jobs": len(jobs), "cached": len(jobs) - len(todo), "todo": len(todo)}), flush=True)
    with _pool(snap, a.workers, a.l3, kernel=kernel) as pool:
        per = max(1, a.per_task)
        batches = [(todo[k:k + per], str(base), str(touch), zones and str(zones)) for k in range(0, len(todo), per)]
        for n, got in enumerate(pool.completed(runner.job_task, batches), 1):
            for s in got:
                done, ticks, errors = done + 1, ticks + s["ticks"], errors + ("error" in s)
                ran += [] if "error" in s else [s["key"]]
                for k, v in s["ends"].items():
                    ends[k] = ends.get(k, 0) + v
                _tally(flags, drift, s)
            if n % (pool.workers * 4) and n < len(batches):
                continue
            dt = time.time() - t0
            print(json.dumps({"done": done, "of": len(todo), "errors": errors, "ticks": ticks, "s": round(dt),
                              "ticks_per_s": round(ticks / dt) if dt else 0, "ends": ends}), flush=True)
        library = _library(a.l3)
    out = {"jobs": len(jobs), "ran": done, "errors": errors, "ticks": ticks, "seconds": round(time.time() - t0),
           "ends": ends, "core": cache.core(), "aim_core": cache.core(cache.CORE_FILES + cache.AIM_FILES),
           "snapshot": snap["meta_sha12"], "l3": a.l3, "library": library}
    if kernel is not None:
        from devkit.reach.native import backend as KB
        out |= {"backend": "kernel", "kernel": KB.kernel_sha12(), "census": _census_of(a.level, snap)[1],
                "flags": flags, "drift": _drifts(drift)}
        if over := [k for k, d in out["drift"].items() if d["over"]]:
            print(json.dumps({"drift_over": over, "do": "run these stages' plans with @l3 (FastL3)"}), flush=True)
    if a.l3 == "fast":
        ok = set(ran)
        out["audit"] = _audit(a, snap, base, [j for j in todo if j["key"] in ok], touch, zones, library, kernel)
        bad, x87 = [x["id"] for au in out["audit"].values() for x in au.get("differ", ())], out["audit"]["x87"]
        if bad or x87.get("x87_differ") or x87.get("x87_workers") == 0 or x87.get("walk_differ"):
            print(json.dumps(out), flush=True)
            raise SystemExit(f"the audit found FastL3 records base L3 or the x87 check gives otherwise: {bad[:20]}"
                             f" (x87 results differing: {x87.get('x87_differ')}, workers that wrote a count: "
                             f"{x87.get('x87_workers')}, C walk decisions differing: {x87.get('walk_differ')}); the "
                             "run stops: find why before another fast run")
    return out


STAGES = {"a": "aims", "t": "fan", "r": "refine", "s": "smallfan", "g": "retarget",
          "p": "pairs", "e": "escalate"}   # a job id's first letter: its stage


def _tally(flags: dict, drift: dict, s: dict) -> None:
    """A kernel job's summary (``reach_native.backend``: its record's ``kernel`` and ``drift``) added to the run's
    counts by stage."""
    st = STAGES.get(s["id"][0], s["id"][0])
    for k, v in (s.get("kernel") or {}).items():
        d = flags.setdefault(st, {})
        if isinstance(v, dict):
            for a, b in v.items():
                d.setdefault(k, {})[a] = d.setdefault(k, {}).get(a, 0) + b
        else:
            d[k] = d.get(k, 0) + v
    if "drift" in s:
        d = drift.setdefault(st, {"jobs": 0})
        d["jobs"] += 1
        for k, v in s["drift"].items():
            d[k] = d.get(k, 0) + v


def _drifts(drift: dict) -> dict:
    """Each stage's drift audit with its silent share and whether it is over ``backend.DRIFT_MAX``."""
    from devkit.reach.native.backend import DRIFT_MAX
    return {k: d | {"share": round(d["silent"] / d["settled"], 4) if d["settled"] else None,
                    "over": bool(d["settled"]) and d["silent"] / d["settled"] > DRIFT_MAX} for k, d in drift.items()}


def _audit(a, snap: dict, base: Path, ran: list[dict], touch: Path, zones: Path | None, library: str,
           kernel: dict | None = None) -> dict:
    """A fast run's audits (Step R2.19b, ``reach_engine.worker``): about 1 job in ``worker.BASE_EVERY`` it ran again
    on base L3 on the stock wheel and, with the patched library, 1 in ``worker.X87_EVERY`` on FastL3 (its C walk in
    check mode) with the x87
    check on, each record compared with the one the run wrote (nothing written): their jobs, those whose record
    differs, those that raised and the x87 check's counts."""
    import shutil
    import tempfile
    from devkit.reach.engine import worker
    from devkit.reach.l3_pool import default_workers
    out = {}
    for name, every in (("base", worker.BASE_EVERY), ("x87", worker.X87_EVERY)):
        jobs = [j for j in ran if worker.audited(j["key"], every)]
        if not jobs or (name == "x87" and library != "patched"):
            out[name] = {"jobs": len(jobs), "ran": False}
            continue
        logs = tempfile.mkdtemp(prefix="reach-x87-") if name == "x87" else None
        try:
            rows = []
            with _pool(snap, min(a.workers or default_workers(), len(jobs)), "base" if name == "base" else "fast",
                       logs, kernel) as pool:
                for got in pool.completed(worker.audit_task, [([j], str(base), str(touch), zones and str(zones))
                                                              for j in jobs]):
                    rows += got
            out[name] = {"jobs": len(jobs), "same": sum(bool(r.get("same")) for r in rows),
                         "differ": [r for r in rows if r.get("same") is False],
                         "errors": [r for r in rows if "error" in r]}
            if logs is not None:
                x = worker.x87_counts(logs)
                out[name] |= {"x87_results": x["results"], "x87_differ": x["differ"], "x87_workers": x["workers"],
                              "walk_checked": x["walk_checked"], "walk_differ": x["walk_differ"]}
        finally:
            if logs is not None:
                shutil.rmtree(logs, ignore_errors=True)
    return out


def _hold_audit(snap: dict, base: Path, items, workers: int | None, kernel: dict | None, counts) -> None:
    """The holds' audits (Step R2.19f+'s X1, as :func:`_audit`'s): of the (job, outcome) ``items`` a fast pool just
    replayed, about 1 in ``worker.BASE_EVERY`` (by hold key) replayed again on base L3 on the stock wheel and, with
    the patched library, 1 in ``worker.X87_EVERY`` on FastL3 with the x87 check on (its C walk in check mode), each
    answer compared with the cached one (``worker.hold_audit_task``); counted in ``counts``, and any difference stops
    the command."""
    import shutil
    import tempfile
    from devkit.reach.engine import worker
    library, bad = _library("fast"), []
    for name, every in (("base", worker.BASE_EVERY), ("x87", worker.X87_EVERY)):
        todo = [i for i in items if worker.audited(hold.key(*i), every)]
        counts[f"hold audit {name}: asked"] += len(todo)
        if not todo or (name == "x87" and library != "patched"):
            continue
        logs = tempfile.mkdtemp(prefix="reach-x87-") if name == "x87" else None
        try:
            rows = []
            with _pool(snap, min(workers or 4, len(todo)), name if name == "base" else "fast", logs, kernel) as pool:
                for got in pool.completed(worker.hold_audit_task, [([i], str(base)) for i in todo]):
                    rows += got
            counts[f"hold audit {name}: same"] += sum(bool(r.get("same")) for r in rows)
            counts[f"hold audit {name}: errors"] += sum("error" in r for r in rows)
            bad += [f"{r['job']}#{r['outcome']}" for r in rows if r.get("same") is False]
            if logs is not None:
                x = worker.x87_counts(logs)
                counts["hold audit x87: results"] += x["results"]
                counts["hold audit x87: differ"] += x["differ"]
                counts["hold audit x87: walk checked"] += x["walk_checked"]
                counts["hold audit x87: walk differ"] += x["walk_differ"]
                bad += [f"x87 results differing: {x['differ']}"] if x["differ"] or not x["workers"] else []
                bad += [f"C walk decisions differing: {x['walk_differ']}"] if x["walk_differ"] else []
        finally:
            if logs is not None:
                shutil.rmtree(logs, ignore_errors=True)
    if bad:
        raise SystemExit(f"the hold audit found FastL3 answers base L3 or the x87 check gives otherwise: {bad[:20]};"
                         " the command stops: find why before another fast run")


def _graph(a, nodes: Nodes | None = None, keep=None):
    """The plans' graph, every zone witness held (:func:`_hold`); with ``keep``, of each record as ``keep`` gives
    it (``aim.unscheduled``: the refinement's)."""
    snap, base = _snap(a.snapshot, a.store), cache.folder(a.level)
    jobs = _plans(a.level, a.plan, snap, getattr(a, "backend", "l3"))
    recs = [(keep or (lambda r: r))(r) for j in jobs if (r := cache.get(base, j["key"])) is not None]
    nodes = _nodes(a.level) if nodes is None else nodes
    g = Graph(nodes, {j["key"]: j for j in jobs}, recs)
    doc = _plan(a.level, a.plan[0], snap, getattr(a, "backend", "l3"))
    _hold(g, recs, snap, base, getattr(a, "workers", None), getattr(a, "l3", "fast"),
          _kernel(a.level, snap, jobs, base / f"targets-{doc['touch']}.json"),
          (a.level, nodes) if getattr(a, "rigs", False) else None)
    return snap, base, {j["key"]: j for j in jobs}, recs, nodes, g


def _hold(g: Graph, recs, snap: dict, base: Path, workers: int | None, mode: str = "fast",
          kernel: dict | None = None, rigs: tuple | None = None) -> None:
    """The hold (``reach_engine.hold``): replay each zone witness ``Graph.hold`` asks for that the cache doesn't
    answer yet, a few per task on a pool (opened only when one is; ``kernel``: the kernel route's, whose replay of a
    kernel candidate is FastL3's confirm), until each rank's best that stays is known.  With ``rigs`` (the level
    and its nodes: ``--rigs``, Step R2.19h1), each witness answered goes through ``rigs.Router.decide``: one
    touching a rig parked for an undecoded trigger is out of logic, kept or not (D847); of those its frozen hold
    kept, one touching another parked rig names it (a trip's witness too), one a moving rig in the level's rig
    recording touches at its load pose or crosses on its swept path (``rigs.sweep_task``, cached apart) stays only
    where its whole-step trip does (``rigs.replay_trip``, cached apart)."""
    from devkit.reach.engine import rigs as R
    by_key = {r["key"]: r for r in recs}
    trips, sweeps, counts, owed, seen = set(), set(), g.counts, {}, {}
    pool = None
    if rigs is not None:
        try:
            doc, verdicts, rec12 = R.recording(rigs[0], snap)
        except FileNotFoundError:                  # made once a snapshot and recorder (rigs.code12)
            pool = _pool(snap, workers, mode, kernel=kernel)
            doc, verdicts, rec12 = R.recording(rigs[0], snap, pool)
        router, zone_at = R.Router(R._level(rigs[0])[0], verdicts, doc["rec"]), rigs[1].zone_at

    def answer(w):
        got = hold.answer(base, by_key[w["job"]], w["outcome"])
        if got is None or rigs is None or "land" not in got:
            return got
        rec, wk = by_key[w["job"]], (w["job"], w["outcome"])
        o, hk = rec["outcomes"][w["outcome"]], hold.key(*wk)
        sw = cache.get(base / "sweep", R.sweep_key(hk))
        how, x = router.decide(got, got.get("route"), o["ticks"],
                               hold.stays(got, zone_at(o["land"], o["land_state"] == 6, False), zone_at),
                               None if sw is None else sw.get("boxes", R.EVERYWHERE),
                               (rec["starts"][o["start"]]["feet"], o.get("took"), o.get("first"), o["land"],
                                got["land"]))
        seen[wk] = "parked" if how == "as" and "parked" in x else how
        if how == "sweep":
            sweeps.add(wk)
            return None
        if how != "trip":
            return x
        t = cache.get(base / "trip", R.trip_hold_key(hk, rec12))
        if t is None:
            trips.add((*wk, tuple(got["land"])))
            return None
        got = R.Router.tripped(got, t, x[1])
        owed[wk] = got["same"]
        if got["same"] and x[1]:
            seen[wk] = "parked"
        return got
    t0, n, ticks, replayed = time.time(), 0, 0, []
    try:
        while want := g.hold(answer):
            pool = pool or _pool(snap, workers, mode, kernel=kernel)
            routed = {(j, k) for j, k, _ in trips} | sweeps
            items = sorted({(w["job"], w["outcome"]) for w in want} - routed)
            replayed += items
            for t in pool.completed(hold.task, [(items[k:k + 8], str(base)) for k in range(0, len(items), 8)]):
                ticks += t
            if sweeps:
                sl = sorted(sweeps)
                for t in pool.completed(R.sweep_task, [(sl[k:k + 8], str(base)) for k in range(0, len(sl), 8)]):
                    ticks += t
                counts["routed witnesses swept"] += len(sl)
                sweeps.clear()
            if trips:
                tl = sorted(trips)
                for t in pool.completed(R.trip_hold_task, [(tl[k:k + 4], str(base), rec12)
                                                           for k in range(0, len(tl), 4)]):
                    ticks += t
                counts["routed witnesses tripped in whole steps"] += len(tl)
                trips.clear()
            n += len(items)
            print(json.dumps({"held": n, "ticks": ticks, "s": round(time.time() - t0)}), flush=True)
    finally:
        if pool is not None:
            pool.close()
    if replayed and mode == "fast":
        _hold_audit(snap, base, replayed, workers, kernel, counts)
    if owed:
        counts["routed witnesses asked, owing a whole-step trip"] = len(owed)
        counts["routed witnesses whose trip held"] = sum(owed.values())
    if seen:
        counts["routed witnesses out of logic: a rig parked for an undecoded trigger"] = sum(
            v == "out" for v in seen.values())
        counts["routed witnesses kept, naming a parked rig"] = sum(v == "parked" for v in seen.values())


def rigs(a) -> dict:
    """The level's rig stage (Step R2.19h1, ``reach_engine.rigs``): the recording and the decks' verdicts (parked by
    name, D847), the kernel's hops and links round each decided moving deck, their FastL3 whole-step trips (a rig
    link, hop or truth board counts only where it holds again alone on a new FastL3: ``held_not_alone`` those that
    didn't) and ``--truth`` random whole-step board trials a deck; ids, names, counts, ticks and witness sha12s."""
    from devkit.reach.engine import rigs as R
    from devkit.reach.engine import worker
    from devkit.reach import models
    from devkit.reach.l3_pool import Pool
    from devkit.sim.ports import vanilla_iso
    from devkit.sim.ports import read_file
    snap = _snap(a.snapshot, a.store)
    absent = _census_of(a.level, snap)[0]["absent"]
    t0, c0 = time.time(), time.process_time()
    pool = Pool(snap["label"], read_file(str(vanilla_iso()), "default.xbe"), store=snap["store"], workers=a.workers,
                name="reach engine rigs", fast=a.l3 == "fast", setup=functools.partial(worker.setup, False))
    try:
        doc, verdicts, rec12 = R.recording(a.level, snap, pool)
        rec_path = str(cache.folder(a.level) / f"rigs-{snap['meta_sha12']}-{R.code12()}.pkl.gz")
        reach = str(models.reach_path(a.level))
        ds = [d for d in R.decks(a.level, doc, verdicts) if not a.deck or d.name in a.deck]
        args = (a.level, rec_path, reach, absent)
        found = {r["oi"]: r for r in pool.completed(R.search_task, [(*args, d.oi) for d in ds])}
        nodes, items = _nodes(a.level), {}
        takeoffs = R.off_decks(R._level(a.level)[0], nodes.takeoffs())
        for d in ds:
            f, its = found[d.oi], []
            for za, hits in f["board"].items():
                its += [("board", za, c, None) for c in sorted(hits, key=R._rank)[:R.TRIPS]]
            for zb, hits in f["alight"].items():
                its += [("alight", zb, c, zb) for c in sorted(hits, key=lambda x: x["ticks"])[:R.TRIPS]]
            for pair, cs in f["links"].items():
                its += [("link", pair, c, pair.split(">")[1]) for c in cs]
            hits = [b for v in f["board"].values() for b in v]
            its += [("truth", f"t{k}", c, None) for k, c in enumerate(R.truth_trials(nodes, d, takeoffs, a.truth, hits))]
            items[d.oi] = its
        trips = {}
        for oi, res in zip([d.oi for d in ds], pool.map(R.trip_task, [(*args, d.oi, items[d.oi]) for d in ds])):
            trips[oi] = res
    finally:
        pool.close()
    out_decks, links, hop_rows = [], [], []
    for oi, v in sorted(verdicts.items()):
        out_decks.append({"oi": oi, **{k: v[k] for k in ("name", "start", "how", "why", "period", "moved_m", "term",
                                                       "of") if k in v}})
    truth = {"trials": 0, "made": 0, "hops_made": [], "pipeline": [], "by_stratum": {}}
    for d in ds:
        f, res = found[d.oi], trips[d.oi]
        made = {(r["kind"], r["key"]) for r in res if r["ok"] and r["kind"] != "truth"}
        for r in res:
            if r["kind"] == "link" and r["ok"]:
                za, zb = r["key"].split(">")
                links.append({"from": za, "to": zb, "via": d.name, "oi": d.oi, "how": d.how,
                              "term": verdicts[d.oi].get("term"), "phase": r["phase"], "witness": r["sha12"],
                              "steps": r["steps"]})
        tr = [r for r in res if r["kind"] == "truth"]
        tz = {c[1]: c[2]["zone"] for c in items[d.oi] if c[0] == "truth"}
        for r in tr:
            st = next(c[2]["stratum"] for c in items[d.oi] if c[0] == "truth" and c[1] == r["key"])
            x = truth["by_stratum"].setdefault(st, {"trials": 0, "made": 0})
            x["trials"] += 1
            x["made"] += r["ok"]
        made_t = sorted({tz[r["key"]] for r in tr if r["ok"]})
        truth["trials"] += len(tr)
        truth["made"] += sum(r["ok"] for r in tr)
        truth["hops_made"] += [f"{d.name}<{z}" for z in made_t]
        truth["pipeline"] += [f"{d.name}<{z}" for z in made_t if ("board", z) in made]
        hop_rows.append({"deck": d.name, "oi": d.oi, "how": d.how, "span": d.span, "cyc": d.cyc,
                         "board_zones": len(f["board"]), "alight_zones": len(f["alight"]),
                         "link_pairs": len(f["links"]),
                         "board_made": sum(1 for k, _ in made if k == "board"),
                         "alight_made": sum(1 for k, _ in made if k == "alight"),
                         "links_made": sum(1 for k, _ in made if k == "link"),
                         "held_not_alone": sum(1 for r in res if r["fresh"] is not None and not r["ok"]),
                         "kernel_cpu_s": f["cpu_s"], "kernel_ticks": f["kernel_ticks"],
                         "trip_cpu_s": round(sum(r["cpu_s"] for r in res if r["kind"] != "truth"), 1),
                         "trip_steps": sum(r["steps"] for r in res if r["kind"] != "truth"),
                         "truth_cpu_s": round(sum(r["cpu_s"] for r in tr), 1),
                         "truth_trials": len(tr), "truth_made": sum(r["ok"] for r in tr),
                         "faults": dict(collections.Counter(str(r["answer"].get("fault") or r["answer"].get("start"))
                                                            for r in res if r["answer"].get("fault")
                                                            or r["answer"].get("start")))})
    hops = sorted(set(truth["hops_made"]))
    seen = set(truth["pipeline"])
    return {"level": a.level, "snapshot": snap["label"], "recording": rec12, "code": R.code12(),
            "decks": out_decks, "parked": [f"{x['name']}: {x['why']}" for x in out_decks if x["how"] == "parked"],
            "by_how": {h: sum(x["how"] == h for x in out_decks) for h in (*R.DECIDED, "parked")},
            "hops": hop_rows, "links": links,
            "truth": {"trials": truth["trials"], "made": truth["made"], "by_stratum": truth["by_stratum"],
                      "hops_made": len(hops),
                      "hops_the_pipeline_made": len(seen), "missed": sorted(set(hops) - seen)},
            "wall_s": round(time.time() - t0), "main_cpu_s": round(time.process_time() - c0, 1),
            "recording_steps": doc["rec"]["steps"]}


def graph(a) -> dict:
    """The engine's zone edges (ids, ranks, witness hashes) and node counts, and the closure per kit."""
    snap, base, jobs, recs, nodes, g = _graph(a)
    zones = [{"from": za, "to": zb, "ranks": {str(r): verdict._wid(w) for r, w in sorted(got.items())}}
             for (za, zb), got in sorted(g.zones.items())]
    return {"level": a.level, "snapshot": snap, "core": cache.core(), "records": len(recs), "jobs": len(jobs),
            "node_edges": len(g.edges), "zone_edges": zones, "touches": len(g.touch), "counts": dict(g.counts),
            "closure": g.kits()}


def diff(a) -> dict:
    """The recall report against the level's derived edges, hand edges and assumed and physics rows."""
    from devkit.rando.draft.author import AUTHORING, read_derived
    from azurkit.tools.randomizer.planner.loader import DATA_DIR
    snap, base, jobs, recs, nodes, g = _graph(a)
    level_doc = tomllib.loads((DATA_DIR / "levels" / f"{a.level}.toml").read_text(encoding="utf-8"))
    spec = tomllib.loads((AUTHORING / f"{a.level}.toml").read_text(encoding="utf-8"))
    return {"snapshot": snap, "core": cache.core(), "records": len(recs), "jobs": len(jobs),
            **verdict.report(a.level, read_derived(a.level), level_doc, spec, g)}


def witness(a) -> list[dict]:
    """Each zone edge's best witness at each rank as a proof record (replay owed)."""
    from devkit.rando.draft.author import read_derived
    from azurkit.tools.randomizer.planner import proofs as pr
    snap, base, jobs, recs, nodes, g = _graph(a)
    by_key = {r["key"]: r for r in recs}
    zoning = pr.zoning(read_derived(a.level))
    return [verdict.witness(a.level, w, by_key[w["job"]], jobs[w["job"]]["heading"], snap, zoning, (za, zb))
            for (za, zb) in sorted(g.zones) for w in g.witnesses((za, zb))]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("sample", "run", "graph", "diff", "witness", "rigs"):
        p = sub.add_parser(name)
        p.add_argument("level")
        p.add_argument("--plan", required=name != "rigs", nargs="+")
        if name == "sample":
            p.add_argument("--region", type=int, nargs="*")
            p.add_argument("--targeted", action="store_true")
            p.add_argument("--no-fan", action="store_true")
            p.add_argument("--spacing", type=float, default=2.0)
            p.add_argument("--min-area", type=float, default=4.0)
            p.add_argument("--limit", type=int)
            p.add_argument("--refine", nargs="+")
            p.add_argument("--snapshot")
            p.add_argument("--store")
            p.add_argument("--workers", type=int)          # the hold's pool (``--refine``)
            p.add_argument("--l3", choices=("fast", "base"), default="fast")
            p.add_argument("--backend", choices=("l3", "kernel"), default="l3")
            p.add_argument("--backstop", choices=("modelled", "all"))
            p.add_argument("--retarget", nargs="+")         # Step R2.19f+'s g1: aims at what these plans' graph left
            p.add_argument("--gate-m", type=float, default=aim.GATE_M)
            p.add_argument("--pairs", action="store_true")     # the pair stage (Step R2.19g2)
            p.add_argument("--budget", type=float)             # ... its CPU-hours (default: every group)
            p.add_argument("--slice", type=float)              # ... each nd stratum's first fraction (a bench's)
            p.add_argument("--truth", nargs="*")               # ... R's frozen rows its rates read
            p.add_argument("--escalate", type=float)           # the escalation's tier, metres (Step R2.19g3)
            p.add_argument("--kit", choices=("k0", "air3"))    # ... one kit's pairs only (default both, k0 first)
            continue
        p.add_argument("--snapshot", required=True)
        p.add_argument("--store")
        p.add_argument("--workers", type=int)              # by default the pool's: the host's cores, at most 16
        p.add_argument("--l3", choices=("fast", "base"), default="fast")   # the module docstring
        p.add_argument("--backend", choices=("l3", "kernel"), default="l3")
        if name == "run":
            p.add_argument("--per-task", type=int, default=2)
        if name in ("graph", "diff", "witness", "rigs"):
            p.add_argument("--out", required=True)
        if name in ("graph", "diff", "witness"):
            p.add_argument("--rigs", action="store_true")      # the router's whole-step trips (Step R2.19h1)
        if name == "rigs":
            p.add_argument("--truth", type=int, default=0)     # random whole-step board trials a deck
            p.add_argument("--deck", nargs="*")                # only these decks (names): a slice
    a = ap.parse_args(argv)
    out = {"sample": sample, "run": run, "graph": graph, "diff": diff, "witness": witness, "rigs": rigs}[a.cmd](a)
    if a.cmd == "witness":
        p = l3.private_out(a.out, None)
        p.write_text("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in out),
                     encoding="utf-8")
        print(json.dumps({"witnesses": len(out), "out": p.name}))
    elif getattr(a, "out", None):
        print(json.dumps({"out": l3.private_out(a.out, out, indent=1).name}))
    else:
        print(json.dumps(out))


if __name__ == "__main__":
    main()
