"""``python -m devkit rando bench``: benchmark the randomizer planner's solver (Modkit's ``rando_bench.py``, its
Step R1.7; Step 4.13b).

Purpose: record what the solver costs, as a step exit records it (a timing
is never a pytest assertion, plan §3.7). It times, each over ``--runs``
runs, the median and the fastest:

- the shipped database (``src/azurkit/tools/randomizer/data``): the load with
  every check (``check_database``), the compile (``Logic``), one reach
  under the default options and a default-settings plan of
  ``--plan-seed`` (the fill with its retries and verify, trap gate
  included: §3.8's exit target, Step R1.12);
- a synthetic authored database of the plan's estimated size (§3.8: 300-600
  nodes, 1-2k edges, 1,418 locations; ``--nodes`` and ``--edges``): the
  same three.

The synthetic level is one ``authored`` level, ``s1``, built from
``--seed``: a corridor of rooms, each to the next and back, plus one-way
drops between random rooms; 12 element powers (3 of each element) on random
rooms and sapphires on the other 1,406 spots; latch buttons on random rooms.
A requirement only names powers and buttons that sit before both its ends
along the corridor, so the vanilla placement is beatable, and a room whose
way back needs a power found further on can't get back until then: the
escape closures the fast path and the cache are for. Victory is level 3 in
all four elements.

Contract: it reads nothing but the shipped database and writes the
synthetic one to a temporary directory it deletes; it needs no game files,
prints no game bytes, and its numbers depend on the machine and its load,
so a commit records them with the load (``uptime``) and at least 2 runs.

    uv run --locked python -m devkit rando bench [--nodes 600] [--edges 3200] [--runs 5] [--seed 1] [--plan-seed 42]
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import tempfile
import time
from pathlib import Path

from azurkit.tools.randomizer.planner.fill import fill
from azurkit.tools.randomizer.planner.loader import check_database
from azurkit.tools.randomizer.planner.solver import Logic

ELEMENTS = ("air", "water", "fire", "earth")
LOCATIONS = 1418
BUTTONS = 40
COUNTERS = ("air", "water", "fire", "earth", "disca", "discw", "discf", "disce", "discl",
            "obsidian", "sapphire", "emerald", "ruby", "diamond", "life", "staff", "ammo")


def synthetic(root: Path, nodes: int, edges: int, seed: int) -> None:
    """Write the synthetic database (the module docstring) under ``root``."""
    rng = random.Random(seed)
    room = [rng.randrange(nodes) for _ in range(len(ELEMENTS) * 3)]        # where each power copy sits
    powers = sorted(zip(room, [(e, k) for e in ELEMENTS for k in (1, 2, 3)]))
    buttons = sorted((rng.randrange(nodes), f"s1.b{i}") for i in range(BUTTONS))

    def requires(a: int, b: int, p: float) -> str:
        """A random need that sits before both ends, with chance ``p``."""
        if rng.random() >= p:
            return "true"
        lo = min(a, b)
        need = [f"{e}>={k}" for r, (e, k) in powers if r < lo] + [f"button:{x}" for r, x in buttons if r < lo]
        return rng.choice(need) if need else "true"

    lines = ['format = "azurik-rando-level/1"', 'level = "s1"', 'status = "authored"', 'route = ["s1/g0/r1"]']
    for i in range(nodes):
        lines += ["", "[[node]]", f'id = "s1_n{i}"', f'anchors = ["cell:C{i}"]']
        lines += ["start = true"] if i == 0 else ["hub = true"] if i == 1 else []

    def edge(a: int, b: int, kind: str, need: str) -> None:
        lines.extend(["", "[[edge]]", f'from = "s1_n{a}"', f'to = "s1_n{b}"', f'kind = "{kind}"',
                      f'requires = "{need}"'])

    for i in range(nodes - 1):
        edge(i, i + 1, "walk", requires(i, i + 1, 0.3) if i else "true")
        edge(i + 1, i, "walk", requires(i, i + 1, 0.3) if i else "true")
    for _ in range(max(0, edges - 2 * (nodes - 1))):
        a, b = rng.sample(range(nodes), 2)
        edge(a, b, "drop", requires(a, b, 0.5))
    for r, b in buttons:
        lines += ["", "[[button]]", f'id = "{b}"', f'at = "s1_n{r}"', 'mode = "latch"']
    (root / "levels").mkdir(parents=True)
    (root / "levels" / "s1.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    spots = [(r, f"power_{e}", "major") for r, (e, _) in powers]
    spots += [(rng.randrange(nodes), "sapphire", "gem") for _ in range(LOCATIONS - len(spots))]
    doc = {"_meta": {"date": "2026-10-12", "format": "azurik-rando-generated/1", "generator": "devkit rando bench",
                     "source": {"file": "none", "sha256_12": "000000000000", "size": 0}},
           "cells": [f"C{i}" for i in range(nodes)], "counts": {}, "graphs": [], "kind": "realm", "level": "s1",
           "locations": [{"cell": f"C{r}", "class": cls, "id": f"s1/g0/r{k + 1}", "item": item, "pool": True}
                         for k, (r, item, cls) in enumerate(spots)],
           **{kind: [] for kind in ("barriers", "bosses", "exits", "game_states", "geodes", "keylocks", "keylords",
                                    "latches", "obsidian_locks", "save_points", "seals", "spots", "teleporters")}}
    (root / "generated").mkdir()
    (root / "generated" / "s1.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    items = ['format = "azurik-rando-items/1"', "", "[counters]", *(f'{c} = "{c}"' for c in COUNTERS)]
    for e in ELEMENTS:
        items += ["", "[[item]]", f'name = "power_{e}"', f"counters = {{ {e} = 1 }}", 'class = "progression"']
    items += ["", "[[item]]", 'name = "sapphire"', "counters = { sapphire = 1 }", 'class = "filler"']
    (root / "items.toml").write_text("\n".join(items) + "\n", encoding="utf-8")
    victory = " & ".join(f"{e}>=3" for e in ELEMENTS)
    (root / "world.toml").write_text(
        f'format = "azurik-rando-world/1"\nstart = "s1_n0"\nhub = "s1_n1"\nvictory = "{victory}"\n'
        'starting_items = []\n\n[[trick]]\nname = "bskip"\ndescription = "barrier skips"\n', encoding="utf-8")
    (root / "tricks.toml").write_text(
        'format = "azurik-rando-tricks/1"\nowner_refs = ["bench"]\nmade = "devkit rando bench"\nskip = []\n\n'
        '[[trick]]\nname = "bskip"\ndescription = "barrier skips"\nmechanism = "bench"\nconfidence = "bench"\n'
        "evidence = []\n", encoding="utf-8")
    (root / "route.toml").write_text('format = "azurik-rando-route/1"\nstatus = "draft"\nlocation_steps = 0\n'
                                     "action_steps = 0\nreplay_problems = 0\nstep = []\n", encoding="utf-8")
    (root / "settings").mkdir()
    (root / "settings" / "defaults.toml").write_text(
        'format = "azurik-rando-settings/1"\nskip_ceiling = 0\nmovement_tier = "standard"\ndark_fire = 1\n\n'
        "[skip_override]\n", encoding="utf-8")


def timed(runs: int, call):
    """``call``'s median and fastest wall time over ``runs`` runs, and its last result."""
    times, result = [], None
    for _ in range(runs):
        t = time.perf_counter()
        result = call()
        times.append(time.perf_counter() - t)
    return statistics.median(times), min(times), result


def bench(name: str, root: Path | None, runs: int, plan_seed: str | None = None) -> None:
    args = () if root is None else (root,)
    load = timed(runs, lambda: check_database(*args))
    report = load[2]
    if report.issues:
        raise SystemExit(f"{name}: the database doesn't load: {[str(i) for i in report.issues][:5]}")
    compile_ = timed(runs, lambda: Logic(report.database))
    reach = timed(runs, compile_[2].reach)
    r = reach[2]
    for what, (median, fastest, _) in (("load", load), ("compile", compile_), ("reach", reach)):
        print(f"{name:10} {what:8} median {median * 1e3:9.1f} ms  fastest {fastest * 1e3:9.1f} ms")
    print(f"{name:10} reach: {len(r.nodes)} nodes, {len(r.safe)} safe, {len(r.traps)} traps, "
          f"{len(r.locations)} locations, victory {r.victory}")
    if plan_seed is not None:   # each run a fresh Logic, as one `rando plan` is
        median, fastest, f = timed(runs, lambda: fill(Logic(report.database), plan_seed))
        print(f"{name:10} {'plan':8} median {median * 1e3:9.1f} ms  fastest {fastest * 1e3:9.1f} ms  "
              f"(seed {plan_seed!r}, default settings, attempt {f.attempt}, compile included)")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m devkit rando bench", description=__doc__.split("\n\n")[0])
    ap.add_argument("--nodes", type=int, default=600)
    ap.add_argument("--edges", type=int, default=3200)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--plan-seed", default="42")
    a = ap.parse_args(argv)
    bench("shipped", None, a.runs, a.plan_seed)
    with tempfile.TemporaryDirectory(prefix="rando-bench-") as tmp:
        synthetic(Path(tmp), a.nodes, a.edges, a.seed)
        bench("synthetic", Path(tmp), a.runs)
    return 0
