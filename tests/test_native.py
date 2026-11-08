"""The compiled kernels (D1009): each library is its sources' build
(``nativekit --check``), this platform's loads, and each kernel gives its
Python twin's answer bit for bit, here and as the side module under
Pyodide, over seeded random inputs (the reach's on the randomizer's own
tables too; the dress's every NaN a NaN); ``AZURKIT_NATIVE=0`` runs the
twin; each reach counts its path."""

from __future__ import annotations

import collections
import inspect
import json
import random
import re

import numpy
import pytest

import nativekit
from azurkit.core import native
from tests import _pyodide


_ONE_NODE = {"nodes": 1, "flags": 0, "locations": 1, "counters": 1, "start": 0, "rules": (("false",),),
             "items": (), "discs": frozenset(), "yields": (1,), "refund": ((-1, -1),), "forced": ((),),
             "forced_phys": ((),), "regions": (), "graphs": (native.Graph(((),)),)}


def _rule(rng: random.Random, count: int) -> int:
    return 1 if rng.random() < 0.35 else rng.randrange(count)


def _tables(rng: random.Random) -> native.Tables:
    """A random database's tables: nodes past one bitset word, rules with
    edge numbers, discs, refund keys, forced flags, regions, teleports."""
    n = rng.choice((1, 2, 7, 40, 70, 150, 300))
    nf, nl, nc, ni = rng.randint(0, 130), rng.randint(0, 90), rng.randint(1, 10), rng.randint(1, 8)
    big = 1 << 40
    rules = [("false",), ("true",)]
    for _ in range(rng.randint(5, 60)):
        k = rng.random()
        if k < 0.3:
            rules.append(("counter", rng.randrange(nc), rng.choice((-1, 0, 1, 1, 2, 3, 4, big, -big))))
        elif k < 0.5 and nf:
            rules.append(("flag", rng.randrange(nf)))
        elif k < 0.6:
            rules.append(("sum", rng.randint(0, 6), tuple(rng.randrange(nc) for _ in range(rng.randint(0, 3)))))
        else:
            rules.append((rng.choice(("and", "or")), tuple(rng.randrange(len(rules)) for _ in range(rng.randint(0, 3)))))
    nr, start = len(rules), rng.randrange(n)
    flags = (lambda most: tuple(rng.sample(range(nf), rng.randint(0, min(most, nf)))))

    def graph() -> native.Graph:
        locs = [(loc, rng.randrange(n), _rule(rng, nr)) for loc in range(nl) if rng.random() < 0.9]
        if rng.random() < 0.3:
            rng.shuffle(locs)
        home = rng.random()   # how often a node has a way back to the start (an escape that holds)
        return native.Graph(
            tuple(tuple((rng.randrange(n), _rule(rng, nr)) for _ in range(rng.choice((0, 1, 1, 2, 3))))
                  + (((start, _rule(rng, nr)),) if rng.random() < home else ()) for _ in range(n)),
            tuple((rng.randrange(nf), rng.randrange(n), rng.random() < 0.2, _rule(rng, nr))
                  for _ in range(rng.randint(0, 2 * nf))) if nf else (),
            tuple(locs),
            tuple((rng.randrange(n), rng.randrange(n), _rule(rng, nr), rng.randrange(nl))
                  for _ in range(rng.randint(0, 3))) if nl else (),
            _rule(rng, nr))
    return native.Tables(
        n, nf, nl, nc, start, tuple(rules),
        tuple(tuple((c, rng.choice((1, 1, 2, 3, 0, -1))) for c in rng.sample(range(nc), rng.randint(0, min(3, nc))))
              for _ in range(ni)),
        frozenset(c for c in range(nc) if rng.random() < 0.3),
        tuple(rng.choice((1, 1, 1, 2, 3)) for _ in range(nl)),
        tuple(tuple(rng.sample(range(nc), 2)) if nc > 1 and rng.random() < 0.15 else (-1, -1) for _ in range(nl)),
        tuple(flags(2) if rng.random() < 0.2 else () for _ in range(n)),
        tuple(flags(2) if rng.random() < 0.2 else () for _ in range(n)),
        tuple((rng.randrange(nl), tuple(rng.sample(range(n), rng.randint(1, min(5, n))))) for _ in range(rng.randint(0, 3)))
        if nl else (),
        tuple(graph() for _ in range(3)))


def _monotone_of(t: native.Tables) -> native.Tables:
    """``t`` made tables whose takes never make a rule false (reach.c's
    ``H_MONO``): every increment and yield at least 0 (1), its refund keys
    neither discs nor another's pending counter, and each pending counter
    read only in sums holding its key as often."""
    rows = [(k, p) for k, p in t.refund if k >= 0 and k != p and k not in t.discs]
    pends, keys = {p for _, p in rows}, collections.defaultdict(list)
    refund = tuple((k, p) if (k, p) in rows and k not in pends and p not in {k for k, _ in rows} else (-1, -1)
                   for k, p in t.refund)
    for k, p in refund:
        if k >= 0:
            keys[p].append(k)
    rules = tuple(("sum", r[2], (r[1], *keys[r[1]])) if r[0] == "counter" and r[1] in keys else
                  ("sum", r[1], (*r[2], *(k for c in r[2] for k in keys.get(c, ())))) if r[0] == "sum" else r
                  for r in t.rules)
    fields = {f: getattr(t, f) for f in native.Tables.__match_args__}
    return native.Tables(**fields | {"rules": rules, "refund": refund, "yields": tuple(max(1, y) for y in t.yields),
                                     "items": tuple(tuple((c, abs(inc)) for c, inc in item) for item in t.items)})


def _call(rng: random.Random, t: native.Tables) -> dict:
    phys = rng.randrange(3)
    got = rng.sample(range(t.locations), rng.randint(0, t.locations // 2)) if rng.random() < 0.3 else None
    return {"graph": rng.randrange(3), "phys": phys, "free": phys if rng.random() < 0.4 else rng.randrange(3),
            "counters": [rng.choice((0, 0, 1, 2, 3, 1 << 40)) for _ in range(t.counters)],
            "held": [rng.choice((0, 0, 1, 2)) for _ in range(len(t.items))],
            "flags": rng.sample(range(t.flags), rng.randint(0, min(5, t.flags))),
            "gives": [rng.randrange(-1, len(t.items)) for _ in range(t.locations)],
            "got": got, "late": rng.sample(got, rng.randint(0, len(got))) if got else [],
            "traps": rng.random() < 0.8, "log": rng.random() < 0.7,
            "take_got": got is not None and len(got) % 2 == 0}   # got's items taken first (no draw: the stream as before)


def _cases(seed: int, count: int):
    rng = random.Random(seed)
    for _ in range(count):
        t = _tables(rng)
        for _ in range(2):
            yield t, _call(rng, t)


def _answer(solved) -> dict:
    """A :class:`native.Solved` as JSON's types, its sets sorted."""
    return {k: sorted(v) if isinstance(v, frozenset) else [sorted(x) for x in v] if k.endswith("_log") else
            list(v) if isinstance(v, tuple) else v for k, v in vars(solved).items()}


_UNDER_PYODIDE = """
import json
from azurkit.core import native

def tup(x):
    return tuple(tup(v) for v in x) if isinstance(x, list) else x

answers = []
docs, dress = json.load(open(json.loads(ARGV)[0]))
for doc, call in docs:
    graphs = tuple(native.Graph(*tup(g)) for g in doc.pop("graphs"))
    t = native.Tables(**{k: tup(v) for k, v in doc.items()} | {"discs": frozenset(doc["discs"])}, graphs=graphs)
    answers.append(_answer(native._native(native.library(), t, **call)))
import random
from azurkit.tools.characters import decimate
rng = random.Random(1407)
cuts = [repr(decimate.decimate(_mesh(rng), 0.3, max_error=0.004)) for _ in range(3)]
json.dumps({"report": native.report(), "answers": answers, "dress": [_dress_answer(case) for case in dress],
            "cuts": cuts})
"""


def test_the_reach_kernel_gives_its_twins_answer_bit_for_bit_and_this_platforms_library_loads():
    lib = native.library()
    assert lib is not None and native.report()["library"] == native.target(), native.report()
    for t, call in _cases(1400, 300):
        assert native._native(lib, t, **call) == native._twin(t, **call)


def test_the_reach_kernels_shortcuts_on_tables_whose_takes_never_make_a_rule_false_give_its_twins_answer():
    """On ``H_MONO``'s tables (the randomizer's own are) an escape ends once
    it reaches a node of the round's backward search (Step 4.4bk): over
    seeded random tables made monotone, and those that aren't, reach.c's
    answer is its twin's bit for bit."""
    lib, kinds = native.library(), collections.Counter()
    for t, call in _cases(1406, 300):
        m = _monotone_of(t)
        kinds[native._monotone(t)] += 1
        assert native._monotone(m)
        for tables in (t, m):
            assert native._native(lib, tables, **call) == native._twin(tables, **call)
    assert kinds[True] and kinds[False], kinds


def test_the_reach_kernel_gives_its_twins_answer_on_the_randomizers_own_tables():
    """The planner's own tables (``Logic._tables`` of its database) under
    RS1's four option sets, each over seeded placements (the pool's items
    shuffled), kits, flags and tracker states: reach.c's answer is its
    twin's bit for bit, each round's log too."""
    from azurkit.tools.randomizer.planner.loader import kept_logic
    from azurkit.tools.randomizer.planner.settings import Settings
    logic, rng, lib = kept_logic(), random.Random(1403), native.library()
    spots = [x for x, lvl in sorted(logic.pool.items()) if lvl not in logic.db.stubs and x not in logic.guardian]
    for st in (Settings(0, "safe", {}), logic.db.defaults, Settings(2, "standard", {}),
               Settings(4, "frame_perfect", {})):
        nt = logic._tables(st)
        assert native._monotone(nt.tables), st
        for _ in range(6):
            stock = [logic.vanilla[x][0] for x in spots]
            rng.shuffle(stock)
            placement = dict(zip(spots, stock))
            held, counters = collections.Counter(), {}
            for name in sorted(logic.items):
                if rng.random() < 0.15:
                    logic._add(held, counters, name, rng.choice((1, 1, 2)))
            got = sorted(rng.sample(sorted(logic.pool), rng.randrange(len(logic.pool)))) if rng.random() < 0.4 else None
            c = [0] * nt.tables.counters
            for name, n in counters.items():
                c[nt.counter[name]] = n
            call = {"graph": nt.graphs[0], "phys": nt.graphs[1], "free": nt.graphs[2], "counters": c,
                    "held": [held[x] for x in nt.items],
                    "flags": [nt.flag[f] for f in rng.sample(sorted(logic.db.flags), rng.randint(0, 4))],
                    "gives": [nt.item.get(logic._item(x, placement), -1) for x in nt.locs],
                    "got": None if got is None else [nt.loc[x] for x in got],
                    "late": [nt.loc[x] for x in got or () if x in logic.guardian],
                    "traps": rng.random() < 0.8, "log": rng.random() < 0.5, "take_got": got is not None}
            assert native._native(lib, nt.tables, **call) == native._twin(nt.tables, **call), st


def test_the_fills_attempt_and_acceptance_kernels_give_their_twins_answers_on_the_randomizers_own_data(monkeypatch):
    """``native/fill.c`` (Step 4.4ci57, D1141): an attempt of the fill (``fill._Kernel.attempt``) is its twin's
    (``_Slots.attempt``): the placement, or the stuck reason and item, each repaired refusal and every note its
    ``_Count`` hears, in order, over a spread of settings, seed difficulties, seeds and attempts (each lean of
    ``difficulty.lean_mode`` among them) that reaches each of the kernel's paths (an own spot, a trade and one that
    fails, the lean and a lean where a rung misses a spot, a repair, its swap, its way in and its spots at the traps,
    its way in past a kept way out and Easy's earliest such spot first, a vault) and placed and stuck outcomes, Normal's
    attempts past today's among them; and a candidate's
    need and play at each rung, stopped or not (with play's notes), and its ``Judge.score``, are ``difficulty``'s."""
    from azurkit.core import progress
    from azurkit.tools.randomizer.planner import difficulty, fill
    from azurkit.tools.randomizer.planner.loader import kept_logic
    from azurkit.tools.randomizer.planner.settings import Settings
    logic, paths, outcomes, notes = kept_logic(), 0, set(), []
    real = native.attempt

    def spy(*a):
        nonlocal paths
        if not isinstance(out := real(*a), int) and out is not None:
            paths |= out[7]
        return out
    monkeypatch.setattr(native, "attempt", spy)
    monkeypatch.setattr(progress, "note", notes.append)

    class Heard(fill._Count):
        def __init__(self):
            super().__init__()
            self.calls = []

        def begin(self, n):
            self.calls.append(n)

        def __call__(self, placed, reach=False):
            self.calls.append((placed, reach))
    cases = [(logic.db.defaults, [("0", 0), ("0", 3), ("11", 3), ("2", 3), ("5", 0)]),
             (Settings(0, "safe", {}), [("4", 0)]), (Settings(4, "frame_perfect", {}), [("0", 0)]),
             (Settings(3, "hard", {}, seed_difficulty=3), [("0", 0), ("1", 3), ("1", 21)]),
             (Settings(3, "hard", {}, seed_difficulty=1), [("2", 0), ("3", 1), ("3", 11)]),
             (Settings(2, "standard", {}, seed_difficulty=2), [("4", 0), ("5", 2)]),
             (Settings(3, "hard", {}, frozenset({"fragments"}), seed_difficulty=3), [("31", 12), ("31", 4)]),
             (Settings(3, "hard", {}, frozenset({"powers"}), seed_difficulty=1), [("30", 0)]),
             (Settings(3, "hard", {}, frozenset({"powers"})), [("52", 20)]),
             (Settings(4, "frame_perfect", {}, seed_difficulty=2), [("15", 3), ("15", 0)])]
    for st, seeds in cases:
        run = fill._Run(logic, st)
        assert run.kernel.blob is not None, st
        for seed, k in seeds:
            answers = []
            for kernel in (False, True):
                heard, repaired = Heard(), []
                try:
                    got = (run.kernel.attempt(seed, k, heard, repaired) if kernel else run.slots.attempt(
                        st, run.reads, fill._streams(seed, k, run.digest), run.known, repaired, run.reaches, heard,
                        run.lean_at(k), run.past_at(k)), None, None)
                except fill._Stuck as exc:
                    got = (None, str(exc), exc.item)
                answers.append((got, repaired, heard.calls))
            assert answers[0] == answers[1], (st, seed, k)
            outcomes.add(answers[0][0][1].split(" for ")[0].split(":")[0] if answers[0][0][1] else "placed")
            if not run.level or (placement := answers[0][0][0]) is None:
                continue
            for rating in range(2, len(run.ladder) + 2):
                for stop in (None, 20, 0):
                    told = []
                    for kernel in (False, True):
                        notes.clear()
                        play = (run.kernel.play(placement, rating, stop) if kernel else
                                difficulty.play(logic, st, placement, rating, stop=stop, needed=True))
                        need = (run.kernel.need(placement, rating) if kernel else
                                difficulty.need(logic, st, placement, rating))
                        told.append((need, play and (play.need, play.stages), len(notes)))
                    assert told[0] == told[1], (st, seed, k, rating, stop)
            if (judge := run.judge) is not None:
                judged = judge.score(placement)
                monkeypatch.setattr(judge, "kernel", None)
                assert judged == judge.score(placement), (st, seed, k)
    assert (paths, outcomes) == (4095, {"placed", "no safe proven spot", "no safe spot", "the verify"}), (
        paths, outcomes)


def test_the_acceptance_kernels_play_keeps_every_stage_when_the_options_collect_one_spot_a_round():
    """A shaped candidate's play in the kernel (``fill._Kernel.play``, az_accept) holds its most stages, L + 2: on a
    chain of L spots the plan's options reach one a round (each spot's item opens the next, the last's is the victory)
    and the rung none, ``difficulty.play``'s stages are a 0, a 1 for each spot, then a 0."""
    from array import array
    from types import SimpleNamespace as NS

    from azurkit.tools.randomizer.planner import fill
    from azurkit.tools.randomizer.planner.difficulty import Play
    n, k = 3, fill._Kernel
    chain = native.Graph(((),), locations=tuple((i, 0, 1 + i if i else 1) for i in range(n)), victory=1 + n)
    t = native.Tables(1, 0, n, n, 0, (("false",), ("true",), *(("counter", i, 1) for i in range(n))),
                      tuple(((i, 1),) for i in range(n)), frozenset(), (1,) * n, ((-1, -1),) * n, ((),), ((),), (),
                      (chain, native.Graph(((),)), native.Graph(((),))))
    w = [k.MAGIC, k.VERSION, n, n, n, 1] + [0] * (k.HEAD - 6)   # fill.c's F_* head: L, I, the names, one graph
    w[7] = len(w)                                               # F_LOCS: each spot open (LF_OPEN), its own vanilla
    for i in range(n):
        w += [32, i] + [0] * 8
    w[8] = len(w)                                               # F_ITEMS: each a progression item, none held
    w += [0] * 5 * n
    w[13] = w[17] = w[21] = w[23] = len(w)                      # F_PROG, F_NONGEM (none), F_GUARD, F_GIVES: zeros
    w += [0] * (n + 1)
    kernel = object.__new__(k)
    kernel.blob, kernel.run, kernel._last = array("q", w), NS(ladder=(None,)), (None, None)
    spots, items = [f"s{i}" for i in range(n)], {f"x{i}": i for i in range(n)}
    kernel.tabs = [NS(tables=t, graphs=(0, 0, 0), locs=spots, item=items), NS(tables=t, graphs=(1, 1, 1))]
    assert kernel.play(dict(zip(spots, items)), 2, None) == Play(True, (0, *[1] * n, 0), ())


def test_the_side_module_under_pyodide_gives_the_twins_answer(pyodide, tmp_path, monkeypatch):
    cases = list(_cases(1401, 40))
    cases += [(_monotone_of(t), call) for t, call in cases[:30]]
    dress = list(_dress_cases(1405, 60))
    docs = [[{k: sorted(v) if k == "discs" else v for k, v in vars(t).items() if k in native.Tables.__match_args__}
             | {"graphs": [[*vars(g).values()] for g in t.graphs]}, call] for t, call in cases]
    (path := tmp_path / "cases.json").write_text(json.dumps([docs, dress]), encoding="utf-8")
    got = pyodide(str(path), python=inspect.getsource(_answer) + inspect.getsource(_dress_answer)
                  + inspect.getsource(_mesh) + _UNDER_PYODIDE, packages=(_pyodide.numpy(),))
    assert got["report"]["loaded"] and got["report"]["library"] == "emscripten-wasm32.so", got["report"]
    assert got["answers"] == json.loads(json.dumps([_answer(native._twin(t, **call)) for t, call in cases]))
    monkeypatch.setattr(native, "_LIB", (None, "the twins", None))
    with numpy.errstate(all="ignore"):
        assert got["dress"] == json.loads(json.dumps([_dress_answer(case) for case in dress]))
    from azurkit.tools.characters import decimate
    rng = random.Random(1407)
    assert got["cuts"] == [repr(decimate.decimate(_mesh(rng), 0.3, max_error=0.004)) for _ in range(3)]


def _dress_cases(seed: int, count: int):
    """Seeded random inputs of the dress's kernels, as JSON: a rig (each
    bone's parent before it), a clip's tracks over its bones and past them
    (one key, a zero-length segment, a held value, signed zeros, huge,
    infinite and float32-limit values; the first case's bone 0 one key at a
    NaN time), times inside and outside the keys, a linear bake's
    components and a sampled chain's, and two byte runs."""
    rng = random.Random(seed)

    def f():
        k = rng.random()
        return (rng.choice((0.0, -0.0, 1e-300, -1e300, 3.4028234663852886e38, float("inf"))) if k < 0.03 else
                rng.uniform(-1e6, 1e6) if k < 0.1 else rng.uniform(-2.0, 2.0))

    def keys():
        ts = sorted(rng.uniform(-0.5, 3.0) for _ in range(rng.choice((1, 2, 3, 5, 9, 30))))
        if len(ts) > 1 and rng.random() < 0.2:
            ts[1] = ts[0]
        return [[t, f(), f() if rng.random() < 0.9 else float("inf"),
                 rng.choice((f(), float("inf"), 3.5e38)) if rng.random() < 0.2 else f()] for t in ts]

    def comps():
        return {str(c): keys() for c in range(4) if rng.random() < 0.6}

    for i in range(count):
        n, m = rng.randint(1, 40), rng.randint(0, 30)
        bones = [[rng.randrange(-1, k) if k and rng.random() < 0.9 else -1, *([f() for _ in range(m)] for m in (4, 4, 4, 3))]
                 for k in range(n)]
        tracks = [[rng.randrange(n + 2), rng.randrange(10), keys()] for _ in range(rng.randint(0, 3 * n))]
        lin = comps()
        length = rng.uniform(0.05, 3.0)
        links = rng.randint(1, 4)
        chain = [comps() for _ in range(links)]
        old = bytes(rng.randrange(3) for _ in range(rng.choice((0, 1, 5, 300))))
        new = bytes(b if rng.random() < 0.8 else rng.randrange(3) for b in old[:rng.randint(0, len(old))])
        yield {"rays": _ray_cases(random.Random(seed * 1000 + i)),
               "bones": bones, "tracks": tracks + [[0, 3, [[float("nan"), 1.0, 0.0, 0.0]]]] * (not i),
               "times": [rng.uniform(-1.0, 4.0) for _ in range(rng.randint(1, 8))] + [k[0] for t in tracks[:3] for k in t[2]],
               "linear": [lin, [f() for _ in range(4)], [[f() for _ in range(4)] for _ in range(4)],
                          sorted({k[0] for ks in lin.values() for k in ks} | {rng.uniform(-1.0, 4.0)})],
               "chain": [chain, [f() for _ in range(4)], [f() for _ in range(4)],
                         sorted({0.0, length, *(rng.uniform(0.0, length) for _ in range(5)),
                                 *(k[0] for c in chain for ks in c.values() for k in ks if 0.0 <= k[0] <= length)}),
                         length],
               "runs": [old.hex(), (new + bytes(rng.randrange(3) for _ in range(rng.choice((0, 3))))).hex()],
               "boxes": [[[f() for _ in range(12)] for _ in range(rng.randint(0, 6))], f()],
               "skin": [[[rng.randrange(n) for _ in range(4)] for _ in range(m)], [[f() for _ in range(4)] for _ in range(m)],
                        [[[f() for _ in range(3)] for _ in range(4)] for _ in range(2 * m)],
                        [[[f() for _ in range(3)] for _ in range(3)] for _ in range(n)], [[f() for _ in range(3)] for _ in range(n)],
                        [[rng.uniform(-0.2, 0.2) for _ in range(3)] for _ in range(rng.randint(1, 9))]]}


def _ray_cases(rng: random.Random) -> list:
    """A round side's op fields and frame (each optional field given or
    not; a taper or a blend's span that divides by zero, which the twin
    raises; signed zeros) and the points its rays are asked through (its
    origin's own among them), as JSON: [op, side, origin, points]."""
    def u(lo=-0.4, hi=0.4):
        return rng.choice((0.0, -0.0)) if rng.random() < 0.05 else rng.uniform(lo, hi)

    def maybe(value):
        return value if rng.random() < 0.5 else None

    out = []
    for _ in range(3):
        radius = [rng.uniform(0.03, 0.4) for _ in range(4)]
        span = rng.random() < 0.05   # a span of zero width: the twin's ZeroDivisionError
        op = {"radius": radius, "blend": [rng.uniform(0.005, 0.1), rng.uniform(0.005, 0.1)],
              "taper": rng.choice((0.0, 0.0, rng.uniform(0.0, 0.9), 1.0)), "taper_in": rng.choice((0.0, rng.random())),
              "taper_back": rng.choice(([0.0, 0.0], [rng.random(), rng.choice((0.0, 0.2))])),
              "taper_low": rng.choice(([0.0, 0.0], [rng.random(), rng.choice((0.0, 0.2))])),
              "back": rng.choice((0.0, rng.uniform(0.05, 0.4))), "inner": rng.choice((0.0, rng.uniform(0.05, 0.4))),
              "drape": maybe([u(), u(), 0.3, 0.3 if span else 0.9, u(-1.0, 1.0)]), "ease": rng.choice((0.0, 0.05)),
              "inner_blend": maybe([rng.uniform(0.01, 0.1), 0.02, 0.02 if span else 0.08]),
              "gate": maybe([-0.5, rng.choice((-0.5, 0.5)) if span else 0.5]),
              "midline": maybe([-0.1, 0.1, 0.05, u(), 0.02][:rng.choice((3, 4, 5))]),
              "behind": maybe([0.0, 0.1, rng.uniform(0.1, 1.0), sorted([[u(), u()] for _ in range(rng.randint(0, 3))])]),
              "window": maybe([-0.3, -0.1, 0.1, 0.3])}
        frame = [[u(-1.0, 1.0) for _ in range(3)] for _ in range(3)]
        side = {"centre": [u() for _ in range(3)], "frame": frame, "rays": [u(-0.1, 0.1) for _ in range(6)],
                "inward_sign": rng.choice((-1.0, 1.0))}
        origin = maybe([0.0, u(), u()])
        start = [side["centre"][i] + side["rays"][0] * frame[1][i] + side["rays"][1] * frame[0][i]
                 + side["rays"][2] * frame[2][i] for i in range(3)] if origin is None else origin
        out.append([op, side, origin, [[u() for _ in range(3)] for _ in range(25)] + [start]])
    return out


def _dress_answer(case: dict) -> list:
    """Each dress kernel's answer to ``case`` (by the library when it's
    loaded, else the twins), every float its bits in hex and NaN as such."""
    import struct

    import numpy as np

    from azurkit.tools import characters
    from azurkit.tools.characters import _player_crossfade as fade
    from azurkit.tools.characters import jiggle
    from azurkit.tools.characters import retarget as rt
    from azurkit.tools.characters.characters import BoneRecord, _boxes

    def bits(x):
        if isinstance(x, (list, tuple)) or type(x).__name__ == "array":
            return [bits(v) for v in x]
        return "nan" if x != x else struct.pack("<d", x).hex()

    def engine(f, *a):   # a lone key at a NaN time: the twin looks for a second key
        try:
            return bits(f(*a))
        except IndexError:
            return "IndexError"

    def keyed(c):
        return {int(k): tuple(map(tuple, v)) for k, v in c.items()}

    bones = tuple(BoneRecord(f"b{k}", p, False, tuple(ra), tuple(jo), tuple(t), tuple(q), (1.0, 1.0, 1.0))
                  for k, (p, jo, q, ra, t) in enumerate(case["bones"]))
    rig = rt.Rig("r", bones, tuple((0.0, 0.0, 0.0) for _ in bones), tuple((0.0, 0.0, 0.0, 1.0) for _ in bones), ())
    clip = rt.Clip(1.0, tuple(rt.Track(t, c, tuple(map(tuple, k))) for t, c, k in case["tracks"]), ())
    lin, rest, m, ts = case["linear"]
    chain, a, c, cts, length = case["chain"]
    rows = [[t, *v] for t, *v in rt._linear_rows(keyed(lin), tuple(rest), m, ts)]
    rows += [[t, *v] for t, *v in rt._chain_rows(list(bones[:len(chain)]), [keyed(x) for x in chain], tuple(a),
                                                 tuple(c), cts, length)]
    pose = fade.sample(rig, clip, case["times"])
    skin = case["skin"]
    pts = {"B": np.array(skin[0], dtype=np.int64).reshape(-1, 4), "W": np.array(skin[1]).reshape(-1, 4),
           "U": np.array(skin[2][:len(skin[0])]).reshape(-1, 4, 3), "UN": np.array(skin[2][len(skin[0]):]).reshape(-1, 4, 3)}
    R, O = np.array(skin[3]), np.array(skin[4])
    from azurkit.tools.characters import mesh_edit as me

    rays = []
    for op, side, origin, points in case["rays"]:
        tup = (lambda v: None if v is None else tuple(v))
        behind = None if op["behind"] is None else (*op["behind"][:3], tuple(map(tuple, op["behind"][3])))
        o = me.RoundOp("b", tuple(op["radius"]), 0.0, tuple(op["blend"]), drape=tup(op["drape"]), ease=op["ease"],
                       inner=op["inner"], back=op["back"], taper=op["taper"], taper_in=op["taper_in"],
                       taper_back=tuple(op["taper_back"]), taper_low=tuple(op["taper_low"]),
                       midline=tup(op["midline"]), inner_blend=tup(op["inner_blend"]), gate=tup(op["gate"]),
                       behind=behind, window=tup(op["window"]))
        s = me._Placed("ops[0]", o, tuple(side["centre"]), tuple(map(tuple, side["frame"])), frozenset(),
                       rays=tuple(side["rays"]), origin=tup(origin), inward_sign=side["inward_sign"])
        for p in points:
            try:
                got = me._ray_at(tuple(p), s, s.origin)
                rays.append("None" if got is None else bits([*got[0], *got[1:]]))
            except ZeroDivisionError:
                rays.append("ZeroDivisionError")
    def springs():   # a spring's chain and the clear's body, as jiggle poses them (the engine model on them alone)
        chain = jiggle._chain(rig, len(bones) - 1)
        whole = jiggle._posed_all(rig, clip, [len(bones) - 1, 0])
        out = []
        for ks, one in ((chain, jiggle._posed(rig, clip, chain)), (whole.order, None)):
            got = jiggle._posed_at(rig, clip, ks, case["times"])
            if got is None:   # the twins'
                got = [{ks[-1]: one(t)} if one else whole(t) for t in case["times"]]
            out.append([[*g[k][0], *g[k][1]] for g in got for k in (ks[-1:] if one else ks)])
        return out
    return [rays, engine(springs),
            engine(rt.origins_at, rig, clip, case["times"]), engine(rt.pose, rig, clip, case["times"][0]), bits(rows),
            characters._runs(*map(bytes.fromhex, case["runs"])), bits(_boxes(*case["boxes"])),
            bits(pose[0].tolist()), bits(pose[1].tolist()), bits(fade._heights(rig, pose).tolist()),
            *(bits(jiggle._skinned(pts, R, O, normals=normals).tolist()) for normals in (False, True)),
            *(bits(x.tolist()) for x in jiggle._signed(np.asarray(skin[5]), jiggle._skinned(pts, R, O),
                                                       jiggle._skinned(pts, R, O, normals=True)))]


def test_the_dress_kernels_give_their_twins_answers_bit_for_bit(monkeypatch):
    """retarget's pose and origins, bake_clip's linear and sampled rows and
    the damage boxes, the crossfade's sample and heights, jiggle's skinning
    and signed distances and the
    character layer's byte runs (``native/dress.c``) equal their twins
    over seeded random inputs, every NaN a NaN (its sign and payload aren't
    held: the compiler may order an operation's two NaN inputs either way)."""
    cases, ran = list(_dress_cases(1404, 400)), collections.Counter()
    for name in ("origins", "linear", "chain", "boxes", "sample", "heights", "skinned", "signed", "runs", "ray"):
        monkeypatch.setattr(native, name, lambda *a, real=getattr(native, name), name=name, **k:
                            ran.update([name]) or real(*a, **k))
    assert native.report()["loaded"]
    with numpy.errstate(all="ignore"):   # case 0's sample is the twin's
        got = [_dress_answer(case) for case in cases]
    asked = sum(len(points) for case in cases for *_, points in case["rays"])
    assert ran == {"origins": 1597, "linear": 400, "chain": 400, "boxes": 400, "sample": 399, "heights": 400,
                   "skinned": 1600, "signed": 400, "runs": 400, "ray": asked}   # by the library but case 0's clip's
    assert 0 < sum(r == "ZeroDivisionError" for g in got for r in g[0]) < asked / 10   # some divide by zero
    monkeypatch.setattr(native, "_LIB", (None, "the twins", None))
    with numpy.errstate(all="ignore"):   # the twins' numpy on infinities
        assert got == [_dress_answer(case) for case in cases]


def _mesh(rng: random.Random):
    """A seeded LOD to cut: a jittered sheet (its edges a border) in two
    materials (their shared column locked), a UV seam (a point's two
    wedges), a two-sided patch (each triangle and its reverse twin) and a
    few skins over four bones."""
    from azurkit.tools.characters.body_codec import Group, Lod, Vertex, slot_code

    w, h = rng.randint(6, 14), rng.randint(6, 14)

    def vertex(x, y, u=0.0):
        a = rng.random()
        return Vertex((x * 0.05, y * 0.05, rng.uniform(-0.01, 0.01) if rng.random() < 0.7 else 0.0),
                      (a, 1.0 - a, 0.0, 0.0), (0.0, 0.0, 1.0), (x / w + u, y / h),
                      slots=(slot_code(rng.randrange(4)), slot_code(rng.randrange(4)), 0, 0))
    groups = []
    for g, (x0, x1) in enumerate(((0, w // 2), (w // 2, w))):
        verts, at = [], {}
        for y in range(h + 1):
            for x in range(x0, x1 + 1):
                at[x, y] = len(verts)
                verts.append(vertex(x, y))
        seam = {}
        for y in range(h + 1):   # a UV seam down the middle column of the first material
            if g == 0 and x0 < (x0 + x1) // 2 < x1:
                seam[y] = len(verts)
                verts.append(vertex((x0 + x1) // 2, y, 0.5))
        tris = []
        for y in range(h):
            for x in range(x0, x1):
                a, b, c, d = at[x, y], at[x + 1, y], at[x + 1, y + 1], at[x, y + 1]
                if g == 0 and x >= (x0 + x1) // 2 and seam:
                    a = seam.get(y, a) if x == (x0 + x1) // 2 else a
                    d = seam.get(y + 1, d) if x == (x0 + x1) // 2 else d
                tris += [(a, b, c), (a, c, d)]
        if g == 1:   # a two-sided patch: its first triangles' reverse twins
            tris += [(t[0], t[2], t[1]) for t in tris[:rng.randint(0, 6)]]
        groups.append(Group(list(range(4)), verts, tris, (g, 0)))
    return Lod(0, groups)


def test_the_decimators_collapses_cut_its_twins_lod_bit_for_bit(monkeypatch):
    """``native/decimate.c``'s collapse loop (Step 4.6c round 4) cuts the
    LOD its twin, ``decimate.decimate``'s loop, cuts: each group's vertices
    and triangles, to a ratio, a max_error, both and neither's stop, over
    seeded random sheets with borders, a seam, a locked material border and
    a two-sided patch."""
    from azurkit.tools.characters import decimate

    ran = collections.Counter()
    monkeypatch.setattr(native, "decimate", lambda *a, real=native.decimate: ran.update(["kernel"]) or real(*a))
    rng = random.Random(1406)
    cases = [(_mesh(rng), stop) for _ in range(12)
             for stop in ((0.5, None), (0.3, 0.004), (None, 0.002), (0.05, 0.02), (0.0, None))]
    assert native.report()["loaded"]
    got = [decimate.decimate(lod, ratio, max_error=error) for lod, (ratio, error) in cases]
    assert ran["kernel"] == len(cases)
    monkeypatch.setattr(native, "_LIB", (None, "the twins", None))
    want = [decimate.decimate(lod, ratio, max_error=error) for lod, (ratio, error) in cases]
    assert [repr(lod) for lod in got] == [repr(lod) for lod in want]
    assert any(decimate.drawn(a) < decimate.drawn(lod) for a, (lod, _) in zip(got, cases))


def test_azurkit_native_0_runs_the_twin(monkeypatch):
    monkeypatch.setenv("AZURKIT_NATIVE", "0")
    monkeypatch.setattr(native, "_LIB", None)
    t, call = next(_cases(1402, 1))
    assert native.library() is None and native.report()["why"] == "AZURKIT_NATIVE=0"
    assert native.solve(t, **call) == native._twin(t, **call)


@pytest.mark.parametrize("change, why", [
    ({"rules": (("false",), ("and", (1,)))}, "rule 1's child (an earlier rule): 1 is no id below 1"),
    ({"graphs": (native.Graph((((5, 0),),)),)}, "graph 0's edge from 0: 5 is no id below 1"),
    ({"yields": ()}, "yields: 0 rows for 1 locations"),
    ({"discs": frozenset({3})}, "discs: [3] name a counter that isn't"),
])
def test_tables_the_kernel_cant_read_are_refused_by_name(change, why):
    with pytest.raises(ValueError, match=f"^{re.escape(why)}"):
        native.Tables(**_ONE_NODE | change)


def test_a_reach_counts_the_path_that_answered_it_and_the_report_shows_the_count(monkeypatch):
    """With the library loaded, the twin still answers a rule deeper than
    the kernel's (``Tables.twin_only``) or a number past ``LIMIT``, in the
    tables or the call, or one its takes could grow past it (an increment
    times a yield, only where the location gives that item): ``report``
    shows that call; ``taken`` hands them over."""
    monkeypatch.setattr(native, "CALLS", collections.Counter())
    assert native.report()["loaded"]
    deep = (("false",), *(("and", (i,)) for i in range(native.DEPTH)))
    huge = {"items": (((0, native.LIMIT - 10),),), "yields": (2,)}
    for tables, call, path in (({}, {}, "kernel"),
                               ({}, {"counters": [native.LIMIT]}, "twin"),
                               ({"rules": deep}, {}, "twin"),
                               ({"rules": (("counter", 0, native.LIMIT),)}, {}, "twin"),
                               (huge, {"held": [0]}, "kernel"),
                               (huge, {"held": [0], "gives": [0]}, "twin")):
        before = native.report()["calls"]
        native.solve(native.Tables(**_ONE_NODE | tables), 0, 0, 0, flags=[],
                     **{"counters": [0], "held": [], "gives": [-1]} | call)
        assert native.report()["calls"] == before | {path: before[path] + 1}, (tables, call)
    assert native.taken() == {"kernel": 2, "twin": 4}
    assert native.report()["calls"] == {"kernel": 0, "twin": 0} and native.taken() == {}


def test_an_engine_process_whose_twin_answers_shows_in_its_servers_report_and_fails_the_perf_gate(monkeypatch):
    """The app's engine (``Spawned``) loads apart from the server whose
    ``sdk.catalog`` the page reads: here the server's library is loaded and
    the process it spawned runs the twin, its counts handed over with its
    answer and kept past its end. The perf gate's native assert fails it."""
    from azurkit.app import engine
    from scripts import perf
    report = native.report()
    assert report["loaded"]
    monkeypatch.setenv("AZURKIT_NATIVE", "0")   # read as the engine's process loads; this one has
    monkeypatch.setattr(native, "CALLS", collections.Counter())
    spawned = engine.Spawned()
    try:
        spawned.call("plan", {"seed": "azurkit", "share": "AZR-AAEA"})
    finally:
        spawned.close()
    report = native.report()
    assert report["loaded"] and report["calls"]["twin"] > 0 and report["calls"]["kernel"] == 0, report
    assert perf.native_failures({"app": [report]}, {"app": (report["library"], report["sha12"])}) == [
        f"native app: its Python twin answered {report['calls']['twin']} of the engine's reach calls"]


def test_nativekit_rebuilds_each_committed_library_to_its_bytes():
    assert nativekit.build(check=True) == []


def test_each_macos_library_leaves_room_after_its_load_commands_for_the_freezes_signature():
    """A freeze signs each library (``codesign``), adding a 16-byte
    LC_CODE_SIGNATURE after its load commands where it has none: with no
    room there (zig's default, and its x86_64 build is unsigned) that went
    over az_origins' first bytes, and the frozen app on an Intel Mac faulted
    at 0xf0000000 dressing keylord (run 41521288667)."""
    import struct

    for name in ("macos-arm64.dylib", "macos-x86_64.dylib"):
        data = (native.FOLDER / name).read_bytes()
        ncmds, size = struct.unpack_from("<2I", data, 16)
        at, first = 32, len(data)
        for _ in range(ncmds):
            cmd, step = struct.unpack_from("<2I", data, at)
            if cmd == 0x19:   # LC_SEGMENT_64: its sections' file offsets (0: a zero-fill one)
                for s in range(struct.unpack_from("<I", data, at + 64)[0]):
                    first = min(first, struct.unpack_from("<I", data, at + 72 + 80 * s + 48)[0] or first)
            at += step
        assert first - (32 + size) >= 16, (name, first - (32 + size))
