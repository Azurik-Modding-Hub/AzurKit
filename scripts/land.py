"""land: fast-forward ``main`` to a lane's branch once a passing receipt
covers its head (the twin of Modkit's ``land``).

    uv run --locked python scripts/land.py BRANCH [--repo PATH] [--dry-run]

It refuses unless BRANCH's head fast-forwards from main (an unborn main takes
any head) and a passing ``scripts/fullsuite.py`` receipt covers that head's
clean tree, in which at least one vanilla and one europe test ran (D26):
either a whole-suite run, or a changed-area run whose base is main's head
and whose flake stage, when it has one (the tests the stack added or edited,
run again and again slowed: ``fullsuite.flake_stage``), passed. A
stack that changes a file under ``src/`` or ``web/``, or another path the
perf stage times (``perf.select``: ``scripts/web_tools.py``, the perf gate's own driver and judge), also needs the
receipt's perf block (D981, ``scripts/perf.py``) with nothing blocking in it
(D1170, ``perf.blocking``, read from its verdicts whichever perf.py wrote
it): a clear regression against the last release's run, a memory peak, a
native failure or a list that grows; its debt rows (an op over its budget,
or new to the release and erring) block nothing. A receipt whose perf stage
was deferred (``fullsuite.py --perf-later``, the landing queue's: one perf
stage a batch, D1215's P1) takes that block from a later receipt of the batch
(:func:`cover_for`): a passing clean one whose head holds this one, whose
perf stage ran against main or a commit main holds (its ``perf_base``) and
timed every op this stack's changes reach, with nothing blocking. Every stack's
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
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import devlog  # noqa: E402
import fullsuite as fs  # noqa: E402
import perf  # noqa: E402

PERF_PATHS = ("src/", "web/")   # a stack touching these lands only with a perf block blocking nothing (D981, D1170)


def passing(folder: Path):
    """Each passing clean receipt in ``folder`` with vanilla and europe tests run (D26) and its flake stage, when
    it has one (the tests the stack added or edited, slowed), passed."""
    for meta in folder.glob("suite-*.meta"):
        m = json.loads(meta.read_text(encoding="utf-8"))
        if (m["clean"] and fs.status_code(m) == 0 and (m.get("vanilla_run") or 0) >= 1
                and (m.get("europe_run") or 0) >= 1 and fs.flake_passed(m)):
            yield m


def receipt_for(folder: Path, head: str, main: str | None, perf_block: bool = False,
                deferred: bool = False) -> dict | None:
    """The newest passing receipt that lets ``head`` land on ``main`` (with
    ``perf_block``, one with a perf block that blocks nothing, D1170; with
    ``deferred``, one whose perf stage waits for its batch's, D1215)."""
    found = [m for m in passing(folder) if m["head"] == head
             and (m["mode"] == "full" or (main is not None and m["base"] == main))
             and (not perf_block or not perf.blocking(m.get("perf"))) and (not deferred or fs.deferred(m))]
    return max(found, key=lambda m: m.get("finished_at") or "", default=None)


def _holds(repo: Path, older: str, newer: str) -> bool:
    """Whether ``newer``'s history holds ``older`` (git merge-base --is-ancestor)."""
    return subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", older, newer],
                          capture_output=True).returncode == 0


def cover_for(folder: Path, repo: Path, head: str, main: str, pairs: set[tuple[str, str]]) -> dict | None:
    """The newest receipt whose perf block covers ``head``'s landing on ``main`` (D1215's P1): a passing clean
    receipt of a later head that holds ``head``, its perf stage run (not deferred) against main or a commit main
    holds (``perf_base``), timing every ``(host, group)`` of ``pairs`` (what ``head``'s changes reach), and nothing
    in it blocking (``perf.blocking``)."""
    found = [m for m in passing(folder) if m["head"] != head and not fs.deferred(m) and m.get("perf_base")
             and isinstance((m.get("perf") or {}).get("cases"), dict) and not perf.blocking(m["perf"])
             and {f"{h}:{g}" for h, g in pairs} <= set(m["perf"].get("pairs") or [])
             and _holds(repo, m["perf_base"], main) and _holds(repo, head, m["head"])]
    return max(found, key=lambda m: m.get("perf_finished_at") or m.get("finished_at") or "", default=None)


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
    timed = any(rel.startswith(PERF_PATHS) for rel in paths.split()) or bool(perf.select(paths.split()))
    m, cover = receipt_for(folder, top, main, timed), None
    if m is None and timed and main and (own := receipt_for(folder, top, main, deferred=True)) is not None:
        if cover := cover_for(folder, repo, top, main, perf.select(paths.split())):
            m = own
    if m is None:
        return 1, (f"land: no passing clean receipt with vanilla and europe tests run"
                   f"{' and a perf block blocking nothing (the perf stage times it: D981, D1170), its own or, for '
                      'a deferred one (--perf-later), a later receipt of its batch covering it (D1215)' if timed else ''} "
                   f"for {branch} ({top[:12]}): run scripts/fullsuite.py on its worktree (receipts in {folder})")
    did = (f"main {main[:12] if main else '(unborn)'} -> {top[:12]} ({branch}; receipt {m['key']}, {m['mode']}"
           + (f"; its perf deferred, covered by receipt {cover['key']}'s" if cover else "") + ")")
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
