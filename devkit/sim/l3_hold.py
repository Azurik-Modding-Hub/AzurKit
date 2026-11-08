"""The L3 store's hold (AZ-720, Step X.83): the snapshots no cleanup deletes.

D658's disk cleanup deleted the start snapshot a running reach-engine run read by its bare label
(``--snapshot x7-w1-k0-205806``: the pool reads it once per worker, so ``lsof`` saw nothing open between jobs),
and every start snapshot main's ``proofs.jsonl`` names.  A snapshot (an ``.l3snap`` anywhere in the store) is held,
whatever its age, when it is:

- in the store's ``reach-live`` folder or a ``reach-live-*`` folder beside it (``reach-live-hold-<date>``, its
  APFS clone): the reach engine's per-level starts (``reach-live/README.txt``);
- named by a running process's command line, by its label (a bare word, as ``reach_engine.py run --snapshot
  LABEL`` takes it) or its file's path;
- the start of a ``proofs.jsonl`` record (``start.snapshot.label``) in a checkout given (by default this
  checkout's ``git worktree list``: the main checkout and its lanes, as prune's), so a proof's L3 replay re-runs
  on its own file (``python -m devkit reach l3-certify recheck``).

``$EV/tools/prune`` reads it (its R5 rows; ``--apply`` and ``--check`` refuse a path holding a held snapshot), and
any other cleanup of the store asks it first: ``uv run --locked python -m devkit sim l3-hold --check PATH ...``
exits 1 naming each held snapshot at or under a PATH.  Stdlib only (prune loads this file by its path).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SUFFIX = ".l3snap"               # devkit.sim.snapshot.SUFFIX (not imported: that module needs numpy)
LIVE = ("reach-live", "reach-live-*")
PROOFS = Path("src/azurkit/tools/randomizer/data/proofs.jsonl")
CHECKOUT = Path(__file__).resolve().parents[2]


def command_lines() -> list[str]:
    """Every running process's command line, whole (``ps -ww``), but this process's and its ancestors': a check's
    own command line (and its shell's) names what it checks."""
    rows = {}
    for line in subprocess.run(["ps", "-A", "-ww", "-o", "pid=,ppid=,command="], capture_output=True, text=True,
                               check=True).stdout.splitlines():
        pid, ppid, *cmd = line.split(None, 2)
        rows[int(pid)] = (int(ppid), cmd[0] if cmd else "")
    mine, pid = set(), os.getpid()
    while pid in rows and pid not in mine:
        mine.add(pid)
        pid = rows[pid][0]
    return [cmd for pid, (_, cmd) in rows.items() if pid not in mine]


def worktrees(checkout) -> list[Path]:
    """``checkout`` and every worktree of its repository (``git worktree list``: the main checkout and its lanes)."""
    out = subprocess.run(["git", "-C", str(checkout), "worktree", "list", "--porcelain"], capture_output=True,
                         text=True, check=True).stdout
    return [Path(line.removeprefix("worktree ")) for line in out.splitlines() if line.startswith("worktree ")]


def proof_starts(checkouts) -> dict[str, Path]:
    """Each snapshot label a ``proofs.jsonl`` record of ``checkouts`` starts from -> the first file naming it."""
    out: dict[str, Path] = {}
    for co in checkouts:
        path = Path(co) / PROOFS
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                label = json.loads(line)["start"]["snapshot"]["label"]
            except (ValueError, KeyError, TypeError):
                continue
            if isinstance(label, str):
                out.setdefault(label, path)
    return out


def held(store: str | Path, checkouts=(), commands: list[str] | None = None) -> dict[Path, str]:
    """Every held snapshot in ``store`` -> why (the module docstring); ``commands`` default to the running
    processes' command lines (:func:`command_lines`)."""
    store = Path(store)
    words = {w.rsplit("/", 1)[-1].removesuffix(SUFFIX)
             for line in (command_lines() if commands is None else commands)
             for w in re.split(r"[\s=,]+", line) if w}
    proofs = proof_starts(checkouts)
    out: dict[Path, str] = {}
    for path in sorted(store.rglob(f"*{SUFFIX}")):
        top, label = path.relative_to(store).parts[0], path.name.removesuffix(SUFFIX)
        if top != path.name and any(fnmatch.fnmatchcase(top, g) for g in LIVE):
            out[path] = f"in {top}/ (the reach engine's starts)"
        elif label in words:
            out[path] = "named by a running process"
        elif label in proofs:
            out[path] = f"a start {proofs[label]} names"
    return out


def blocking(paths, holds: dict[Path, str]) -> list[tuple[Path, str]]:
    """The held snapshots (``holds``, :func:`held`'s) at or under each of ``paths``: what deleting them would lose."""
    real = [(h.resolve(), h, why) for h, why in holds.items()]
    out = []
    for raw in paths:
        p = Path(raw).resolve()
        out += [(h, why) for r, h, why in real if r == p or p in r.parents]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m devkit sim l3-hold", description=__doc__.split("\n\n")[0])
    ap.add_argument("--store", help="the L3 store (default: devkit.sim.snapshot.store()'s)")
    ap.add_argument("--checkout", action="append", default=[],
                    help="a checkout whose proofs.jsonl starts are held (default: this checkout's worktrees, "
                         "the main checkout and its lanes)")
    ap.add_argument("--check", nargs="+", metavar="PATH",
                    help="exit 1 naming each held snapshot at or under a PATH (a cleanup asks this first)")
    a = ap.parse_args(argv)
    if a.store:
        store = Path(a.store)
    else:
        from devkit.sim.snapshot import store as default_store
        store = default_store()
    checkouts = [Path(c) for c in a.checkout] or worktrees(CHECKOUT)
    holds = held(store, checkouts)
    if a.check:
        hits = blocking(a.check, holds)
        for h, why in hits:
            print(f"held: {h} ({why})")
        print(f"{len(hits)} held snapshot(s) at or under {len(a.check)} path(s)"
              + (": delete none of them (AZ-720)" if hits else ""))
        return 1 if hits else 0
    by: dict[str, int] = {}
    for why in holds.values():
        by[why] = by.get(why, 0) + 1
    for why, n in sorted(by.items()):
        print(f"{n:5d} {why}")
    starts = proof_starts(checkouts)
    names = {p.name.removesuffix(SUFFIX) for p in store.rglob(f"*{SUFFIX}")}
    print(f"{len(holds)} held in {store}; proofs.jsonl names {len(starts)} start(s), {len(set(starts) & names)} "
          "of them in the store")
    return 0


if __name__ == "__main__":
    sys.exit(main())
