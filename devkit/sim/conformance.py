"""Re-run the local L3 conformance corpus offline after an engine change (Step X.10).

Every xemu replay of an L3 string is kept in the private store's ``conformance.jsonl``
(``devkit.sim.corpus``); this runs each record's string in L3 again from its kept snapshot and compares the
new trace with xemu's: a record that passed and now diverges is a regression (exit 1).  It prints one
coordinate-free line per record (its snapshot label, mode, ticks, whether it passed then and now, where it
diverges now, the first tick L3's own trace changed) and the counts.  A build's record runs on the disc it was
replayed with (the path the corpus kept, or an image ``--disc`` names that hashes the same; AZ-380); one whose
disc is gone is ``missing`` by name, and so is one whose snapshot was re-taken under its label (its ``meta_sha12``).
``--l3 fast`` runs the strings on FastL3 (``devkit.reach.l3_fast``, the reach engine's simulator) in a pool's
workers, on the patched libunicorn once ``devkit/reach/unicorn/build_unicorn.py`` has built it (its switches set in
this process's environment for the workers it spawns, as ``reach_engine.py --l3 fast`` does), else on the stock
wheel; ``--l3 base`` (the default) on L3 with the switches cleared.

    uv run --locked python -m devkit sim conformance [--store DIR] [--workers N] [--l3 {base,fast}] [--only LABEL ...]
        [--disc ISO ...] [--json PATH]

Dev tooling: never in pytest (the snapshots are private and local), never a CLI verb.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from devkit.sim import corpus


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--store", type=Path, default=None, help="the private snapshot store (default: the user data dir's)")
    ap.add_argument("--workers", type=int, default=0, help="a worker pool per snapshot (default: in this process)")
    ap.add_argument("--l3", choices=("base", "fast"), default="base",
                    help="the simulator: L3 (base, the default) or FastL3 (fast, which needs --workers)")
    ap.add_argument("--only", nargs="*", default=(), help="only the records of these snapshot labels")
    ap.add_argument("--disc", type=Path, nargs="*", default=(),
                    help="build images a record's disc may be now (matched by sha256[:12])")
    ap.add_argument("--json", type=Path, default=None, help="also write the results (coordinate-free) here")
    a = ap.parse_args(argv)
    if a.l3 == "fast" and not a.workers:
        ap.error("--l3 fast needs --workers N: the patched libunicorn loads only in a pool's new workers")
    from devkit.reach import l3_fast
    from devkit.sim.ports import vanilla_iso
    from devkit.sim.ports import read_file
    for k in ("LIBUNICORN_PATH", *l3_fast.SWITCHES):          # the pool's workers inherit this environment
        os.environ.pop(k, None)
    if a.l3 == "fast":
        os.environ.update(l3_fast.worker_env())
    results = corpus.rerun(read_file(str(vanilla_iso()), "default.xbe"), store=a.store, workers=a.workers,
                           only=set(a.only), discs=a.disc, fast=a.l3 == "fast")
    for r in results:
        print(json.dumps(r), flush=True)
    counts = corpus.report(results)
    print(json.dumps(counts))
    if a.json:
        a.json.write_text(json.dumps({"results": results, "counts": counts}, indent=1) + "\n", encoding="utf-8")
    return 1 if counts["regressions"] else 0


if __name__ == "__main__":
    sys.exit(main())
