"""``python -m devkit rando author LEVEL... [--check]``: write each level's file (``data/levels/``), its movement file
(``data/movement/``) and the arrivals of the stub levels' exits into them from its derived data, ``tricks.toml`` and
``devkit/rando/draft/authoring/<level>.toml`` (docs/RANDOMIZER_DB.md §4, §16), all or nothing (D35); Modkit's
``rando author`` (Step 4.13c).

Every authored level is named together (their exits arrive in each other's nodes). ``--check`` writes nothing and
exits 1 unless each file is current.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="python -m devkit rando author", description=__doc__.split("\n\n")[0])
    p.add_argument("levels", nargs="+", metavar="LEVEL",
                   help="every authored level, named together (all 22: a1 a3 a5 a6 airship d1 d2 e2 e5 e6 e7 f1 f2 "
                        "f3 f4 f6 life town w1 w2 w3 w4); one left out is named and nothing is written")
    p.add_argument("--check", action="store_true", help="write nothing; exit 1 unless every file equals its authoring")
    args = p.parse_args(argv)
    from devkit.rando.draft.author import author
    try:
        files, issues = author(list(args.levels))
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if issues:
        print("ERROR: the authoring is incomplete:\n" + "\n".join(f"  {i}" for i in issues), file=sys.stderr)
        return 1
    stale = sorted(p for p, text in files.items()
                   if not Path(p).is_file() or Path(p).read_text(encoding="utf-8") != text)
    if args.check:
        if stale:
            print(f"ERROR: not their authoring's output (re-run `python -m devkit rando author "
                  f"{' '.join(args.levels)}`): {', '.join(Path(p).name for p in stale)}", file=sys.stderr)
            return 1
        print(f"{len(files)} level files equal their authoring")
        return 0
    for p in stale:
        Path(p).parent.mkdir(exist_ok=True)
        Path(p).write_text(files[p], encoding="utf-8")
    print(f"{len(stale)} of {len(files)} level files written")
    return 0
