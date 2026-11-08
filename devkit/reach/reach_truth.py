"""The reach engine's truth set (Step R2.19c; D825, D845, D846): R, the reference search, on a seeded stratified
sample of a level's zone pairs, each pair's result frozen, so the engine's recall is measured against more than its
own finds.

``frame`` writes a level's frame (``reach_engine.candidates.frame``, there since Step R2.19g2, which the engine's
pair stage reads too): the ordered zone pairs inside a widened envelope per kit (``k0``: rank 0, no shield;
``air3``: the shield's rank 3, Flaps 5), in strata ``dm`` (a derived jump or flap edge of the pair, modelled), ``dp``
(one probe-needed, none modelled) and ``nd`` (no derived edge at all), each crossed with the kit, each stratum's pairs
in a seeded order, so a sample is the first N and a larger one holds every smaller one.  The frame file is written
once.

``run`` runs R on the next ``--take`` pairs of each ``--strata`` (from ``--skip``) on an L3 pool (FastL3 by default):
first an aim at the pair with every pass of ``reach_engine.aim`` (the six; ``stop`` at the kit's rank), from the
derived flight where the pair has one, else from the two zones' points that the envelope's slack ranks best (a run
jump; with air3 Flaps 5, the sixth pass on the envelope's schedule); where it holds no find, the refinement's
launches at the same target (``aim.refine``, twinned to the aim), R0's fan and the roll jumps from the from-zone's
regions under 4 m2 (the refinement's small fan) and :data:`FAN_N` of its takeoffs nearest the to-zone at
:data:`FAN_TURNS` off the heading to it, R0's 14 launches each.  A pair is real when a witness of those jobs lands in
the to-zone from a start in the from-zone at the kit's rank or under and its body stays there the hold's 60 idle
ticks (``reach_engine.hold``; a found witness is the evidence, D277, D661).  Each pair's result (real, the least
rank, which job found it, its jobs' keys, the CPU-seconds and L3 ticks its new jobs and holds took) goes to the
private ``truth/<name>.jsonl`` with the code that made it (the L3 core, the aim core, this file, the pair aim's
``reach_engine.candidates``, ``--l3`` and the library), and a pair already there is never run again (frozen).
``--quota N`` (Step R2.19c3, PLAN-v2 §1.3's thin levels) runs rounds instead, each stratum's next pairs in its order
until it holds ``--per`` R-real links or ``--cap`` pairs, then the stratum with the highest real rate until the
strata hold N R-real links in all (:func:`_takes`).  FastL3 decides every pair (D845); a fast invocation's jobs are
audited as ``reach_engine.py run``'s (about 1 in 500 again on base L3, 1 in 1,000 under the x87 check) before its pairs
are frozen, and a difference freezes none.  The output's ``sample`` gives each stratum's inverse-probability weight (its
frame's pairs / its sampled ones) and the frame's R-real links they estimate.  ``recall`` reads such results beside
``reach_engine.py graph``'s zone edges: the engine's recall against R per stratum (Wilson 95 % intervals) and pooled by
those weights (Wilson's interval on the R-real links' Kish effective number; a pair frozen under two names counts once),
R's misses (the engine's finds R didn't make: never added to R's denominator) and :data:`KNOWN_REAL`'s links on the
level.

Step R2.19c2a (PLAN-v3's c2a, NS.0(a)): ``run --backend kernel`` runs R's jobs on the native kernel route
(``reach_native.backend``: each launch on the kernel, a flagged one on FastL3, keys apart), so the kernel only
proposes and FastL3 still decides each pair (D845: an aim's hit is confirmed as it is found, every other candidate at
the hold); each row then holds the pair's candidates before the confirm (kernel or FastL3 launches) and each tried
one's FastL3 answer, and with ``--refly`` each kernel candidate whose confirm failed flies once more on FastL3 under its
own closed-loop controller from its start's FastL3 twin (its job run again on the kernel up to that launch), then held
from the snapshot (:func:`refly_task`).  ``--like NAME ...`` takes the pairs frozen under those names (``--strata``'s),
``--pairs FROM>TO:KIT ...`` named pairs (stratum ``known-<kit>``, no frame needed).  ``calib`` reads a kernel run
against FastL3 rows of the same pairs: per stratum the FastL3-R real pairs the kernel run keeps alone and with its
re-fly, the confirms that failed by their FastL3 end, and the false-positive factor (pairs with a kernel candidate /
real pairs).  ``generate`` is the independent generator (PLAN-v2 §1.2 item 3): per pair :data:`GEN_STRINGS`
open-loop random strings on the kernel, each from a random border point of the from-zone (its kernel start and kit
settled once), a heading within :data:`GEN_CONE` of the bearing to the to-zone, the camera turned to it at the pad's
rate, the stick full along it, Y pressed after a random run-up and, with air3, flaps and recasts on random ticks; the
stick rests from the first touch-down until the body has settled (:func:`_kfly`).  A string the kernel lands settled
in the to-zone at the kit's rank or under is a candidate FastL3 confirms with the hold (fewest ticks first, at most
:data:`GEN_CONFIRMS`); while none stays, at most :data:`GEN_FLAGGED` of the strings the kernel flagged fly on FastL3
(:func:`_l3fly`) and a landing there is held.  With ``--against NAME ...`` each pair the generator holds and those
rows' R doesn't is classed: R's aim and refinement from the generator's start at its landing, on the kernel route,
find it (``targeting``: R had the moves, it aimed elsewhere) or not (``movement``).  ``chapman`` reads R, the
engine's graph and the generator on the same pairs: per stratum Chapman's estimate of the links (R or the engine as
the first capture, the generator the second), the links both R and the engine miss (a share of R's real links) and
the generator's links R missed by class, pooled by the frame's weights.

Step R2.19c2b (PLAN-v3's c2b, the bulk): ``--strata`` takes c1's slack-band strata too, :data:`BANDS`
(``candidates.tier``'s split of nd-air3: near at ``BAND_M`` or deeper inside the envelope, else far); a band's
``--take`` / ``--skip`` count its own pairs in nd-air3's order and its rows stay ``nd-air3``'s.  ``run``'s ``sample``
and ``recall`` weigh nd-air3 by band, and ``recall`` counts a pair frozen under several names once, real when any
name's R held it (a re-fly's find too).

    uv run --locked python -m devkit reach reach-truth frame LEVEL [--seed 219] --out COUNTS.json
    nice -n 10 uv run --locked python -m devkit reach reach-truth run LEVEL --snapshot LABEL --name NAME
        [--strata nd-k0 ...] (--take N [--skip K] | --quota N [--per 50] [--cap 100] [--step 20] | --like NAME ...
        | --pairs FROM>TO:KIT ...) [--seed 219] [--workers N] [--l3 fast|base] [--backend l3|kernel [--refly]]
        --out RUN.json
    uv run --locked python -m devkit reach reach-truth recall LEVEL --name NAME ... --graph EDGES.json --out RECALL.json
    uv run --locked python -m devkit reach reach-truth calib LEVEL --kernel NAME --fast NAME ... --out CALIB.json
    nice -n 10 uv run --locked python -m devkit reach reach-truth generate LEVEL --snapshot LABEL --name NAME
        [--strata nd-k0 ...] (--take N [--skip K] | --like NAME ... | --pairs FROM>TO:KIT ...) [--strings 20000]
        [--flagged 50] [--confirms 10] [--seed 219] [--workers N] [--against NAME ...] --out GEN.json
    uv run --locked python -m devkit reach reach-truth chapman LEVEL --r NAME ... --gen NAME --graph EDGES.json
        --out CHAPMAN.json

Outputs (``l3.private_out``: mode 0600, never over a file) hold zone ids, counts, ticks and seconds; the frame, the
jobs and each pair's witness keys stay in the AzurKit user cache's ``reach-engine/<level>/truth`` (mode 700).  Dev
tooling: never in pytest, never a CLI verb.
"""

from __future__ import annotations

import argparse
import ctypes
import gzip
import json
import math
import struct
import sys
import time
from pathlib import Path

import numpy as np

from devkit.reach import reach_engine as RE  # noqa: E402

from devkit.reach.engine import aim, cache, hold, runner  # noqa: E402
from devkit.reach.engine import candidates as C  # noqa: E402
from devkit.reach.engine.candidates import KITS, SEED, STRATA, _reach, _sha  # noqa: E402
from devkit.reach.engine.graph import Graph  # noqa: E402
from devkit.reach.engine.macros import (  # noqa: E402
    AIR_CAP, AIRBORNE, DEAD, JUMP_HOLD, R0, RUN_CAP, SETTLE, STILL, STUCK, SWIMMING, TICKS, min_rank)
from devkit.sim import l3  # noqa: E402
from devkit.sim.inputs import CAM_RATE, heading_to, stick, wrap  # noqa: E402
from devkit.sim.l3_search import segments  # noqa: E402
from devkit.sim.obs import settled  # noqa: E402

FAN_N = 2             # [default D115, PLAN-v2 arith §3's N] R's local fan: this many takeoffs of the from-zone
FAN_TURNS = (0.0, math.radians(20.0), -math.radians(20.0))   # [default D115] ... at these off the heading to the
                                                              # to-zone (PLAN-v2: 3 headings facing it)
QUOTA_PER, CAP, STEP = 50, 100, 20   # [default D115, Step R2.19c3] ``run --quota``'s R-real links a stratum, its pairs
                                     # a stratum before the top-up, and a stratum's take a round while it holds
                                     # no R-real link (:func:`_takes`)
KNOWN_REAL = (        # links seen in game (owner demos), by zone at the zoning named (D634, the v1.1 inventory's
                      # DEC-14; X.67's per-frame trace, owner-2026-10-24): c2's class check
    {"level": "w2", "zoning": "2640f2a8437e", "from": "w2.Z050", "to": "w2/phys/2fa5a7cd103a", "kind": "touch",
     "air": 3, "jumps": 1, "flaps": 1, "casts": 1, "trace": "clk 281.23-283.20",
     "why": "D634: onto the ice slide with air 3 (a first touch-down: the body slides off, so no zone edge)"},
    {"level": "w3", "zoning": "e211f5ec1484", "from": "w3.Z000", "to": "w3.Z012", "kind": "zone",
     "air": 1, "jumps": 4, "flaps": 4, "casts": 3, "trace": "clk 402.90-410.23",
     "why": "the owner's lake to Z012 approach before the ice climb (R2.18's REPORT: not encoded)"},
)
BANDS = ("nd-air3-near", "nd-air3-far")   # [Step R2.19c2b, c1's slack-band strata] nd-air3 split at
                      # candidates.BAND_M (all of c1's R-real air3 pairs lay that far inside the envelope or more)
GEN_STRINGS = 20_000  # [PLAN-v2 §1.2 item 3] the generator's open-loop strings a pair
GEN_FLAGGED = 50      # [PLAN-v2 §1.2 item 3] at most this many of a pair's flagged strings fly on FastL3
GEN_CONFIRMS = 10     # [default D115] a pair's kernel landings FastL3 confirms, fewest ticks first, until one stays
GEN_RUN_MAX = 30      # [default D115] a string's run-up: 0 to this many ticks of full stick before its Y press
GEN_CONE = math.radians(90.0)   # [default D115] a string's heading: within this of the bearing to the to-zone
GEN_FLAPS, GEN_RECASTS = 5, 2   # [default D115] air3: up to this many flaps and recasts on random ticks ...
GEN_WINDOW = 150      # [default D115] ... of the first this many after the jump's hold
GEN_CHUNK = 16        # the kernel's ticks a call while a string is in the air (a touch-down's chunk is run again)
_PAD = np.dtype([("sx", "<f4"), ("sy", "<f4"), ("cx", "<f4"), ("cy", "<f4"), ("b", "<i4")])   # reach_native.Pad
_BUTTONS = {0: frozenset(), 1: frozenset({"y"}), 3: frozenset({"lt", "y"})}
_FULL = stick(0.0, 0.0)   # the stick full along the camera (a string's, once it has turned to its heading)
GEN_BELOW_M = {"k0": 2.5, "air3": 8.5}   # [default D115] a fall this far under the to-zone's lowest floor or
                                         # water surface ends: no flap left climbs back (5 x 1.2 m)


def _folder(level: str) -> Path:
    return C.folder(level)


def _frame_path(level: str, zoning: str, seed: int) -> Path:
    return C.frame_path(level, zoning, seed, _folder(level))


def frame(a) -> dict:
    """The frame (``reach_engine.candidates.frame``), written privately once; its counts."""
    from devkit.rando.draft.author import read_derived
    return C.frame(a.level, RE._nodes(a.level), read_derived(a.level), a.seed, _folder(a.level))


# -- R ------------------------------------------------------------------------------------------------------------------

class Sampler(C.Aims):
    """A level's R jobs (the module docstring): its pair aims (``candidates.Aims``, edge ``truth:modelled``: every
    pass), takeoffs and small regions' takeoffs."""

    def __init__(self, level: str, derived: dict, nodes) -> None:
        from azurkit.tools.randomizer.draft.geometry import CELL
        super().__init__(level, derived, nodes, "truth:modelled")   # its confidence names aim.MORE's passes: all six
        zone_of = lambda f: nodes.zone_at(f, False, False)   # noqa: E731
        self.takeoffs = [(t, zone_of(t.feet)) for t in nodes.takeoffs()]
        w = nodes.walk
        small = {r for r in range(w.nreg) if w.reg_count[r] * CELL * CELL < 4.0}
        self.small = [(t, zone_of(t.feet)) for t in nodes.takeoffs(min_area=0.0, regions=small)]
        self.small_fan = R0 + tuple(m for m in aim.refine("runjump", "air3", 5) if m.kind == "rolljump")

    def zmin(self, z: str) -> float:
        """Zone ``z``'s lowest logic-walk sample or swim water surface (its floor's least height)."""
        if not hasattr(self, "_zmin"):
            lw, zo, wg = self.nodes.logic, np.asarray(self.nodes.R.zone_of), self.nodes.wg
            j = np.nonzero(lw.reg_soft >= 0)[0]
            zone, h = zo[lw.reg_soft[j]].astype(np.int64), lw.z[j].astype(np.float64)
            if len(getattr(wg, "col", ())):
                m = np.nonzero(wg.lab >= 0)[0]
                zone = np.concatenate([zone, zo[lw.nreg + wg.lab[m]].astype(np.int64)])
                h = np.concatenate([h, wg.hi[m].astype(np.float64)])
            self._zmin = np.full(int(zone.max()) + 1, np.inf)
            np.minimum.at(self._zmin, zone, h)
        return float(self._zmin[int(z.rsplit(".Z", 1)[1])])

    def rest(self, seq: str, za: str, zb: str, kit: str, aim_job: dict, aim_rec: dict | None) -> list[dict]:
        """The pair's refinement (twinned to its aim), small fan and local fan jobs."""
        jobs = []
        if aim_rec is not None:
            r = {k: v for k, v in aim_job.items() if k not in ("env", "key")}
            r.update(id=f"r{seq}", macros=[list(m) for m in aim.refine(*aim_job["cert"])])
            jobs.append(aim.twinned(r, aim_job, aim_rec))
        small = [t for t, z in self.small if z == za]
        jobs += [dict(j, id="s" + j["id"][1:]) for j in runner.fan_jobs(self.nodes, small, self.small_fan)]
        mine = [t for t, z in self.takeoffs if z == za]
        to = self._zone(self.dst, zb)
        if mine and len(to):
            d = self.dst
            best = []
            for t in mine:
                s = np.hypot(d["x"][to] - t.feet[0], d["y"][to] - t.feet[1]) - _reach(d["z"][to] - t.feet[2],
                                                                                          self.tables[kit])
                k = int(np.argmin(s))
                best.append((float(s[k]), t.i, t, int(to[k])))
            for _, _, t, q in sorted(best, key=lambda b: b[:2])[:FAN_N]:
                h = heading_to(t.feet, self._xyz(d, q))
                jobs += [runner._job(self.nodes, t, wrap(h + o), R0, id=f"f{t.i}h{n}") for n, o in enumerate(FAN_TURNS)]
        return jobs


def _count(sim) -> list:
    """A counter of ``sim``'s steps (its ``step`` wrapped once)."""
    if getattr(sim, "_truth_steps", None) is None:
        n, step = [0], sim.step

        def counted(*a, **k):
            n[0] += 1
            return step(*a, **k)
        sim.step, sim._truth_steps = counted, n
    return sim._truth_steps


def job_task(w, job: dict, base: str, touch: str, zones: str | None) -> dict:
    """A pool task: ``runner.job_task`` on one job, with its CPU-seconds, L3 steps and (the kernel route's) kernel
    ticks."""
    n = _count(w.sim(False, deep=False))
    n0, c0 = n[0], time.process_time()
    got = runner.job_task(w, [job], base, touch, zones)[0]
    return {"key": job["key"], "cpu": time.process_time() - c0, "steps": n[0] - n0, "error": got.get("error"),
            "kticks": (got.get("kernel") or {}).get("kernel_ticks", 0)}


def hold_task(w, items: list, base: str) -> list:
    """A pool task: ``hold.task`` on each item, with its CPU-seconds and ticks."""
    out = []
    for item in items:
        c0 = time.process_time()
        ticks = hold.task(w, [tuple(item)], base)
        out.append([list(item), ticks, time.process_time() - c0])
    return out


class Run:
    """One ``run``'s pool and cache, and the level's cost ledger (``truth/costs.jsonl``: each job and hold a truth
    run ran, its CPU-seconds and L3 ticks, so a pair's price outlives the cache's answer to its jobs)."""

    def __init__(self, a, pool, snap: dict, base: Path, touch: Path, zones) -> None:
        self.a, self.pool, self.snap, self.base, self.touch, self.zones = a, pool, snap, base, touch, zones
        self.ledger = _folder(a.level) / "costs.jsonl"
        self.cost: dict[str, dict] = {}       # job key -> cpu, steps (every job a truth run ran)
        self.held: dict[tuple, dict] = {}     # (job, outcome) -> ticks, cpu (every hold a truth run replayed)
        if self.ledger.exists():
            for r in map(json.loads, self.ledger.read_text(encoding="utf-8").splitlines()):
                if "outcome" in r:
                    self.held[(r["job"], r["outcome"])] = r
                else:
                    self.cost[r["job"]] = r
        self.ran: set = set()
        self.seen_j: set = set()              # jobs and holds a row priced already (once an invocation)
        self.seen_h: set = set()
        self.bad: set = set()                 # jobs that raised (never audited)
        self.errors = 0

    def _log(self, rows: list[dict]) -> None:
        with open(self.ledger, "a", encoding="utf-8") as f:
            f.write("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))

    def jobs(self, jobs: list[dict]) -> None:
        todo = list({j["key"]: j for j in jobs if not cache.path(self.base, j["key"]).exists()}.values())
        args = [(j, str(self.base), str(self.touch), self.zones and str(self.zones)) for j in todo]
        t0 = time.time()
        for n, got in enumerate(self.pool.completed(job_task, args), 1):
            self.ran.add(got["key"])
            self.errors += got["error"] is not None
            if got["error"] is not None:
                self.bad.add(got["key"])
            if got["error"] is None:
                self.cost[got["key"]] = {"job": got["key"], "cpu": round(got["cpu"], 4), "steps": got["steps"],
                                         **({"kticks": got["kticks"]} if got["kticks"] else {})}
                self._log([self.cost[got["key"]]])
            if n % 50 == 0 or n == len(args):
                print(json.dumps({"jobs": n, "of": len(args), "errors": self.errors, "s": round(time.time() - t0)}),
                      flush=True)

    def hold(self, graphs: list) -> None:
        recs: dict[str, dict] = {}

        def answer(w):
            rec = recs.get(w["job"]) or recs.setdefault(w["job"], cache.get(self.base, w["job"]))
            return hold.answer(self.base, rec, w["outcome"])
        while True:
            want = sorted({(w["job"], w["outcome"]) for g in graphs for w in g.hold(answer)})
            if not want:
                return
            for got in self.pool.completed(hold_task, [(want[k:k + 4], str(self.base)) for k in range(0, len(want), 4)]):
                for item, ticks, cpu in got:
                    self.held[tuple(item)] = r = {"job": item[0], "outcome": item[1], "ticks": ticks,
                                                  "cpu": round(cpu, 4)}
                    self._log([r])


def _graph(nodes, jobs: list[dict], base: Path, pair: tuple, rank: int) -> tuple[Graph, list]:
    """The graph of ``jobs``' records, its witnesses for ``pair`` at ``rank`` or under the only ones held."""
    recs = [r for j in jobs if (r := cache.get(base, j["key"])) is not None]
    g = Graph(nodes, {j["key"]: j for j in jobs}, recs)
    keep = {r: ws for r, ws in g.cands.get(pair, {}).items() if r <= rank}
    g.cands.clear()
    if keep:
        g.cands[pair] = keep
    return g, recs


def _found(g: Graph, pair: tuple, recs: list) -> dict | None:
    """The pair's held find (its least rank's witness: job id, kind, pass), None for none."""
    if pair not in g.cands or not g.zones.get(pair):
        return None
    r = min(g.zones[pair])
    w = g.zones[pair][r]
    o = next(x for x in recs if x["key"] == w["job"])["outcomes"][w["outcome"]]
    kind = {"q": "aim", "r": "refine", "s": "small fan", "f": "local fan", "g": "class aim"}[w["id"][0]]
    return {"rank": r, "by": kind + (f" pass {o['pass']}" if "pass" in o else ""), "job": w["job"],
            "outcome": w["outcome"], "witness_by": w.get("by", "l3")}


def _code(mode: str, census12: str | None = None) -> dict:
    """The code a row's result comes from; with ``census12`` (the snapshot's census) the kernel route's too."""
    out = {"core": cache.core(), "aim_core": cache.core(cache.CORE_FILES + cache.AIM_FILES),
           "zones": cache.core(cache.ZONE_FILES), "hold": cache.core(cache.CORE_FILES + hold.FILES),
           "truth": _sha(Path(__file__).read_text(encoding="utf-8"))[:12],
           "candidates": _sha(Path(C.__file__).read_text(encoding="utf-8"))[:12], "l3": mode,
           "library": RE._library(mode)}
    if census12 is not None:
        from devkit.reach.native import backend as KB
        out |= {"backend": "kernel", "kernel": KB.kernel_sha12(), "census": census12}
    return out


def _band(stratum: str, slack) -> str:
    """A row's or frame pair's stratum, ``nd-air3`` split into its slack band (:data:`BANDS`, ``candidates.tier``)."""
    return C.tier(stratum, slack) if stratum == "nd-air3" else stratum


def _in(r: dict, s: str) -> bool:
    """Row ``r`` is of stratum or slack band ``s``."""
    return r["stratum"] == s or _band(r["stratum"], r.get("slack")) == s


def _of(fdoc: dict, s: str) -> list[tuple[int, list]]:
    """Stratum or slack band ``s``'s frame pairs in the frame's order, each with its place in its stratum's."""
    st = "nd-air3" if s in BANDS else s
    return [(n, p) for n, p in enumerate(fdoc["strata"][st]) if st == s or _band(st, p[2]) == s]


def _sizes(fdoc: dict) -> dict[str, int]:
    """The frame's pairs by stratum, ``nd-air3``'s by slack band."""
    out = {s: len(v) for s, v in fdoc["strata"].items() if s != "nd-air3"}
    return out | ({b: len(_of(fdoc, b)) for b in BANDS} if "nd-air3" in fdoc["strata"] else {})


def _state(fdoc: dict, rows: list[dict], strata) -> dict[str, tuple[int, int, int]]:
    """Per stratum (or slack band) of ``strata``: its pairs sampled (``rows``, a no-aim pair too), R-real among them
    and left."""
    out = {}
    for s in strata:
        rs = [r for r in rows if _in(r, s)]
        out[s] = (len(rs), sum(bool(r.get("real")) for r in rs), len(_of(fdoc, s)) - len(rs))
    return out


def _takes(state: dict, quota: int, per: int, cap: int, step: int) -> dict[str, int]:
    """The next round's pairs a stratum (``run --quota``; Step R2.19c3), from ``state`` (:func:`_state`): each stratum
    short of ``per`` R-real links takes what its real rate says it lacks (``step`` before it has one, or while it is
    0), never past ``cap`` pairs; once none is short under its cap and the strata hold fewer than ``quota`` R-real
    links in all, the stratum with the highest real rate takes what the shortfall needs at that rate, past ``cap``
    (to the frame's end); nothing once the quota is held or the frame is spent."""
    def want(n: int, r: int, need: int) -> int:
        return math.ceil(need * n / r) if r else step
    short = {s: min(left, cap - n, want(n, r, per - r)) for s, (n, r, left) in state.items()
             if r < per and min(left, cap - n) > 0}
    if short:
        return short
    need = quota - sum(r for _, r, _ in state.values())
    open_ = sorted((s for s in state if state[s][2] > 0), key=lambda s: (-state[s][1] / max(state[s][0], 1), s))
    if need <= 0 or not open_:
        return {}
    n, r, left = state[open_[0]]
    return {open_[0]: min(left, want(n, r, need))}


def _next(fdoc: dict, rows: list[dict], takes: dict[str, int]) -> list:
    """The next ``takes[s]`` pairs of each stratum (or slack band) ``s`` in the frame's order not in ``rows``, with
    their stratum and place."""
    done = {(r["stratum"], r["from"], r["to"]) for r in rows}
    out = []
    for s, k in takes.items():
        st = "nd-air3" if s in BANDS else s
        got = [(st, n, p) for n, p in _of(fdoc, s) if (st, p[0], p[1]) not in done]
        out += got[:k]
    return out


def _weights(sizes: dict, rows: list[dict]) -> dict[str, float]:
    """Each stratum's (``nd-air3``'s: each slack band's) inverse-probability weight (PLAN-v2 §1.3): its frame's pairs
    (``sizes``, :func:`_sizes`) / its sampled ones (``rows``, a no-aim pair too)."""
    n: dict[str, int] = {}
    for r in rows:
        b = _band(r["stratum"], r.get("slack"))
        n[b] = n.get(b, 0) + 1
    return {st: sizes[st] / k for st, k in n.items()}


def _pooled(w: list[float]) -> tuple[float, float]:
    """The weighted count of links weighted ``w`` and their Kish effective number (what a pooled interval stands
    on)."""
    sw, sw2 = sum(w), sum(x * x for x in w)
    return sw, (sw * sw / sw2 if sw2 else 0.0)


def _sample(fdoc: dict, rows: list[dict]) -> dict:
    """The frozen sample ``rows`` against the frame: per stratum (slack band) its pairs, R-real, weight
    (:func:`_weights`) and the frame's R-real links it estimates; in all, the R-real links, the frame's estimated and
    their Kish number."""
    sizes = _sizes(fdoc)
    w = _weights(sizes, rows)
    per = {}
    for st in sorted(w):
        rs = [r for r in rows if _in(r, st)]
        real = sum(bool(r.get("real")) for r in rs)
        per[st] = {"frame": sizes[st], "sampled": len(rs), "real": real, "weight": round(w[st], 3),
                   "est_real_in_frame": round(w[st] * real)}
    est, kish = _pooled([w[_band(r["stratum"], r.get("slack"))] for r in rows if r.get("real")])
    return {"strata": per, "real": sum(d["real"] for d in per.values()), "est_real_in_frame": round(est),
            "kish_n_real": round(kish, 1)}


def _rows(R: Run, pairs: list[dict], base: Path) -> list[dict]:
    """Each pair's frozen row (the module docstring); a job or hold is priced once an invocation."""
    rows = []
    for p in pairs:
        row = {k: p[k] for k in ("stratum", "seq", "from", "to", "kit", "slack", "na")}
        if p["aim"] is not None:
            keys = [j["key"] for j in p["jobs"]]
            mine = [k for k in dict.fromkeys(keys) if k in R.cost and k not in R.seen_j]   # priced: the ledger's,
            R.seen_j.update(mine)                                                         # once an invocation
            g, ks = p["graph"][0], set(keys)
            hk = [h for h in R.held if h[0] in ks and h not in R.seen_h]
            R.seen_h.update(hk)
            f = p["found"]
            row.update(real=f is not None, rank=f and f["rank"], by=f and f["by"],
                       witness=f and [f["job"], f["outcome"]], jobs=keys, priced=len(mine),
                       ran=len(ks & R.ran), engine_cached=len(ks - set(R.cost)),
                       missing=sum(cache.get(base, k) is None for k in keys),
                       cpu=round(sum(R.cost[k]["cpu"] for k in mine) + sum(R.held[h]["cpu"] for h in hk), 3),
                       steps=sum(R.cost[k]["steps"] for k in mine) + sum(R.held[h]["ticks"] for h in hk),
                       holds=len(hk), candidates=sum(len(v) for v in g.cands.get((p["from"], p["to"]), {}).values()))
            if "kernel" in p:                                   # the kernel route's (:func:`_kfacts`)
                k = p["kernel"]
                row["kernel"] = {key: v for key, v in k.items() if key != "failed"} | {
                    "kticks": sum(R.cost[x].get("kticks", 0) for x in mine), "witness_by": f and f["witness_by"]}
                row["refly_real"] = bool(f) or k.get("refly", {}).get("held", 0) > 0
        rows.append(row)
    return rows


def run(a) -> dict:
    """R on the sample (the module docstring): the ``--take`` pairs, or with ``--quota`` rounds of them; each pair's
    frozen result, written once the invocation's FastL3 audit passes; the run's counts by stratum."""
    from devkit.rando.draft.author import read_derived
    derived = read_derived(a.level)
    fdoc, out_p, frozen = _setup(a, derived)
    snap, base = RE._snap(a.snapshot, a.store), cache.folder(a.level)
    nodes = RE._nodes(a.level)
    t0 = time.time()
    smp = Sampler(a.level, derived, nodes)
    touch, touch12 = _targets(nodes, base)
    kspec = _kspec(a.level, snap, touch) if a.backend == "kernel" else None
    print(json.dumps({"frozen_already": len(frozen), "setup_s": round(time.time() - t0)}), flush=True)
    new, ran, zones, rounds = [], {}, None, 0

    def keyed(j: dict) -> dict:
        return _keyed(j, snap, touch12, kspec)
    with RE._pool(snap, a.workers, a.l3, kernel=kspec) as pool:
        code = _code(a.l3, kspec and kspec["census12"])
        R = Run(a, pool, snap, base, touch, None)
        while True:
            if a.quota is None:
                want = [] if rounds else _want(a, fdoc, frozen)
            else:
                state = _state(fdoc, frozen + new, a.strata)
                print(json.dumps({"round": rounds, "state": state}), flush=True)
                want = _next(fdoc, frozen + new, _takes(state, a.quota, a.per, a.cap, a.step))
            if not want:
                break
            rounds += 1
            smp.prepare([(p[0], p[1]) for _, _, p in want])
            pairs = []
            for s, n, (za, zb, slack) in want:
                kit = s.split("-")[1]
                j, why = smp.aim_job(f"q{s}:{n}", za, zb, kit)
                pairs.append({"stratum": s, "seq": n, "from": za, "to": zb, "kit": kit, "slack": slack,
                              "aim": j and keyed(j), "na": why})
            live = [p for p in pairs if p["aim"] is not None]
            zones = R.zones = RE._zones(a.level, [p["aim"] for p in live]) or zones
            R.jobs([p["aim"] for p in live])
            for p in live:                                   # stage A: the aim alone
                p["jobs"] = [p["aim"]]
                p["graph"] = _graph(nodes, p["jobs"], base, (p["from"], p["to"]), KITS[p["kit"]])
            R.hold([p["graph"][0] for p in live])
            rest = []
            for p in live:
                p["found"] = _found(p["graph"][0], (p["from"], p["to"]), p["graph"][1])
                if p["found"] is None:                       # stage B: the refinement, the small and the local fans
                    aim_rec = cache.get(base, p["aim"]["key"])
                    more = smp.rest(f"{p['stratum']}:{p['seq']}", p["from"], p["to"], p["kit"], p["aim"], aim_rec)
                    p["jobs"] += [keyed(j) for j in more]
                    rest.append(p)
            R.jobs([j for p in rest for j in p["jobs"][1:]])
            for p in rest:
                p["graph"] = _graph(nodes, p["jobs"], base, (p["from"], p["to"]), KITS[p["kit"]])
            R.hold([p["graph"][0] for p in rest])
            for p in rest:
                p["found"] = _found(p["graph"][0], (p["from"], p["to"]), p["graph"][1])
            if kspec is not None:                            # the candidates, their confirms and the re-fly
                for p in live:
                    p["kernel"] = _kfacts(p["graph"][0], (p["from"], p["to"]), KITS[p["kit"]], p["graph"][1], base,
                                          nodes.zone_at)
                if a.refly:
                    _reflies(R, live, base, touch, zones)
            ok = R.ran - R.bad
            ran.update({j["key"]: j for p in live for j in p["jobs"] if j["key"] in ok})
            for row in _rows(R, pairs, base):
                new.append(row | {"code": code, "frame": fdoc and fdoc["seed"], "frame_zoning": fdoc and fdoc["zoning"],
                                  "snapshot": snap["meta_sha12"]})
            if a.quota is None:
                break
    out = {"level": a.level, "name": a.name, "code": code, "snapshot": snap["meta_sha12"], "pairs": len(new),
           "rounds": rounds, "errors": R.errors, "summary": _summary(new)}
    if a.l3 == "fast" and ran:                           # PLAN-v2 §1.5c: FastL3 decides, so its records are audited
        out["audit"] = au = RE._audit(a, snap, base, list(ran.values()), touch, zones, code["library"], kspec)
        bad, x87 = [x["id"] for v in au.values() for x in v.get("differ", ())], au["x87"]
        if bad or x87.get("x87_differ") or x87.get("x87_workers") == 0 or x87.get("walk_differ"):
            print(json.dumps(out), flush=True)
            raise SystemExit(f"the audit found FastL3 records base L3 or the x87 check gives otherwise: {bad[:20]}; "
                             "no pair of this invocation was frozen: find why before another run")
    with open(out_p, "a", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, sort_keys=True) + "\n" for r in new))
    return out | {"wall_s": round(time.time() - t0),
                  "sample": fdoc and _sample(fdoc, [r for r in frozen + new if r["stratum"] in fdoc["strata"]]),
                  "rows": [{k: v for k, v in r.items() if k not in ("jobs", "witness", "code")} for r in new]}


def _setup(a, derived: dict) -> tuple[dict | None, Path, list[dict]]:
    """A run's frame (None for ``--pairs`` without one), its output file and the rows frozen there already."""
    from azurkit.tools.randomizer.planner.proofs import zoning
    fp = _frame_path(a.level, zoning(derived), a.seed)
    if not fp.exists() and not getattr(a, "pairs", None):
        raise SystemExit(f"no frame {fp.name}: run `frame {a.level}` first")
    fdoc = json.loads(gzip.decompress(fp.read_bytes())) if fp.exists() else None
    out_p = _folder(a.level) / f"{a.name}.jsonl"
    return fdoc, out_p, _read(a.level, a.name) if out_p.exists() else []


def _read(level: str, name: str) -> list[dict]:
    return C.rows(level, name, _folder(level))


def _targets(nodes, base: Path) -> tuple[Path, str]:
    """The volumes and pickups a run judges touches against (``Nodes.targets``), written once; its path and sha12."""
    doc = nodes.targets()
    touch12 = cache.sha12(doc)
    touch = base / f"targets-{touch12}.json"
    if not touch.exists():
        cache.write(touch, doc)
    return touch, touch12


def _kspec(level: str, snap: dict, touch: Path) -> dict:
    """The kernel route's worker spec (``devkit/reach/reach_engine.py``'s): the snapshot's census and the targets file."""
    census, census12 = RE._census_of(level, snap)
    return {"level": level, "absent": census["absent"], "touch": str(touch), "census12": census12}


def _want(a, fdoc: dict | None, frozen: list[dict]) -> list:
    """The pairs a run or a generator takes, (stratum, its place, [from, to, slack]) each, none ``frozen`` already:
    ``--like``'s names' pairs of ``--strata`` (the last name's row of a pair), ``--pairs`` (stratum ``known-<kit>``),
    else each stratum's (or slack band's: its own pairs in its stratum's order) next ``--take`` from ``--skip``."""
    done = {(r["stratum"], r["from"], r["to"]) for r in frozen}
    if getattr(a, "like", None):
        rows = {(r["stratum"], r["from"], r["to"]): r for n in a.like for r in _read(a.level, n)}
        return [(s, r["seq"], [f, t, r.get("slack")]) for (s, f, t), r in rows.items()
                if s in a.strata and (s, f, t) not in done]
    if getattr(a, "pairs", None):
        out = []
        for n, q in enumerate(a.pairs):
            pair, _, kit = q.rpartition(":")
            za, zb = pair.split(">")
            if kit not in KITS:
                raise SystemExit(f"--pairs {q}: the kit is one of {sorted(KITS)}")
            if (f"known-{kit}", za, zb) not in done:
                out.append((f"known-{kit}", n, [za, zb, None]))
        return out
    return [(st, n, p) for s in a.strata for st in ["nd-air3" if s in BANDS else s]
            for n, p in _of(fdoc, s)[a.skip:a.skip + a.take] if (st, p[0], p[1]) not in done]


# -- the kernel route's candidates, confirms and re-fly (Step R2.19c2a) ------------------------------------------------

def _verdict(got: dict, to: str, rank: int, zone_at) -> str:
    """A FastL3 answer's class for pair (…, ``to``) at ``rank``: ``held`` (it lands there settled at the rank or under
    and stays the hold's 60 ticks), else why not: a fault (``fault:start``: L3 doesn't stand the start), the string's
    end (unsettled, dead, ...), ``landed elsewhere``, ``over the kit``, ``more flaps than its candidate`` (a confirm's
    rank over the kernel's), ``left in the hold``; an L3 witness's hold (``hold.replay``: no re-derived outcome) is
    ``held`` or ``left in the hold``."""
    if "fault" in got:
        return f"fault:{str(got['fault']).split('@')[0]}"
    o = got.get("outcome")
    if o is not None:
        if o["end"] != "settled":
            return o["end"].split(":")[0]
        if zone_at(o["land"], o["land_state"] == SWIMMING, False) != to:
            return "landed elsewhere"
        if min_rank(o) > rank:
            return "over the kit"
        if not got.get("same"):
            return "more flaps than its candidate"
    return "held" if hold.stays(got, to, zone_at) else "left in the hold"


def _kfacts(g: Graph, pair: tuple, rank: int, recs: list[dict], base: Path, zone_at) -> dict:
    """A kernel-route pair's candidates before the confirm (its jobs' aim hits, confirmed or held as found, and the
    graph's best ``graph.TRIES`` a rank at ``rank`` or under), by the side that flew them (``kernel``, also once the
    graph's hold confirmed it, ``by`` "confirmed"; or ``l3``: a launch the kernel flagged, or a start L3 took), and
    each one's FastL3 answer by :func:`_verdict` (``untried``: the hold stopped at an earlier one that stayed);
    ``failed`` the kernel candidates whose confirm failed (job key, outcome: the re-fly's)."""
    by_key = {r["key"]: r for r in recs}
    seen, got = set(), []
    for r in recs:
        for k, o in enumerate(r["outcomes"]):
            if "hold" in o:                                 # an aim's hit (its job's stop is this pair)
                seen.add((r["key"], k))
                got.append((r["key"], k, "kernel" if o.get("by") in ("kernel", "confirmed") else "l3", o["hold"]))
    for rr, ws in g.cands.get(pair, {}).items():
        for w in ws if rr <= rank else ():
            if (w["job"], w["outcome"]) not in seen:
                seen.add((w["job"], w["outcome"]))
                got.append((w["job"], w["outcome"], "kernel" if w["by"] in ("kernel", "confirmed") else "l3",
                            hold.answer(base, by_key[w["job"]], w["outcome"])))
    out = {"cands": {"kernel": 0, "l3": 0}, "answers": {"kernel": {}, "l3": {}}, "failed": []}
    for job, k, side, ans in got:
        v = "untried" if ans is None else _verdict(ans, pair[1], rank, zone_at)
        out["cands"][side] += 1
        out["answers"][side][v] = out["answers"][side].get(v, 0) + 1
        if side == "kernel" and v not in ("held", "untried"):
            out["failed"].append([job, k])
    return out


def _reflies(R: Run, pairs: list[dict], base: Path, touch: Path, zones: Path | None) -> None:
    """Each failed kernel candidate of ``pairs`` (:func:`_kfacts`) flown once more on FastL3 (:func:`refly_task`), a
    job's together; each pair's ``kernel["refly"]``: tried, held, the classes, the CPU-seconds and L3 ticks."""
    jobs = {j["key"]: j for p in pairs for j in p["jobs"]}
    want: dict[str, dict] = {}
    for p in pairs:
        for job, k in p["kernel"]["failed"]:
            want.setdefault(job, {})[k] = [k, p["to"], KITS[p["kit"]]]
    got: dict[tuple, dict] = {}
    t0, cost = time.time(), {}
    for n, r in enumerate(R.pool.completed(refly_task, [(jobs[j], list(ts.values()), str(base), str(touch),
                                                         zones and str(zones)) for j, ts in want.items()]), 1):
        cost[r["job"]] = r
        got.update({(r["job"], int(k)): v for k, v in r["got"].items()})
        if n % 50 == 0 or n == len(want):
            print(json.dumps({"reflown_jobs": n, "of": len(want), "s": round(time.time() - t0)}), flush=True)
    for p in pairs:
        cls: dict[str, int] = {}
        for job, k in p["kernel"]["failed"]:
            v = got.get((job, k), {}).get("class", "error")
            cls[v] = cls.get(v, 0) + 1
        mine = {job for job, _ in p["kernel"]["failed"]}
        p["kernel"]["refly"] = {"tried": len(p["kernel"]["failed"]), "held": cls.get("held", 0), "classes": cls,
                                "cpu": round(sum(cost[j]["cpu"] for j in mine if j in cost), 3),
                                "steps": sum(cost[j]["steps"] for j in mine if j in cost)}


class _Done(Exception):
    """A re-fly's job run stops once each of its targets has flown again."""


def refly_task(w, job: dict, targets: list, base: str, touch: str, zones: str | None) -> dict:
    """A pool task on the kernel route: kernel job ``job``'s outcomes ``targets`` ([outcome, to-zone, rank] each:
    candidates whose FastL3 confirm failed) each flown once more on FastL3, from its start's FastL3 twin under the
    controller that flew it (the job run again on the kernel, its launch families in Python (``c_launches`` off, so
    each one passes the spy; R2.19p measured their records equal to C's), each aim hit's answer the record's, until
    each target's launch comes round: its pads, start and macro the record's), then confirmed from the snapshot with the hold
    (``reach_native.backend.confirm``); each one's :func:`_verdict` (``unmatched``: its launch never came round), the
    task's CPU-seconds and L3 ticks."""
    from devkit.reach.native import backend as KB
    sim = w.sim(False, deep=False)
    n = _count(sim)
    n0, c0 = n[0], time.process_time()
    if getattr(w, "_reach_here", None) is None:
        w._reach_here = runner.here_cell(sim)
    rec, zone_at = cache.get(Path(base), job["key"]), runner._zones(w, zones)
    want = {}
    for k, to, rank in targets:
        o = rec["outcomes"][k]
        want[k] = (o, [(p.stick, p.buttons, p.cam) for p in l3.pads(o["segments"])],
                   tuple(rec["starts"][o["start"]]["feet"]), to, rank)
    held = {json.dumps(o["segments"], sort_keys=True): o["hold"] for o in rec["outcomes"] if "hold" in o}
    got: dict[int, dict] = {}
    launches, c_launches, replay = KB.launches, KB.c_launches, hold.replay

    def answered(sim_, st, h, o):                   # an aim hit the record answers: not confirmed again
        return held.get(json.dumps(o["segments"], sort_keys=True)) or replay(sim_, st, h, o)

    def spy(sim_, fam, heading, cam, feet, back, *, target=None, ctl=None):
        if not isinstance(sim_, KB.KernelSim) or sim_.mode != "kernel":
            return launches(sim_, fam, heading, cam, feet, back, target=target, ctl=ctl)
        state = sim_.save()
        gos = launches(sim_, fam, heading, cam, feet, back, target=target, ctl=ctl)
        for m, g in zip(fam, gos):
            tail = [(p.stick, p.buttons, struct.unpack("<2f", r.cam)) for p, r in zip(g.pads, g.rows)]
            for k, (o, pads, at, to, rank) in want.items():
                cut = len(pads) - len(tail)
                if k in got or o["macro"] != m.name or at != tuple(feet) or cut < 0 or pads[cut:] != tail:
                    continue
                twin = sim_.on_l3(state)
                if twin is None:
                    got[k] = {"class": "fault:start"}
                    continue
                sim_.l3.reset(twin)
                go = launches(sim_.l3, [m], heading, cam, feet, back, target=target, ctl=ctl)[0]
                flown = {"segments": segments([l3.Pad(s, b, None, c) for s, b, c in pads[:cut]] + list(go.pads)),
                         "kit": o["kit"], "macro": o["macro"], "flaps_planned": o["flaps_planned"], "flaps": 9}
                ans = KB.confirm(sim_.l3, rec["starts"][o["start"]], rec["heading"], flown)
                got[k] = {"class": _verdict(ans, to, rank, zone_at)}
        if len(got) == len(want):
            raise _Done
        return gos
    KB.launches, KB.c_launches, hold.replay = spy, lambda *a, **k: None, answered
    miss = "unmatched"
    try:
        runner.run_job(sim, job, runner._touch(w, touch), w._reach_here, zone_at)
    except _Done:
        pass
    except Exception as exc:          # noqa: BLE001 (a step stopped for time, or a bug: kept by name, never a class)
        miss = f"error: {type(exc).__name__}"
    finally:
        KB.launches, KB.c_launches, hold.replay = launches, c_launches, replay
    return {"job": job["key"], "got": {str(k): got.get(k, {"class": miss}) for k in want},
            "cpu": round(time.process_time() - c0, 4), "steps": n[0] - n0}


def calib(a) -> dict:
    """A kernel run (``--kernel``: ``run --backend kernel``'s rows) against FastL3 rows of the same pairs
    (``--fast``, the last name's row of a pair): per stratum the FastL3-R real pairs, those the kernel run keeps alone
    and with its re-fly (Wilson 95 %), its finds FastL3-R lacks, the pairs with a kernel candidate and the
    false-positive factor (those / the kernel run's real pairs; ``_any``: a candidate of either side), the confirms
    by FastL3 answer, the re-fly's classes,
    and each side's CPU-seconds, L3 ticks and kernel ticks."""
    kr = {(r["stratum"], r["from"], r["to"]): r for r in _read(a.level, a.kernel)}
    fr = {(r["stratum"], r["from"], r["to"]): r for n in a.fast for r in _read(a.level, n)}
    out = {}
    for s in sorted({k[0] for k in kr}):
        both = [(kr[k], fr[k]) for k in kr if k[0] == s and k in fr and not kr[k]["na"] and not fr[k]["na"]]
        if not both:
            continue
        real = [(k, f) for k, f in both if f["real"]]
        kept, kept2 = (sum(bool(k.get(x, k["real"])) for k, _ in real) for x in ("real", "refly_real"))
        kpos = sum(k["kernel"]["cands"]["kernel"] > 0 for k, _ in both)
        apos = sum(sum(k["kernel"]["cands"].values()) > 0 for k, _ in both)
        kreal = sum(bool(k["real"]) for k, _ in both)
        answers: dict[str, dict] = {"kernel": {}, "l3": {}}
        refly: dict[str, int] = {}
        for k, _ in both:
            for side, got in k["kernel"]["answers"].items():
                for v, c in got.items():
                    answers[side][v] = answers[side].get(v, 0) + c
            for v, c in k["kernel"].get("refly", {}).get("classes", {}).items():
                refly[v] = refly.get(v, 0) + c
        kc = sum(k["cpu"] + k["kernel"].get("refly", {}).get("cpu", 0.0) for k, _ in both)
        ks = sum(k["steps"] + k["kernel"].get("refly", {}).get("steps", 0) for k, _ in both)
        fc, fs = sum(f["cpu"] for _, f in both), sum(f["steps"] for _, f in both)
        out[s] = {"pairs": len(both), "fast_real": len(real), "kernel_kept": kept, "kernel_kept_refly": kept2,
                  "kept": round(kept / len(real), 4) if real else None, "ci95": _wilson(kept, len(real)),
                  "kept_refly": round(kept2 / len(real), 4) if real else None,
                  "ci95_refly": _wilson(kept2, len(real)),
                  "lost": sorted(f"{f['from']}>{f['to']}" for k, f in real if not k.get("refly_real", k["real"])),
                  "kernel_only": sorted(f"{k['from']}>{k['to']}" for k, f in both
                                        if k.get("refly_real", k["real"]) and not f["real"]),
                  "kernel_real": kreal, "kernel_positive_pairs": kpos,
                  "fp_factor": round(kpos / kreal, 3) if kreal else None, "positive_pairs_any": apos,
                  "fp_factor_any": round(apos / kreal, 3) if kreal else None, "answers": answers, "refly": refly,
                  "kernel_cpu_s": round(kc, 1), "kernel_l3_ticks": ks,
                  "kernel_kticks": sum(k["kernel"].get("kticks", 0) for k, _ in both),
                  "fast_cpu_s": round(fc, 1), "fast_l3_ticks": fs,
                  "fast_priced_in_full": all(f.get("engine_cached", 0) == 0 for _, f in both)}
    return {"level": a.level, "kernel": a.kernel, "fast": a.fast, "strata": out}


# -- the independent generator (Step R2.19c2a; PLAN-v2 §1.2 item 3) ----------------------------------------------------

def _buttons(run: int, flaps=(), recasts=()) -> np.ndarray:
    """A string's buttons on each tick after its camera's turn, to the launch cap (``macros.TICKS``): Y from tick
    ``run`` held ``macros.JUMP_HOLD`` ticks, then Y for one tick at each of ``flaps`` and LT+Y at each of ``recasts``
    (ticks after the hold's release)."""
    b = np.zeros(TICKS, np.int32)
    b[run:run + JUMP_HOLD] = 1
    at = run + JUMP_HOLD + 1
    for t, v in [(t, 1) for t in flaps] + [(t, 3) for t in recasts]:
        if at + t < TICKS:
            b[at + t] = v
    return b


def _turn(cam0: float, k: int) -> list[float]:
    """The camera's yaws turning ``k`` ticks from ``cam0`` at the pad's rate (``inputs.CAM_RATE``; left for k > 0),
    the stick at rest (``macros.align``'s ticks): a string's heading is on that grid, so a start's turn is run once."""
    return [cam0 + j * math.copysign(CAM_RATE, k) for j in range(1, abs(k) + 1)]


def _kpads(yaws: list[float], n: int = 0, c: float | None = None) -> np.ndarray:
    """Pads as the kernel reads them (``reach_native.Pad``: the camera as ``l3.camera_dir``'s f32 pair): one at rest
    under each of ``yaws``, then ``n`` under camera ``c`` with the stick full along it (their buttons the caller's)."""
    a = np.zeros(len(yaws) + n, _PAD)
    k = len(yaws)
    a["cx"][:k], a["cy"][:k] = [-math.sin(y) for y in yaws], [math.cos(y) for y in yaws]
    if n:
        a["cx"][k:], a["cy"][k:] = -math.sin(c), math.cos(c)
        a["sx"][k:], a["sy"][k:] = _FULL
    return a


def _lpads(yaws: list[float], c: float, b: np.ndarray, n: int, first: int | None) -> list:
    """A string's first ``n`` pads as ``l3.Pad`` s (its camera's turn ``yaws``, then the stick full along camera
    ``c`` with buttons ``b``: the pads :func:`_kpads` gives the kernel), the stick at rest and no button after tick
    ``first`` (the first touch-down)."""
    k = len(yaws)
    out = [l3.Pad((0.0, 0.0), frozenset(), y) for y in yaws[:n]]
    rest = l3.Pad((0.0, 0.0), frozenset(), c)
    return out + [rest if first is not None and t > first else l3.Pad(_FULL, _BUTTONS[int(b[t - k])], c)
                  for t in range(k, n)]


def _kturn(lib, wp: int, p0, yaws: list[float]):
    """Player ``p0`` after its camera's turn (``yaws``) on the kernel (a copy), None when the kernel flags a tick."""
    from devkit.reach import native as N
    p = N.Player.from_buffer_copy(p0)
    if yaws:
        a, out = _kpads(yaws), np.empty((len(yaws), 10))
        got = lib.p_run(wp, ctypes.byref(p), len(yaws), a.ctypes.data, out.ctypes.data)
        codes = out[:got, 9].astype(np.int64)
        if got < len(yaws) or np.any((codes % 16) | ((codes >> 4) & 16)):
            return None
    return p


def _kfly(lib, wp: int, p0, pads: np.ndarray, rest: np.ndarray, run: int, zfloor: float, out: np.ndarray) -> tuple:
    """One string after its camera's turn (``pads``) on the kernel (``lib``, world ``wp``) from player ``p0``, its
    stick at rest from the first touch-down on (``rest``): (how it ended, ``macros.launch``'s ends as far as the kernel
    tells them: settled, unsettled, dead, air cap, stuck, stayed (never left the floor), ticks; flag: a stop or a law
    the kernel doesn't port; below: falling with its feet under ``zfloor``, where no landing in the to-zone is left),
    the ticks it ran (its rows in ``out``), the first touch-down's tick or None).  In the air it runs
    :data:`GEN_CHUNK` ticks a call; a touch-down's chunk runs again to that tick."""
    from devkit.reach import native as N
    p, size = N.Player.from_buffer_copy(p0), ctypes.sizeof(N.Player)
    pp, op, L = pads.ctypes.data, out.ctypes.data, len(pads)
    t, took, first, air, still, stay = 0, None, None, 0, 0, run + JUMP_HOLD + RUN_CAP
    while first is None:
        if t >= L:
            return "ticks", t, None
        n = min(L - t, GEN_CHUNK if t else run + JUMP_HOLD + GEN_CHUNK)
        keep = N.Player.from_buffer_copy(p)
        got = lib.p_run(wp, ctypes.byref(p), n, pp + t * _PAD.itemsize, op + t * 80)
        for i, r in enumerate(out[t:t + got].tolist()):
            code, s = int(r[9]), int(r[6])
            if code % 16 or (code >> 4) & 16:
                return "flag", t + i + 1, None
            if s in DEAD:
                return "dead", t + i + 1, None
            if s in AIRBORNE:
                took, air = t + i if took is None else took, air + 1
                still = still + 1 if math.hypot(r[3], r[4], r[5]) < 0.05 else 0
                if air > AIR_CAP or still >= STUCK:
                    return ("air cap" if air > AIR_CAP else "stuck"), t + i + 1, None
                if r[5] <= 0.0 and r[2] - 1.0 < zfloor:
                    return "below", t + i + 1, None
            elif took is not None:
                first = t + i
                break
            elif t + i >= stay:
                return "stayed", t + i + 1, None
        if first is None:
            t += got
    ctypes.memmove(ctypes.byref(p), ctypes.byref(keep), size)       # back to the chunk's start, to the touch-down
    lib.p_run(wp, ctypes.byref(p), first - t + 1, pp + t * _PAD.itemsize, op + t * 80)
    t, still, cap = first + 1, int(out[first, 6] == 0), min(L, first + 1 + SETTLE)
    while t < cap:
        got = lib.p_run(wp, ctypes.byref(p), min(len(rest), cap - t), rest.ctypes.data, op + t * 80)
        for i, r in enumerate(out[t:t + got].tolist()):
            code, s = int(r[9]), int(r[6])
            if code % 16 or (code >> 4) & 16:
                return "flag", t + i + 1, first
            if s in DEAD:
                return "dead", t + i + 1, first
            still = still + 1 if s == 0 else 0       # standing (the kernel flags water and ice: no other settles)
            if still >= STILL:
                return "settled", t + i + 1, first
        t += got
    return "unsettled", t, first


def _l3fly(sim, pre: list, rest, k: int, run: int) -> tuple:
    """A string (``pre``: its whole schedule as ``l3.Pad`` s, its camera's turn's ``k`` first) on FastL3 from its
    state now, as :func:`_kfly` flies it on the kernel (the stick at rest from the first touch-down: ``rest``): (how
    it ended, its pads, its last row, its most flaps in the jump)."""
    took = first = row = None
    air = still = 0
    flaps, used, stay = 0, [], k + run + JUMP_HOLD + RUN_CAP
    for t in range(len(pre)):
        if first is not None and t - first > SETTLE:
            return "unsettled", used, row, flaps
        pad = pre[t] if first is None else rest
        try:
            row = sim.step(pad)
        except l3.LevelExit:
            return "exit", used + [pad], row, flaps
        except l3.L3Error:
            return "fault", used + [pad], row, flaps
        used.append(pad)
        flaps = max(flaps, (row.obs.flaps_used or 0) if row.obs is not None else 0)
        if row.state in DEAD or row.hp <= 0:
            return "dead", used, row, flaps
        if first is None:
            if row.state in AIRBORNE:
                took, air = t if took is None else took, air + 1
                still = still + 1 if row.obs is not None and math.hypot(*row.obs.vel) < 0.05 else 0
                if air > AIR_CAP or still >= STUCK:
                    return ("air cap" if air > AIR_CAP else "stuck"), used, row, flaps
                continue
            if took is None:
                if t >= stay:
                    return "stayed", used, row, flaps
                continue
            first, still = t, 0
        still = still + 1 if settled(row) else 0
        if still >= STILL:
            return "settled", used, row, flaps
    return "ticks", used, row, flaps


def _kstart(ks, feet, cells: list, kit: str):
    """A generator start on the kernel (``ks``, a ``KernelSim``): R6 onto ``feet`` and the settle
    (``runner.find_start``), then the kit: its player, its camera's yaw, its saved state and the start's record; None
    when the kernel doesn't stand it (or flags its settle or kit)."""
    ks.reset()
    st = runner.find_start(ks, [list(feet)], 0.0, cells)
    if "cell" not in st or ks.mode != "kernel":
        return None
    rows = runner.set_kit(ks, kit)
    if ks.mode != "kernel":
        return None
    state = ks.save()
    return state[1], runner._cam(rows[-1]), state, st


def gen_task(w, spec: dict, zones: str, seed: int, strings: int, flagged: int, confirms: int) -> dict:
    """A pool task on the kernel route: the generator on one pair (``spec``: :func:`_gen_spec`; the module docstring):
    its counts, whether FastL3 holds one of its strings (``real``, ``rank``, ``by`` kernel: a confirmed kernel
    landing, l3: a flagged string flown there; ``witness``: private), the CPU-seconds, L3 and kernel ticks."""
    from devkit.reach.engine import worker
    from devkit.reach.native import backend as KB
    sim = w.sim(False, deep=False)
    n = _count(sim)
    n0, c0 = n[0], time.process_time()
    if getattr(w, "_reach_here", None) is None:
        w._reach_here = runner.here_cell(sim)
    try:
        ks = KB.KernelSim(worker.timed(sim), KB.world(KB._SPEC["level"], KB._SPEC.get("absent", ()))[0], KB.base(sim))
        got = _generate(w, ks, spec, runner._zones(w, zones), seed, strings, flagged, confirms)
    except Exception as exc:          # noqa: BLE001 (a step stopped for time, or a bug: the pair's error, no row)
        got = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    return {"key": [spec["stratum"], *spec["pair"]]} | got | {"cpu": round(time.process_time() - c0, 3),
                                                              "l3_ticks": n[0] - n0}


def _generate(w, ks, spec: dict, zone_at, seed: int, strings: int, flagged: int, confirms: int) -> dict:
    from devkit.reach.native import backend as KB
    za, zb = spec["pair"]
    kit, pts, n = spec["kit"], spec["points"], strings
    rank, here, lib, wp = KITS[kit], w._reach_here, ks.lib, ks.w.ptr
    starts = w.__dict__.setdefault("_gen_starts", {})
    turned = w.__dict__.setdefault("_gen_turned", {})
    kt = 0

    def start(i: int):
        key = (tuple(pts[i]), kit)
        if key not in starts:
            got = _kstart(ks, pts[i], [here] + [c for c in spec["cells"][i] if c != here], kit)
            starts[key] = got and (got, zone_at(got[3]["settled"], False, False))
        got = starts[key]
        return got[0] if got and got[1] == za else None
    stood = [i for i in range(len(pts)) if start(i) is not None]
    out = {"strings": 0, "points": len(pts), "points_stood": len(stood), "ends": {}, "candidates": 0,
           "confirms": {}, "flagged_flown": {}, "real": False, "rank": None, "by": None, "kernel_ticks": 0,
           "witness": None}
    if not stood:
        return out
    rng = np.random.default_rng(int(_sha(f"{seed}/{spec['level']}/{spec['stratum']}/{za}>{zb}")[:16], 16))
    d = {"pt": rng.integers(len(stood), size=n), "off": rng.uniform(-GEN_CONE, GEN_CONE, n),
         "run": rng.integers(0, GEN_RUN_MAX + 1, n)}
    if rank:
        d |= {"nf": rng.integers(0, GEN_FLAPS + 1, n), "ft": rng.integers(0, GEN_WINDOW, (n, GEN_FLAPS)),
              "nr": rng.integers(0, GEN_RECASTS + 1, n), "rt": rng.integers(0, GEN_WINDOW, (n, GEN_RECASTS))}

    def string(i: int) -> tuple:
        pi = stood[int(d["pt"][i])]
        st = start(pi)
        k = round(wrap(spec["bearing"][pi] + float(d["off"][i]) - st[1]) / CAM_RATE)
        yaws = _turn(st[1], k)
        b = _buttons(int(d["run"][i]), sorted(d["ft"][i, :d["nf"][i]].tolist()) if rank else (),
                     d["rt"][i, :d["nr"][i]].tolist() if rank else ())
        return pi, st, k, yaws, (yaws[-1] if yaws else st[1]), b

    ends: dict[str, int] = {}
    cands, flags = [], []
    rows, posts = np.empty((TICKS + 8, 10)), {}
    for i in range(n):
        pi, st, k, yaws, c, b = string(i)
        if (key := (tuple(pts[pi]), kit, k)) not in turned:
            turned[key] = _kturn(lib, wp, st[0], yaws)
            kt += len(yaws)
        if k not in posts:
            posts[k] = (_kpads([], TICKS, c), _kpads([c] * 8))
        p1, (post, rest) = turned[key], posts[k]
        if p1 is None:
            end, used, first = "flag", 0, None
        else:
            pads = post.copy()
            pads["b"] = b
            end, used, first = _kfly(lib, wp, p1, pads, rest, int(d["run"][i]), spec["zfloor"], rows)
        kt += used
        ends[end] = ends.get(end, 0) + 1
        if end == "flag":
            if len(flags) < flagged:
                flags.append(i)
            continue
        if end != "settled":
            continue
        r = rows[used - 1]
        if zone_at((r[0], r[1], r[2] - 1.0), int(r[6]) == SWIMMING, False) != zb:
            continue
        ends["landed in the to-zone"] = ends.get("landed in the to-zone", 0) + 1
        if min_rank({"kit": kit, "flaps": int(rows[:used, 7].max())}) > rank:
            continue
        cands.append((used, i, len(yaws) + used, None if first is None else len(yaws) + first))
    out |= {"strings": n, "ends": ends, "candidates": len(cands), "kernel_ticks": kt}
    found, tried, flown = None, out["confirms"], out["flagged_flown"]
    for _, i, used, first in sorted(cands)[:confirms]:        # the kernel's landings, fewest ticks first
        pi, st, k, yaws, c, b = string(i)
        o = {"segments": segments(_lpads(yaws, c, b, used, first)), "kit": kit, "macro": "generator",
             "flaps_planned": int(d["nf"][i]) if rank else 0, "flaps": 9 if rank else 0}
        at = dict(st[3], yaw=c)
        ans = KB.confirm(ks.l3, at, c, o)
        v = _verdict(ans, zb, rank, zone_at)
        tried[v] = tried.get(v, 0) + 1
        if v == "held":
            found = {"by": "kernel", "rank": min_rank(ans["outcome"]), "start": at, "heading": c, "kit": kit,
                     "segments": o["segments"], "land": ans["outcome"]["land"]}
            break
    for i in flags if found is None else ():                  # the flagged strings on FastL3, in draw order
        pi, st, k, yaws, c, b = string(i)
        at = dict(st[3], yaw=c)
        twin = ks.on_l3((*st[2][:2], (tuple(at["feet"]), c, at["cell"]), *st[2][3:]))
        if twin is None:
            flown["fault:start"] = flown.get("fault:start", 0) + 1
            continue
        ks.l3.reset(twin)
        end, used, row, fl = _l3fly(ks.l3, _lpads(yaws, c, b, len(yaws) + TICKS, None),
                                    l3.Pad((0.0, 0.0), frozenset(), c), len(yaws), int(d["run"][i]))
        feet = runner._feet(row) if row is not None else None
        v = (end if end != "settled" else "landed elsewhere"
             if zone_at(feet, row.state == SWIMMING, False) != zb else
             "over the kit" if min_rank({"kit": kit, "flaps": fl}) > rank else None)
        if v is None:
            try:
                for _ in range(hold.HOLD):
                    row = ks.l3.step(l3.Pad())
            except l3.L3Error as exc:
                v = f"fault:{str(getattr(exc, 'site', 'other')).split('@')[0]}"
            else:
                v = ("held" if settled(row) and zone_at(runner._feet(row), row.state == SWIMMING, False) == zb
                     else "left in the hold")
        flown[v] = flown.get(v, 0) + 1
        if v == "held":
            found = {"by": "l3", "rank": min_rank({"kit": kit, "flaps": fl}), "start": at, "heading": c, "kit": kit,
                     "segments": segments(used), "land": list(feet)}
            break
    return out | {"real": found is not None, "rank": found and found["rank"], "by": found and found["by"],
                  "witness": found}


def _gen_spec(smp: Sampler, s: str, n: int, za: str, zb: str) -> dict | None:
    """The generator's spec of pair ``za`` > ``zb`` (stratum ``s``, its place ``n``): the from-zone's border points
    (the takeoff side's, binned), their cells, each one's bearing to the to-zone's nearest point (the landing side's)
    and ``zfloor``, :data:`GEN_BELOW_M` under the to-zone's lowest logic sample or water surface; None when a zone
    has no border point."""
    f, t = smp._zone(smp.src, za), smp._zone(smp.dst, zb)
    if not len(f) or not len(t):
        return None
    pts = [smp._xyz(smp.src, i) for i in f]
    tx, ty = smp.dst["x"][t], smp.dst["y"][t]
    near = [int(np.argmin(np.hypot(tx - p[0], ty - p[1]))) for p in pts]
    kit = s.split("-")[1]
    return {"level": smp.level, "stratum": s, "seq": n, "pair": [za, zb], "kit": kit,
            "points": [list(p) for p in pts], "cells": [list(c) for c in smp.nodes.cells(pts)],
            "bearing": [heading_to(p, (float(tx[k]), float(ty[k]))) for p, k in zip(pts, near)],
            "zfloor": smp.zmin(zb) - GEN_BELOW_M[kit]}


def _keyed(j: dict, snap: dict, touch12: str, kspec: dict | None) -> dict:
    """Job ``j`` keyed (``cache.job_key``; with ``kspec``, the kernel route's key and backend)."""
    j["key"] = cache.job_key(j, snap["meta_sha12"], touch=touch12)
    if kspec is not None:
        from devkit.reach.native import backend as KB
        j["key"], j["backend"] = KB.key(j["key"], kspec["census12"]), "kernel"
    return j


def _classed(R: Run, smp: Sampler, nodes, rows: list[dict], wit: dict, snap: dict, touch12: str, kspec: dict,
             base: Path) -> None:
    """Each row the generator holds whose pair ``R`` lacks (its ``r_real`` False) classed (the module docstring): R's
    aim from the generator's start at its landing, then where that holds no find its refinement twinned to it, on
    the kernel route, find the pair (``targeting``) or not (``movement``); ``class_cpu`` their price."""
    todo = []
    for row in rows:
        w = wit.get((row["stratum"], row["from"], row["to"]))
        if not row.get("real") or row.get("r_real") is not False or w is None:
            continue
        src, land = tuple(w["start"]["feet"]), tuple(w["land"])
        if (region := nodes.region_at(src)) is None:
            row["class"] = "no walkable takeoff"
            continue
        dst = nodes.snap(land, row["to"]) or land
        j = _keyed(smp.aim_at(f"g{row['stratum']}:{row['seq']}", row["from"], row["to"], row["kit"], src, dst, land,
                              region), snap, touch12, kspec)
        todo.append((row, [j]))
    for stage in (0, 1):
        R.jobs([js[-1] for _, js in todo])
        live = []
        for row, js in todo:
            pair = (row["from"], row["to"])
            g, recs = _graph(nodes, js, base, pair, KITS[row["kit"]])
            live.append((row, js, g, recs))
        R.hold([g for _, _, g, _ in live])
        todo = []
        for row, js, g, recs in live:
            if _found(g, (row["from"], row["to"]), recs) is not None:
                row["class"] = "targeting"
            elif any(cache.get(base, j["key"]) is None for j in js):
                row["class"] = "error"
            elif stage == 0:
                r = {k: v for k, v in js[0].items() if k not in ("env", "key", "backend")}
                r.update(id="r" + js[0]["id"][1:], macros=[list(m) for m in aim.refine(*js[0]["cert"])])
                todo.append((row, js + [_keyed(aim.twinned(r, js[0], cache.get(base, js[0]["key"])), snap, touch12,
                                               kspec)]))
            else:
                row["class"] = "movement"
            keys = {j["key"] for j in js}
            row["class_cpu"] = round(sum(R.cost[k]["cpu"] for k in keys if k in R.cost)
                                     + sum(v["cpu"] for h, v in R.held.items() if h[0] in keys), 3)


def generate(a) -> dict:
    """The generator (the module docstring) on the run's pairs, each pair's row frozen (``truth/NAME.jsonl``; its
    witness, positions and strings, in the private ``truth/NAME-witness-<time>.json.gz``); the counts by stratum."""
    from devkit.rando.draft.author import read_derived
    derived = read_derived(a.level)
    fdoc, out_p, frozen = _setup(a, derived)
    snap, base = RE._snap(a.snapshot, a.store), cache.folder(a.level)
    nodes = RE._nodes(a.level)
    t0 = time.time()
    smp = Sampler(a.level, derived, nodes)
    touch, touch12 = _targets(nodes, base)
    kspec = _kspec(a.level, snap, touch)
    zones = RE._zones(a.level, [{"stop": {"zoning": smp.zoned}}])
    specs, rows = [], []
    for s, n, (za, zb, slack) in _want(a, fdoc, frozen):
        spec = _gen_spec(smp, s, n, za, zb)
        rows.append({"stratum": s, "seq": n, "from": za, "to": zb, "kit": s.split("-")[1], "slack": slack,
                     "na": None if spec else "a zone with no border point"})
        specs += [spec] if spec else []
    code = _code("fast", kspec["census12"]) | {"generator": {
        "strings": a.strings, "flagged": a.flagged, "confirms": a.confirms, "seed": a.seed, "run_max": GEN_RUN_MAX,
        "cone_deg": round(math.degrees(GEN_CONE)), "flaps": GEN_FLAPS, "recasts": GEN_RECASTS, "window": GEN_WINDOW}}
    print(json.dumps({"frozen_already": len(frozen), "pairs": len(specs), "setup_s": round(time.time() - t0)}),
          flush=True)
    by = {(r["stratum"], r["from"], r["to"]): r for r in rows}
    wit, errors = {}, 0
    with RE._pool(snap, a.workers, "fast", kernel=kspec) as pool:
        for k, got in enumerate(pool.completed(gen_task, [(sp, str(zones), a.seed, a.strings, a.flagged, a.confirms)
                                                         for sp in specs]), 1):
            row = by[tuple(got.pop("key"))]
            if "error" in got:
                errors += 1
                row["error"] = got["error"]
                continue
            if (w := got.pop("witness")) is not None:
                wit[(row["stratum"], row["from"], row["to"])] = w
            row.update(got)
            if k % 10 == 0 or k == len(specs):
                print(json.dumps({"pairs": k, "of": len(specs), "real": sum(bool(r.get("real")) for r in rows),
                                  "errors": errors, "s": round(time.time() - t0)}), flush=True)
        if a.against:
            rr: dict[tuple, bool] = {}
            for name in a.against:
                for r in _read(a.level, name):
                    k = (r["stratum"], r["from"], r["to"])
                    rr[k] = rr.get(k, False) or bool(r.get("real")) or bool(r.get("refly_real"))
            for row in rows:
                row["r_real"] = rr.get((row["stratum"], row["from"], row["to"]))
            R = Run(a, pool, snap, base, touch, zones)
            R.zones = zones
            try:
                _classed(R, smp, nodes, rows, wit, snap, touch12, kspec, base)
            except Exception as exc:  # noqa: BLE001 (the generator's rows are the run's price: frozen unclassed)
                import traceback
                traceback.print_exc()
                for row in rows:
                    if row.get("real") and row.get("r_real") is False and not row.get("class"):
                        row["class"] = f"error: {type(exc).__name__}"
    keep = [r | {"code": code, "frame": fdoc and fdoc["seed"], "frame_zoning": fdoc and fdoc["zoning"],
                 "snapshot": snap["meta_sha12"]} for r in rows if "error" not in r]
    with open(out_p, "a", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, sort_keys=True) + "\n" for r in keep))
    if wit:
        cache.write(_folder(a.level) / f"{a.name}-witness-{int(time.time())}.json.gz",
                    {f"{k[0]}:{k[1]}>{k[2]}": v for k, v in wit.items()}, zipped=True)
    summ: dict[str, dict] = {}
    for r in keep:
        d = summ.setdefault(r["stratum"], {"pairs": 0, "na": 0, "real": 0, "by": {}, "classes": {}, "cpu_s": 0.0,
                                           "kernel_ticks": 0, "l3_ticks": 0, "strings": 0, "ends": {}})
        d["pairs"] += 1
        d["na"] += bool(r["na"])
        d["real"] += bool(r.get("real"))
        for k_, v in (("by", r.get("by")), ("classes", r.get("class"))):
            if v:
                d[k_][v] = d[k_].get(v, 0) + 1
        d["cpu_s"] = round(d["cpu_s"] + r.get("cpu", 0.0) + r.get("class_cpu", 0.0), 1)
        for k_ in ("kernel_ticks", "l3_ticks", "strings"):
            d[k_] += r.get(k_, 0)
        for e, v in r.get("ends", {}).items():
            d["ends"][e] = d["ends"].get(e, 0) + v
    return {"level": a.level, "name": a.name, "code": code, "snapshot": snap["meta_sha12"], "pairs": len(keep),
            "errors": errors, "wall_s": round(time.time() - t0), "summary": summ,
            "rows": [{k: v for k, v in r.items() if k != "code"} for r in keep]}


# -- Chapman (Step R2.19c2a) ------------------------------------------------------------------------------------------

def _chapman(n1: int, n2: int, m: int) -> tuple[float, float]:
    """Chapman's estimate of a population two captures of ``n1`` and ``n2`` with ``m`` in both saw, and its
    variance (Seber's)."""
    return ((n1 + 1) * (n2 + 1) / (m + 1) - 1,
            (n1 + 1) * (n2 + 1) * (n1 - m) * (n2 - m) / ((m + 1) ** 2 * (m + 2)))


def chapman(a) -> dict:
    """The links both R and the engine miss (the module docstring): on the pairs the generator (``--gen``) and R
    (``--r``: a pair real in any name's row, a re-fly's find too) share, per stratum the first capture (R or the
    engine, ``--graph``'s zone edges at the pair's kit), the second (the generator), both, Chapman's estimate, the
    estimated links both R and the engine miss (the estimate less the first capture) as a share of R's real links
    (B4's "of nd R-real"), and the generator's links R missed by class; pooled over the strata by the frame's weights
    (each stratum's frame pairs / its sampled pairs; the interval from the strata's variances)."""
    g = json.loads(Path(a.graph).read_text(encoding="utf-8"))
    ranks = {(e["from"], e["to"]): min(int(r) for r in e["ranks"]) for e in g["zone_edges"]}
    rr: dict[tuple, bool] = {}
    for name in a.r:
        for r in _read(a.level, name):
            if not r["na"]:
                k = (r["stratum"], r["from"], r["to"])
                rr[k] = rr.get(k, False) or bool(r.get("real")) or bool(r.get("refly_real"))
    gen = {(r["stratum"], r["from"], r["to"]): r for r in _read(a.level, a.gen) if not r["na"]}
    sizes = None
    if frames := {(r["frame_zoning"], r["frame"]) for r in gen.values() if r.get("frame_zoning")}:
        zoned, seed = frames.pop()
        sizes = {s: len(v) for s, v in json.loads(gzip.decompress(_frame_path(a.level, zoned, seed).read_bytes()))[
            "strata"].items()}
    out, pool = {}, {"first": 0.0, "r_real": 0.0, "miss": 0.0, "var": 0.0}
    for s in sorted({k[0] for k in gen}):
        keys = [k for k in gen if k[0] == s and k in rr]
        if not keys:
            continue
        first = {k for k in keys if rr[k] or ranks.get(k[1:], 9) <= KITS[gen[k]["kit"]]}
        second = {k for k in keys if gen[k].get("real")}
        n1, n2, m, nr = len(first), len(second), len(first & second), sum(rr[k] for k in keys)
        est, var = _chapman(n1, n2, m)
        sd = math.sqrt(var)
        cls: dict[str, int] = {}
        for k in second:
            if not rr[k]:
                cls[gen[k].get("class") or "unclassed"] = cls.get(gen[k].get("class") or "unclassed", 0) + 1
        out[s] = {"pairs": len(keys), "r_real": nr, "first": n1, "second": n2, "both": m,
                  "chapman": round(est, 2), "ci95": [round(max(est - 1.96 * sd, len(first | second)), 2),
                                                     round(est + 1.96 * sd, 2)],
                  "missed_by_r_and_engine": round(est - n1, 2),
                  "share_of_r_real": round((est - n1) / nr, 4) if nr else None,
                  "generator_not_r": sum(not rr[k] for k in second), "generator_not_r_by_class": cls,
                  "generator_only": sorted(f"{k[1]}>{k[2]}" for k in second - first)}
        if sizes and s in sizes:
            w = sizes[s] / len(keys)
            out[s]["weight"] = round(w, 3)
            pool["first"] += w * n1
            pool["r_real"] += w * nr
            pool["miss"] += w * (est - n1)
            pool["var"] += w * w * var
    pooled = None
    if pool["r_real"]:
        h, nr = 1.96 * math.sqrt(pool["var"]), pool["r_real"]
        pooled = {"first_est": round(pool["first"]), "r_real_est": round(nr), "missed_est": round(pool["miss"]),
                  "share": round(pool["miss"] / nr, 4),
                  "ci95": [round((pool["miss"] - h) / nr, 4), round((pool["miss"] + h) / nr, 4)]}
    return {"level": a.level, "r": a.r, "gen": a.gen, "graph_core": g.get("core"), "strata": out, "pooled": pooled}


def _summary(rows: list[dict]) -> dict:
    out = {}
    for s in sorted({r["stratum"] for r in rows}):
        rs = [r for r in rows if r["stratum"] == s and not r["na"]]
        real = [r for r in rs if r["real"]]
        by: dict[str, int] = {}
        for r in real:
            by[r["by"].split(" pass")[0]] = by.get(r["by"].split(" pass")[0], 0) + 1
        out[s] = {"pairs": len(rs), "na": sum(1 for r in rows if r["stratum"] == s and r["na"]), "real": len(real),
                  "real_rate": round(len(real) / len(rs), 3) if rs else None, "found_by": by,
                  "cpu_s": round(sum(r["cpu"] for r in rs), 1), "steps": sum(r["steps"] for r in rs),
                  "cpu_s_a_pair": round(sum(r["cpu"] for r in rs) / len(rs), 2) if rs else None,
                  "steps_a_pair": round(sum(r["steps"] for r in rs) / len(rs)) if rs else None,
                  "jobs_priced": sum(r["priced"] for r in rs), "jobs_ran": sum(r["ran"] for r in rs),
                  "jobs_engine_cached": sum(r["engine_cached"] for r in rs),
                  "missing_records": sum(r["missing"] for r in rs)}
    return out


# -- recall -------------------------------------------------------------------------------------------------------------

def _wilson(k: int, n: int, z: float = 1.96) -> list | None:
    if not n:
        return None
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def recall(a) -> dict:
    """The engine's (``--graph``: ``reach_engine.py graph``'s zone edges) recall against the frozen R results: per
    stratum (``nd-air3`` per slack band), and pooled over them by their weights (:func:`_weights`; Wilson's interval
    on the R-real links' Kish number).  A pair frozen under more than one ``--name`` counts once, real when any
    name's R held it (a re-fly's find too, as ``chapman`` reads R)."""
    g = json.loads(Path(a.graph).read_text(encoding="utf-8"))
    ranks = {(e["from"], e["to"]): min(int(r) for r in e["ranks"]) for e in g["zone_edges"]}
    by: dict[tuple, dict] = {}
    for n in a.name:
        for r in _read(a.level, n):
            k = (r["stratum"], r["from"], r["to"])
            by[k] = r | {"real": bool(r.get("real") or r.get("refly_real") or by.get(k, {}).get("real"))}
    rows = list(by.values())
    out = {}
    for s in sorted({_band(r["stratum"], r.get("slack")) for r in rows}):
        rs = [r for r in rows if _in(r, s) and not r["na"]]
        eng = [r for r in rs if ranks.get((r["from"], r["to"]), 9) <= KITS[r["kit"]]]
        real = [r for r in rs if r["real"]]
        hit = [r for r in real if r in eng]
        out[s] = {"pairs": len(rs), "r_real": len(real), "engine_found": len(eng), "engine_found_r_real": len(hit),
                  "recall_vs_r": round(len(hit) / len(real), 4) if real else None, "ci95": _wilson(len(hit), len(real)),
                  "r_misses": len([r for r in eng if not r["real"]]),
                  "engine_misses": sorted(f"{r['from']}>{r['to']}" for r in real if r not in eng)}
    pooled = None
    if frames := {(r["frame_zoning"], r["frame"]) for r in rows}:
        if len(frames) > 1:
            raise SystemExit(f"the names' pairs come from {len(frames)} frames: pool one frame's")
        zoned, seed = frames.pop()
        fdoc = json.loads(gzip.decompress(_frame_path(a.level, zoned, seed).read_bytes()))
        w = _weights(_sizes(fdoc), rows)
        real = [r for r in rows if r.get("real")]
        found = [r for r in real if ranks.get((r["from"], r["to"]), 9) <= KITS[r["kit"]]]
        (sr, kish), (sf, _) = (_pooled([w[_band(r["stratum"], r.get("slack"))] for r in x]) for x in (real, found))
        pooled = {"r_real": len(real), "engine_found_r_real": len(found), "kish_n_real": round(kish, 1),
                  "recall_vs_r": round(sf / sr, 4) if sr else None,
                  "ci95": _wilson(sf / sr * kish, kish) if sr else None}
    known = [{**k, "engine_rank": ranks.get((k["from"], k["to"])) if k["kind"] == "zone" else "node: c2"}
             for k in KNOWN_REAL if k["level"] == a.level]
    return {"level": a.level, "names": a.name, "graph_records": g.get("records"), "graph_core": g.get("core"),
            "strata": out, "pooled": pooled, "known_real": known}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("frame", "run", "recall", "calib", "generate", "chapman"):
        p = sub.add_parser(name)
        p.add_argument("level")
        p.add_argument("--out", required=True)
        if name in ("frame", "run", "generate"):
            p.add_argument("--seed", type=int, default=SEED)
        if name in ("run", "generate"):
            p.add_argument("--snapshot", required=True)
            p.add_argument("--store")
            p.add_argument("--name", required=True)
            p.add_argument("--strata", nargs="+", choices=STRATA + BANDS, default=list(STRATA))
            how = p.add_mutually_exclusive_group(required=True)
            how.add_argument("--take", type=int)
            how.add_argument("--like", nargs="+")
            how.add_argument("--pairs", nargs="+")
            p.add_argument("--skip", type=int, default=0)
            p.add_argument("--workers", type=int)
        if name == "run":
            how.add_argument("--quota", type=int)
            p.add_argument("--per", type=int, default=QUOTA_PER)
            p.add_argument("--cap", type=int, default=CAP)
            p.add_argument("--step", type=int, default=STEP)
            p.add_argument("--l3", choices=("fast", "base"), default="fast")
            p.add_argument("--backend", choices=("l3", "kernel"), default="l3")
            p.add_argument("--refly", action="store_true")
        if name == "generate":
            p.add_argument("--strings", type=int, default=GEN_STRINGS)
            p.add_argument("--flagged", type=int, default=GEN_FLAGGED)
            p.add_argument("--confirms", type=int, default=GEN_CONFIRMS)
            p.add_argument("--against", nargs="+")
        if name == "recall":
            p.add_argument("--name", nargs="+", required=True)
            p.add_argument("--graph", required=True)
        if name == "calib":
            p.add_argument("--kernel", required=True)
            p.add_argument("--fast", nargs="+", required=True)
        if name == "chapman":
            p.add_argument("--r", nargs="+", required=True)
            p.add_argument("--gen", required=True)
            p.add_argument("--graph", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "run" and a.refly and a.backend != "kernel":
        ap.error("--refly flies the kernel route's failed confirms again: it needs --backend kernel")
    out = {"frame": frame, "run": run, "recall": recall, "calib": calib, "generate": generate,
           "chapman": chapman}[a.cmd](a)
    print(json.dumps({"out": l3.private_out(a.out, out, indent=1).name}))


if __name__ == "__main__":
    main()
