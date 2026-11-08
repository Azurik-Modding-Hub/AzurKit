"""Run the trick explorer (Step TD.1, ``devkit.sim.l3_explore``) on L3 snapshots: one problem, or a batch of them.

A problem is a start (an L3 snapshot in the private store, a natural start; or with ``--start`` a private start file
holding an R6 ``teleport``, a placed start whose finds are ``partial``; a spec's ``prefix``, private found files whose
strings run first in L3, in order, each a find from that start after the files before it: a start chained on them,
Step TD.2), a kit (element levels set in L3 by R2, 0 for each it doesn't name, so an empty kit is kit 0;
``"snapshot"`` keeps the snapshot's own levels, AZ-528; the air
armor cast by input), the mode (a spec's ``scene``: whole steps, so rigs, rides and triggers run) and either a target
(``--goal`` zones or a level-file node, ``--location`` a pickup by its item's own touch, ``--exit`` a level exit's
trigger, from out of bounds too: guidance on the light trick graph, ``l3_goal.make_trick_goal`` /
``make_trick_exit_goal``) or none (a discovery problem: novelty picks only, ``l3_goal.make_zone_guide``), explored
with ``--seeds`` derived seeds to ``--steps`` emulated ticks each; ``--sites`` adds the mined sites' prior
(``draft.sites.Prior``), and a spec's ``limits`` its ablations (``{"ablate": ["speed", "options", "sites"]}``).
``bench SPEC`` runs a JSON list of such problems (``{"key", "snapshot", "level", "start", "kit", "goal", "location",
"exit", "touch", "sites", "steps", "seeds", "score", "scene", "prefix", "limits"}``; ``score``: zones whose first
reach is reported), each problem in a process and on a pool of its own (a worker per seed, at most ``--workers``;
its own batch token), at most ``--workers`` workers at once.  A SIGTERM or Ctrl-C stops every run at its next round
and removes the bench's scratch.

``census LEVEL`` (Step TD.4) mines the level's sites at the kit (``draft.sites``) and writes to ``--out`` the counts
of its surface classes, sites and exits, with the faces the given runs' private files touched and the volumes they
entered; ``--rank`` also writes the value ranker's queue (``draft.value``) to the private store, never to a report
(the blind protocol keeps the pilot's levels' ranks out of reports).

    uv run --locked python -m devkit sim explore run LABEL --level L [--start PRIVATE.json] [--kit air=1 ... | snapshot]
        [--goal ZONE ... | --location ID [--touch M] | --exit ID] [--sites] [--steps 2000000] [--seeds 1]
        [--out OUT.json]
    uv run --locked python -m devkit sim explore bench SPEC.json --out OUT.json [--workers 8] [--digest]
    uv run --locked python -m devkit sim explore census LEVEL [--kit air=2] [--runs PRIVATE.json ...] --out OUT.json
        [--rank]

``--digest`` adds each run's archive digest (every cell and its two strings' hashes: the determinism check).  The
output (mode 0600; never over a file there: a taken name gets ``.2``, ``.3``, ``l3.private_out``, Step X.51) holds
verdicts, counts, metres, zone ids and string hashes; each found string and the first string that
stood in each zone (only ``score``'s, with one) and opened each pseudo-region (``l3.pads`` segments: a find's seed
for its confirmation), with the faces the runs touched and the volumes they entered (ids: the census's input), go to
the private store's ``td1`` folder (mode 700, files 0600).  Dev tooling: never in pytest, never a CLI verb.
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from devkit.sim import l3  # noqa: E402
from devkit.sim.l3_explore import Limits, Problem, blind, explore_many  # noqa: E402
from devkit.sim.l3_search import Segment  # noqa: E402

GOALS = "devkit.rando.draft.l3_goal"
SETTLE = 20          # the start's settle ticks (l3_certify's)


def private() -> Path:
    p = l3.store() / "td1"
    p.mkdir(mode=0o700, exist_ok=True)
    p.chmod(0o700)
    return p


def chain(spec: dict, teleport, kit) -> list:
    """A spec's ``prefix``: its found files' strings in order.  Each file must be a find from this very start (the
    snapshot, teleport, settle, kit and mode) after the files before it (its own prefix their strings), else the
    chain would start somewhere else: refused by the file's name."""
    prefix: list = []
    for f in spec.get("prefix") or ():
        doc = json.loads(Path(f).read_text(encoding="utf-8"))
        want = {"snapshot": spec["snapshot"], "teleport": teleport, "settle": SETTLE, "kit": kit,
                "scene": bool(spec.get("scene")), "prefix": prefix}
        got = {k: doc.get(k, {"scene": False, "prefix": []}.get(k)) for k in want}
        bad = [k for k in want if json.dumps(got[k], sort_keys=True) != json.dumps(want[k], sort_keys=True)]
        if bad or not doc.get("string"):
            raise ValueError(f"prefix {Path(f).name}: not a find from this start after the files before it "
                             f"({', '.join(bad) or 'no string'} differ)")
        prefix = prefix + doc["string"]
    return prefix


def problem(spec: dict) -> Problem:
    """A bench spec's problem (the module docstring)."""
    from devkit.reach import models
    blind(spec["snapshot"], spec.get("start"))      # before a start file is read or a pool loads the snapshot
    kit = None if spec.get("kit") == "snapshot" else dict(spec.get("kit") or {})   # {}: R2's zeros (AZ-528)
    teleport = None
    if spec.get("start"):
        doc = json.loads(Path(spec["start"]).read_text(encoding="utf-8"))
        teleport = (doc.get("start") or doc)["teleport"]
    prefix = chain(spec, teleport, kit)
    reach = str(models.reach_path(spec["level"]))
    air = int((kit or {}).get("air", 0))
    target = spec.get("location") or spec.get("goal")
    more = {"sites": True} if spec.get("sites") else {}
    if spec.get("exit"):
        guide = {"module": GOALS, "factory": "make_trick_exit_goal",
                 "kwargs": {"reach": reach, "exit_id": spec["exit"], "air": air, **more}}
    elif target:
        kw = {"reach": reach, "target": target, "air": air, **more}
        if spec.get("touch") is not None:
            kw["touch"] = spec["touch"]
        guide = {"module": GOALS, "factory": "make_trick_goal", "kwargs": kw}
    else:
        guide = {"module": GOALS, "factory": "make_zone_guide",
                 "kwargs": {"reach": reach, **({"air": air, **more} if more else {})}}
    lim = Limits(steps=int(spec.get("steps", Limits.steps)), **spec.get("limits", {}))
    return Problem(Segment(spec["snapshot"], teleport=teleport, settle=SETTLE, kit=kit, prefix=prefix,
                           scene=bool(spec.get("scene"))), guide, lim, int(spec.get("seeds", 1)))


def _public(spec: dict, r: dict) -> dict:
    score = {z: r["zones"].get(z) for z in spec.get("score", ())}
    w = r["winner"]
    return {"key": spec["key"], "level": spec["level"], "kind": "target" if (spec.get("goal") or spec.get(
        "location") or spec.get("exit")) else "discovery", "verdict": r["verdict"], "found": r["found"],
        "partial": r["partial"], "inconclusive": r["inconclusive"], "problem": r["problem"], "steps": r["steps"],
        "ticks": w["ticks"] if w else None, "string_sha12": w.get("string_sha12") if w else None,
        "score": score, "zones_reached": len(r["zones"]), "transitions": len(r["transitions"]),
        "saturated": len(r["saturated"]), "faces_touched": len({f for f, _, _ in r["touched"]}),
        "runs": [{k: v for k, v in x.items() if k not in ("bandit", "zones", "cam", "regions", "transitions")}
                 | {"zones": len(x["zones"]), "regions": len(x["regions"]), "transitions": len(x["transitions"])}
                 for x in r["runs"]]}


def run_one(spec: dict, digest: bool = False, workers: int | None = None) -> dict:
    """One problem on a pool of its own (a worker per seed, at most ``workers``): its public result; its found
    string and first strings go to the private store."""
    from devkit.sim.ports import vanilla_iso
    from devkit.sim.ports import read_file
    from devkit.reach.l3_pool import Pool
    p = problem(spec)
    with Pool(spec["snapshot"], read_file(str(vanilla_iso()), "default.xbe"), workers=min(p.seeds, workers or p.seeds),
              name="l3 explore") as pool:
        r = explore_many(pool, [p], digest=digest)[0]
    score = set(spec.get("score") or ())
    # a zone's (``<level>.Z<n>``: score's only, with one) and each pseudo-region's (``R<n>`` or ``C<place>``)
    firsts = {k: v for k, v in r["firsts"].items() if not score or k in score or k[0] in "RC"}
    if r["winner"] or firsts or r["touched"] or r["entered"]:
        f = private() / f"{spec['key']}-{r['problem']}.json"
        f.touch(mode=0o600)
        f.write_text(json.dumps({"key": spec["key"], "snapshot": spec["snapshot"], "teleport": p.seg.teleport,
                                 "kit": p.seg.kit, "settle": p.seg.settle, "scene": p.seg.scene,
                                 "prefix": p.seg.prefix,
                                 "cam": r["winner"]["cam"] if r["winner"] else r["runs"][0]["cam"],
                                 "string": r["winner"]["string"] if r["winner"] else None, "firsts": firsts,
                                 "level": spec["level"], "touched": r["touched"], "entered": r["entered"],
                                 "used": r["used"],
                                 "transitions": r["transitions"], "saturated": r["saturated"],
                                 "zones": sorted(r["zones"]), "regions": sorted({g for x in r["runs"]
                                                                                 for g in x["regions"]})}),
                     encoding="utf-8")
        f.chmod(0o600)
    return _public(spec, r)


def census(level: str, air: int, runs: list[Path], rank: bool = False) -> dict:
    """The level's site and surface census at the kit's ``air`` level (``draft.sites``), with the faces the private
    run files touched and used, and the probe list (the logic edges out of a saturated zone none of the runs
    reproduced, ``draft.sites.probes``); with ``rank`` the value ranker's queue goes to the private store."""
    from devkit.rando.draft import sites, value
    from devkit.rando.draft.author import read_derived
    from devkit.reach import models
    reach = models.read(models.reach_path(level))
    surf = sites.surface(reach.lv, reach.present)
    found = sites.mine(reach.lv, reach=reach, kit=air, surf=surf)
    touched, entered, used, moves, sat, zones, regions = {}, {}, set(), {}, set(), set(), set()
    for p in runs:
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
        if doc.get("level") != level:
            raise SystemExit(f"{p}: a run of {doc.get('level')!r}, not {level!r}")
        for fid, cls, n in doc.get("touched") or ():
            touched[(fid, cls)] = touched.get((fid, cls), 0) + n
        if entered is not None and "entered" in doc:
            for fid, cls, n in doc["entered"]:
                entered[(fid, cls)] = entered.get((fid, cls), 0) + n
        else:
            entered = None                # a run from before the volume record: its volumes are unmeasured
        used |= set(doc.get("used") or ())
        moves.update(doc.get("transitions") or {})
        sat |= set(doc.get("saturated") or ())
        zones |= set(doc.get("zones") or ())
        regions |= set(doc.get("regions") or ())
    derived = read_derived(level)
    cov = derived.get("coverage", {}).get("exits", {})
    exits = sites.exit_faces(reach.lv, reach)
    no_way = [e for e in exits if e in cov and value.beyond(cov[e].get("least_air"), air)]
    out = {"level": level, "air": air, "runs": len(runs),
           **sites.census(reach.lv, found, touched, sorted(used), reach.present, surf, regions, entered, exits,
                          no_way)}
    entered = {e["to"] for e in derived["edges"] if e.get("logic") is not False and e["from"] != e["to"]}
    unentered = {z["id"] for z in derived["zones"]} - entered
    out["zones"] = {"zones": len(derived["zones"]), "stood_in": len(zones), "unentered": len(unentered),
                    "unentered_stood_in": len(unentered & zones), "saturated": len(sat)}
    out["probes"] = sites.probes(derived, sorted(z for z in sat if z.startswith(f"{level}.Z")), moves)
    out["transitions"] = len(moves)
    if rank:
        queue = value.rank(found, value.near_zones(reach, found), value.zone_values(derived, air))
        f = private() / f"census-{level}-air{air}-rank.json"
        f.touch(mode=0o600)
        f.write_text(json.dumps(queue), encoding="utf-8")
        f.chmod(0o600)
    return out


def bench(spec_path: Path, workers: int, digest: bool = False, log=print) -> list[dict]:
    """Every problem of the spec file, each in a process of its own (``one``: its own pool and batch token), at most
    ``workers`` pool workers at once; the public results in the specs' order."""
    specs = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp(prefix="td1-bench.", dir="/tmp"))
    out: list[dict | None] = [None] * len(specs)
    pending, running, busy = list(range(len(specs))), {}, 0
    try:
        while pending or running:
            while pending and busy + min(int(specs[pending[0]].get("seeds", 1)), workers) <= workers:
                i = pending.pop(0)
                n, f = min(int(specs[i].get("seeds", 1)), workers), tmp / f"{i}.json"
                proc = subprocess.Popen([sys.executable, "-m", "devkit.sim.explore", "one", str(spec_path), str(i),
                                         str(f), "--workers", str(workers)] + (["--digest"] if digest else []),
                                        cwd=Path(__file__).resolve().parents[2])   # devkit imports from the root
                running[proc], busy = (i, n, f), busy + n
                log(f"{time.strftime('%H:%M:%S')} {specs[i]['key']} ({specs[i]['snapshot']}) on {n} workers",
                    flush=True)
            time.sleep(5)
            for proc in [q for q in running if q.poll() is not None]:
                i, n, f = running.pop(proc)
                busy -= n
                out[i] = json.loads(f.read_text(encoding="utf-8")) if proc.returncode == 0 and f.exists() else \
                    {"key": specs[i]["key"], "error": f"exit {proc.returncode}"}
                f.unlink(missing_ok=True)
                log(json.dumps({k: out[i].get(k) for k in ("key", "verdict", "partial", "steps", "ticks", "score",
                                                           "error")}), flush=True)
    finally:
        for proc in running:             # each stops its runs at their next round (main's SIGTERM handler)
            proc.terminate()
        for proc in running:
            proc.wait()
        for f in tmp.iterdir():
            f.unlink()
        tmp.rmdir()
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("snapshot")
    p.add_argument("--level", required=True)
    p.add_argument("--start")
    p.add_argument("--kit", nargs="*", default=[])
    p.add_argument("--goal", nargs="*")
    p.add_argument("--location")
    p.add_argument("--exit")
    p.add_argument("--touch", type=float)
    p.add_argument("--sites", action="store_true")
    p.add_argument("--steps", type=int, default=Limits.steps)
    p.add_argument("--seeds", type=int, default=1)
    p.add_argument("--out")
    p.add_argument("--digest", action="store_true")
    p = sub.add_parser("bench")
    p.add_argument("spec")
    p.add_argument("--out", required=True)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--digest", action="store_true")
    p = sub.add_parser("census", help="a level's site and surface census (Step TD.4)")
    p.add_argument("level")
    p.add_argument("--kit", nargs="*", default=[])
    p.add_argument("--runs", nargs="*", default=[])
    p.add_argument("--out", required=True)
    p.add_argument("--rank", action="store_true")
    p = sub.add_parser("one", help="one problem of a spec file (bench's child)")
    p.add_argument("spec")
    p.add_argument("index", type=int)
    p.add_argument("out")
    p.add_argument("--workers", type=int)
    p.add_argument("--digest", action="store_true")
    a = ap.parse_args(argv)
    # a SIGTERM unwinds like Ctrl-C: explore_many stops its seeds, the pool and batch token close, bench's scratch goes
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(128 + signal.SIGTERM))
    if a.cmd == "one":
        spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))[a.index]
        Path(a.out).write_text(json.dumps(run_one(spec, a.digest, a.workers)), encoding="utf-8")
        return
    if a.cmd == "census":
        kit = {k: int(v) for k, v in (x.split("=") for x in a.kit)}
        l3.private_out(a.out, census(a.level, kit.get("air", 0), a.runs, a.rank), indent=1)
        return
    if a.cmd == "run":
        spec = {"key": a.snapshot, "snapshot": a.snapshot, "level": a.level, "start": a.start,
                "kit": "snapshot" if a.kit == ["snapshot"] else {k: int(v) for k, v in (x.split("=") for x in a.kit)},
                "goal": a.goal,
                "location": a.location, "exit": a.exit, "touch": a.touch, "sites": a.sites, "steps": a.steps,
                "seeds": a.seeds}
        res = [run_one(spec, a.digest)]
    else:
        res = bench(Path(a.spec), a.workers, a.digest)
    if a.out:
        l3.private_out(a.out, res, indent=1)


if __name__ == "__main__":
    main()
