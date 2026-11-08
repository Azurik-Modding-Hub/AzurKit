"""Step R2.17's native-kernel prototype: L3 traces of sampled reach-engine launches, tick by tick, with the game's
own move internals, for ``devkit/reach/native_check.py`` to compare the native kernel against.

Per level, launches are sampled (seeded) from the bench's cached records (R2.16e round 1: the R0 fan plan and the
aims plan's first pass, whose starts are the job's own "run"/"stand" placements and heading), stratified by macro,
and replayed on one in-process L3 exactly as the engine ran them: the start placed (``runner.place``), the kit set
(``runner.set_kit``), then the witness's pads (``l3.pads(segments)``).  A replay whose length or landing differs from
its record is dropped and counted.  Each tick keeps the pad, the light observation and, by Unicorn hooks on the
game's move code, every player move (0x47380): its request (radii, dt, position, velocity after gravity, the
friction reference w, flags), each sweep's contact record (0x4754C: t, normal, d, word, the hit object's flag
bit 21), its result (0x48030: position, velocity, contact flag), and the walk's ground probe (0x86249) and the
classifier's contact (0x85920).

Private output (positions): a pickle at OUT (mode 0600); stdout prints counts only.
    nice -n 10 uv run --locked python -m devkit reach native-trace LEVEL SNAPSHOT N_FAN N_AIM SEED OUT
"""

from __future__ import annotations

import collections
import json
import os
import pickle
import random
import struct
import sys
import time
from pathlib import Path

from devkit.reach import reach_engine as RE  # noqa: E402
from unicorn import UC_HOOK_CODE  # noqa: E402
from unicorn import x86_const as X  # noqa: E402

from devkit.sim.ports import vanilla_iso  # noqa: E402
from devkit.sim.ports import read_file  # noqa: E402
from devkit.reach.engine import cache, runner  # noqa: E402
from devkit.sim import l3  # noqa: E402
from devkit.reach.l3_pool import Worker  # noqa: E402

MOVE, SWEPT, MOVE_END, PROBED, CLASSIFY = 0x47380, 0x4754C, 0x48030, 0x86249, 0x85920
PLANS = {"fan": "r216e-base-fan", "aim": "r216e-r1abc-aims"}


def f3(b, o):
    return struct.unpack_from("<3f", b, o)


class Tap:
    """The hooks: each player move's request, sweeps and result, the walk's probe and the classifier's contact."""

    def __init__(self, sim) -> None:
        self.sim, self.uc = sim, sim.uc
        self.tick: list = []
        self.cur = None
        for va, fn in ((MOVE, self._move), (SWEPT, self._swept), (MOVE_END, self._end), (PROBED, self._probed),
                       (CLASSIFY, self._classify)):
            self.uc.hook_add(UC_HOOK_CODE, fn, begin=va, end=va)

    def esp(self) -> int:
        return self.uc.reg_read(X.UC_X86_REG_ESP)

    def u32(self, va) -> int:
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def _move(self, uc, addr, size, _):
        req = self.u32(self.esp() + 4)
        b = bytes(uc.mem_read(req, 0x70))
        self.cur = {"req": req, "r": struct.unpack_from("<2f", b, 4), "dt": struct.unpack_from("<f", b, 0xC)[0],
                    "pos": f3(b, 0x10), "vel": f3(b, 0x1C), "w": f3(b, 0x28), "f34": b[0x34], "f35": b[0x35],
                    "sweeps": []}
        self.tick.append(("move", self.cur))

    def _rec(self, at: int) -> dict:
        b = bytes(self.uc.mem_read(at, 0x48))
        obj = struct.unpack_from("<I", b, 0x38)[0]
        flag = None
        if obj:
            try:
                flag = (self.u32(obj + 0x168) >> 21) & 1
            except Exception:  # noqa: BLE001
                flag = None
        return {"p0": f3(b, 0), "n": f3(b, 0xC), "t": struct.unpack_from("<f", b, 0x18)[0],
                "d": struct.unpack_from("<f", b, 0x1C)[0], "word": struct.unpack_from("<I", b, 0x20)[0],
                "obj": obj, "dl": flag, "sv": f3(b, 0x3C)}

    def _swept(self, uc, addr, size, _):
        if self.cur is None:
            return
        esp = self.esp()
        hit = uc.reg_read(X.UC_X86_REG_EAX) & 0xFF
        s = {"hit": hit, "pos": f3(bytes(uc.mem_read(esp + 0x28, 12)), 0),
             "target": f3(bytes(uc.mem_read(esp + 0x38, 12)), 0),
             "rem": struct.unpack("<f", uc.mem_read(esp + 0x18, 4))[0]}
        if hit:
            s.update(self._rec(esp + 0x48))
        self.cur["sweeps"].append(s)

    def _end(self, uc, addr, size, _):
        if self.cur is None:
            return
        esp = self.esp()
        req = self.cur["req"]
        b = bytes(uc.mem_read(req, 0x160))
        self.cur.update(out=f3(bytes(uc.mem_read(esp + 0x38, 12)), 0), vout=f3(b, 0x60), contact=b[0x15C])
        self.cur = None

    def _probed(self, uc, addr, size, _):
        esp = self.esp()
        hit = uc.reg_read(X.UC_X86_REG_EAX) & 0xFF
        p = {"hit": hit}
        if hit:
            p.update(self._rec(esp + 0x80))
        self.tick.append(("probe", p))

    def _classify(self, uc, addr, size, _):
        esp = self.esp()
        rec = self.u32(esp + 0xC)
        self.tick.append(("classify", self._rec(rec)))

    def take(self) -> list:
        t, self.tick, self.cur = self.tick, [], None
        return t


def obs_row(row) -> dict:
    o = row.obs
    return {"pos": row.pos, "state": row.state, "hp": row.hp, "vel": o.vel if o else None,
            "normal": o.normal if o else None, "flaps_used": o.flaps_used if o else None,
            "peak_z": o.peak_z if o else None, "gauge": o.gauge if o else None, "anim": o.anim if o else None,
            "cam": struct.unpack("<2f", row.cam) if row.cam else None}


def candidates(level: str, snap: dict) -> dict:
    """{stage: [(job, rec, outcome index)]} of replayable launches (a start the job's own placement made)."""
    base = cache.folder(level)
    out = {}
    for stage, plan in PLANS.items():
        rows = []
        for j in RE._plan(level, plan, snap)["jobs"]:
            rec = cache.get(base, j["key"])
            if rec is None:
                continue
            for i, o in enumerate(rec["outcomes"]):
                st = rec["starts"].get(o.get("start", ""))
                if o.get("start") not in ("run", "stand") or not st or "cell" not in st:
                    continue
                if o["end"].startswith("fault") or o.get("pass", 1) != 1:
                    continue
                rows.append((j, rec, i))
        out[stage] = rows
    return out


def stratified(rows, n: int, rnd: random.Random):
    by = collections.defaultdict(list)
    for r in rows:
        by[r[1]["outcomes"][r[2]]["macro"]].append(r)
    keys = sorted(by)
    for k in keys:
        rnd.shuffle(by[k])
    pick = []
    while len(pick) < n and any(by[k] for k in keys):
        for k in keys:
            if by[k] and len(pick) < n:
                pick.append(by[k].pop())
    return pick




def main(argv=None) -> None:
    level, label, n_fan, n_aim, seed, out = (sys.argv[1:] if argv is None else argv)[:6]
    n = {"fan": int(n_fan), "aim": int(n_aim)}
    t0 = time.process_time()
    snap = RE._snap(label)
    cands = candidates(level, snap)
    rnd = random.Random(f"r2.17-native-{level}-{seed}")
    W = Worker(label, RE._store(None), read_file(str(vanilla_iso()), "default.xbe"), None)
    sim = W.sim(False, deep=False)
    tap = Tap(sim)
    result = {"level": level, "snapshot": label, "launches": []}
    counts = collections.Counter()
    steps = 0
    for stage in ("fan", "aim"):
        for j, rec, i in stratified(cands[stage], n[stage], rnd):
            o = rec["outcomes"][i]
            st = rec["starts"][o["start"]]
            sim.reset()
            tap.take()
            runner.place(sim, st["feet"], rec["heading"], st["cell"])
            kit_rows = runner.set_kit(sim, o["kit"])
            tap.take()
            start = obs_row(kit_rows[-1])
            ticks = []
            for pad in l3.pads(o["segments"]):
                try:
                    row = sim.step(pad)
                except l3.L3Error as exc:
                    ticks.append({"fault": str(exc)[:80]})
                    break
                ticks.append({"pad": (pad.stick, sorted(pad.buttons), pad.cam), "obs": obs_row(row),
                              "tap": tap.take()})
            steps += 21 + len(kit_rows) + len(ticks)
            last = ticks[-1].get("obs") if ticks else None
            ok = (last is not None and len(ticks) == o["ticks"] and o["land"] is not None
                  and max(abs(a - b) for a, b in zip((last["pos"][0], last["pos"][1], last["pos"][2] - 1.0),
                                                     o["land"])) < 1e-4)
            counts[(stage, "ok" if ok else "differs")] += 1
            result["launches"].append({"stage": stage, "job": j["id"], "macro": o["macro"], "kit": o["kit"],
                                       "end": o["end"], "first": o.get("first"), "ok": ok, "start": start,
                                       "ticks": ticks})
    cpu = time.process_time() - t0
    p = Path(out)
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        pickle.dump(result, f)
    print(json.dumps({"level": level, "candidates": {k: len(v) for k, v in cands.items()},
                      "replayed": {f"{a}:{b}": c for (a, b), c in sorted(counts.items())},
                      "l3_steps": steps, "cpu_s": round(cpu, 1)}))


if __name__ == "__main__":
    main()
