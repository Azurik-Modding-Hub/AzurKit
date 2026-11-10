"""The exhaustive reach engine (``devkit/reach/engine/``, Step R2.16a): its nodes, launches, runner, cache,
graph, verdicts and witness records, on a hand-built two-platform level run by a stand-in for L3 (pure: the
engine's L3 runs are evidence, never pytest)."""

from __future__ import annotations

import argparse
import collections
import functools
import gzip
import json
import math
import os
import pickle
import shutil
from pathlib import Path

import numpy as np
import pytest

from devkit.rando.draft.reach import Reach
from azurkit.tools.randomizer.planner import proofs
from devkit.reach.engine import aim, cache, candidates, fast, graph, hold, runner, triggers, verdict, worker
from devkit.reach.engine.nodes import Nodes, Zones
from devkit.sim import l3, obs
from tests.test_reach_model import _level, _quad

G, DT = 9.8, 1 / 30


class _Sim:
    """A stand-in for L3 on axis-aligned floors ((x0, y0, x1, y1, z) each): a run at 7 m/s along the pad's heading
    (camera yaw plus the stick's angle), a jump of 1.1 m (1.2 m with air) that latches peak_z, the game's air law
    (v := T + (v - T) 0.6^dt toward air control 9, 12 with air, x the stick) and flap law with air (up to Flaps
    1/2/5 a jump; d = peak_z + 1.2 - z, vz := min(v0f, vz + 1.5 v0f)), gravity, a landing on a floor's top, death
    30 m under the floors; BLACK's roll (state 0x100: 21 rows at 4.8 m/s along the heading it was pressed at, off an
    edge falling; a press on its rows 12-20 chains another every 19; Y held on its last row jumps, in mid-air too,
    and resets the flaps); R6 places the feet (the body 1 m over them), airborne."""

    def __init__(self, floors):
        self.floors, self.taint = floors, set()
        self._base = self._s = {"feet": (0.0, 0.0, 0.0), "v": (0.0, 0.0, 0.0), "state": 0, "air": 0, "flaps": 0,
                                "y": False, "b": False, "cam": 0.0, "k": 0, "peak": None, "roll": None}

    def save(self):
        return dict(self._s)

    def reset(self, state=None):
        self._s = dict(state or self._base)

    def kit_writes(self, kit):
        return (("air", int(kit.get("air", 0))),)

    def teleport(self, feet, yaw, *, cell=None):
        self._s.update(feet=(feet[0], feet[1], feet[2] + 0.01), v=(0.0, 0.0, 0.0), state=2)
        return self.step()

    def _floor(self, x, y, z0, z1):
        return max((f[4] for f in self.floors if f[0] <= x <= f[2] and f[1] <= y <= f[3] and z1 <= f[4] <= z0),
                   default=None)

    def _jump(self, s, z):
        h = 1.2 if s["air"] else 1.1
        s["state"], s["flaps"], s["peak"] = 2, 0, z + 1.0 + h
        return math.sqrt(2 * G * h)

    def step(self, pad=l3.Pad(), writes=()):
        s = self._s
        for va, v in writes:
            s["air"] = v
        s["cam"] = (math.atan2(-pad.cam[0], pad.cam[1]) if pad.cam is not None    # a recorded string's f32 pair
                    else s["cam"] if pad.yaw is None else pad.yaw)
        mag = min(1.0, math.hypot(*pad.stick))
        h = s["cam"] + math.atan2(-pad.stick[0], pad.stick[1])
        tx, ty = -math.sin(h) * 7.0 * mag, math.cos(h) * 7.0 * mag
        y = "y" in pad.buttons and "lt" not in pad.buttons
        black = "black" in pad.buttons
        press, s["y"] = y and not s["y"], y
        tap, s["b"] = black and not s["b"], black
        (x, yy, z), (vx, vy, vz) = s["feet"], s["v"]
        if s["state"] == 0 and tap:
            s["state"], s["roll"] = 0x100, {"t": 0, "h": h, "chain": False}
        if s["state"] == 0x100:
            r = s["roll"]
            vx, vy = -math.sin(r["h"]) * 4.8, math.cos(r["h"]) * 4.8
            vz = 0.0 if self._floor(x, yy, z + 0.05, z - 0.05) is not None else vz - G * DT
            r["chain"] |= tap and 11 <= r["t"] <= 19
            if r["t"] == 20 and y:
                vz = self._jump(s, z)
            elif r["t"] == 18 and r["chain"]:
                r.update(t=-1, chain=False)
            elif r["t"] == 20:
                s["state"] = 0 if vz == 0.0 else 2
            r["t"] += 1
        elif s["state"] == 0:
            vx, vy = tx, ty
            if press:
                vz = self._jump(s, z)
        else:
            ac = (12.0 if s["air"] else 9.0) * mag
            bl = 0.6 ** DT
            vx, vy = -math.sin(h) * ac + (vx + math.sin(h) * ac) * bl, math.cos(h) * ac + (vy - math.cos(h) * ac) * bl
            if press and s["air"] and s["flaps"] < {1: 1, 2: 2, 3: 5}[s["air"]]:
                d = 1.2 if s["peak"] is None else s["peak"] + 1.2 - (z + 1.0)
                v0f = math.sqrt(2 * G * min(max(d, 0.0), 1.2))
                vz, s["flaps"] = min(v0f, vz + 1.5 * v0f), s["flaps"] + 1
            vz -= G * DT
        nx, ny, nz = x + vx * DT, yy + vy * DT, z + vz * DT
        top = self._floor(nx, ny, max(z, nz), min(z, nz) - 0.05)
        if s["state"] == 0 and top is None and self._floor(nx, ny, z + 0.4, z - 0.4) is None:
            s["state"], vz = 2, 0.0                       # walked off
        elif s["state"] in (2, 0x100) and vz <= 0 and top is not None:
            nz, vz = top, 0.0
            s["state"] = 0 if s["state"] == 2 else 0x100
        elif s["state"] == 0:
            nz = z
        if nz < -30:
            s["state"] = 7
        s["feet"], s["v"], s["k"] = (nx, ny, nz), (vx, vy, vz), s["k"] + 1
        pos = (nx, ny, nz + 1.0)
        o = obs.Obs(pos, (vx, vy, vz), s["state"], 0 if s["state"] == 7 else 200, 200, s["flaps"],
                    normal=(0.0, 0.0, 1.0), anim=0, peak_z=s["peak"])
        return l3.Row(s["k"], pos, s["state"], o.hp, None, (), l3.camera_dir(s["cam"]), frozenset(), o)


A, B, C = (-8, 0, 4, 4, 0.0), (12, 0, 20, 4, 0.0), (0, 8, 4, 12, 10.0)   # B 8 m past A; C 10 m up


def _zone(feet, prefer_water=False, fallback=True):
    """The zones of the toy derived doc: one per platform."""
    return next((z for z, f in (("t.Z000", A), ("t.Z001", B), ("t.Z002", C))
                 if f[0] - 0.5 <= feet[0] <= f[2] + 0.5 and f[1] - 0.5 <= feet[1] <= f[3] + 0.5), None)


@pytest.fixture(scope="module")
def two_platforms():
    """The level's nodes and its R0 fan run on the stand-in: (nodes, jobs by key, records)."""
    nodes = Nodes(Reach(_level(_quad(*A[:4], A[4]) + _quad(*B[:4], B[4]) + _quad(*C[:4], C[4])), flights=False))
    nodes.zone_at = _zone
    jobs = runner.fan_jobs(nodes, nodes.takeoffs())
    for j in jobs:
        j["key"] = cache.job_key(j, "0" * 12, "c" * 12)
    sim = _Sim([A, B, C])
    return nodes, {j["key"]: j for j in jobs}, [runner.run_job(sim, j, here=0) for j in jobs]


def test_two_platforms_join_across_the_gap_only_with_a_flap(two_platforms):
    """The known answer: a running jump (about 6.8 m) falls short of the platform 8 m past the first and dies; the
    shield's jump and one flap lands on it, and only the shield's flaps land back; the platform 10 m up is no
    launch's.  So the edge's least
    air rank is 1, the closure grows with the kit (monotone) and reaches the high one at none; the takeoffs face
    out of their platforms; the zone edges don't hang on how the floors are cut into nodes (both platforms one
    walkable region: the same zone edges, no node edge); the same jobs run again give the same strings, and a
    string's id names its kit (the same pads in both kit branches are two witnesses); and the verdicts read off
    it: the toy derive's flap across FOUND (at its air 1, and so with water beside its air: the witness needs none;
    with ``requires false`` N/A, the derive's own fault, which the report's graded recall leaves out and the
    witness refutes), its jump up MAY, a row needing an event N/A, a row to a
    zone neither graph reaches MAY (R0 refutes nothing) but N/A if it asks for fire too, DATA once a derived
    geometry edge alone reaches it, and a hand edge there N/A; and the report's recall counts a find at the
    edge's own kit only (a jump across found with a flap misses); and a worker's pickled zone map
    (``nodes.Zones``) names the zones the nodes do."""
    nodes, jobs, recs = two_platforms
    a, b, c = (nodes.node_at((f[0] + 2, f[1] + 2, f[4]), 0) for f in (A, B, C))
    ts = nodes.takeoffs()
    assert {t.region for t in ts} == {nodes.region_at((f[0] + 2, f[1] + 2, f[4])) for f in (A, B, C)}
    east = [t for t in ts if nodes.node_at(t.feet, 0) == a and t.feet[0] > 3.5 and 1 < t.feet[1] < 3]
    assert east and all(abs(math.remainder(t.heading + math.pi / 2, 2 * math.pi)) < 0.5 for t in east)  # faces +x
    g = graph.Graph(nodes, jobs, recs)
    assert min(g.edges[(a, b)]) == 1 and min(g.edges[(b, a)]) >= 1
    reach = {r: graph.closure(g.adjacency(r), [a]) for r in graph.RANKS}
    assert reach[0] == {a} and reach[1] >= {a, b} and c not in reach[3]
    assert all(reach[r] <= reach[r + 1] for r in graph.RANKS[:-1])
    one = type("One", (), {"frozen": {}, "zone_at": staticmethod(_zone), "node_at": lambda self, feet, state: "n"})()
    g1 = graph.Graph(one, jobs, recs)
    strings = {pair: {r: w["string_sha12"] for r, w in got.items()} for pair, got in g.zones.items()}
    assert not g1.edges and g1.zones and {pair: {r: w["string_sha12"] for r, w in got.items()}
                                          for pair, got in g1.zones.items()} == strings
    assert all("one_region" in w["flags"] for pair in g1.zones for w in g1.witnesses(pair))
    assert not any("one_region" in w["flags"] for pair in g.zones for w in g.witnesses(pair))
    again = [runner.run_job(_Sim([A, B, C]), j, here=0) for j in list(jobs.values())[:6]]
    assert [o["string_sha12"] for r in again for o in r["outcomes"]] == \
        [o["string_sha12"] for r in recs[:6] for o in r["outcomes"]]
    kits = collections.defaultdict(set)
    for o in (o for r in recs for o in r["outcomes"]):
        kits[o["string_sha12"]].add(o["kit"])
    assert all(len(k) == 1 for k in kits.values())
    derived = {"edges": [{"from": "t.Z000", "to": "t.Z001", "kind": "flap", "confidence": "modelled",
                          "requires": "air>=1"},
                         {"from": "t.Z000", "to": "t.Z002", "kind": "jump", "confidence": "modelled",
                          "requires": "true"}]}
    got = {(x["from"], x["to"]): (x["verdict"], x.get("rank")) for x in verdict.zone_edges(derived, g)}
    assert got == {("t.Z000", "t.Z001"): (verdict.FOUND, 1), ("t.Z000", "t.Z002"): (verdict.MAY, None)}
    mixed = {"edges": [derived["edges"][0] | {"requires": r} for r in ("air>=1 & water>=1", "false")]}
    assert [(x["verdict"], x.get("over"), x.get("extra"), x.get("refuted")) for x in verdict.zone_edges(mixed, g)] \
        == [(verdict.FOUND, False, ["water:1"], None), (verdict.NA, None, None, 1)]
    graded = verdict.report("t", mixed, {}, {}, g)["modelled"]
    assert graded["recall"] == 0.5 and graded["graded"] == {"edges": 1, "recall": 1.0, "out": {"requires false": 1}}
    level_doc = {"node": [{"id": n, "anchors": [f"zone:{z}"]} for n, z in (("na", "t.Z000"), ("nc", "t.Z002"))],
                 "edge": [{"from": "na", "to": "nc", "requires": "event:t.lift", "confidence": "assumed"},
                          {"from": "na", "to": "nc", "requires": "true", "confidence": "assumed"}]}
    assert [x["verdict"] for x in verdict.rows(derived, level_doc, g)] == [verdict.NA, verdict.MAY]
    level_doc["node"].append({"id": "nb", "anchors": ["zone:t.Z001"]})
    level_doc["edge"] = [{"from": "nb", "to": "nc", "requires": "air>=3", "confidence": "assumed"}]
    assert [x["verdict"] for x in verdict.rows(derived, level_doc, g)] == [verdict.MAY]
    walk = {"from": "t.Z001", "to": "t.Z002", "kind": "walk", "confidence": "geometry", "requires": "true"}
    assert [x["verdict"] for x in verdict.rows({"edges": [walk]}, level_doc, g)] == [verdict.DATA]
    assert verdict.hand({}, {"edge": [{"from": "t.Z001", "to": "t.Z002", "requires": "air>=3"}]}, g)[0]["verdict"] \
        == verdict.NA
    jump = {"from": "t.Z000", "to": "t.Z001", "kind": "jump", "confidence": "modelled", "requires": "true"}
    level_doc["edge"] += [{"from": "na", "to": "nb", "requires": "air>=1", "confidence": "assumed"},
                          {"from": "nb", "to": "nc", "requires": "air>=1 & fire>=1", "confidence": "assumed"}]
    rep = verdict.report("t", {"edges": derived["edges"] + [jump]}, level_doc, {}, g)
    assert (rep["modelled"]["found_at_kit"], rep["modelled"]["found_any_rank"], rep["modelled"]["recall"]) == \
        (1, 2, round(1 / 3, 4))
    assert [x["verdict"] for x in rep["assumed"]] == [verdict.MAY, verdict.FOUND, verdict.NA]
    had = getattr(nodes.R, "zone_of", None)
    nodes.R.zone_of = np.arange(nodes.logic.nreg + 64, dtype=np.int64)
    try:
        zones = pickle.loads(pickle.dumps(Zones(nodes)))
        pts = [(f[0] + 2, f[1] + 2, f[4]) for f in (A, B, C)] + [(f[0] + 1, f[1] + 3, f[4] + 0.2) for f in (A, B)]
        names = [Nodes.zone_at(nodes, p, False, False) for p in pts]
        assert None not in names and [zones.zone_at(p, False, False) for p in pts] == names
    finally:
        nodes.R.zone_of = had


def test_a_code_key_ignores_comments_docstrings_and_layout_but_not_a_minus_minus_or_a_string_slash_slash(
        tmp_path, monkeypatch):
    """Step R2.19f+'s SF0 (``cache.code_bytes``, under core_sha12, kernel_sha12 and l3_impl): a C file is hashed as
    its tokens, a Python file as its AST without docstrings, so a comment, a docstring or the spacing moves no key;
    ``a - -b`` and ``a--b``, a ``//`` inside a string and one after it, and a preprocessor line's end keep apart.
    The kernel's code is hashed once a process, not once a job's key (0.1 s a job at the bench's first cut)."""
    def key(name, text):
        (p := tmp_path / name).write_text(text, encoding="utf-8")
        return cache.code_sha12(p)
    rows = [   # (file, text, the same key as the row's first text?)
        ("k.c", "int f(int a, int b) { return a - -b; }  /* x */\n", None),
        ("k.c", "int f(int a,int b){\n  return a - - b;  // y\n}\n", True),
        ("k.c", "int f(int a, int b) { return a--b; }\n", False),
        ("s.c", 'const char *s = "a//b";\n', None),
        ("s.c", 'const char *s = "a" //b;\n', False),
        ("s.c", 'const char *s = "a//b"; /* "c" */\n', True),
        ("d.c", "#define X 1\nint y;\n", None),
        ("d.c", "#define X 1 int y;\n", False),
        ("m.py", 'def f(x):\n    """Doc."""\n    return x + 1  # one\n', None),
        ("m.py", "def f(x):\n\n    return (x +\n            1)\n", True),
        ("m.py", "def f(x):\n    return x + 2\n", False),
    ]
    first = None
    for name, text, same in rows:
        got = key(name, text)
        if same is None:
            first = got
        else:
            assert (got == first) is same, (name, text)
    from devkit.reach.native import backend as KB
    KB.kernel_sha12.cache_clear()
    read, real = [], cache.code_bytes
    monkeypatch.setattr(cache, "code_bytes", lambda p: read.append(p) or real(p))
    assert len({KB.key(f"{n:012x}", "c" * 12) for n in range(3)}) == 3 and len(read) == len(KB.FILES)


def test_a_job_key_moves_with_the_l3_core_and_the_start_and_outcomes_remap_without_a_run(two_platforms, tmp_path):
    """An outcome is cached by the L3 core, the snapshot, the plan's targets and the start, never the derive: an
    edit to a core file moves the core's sha and every key (the jobs run again), as new targets do, and an edit to
    the targeted pass's code moves only an aimed job's core (R0's fan doesn't run again); a new heading
    moves the job's; its id doesn't; a job
    that raises writes no record (it runs again) and ends no batch; and a changed floor split (the far platform cut
    in two, as a re-derive renumbers) re-maps the cached outcomes onto the new nodes with no simulator at all."""
    nodes, jobs, recs = two_platforms
    root = tmp_path / "checkout"
    for rel in cache.CORE_FILES:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(Path(cache.__file__).resolve().parents[3] / rel, root / rel)
    for rel in cache.AIM_FILES:
        shutil.copy(Path(cache.__file__).resolve().parents[3] / rel, root / rel)
    before, aimed = cache.core_sha12(root), cache.core_sha12(root, cache.CORE_FILES + cache.AIM_FILES)
    aim_py = root / "devkit/reach/engine/aim.py"
    aim_py.write_text(aim_py.read_text(encoding="utf-8") + "\nX = 1\n", encoding="utf-8")   # an aim-only edit: the
                                                                                            # aims re-run, the fan not
    assert cache.core_sha12(root) == before and cache.core_sha12(root, cache.CORE_FILES + cache.AIM_FILES) != aimed
    l3_py = root / "devkit/sim/l3.py"
    l3_py.write_text(l3_py.read_text(encoding="utf-8") + "\nX = 1\n", encoding="utf-8")
    assert cache.core_sha12(root) != before
    job = next(iter(jobs.values()))
    assert cache.job_key(job, "0" * 12, "d" * 12) != job["key"]
    assert cache.job_key(job | {"heading": job["heading"] + 0.1}, "0" * 12, "c" * 12) != job["key"]
    assert cache.job_key(job, "0" * 12, "c" * 12, touch="1" * 12) != job["key"]
    assert cache.job_key(job | {"id": "other"}, "0" * 12, "c" * 12) == job["key"]
    assert cache.job_key(job | {"edge": "x"}, "0" * 12, "c" * 12) != job["key"]     # an aim's edge: MORE reads it
    stops = job | {"stop": {"air": 0, "to": "t.Z001", "zoning": "z"}}    # a stopped job's key: its zone code too
    assert cache.job_key(stops, "0" * 12, "c" * 12, zones12="1" * 12) != cache.job_key(stops, "0" * 12, "c" * 12,
                                                                                       zones12="2" * 12)
    assert cache.job_key(job, "0" * 12, "c" * 12, zones12="1" * 12) == job["key"]
    base = cache.folder("t", tmp_path / "cache")
    for r in recs:
        cache.put(base, r["key"], r)
    assert oct(base.stat().st_mode & 0o777) == ("0o700" if os.name == "posix" else "0o777")   # owner-only on POSIX;
                                                       # Windows keeps no such mode, only the read-only bit (writable)

    class _Broken(_Sim):                  # a job whose start raises is that job's error: no record, the batch goes on
        def teleport(self, *a, **k):
            raise RuntimeError("boom")
    worker = type("W", (), {"sim": lambda self, *a, **k: _Broken([A]), "_reach_here": 0})()
    lost = job | {"key": "f" * 12}
    assert runner.job_task(worker, [lost], str(base))[0]["error"] == "RuntimeError: boom"
    assert cache.get(base, lost["key"]) is None
    cut = Nodes(Reach(_level(_quad(*A[:4], A[4]) + _quad(12, 0, 15.5, 4, 0.0) + _quad(17, 0, 20, 4, 0.0)
                             + _quad(*C[:4], C[4])), flights=False))
    g = graph.Graph(cut, jobs, [cache.get(base, k) for k in jobs])
    a = cut.node_at((2, 2, 0.0), 0)
    halves = {cut.node_at((14, 2, 0.0), 0), cut.node_at((18.5, 2, 0.0), 0)}
    assert len(halves) == 2 and {b for (x, b) in g.edges if x == a} & halves


# What ``worker.setup`` (``fast.install_driver``) sets: a test that calls it restores these.
_DRIVER = ((runner, "outcome"), (aim, "find_start"), (aim, "stands"), (fast, "PLACED_ON"))


def test_a_step_stopped_for_time_is_its_jobs_error_and_a_game_fault_its_launchs_end(two_platforms, tmp_path,
                                                                                     monkeypatch):
    """AZ-813: a step L3's watchdog stops for time (``runaway@``: a starved worker, not the game) ends no launch,
    start or hold in the reach engine's pool workers (``worker.setup``): the job is that job's error, no record
    written (a later run tries it again), and a hold raises (no answer cached); the game's own fault
    (``unmapped@``) still ends its launch and its hold."""
    from devkit.reach.engine import worker
    _, jobs, recs = two_platforms
    for mod, name in ((runner, "run_job"), (hold, "replay"), *_DRIVER):
        monkeypatch.setattr(mod, name, getattr(mod, name))
    worker.setup()
    base = cache.folder("t", tmp_path / "cache")
    rec = recs[0]
    job, o = jobs[rec["key"]], next(o for o in rec["outcomes"] if o["macro"].startswith("runjump"))

    def stops(site):
        class _Stops(_Sim):         # a launch's jump press faults at ``site``: mid-launch, mid-hold
            def step(self, pad=l3.Pad(), writes=()):
                if "y" in pad.buttons:
                    raise l3.L3Error(f"stopped at {site}", site)
                return super().step(pad, writes)
        sim = _Stops([A, B, C])
        return sim, type("W", (), {"sim": lambda self, *a, **k: sim, "_reach_here": 0})()
    sim, w = stops("runaway@0x8a000")
    assert runner.job_task(w, [job], str(base))[0]["error"].startswith("StepTimeout: a step stopped for time")
    assert cache.get(base, job["key"]) is None
    with pytest.raises(worker.StepTimeout):
        hold.replay(sim, rec["starts"][o["start"]], rec["heading"], o)
    sim, w = stops("unmapped@0x8a000")
    assert "error" not in runner.job_task(w, [job], str(base))[0]
    assert "fault:unmapped@0x8a000" in {x["end"] for x in cache.get(base, job["key"])["outcomes"]}
    assert hold.replay(sim, rec["starts"][o["start"]], rec["heading"], o)["fault"] == "unmapped@0x8a000"


def test_a_worker_stamps_each_record_with_its_l3_and_an_audit_names_one_its_rerun_gives_otherwise(two_platforms,
                                                                                                    tmp_path,
                                                                                                    monkeypatch):
    """Step R2.19b (PLAN-v2 §1.5c): a pool worker's records carry ``l3_impl`` (base or fast, the loaded libunicorn's
    sha12, the switches), a field outside the record the audits compare, and an audit (``worker.audit_task``, a fast
    run's jobs again on base L3 or with the x87 check) says ``same`` of a cached record its re-run gives and names
    one it gives otherwise: the run then stops (``devkit/reach/reach_engine.py``).  So with a hold answer (Step R2.19f+'s
    X1: ``hold.task`` stamps it, ``worker.hold_audit_task`` replays it again).  The x87 audit's workers' exit lines
    sum to its counts, the C walk's checked and differing decisions too (Step R2.19m)."""
    from devkit.reach.engine import worker
    _, jobs, recs = two_platforms
    for mod, name in ((runner, "run_job"), (hold, "replay"), *_DRIVER):
        monkeypatch.setattr(mod, name, getattr(mod, name))
    worker.setup()
    base = cache.folder("t", tmp_path / "cache")
    w = type("W", (), {"sim": lambda self, *a, **k: _Sim([A, B, C]), "_reach_here": 0})()
    one, two = (jobs[r["key"]] for r in recs[:2])
    runner.job_task(w, [one], str(base))
    impl = cache.get(base, one["key"])["l3_impl"]
    assert impl["l3"] == "base" and len(impl["library"]) == 12 and "code" not in impl
    assert worker.bare(cache.get(base, one["key"])) == worker.bare(recs[0])
    wrong = recs[1] | {"outcomes": [recs[1]["outcomes"][0] | {"land": [0.0, 0.0, 0.0]}, *recs[1]["outcomes"][1:]]}
    cache.put(base, two["key"], wrong)
    assert [(r["id"], r["same"]) for r in worker.audit_task(w, [one, two], str(base))] == \
        [(one["id"], True), (two["id"], False)]
    assert worker.audited("1f4", 500) and not worker.audited("1f5", 500)
    hold.task(w, [(one["key"], 0), (one["key"], 1)], str(base))     # X1: a hold answer is stamped and audited alike
    got = cache.get(base / "hold", hold.key(one["key"], 0))
    assert got["l3_impl"]["l3"] == "base" and "land" in got
    cache.put(base / "hold", hold.key(one["key"], 1), got | {"land": [0.0, 0.0, -9.0]})   # a wrong answer
    assert [r["same"] for r in worker.hold_audit_task(w, [(one["key"], 0), (one["key"], 1)], str(base))] == \
        [True, False]
    (tmp_path / "x87").mkdir()                                 # an x87 audit worker's exit lines (Step R2.19m)
    (tmp_path / "x87" / "1.log").write_text("x87 fast path: 9 fast results, 0 differ from softfloat\n"
                                            "walk check: 7 checked, 1 differ\n", encoding="utf-8")
    assert worker.x87_counts(tmp_path / "x87") == {"results": 9, "differ": 0, "workers": 1, "walk_checked": 7,
                                                   "walk_differ": 1}


def test_the_hold_audit_stops_the_command_on_a_c_walk_decision_that_differs(tmp_path, monkeypatch):
    """Step R2.19m, rebased onto R2.19f+: the hold audit's x87 pool runs FastL3's C walk in check mode, and a face
    decision the walk gives otherwise than the game's code stops the command as the jobs' audit does
    (``devkit/reach/reach_engine.py``'s ``_hold_audit``), every hold answer the same; with none differing it goes on."""
    from devkit.reach import reach_engine as RE

    class _Pool:                # every answer the cached one; an x87 worker's exit line, ``walk`` decisions differing
        walk = 0

        def __init__(self, snap, workers, mode, logs=None, kernel=None):
            self.logs = logs

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def completed(self, fn, batches):
            if self.logs:
                (Path(self.logs) / "1.log").write_text("x87 fast path: 3 fast results, 0 differ from softfloat\n"
                                                       f"walk check: 5 checked, {self.walk} differ\n", encoding="utf-8")
            return [[{"job": j, "outcome": k, "same": True} for j, k in items] for items, _ in batches]
    monkeypatch.setattr(RE, "_pool", _Pool)
    monkeypatch.setattr(RE, "_library", lambda mode: "patched")
    monkeypatch.setattr(worker, "audited", lambda key, every: True)
    for walk in (0, 1):
        _Pool.walk, counts = walk, collections.Counter()
        try:
            RE._hold_audit({}, tmp_path, [("job", 0)], 1, None, counts)
        except SystemExit as stop:
            assert walk and "C walk decisions differing: 1" in str(stop)
        else:
            assert not walk
        assert (counts["hold audit x87: walk checked"], counts["hold audit x87: walk differ"]) == (5, walk)


def test_a_witness_is_an_edge_proof_record_whose_replay_is_owed(two_platforms):
    """A FOUND edge's witness is a ``proofs.jsonl`` ``azurik-l3-proof/1`` edge record (no coordinate) that the
    loader takes once its xemu replay is in: until then its replay is owed and the loader says so."""
    nodes, jobs, recs = two_platforms
    nodes.zone_at = _zone
    g = graph.Graph(nodes, jobs, recs)
    w = g.best(("t.Z000", "t.Z001"), zones=True)
    rec = next(r for r in recs if r["key"] == w["job"])
    snap = {"label": "s", "meta_sha12": "a" * 12, "at": "scene", "level": "levels/t", "tag": "t", "xemu": "x",
            "iso_sha12": "b" * 12}
    doc = verdict.witness("t", w, rec, jobs[w["job"]]["heading"], snap, "e" * 64, ("t.Z000", "t.Z001"))
    assert doc["claim"]["min_air"] == 1 and doc["ref"] == f"r2.16d/{doc['string']['sha12']}@{'a' * 12}"
    assert "replay" in proofs.record_problem(doc)
    assert proofs.record_problem(doc | {"replay": {"equal": True}}) is None


def _lift_router():
    """A ``rigs.Router`` over a lift (1) moving 0.1 m a row from x = 30, a gate (2) parked for an undecoded trigger
    and a door (3) parked with a read one; a kept frozen answer and its ``decide`` for a witness flying y -5..5 at
    ``x``, ``z``."""
    from types import SimpleNamespace

    from devkit.reach.engine import rigs
    cube = np.array([[[0, 0, 0], [1, 0, 0], [1, 1, 1]], [[0, 0, 0], [0, 1, 1], [1, 1, 1]]], float)
    lv = SimpleNamespace(owners={1: {"world": np.eye(4)}}, P=cube, tris_of=lambda oi: [0, 1])
    rows = np.tile(np.eye(4), (400, 1, 1))
    rows[:, 3, 0] = 30 - 0.1 * np.arange(400)
    verdicts = {1: {"name": "lift", "start": "load", "how": "cycles"},
                2: {"name": "gate", "start": "undecoded", "how": "parked"},
                3: {"name": "door", "start": "wired", "how": "parked"}}
    r = rigs.Router(lv, verdicts, {"poses": {1: rows.reshape(400, 16)}})
    got = {"land": [20.0, 5.0, 0.0], "state": 0, "settled": True, "same": True, "outcome": {"hp0": 200}}

    def decide(route=(), x=20.0, z=0.5, ticks=10, stays=True, swept=True):
        path = [(x, y, z) for y in np.linspace(-5, 5, 30)]
        return r.decide(got, {"rigs": list(route)}, ticks, stays, rigs.path_boxes(path) if swept else None,
                        (path[0], path[-1]))
    return got, decide


def test_the_router_trips_only_a_kept_witness_a_moving_rig_crosses_takes_out_undecoded_rigs_and_owes_the_wait(
        two_platforms):
    """Step R2.19h1's router (``rigs.Router``) on a witness's frozen hold answer: one the hold dropped stays as it is
    (no trip rescues it); one touching a rig parked for an undecoded trigger is out (not the same, its confirm's
    outcome gone, the rig named), one touching a read-trigger parked rig keeps its answer and names it; a lift moving
    0.1 m a row from x = 30 owes a trip to a witness it touches at its load pose and to one whose swept path its posed
    box crosses within the witness's window (the path swept first), never to one under which it passes 50 m lower or
    which it reaches only after a short window; and a trip that held after a 15-tick idle makes the witness's proof
    record idle those ticks before its R6, where a failed one drops the confirm's outcome."""
    from devkit.reach.engine import rigs
    got, decide = _lift_router()
    assert decide([1], stays=False) == ("as", got)
    how, out = decide([2])
    assert how == "out" and not out["same"] and "outcome" not in out and out["parked"] == ["gate"]
    assert decide([3], x=5.0) == ("as", got | {"parked": ["door"]})
    assert decide([1], x=5.0) == ("trip", ([1], [])) and decide(swept=False) == ("sweep", None)
    assert decide() == ("trip", ([1], [])) and decide(z=-50.0) == ("as", got)
    assert decide(x=5.0) == ("as", got) and decide(x=5.0, ticks=200) == ("trip", ([1], []))
    t = {"land": [20.0, 5.0, 0.0], "state": 0, "settled": True, "same": True, "wait": 15}
    held, failed = rigs.Router.tripped(got, t), rigs.Router.tripped(got, t | {"same": False})
    assert held["same"] and held["outcome"] and held["trip"] == t
    assert not failed["same"] and "outcome" not in failed
    nodes, jobs, recs = two_platforms
    nodes.zone_at = _zone
    w = graph.confirmed(graph.Graph(nodes, jobs, recs).best(("t.Z000", "t.Z001"), zones=True), held | {"outcome": None})
    rec = next(x for x in recs if x["key"] == w["job"])
    doc = verdict.witness("t", w, rec, jobs[w["job"]]["heading"], {"meta_sha12": "a" * 12}, "e" * 64, ("a", "b"))
    assert verdict._wid(w)["wait"] == 15 and doc["start"]["setup"][0] == ["idle", 15]
    assert doc["start"]["setup"][1][0] == "R6"


def test_a_trip_owing_witness_names_the_parked_rigs_it_touches_and_a_dropped_one_on_an_undecoded_rig_gives_no_touches():
    """Step R2.19h1's late review: a kept witness a moving lift owes a trip, whose path also touches a door parked
    for a read trigger, carries the door's name with its trip's answer, held or failed (PLAN-v2 §1.5d: the parked
    rigs it touches stay named for R2.16g's intake); and a witness its frozen hold dropped whose path touches a gate
    parked for an undecoded trigger is out (D847), its confirm's outcome gone (so its touches, MAY and node edge go
    too), the gate named."""
    from devkit.reach.engine import rigs
    got, decide = _lift_router()
    how, (owe, names) = decide([1, 3], x=5.0)
    assert (how, owe, names) == ("trip", [1], ["door"])
    t = {"land": [20.0, 5.0, 0.0], "state": 0, "settled": True, "same": True, "wait": 15}
    held, failed = rigs.Router.tripped(got, t, names), rigs.Router.tripped(got, t | {"same": False}, names)
    assert held["same"] and held["outcome"] and held["parked"] == ["door"]
    assert not failed["same"] and "outcome" not in failed and failed["parked"] == ["door"]
    how, out = decide([2], stays=False)
    assert how == "out" and not out["same"] and "outcome" not in out and out["parked"] == ["gate"]


def test_a_routed_witness_trip_runs_each_wait_on_a_scene_l3_that_never_ran(two_platforms):
    """Step R2.19h1's measure: a reset doesn't undo all of a long whole-step run (a toggled deck's poke stopped moving
    it after the recording on the same L3), so the router's whole-step trip (``rigs.replay_trip``) runs each try of
    its phase loop on a new L3 from ``make()``: one try where the witness lands as it did, all 8 where it can't."""
    from devkit.reach.engine import rigs

    class New(_Sim):
        def step(self, pad=l3.Pad(), writes=(), **_):
            return super().step(pad, writes)
    rec, o = next((r, o) for r in two_platforms[2] for o in r["outcomes"] if o["end"] == "settled")
    made = []

    def make():
        made.append(New([A, B, C]))
        return made[-1]
    for land, tries in ((o["land"], 1), ([99.0, 99.0, 99.0], rigs.PHASES)):
        made.clear()
        got = rigs.replay_trip(make, rec["starts"][o["start"]], rec["heading"], dict(o, land=land))
        assert (got["tries"], len(made), got["same"]) == (tries, tries, tries == 1)


def test_an_aim_lands_where_the_held_stick_flies_past_and_a_roll_jump_jumps_from_mid_air():
    """The launches on the stand-in: a rank-0 run jump pressed at the takeoff at a target on a ledge 3 m down and 4-7 m
    out lands on it by the predictive landing control (the stick eased or turned back as the closed-form landing
    says), where the stick held at the heading flies past it and dies, and one at a target past its reach walks on
    at it once down; a run jump presses where its run-up along the heading ends (a start 1 m off the line too), and
    one whose body leaves the floor first is ``walked off``; a swimmer that its idle hold leaves on a slope is
    ``unsettled``; an aimed job ends at its first launch from a start in its edge's from-zone that settles in its
    to-zone at its air rank and stays there 60 idle ticks on (its standing start never tried; a hit a slide carries
    out of its to-zone within those ticks is none, so the job runs on), and with no stop runs every macro, the
    first giving
    the same string, and from a start that settled in another zone (no hit) every macro three times (a probe-needed
    edge's once): as planned, walked at the target once down and steered 1.5 m short of it, and then its
    certificate's aims from 12 and 25 degrees either side, then from other points of its from-zone within 2.5 m that
    L3 stands on (found when its own takeoff is off the floor); an aimed job whose starts all fall stands on the
    ring 0.25 m around its first in its from-zone (with no stop, or in another zone, the start is dropped); one
    whose target lies past the ledge, where no body stands, aims at the nearest point of the 0.5 m grid where one
    stands in its to-zone with 3 of its 4 neighbours (and lands there), where steered at the target itself every
    launch misses; macros that differ only in their flaps run together give each the pads and rows it gives alone,
    their shared ticks stepped once; an aim's starts and target lie over floor faces (a start whose point falls off
    a 1 m strip moves onto it first, R0's raster start after it; a target off the ledge's face moves 0.5 m inside
    it, in its zone); a two-roll roll jump presses BLACK at the takeoff and on its first roll's chaining ticks,
    holds Y into the last roll's end and jumps from mid-air there (the fall's speed replaced by the jump's)."""
    from devkit.reach.engine import macros
    strip, ledge = (0, 0, 6, 1, 0.0), (8, 0, 11, 4, -3.0)
    sim, east, start = _Sim([strip[:3] + (4, 0.0), ledge]), -math.pi / 2, (2.5, 2.0, 0.0)

    def go(m, target=None, back=1.0):
        sim.reset()
        sim.teleport(start, east)
        for _ in range(5):
            sim.step(l3.Pad())
        return macros.launch(sim, m, east, east, start, back, target=target, ctl=aim.Aim)
    run = macros.Macro("runjump", "k0", 0, 0.0, 0.0)
    held, aimed = go(run), go(run, (9.5, 2.0, -3.0))
    assert held.end == "dead" and go(run, back=5.0).end == "walked off"
    flat = _Sim([(0, 0, 30, 4, 0.0)])                  # a target past the jump's reach on one floor: it walks on at it
    flat.teleport(start, east)
    short = macros.launch(flat, run, east, east, start, 1.0, target=(13.0, 2.0, 0.0),
                          ctl=functools.partial(aim.Aim, home=(13.0, 2.0, 0.0)))
    assert short.end == "settled" and short.rows[-1].pos[0] - short.rows[short.first].pos[0] > 0.5
    assert short.pads[-1].stick == (0.0, 0.0) and 13.0 - short.rows[-1].pos[0] <= aim.HOME_M   # walked all the way
    assert aimed.end == "settled" and 8 <= aimed.rows[-1].pos[0] <= 11 and aimed.rows[-1].pos[2] == pytest.approx(-2)
    job = {"key": "k", "id": "a0", "heading": east, "takeoff_feet": [5.0, 2.0, 0.0], "cells": [0],
           "starts": {"run": [[4.0, 3.0, 0.0]], "stand": []}, "macros": [list(run)]}
    took = runner.run_job(_Sim([strip[:3] + (4, 0.0), ledge]), job, here=0)["outcomes"][0]["took"]
    assert 5.0 <= took[0] < 5.0 + 7.0 / 30         # not 1.41 m on: the start's distance to the takeoff

    class _Swim:                            # off the floor 3 ticks, swimming, then on a slope (state 3) for good
        k = 0

        def step(self, pad=l3.Pad(), writes=()):
            self.k += 1
            st, pos = 2 if self.k <= 3 else 6 if self.k <= 30 else 3, (0.0, 0.0, 1.0)
            o = obs.Obs(pos, (0.0, 0.0, 0.0), st, 200, 200, 0, normal=(0.0, 0.6, 0.8) if st == 3 else (0.0, 0.0, 1.0),
                        anim=0, peak_z=None)
            return l3.Row(self.k, pos, st, 200, None, (), l3.camera_dir(0.0), frozenset(), o)
    drift = macros.launch(_Swim(), macros.Macro("walkoff", "k0"), east, east, start, 1.0)
    assert drift.end == "unsettled" and drift.rows[-1].state == 3
    aimjob = job | {"target": [9.5, 2.0, -3.0], "aim": [9.0, 2.0, -3.0],
                    "starts": {"run": [[4.0, 2.0, 0.0]], "stand": [[4.7, 2.0, 0.0]]},
                 "from": "t.S", "edge": "t.S>t.N:jump:modelled",
                 "macros": [list(run), list(macros.Macro("runjump", "k0", 0, 0.0, 0.0, hold=True)),
                            list(macros.Macro("standjump", "k0"))]}
    north = {"air": 0, "to": "t.N", "zoning": "z"}

    def zone(feet, swim=False, fallback=True):
        return "t.N" if feet[0] >= 7 else "t.S"
    every = runner.run_job(_Sim([strip[:3] + (4, 0.0), ledge]), aimjob | {"stop": None}, here=0, zone_at=zone)
    first = runner.run_job(_Sim([strip[:3] + (4, 0.0), ledge]), aimjob | {"stop": north}, here=0, zone_at=zone)
    elsewhere = runner.run_job(_Sim([strip[:3] + (4, 0.0), ledge]), aimjob | {"stop": north, "from": "t.W"}, here=0,
                               zone_at=zone)
    assert len(every["outcomes"]) == 3 and set(every["starts"]) == {"run", "stand"}
    assert len(first["outcomes"]) == 1 and set(first["starts"]) == {"run"}
    assert [o["string_sha12"] for o in elsewhere["outcomes"]][:3] == [o["string_sha12"] for o in every["outcomes"]]
    assert len(elsewhere["outcomes"]) == 9      # no hit: the same three again walked at the target, then steered short
    probe = aimjob | {"stop": north, "from": "t.W", "edge": "t.W>t.N:jump:probe-needed"}
    assert len(runner.run_job(_Sim([strip[:3] + (4, 0.0), ledge]), probe, here=0, zone_at=zone)["outcomes"]) == 3
    lands = [o["first"][0] for o in elsewhere["outcomes"] if o["macro"] == "standjump-k0-f0"]
    assert aim.short_of([9.5, 2, -3], [5, 2, 0]) == pytest.approx([8.0, 2, -3]) and lands[2] < lands[0] - 0.5
    turned = runner.run_job(_Sim([strip[:3] + (4, 0.0), ledge]), aimjob | {"stop": north, "from": "t.W",
                                                                        "cert": ["runjump", "k0", 0]}, here=0,
                            zone_at=zone)                # then the certificate's 4 aims at 12 and 25 deg either side
    assert len(turned["outcomes"]) == 9 + 4 * 4 and turned["starts"]["run@h-25"]["yaw"] == \
        pytest.approx(east - math.radians(25)) and "yaw" not in turned["starts"]["run"]
    off = aimjob | {"stop": north, "takeoff_feet": [6.8, 2.0, 0.0], "starts": {"run": [[6.8, 2.0, 0.0]], "stand": []},
                    "macros": [list(run)], "cert": ["runjump", "k0", 0]}      # its takeoff 0.8 m off the strip
    moved = runner.run_job(_Sim([strip[:3] + (4, 0.0), ledge]), off, here=0, zone_at=zone)
    assert moved["from_floor"]["stood"] and aim.hit(moved["outcomes"][-1], moved["starts"]["run@s0"], off, zone)
    o, st = first["outcomes"][0], first["starts"]["run"]
    assert aim.hit(o, st, aimjob | {"stop": north}, zone)
    assert not aim.hit(o, st, aimjob | {"stop": north | {"to": "t.S"}}, zone)
    assert not aim.hit(o, st, aimjob | {"stop": north, "from": "t.W"}, zone)
    assert first["outcomes"][0]["string_sha12"] == every["outcomes"][0]["string_sha12"]

    class _Carried(_Sim):                   # the ledge carries a standing body on at 2 m/s, off its far edge: a slide
        def step(self, pad=l3.Pad(), writes=()):
            f = self._s["feet"]
            if self._s["state"] == 0 and f[2] == -3.0:
                self._s["feet"] = (f[0] + 2.0 * DT, f[1], f[2])
            return super().step(pad, writes)
    carried = runner.run_job(_Carried([strip[:3] + (4, 0.0), ledge]), aimjob | {"stop": north}, here=0,
                             zone_at=zone)["outcomes"]
    assert aim.hit(carried[0], first["starts"]["run"], aimjob | {"stop": north}, zone) and carried[0]["hold"]["same"]
    assert {o["pass"] for o in carried} == {1, 2, 3, 5}
    assert not any(hold.stays(o["hold"], "t.N", zone) for o in carried if "hold" in o)
    brink = {"run": [[6.2, 2.0, 0.0]], "stand": []}                 # 0.2 m past the strip's edge: it falls
    ringed = runner.run_job(_Sim([strip[:3] + (4, 0.0), ledge]), aimjob | {"stop": north, "starts": brink}, here=0,
                            zone_at=zone)
    assert ringed["starts"]["run"]["ring"] and ringed["starts"]["run"]["feet"] == pytest.approx([5.95, 2.0, 0.0])
    assert ringed["outcomes"] and "cell" not in ringed["starts"]["stand"]
    far = {"target": [11.6, 2.0, -3.0], "aim": [11.6, 2.0, -3.0]}      # 0.6 m past the ledge's far edge
    snapped = runner.run_job(_Sim([strip[:3] + (4, 0.0), ledge]), aimjob | far | {"stop": north}, here=0, zone_at=zone)
    past = runner.run_job(_Sim([strip[:3] + (4, 0.0), ledge]), aimjob | far | {"stop": None}, here=0, zone_at=zone)
    assert snapped["floor"]["snap"] == pytest.approx([10.6, 2.0, -3.0]) and snapped["floor"]["m"] == 1.0
    assert aim.hit(snapped["outcomes"][-1], snapped["starts"]["run"], aimjob | {"stop": north}, zone)
    assert "floor" not in past and not any(o["end"] == "settled" and zone(o["land"]) == "t.N" for o in past["outcomes"])
    for other in ({"stop": None}, {"stop": north, "from": "t.N"}):
        assert "cell" not in runner.run_job(_Sim([strip[:3] + (4, 0.0), ledge]), aimjob | other | {"starts": brink},
                                            here=0, zone_at=zone)["starts"]["run"]
    fam, steps = [macros.Macro("runjump", "air3", f) for f in (0, 1, 2, 5)], [0]
    real = sim.step

    def counted(*a, **k):
        steps[0] += 1
        return real(*a, **k)
    sim.step = counted

    def at_start():
        sim.reset()
        sim.teleport(start, east)
        for _ in range(5):
            sim.step(l3.Pad())
        sim.step(writes=(("air", 3),))
        steps[0] = 0
    at_start()
    together, shared = macros.launches(sim, fam, east, east, start, 1.0), steps[0]
    alone = []
    for m in fam:
        at_start()
        alone.append((macros.launch(sim, m, east, east, start, 1.0), steps[0]))
    assert [(x.pads, [r.pos for r in x.rows], x.end, x.first) for x in together] == \
        [(x.pads, [r.pos for r in x.rows], x.end, x.first) for x, _ in alone]
    assert len({len(x.rows) for x in together}) > 1 and shared < sum(n for _, n in alone) - 20
    sim.step = real
    roll = go(macros.Macro("rolljump", "k0", 0, 0.0, 0.0, 2))
    black = [t for t, p in enumerate(roll.pads) if "black" in p.buttons]
    assert black[:3] == [5, 6, 7] and black[3:] == list(range(18, 23))
    rolled = [t for t, r in enumerate(roll.rows) if r.state == 0x100]
    jump = roll.rows[rolled[-1] + 1]
    assert len(rolled) > macros.ROLL_TICKS and "y" in roll.pads[rolled[-1]].buttons and jump.state == 2
    assert jump.obs.vel[2] == pytest.approx(math.sqrt(2 * G * 1.1)) and jump.pos[2] < 0.0
    nodes = Nodes(Reach(_level(_quad(*strip) + _quad(*ledge)), flights=False))
    nodes.zone_at = lambda feet, prefer_water=False, fallback=True: "t.N" if feet[0] >= 7 else "t.S"
    off = 0
    for t in nodes.takeoffs():
        if nodes.node_at(t.feet, 0) != nodes.node_at((3, 0.5, 0), 0):
            continue
        for d in (-0.7, 0.0, 0.7):
            h = t.heading + d
            f = nodes.starts(t, h, macros.BACK_RUN)[0]
            assert nodes.faces.floor_z(*f) is not None and nodes.region_at(f) == t.region
            off += nodes.faces.floor_z(t.feet[0] - math.sin(-h), t.feet[1] - math.cos(h), 0.0) is None
    assert off
    x, y, z = nodes.snap((7.6, 2.0, -3.0), "t.N")
    assert 8.5 <= x <= 10.5 and 0.5 <= y <= 3.5 and z == -3.0


def test_an_aims_last_pass_flies_its_certificates_flaps_on_the_envelope_schedule():
    """Step R2.16e: a flap is pressed on the first tick it can go at or past its scheduled tick after the takeoff
    (``env``: the envelope's schedule for the certificate), every one flown, not on the flap law's tick (which never
    flaps rising); an aimed job with ``env`` whose five passes all miss flies its certificate's unheld aims once more
    from its own starts so, after those passes' launches unchanged, and one without ``env`` stops at the fifth; the
    refinement is sampled on its record without that pass (so what the refinement runs doesn't hang on it)."""
    from devkit.reach.engine import macros
    east, strip, start = -math.pi / 2, (0, 0, 6, 4, 0.0), (4.0, 2.0, 0.0)
    sim = _Sim([strip])
    sim.teleport(start, east)
    for _ in range(5):
        sim.step(l3.Pad())
    sim.step(writes=(("air", 3),))
    got = macros.launch(sim, macros.Macro("runjump", "air3", 2, 0.0, 0.0), east, east, start, 1.0,
                        target=(30.0, 2.0, 0.0), ctl=functools.partial(aim.Sched, sched=(10, 25)))
    took = next(t for t, r in enumerate(got.rows) if r.state in macros.AIRBORNE)
    assert [t for t, p in enumerate(got.pads) if "y" in p.buttons and t >= took + macros.JUMP_HOLD] == \
        [took + 10, took + 25] and max(r.obs.flaps_used for r in got.rows) == 2
    job = {"key": "k", "id": "a0", "heading": east, "takeoff_feet": [5.0, 2.0, 0.0], "cells": [0],
           "starts": {"run": [[4.0, 2.0, 0.0]], "stand": []}, "target": [30.0, 2.0, 0.0], "aim": [30.0, 2.0, 0.0],
           "macros": [list(m) for m in aim.aims("runjump", "air3", 2)], "from": "t.S", "cert": ["runjump", "air3", 2],
           "edge": "t.S>t.N:jump:modelled", "stop": {"air": 3, "to": "t.N", "zoning": "z"}}

    def zone(feet, swim=False, fallback=True):
        return "t.N" if feet[0] >= 20 else "t.S"
    five = runner.run_job(_Sim([strip]), job, here=0, zone_at=zone)["outcomes"]
    six = runner.run_job(_Sim([strip]), job | {"env": [10, 25]}, here=0, zone_at=zone)["outcomes"]
    assert {o["pass"] for o in five} == {1, 2, 3, 4, 5} and six[:len(five)] == five
    assert [(o["macro"], o["pass"]) for o in six[len(five):]] == \
        [(m.name, 6) for m in aim.aims("runjump", "air3", 2) if not m.hold]
    assert aim.unscheduled({"key": "k", "outcomes": six}) == {"key": "k", "outcomes": five}
    from devkit.rando import physics
    env = physics.envelope()           # a sampled aim's ``env`` (``aim.aim_jobs``): one tick for each of the kit's flaps
    assert [len(env.schedule(r, 0.0)) for r in (2, 3)] == [env.kit(r, None).flaps for r in (2, 3)]


def test_a_probe_needed_aim_runs_every_pass_when_its_job_asks_for_more():
    """Step R2.19f+'s g1: an aimed job at a probe-needed edge runs pass 1 only, and with ``more``
    (``aim.retarget``'s) passes 2-6 as a modelled edge's does, pass 6 on its ``env``; ``more`` is part of its key."""
    east, strip = -math.pi / 2, (0, 0, 6, 4, 0.0)
    job = {"key": "k", "id": "a0", "heading": east, "takeoff_feet": [5.0, 2.0, 0.0], "cells": [0],
           "starts": {"run": [[4.0, 2.0, 0.0]], "stand": []}, "target": [30.0, 2.0, 0.0], "aim": [30.0, 2.0, 0.0],
           "macros": [list(m) for m in aim.aims("runjump", "air3", 2)], "from": "t.S", "cert": ["runjump", "air3", 2],
           "edge": "t.S>t.N:jump:probe-needed", "stop": {"air": 3, "to": "t.N", "zoning": "z"}, "env": [10, 25]}

    def zone(feet, swim=False, fallback=True):
        return "t.N" if feet[0] >= 20 else "t.S"
    one = runner.run_job(_Sim([strip]), job, here=0, zone_at=zone)["outcomes"]
    every = runner.run_job(_Sim([strip]), job | {"more": True}, here=0, zone_at=zone)["outcomes"]
    assert {o["pass"] for o in one} == {1} and {o["pass"] for o in every} == {1, 2, 3, 4, 5, 6}
    assert every[:len(one)] == one and aim.more(job | {"more": True}) and not aim.more(job)
    assert cache.job_key(job | {"more": True}, "0" * 12, "c" * 12) != cache.job_key(job, "0" * 12, "c" * 12)


def test_retarget_aims_rank_0_at_a_pair_held_only_above_it_and_at_a_hold_rejected_rank_and_leaves_a_far_probe_needed_miss(
        two_platforms, monkeypatch):
    """Step R2.19f+'s g1 (``aim.retarget``), a row a class: a truth-frame pair the graph holds only at rank 1 gets a
    rank-0 aim from its witness's takeoff at its landing, one held at rank 0 none; a zone rank the hold left with
    no witness (none under it) gets an aim in its kit at the to-zone, every pass, one with a lower rank held none; a
    probe-needed edge unfound at kit whose pass-1 landing came within 3 m of its to-zone gets its aims and twinned
    refinement, every pass, and one whose pass 1 landed 9 m off gets none."""
    nodes = two_platforms[0]
    za, zb, zc = (_zone(f) for f in ((0.0, 2.0, 0.0), (16.0, 2.0, 0.0), (2.0, 10.0, 10.0)))
    rec = {"key": "r", "starts": {"run": {"feet": [2.0, 2.0, 0.0], "settled": [2.0, 2.0, 0.0]}}, "outcomes": [
        {"start": "run", "took": [3.5, 2.0, 0.0], "land": [16.0, 2.0, 0.0], "pass": 1, "first": None},
        {"start": "run", "took": [3.5, 2.0, 0.0], "land": [2.0, 10.0, 10.0], "pass": 1, "first": None}]}
    near = dict(rec, key="n", outcomes=[dict(rec["outcomes"][0], land=[13.0, 2.0, 0.0])])
    far = dict(rec, key="f", outcomes=[dict(rec["outcomes"][0], land=[2.0, 2.0, 9.0])])
    w = {"job": "r", "outcome": 0}
    g = type("G", (), {"zones": {(za, zb): {1: w}, (zb, za): {0: w}, (za, zc): {1: w}},
                       "cands": {(zc, za): {0: [dict(w, outcome=1)]}, (za, zc): {2: [w]}}})()
    edges = {e: f"{za}>{zb}:jump:{c}" for e, c in (("n", "probe-needed"), ("f", "probe-needed"))}
    jobs = {"n": {"id": "a1", "edge": edges["n"], "macros": [[0]]},
            "f": {"id": "a2", "edge": f"{zb}>{za}:jump:probe-needed", "macros": [[0]]}}
    asked = []

    def aim_jobs(nodes_, derived, only=None, prefix="a", more_of=(), **kw):
        asked.append((prefix, sorted(only), sorted(more_of)))
        return [{"id": f"{prefix}{k}", "edge": e, "macros": [[0], [1]]} for k, e in enumerate(sorted(only))]
    monkeypatch.setattr(aim, "aim_jobs", aim_jobs)
    monkeypatch.setattr("azurkit.tools.randomizer.planner.proofs.zoning", lambda d: "z" * 12)
    verdicts = [{"from": za, "to": zb, "kind": "jump", "confidence": "probe-needed", "air": 0, "verdict": "MAY"},
                {"from": zb, "to": za, "kind": "jump", "confidence": "probe-needed", "air": 0, "verdict": "MAY"}]
    got = aim.retarget(nodes, {}, g, {"r": rec, "n": near, "f": far}, jobs, [(za, zb), (zb, za)], verdicts)
    rows = [(j["id"][:2], j.get("from"), j.get("stop", {}).get("to"), j.get("stop", {}).get("air"), j.get("more"))
            for j in got]
    assert rows == [("ga", za, zb, 0, None), ("gb", zc, za, 0, True), ("gc", None, None, None, None),
                    ("gd", None, None, None, None)]
    assert got[0]["cert"] == ["runjump", "k0", 0] and got[0]["takeoff_feet"] == [3.5, 2.0, 0.0]
    assert asked == [("gc", [edges["n"]], [edges["n"]]), ("gd", [edges["n"]], [edges["n"]])]
    assert got[3]["macros"] == [[1]] and got[3]["twin"]["starts"] == {"run": near["starts"]["run"]}


def test_a_refinement_job_repeats_nothing_its_aim_twin_ran():
    """Step R2.16e: a refinement job given its aim twin (the aims' job at the same edge, from the same starts at the
    same target) runs none of the twin's macros and no fourth pass (the twin's own), takes the twin's floor and start
    answers in place of searching again, and its every other outcome is the one it gives alone; a twin that
    disagrees on its starts is no twin."""
    east, strip = -math.pi / 2, (0, 0, 6, 4, 0.0)
    job = {"key": "k", "id": "a0", "heading": east, "takeoff_feet": [5.0, 2.0, 0.0], "cells": [0],
           "starts": {"run": [[6.4, 2.0, 0.0], [4.0, 2.0, 0.0]], "stand": [[4.7, 2.0, 0.0]]},
           "target": [30.0, 2.0, 0.0], "aim": [30.0, 2.0, 0.0], "from": "t.S", "cert": ["runjump", "air3", 2],
           "macros": [list(m) for m in aim.aims("runjump", "air3", 2)],
           "edge": "t.S>t.N:jump:modelled", "stop": {"air": 3, "to": "t.N", "zoning": "z"}}

    def zone(feet, swim=False, fallback=True):
        return "t.N" if feet[0] >= 20 else "t.S"

    class _Placed(_Sim):
        n = 0

        def teleport(self, *a, **k):
            self.n += 1
            return super().teleport(*a, **k)
    twin = runner.run_job(_Sim([strip]), job, here=0, zone_at=zone)
    ref = job | {"id": "r0", "macros": [list(m) for m in aim.refine("runjump", "air3", 2)]}
    got = aim.twinned(ref, job, twin)
    assert got["macros"] == [m for m in ref["macros"] if m != list(aim.aims("runjump", "air3", 2)[0])] != ref["macros"]
    assert aim.twinned(ref, job | {"starts": {"run": [[4.0, 2.0, 0.0]], "stand": []}}, twin) is ref
    sims = [_Placed([strip]), _Placed([strip])]
    alone, paired = (runner.run_job(sim, j, here=0, zone_at=zone) for sim, j in zip(sims, (ref, got)))
    flown = {aim.Macro(*m).name for m in job["macros"]}
    assert paired["outcomes"] == [o for o in alone["outcomes"] if o["pass"] != 4 and o["macro"] not in flown]
    assert paired["floor"] == twin["floor"] | {"placements": 0} and twin["floor"]["placements"] > 1
    assert (paired["starts"]["run"]["tries"], twin["starts"]["run"]["tries"]) == (1, 2)
    assert sims[1].n < sims[0].n - twin["floor"]["placements"]


def test_the_fast_cuts_give_an_aimed_jobs_record_with_a_landing_at_rest_on_ice_settled_and_refuse_a_moved_copy(
        monkeypatch, tmp_path):
    """Step R2.19a (its review's D1): the pool's cuts (``reach_engine.fast``: a later pass resumed at each launch's
    first touch-down, a hit held from its launch's end) give ``aim.run_job``'s record on the stand-in, a hit's and
    one with no hit, which runs on through pass 4, also where the landing is ice (Step R1.39b: a body at rest there
    reads the slide state, settled by ``obs.settled`` in the hit's launch and its hold, AZ-737); so do Step R2.19l's
    driver cuts (a launch's touches found once; placement answers kept, a start try whose kept answer falls not
    placed again), cold, warm, from the answers another worker stored and with every kept answer and launch done
    again, and a kept answer that placing again gives otherwise stops the run (``fast.Drift``); and the code they
    copy is pinned (``fast.SHADOWS``): an edit to one fails here and stops the install that copies it until fast.py
    is edited beside it and the new hash pinned (a tick cut's ``fast.install`` alone, so ``--l3 base`` still runs; a
    driver cut's every pool's ``worker.setup``)."""
    from devkit.reach.engine import macros
    assert fast.stale() == [], "edit reach_engine/fast.py beside these (its cuts copy them), then pin their hashes"

    class _Ice(_Sim):                       # the ledge (x >= 8) is flat ice: a body on it reads the slide state
        def step(self, pad=l3.Pad(), writes=()):
            r = super().step(pad, writes)
            return r._replace(state=3, obs=r.obs._replace(state=3)) if r.state == 0 and r.pos[0] >= 8 else r
    floors, east = [(0, 0, 6, 4, 0.0), (8, 0, 11, 4, -3.0)], -math.pi / 2
    run = macros.Macro("runjump", "k0", 0, 0.0, 0.0)
    job = {"key": "k", "id": "a0", "heading": east, "takeoff_feet": [5.0, 2.0, 0.0], "cells": [0],
           "starts": {"run": [[4.0, 9.0, 0.0], [4.0, 2.0, 0.0]], "stand": [[4.7, 2.0, 0.0]]},
           "target": [9.5, 2.0, -3.0], "aim": [9.0, 2.0, -3.0], "from": "t.S", "edge": "t.S>t.N:jump:modelled",
           "cert": ["runjump", "k0", 0], "stop": {"air": 0, "to": "t.N", "zoning": "z"},
           "macros": [list(run), list(run._replace(hold=True)), list(macros.Macro("standjump", "k0"))]}
    box = [[[8.5, 0, z], [10.5, 0, z], [10.5, 4, z]] for z in (-3.5, 0.0)] + \
          [[[8.5, 0, z], [10.5, 4, z], [8.5, 4, z]] for z in (-3.5, 0.0)]      # a volume over the ledge's middle
    touch = runner.Touch({"V": [box], "ids": [7], "picks": [[3, [6.0, 2.0, 1.5]], [4, [0.0, 30.0, 0.0]]]})

    def zone(feet, swim=False, fallback=True):
        return "t.N" if feet[0] >= 7 else "t.S"
    jobs = [(s, j) for s in (_Sim, _Ice) for j in (job, job | {"from": "t.W"})]
    plain = [runner.run_job(s(floors), j, touch, here=0, zone_at=zone) for s, j in jobs]
    assert [o["volumes"] for o in plain[0]["outcomes"]][0] == [7] and plain[0]["outcomes"][0]["picks"] == [3]
    assert plain[0]["starts"]["run"]["tries"] == 2
    for mod, name in ((aim, "run_macros"), (aim, "run_job"), (hold, "replay"), (runner, "run_job"), *_DRIVER):
        monkeypatch.setattr(mod, name, getattr(mod, name))
    monkeypatch.setattr(cache, "folder", lambda level: tmp_path / level)
    monkeypatch.setattr(worker, "IMPL", {"l3": "fast", "code": "c"})      # a pool worker's: its answers stored
    was = dict(fast.STATS) | fast.DRIVER
    fast.install()
    fast.install_driver(on=(_Sim,))
    sims = {s: s(floors) for s in (_Sim, _Ice)}                 # one a class: the second run of a job warm
    for s in sims.values():
        s.snap = l3.Snapshot({}, [], {"level": f"levels/t/{type(s).__name__}"})
    assert [runner.run_job(sims[s], j, touch, here=0, zone_at=zone) for s, j in jobs * 2] == plain * 2
    assert all(fast.STATS[k] > was[k] for k in ("resumed", "held_from_end"))
    assert all(fast.DRIVER[k] > was[k] for k in ("kept", "skipped", "spanned", "near_picks"))
    assert fast.DRIVER["spanned"] < fast.DRIVER["points"]
    other, was = _Sim(floors), dict(fast.DRIVER)                # another worker: the answers the first stored
    other.snap = sims[_Sim].snap
    assert runner.run_job(other, job, touch, here=0, zone_at=zone) == plain[0]
    store = other.__dict__["_store"]["dir"]                     # its files, listed sizes and own: what it could read
    assert fast.DRIVER["read"] > was["read"] and fast.DRIVER["skipped"] > was["skipped"], (
        [(e.name, e.stat().st_size, os.stat(e.path).st_size) for e in os.scandir(store)] if store else store)
    monkeypatch.setattr(fast, "AUDIT_EVERY", 1)                 # every kept answer and launch done again: the same
    assert [runner.run_job(sims[s], j, touch, here=0, zone_at=zone) for s, j in jobs] == plain
    assert {o["pass"] for o in plain[1]["outcomes"]} == {1, 2, 3, 4} and "hold" in plain[0]["outcomes"][0]
    ice = plain[2]["outcomes"][-1]
    assert (ice["end"], ice["land_state"], ice["hold"]["state"], ice["hold"]["settled"]) == ("settled", 3, 3, True)
    sims[_Sim].floors = [(0, 0, 6, 12, 0.0), *floors[1:]]       # the floor under the falling start grown: it stands
    with pytest.raises(fast.Drift, match="kept answer"):
        runner.run_job(sims[_Sim], job, touch, here=0, zone_at=zone)
    monkeypatch.setitem(fast.SHADOWS, "hold.replay", "0" * 12)      # a tick cut's copy: --l3 base still runs
    with pytest.raises(RuntimeError, match="hold.replay.*--l3 base"):
        fast.install()
    worker.setup()
    monkeypatch.setitem(fast.SHADOWS, "runner.place", "0" * 12)     # a driver cut's: every pool stops
    for setup in (fast.install_driver, worker.setup):
        with pytest.raises(RuntimeError, match="runner.place") as e:
            setup()
        assert "--l3 base" not in str(e.value)


class _Lots:
    """Hand-made graph nodes: a node every 10 m of x, a zone every 20 m; y is the zone's floor gap."""
    frozen: dict = {}

    def node_at(self, f, state):
        return f"n{int(f[0] // 10)}"

    def zone_at(self, f, prefer_water=False, fallback=True):
        return f"Z{int(f[0] // 20)}"

    def zone_gap(self, f, swim=False):
        return f[1]

    def floor_near(self, p, zone):
        return p[0] < 100


def _out(sha, ticks, land, state=0, took=None, taint=(), **kw):
    """A hand-made settled outcome at rank 0 from start ``run``."""
    return {"macro": "m", "kit": "k0", "flaps": 0, "end": "settled", "ticks": ticks, "land": land,
            "land_state": state, "first": None, "first_state": None, "took": took, "hp0": 200, "hp_min": 200,
            "labels": [], "volumes": [], "picks": [], "taint": list(taint), "string_sha12": sha, "start": "run"} | kw


def test_a_worker_reads_the_placements_another_stores_while_its_file_is_open_whatever_size_the_folder_lists(
        tmp_path, monkeypatch):
    """Step 4.37j: a pool worker reads the placement answers another worker stored (``fast._read``) by each store
    file's own size, never the folder listing's: Windows' listing gives the size a file had when it was last closed,
    so a file the other worker still has open listed as empty and nothing was read (the fast cuts' test failed there:
    ``DRIVER["read"]`` stayed 0). Stood in here: a listing whose every size is 0."""
    import types

    monkeypatch.setattr(cache, "folder", lambda level: tmp_path / level)
    monkeypatch.setattr(worker, "IMPL", {"l3": "fast", "code": "c"})
    one, two = (types.SimpleNamespace(snap=l3.Snapshot({}, [], {"level": "levels/t/x"})) for _ in range(2))
    at, got = fast._at(one, (4.0, 2.0, 0.0), 0.5, 3), ((4.0, 2.0, 0.25), 0, True)
    fast._keep(one, at, got, True)                    # stored: its worker keeps the file open for its life
    listed = os.scandir

    def windows_listing(path):
        return [types.SimpleNamespace(name=e.name, path=e.path, stat=lambda: os.stat_result((0,) * 10))
                for e in listed(path)]
    try:
        monkeypatch.setattr(fast.os, "scandir", windows_listing)
        was = fast.DRIVER["read"]
        fast._read(two)
        monkeypatch.undo()
        assert (two.__dict__.get("_placed"), fast.DRIVER["read"] - was) == ({at: got}, 1)
    finally:
        os.close(one._store["fd"])


def test_a_zone_pair_keeps_its_best_witness_and_its_zone_mapping_flags():
    """The graph on hand-made records: a start that settled on another node of the job's from-zone is kept (its
    edges run from where it stood); a zone pair keeps its best witness a rank (untainted first, then fewest ticks);
    a landing whose zone is named by a floor sample over half a metre off is ``zone_far``, a launch that took off in
    another zone than its start's ``takeoff_zone``, one that ends swimming ``swim``; and an unfound derived edge
    whose aims' starts all fell is a ``takeoff`` fault (N/A, but attempted), one whose aim lands where the engine's
    face list holds no floor near stays MAY with that ``landing`` fault as a flag, as does one where L3 stood no
    body in its to-zone near its target while a launch lands in that zone, but where none does it is the derive's
    phantom landing (N/A, out of the graded recall), as a takeoff fault whose from-zone L3 stands no body near is
    its phantom takeoff; a found one or one no aim ran for has none; the refinement
    takes the MAY, the faults and a find above its kit, not a find at its kit; and the hold keeps a pair's best
    witness a rank whose body stays in its to-zone (asking for the best's answer first, then the next one's), past
    its 3 best an aim's hit held as it was found, and drops a pair none of whose witnesses stays."""
    Lots, o = _Lots, _out
    outs = [o("s1", 50, [25, 0.2, 0]), o("s2", 40, [26, 0.9, 0]), o("s5", 30, [27, 0, 0], taint=["x"]),
            o("s3", 60, [45, 0, 0], took=[21, 0, 0]), o("w1", 50, [65, 0, 0], 6)]
    recs = [{"key": f"j{k}", "id": f"a{k}", "starts": {"run": {"settled": [12, 0, 0]}}, "outcomes": [x]}
            for k, x in enumerate(outs)]
    g = graph.Graph(Lots(), {f"j{k}": {"key": f"j{k}", "takeoff_feet": [1, 0, 0], "from": "Z0"} for k in range(5)},
                    recs)
    assert g.counts["starts kept by their zone, off the takeoff's node"] == 5 and ("n1", "n2") in g.edges
    assert [(w["string_sha12"], w["flags"]) for w in g.witnesses(("Z0", "Z1"))] == [("s2", ["zone_far"])]
    assert g.best(("Z0", "Z2"), zones=True)["flags"] == ["takeoff_zone"]
    assert g.best(("Z0", "Z3"), zones=True)["swim"]
    got, then = set(), {"s2": [45, 0, 0], "s1": [25, 0.2, 0], "s3": [45, 0, 0], "w1": [65, 0, 0]}   # s2 slid on to Z2

    def answer(w):
        x = w["string_sha12"]
        return {"land": then[x], "state": 2 if x == "w1" else 0, "same": True} if x in got else None
    assert {w["string_sha12"] for w in g.hold(answer)} == {"s2", "s3", "w1"}
    got |= {"s2", "s3", "w1"}
    assert [w["string_sha12"] for w in g.hold(answer)] == ["s1"] and g.best(("Z0", "Z1"), zones=True)["id"] == "a1"
    got.add("s1")
    assert g.hold(answer) == [] and g.best(("Z0", "Z1"), zones=True)["string_sha12"] == "s1"
    assert ("Z0", "Z2") in g.zones and ("Z0", "Z3") not in g.zones
    stay = {"land": [106, 0, 0], "state": 0, "same": True}     # an aim's hit held as found: its job stopped there
    four = [o(f"q{k}", 10 + k, [105, 0, 0]) for k in range(3)] + [o("q9", 90, [106, 0, 0]) | {"hold": stay}]
    g4 = graph.Graph(Lots(), {f"k{k}": {"key": f"k{k}", "takeoff_feet": [1, 0, 0], "from": "Z0"} for k in range(4)},
                     [{"key": f"k{k}", "id": f"q{k}", "starts": recs[0]["starts"], "outcomes": [x]}
                      for k, x in enumerate(four)])
    left = {"land": [125, 0, 0], "state": 0, "same": True}    # the three quicker ones slide on into Z6
    assert g4.hold(lambda w: stay if w["string_sha12"] == "q9" else left) == []
    assert g4.best(("Z0", "Z5"), zones=True)["string_sha12"] == "q9"
    run = recs[0]["starts"]
    aimed = {"a7": ("Z4", [85, 0, 0], run, 84), "a8": ("Z5", [105, 0, 0], run, 75),       # a8 falls short, off
             "a9": ("Z6", [65, 0, 0], {"run": {"tries": 3}}, None),                     # every start of a9 fell
             "a10": ("Z8", [165, 0, 0], run, 165),                                     # found with a flap
             "a11": ("Z9", [185, 0, 0], run, 25), "a12": ("Z1", [35, 0, 0], run, 75)}  # L3 stood none near
    jobs = {k: {"key": k, "takeoff_feet": [1, 0, 0], "from": "Z0", "edge": f"Z0>{z}:jump:modelled", "aim": p}
            for k, (z, p, _, _) in aimed.items()}
    recs = [{"key": k, "id": k, "starts": st, "outcomes": [o(k, 50, [x, 0, 0])] if x else []}
            for k, (_, _, st, x) in aimed.items()]
    recs[3]["outcomes"][0] |= {"kit": "air3", "flaps": 1}
    for r in recs[4:]:
        r["floor"] = {"to": False, "placements": 81}
    recs[2]["from_floor"] = {"stood": 0}                            # and a9's from-zone stands no body near
    derived = {"edges": [{"from": "Z0", "to": f"Z{z}", "kind": "jump", "confidence": "modelled", "requires": "true"}
                         for z in (4, 5, 6, 7, 8, 9)]}
    derived["edges"].append(derived["edges"][0] | {"to": "Z1"})
    g = graph.Graph(Lots(), jobs, recs)
    rows = verdict.zone_edges(derived, g)
    got = [(x["to"], x["verdict"], x.get("fault"), x.get("derive")) for x in rows]
    assert got == [("Z4", verdict.FOUND, None, None), ("Z5", verdict.MAY, "landing", None),
                   ("Z6", verdict.NA, "takeoff", "no L3 floor at its takeoff"), ("Z7", verdict.MAY, None, None),
                   ("Z8", verdict.FOUND, None, None), ("Z9", verdict.NA, "landing", "no L3 floor at its landing"),
                   ("Z1", verdict.FOUND, None, None)]
    assert set(aim.refined(rows)) == {f"Z0>Z{z}:jump:modelled" for z in (5, 6, 7, 8, 9)}
    rep = verdict.report("t", derived, {}, {}, g)["modelled"]
    assert (rep["attempted"], rep["recall_attempted"], rep["floor_faults"]) == \
        (7, round(2 / 7, 4), {"landing": 2, "takeoff": 1})
    assert rep["graded"] == {"edges": 5, "recall": round(2 / 5, 4),
                             "out": {"no L3 floor at its landing": 1, "no L3 floor at its takeoff": 1}}


def test_an_aim_hit_whose_hold_left_takes_no_try_and_a_kernel_confirm_gives_its_touches_may_and_node_edge():
    """Step R2.19k's graph fixes: an aim's hit whose own hold left its to-zone takes none of a zone pair's
    ``TRIES`` (three such quicker hits no longer push out the fan witness that stays), though its to-zone still
    counts as landed in (``verdict``'s phantom-landing guard), and each FastL3 confirm the hold reads, staying or not,
    gives the touches, MAY candidate and node edge of FastL3's run of the string, which the kernel candidate itself
    gives none of.  Step R2.19f+: a witness repeating a kept try's string (a refinement's twin) takes no try either
    (a5's twins pushed out the aim that stayed), and a retarget's witnesses take tries of their own (g1's quicker
    re-aims that left pushed out e7's witness that stays); Step R2.19g2: so do the pair stage's (its quicker aims
    that left pushed out three of a5's); Step R2.19g3: and an escalation's, tried after every other, so one that stays
    never ends the hold before a kernel confirm (g3's measure: e7 lost 27 MAY edges so)."""
    left = {"land": [125, 0, 0], "state": 0, "same": True}                  # slid on into Z6
    stay = {"land": [106, 0, 0], "state": 0, "same": True}
    outs = [_out(f"h{k}", 10 + k, [105, 0, 0], hold=left) for k in range(graph.TRIES)]   # quicker than the fan's
    outs += [_out("fan", 50, [106, 0, 0]), _out("k1", 40, [106, 0, 0], by="kernel"),
             _out("k2", 40, [145, 0, 0], by="kernel"),                      # k1 to Z5, k2 to Z7
             _out("h9", 9, [165, 0, 0], hold=left)]                         # the only launch to land in Z8
    outs += [_out("d", 30, [106, 0, 0]), _out("d", 30, [106, 0, 0])]       # one string twice: one try, not two
    run = {"run": {"settled": [12, 0, 0]}}
    g = graph.Graph(_Lots(), {f"j{k}": {"key": f"j{k}", "takeoff_feet": [1, 0, 0], "from": "Z0"}
                              for k in range(len(outs))},
                    [{"key": f"j{k}", "id": f"a{k}", "starts": run, "outcomes": [x]} for k, x in enumerate(outs)])
    assert g.counts["aim hits whose hold left, taking no try"] == graph.TRIES + 1
    assert [w["string_sha12"] for w in g.cands[("Z0", "Z5")][0]] == ["d", "k1", "fan"]
    assert g.counts["zone witnesses repeating a kept try's string, taking no try"] == 1
    assert g.cands[("Z0", "Z8")] == {0: []}                                 # no try, but it landed in Z8
    assert not g.touch and not g.may and set(g.edges) == {("n1", "n10"), ("n1", "n16")}
    l3s = {"k1": _out("k1'", 41, [106, 0, 0], volumes=["v1"], picks=["p1"], first=[35, 0, 0], first_state=0),
           "k2": _out("k2'", 44, [125, 0, 0], volumes=["v2"])}             # FastL3's k2 slid on to Z6: no stay
    conf = {"k1": stay | {"outcome": l3s["k1"]}, "k2": left | {"same": False, "outcome": l3s["k2"]}, "d": left}
    assert g.hold(lambda w: conf.get(w["string_sha12"], stay)) == []
    assert g.best(("Z0", "Z5"), zones=True)["string_sha12"] == "k1'" and ("Z0", "Z7") not in g.zones
    quick = outs + [_out(f"{c}{k}", 20 + n, [106, 0, 0])                 # g1's quicker re-aims to Z5, then the
                    for n, (c, k) in enumerate((c, k) for c in "gpe" for k in range(graph.TRIES))]  # pair stage's, g3's
    ids = ["gb", "p", "ea"]
    g2 = graph.Graph(_Lots(), {f"j{k}": {"key": f"j{k}", "takeoff_feet": [1, 0, 0], "from": "Z0"}
                               for k in range(len(quick))},
                     [{"key": f"j{k}", "starts": run, "outcomes": [x],
                       "id": f"a{k}" if k < len(outs) else f"{ids[(k - len(outs)) // graph.TRIES]}{k}"}
                      for k, x in enumerate(quick)])
    assert [w["string_sha12"] for w in g2.cands[("Z0", "Z5")][0]] == ["g0", "g1", "g2", "p0", "p1", "p2", "e0", "e1",
                                                                         "e2", "d", "k1", "fan"]
    assert g2.hold(lambda w: stay if w["id"][0] == "e" else left if w["id"][0] in "gp"     # g3's would stay too
                   else conf.get(w["string_sha12"], stay)) == []
    assert g2.best(("Z0", "Z5"), zones=True)["string_sha12"] == "k1'"
    assert g2.touch == g.touch and g2.may == g.may        # k1's confirm was read, as with no witness of g3's
    assert g.touch == {("n1", "vol:v1"): 0, ("n1", "pick:p1"): 0, ("n1", "vol:v2"): 0}
    assert g.may == {("n1", "n3"): 0}
    assert set(g.edges) == {("n1", "n10"), ("n1", "n16"), ("n1", "n12")}
    assert g.edges[("n1", "n12")][0]["by"] == "confirmed"


def _triggers(iso, level):
    """A level's geometry and its :class:`triggers.Triggers` over the derive's wiring, as ``rig_triggers.py`` reads it."""
    from devkit.rando.draft.export import derive_inputs
    from azurkit.tools.randomizer.draft.geometry import Level
    from azurkit.tools.randomizer.draft.wiring import Wiring
    from azurkit.tools.randomizer.planner.loader import load_database

    db = load_database()
    lv = Level.read(iso, level)
    return lv, triggers.Triggers(lv, Wiring(lv, db.generated.get(level, {}),
                                            derive_inputs(level, db.tricks, db.levels.get(level, {}), db.generated)["level"]))


def test_a_rigs_start_is_read_from_its_wiring_and_poked_at_its_own_pad(usa_iso):
    """Step R2.19h2 (D847): a rig's trigger comes from its level's wiring.  a5's Top2 deck starts when Top1 is
    touched, poked at Top1's touch (the R2.17 platforms prototype's L3 toggle dropped both); its Chain_Bob decks
    move from load; e7's mine elevator ramp, whose switch toggles while locked through an xor the wiring can't read,
    starts at its GoTriggerField's touch (``rig_triggers.py witness`` moved it in L3: the player spawns standing in
    it, so the pad must change); d1's elevator, whose goal the elevator's own height feeds back into, is parked by
    name."""
    def starts(level, *names):
        lv, T = _triggers(usa_iso, level)
        g = lv.graphs[0]
        pad = lambda a: f"{a.split(':')[0]}:{g.names[int(a.split(':')[2])]}"     # noqa: E731
        out = {}
        for n in names:
            oi = next(oi for oi in lv.by_name[n] if oi in T.rigs())
            st = T.rig(oi)
            out[n] = (st.kind, sorted(sorted(pad(a) for a in t) for t in st.on) if st.kind == "wired" else None,
                      [(p.plug, g.names[p.R], p.of) for p in T.pokes(oi)] if st.kind == "wired" else None)
        return out

    assert starts("a5", "Top2Shape", "Chain_Bob:Chain_bobShape") == {
        "Top2Shape": ("wired", [["touch:Top1Shape"]], [("touch", "Top1Shape", "condition")]),
        "Chain_Bob:Chain_bobShape": ("load", None, None)}
    assert starts("e7", "rampShape")["rampShape"][1:] == ([["touch:GoTriggerFieldShape"]],
                                                         [("touch", "GoTriggerFieldShape", "condition")])
    assert starts("d1", "ElevatorShape")["ElevatorShape"][0] == "undecoded"


def test_an_exported_rig_is_the_owner_its_movers_name_not_the_first_of_its_name(usa_iso):
    """Step R2.19h2's review: the derive exports e6's nShape2 deck twice, the mirrors Mirror_Timer7 and
    Mirror_Timer11 move; a third twin, Mirror_Timer10's, joins no zones, so isn't exported, though it comes before
    Timer11's in owner order (picking by name order witnessed it, and 17 more wrong owners on e6 and 5 other
    levels)."""
    from devkit.rando.draft.author import read_derived

    lv, T = _triggers(usa_iso, "e6")
    ex = T.exported(read_derived("e6")["rigs"])
    assert sorted(lv.mover_of(oi)[0] for oi in ex if lv.owners[oi]["name"] == "nShape2") == [
        ["Mirror_Timer11"], ["Mirror_Timer7"]]
    assert len(ex) == len(read_derived("e6")["rigs"]) == 13


def test_the_truth_frame_reaches_a_rise_up_to_the_kits_rise_plus_1m_at_its_highest_travel():
    """Step R2.19c1's review: the truth frame (``reach_engine.candidates`` since Step R2.19g2) holds a pair rising up
    to the kit's rise + 1 m at the travel of the envelope's highest level with one; air3 has none at its rise itself,
    which the table stored as 0, so no pair rising past 2.37 m was in an air3 stratum."""
    T = candidates
    for rank in (0, 3):
        g, t, top = table = T._table(rank)
        r = T._reach(np.array([g[-1], top, top + T.RISE_PLUS_M, top + T.RISE_PLUS_M + 0.01]), table)
        assert t[-1] > 0 and np.all(r[:3] == T.WIDEN * t[-1]) and r[3] == -np.inf, rank


def test_the_pair_stage_aims_at_each_frame_pair_the_graph_lacks_at_its_kit_k0_first_and_names_what_its_budget_leaves():
    """Step R2.19g2: ``candidates.queue`` takes each nd frame pair with no zone witness at its kit's rank or under (a
    rank-1 witness leaves the k0 pair, not the air3 one; a dm pair is the base's), groups them at most 32 targets of
    one from-zone, kit and tier in the frame's order, and orders the groups by tier, nd-k0 first (PLAN-v3's order,
    though here near's expected links a CPU-second, the tier's pass-1 share in R's rows of pairs the graph lacks at
    their kit, are k0's x 1.6; a row the graph holds at its kit is dropped, one it holds only at a higher rank kept),
    then by the frame's order (a 1-target group first); each group's expected links (the far tier's: those rows' nd
    R-real share x 0.4) and a budget's rest by tier are named.  Its aims fly pass 1 alone (``aim.MORE``)."""
    C = candidates

    def z(n):
        return f"e2.Z{n:03d}"
    strata = {"nd-k0": [[z(0), z(n), -5.0] for n in range(1, 41)],
              "nd-air3": [[z(0), z(2), -30.0], [z(9), z(10), -21.0], [z(5), z(6), -25.0], [z(5), z(7), -30.0],
                          [z(5), z(8), -3.0]],
              "dm-k0": [[z(0), z(50), -9.0]]}
    zones = {(z(0), z(1)): {0: {}}, (z(0), z(2)): {1: {}}}

    def row(stratum, slack, by=None, held=None):
        r = {"stratum": stratum, "from": z(0), "to": z(len(rows) + 100), "slack": slack, "na": None, "by": by,
             "real": by is not None}
        if held is not None:
            zones[(r["from"], r["to"])] = {held: {}}
        return r
    rows: list[dict] = []
    for k in range(20):
        rows.append(row("nd-k0", -5.0, "aim pass 1" if k < 2 else None, held=1 if k == 0 else None))
    for k in range(20):
        rows.append(row("nd-air3", -30.0, "aim pass 1" if k < 4 else "refine pass 1" if k < 6 else None))
    for k in range(5):
        rows.append(row("nd-air3", -3.0))
    for stratum, rank in [("nd-k0", 0)] * 5 + [("nd-air3", 1)]:
        rows.append(row(stratum, -30.0, "aim pass 1", held=rank))
    rates = C.rates(rows, zones)
    assert {t: v["rate"] for t, v in rates.items()} == {"nd-k0": 0.1, "nd-air3-near": 0.2,
                                                        "nd-air3-far": 8 / 45 * C.LEVEL_SHARE}
    rate, cost = {t: v["rate"] for t, v in rates.items()}, C.COST_S["kernel"]

    def shape(groups):
        return [(g["from"], g["kit"], g["tier"], [t[1] for t in g["targets"]]) for g in groups]
    every, none = C.queue(strata, zones, rate, cost)
    assert none == [] and shape(every) == [
        (z(0), "k0", "nd-k0", [z(n) for n in range(2, 34)]), (z(0), "k0", "nd-k0", [z(n) for n in range(34, 41)]),
        (z(9), "air3", "nd-air3-near", [z(10)]), (z(5), "air3", "nd-air3-near", [z(6), z(7)]),
        (z(5), "air3", "nd-air3-far", [z(8)])]
    taken, left = C.queue(strata, zones, rate, cost, budget_s=11.0)
    assert shape(taken) == shape(every)[:3] and shape(left) == shape(every)[3:]
    assert C.tally(left) == {"nd-air3-near": {"pairs": 2, "groups": 1, "expected_links": 0.4, "cpu_h": 0.0},
                             "nd-air3-far": {"pairs": 1, "groups": 1, "expected_links": 0.1, "cpu_h": 0.0}}
    assert C.EDGE.rsplit(":", 1)[-1] not in aim.MORE


def test_a_pair_whose_pass_1_came_within_the_tier_escalates_and_a_farther_one_waits():
    """Step R2.19g3: ``candidates.escalate`` gives each pair stage aim (ids ``p...``) whose pair the graph lacks at its
    kit and whose pass-1 landing or first touch-down came within the tier of its to-zone's landing-side points (its
    record's) the same aim with every pass, k0 first, then nearest; once that aim has a record (its pair still
    lacking), the refinement twinned to the pass-1 aim.  A farther pair, or one with no pass-1 landing, waits, and a
    wider tier takes the farther one; a pair held at its kit (rank 3 holds the air3 pair, not the k0 one), another
    stage's aim and an unrun one are neither."""
    C = candidates

    def z(n):
        return f"e7.Z{n:03d}"
    dst = {"x": np.array([10.0, 12.0, 50.0, 80.0]), "y": np.zeros(4), "z": np.zeros(4), "zone": np.array([2, 2, 3, 4])}

    def job(jid, to, kit):
        flaps = C.KITS[kit] and aim.FLAPS_OF_RANK[3]
        return {"id": jid, "from": z(1), "stop": {"air": C.KITS[kit], "to": z(to), "zoning": "z"},
                "cert": ["runjump", kit, flaps], "edge": f"{z(1)}>{z(to)}:{C.EDGE}", "takeoff_feet": [0.0, 0.0, 0.0],
                "heading": 0.0, "cells": [0], "starts": {"run": [[0.0, 0.0, 0.0]], "stand": []},
                "target": [10.0, 0.0, 0.0], "aim": [10.0, 0.0, 0.0], "target_cells": [0], "group": 0,
                "backend": "kernel", "macros": [list(m) for m in aim.aims("runjump", kit, flaps)]}

    def rec(land, first=None):
        return {"starts": {"run": {"feet": [0.0, 0.0, 0.0], "cell": 0}}, "floor": {"to": True, "placements": 3},
                "outcomes": [{"pass": 1, "land": land, "first": first}]}
    jobs = {"k0": job("p0", 2, "air3"), "k1": job("p1", 2, "k0"), "k2": job("p2", 3, "air3"), "k3": job("p3", 3, "k0"),
            "k4": job("p4", 4, "k0"), "k5": job("a5", 4, "air3"), "k6": job("p6", 4, "air3")}
    recs = {"k0": rec([10.5, 0.0, 0.0]), "k1": rec([30.0, 0.0, 0.0], [10.0, 1.5, 0.0]), "k2": rec([50.2, 0.0, 0.0]),
            "k3": rec([54.0, 0.0, 0.0]), "k4": rec(None), "k5": rec([80.0, 0.0, 0.0])}
    zones = {(z(1), z(2)): {3: {}}}

    def shape(got):
        return [(j["id"], j["cert"][1], j["stop"]["to"], j["near_m"], j["more"]) for j in got[0]], got[1]
    assert shape(C.escalate(jobs, recs, dst, zones, 2.0)) == (
        [("ea0", "k0", z(2), 1.5, True), ("ea1", "air3", z(3), 0.2, True)],
        [[z(1), z(3), "k0", 4.0], [z(1), z(4), "k0", None]])
    wide = C.escalate(jobs, recs, dst, zones, 5.0)
    assert shape(wide) == ([("ea0", "k0", z(2), 1.5, True), ("ea1", "k0", z(3), 4.0, True),
                            ("ea2", "air3", z(3), 0.2, True)], [[z(1), z(4), "k0", None]])
    assert not {"key", "backend", "group"} & {k for j in wide[0] for k in j}
    got, wait = C.escalate(jobs | {"e0": wide[0][0]}, recs | {"e0": rec([30.0, 0.0, 0.0])}, dst, zones, 2.0, ("k0",))
    flown = jobs["k1"]["macros"]
    assert [(j["id"], j["more"], j["near_m"]) for j in got] == [("er0", True, 1.5)] and len(wait) == 2
    assert got[0]["macros"] == [list(m) for m in aim.refine("runjump", "k0", 0) if list(m) not in flown]
    assert got[0]["twin"] == {"starts": {"run": recs["k1"]["starts"]["run"]}, "floor": {"to": True}}


def test_the_truth_sets_slack_bands_take_their_own_pairs_and_pooled_recall_weighs_each_band_by_its_frame(monkeypatch,
                                                                                                         tmp_path):
    """Steps R2.19c3 and R2.19c2b: ``devkit/reach/reach_truth.py`` splits ``nd-air3`` into its slack bands (near: 20 m or
    more inside the envelope).  ``run --strata nd-air3-near --skip 1 --take 2`` takes the band's 2nd and 3rd pairs at
    their places in nd-air3's order, still stratum ``nd-air3``.  ``recall`` pools by inverse-probability weights
    (frame pairs / sampled) per band: a 10-pair census with 8 R-real links the engine all found, 10 of 400 near pairs
    with 2 R-real it found 1 of, 5 of 600 far pairs with none, pool to (8 + 40) / (8 + 80), on Wilson's interval at
    the Kish number 88^2 / 3,208; a pair frozen under two names counts once, real when either's R held it (a re-fly's
    find too)."""
    from devkit.reach import reach_truth as T

    monkeypatch.setattr(T, "_folder", lambda level: tmp_path)
    air = [["e2.Z000", f"e2.Z{n:03d}", -30.0 if n % 5 < 2 else -5.0] for n in range(1000)]   # near at 0, 1, 5, 6 ...
    frame = {"strata": {"dm-k0": [["e2.Z000", "e2.Z900", None]] * 10, "nd-air3": air}}
    T._frame_path("e2", "z" * 12, 219).write_bytes(gzip.compress(json.dumps(frame).encode()))
    take = argparse.Namespace(strata=["nd-air3-near"], skip=1, take=2, like=None, pairs=None)
    assert T._want(take, frame, []) == [("nd-air3", 1, air[1]), ("nd-air3", 5, air[5])]

    def row(stratum, n, real, slack=None, **kw):
        return {"stratum": stratum, "from": "e2.Z000", "to": f"e2.Z{n:03d}", "kit": stratum.split("-")[1],
                "slack": slack, "na": None, "real": real, "frame_zoning": "z" * 12, "frame": 219, **kw}
    near = [n for n in range(1000) if n % 5 < 2][:10]
    rows = ([row("dm-k0", 900 + n, n < 8) for n in range(10)] + [row("nd-air3", n, n == 0, -30.0) for n in near]
            + [row("nd-air3", n, False, -5.0) for n in (2, 3, 4, 7, 8)])
    (tmp_path / "a.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (tmp_path / "b.jsonl").write_text(json.dumps(row("nd-air3", 1, False, -30.0, refly_real=True)) + "\n",
                                      encoding="utf-8")
    edges = [{"from": "e2.Z000", "to": f"e2.Z{n:03d}", "ranks": ["0"]} for n in (*range(900, 908), 0)]
    (tmp_path / "g.json").write_text(json.dumps({"zone_edges": edges}), encoding="utf-8")
    got = T.recall(argparse.Namespace(level="e2", name=["a", "b"], graph=str(tmp_path / "g.json")))
    kish = 88 ** 2 / 3208
    assert {s: (d["pairs"], d["r_real"], d["engine_found_r_real"]) for s, d in got["strata"].items()} == {
        "dm-k0": (10, 8, 8), "nd-air3-near": (10, 2, 1), "nd-air3-far": (5, 0, 0)}
    assert got["pooled"] == {"r_real": 10, "engine_found_r_real": 9, "kish_n_real": round(kish, 1),
                             "recall_vs_r": round(48 / 88, 4), "ci95": T._wilson(48 / 88 * kish, kish)}


def test_the_truth_sets_kernel_candidate_the_graphs_hold_confirmed_stays_on_the_kernel_side(monkeypatch):
    """Step R2.19c2a's review: ``Graph.hold`` renames a kernel candidate FastL3 confirmed (``graph.confirmed``: ``by``
    "confirmed"), and ``devkit/reach/reach_truth.py``'s candidate count still puts it on the kernel side, beside a failed
    kernel candidate (the re-fly's) and an L3 one."""
    from devkit.reach import reach_truth as T

    o = {"string_sha12": "s", "ticks": 9, "taint": 0, "flaps": 0, "hp0": 1, "hp_min": 1, "labels": [], "kit": "k0"}
    held = graph.confirmed({"job": "a", "outcome": 0, "by": "kernel"}, {"outcome": o})
    cands = [held, {"job": "b", "outcome": 0, "by": "kernel"}, {"job": "c", "outcome": 0, "by": "l3"}]
    monkeypatch.setattr(T.hold, "answer", lambda base, rec, k: {"v": {"b": "dead"}.get(rec["key"], "held")})
    monkeypatch.setattr(T, "_verdict", lambda got, to, rank, zone_at: got["v"])
    g = argparse.Namespace(cands={("e2.Z000", "e2.Z001"): {0: cands}})
    got = T._kfacts(g, ("e2.Z000", "e2.Z001"), 0, [{"key": k, "outcomes": [{}]} for k in "abc"], Path(), None)
    assert held["by"] == "confirmed"
    assert got == {"cands": {"kernel": 2, "l3": 1}, "answers": {"kernel": {"held": 1, "dead": 1}, "l3": {"held": 1}},
                   "failed": [["b", 0]]}


def test_the_truth_sets_refly_flies_again_a_failed_kernel_candidate_the_c_controllers_launched(two_platforms,
                                                                                                monkeypatch):
    """Step R2.19c2b's check: ``devkit/reach/reach_truth.py``'s ``refly_task`` runs a kernel job again until each failed
    candidate's launch comes round, then flies it once more on L3 (here the stand-in).  With the launch families in C
    (``backend.c_launches``, R2.19p's default) each one still comes round and the stand-in's flight from A to B holds
    (the bulk's 2,876 targets had all come back ``unmatched``), and the backend's launch routes are its own after."""
    from devkit.reach import reach_truth as T

    from devkit.reach import native as N
    from devkit.reach.native import backend as KB
    nodes, jobs, recs = two_platforms
    stand = _Sim([A, B, C])
    row0 = stand.teleport((0.0, 2.0, 0.0), 0.0)
    b = KB.Base(row0, [stand.step() for _ in range(runner.SETTLE_START)][-1])
    world = N.World(_quads(A, B, C), np.full(6, 0x8050, np.int32))
    monkeypatch.setattr(KB, "CONTROLLERS", "c")
    monkeypatch.setattr(runner, "run_macros", KB.run_macros)
    job = next(jobs[r["key"]] for r in recs if any(o["end"] == "settled" and _zone(o["land"]) == "t.Z001"
                                                     and _zone(r["starts"][o["start"]]["settled"]) == "t.Z000"
                                                     for o in r["outcomes"]))
    rec = runner.run_job(KB.KernelSim(stand, world, b), job, here=0)
    want = [[k, "t.Z001", T.KITS[o["kit"]]] for k, o in enumerate(rec["outcomes"])
            if o["by"] == "kernel" and o["end"] == "settled" and _zone(o["land"]) == "t.Z001"]
    monkeypatch.setattr(cache, "get", lambda base, key: rec)
    monkeypatch.setattr(runner, "_zones", lambda w, path: _zone)
    routes = KB.launches, KB.c_launches, hold.replay
    got = T.refly_task(argparse.Namespace(sim=lambda *a, **k: KB.KernelSim(stand, world, b), _reach_here=0), job,
                       want, "base", None, "zones")
    assert want and len(got["got"]) == len(want) and "unmatched" not in {v["class"] for v in got["got"].values()}
    assert "held" in {v["class"] for v in got["got"].values()} and (KB.launches, KB.c_launches, hold.replay) == routes


def test_the_truth_sets_chapman_share_is_of_r_real_links_not_of_the_first_capture(monkeypatch, tmp_path):
    """Step R2.19c2a's review: B4 reads the links both R and the engine miss as a share of nd R-real.  Of 10 sampled
    pairs (a 100-pair stratum), R holds 4 real and the engine one more (first capture 5), the generator 4 with 3 of
    them in the first: Chapman (6 x 5 / 4 - 1) 6.5, so 1.5 missed, 0.375 of R's 4 real links (not 0.3 of 5)."""
    from devkit.reach import reach_truth as T

    monkeypatch.setattr(T, "_folder", lambda level: tmp_path)
    T._frame_path("e2", "z" * 12, 219).write_bytes(gzip.compress(json.dumps({"strata": {"nd-k0": [0] * 100}}).encode()))

    def rows(name, real):
        (tmp_path / f"{name}.jsonl").write_text("".join(json.dumps(
            {"stratum": "nd-k0", "from": "e2.Z000", "to": f"e2.Z{n:03d}", "kit": "k0", "na": None, "real": n in real,
             "frame_zoning": "z" * 12, "frame": 219}) + "\n" for n in range(10)), encoding="utf-8")
    rows("r", {0, 1, 2, 3})
    rows("gen", {0, 1, 4, 5})
    (tmp_path / "g.json").write_text(json.dumps({"zone_edges": [{"from": "e2.Z000", "to": "e2.Z004", "ranks": ["0"]}]}),
                                     encoding="utf-8")
    got = T.chapman(argparse.Namespace(level="e2", r=["r"], gen="gen", graph=str(tmp_path / "g.json")))
    h = 1.96 * math.sqrt(100 * 6 * 5 * 2 * 1 / (16 * 5))
    assert got["strata"]["nd-k0"]["share_of_r_real"] == 0.375
    assert got["pooled"] == {"first_est": 50, "r_real_est": 40, "missed_est": 15, "share": 0.375,
                             "ci95": [round((15 - h) / 40, 4), round((15 + h) / 40, 4)]}


def test_the_native_kernel_walks_jumps_and_lands_by_the_games_measured_laws_on_a_flat_floor():
    """Step R2.17's native kernel (``devkit.reach.native``, zig-built) on a 40 m flat floor: from rest a full
    stick reaches 3.27, 6.53 then 7.0 m/s (the move's friction, mu 10 x g dt; xemu s6 measured 3.26691, 6.53610,
    7.00009), Y's edge leaves at sqrt(2 g 1.1) = 4.6433 m/s, and the body comes back down onto the floor walking."""
    from devkit.reach import native as N
    P = np.array([[[-20, -20, 0], [20, -20, 0], [20, 20, 0]], [[-20, -20, 0], [20, 20, 0], [-20, 20, 0]]], float)
    world = N.World(P, np.full(2, 0x8050, np.int32))
    p = N.player((0.0, 0.0, 1.0 + 1e-3), (0.0, 0.0, 0.0), 0, (0.0, 0.0, 1.0))
    run = l3.Pad((0.0, 1.0), frozenset(), None, (0.0, 1.0))
    rows = world.run(p, [l3.Pad(cam=(0.0, 1.0))] * 5 + [run] * 4)
    assert [round(math.hypot(*r[3:5]), 2) for r in rows[5:8]] == [3.27, 6.53, 7.0]
    rows = world.run(p, [l3.Pad((0.0, 1.0), frozenset({"y"}), None, (0.0, 1.0))] + [run] * 40)
    assert rows[0][6] == 2 and rows[0][5] == pytest.approx(4.6433, abs=1e-3)
    assert rows[-1][6] == 0 and rows[-1][2] == pytest.approx(1.0, abs=0.01)


def test_a_posed_mover_blocks_an_arc_at_its_tick_and_not_at_another():
    """Step R2.19h1's movers in the kernel (``World.movers``): a wall whose pose table puts it across a 10 m path at
    row 0 and 45 m off at row 1 stops the body's sweep (the mover's own contact) at clock 0, at the face 0.5 m short
    of it, and lets it through at clock 1; a cycling table wraps (clock 2 is row 0 again); and a body standing on a
    deck that rises 0.1 m a row rides it up, tick by tick."""
    from devkit.reach import native as N
    wall = np.array([[[0, -5, -5], [0, -5, 5], [0, 5, 5]], [[0, -5, -5], [0, 5, 5], [0, 5, -5]]], float)
    at = [np.eye(4) for _ in range(2)]
    at[0][3, :3], at[1][3, :3] = (5.0, 0.0, 0.0), (50.0, 0.0, 0.0)
    world = N.World(np.zeros((0, 3, 3)), np.zeros(0, np.int32))
    world.movers([wall], [np.full(2, 0x8050)], [np.array(at)], [True])
    hits = []
    for tick in (0, 1, 2):
        world.clock(tick)
        c = world.sweep((0.0, 0.0, 1.0), (10.0, 0.0, 1.0))
        hits.append(None if c is None else (c.src, round(c.t * 10.0, 3)))
    assert hits == [(0, 4.5), None, (0, 4.5)]
    deck = _quads((-2, -2, 2, 2, 0))
    rise = [np.eye(4) for _ in range(20)]
    for k, m in enumerate(rise):
        m[3, 2] = 0.1 * k
    world.movers([deck], [np.full(len(deck), 0x8050)], [np.array(rise)], [False])
    p = N.player((0.0, 0.0, 1.0 + 1e-3), (0.0, 0.0, 0.0), 0, (0.0, 0.0, 1.0))
    rows = world.run(p, [l3.Pad(cam=(0.0, 1.0))] * 12)
    assert p.tick == 12 and p.on == 0
    assert rows[-1][2] == pytest.approx(1.0 + 0.1 * 12, abs=0.02) and rows[-1][6] == 0


def _box(x0, y0, z0, x1, y1, z1) -> np.ndarray:
    """A closed box wound inward, as the game's volume meshes are: a ray up from inside meets its top facing down."""
    top = _quads((x0, y0, x1, y1, z1))[:, ::-1]
    sides = [((x0, y0, z0), (x0, y0, z1), (x1, y0, z1)), ((x0, y0, z0), (x1, y0, z1), (x1, y0, z0)),
             ((x0, y1, z0), (x1, y1, z1), (x0, y1, z1)), ((x0, y1, z0), (x1, y1, z0), (x1, y1, z1)),
             ((x0, y0, z0), (x0, y1, z1), (x0, y0, z1)), ((x0, y0, z0), (x0, y1, z0), (x0, y1, z1)),
             ((x1, y0, z0), (x1, y0, z1), (x1, y1, z1)), ((x1, y0, z0), (x1, y1, z1), (x1, y1, z0))]
    return np.concatenate([_quads((x0, y0, x1, y1, z0)), top, np.array(sides, float)])


def test_the_kernels_volume_and_spring_laws_keep_the_games_measured_constants():
    """Step R2.19e's kernel ports (``kernel.c``'s header) on a 40 m floor, each row a law and its measured constant:
    airborne in an updraft (pushZ 10) vz' = vz + 0.035404 (pushZ / 0.9 - vz) with no gravity [xemu calib §3]; a full
    stick 10 m under a water surface swims at 9.000 m/s after 1 s and BLACK dives at -4.5 [xemu s6]; an autoSpring
    pad of S 24 launches at 21.68870735 m/s [xemu, placed]; a horizontal push leaves a walk's 3.27/6.53/7.0 ramp as it
    is (pushes act in the air and the water only); a volume that moves or switches stops the run (STOP_PUSH); a
    world queries only its own volumes, never another world's; in two overlapping water volumes the depth is the
    deeper one's, the later one's too (0x60DCB); an autoSpring rig (a mover) launches at its own S, as a static pad
    does (R2.19e's late review); the plain air (no push) rounds its blend as R2.19d did, not as 0x89613."""
    from devkit.reach import native as N
    floor = _quads((-20, -20, 20, 20, 0.0))
    run, idle = l3.Pad((0.0, 1.0), frozenset(), None, (0.0, 1.0)), l3.Pad(cam=(0.0, 1.0))
    dive = l3.Pad((0.0, 0.0), frozenset({"black"}), None, (0.0, 1.0))

    def kernel(vol=None, word=0xC028, push=(0.0, 0.0, 0.0), stop=0, spring=None):
        w = N.World(floor, np.full(len(floor), 0x8050 | (4 * (spring is not None)), np.int32),
                    spring=None if spring is None else np.full(len(floor), spring))
        f = N.Fields([] if vol is None else [{"P": vol, "word": word, "push": push, "stop": stop}])
        w.fields(f)
        return w, f

    def updraft(rows, p0):
        vz = [0.0] + [r[5] for r in rows]
        return all(b == pytest.approx(a + 0.035404 * (10 / 0.9 - a), abs=1e-4) for a, b in zip(vz, vz[1:]))
    cases = [   # law, kernel, start (pos, state), pads, check
        ("updraft", kernel(_box(-5, -5, 2, 5, 5, 30), push=(0.0, 0.0, 10.0)), ((0.0, 0.0, 10.0), 2), [idle] * 10,
         updraft),
        ("swim", kernel(_box(-10, -10, -20, 10, 10, 0), 0xC120), ((0.0, 0.0, -10.0), 2), [run] * 30,
         lambda rows, p: rows[-1][6] == 6 and math.hypot(*rows[-1][3:5]) == pytest.approx(9.0, abs=1e-3)),
        ("dive", kernel(_box(-10, -10, -20, 10, 10, 0), 0xC120), ((0.0, 0.0, -10.0), 6), [dive] * 30,
         lambda rows, p: rows[-1][5] == pytest.approx(-4.5, abs=1e-3)),
        ("spring", kernel(spring=24.0), ((0.0, 0.0, 1.0 + 1e-3), 0), [idle] * 3,
         lambda rows, p: rows[1][6] == 2 and rows[1][5] == pytest.approx(21.68870735, abs=1e-4)),
        ("walk in a push", kernel(_box(-5, -5, 0, 5, 5, 3), push=(5.0, 0.0, 0.0)), ((0.0, 0.0, 1.0 + 1e-3), 0),
         [idle] * 5 + [run] * 4,
         lambda rows, p: [round(math.hypot(*r[3:5]), 2) for r in rows[5:8]] == [3.27, 6.53, 7.0]),
        ("switched", kernel(_box(-5, -5, 2, 5, 5, 30), push=(0.0, 0.0, 10.0), stop=N.STOP_PUSH),
         ((0.0, 0.0, 10.0), 2), [idle] * 10, lambda rows, p: len(rows) == 1 and int(rows[0][9]) % 16 == N.STOP_PUSH),
    ]
    for law, (world, keep), (pos, state), pads, check in cases:
        world.fields(keep)
        p = N.player(pos, (0.0, 0.0, 0.0), state, (0.0, 0.0, 1.0))
        assert check(world.run(p, pads), p), law
    bare = N.World(floor, np.full(len(floor), 0x8050, np.int32))     # no volumes of its own, the others' alive
    assert len(bare.run(N.player((0.0, 0.0, 10.0), (0.0, 0.0, 0.0), 2, (0.0, 0.0, 1.0)), [idle] * 10)) == 10
    rig = N.World(np.zeros((0, 3, 3)), np.zeros(0, np.int32))      # an autoSpring rig of S 24: S's launch, not the kit's
    rig.movers([_quads((-2, -2, 2, 2, 0.0))], [np.full(2, 0x8054)], [np.eye(4)[None]], [False], [24.0])
    rows = rig.run(N.player((0.0, 0.0, 1.0 + 1e-3), (0.0, 0.0, 0.0), 0, (0.0, 0.0, 1.0)), [idle] * 3)
    assert rows[1][6] == 2 and rows[1][5] == pytest.approx(21.68870735, abs=1e-4)

    def f32(x):
        return float(np.float32(x))
    side = l3.Pad((0.6, 0.8), frozenset(), None, (0.0, 1.0))         # the plain air keeps R2.19d's rounding (R2.19e's
    sx, sy = f32(0.6), f32(0.8)                                       # revert: a5's t4018h2 settles in 65 ticks, as
    ac = 9.0 * math.sqrt(sx * sx + sy * sy)                           # FastL3's and main's, not the blend's 66)
    tx, kb = f32(ac * f32(-math.sin(math.atan2(-0.0, 1.0) + math.atan2(-sx, sy)))), 0.6 ** DT
    vx = next(v for v in (f32(1.0 + k * 1e-6) for k in range(10_000))
              if f32(tx + (v - tx) * kb) != f32(f32((v - tx) * kb) + tx))
    rows = bare.run(N.player((0.0, 0.0, 10.0), (vx, 0.0, 0.0), 2, (0.0, 0.0, 1.0)), [side])
    assert rows[0][3] == f32(tx + (vx - tx) * kb)
    pools = [{"P": _box(-10, -10, -20, 10, 10, z), "word": 0xC120, "push": (0.0, 0.0, 0.0), "stop": 0} for z in (0, 3)]
    assert N.Fields(pools).at((0.0, 0.0, -10.0))[3] == pytest.approx(13.0)


def test_an_updrafts_contact_lands_nothing_and_keeps_the_stored_normal_as_the_classifier_0x85920_does():
    """Step R2.19f+'s NS.K (the classifier 0x85920 read against the kernel): a body falling onto a floor inside an
    updraft (pushZ > 0) touches it and stays airborne, its stored normal the last one (0x85AA7 skips the store);
    the same fall outside the updraft lands (on this slippery floor, state 3) with the floor's normal; 0x85A34's
    (0, 0, 1) is the dead stop's,
    which the kernel already ports."""
    from devkit.reach import native as N
    floor = _quads((-20, -20, 20, 20, 0.0))
    idle = l3.Pad(cam=(0.0, 1.0))
    got = []
    for push in (10.0, None):
        w = N.World(floor, np.full(len(floor), 0x8051, np.int32))   # slippery: the slide keeps it moving
        vols = [] if push is None else [{"P": _box(-5, -5, -1, 5, 5, 30), "word": 0xC028, "push": (0.0, 0.0, push),
                                         "stop": 0}]
        f = N.Fields(vols)
        w.fields(f)
        p = N.player((0.0, 0.0, 1.02), (3.0, 0.0, -2.0), 2, (0.6, 0.0, 0.8))
        rows = w.run(p, [idle])
        got.append((int(rows[0][6]), int(rows[0][8]) > 0, tuple(round(x, 3) for x in p.normal)))
    assert got == [(2, True, (0.6, 0.0, 0.8)), (3, True, (0.0, 0.0, 1.0))]


def test_the_kernels_lip_lift_mounts_a_ledge_in_its_window_and_plays_its_clip_in_place_and_not_one_above_it():
    """Step R2.19f+'s f (FastL3's clip as the e7 probe measured it): a body falling against a wall whose ledge is
    0.7-1.5 m over its feet is put on the ledge 1.236 m ahead that tick, still, in state 0x100 for anim 66's 37 rows,
    then walks there on the very next tick (FastL3 runs the walk on the tick after a clip's last row: a jump there at a
    step-up's end, a5 job a502); a ledge 2.6 m over its feet (above the 2.301 m window) lifts nothing and the body
    falls on."""
    from devkit.reach import native as N
    push = l3.Pad((0.0, 1.0), frozenset(), None, (1.0, 0.0))           # the stick along +x
    got = []
    for top in (1.0, 2.6):
        wall = np.array([[[0.6, -5, -10], [0.6, 5, top], [0.6, 5, -10]], [[0.6, -5, -10], [0.6, -5, top],
                                                                           [0.6, 5, top]]], float)
        P = np.concatenate([wall, _quads((0.6, -5, 5, 5, top), (-20, -20, 20, 20, -10.0))])
        w = N.World(P, np.full(len(P), 0x8050, np.int32))
        p = N.player((0.05, 0.0, 1.0), (3.0, 0.0, 0.0), 2, (0.0, 0.0, 1.0))
        p.state_t = 1.0
        rows = w.run(p, [push] * 40)
        got.append(rows)
    lift, fall = got
    assert lift[0][6] == 0x100 and lift[0][0] == pytest.approx(0.05 + 1.236, abs=1e-3)
    assert lift[0][2] == pytest.approx(2.0, abs=0.01) and [int(r[6]) for r in lift[:38]].count(0x100) == 37
    assert lift[37][6] == 0 and lift[37][0] > lift[36][0] + 0.05 and lift[39][2] == pytest.approx(2.0, abs=0.01)
    assert all(r[6] == 2 for r in fall[:5]) and fall[-1][2] < 0.0


def test_the_kernel_hands_a_step_up_to_fastl3_and_walks_on_against_a_wall_too_high_to_step():
    """Step R2.19f+'s f, the step-up reverted: the kernel decides 0x8B1D0's step-up but doesn't play it (where the game
    puts the body on the step isn't the decision's point: 0.16-0.19 m across on a5's and f2's FastL3 step-ups), so a
    walk into a 0.3 m step stops its run with the step-up's code (4) for FastL3, and a 0.6 m wall stops nothing."""
    from devkit.reach import native as N
    push = l3.Pad((0.0, 1.0), frozenset(), None, (1.0, 0.0))           # the stick along +x
    got = []
    for s in (0.3, 0.6):
        wall = np.array([[[2.0, -5, 0], [2.0, 5, s], [2.0, 5, 0]], [[2.0, -5, 0], [2.0, -5, s], [2.0, 5, s]]], float)
        P = np.concatenate([wall, _quads((-20, -20, 2.0, 20, 0.0), (2.0, -20, 20, 20, s))])
        w = N.World(P, np.full(len(P), 0x8050, np.int32))
        rows = w.run(N.player((0.0, 0.0, 1.0 + 1e-3), (0.0, 0.0, 0.0), 0, (0.0, 0.0, 1.0)), [push] * 40)
        got.append((len(rows) < 40, int(rows[-1][9]) % 16, int(rows[-1][6])))
    assert got == [(True, 4, 0), (False, 0, 0)]


def _quads(*floors) -> np.ndarray:
    """Axis-aligned floors ((x0, y0, x1, y1, z) each) as upward triangles, two a floor."""
    return np.array([t for x0, y0, x1, y1, z in floors
                     for t in (((x0, y0, z), (x1, y0, z), (x1, y1, z)), ((x0, y0, z), (x1, y1, z), (x0, y1, z)))],
                    float)


def test_a_launch_the_kernel_flags_runs_on_l3_and_a_kernel_find_counts_once_l3_confirms_it_with_its_fields(
        two_platforms, monkeypatch):
    """Step R2.19d's kernel route (``reach_native.backend``) on the two platforms, the kernel's world their floors
    and L3 the stand-in, here one that takes 10 HP at each Y press and taints its runs: a roll jump stops the kernel at
    its BLACK press, so its launch is the stand-in's (``by`` "l3"); every other launch is a kernel candidate (``by``
    "kernel": no HP lost, no label, touch or node edge in the graph), and a zone witness counts only once its confirm,
    the stand-in's run of its string and hold, stays, the witness then carrying the stand-in's HP, taint and labels."""
    from devkit.reach import native as N
    from devkit.reach.engine.macros import Macro
    from devkit.reach.native import backend as KB

    class Hurt(_Sim):
        def step(self, pad=l3.Pad(), writes=()):
            row = super().step(pad, writes)
            self._s["hurt"] = self._s.get("hurt", 0) + 10 * ("y" in pad.buttons and "lt" not in pad.buttons)
            hp = row.hp - self._s["hurt"] if row.hp else 0
            return row._replace(hp=hp, obs=row.obs._replace(hp=hp))

    nodes, jobs, recs = two_platforms
    stand = Hurt([A, B, C])
    row0 = stand.teleport((0.0, 2.0, 0.0), 0.0)
    b = KB.Base(row0, [stand.step() for _ in range(runner.SETTLE_START)][-1])
    ks = KB.KernelSim(stand, N.World(_quads(A, B, C), np.full(6, 0x8050, np.int32)), b)
    monkeypatch.setattr(runner, "run_macros", KB.run_macros)
    job = next(jobs[r["key"]] for r in recs if any(o["end"] == "settled" and _zone(o["land"]) == "t.Z001"
                                                     and _zone(r["starts"][o["start"]]["settled"]) == "t.Z000"
                                                     for o in r["outcomes"]))   # one the stand-in finds A to B with
    job = dict(job, macros=job["macros"] + [list(Macro("rolljump", "k0"))])
    rec = runner.run_job(ks, job, here=0)
    by = collections.Counter((o["macro"].split("-")[0], o["by"]) for o in rec["outcomes"])
    assert by[("rolljump", "l3")] == 1 and sum(n for (m, b_), n in by.items() if b_ == "kernel") == len(job["macros"]) - 1
    assert all(o["hp0"] == o["hp_min"] and not o["labels"] for o in rec["outcomes"] if o["by"] == "kernel")
    g = graph.Graph(nodes, {job["key"]: job}, [rec])
    assert g.counts["kernel candidates"] and all(w["by"] == "l3" for e in g.edges.values() for w in e.values())
    stand.taint = {"render"}
    answers = {}
    while want := g.hold(lambda w: answers.get((w["job"], w["outcome"]))):
        for w in want:
            o = rec["outcomes"][w["outcome"]]
            answers[w["job"], w["outcome"]] = KB.replay(stand, rec["starts"][o["start"]], rec["heading"], dict(o))
    kept = [w for ranks in g.zones.values() for w in ranks.values()]
    assert kept and all(w["by"] in ("l3", "confirmed") for w in kept)
    w = next(w for w in kept if w["by"] == "confirmed")
    got = answers[w["job"], w["outcome"]]["outcome"]
    assert (w["taint"], w["hp_lost"], w["labels"]) == (["render"], got["hp0"] - got["hp_min"], got["labels"])
    assert w["hp_lost"] > 0 == rec["outcomes"][w["outcome"]]["hp0"] - rec["outcomes"][w["outcome"]]["hp_min"]


def test_the_kernel_routes_checks_are_l3s_a_start_only_the_kernel_stands_a_floor_and_a_step_stopped_for_time(
        two_platforms, monkeypatch):
    """Step R2.19d's review: on the kernel route (``reach_native.backend.install`` in a ``worker.setup`` worker, the
    kernel's world the three platforms, L3 a stand-in without C) a kernel candidate from a start on C, which only the
    kernel stands, confirms as a ``start`` fault (no stay); an aim's floor scan says what L3 says, the kernel's point
    kept where L3 stands there too (on A), L3's own scan where it doesn't (C: no floor); and a hold whose step L3's
    watchdog stops for time raises ``StepTimeout`` (no answer cached, AZ-813) each time, for a kernel candidate and an
    L3 outcome alike."""
    from devkit.reach import native as N
    from devkit.reach.engine import worker
    from devkit.reach.native import backend as KB
    for mod, name in ((runner, "run_job"), (runner, "summary"), (runner, "run_macros"), (aim, "run_macros"),
                      (aim, "floor"), (aim, "other_starts"), (hold, "replay"), (KB, "_held"), (KB, "_floor"),
                      (KB, "_others"), *_DRIVER):
        monkeypatch.setattr(mod, name, getattr(mod, name))
    worker.setup()
    KB.install({})
    rec = two_platforms[2][0]
    o = next(o for o in rec["outcomes"] if o["macro"].startswith("runjump"))
    st, on_c = rec["starts"][o["start"]], (2.0, 10.0, 10.0)
    stand = _Sim([A, B])
    row0 = stand.teleport((0.0, 2.0, 0.0), 0.0)
    b = KB.Base(row0, [stand.step() for _ in range(runner.SETTLE_START)][-1])
    ks = KB.KernelSim(stand, N.World(_quads(A, B, C), np.full(6, 0x8050, np.int32)), b)
    assert KB.stood(runner.place(ks, on_c, 0.0, 0), on_c)
    assert hold.replay(stand, dict(st, feet=list(on_c)), rec["heading"], dict(o, by="kernel"))["fault"] == "start"
    assert aim.floor(ks, (2.0, 2.0, 0.0), "t.Z000", 0.0, [0], _zone) == {"to": True, "placements": 1, "l3": "point"}
    assert aim.floor(ks, on_c, "t.Z002", 0.0, [0], _zone) | {"placements": 0} == \
        {"to": False, "placements": 0, "l3": "scan"}
    assert aim.other_starts(ks, on_c, 0.0, (2.0, 2.0, 0.0), "t.Z002", [0], _zone) == ([], 0)

    class _Stops(_Sim):             # the jump press runs past L3's watchdog
        def step(self, pad=l3.Pad(), writes=()):
            if "y" in pad.buttons:
                raise l3.L3Error("stopped at runaway@0x8a000", "runaway@0x8a000")
            return super().step(pad, writes)
    stops = _Stops([A, B, C])
    for by in ("kernel", "kernel", "l3", "l3"):
        with pytest.raises(worker.StepTimeout):
            hold.replay(stops, st, rec["heading"], dict(o, by=by))


def test_the_c_controllers_give_the_python_controllers_records_and_kernel_counts(monkeypatch):
    """Step R2.19p: ``controllers.c`` (``backend.c_launches``, one C call a launch family) gives each family of the
    table on the kernel over the three platforms the records ``macros.launches`` gives under the Python controllers
    (``AZURIK_REACH_CONTROLLERS=py``): R0's fan (two of its launches play the kernel's lip clip), an aim's seven,
    the refinement's (roll jumps, which the kernel flags to L3, and a recast), R0's at a target the fan's walk-off
    can't reach, and ``aim.Aim`` and ``aim.Sched`` at B with and without home, short of it and on the envelope's
    schedule, from a run-up and a standing start. Every outcome (the pads as the witness's segments, ends, landings,
    first touch-downs, takeoffs, flaps) and kernel count is the same; the hypot it ports is CPython's (libm's
    differs), the libm calls it makes are CPython's bit for bit (Step 4.37j: on Windows zig links its own sin and
    cos ahead of the UCRT's, which CPython calls, so the stick parted in the last bit), and the Python sources it
    copies are as it pins them."""
    import ctypes
    import random

    from devkit.reach import native as N
    from devkit.reach.engine import macros
    from devkit.reach.native import backend as KB
    lib, rng = N.build(), random.Random(23)
    for _ in range(5_000):
        x, y = rng.uniform(-8.0, 8.0), rng.uniform(-8.0, 8.0)
        for f, (name, want) in enumerate((("sin", math.sin(x)), ("cos", math.cos(x)), ("atan2", math.atan2(x, y)),
                                          ("pow", math.pow(abs(x), y)))):
            got = lib.c_libm(f, abs(x) if name == "pow" else x, y)
            assert got.hex() == want.hex(), f"controllers.c's {name} isn't CPython's at {x!r}, {y!r}: {got!r}"
    stand = _Sim([A, B, C])
    row0 = stand.teleport((0.0, 2.0, 0.0), 0.0)
    b = KB.Base(row0, [stand.step() for _ in range(runner.SETTLE_START)][-1])
    world = N.World(_quads(A, B, C), np.full(6, 0x8050, np.int32))
    east, target = -math.pi / 2, [14.5, 2.0, 0.0]
    takeoff, starts = [4.0, 2.0, 0.0], {"run": [[3.0, 2.0, 0.0]], "stand": [[3.7, 2.0, 0.0]]}
    short = aim.short_of(target, takeoff)
    table = [   # (macros, controller, target)
        (macros.R0, None, None),
        (aim.aims("runjump", "air3", 2), functools.partial(aim.Aim, home=None), target),
        (aim.aims("standjump", "k0", 0), functools.partial(aim.Aim, home=None), target),
        (aim.aims("runjump", "air3", 5), functools.partial(aim.Aim, home=target), target),
        (aim.aims("runjump", "air3", 1), functools.partial(aim.Aim, home=target), short),
        (aim.refine("runjump", "air3", 5), functools.partial(aim.Aim, home=None), target),
        ([m for m in aim.aims("runjump", "air3", 2) if not m.hold], functools.partial(aim.Sched, home=target,
                                                                                         sched=[6, 19]), target),
        (macros.R0, functools.partial(aim.Aim, home=None), [0.0, 30.0, 0.0])]
    got, ran, c_launches = {}, collections.Counter(), KB.c_launches

    def counted(*a):
        out = c_launches(*a)
        ran[KB.CONTROLLERS, out is not None] += 1
        return out
    monkeypatch.setattr(KB, "c_launches", counted)
    for how in ("py", "c"):
        monkeypatch.setattr(KB, "CONTROLLERS", how)
        recs = []
        for ms, ctl, at in table:
            KB._COST.clear()
            ks = KB.KernelSim(stand, world, b)
            rec = {"starts": {}, "outcomes": []}
            KB.run_macros(ks, rec, ms, east, takeoff, starts, [0], target=lambda m, at=at: at, ctl=ctl)
            recs.append((rec, dict(KB._COST), ks.ticks))
        got[how] = recs
    assert got["c"] == got["py"] and ran["c", True] >= len(table) and not ran["c", False]
    outs = [o for rec, _, _ in got["c"] for o in rec["outcomes"]]
    assert len(outs) == sum(len(ms) for ms, _, _ in table) and {o["by"] for o in outs} == {"kernel", "l3"}
    assert {"settled", "unsettled", "air cap"} <= {o["end"] for o in outs} and max(o["flaps"] for o in outs) == 5
    assert "roll" in {why for _, cost, _ in got["c"] for why in cost.get("why", {})}
    rng = random.Random(19)
    for _ in range(20_000):
        v = [rng.uniform(-1.0, 1.0) * 10.0 ** rng.randint(-8, 4) for _ in range(rng.choice((2, 3)))]
        assert lib.c_hypot(len(v), ctypes.byref((ctypes.c_double * 3)(*v))) == math.hypot(*v)
    assert KB.stale() == []


def test_the_c_controllers_build_steps_the_kernel_as_kernel_c_alone_does(tmp_path, monkeypatch):
    """Step R2.19p: ``controllers.c`` turns floating-point contraction off for its own code only (the pragma after
    its ``#include "kernel.c"``; ``reach_native.FLAGS`` name no contraction), so the kernel built with the
    controllers steps a body as ``kernel.c`` built alone with the same flags (R2.19f+'s build) does: every row and
    every field of the last state of a body run, jumped and flapped over the three platforms are the same bit for
    bit. ``-ffp-contract=off`` on the whole build had moved 11-22 % of a level's kernel records off the parent's and
    lost finds against it; here it moves the contact normal."""
    import ctypes
    import importlib.util
    import os
    import subprocess

    from devkit.reach import native as N
    assert not any(f.startswith("-ffp-contract") for f in N.FLAGS)
    built, so, zc = N.build(), tmp_path / "kernel-alone.so", str(N._cache() / "zig-cache")
    subprocess.run([str(Path(importlib.util.find_spec("ziglang").origin).with_name("zig")), "cc", *N.FLAGS, "-o",
                    str(so), str(N.SRC.with_name("kernel.c"))],
                   env=os.environ | {"ZIG_GLOBAL_CACHE_DIR": zc, "ZIG_LOCAL_CACHE_DIR": zc}, check=True,
                   capture_output=True)
    alone = ctypes.CDLL(str(so))
    for name in ("w_new", "w_free", "p_run"):
        f, g = getattr(alone, name), getattr(built, name)
        f.argtypes, f.restype = g.argtypes, g.restype

    def runs(lib):
        monkeypatch.setattr(N, "build", lambda: lib)
        world, got = N.World(_quads(A, B, C), np.full(6, 0x8050, np.int32)), []
        for k in range(12):
            p = N.player((0.0, 2.0, 0.9), (0.0, 0.0, 0.0), 0, (0.0, 0.0, 1.0), flaps_max=3)
            pads = [N.Pad(0.9 * math.cos(0.3 * k + 0.02 * t), 0.9 * math.sin(0.3 * k + 0.02 * t),
                          -math.sin(0.1 * k), math.cos(0.1 * k), N.Y if t - k in (20, 21, 45, 70) else 0)
                    for t in range(140)]
            got.append(world.run(p, pads).tobytes())
            got += [ctypes.string_at(ctypes.addressof(p) + getattr(N.Player, f).offset, getattr(N.Player, f).size)
                    for f, _ in N.Player._fields_]
        return got
    assert runs(built) == runs(alone)


_BUILD_AT_ONCE = r"""
import ctypes, json, os, subprocess, sys, time, types
from pathlib import Path

import platformdirs

from devkit.reach import l3_fast, native

cache, which, me, other = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
replace = os.replace


def zig(argv, **kw):         # zig cc stood in: both compile before either installs, and "b" installs once "a" has
    Path(argv[argv.index("-o") + 1]).write_bytes(b"lib")             # loaded the build it installed
    (cache / f"compiled-{me}").touch()
    while not (cache / f"compiled-{other}").exists() or (me == "b" and not (cache / "loaded-a").exists()):
        time.sleep(0.01)
    return subprocess.CompletedProcess(argv, 0, "", "")


def windows_replace(src, dst):   # Windows won't replace a library another process has loaded (WinError 5)
    if Path(dst).exists() and any(cache.glob("loaded-*")):
        raise PermissionError(13, "Access is denied", str(src), None, str(dst))
    replace(src, dst)


class Lib:                   # ctypes.CDLL stood in: it names the file it loads
    def __init__(self, path):
        self.path = path
        (cache / f"loaded-{me}").write_text(path)

    def __getattr__(self, name):
        setattr(self, name, value := types.SimpleNamespace())
        return value


platformdirs.user_cache_dir = lambda *a, **k: str(cache)
subprocess.run, os.replace, ctypes.CDLL = zig, windows_replace, Lib
print(json.dumps((native.build() if which == "kernel" else l3_fast.step_lib()).path))
"""


@pytest.mark.parametrize("which", ["kernel", "step"])
def test_two_processes_building_one_c_library_into_an_empty_cache_at_once_both_load_its_one_build(which, tmp_path):
    """Step 4.37j: two pool workers that find the kernel (``native.build``) or FastL3's C step (``l3_fast.step_lib``)
    missing from the cache both compile it; the first installs and loads its build, and Windows refuses the second's
    install over a library a process has loaded (``PermissionError``, WinError 5; stood in here, as is zig cc), so
    the second drops its own build and loads the one installed (the same name: the same source and flags). Both
    load the one file, and no part file stays."""
    import subprocess
    import sys

    root, runs = Path(__file__).resolve().parents[1], []
    try:
        for me, other in (("a", "b"), ("b", "a")):
            runs.append(subprocess.Popen([sys.executable, "-c", _BUILD_AT_ONCE, str(tmp_path), which, me, other],
                                         cwd=root, env={**os.environ}, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True))
        outs = [p.communicate(timeout=120) for p in runs]
    finally:
        for p in runs:
            p.kill()
            p.wait()
    assert [(p.returncode, err) for p, (_, err) in zip(runs, outs)] == [(0, ""), (0, "")]
    built = [p for p in tmp_path.rglob("*") if p.is_file() and not p.name.startswith(("compiled-", "loaded-"))]
    assert len(built) == 1 and built[0].suffix == ".so" and built[0].read_bytes() == b"lib"
    assert [json.loads(out) for out, _ in outs] == [str(built[0])] * 2


def test_the_router_routes_a_witness_touching_a_mover_and_flags_one_passing_near_a_rig():
    """The mover-contact router (``reach_native.backend.Movers``, PLAN-v2 §1.5b) over a rig's deck (4 m square at
    z 0) and a toggled gate (a wall at x 10): a body standing on the deck is routed to the rig, one walking through
    the gate's place owes the gate, one 2 m off the deck's edge passes near the rig (near_parked_rig) and one 6 m off
    touches nothing."""
    from devkit.reach.native import backend as KB
    wall = [((10, -2, 0), (10, 2, 0), (10, 2, 3)), ((10, -2, 0), (10, 2, 3), (10, -2, 3))]
    M = KB.Movers(np.concatenate([_quads((0, 0, 4, 4, 0.0)), np.array(wall, float)]), [1, 1, 2, 2],
                  {1: "rig", 2: "gate"})
    on_deck = [(2.0, 2.0, 1.0)] * 3
    through = [(8.0 + 0.2 * k, 0.0, 1.5) for k in range(21)]
    assert M.route(on_deck) == {"rigs": [1], "gates": [], "near": []}
    assert M.route(through) == {"rigs": [], "gates": [2], "near": []}
    assert M.route([(x, 6.0, 1.0) for x in (1.0, 2.0, 3.0)]) == {"rigs": [], "gates": [], "near": [1]}
    assert M.route([(x, 10.0, 1.0) for x in (1.0, 2.0, 3.0)]) == {"rigs": [], "gates": [], "near": []}


def test_a_reach_model_pickled_here_loads_and_one_naming_a_modkit_module_or_any_other_global_is_refused():
    """Step 4.13f: the L3 store's reach models (``x7/reach``) are this checkout's pickles (Modkit's went, D1172):
    ``models.load`` takes the modules they name and the standard library's and numpy's few globals they hold, and
    refuses any other global by name, a Modkit module's too."""
    import io

    from azurkit.tools.randomizer.art import nodes as art_nodes
    from azurkit.tools.randomizer.planner import proofs as pr
    from devkit.reach import models

    here = (pr.zoning, art_nodes.Link, collections.Counter("ab"))
    assert models.load(io.BytesIO(pickle.dumps(here, protocol=0))) == here
    assert np.array_equal(models.load(io.BytesIO(pickle.dumps(np.arange(3.0), protocol=5))), np.arange(3.0))
    modkit = pickle.dumps(art_nodes.Link, protocol=0).replace(b"azurkit.tools.randomizer.art.nodes", b"azurik_mod.xbr.nodes")
    for blob, named in ((modkit, "azurik_mod.xbr.nodes.Link"), *((pickle.dumps(f, protocol=0), f"{f.__module__}.{f.__name__}")
                                                                for f in (shutil.rmtree, math.floor))):
        with pytest.raises(pickle.UnpicklingError, match=f"names {named}"):
            models.load(io.BytesIO(blob))


def test_every_reach_verb_prints_its_usage_on_help_and_exits_0(capsys):
    """Step 4.13d1: ``python -m devkit reach VERB --help`` prints the verb's usage and exits 0 for every verb,
    the positional ones (native-trace, native-census) too, and runs nothing."""
    import devkit.reach
    from devkit import __main__ as dk

    for verb in devkit.reach.VERBS:
        with pytest.raises(SystemExit) as stop:
            dk.main(["reach", verb, "--help"])
        assert stop.value.code == 0, verb
        assert "usage:" in capsys.readouterr().out, verb
