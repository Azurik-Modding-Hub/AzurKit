"""The witness check (Step 4.78a, check v1: what "passes xemu checks" means for D1311): a reach witness replayed in
xemu from the game's own arrival on the engine snapshot's event clock, and judged by zones (dev only).

``plan`` picks the rows from a level's witness file (``reach-engine witness``'s ``azurik-l3-proof/1`` edge records),
ids only, each joined with its class fields from the cache's job records and the plans' graph (plan, backend,
macro, pass, rank, kit, swim, zone-mapping flags, the derived edge's kind or ``new``; ``cls`` their tags): every
record, or with ``--edges`` the witness of each (from, to, air) row of those rows files (its pair's at the least rank
at or under the row's air), ``--minus`` what another witness file lacks, ``--negatives hold`` the candidates whose
cached hold answer leaves (their records written privately beside ``--out``), and ``--per-class N`` each class's
first N by the sha256 of the record's ``ref`` (so any seat draws the same rows).  It refuses a witness file of
another zoning than the level's derived file or of a snapshot whose ``meta_sha12`` isn't the store's.

``run`` checks the rows in one sitting (``devkit.xemu.sitting``), a level at a time: the warm boot of
``vanilla-ig-new``'s SaveGame #2, R7 to the level's arrival (:data:`ARRIVALS`, the engine's snapshots'), R2 kit 0,
every popup seen, the player ticks run to the engine snapshot's event clock, an in-memory checkpoint and its RAM's
``control_state_sha12``.  Per row, from that checkpoint (the check, v1):

- **the start:** ``--start recipe`` (v1's proposal) takes one L3 snapshot a level at the arrival (into the L3
  store's ``witness-check/<NAME>/``, never ``reach-live``) and runs the witness record's own setup in L3 from it (its
  idle wait, R6 onto the start's feet at its yaw in its cell, the 20-tick settle, R2's kit, with air the cast), then
  the string and :data:`HOLD` idle ticks, every tick whose pad holds no camera carrying the record's start camera
  (``runner.find_start``'s ``cam``); xemu replays that whole run tick for tick with L3's writes and camera.
  ``--start placed`` is R2.16e's arm: the sitting's R6 and the game's own settle, R2, an L3 snapshot there, and from
  it a kit tick, the cast, the string and the hold.
- **a pass is all of:** the start stands (at the settle's end the body is in state 0 within ``runner.START_XY``
  across and ``START_Z`` up or down of the start's feet, and in the from-zone where the record's own start is), alive
  throughout (HP over 0, never state 7), in the to-zone at the string's last tick, settled there :data:`HOLD` ticks on
  (``hold.stays``' rule) and no level load before then.  Zones, never metres or tick equality: the xemu-to-L3
  comparison, the end's distance from the record and the HP lost are diagnostics.
- **verdicts:** PASS; START (the start doesn't stand: a false find); FRAGILE (L3 from the game's own start misses
  too); WORLD (L3 holds and the game doesn't: its HP falls under L3's, a hit state appears, a level loads, or it leaves
  L3's path); LEFT (L3 holds, the game reaches the to-zone and leaves it); STALL (a popup the replay couldn't clear);
  ERROR (the harness: a boot, a restore, a bugcheck, a timeout; run again once from a fresh arrival, and never
  counted against the link).
- **tries:** one (a replay is deterministic); only after a WORLD miss again at each later ``--phases`` wait (15 and
  30 idle ticks before the R6), a pass recording its ``wait``.  A popup on the way is cleared in place
  (``l3_certify.replay_clearing``) and is no new try.

Each try is a coordinate-free row in the evidence folder's ``results/runs.jsonl`` (``row: check``; the last of a row
``final``): the claim's ids and class fields, the verdict, the try, its phase, the HP lost, the string's ticks, the
start's distances, each stage's seconds, the sandbox, the xemu binary's and the disc's sha12, the arrival's
``control_state_sha12`` and the engine's three key sha12s.  Each final verdict's record, its ``replay`` filled
(``equal``, ``max_err_m``, ``ticks``, ``sitting``, ``check``, ``verdict``, ``tries``, ``wait``), is appended privately
beside its witness file (``<stem>.checked.jsonl``, mode 0600).  A run resumes: a row with a final verdict but ERROR
for its start is skipped.  The arrival snapshots are deleted at the end once ``devkit sim l3-hold --check`` holds
none of them (kept with ``--corpus STORE``, which appends every try's replay to that conformance corpus).

``tally`` counts the final verdicts by start, level and class with Wilson 95 % intervals (ERROR outside them), and
with ``--truth`` (kept ``runs.jsonl`` files: R2.16e's rows by level, from, to and air, a check's own by ``ref``) the
rows whose verdict moved.

    uv run --locked python -m devkit reach witness-check plan LEVEL --witness FILE --plan P [P ...]
        --snapshot LABEL [--store DIR] [--backend l3|kernel] [--edges ROWS.json ...] [--minus FILE]
        [--negatives hold] [--per-class N] --out ROWS.json
    nice -n 10 uv run --locked python -m devkit reach witness-check run NAME --rows ROWS.json [...] --ev DIR
        [--start recipe|placed] [--phases 0,15,30] [--corpus STORE]
    uv run --locked python -m devkit reach witness-check tally DIR [--truth KEPT.jsonl ...]

Positions and strings stay in memory, the private rows and the reach cache; nothing printed or kept in ``--ev`` holds
one (:func:`public`).  Dev only: never in pytest but its offline table test (no xemu), never a CLI verb.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import hashlib
import json
import math
import os
import struct
import time
import traceback
from pathlib import Path

from azurkit.tools.randomizer.live import recipes
from devkit.reach.engine import cache, hold
from devkit.reach.engine.macros import KITS, SETTLED, SWIMMING
from devkit.reach.engine.runner import SETTLE_START, START_XY, START_Z
from devkit.sim import l3
from devkit.sim.l3 import L3Error, Pad
from devkit.sim.l3_search import CAST_WAIT

CHECK = "v1"
PASS, START, FRAGILE, WORLD, LEFT, STALL, ERROR = "PASS", "START", "FRAGILE", "WORLD", "LEFT", "STALL", "ERROR"
DONE = frozenset({PASS, START, FRAGILE, WORLD, LEFT, STALL})   # a resumed run skips a row with one of these
HOLD = hold.HOLD          # idle ticks after the string the body must stay through
DEAD = 7                  # entity+0x94: the death check's state (alive: never this, HP over 0)
HIT = 0x102               # entity+0x94: the hit handler's state (13 ticks, the game reference's)
PHASES = (0, 15, 30)      # idle ticks before the R6 a try waits: the first, then one more each after a WORLD miss
SAVE_TAG, SAVE = "vanilla-ig-new", 2   # the D98 drive's new-game character, as the engine's snapshots were taken
PRESSES = 20              # A presses on the way to the snapshot's clock (a dialog) before the arrival fails
FOLDER = "witness-check"  # the L3 store's folder of a run's arrival snapshots (<FOLDER>/<NAME>/)
PRIVATE = frozenset({"pos", "feet", "land", "settled", "first", "took", "cam", "segments", "obs", "writes",
                     "centre", "quat"})   # keys that hold a position, a camera or a string: never in a public row
CLASS = ("from", "to", "rank", "kit", "id", "plan", "backend", "by", "macro", "pass", "swim", "flags", "derived",
         "cls", "negative", "edges", "string_sha12", "ticks")   # a row's ids a try's row carries (and its record_wait)
# The engine's per-level snapshots' arrivals (R7: the level's path, the playerLocation; the L3 store's
# reach-live/README.txt): the check arrives where its level's snapshot was taken.
ARRIVALS = {
    "w1": ("levels/water/w1", "W3_W1d"), "w2": ("levels/water/w2", "W1_W2"), "w3": ("levels/water/w3", "W1_W3d"),
    "w4": ("levels/water/w4", "W1_W4"), "a1": ("levels/air/a1", "E6_A1"), "a3": ("levels/air/a3", "W1_A3"),
    "a5": ("levels/air/a5", "A3_A5"), "a6": ("levels/air/a6", "A1_A6"), "airship": ("levels/air/airship", "startspot"),
    "d1": ("levels/death/d1", "D2_D1"), "d2": ("levels/death/d2", "D1_D2"), "e2": ("levels/earth/e2", "Town_E2"),
    "e5": ("levels/earth/e5", "E2a_E5a"), "e6": ("levels/earth/e6", "A1_E6"), "e7": ("levels/earth/e7", "E2_E7"),
    "f1": ("levels/fire/f1", "Town_F1"), "f2": ("levels/fire/f2", "F4_F2"), "f3": ("levels/fire/f3", "F1_F3"),
    "f4": ("levels/fire/f4", "F2_F4b"), "f6": ("levels/fire/f6", "F1_F6"), "life": ("levels/life", "Town_L1"),
    "town": ("levels/town", "W1_Town")}


# -- the judgement (pure) ---------------------------------------------------------------------------------------------

def _feet(pos) -> tuple[float, float, float]:
    return pos[0], pos[1], pos[2] - 1.0


def _fields(r) -> tuple:
    """A row's body centre, state and HP: an L3 ``Row``, a replay's dict or a snapshot's metadata."""
    return (r.pos, r.state, r.hp) if hasattr(r, "pos") else (r["pos"], r["state"], r["hp"])


def stands(row, feet, zone_at, frm: str | None) -> dict:
    """Whether the start stands at ``row`` (the settle's end; None: the run never got there): state 0 within
    ``START_XY`` across and ``START_Z`` up or down of the start's ``feet`` and, with ``frm``, in that zone."""
    if row is None:
        return {"stands": None}
    pos, state, _ = _fields(row)
    g = _feet(pos)
    xy, dz = math.hypot(g[0] - feet[0], g[1] - feet[1]), abs(g[2] - feet[2])
    inside = None if frm is None else zone_at(g, state == SWIMMING, False) == frm
    return {"stands": state == 0 and xy <= START_XY and dz <= START_Z and inside is not False,
            "start_xy_m": round(xy, 3), "start_z_m": round(dz, 3), "start_state": state, "start_in_from": inside}


def judge(rows, end: int, to: str, zone_at, land=None, held_land=None) -> dict:
    """A run's outcome (``rows``: its string ends at row ``end``, its hold :data:`HOLD` rows on): alive throughout,
    in ``to`` at the string's end, settled there at the hold's end; with ``land`` (``held_land``) the end's (the
    hold's) distance from the record's."""
    n = end + HOLD
    sts = [_fields(r) for r in rows[:n]]
    out = {"ticks": len(rows), "alive": all(hp > 0 and st != DEAD for _, st, hp in sts),
           "hp_min": min((hp for *_, hp in sts), default=None), "short": len(rows) < n, "in_to_end": False,
           "held": False}
    if 0 < end <= len(rows):
        pe, se, _ = sts[end - 1]
        out |= {"in_to_end": zone_at(_feet(pe), se == SWIMMING, False) == to, "state_end": se}
        if land is not None:
            out["end_vs_record_m"] = round(math.dist(_feet(pe), land), 3)
    if not out["short"]:
        ph, sh, _ = sts[n - 1]
        out |= {"held": sh in SETTLED and zone_at(_feet(ph), sh == SWIMMING, False) == to, "state_held": sh}
        if held_land is not None:
            out["held_vs_record_m"] = round(math.dist(_feet(ph), held_land), 3)
    out["pass"] = out["alive"] and out["in_to_end"] and out["held"]
    return out


def verdict(start: dict, game: dict, sim: dict, stop: str | None, hit: bool) -> str:
    """The try's verdict (the module docstring) from the start's stand, the game's and L3's :func:`judge`, how the
    replay ended and whether a hit state appeared in the game where L3 had none."""
    if stop == "stall":
        return STALL
    if start["stands"] is False:
        return START
    if game["pass"]:
        return PASS
    if not sim["pass"]:
        return FRAGILE
    if stop == "load" or hit or (game["hp_min"] is not None and sim["hp_min"] is not None
                                  and game["hp_min"] < sim["hp_min"]):
        return WORLD
    return LEFT if game["in_to_end"] and not game["held"] else WORLD


def public(row: dict) -> dict:
    """``row``, refused (ValueError) where a key at any depth may hold a position or a string (:data:`PRIVATE`)."""
    def walk(v, where: str) -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                if k in PRIVATE:
                    raise ValueError(f"a public row holds {where}{k}")
                walk(x, f"{where}{k}.")
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x, where)
    walk(row, "")
    return row


def order(ref: str) -> str:
    """A record's place in a class's sample: the sha256 of its ``ref``."""
    return hashlib.sha256(ref.encode()).hexdigest()


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """The Wilson interval of ``k`` passes in ``n`` (95 % by default); None for none."""
    if not n:
        return None
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def read_jsonl(path) -> list[dict]:
    return [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


# -- plan -------------------------------------------------------------------------------------------------------------

def setup_of(w: dict) -> dict:
    """A witness record's R6 step (its job, start, yaw, cell, place sha12) and its idle wait."""
    out = {"wait": 0}
    for step in w["start"]["setup"]:
        if step[0] == "idle":
            out["wait"] = int(step[1])
        elif step[0] == "R6":
            out |= step[1]
    return out


def refuse(ws, level: str, zoning: str, meta_sha12: str, name: str) -> None:
    """Refuse (SystemExit) a witness file holding a record of another level, of another zoning than the level's
    derived file or of a snapshot whose metadata hash isn't the store's."""
    for w in ws:
        c, m = w["claim"], w["start"]["snapshot"].get("meta_sha12")
        if c.get("level") != level:
            raise SystemExit(f"{name}: a record of {c.get('level')}, not {level}")
        if c.get("zoning") != zoning:
            raise SystemExit(f"{name}: a record of another zoning ({str(c.get('zoning'))[:12]}) than {level}'s derived "
                             f"file ({zoning[:12]}): witness it again")
        if m != meta_sha12:
            raise SystemExit(f"{name}: a record of snapshot {m}, not the store's ({meta_sha12})")


def pick_edges(ws, level: str, files) -> tuple[dict, list]:
    """The witness of each (from, to, air) row of ``files`` (rows files, ``{"rows": [...]}``, of ``level``): its
    pair's at the least rank at or under the row's air, by ``ref`` with the rows it answers; and the rows none
    answers."""
    by_pair = collections.defaultdict(list)
    for w in ws:
        by_pair[(w["claim"]["from"], w["claim"]["to"])].append(w)
    picked, missing = {}, []
    for f in files:
        doc = json.loads(Path(f).read_text(encoding="utf-8"))
        for x in doc["rows"] if isinstance(doc, dict) else doc:
            if x.get("level", level) != level:
                continue
            e = {"src": Path(f).name, "i": x.get("i"), "air": x["air"]}
            got = [w for w in by_pair[(x["from"], x["to"])] if w["claim"]["min_air"] <= x["air"]]
            if not got:
                missing.append(e | {"from": x["from"], "to": x["to"]})
                continue
            w = min(got, key=lambda w: w["claim"]["min_air"])
            picked.setdefault(w["ref"], (w, []))[1].append(e)
    return picked, missing


def tags(row: dict) -> list[str]:
    """A row's classes: its plan, backend, stage (its job id's first letter), kit, derived kind or ``new``, swim,
    flags and negative kind."""
    from devkit.reach.reach_engine import STAGES
    out = [f"plan:{row['plan']}", f"backend:{row['backend']}", f"stage:{STAGES.get(row['id'][:1], row['id'][:1])}",
           f"kit:{row['kit']}", "new" if row["derived"] == "new" else f"derived:{row['derived']}"]
    out += ["swim"] * bool(row["swim"]) + [f"flag:{f}" for f in row["flags"] or ()]
    return out + ([f"negative:{row['negative']}"] if row.get("negative") else [])


def per_class(rows: list[dict], n: int) -> list[dict]:
    """Each class's (:func:`tags`) first ``n`` rows by :func:`order`, together, in that order."""
    keep = set()
    for t in sorted({t for r in rows for t in r["cls"]}):
        keep |= {r["ref"] for r in sorted((r for r in rows if t in r["cls"]), key=lambda r: order(r["ref"]))[:n]}
    return [r for r in rows if r["ref"] in keep]


def joined(level: str, w: dict, rec: dict, job: dict, plan: str, cands, kinds: dict, negative: str | None) -> dict:
    """Witness record ``w``'s row: its ids and class fields, from its job record ``rec``, ``job``, its ``plan``, the
    graph's candidates at its pair and rank (its flags) and the derived edges' ``kinds``."""
    su, c = setup_of(w), w["claim"]
    k = next((k for k, o in enumerate(rec["outcomes"]) if o["string_sha12"] == w["string"]["sha12"]
              and o["start"] == su["start"]), None)
    if k is None:
        raise SystemExit(f"{w['ref']}: job {rec['key']} holds no outcome of its string: another cache's witness")
    o = rec["outcomes"][k]
    cand = next((x for x in cands if x["job"] == rec["key"] and x["outcome"] == k), None)
    row = {"ref": w["ref"], "level": level, "from": c["from"], "to": c["to"], "rank": c["min_air"], "kit": o["kit"],
           "job": rec["key"], "id": rec["id"], "outcome": k, "start_id": su["start"], "wait": su["wait"],
           "place_sha12": su.get("place_sha12"), "string_sha12": w["string"]["sha12"], "ticks": w["string"]["ticks"],
           "plan": plan, "backend": job.get("backend", "l3"), "by": o.get("by", "l3"), "macro": o["macro"],
           "pass": o.get("pass"), "swim": o.get("land_state") == SWIMMING, "flags": cand["flags"] if cand else None,
           "derived": kinds.get((c["from"], c["to"]), "new"), "negative": negative}
    return row | {"cls": tags(row)}


def _private_jsonl(path: Path, recs) -> Path:
    """``recs`` as JSON lines in a new file, mode 0600 (``l3.private_out``'s rule: never over a file there)."""
    path, n = Path(path), 1
    while True:
        p = path if n == 1 else path.with_name(f"{path.stem}.{n}{path.suffix}")
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            n += 1
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in recs)
        return p


def plan(a) -> dict:
    """The rows file (the module docstring), written privately; its counts."""
    from azurkit.tools.randomizer.planner.proofs import zoning as zoning_of
    from devkit.rando.draft.author import read_derived
    from devkit.reach import reach_engine as RE
    from devkit.reach.engine import verdict as V
    from devkit.reach.engine.graph import Graph
    snap, wpath = RE._snap(a.snapshot, a.store), Path(a.witness)
    derived = read_derived(a.level)
    zoning = zoning_of(derived)
    ws = read_jsonl(wpath)
    refuse(ws, a.level, zoning, snap["meta_sha12"], wpath.name)
    base, jobs, plan_of = cache.folder(a.level), {}, {}
    for name in a.plan:
        for j in RE._plan(a.level, name, snap, a.backend)["jobs"]:
            if j["key"] not in jobs:
                jobs[j["key"]], plan_of[j["key"]] = j, name
    recs = {k: r for k in jobs if (r := cache.get(base, k)) is not None}
    if lost := sum(setup_of(w)["job"] not in recs for w in ws):
        raise SystemExit(f"{lost} of {len(ws)} witness records name a job these plans (keyed --backend {a.backend}) "
                         "or the cache don't hold: name the witness run's plans, snapshot and backend")
    g = Graph(RE._nodes(a.level), jobs, list(recs.values()))
    negative, src = None, wpath
    if a.negatives:
        negative, got = a.negatives, {}
        for pair, ranks in sorted(g.cands.items()):
            for _, cands in sorted(ranks.items()):
                for w in cands:
                    ans = hold.answer(base, recs[w["job"]], w["outcome"])
                    if ans is not None and not hold.stays(ans, pair[1], g.nodes.zone_at):
                        rec = V.witness(a.level, w, recs[w["job"]], jobs[w["job"]]["heading"], snap, zoning, pair)
                        got.setdefault(rec["ref"], rec)
        ws = list(got.values())
        src = _private_jsonl(Path(a.out).with_suffix(".negatives.jsonl"), ws)
    if a.minus:
        drop = {w["ref"] for w in read_jsonl(a.minus)}
        ws = [w for w in ws if w["ref"] not in drop]
    edges, missing = {}, []
    if a.edges:
        picked, missing = pick_edges(ws, a.level, a.edges)
        ws, edges = [w for w, _ in picked.values()], {ref: e for ref, (_, e) in picked.items()}
    kinds = {}
    for e in derived.get("edges", ()):
        kinds.setdefault((e["from"], e["to"]), f"{e['kind']}:{e.get('confidence')}")
    rows = []
    for w in ws:
        job = setup_of(w)["job"]
        r = joined(a.level, w, recs[job], jobs[job], plan_of[job],
                   g.cands.get((w["claim"]["from"], w["claim"]["to"]), {}).get(w["claim"]["min_air"], []), kinds,
                   negative)
        rows.append(r | ({"edges": edges[w["ref"]]} if w["ref"] in edges else {}))
    rows.sort(key=lambda r: order(r["ref"]))
    if a.per_class:
        rows = per_class(rows, a.per_class)
    doc = {"level": a.level, "check": CHECK, "witness": str(src.resolve()), "zoning": zoning,
           "snapshot": {k: snap[k] for k in ("label", "meta_sha12", "store")}, "plans": a.plan, "backend": a.backend,
           "records": len(ws), "missing": missing, "rows": rows}
    p = l3.private_out(a.out, doc, indent=1)
    return {"level": a.level, "rows": len(rows), "records": len(ws), "edges_missing": len(missing),
            "unflagged": sum(r["flags"] is None for r in rows),
            "by_class": dict(sorted(collections.Counter(t for r in rows for t in r["cls"]).items())), "out": p.name}


# -- run --------------------------------------------------------------------------------------------------------------

def recipe(sim, st: dict, yaw: float, kit: dict, cast: list, string: list, idle: int) -> tuple:
    """The witness record's setup and string as L3 runs them from an arrival snapshot (the module docstring's recipe
    start): its pads, rows, the settle's last row's index, the rows through the string's end and the fault site
    that stopped L3 early (None)."""
    cam = st.get("cam")

    def carry(p: Pad) -> Pad:
        return p if cam is None or p.cam is not None or p.yaw is not None else p._replace(yaw=cam)
    steps = ([(Pad(), None)] * idle + [(Pad(), "R6")] + [(Pad(), None)] * SETTLE_START + [(Pad(), "R2")]
             + [(p, None) for p in cast + string] + [(Pad(), None)] * HOLD)
    pads, rows = [carry(p) for p, _ in steps], []
    sim.reset()
    try:
        for p, (_, what) in zip(pads, steps):
            writes = (recipes.place(sim.u32, st["feet"], yaw, cell=st["cell"]) if what == "R6"
                      else sim.kit_writes(kit) if what == "R2" else ())
            rows.append(sim.step(p, writes=writes))
            if what == "R6" and sim.u32(writes[-1][0]):
                raise L3Error("the place request wasn't consumed", "place not consumed")
    except L3Error as exc:
        return pads, rows, idle + SETTLE_START, len(steps) - HOLD, l3.fault_site(exc)
    return pads, rows, idle + SETTLE_START, len(steps) - HOLD, None


def _steps(sim, pads) -> tuple[list, str | None]:
    """``pads`` run on ``sim``: its rows, and the fault site that stopped it early (None)."""
    rows = []
    try:
        for p in pads:
            rows.append(sim.step(p))
    except L3Error as exc:
        return rows, l3.fault_site(exc)
    return rows, None


def compare(rows, got) -> dict:
    """xemu's rows against L3's (``oracle.l3_compare``'s counts: no positions)."""
    if not rows or not got:
        return {"ticks": len(got), "l3_ticks": len(rows), "max_err_m": None, "first_err_tick": None,
                "states_differ": None, "hp_differ": None}
    from devkit.xemu import oracle as xo
    c = xo.l3_compare(rows, got)
    return {k: c[k] for k in ("ticks", "l3_ticks", "max_err_m", "first_err_tick", "states_differ", "hp_differ")}


def engine_keys() -> dict:
    """The engine's three key sha12s: the L3 core's, an aimed job's core's and the native kernel's."""
    from devkit.reach.native import backend
    return {"core_sha12": cache.core_sha12(),
            "core_aim_sha12": cache.core_sha12(files=cache.CORE_FILES + cache.AIM_FILES),
            "kernel_sha12": backend.kernel_sha12()}


class Game:
    """The check's hands on a sitting (``devkit.xemu.sitting.Sitting``); the table test's stand-in has the same."""

    def __init__(self, s) -> None:
        self.s = s

    def boot(self) -> dict:
        return self.s.boot(tag=SAVE_TAG, save=SAVE)

    def hop(self, level: str) -> dict:
        return self.s.hop(*ARRIVALS[level])

    def kit(self, levels: dict) -> dict:
        return self.s.kit(**levels)

    def quiet(self) -> None:
        self.s.quiet()

    def clock(self) -> float | None:
        """Run to the next player tick: the player's event clock there, None for no tick."""
        ent = self.s.tick()
        return None if ent is None else struct.unpack("<d", self.s.sb.read(ent + 0x18, 8))[0]

    def press_a(self) -> None:
        self.s.sb.press("a", seconds=0.3)

    def idle(self, n: int) -> None:
        for _ in range(n):
            if self.s.tick() is None:
                raise SystemExit("no player tick in the idle wait before the R6")

    def place(self, feet, yaw: float, cell: int) -> dict:
        return self.s.place(feet, math.degrees(yaw), cell=cell, settle=SETTLE_START)

    def checkpoint(self, name: str) -> None:
        self.s.sb.checkpoint_save(name)

    def restore(self, name: str) -> None:
        self.s.sb.checkpoint_restore(name)

    def ram_sha12(self) -> str:
        return self.s.sb.ram_sha256()[:12]

    def snapshot(self, label: str, store: Path) -> Path:
        return Path(self.s.sb.snapshot(label, store=store)["path"])

    def replay(self, pads, rows, meta) -> tuple[list, dict]:
        from devkit.reach import l3_certify
        from devkit.xemu import oracle as xo
        return l3_certify.replay_clearing(self.s.sb, xo, pads, rows, meta)

    def xbe(self) -> bytes:
        return self.s.sb._xbe("dvd.iso")

    def ids(self) -> dict:
        st = self.s.sb.st
        return {"xemu_sha12": st.get("xemu_sha12"), "disc_sha12": (st.get("disc_sha12") or {}).get("dvd.iso")}

    def corpus(self, meta: dict, pads, rows, got, store) -> None:
        from devkit.sim import corpus
        corpus.record(meta, False, pads, rows, got, store=store, disc=self.s.sb.disc_source())

    def result(self, row: dict) -> dict:
        return self.s.result(row)

    def note(self, text: str) -> None:
        self.s.notes.append(text)

    def maybe_yield(self) -> bool:
        return self.s.maybe_yield()


class Sources:
    """What the check reads offline: the cache's job records and hold answers, a level's zones, the snapshots and
    L3; the table test's stand-in has the same."""

    def __init__(self) -> None:
        self._zones: dict = {}

    def check(self, doc: dict) -> None:
        """Refuse (SystemExit) a rows file whose snapshot's metadata or level's zoning isn't today's."""
        from azurkit.tools.randomizer.planner.proofs import zoning
        from devkit.rando.draft.author import read_derived
        from devkit.reach import reach_engine as RE
        snap = RE._snap(doc["snapshot"]["label"], doc["snapshot"]["store"])
        if snap["meta_sha12"] != doc["snapshot"]["meta_sha12"]:
            raise SystemExit(f"{doc['level']}: the rows name snapshot {doc['snapshot']['meta_sha12']}, the store holds "
                             f"{snap['meta_sha12']}")
        if zoning(read_derived(doc["level"])) != doc["zoning"]:
            raise SystemExit(f"{doc['level']}: the rows were planned under another zoning: plan them again")

    def record(self, level: str, job: str) -> dict:
        if (rec := cache.get(cache.folder(level), job)) is None:
            raise SystemExit(f"{level}: the cache holds no record of job {job}")
        return rec

    def hold(self, level: str, rec: dict, k: int) -> dict | None:
        return hold.answer(cache.folder(level), rec, k)

    def zone_at(self, level: str):
        """The level's ``zone_at``: the engine's pickled zones for today's zoning, else its nodes (built, not kept)."""
        if level not in self._zones:
            import pickle
            from azurkit.tools.randomizer.planner.proofs import zoning
            from devkit.rando.draft.author import read_derived
            p = cache.folder(level) / f"zones-{zoning(read_derived(level))[:12]}.pkl"
            if p.exists():
                with p.open("rb") as f:
                    self._zones[level] = pickle.load(f).zone_at
            else:
                from devkit.reach import reach_engine as RE
                self._zones[level] = RE._nodes(level).zone_at
        return self._zones[level]

    def engine_meta(self, snap: dict) -> dict:
        return l3.read_meta(l3.snapshot_path(snap["label"], snap["store"]))

    def snapshot(self, path: Path):
        return l3.read_snapshot(path)

    def sim(self, sn, xbe: bytes):
        return l3.L3(sn, xbe)

    def held(self, folder: Path) -> bool:
        """Whether ``devkit sim l3-hold --check`` holds a snapshot at or under ``folder``."""
        from devkit.sim import l3_hold
        return l3_hold.main(["--store", str(l3.store()), "--check", str(folder)]) != 0


class Check:
    """One run's checks (``run``; the module docstring): ``game`` a :class:`Game`, ``src`` a :class:`Sources`,
    ``ev`` the evidence folder (its ``results/runs.jsonl``), ``folder`` the arrival snapshots' folder."""

    def __init__(self, game, src, *, ev, name: str, folder, start: str = "recipe", phases=PHASES, keys=None,
                 corpus=None) -> None:
        self.game, self.src, self.ev, self.name, self.folder = game, src, Path(ev), name, Path(folder)
        self.start, self.phases, self.keys, self.corpus = start, tuple(phases), keys or {}, corpus
        self.arrived: dict[str, dict] = {}
        self.snaps: list[Path] = []
        self.records: dict[Path, dict] = {}
        self.ids: dict | None = None
        self.xbe: bytes | None = None
        self.n = 0
        self.verdicts: collections.Counter = collections.Counter()

    def done(self) -> set:
        """(start, level, ref) of each row the evidence folder holds a final verdict for, ERROR aside."""
        p = self.ev / "results" / "runs.jsonl"
        return {(r["start"], r["level"], r["ref"]) for r in (read_jsonl(p) if p.exists() else ())
                if r.get("row") == "check" and r.get("final") and r.get("verdict") in DONE}

    def run(self, docs) -> collections.Counter:
        """Every row of ``docs`` (rows files) not done, a level at a time; the final verdicts' counts."""
        done, by_level = self.done(), {}
        for d in docs:
            by_level.setdefault(d["level"], []).append(d)
        for level, ds in by_level.items():
            todo = [(d, r) for d in ds for r in d["rows"] if (self.start, level, r["ref"]) not in done]
            if not todo:
                continue
            zone_at = self.src.zone_at(level)
            self.arrive(level, ds[0]["snapshot"], again=True)
            for d, r in todo:
                self.row(level, d, r, zone_at)
                if self.game.maybe_yield():           # a new sandbox: its checkpoints are gone
                    self.arrive(level, d["snapshot"])
        return self.verdicts

    def _label(self, level: str, what: str) -> str:
        self.n += 1
        return f"{self.name}-{level}-{what}-{self.n}"

    def arrive(self, level: str, snap: dict, again: bool = False) -> None:
        """The level's arrival (the module docstring), its checkpoint and its row; with ``again``, a harness error
        on the way is met with one more arrival."""
        if again:
            from devkit.xemu.sitting import Hold, Teardown
            try:
                return self.arrive(level, snap)
            except (KeyboardInterrupt, Teardown, Hold):
                raise
            except (Exception, SystemExit) as exc:
                self.game.note(f"{level}: the arrival failed once ({type(exc).__name__}: {str(exc)[:160]}); again")
        g, t0 = self.game, time.monotonic()
        boot = g.boot()
        self.xbe = self.xbe if self.xbe is not None else g.xbe()
        self.ids = self.ids or g.ids()
        hop = g.hop(level)
        kit = g.kit({})
        g.quiet()
        want, waited, presses = self.src.engine_meta(snap)["clock"], 0, 0
        while (clock := g.clock()) is None or clock < want - 1e-6:
            if clock is None:
                presses += 1
                if presses > PRESSES:
                    raise SystemExit(f"{level}: no player tick on the way to the snapshot's clock")
                g.press_a()
            else:
                waited += 1
        g.quiet()
        arr: dict = {}
        if self.start == "recipe":
            path = g.snapshot(self._label(level, "arrive"), self.folder)
            self.snaps.append(path)
            sn = self.src.snapshot(path)
            arr |= {"meta": sn.meta, "sim": self.src.sim(sn, self.xbe),
                    "snapshot_ticks_past": round((sn.meta["clock"] - want) * 30, 2)}
        g.checkpoint(f"arrive-{level}")
        arr["ctrl"] = g.ram_sha12()
        self.arrived[level] = arr
        g.result(public({"row": "arrive", "check": CHECK, "level": level, "start": self.start,
                         "boot_s": (boot or {}).get("s"), "hop_ok": hop.get("ok"), "hop_s": hop.get("s"),
                         "kit_read_back": kit, "clock": {"want": round(want, 4), "got": round(clock, 4),
                                                         "ticks_past": round((clock - want) * 30, 2),
                                                         "ticks_run": waited, "a_presses": presses},
                         "snapshot_ticks_past": arr.get("snapshot_ticks_past"), "control_state_sha12": arr["ctrl"],
                         "s": round(time.monotonic() - t0, 1)}))

    def row(self, level: str, doc: dict, r: dict, zone_at) -> None:
        """Row ``r``'s tries (the module docstring), each a results row; the final one's record kept privately."""
        rec = self.src.record(level, r["job"])
        o = rec["outcomes"][r["outcome"]]
        st = rec["starts"][o["start"]]
        base = {"row": "check", "check": CHECK, "start": self.start, "level": level, "ref": r["ref"],
                **{k: r.get(k) for k in CLASS}, "record_wait": r.get("wait"), **(self.ids or {}), **self.keys}
        for n, phase in enumerate(self.phases, 1):
            got = self.attempt(level, doc, r, rec, o, st, phase, zone_at)
            final = got["verdict"] != WORLD or n == len(self.phases)
            row = base | {"try": n, "phase": phase, "control_state_sha12": self.arrived[level]["ctrl"],
                          **got["public"], "verdict": got["verdict"]}
            if final:
                row |= {"final": True, "tries": n, "wait": phase if got["verdict"] == PASS else None}
            self.game.result(public(row))
            if final:
                self.verdicts[got["verdict"]] += 1
                self.keep(doc, r, got, n, phase)
                return

    def attempt(self, level: str, doc: dict, r: dict, rec: dict, o: dict, st: dict, phase: int, zone_at) -> dict:
        """One try (:meth:`once`); a harness error runs it again once from a fresh arrival, and a second is ERROR."""
        from devkit.xemu.sitting import Hold, Teardown
        err = None
        for k in (0, 1):
            try:
                got = self.once(level, r, rec, o, st, phase, zone_at)
                got["public"] |= {"reruns": k} | ({"error_first": err} if err else {})
                return got
            except (KeyboardInterrupt, Teardown, Hold):
                raise
            except (Exception, SystemExit) as exc:   # a harness error (a boot, a restore, a bugcheck, a timeout)
                err = f"{type(exc).__name__}: {exc}"[:300]
                trace = traceback.format_exc()[-400:]
                if k == 0:
                    self.arrive(level, doc["snapshot"])
        return {"verdict": ERROR, "public": {"error": err, "trace": trace, "reruns": 1}}

    def once(self, level: str, r: dict, rec: dict, o: dict, st: dict, phase: int, zone_at) -> dict:
        """One try from the level's checkpoint: the start, L3's run, xemu's replay of it, the judgement."""
        g, t0 = self.game, time.monotonic()
        kit, idle, yaw = KITS[o["kit"]], int(r.get("wait") or 0) + phase, st.get("yaw", rec["heading"])
        cast = [Pad(buttons=frozenset({"lt", "y"}))] + [Pad()] * CAST_WAIT if kit.get("air") else []
        string = l3.pads(o["segments"])
        g.restore(f"arrive-{level}")
        t1, placed = time.monotonic(), None
        if self.start == "recipe":
            meta = self.arrived[level]["meta"]
            pads, rows, settle, end, fault = recipe(self.arrived[level]["sim"], st, yaw, kit, cast, string, idle)
        else:
            g.idle(idle)
            p = g.place(st["feet"], yaw, st["cell"])
            placed = {"stood": p.get("settled"), "off_m": p.get("off_m")}
            g.kit(kit)
            path = g.snapshot(self._label(level, "placed"), self.folder)
            try:
                sn = self.src.snapshot(path)
                meta, pads = sn.meta, [Pad()] + cast + string + [Pad()] * HOLD
                rows, fault = _steps(self.src.sim(sn, self.xbe), pads)
                settle, end = None, 1 + len(cast) + len(string)
            finally:
                path.unlink(missing_ok=True)
        t2 = time.monotonic()
        got, stops = g.replay(pads[:len(rows)], rows, meta) if rows else ([], {})
        if stops.get("at") == "lost":
            raise SystemExit(f"the replay lost a tick clearing a popup (at tick {stops.get('k')})")
        t3 = time.monotonic()
        if self.corpus and rows:
            g.corpus(meta, pads[:len(rows)], rows, got, self.corpus)
        frm = r["from"] if zone_at(tuple(st["settled"]), False, False) == r["from"] else None
        at = meta if settle is None else got[settle] if len(got) > settle else None
        start = stands(at, st["feet"], zone_at, frm)
        ans = self.src.hold(level, rec, r["outcome"])
        held_land = ans.get("land") if ans else None
        x = judge(got, end, r["to"], zone_at, o.get("land"), held_land)
        lj = judge(rows, end, r["to"], zone_at, o.get("land"), held_land)
        hit = any(a["state"] == HIT and b.state != HIT for a, b in zip(got, rows))
        v = verdict(start, x, lj, stops.get("at"), hit)
        cmp = compare(rows, got)
        hp0 = _fields(at)[2] if at is not None else None
        out = {"string_ticks": len(string), "idle": idle, "stop": stops.get("at"), "popups": stops.get("popups", 0),
               **start, "hp_lost": None if hp0 is None or x["hp_min"] is None
               else hp0 - x["hp_min"], "hit": hit, "l3_fault": fault, "placed": placed,
               "record_held": bool(ans and hold.stays(ans, r["to"], zone_at)), "xemu": x, "l3": lj,
               "xemu_vs_l3": cmp, "s": {"restore": round(t1 - t0, 2), "l3": round(t2 - t1, 2),
                                         "xemu": round(t3 - t2, 2), "row": round(time.monotonic() - t0, 2)}}
        equal = bool(cmp["max_err_m"] == 0 and cmp["ticks"] == cmp["l3_ticks"] and not cmp["states_differ"]
                     and not cmp["hp_differ"])
        return {"verdict": v, "public": out, "replay": {"equal": equal, "max_err_m": cmp["max_err_m"],
                                                         "ticks": len(got)}}

    def keep(self, doc: dict, r: dict, got: dict, tries: int, phase: int) -> None:
        """The row's witness record, its ``replay`` filled, appended privately beside its witness file."""
        src = Path(doc["witness"])
        if src not in self.records:
            self.records[src] = {w["ref"]: w for w in read_jsonl(src)} if src.exists() else {}
        if (w := self.records[src].get(r["ref"])) is None:
            return
        rep = {**got.get("replay", {}), "sitting": self.name, "check": CHECK, "start": self.start,
               "verdict": got["verdict"], "tries": tries, "wait": phase if got["verdict"] == PASS else None}
        fd = os.open(src.with_name(f"{src.stem}.checked.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps({**w, "replay": rep}, sort_keys=True, separators=(",", ":")) + "\n")

    def finish(self) -> None:
        """The arrival snapshots: kept with a corpus (its rows re-run from them), else deleted, each by its path,
        once ``l3-hold`` holds none of them."""
        if not self.snaps:
            return
        if self.corpus:
            self.game.note(f"kept {len(self.snaps)} arrival snapshot(s) in {self.folder.name}/ for the corpus's rows")
        elif self.src.held(self.folder):
            self.game.note(f"l3-hold holds a snapshot in {self.folder.name}/: none deleted")
        else:
            for p in self.snaps:
                p.unlink(missing_ok=True)
            with contextlib.suppress(OSError):
                self.folder.rmdir()


def run(a) -> dict:
    """The rows files' checks in one sitting (the module docstring); the final verdicts' counts."""
    from devkit.xemu import sitting as xs
    docs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in a.rows]
    src = Sources()
    for d in docs:
        if d.get("check") != CHECK:
            raise SystemExit(f"{d.get('level')}: rows of check {d.get('check')}, not {CHECK}")
        src.check(d)
    keys, folder = engine_keys(), l3.store() / FOLDER / xs.slug(a.name)
    with xs.Sitting(a.name, ev=a.ev) as s:
        chk = Check(Game(s), src, ev=a.ev, name=xs.slug(a.name), folder=folder, start=a.start, phases=a.phases,
                    keys=keys, corpus=a.corpus)
        try:
            got = chk.run(docs)
        finally:
            chk.finish()
    return {"start": a.start, "verdicts": dict(sorted(got.items()))}


# -- tally ------------------------------------------------------------------------------------------------------------

def finals(path: Path) -> list[dict]:
    """The last final row of each (start, level, ref) in a results file."""
    last = {}
    for r in read_jsonl(path):
        if r.get("row") == "check" and r.get("final"):
            last[(r["start"], r["level"], r["ref"])] = r
    return list(last.values())


def rate(rows) -> dict:
    """Verdict counts and the PASS share with its Wilson interval, ERROR outside it (never against the link)."""
    v = collections.Counter(r["verdict"] for r in rows)
    n = len(rows) - v[ERROR]
    return {"n": len(rows), "verdicts": dict(sorted(v.items())), "pass": v[PASS],
            "pass_share": round(v[PASS] / n, 4) if n else None, "wilson95": wilson(v[PASS], n)}


def truths(files) -> dict:
    """Kept verdicts: a check's own final rows by ``ref``; R2.16e's sitting rows (``row: witness``, its ``xemu``
    judgement) by level, from, to and air as PASS or FAIL, the clock arrival's over the fresh one's."""
    out: dict = {}
    for f in files:
        for r in read_jsonl(f):
            if r.get("row") == "check" and r.get("final"):
                out[("ref", r["ref"])] = (r["verdict"], "check")
            elif r.get("row") == "witness" and "error" not in r and isinstance(r.get("xemu"), dict):
                key, arr = ("edge", r["level"], r["from"], r["to"], r["air"]), r.get("arrival", "fresh")
                if arr == "clock" or out.get(key, (None, None))[1] != "clock":
                    out[key] = (PASS if r["xemu"].get("match") else "FAIL", arr)
    return out


def against(rows, files) -> dict:
    """The rows whose verdict moved from the kept one (an R2.16e label: PASS or not), ERROR rows aside."""
    t, joined, agree, moved = truths(files), 0, 0, []
    for r in rows:
        if r["verdict"] == ERROR:
            continue
        if ("ref", r["ref"]) in t:
            labels = [t[("ref", r["ref"])][0]]
            same = labels[0] == r["verdict"]
        else:
            labels = [t[k][0] for e in r.get("edges") or () if (k := ("edge", r["level"], r["from"], r["to"],
                                                                         e["air"])) in t]
            if not labels:
                continue
            same = all((x == PASS) == (r["verdict"] == PASS) for x in labels)
        joined, agree = joined + 1, agree + same
        if not same:
            moved.append({k: r.get(k) for k in ("start", "level", "from", "to", "rank", "ref", "verdict")}
                         | {"kept": labels})
    return {"joined": joined, "agree": agree, "moved": moved}


def tally(a) -> dict:
    """The final verdicts by start, level and class, the seconds a row and the rows a sandbox-hour; with ``--truth``
    the rows that moved."""
    path = Path(a.dir) / "results" / "runs.jsonl"
    rows, allr = finals(path), read_jsonl(path)
    out: dict = {"rows": len(rows), "by_start": {}}
    for start in sorted({r["start"] for r in rows}):
        rs = [r for r in rows if r["start"] == start]
        secs = collections.Counter()
        for r in allr:
            if r.get("row") == "check" and r.get("start") == start:
                secs[(r["level"], r["ref"])] += (r.get("s") or {}).get("row", 0.0)
        arrive_s = sum(r.get("s", 0.0) for r in allr if r.get("row") == "arrive" and r.get("start") == start)
        per = sorted(secs.values())
        out["by_start"][start] = {
            **rate(rs), "by_level": {lv: rate([r for r in rs if r["level"] == lv])
                                     for lv in sorted({r["level"] for r in rs})},
            "by_class": {c: rate([r for r in rs if c in (r.get("cls") or ())])
                         for c in sorted({c for r in rs for c in r.get("cls") or ()})},
            "passed_at_a_later_phase": sum(r["verdict"] == PASS and r["tries"] > 1 for r in rs),
            "rerun_after_an_error": sum(bool(r.get("reruns")) for r in rs),
            "row_s_median": per[len(per) // 2] if per else None, "arrival_s": round(arrive_s, 1),
            "rows_a_sandbox_hour": round(3600 * len(per) / spent, 1) if (spent := sum(per) + arrive_s) else None}
    if a.truth:
        out["truth"] = against(rows, a.truth)
    return out


def _phases(text: str) -> tuple[int, ...]:
    got = tuple(int(x) for x in text.split(","))
    if not got or any(x < 0 for x in got):
        raise argparse.ArgumentTypeError("phases: idle ticks, comma separated, none negative (0,15,30)")
    return got


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m devkit reach witness-check", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="the rows to check, ids only (private: --out)")
    p.add_argument("level")
    p.add_argument("--witness", required=True, help="the level's witness file (reach-engine witness --out)")
    p.add_argument("--plan", nargs="+", required=True, help="the plans the witness run read")
    p.add_argument("--snapshot", required=True, help="the engine snapshot's label")
    p.add_argument("--store", help="the snapshot's folder (default: the L3 store's reach-live)")
    p.add_argument("--backend", choices=("l3", "kernel"), default="l3", help="the witness run's (it keys the jobs)")
    p.add_argument("--edges", nargs="+", metavar="ROWS.json", help="the witness of each (from, to, air) row")
    p.add_argument("--minus", metavar="FILE", help="keep what this witness file lacks")
    p.add_argument("--negatives", choices=("hold",), help="the candidates whose hold answer leaves")
    p.add_argument("--per-class", type=int, metavar="N", help="each class's first N by sha256 of ref")
    p.add_argument("--out", required=True)
    r = sub.add_parser("run", help="the rows checked in one sitting, results in --ev")
    r.add_argument("name", help="the sitting's name (its sandbox group)")
    r.add_argument("--rows", nargs="+", required=True, help="plan's rows files")
    r.add_argument("--ev", required=True, help="the evidence folder (results/runs.jsonl, REPORT.txt)")
    r.add_argument("--start", choices=("recipe", "placed"), default="recipe")
    r.add_argument("--phases", type=_phases, default=PHASES, help="idle ticks before the R6 a try waits (0,15,30)")
    r.add_argument("--corpus", metavar="STORE", help="append each try's replay to this conformance corpus")
    t = sub.add_parser("tally", help="verdicts by class with Wilson intervals; --truth: the rows that moved")
    t.add_argument("dir", help="a run's evidence folder")
    t.add_argument("--truth", nargs="+", metavar="KEPT.jsonl")
    a = ap.parse_args(argv)
    out = {"plan": plan, "run": run, "tally": tally}[a.cmd](a)
    print(json.dumps(out, indent=1 if a.cmd == "tally" else None, sort_keys=True))
    return 0
