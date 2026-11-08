"""The rigs' triggers (Step R2.19h2, ``devkit.reach.engine.triggers``): what starts each moving solid, read from
each level's wiring, and its witness in the game's own code.

``census`` reads every level's rigs (every solid platform owner a link moves) and the derive's exported ones (its
``rigs``: the decks whose movers lift them, MOVES.txt's 166; each entry's owner by its movers,
``Triggers.exported``) and prints and writes their starts by kind (load, wired, never, undecoded), the undecoded
leaves and the pokes' kind: names and counts only.

``witness`` is the rigs-only re-run (D847) on simulator Level 3: from the level's start snapshot (``--snapshot``,
by default its ``reach-live`` one), ``--ticks`` whole steps untouched (the baseline: every deck's pose each tick),
then, for each wired or undecoded rig, the same steps with its pokes held (``Runtime.hold``: written at each
graph pass's entry): a pad's pulse at 0 for 3 ticks (a player who stands in it at the snapshot steps out: a switch
acts on a change), then every poke for ``--hold`` ticks; its start's terms are tried in turn, at most 3 (an
elevator called to the floor it stands at doesn't move), with the movers' own inputs last; a rig is **witnessed** when its deck, where the game
collides with it (``Runtime.deck``), leaves the baseline on the poked run (a corner of its box 5 cm off at the same
tick), and the run goes on until it has stood still for 30 ticks or ``--ticks`` (``moved_m``, the farthest a
corner went from the baseline, and ``rest_tick``); a load rig is witnessed when it moves on the baseline, and a
wired or undecoded one that already moves there is not (``moves untouched``: no poke can show it).  ``--rigs
exported`` (the default) or ``all``.  Each rig's row: its start, its pokes' kind (``condition``: the start's own
atoms; ``source``: the mover's input), witnessed, the tick, L3 steps and CPU, and each try's term, stop and tick
(``tries``); a fault or a level exit ends that try and is its ``stop``.  Every step runs under a cap of
``CAP_US``, not L3's own: those are wall-clock (a render's 5 s), and a step that loads from the stream after a poke
(e6's mirrors: 330 contiguous allocations, each a Unicorn region that maps slower the more a process has mapped)
passed one under load or late in a worker and not otherwise, so a try's verdict changed from run to run.
Positions stay in memory: the rows hold names, ticks and counts.  A CPU-heavy batch job: run it under ``nice`` with
``-j`` workers the machine can spare (one level a worker).

    uv run --locked python -m devkit reach rig-triggers census [LEVEL ...] [--out FILE.json]
    nice -n 10 uv run --locked python -m devkit reach rig-triggers witness LEVEL ... [--snapshot LABEL] [--ticks 600]
        [--hold 6] [--rigs exported|all] [-j N] --out FILE.json
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

LEVELS = "a1 a3 a5 a6 airship d1 d2 e2 e5 e6 e7 f1 f2 f3 f4 f6 life town w1 w2 w3 w4".split()
EPS = 0.05          # [proposal] a deck witnessed: a box corner 5 cm off the baseline at the same tick
REST = 30           # [proposal] then at rest: no corner moved 2 cm a tick for this many ticks
RELEASE = 3         # [proposal] a pad's pulse is first held at 0 this many ticks (a player standing in it at the
                    # snapshot steps out), then at 1 for --hold ticks (steps back in): a switch sees the change
PULSES = ("touch", "actionButton", "whack", "joystickOn", "magic", "teleported")
TRIES = 3           # [proposal] a start's first terms tried in turn (then its source pokes) until one moves the deck
CAP_US = 120_000_000   # [proposal] a step's wall-clock cap: past any load's slowdown of a finite step (the heaviest
                       # seen, a stream load of 330 allocations, took 2.4 s of wall at load 40), a runaway still stops


def _load(name: str):
    from devkit.sim.ports import resolve_vanilla_iso
    from devkit.rando.draft.export import derive_inputs
    from azurkit.tools.randomizer.draft.geometry import Level
    from azurkit.tools.randomizer.draft.wiring import Wiring
    from azurkit.tools.randomizer.planner.loader import load_database
    from devkit.reach.engine.triggers import Triggers

    db = load_database()
    lv = Level.read(resolve_vanilla_iso(), name)
    ins = derive_inputs(name, db.tricks, db.levels.get(name, {}), db.generated)
    return lv, Triggers(lv, Wiring(lv, db.generated.get(name, {}), ins["level"]))


def exported(name: str, T) -> list[int]:
    """The rig owners of the derive's exported ``rigs`` (``Triggers.exported``: each entry's by its movers)."""
    from devkit.rando.draft.author import read_derived

    return T.exported(read_derived(name).get("rigs", []))


def _kind(st) -> str:
    return st.kind + (" (partial)" if st.kind == "wired" and st.leaves else "")


def census(levels: list[str]) -> dict:
    out = {"levels": {}, "exported": collections.Counter(), "every": collections.Counter(),
           "leaves_undecoded": collections.Counter(), "undecoded_exported": []}
    for name in levels:
        lv, T = _load(name)
        ex = set(exported(name, T))
        c = collections.Counter()
        for oi in T.rigs():
            st = T.rig(oi)
            k = _kind(st)
            out["every"][k] += 1
            c[k] += 1
            if st.kind == "undecoded":
                out["leaves_undecoded"].update(st.leaves)
            if oi in ex:
                pk = "+".join(sorted({p.of for p in T.pokes(oi)})) or "none"
                out["exported"][f"{k} / pokes {pk}"] += 1
                if st.kind == "undecoded":
                    out["undecoded_exported"].append(f"{name} {lv.owners[oi]['name']}: {sorted(st.leaves)}")
        out["levels"][name] = dict(c, exported=len(ex))
    return {k: dict(v) if isinstance(v, collections.Counter) else v for k, v in out.items()}


def _snapshot(name: str, label: str | None):
    from devkit.sim import l3
    folder = l3.store() / "reach-live"
    if label is None:
        hits = sorted(folder.glob(f"*-{name}-k0-*{l3.SUFFIX}"))
        if len(hits) != 1:
            raise SystemExit(f"{name}: {len(hits)} reach-live snapshots; name one with --snapshot")
        label = hits[0].name[: -len(l3.SUFFIX)]
    return label, l3.read_snapshot(l3.snapshot_path(label, folder))


def witness(name: str, label: str | None, ticks: int, hold: int, which: str) -> dict:
    """One level's rigs-only re-run (the module docstring)."""
    import struct

    import numpy as np

    from devkit.sim.ports import resolve_vanilla_iso
    from devkit.sim.ports import XisoReader
    from devkit.reach.engine.triggers import Runtime
    from devkit.sim import l3

    t_all = time.process_time()
    lv, T = _load(name)
    with XisoReader(resolve_vanilla_iso()) as rd:
        xbe = bytes(rd.read_file("default.xbe"))
    label, snap = _snapshot(name, label)
    sim = l3.L3(snap, xbe, scene=True, deep=False)
    rt = Runtime(sim, lv)
    rigs = exported(name, T) if which == "exported" else T.rigs()
    rows, decks = [], {}
    for oi in rigs:
        o = lv.owners[oi]
        if o["G"] in rt.graph and (obj := rt.deck(o["G"], o["R"])) is not None:
            W = np.array(o["world"], dtype=np.float64)       # its load-time world matrix (column vectors)
            P = lv.P[lv.tris_of(oi)].reshape(-1, 3)
            loc = (np.linalg.inv(W) @ np.c_[P, np.ones(len(P))].T)[:3].T
            lo, hi = loc.min(0), loc.max(0)
            decks[oi] = (obj, np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1])
                                        for z in (lo[2], hi[2])] + [loc.mean(0)]))
    keys = list(decks)

    def read():
        """Each deck's box corners and centroid where the game poses it now (in memory only)."""
        out = []
        for oi in keys:
            obj, c = decks[oi]
            M = np.array(rt.pose(obj), dtype=np.float64).reshape(4, 4)
            out.append(c @ M[:3, :3] + M[3, :3])
        return np.array(out)

    def run(pokes, stop_on=None, base=None):
        """Steps from the snapshot with ``pokes`` held ``hold`` ticks; (poses per tick, the tick deck ``stop_on``
        left ``base``, steps, why it stopped).  After that tick the run goes on until the deck has stood still
        (no corner 2 cm a tick) for REST ticks, so the rows carry how far the trigger moved it."""
        sim.reset()
        free = [q._replace(value=0.0) for q in pokes if q.plug in PULSES]
        rt.hold(free)
        vals, at, why, still = [read()], None, "ticks", 0
        try:
            for k in range(ticks):
                if k == RELEASE:
                    rt.hold(pokes)
                if k == RELEASE + hold:
                    rt.hold([])
                sim.step(l3.Pad(), timeout_us=CAP_US)
                v = read()
                vals.append(v)
                if stop_on is None:
                    continue
                if at is None:
                    if np.linalg.norm(v[stop_on] - base[k + 1][stop_on], axis=-1).max() > EPS:
                        at, why = k + 1, "witnessed"
                    continue
                still = still + 1 if np.linalg.norm(v[stop_on] - vals[-2][stop_on], axis=-1).max() < 0.02 else 0
                if still >= REST:
                    why = "witnessed, at rest"
                    break
        except l3.LevelExit:
            why = "level exit"
        except l3.L3Error as e:
            why = f"fault: {l3.fault_site(e)}"
        rt.hold([])
        return np.array(vals), at, len(vals) - 1, why

    t0 = time.process_time()
    base, _, nb, why_b = run([])
    base_cpu = time.process_time() - t0
    dev_b = np.linalg.norm(base - base[0], axis=-1).max(-1) if len(keys) else np.zeros((len(base), 0))
    for oi in rigs:
        o = lv.owners[oi]
        st = T.rig(oi)
        row = {"rig": o["name"], "start": _kind(st), "leaves": sorted(st.leaves), "pokes": "none",
               "witnessed": None, "tick": None, "steps": 0, "cpu_s": 0.0, "stop": None}
        if oi not in decks:
            row["stop"] = "no collision object"
            rows.append(row)
            continue
        j = keys.index(oi)
        mv = bool(dev_b[:, j].max() > EPS)
        row["moved_on_baseline_m"] = round(float(dev_b[:, j].max()), 2)
        if st.kind in ("load", "never"):
            row["witnessed"] = mv if st.kind == "load" else None
            if mv:
                row["tick"] = int(np.argmax(dev_b[:, j] > EPS))
        elif mv:
            row.update(witnessed=False, stop="moves untouched", tick=int(np.argmax(dev_b[:, j] > EPS)))
        else:
            tries = T.tries(oi)[:TRIES]
            if tries and len(base) == ticks + 1:
                t1, steps, row["tries"] = time.process_time(), 0, []
                for k_, pokes in enumerate(tries):
                    vals, at, n, why = run(pokes, j, base)
                    steps += n
                    term = sorted(f"{p.plug}:{lv.graphs[p.G].names[p.R]}" for p in pokes)
                    of = "+".join(sorted({p.of for p in pokes}))
                    row["tries"].append({"pokes": of, "term": term, "stop": why, "tick": at, "steps": n})
                    row.update(pokes=of, tried=k_ + 1, witnessed=at is not None, tick=at, stop=why,
                               moved_m=round(float(np.linalg.norm(vals[:, j] - base[:len(vals), j], axis=-1).max()), 2),
                               rest_tick=n - REST if why == "witnessed, at rest" else None, term=term)
                    if at is not None:
                        break
                row.update(steps=steps, cpu_s=round(time.process_time() - t1, 2))
            elif tries:
                row["stop"] = f"baseline stopped: {why_b}"
        rows.append(row)
    return {"level": name, "snapshot": label, "ticks": ticks, "hold": hold, "rigs": which,
            "graphs_found": sorted(rt.graph), "baseline": {"steps": nb, "cpu_s": round(base_cpu, 2), "stop": why_b},
            "rows": rows, "cpu_s": round(time.process_time() - t_all, 2),
            "steps": nb + sum(r["steps"] for r in rows)}


def _witness_job(args):
    return witness(*args)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("census")
    c.add_argument("levels", nargs="*")
    c.add_argument("--out")
    w = sub.add_parser("witness")
    w.add_argument("levels", nargs="+")
    w.add_argument("--snapshot")
    w.add_argument("--ticks", type=int, default=600)
    w.add_argument("--hold", type=int, default=6)
    w.add_argument("--rigs", choices=("exported", "all"), default="exported")
    w.add_argument("-j", type=int, default=1)
    w.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "census":
        res = census(a.levels or LEVELS)
        print(json.dumps({k: res[k] for k in ("exported", "every", "leaves_undecoded", "undecoded_exported")},
                         indent=1, sort_keys=True))
    else:
        if a.snapshot and len(a.levels) > 1:
            raise SystemExit("--snapshot names one level's snapshot")
        jobs = [(n, a.snapshot, a.ticks, a.hold, a.rigs) for n in a.levels]
        if a.j > 1:
            import multiprocessing
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(min(a.j, len(jobs)), mp_context=multiprocessing.get_context("spawn")) as pool:
                res = {r["level"]: r for r in pool.map(_witness_job, jobs)}
        else:
            res = {j[0]: witness(*j) for j in jobs}
        for n, r in res.items():
            c = collections.Counter((x["start"].split(" ")[0], x["witnessed"], x["pokes"] if x["witnessed"] and x["pokes"] != "none" else "")
                                    for x in r["rows"])
            print(f"{n}: {len(r['rows'])} rigs, {r['steps']} steps, {r['cpu_s']} CPU-s; "
                  + ", ".join(f"{k} {'witnessed' if v else 'not' if v is False else '-'}{' by ' + p if p else ''} {m}"
                              for (k, v, p), m in sorted(c.items(), key=str)))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
