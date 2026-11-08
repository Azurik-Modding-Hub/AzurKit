"""Re-run the local L3 conformance corpus offline after an engine change (Step X.10).

Every xemu replay of an L3 string is kept in the private store's ``conformance.jsonl``
(``devkit.sim.corpus``); this runs each record's string in L3 again from its kept snapshot and compares the
new trace with xemu's: a record that passed and now diverges is a regression (exit 1).  It prints one
coordinate-free line per record (its snapshot label, mode, ticks, whether it passed then and now, where it
diverges now, the first tick L3's own trace changed) and the counts.  A build's record runs on the disc it was
replayed with (the path the corpus kept, or an image ``--disc`` names that hashes the same; AZ-380); one whose
disc is gone is ``missing`` by name.

    uv run --locked python -m devkit sim conformance [--store DIR] [--workers N] [--only LABEL ...] [--disc ISO ...]
        [--json PATH]

Dev tooling: never in pytest (the snapshots are private and local), never a CLI verb.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from devkit.sim import corpus


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--store", type=Path, default=None, help="the private snapshot store (default: the user data dir's)")
    ap.add_argument("--workers", type=int, default=0, help="a worker pool per snapshot (default: in this process)")
    ap.add_argument("--only", nargs="*", default=(), help="only the records of these snapshot labels")
    ap.add_argument("--disc", type=Path, nargs="*", default=(),
                    help="build images a record's disc may be now (matched by sha256[:12])")
    ap.add_argument("--json", type=Path, default=None, help="also write the results (coordinate-free) here")
    a = ap.parse_args(argv)
    from devkit.sim.ports import vanilla_iso
    from devkit.sim.ports import read_file
    results = corpus.rerun(read_file(str(vanilla_iso()), "default.xbe"), store=a.store, workers=a.workers,
                           only=set(a.only), discs=a.disc)
    for r in results:
        print(json.dumps(r), flush=True)
    counts = corpus.report(results)
    print(json.dumps(counts))
    if a.json:
        a.json.write_text(json.dumps({"results": results, "counts": counts}, indent=1) + "\n", encoding="utf-8")
    return 1 if counts["regressions"] else 0


if __name__ == "__main__":
    sys.exit(main())
