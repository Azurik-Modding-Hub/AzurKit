"""Write Seed difficulty's rate table, ``data/forcing.json`` (:mod:`~azurkit.tools.randomizer.planner.difficulty`), from
a campaign of the fill over seeds "0".."29" at every Movement x Skips cell with a trick in it, at its default toggles,
nothing kept: for Standard, and Hard where the cell allows Hard, the share of kept plans that meet the promise
throughout and the share that meet it once, from Hard's plans the share needing Frame-perfect, and the seeds each pick
and the tier open a step-up in at the level's rating; the fragments-kept and powers-kept rows at Hard/Hard.
A database change re-runs it (the test that holds the table to the database's digest and the skips' tag names it); any
re-run that changes a number bumps ``SEED_DIFFICULTY_FILL``.

    uv run --locked python scripts/seed_forcing.py [--check] [--workers N]
    uv run --locked python scripts/seed_forcing.py --rows FILE --seeds N [--config NAME ...]

``--rows`` writes no table: one JSON line a plan at the configs named (:data:`OP_CONFIGS` by default: what the perf
ops plan), its seed, attempt, candidates rejected, fill reaches and seconds, whether it meets the promise and needs its
rating: how the ops' seeds are named and the costs measured. The most plans any one open proven spot holds progression
in is printed beside each config's rates (the tell: a player learns such spots).
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import multiprocessing
import sys
import time

from azurkit.tools.randomizer.planner import difficulty as D
from azurkit.tools.randomizer.planner import fill as F
from azurkit.tools.randomizer.planner.loader import kept_logic
from azurkit.tools.randomizer.planner.settings import MOVEMENT_TIERS, Settings
from azurkit.tools.randomizer.planner.solver import Logic

SEEDS = 30
CEILINGS = (0, 2, 3, 4)
OP_CONFIGS = {    # the perf ops' settings (the design's sec. 4.3): (tier, ceiling, level, kept categories)
    "standard-ss": ("standard", 2, 2, ()), "standard-hh": ("hard", 3, 2, ()), "hard-hh": ("hard", 3, 3, ()),
    "hard-hs": ("hard", 2, 3, ()), "hard-hh-fragments": ("hard", 3, 3, ("fragments",)),
    "fp-ff": ("frame_perfect", 4, 4, ()), "hard-h0": ("hard", 0, 3, ())}


def _planned(logic: Logic, seed: str, st: Settings, ask: D.Ask | None = None) -> dict:
    """``seed``'s fill at the promise ``ask`` (throughout at the level's rating when ``None``; the table's own at the
    settings otherwise), with its reaches counted."""
    calls = [0]
    real = Logic.reach

    def counted(self, *args, **kw):
        calls[0] += 1
        return real(self, *args, **kw)

    Logic.reach = counted
    t0 = time.perf_counter()
    F.asked = (lambda settings, skips: ask) if ask is not None else D.asked
    try:
        made = F._fill(logic, seed, st)
    finally:
        Logic.reach = real
        F.asked = D.asked
    seconds = time.perf_counter() - t0
    return {"seed": seed, "attempt": made.attempt, "rejected": sum(": passed, but " in r for r in made.failed),
            "reaches": calls[0], "seconds": round(seconds, 3), "placement": made.placement}


def _measure(job: tuple) -> dict:
    """One config's plans and what each needs: at the promise the table asks there, or (``forced``, the table's own
    campaign, whatever it would ask) throughout at the level's rating."""
    tier, ceiling, level, kept, n, forced = job
    logic = kept_logic()
    st = Settings(ceiling, tier, 1, {}, frozenset(kept), seed_difficulty=level)
    ask = D.Ask(level, False, D.Fraction(1)) if forced else D.asked(st, logic.skip_tables)
    shape = D.Shape(logic, st, ask)
    rating = ask.rating
    rows, throughout, once, fp, openers, spots = [], 0, 0, 0, collections.defaultdict(set), collections.Counter()
    cls = {it["name"]: it["class"] for it in logic.db.items["item"]}
    placeable = F._Slots(logic, st).open_proven()
    for i in range(n):
        try:
            got = _planned(logic, str(i), st, ask)
        except F.FillError as exc:
            rows.append({"seed": str(i), "error": str(exc)[:200]})
            continue
        pl = got.pop("placement")
        needs = D.need(logic, st, pl, rating)
        meets = needs and shape.why_not(pl) is None
        throughout += meets
        once += needs
        allowed = max(MOVEMENT_TIERS.index(tier) + 1, ceiling)
        if allowed >= 4 and rating == 3:
            fp += D.need(logic, st, pl, 4)
        for opener in D.openers(logic, st, pl, rating) if forced else ():
            for name in {p.split(" (")[0] for p in opener["picks"]}:
                openers[name].add(i)
        spots.update(loc for loc in placeable if cls.get(pl[loc]) == "progression")
        rows.append(got | {"meets": bool(meets), "needs": bool(needs)})
    return {"key": D.cell_key(tier, ceiling), "level": level, "kept": list(kept), "throughout": throughout, "once": once,
            "fp": fp, "openers": {name: sorted(seeds) for name, seeds in sorted(openers.items())}, "rows": rows, "spot_max": max(spots.values(), default=0)}


def jobs(n: int) -> list[tuple]:
    out = []
    for tier in MOVEMENT_TIERS:
        for ceiling in CEILINGS:
            top = max(MOVEMENT_TIERS.index(tier) + 1, ceiling)
            out += [(tier, ceiling, level, (), n, True) for level in (2, 3) if level <= top]
    return out + [("hard", 3, level, (category,), n, True) for category in D.KEY_CATEGORIES for level in (2, 3)]


def _table(done: list[dict], logic: Logic, n: int) -> dict:
    cells: dict = {}
    kept: dict = {}
    for row in done:
        counts = {"throughout": row["throughout"], "once": row["once"]}
        if row["kept"]:
            kept.setdefault(row["kept"][0], {})[str(row["level"])] = counts
            continue
        cell = cells.setdefault(row["key"], {"openers": {}})
        cell[str(row["level"])] = counts
        cell["openers"][str(row["level"])] = row["openers"]
        if row["key"].startswith("frame_perfect/") or row["key"].endswith("/4"):
            if row["level"] == 3:
                cell["4"] = {"throughout": row["fp"], "once": row["fp"]}
    skips = logic.skip_tables
    return {"format": D.FORCING_FORMAT, "db_digest": F.db_digest(logic.db), "skips": D.skips_tag(skips),
            "seeds": n, "lines": {"rate": str(D.RATE_LINE), "say": str(D.SAY_LINE), "force": str(D.FORCE_LINE)},
            "cells": dict(sorted(cells.items())), "kept": dict(sorted(kept.items()))}


def _text(table: dict) -> str:
    return json.dumps(table, indent=1, sort_keys=True) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail when the table on disk isn't what the campaign writes")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--rows", help="write each plan's row to this file, and no table")
    ap.add_argument("--seeds", type=int, default=SEEDS)
    ap.add_argument("--config", action="append", help=f"with --rows: one of {', '.join(OP_CONFIGS)}")
    args = ap.parse_args()
    logic = kept_logic()
    if args.rows:
        names = args.config or list(OP_CONFIGS)
        todo = [(*OP_CONFIGS[name], args.seeds, False) for name in names]
    else:
        todo = jobs(SEEDS)
    with multiprocessing.get_context("spawn").Pool(args.workers) as pool:
        done = pool.map(_measure, todo, chunksize=1)
    for row in done:
        print(f"{row['key']} level {row['level']} kept {row['kept']}: throughout {row['throughout']} once {row['once']} "
              f"fp {row['fp']} of {args.seeds if args.rows else SEEDS}; the most any spot holds progression: "
              f"{row['spot_max']}", flush=True)
    if args.rows:
        with open(args.rows, "w", encoding="utf-8") as out:
            for name, row in zip(args.config or list(OP_CONFIGS), done):
                for plan in row["rows"]:
                    out.write(json.dumps({"config": name, **plan}) + "\n")
        return 0
    text = _text(_table(done, logic, SEEDS))
    if args.check:
        if D.FORCING.read_text(encoding="utf-8") != text:
            print("forcing.json isn't what the campaign writes", file=sys.stderr)
            return 1
        return 0
    D.FORCING.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
