"""The reach engine's runner (Step R2.16a; the R2.16 design §2c): a job on simulator Level 3, and the pool tasks.

A job is a takeoff and a heading: ``starts`` the feet to place a run-up start and a standing start at
(``Nodes.starts``: 1 m and 0.3 m behind the takeoff on its floor or its floor face, then nearer), ``cells`` the rooms
to place them in and ``macros`` its launches (:class:`macros.Macro`'s fields); a targeted aim's (one with a
``target``) is :mod:`.aim`'s, keyed by its own code too (``cache.AIM_FILES``), so an aim-only change re-runs no fan
job.  :func:`run_job`, per start (:func:`find_start`): from the snapshot, an R6 teleport facing the heading and
:data:`SETTLE_START` ticks at rest, which must leave the body standing within :data:`START_XY` (and :data:`START_Z`)
of where it was put; else the same feet in the job's next cell, the snapshot's own first (AZ-488: a wrong room's
placement doesn't land), then the next feet; a start none of them gives is dropped and counted, never an edge.  Then, per
kit branch, R2's element levels (and with air, the shield cast by LT+Y, on the tick after the release:
``l3_search.CAST_WAIT``) and the camera turned to the heading (``macros.align``: its ticks open each witness
string), saved; each macro runs from that saved state, those differing only in their flaps together
(:func:`macros.launches`).

An outcome (private: the cache's) holds where the body settled and first touched down (feet), its state there,
where it took off (its last standing row before the air), how the launch ended, its ticks, the HP it lost, the most
flaps it made in one jump, the trigger, push and damage volumes and pickups its body centre touched (ids),
``tricks_detect``'s labels, the run's taint and its witness: the pads as ``l3.pads`` segments and their
``string_sha12`` after the place struct and the kit (:func:`witness_prefix`: no pad holds the kit, so one string
from one start in two kits is two witnesses).  A found witness is the evidence (D277, D661: no jitter replays).
Positions stay in memory and the private cache.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path

import numpy as np

from devkit.reach.engine import cache
from devkit.reach.engine.macros import AIRBORNE, BACK_RUN, BACK_STAND, KITS, R0, Macro, align, launches
from azurkit.tools.randomizer.live import recipes
from devkit.sim.inputs import wrap
from devkit.sim.l3 import L3Error, Pad
from devkit.sim.l3_search import CAST_WAIT, segments, string_sha12

HEADINGS = (0.0, math.radians(40.0), -math.radians(40.0))   # [default, the design's R0] the outward normal, +-40 deg
SETTLE_START = 20     # ticks at rest after a teleport (l3_certify's SETTLE): the start's settle
START_XY, START_Z = 0.75, 0.6   # [proposal] a settled start this near (m) where it was put stands on its floor
CAST = ("cast", "LT+Y")


def _feet(row) -> tuple[float, float, float]:
    return row.pos[0], row.pos[1], row.pos[2] - 1.0


def _cam(row) -> float:
    cx, cy = struct.unpack("<2f", row.cam)
    return math.atan2(-cx, cy)


def place_sha12(feet, yaw: float, cell: int) -> str:
    """sha256[:12] of R6's place struct (a record names a teleport by it)."""
    return hashlib.sha256(recipes.place_struct(feet, yaw, cell=cell)).hexdigest()[:12]


def witness_prefix(feet, heading: float, cell: int, kit: str) -> bytes:
    """What a witness string's sha12 is taken after: R6's place struct (``l3_certify``'s rule) and the kit branch
    (:data:`macros.KITS`: its R2 levels and, with air, the cast), which no pad holds."""
    return recipes.place_struct(feet, heading, cell=cell) + json.dumps(KITS[kit], sort_keys=True).encode()


def here_cell(sim) -> int:
    """The cell (room) the snapshot's player stands in."""
    sim.reset()
    return recipes.cell_of(sim.u32, sim.u32(sim.entity + 0x20), recipes.chain(sim.u32))


def place(sim, feet, heading: float, cell: int):
    """From the snapshot: R6 onto ``feet`` facing ``heading`` in ``cell`` and :data:`SETTLE_START` ticks at rest;
    the last row."""
    sim.reset()
    sim.teleport(tuple(feet), heading, cell=cell)
    row = None
    for _ in range(SETTLE_START):
        row = sim.step(Pad())
    return row


def find_start(sim, feet_list, heading: float, cells, ok=None, tries: int = 0) -> dict:
    """The first of ``feet_list`` x ``cells`` (in that order) whose placement stands where it was put (the module
    docstring; with ``ok``, also where ``ok`` takes its settled feet): its feet, cell, settled feet, tries (counted
    on from ``tries``) and place sha12, or ``{"tries": n}`` for none."""
    for f in feet_list:
        for c in cells:
            tries += 1
            try:
                r = place(sim, f, heading, c)
            except L3Error:
                continue
            g = _feet(r)
            if (r.state == 0 and math.hypot(g[0] - f[0], g[1] - f[1]) <= START_XY and abs(g[2] - f[2]) <= START_Z
                    and (ok is None or ok(g))):
                return {"feet": list(f), "cell": int(c), "settled": list(g), "tries": tries, "hp": r.hp,
                        "cam": _cam(r), "place_sha12": place_sha12(f, heading, c)}
    return {"tries": tries}


def set_kit(sim, kit: str) -> list:
    """R2's element levels of kit branch ``kit`` (every other level 0) at one step's entry and, with air, the
    shield cast by input; the rows."""
    rows = [sim.step(writes=sim.kit_writes(KITS[kit]))]
    if KITS[kit].get("air"):
        rows += [sim.step(p) for p in [Pad(buttons=frozenset({"lt", "y"}))] + [Pad()] * CAST_WAIT]
    return rows


class Touch:
    """The volumes and pickups a body centre touches (``Nodes.targets``' arrays): :meth:`at` a point's ids."""

    def __init__(self, doc: dict) -> None:
        from devkit.sim.faces import Volumes
        V = [np.asarray(v, dtype=np.float64).reshape(-1, 3, 3) for v in doc["V"]]
        cut = np.cumsum([0] + [len(v) for v in V])
        self.vol = Volumes(np.concatenate(V) if V else np.zeros((0, 3, 3)),
                           [np.arange(a, b) for a, b in zip(cut[:-1], cut[1:])])
        self.vol.ids = list(doc["ids"])
        self.pick_ids = [i for i, _ in doc["picks"]]
        self.pick_pts = np.asarray([p for _, p in doc["picks"]], dtype=np.float64).reshape(-1, 3)
        self.radius = float(doc.get("pick_m", 1.5))

    def at(self, pos) -> tuple[list[int], list[str]]:
        p = np.asarray(pos, dtype=np.float64)
        picks = np.nonzero(np.linalg.norm(self.pick_pts - p, axis=1) <= self.radius)[0] if len(self.pick_pts) else []
        return self.vol.holding(p) if self.vol.ids else [], [self.pick_ids[i] for i in picks]


def _took(rows) -> int | None:
    """The index of a launch's last standing row before it first went airborne (its takeoff), None if none."""
    k = next((k for k, r in enumerate(rows) if r.state in AIRBORNE), None)
    return None if k is None else next((j for j in range(k - 1, -1, -1) if rows[j].state == 0), None)


def outcome(m: Macro, pads, rows, end: str, first, hp0: int, place: bytes, touch: Touch | None, taint) -> dict:
    """A launch's outcome record (the module docstring); ``place`` the string's prefix (:func:`witness_prefix`)."""
    from devkit.sim.tricks_detect import detect, from_l3
    vols, picks = set(), set()
    if touch is not None:
        for r in rows:
            v, p = touch.at(r.pos)
            vols.update(v)
            picks.update(p)
    last = rows[-1] if rows else None
    took = _took(rows)
    return {"macro": m.name, "kit": m.kit, "flaps_planned": m.flaps, "end": end, "ticks": len(rows),
            "land": list(_feet(last)) if last else None, "land_state": last.state if last else None,
            "first": list(_feet(rows[first])) if first is not None else None,
            "first_state": rows[first].state if first is not None else None,
            "took": list(_feet(rows[took])) if took is not None else None,
            "hp0": hp0, "hp_min": min((r.hp for r in rows), default=hp0),
            "flaps": max(((r.obs.flaps_used or 0) for r in rows if r.obs is not None), default=0),
            "labels": sorted({e.name for e in detect(from_l3(rows, pads))}) if rows and rows[0].obs else [],
            "volumes": sorted(vols), "picks": sorted(picks), "taint": sorted(taint),
            "segments": segments(pads, rows), "string_sha12": string_sha12(pads, place, rows=rows)}


def _job(nodes, t, heading: float, macros, zone: str | None = None, **extra) -> dict:
    return {"takeoff": t.i, "sample": t.sample, "region": t.region, "takeoff_feet": list(t.feet), "heading": heading,
            "starts": {"run": [list(f) for f in nodes.starts(t, heading, BACK_RUN, zone)],
                       "stand": [list(f) for f in nodes.starts(t, heading, BACK_STAND, zone)]},
            "cells": list(t.cells), "macros": [list(m) for m in macros], **extra}


def fan_jobs(nodes, takeoffs, macros=R0, headings=HEADINGS) -> list[dict]:
    """R0's fan (the design §1): a job per takeoff and heading (its outward normal and each of ``headings`` off
    it), every macro of ``macros`` from it; ids ``t<takeoff>h<heading index>``."""
    return [_job(nodes, t, wrap(t.heading + d), macros, id=f"t{t.i}h{k}")
            for t in takeoffs for k, d in enumerate(headings)]


def run_macros(sim, rec: dict, ms, heading: float, takeoff, starts: dict, cells, touch: Touch | None = None, *,
               find=find_start, memo: dict | None = None, name: str = "", target=None, ctl=None, done=None) -> bool:
    """Run macros ``ms`` (:class:`macros.Macro` s) along ``heading`` into job record ``rec`` (:func:`run_job`): each
    start (``starts[variant]``, the feet ``find`` tries: :func:`find_start`) and kit branch set up the first time a
    macro needs it (kept in ``memo`` for a later call from the same starts), ``rec["starts"][variant + name]`` what
    it gave, and with each macro the later ones of its start, kit and kind that differ from it only in their flaps
    (``macros.launches``: their shared ticks stepped once), under controller ``ctl`` at ``target(m)``; each outcome
    appended to ``rec["outcomes"]``.  True once ``done(outcome, start)`` takes one (the rest don't run)."""
    memo = {} if memo is None else memo
    ran = set()
    for n, m in enumerate(ms):
        if n in ran:
            continue
        family = [k for k in range(n, len(ms)) if k not in ran and ms[k]._replace(flaps=0) == m._replace(flaps=0)]
        ran.update(family)
        kind = "stand" if m.stands else "run"
        variant = kind + name
        if variant not in rec["starts"]:
            st = rec["starts"][variant] = find(sim, starts[kind], heading, cells)
            memo[variant] = sim.save() if "cell" in st else None
        if memo[variant] is None:
            continue
        st = rec["starts"][variant]
        if (variant, m.kit) not in memo:
            sim.reset(memo[variant])
            try:
                rows = set_kit(sim, m.kit)
                turn, turned, cam = align(sim, _cam(rows[-1]), heading)
            except L3Error:
                memo[(variant, m.kit)] = None
            else:
                memo[(variant, m.kit)] = (sim.save(), turn, turned, cam, rows[-1].hp,
                                          witness_prefix(st["feet"], heading, st["cell"], m.kit))
        if (got := memo[(variant, m.kit)]) is None:
            continue
        state, turn, turned, cam, hp0, prefix = got
        back = ((takeoff[0] - st["feet"][0]) * -math.sin(heading)   # the run-up along the heading (a start the
                + (takeoff[1] - st["feet"][1]) * math.cos(heading))  # face rule moved off its line)
        sim.reset(state)
        gos = launches(sim, [ms[k] for k in family], heading, cam, tuple(st["feet"]), back,
                       target=None if target is None else target(m), ctl=ctl)
        k, stop = len(turn), False
        for f, go in zip(family, gos):
            o = outcome(ms[f], turn + go.pads, turned + go.rows, go.end, None if go.first is None else go.first + k,
                        hp0, prefix, touch, go.taint) | {"start": variant}
            rec["outcomes"].append(o)
            stop |= done is not None and done(o, st)
        if stop:
            return True
    return False


def run_job(sim, job: dict, touch: Touch | None = None, here: int | None = None, zone_at=None) -> dict:
    """Run ``job`` on ``sim`` (the module docstring; a targeted aim's: ``aim.run_job``, which stops by
    ``zone_at``): its macros in order (:func:`run_macros`).  Its record: ``key``, ``id``, ``heading``, ``starts``
    (per start tried, what :func:`find_start` gave) and ``outcomes`` (one per macro run whose start stood)."""
    here = here_cell(sim) if here is None else here
    if job.get("target") is not None:
        from devkit.reach.engine import aim
        return aim.run_job(sim, job, touch, here, zone_at)
    rec = {"key": job["key"], "id": job["id"], "heading": job["heading"], "starts": {}, "outcomes": []}
    run_macros(sim, rec, [Macro(*m) for m in job["macros"]], job["heading"], job["takeoff_feet"], job["starts"],
               [here] + [c for c in job["cells"] if c != here], touch)
    return rec


def summary(rec: dict) -> dict:
    """A job record's counts (no position): its key, starts found and dropped, outcomes, ticks and ends."""
    ends: dict[str, int] = {}
    for o in rec["outcomes"]:
        ends[o["end"]] = ends.get(o["end"], 0) + 1
    return {"key": rec["key"], "id": rec["id"], "outcomes": len(rec["outcomes"]),
            "starts": sum("cell" in s for s in rec["starts"].values()),
            "dropped": sum("cell" not in s for s in rec["starts"].values()),
            "ticks": sum(o["ticks"] for o in rec["outcomes"]), "ends": ends}


# -- pool tasks (devkit.reach.l3_pool's workers) ------------------------------------------------------------------

def _touch(w, path: str | None) -> Touch | None:
    if path is None:
        return None
    if getattr(w, "_reach_touch", (None,))[0] != path:
        w._reach_touch = (path, Touch(json.loads(Path(path).read_text(encoding="utf-8"))))
    return w._reach_touch[1]


def _zones(w, path: str | None):
    if path is None:
        return None
    if getattr(w, "_reach_zones", (None,))[0] != path:
        import pickle
        with open(path, "rb") as f:
            w._reach_zones = (path, pickle.load(f).zone_at)
    return w._reach_zones[1]


def job_task(w, jobs: list[dict], base: str, touch: str | None = None, zones: str | None = None) -> list[dict]:
    """Run ``jobs`` on a pool worker's L3 (player ticks, light observations), each record written to the cache
    folder ``base`` atomically as it finishes; their summaries; ``zones`` the pickled ``nodes.Zones`` aimed jobs
    stop by.  A job that raises is that job's (``error``, no record written, so a later run tries it again),
    never the batch's."""
    sim = w.sim(False, deep=False)
    if getattr(w, "_reach_here", None) is None:
        w._reach_here = here_cell(sim)
    out = []
    for job in jobs:
        try:
            rec = run_job(sim, job, _touch(w, touch), w._reach_here, _zones(w, zones))
        except Exception as exc:          # noqa: BLE001 (a fault L3 raised outside a launch, or a bug: kept by name)
            out.append({"key": job["key"], "id": job["id"], "error": f"{type(exc).__name__}: {exc}"[:300],
                        "outcomes": 0, "starts": 0, "dropped": 0, "ticks": 0, "ends": {}})
            continue
        cache.put(Path(base), job["key"], rec)
        out.append(summary(rec))
    return out

