"""land: fast-forward ``main`` to a lane's branch once a passing receipt
covers its head (the twin of Modkit's ``land``).

    uv run --locked python scripts/land.py BRANCH [--repo PATH] [--dry-run]

It refuses unless BRANCH's head fast-forwards from main (an unborn main takes
any head), and when a commit it would land adds a byte literal holding a run
of either release's vanilla ``default.xbe`` or ``gamedata/config.xbr``
(``tests/_leak_guard.py``'s vanilla-run rule, run over each commit, not only
the head: a run a later commit removes stays in the history), naming the
commit, file, line and lengths, never the bytes. It reads both releases'
files from their images (``AZURKIT_ISO``, ``AZURKIT_ISO_EUROPE`` or the user
data folder). It
also needs a passing ``scripts/fullsuite.py`` receipt for that head's clean
tree, in which at least one vanilla and one europe test ran (D26): either a
whole-suite run, or a changed-area run whose base is main's head.

Then it moves main. In the worktree that has main checked out, that is a
fast-forward merge; otherwise it updates the ref from its old value. It removes
BRANCH's lane worktree and deletes BRANCH; if the main worktree has BRANCH
checked out, it switches that worktree to main first. Last, it appends a line
to the receipts' ``landings.log``.

The landing is local only: AzurKit has no remote until it goes public (D137).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import fullsuite as fs  # noqa: E402

from tests import _leak_guard  # noqa: E402


def receipt_for(folder: Path, head: str, main: str | None) -> dict | None:
    """The newest passing receipt that lets ``head`` land on ``main``."""
    found = []
    for meta in folder.glob("suite-*.meta"):
        m = json.loads(meta.read_text(encoding="utf-8"))
        if (m["head"] == head and m["clean"] and fs.status_code(m) == 0
                and (m.get("vanilla_run") or 0) >= 1 and (m.get("europe_run") or 0) >= 1
                and (m["mode"] == "full" or (main is not None and m["base"] == main))):
            found.append(m)
    return max(found, key=lambda m: m.get("finished_at") or "", default=None)


def vanilla_files() -> dict[str, bytes]:
    """Each release's vanilla ``tests/_leak_guard.py`` ``VANILLA_FILES``, read
    from its image and named by ``vanilla_named``; ``ValueError`` or
    ``OSError`` says which is missing or not vanilla."""
    from azurkit.core import gate, iso
    files = {}
    for release in gate.RELEASES:
        if (path := gate.find(release)) is None:
            raise ValueError(f"no {release.label} image: {gate.missing(release)}")
        with iso.Reader(path) as r:
            for rel in _leak_guard.VANILLA_FILES:
                data = r.read(rel)
                if [len(data), hashlib.sha256(data).hexdigest()] != release.files[rel]:
                    raise ValueError(f"{path}'s {rel} isn't the vanilla {release.label} one")
                files[release.label, rel] = data
    return _leak_guard.vanilla_named(files)


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


def land(repo: Path, branch: str, dry_run: bool = False) -> tuple[int, str]:
    """(exit code, what it did or why it refused)."""
    top = fs.git(repo, "rev-parse", "--verify", "-q", f"refs/heads/{branch}", check=False).strip()
    if not top:
        return 1, f"land: no branch {branch}"
    main = fs.git(repo, "rev-parse", "--verify", "-q", "refs/heads/main", check=False).strip() or None
    if main and fs.git(repo, "merge-base", main, top, check=False).strip() != main:
        return 1, f"land: {branch} ({top[:12]}) doesn't fast-forward from main ({main[:12]}): rebase it onto main"
    try:
        runs = _leak_guard.vanilla_runs_in_commits(repo, [top, *(("--not", main) if main else ())], vanilla_files())
    except (OSError, ValueError) as exc:
        return 1, f"land: the vanilla-run guard needs both images: {exc}"
    if runs:
        return 1, (f"land: {branch} ({top[:12]}) adds a run of vanilla bytes as a literal; read it from the "
                   f"player's image instead, and rewrite the commit that adds it:\n" + "\n".join(runs))
    folder = fs.receipts(repo)
    if (m := receipt_for(folder, top, main)) is None:
        return 1, (f"land: no passing clean receipt with vanilla and europe tests run for {branch} ({top[:12]}): "
                   f"run scripts/fullsuite.py on its worktree (receipts in {folder})")
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
