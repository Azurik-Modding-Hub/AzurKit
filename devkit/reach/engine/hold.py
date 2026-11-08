"""The reach engine's hold (Step R2.16d, its skeptic's K2): a zone witness counts only where its body stays.

A launch ends ``settled`` once the body has been settled ``macros.STILL`` ticks (a swimmer then held at rest
``macros.SWIM_HOLD`` more), and a body that lands teetering on a brink, or slides, stands that long and then leaves:
of w1's 2,873 edges found at their kit on 9c3db5ac's engine and Step R2.16d's aims, 117 left their to-zone within
:data:`HOLD` idle ticks after the string, 116 of them standing landings, the sitting's t8522h1 among them (xemu
replays it as L3 runs it).  So a witness is replayed from scratch on the snapshot (:func:`replay`: R6 onto its start
at its yaw, its kit, its pads: ``verdict.witness``'s recipe) and held :data:`HOLD` ticks at rest after; it
:func:`stays` when the body is still settled in its to-zone then.  An aim's hit is so checked as it is found
(``aim.run_job``: a hit that leaves is none, so the job's later passes still run), its answer kept in the outcome
(``hold``); every other zone witness at the graph (``graph.Graph.hold``, on ``devkit/reach/reach_engine.py``'s pool), its
answer cached apart (:func:`key`: the L3 core and this file, so a change here re-runs no launch).  Positions stay in
memory and the private cache.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from devkit.reach.engine import cache
from devkit.reach.engine.macros import SETTLED, SWIMMING, settled
from devkit.reach.engine.runner import SETTLE_START, _feet, place, set_kit
from devkit.sim import l3
from devkit.sim.l3 import L3Error, Pad

HOLD = 60          # [the skeptic's, D610] idle ticks after a witness's string it must stay through (SWIM_HOLD's)
SAME_M = 0.01      # a replay that ends this near its outcome's landing is the same launch (L3's: 0.0 m)
FILES = ("devkit/reach/engine/hold.py",)   # the code an answer depends on, beside ``cache.CORE_FILES``


def replay(sim, st: dict, heading: float, o: dict) -> dict:
    """Outcome ``o`` of start ``st`` (at its ``yaw``, else ``heading``) run again from the snapshot, then
    :data:`HOLD` ticks at rest: where the body is then (``land``, ``state``), whether the string ended where ``o``
    did (``same``) and the L3 ticks it took; a raise is ``fault`` (no stay)."""
    pads, ticks = l3.pads(o["segments"]), SETTLE_START
    try:
        place(sim, st["feet"], st.get("yaw", heading), st["cell"])
        ticks += len(set_kit(sim, o["kit"]))
        row = None
        for p in pads:
            row, ticks = sim.step(p), ticks + 1
        same = row is not None and math.dist(_feet(row), o["land"]) <= SAME_M
        for _ in range(HOLD):
            row, ticks = sim.step(Pad()), ticks + 1
    except L3Error as exc:
        return {"fault": str(getattr(exc, "site", "other")), "ticks": ticks}
    return {"land": list(_feet(row)), "state": row.state, "settled": settled(row), "same": same, "ticks": ticks}


def stays(got: dict, to: str, zone_at) -> bool:
    """Whether :func:`replay`'s answer ``got`` holds the body in zone ``to`` (``zone_at``, the graph's rule):
    the same launch, settled there (``l3_search.settled``: standing, swimming or at rest on near-flat ice) :data:`HOLD`
    ticks on (an answer from before AZ-737's ``settled`` by its state)."""
    return bool(got.get("same")) and got.get("settled", got["state"] in SETTLED) and \
        zone_at(got["land"], got["state"] == SWIMMING, False) == to


def key(job: str, k: int) -> str:
    """The cache key of job ``job``'s (its key) outcome ``k``'s answer."""
    doc = {"core": cache.core(cache.CORE_FILES + FILES), "job": job, "outcome": k}
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:12]


def answer(base: Path, rec: dict, k: int) -> dict | None:
    """Record ``rec``'s outcome ``k``'s answer: the outcome's own (an aim's hit), else the cache's, else None."""
    o = rec["outcomes"][k]
    return o["hold"] if "hold" in o else cache.get(Path(base) / "hold", key(rec["key"], k))


def task(w, items, base: str) -> int:
    """A pool task: :func:`replay` each (job key, outcome) of ``items`` (by job) on the worker's L3, each answer
    cached, stamped with what ran it (``l3_impl``: ``worker.IMPL``, as a job record is; Step R2.19f+'s X1); their L3
    ticks."""
    from devkit.reach.engine import worker
    sim, b, rec, ticks = w.sim(False, deep=False), Path(base), None, 0
    (b / "hold").mkdir(mode=0o700, exist_ok=True)
    for job, k in items:
        rec = rec if rec is not None and rec["key"] == job else cache.get(b, job)
        o = rec["outcomes"][k]
        got = replay(sim, rec["starts"][o["start"]], rec["heading"], o)
        cache.put(b / "hold", key(job, k), got | {"l3_impl": dict(worker.IMPL)})
        ticks += got["ticks"]
    return ticks
