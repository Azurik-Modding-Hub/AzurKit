"""The compiled kernels (D1009): each library is its sources' build
(``nativekit --check``), this platform's loads, and each kernel gives its
Python twin's answer bit for bit, here and as the side module under
Pyodide, over seeded random inputs (the reach's on the randomizer's own
tables too); ``AZURKIT_NATIVE=0`` runs the twin; each call counts its path."""

from __future__ import annotations

import collections
import inspect
import json
import random
import re

import pytest

import nativekit
from azurkit.core import native


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


def _call(rng: random.Random, t: native.Tables) -> dict:
    phys = rng.randrange(3)
    got = rng.sample(range(t.locations), rng.randint(0, t.locations // 2)) if rng.random() < 0.3 else None
    return {"graph": rng.randrange(3), "phys": phys, "free": phys if rng.random() < 0.4 else rng.randrange(3),
            "counters": [rng.choice((0, 0, 1, 2, 3, 1 << 40)) for _ in range(t.counters)],
            "held": [rng.choice((0, 0, 1, 2)) for _ in range(len(t.items))],
            "flags": rng.sample(range(t.flags), rng.randint(0, min(5, t.flags))),
            "gives": [rng.randrange(-1, len(t.items)) for _ in range(t.locations)],
            "got": got, "late": rng.sample(got, rng.randint(0, len(got))) if got else [],
            "traps": rng.random() < 0.8, "log": rng.random() < 0.7}


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
for doc, call in json.load(open(json.loads(ARGV)[0])):
    graphs = tuple(native.Graph(*tup(g)) for g in doc.pop("graphs"))
    t = native.Tables(**{k: tup(v) for k, v in doc.items()} | {"discs": frozenset(doc["discs"])}, graphs=graphs)
    answers.append(_answer(native._native(native.library(), t, **call)))
json.dumps({"report": native.report(), "answers": answers})
"""


def test_the_reach_kernel_gives_its_twins_answer_bit_for_bit_and_this_platforms_library_loads():
    lib = native.library()
    assert lib is not None and native.report()["library"] == native.target(), native.report()
    for t, call in _cases(1400, 300):
        assert native._native(lib, t, **call) == native._twin(t, **call)


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
                    "traps": rng.random() < 0.8, "log": rng.random() < 0.5}
            assert native._native(lib, nt.tables, **call) == native._twin(nt.tables, **call), st


def test_the_side_module_under_pyodide_gives_the_twins_answer(pyodide, tmp_path):
    cases = list(_cases(1401, 40))
    docs = [[{k: sorted(v) if k == "discs" else v for k, v in vars(t).items() if k in native.Tables.__match_args__}
             | {"graphs": [[*vars(g).values()] for g in t.graphs]}, call] for t, call in cases]
    (path := tmp_path / "cases.json").write_text(json.dumps(docs), encoding="utf-8")
    got = pyodide(str(path), python=inspect.getsource(_answer) + _UNDER_PYODIDE)
    assert got["report"]["loaded"] and got["report"]["library"] == "emscripten-wasm32.so", got["report"]
    assert got["answers"] == json.loads(json.dumps([_answer(native._twin(t, **call)) for t, call in cases]))


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
    tables or the call: ``report`` shows that call; ``taken`` hands them over."""
    monkeypatch.setattr(native, "CALLS", collections.Counter())
    assert native.report()["loaded"]
    deep = (("false",), *(("and", (i,)) for i in range(native.DEPTH)))
    for tables, counters, path in (({}, [0], "kernel"),
                                   ({}, [native.LIMIT], "twin"),
                                   ({"rules": deep}, [0], "twin"),
                                   ({"rules": (("counter", 0, native.LIMIT),)}, [0], "twin")):
        before = native.report()["calls"]
        native.solve(native.Tables(**_ONE_NODE | tables), 0, 0, 0, counters=counters, held=[], flags=[], gives=[-1])
        assert native.report()["calls"] == before | {path: before[path] + 1}, (tables, counters)
    assert native.taken() == {"kernel": 1, "twin": 3}
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
