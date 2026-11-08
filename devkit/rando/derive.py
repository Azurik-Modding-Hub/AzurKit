"""``python -m devkit rando derive LEVEL... | --all [--check] [-j N] [--svg DIR] [--iso ISO]``: run the reach model
on each level and write its derived data, ``src/azurkit/tools/randomizer/data/derived/<level>.json.gz`` (Modkit's
``rando derive``, Step 4.13c).

``--all`` derives every committed one. The levels run in ``-j`` processes (default: the CPU count; ``-j 1`` runs them
in this one). ``--check`` writes nothing and exits 1 unless each committed file equals a fresh derivation; ``--svg
DIR`` also writes each level's per-tier pictures there. Nothing is written unless every level derives (D35).

:func:`router` is the harness-free half of Modkit's xemu route pilot: a level's reach model and route graph.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_DERIVE: dict = {}


def _derive_init(iso: str, db=None) -> None:
    """A derive worker's shared inputs, read once: the database, the node
    schema of the ISO's ``default.xbe`` and the movement envelope (kept:
    :meth:`~devkit.rando.draft.flights.Env.kept`)."""
    from azurkit.tools.randomizer.art import nodes
    from azurkit.tools.randomizer.planner.loader import load_database
    from azurkit.tools.randomizer.ports import XisoReader
    from devkit.rando.draft.flights import Env

    with XisoReader(Path(iso)) as rd:
        schema = nodes.Schema(bytes(rd.read_file("default.xbe")))
    _DERIVE.update(iso=Path(iso), db=db if db is not None else load_database(), schema=schema, env=Env.kept())


def _derive_one(name: str, svg: str | None) -> tuple[str, str, str]:
    """(level, its derived file's text, a one-line summary): the reach model
    on one level, in a worker :func:`_derive_init` set up."""
    import time

    from azurkit.tools.randomizer.draft.geometry import Level
    from devkit.rando.draft import export
    from devkit.rando.draft.reach import Reach

    t0 = time.process_time()
    r = Reach(Level.read(_DERIVE["iso"], name, _DERIVE["schema"]), _DERIVE["env"], db=_DERIVE["db"])
    doc = export.build_doc(r, export.stamp(name))
    text = export.dumps(doc)
    if svg is not None:
        from devkit.rando.draft.svg import render
        render(r, Path(svg))
    c = doc["counts"]
    return name, text, (f"{name}: {c['zones_output']} zones, {c['zone_edges']} zone edges, {len(doc['gates'])} gates, "
                        f"{len(doc['skips'])} held generated skips, {len(doc['locations'])} locations "
                        f"({time.process_time() - t0:.0f} s)")


def derive_levels(names: list[str], iso: Path, db, *, jobs: int, svg: Path | None = None):
    """Yield (level, text, summary) for each level as it finishes: in this
    process when ``jobs`` is 1, else in a pool of ``min(jobs, levels)``
    spawned processes, one level at a time while an xemu sitting waits for
    a slot (``BatchToken``, Step X.8).  Each level derives alone from the
    same inputs, so the texts equal the serial run's byte for byte; the
    first failure stops the workers and is raised."""
    svg_ = str(svg) if svg is not None else None
    if jobs == 1:
        _derive_init(str(iso), db)
        for name in names:
            yield _derive_one(name, svg_)
        return
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    from devkit.xemu.queue import BatchToken

    pool = ProcessPoolExecutor(min(jobs, len(names)), mp_context=multiprocessing.get_context("spawn"),
                               initializer=_derive_init, initargs=(str(iso),))
    try:
        with BatchToken("rando derive", min(jobs, len(names))) as tok:
            for f in tok.completed(pool, _derive_one, [(name, svg_) for name in names]):
                yield f.result()
    except BaseException:
        pool.terminate_workers()     # a failure (or an interrupt) stops the levels still running
        raise
    pool.shutdown()


def router(iso, level: str, prof: str = "logic", *, data=None):
    """The reach model of ``level`` (from ``iso``, the vanilla ISO) and its
    route graph for ``prof``; build once per sitting (minutes), keep it."""
    from azurkit.tools.randomizer.draft.geometry import Level
    from azurkit.tools.randomizer.planner.loader import load_database
    from devkit.rando.draft.reach import Reach
    from devkit.rando.draft.route import Router
    if _DERIVE.get("iso") != Path(iso):
        _derive_init(str(iso), load_database(data) if data else None)
    reach = Reach(Level.read(_DERIVE["iso"], level, _DERIVE["schema"]), _DERIVE["env"], db=_DERIVE["db"])
    return Router(reach, prof)


def _image(arg: str | None) -> Path:
    """The vanilla USA image (``--iso``, else the one the identity gate finds); ``FileNotFoundError`` where it
    looked."""
    from azurkit.core import gate
    if arg:
        return Path(arg)
    if (path := gate.find(gate.USA)) is None:
        raise FileNotFoundError(gate.missing(gate.USA))
    return path


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="python -m devkit rando derive", description=__doc__.split("\n\n")[0])
    p.add_argument("levels", nargs="*", metavar="LEVEL", help="playable levels to derive (e.g. w1 town)")
    p.add_argument("--all", action="store_true", help="every level with a committed derived file")
    p.add_argument("--check", action="store_true",
                   help="write nothing; exit 1 unless each committed file equals a fresh derivation")
    p.add_argument("-j", "--jobs", type=int, metavar="N",
                   help="derive the levels in N processes (default: the CPU count; 1: in this process)")
    p.add_argument("--svg", metavar="DIR",
                   help="also write each level's per-tier pictures into DIR (outside the repository: they show "
                        "geometry)")
    p.add_argument("--iso", help="the vanilla USA image (default: the one the identity gate finds)")
    args = p.parse_args(argv)
    try:
        import numpy  # noqa: F401
    except ModuleNotFoundError as exc:
        print(f"ERROR: derive needs {exc.name}: run `uv sync --locked`", file=sys.stderr)
        return 1
    from azurkit.core import gate
    from azurkit.tools.randomizer.planner.loader import DatabaseError, load_database
    from devkit.rando.draft import export
    from devkit.rando.draft.reach import SPAWN

    try:
        if args.all == bool(args.levels):
            raise ValueError("name the levels to derive, or --all (every committed derived file)")
        jobs = args.jobs if args.jobs is not None else (os.process_cpu_count() or 1)
        if jobs < 1:
            raise ValueError(f"-j {jobs}: at least one process")
        names = sorted(p.name.removesuffix(".json.gz") for p in export.DERIVED.glob("*.json.gz")) if args.all \
            else list(args.levels)
        unknown = [n for n in names if n not in SPAWN]
        if unknown:
            raise ValueError(f"not a playable level: {', '.join(unknown)} (one of {', '.join(sorted(SPAWN))})")
        iso = _image(args.iso)
        svg = Path(args.svg) if args.svg else None
        if svg is not None and svg.resolve() in (iso.resolve(), iso.resolve().parent):
            raise ValueError(f"--svg {svg}: not the image or its folder (D36)")
        gate.verify(iso, releases=(gate.USA,))
        db = load_database()     # here first, so a database error is named before any worker starts
        texts = {}
        for name, text, line in derive_levels(names, iso, db, jobs=jobs, svg=svg):
            texts[name] = text
            print(line, flush=True)
    except (OSError, ValueError, DatabaseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.check:
        old = {n: export.read_text(export.path_of(n)) if export.path_of(n).is_file() else None for n in names}
        stale = [n for n in names if old[n] != texts[n]]
        # the same stamp over a different text: the derive's code changed its output without a DERIVE_VERSION bump
        unbumped = [n for n in stale if old[n] is not None and
                    json.loads(old[n])["_meta"]["stamp"] == json.loads(texts[n])["_meta"]["stamp"]]
        if unbumped:
            print(f"ERROR: the derive's output changed under an unchanged stamp: {', '.join(unbumped)}; bump "
                  f"DERIVE_VERSION (devkit/rando/draft/export.py) and re-derive", file=sys.stderr)
        if stale:
            print(f"ERROR: stale derived data (re-derive with `python -m devkit rando derive {' '.join(stale)}`): "
                  f"{', '.join(stale)}", file=sys.stderr)
            return 1
        print(f"{len(names)} derived files equal a fresh derivation")
        return 0
    export.DERIVED.mkdir(exist_ok=True)
    for name in names:
        export.write_text(export.path_of(name), texts[name])
    print(f"{len(texts)} derived files written to {export.DERIVED}")
    return 0
