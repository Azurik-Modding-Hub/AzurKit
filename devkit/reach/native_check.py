"""Step R2.17's native-kernel prototype: the kernel (``devkit.reach.native``) against L3, tick by tick, on the
launches ``devkit/reach/native_trace.py`` traced, and its speed.

Three checks per level:
  moves     every player move L3 made (the game's request: position, velocity after gravity, w, dt), run by the
            kernel's move from the same request: where it ends (|out - L3's|), its velocity, whether it touched,
            and its first contact's t, normal and depth;
  launches  each launch run free from the row after the kit (position, velocity, state, stored normal, flaps,
            peak_z, gauge) over the witness's pads: the first tick its body is 1 cm, 10 cm and 50 cm off L3's,
            the first tick its state differs, the takeoff and the first touch-down (tick and place), the end, and
            the first law the kernel reached that it doesn't port (``kernel.c``'s TRY_ flags, its stops);
  speed     the launches' ticks run REPEAT times: ticks a CPU-second, and the moves' sweeps a CPU-second.
Prints one JSON line of counts, ticks, ratios and relative metres (no position); with OUT also a JSON of each
launch's numbers (the same kinds), mode 0600.
    nice -n 10 uv run --locked python -B -m devkit reach native-check TRACE.pkl [--out OUT.json] [--repeat 20]
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np

from devkit.reach import native as N
from devkit.sim.ports import vanilla_iso
from azurkit.tools.randomizer.draft.geometry import Level
from devkit.sim import l3

AIR = {2, 0x102}
GROUND = {0, 3, 4, 6}
END_M = 0.5                     # [proposal] an end this near L3's is the same find (a zone is metres wide)


def dist(a, b) -> float:
    return math.dist(a, b)


def check_moves(world, trace) -> dict:
    out = collections.Counter()
    errs, verrs = [], []
    first = collections.Counter()
    for L in trace["launches"]:
        for t in L["ticks"]:
            for kind, m in t.get("tap", ()):
                if kind != "move" or "out" not in m:
                    continue
                got = world.move(m["pos"], m["vel"], m["w"], m["dt"], m["f35"])
                e = dist(tuple(got.out), m["out"])
                errs.append(e)
                verrs.append(dist(tuple(got.vout), m["vout"]))
                out["moves"] += 1
                out["contact_agree"] += int(bool(got.contact) == bool(m["contact"]))
                hits = [s for s in m["sweeps"] if s["hit"]]
                if hits and got.contact:
                    s = hits[0]
                    first["both"] += 1
                    first["t_1e-3"] += int(abs(got.first.t - s["t"]) < 1e-3)
                    first["n_1e-3"] += int(dist(tuple(got.first.n), s["n"]) < 1e-3)
                    first["d_1e-4"] += int(abs(got.first.d - s["d"]) < 1e-4)
                elif hits:
                    first["l3_only"] += 1
                elif got.contact:
                    first["native_only"] += 1
                if len(hits) != got.contacts:
                    out["contact_count_differs"] += 1
    e = np.array(errs)
    v = np.array(verrs)
    return {"moves": out["moves"], "contact_agree": out["contact_agree"],
            "contact_count_differs": out["contact_count_differs"], "first_contact": dict(first),
            "out_err_m": {f"p{q}": round(float(np.percentile(e, q)), 6) for q in (50, 90, 99, 99.9)} if len(e) else {},
            "out_within": {k: int((e < k).sum()) for k in (1e-4, 1e-3, 1e-2)},
            "vout_err": {f"p{q}": round(float(np.percentile(v, q)), 5) for q in (50, 90, 99)} if len(v) else {}}


def start_player(L) -> N.Player:
    s = L["start"]
    flaps = 5 if L["kit"] == "air3" else 0
    return N.player(s["pos"], s["vel"], s["state"], s["normal"], flaps_max=flaps, flaps_used=s["flaps_used"] or 0,
                    peak_z=s["peak_z"] if s["peak_z"] is not None else -3.4e38,
                    gauge=s["gauge"] if s["gauge"] is not None else 1.0)


def pads_of(L):
    out = []
    for t in L["ticks"]:
        if "pad" not in t:
            break
        stick, buttons, cam = t["pad"]
        out.append(l3.Pad(tuple(stick), frozenset(buttons), None, tuple(cam) if cam else None))
    return out


def first(seq, pred):
    return next((k for k, x in enumerate(seq) if pred(x)), None)


def check_launch(world, L, static_obj=None, zone_at=None) -> dict:
    """One launch run free: per tick errors, the first divergences, and its outcome class against L3's end:
    AGREE (the kernel's end, where it ran out or stopped, within END_M of L3's), FLAGGED (not, but the kernel
    stopped or reached a law it doesn't port at or before its first 10 cm divergence: it knows to ask L3), SILENT
    (not, and no flag first) and the first divergence's cause."""
    pads = pads_of(L)
    rows = [t["obs"] for t in L["ticks"][:len(pads)]]
    p = start_player(L)
    got = world.run(p, pads)
    n = len(got)
    err = [dist(tuple(got[k, :3]), rows[k]["pos"]) for k in range(n)]
    st_l3 = [r["state"] for r in rows]
    st_n = [int(got[k, 6]) for k in range(n)]
    code = [int(got[k, 9]) for k in range(n)]
    took_l3 = first(st_l3, lambda s: s in AIR)
    took_n = first(st_n, lambda s: s in AIR)
    down = lambda sts, k0: None if k0 is None else next((k for k in range(k0, len(sts)) if sts[k] in GROUND), None)  # noqa: E731
    td_l3, td_n = down(st_l3, took_l3), down(st_n, took_n)
    stop = N.STOP.get(code[-1] % 16, "?") if n and code[-1] % 16 else ""
    r = {"stage": L["stage"], "macro": L["macro"], "end": L["end"], "ticks": len(pads), "ran": n, "stop": stop,
         "l3_states": sorted(set(st_l3)),
         "first_1cm": first(err, lambda e: e > 0.01), "first_10cm": first(err, lambda e: e > 0.10),
         "first_50cm": first(err, lambda e: e > 0.50), "first_state": first(range(n), lambda k: st_l3[k] != st_n[k]),
         "took": [took_l3, took_n], "touch": [td_l3, td_n], "max_err_air": None, "touch_err": None,
         "end_err": round(dist(tuple(got[-1, :3]), rows[-1]["pos"]), 4) if n else None}
    if took_l3 is not None and td_l3 is not None and td_l3 < n:
        r["max_err_air"] = round(max(err[took_l3:td_l3 + 1]), 4)
    if td_l3 is not None and td_n is not None and td_l3 < n and td_n < n:
        r["touch_err"] = round(dist(tuple(got[td_n, :3]), rows[td_l3]["pos"]), 4)
    k = r["first_10cm"]
    kd = k if k is not None else (n - 1 if stop else None)    # where the kernel first parts from L3
    flags = sorted({N.TRIES[b] for c in code[:(kd if kd is not None else n) + 1] for b in N.TRIES if (c >> 4) & b})
    r["flags"] = flags
    r["flag_any"] = sorted({N.TRIES[b] for c in code for b in N.TRIES if (c >> 4) & b} | ({stop} if stop else set()))
    r["l3_ticks"] = len(pads)
    agree = r["end_err"] is not None and r["end_err"] <= END_M
    r["prod"] = ("TO-L3" if r["flag_any"] else "NATIVE-AGREE" if agree else "NATIVE-WRONG")
    if zone_at is not None and n:
        za = zone_at((rows[-1]["pos"][0], rows[-1]["pos"][1], rows[-1]["pos"][2] - 1.0))
        zb = zone_at((float(got[-1, 0]), float(got[-1, 1]), float(got[-1, 2]) - 1.0))
        r["zone_l3"], r["zone_same"] = za, za is not None and za == zb
        r["prod_zone"] = ("TO-L3" if r["flag_any"] else "NATIVE-SAME-ZONE" if r["zone_same"] else "NATIVE-OTHER-ZONE")
    if agree:
        r["class"] = "AGREE"
    elif stop or (kd is not None and any((c >> 4) & sum(N.TRIES) for c in code[:kd + 1])):
        r["class"] = "FLAGGED"
    else:
        r["class"] = "SILENT"
    if kd is not None and not agree:
        tap = L["ticks"][kd].get("tap", ())
        objs = {s.get("obj") for kind, m in tap if kind == "move" for s in m["sweeps"] if s.get("hit")}
        lst = st_l3[kd]
        if stop:
            cause = f"kernel stop: {stop} (state {st_n[-1]:#x})" if stop == "state" else f"kernel stop: {stop}"
        elif lst not in (0, 2) or (kd and st_l3[kd - 1] not in (0, 2)):
            cause = f"L3 state {lst:#x}"
        elif flags:
            cause = "unported law: " + "+".join(flags)
        elif static_obj is not None and objs - {static_obj}:
            cause = "L3 met a non-static object"
        else:
            cause = "other"
        r["cause"] = cause
    return r


def speed(world, trace, repeat: int) -> dict:
    jobs = [(start_player(L), [N.to_pad(p) for p in pads_of(L)]) for L in trace["launches"]]
    import ctypes
    arrs = [((N.Pad * len(pads))(*pads), len(pads)) for _, pads in jobs]
    out = np.zeros((max(n for _, n in arrs), 10))
    ticks = 0
    t0 = time.process_time()
    for _ in range(repeat):
        for (p0, _), (arr, n) in zip(jobs, arrs):
            p = N.Player.from_buffer_copy(p0)
            ticks += world.lib.p_run(world.ptr, ctypes.byref(p), n, ctypes.addressof(arr), out.ctypes.data)
    cpu = time.process_time() - t0
    return {"ticks": ticks, "cpu_s": round(cpu, 3), "ticks_per_cpu_s": round(ticks / cpu) if cpu else None}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--out")
    ap.add_argument("--repeat", type=int, default=20)
    ap.add_argument("--census", help="native_census.py's JSON: the platforms to leave out")
    ap.add_argument("--zones", action="store_true", help="map each end to its zone (the reach model: slow to load)")
    a = ap.parse_args(argv)
    trace = pickle.load(open(a.trace, "rb"))
    t0 = time.process_time()
    level = Level.read(vanilla_iso(), trace["level"])
    absent = json.load(open(a.census, encoding="utf-8"))["absent"] if a.census else ()
    P, words = N.solid(level, absent)
    world = N.World(P, words, spring=N.springs(level, absent))
    vols = N.Fields(N.fields(level))
    world.fields(vols)
    setup = time.process_time() - t0
    moves = check_moves(world, trace)
    objs = collections.Counter(s["obj"] for L in trace["launches"] for t in L["ticks"] for kind, m in t.get("tap", ())
                               if kind == "move" for s in m["sweeps"] if s.get("hit"))
    static_obj = objs.most_common(1)[0][0] if objs else None
    zone_at = None
    if a.zones:
        from devkit.reach import reach_engine as RE
        zone_at = RE._nodes(trace["level"]).zone_at
    launches = [check_launch(world, L, static_obj, zone_at) for L in trace["launches"]]
    sp = speed(world, trace, a.repeat)
    summ, causes = collections.Counter(), collections.Counter()
    for r in launches:
        summ["launches"] += 1
        summ["ran_all"] += int(r["ran"] == r["ticks"])
        for key in ("first_1cm", "first_10cm", "first_50cm", "first_state"):
            summ[f"no_{key}"] += int(r[key] is None and r["ran"] == r["ticks"])
        if r["max_err_air"] is not None:
            summ["air_graded"] += 1
            summ["air_within_1cm"] += int(r["max_err_air"] <= 0.01)
            summ["air_within_10cm"] += int(r["max_err_air"] <= 0.10)
        if r["touch_err"] is not None:
            summ["touch_graded"] += 1
            summ["touch_same_tick"] += int(r["touch"][0] == r["touch"][1])
            summ["touch_within_25cm"] += int(r["touch_err"] <= 0.25)
        summ["class_" + r["class"]] += 1
        summ["prod_" + r["prod"]] += 1
        summ["prod_ticks_" + r["prod"]] += r["l3_ticks"]
        summ["ticks"] += r["l3_ticks"]
        if r["end"] == "settled":
            summ["settled"] += 1
            summ["settled_prod_" + r["prod"]] += 1
            if r.get("zone_l3") is not None:
                summ["settled_zoned"] += 1
                summ["settled_zone_" + r["prod_zone"]] += 1
        if "cause" in r:
            causes[r["class"] + ": " + r["cause"]] += 1
    res = {"level": trace["level"], "solid_tris": int(len(P)), "census_absent": len(absent), "setup_cpu_s": round(setup, 2), "moves": moves,
           "launch_summary": dict(summ), "causes": dict(causes.most_common()), "speed": sp,
           "tests_per_tick": round(world.tests / max(1, sp["ticks"]), 2)}
    print(json.dumps(res))
    if a.out:
        fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"summary": res, "launches": launches}, f, indent=1)


if __name__ == "__main__":
    sys.exit(main())
