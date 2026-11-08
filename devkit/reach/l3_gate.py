"""The trick explorer's starts and the long-replay gate (Step TD.0; the trick-discovery plan's T0 and its pilot P1/P2).

``states``: each L3 snapshot's player run with the pad at rest for ``--ticks`` player ticks, the states it holds
(counts) and its HP: whether a start is natural ground (sitting x7's w1 start swims on every tick).  ``start``: in a
sandbox, a natural start from a loadable state (the w1 beach spawn from ``vanilla-rz-new``): its first player ticks
run with the pad at rest until the player has stood in ``--state`` (0, the ground) ``--settle`` ticks in a row, then
an L3 snapshot of the next update entry (``Sandbox.snapshot``), kept halted there with ``--hold``.  ``build``: an L3
input string of at least ``--ticks`` player ticks from a snapshot, drawn segment by segment (8-32 ticks: a heading
in 24 sectors with a little noise or the stick at rest; magnitude 0.35, 0.7 or 1.0; Y, BLACK or nothing held; the
camera turned toward the heading at most 3.33 degrees a tick) and each kept only when L3 runs it with the player
alive and unhurt (no hazard), untainted, within ``--radius`` m of the start (fewer exits and pickups on the way)
and never more than ``FALL`` ticks airborne; a refused draw is drawn again from the same state, and after
``TRIES`` refusals the last segments are dropped.  Seeded: a seed and a
snapshot give one string.  ``replay``: that string replayed in xemu from the snapshot's start where ``start --hold``
left the guest (``Sandbox.replay`` with D172's stops: a level load, a popup or a dialog ends it, and so does the
first tick off L3 by any distance or in state or HP), the comparison (``l3_compare``: every observed field's
count of ticks off too) and where it broke, and the replay into the conformance corpus.  The gate (PLAN §5 T0): at least 5,000 ticks replayed exactly.

``--scene`` (Step TD.4b): whole steps instead of player ticks, so rigs, enemies and triggers run (D172's chains
through rides, TD.5's whole-step re-runs): ``start --scene`` takes the snapshot at the next scene tick's entry,
``build --scene`` draws the string in whole steps, ``replay --scene`` runs L3's side in whole steps (the xemu side is
the same per-tick replay) and the gate is then 5,000 whole steps replayed exactly.  ``split``: a long string from the
snapshot's own start (as ``build``'s) run in L3 and cut at settle points into D172 pieces of at most ``--most``
ticks (``l3_explore.split``), each a string of its own for a chained replay.

    uv run --locked python -m devkit reach l3-gate states LABEL [LABEL ...] [--ticks 120] [--scene]
    uv run --locked python -m devkit reach l3-gate start W TAG LABEL [--state 0] [--settle 10] [--hold] [--scene]
    uv run --locked python -m devkit reach l3-gate build LABEL OUT [--ticks 5200] [--seed 1] [--radius 40] [--scene]
    uv run --locked python -m devkit reach l3-gate replay W LABEL OUT [--scene]
    uv run --locked python -m devkit reach l3-gate split LABEL IN OUT [--most 5000] [--scene]

The string (OUT: ``l3.pads`` segments, no positions) and the snapshots stay in the private L3 store; printed output
is counts, metres and hashes only.  Dev only (devkit, Step 4.13d2), never a player's verb and never in pytest; the sandbox rules are the
azurik-xemu-oracle skill's.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import random
import struct
import sys
import time
from pathlib import Path

from azurkit.tools.randomizer.live import recipes
from devkit.sim import corpus, inputs, l3
from devkit.sim.l3_explore import GATE_TICKS
from devkit.sim.l3_explore import split as split_rows
from devkit.sim.l3_search import segments, string_sha12
from devkit.xemu import oracle as xo

FALL = 90              # airborne ticks a kept segment may reach (a fall past it risks the fall rule 0x8BE00)
UNSAFE = (7, 8)        # dead
TRIES = 64             # draws from one state before the build backs off a segment


def _sim(label: str, store=None, scene: bool = False) -> l3.L3:
    return l3.L3(l3.read_snapshot(l3.snapshot_path(label, store)), xo.read_file(xo.vanilla_iso(), "default.xbe"),
                 deep=False, scene=scene)


def states(labels: list[str], ticks: int, store=None, scene: bool = False) -> list[dict]:
    """Per snapshot: the states its player holds over ``ticks`` neutral player ticks (whole steps with ``scene``;
    counts, by hex), its HP at the start and the end, its level."""
    out = []
    for label in labels:
        sim = _sim(label, store, scene)
        rows = sim.run([l3.Pad()] * ticks)
        out.append({"label": label, "level": sim.snap.meta.get("level"), "start_state": hex(sim.snap.meta["state"]),
                    "states": {hex(s): n for s, n in sorted(collections.Counter(r.state for r in rows).items())},
                    "hp": [sim.snap.meta.get("hp"), rows[-1].hp], "taint": sorted(rows[-1].taint)})
    return out


def start(sb, tag: str, label: str, *, state: int = 0, settle: int = 10, max_ticks: int = 900,
          store=None, scene: bool = False) -> dict:
    """``loadvm tag`` (halted at its first player tick), then player ticks with the pad at rest until the state
    has been ``state`` for ``settle`` ticks in a row (within ``max_ticks``), then the L3 snapshot ``label`` (with
    ``scene``, at the next scene tick's entry, for whole steps)."""
    load = sb.loadvm(tag)
    seen, run = collections.Counter(), 0
    for _ in range(max_ticks):
        if sb.wait_bp([xo.PLAYER_TICK], 10.0) != xo.PLAYER_TICK:
            raise SystemExit(f"no player tick within 10 s after {sum(seen.values())} (a menu, dialog or cutscene?)")
        st = sb.read_u32(sb.read_u32(sb.g.regs()["esp"] + 4) + 0x94)
        seen[st] += 1
        run = run + 1 if st == state else 0
        if run >= settle:
            break
    else:
        raise SystemExit(f"{tag}: never {settle} ticks in a row in state {state:#x} within {max_ticks} "
                         f"({dict(seen)})")
    snap = sb.snapshot(label, store=store, scene=scene)
    return {"tag": tag, "loadvm_s": load.get("loadvm_s"), "ticks_before": sum(seen.values()),
            "states_before": {hex(s): n for s, n in sorted(seen.items())},
            **{k: snap[k] for k in ("label", "level", "state", "hp", "pages", "sha12")}}


def build(sim: l3.L3, ticks: int, seed: int, radius: float) -> tuple[list[dict], dict]:
    """The string (``l3.pads`` segments with ``yaw``: a tick's own while the camera turns) and its counts (the
    module docstring).  Each tick of a segment turns the camera toward its heading by at most ``CAM_RATE`` and
    points the stick along the heading under that camera; a back-off goes on from the kept segments' last camera
    and airborne run."""
    rng = random.Random(seed)
    probe = sim.save()
    r0 = sim.step(l3.Pad())
    cam0, home, hp0 = math.atan2(-struct.unpack("<2f", r0.cam)[0], struct.unpack("<2f", r0.cam)[1]), r0.pos, r0.hp
    sim.reset(probe)
    kept: list[tuple[list[l3.Pad], collections.Counter, float, int]] = []   # pads, states, last camera, air run
    total, refused, why = 0, 0, collections.Counter()
    while total < ticks:
        at = sim.save()
        cam, air = kept[-1][2:] if kept else (cam0, 0)
        for _ in range(TRIES):
            n = rng.randint(8, 32)
            if rng.random() < 0.1:
                heading, mag = None, 0.0
            else:
                heading, mag = rng.randrange(24) * math.pi / 12 + rng.uniform(-0.1, 0.1), rng.choice((0.35, 0.7, 1.0))
            buttons = frozenset(rng.choices([[], ["y"], ["black"]], weights=(6, 3, 1))[0])
            seg, got, a, y, bad = [], collections.Counter(), air, cam, None
            try:
                for _k in range(n):
                    y = inputs.camera(y, heading)
                    seg.append(l3.Pad(inputs.stick(heading, y, mag), buttons, y))
                    r = sim.step(seg[-1])
                    got[r.state] += 1
                    a = a + 1 if r.state == 2 else 0
                    bad = ("dead" if r.state in UNSAFE else "hurt" if r.hp < hp0 else "taint" if r.taint
                           else "airborne" if a > FALL else "radius" if math.dist(r.pos[:2], home[:2]) > radius
                           else None)
                    if bad:
                        break
            except l3.L3Error:
                bad = "l3 error"
            if bad is None:
                break
            why[bad] += 1
            refused += 1
            sim.reset(at)
        else:
            if not kept or refused > 100 * TRIES:
                raise SystemExit(f"no safe segment at tick {total} after {refused} refused draws ({dict(why)})")
            del kept[-3:]   # back off: the last segments led nowhere safe; rebuild from the state before them
            sim.reset()
            sim.run([pad for k in kept for pad in k[0]])
            total = sum(len(k[0]) for k in kept)
            continue
        kept.append((seg, got, y, a))
        total += n
    pad_list = [pad for k in kept for pad in k[0]]
    seen = sum((k[1] for k in kept), collections.Counter())
    return segments(pad_list), {"ticks": total, "segments": len(kept), "refused": refused, "why": dict(why),
                                "states": {hex(s): k for s, k in sorted(seen.items())},
                                "string_sha12": string_sha12(pad_list)}


def replay(sb, label: str, segs: list[dict], store=None, scene: bool = False) -> dict:
    """``segs`` run in L3 from snapshot ``label`` (whole steps with ``scene``) and replayed in xemu from its start
    (the guest halted there), every tick compared; ends on the first tick off (any distance, state or HP), a load
    or a stall."""
    snap = l3.read_snapshot(l3.snapshot_path(label, store))
    pads = l3.pads(segs)
    t0 = time.monotonic()
    rows = l3.L3(snap, sb._xbe("dvd.iso"), scene=scene).run(pads)
    t1 = time.monotonic()
    stops = {"diverge": 0.0}
    got = sb.replay(pads, rows, snap.meta, stops=stops)
    corpus.record(snap.meta, scene, pads, rows, got, store=store, disc=sb.disc_source())
    cmp = xo.l3_compare(rows[:len(got)], got)
    off = next((k for k, (a, b) in enumerate(zip(rows, got))   # the first tick off: the body, the state or HP
                if math.dist(a.pos, b["pos"]) or (a.state, a.hp) != (b["state"], b["hp"])), None)
    return {"label": label, "mode": "scene" if scene else "tick", "l3_ticks": len(rows), "replayed": len(got),
            "stop": stops,
            "exact_ticks": len(got) if off is None else off,
            "gate_5000": off is None and len(got) >= 5000 and stops.get("at") == "entry",
            "l3_s": round(t1 - t0, 1), "xemu_s": round(time.monotonic() - t1, 1),
            **{k: cmp[k] for k in ("max_err_m", "first_err_tick", "states_differ", "hp_differ", "path_m")},
            "fields_differ": cmp.get("fields_differ")}   # per observed field, the ticks off (TD.0's fields too)


def split(sim: l3.L3, segs: list[dict], most: int = GATE_TICKS) -> list[dict]:
    """``segs`` run in ``sim`` and cut at settle points into D172 pieces of at most ``most`` ticks
    (``l3_explore.split``), each with its own string (``l3.pads`` segments) and hash."""
    pads = l3.pads(segs)
    rows = sim.run(pads)
    return [{**p, "string": segments(pads[p["start"]:p["start"] + p["ticks"]]),
             "string_sha12": string_sha12(pads[p["start"]:p["start"] + p["ticks"]])}
            for p in split_rows(rows, most=most)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("states", help="the states each snapshot's player holds over neutral L3 ticks")
    p.add_argument("labels", nargs="+")
    p.add_argument("--ticks", type=int, default=120)
    p = sub.add_parser("start", help="a natural start: settle in a state after a load, then an L3 snapshot")
    p.add_argument("W", type=Path)
    p.add_argument("tag")
    p.add_argument("label")
    p.add_argument("--state", type=lambda v: int(v, 0), default=0)
    p.add_argument("--settle", type=int, default=10)
    p.add_argument("--hold", action="store_true", help="leave the guest halted at the start, for replay")
    p = sub.add_parser("build", help="a long safe L3 string from a snapshot")
    p.add_argument("label")
    p.add_argument("out", type=Path, help="the segments JSON (keep it in the private store)")
    p.add_argument("--ticks", type=int, default=5200)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--radius", type=float, default=40.0)
    p = sub.add_parser("replay", help="the string replayed in xemu from the held start, every tick compared")
    p.add_argument("W", type=Path)
    p.add_argument("label")
    p.add_argument("inputs", type=Path)
    p = sub.add_parser("split", help="a long string cut at settle points into D172 pieces")
    p.add_argument("label")
    p.add_argument("inputs", type=Path)
    p.add_argument("out", type=Path, help="the pieces JSON (keep it in the private store)")
    p.add_argument("--most", type=int, default=GATE_TICKS)
    for q in sub.choices.values():
        q.add_argument("--store", type=Path, help="the private L3 store (default: the user data dir's)")
        q.add_argument("--scene", action="store_true", help="whole steps (a --scene snapshot, or one holding its "
                       "stack)")
    a = ap.parse_args(argv)
    if a.cmd == "states":
        for row in states(a.labels, a.ticks, a.store, a.scene):
            print(json.dumps(row))
        return 0
    if a.cmd in ("build", "split"):
        t0 = time.monotonic()
        if a.cmd == "build":
            segs, info = build(_sim(a.label, a.store, a.scene), a.ticks, a.seed, a.radius)
        else:
            segs = split(_sim(a.label, a.store, a.scene), json.loads(a.inputs.read_text(encoding="utf-8")), a.most)
            info = {"pieces": [{k: p[k] for k in ("start", "ticks", "settled", "string_sha12")} for p in segs]}
        l3.private_out(a.out, segs)
        print(json.dumps({**info, "mode": "scene" if a.scene else "tick", "seconds": round(time.monotonic() - t0, 1)}))
        return 0
    sb = xo.Sandbox.attach(a.W)
    try:
        if a.cmd == "start":
            print(json.dumps(start(sb, a.tag, a.label, state=a.state, settle=a.settle, store=a.store, scene=a.scene)))
            if a.hold:
                sb.detach()
                return 0
        else:
            out = replay(sb, a.label, json.loads(a.inputs.read_text(encoding="utf-8")), a.store, a.scene)
            print(json.dumps(out))
            return 0 if out["gate_5000"] else 1
    finally:
        sb.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
