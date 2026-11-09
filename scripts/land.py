"""land: fast-forward ``main`` to a lane's branch once a passing receipt
covers its head (the twin of Modkit's ``land``).

    uv run --locked python scripts/land.py BRANCH [--repo PATH] [--dry-run]

It refuses unless BRANCH's head fast-forwards from main (an unborn main takes
any head) and a passing ``scripts/fullsuite.py`` receipt covers that head's
clean tree, in which at least one vanilla and one europe test ran (D26):
either a whole-suite run, or a changed-area run whose base is main's head
and whose flake stage, when it has one (the tests the stack added or edited,
run again and again slowed: ``fullsuite.flake_stage``), passed. A
stack that changes a file under ``src/`` or ``web/`` also needs the
receipt's passing perf block (D981, ``scripts/perf.py``). Every stack's
``tests/perf_ceilings.toml`` only shrinks: it refuses one that adds an op, a
debt, a memory peak or an untimed op, or raises a ceiling, against main's
(``perf.check_list``; main without the file takes any, the first record, and
a browser the stack's perf.py times and main's doesn't may add its own once,
its first record: ``perf.new_browsers``, D994). It refuses a head whose
``docs/DEVLOG.md`` holds a bullet twice (``scripts/devlog.py``: the stale copy
a union merge keeps of a bullet its lane edited, Step 4.4dx1).
Landing never waits for a release (D1170): a release is a tag on a commit
that is on main (``release.yml`` checks that), cut whenever its tests pass,
and the perf list holds no release back (an op over its budget is a debt row).

Then it moves main. In the worktree that has main checked out, that is a
fast-forward merge; otherwise it updates the ref from its old value. It removes
BRANCH's lane worktree and deletes BRANCH; if the main worktree has BRANCH
checked out, it switches that worktree to main first. Last, it appends a line
to the receipts' ``landings.log``.

The landing is local only: AzurKit has no remote until it goes public (D137).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import devlog  # noqa: E402
import fullsuite as fs  # noqa: E402
import perf  # noqa: E402

PERF_PATHS = ("src/", "web/")   # a stack touching these lands only with a passing perf block (D981)


def receipt_for(folder: Path, head: str, main: str | None, perf_block: bool = False) -> dict | None:
    """The newest passing receipt that lets ``head`` land on ``main`` (with
    ``perf_block``, one whose perf block passed)."""
    found = []
    for meta in folder.glob("suite-*.meta"):
        m = json.loads(meta.read_text(encoding="utf-8"))
        if (m["head"] == head and m["clean"] and fs.status_code(m) == 0
                and (m.get("vanilla_run") or 0) >= 1 and (m.get("europe_run") or 0) >= 1
                and (m["mode"] == "full" or (main is not None and m["base"] == main))
                and fs.flake_passed(m)   # a changed run's flake stage (the tests the stack added or edited, slowed)
                and (not perf_block or (m.get("perf") or {}).get("passed") is True)):
            found.append(m)
    return max(found, key=lambda m: m.get("finished_at") or "", default=None)


def worktrees(repo: Path) -> list[tuple[Path, str | None]]:
    """``(path, branch)`` of each worktree, the main one first."""
    out, path = [], None
    for line in fs.git(repo, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = Path(line.removeprefix("worktree "))
            out.append((path, None))
        elif line.startswith("branch refs/heads/"):
            out[-1] = (path, line.removeprefix("branch refs/heads/"))
    return out


def perf_list(repo: Path, rev: str | None) -> dict | None:
    """``rev``'s ``tests/perf_ceilings.toml`` (:func:`perf.listed`), or None without one."""
    text = fs.git(repo, "show", f"{rev}:{perf.CEILINGS}", check=False) if rev else ""
    return perf.listed(text) if text else None


def land(repo: Path, branch: str, dry_run: bool = False) -> tuple[int, str]:
    """(exit code, what it did or why it refused)."""
    top = fs.git(repo, "rev-parse", "--verify", "-q", f"refs/heads/{branch}", check=False).strip()
    if not top:
        return 1, f"land: no branch {branch}"
    main = fs.git(repo, "rev-parse", "--verify", "-q", "refs/heads/main", check=False).strip() or None
    if main and fs.git(repo, "merge-base", main, top, check=False).strip() != main:
        return 1, f"land: {branch} ({top[:12]}) doesn't fast-forward from main ({main[:12]}): rebase it onto main"
    if twice := devlog.stale(fs.git(repo, "show", f"{top}:{devlog.LOG}", check=False)):
        return 1, f"land: {branch}'s developer log holds a bullet twice (Step 4.4dx1): " + "; ".join(twice)
    left = perf_list(repo, top) or perf.listed(None)
    new = perf.new_browsers(repo, main, top)   # each one's first record may add its own ops (D994)
    if grown := perf.check_list(left, perf_list(repo, main), new):   # any stack, list-only ones too (no perf stage)
        return 1, f"land: {branch}'s {perf.CEILINGS} grows main's list (D981): " + "; ".join(grown)
    folder = fs.receipts(repo)
    paths = fs.git(repo, "diff", "--name-only", main, top) if main else fs.git(repo, "ls-tree", "-r", "--name-only", top)
    timed = any(rel.startswith(PERF_PATHS) for rel in paths.split())
    if (m := receipt_for(folder, top, main, timed)) is None:
        return 1, (f"land: no passing clean receipt with vanilla and europe tests run"
                   f"{' and a passing perf block (it changes src/ or web/: D981)' if timed else ''} for {branch} "
                   f"({top[:12]}): run scripts/fullsuite.py on its worktree (receipts in {folder})")
    did = f"main {main[:12] if main else '(unborn)'} -> {top[:12]} ({branch}; receipt {m['key']}, {m['mode']})"
    if dry_run:
        return 0, f"land --dry-run: would move {did}"
    trees = worktrees(repo)
    home = trees[0][0]   # the main worktree: the lane's may be the one removed
    if holder := next((path for path, b in trees if b == "main"), None):
        fs.git(holder, "merge", "--ff-only", "--quiet", top)
    else:
        fs.git(home, "update-ref", "refs/heads/main", top, main or "0" * 40)
    for path, b in trees:
        if b == branch and path == home:
            fs.git(home, "switch", "--quiet", "main")
        elif b == branch:
            fs.git(home, "worktree", "remove", str(path))
    fs.git(home, "branch", "--quiet", "-D", branch)   # main holds it now
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "landings.log", "a", encoding="utf-8") as log:
        log.write(f"{fs.now()} {did}\n")
    return 0, f"land: moved {did}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="land", description=__doc__.split("\n\n")[0])
    ap.add_argument("branch")
    ap.add_argument("--repo", type=Path, default=Path.cwd())
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    code, text = land(args.repo, args.branch, args.dry_run)
    print(text, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
