"""``python -m devkit rando restack [-j N] [--derive-check] [--no-goldens]``: bring the randomizer's data and goldens
up to date after a rebase or a change to the derive, the authoring or the database (Modkit's ``scripts/restack.py``
in AzurKit's form, Step 4.13c).

Run it in a lane worktree (it refuses the main checkout). In order, each step stopping the run when it fails (what
the earlier steps wrote stays, for the agent to read):

1. **derive**: each level whose derived file is stale (its ``_meta.stamp`` not ``export.stamp(level)``) derives
   again in ``-j N`` processes. ``--derive-check`` first runs ``derive --all --check`` instead, a full derivation,
   which also finds a derive-code change that didn't bump ``DERIVE_VERSION``;
2. **author** on every authored level (it writes only the files that differ). A level file it rewrites makes that
   level's stamp stale only when a part the derive reads changed (``export.derive_inputs``), so it derives again,
   and the two alternate until a derive changes nothing (at most :data:`ROUNDS` rounds);
3. **check**: the database loads with 0 errors;
4. **goldens**: ``scripts/record_goldens.py`` re-records the randomizer's (:data:`GOLDENS`; ``--no-goldens`` stops
   before them). A seed that no longer fills fails there, naming its case.

It runs at nice 15 (on Windows, which has no nice, below normal priority), as does every process it starts, so the
suite's gate gets the CPU first. It stages and commits
nothing: the agent reads ``git diff``, and a commit names each golden it changed. Exit codes: 0 done, 1 a step
failed, 2 usage.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUNDS = 3
NICE = 15
WINDOWS = sys.platform == "win32"
IDLE, BELOW_NORMAL = 0x40, 0x4000      # <winbase.h>'s priority classes: the lowest, and the one above it
GOLDENS = ("rando_plans.json", "pipelines.json", "europe/pipelines.json", "tracker.json")


class StepError(Exception):
    """A step failed; the message names it."""


def _run(step: str, *args: str) -> str:
    """Run ``args`` (a ``python`` command line from the checkout's root); its output, else :class:`StepError`."""
    r = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode:
        raise StepError(f"{step}: `{' '.join(args)}` exited {r.returncode}\n{r.stderr.strip()}")
    return r.stdout


def stale_levels() -> list[str]:
    """The levels whose derived file's stamp isn't the current one."""
    from devkit.rando.draft import export
    names = sorted(p.name.removesuffix(".json.gz") for p in export.DERIVED.glob("*.json.gz"))
    return [n for n in names if json.loads(export.read_text(export.path_of(n)))["_meta"]["stamp"] != export.stamp(n)]


def authored_levels() -> list[str]:
    """The levels whose authoring spec exists (every authored level, named together as author needs)."""
    from devkit.rando.draft.author import AUTHORING
    return sorted(p.stem for p in AUTHORING.glob("*.toml"))


def restack(jobs: int, derive_check: bool, goldens: bool) -> None:
    derive = ("-m", "devkit", "rando", "derive", "-j", str(jobs))
    if derive_check:
        _run("derive --check", *derive, "--all", "--check")
    for k in range(ROUNDS):
        if stale := stale_levels():
            _run("derive", *derive, *stale)
        out = _run("author", "-m", "devkit", "rando", "author", *authored_levels())
        if out.startswith("0 of ") and not stale_levels():
            break
    else:
        if stale := stale_levels():
            raise StepError(f"author: still stale after {ROUNDS} rounds of derive and author: {', '.join(stale)}")
    _run("check", "-m", "devkit", "rando", "check")
    if goldens:
        _run("goldens", "scripts/record_goldens.py", *GOLDENS)


def _kernel32():
    """Windows' kernel32, its handles typed as pointers."""
    import ctypes

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.GetPriorityClass.argtypes = [ctypes.c_void_p]
    k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    return k


def lower_priority() -> None:
    """This process at nice :data:`NICE` or lower, as each process it starts then is: from 0 or the gate's 10 to
    15, a lower priority left as it is. Windows has no nice (``os.nice`` is POSIX's): its priority class goes below
    normal, an idle one left as it is, and a process it starts takes it."""
    if not WINDOWS:
        os.nice(max(0, NICE - os.nice(0)))
        return
    k = _kernel32()
    me = k.GetCurrentProcess()
    if k.GetPriorityClass(me) != IDLE and not k.SetPriorityClass(me, BELOW_NORMAL):
        import ctypes
        raise ctypes.WinError(ctypes.get_last_error())


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="python -m devkit rando restack", description=__doc__.split("\n\n")[0])
    p.add_argument("-j", "--jobs", type=int, default=os.process_cpu_count() or 1, metavar="N",
                   help="the derive's processes (default: the CPU count)")
    p.add_argument("--derive-check", action="store_true", help="a full derive --all --check first")
    p.add_argument("--no-goldens", action="store_true", help="stop after the check")
    args = p.parse_args(argv)
    git = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-dir",
                          "--git-common-dir"],
                         capture_output=True, text=True)
    if git.returncode or len(set(map(os.path.realpath, git.stdout.split()))) != 2:
        print("ERROR: run restack in a lane worktree, not the main checkout", file=sys.stderr)
        return 2
    lower_priority()
    try:
        restack(args.jobs, args.derive_check, not args.no_goldens)
    except StepError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0
