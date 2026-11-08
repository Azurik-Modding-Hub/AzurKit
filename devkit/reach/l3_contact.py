"""Measure the randomizer's contact flights at modified movement in L3 (Step X.11, D173's T6).

The movement calculator (``src/azurkit/tools/randomizer/physics.py``) models arcs, not contact (lip lifts, slopes, rims,
roofs, walk-offs), so a flight it can't reproduce or that sits at its limit keeps only movement no weaker than
vanilla's.  This script runs such a flight in L3, the game's own code, on a vanilla snapshot with a build laid over
it (``devkit/sim/overlay.py``), and finds each slider's value past which no input string makes it, by
bisection.  Per value, on a worker pool of the case's snapshot (``devkit/reach/l3_pool.py``): every string an
earlier value won with is graded again, and ``--seeds`` searches (seeded by the route planner's plan alone, each to
its own end) run from a teleport onto the flight's start zone to its landing zone; each winner is graded by
``l3_search.robustness`` at the build's frame rate (jittered copies: each jump a 30 fps tick off, AZ-388; each
heading 2 degrees off).  A value passes a tier when a winner's robustness reaches the tier's floor (``TIERS``;
``frame_perfect``: any string).  A failing value only means no search found a string within the budget, so a
measured range errs toward less movement.  A case's ``.fly`` twin ends a branch that swims, so the string must make
the flight rather than swim round the zones.

    uv run --locked python -m devkit reach l3-contact measure CASE PACK.SLIDER --out DIR [--lo X] [--hi Y] [--at V ...]
    uv run --locked python -m devkit reach l3-contact walkoff --out DIR [--ledges N]
    uv run --locked python -m devkit reach l3-contact apply DIR [DIR ...]    # src/azurkit/tools/randomizer/data/contact.json

``CASE`` is a key of :data:`CASES`.  Public results (values, verdicts, counts, robustness, hashes; no positions)
go to ``DIR`` (an evidence folder); the private parts (teleports, strings, derived kit snapshots) to the L3 store.
Dev only (devkit, Step 4.13d2), never a player's verb and never in pytest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import time
from pathlib import Path

import numpy as np

from azurkit.tools.randomizer.live import recipes
from devkit.rando.draft.l3_goal import RouteGoal, load_router, route_seed
from devkit.reach import l3_certify as cert   # the certification pipeline's router, start and goal
from devkit.sim import l3, overlay
from devkit.sim.l3_search import Limits, Seg, Segment, derived_seed, problem_sha12

BASE = "x7-w1-k0-205806"          # w1, a new game's character (kit 0), taken at the scene tick (sitting x7)
# Each level's kit 0 snapshot at the scene tick: sitting x7's (an R7 hop) and x18-snaps' (the native level warp)
BASES = {"w1": BASE, "e2": "x7-e2-k0-205148", "e5": "x7-e5-k0-205459", "f1": "x7-f1-k0-205619",
         "f2": "x7-f2-k0-205639", "f4": "x7-f4-k0-205700", "town": "x7-town-k0-205747",
         "w3": "x7-w3-k0-205822", "a6": "x7-a6-k0-205004", "a1": "x18-a1-k0-090614", "a3": "x18-a3-k0-090517", "d2": "x18-d2-k0-090648",
         "f3": "x18-f3-k0-090459"}
TIERS = cert.TIERS   # devkit/reach/l3_certify.py's (D259): robustness -> the tier it supports
SETTLE = 20
# A flight of the randomizer's logic: its level, the derive's zone edge (start, landing), the air rank it flies
# with, the hop (a level-file edge) its certificate witnesses (data/movement/<level>.json) and, where the zone edge
# has more than one option of that rank, the certificate's dh; ``prof`` "phys": the goal's route graph is the physical
# one (the logic graph has no way for that air rank). Zones and hops are Step X.16's zoning (DERIVE_VERSION 5; a zone
# the one holding most of its old walk samples): a3.z045's start is a slide now. Step R1.39 (AZ-378) re-keyed
# f1.lava_tubes to DERIVE_VERSION 7 (its hop's certificate lands in f1.Z179 now; X.16's zones keep their numbers) and
# dropped a6.core and w3.z145: their hops (a6_core > a6_z005, w3_z155 > w3_z012) are in no level file now and their
# zone edges' certificates in no movement file, so contact.json can't hold them
CASES = {
    "w1.cove": {"level": "w1", "start": "w1.Z009", "goal": "w1.Z439", "air": 1, "hop": "w1_cove > w1_z062"},
    "w1.dark_cave": {"level": "w1", "start": "w1.Z183", "goal": "w1.Z367", "air": 0, "hop": "w1_z022 > w1_dark_cave"},
    "w1.lip": {"level": "w1", "start": "w1.Z048", "goal": "w1.Z066", "air": 1, "hop": "w1_z048 > w1_z027"},
    "w1.bay": {"level": "w1", "start": "w1.Z001", "goal": "w1.Z124", "air": 1, "hop": "w1_bay > w1_stone2"},
    # the flights that bind seed 42's ranges once the lip and cove are measured (Step X.18)
    "w1.town_side": {"level": "w1", "start": "w1.Z043", "goal": "w1.Z703", "air": 3, "hop": "w1_town_side > w1_z703",
                     "dh": 2.25},
    "a3.z045": {"level": "a3", "start": "a3.Z045", "goal": "a3.Z095", "air": 3, "hop": "a3_z018 > a3_z095"},
    "e2.z005": {"level": "e2", "start": "e2.Z005", "goal": "e2.Z278", "air": 3, "hop": "e2_z005 > e2_z148"},
    "e2.z024": {"level": "e2", "start": "e2.Z024", "goal": "e2.Z399", "air": 0, "hop": "e2_z024 > e2_z399", "dh": 0.37},
    "e5.dock": {"level": "e5", "start": "e5.Z009", "goal": "e5.Z369", "air": 1, "hop": "e5_z009 > e5_dock"},
    "f1.lava_tubes": {"level": "f1", "start": "f1.Z016", "goal": "f1.Z179", "air": 0, "hop": "f1_lava_tubes > f1_core"},
    "f2.z153": {"level": "f2", "start": "f2.Z158", "goal": "f2.Z097", "air": 3, "hop": "f2_z158 > f2_z097"},
    "f3.z042": {"level": "f3", "start": "f3.Z042", "goal": "f3.Z245", "air": 3, "hop": "f3_z042 > f3_z245"},
    "f4.cliffside": {"level": "f4", "start": "f4.Z135", "goal": "f4.Z017", "air": 0, "hop": "f4_cliffside > f4_z034"},
    # roofed flights that bound the golden seed's jump at 1.4 and 1.5 under the old roof rule (Step X.21, AZ-364)
    "a3.z242": {"level": "a3", "start": "a3.Z240", "goal": "a3.Z332", "air": 0, "hop": "a3_z155 > a3_z165"},
    "town.z013": {"level": "town", "start": "town.Z011", "goal": "town.Z475", "air": 0,
                  "hop": "town_e2_pocket > town_z475"},
    "f2.z269": {"level": "f2", "start": "f2.Z251", "goal": "f2.Z282", "air": 1, "hop": "f2_z052 > f2_z303"},
    "e5.z010": {"level": "e5", "start": "e5.Z010", "goal": "e5.Z485", "air": 1, "hop": "e5_z010 > e5_z050"},
    "town.z010": {"level": "town", "start": "town.Z009", "goal": "town.Z030", "air": 1, "hop": "town_z009 > town_z016"},
}
# The flight itself: the same, but a run that swims ends its branch (from a floor start), so a string can't reach
# the landing by swimming round and climbing out (which the derive doesn't model: the any-way cases above find it)
CASES |= {f"{k}.fly": dict(v, swim=False) for k, v in CASES.items()}
# Seed 2's roof flights sampled for AZ-387's headroom profile (Step R1.24a, DERIVE_VERSION 7 zoning; flights only,
# swim False), measured from the reach engine's live kit 0 snapshots (reach-live/r216c-<level>-k0-*, cloned to
# r124a-<level>-k0): f2's, f6's and f1's are the three the profile's clip dropped though L3 makes them.  BASES
# doesn't name those clones (f6 and e6 have no entry; f1's, f2's, w3's and e5's are X.7's), so a re-measure takes
# the clones and the BASES override of Step R1.24a's certify scripts (bases.sh, l3_roof_hi.py, in its evidence)
CASES |= {k: dict(v, swim=False) for k, v in {
    "r124a.f2.z189": {"level": "f2", "start": "f2.Z189", "goal": "f2.Z052", "air": 0, "hop": "f2_z103 > f2_z052",
                      "dh": -1.07},
    "r124a.w3.z076": {"level": "w3", "start": "w3.Z076", "goal": "w3.Z099", "air": 3, "hop": "w3_z076 > w3_z099",
                      "dh": -7.72},
    "r124a.f6.z876": {"level": "f6", "start": "f6.Z876", "goal": "f6.Z507", "air": 3, "hop": "f6_z877 > f6_z093"},
    "r124a.f1.z220": {"level": "f1", "start": "f1.Z220", "goal": "f1.Z008", "air": 0, "hop": "f1_z077 > f1_town_side"},
    "r124a.e6.z049": {"level": "e6", "start": "e6.Z049", "goal": "e6.Z050", "air": 0, "hop": "e6_z049 > e6_z047"},
    "r124a.e5.z017": {"level": "e5", "start": "e5.Z017", "goal": "e5.Z122", "air": 1, "hop": "e5_z017 > e5_z122"},
}.items()}


def private() -> Path:
    p = l3.store() / "x11"
    p.mkdir(mode=0o700, exist_ok=True)
    p.chmod(0o700)
    return p


def _read(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def vanilla_xbe() -> bytes:
    from devkit.sim.ports import read_file, vanilla_iso
    return read_file(str(vanilla_iso()), "default.xbe")


# -- the kit ---------------------------------------------------------------------------------------------------------

def air_writes(u32, read, n: int) -> list[tuple[int, bytes]]:
    """Air shield ``n`` worn, its gauge full (placed: what the magic selector 0x838E0 writes for an armor row,
    RAM_RECIPES §3, without spending fuel): the inventory's air level, the armor manager's slot (+0x20), gauge
    (+0x24 = 1.0), mask (+0x2C, air) and level byte (+0x61), and the request block's Flaps flag (+0x03)."""
    c = recipes.chain(u32)
    begin, end = u32(overlay.ARMOR_SLOTS), u32(overlay.ARMOR_SLOTS + 4)
    slot = next(a for a in range(begin, end, overlay.SLOT_SIZE)
                if read(u32(a), 16).split(b"\0")[0] == f"air_shield_{n}".encode())
    return [(c["inv"] + recipes.INV_LEVEL["air"], struct.pack("<i", n)),
            (c["armor_mgr"] + 0x20, struct.pack("<I", slot)),
            (c["armor_mgr"] + 0x24, struct.pack("<f", 1.0)), (c["armor_mgr"] + 0x2C, struct.pack("<i", 2)),
            (c["armor_mgr"] + 0x61, bytes([n])), (c["req"] + 0x03, b"\x01")]


def kit_snapshot(air: int, base: str = BASE) -> str:
    """The label of ``base`` with air shield ``air`` worn (a derived snapshot in the private store, made once)."""
    if air == 0:
        return base
    label = f"x11-{base}-air{air}"
    path = l3.snapshot_path(label)
    if path.exists():
        return label
    src = l3.read_snapshot(l3.snapshot_path(base))
    mem = {va: bytearray(d) for va, d in src.runs}

    def at(va):
        s = max(s for s in mem if s <= va)
        return mem[s], va - s

    def read(va, n):
        b, o = at(va)
        return bytes(b[o:o + n])

    def u32(va):
        return struct.unpack("<I", read(va, 4))[0]
    for va, data in air_writes(u32, read, air):
        b, o = at(va)
        b[o:o + len(data)] = data
    meta = dict(src.meta, label=label, derived={"from": l3.meta_sha12(src.meta), "kit": {"air": air}})
    header = json.dumps({"format": l3.FORMAT, "regs": src.regs, "runs": [[va, len(d)] for va, d in src.runs],
                         "meta": meta}).encode()
    head = l3.MAGIC + struct.pack("<I", len(header)) + header
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(head + bytes(-len(head) % l3.PAGE))
        for va, _ in src.runs:
            f.write(mem[va])
    return label


# -- one value -------------------------------------------------------------------------------------------------------

def _string_sha12(segs, cam) -> str:
    """sha256[:12] of a string's segments and the camera yaw it starts from (floats by their repr)."""
    doc = [[repr(x) if isinstance(x, float) else x for x in s] for s in segs] + [repr(cam)]
    return hashlib.sha256(json.dumps(doc).encode()).hexdigest()[:12]


class NoSwim:
    """A simulator whose step raises ``L3Error`` once the player swims (state 6): a search's branch ends there."""

    def __init__(self, sim):
        self.sim = sim

    def __getattr__(self, name):
        return getattr(self.sim, name)

    def step(self, pad=l3.Pad(), **kw):
        row = self.sim.step(pad, **kw)
        if row.state == 6:
            raise l3.L3Error("the player swims: this case flies")
        return row


def floor_start(sim, router, zone: str, goal) -> dict | None:
    """``l3_certify._start`` on floor samples only: the first of the zone's floor samples nearest the goal that a
    teleport lands on and stays on (standing, not swimming; the 24 nearest, then the 48 nearest a metre or more from
    the floor's edge); where none does, the first on which the body slides
    (state 3: a slope the reach model counts as floor) and is still in the zone after the settle."""
    zn = int(zone.rsplit(".Z", 1)[1])
    node = router.node[:router.ns]
    js = np.nonzero((node >= 0) & (router.R.zone_of[np.maximum(node, 0)] == zn))[0]
    cost = goal.dist[js]
    order = np.lexsort((-router.clear[js], np.where(np.isfinite(cost), cost, 1e9)))
    cells = recipes.chain(sim.u32)["cells"]
    sliding, ranked = None, js[order]
    clear = ranked[router.clear[ranked] >= 1.0]            # then samples a metre from any edge, nearest first
    for v in list(dict.fromkeys(ranked[:24].tolist() + clear[:48].tolist())):
        p = router.pt(v)
        nx = int(goal.nxt[v]) if goal.nxt[v] >= 0 else v
        yaw = cert.heading_to(p, router.pt(nx)) if nx != v else 0.0
        sim.reset()
        cell = (sim.u32(sim.u32(sim.entity + 0x20) + 0x158) - cells) // 0xB4
        sim.teleport(p, yaw, cell=cell)
        r = sim.run([l3.Pad()] * SETTLE)[-1]
        if r.state in (0, 3) and router.zone_at(cert._feet(r)) == zone:
            st = {"teleport": (list(p), yaw, cell), "sample": v, "cell": cell,
                  "how": f"R6 onto a {'floor' if r.state == 0 else 'sliding'} sample of {zone}"}
            if r.state == 0:
                return st
            sliding = sliding or st
    return sliding


class Case:
    """One flight's search set-up: its kit snapshot, start (a teleport onto its start zone, private) and goal."""

    def __init__(self, key: str, xbe: bytes):
        self.key, self.c, self.xbe = key, CASES[key], xbe
        if self.c["level"] not in BASES:
            raise SystemExit(f"{key}: no kit 0 snapshot of {self.c['level']} (BASES)")
        self.label = kit_snapshot(self.c["air"], BASES[self.c["level"]])
        lvl = self.c["level"]
        self.reach, zoning = str(cert._reach_path(lvl)), cert.pr.zoning(cert.read_derived(lvl))
        self.prof = self.c.get("prof", "logic")
        router = load_router(self.reach, self.prof)
        priv = private() / f"{key}.json"
        self.priv = _read(priv, {})
        if self.priv and (self.priv.get("zoning", cert._stamp(cert.private() / "reach" / f"{lvl}.pkl")) != zoning
                          or self.priv.get("prof", "logic") != self.prof):
            self.priv = {}              # its start, seed and strings were made on another reach model or graph
        self.priv |= {"zoning": zoning, "prof": self.prof}
        goal = RouteGoal(router, self.c["goal"], air=self.c["air"])
        self.swim = self.c.get("swim", True)
        if "start" not in self.priv:
            sim = l3.L3(l3.read_snapshot(l3.snapshot_path(self.label)), xbe)
            st = (cert._start(sim, router, {"start": self.c["start"]}, goal) if self.swim
                  else floor_start(sim, router, self.c["start"], goal))
            if st is None:
                raise SystemExit(f"{key}: no sample of {self.c['start']} lands and settles there")
            self.priv["start"] = st
            sim.reset()
            seg = Segment(self.label, teleport=st["teleport"], settle=SETTLE)
            from devkit.sim.l3_search import start_of
            _, row, _, _, _ = start_of(sim, seg)
            self.priv["route_seed"] = route_seed(goal.R, cert._feet(row), self.c["goal"], air=self.c["air"])
            self.priv.setdefault("winners", [])
            _write(priv, self.priv)
            priv.chmod(0o600)
        self.spec = {"module": cert.GOAL_MODULE, "factory": "make_goal",
                     "kwargs": {"reach": self.reach, "target": self.c["goal"], "prof": self.prof, "air": self.c["air"]}}

    def segment(self, ov=None) -> Segment:
        return Segment(self.label, teleport=self.priv["start"]["teleport"], settle=SETTLE, overlay=ov)

    def keep(self, res: dict, ov: str | None, rate: float = 30.0) -> None:
        """A winner's string (and the overlay it won under), to seed the next values (private; read again first,
        so runs of one case in two processes keep each other's)."""
        if not res.get("reached"):
            return
        path = private() / f"{self.key}.json"
        self.priv["winners"] = _read(path, self.priv)["winners"]
        if res["segs"] not in [w["segs"] for w in self.priv["winners"]]:
            self.priv["winners"].append({"segs": res["segs"], "cam": res["cam"], "overlay": ov,
                                         "robustness": res.get("robustness"), "rate": rate})
            tmp = path.with_suffix(".tmp")
            _write(tmp, self.priv)
            tmp.chmod(0o600)
            tmp.replace(path)


def grade(w, seg: Segment, spec: dict, segs: list, trials: int, swim: bool = True, rate: float = 30.0) -> dict:
    """A pool task: a known string from ``seg``'s start (the overlay's) to the goal: whether it still reaches
    (``l3_search.confirm``) and its robustness at the build's frame ``rate`` (``swim`` False: a run that swims
    fails)."""
    from devkit.sim.l3_search import confirm, robustness, start_of
    sim = w.sim(seg.scene, deep=False, overlay=seg.overlay)
    sim = sim if swim else NoSwim(sim)
    goal = w.goal(spec)
    start, _, cam, _, _ = start_of(sim, seg)
    segs = [Seg(*x) for x in segs]
    ticks = confirm(sim, start, segs, cam, goal)
    return {"reached": ticks is not None, "ticks": ticks, "segs": [list(x) for x in segs], "cam": cam,
            "robustness": robustness(sim, start, segs, goal, cam=cam, trials=trials, rate=rate) if ticks else None}


def fly(w, seg: Segment, spec: dict, limits: Limits, i: int, seed: int, strings, trials: int, swim: bool,
        rate: float = 30.0) -> dict:
    """A pool task: ``l3_pool.search_task`` (one seed's search and its winner's robustness at the build's frame
    ``rate``), where with ``swim`` False a run that swims ends its branch."""
    from devkit.sim.l3_search import robustness, search, start_of
    sim = w.sim(seg.scene, deep=False, overlay=seg.overlay)
    sim = sim if swim else NoSwim(sim)
    goal = w.goal(spec)
    start, row, cam, _, _ = start_of(sim, seg)
    res = search(sim, start, row, goal, limits, cam=cam, seed=seed, seeds=strings)
    out = {"index": i, "seed": seed, **res.summary(), "segs": [list(x) for x in res.segs], "cam": cam}
    if res.reached:
        out["robustness"] = robustness(sim, start, res.segs, goal, cam=cam, trials=trials, seed=seed, rate=rate)
    return out


def rescale(segs: list, w: dict, rate: float) -> list:
    """A winner's string at another frame rate: each segment's ticks (and its held, roll and cast ticks) scaled by
    the rates' ratio, so the presses fall at the same times (a winner from before Step X.18 kept no rate: 30 when
    it won on vanilla, else left as it is)."""
    src = w.get("rate") or (30.0 if w.get("overlay") is None else rate)
    if src == rate:
        return segs
    out = []
    for x in segs:
        x = list(x)
        n = max(1, round(x[0] * rate / src))
        out.append([n, x[1], *(min(n, max(1, round(k * rate / src))) if k else 0 for k in x[2:])])
    return out


def limits_at(rate: float, steps: int, shape: dict | None = None) -> Limits:
    """The search's budget and shape at ``rate`` frames a second.  ``Limits`` counts ticks (the step budget, the
    longest string, a segment, Y's hold, the most ticks in the air, and the wall cap with the budget), so at F fps
    each is F/30 times vanilla's: the same game time (AZ-372: f3_z042 > f3_z235 flies 2.3-3.4 s, past 120 ticks in
    the air at 60 fps, so no search found it there).  At 30 the limits are vanilla's own; ``shape`` wins."""
    k, base = rate / 30.0, Limits()
    scaled = {} if k == 1 else {f: round(getattr(base, f) * k) for f in ("ticks", "seg", "hold", "fall")}
    return Limits(steps=round(steps * k), wall_cap_s=3600.0 * max(1.0, k), **(scaled | (shape or {})))


def spec_at(spec: dict, rate: float) -> dict:
    """The goal ``spec`` at ``rate`` frames a second: the landing held for the same time at rest as at 30 (its
    ``settle`` ticks times F/30; at 120 fps most strings that touched f3.Z235 for 10 ticks died within the second,
    AZ-372)."""
    k = rate / 30.0
    return spec if k == 1 else {**spec, "kwargs": {**spec["kwargs"], "settle": round(10 * k)}}


def point(pool, case: Case, ov, steps: int, seeds: int, trials: int = 16, shape: dict | None = None,
          rate: float = 30.0) -> dict:
    """At the overlay ``ov`` (None: vanilla): every string the earlier values won with, graded (still reaching?
    robust?), and ``seeds`` searches seeded only by the route planner's plan (so they find their own strings),
    each to its own end: whether any reached, the most robust winner's robustness and the tier it supports,
    counts and taint (public), the winners kept (private)."""
    seg, limits, spec = case.segment(ov), limits_at(rate, steps, shape), spec_at(case.spec, rate)
    name = problem_sha12(seg, spec, limits)
    t0 = time.monotonic()
    known = sorted(case.priv.get("winners", []), key=lambda w: -(w.get("robustness") or 0.0))[:8]
    graded = pool.map(grade, [(seg, spec, rescale(w["segs"], w, rate), trials, case.swim, rate) for w in known])
    seed = [[tuple(x) for x in case.priv["route_seed"]]] if case.priv.get("route_seed") else []
    runs = pool.map(fly, [(seg, spec, limits, i, derived_seed(name, i), seed, trials, case.swim, rate)
                          for i in range(seeds)])
    for r in runs:
        case.keep(r, None if ov is None else ov.sha12, rate)
    best = max((r for r in graded + runs if r["reached"]), key=lambda r: r.get("robustness") or 0.0, default=None)
    rob = None if best is None else best.get("robustness") or 0.0
    tier = None if best is None else next(t for t, f in TIERS if rob >= f)
    return {"problem": name, "overlay": None if ov is None else ov.sha12, "reached": best is not None,
            "robustness": rob, "tier": tier, "seconds": round(time.monotonic() - t0, 1),
            "string": None if best is None else _string_sha12(best["segs"], best["cam"]),
            "ticks": None if best is None else best["ticks"],
            "known": [{"reached": g["reached"], "robustness": g["robustness"]} for g in graded],
            "runs": [{k: r[k] for k in ("index", "reached", "why", "ticks", "steps", "taint", "best_cost_s")}
                     | {"robustness": r.get("robustness")} for r in runs]}


# -- bisection -------------------------------------------------------------------------------------------------------

def passes(p: dict, floor: float) -> bool:
    return p["reached"] and (p["robustness"] >= floor if floor > 0 else True)


def regrade(pool, case: Case, ov=None, trials: int = 16, rate: float = 30.0) -> dict:
    """Every string the case has won with (at any value), graded from the start under the overlay ``ov`` (None:
    vanilla); how many, whether one reaches and the best robustness."""
    seg, ws = case.segment(ov), _read(private() / f"{case.key}.json", case.priv)["winners"]
    graded = pool.map(grade, [(seg, spec_at(case.spec, rate), rescale(w["segs"], w, rate), trials, case.swim, rate)
                              for w in ws])
    ok = [g["robustness"] or 0.0 for g in graded if g["reached"]]
    return {"strings": len(ws), "reached": bool(ok), "robustness": max(ok, default=None)}


def measure(key: str, slider: str, out: Path, steps: int, seeds: int, workers: int | None,
            lo: float | None, hi: float | None, tol: float | None, at_values=(), shape: dict | None = None) -> dict:
    """Bisect ``slider`` (``pack.name``) on each side of vanilla named by ``lo``/``hi`` (its far ends) for the
    tiers frame_perfect and standard: the last value that passes and the first that fails, per side and tier;
    and grade each of ``at_values`` alone.  Results accumulate in ``out/results.json`` (a value is run once).
    A value fails only once every string the case has won with (at any value) is graded there too (``regrade``),
    and the bisection runs a second time once all are in.
    A tier's robustness floor is vanilla's own where L3 rates the flight below the tier at vanilla (as
    ``physics.keeps`` keeps a flight the calculator can't reproduce only while no weaker than vanilla), vanilla's
    robustness being the best of its own point and of every string the case won with graded at vanilla after the
    bisection; a side where vanilla doesn't reach isn't measured."""
    from devkit.sim.ports import get_pack
    from devkit.reach.l3_pool import Pool
    xbe = vanilla_xbe()
    case = Case(key, xbe)
    pack, name = slider.split(".")
    site = next(s for s in (*get_pack(pack).parametric_sites(), *get_pack(pack).xbr_parametric_sites())
                if s.name == name)
    v0 = 30.0 if name == "target_fps" else float(site.default)   # the pack's default is its value when on
    whole = name.endswith("_flaps") or name == "target_fps"
    tol = tol or (1.0 if whole else 0.01 * v0)
    doc_path = out / "results.json"
    doc = _read(doc_path, {})
    rec = doc.setdefault(key, {}).setdefault(slider, {"vanilla": v0, "points": {}, "sides": {}})
    rec.update(case=CASES[key], steps=steps, seeds=seeds, snapshot=case.label,
               snapshot_meta_sha12=l3.meta_sha12(l3.read_meta(l3.snapshot_path(case.label))))

    overlays: dict = {}

    def rate(v: float) -> float:
        """The frame rate at ``v`` (a string from another rate is rescaled to it: ``rescale``)."""
        return v if name == "target_fps" else 30.0

    def ov_at(v: float):
        if v != v0 and v not in overlays:
            overlays[v] = overlay.build(xbe, {pack: {name: v}}, f"{slider}={v:g}")
        return overlays.get(v)

    def at(v: float) -> dict:
        k = repr(round(v, 6))
        if k not in rec["points"]:
            rec["points"][k] = dict(point(pool, case, ov_at(v), steps, seeds, shape=shape, rate=rate(v)), value=v)
            _write(doc_path, doc)
            p = rec["points"][k]
            print(f"{key} {slider}={v:g}: reached {p['reached']} robustness {p['robustness']} tier {p['tier']} "
                  f"({p['seconds']} s)", flush=True)
        return rec["points"][k]

    def ok(v: float, fl: float) -> bool:
        """``v`` passes at the robustness floor ``fl``: its point, or else every known string graded there (again
        when strings were won since)."""
        p = at(v)
        if passes(p, fl):
            return True
        known = len(_read(private() / f"{case.key}.json", case.priv)["winners"])
        if (p.get("regraded") or {}).get("strings", -1) < known:
            p["regraded"] = regrade(pool, case, ov_at(v), rate=rate(v))
            _write(doc_path, doc)
            print(f"{key} {slider}={v:g} regraded: {p['regraded']}", flush=True)
        return passes(p["regraded"], fl)

    def floor(tier: str) -> float | None:
        """The tier's robustness floor (None: vanilla doesn't reach)."""
        ps = [p for p in (base, base.get("regraded"), rec.get("vanilla_regraded")) if p and p["reached"]]
        if not ps:
            return None
        f = dict(TIERS)[tier]
        return min(f, max(p["robustness"] or 0.0 for p in ps)) if f > 0 else 0.0

    def sides() -> None:
        for far in (x for x in (lo, hi) if x is not None):
            side = "below" if far < v0 else "above"
            for tier in ("frame_perfect", "standard"):
                fl = floor(tier)
                if fl is None:
                    rec["sides"][f"{side}.{tier}"] = {"pass": None, "fail": v0, "why": "vanilla fails"}
                    continue
                cands = []                      # widen from vanilla: 1/16 of the way to the far end, 1/8, ...
                for f in (1 / 16, 1 / 8, 1 / 4, 1 / 2, 1.0):
                    v = v0 + (far - v0) * f
                    v = float(round(v)) if whole else v
                    if v != v0 and v not in cands:
                        cands.append(v)
                good, bad = v0, None
                for v in cands:
                    if not ok(v, fl):
                        bad = v
                        break
                    good = v
                while bad is not None and abs(bad - good) > tol + 1e-12:
                    mid = (good + bad) / 2
                    if whole:
                        mid = float(math.floor(mid) if bad > good else math.ceil(mid))
                        if mid in (good, bad):
                            break
                    good, bad = (mid, bad) if ok(mid, fl) else (good, mid)
                rec["sides"][f"{side}.{tier}"] = {"pass": good, "fail": bad, "floor": fl}
                _write(doc_path, doc)
                print(f"{key} {slider} {side} {tier} (floor {fl:g}): passes at {good:g}, fails at {bad}", flush=True)

    with Pool(case.label, xbe, workers=workers, name="l3 contact") as pool:
        base = at(v0)
        for v in at_values:             # single values (no bisection)
            at(v)
        sides()
        rec["vanilla_regraded"] = regrade(pool, case)
        _write(doc_path, doc)
        print(f"{key} {slider} vanilla regraded: {rec['vanilla_regraded']}", flush=True)
        sides()                         # again: its floor and every failing value with every string won since
    return rec


# -- walk-offs -------------------------------------------------------------------------------------------------------

DROPS = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 16.0)   # physics.FREE_CARRY_DROPS: the free walk-off table
TAKEOFF_BEFORE_END = 0.25                                       # the router's takeoff: this far before the floor's end


def ledges(router, n: int = 40, drop: float = 10.0) -> list[dict]:
    """``n`` walk-offs of the level's reach model (region edges of kind ``drop``) with at least ``drop`` m of fall
    and 1 m of straight floor behind the takeoff (the run ramps to full speed in 3-4 ticks, under 1 m), the widest
    gaps first (the longest free arcs), one per takeoff region: each its takeoff (the router's: 0.25 m before the
    takeoff floor ends on its track), unit track, the floor behind it and the drop (private)."""
    from devkit.rando.draft import route as rt
    R, out, seen = router, [], set()
    ks = np.nonzero(R.kind == rt.K_EDGE)[0].tolist()
    for k in sorted(ks, key=lambda k: -(R.edges[int(R.eid[k])][2].get("gap") or 0.0)):
        e = R.edges[int(R.eid[k])][2]
        u, w = int(R.src[k]), int(R.dst[k])
        if e["kind"] != "drop" or u >= R.ns or w >= R.ns or R.Z[w] - R.Z[u] > -drop or int(R.node[u]) in seen:
            continue
        at = R._takeoff(u, w, e)
        p, q = R.pt(u), R.pt(w)
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        if d < 0.5:
            continue
        ux, uy = (q[0] - p[0]) / d, (q[1] - p[1]) / d
        back, _ = R.run_on(at, (-ux, -uy), int(R.node[u]), 3.0)
        if back < 1.0:
            continue
        seen.add(int(R.node[u]))
        out.append({"at": at, "u": (ux, uy), "back": back, "drop": float(R.Z[u] - R.Z[w]), "zone": R.zone_at(at)})
        if len(out) == n:
            break
    return out


def walk_off(sim, ledge: dict, ticks: int = 90) -> dict:
    """Run straight off ``ledge`` from as far behind its takeoff as its floor runs (at most 3 m) at full stick:
    the leave tick, the body's place then and, per drop of :data:`DROPS`, how far past the floor's end (the
    takeoff + 0.25 m) the body is when the feet first stand that far under the leave height (missing: not
    reached in the air)."""
    (ax, ay, az), (ux, uy) = ledge["at"], ledge["u"]
    h, run_m = math.atan2(-ux, uy), ledge["back"] - 0.1
    sim.reset()
    sim.teleport((ax - ux * run_m, ay - uy * run_m, az), h)
    sim.run([l3.Pad((0.0, 0.0), frozenset(), h)] * SETTLE)
    rows = sim.run([l3.Pad((0.0, 1.0), frozenset(), h)] * ticks)
    end = TAKEOFF_BEFORE_END

    def along(r):
        return (r.pos[0] - ax) * ux + (r.pos[1] - ay) * uy
    leave = next((i for i in range(1, len(rows)) if rows[i].state == 2 and rows[i - 1].state != 2), None)
    if leave is None:
        return {"leave": None}
    z0 = rows[leave - 1].pos[2]
    reach = {}
    for dd in DROPS:
        for i in range(leave, len(rows)):
            if rows[i].state != 2:
                break
            if rows[i].pos[2] <= z0 - dd:
                a, b = rows[i - 1], rows[i]
                t = (a.pos[2] - (z0 - dd)) / (a.pos[2] - b.pos[2])
                reach[dd] = round(along(a) + t * (along(b) - along(a)) - end, 4)
                break
    return {"leave": leave, "leave_past_end_m": round(along(rows[leave - 1]) - end, 4),
            "speed": round(math.hypot(*rows[leave - 1].obs.vel[:2]), 4), "reach": reach}


def walkoff(out: Path, n: int) -> dict:
    """The free walk-off table (``physics.free_certs``: a zone may walk off a ledge ``d`` m down onto a floor as
    far as vanilla's carry + ``physics.WALKOFF_SLACK`` from the ledge's end) on ``n`` real w1 ledges: the reach past the floor's end
    per drop at vanilla, and per movement slider the value at which the least reach over the ledges and drops
    falls under the table's gap (bisection; each value one run per ledge, no search)."""
    from devkit.rando import physics as ph
    xbe = vanilla_xbe()
    router = cert._router("w1")
    snap = l3.read_snapshot(l3.snapshot_path(BASE))
    sim0 = l3.L3(snap, xbe)
    cand = []                   # clean ledges: at vanilla the run leaves within 0.5 m of the floor's end at full speed
    for c in ledges(router):
        r = walk_off(sim0, c)
        if r.get("leave") and abs(r["leave_past_end_m"]) <= 0.5 and r["speed"] >= 6.95 and len(r["reach"]) >= 6:
            cand.append(c)
        if len(cand) == n:
            break
    if not cand:
        raise SystemExit("no clean ledge: no walk-off of the reach model leaves at its floor's end at full speed")
    _write(private() / "walkoff.json", {"ledges": cand})
    calc = {dd: ph.Physics(ph.VANILLA).walk_off_carry(dd) for dd in DROPS}
    doc = {"ledges": [{"drop_m": round(c["drop"], 2), "zone": c["zone"]} for c in cand],
           "calc_carry_m": {str(k): round(v, 4) for k, v in calc.items()}, "runs": {}, "thresholds": {}}

    def worst(params: dict) -> tuple[float, list]:
        ov = overlay.build(xbe, params) if params else None
        sim = l3.L3(snap, xbe, overlay=ov)
        runs = [walk_off(sim, c) for c in cand]
        slack = [r["reach"][dd] - calc[dd] - ph.WALKOFF_SLACK for r in runs if r.get("leave") for dd in r["reach"]]
        return min(slack, default=-math.inf), runs

    base, runs = worst({})
    doc["runs"]["vanilla"] = runs
    doc["vanilla_least_slack_m"] = round(base, 4)
    # the arc alone: L3's carry from the last tick on the ground against the calculator's (both from the leave)
    doc["arc_minus_calc_m"] = [{str(dd): round(r["reach"][dd] - r["leave_past_end_m"] - calc[dd], 4)
                                for dd in r["reach"]}
                               for r in runs]
    if base < 0:                 # vanilla itself carries less than the zone model assumes: no margin to measure
        doc["thresholds"] = "none: at vanilla the least reach is under the zone model's walk-off by " \
                            f"{-base:.3f} m"
        _write(out / "walkoff.json", doc)
        print(f"walk-off: {doc['thresholds']}", flush=True)
        return doc
    for pack, name, far in (("player_physics", "walk_speed_scale", 0.25), ("player_physics", "gravity", 39.2),
                            ("player_physics", "air_control_scale", 0.25)):
        v0 = 9.8 if name == "gravity" else 1.0
        good, bad = v0, far
        for _ in range(14):
            mid = (good + bad) / 2
            s_, r_ = worst({pack: {name: mid}})
            doc["runs"][f"{name}={mid:.5g}"] = r_
            good, bad = (mid, bad) if s_ >= 0 else (good, mid)
            if abs(bad - good) <= 0.001 * v0:
                break
        doc["thresholds"][f"{pack}.{name}"] = {"pass": round(good, 5), "fail": round(bad, 5)}
        print(f"walk-off {pack}.{name}: holds to {good:.5g}, fails at {bad:.5g}", flush=True)
    _write(out / "walkoff.json", doc)
    return doc


# -- apply -----------------------------------------------------------------------------------------------------------

CONTACT = Path(__file__).resolve().parents[2] / "src" / "azurkit" / "tools" / "randomizer" / "data" / "contact.json"
SIDE_TIERS = ("frame_perfect", "standard")


def _field(slider: str) -> tuple[str, float]:
    """A slider's Movement field (``physics.SLIDERS``; the flaps per shield ``flaps1`` .. ``flaps3``) and the
    factor from the slider's value to the field's."""
    from devkit.rando.physics import SLIDERS
    fld, how = SLIDERS[tuple(slider.split("."))]
    return (f"flaps{how + 1}", 1.0) if fld == "flaps" else (fld, how or 1.0)


def monotone(rec: dict, side: str, tier: str) -> bool:
    """Whether every value tried on ``side`` of vanilla past its first failing one fails too at ``tier`` (its
    point or its regrade under the side's floor): the bisection's assumption, which a fragile flight's search luck
    breaks (then L3 doesn't decide that side)."""
    fl = (rec["sides"].get(f"{side}.{tier}") or {}).get("floor", dict(TIERS)[tier])
    v0 = rec["vanilla"]
    pts = [p for p in rec["points"].values() if (p["value"] < v0 if side == "below" else p["value"] > v0)]
    good = {id(p): passes(p, fl) or (p.get("regraded") is not None and passes(p["regraded"], fl)) for p in pts}
    fails = [abs(p["value"] - v0) for p in pts if not good[id(p)]]
    return not fails or not any(good[id(p)] for p in pts if abs(p["value"] - v0) > min(fails))


def apply(dirs: list[Path], out: Path = CONTACT) -> dict:
    """``contact.json`` from the ``measure`` results in ``dirs``: per case, its certificate (the derive's for
    its zone edge and air rank, which must be in its level's movement file) and per slider and tier the range
    measured (``[lo, hi]`` in the Movement field's units; None: that side not measured), with each one's
    evidence id (the evidence folder, case, slider and the snapshot's metadata hash, and the string that last
    passed on each side).  A side L3 doesn't decide (vanilla doesn't reach, or not ``monotone``) stays None."""
    from devkit.rando.draft.author import read_derived
    from azurkit.tools.randomizer.planner.loader import DATA_DIR, FORMATS
    flights: dict[str, dict] = {}
    for d in dirs:
        posix = d.resolve().as_posix()      # an evidence id names the folder under evidence/, never a home path
        where = posix.split("/evidence/", 1)[1] if "/evidence/" in posix else d.name
        for key, sliders in _read(d / "results.json", {}).items():
            c = CASES[key]
            cert = next(o["cert"] for e in read_derived(c["level"])["edges"]
                        if (e["from"], e["to"]) == (c["start"], c["goal"])
                        for o in (e.get("options") or [e]) if (o.get("cert") or {}).get("rank") == c["air"]
                        and c.get("dh", o["cert"]["dh"]) == o["cert"]["dh"])
            movement = json.loads((DATA_DIR / "movement" / f"{c['level']}.json").read_text(encoding="utf-8"))
            if cert not in movement["certs"]:
                raise SystemExit(f"{key}: its certificate is in no movement file of {c['level']} (re-author?)")
            f = flights.setdefault(key, {"level": c["level"], "hop": c["hop"], "edge": [c["start"], c["goal"]],
                                         "kit": {"air": c["air"]}, "cert": cert, "ranges": {}, "evidence": {}})
            for slider, rec in sliders.items():
                fld, k = _field(slider)
                for tier in SIDE_TIERS:       # a side where vanilla doesn't reach, or not monotone: unmeasured
                    lo, hi = ((s_ if s_ and s_["pass"] is not None and monotone(rec, side, tier) else None)
                              for side, s_ in (("below", rec["sides"].get(f"below.{tier}")),
                                               ("above", rec["sides"].get(f"above.{tier}"))))
                    for side in ("below", "above"):
                        if rec["sides"].get(f"{side}.{tier}") and not monotone(rec, side, tier):
                            print(f"{key} {slider} {side} {tier}: not monotone, left to the calculator", flush=True)
                    if lo is None and hi is None:
                        continue
                    f["ranges"].setdefault(fld, {})[tier] = [None if s_ is None else round(s_["pass"] * k, 6)
                                                             for s_ in (lo, hi)]
                if fld not in f["ranges"]:
                    continue
                last = {side: next((p["string"] for p in rec["points"].values()
                                    if p["value"] == (rec["sides"].get(f"{side}.frame_perfect") or {}).get("pass")),
                                   None) for side in ("below", "above")}
                f["evidence"][fld] = (f"l3:{where}:{slider}@{rec['snapshot_meta_sha12']}"
                                      + "".join(f"/{side}:{s_}" for side, s_ in last.items() if s_))
    doc = {"format": FORMATS["contact"], "flights": [flights[k] for k in sorted(flights)], "free": {}}
    out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return doc


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("measure")
    p.add_argument("case", choices=sorted(CASES))
    p.add_argument("slider", help="pack.slider, e.g. player_physics.jump_speed_scale")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--steps", type=int, default=60_000)
    p.add_argument("--seeds", type=int, default=16)
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--lo", type=float, default=None, help="the far end below vanilla (none: not searched)")
    p.add_argument("--hi", type=float, default=None, help="the far end above vanilla (none: not searched)")
    p.add_argument("--tol", type=float, default=None)
    p.add_argument("--at", type=float, action="append", default=[], help="a value to grade alone (repeatable)")
    p.add_argument("--temp", type=float, default=None, help="the search's temp (a broader exploration: 30)")
    p.add_argument("--pursue", type=float, default=None, help="the share of guided segments (broader: 0.3)")
    p = sub.add_parser("apply")
    p.add_argument("dirs", type=Path, nargs="+")
    p = sub.add_parser("walkoff")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--ledges", type=int, default=3)
    a = ap.parse_args(argv)
    if a.cmd == "measure":
        shape = {k: v for k, v in (("temp", a.temp), ("pursue", a.pursue)) if v is not None}
        measure(a.case, a.slider, a.out, a.steps, a.seeds, a.workers, a.lo, a.hi, a.tol, a.at, shape)
    elif a.cmd == "walkoff":
        walkoff(a.out, a.ledges)
    elif a.cmd == "apply":
        apply(a.dirs)


if __name__ == "__main__":
    main()
